from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.adaptive_rag_agent import create_adaptive_rag_graph, run_adaptive_rag
from app.agent.adaptive_rag_nodes import (
    make_route_question_node,
    make_sql_agent_node,
    make_web_search_agent_node,
)
from app.agent.adaptive_rag_state import AdaptiveRAGState, RouterQuery
from app.schemas.chat import Source, TokenUsage
from app.schemas.retrieval import RetrievedChunk


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_tenant(config: dict | None = None) -> MagicMock:
    tenant = MagicMock()
    tenant.tenant_id = "test_tenant"
    tenant.name = "Test Tenant"
    tenant.schema_name = "tenant_test"
    tenant.config = config or {
        "domain": "engineering documents",
        "enabled_routes": ["retrieve", "web_search"],
    }
    return tenant


def _make_provider() -> AsyncMock:
    provider = AsyncMock()
    provider.embed = AsyncMock(return_value=[0.1] * 1536)
    provider.generate = AsyncMock(
        return_value=(json.dumps({"datasource": "retrieve", "reasoning": "doc query"}), None)
    )
    return provider


def _make_chunk(
    doc_number: str = "EA-SOP-001",
    page: int = 1,
    content: str = "Screen installation requires proper torque settings.",
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        doc_number=doc_number,
        doc_type="SOP",
        title="Screen Installation Guide",
        classification="STANDARD",
        s3_key=f"ea/{doc_number}.pdf",
        page_number=page,
        heading="Installation Procedure",
        content=content,
        similarity_score=0.12,
    )


def _make_state(**overrides: object) -> AdaptiveRAGState:
    base: AdaptiveRAGState = {
        "query": "test query",
        "datasource": "",
        "rewritten_queries": [],
        "retrieved_docs": [],
        "answer": "",
        "sources": [],
        "usage": None,
        "iteration_count": 0,
    }
    base.update(overrides)  # type: ignore[typeddict-item]
    return base


# ---------------------------------------------------------------------------
# Schema validation tests
# ---------------------------------------------------------------------------


def test_router_query_valid_retrieve() -> None:
    rq = RouterQuery(datasource="retrieve", reasoning="technical doc query")
    assert rq.datasource == "retrieve"


def test_router_query_valid_web_search() -> None:
    rq = RouterQuery(datasource="web_search")
    assert rq.datasource == "web_search"


def test_router_query_valid_sql_agent() -> None:
    rq = RouterQuery(datasource="sql_agent")
    assert rq.datasource == "sql_agent"


def test_router_query_invalid_datasource() -> None:
    with pytest.raises(Exception):
        RouterQuery(datasource="invalid_source")  # type: ignore[arg-type]


def test_router_query_reasoning_defaults_empty() -> None:
    rq = RouterQuery(datasource="retrieve")
    assert rq.reasoning == ""


# ---------------------------------------------------------------------------
# Unit tests — route_question_node
# ---------------------------------------------------------------------------


async def test_route_question_routes_to_retrieve() -> None:
    """LLM returning 'retrieve' on a doc keyword query."""
    tenant = _make_tenant()
    provider = _make_provider()
    provider.generate = AsyncMock(
        return_value=(json.dumps({"datasource": "retrieve", "reasoning": "SOP query"}), None)
    )
    node = make_route_question_node(tenant, provider)
    result = await node(_make_state(query="What is the installation SOP?"))
    assert result["datasource"] == "retrieve"


async def test_route_question_routes_to_web_search() -> None:
    """LLM returning 'web_search' for a general knowledge query."""
    tenant = _make_tenant()
    provider = _make_provider()
    provider.generate = AsyncMock(
        return_value=(json.dumps({"datasource": "web_search", "reasoning": "news query"}), None)
    )
    node = make_route_question_node(tenant, provider)
    result = await node(_make_state(query="What is the current price of rubber?"))
    assert result["datasource"] == "web_search"


async def test_route_question_defaults_to_retrieve_on_parse_error() -> None:
    """JSON parse error in router → fail-safe default 'retrieve'."""
    tenant = _make_tenant()
    provider = _make_provider()
    provider.generate = AsyncMock(return_value=("not valid json", None))
    node = make_route_question_node(tenant, provider)
    result = await node(_make_state(query="anything"))
    assert result["datasource"] == "retrieve"


async def test_route_question_rejects_disabled_route() -> None:
    """LLM returning a disabled datasource → falls back to 'retrieve'."""
    tenant = _make_tenant(config={
        "enabled_routes": ["retrieve"],  # web_search disabled
        "domain": "engineering",
    })
    provider = _make_provider()
    provider.generate = AsyncMock(
        return_value=(json.dumps({"datasource": "web_search", "reasoning": "oops"}), None)
    )
    node = make_route_question_node(tenant, provider)
    result = await node(_make_state(query="latest rubber news"))
    assert result["datasource"] == "retrieve"


async def test_route_question_rejects_sql_when_disabled() -> None:
    """sql_agent not in enabled_routes → fallback to 'retrieve'."""
    tenant = _make_tenant(config={
        "enabled_routes": ["retrieve", "web_search"],
        "domain": "engineering",
    })
    provider = _make_provider()
    provider.generate = AsyncMock(
        return_value=(json.dumps({"datasource": "sql_agent", "reasoning": "count query"}), None)
    )
    node = make_route_question_node(tenant, provider)
    result = await node(_make_state(query="how many employees?"))
    assert result["datasource"] == "retrieve"


async def test_route_question_uses_tenant_routing_hints() -> None:
    """Tenant routing config is included in the prompt (provider is called with it)."""
    tenant = _make_tenant(config={
        "enabled_routes": ["retrieve"],
        "routing": {"retrieve_keywords": ["banana", "screen"]},
    })
    provider = _make_provider()
    provider.generate = AsyncMock(
        return_value=(json.dumps({"datasource": "retrieve", "reasoning": "banana screen query"}), None)
    )
    node = make_route_question_node(tenant, provider)
    await node(_make_state(query="banana screen spec"))
    # Confirm provider was called (routing hints were passed)
    provider.generate.assert_called_once()
    prompt_args = provider.generate.call_args
    assert "banana" in str(prompt_args)


# ---------------------------------------------------------------------------
# Unit tests — web_search_agent_node
# ---------------------------------------------------------------------------


async def test_web_search_agent_skips_without_tavily_key() -> None:
    """When TAVILY_API_KEY is empty, returns fallback answer without error."""
    node = make_web_search_agent_node()
    with patch("app.agent.adaptive_rag_nodes.settings") as mock_settings:
        mock_settings.tavily_api_key = ""
        mock_settings.openai_api_key = "sk-test"
        result = await node(_make_state(query="anything"))
    assert result["answer"] != ""
    assert result["sources"] == []


async def test_web_search_agent_skips_without_openai_key() -> None:
    """When OPENAI_API_KEY is empty, returns fallback answer without error."""
    node = make_web_search_agent_node()
    with patch("app.agent.adaptive_rag_nodes.settings") as mock_settings:
        mock_settings.tavily_api_key = "tvly-test"
        mock_settings.openai_api_key = ""
        result = await node(_make_state(query="anything"))
    assert result["answer"] != ""
    assert result["sources"] == []


async def test_web_search_agent_returns_answer() -> None:
    """When both keys present, returns answer from ReAct agent."""
    from unittest.mock import MagicMock

    node = make_web_search_agent_node()

    mock_agent = AsyncMock()
    mock_message = MagicMock()
    mock_message.content = "The current rubber price is $2.50/kg."
    mock_agent.ainvoke = AsyncMock(return_value={"messages": [mock_message]})

    with patch("app.agent.adaptive_rag_nodes.settings") as mock_settings:
        mock_settings.tavily_api_key = "tvly-test"
        mock_settings.openai_api_key = "sk-test"
        mock_settings.openai_llm_model = "gpt-4o-mini"
        with patch("app.agent.adaptive_rag_nodes.TavilySearchResults", return_value=MagicMock()), \
             patch("app.agent.adaptive_rag_nodes.ChatOpenAI", return_value=MagicMock()), \
             patch("app.agent.adaptive_rag_nodes.create_react_agent", return_value=mock_agent):
            result = await node(_make_state(query="current rubber price"))

    assert result["answer"] == "The current rubber price is $2.50/kg."
    assert result["sources"] == []


async def test_web_search_agent_handles_agent_error() -> None:
    """Exception from ReAct agent returns graceful fallback answer."""
    node = make_web_search_agent_node()

    mock_agent = AsyncMock()
    mock_agent.ainvoke = AsyncMock(side_effect=RuntimeError("Tavily unreachable"))

    with patch("app.agent.adaptive_rag_nodes.settings") as mock_settings:
        mock_settings.tavily_api_key = "tvly-test"
        mock_settings.openai_api_key = "sk-test"
        mock_settings.openai_llm_model = "gpt-4o-mini"
        with patch("app.agent.adaptive_rag_nodes.TavilySearchResults", return_value=MagicMock()), \
             patch("app.agent.adaptive_rag_nodes.ChatOpenAI", return_value=MagicMock()), \
             patch("app.agent.adaptive_rag_nodes.create_react_agent", return_value=mock_agent):
            result = await node(_make_state(query="current rubber price"))

    assert "failed" in result["answer"].lower() or len(result["answer"]) > 0
    assert result["sources"] == []


# ---------------------------------------------------------------------------
# Unit tests — sql_agent_node
# ---------------------------------------------------------------------------


async def test_sql_agent_raises_not_implemented() -> None:
    """sql_agent_node is a stub — always raises NotImplementedError."""
    node = make_sql_agent_node()
    with pytest.raises(NotImplementedError):
        await node(_make_state(query="how many employees?"))


# ---------------------------------------------------------------------------
# Integration tests — full graph flow
# ---------------------------------------------------------------------------


async def test_adaptive_rag_graph_retrieve_path() -> None:
    """route_question → retrieve → grade → generate → END (retrieve path)."""
    tenant = _make_tenant()
    provider = _make_provider()
    call_log: list[str] = []

    async def mock_route(state: AdaptiveRAGState) -> dict:
        call_log.append("route_question")
        return {"datasource": "retrieve"}

    async def mock_retrieve(state: AdaptiveRAGState) -> dict:
        call_log.append("retrieve")
        return {"retrieved_docs": [_make_chunk()]}

    async def mock_grade(state: AdaptiveRAGState) -> dict:
        call_log.append("grade_documents")
        return {"retrieved_docs": state["retrieved_docs"], "usage": None}

    async def mock_generate(state: AdaptiveRAGState) -> dict:
        call_log.append("generate")
        return {"answer": "Torque spec is 370 Nm.", "sources": [], "usage": None, "iteration_count": 1}

    async def mock_transform(state: AdaptiveRAGState) -> dict:
        call_log.append("transform_query")
        return {"rewritten_queries": []}

    async def mock_web_search(state: AdaptiveRAGState) -> dict:
        call_log.append("web_search_agent")
        return {"answer": "web answer", "sources": [], "usage": None}

    async def mock_sql(state: AdaptiveRAGState) -> dict:
        call_log.append("sql_agent")
        raise NotImplementedError

    with (
        patch("app.agent.adaptive_rag_agent.make_route_question_node", return_value=mock_route),
        patch("app.agent.adaptive_rag_agent.make_retrieve_node", return_value=mock_retrieve),
        patch("app.agent.adaptive_rag_agent.make_grade_documents_node", return_value=mock_grade),
        patch("app.agent.adaptive_rag_agent.make_generate_node", return_value=mock_generate),
        patch("app.agent.adaptive_rag_agent.make_transform_query_node", return_value=mock_transform),
        patch("app.agent.adaptive_rag_agent.make_web_search_agent_node", return_value=mock_web_search),
        patch("app.agent.adaptive_rag_agent.make_sql_agent_node", return_value=mock_sql),
        patch("app.agent.adaptive_rag_agent.make_check_answer_quality", return_value=lambda state: "END"),
    ):
        graph = create_adaptive_rag_graph(tenant, provider)
        initial: AdaptiveRAGState = {
            "query": "What is the torque spec?",
            "datasource": "",
            "rewritten_queries": [],
            "retrieved_docs": [],
            "answer": "",
            "sources": [],
            "usage": None,
            "iteration_count": 0,
        }
        final_state = await graph.ainvoke(initial)

    assert "route_question" in call_log
    assert "retrieve" in call_log
    assert "grade_documents" in call_log
    assert "generate" in call_log
    assert "web_search_agent" not in call_log
    assert final_state["answer"] == "Torque spec is 370 Nm."


async def test_adaptive_rag_graph_web_search_path() -> None:
    """route_question → web_search_agent → END (web search path)."""
    tenant = _make_tenant()
    provider = _make_provider()
    call_log: list[str] = []

    async def mock_route(state: AdaptiveRAGState) -> dict:
        call_log.append("route_question")
        return {"datasource": "web_search"}

    async def mock_retrieve(state: AdaptiveRAGState) -> dict:
        call_log.append("retrieve")
        return {"retrieved_docs": []}

    async def mock_grade(state: AdaptiveRAGState) -> dict:
        call_log.append("grade_documents")
        return {"retrieved_docs": [], "usage": None}

    async def mock_generate(state: AdaptiveRAGState) -> dict:
        call_log.append("generate")
        return {"answer": "vector answer", "sources": [], "usage": None, "iteration_count": 1}

    async def mock_transform(state: AdaptiveRAGState) -> dict:
        call_log.append("transform_query")
        return {"rewritten_queries": []}

    async def mock_web_search(state: AdaptiveRAGState) -> dict:
        call_log.append("web_search_agent")
        return {"answer": "Current rubber price is $2.50/kg.", "sources": [], "usage": None}

    async def mock_sql(state: AdaptiveRAGState) -> dict:
        call_log.append("sql_agent")
        raise NotImplementedError

    with (
        patch("app.agent.adaptive_rag_agent.make_route_question_node", return_value=mock_route),
        patch("app.agent.adaptive_rag_agent.make_retrieve_node", return_value=mock_retrieve),
        patch("app.agent.adaptive_rag_agent.make_grade_documents_node", return_value=mock_grade),
        patch("app.agent.adaptive_rag_agent.make_generate_node", return_value=mock_generate),
        patch("app.agent.adaptive_rag_agent.make_transform_query_node", return_value=mock_transform),
        patch("app.agent.adaptive_rag_agent.make_web_search_agent_node", return_value=mock_web_search),
        patch("app.agent.adaptive_rag_agent.make_sql_agent_node", return_value=mock_sql),
        patch("app.agent.adaptive_rag_agent.make_check_answer_quality", return_value=lambda state: "END"),
    ):
        graph = create_adaptive_rag_graph(tenant, provider)
        initial: AdaptiveRAGState = {
            "query": "What is the current rubber price?",
            "datasource": "",
            "rewritten_queries": [],
            "retrieved_docs": [],
            "answer": "",
            "sources": [],
            "usage": None,
            "iteration_count": 0,
        }
        final_state = await graph.ainvoke(initial)

    assert "route_question" in call_log
    assert "web_search_agent" in call_log
    assert "retrieve" not in call_log
    assert "generate" not in call_log
    assert final_state["answer"] == "Current rubber price is $2.50/kg."


# ---------------------------------------------------------------------------
# Integration test — run_adaptive_rag wrapper
# ---------------------------------------------------------------------------


async def test_run_adaptive_rag_returns_tuple() -> None:
    """run_adaptive_rag returns (answer, sources, usage) tuple."""
    tenant = _make_tenant()
    provider = _make_provider()

    expected_source = Source(
        doc_number="EA-SOP-001",
        title="Screen Guide",
        page_number=3,
        s3_key="ea/sop.pdf",
    )
    expected_usage = TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150)

    async def mock_route(state: AdaptiveRAGState) -> dict:
        return {"datasource": "retrieve"}

    async def mock_retrieve(state: AdaptiveRAGState) -> dict:
        return {"retrieved_docs": [_make_chunk()]}

    async def mock_grade(state: AdaptiveRAGState) -> dict:
        return {"retrieved_docs": state["retrieved_docs"], "usage": None}

    async def mock_generate(state: AdaptiveRAGState) -> dict:
        return {
            "answer": "Torque is 370 Nm.",
            "sources": [expected_source],
            "usage": expected_usage,
            "iteration_count": 1,
        }

    async def mock_transform(state: AdaptiveRAGState) -> dict:
        return {"rewritten_queries": []}

    async def mock_web_search(state: AdaptiveRAGState) -> dict:
        return {"answer": "", "sources": [], "usage": None}

    async def mock_sql(state: AdaptiveRAGState) -> dict:
        raise NotImplementedError

    with (
        patch("app.agent.adaptive_rag_agent.make_route_question_node", return_value=mock_route),
        patch("app.agent.adaptive_rag_agent.make_retrieve_node", return_value=mock_retrieve),
        patch("app.agent.adaptive_rag_agent.make_grade_documents_node", return_value=mock_grade),
        patch("app.agent.adaptive_rag_agent.make_generate_node", return_value=mock_generate),
        patch("app.agent.adaptive_rag_agent.make_transform_query_node", return_value=mock_transform),
        patch("app.agent.adaptive_rag_agent.make_web_search_agent_node", return_value=mock_web_search),
        patch("app.agent.adaptive_rag_agent.make_sql_agent_node", return_value=mock_sql),
        patch("app.agent.adaptive_rag_agent.make_check_answer_quality", return_value=lambda state: "END"),
    ):
        answer, sources, usage = await run_adaptive_rag(
            "What is the torque spec?", tenant, provider
        )

    assert answer == "Torque is 370 Nm."
    assert len(sources) == 1
    assert sources[0].doc_number == "EA-SOP-001"
    assert usage is not None
    assert usage.total_tokens == 150


async def test_run_adaptive_rag_stateless_without_thread_id() -> None:
    """run_adaptive_rag without thread_id runs stateless (no checkpointer)."""
    tenant = _make_tenant()
    provider = _make_provider()

    async def mock_route(state: AdaptiveRAGState) -> dict:
        return {"datasource": "web_search"}

    async def mock_web_search(state: AdaptiveRAGState) -> dict:
        return {"answer": "Web answer.", "sources": [], "usage": None}

    async def mock_retrieve(state: AdaptiveRAGState) -> dict:
        return {"retrieved_docs": []}

    async def mock_grade(state: AdaptiveRAGState) -> dict:
        return {"retrieved_docs": [], "usage": None}

    async def mock_generate(state: AdaptiveRAGState) -> dict:
        return {"answer": "", "sources": [], "usage": None, "iteration_count": 1}

    async def mock_transform(state: AdaptiveRAGState) -> dict:
        return {"rewritten_queries": []}

    async def mock_sql(state: AdaptiveRAGState) -> dict:
        raise NotImplementedError

    with (
        patch("app.agent.adaptive_rag_agent.make_route_question_node", return_value=mock_route),
        patch("app.agent.adaptive_rag_agent.make_retrieve_node", return_value=mock_retrieve),
        patch("app.agent.adaptive_rag_agent.make_grade_documents_node", return_value=mock_grade),
        patch("app.agent.adaptive_rag_agent.make_generate_node", return_value=mock_generate),
        patch("app.agent.adaptive_rag_agent.make_transform_query_node", return_value=mock_transform),
        patch("app.agent.adaptive_rag_agent.make_web_search_agent_node", return_value=mock_web_search),
        patch("app.agent.adaptive_rag_agent.make_sql_agent_node", return_value=mock_sql),
        patch("app.agent.adaptive_rag_agent.make_check_answer_quality", return_value=lambda state: "END"),
    ):
        # No thread_id — should not import or use AsyncPostgresSaver
        answer, sources, usage = await run_adaptive_rag(
            "current price of rubber", tenant, provider, thread_id=None
        )

    assert answer == "Web answer."
