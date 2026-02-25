from __future__ import annotations

import logging
import logging.config
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from app.api.v1.router import router as api_router
from app.config import settings


def _configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    _configure_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting RAG System API", extra={"env": settings.app_env})
    yield
    logger.info("Shutting down RAG System API")


app = FastAPI(
    title="RAG System API",
    version="1.0.0",
    description="Multi-tenant document intelligence system",
    lifespan=lifespan,
)


app.include_router(api_router, prefix="/api/v1")


@app.get("/api/v1/health", tags=["health"])
async def health() -> dict[str, Any]:
    return {"status": "ok", "env": settings.app_env}
