from __future__ import annotations

from app.core.providers.base import BaseLLMProvider

# TODO: implement in Task 5
# Uses openai.AsyncOpenAI client
# Logs: model, prompt_tokens, completion_tokens, latency_ms on every call
# embed() calls text-embedding-3-small (settings.openai_embedding_model)
# generate() calls gpt-4o-mini (settings.openai_llm_model)


class OpenAIProvider(BaseLLMProvider):
    async def generate(self, system_prompt: str, user_message: str, **kwargs: object) -> str:
        raise NotImplementedError

    async def embed(self, text: str) -> list[float]:
        raise NotImplementedError

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError
