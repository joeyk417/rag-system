from __future__ import annotations

from app.core.providers.base import BaseLLMProvider
from app.ingestion.chunker import ChunkData


async def embed_chunks(
    chunks: list[ChunkData],
    provider: BaseLLMProvider,
) -> list[list[float]]:
    """Return embedding vectors for each chunk, in the same order.

    Batching is handled inside provider.embed_batch() (100 texts per call).
    """
    texts = [chunk.content for chunk in chunks]
    return await provider.embed_batch(texts)
