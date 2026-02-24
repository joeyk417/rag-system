# Architecture Decisions

## Why RDS PostgreSQL + pgvector, not Supabase

Elastomers Australia's strategy document (EA-STRAT-002) explicitly requires: *"Processing of EA's proprietary engineering drawings, client data, and operational data will occur exclusively on Australian-hosted infrastructure."*

Supabase managed cloud is US-hosted. This disqualifies it for this client and likely for most Australian B2B clients with similar compliance requirements.

RDS PostgreSQL 16 + pgvector in ap-southeast-2 gives us:
- Full Australian data sovereignty
- Single managed service for both vector and relational data
- SQL metadata filtering without a separate query layer
- pgvector is production-grade at our scale
- Cost-effective vs dedicated vector DBs (Pinecone, Weaviate)

## Why Schema-per-Tenant, not Shared Table with tenant_id

- Easier to delete/export a single tenant's data (GDPR-style right to erasure)
- pgvector indices optimised per tenant
- Cleaner compliance audit trail
- No risk of accidental cross-tenant data leakage via missing WHERE clause

## Why OpenAI for Phase 1, Bedrock for Phase 2

OpenAI Phase 1: fastest path to working system. `gpt-4o-mini` is capable and cheap. `text-embedding-3-small` gives 1536-dim embeddings.

OpenAI caveat: data processed in the US. For clients with strict AU data sovereignty (like EA), this is non-compliant. The `LLMProvider` abstraction in `app/core/providers/` makes switching a config change, not a rewrite.

AWS Bedrock Phase 2: runs in ap-southeast-2. Satisfies AU sovereignty. Uses Claude for generation (higher quality than gpt-4o-mini for technical docs), Titan embeddings.

## Why Docling for PDF Extraction

Docling (IBM) handles:
- Multi-column layouts common in engineering specs
- Tables extracted as markdown tables (critical for torque spec tables, panel comparison tables)
- Hierarchical structure preserved (headings → sub-headings)
- Page-level extraction built in

Alternatives considered:
- PyPDF2/pdfplumber: loses table structure and formatting
- AWS Textract: adds cost, latency, and another service dependency in Phase 1
- LlamaParse: cloud-based, sovereignty concern

## Why CRAG for Phase 1 (not Self-RAG or Adaptive)

CRAG (Corrective RAG) is the right Phase 1 choice because:
- Single retry cycle prevents infinite loops — safe for production
- Easier to debug than Self-RAG (fewer moving parts)
- Graceful fallback to web search when docs don't contain the answer
- Self-RAG's hallucination checking adds latency (2-3 extra LLM calls per query)

Phase 2 upgrades to Self-RAG when we need higher answer quality guarantees, then Adaptive RAG when we add SQL routing.

## Why Hybrid Vector + BM25, not Vector-Only

Vector similarity alone misses exact technical terms. An engineer asking "NR-35-SA cure temperature" needs exact compound code matching, not just semantic similarity.

BM25Plus re-ranking on heading+content chunks combines:
- Vector search: semantic understanding ("what temperature does this compound cure at?")
- BM25: exact term matching ("NR-35-SA", "M20 Grade 10.9", "HF-2472")

This pattern is directly derived from the reference notebooks (Notebook 02).
