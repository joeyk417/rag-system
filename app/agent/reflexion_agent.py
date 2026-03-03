from __future__ import annotations

import logging

from langgraph.graph import END, START, StateGraph
from langgraph.graph.graph import CompiledGraph

from app.agent.reflexion_nodes import (
    make_draft_node,
    make_retrieve_node,
    make_revise_node,
    should_continue,
)
from app.agent.reflexion_state import ReflexionState
from app.core.providers.base import BaseLLMProvider
from app.db.models import Tenant
from app.schemas.chat import Source, TokenUsage

logger = logging.getLogger(__name__)


def create_reflexion_graph(
    tenant: Tenant,
    provider: BaseLLMProvider,
) -> CompiledGraph:
    """Compile a Reflexion graph with nodes closed over tenant and provider.

    Graph flow:
        START → draft → retrieve → revise → should_continue
                             ↑                     |
                             └──── [incomplete] ───┘
                                                   |
                                            [complete OR max_iter]
                                                   ↓
                                                  END
    """
    builder: StateGraph = StateGraph(ReflexionState)

    builder.add_node("draft", make_draft_node(provider))
    builder.add_node("retrieve", make_retrieve_node(tenant, provider))
    builder.add_node("revise", make_revise_node(tenant, provider))

    builder.add_edge(START, "draft")
    builder.add_edge("draft", "retrieve")
    builder.add_edge("retrieve", "revise")
    builder.add_conditional_edges(
        "revise",
        should_continue,
        {"retrieve": "retrieve", "END": END},
    )

    return builder.compile()


async def run_reflexion(
    query: str,
    tenant: Tenant,
    provider: BaseLLMProvider,
) -> tuple[str, list[Source], TokenUsage | None]:
    """Run the Reflexion pipeline and return (answer, sources, usage).

    Builds a new compiled graph per call (graphs are lightweight; tenant/provider
    bindings live in node closures, not in graph state).
    """
    graph = create_reflexion_graph(tenant, provider)

    initial_state: ReflexionState = {
        "query": query,
        "answer": "",
        "reflection": "",
        "search_queries": [],
        "retrieved_docs": [],
        "sources": [],
        "is_complete": False,
        "iteration_count": 0,
        "usage": None,
    }

    logger.info(
        "agent.reflexion.start",
        extra={"tenant": tenant.tenant_id, "query": query},
    )

    final_state: ReflexionState = await graph.ainvoke(initial_state)  # type: ignore[assignment]

    answer = final_state.get("answer", "")
    sources = final_state.get("sources", [])
    usage: TokenUsage | None = final_state.get("usage")  # type: ignore[assignment]

    logger.info(
        "agent.reflexion.done",
        extra={
            "tenant": tenant.tenant_id,
            "iterations": final_state.get("iteration_count", 0),
            "n_sources": len(sources),
            "answer_chars": len(answer),
            "total_tokens": usage.total_tokens if usage else None,
        },
    )

    return answer, sources, usage
