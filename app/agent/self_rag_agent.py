from __future__ import annotations

import logging

from langgraph.graph import END, START, StateGraph
from langgraph.graph.graph import CompiledGraph

from app.agent.self_rag_nodes import (
    make_check_answer_quality,
    make_generate_node,
    make_grade_documents_node,
    make_retrieve_node,
    make_transform_query_node,
    should_generate,
)
from app.agent.self_rag_state import SelfRAGState
from app.core.providers.base import BaseLLMProvider
from app.db.models import Tenant
from app.schemas.chat import Source, TokenUsage

logger = logging.getLogger(__name__)

# Self-RAG agent stack with three independent quality gates: 
# document relevance grading (pre-generate), 
# hallucination detection (post-generate), and 
# answer completeness grading (post-hallucination check).

def create_self_rag_graph(
    tenant: Tenant,
    provider: BaseLLMProvider,
) -> CompiledGraph:
    """Compile a Self-RAG graph with nodes closed over tenant and provider.

    Graph flow:
        START → retrieve → grade_documents → should_generate
                                                  |            |
                                            [relevant]  [empty → transform_query]
                                                  |                    |
                                              generate ←───────────────┘
                                                  |
                                       check_answer_quality
                                        /          |          \\
                               [halluc.]   [incomplete]   [grounded+complete]
                              generate    transform_query        END
    """
    builder: StateGraph = StateGraph(SelfRAGState)

    builder.add_node("retrieve", make_retrieve_node(tenant, provider))
    builder.add_node("grade_documents", make_grade_documents_node(tenant, provider))
    builder.add_node("generate", make_generate_node(tenant, provider))
    builder.add_node("transform_query", make_transform_query_node(tenant, provider))

    builder.add_edge(START, "retrieve")
    builder.add_edge("retrieve", "grade_documents")
    builder.add_edge("transform_query", "retrieve")
    builder.add_conditional_edges(
        "grade_documents",
        should_generate,
        {"generate": "generate", "transform_query": "transform_query"},
    )
    builder.add_conditional_edges(
        "generate",
        make_check_answer_quality(tenant, provider),
        {"generate": "generate", "transform_query": "transform_query", "END": END},
    )

    return builder.compile()


async def run_self_rag(
    query: str,
    tenant: Tenant,
    provider: BaseLLMProvider,
) -> tuple[str, list[Source], TokenUsage | None]:
    """Run the Self-RAG pipeline and return (answer, sources, usage).

    Builds a new compiled graph per call (graphs are lightweight; tenant/provider
    bindings live in node closures, not in graph state).
    """
    graph = create_self_rag_graph(tenant, provider)

    initial_state: SelfRAGState = {
        "query": query,
        "rewritten_queries": [],
        "retrieved_docs": [],
        "answer": "",
        "sources": [],
        "usage": None,
        "iteration_count": 0,
    }

    logger.info(
        "agent.self_rag.start",
        extra={"tenant": tenant.tenant_id, "query": query},
    )

    final_state: SelfRAGState = await graph.ainvoke(initial_state)  # type: ignore[assignment]

    answer = final_state.get("answer", "")
    sources = final_state.get("sources", [])
    usage: TokenUsage | None = final_state.get("usage")  # type: ignore[assignment]

    logger.info(
        "agent.self_rag.done",
        extra={
            "tenant": tenant.tenant_id,
            "iterations": final_state.get("iteration_count", 0),
            "n_sources": len(sources),
            "answer_chars": len(answer),
            "total_tokens": usage.total_tokens if usage else None,
        },
    )

    return answer, sources, usage
