from __future__ import annotations

from fastapi import APIRouter, Depends

from app.agent.crag_agent import run_crag
from app.core.providers.base import BaseLLMProvider
from app.db.models import Tenant
from app.dependencies import get_provider, get_tenant
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter()


@router.post("", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    tenant: Tenant = Depends(get_tenant),
    provider: BaseLLMProvider = Depends(get_provider),
) -> ChatResponse:
    """Query the knowledge base using the CRAG agent.

    Returns the generated answer and source document citations.
    """
    answer, sources, usage = await run_crag(body.query, tenant, provider)
    return ChatResponse(answer=answer, sources=sources, query=body.query, usage=usage)
