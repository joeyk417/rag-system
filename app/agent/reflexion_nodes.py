from __future__ import annotations

import json
import logging
from collections.abc import Callable, Coroutine
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from app.agent.reflexion_state import ReflexionAnswer, ReflexionState
from app.core.providers.base import BaseLLMProvider, LLMUsage
from app.db.models import Tenant
from app.retrieval import retriever
from app.schemas.chat import Source, TokenUsage
from app.schemas.retrieval import RetrievedChunk

logger = logging.getLogger(__name__)

_Node = Callable[[ReflexionState], Coroutine[Any, Any, dict[str, Any]]]

MAX_ITERATIONS = 3
_MAX_CONTEXT_CHARS = 12_000
_CHUNK_PREVIEW_CHARS = 800


# ---------------------------------------------------------------------------
# Node factories
# ---------------------------------------------------------------------------


def make_draft_node(provider: BaseLLMProvider) -> _Node:
    """Return an async node that generates the initial draft answer with reflection."""

    async def draft_node(state: ReflexionState) -> dict[str, Any]:
        query = state["query"]
        system_prompt = (
            "You are an expert research assistant. "
            "Generate an initial answer to the user's question. "
            "Be honest about gaps and uncertainties in your reflection. "
            "Produce 1-3 specific, focused sub-queries to retrieve supporting evidence. "
            "Each sub-query should target a distinct aspect of the question. "
            "Respond ONLY with valid JSON matching: "
            '{"answer": "<250-300 word markdown answer>", '
            '"reflection": "<what information is still missing or uncertain>", '
            '"search_queries": ["<sub-query 1>", ...], '
            '"is_complete": false}'
        )
        user_message = (
            f"QUESTION: {query}\n\n"
            "Generate an initial answer, identify gaps, and produce targeted retrieval sub-queries."
        )

        llm_usage: LLMUsage | None = None
        try:
            raw, llm_usage = await provider.generate(
                system_prompt,
                user_message,
                response_format={"type": "json_object"},
            )
            parsed = ReflexionAnswer.model_validate(json.loads(raw))
        except (json.JSONDecodeError, ValidationError, Exception) as exc:
            logger.warning("reflexion.draft: parse error — using fallback", exc_info=exc)
            parsed = ReflexionAnswer(
                answer="I need to retrieve information to answer this question.",
                reflection="Initial retrieval required.",
                search_queries=[query],
                is_complete=False,
            )

        # Guard: no queries → force complete to prevent infinite loop
        if not parsed.search_queries:
            parsed.is_complete = True

        usage = _accumulate_usage(state.get("usage"), llm_usage)
        logger.info(
            "reflexion.draft",
            extra={"query": query, "n_queries": len(parsed.search_queries)},
        )
        return {
            "answer": parsed.answer,
            "reflection": parsed.reflection,
            "search_queries": parsed.search_queries,
            "is_complete": parsed.is_complete,
            "iteration_count": 1,
            "usage": usage,
        }

    return draft_node


def make_retrieve_node(tenant: Tenant, provider: BaseLLMProvider) -> _Node:
    """Return an async node that retrieves docs for each sub-query and deduplicates."""

    async def retrieve_node(state: ReflexionState) -> dict[str, Any]:
        search_queries = state.get("search_queries", [])
        existing_docs: list[RetrievedChunk] = state.get("retrieved_docs", [])
        seen_ids: set[UUID] = {doc.chunk_id for doc in existing_docs}

        new_docs: list[RetrievedChunk] = []
        for sub_query in search_queries:
            docs = await retriever.retrieve(sub_query, tenant, provider)
            for doc in docs:
                if doc.chunk_id not in seen_ids:
                    new_docs.append(doc)
                    seen_ids.add(doc.chunk_id)

        accumulated = existing_docs + new_docs
        logger.info(
            "reflexion.retrieve",
            extra={
                "tenant": tenant.tenant_id,
                "n_queries": len(search_queries),
                "new_docs": len(new_docs),
                "total_docs": len(accumulated),
            },
        )
        return {"retrieved_docs": accumulated}

    return retrieve_node


def make_revise_node(tenant: Tenant, provider: BaseLLMProvider) -> _Node:
    """Return an async node that revises the answer using retrieved evidence."""

    async def revise_node(state: ReflexionState) -> dict[str, Any]:
        query = state["query"]
        answer = state.get("answer", "")
        reflection = state.get("reflection", "")
        docs: list[RetrievedChunk] = state.get("retrieved_docs", [])
        iteration = state.get("iteration_count", 1)

        context, sources = _build_context(docs)

        domain = (
            tenant.config.get("domain", "technical documents")
            if tenant.config
            else "technical documents"
        )
        system_prompt = (
            f"You are an expert assistant for {tenant.name}, specialising in {domain}. "
            "Revise the draft answer using the retrieved evidence to fill identified gaps. "
            "Cite sources inline as [1], [2], etc. "
            "Do not repeat search_queries already used in previous iterations. "
            "Set is_complete: true when all aspects of the question are fully answered. "
            "Respond ONLY with valid JSON matching: "
            '{"answer": "<revised 250-300 word markdown answer with inline citations>", '
            '"reflection": "<what is still missing, empty string if complete>", '
            '"search_queries": ["<new sub-query>", ...], '
            '"is_complete": true|false}'
        )
        user_message = (
            f"ORIGINAL QUESTION: {query}\n\n"
            f"PREVIOUS ANSWER:\n{answer}\n\n"
            f"IDENTIFIED GAPS:\n{reflection}\n\n"
            f"RETRIEVED EVIDENCE:\n{context}"
        )

        llm_usage: LLMUsage | None = None
        try:
            raw, llm_usage = await provider.generate(
                system_prompt,
                user_message,
                response_format={"type": "json_object"},
            )
            parsed = ReflexionAnswer.model_validate(json.loads(raw))
        except (json.JSONDecodeError, ValidationError, Exception) as exc:
            logger.warning("reflexion.revise: parse error — keeping current answer", exc_info=exc)
            parsed = ReflexionAnswer(
                answer=answer,
                reflection="",
                search_queries=[],
                is_complete=True,
            )

        # Guard: no queries → force complete
        if not parsed.search_queries:
            parsed.is_complete = True

        usage = _accumulate_usage(state.get("usage"), llm_usage)
        logger.info(
            "reflexion.revise",
            extra={
                "tenant": tenant.tenant_id,
                "iteration": iteration,
                "is_complete": parsed.is_complete,
                "n_sources": len(sources),
            },
        )
        return {
            "answer": parsed.answer,
            "reflection": parsed.reflection,
            "search_queries": parsed.search_queries,
            "is_complete": parsed.is_complete,
            "iteration_count": iteration + 1,
            "sources": sources,
            "usage": usage,
        }

    return revise_node


# ---------------------------------------------------------------------------
# Router (plain function — not a factory)
# ---------------------------------------------------------------------------


def should_continue(state: ReflexionState) -> str:
    """Conditional edge: END if complete, no queries, or iteration cap reached."""
    if (
        state.get("is_complete", False)
        or not state.get("search_queries")
        or state.get("iteration_count", 0) >= MAX_ITERATIONS
    ):
        return "END"
    return "retrieve"


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
