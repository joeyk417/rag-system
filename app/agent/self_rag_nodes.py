from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from app.agent.self_rag_state import (
    GradeAnswer,
    GradeDocuments,
    GradeHallucinations,
    SearchQueries,
    SelfRAGState,
)
from app.core.providers.base import BaseLLMProvider, LLMUsage
from app.db.models import Tenant
from app.retrieval import retriever
from app.schemas.chat import Source, TokenUsage
from app.schemas.retrieval import RetrievedChunk

logger = logging.getLogger(__name__)

_Node = Callable[[SelfRAGState], Coroutine[Any, Any, dict[str, Any]]]
_Router = Callable[[SelfRAGState], Coroutine[Any, Any, str]]

MAX_ITERATIONS = 3
_MAX_CONTEXT_CHARS = 12_000


# ---------------------------------------------------------------------------
# Node factories
# ---------------------------------------------------------------------------


def make_retrieve_node(tenant: Tenant, provider: BaseLLMProvider) -> _Node:
    """Return an async node that retrieves docs for each query and deduplicates."""

    async def retrieve_node(state: SelfRAGState) -> dict[str, Any]:
        rewritten_queries = state.get("rewritten_queries", [])
        queries_to_search = rewritten_queries if rewritten_queries else [state["query"]]

        seen_ids: set[UUID] = set()
        deduped: list[RetrievedChunk] = []

        for sub_query in queries_to_search:
            docs = await retriever.retrieve(sub_query, tenant, provider)
            for doc in docs:
                if doc.chunk_id not in seen_ids:
                    deduped.append(doc)
                    seen_ids.add(doc.chunk_id)

        logger.info(
            "self_rag.retrieve",
            extra={
                "tenant": tenant.tenant_id,
                "n_queries": len(queries_to_search),
                "n_docs": len(deduped),
            },
        )
        return {"retrieved_docs": deduped}

    return retrieve_node


def make_grade_documents_node(tenant: Tenant, provider: BaseLLMProvider) -> _Node:
    """Return an async node that grades each chunk individually and filters irrelevant ones.

    Grading is permissive: only discard chunks that are clearly irrelevant
    ('erroneous retrievals'). Borderline chunks are kept.
    Fail-open: JSON parse errors keep the chunk.
    """

    system_prompt = (
        "You are a grader assessing whether a retrieved document is relevant to a user query. "
        "The goal is to filter out erroneous retrievals only — be permissive. "
        "If the document contains keywords or semantic meaning related to the query, grade it as relevant. "
        'Respond ONLY with valid JSON: {"binary_score": "yes"} or {"binary_score": "no"}'
    )

    async def grade_documents_node(state: SelfRAGState) -> dict[str, Any]:
        query = state["query"]
        docs: list[RetrievedChunk] = state.get("retrieved_docs", [])

        filtered: list[RetrievedChunk] = []
        usage: TokenUsage | None = state.get("usage")

        for doc in docs:
            user_message = f"Document:\n{doc.content}\n\nUser query: {query}"
            llm_usage: LLMUsage | None = None
            try:
                raw, llm_usage = await provider.generate(
                    system_prompt,
                    user_message,
                    response_format={"type": "json_object"},
                )
                grade = GradeDocuments.model_validate_json(raw)
                relevant = grade.binary_score == "yes"
            except (ValidationError, Exception) as exc:
                logger.warning(
                    "self_rag.grade_documents: parse error — keeping chunk",
                    exc_info=exc,
                    extra={"chunk_id": str(doc.chunk_id)},
                )
                relevant = True  # fail-open

            if relevant:
                filtered.append(doc)
            usage = _accumulate_usage(usage, llm_usage)

        logger.info(
            "self_rag.grade_documents",
            extra={
                "tenant": tenant.tenant_id,
                "total": len(docs),
                "kept": len(filtered),
            },
        )
        return {"retrieved_docs": filtered, "usage": usage}

    return grade_documents_node


def make_generate_node(tenant: Tenant, provider: BaseLLMProvider) -> _Node:
    """Return an async node that generates an answer with inline citations."""

    async def generate_node(state: SelfRAGState) -> dict[str, Any]:
        query = state["query"]
        docs: list[RetrievedChunk] = state.get("retrieved_docs", [])
        iteration = state.get("iteration_count", 0)

        context, sources = _build_context(docs)

        domain = (
            tenant.config.get("domain", "technical documents")
            if tenant.config
            else "technical documents"
        )
        system_prompt = (
            f"You are an expert assistant for {tenant.name}, specialising in {domain}. "
            "Answer the user's question using ONLY the provided document context. "
            "Write a comprehensive answer (200-300 words) in MARKDOWN format. "
            "Use ## headings for sections and **bold** for key terms where appropriate. "
            "Cite sources inline as [1], [2], etc., where each number refers to a retrieved document. "
            "End your answer with a ## Sources section listing all cited documents."
        )
        user_message = f"QUESTION: {query}\n\nDOCUMENT CONTEXT:\n{context}"

        llm_usage: LLMUsage | None = None
        answer = ""
        try:
            answer, llm_usage = await provider.generate(system_prompt, user_message)
        except Exception as exc:
            logger.warning("self_rag.generate: LLM error", exc_info=exc)
            answer = "I was unable to generate an answer based on the retrieved documents."

        usage = _accumulate_usage(state.get("usage"), llm_usage)
        logger.info(
            "self_rag.generate",
            extra={
                "tenant": tenant.tenant_id,
                "iteration": iteration + 1,
                "n_sources": len(sources),
            },
        )
        return {
            "answer": answer,
            "sources": sources,
            "usage": usage,
            "iteration_count": iteration + 1,
        }

    return generate_node


def make_transform_query_node(tenant: Tenant, provider: BaseLLMProvider) -> _Node:
    """Return an async node that decomposes the query into 1-3 focused sub-queries.

    Accumulates into rewritten_queries (never replaces) so the LLM can
    see previously tried queries and avoid repeating them.
    Fail-open: on parse error, appends the original query.
    """

    system_prompt = (
        "You are a query re-writer that decomposes a query into focused sub-queries "
        "optimised for vector-store retrieval. "
        "Break the original query into 1-3 specific, self-contained queries. "
        "Each query should target a single document, concept, or time period. "
        "Expand abbreviations and add domain context where helpful. "
        "Do NOT repeat any query that has already been tried. "
        'Respond ONLY with valid JSON: {"queries": ["<sub-query 1>", ...]}'
    )

    async def transform_query_node(state: SelfRAGState) -> dict[str, Any]:
        query = state["query"]
        previous: list[str] = state.get("rewritten_queries", [])

        context_parts = [f"Original query: {query}"]
        if previous:
            tried = "\n".join(f"  - {q}" for q in previous)
            context_parts.append(f"Previously tried queries (do not repeat):\n{tried}")
        context_parts.append(
            "Generate 1-3 focused sub-queries that target distinct aspects of the original query."
        )
        user_message = "\n\n".join(context_parts)

        llm_usage: LLMUsage | None = None
        new_queries: list[str] = []
        try:
            raw, llm_usage = await provider.generate(
                system_prompt,
                user_message,
                response_format={"type": "json_object"},
            )
            parsed = SearchQueries.model_validate_json(raw)
            new_queries = parsed.queries
        except (ValidationError, Exception) as exc:
            logger.warning(
                "self_rag.transform_query: parse error — appending original query",
                exc_info=exc,
            )
            new_queries = [query]

        accumulated = previous + new_queries
        logger.info(
            "self_rag.transform_query",
            extra={
                "tenant": tenant.tenant_id,
                "new_queries": new_queries,
                "total_queries": len(accumulated),
            },
        )
        # Note: usage from transform_query is not accumulated into state — routing
        # functions cannot update state, and this node's token cost is intentionally
        # excluded from the reported usage total to keep accounting simple.
        return {"rewritten_queries": accumulated}

    return transform_query_node


# ---------------------------------------------------------------------------
# Routing functions
# ---------------------------------------------------------------------------


def should_generate(state: SelfRAGState) -> str:
    """Conditional edge after grade_documents: route based on whether any docs remain."""
    return "generate" if state.get("retrieved_docs") else "transform_query"


def make_check_answer_quality(tenant: Tenant, provider: BaseLLMProvider) -> _Router:
    """Return an async routing function that grades hallucinations then answer completeness.

    1. Hallucination check: if not grounded → "generate" (retry with same docs)
    2. Answer quality check: if grounded but incomplete → "transform_query"
    3. Grounded + complete → "END"

    Note: LLM usage from these two grading calls is logged but not accumulated
    into state (routing functions cannot return state updates in LangGraph).
    """

    hallucination_system = (
        "You are a grader assessing whether an LLM generation is grounded in the retrieved facts. "
        "Give 'yes' if the answer is fully supported by the facts; 'no' if it contains information "
        "not found in or contradicted by the facts. "
        'Respond ONLY with valid JSON: {"binary_score": "yes"} or {"binary_score": "no"}'
    )

    answer_quality_system = (
        "You are a grader assessing whether an answer fully addresses a user query. "
        "Give 'yes' if the answer resolves the query; 'no' if it is incomplete or off-topic. "
        'Respond ONLY with valid JSON: {"binary_score": "yes"} or {"binary_score": "no"}'
    )

    async def check_answer_quality(state: SelfRAGState) -> str:
        # Safety guard: cap the generate retry loop
        if state.get("iteration_count", 0) >= MAX_ITERATIONS:
            logger.info(
                "self_rag.check_quality: max iterations reached — forcing END",
                extra={"tenant": tenant.tenant_id},
            )
            return "END"

        answer = state.get("answer", "")
        query = state["query"]
        context, _ = _build_context(state.get("retrieved_docs", []))

        # 1. Hallucination check
        try:
            raw, usage = await provider.generate(
                hallucination_system,
                f"Facts:\n{context}\n\nLLM Generation: {answer}",
                response_format={"type": "json_object"},
            )
            hall_grade = GradeHallucinations.model_validate_json(raw)
            grounded = hall_grade.binary_score == "yes"
        except (ValidationError, Exception) as exc:
            logger.warning(
                "self_rag.check_quality: hallucination parse error — assuming grounded",
                exc_info=exc,
            )
            grounded = True  # fail-open

        logger.info(
            "self_rag.hallucination_check",
            extra={"tenant": tenant.tenant_id, "grounded": grounded},
        )

        if not grounded:
            return "generate"  # retry generation with same docs

        # 2. Answer quality check
        try:
            raw2, usage2 = await provider.generate(
                answer_quality_system,
                f"User query: {query}\n\nAnswer: {answer}",
                response_format={"type": "json_object"},
            )
            ans_grade = GradeAnswer.model_validate_json(raw2)
            complete = ans_grade.binary_score == "yes"
        except (ValidationError, Exception) as exc:
            logger.warning(
                "self_rag.check_quality: answer quality parse error — assuming complete",
                exc_info=exc,
            )
            complete = True  # fail-open

        logger.info(
            "self_rag.answer_quality",
            extra={"tenant": tenant.tenant_id, "complete": complete},
        )

        return "END" if complete else "transform_query"

    return check_answer_quality


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _build_context(docs: list[RetrievedChunk]) -> tuple[str, list[Source]]:
    """Format retrieved chunks into a context string and extract Source citations."""
    parts: list[str] = []
    sources: list[Source] = []
    total_chars = 0

    for i, doc in enumerate(docs, 1):
        heading = f" — {doc.heading}" if doc.heading else ""
        label = f"[{i}] {doc.doc_number or 'N/A'} p.{doc.page_number}{heading}"
        block = f"{label}\n{doc.content}"

        if total_chars + len(block) > _MAX_CONTEXT_CHARS:
            remaining = _MAX_CONTEXT_CHARS - total_chars
            if remaining > 200:
                parts.append(f"{label}\n{doc.content[:remaining]}...")
            break

        parts.append(block)
        total_chars += len(block)
        relevance = round(max(0.0, 1.0 - doc.similarity_score), 4)
        sources.append(
            Source(
                doc_number=doc.doc_number,
                title=doc.title,
                page_number=doc.page_number,
                s3_key=doc.s3_key,
                score=relevance,
            )
        )

    return "\n\n".join(parts), sources


def _accumulate_usage(
    current: TokenUsage | None,
    new: LLMUsage | None,
) -> TokenUsage | None:
    """Add LLM token usage from a new call to the running total in state."""
    if new is None:
        return current
    if current is None:
        return TokenUsage(
            input_tokens=new.input_tokens,
            output_tokens=new.output_tokens,
            total_tokens=new.total_tokens,
        )
    return TokenUsage(
        input_tokens=current.input_tokens + new.input_tokens,
        output_tokens=current.output_tokens + new.output_tokens,
        total_tokens=current.total_tokens + new.total_tokens,
    )
