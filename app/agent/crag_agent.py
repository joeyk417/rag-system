from __future__ import annotations

import logging

from langgraph.graph import END, START, StateGraph
from langgraph.graph.graph import CompiledGraph

from app.agent.nodes import (
    make_generate_node,
    make_grade_node,
    make_retrieve_node,
    make_rewrite_node,
    make_web_search_node,
    should_rewrite,
)
from app.agent.state import AgentState
from app.core.providers.base import BaseLLMProvider
from app.db.models import Tenant
from app.schemas.chat import Source, TokenUsage

logger = logging.getLogger(__name__)


def create_crag_graph(
    tenant: Tenant,
    provider: BaseLLMProvider,
) -> CompiledGraph:
    """Compile a CRAG graph with nodes closed over tenant and provider.

    Graph flow:
        START → retrieve → grade → [relevant]    → generate → END
                                  → [irrelevant] → rewrite → web_search → generate → END
    """
    builder: StateGraph = StateGraph(AgentState)

    builder.add_node("retrieve", make_retrieve_node(tenant, provider))
    builder.add_node("grade", make_grade_node(provider))
    builder.add_node("rewrite", make_rewrite_node(provider))
    builder.add_node("web_search", make_web_search_node())
    builder.add_node("generate", make_generate_node(tenant, provider))

    builder.add_edge(START, "retrieve")
    builder.add_edge("retrieve", "grade")
    builder.add_conditional_edges("grade", should_rewrite, ["rewrite", "generate"])
    builder.add_edge("rewrite", "web_search")
    builder.add_edge("web_search", "generate")
    builder.add_edge("generate", END)

    return builder.compile()


async def run_crag(
    query: str,
    tenant: Tenant,
    provider: BaseLLMProvider,
) -> tuple[str, list[Source], TokenUsage | None]:
    """Run the CRAG pipeline and return (answer, sources, usage).

    Builds a new compiled graph per call (graphs are lightweight; tenant/provider
    bindings live in node closures, not in graph state).
    """
    graph = create_crag_graph(tenant, provider)

    initial_state: AgentState = {
        "query": query,
        "rewritten_query": "",
        "retrieved_docs": [],
        "web_results": "",
        "is_relevant": False,
        "answer": "",
        "sources": [],
        "usage": None,
    }

    logger.info(
        "agent.crag.start",
        extra={"tenant": tenant.tenant_id, "query": query},
    )

    final_state: AgentState = await graph.ainvoke(initial_state)  # type: ignore[assignment]

    answer = final_state.get("answer", "")
    sources = final_state.get("sources", [])
    usage: TokenUsage | None = final_state.get("usage")  # type: ignore[assignment]

    logger.info(
        "agent.crag.done",
        extra={
            "tenant": tenant.tenant_id,
            "n_sources": len(sources),
            "answer_chars": len(answer),
            "total_tokens": usage.total_tokens if usage else None,
        },
    )

    return answer, sources, usage
