from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.retrieval.filter_extractor import QueryFilters
from app.retrieval.retriever import retrieve
from app.schemas.retrieval import RetrievedChunk


def _make_tenant(schema: str = "tenant_test") -> MagicMock:
    tenant = MagicMock()
    tenant.tenant_id = "test_tenant"
    tenant.schema_name = schema
    tenant.config = {}
    return tenant


def _make_provider(embedding: list[float] | None = None) -> MagicMock:
    provider = MagicMock()
    provider.embed = AsyncMock(return_value=embedding or [0.1] * 1536)
    return provider


def _chunk(content: str = "test content") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        doc_number="EA-SOP-001",
        doc_type="SOP",
        title="Test",
        classification="STANDARD",
        s3_key="tenants/ea/test.pdf",
        page_number=1,
        heading=None,
        content=content,
        similarity_score=0.2,
    )


@pytest.mark.asyncio
async def test_retrieve_returns_ranked_chunks() -> None:
    chunks = [_chunk(f"chunk {i}") for i in range(3)]
    provider = _make_provider()

    with (
        patch("app.retrieval.retriever.filter_extractor.extract", new=AsyncMock(return_value=QueryFilters())),
        patch("app.retrieval.retriever.keyword_generator.generate", new=AsyncMock(return_value=["screen", "installation"])),
        patch("app.retrieval.retriever.vector_store.search", new=AsyncMock(return_value=chunks)),
        patch("app.retrieval.retriever.bm25_ranker.rank", return_value=chunks[:2]) as mock_rank,
        patch("app.retrieval.retriever.tenant_session") as mock_ts,
    ):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_ts.return_value = MagicMock(return_value=mock_session)

        result = await retrieve("screen installation steps", _make_tenant(), provider, k=2)

    assert len(result) == 2
    mock_rank.assert_called_once()


@pytest.mark.asyncio
async def test_retrieve_calls_embed_once() -> None:
    provider = _make_provider()

    with (
        patch("app.retrieval.retriever.filter_extractor.extract", new=AsyncMock(return_value=QueryFilters())),
        patch("app.retrieval.retriever.keyword_generator.generate", new=AsyncMock(return_value=["kw1"])),
        patch("app.retrieval.retriever.vector_store.search", new=AsyncMock(return_value=[])),
        patch("app.retrieval.retriever.bm25_ranker.rank", return_value=[]),
        patch("app.retrieval.retriever.tenant_session") as mock_ts,
    ):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_ts.return_value = MagicMock(return_value=mock_session)

        await retrieve("any query", _make_tenant(), provider)

    provider.embed.assert_awaited_once_with("any query")


@pytest.mark.asyncio
async def test_retrieve_returns_empty_on_no_candidates() -> None:
    provider = _make_provider()

    with (
        patch("app.retrieval.retriever.filter_extractor.extract", new=AsyncMock(return_value=QueryFilters())),
        patch("app.retrieval.retriever.keyword_generator.generate", new=AsyncMock(return_value=[])),
        patch("app.retrieval.retriever.vector_store.search", new=AsyncMock(return_value=[])),
        patch("app.retrieval.retriever.bm25_ranker.rank", return_value=[]),
        patch("app.retrieval.retriever.tenant_session") as mock_ts,
    ):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_ts.return_value = MagicMock(return_value=mock_session)

        result = await retrieve("query with no results", _make_tenant(), provider)

    assert result == []


@pytest.mark.asyncio
async def test_retrieve_passes_filters_to_vector_store() -> None:
    filters = QueryFilters(doc_type="SOP")
    provider = _make_provider()

    with (
        patch("app.retrieval.retriever.filter_extractor.extract", new=AsyncMock(return_value=filters)),
        patch("app.retrieval.retriever.keyword_generator.generate", new=AsyncMock(return_value=["kw"])),
        patch("app.retrieval.retriever.vector_store.search", new=AsyncMock(return_value=[])) as mock_vs,
        patch("app.retrieval.retriever.bm25_ranker.rank", return_value=[]),
        patch("app.retrieval.retriever.tenant_session") as mock_ts,
    ):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_ts.return_value = MagicMock(return_value=mock_session)

        await retrieve("show me the SOP", _make_tenant(), provider)

    call_kwargs = mock_vs.call_args.kwargs
    assert call_kwargs["filters"].doc_type == "SOP"
