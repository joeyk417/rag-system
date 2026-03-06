from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.adaptive_rag_agent import run_adaptive_rag
from app.agent.crag_agent import run_crag
from app.agent.reflexion_agent import run_reflexion
from app.agent.self_rag_agent import run_self_rag
from app.core.providers.base import BaseLLMProvider
from app.core.token_budget import check_token_budget, record_token_usage
from app.db.models import Tenant
from app.dependencies import get_db, get_provider, get_tenant
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    tenant: Tenant = Depends(get_tenant),
    provider: BaseLLMProvider = Depends(get_provider),
    session: AsyncSession = Depends(get_db),
) -> ChatResponse:
    """Query the knowledge base using the selected agent.

    agent_type="crag" (default): single retrieve-grade-generate cycle with web fallback.
    agent_type="reflexion": multi-hop iterative draft→retrieve→revise loop.
    agent_type="self_rag": per-doc relevance grading + hallucination detection + answer quality check.
    agent_type="adaptive_rag": intelligent router → Self-RAG / web search / SQL (stub) based on query intent.
    """
    await check_token_budget(session, tenant.tenant_id)

    try:
        if body.agent_type == "reflexion":
            answer, sources, usage = await run_reflexion(body.query, tenant, provider)
        elif body.agent_type == "self_rag":
            answer, sources, usage = await run_self_rag(body.query, tenant, provider)
        elif body.agent_type == "adaptive_rag":
            answer, sources, usage = await run_adaptive_rag(
                body.query, tenant, provider, thread_id=body.thread_id
            )
        else:
            answer, sources, usage = await run_crag(body.query, tenant, provider)
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "chat.error agent_type=%s tenant=%s", body.agent_type, tenant.tenant_id
        )
        raise HTTPException(status_code=500, detail="Agent failed. Check server logs.")

    if usage and usage.total_tokens:
        await record_token_usage(session, tenant.tenant_id, usage.total_tokens)

    return ChatResponse(answer=answer, sources=sources, query=body.query, usage=usage)
