from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.reflexion_agent import create_reflexion_graph, run_reflexion
from app.agent.reflexion_nodes import (
    MAX_ITERATIONS,
    make_draft_node,
    make_retrieve_node,
    make_revise_node,
    should_continue,
)
from app.agent.reflexion_state import ReflexionState
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
    tenant.config = config or {"domain": "engineering documents"}
    return tenant


def _make_provider() -> AsyncMock:
    provider = AsyncMock()
    provider.embed = AsyncMock(return_value=[0.1] * 1536)
    provider.generate = AsyncMock(return_value=("mocked response", None))
    return provider


def _make_chunk(
    chunk_id: uuid.UUID | None = None,
    doc_number: str = "EA-SOP-001",
    page: int = 1,
    content: str = "Screen installation requires proper torque settings.",
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id or uuid.uuid4(),
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


def _make_state(**overrides: object) -> ReflexionState:
    base: ReflexionState = {
        "query": "test query",
        "answer": "",
        "reflection": "",
        "search_queries": ["sub-query 1"],
        "retrieved_docs": [],
        "sources": [],
        "is_complete": False,
        "iteration_count": 1,
        "usage": None,
    }
    base.update(overrides)  # type: ignore[typeddict-item]
    return base


# ---------------------------------------------------------------------------
# Unit tests — should_continue router
# ---------------------------------------------------------------------------


def test_should_continue_complete() -> None:
    state = _make_state(is_complete=True, iteration_count=1)
    assert should_continue(state) == "END"


def test_should_continue_no_queries() -> None:
    state = _make_state(search_queries=[], is_complete=False, iteration_count=1)
    assert should_continue(state) == "END"


def test_should_continue_max_iter() -> None:
    state = _make_state(is_complete=False, iteration_count=MAX_ITERATIONS)
    assert should_continue(state) == "END"


def test_should_continue_incomplete() -> None:
    state = _make_state(is_complete=False, search_queries=["more info"], iteration_count=1)
    assert should_continue(state) == "retrieve"


# ---------------------------------------------------------------------------
# Unit tests — draft_node
# ---------------------------------------------------------------------------


async def test_draft_node_returns_fields() -> None:
    provider = _make_provider()
    provider.generate = AsyncMock(
        return_value=(
            json.dumps({
                "answer": "Initial answer about torque.",
                "reflection": "Need exact torque values.",
                "search_queries": ["M20 Grade 10.9 torque spec EA"],
                "is_complete": False,
            }),
            None,
        )
    )
    draft_node = make_draft_node(provider)
    result = await draft_node(_make_state())

    assert result["answer"] == "Initial answer about torque."
    assert result["reflection"] == "Need exact torque values."
    assert result["search_queries"] == ["M20 Grade 10.9 torque spec EA"]
    assert result["is_complete"] is False
    assert result["iteration_count"] == 1


async def test_draft_node_parse_error_fallback() -> None:
    provider = _make_provider()
    provider.generate = AsyncMock(return_value=("this is not json", None))
    draft_node = make_draft_node(provider)
    state = _make_state(query="What is the torque?")
    result = await draft_node(state)

    # Fallback uses original query as the sole search_query
    assert result["search_queries"] == ["What is the torque?"]
    assert result["iteration_count"] == 1


async def test_draft_node_empty_queries_forces_complete() -> None:
    provider = _make_provider()
    provider.generate = AsyncMock(
        return_value=(
            json.dumps({
                "answer": "I know everything.",
                "reflection": "",
                "search_queries": [],
                "is_complete": False,
            }),
            None,
        )
    )
    draft_node = make_draft_node(provider)
    result = await draft_node(_make_state())

    assert result["is_complete"] is True


# ---------------------------------------------------------------------------
# Unit tests — retrieve_node
# ---------------------------------------------------------------------------


async def test_retrieve_node_deduplicates_by_chunk_id() -> None:
    """Same chunk_id from two sub-queries should only appear once."""
    shared_id = uuid.uuid4()
    chunk_a = _make_chunk(chunk_id=shared_id, doc_number="EA-SOP-001")
    chunk_b = _make_chunk(chunk_id=shared_id, doc_number="EA-SOP-001")  # duplicate ID
    chunk_c = _make_chunk(doc_number="EA-ENG-DRW-7834")  # unique ID

    tenant = _make_tenant()
    provider = _make_provider()

    call_count = 0

    async def mock_retrieve(query: str, t: object, p: object, **kw: object) -> list[RetrievedChunk]:
        nonlocal call_count
        call_count += 1
        return [chunk_a] if call_count == 1 else [chunk_b, chunk_c]

    state = _make_state(search_queries=["query 1", "query 2"])

    with patch("app.agent.reflexion_nodes.retriever.retrieve", side_effect=mock_retrieve):
        retrieve_node = make_retrieve_node(tenant, provider)
        result = await retrieve_node(state)

    docs = result["retrieved_docs"]
    # chunk_b is a duplicate of chunk_a (same chunk_id) — should be excluded
    assert len(docs) == 2
    ids = [d.chunk_id for d in docs]
    assert shared_id in ids


async def test_retrieve_node_accumulates_existing_docs() -> None:
    """Docs already in state should be preserved and new unique ones appended."""
    existing = _make_chunk(doc_number="EA-STRAT-002")
    new_chunk = _make_chunk(doc_number="EA-ENG-MAT-019")

    tenant = _make_tenant()
    provider = _make_provider()

    async def mock_retrieve(query: str, t: object, p: object, **kw: object) -> list[RetrievedChunk]:
        return [new_chunk]

    state = _make_state(
        search_queries=["query"],
        retrieved_docs=[existing],
    )

    with patch("app.agent.reflexion_nodes.retriever.retrieve", side_effect=mock_retrieve):
        retrieve_node = make_retrieve_node(tenant, provider)
        result = await retrieve_node(state)

    assert len(result["retrieved_docs"]) == 2


# ---------------------------------------------------------------------------
# Unit tests — revise_node
# ---------------------------------------------------------------------------


async def test_revise_node_increments_iteration() -> None:
    provider = _make_provider()
    provider.generate = AsyncMock(
        return_value=(
            json.dumps({
                "answer": "Revised answer with torque value 370 Nm.",
                "reflection": "",
                "search_queries": [],
                "is_complete": True,
            }),
            None,
        )
    )
    tenant = _make_tenant()
    revise_node = make_revise_node(tenant, provider)
    state = _make_state(
        iteration_count=1,
        retrieved_docs=[_make_chunk()],
    )
    result = await revise_node(state)

    assert result["iteration_count"] == 2


async def test_revise_node_forces_complete_on_empty_queries() -> None:
    provider = _make_provider()
    provider.generate = AsyncMock(
        return_value=(
            json.dumps({
                "answer": "Answer.",
                "reflection": "Still missing data.",
                "search_queries": [],
                "is_complete": False,  # would loop — must be forced True
            }),
            None,
        )
    )
    tenant = _make_tenant()
    revise_node = make_revise_node(tenant, provider)
    result = await revise_node(_make_state(retrieved_docs=[_make_chunk()]))

    assert result["is_complete"] is True


async def test_revise_node_populates_sources() -> None:
    provider = _make_provider()
    provider.generate = AsyncMock(
        return_value=(
            json.dumps({
                "answer": "The torque spec is 370 Nm [1].",
                "reflection": "",
                "search_queries": [],
                "is_complete": True,
            }),
            None,
        )
    )
    tenant = _make_tenant()
    revise_node = make_revise_node(tenant, provider)
    chunk = _make_chunk(doc_number="EA-SOP-001", page=5)
    result = await revise_node(_make_state(retrieved_docs=[chunk]))

    assert len(result["sources"]) == 1
    assert result["sources"][0].doc_number == "EA-SOP-001"
    assert result["sources"][0].page_number == 5


async def test_revise_node_parse_error_keeps_current_answer() -> None:
    provider = _make_provider()
    provider.generate = AsyncMock(return_value=("bad json output", None))
    tenant = _make_tenant()
    revise_node = make_revise_node(tenant, provider)
    state = _make_state(answer="Previous answer", retrieved_docs=[_make_chunk()])
    result = await revise_node(state)

    assert result["answer"] == "Previous answer"
    assert result["is_complete"] is True


# ---------------------------------------------------------------------------
# Integration tests — full graph flow
# ---------------------------------------------------------------------------


async def test_reflexion_graph_one_iteration_then_complete() -> None:
    """Graph should: draft → retrieve → revise (complete) → END."""
    tenant = _make_tenant()
    provider = _make_provider()

    call_log: list[str] = []

    async def mock_draft(state: ReflexionState) -> dict:
        call_log.append("draft")
        return {
            "answer": "Initial answer.",
            "reflection": "Need more data.",
            "search_queries": ["sub query"],
            "is_complete": False,
            "iteration_count": 1,
            "usage": None,
        }

    async def mock_retrieve(state: ReflexionState) -> dict:
        call_log.append("retrieve")
        return {"retrieved_docs": [_make_chunk()]}

    async def mock_revise(state: ReflexionState) -> dict:
        call_log.append("revise")
        return {
            "answer": "Final answer.",
            "reflection": "",
            "search_queries": [],
            "is_complete": True,
            "iteration_count": 2,
            "sources": [],
            "usage": None,
        }

    with (
        patch("app.agent.reflexion_agent.make_draft_node", return_value=mock_draft),
        patch("app.agent.reflexion_agent.make_retrieve_node", return_value=mock_retrieve),
        patch("app.agent.reflexion_agent.make_revise_node", return_value=mock_revise),
    ):
        graph = create_reflexion_graph(tenant, provider)
        initial: ReflexionState = {
            "query": "test",
            "answer": "",
            "reflection": "",
            "search_queries": [],
            "retrieved_docs": [],
            "sources": [],
            "is_complete": False,
            "iteration_count": 0,
            "usage": None,
        }
        final_state = await graph.ainvoke(initial)

    assert call_log == ["draft", "retrieve", "revise"]
    assert final_state["answer"] == "Final answer."


async def test_reflexion_graph_loops_until_max_iterations() -> None:
    """Graph should loop retrieve→revise until iteration cap, then END."""
    tenant = _make_tenant()
    provider = _make_provider()

    revise_count = 0

    async def mock_draft(state: ReflexionState) -> dict:
        return {
            "answer": "Draft.",
            "reflection": "More needed.",
            "search_queries": ["q1"],
            "is_complete": False,
            "iteration_count": 1,
            "usage": None,
        }

    async def mock_retrieve(state: ReflexionState) -> dict:
        return {"retrieved_docs": []}

    async def mock_revise(state: ReflexionState) -> dict:
        nonlocal revise_count
        revise_count += 1
        iteration = state.get("iteration_count", 1)
        return {
            "answer": f"Answer iter {iteration}.",
            "reflection": "Still incomplete.",
            "search_queries": ["more q"],
            "is_complete": False,
            "iteration_count": iteration + 1,
            "sources": [],
            "usage": None,
        }

    with (
        patch("app.agent.reflexion_agent.make_draft_node", return_value=mock_draft),
        patch("app.agent.reflexion_agent.make_retrieve_node", return_value=mock_retrieve),
        patch("app.agent.reflexion_agent.make_revise_node", return_value=mock_revise),
    ):
        graph = create_reflexion_graph(tenant, provider)
        initial: ReflexionState = {
            "query": "test",
            "answer": "",
            "reflection": "",
            "search_queries": [],
            "retrieved_docs": [],
            "sources": [],
            "is_complete": False,
            "iteration_count": 0,
            "usage": None,
        }
        await graph.ainvoke(initial)

    # draft produces iteration_count=1; revise increments; should stop at MAX_ITERATIONS
    assert revise_count == MAX_ITERATIONS - 1


async def test_run_reflexion_returns_tuple() -> None:
    """run_reflexion convenience wrapper returns (answer, sources, usage) tuple."""
    tenant = _make_tenant()
    provider = _make_provider()

    expected_source = Source(
        doc_number="EA-SOP-001", title="Screen Guide", page_number=3, s3_key="ea/sop.pdf"
    )
    expected_usage = TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150)

    async def mock_draft(state: ReflexionState) -> dict:
        return {
            "answer": "Initial.",
            "reflection": "",
            "search_queries": [],
            "is_complete": True,
            "iteration_count": 1,
            "usage": expected_usage,
        }

    async def mock_retrieve(state: ReflexionState) -> dict:
        return {"retrieved_docs": []}

    async def mock_revise(state: ReflexionState) -> dict:
        return {
            "answer": "Torque is 370 Nm.",
            "reflection": "",
            "search_queries": [],
            "is_complete": True,
            "iteration_count": 2,
            "sources": [expected_source],
            "usage": expected_usage,
        }

    with (
        patch("app.agent.reflexion_agent.make_draft_node", return_value=mock_draft),
        patch("app.agent.reflexion_agent.make_retrieve_node", return_value=mock_retrieve),
        patch("app.agent.reflexion_agent.make_revise_node", return_value=mock_revise),
    ):
        answer, sources, usage = await run_reflexion("What torque?", tenant, provider)

    assert answer == "Torque is 370 Nm."
    assert len(sources) == 1
    assert sources[0].doc_number == "EA-SOP-001"
    assert usage is not None
