from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import ingest, chat, documents, admin

router = APIRouter()
router.include_router(ingest.router, prefix="/ingest", tags=["ingest"])
router.include_router(chat.router, prefix="/chat", tags=["chat"])
router.include_router(documents.router, prefix="/documents", tags=["documents"])
router.include_router(admin.router, prefix="/admin", tags=["admin"])
