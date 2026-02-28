from __future__ import annotations

"""validate_queries.py — Run all validation queries from docs/validation-queries.md.

Requires a running API server and ingested EA sample documents.

Usage:
    uvicorn app.main:app --port 8000 &
    python scripts/ingest_sample_docs.py
    python scripts/validate_queries.py

Set EA_API_KEY env var or use the default dev key.
"""

import os
import sys
import textwrap
from pathlib import Path

import httpx

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_BASE = os.getenv("API_BASE", "http://localhost:8000")
EA_API_KEY = os.getenv("EA_API_KEY", "ea-dev-key-local-testing-only")
TIMEOUT = 60  # seconds per query

# Validation queries from docs/validation-queries.md
QUERIES = [
    {
        "id": 1,
        "query": "What torque for M20 Grade 10.9 bolts lubricated?",
        "expected_source": "EA-SOP-001 Table 7.1",
        "expected_hint": "370",
    },
    {
        "id": 2,
        "query": "What PPE is required for screen installation?",
        "expected_source": "EA-SOP-001 Section 4.1",
        "expected_hint": "PPE",
    },
    {
        "id": 3,
        "query": "What are the slope angles on the HF-2160?",
        "expected_source": "EA-ENG-DRW-7834 model table",
        "expected_hint": "35",
    },
    {
        "id": 4,
        "query": "What motor bolt size for the HF-2472?",
        "expected_source": "EA-ENG-DRW-7834 Stage 2",
        "expected_hint": "M24",
    },
    {
        "id": 5,
        "query": "Shore A hardness for PU-500 panels?",
        "expected_source": "EA-ENG-DRW-4281 Section 2",
        "expected_hint": "80",
    },
    {
        "id": 6,
        "query": "Max feed size for PU-600 series?",
        "expected_source": "EA-ENG-DRW-4281 Section 2",
        "expected_hint": "400",
    },
    {
        "id": 7,
        "query": "What is NR-35-SA compound used for?",
        "expected_source": "EA-ENG-MAT-019 Section 2.1",
        "expected_hint": "wear",
    },
    {
        "id": 8,
        "query": "Cure temperature for NR-55-HA?",
        "expected_source": "EA-ENG-MAT-019 Section 2.2",
        "expected_hint": "155",
    },
    {
        "id": 9,
        "query": "How many field technicians does EA employ?",
        "expected_source": "EA-STRAT-002 Section 2.1",
        "expected_hint": "350",
    },
    {
        "id": 10,
        "query": "What is the new hire competency timeline?",
        "expected_source": "EA-SOP-001 Section 11",
        "expected_hint": "week",
    },
]

# Bonus cross-document queries (no hint check — just verify non-empty answer)
BONUS_QUERIES = [
    {
        "id": "B1",
        "query": "What panel spec applies to the HF-2472?",
        "expected_source": "EA-ENG-DRW-4281 (cross-reference from DRW-7834 Stage 4)",
        "expected_hint": None,
    },
    {
        "id": "B2",
        "query": "What are the training requirements before installation?",
        "expected_source": "EA-SOP-001 Section 11 + STRAT-002 VR context",
        "expected_hint": None,
    },
]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_query(client: httpx.Client, query: str) -> dict:
    response = client.post(
        f"{API_BASE}/api/v1/chat",
        headers={"X-API-Key": EA_API_KEY, "Content-Type": "application/json"},
        json={"query": query},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def check_result(result: dict, hint: str | None) -> bool:
    answer = result.get("answer", "")
    if not answer:
        return False
    if hint and hint.lower() not in answer.lower():
        return False
    return True


def main() -> None:
    print("=" * 70)
    print("  RAG System — Validation Query Runner")
    print(f"  API: {API_BASE}")
    print(f"  Key: {EA_API_KEY[:8]}...")
    print("=" * 70)
    print()

    passed = 0
    failed = 0
    errors = 0

    all_queries = QUERIES + BONUS_QUERIES

    with httpx.Client() as client:
        for q in all_queries:
            qid = q["id"]
            query = q["query"]
            hint = q.get("expected_hint")
            source = q["expected_source"]

            print(f"[{qid:>2}] {query}")
            print(f"     Expected source: {source}")

            try:
                result = run_query(client, query)
                answer = result.get("answer", "")
                sources = result.get("sources", [])
                ok = check_result(result, hint)

                status = "✅ PASS" if ok else "❌ FAIL"
                if ok:
                    passed += 1
                else:
                    failed += 1

                # Print truncated answer
                preview = textwrap.shorten(answer, width=120, placeholder="...")
                print(f"     {status} | Sources: {len(sources)} | Answer: {preview}")

                if hint and hint.lower() not in answer.lower():
                    print(f"     ⚠️  Expected hint '{hint}' not found in answer")

            except Exception as exc:
                errors += 1
                print(f"     💥 ERROR: {exc}")

            print()

    print("=" * 70)
    total = len(all_queries)
    print(f"  Results: {passed}/{total} passed | {failed} failed | {errors} errors")
    if failed == 0 and errors == 0:
        print("  🎉 All validation queries passed!")
    else:
        print("  ⚠️  Some queries failed — check answers above.")
    print("=" * 70)

    sys.exit(0 if (failed == 0 and errors == 0) else 1)


if __name__ == "__main__":
    main()
