from __future__ import annotations

import json
import logging

from pydantic import BaseModel

from app.core.providers.base import BaseLLMProvider
from app.db.models import Tenant

logger = logging.getLogger(__name__)

# Default EA doc types — used if tenant.config lacks "valid_doc_types"
_DEFAULT_DOC_TYPES = ["SOP", "ENG-DRW", "ENG-MAT", "STRAT"]


class QueryFilters(BaseModel):
    doc_type: str | None = None     # e.g. "SOP", "ENG-DRW", "ENG-MAT"
    doc_number: str | None = None   # e.g. "EA-SOP-001"
    classification: str | None = None


async def extract(
    query: str,
    tenant: Tenant,
    provider: BaseLLMProvider,
) -> QueryFilters:
    """Extract metadata filters from a user query using the LLM.

    Injects tenant-specific doc type vocabulary so the LLM can map natural
    language references (e.g. "SOP", "drawing", "strategy doc") to the
    exact values stored in the documents table.

    Returns empty QueryFilters (all None) on any parse failure.
    """
    config: dict = tenant.config or {}
    valid_doc_types: list[str] = config.get("valid_doc_types", _DEFAULT_DOC_TYPES)
    doc_number_pattern: str = config.get("doc_number_pattern", r"[A-Z]+-[A-Z0-9\-]+")

    system_prompt = (
        "You extract metadata filters from a user query about documents.\n"
        "Return ONLY valid JSON with these optional fields:\n"
        '  "doc_type": string or null\n'
        '  "doc_number": string or null\n'
        '  "classification": string or null\n'
        "Set a field to null if the query does not mention it.\n\n"
        f"Valid doc_types for this tenant: {valid_doc_types}\n"
        f"Doc number pattern: {doc_number_pattern}\n\n"
        "EXAMPLES:\n"
        '  "show me the screen installation SOP" -> {"doc_type": "SOP", "doc_number": null, "classification": null}\n'
        '  "EA-ENG-DRW-7834 banana screen manual" -> {"doc_type": "ENG-DRW", "doc_number": "EA-ENG-DRW-7834", "classification": null}\n'
        '  "what is the digital strategy?" -> {"doc_type": "STRAT", "doc_number": null, "classification": null}\n'
        '  "rubber compound formulations" -> {"doc_type": "ENG-MAT", "doc_number": null, "classification": null}\n'
    )

    try:
        raw = await provider.generate(
            system_prompt,
            query,
            response_format={"type": "json_object"},
        )
        data = json.loads(raw)
        return QueryFilters.model_validate(data)
    except Exception as exc:
        logger.warning("filter_extractor: parse failed — %s", exc)
        return QueryFilters()
