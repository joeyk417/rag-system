from __future__ import annotations

from fastapi import APIRouter, Depends

from app.agent.crag_agent import run_crag
from app.agent.reflexion_agent import run_reflexion
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
    """Query the knowledge base using the selected agent.

    agent_type="crag" (default): single retrieve-grade-generate cycle with web fallback.
    agent_type="reflexion": multi-hop iterative draft→retrieve→revise loop. With reflexion, usage.total_tokens will be higher (draft + revise calls) and the answer tends to be more comprehensive on cross-document queries
    """
    if body.agent_type == "reflexion":
        answer, sources, usage = await run_reflexion(body.query, tenant, provider)
    else:
        answer, sources, usage = await run_crag(body.query, tenant, provider)
    return ChatResponse(answer=answer, sources=sources, query=body.query, usage=usage)
