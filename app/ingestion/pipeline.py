from __future__ import annotations

# TODO: implement in Task 3
# Orchestrates full ingestion flow:
#   1. dedup.check_hash()         → skip if duplicate
#   2. S3 upload (boto3)          → store raw PDF
#   3. pdf_extractor.extract()    → Docling → per-page markdown
#   4. metadata_parser.parse()    → doc_number, doc_type, etc.
#   5. chunker.chunk()            → list[Chunk]
#   6. embedder.embed()           → attach embedding vectors
#   7. DB insert: Document + Chunks in a single transaction
#   8. Update IngestJob.status = "completed" (or "failed" on error)
