from __future__ import annotations

import logging
import time

from openai import AsyncOpenAI

from app.config import settings
from app.core.providers.base import BaseLLMProvider, LLMUsage

logger = logging.getLogger(__name__)

_EMBED_BATCH_SIZE = 100


class OpenAIProvider(BaseLLMProvider):
    def __init__(self) -> None:
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def generate(
        self, system_prompt: str, user_message: str, **kwargs: object
    ) -> tuple[str, LLMUsage | None]:
        start = time.monotonic()
        response = await self._client.chat.completions.create(
            model=settings.openai_llm_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            **kwargs,  # type: ignore[arg-type]
        )
        latency_ms = int((time.monotonic() - start) * 1000)
        raw_usage = response.usage
        usage = (
            LLMUsage(
                input_tokens=raw_usage.prompt_tokens,
                output_tokens=raw_usage.completion_tokens,
            )
            if raw_usage
            else None
        )
        logger.info(
            "OpenAI generate",
            extra={
                "model": settings.openai_llm_model,
                "prompt_tokens": usage.input_tokens if usage else None,
                "completion_tokens": usage.output_tokens if usage else None,
                "latency_ms": latency_ms,
            },
        )
        return response.choices[0].message.content or "", usage

    async def embed(self, text: str) -> list[float]:
        vectors = await self.embed_batch([text])
        return vectors[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        all_vectors: list[list[float]] = []
        for i in range(0, len(texts), _EMBED_BATCH_SIZE):
            batch = texts[i : i + _EMBED_BATCH_SIZE]
            start = time.monotonic()
            response = await self._client.embeddings.create(
                model=settings.openai_embedding_model,
                input=batch,
                dimensions=settings.openai_embedding_dimensions,
            )
            latency_ms = int((time.monotonic() - start) * 1000)
            usage = response.usage
            logger.info(
                "OpenAI embed_batch",
                extra={
                    "model": settings.openai_embedding_model,
                    "batch_size": len(batch),
                    "prompt_tokens": usage.prompt_tokens if usage else None,
                    "latency_ms": latency_ms,
                },
            )
            all_vectors.extend([item.embedding for item in response.data])

        return all_vectors
