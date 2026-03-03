from __future__ import annotations

import uuid

from app.retrieval.bm25_ranker import rank
from app.schemas.retrieval import RetrievedChunk


def _chunk(content: str, heading: str = "", score: float = 0.5) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        doc_number="EA-TEST-001",
        doc_type="SOP",
        title="Test Doc",
        classification="STANDARD",
        s3_key="tenants/ea/test.pdf",
        page_number=1,
        heading=heading or None,
        content=content,
        similarity_score=score,
    )


def test_rank_returns_top_k() -> None:
    candidates = [
        _chunk("installation procedure for screen panels"),
        _chunk("bolt torque specifications M20"),
        _chunk("tensioning method for banana screens"),
        _chunk("rubber compound formulation register"),
        _chunk("safety requirements for mining operations"),
    ]
    result = rank(candidates, ["installation", "procedure", "screen"], k=3)
    assert len(result) == 3


def test_rank_relevant_chunk_first() -> None:
    candidates = [
        _chunk("rubber compound grade 60 shore A"),
        _chunk("screen installation procedure step by step"),
        _chunk("digital AI strategy roadmap"),
    ]
    result = rank(candidates, ["screen", "installation", "procedure"], k=3)
    assert "installation" in result[0].content.lower()


def test_rank_empty_candidates_returns_empty() -> None:
    result = rank([], ["installation", "procedure"], k=5)
    assert result == []


def test_rank_no_keywords_returns_top_k_by_order() -> None:
    candidates = [_chunk(f"content {i}") for i in range(5)]
    result = rank(candidates, [], k=3)
    assert len(result) == 3
    assert result == candidates[:3]


def test_rank_fewer_candidates_than_k() -> None:
    candidates = [_chunk("only one chunk")]
    result = rank(candidates, ["installation"], k=5)
    assert len(result) == 1
    assert result[0].content == "only one chunk"


def test_rank_uses_heading_in_scoring() -> None:
    candidates = [
        _chunk("general safety information", heading="Safety"),
        _chunk("general safety information", heading="Installation Procedure"),
    ]
    result = rank(candidates, ["installation", "procedure"], k=2)
    # Chunk with matching heading should score higher
    assert result[0].heading == "Installation Procedure"


def test_rank_k_larger_than_candidates() -> None:
    candidates = [_chunk("a"), _chunk("b")]
    result = rank(candidates, ["a"], k=10)
    assert len(result) == 2
