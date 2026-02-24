from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()

# TODO: implement in Task 3
# POST /ingest  → upload PDF, kick off background ingest, return job_id
# GET  /ingest/{job_id} → poll status from ingest_jobs DB table
