from __future__ import annotations

# TODO: implement in Task 3
# Ingests all 5 EA sample PDFs from sample_docs/ via the /ingest API:
#   - EA-SOP-001-Screen-Installation.pdf
#   - EA-ENG-DRW-7834-HF-Banana-Screen.pdf
#   - EA-ENG-MAT-019-Compound-Register.pdf
#   - EA-STRAT-002-Digital-AI-Strategy.pdf
#   - EA-ENG-DRW-4281-PU-Panel-Spec.pdf
# Polls GET /ingest/{job_id} until status == "completed"
# Prints progress and final document_ids
#
# Usage: python scripts/ingest_sample_docs.py
