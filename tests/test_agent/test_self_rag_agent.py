from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.self_rag_agent import create_self_rag_graph, run_self_rag
from app.agent.self_rag_nodes import (
    MAX_ITERATIONS,
    make_generate_node,
    make_grade_documents_node,
    make_retrieve_node,
    make_transform_query_node,
    make_check_answer_quality,
    should_generate,
)
from app.agent.self_rag_state import (
    GradeAnswer,
    GradeDocuments,
    GradeHallucinations,
    SearchQueries,
    SelfRAGState,
)
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
    provider.generate = AsyncMock(
        return_value=(json.dumps({"binary_score": "yes"}), None)
    )
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


def _make_state(**overrides: object) -> SelfRAGState:
    base: SelfRAGState = {
        "query": "test query",
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


def test_grade_documents_schema_valid() -> None:
    assert GradeDocuments(binary_score="yes").binary_score == "yes"
    assert GradeDocuments(binary_score="no").binary_score == "no"


def test_grade_documents_schema_invalid() -> None:
    with pytest.raises(Exception):
        GradeDocuments(binary_score="maybe")


def test_grade_hallucinations_schema_valid() -> None:
    assert GradeHallucinations(binary_score="yes").binary_score == "yes"
    assert GradeHallucinations(binary_score="no").binary_score == "no"


def test_grade_answer_schema_valid() -> None:
    assert GradeAnswer(binary_score="yes").binary_score == "yes"
    assert GradeAnswer(binary_score="no").binary_score == "no"


def test_search_queries_schema_valid() -> None:
    sq = SearchQueries(queries=["query one", "query two"])
    assert len(sq.queries) == 2


# ---------------------------------------------------------------------------
# Unit tests — should_generate router
# ---------------------------------------------------------------------------


def test_should_generate_with_docs() -> None:
    state = _make_state(retrieved_docs=[_make_chunk()])
    assert should_generate(state) == "generate"


def test_should_generate_empty_docs() -> None:
    state = _make_state(retrieved_docs=[])
    assert should_generate(state) == "transform_query"


# ---------------------------------------------------------------------------
# Unit tests — check_answer_quality router
# ---------------------------------------------------------------------------


async def test_check_answer_quality_max_iterations() -> None:
    """Hitting MAX_ITERATIONS cap forces END regardless of grading."""
    tenant = _make_tenant()
    provider = _make_provider()
    check_fn = make_check_answer_quality(tenant, provider)
    state = _make_state(
        iteration_count=MAX_ITERATIONS,
        answer="Some answer.",
        retrieved_docs=[_make_chunk()],
    )
    result = await check_fn(state)
    assert result == "END"
    provider.generate.assert_not_called()


async def test_check_answer_quality_hallucinating() -> None:
    """Hallucinating answer (binary_score=no) → retry generate."""
    tenant = _make_tenant()
    provider = _make_provider()
    provider.generate = AsyncMock(
        return_value=(json.dumps({"binary_score": "no"}), None)
    )
    check_fn = make_check_answer_quality(tenant, provider)
    state = _make_state(
        iteration_count=1,
        answer="Some answer.",
        retrieved_docs=[_make_chunk()],
    )
    result = await check_fn(state)
    assert result == "generate"


async def test_check_answer_quality_grounded_and_complete() -> None:
    """Grounded + complete answer → END."""
    tenant = _make_tenant()
    provider = _make_provider()
    # Both hallucination and answer grade return "yes"
    provider.generate = AsyncMock(
        return_value=(json.dumps({"binary_score": "yes"}), None)
    )
    check_fn = make_check_answer_quality(tenant, provider)
    state = _make_state(
        iteration_count=1,
        answer="Complete answer.",
        retrieved_docs=[_make_chunk()],
    )
    result = await check_fn(state)
    assert result == "END"


async def test_check_answer_quality_grounded_but_incomplete() -> None:
    """Grounded but incomplete answer → transform_query."""
    tenant = _make_tenant()
    provider = _make_provider()
    # First call (hallucination): "yes" (grounded). Second call (answer quality): "no" (incomplete).
    provider.generate = AsyncMock(
        side_effect=[
            (json.dumps({"binary_score": "yes"}), None),
            (json.dumps({"binary_score": "no"}), None),
        ]
    )
    check_fn = make_check_answer_quality(tenant, provider)
    state = _make_state(
        iteration_count=1,
        answer="Incomplete answer.",
        retrieved_docs=[_make_chunk()],
    )
    result = await check_fn(state)
    assert result == "transform_query"


async def test_check_answer_quality_parse_error_fail_open() -> None:
    """Parse error in hallucination check → assume grounded (fail-open), then check answer quality."""
    tenant = _make_tenant()
    provider = _make_provider()
    provider.generate = AsyncMock(
        side_effect=[
            ("not valid json", None),              # hallucination check fails → fail-open (grounded=True)
            (json.dumps({"binary_score": "yes"}), None),  # answer quality → complete
        ]
    )
    check_fn = make_check_answer_quality(tenant, provider)
    state = _make_state(
        iteration_count=1,
        answer="Some answer.",
        retrieved_docs=[_make_chunk()],
    )
    result = await check_fn(state)
    assert result == "END"


# ---------------------------------------------------------------------------
# Unit tests — retrieve_node
# ---------------------------------------------------------------------------


async def test_retrieve_node_uses_original_query_when_no_rewrites() -> None:
    """When rewritten_queries is empty, retrieve using original query."""
    tenant = _make_tenant()
    provider = _make_provider()
    chunk = _make_chunk()
    captured_queries: list[str] = []

    async def mock_retrieve(query: str, t: object, p: object, **kw: object) -> list[RetrievedChunk]:
        captured_queries.append(query)
        return [chunk]

    state = _make_state(query="What is the torque spec?", rewritten_queries=[])

    with patch("app.agent.self_rag_nodes.retriever.retrieve", side_effect=mock_retrieve):
        node = make_retrieve_node(tenant, provider)
        result = await node(state)

    assert captured_queries == ["What is the torque spec?"]
    assert len(result["retrieved_docs"]) == 1


async def test_retrieve_node_uses_rewritten_queries() -> None:
    """When rewritten_queries is present, retrieve for each sub-query."""
    tenant = _make_tenant()
    provider = _make_provider()
    chunk_a = _make_chunk(doc_number="EA-SOP-001")
    chunk_b = _make_chunk(doc_number="EA-ENG-DRW-7834")
    captured_queries: list[str] = []

    async def mock_retrieve(query: str, t: object, p: object, **kw: object) -> list[RetrievedChunk]:
        captured_queries.append(query)
        return [chunk_a] if "torque" in query else [chunk_b]

    state = _make_state(
        query="original query",
        rewritten_queries=["torque spec", "installation guide"],
    )

    with patch("app.agent.self_rag_nodes.retriever.retrieve", side_effect=mock_retrieve):
        node = make_retrieve_node(tenant, provider)
        result = await node(state)

    assert captured_queries == ["torque spec", "installation guide"]
    assert len(result["retrieved_docs"]) == 2


async def test_retrieve_node_deduplicates_by_chunk_id() -> None:
    """Same chunk_id from two sub-queries should only appear once."""
    shared_id = uuid.uuid4()
    chunk_a = _make_chunk(chunk_id=shared_id, doc_number="EA-SOP-001")
    chunk_b = _make_chunk(chunk_id=shared_id, doc_number="EA-SOP-001")  # duplicate
    chunk_c = _make_chunk(doc_number="EA-ENG-DRW-7834")  # unique

    tenant = _make_tenant()
    provider = _make_provider()
    call_count = 0

    async def mock_retrieve(query: str, t: object, p: object, **kw: object) -> list[RetrievedChunk]:
        nonlocal call_count
        call_count += 1
        return [chunk_a] if call_count == 1 else [chunk_b, chunk_c]

    state = _make_state(rewritten_queries=["q1", "q2"])

    with patch("app.agent.self_rag_nodes.retriever.retrieve", side_effect=mock_retrieve):
        node = make_retrieve_node(tenant, provider)
        result = await node(state)

    assert len(result["retrieved_docs"]) == 2
    ids = [d.chunk_id for d in result["retrieved_docs"]]
    assert shared_id in ids


# ---------------------------------------------------------------------------
# Unit tests — grade_documents_node
# ---------------------------------------------------------------------------


async def test_grade_documents_keeps_relevant_chunks() -> None:
    """Chunks graded 'yes' are kept in retrieved_docs."""
    tenant = _make_tenant()
    provider = _make_provider()
    provider.generate = AsyncMock(
        return_value=(json.dumps({"binary_score": "yes"}), None)
    )
    chunk = _make_chunk()
    state = _make_state(retrieved_docs=[chunk])

    node = make_grade_documents_node(tenant, provider)
    result = await node(state)

    assert len(result["retrieved_docs"]) == 1


async def test_grade_documents_discards_irrelevant_chunks() -> None:
    """Chunks graded 'no' are removed from retrieved_docs."""
    tenant = _make_tenant()
    provider = _make_provider()
    provider.generate = AsyncMock(
        return_value=(json.dumps({"binary_score": "no"}), None)
    )
    chunk = _make_chunk()
    state = _make_state(retrieved_docs=[chunk])

    node = make_grade_documents_node(tenant, provider)
    result = await node(state)

    assert result["retrieved_docs"] == []


async def test_grade_documents_filters_mixed_chunks() -> None:
    """Only chunks graded 'yes' survive; 'no' chunks are discarded."""
    tenant = _make_tenant()
    provider = _make_provider()
    chunk_a = _make_chunk(doc_number="EA-SOP-001")
    chunk_b = _make_chunk(doc_number="EA-ENG-DRW-7834")

    # First chunk relevant, second irrelevant
    provider.generate = AsyncMock(
        side_effect=[
            (json.dumps({"binary_score": "yes"}), None),
            (json.dumps({"binary_score": "no"}), None),
        ]
    )
    state = _make_state(retrieved_docs=[chunk_a, chunk_b])

    node = make_grade_documents_node(tenant, provider)
    result = await node(state)

    assert len(result["retrieved_docs"]) == 1
    assert result["retrieved_docs"][0].doc_number == "EA-SOP-001"


async def test_grade_documents_fail_open_on_parse_error() -> None:
    """JSON parse error during grading keeps the chunk (fail-open)."""
    tenant = _make_tenant()
    provider = _make_provider()
    provider.generate = AsyncMock(return_value=("not json", None))
    chunk = _make_chunk()
    state = _make_state(retrieved_docs=[chunk])

    node = make_grade_documents_node(tenant, provider)
    result = await node(state)

    assert len(result["retrieved_docs"]) == 1


async def test_grade_documents_accumulates_usage() -> None:
    """Usage is accumulated across all per-document grading calls."""
    from app.core.providers.base import LLMUsage

    tenant = _make_tenant()
    provider = _make_provider()
    usage_per_call = LLMUsage(input_tokens=10, output_tokens=5)
    provider.generate = AsyncMock(
        return_value=(json.dumps({"binary_score": "yes"}), usage_per_call)
    )
    chunks = [_make_chunk(), _make_chunk()]
    state = _make_state(retrieved_docs=chunks)

    node = make_grade_documents_node(tenant, provider)
    result = await node(state)

    assert result["usage"] is not None
    assert result["usage"].input_tokens == 20  # 10 per chunk × 2


# ---------------------------------------------------------------------------
# Unit tests — generate_node
# ---------------------------------------------------------------------------


async def test_generate_node_returns_answer_and_sources() -> None:
    tenant = _make_tenant()
    provider = _make_provider()
    provider.generate = AsyncMock(
        return_value=("The torque spec is 370 Nm [1].", None)
    )
    chunk = _make_chunk(doc_number="EA-SOP-001", page=5)
    state = _make_state(retrieved_docs=[chunk])

    node = make_generate_node(tenant, provider)
    result = await node(state)

    assert result["answer"] == "The torque spec is 370 Nm [1]."
    assert len(result["sources"]) == 1
    assert result["sources"][0].doc_number == "EA-SOP-001"


async def test_generate_node_increments_iteration_count() -> None:
    tenant = _make_tenant()
    provider = _make_provider()
    provider.generate = AsyncMock(return_value=("Answer.", None))
    state = _make_state(retrieved_docs=[_make_chunk()], iteration_count=1)

    node = make_generate_node(tenant, provider)
    result = await node(state)

    assert result["iteration_count"] == 2


async def test_generate_node_handles_llm_error() -> None:
    """LLM exception produces a fallback answer, not a crash."""
    tenant = _make_tenant()
    provider = _make_provider()
    provider.generate = AsyncMock(side_effect=RuntimeError("LLM unavailable"))
    state = _make_state(retrieved_docs=[_make_chunk()])

    node = make_generate_node(tenant, provider)
    result = await node(state)

    assert "unable to generate" in result["answer"].lower()


# ---------------------------------------------------------------------------
# Unit tests — transform_query_node
# ---------------------------------------------------------------------------


async def test_transform_query_node_accumulates_queries() -> None:
    """New queries are appended to existing rewritten_queries, not replaced."""
    tenant = _make_tenant()
    provider = _make_provider()
    provider.generate = AsyncMock(
        return_value=(json.dumps({"queries": ["new query A", "new query B"]}), None)
    )
    state = _make_state(
        query="original",
        rewritten_queries=["previous query"],
    )

    node = make_transform_query_node(tenant, provider)
    result = await node(state)

    assert "previous query" in result["rewritten_queries"]
    assert "new query A" in result["rewritten_queries"]
    assert "new query B" in result["rewritten_queries"]
    assert len(result["rewritten_queries"]) == 3


async def test_transform_query_node_parse_error_appends_original() -> None:
    """Parse error falls back to appending the original query."""
    tenant = _make_tenant()
    provider = _make_provider()
    provider.generate = AsyncMock(return_value=("bad json", None))
    state = _make_state(query="What is the torque?", rewritten_queries=[])

    node = make_transform_query_node(tenant, provider)
    result = await node(state)

    assert "What is the torque?" in result["rewritten_queries"]


# ---------------------------------------------------------------------------
# Integration tests — full graph flow
# ---------------------------------------------------------------------------


async def test_self_rag_graph_happy_path() -> None:
    """Full graph: retrieve → grade (relevant) → generate → quality check (complete) → END."""
    tenant = _make_tenant()
    provider = _make_provider()
    call_log: list[str] = []

    async def mock_retrieve(state: SelfRAGState) -> dict:
        call_log.append("retrieve")
        return {"retrieved_docs": [_make_chunk()]}

    async def mock_grade(state: SelfRAGState) -> dict:
        call_log.append("grade_documents")
        return {"retrieved_docs": state["retrieved_docs"], "usage": None}

    async def mock_generate(state: SelfRAGState) -> dict:
        call_log.append("generate")
        return {
            "answer": "The torque spec is 370 Nm.",
            "sources": [],
            "usage": None,
            "iteration_count": 1,
        }

    async def mock_transform(state: SelfRAGState) -> dict:
        call_log.append("transform_query")
        return {"rewritten_queries": ["sub-query"]}

    with (
        patch("app.agent.self_rag_agent.make_retrieve_node", return_value=mock_retrieve),
        patch("app.agent.self_rag_agent.make_grade_documents_node", return_value=mock_grade),
        patch("app.agent.self_rag_agent.make_generate_node", return_value=mock_generate),
        patch("app.agent.self_rag_agent.make_transform_query_node", return_value=mock_transform),
        patch(
            "app.agent.self_rag_agent.make_check_answer_quality",
            return_value=lambda state: "END",
        ),
    ):
        graph = create_self_rag_graph(tenant, provider)
        initial: SelfRAGState = {
            "query": "What is the torque spec?",
            "rewritten_queries": [],
            "retrieved_docs": [],
            "answer": "",
            "sources": [],
            "usage": None,
            "iteration_count": 0,
        }
        final_state = await graph.ainvoke(initial)

    assert "retrieve" in call_log
    assert "grade_documents" in call_log
    assert "generate" in call_log
    assert "transform_query" not in call_log
    assert final_state["answer"] == "The torque spec is 370 Nm."


async def test_self_rag_graph_transform_then_retrieve() -> None:
    """Grade returns empty docs → transform_query → retrieve again → grade (relevant) → generate → END."""
    tenant = _make_tenant()
    provider = _make_provider()
    call_log: list[str] = []
    retrieve_count = 0

    async def mock_retrieve(state: SelfRAGState) -> dict:
        nonlocal retrieve_count
        retrieve_count += 1
        call_log.append("retrieve")
        # Second retrieval returns a doc
        return {"retrieved_docs": [_make_chunk()] if retrieve_count > 1 else []}

    async def mock_grade(state: SelfRAGState) -> dict:
        call_log.append("grade_documents")
        return {"retrieved_docs": state["retrieved_docs"], "usage": None}

    async def mock_generate(state: SelfRAGState) -> dict:
        call_log.append("generate")
        return {
            "answer": "Answer after transform.",
            "sources": [],
            "usage": None,
            "iteration_count": 1,
        }

    async def mock_transform(state: SelfRAGState) -> dict:
        call_log.append("transform_query")
        return {"rewritten_queries": ["focused sub-query"]}

    with (
        patch("app.agent.self_rag_agent.make_retrieve_node", return_value=mock_retrieve),
        patch("app.agent.self_rag_agent.make_grade_documents_node", return_value=mock_grade),
        patch("app.agent.self_rag_agent.make_generate_node", return_value=mock_generate),
        patch("app.agent.self_rag_agent.make_transform_query_node", return_value=mock_transform),
        patch(
            "app.agent.self_rag_agent.make_check_answer_quality",
            return_value=lambda state: "END",
        ),
    ):
        graph = create_self_rag_graph(tenant, provider)
        initial: SelfRAGState = {
            "query": "What is the compound spec?",
            "rewritten_queries": [],
            "retrieved_docs": [],
            "answer": "",
            "sources": [],
            "usage": None,
            "iteration_count": 0,
        }
        final_state = await graph.ainvoke(initial)

    assert call_log.count("retrieve") == 2
    assert "transform_query" in call_log
    assert "generate" in call_log
    assert final_state["answer"] == "Answer after transform."


# ---------------------------------------------------------------------------
# Integration test — run_self_rag wrapper
# ---------------------------------------------------------------------------


async def test_run_self_rag_returns_tuple() -> None:
    """run_self_rag convenience wrapper returns (answer, sources, usage) tuple."""
    tenant = _make_tenant()
    provider = _make_provider()

    expected_source = Source(
        doc_number="EA-SOP-001",
        title="Screen Guide",
        page_number=3,
        s3_key="ea/sop.pdf",
    )
    expected_usage = TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150)

    async def mock_retrieve(state: SelfRAGState) -> dict:
        return {"retrieved_docs": [_make_chunk()]}

    async def mock_grade(state: SelfRAGState) -> dict:
        return {"retrieved_docs": state["retrieved_docs"], "usage": None}

    async def mock_generate(state: SelfRAGState) -> dict:
        return {
            "answer": "Torque is 370 Nm.",
            "sources": [expected_source],
            "usage": expected_usage,
            "iteration_count": 1,
        }

    async def mock_transform(state: SelfRAGState) -> dict:
        return {"rewritten_queries": []}

    with (
        patch("app.agent.self_rag_agent.make_retrieve_node", return_value=mock_retrieve),
        patch("app.agent.self_rag_agent.make_grade_documents_node", return_value=mock_grade),
        patch("app.agent.self_rag_agent.make_generate_node", return_value=mock_generate),
        patch("app.agent.self_rag_agent.make_transform_query_node", return_value=mock_transform),
        patch(
            "app.agent.self_rag_agent.make_check_answer_quality",
            return_value=lambda state: "END",
        ),
    ):
        answer, sources, usage = await run_self_rag("What torque?", tenant, provider)

    assert answer == "Torque is 370 Nm."
    assert len(sources) == 1
    assert sources[0].doc_number == "EA-SOP-001"
    assert usage is not None
    assert usage.total_tokens == 150
