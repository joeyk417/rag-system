from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMUsage:
    """Token usage returned by a generate() call."""

    input_tokens: int
    output_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class BaseLLMProvider(ABC):
    """Abstract LLM + embedding provider.

    Concrete implementations: OpenAIProvider (Phase 1), BedrockProvider (Phase 2).
    The active provider is selected per-tenant based on tenants.config.data_sovereignty.
    """

    @abstractmethod
    async def generate(
        self, system_prompt: str, user_message: str, **kwargs: object
    ) -> tuple[str, LLMUsage | None]:
        """Generate a text response. Returns (answer, usage)."""
        ...

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """Return embedding vector for a single text."""
        ...

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Return embedding vectors for a batch of texts."""
        ...
