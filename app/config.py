from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # OpenAI
    openai_api_key: str = Field(default="")
    openai_llm_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dimensions: int = 1536

    # Database
    database_url: str = Field(default="postgresql+asyncpg://raguser:ragpass@localhost:5432/ragdb")

    # AWS
    aws_region: str = "ap-southeast-2"
    aws_access_key_id: str = Field(default="")
    aws_secret_access_key: str = Field(default="")
    s3_bucket_name: str = Field(default="rag-system-docs-dev")

    # App
    app_env: str = "development"
    admin_api_key: str = Field(default="")
    log_level: str = "INFO"
    max_retrieval_k: int = 5
    retrieval_fetch_multiplier: int = 20

    # Web search
    tavily_api_key: str = Field(default="")

    # CORS (comma-separated origins, e.g. "http://localhost:3000,https://staging.example.com")
    cors_origins: list[str] = Field(default=["*"])

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors(cls, v: str | list) -> list[str]:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v


settings = Settings()
