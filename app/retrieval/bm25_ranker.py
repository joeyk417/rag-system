from __future__ import annotations

import logging

from rank_bm25 import BM25Plus

from app.schemas.retrieval import RetrievedChunk

logger = logging.getLogger(__name__)


def rank(
    candidates: list[RetrievedChunk],
    keywords: list[str],
    k: int,
) -> list[RetrievedChunk]:
    """Re-rank vector search candidates using BM25Plus on heading + content.

    Mirrors reference_notebooks/02 rank_documents_by_keywords().
    Gracefully returns candidates[:k] if no keywords supplied or no candidates.
    """
    if not candidates:
        return []

    if not keywords:
        logger.warning("bm25_ranker: no keywords supplied — returning top-%d by vector score", k)
        return candidates[:k]

    query_tokens = " ".join(keywords).lower().split()

    doc_tokens = [
        f"{chunk.heading or ''} {chunk.content}".lower().split()
        for chunk in candidates
    ]

    bm25 = BM25Plus(doc_tokens)
    scores = bm25.get_scores(query_tokens)

    ranked_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)

    logger.info(
        "bm25_ranker.rank",
        extra={
            "candidates": len(candidates),
            "k": k,
            "top_score": float(scores[ranked_indices[0]]) if ranked_indices else 0.0,
        },
    )

    return [candidates[i] for i in ranked_indices[:k]]
