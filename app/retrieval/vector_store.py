from __future__ import annotations

# TODO: implement in Task 4
# pgvector cosine similarity search within tenant schema
# Uses ivfflat index on chunks.embedding (vector_cosine_ops)
# Applies metadata filters (doc_type, doc_number, classification) via SQL WHERE
# Enforces restricted_doc_types from tenants.config at retrieval layer
# Fetch k * settings.retrieval_fetch_multiplier candidates, return top k after re-ranking
