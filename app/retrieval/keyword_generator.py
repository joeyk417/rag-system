from __future__ import annotations

import json
import logging

from pydantic import BaseModel, Field

from app.core.providers.base import BaseLLMProvider
from app.db.models import Tenant

logger = logging.getLogger(__name__)


class RankingKeywords(BaseModel):
    keywords: list[str] = Field(min_length=1, max_length=10)


async def generate(
    query: str,
    tenant: Tenant,
    provider: BaseLLMProvider,
) -> list[str]:
    """Generate exactly 5 domain-specific BM25 ranking keywords from a user query.

    Keywords use exact terminology found in the tenant's documents so BM25Plus
    scoring aligns with actual chunk content.

    Falls back to naive whitespace-split tokens if the LLM call fails.
    """
    config: dict = tenant.config or {}
    tenant_domain: str = config.get("domain", tenant.name)
    domain_hints: list[str] = config.get("keyword_hints", [])

    hints_section = (
        f"Domain terminology hints: {domain_hints}\n" if domain_hints else ""
    )

    system_prompt = (
        "Generate EXACTLY 5 technical keywords for BM25 ranking of engineering/industrial documents.\n"
        "Use exact terminology found in the documents — headings, labels, and technical terms.\n"
        f"Document domain: {tenant_domain}\n"
        f"{hints_section}"
        'Return ONLY valid JSON: {"keywords": ["term1", "term2", "term3", "term4", "term5"]}\n\n'
        "RULES:\n"
        "- Return EXACTLY 5 keywords\n"
        "- Use exact phrases likely to appear verbatim in the documents\n"
        "- Match the query topic (installation → installation steps, procedure, method)\n"
        "- Include both specific and general terms\n\n"
        "EXAMPLES:\n"
        '  "screen installation steps" -> {"keywords": ["installation procedure", "installation steps", '
        '"screen panel", "tensioning", "assembly"]}\n'
        '  "rubber compound formulation" -> {"keywords": ["compound formulation", "rubber compound", '
        '"formulation register", "material specification", "compound grade"]}\n'
        '  "digital AI strategy" -> {"keywords": ["digital strategy", "artificial intelligence", '
        '"technology roadmap", "digital transformation", "AI implementation"]}\n'
    )

    try:
        raw = await provider.generate(
            system_prompt,
            query,
            response_format={"type": "json_object"},
        )
        data = json.loads(raw)
        result = RankingKeywords.model_validate(data)
        return result.keywords
    except Exception as exc:
        logger.warning("keyword_generator: parse failed — %s", exc)
        # Naive fallback: use query tokens
        tokens = query.lower().split()
        return tokens[:5] if len(tokens) >= 5 else tokens
