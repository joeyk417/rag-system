from __future__ import annotations

"""ingest_sample_docs.py — Ingest all 5 EA sample PDFs via the /ingest API.

Usage:
    python scripts/ingest_sample_docs.py

Requires:
  - API running at http://localhost:8000
  - EA_API_KEY env var or hard-coded key from seed_tenant.py output
"""

import asyncio
import os
import sys
import time
from pathlib import Path

import httpx

BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
API_KEY = os.getenv("EA_API_KEY", "")
SAMPLE_DOCS_DIR = Path(__file__).parent.parent / "sample_docs"
POLL_INTERVAL = 2  # seconds between status polls
POLL_TIMEOUT = 300  # max seconds to wait per doc


async def ingest_file(client: httpx.AsyncClient, pdf_path: Path) -> str | None:
    """Upload a PDF and return the document_id once completed."""
    print(f"\n→ Uploading {pdf_path.name} …")
    with pdf_path.open("rb") as f:
        response = await client.post(
            f"{BASE_URL}/api/v1/ingest",
            files={"file": (pdf_path.name, f, "application/pdf")},
            headers={"X-API-Key": API_KEY},
            timeout=60,
        )

    if response.status_code not in (200, 202):
        print(f"  ✗ Upload failed ({response.status_code}): {response.text}")
        return None

    body = response.json()

    # Fast dedup path — already ingested
    if body.get("status") == "completed" and body.get("document_id"):
        print(f"  ✓ Already ingested — document_id: {body['document_id']}")
        return body["document_id"]

    job_id = body.get("job_id")
    if not job_id:
        print(f"  ✗ No job_id in response: {body}")
        return None

    print(f"  job_id: {job_id} — polling …", end="", flush=True)

    # Poll until done
    deadline = time.monotonic() + POLL_TIMEOUT
    while time.monotonic() < deadline:
        await asyncio.sleep(POLL_INTERVAL)
        status_resp = await client.get(
            f"{BASE_URL}/api/v1/ingest/{job_id}",
            headers={"X-API-Key": API_KEY},
            timeout=10,
        )
        if status_resp.status_code != 200:
            print(f"\n  ✗ Status check failed: {status_resp.text}")
            return None

        status_body = status_resp.json()
        status = status_body.get("status")
        print(".", end="", flush=True)

        if status == "completed":
            doc_id = status_body.get("document_id")
            print(f"\n  ✓ Completed — document_id: {doc_id}")
            return doc_id
        elif status == "failed":
            print(f"\n  ✗ Failed — error: {status_body.get('error')}")
            return None

    print(f"\n  ✗ Timed out after {POLL_TIMEOUT}s")
    return None


async def main() -> None:
    if not API_KEY:
        print("Error: EA_API_KEY environment variable is not set.")
        print("Set it to the API key printed by: python scripts/seed_tenant.py")
        sys.exit(1)

    pdfs = sorted(SAMPLE_DOCS_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found in {SAMPLE_DOCS_DIR}")
        sys.exit(1)

    print(f"Found {len(pdfs)} PDF(s) in {SAMPLE_DOCS_DIR}")
    results: dict[str, str | None] = {}

    async with httpx.AsyncClient() as client:
        for pdf_path in pdfs:
            doc_id = await ingest_file(client, pdf_path)
            results[pdf_path.name] = doc_id

    print("\n" + "=" * 60)
    print("Ingest summary:")
    for name, doc_id in results.items():
        status = f"document_id={doc_id}" if doc_id else "FAILED"
        print(f"  {name}: {status}")
    print("=" * 60)

    failed = [n for n, d in results.items() if d is None]
    if failed:
        print(f"\n{len(failed)} document(s) failed to ingest.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
