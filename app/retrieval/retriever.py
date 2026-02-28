from __future__ import annotations

import asyncio
import logging

from app.config import settings
from app.core.providers.base import BaseLLMProvider
from app.db.models import Tenant
from app.db.session import tenant_session
from app.retrieval import bm25_ranker, filter_extractor, keyword_generator, vector_store
from app.schemas.retrieval import RetrievedChunk

logger = logging.getLogger(__name__)


async def retrieve(
    query: str,
    tenant: Tenant,
    provider: BaseLLMProvider,
    k: int | None = None,
) -> list[RetrievedChunk]:
    """Hybrid retrieval: vector search + BM25Plus re-ranking.

    Pipeline:
      1. Parallelise: extract metadata filters + generate BM25 keywords + embed query
      2. Vector search with filters (fetch k * multiplier candidates)
      3. BM25Plus re-rank → return top-k

    The tenant's restricted_doc_types are enforced in vector_store — they never
    appear in the returned candidates.
    """
    k = k or settings.max_retrieval_k
    fetch_k = k * settings.retrieval_fetch_multiplier

    # Run filter extraction, keyword generation, and query embedding in parallel
    filters, keywords, query_embedding = await asyncio.gather(
        filter_extractor.extract(query, tenant, provider),
        keyword_generator.generate(query, tenant, provider),
        provider.embed(query),
    )

    logger.info(
        "retriever.retrieve",
        extra={
            "tenant": tenant.tenant_id,
            "k": k,
            "fetch_k": fetch_k,
            "filters": filters.model_dump(exclude_none=True),
            "keywords": keywords,
        },
    )

    session_maker = tenant_session(tenant.schema_name)
    async with session_maker() as session:
        candidates = await vector_store.search(
            query_embedding=query_embedding,
            filters=filters,
            tenant=tenant,
            session=session,
            fetch_k=fetch_k,
        )

    return bm25_ranker.rank(candidates, keywords, k)
