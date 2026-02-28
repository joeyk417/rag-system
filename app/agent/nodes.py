from __future__ import annotations

import json
import logging
from collections.abc import Callable, Coroutine
from typing import Any

from pydantic import BaseModel, ValidationError
from tavily import TavilyClient

from app.agent.state import AgentState
from app.config import settings
from app.core.providers.base import BaseLLMProvider
from app.db.models import Tenant
from app.retrieval import retriever
from app.schemas.chat import Source
from app.schemas.retrieval import RetrievedChunk

logger = logging.getLogger(__name__)

# Type alias for an async node callable
_Node = Callable[[AgentState], Coroutine[Any, Any, dict[str, Any]]]

# Maximum characters per retrieved chunk shown to the grader/generator
_CHUNK_PREVIEW_CHARS = 800
# Maximum total context chars sent to the generate prompt
_MAX_CONTEXT_CHARS = 12_000


# ---------------------------------------------------------------------------
# Internal Pydantic model for structured grading output
# ---------------------------------------------------------------------------


class GradeDecision(BaseModel):
    is_relevant: bool
    reasoning: str = ""


# ---------------------------------------------------------------------------
# Node factories
# ---------------------------------------------------------------------------


def make_retrieve_node(tenant: Tenant, provider: BaseLLMProvider) -> _Node:
    """Return an async node that runs the hybrid retrieval pipeline."""

    async def retrieve_node(state: AgentState) -> dict[str, Any]:
        query = state.get("rewritten_query") or state["query"]
        docs = await retriever.retrieve(query, tenant, provider)
        logger.info(
            "agent.retrieve",
            extra={"tenant": tenant.tenant_id, "query": query, "n_docs": len(docs)},
        )
        return {"retrieved_docs": docs}

    return retrieve_node


def make_grade_node(provider: BaseLLMProvider) -> _Node:
    """Return an async node that grades whether retrieved docs answer the query.

    Fail-open: returns is_relevant=True on any parse or LLM error so the
    pipeline never silently falls back to web search due to a grading bug.
    """

    async def grade_node(state: AgentState) -> dict[str, Any]:
        query = state["query"]
        docs: list[RetrievedChunk] = state.get("retrieved_docs", [])

        if not docs:
            logger.info("agent.grade: no docs retrieved — marking irrelevant")
            return {"is_relevant": False}

        # Format docs as a compact preview for the grader
        doc_text = _format_docs_for_grading(docs)

        system_prompt = (
            "You are a document relevance grader. "
            "Evaluate whether the retrieved documents contain enough information "
            "to answer the user's question. "
            "Respond ONLY with valid JSON matching: "
            '{"is_relevant": true|false, "reasoning": "<brief explanation>"}'
        )
        user_message = (
            f"USER QUESTION:\n{query}\n\n"
            f"RETRIEVED DOCUMENTS:\n{doc_text}\n\n"
            "Is the retrieved content sufficient to answer the question?"
        )

        try:
            raw = await provider.generate(
                system_prompt,
                user_message,
                response_format={"type": "json_object"},
            )
            decision = GradeDecision.model_validate(json.loads(raw))
            logger.info(
                "agent.grade",
                extra={
                    "is_relevant": decision.is_relevant,
                    "reasoning": decision.reasoning,
                },
            )
            return {"is_relevant": decision.is_relevant}
        except (json.JSONDecodeError, ValidationError, Exception) as exc:
            logger.warning("agent.grade: parse error — failing open", exc_info=exc)
            return {"is_relevant": True}

    return grade_node


def make_rewrite_node(provider: BaseLLMProvider) -> _Node:
    """Return an async node that rewrites the query for better retrieval."""

    async def rewrite_node(state: AgentState) -> dict[str, Any]:
        original = state["query"]
        system_prompt = (
            "You are a search query optimization expert. "
            "Rewrite the user's question to be more specific and keyword-rich "
            "so it retrieves better results from a technical document store. "
            "Output ONLY the rewritten query — no explanation, no quotes."
        )
        user_message = f"Original question: {original}"

        rewritten = await provider.generate(system_prompt, user_message)
        rewritten = rewritten.strip().strip('"').strip("'")
        logger.info(
            "agent.rewrite",
            extra={"original": original, "rewritten": rewritten},
        )
        return {"rewritten_query": rewritten}

    return rewrite_node


def make_web_search_node() -> _Node:
    """Return an async node that performs a Tavily web search fallback.

    Raises ValueError at call time if TAVILY_API_KEY is not configured.
    """

    async def web_search_node(state: AgentState) -> dict[str, Any]:
        api_key = settings.tavily_api_key
        if not api_key:
            raise ValueError(
                "TAVILY_API_KEY is not set — cannot perform web search fallback."
            )

        query = state.get("rewritten_query") or state["query"]
        logger.info("agent.web_search", extra={"query": query})

        # TavilyClient is synchronous — run in thread pool via asyncio
        import asyncio

        loop = asyncio.get_event_loop()
        client = TavilyClient(api_key=api_key)
        results = await loop.run_in_executor(
            None,
            lambda: client.search(query, max_results=3),
        )

        formatted = _format_tavily_results(results)
        logger.info(
            "agent.web_search.done",
            extra={"n_results": len(results.get("results", []))},
        )
        return {"web_results": formatted}

    return web_search_node


def make_generate_node(tenant: Tenant, provider: BaseLLMProvider) -> _Node:
    """Return an async node that generates the final answer with source citations."""

    async def generate_node(state: AgentState) -> dict[str, Any]:
        query = state["query"]
        is_relevant: bool = state.get("is_relevant", False)
        docs: list[RetrievedChunk] = state.get("retrieved_docs", [])
        web_results: str = state.get("web_results", "")

        domain = tenant.config.get("domain", "technical documents") if tenant.config else "technical documents"
        system_prompt = (
            f"You are an expert assistant for {tenant.name}, "
            f"specialising in {domain}. "
            "Answer the user's question using ONLY the provided context. "
            "Cite sources inline as [1], [2], etc. and list them at the end under "
            "'## Sources'. If the context does not contain the answer, say so clearly."
        )

        if is_relevant and docs:
            context, sources = _build_vector_context(docs)
        else:
            context = web_results or "No relevant documents or web results found."
            sources = []

        user_message = f"Question: {query}\n\nContext:\n{context}"

        answer = await provider.generate(system_prompt, user_message)
        logger.info(
            "agent.generate",
            extra={
                "tenant": tenant.tenant_id,
                "path": "vector" if (is_relevant and docs) else "web",
                "n_sources": len(sources),
            },
        )
        return {"answer": answer, "sources": sources}

    return generate_node


# ---------------------------------------------------------------------------
# Router (plain function — not a factory)
# ---------------------------------------------------------------------------


def should_rewrite(state: AgentState) -> str:
    """Conditional edge: route to 'generate' if docs are relevant, else 'rewrite'."""
    return "generate" if state.get("is_relevant", False) else "rewrite"


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _format_docs_for_grading(docs: list[RetrievedChunk]) -> str:
    parts: list[str] = []
    for i, doc in enumerate(docs, 1):
        heading = f" — {doc.heading}" if doc.heading else ""
        preview = doc.content[:_CHUNK_PREVIEW_CHARS]
        if len(doc.content) > _CHUNK_PREVIEW_CHARS:
            preview += "..."
        parts.append(
            f"[{i}] {doc.doc_number or 'N/A'} p.{doc.page_number}{heading}\n{preview}"
        )
    return "\n\n".join(parts)


def _build_vector_context(docs: list[RetrievedChunk]) -> tuple[str, list[Source]]:
    """Format retrieved chunks into a context string and extract Source citations."""
    parts: list[str] = []
    sources: list[Source] = []
    total_chars = 0

    for i, doc in enumerate(docs, 1):
        heading = f" — {doc.heading}" if doc.heading else ""
        label = f"[{i}] {doc.doc_number or 'N/A'} p.{doc.page_number}{heading}"
        snippet = doc.content
        block = f"{label}\n{snippet}"

        if total_chars + len(block) > _MAX_CONTEXT_CHARS:
            remaining = _MAX_CONTEXT_CHARS - total_chars
            if remaining > 200:
                parts.append(f"{label}\n{snippet[:remaining]}...")
            break

        parts.append(block)
        total_chars += len(block)
        sources.append(
            Source(
                doc_number=doc.doc_number,
                title=doc.title,
                page_number=doc.page_number,
                s3_key=doc.s3_key,
            )
        )

    return "\n\n".join(parts), sources


def _format_tavily_results(results: dict[str, Any]) -> str:
    items = results.get("results", [])
    parts: list[str] = []
    for i, item in enumerate(items, 1):
        title = item.get("title", "")
        url = item.get("url", "")
        content = item.get("content", "")[:_CHUNK_PREVIEW_CHARS]
        parts.append(f"[{i}] {title}\n{url}\n{content}")
    return "\n\n".join(parts) if parts else "No web results found."
