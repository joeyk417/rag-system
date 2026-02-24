from __future__ import annotations

# TODO: implement in Task 4
# Main retrieval orchestrator:
#   1. filter_extractor.extract(query)     → metadata filters
#   2. keyword_generator.generate(query)   → BM25 keywords
#   3. vector_store.search(query_embedding, filters, k * multiplier) → candidates
#   4. bm25_ranker.rank(candidates, keywords, k)  → final top-k chunks
# Returns list[RetrievedChunk] with document metadata for citations
