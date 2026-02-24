from __future__ import annotations

# TODO: implement in Task 3
# Generates embeddings via BaseLLMProvider.embed_batch()
# Called ONCE at ingest time — embeddings are stored in chunks.embedding
# NEVER re-embeds at query time (only user query is embedded at query time)
# Batch size: 100 chunks per API call to stay within token limits
