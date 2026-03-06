from __future__ import annotations

import logging

from langgraph.graph import END, START, StateGraph
from langgraph.graph.graph import CompiledGraph

from app.agent.adaptive_rag_nodes import (
    make_route_question_node,
    make_sql_agent_node,
    make_web_search_agent_node,
)
from app.agent.adaptive_rag_state import AdaptiveRAGState
from app.agent.self_rag_nodes import (
    make_check_answer_quality,
    make_generate_node,
    make_grade_documents_node,
    make_retrieve_node,
    make_transform_query_node,
    should_generate,
)
from app.config import settings
from app.core.providers.base import BaseLLMProvider
from app.db.models import Tenant
from app.schemas.chat import Source, TokenUsage

logger = logging.getLogger(__name__)


def _route_datasource(state: AdaptiveRAGState) -> str:
    """Conditional edge: dispatch based on datasource set by route_question."""
    return state.get("datasource", "retrieve")


def create_adaptive_rag_graph(
    tenant: Tenant,
    provider: BaseLLMProvider,
    checkpointer: object | None = None,
) -> CompiledGraph:
    """Compile an Adaptive RAG graph.

    Graph flow:
        START → route_question
            [retrieve]    → retrieve → grade_documents → should_generate
                                           ↓(empty docs)
                                      transform_query → retrieve (loop)
                                           ↓(generate)
                                      generate → check_answer_quality → END
            [web_search]  → web_search_agent → END
            [sql_agent]   → sql_agent → END
    """
    builder: StateGraph = StateGraph(AdaptiveRAGState)

    # Routing node
    builder.add_node("route_question", make_route_question_node(tenant, provider))

    # Self-RAG inner nodes (reused unchanged, work with AdaptiveRAGState superset)
    builder.add_node("retrieve", make_retrieve_node(tenant, provider))  # type: ignore[arg-type]
    builder.add_node("grade_documents", make_grade_documents_node(tenant, provider))  # type: ignore[arg-type]
    builder.add_node("generate", make_generate_node(tenant, provider))  # type: ignore[arg-type]
    builder.add_node("transform_query", make_transform_query_node(tenant, provider))  # type: ignore[arg-type]

    # Web search and SQL nodes
    builder.add_node("web_search_agent", make_web_search_agent_node())
    builder.add_node("sql_agent", make_sql_agent_node())

    # Edges
    builder.add_edge(START, "route_question")
    builder.add_conditional_edges(
        "route_question",
        _route_datasource,
        {"retrieve": "retrieve", "web_search": "web_search_agent", "sql_agent": "sql_agent"},
    )

    # Self-RAG inner flow
    builder.add_edge("retrieve", "grade_documents")
    builder.add_edge("transform_query", "retrieve")
    builder.add_conditional_edges(
        "grade_documents",
        should_generate,  # type: ignore[arg-type]
        {"generate": "generate", "transform_query": "transform_query"},
    )
    builder.add_conditional_edges(
        "generate",
        make_check_answer_quality(tenant, provider),  # type: ignore[arg-type]
        {"generate": "generate", "transform_query": "transform_query", "END": END},
    )

    # Terminal edges
    builder.add_edge("web_search_agent", END)
    builder.add_edge("sql_agent", END)

    return builder.compile(checkpointer=checkpointer)  # type: ignore[arg-type]


async def run_adaptive_rag(
    query: str,
    tenant: Tenant,
    provider: BaseLLMProvider,
    thread_id: str | None = None,
) -> tuple[str, list[Source], TokenUsage | None]:
    """Run the Adaptive RAG pipeline and return (answer, sources, usage).

    When thread_id is provided, enables PostgreSQL multi-turn checkpointing.
    When omitted, runs stateless (same behaviour as other agents).
    """
    logger.info(
        "agent.adaptive_rag.start",
        extra={"tenant": tenant.tenant_id, "query": query, "thread_id": thread_id},
    )

    initial_state: AdaptiveRAGState = {
        "query": query,
        "datasource": "",
        "rewritten_queries": [],
        "retrieved_docs": [],
        "answer": "",
        "sources": [],
        "usage": None,
        "iteration_count": 0,
    }

    invoke_config: dict[str, object] | None = None

    if thread_id:
        # Use PostgreSQL checkpointer for multi-turn memory
        # Convert SQLAlchemy URL to plain asyncpg-compatible URL
        pg_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

            async with AsyncPostgresSaver.from_conn_string(pg_url) as checkpointer:
                await checkpointer.setup()
                graph = create_adaptive_rag_graph(tenant, provider, checkpointer=checkpointer)
                invoke_config = {"configurable": {"thread_id": thread_id}}
                final_state: AdaptiveRAGState = await graph.ainvoke(  # type: ignore[assignment]
                    initial_state, config=invoke_config
                )
        except ImportError:
            logger.warning(
                "agent.adaptive_rag: langgraph-checkpoint-postgres not installed — "
                "running stateless despite thread_id=%s",
                thread_id,
            )
            graph = create_adaptive_rag_graph(tenant, provider)
            final_state = await graph.ainvoke(initial_state)  # type: ignore[assignment]
        except Exception as exc:
            logger.warning(
                "agent.adaptive_rag: checkpointer setup failed (%s) — running stateless",
                exc,
                exc_info=exc,
            )
            graph = create_adaptive_rag_graph(tenant, provider)
            final_state = await graph.ainvoke(initial_state)  # type: ignore[assignment]
    else:
        graph = create_adaptive_rag_graph(tenant, provider)
        final_state = await graph.ainvoke(initial_state)  # type: ignore[assignment]

    answer = final_state.get("answer", "")
    sources = final_state.get("sources", [])
    usage: TokenUsage | None = final_state.get("usage")  # type: ignore[assignment]

    logger.info(
        "agent.adaptive_rag.done",
        extra={
            "tenant": tenant.tenant_id,
            "datasource": final_state.get("datasource", ""),
            "iterations": final_state.get("iteration_count", 0),
            "n_sources": len(sources),
            "answer_chars": len(answer),
            "total_tokens": usage.total_tokens if usage else None,
        },
    )

    return answer, sources, usage
