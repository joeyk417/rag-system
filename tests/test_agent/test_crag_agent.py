from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.crag_agent import create_crag_graph, run_crag
from app.agent.nodes import (
    GradeDecision,
    make_generate_node,
    make_grade_node,
    make_retrieve_node,
    make_rewrite_node,
    should_rewrite,
)
from app.agent.state import AgentState
from app.schemas.chat import Source
from app.schemas.retrieval import RetrievedChunk


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_tenant(config: dict | None = None) -> MagicMock:
    tenant = MagicMock()
    tenant.tenant_id = "test_tenant"
    tenant.name = "Test Tenant"
    tenant.schema_name = "tenant_test"
    tenant.config = config or {"domain": "engineering documents"}
    return tenant


def _make_provider() -> AsyncMock:
    provider = AsyncMock()
    provider.embed = AsyncMock(return_value=[0.1] * 1536)
    provider.generate = AsyncMock(return_value="mocked response")
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


# ---------------------------------------------------------------------------
# Unit tests — should_rewrite router
# ---------------------------------------------------------------------------


def test_should_rewrite_relevant() -> None:
    state: AgentState = {
        "query": "q",
        "rewritten_query": "",
        "retrieved_docs": [],
        "web_results": "",
        "is_relevant": True,
        "answer": "",
        "sources": [],
    }
    assert should_rewrite(state) == "generate"


def test_should_rewrite_irrelevant() -> None:
    state: AgentState = {
        "query": "q",
        "rewritten_query": "",
        "retrieved_docs": [],
        "web_results": "",
        "is_relevant": False,
        "answer": "",
        "sources": [],
    }
    assert should_rewrite(state) == "rewrite"


# ---------------------------------------------------------------------------
# Unit tests — grade_node
# ---------------------------------------------------------------------------


async def test_grade_node_relevant() -> None:
    provider = _make_provider()
    provider.generate = AsyncMock(
        return_value=json.dumps({"is_relevant": True, "reasoning": "Documents answer the question."})
    )
    grade_node = make_grade_node(provider)
    state: AgentState = {
        "query": "What is the installation torque?",
        "rewritten_query": "",
        "retrieved_docs": [_make_chunk()],
        "web_results": "",
        "is_relevant": False,
        "answer": "",
        "sources": [],
    }
    result = await grade_node(state)
    assert result["is_relevant"] is True


async def test_grade_node_irrelevant() -> None:
    provider = _make_provider()
    provider.generate = AsyncMock(
        return_value=json.dumps({"is_relevant": False, "reasoning": "Documents are unrelated."})
    )
    grade_node = make_grade_node(provider)
    state: AgentState = {
        "query": "What is the price of rubber?",
        "rewritten_query": "",
        "retrieved_docs": [_make_chunk()],
        "web_results": "",
        "is_relevant": False,
        "answer": "",
        "sources": [],
    }
    result = await grade_node(state)
    assert result["is_relevant"] is False


async def test_grade_node_no_docs_returns_irrelevant() -> None:
    provider = _make_provider()
    grade_node = make_grade_node(provider)
    state: AgentState = {
        "query": "empty retrieval?",
        "rewritten_query": "",
        "retrieved_docs": [],
        "web_results": "",
        "is_relevant": False,
        "answer": "",
        "sources": [],
    }
    result = await grade_node(state)
    assert result["is_relevant"] is False
    provider.generate.assert_not_called()


async def test_grade_node_parse_error_fails_open() -> None:
    """On invalid JSON / parse error, grade should fail-open (is_relevant=True)."""
    provider = _make_provider()
    provider.generate = AsyncMock(return_value="this is not json")
    grade_node = make_grade_node(provider)
    state: AgentState = {
        "query": "any query",
        "rewritten_query": "",
        "retrieved_docs": [_make_chunk()],
        "web_results": "",
        "is_relevant": False,
        "answer": "",
        "sources": [],
    }
    result = await grade_node(state)
    assert result["is_relevant"] is True  # fail-open


# ---------------------------------------------------------------------------
# Unit tests — rewrite_node
# ---------------------------------------------------------------------------


async def test_rewrite_node_updates_rewritten_query() -> None:
    provider = _make_provider()
    provider.generate = AsyncMock(return_value="rubber compound formulation EA screen panels")
    rewrite_node = make_rewrite_node(provider)
    state: AgentState = {
        "query": "What rubber is used?",
        "rewritten_query": "",
        "retrieved_docs": [],
        "web_results": "",
        "is_relevant": False,
        "answer": "",
        "sources": [],
    }
    result = await rewrite_node(state)
    assert result["rewritten_query"] == "rubber compound formulation EA screen panels"


async def test_rewrite_node_strips_quotes() -> None:
    provider = _make_provider()
    provider.generate = AsyncMock(return_value='"quoted rewritten query"')
    rewrite_node = make_rewrite_node(provider)
    state: AgentState = {
        "query": "original",
        "rewritten_query": "",
        "retrieved_docs": [],
        "web_results": "",
        "is_relevant": False,
        "answer": "",
        "sources": [],
    }
    result = await rewrite_node(state)
    assert result["rewritten_query"] == "quoted rewritten query"


# ---------------------------------------------------------------------------
# Unit tests — generate_node
# ---------------------------------------------------------------------------


async def test_generate_node_vector_path_populates_sources() -> None:
    provider = _make_provider()
    provider.generate = AsyncMock(return_value="The installation requires 45 Nm torque. [1]")
    tenant = _make_tenant()
    generate_node = make_generate_node(tenant, provider)
    chunk = _make_chunk(doc_number="EA-SOP-001", page=3)
    state: AgentState = {
        "query": "What torque is required?",
        "rewritten_query": "",
        "retrieved_docs": [chunk],
        "web_results": "",
        "is_relevant": True,
        "answer": "",
        "sources": [],
    }
    result = await generate_node(state)
    assert result["answer"] == "The installation requires 45 Nm torque. [1]"
    assert len(result["sources"]) == 1
    src: Source = result["sources"][0]
    assert src.doc_number == "EA-SOP-001"
    assert src.page_number == 3
    assert src.s3_key == "ea/EA-SOP-001.pdf"


async def test_generate_node_web_path_returns_empty_sources() -> None:
    provider = _make_provider()
    provider.generate = AsyncMock(return_value="Web-sourced answer about torque.")
    tenant = _make_tenant()
    generate_node = make_generate_node(tenant, provider)
    state: AgentState = {
        "query": "installation torque spec",
        "rewritten_query": "installation torque EA screen panels",
        "retrieved_docs": [],
        "web_results": "[1] Some Title\nhttps://example.com\nContent about torque.",
        "is_relevant": False,
        "answer": "",
        "sources": [],
    }
    result = await generate_node(state)
    assert result["answer"] == "Web-sourced answer about torque."
    assert result["sources"] == []


async def test_generate_node_no_context() -> None:
    """When neither docs nor web_results exist, generate still returns an answer."""
    provider = _make_provider()
    provider.generate = AsyncMock(return_value="I don't have enough information.")
    tenant = _make_tenant()
    generate_node = make_generate_node(tenant, provider)
    state: AgentState = {
        "query": "unknown query",
        "rewritten_query": "",
        "retrieved_docs": [],
        "web_results": "",
        "is_relevant": False,
        "answer": "",
        "sources": [],
    }
    result = await generate_node(state)
    assert "answer" in result
    assert result["sources"] == []


# ---------------------------------------------------------------------------
# Integration tests — full graph flow
# ---------------------------------------------------------------------------


async def test_crag_graph_relevant_path() -> None:
    """When grade returns relevant, the graph should NOT call rewrite or web_search."""
    tenant = _make_tenant()
    provider = _make_provider()
    chunk = _make_chunk()

    call_log: list[str] = []

    async def mock_retrieve(state: AgentState) -> dict:
        call_log.append("retrieve")
        return {"retrieved_docs": [chunk]}

    async def mock_grade(state: AgentState) -> dict:
        call_log.append("grade")
        return {"is_relevant": True}

    async def mock_rewrite(state: AgentState) -> dict:
        call_log.append("rewrite")
        return {"rewritten_query": "rewritten"}

    async def mock_web_search(state: AgentState) -> dict:
        call_log.append("web_search")
        return {"web_results": "some web content"}

    async def mock_generate(state: AgentState) -> dict:
        call_log.append("generate")
        return {"answer": "Final answer.", "sources": []}

    with (
        patch("app.agent.crag_agent.make_retrieve_node", return_value=mock_retrieve),
        patch("app.agent.crag_agent.make_grade_node", return_value=mock_grade),
        patch("app.agent.crag_agent.make_rewrite_node", return_value=mock_rewrite),
        patch("app.agent.crag_agent.make_web_search_node", return_value=mock_web_search),
        patch("app.agent.crag_agent.make_generate_node", return_value=mock_generate),
    ):
        graph = create_crag_graph(tenant, provider)
        initial: AgentState = {
            "query": "test query",
            "rewritten_query": "",
            "retrieved_docs": [],
            "web_results": "",
            "is_relevant": False,
            "answer": "",
            "sources": [],
        }
        final_state = await graph.ainvoke(initial)

    assert "retrieve" in call_log
    assert "grade" in call_log
    assert "rewrite" not in call_log, "rewrite should not be called on relevant path"
    assert "web_search" not in call_log, "web_search should not be called on relevant path"
    assert "generate" in call_log
    assert final_state["answer"] == "Final answer."


async def test_crag_graph_irrelevant_path() -> None:
    """When grade returns irrelevant, the graph MUST call rewrite and web_search."""
    tenant = _make_tenant()
    provider = _make_provider()

    call_log: list[str] = []

    async def mock_retrieve(state: AgentState) -> dict:
        call_log.append("retrieve")
        return {"retrieved_docs": []}

    async def mock_grade(state: AgentState) -> dict:
        call_log.append("grade")
        return {"is_relevant": False}

    async def mock_rewrite(state: AgentState) -> dict:
        call_log.append("rewrite")
        return {"rewritten_query": "better query"}

    async def mock_web_search(state: AgentState) -> dict:
        call_log.append("web_search")
        return {"web_results": "[1] Web result content"}

    async def mock_generate(state: AgentState) -> dict:
        call_log.append("generate")
        return {"answer": "Answer from web.", "sources": []}

    with (
        patch("app.agent.crag_agent.make_retrieve_node", return_value=mock_retrieve),
        patch("app.agent.crag_agent.make_grade_node", return_value=mock_grade),
        patch("app.agent.crag_agent.make_rewrite_node", return_value=mock_rewrite),
        patch("app.agent.crag_agent.make_web_search_node", return_value=mock_web_search),
        patch("app.agent.crag_agent.make_generate_node", return_value=mock_generate),
    ):
        graph = create_crag_graph(tenant, provider)
        initial: AgentState = {
            "query": "unknown topic",
            "rewritten_query": "",
            "retrieved_docs": [],
            "web_results": "",
            "is_relevant": False,
            "answer": "",
            "sources": [],
        }
        final_state = await graph.ainvoke(initial)

    assert call_log == ["retrieve", "grade", "rewrite", "web_search", "generate"]
    assert final_state["answer"] == "Answer from web."


async def test_run_crag_returns_answer_and_sources() -> None:
    """run_crag convenience wrapper returns (answer, sources) tuple."""
    tenant = _make_tenant()
    provider = _make_provider()

    async def mock_retrieve(state: AgentState) -> dict:
        return {"retrieved_docs": [_make_chunk()]}

    async def mock_grade(state: AgentState) -> dict:
        return {"is_relevant": True}

    async def mock_generate(state: AgentState) -> dict:
        return {
            "answer": "Torque is 45 Nm.",
            "sources": [
                Source(doc_number="EA-SOP-001", title="Screen Guide", page_number=3, s3_key="ea/sop.pdf")
            ],
        }

    async def mock_rewrite(state: AgentState) -> dict:
        return {"rewritten_query": ""}

    async def mock_web_search(state: AgentState) -> dict:
        return {"web_results": ""}

    with (
        patch("app.agent.crag_agent.make_retrieve_node", return_value=mock_retrieve),
        patch("app.agent.crag_agent.make_grade_node", return_value=mock_grade),
        patch("app.agent.crag_agent.make_rewrite_node", return_value=mock_rewrite),
        patch("app.agent.crag_agent.make_web_search_node", return_value=mock_web_search),
        patch("app.agent.crag_agent.make_generate_node", return_value=mock_generate),
    ):
        answer, sources = await run_crag("What torque?", tenant, provider)

    assert answer == "Torque is 45 Nm."
    assert len(sources) == 1
    assert sources[0].doc_number == "EA-SOP-001"
