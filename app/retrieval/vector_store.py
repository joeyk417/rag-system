from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Tenant
from app.retrieval.filter_extractor import QueryFilters
from app.schemas.retrieval import RetrievedChunk

logger = logging.getLogger(__name__)


async def search(
    query_embedding: list[float],
    filters: QueryFilters,
    tenant: Tenant,
    session: AsyncSession,
    fetch_k: int,
) -> list[RetrievedChunk]:
    """Cosine similarity search against pgvector with optional metadata filters.

    Always excludes doc_types listed in tenant.config["restricted_doc_types"].
    The session must already be scoped to the tenant's schema via tenant_session().
    """
    config: dict = tenant.config or {}
    restricted: list[str] = config.get("restricted_doc_types", [])

    # Build WHERE clause dynamically
    where_clauses = ["d.status = 'completed'"]
    params: dict = {
        "query_vec": str(query_embedding),
        "fetch_k": fetch_k,
    }

    if filters.doc_type:
        where_clauses.append("d.doc_type = :doc_type")
        params["doc_type"] = filters.doc_type

    if filters.doc_number:
        where_clauses.append("d.doc_number = :doc_number")
        params["doc_number"] = filters.doc_number

    if filters.classification:
        where_clauses.append("d.classification = :classification")
        params["classification"] = filters.classification

    if restricted:
        # Build positional placeholders :r0, :r1, ...
        placeholders = ", ".join(f":r{i}" for i in range(len(restricted)))
        where_clauses.append(f"d.doc_type NOT IN ({placeholders})")
        for i, rt in enumerate(restricted):
            params[f"r{i}"] = rt

    where_sql = " AND ".join(where_clauses)

    # schema_translate_map only applies to ORM queries, not raw text().
    # Prefix table names explicitly with the tenant schema.
    schema = tenant.schema_name
    sql = text(
        f"""
        SELECT
            c.id            AS chunk_id,
            c.document_id,
            c.page_number,
            c.heading,
            c.content,
            d.doc_number,
            d.doc_type,
            d.title,
            d.classification,
            d.s3_key,
            c.embedding <=> CAST(:query_vec AS vector) AS similarity_score
        FROM {schema}.chunks c
        JOIN {schema}.documents d ON c.document_id = d.id
        WHERE {where_sql}
        ORDER BY c.embedding <=> CAST(:query_vec AS vector)
        LIMIT :fetch_k
        """
    )

    result = await session.execute(sql, params)
    rows = result.mappings().all()

    logger.info(
        "vector_store.search",
        extra={
            "tenant": tenant.tenant_id,
            "fetch_k": fetch_k,
            "rows_returned": len(rows),
            "filters": filters.model_dump(exclude_none=True),
            "restricted_excluded": restricted,
        },
    )

    return [
        RetrievedChunk(
            chunk_id=UUID(str(row["chunk_id"])),
            document_id=UUID(str(row["document_id"])),
            doc_number=row["doc_number"],
            doc_type=row["doc_type"],
            title=row["title"],
            classification=row["classification"],
            s3_key=row["s3_key"],
            page_number=row["page_number"],
            heading=row["heading"],
            content=row["content"],
            similarity_score=float(row["similarity_score"]),
        )
        for row in rows
    ]
