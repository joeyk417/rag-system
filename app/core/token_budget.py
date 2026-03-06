from __future__ import annotations

import logging

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

logger = logging.getLogger(__name__)

# Default estimated token cost used for pre-flight quota check.
# Actual tokens are always recorded post-call.
_ESTIMATED_TOKENS = 500


def _tier_label(token_quota: int) -> str:
    if token_quota <= settings.token_quota_starter:
        return "Starter"
    if token_quota <= settings.token_quota_professional:
        return "Professional"
    return "Enterprise"


async def check_token_budget(
    db: AsyncSession,
    tenant_id: str,
    estimated_tokens: int = _ESTIMATED_TOKENS,
) -> None:
    """Raise HTTP 402 if the tenant's monthly quota would be exceeded.

    Uses a conservative estimate before the LLM call. If no usage row exists
    for the current month the request is allowed (fail-open) — a row will be
    created by record_token_usage on the first successful call.
    """
    result = await db.execute(
        text(
            "SELECT tokens_used, token_quota FROM public.tenant_usage "
            "WHERE tenant_id = :tid "
            "AND period_month = date_trunc('month', now())::date"
        ),
        {"tid": tenant_id},
    )
    row = result.fetchone()
    if row is None:
        # No usage row yet for this month — fail-open.
        logger.debug("token_budget.no_row tenant=%s — allowing (fail-open)", tenant_id)
        return
    if row.tokens_used + estimated_tokens > row.token_quota:
        logger.warning(
            "token_budget.quota_exceeded tenant=%s used=%d quota=%d",
            tenant_id,
            row.tokens_used,
            row.token_quota,
        )
        raise HTTPException(status_code=402, detail="Monthly token quota exceeded")


async def record_token_usage(
    db: AsyncSession,
    tenant_id: str,
    input_tokens: int,
    output_tokens: int,
) -> None:
    """Upsert actual token consumption for the current calendar month.

    Tracks input and output tokens separately for accurate cost attribution.
    Creates the row for the new month automatically using the tenant's stored
    quota from the most recent existing row (fallback: settings.token_quota_starter).
    The UPDATE is atomic in PostgreSQL — no application-level locking needed.
    """
    total = input_tokens + output_tokens
    await db.execute(
        text(
            "INSERT INTO public.tenant_usage "
            "  (tenant_id, period_month, tokens_used, input_tokens, output_tokens, token_quota) "
            "VALUES (:tid, date_trunc('month', now())::date, :total, :input, :output, "
            "  COALESCE("
            "    (SELECT token_quota FROM public.tenant_usage "
            "     WHERE tenant_id = :tid ORDER BY period_month DESC LIMIT 1),"
            "    :default_quota"
            "  )) "
            "ON CONFLICT (tenant_id, period_month) DO UPDATE "
            "SET tokens_used   = public.tenant_usage.tokens_used   + :total, "
            "    input_tokens  = public.tenant_usage.input_tokens  + :input, "
            "    output_tokens = public.tenant_usage.output_tokens + :output"
        ),
        {
            "tid": tenant_id,
            "total": total,
            "input": input_tokens,
            "output": output_tokens,
            "default_quota": settings.token_quota_starter,
        },
    )
    await db.commit()
    logger.info(
        "token_budget.recorded tenant=%s input=%d output=%d total=%d",
        tenant_id, input_tokens, output_tokens, total,
    )


async def get_all_usage(db: AsyncSession) -> list[dict]:
    """Return current-month usage for all tenants (admin endpoint)."""
    result = await db.execute(
        text(
            "SELECT tenant_id, period_month, tokens_used, input_tokens, output_tokens, token_quota "
            "FROM public.tenant_usage "
            "WHERE period_month = date_trunc('month', now())::date "
            "ORDER BY tokens_used DESC"
        )
    )
    rows = result.fetchall()
    return [
        {
            "tenant_id": row.tenant_id,
            "period_month": row.period_month.isoformat(),
            "tokens_used": row.tokens_used,
            "input_tokens": row.input_tokens,
            "output_tokens": row.output_tokens,
            "token_quota": row.token_quota,
            "percent_used": round(row.tokens_used / row.token_quota * 100, 2)
            if row.token_quota
            else 0.0,
            "estimated_cost_usd": round(
                row.input_tokens / 1000 * settings.token_cost_input_per_1k
                + row.output_tokens / 1000 * settings.token_cost_output_per_1k,
                4,
            ),
            "tier": _tier_label(row.token_quota),
        }
        for row in rows
    ]
