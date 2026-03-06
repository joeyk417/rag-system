# Phase 4b — Token Limiting (Primary Tenant Control)

Token consumption maps directly to cost (Bedrock/OpenAI bill per token), making it the correct unit
for subscription enforcement — not request rate limiting. This phase inserts between Phase 4
(Adaptive RAG) and Phase 5 (AWS deployment).

---

## Overview

Two enforcement mechanisms work together:

| Layer | Mechanism | Purpose |
|-------|-----------|---------|
| Monthly budget | `public.tenant_usage` quota check before each LLM call | Subscription enforcement — blocks over-quota tenants with 402 |
| Per-request cap | `max_tokens` ceiling on every Bedrock/OpenAI API call | Prevents runaway agent loops burning the monthly budget in one call |

---

## Request Routing Flow

```
Inbound request (X-API-Key)
        │
        ▼
Hash key → look up public.tenants (tenant_id, schema_name, s3_prefix, config)
        │
        ▼
Check public.tenant_usage — tokens_used + estimated_tokens > token_quota?
        │ YES → 402 Monthly token quota exceeded
        │ NO  ▼
Set search_path → tenant schema_name
        │
        ▼
LLM call (with max_tokens ceiling from config)
        │
        ▼
Record actual tokens → UPDATE public.tenant_usage SET tokens_used = tokens_used + actual
        │
        ▼
Return response
```

### New Tenant Provisioning

When creating a tenant via `POST /api/v1/admin/tenants`:
1. Create tenant schema + seed API key (existing flow)
2. Set `token_quota` (from request body, defaults to Starter tier: 500 000)
3. Insert into `public.tenant_usage` for the current month with `tokens_used = 0`

---

## Database Migration

```sql
-- Run before enabling token limiting.
CREATE TABLE public.tenant_usage (
  tenant_id    TEXT    NOT NULL REFERENCES public.tenants(tenant_id),
  period_month DATE    NOT NULL,  -- first day of month e.g. 2026-03-01
  tokens_used  BIGINT  NOT NULL DEFAULT 0,
  token_quota  BIGINT  NOT NULL,  -- set per subscription tier on onboarding
  PRIMARY KEY (tenant_id, period_month)
);

-- Seed EA anchor client at Enterprise tier (10M tokens/month).
INSERT INTO public.tenant_usage (tenant_id, period_month, tokens_used, token_quota)
VALUES ('elastomers_au', date_trunc('month', now())::date, 0, 10000000)
ON CONFLICT (tenant_id, period_month) DO NOTHING;
```

---

## Subscription Tiers

| Tier | Monthly token quota | Typical usage |
|------|--------------------:|---------------|
| Starter | 500,000 | ~1,000 simple RAG queries |
| Professional | 2,000,000 | ~4,000 queries or ~500 agent calls |
| Enterprise | 10,000,000 | Daily heavy use across a full team (EA anchor client) |

Tier labels are derived at runtime from `token_quota` value:
- `<= 500_000` → Starter
- `<= 2_000_000` → Professional
- `> 2_000_000` → Enterprise

---

## Implementation Details

### `app/core/token_budget.py`

```python
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def check_token_budget(db: AsyncSession, tenant_id: str, estimated_tokens: int = 500) -> None:
    """Raise 402 if the tenant's monthly quota would be exceeded."""
    result = await db.execute(
        text(
            "SELECT tokens_used, token_quota FROM public.tenant_usage "
            "WHERE tenant_id = :tid AND period_month = date_trunc('month', now())::date"
        ),
        {"tid": tenant_id},
    )
    row = result.fetchone()
    if row is None:
        return  # No usage row yet — allow (fail-open); row is created on first record call
    if row.tokens_used + estimated_tokens > row.token_quota:
        raise HTTPException(status_code=402, detail="Monthly token quota exceeded")


async def record_token_usage(db: AsyncSession, tenant_id: str, actual_tokens: int) -> None:
    """Upsert token consumption for the current month and flush to DB."""
    await db.execute(
        text(
            "INSERT INTO public.tenant_usage (tenant_id, period_month, tokens_used, token_quota) "
            "VALUES (:tid, date_trunc('month', now())::date, :tokens, "
            "  (SELECT token_quota FROM public.tenants WHERE tenant_id = :tid)) "
            "ON CONFLICT (tenant_id, period_month) DO UPDATE "
            "SET tokens_used = public.tenant_usage.tokens_used + :tokens"
        ),
        {"tid": tenant_id, "tokens": actual_tokens},
    )
    await db.commit()
```

### Integration Points

**`app/dependencies.py`** — add `check_token_budget()` call in the chat dependency (before
dispatching to any agent). Use the public-schema session (engine without schema translation).

**`app/core/providers/openai_provider.py`** — after each `client.chat.completions.create()` call:
- Pass `max_tokens` from `settings.OPENAI_MAX_TOKENS_PER_REQUEST` (default 2000)
- Call `record_token_usage(db, tenant_id, response.usage.total_tokens)`

> Note: The `check_token_budget` uses an estimated token count (default 500) as a pre-flight
> guard. The actual consumption is always recorded post-call for accuracy.

---

## Admin API

### `GET /api/v1/admin/usage`

Returns current-month usage for all tenants. Admin API key required.

**Response:**
```json
[
  {
    "tenant_id": "elastomers_au",
    "period_month": "2026-03-01",
    "tokens_used": 42300,
    "token_quota": 10000000,
    "percent_used": 0.42,
    "estimated_cost_usd": 0.006,
    "tier": "Enterprise"
  }
]
```

**Cost formula:**
```
estimated_cost_usd = (tokens_used / 1000) * cost_per_1k_tokens
```
Default `cost_per_1k_tokens = 0.00015` (blended gpt-4o-mini + text-embedding-3-small rate).
Overridable per tenant via `tenants.config["cost_per_1k_tokens_usd"]`.

---

## Admin UI — Token Dashboard

Add a "Usage" section to the existing `/admin` frontend page (below the tenant list table).

**Columns:** Tenant ID | Period | Tokens Used | Quota | % Used (progress bar) | Est. Cost ($) | Tier

**Progress bar colour:**
- Green: < 70%
- Yellow: 70–90%
- Red: > 90%

**Data source:** `GET /api/v1/admin/usage` (admin key required). Shown only when admin key is set.
Refresh button to reload. Auto-refreshes when the tenant list refreshes.

---

## Build Order

1. **DB migration** — add `public.tenant_usage` DDL in `scripts/setup_db.py`
2. **Seed EA** — insert Enterprise-tier row in `scripts/seed_tenant.py`
3. **`TenantUsage` model** — add to `app/db/models.py` (public schema, composite PK)
4. **`app/core/token_budget.py`** — `check_token_budget()` + `record_token_usage()`
5. **Schemas** — add `token_quota: int` to `TenantCreate`/`TenantPatch` in `app/schemas/tenant.py`; add `TenantUsageResponse` schema
6. **Admin API** — persist `token_quota` in `POST /admin/tenants`; add `GET /admin/usage`
7. **Wire quota check** — call `check_token_budget()` in `app/dependencies.py` (public-schema session) before LLM dispatch in `POST /chat`
8. **Wire usage recording** — call `record_token_usage()` in `app/core/providers/openai_provider.py`; add `max_tokens` to all completion calls
9. **Frontend** — add `getTenantsUsage()` to `frontend/src/lib/api.ts`; add usage table to `frontend/src/app/admin/page.tsx`
10. **Tests** — `tests/test_token_budget.py`: quota-exceeded → 402, usage increments, new-month upsert, admin usage endpoint

---

## CloudWatch Integration (Phase 5 hook)

`record_token_usage()` emits a `TokensConsumed` custom metric to CloudWatch (wired in Phase 5):

```python
cloudwatch.put_metric_data(
    Namespace="RAGPlatform/Tenants",
    MetricData=[{
        "MetricName": "TokensConsumed",
        "Dimensions": [{"Name": "TenantId", "Value": tenant_id}],
        "Value": actual_tokens,
        "Unit": "Count",
    }]
)
```

In local/development mode (`APP_ENV != "production"`), the CloudWatch call is skipped.

---

## Production Notes

- **New month handling:** `record_token_usage()` uses `ON CONFLICT ... DO UPDATE` — a new row is
  auto-created on the first call of each calendar month. No cron job required.
- **Fail-open vs fail-closed:** If no usage row exists for the current month,
  `check_token_budget()` allows the request (fail-open). This prevents blocking tenants whose row
  wasn't seeded. Operators can switch to fail-closed by raising 402 when `row is None`.
- **Concurrency:** The `UPDATE tokens_used = tokens_used + :tokens` is atomic in PostgreSQL —
  no application-level locking needed.
- **Viewing usage:** `GET /api/v1/admin/usage` for API access; `/admin` frontend page for visual
  monitoring with cost estimates and tier badges.
- **`token_quota` storage:** Stored in `public.tenant_usage` (per-month) rather than
  `public.tenants` — this allows quota changes mid-month without retroactively altering existing
  period rows.
