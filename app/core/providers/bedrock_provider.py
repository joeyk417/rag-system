from __future__ import annotations

from app.core.providers.base import BaseLLMProvider

# TODO: implement in Phase 2 (Task 2-5 of phase2-aws.md)
# Used when tenant.config.data_sovereignty == "AU"
# Models: anthropic.claude-haiku-4-5 (generation), amazon.titan-embed-text-v2 (embeddings)
# All calls stay within ap-southeast-2


class BedrockProvider(BaseLLMProvider):
    async def generate(self, system_prompt: str, user_message: str, **kwargs: object) -> str:
        raise NotImplementedError

    async def embed(self, text: str) -> list[float]:
        raise NotImplementedError

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError
