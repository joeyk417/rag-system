from __future__ import annotations

"""CLI smoke test for the retrieval pipeline.

Usage:
    python scripts/test_query.py "what are the screen installation steps?"
    python scripts/test_query.py "rubber compound formulation register"

Requires EA_API_KEY env var (default: ea-dev-key-local-testing-only).
Requires a running Postgres with ingested EA sample docs.
"""

import asyncio
import hashlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select

from app.config import settings  # noqa: F401 — loads .env
from app.core.providers.openai_provider import OpenAIProvider
from app.db.models import Tenant
from app.db.session import AsyncSessionLocal
from app.retrieval import retriever


async def main(query: str) -> None:
    api_key = os.environ.get("EA_API_KEY", "ea-dev-key-local-testing-only")
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Tenant).where(Tenant.api_key_hash == key_hash)
        )
        tenant = result.scalar_one_or_none()

    if tenant is None:
        print(f"ERROR: No tenant found for API key. Run scripts/seed_tenant.py first.")
        sys.exit(1)

    print(f"Tenant : {tenant.name} ({tenant.tenant_id})")
    print(f"Query  : {query!r}")
    print("-" * 60)

    provider = OpenAIProvider()
    chunks = await retriever.retrieve(query, tenant, provider)

    if not chunks:
        print("No results returned.")
        return

    for rank, chunk in enumerate(chunks, 1):
        doc_ref = f"{chunk.doc_number or 'unknown'}"
        print(
            f"[{rank}] {doc_ref} | {chunk.doc_type} | page {chunk.page_number} "
            f"| score: {chunk.similarity_score:.4f}"
        )
        if chunk.heading:
            print(f"     Heading : {chunk.heading}")
        print(f"     {chunk.content[:300].strip()}")
        print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/test_query.py <query>")
        sys.exit(1)

    query_arg = " ".join(sys.argv[1:])
    asyncio.run(main(query_arg))
