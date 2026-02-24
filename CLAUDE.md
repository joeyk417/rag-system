# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Multi-tenant document intelligence system. Companies upload PDFs; users query them in natural language. Each tenant gets an isolated knowledge base.

**Reference client:** Elastomers Australia (EA) — mining screen media manufacturer with engineering drawings, SOPs, formulation registers, and product specs.

**Current state:** No production code exists yet. The spec below is the blueprint. `reference_notebooks/` contains working Jupyter prototypes (using Ollama + ChromaDB locally) that validate the core patterns — read these before implementing any module.

---

## Commands

```bash
# Setup
python3.12 -m venv venv && source venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env                        # then fill in secrets

# Database
docker-compose up -d postgres               # start local postgres+pgvector
python scripts/setup_db.py                  # create schemas, enable pgvector
python scripts/seed_tenant.py               # create EA tenant record

# Run
uvicorn app.main:app --reload --port 8000

# Ingest & Test
python scripts/ingest_sample_docs.py        # ingest all 5 EA sample PDFs
python scripts/test_query.py "your query"   # quick CLI query test

# Tests
pytest tests/ -v
pytest tests/test_api/ -v
pytest tests/test_ingestion/test_chunker.py -v   # run a single test module
pytest tests/ -v -k "test_deduplication"          # run a single test by name
```

---

## Reference Notebooks

`reference_notebooks/` contains 7 Jupyter notebooks that prototype the full system. Read these before implementing each module:

| Notebook | What it demonstrates |
|----------|---------------------|
| `01. PageRAG - Data Ingestion.ipynb` | Docling extraction, metadata parsing, SHA-256 dedup, vector store ingest |
| `02. Data Retrieval and ReRanking.ipynb` | Vector search + BM25 hybrid re-ranking |
| `03. Agentic PageRAG.ipynb` | LangGraph multi-node orchestration |
| `04. Corrective RAG (CRAG).ipynb` | grade → rewrite → web search flow |
| `05. Reflexion Agentic RAG.ipynb` | Multi-hop reasoning |
| `06. Self-RAG.ipynb` | Hallucination detection + answer quality grading |
| `07. Adaptive RAG.ipynb` | Routing to different agents based on query type |

The notebooks use Ollama + ChromaDB locally; production code replaces these with OpenAI + pgvector.

---

## Tech Stack

```
Language:        Python 3.12
API:             FastAPI 0.115+
LLM/Embeddings:  OpenAI API (gpt-4o-mini + text-embedding-3-small, 1536 dims)
Agent Framework: LangGraph 0.2+ / LangChain 0.3+
PDF Processing:  Docling 2.x
Vector DB:       pgvector on PostgreSQL 16
ORM:             SQLAlchemy 2.x async + asyncpg
Re-ranking:      rank-bm25 (BM25Plus)
Storage:         AWS S3 ap-southeast-2 (boto3)
Auth:            X-API-Key header per tenant
Validation:      Pydantic v2
Config:          pydantic-settings (.env)
Testing:         pytest + pytest-asyncio
Containers:      Docker + docker-compose (local dev)
```

---

## Database Schema

### Shared (public schema)

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE public.tenants (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT UNIQUE NOT NULL,
    name            TEXT NOT NULL,
    api_key_hash    TEXT NOT NULL,
    schema_name     TEXT NOT NULL,
    s3_prefix       TEXT NOT NULL,
    config          JSONB NOT NULL DEFAULT '{}',
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Per-tenant schema (e.g. `tenant_elastomers_au`)

```sql
CREATE TABLE documents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_hash       TEXT NOT NULL UNIQUE,
    filename        TEXT NOT NULL,
    s3_key          TEXT NOT NULL,
    doc_number      TEXT,
    doc_type        TEXT,
    revision        TEXT,
    title           TEXT,
    classification  TEXT,
    extra_metadata  JSONB NOT NULL DEFAULT '{}',
    page_count      INTEGER,
    status          TEXT NOT NULL DEFAULT 'pending',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE chunks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_number     INTEGER NOT NULL,
    chunk_index     INTEGER NOT NULL,
    heading         TEXT,
    content         TEXT NOT NULL,
    embedding       vector(1536),
    token_count     INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_chunks_embedding ON chunks
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_chunks_document_id ON chunks(document_id);
CREATE INDEX idx_documents_doc_type ON documents(doc_type);
```

---

## Environment Variables

```bash
OPENAI_API_KEY=sk-...
OPENAI_LLM_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_EMBEDDING_DIMENSIONS=1536

DATABASE_URL=postgresql+asyncpg://raguser:ragpass@localhost:5432/ragdb

AWS_REGION=ap-southeast-2
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
S3_BUCKET_NAME=rag-system-docs-dev

APP_ENV=development
ADMIN_API_KEY=...
LOG_LEVEL=INFO
MAX_RETRIEVAL_K=5
RETRIEVAL_FETCH_MULTIPLIER=20
```

---

## Document Metadata Parsing

EA filenames follow: `{DOC-NUMBER}-{Title}.pdf`

```
EA-SOP-001-Screen-Installation.pdf       → doc_type=SOP,     doc_number=EA-SOP-001
EA-ENG-DRW-7834-HF-Banana-Screen.pdf    → doc_type=ENG-DRW, doc_number=EA-ENG-DRW-7834
EA-ENG-MAT-019-Compound-Register.pdf    → doc_type=ENG-MAT, doc_number=EA-ENG-MAT-019
EA-STRAT-002-Digital-AI-Strategy.pdf    → doc_type=STRAT,   doc_number=EA-STRAT-002
EA-ENG-DRW-4281-PU-Panel-Spec.pdf       → doc_type=ENG-DRW, doc_number=EA-ENG-DRW-4281
```

Each doc has a structured header on page 1 — extract: Document Number, Revision, Effective Date, Classification.

Tenant-specific parsing rules live in `tenants.config` JSONB — the parser must be tenant-configurable, not hardcoded to EA conventions.

---

## API Endpoints

```
POST   /api/v1/ingest                  Upload PDF → async ingest pipeline
GET    /api/v1/ingest/{job_id}         Poll ingest status
POST   /api/v1/chat                    Query the knowledge base
GET    /api/v1/documents               List documents (tenant-scoped)
DELETE /api/v1/documents/{id}          Delete document + chunks + S3 object
GET    /api/v1/health                  Health check (no auth)

# Admin (ADMIN_API_KEY only)
POST   /api/v1/admin/tenants
GET    /api/v1/admin/tenants
PATCH  /api/v1/admin/tenants/{id}
```

---

## Agent Architecture (Phase 1: CRAG)

```
START → retrieve → grade → [relevant]     → generate → END
                          → [not relevant] → rewrite  → web_search → generate → END
```

Phase 2 upgrades to Self-RAG then Adaptive RAG. See `docs/phase2-aws.md`.

---

## Coding Conventions

- Python 3.12+, `from __future__ import annotations` in all files
- Type hints everywhere — no untyped functions
- Pydantic v2 for all data models
- `async/await` throughout — no sync DB or HTTP calls in request path
- FastAPI `HTTPException` for user-facing errors, never expose stack traces
- All config via `app/config.py` — never `os.environ.get()` in business logic
- Log all LLM calls: model, token counts, latency

---

## Key Design Constraints — Must Follow

1. **Tenant isolation is absolute.** Every DB query operates within the correct tenant schema. No shared tables contain document content or embeddings across tenants.

2. **Never ingest the same file twice.** SHA-256 hash check runs BEFORE Docling extraction. If hash exists in `documents.file_hash`, return existing document_id immediately.

3. **Confidential docs need access control at the retrieval layer.** `EA-ENG-MAT-019` (rubber formulation register) is marked HIGHEST CONFIDENTIALITY. Check `tenants.config.restricted_doc_types` before returning chunks — enforce at retrieval, not just the API layer.

4. **Embeddings generated once at ingest, never at query time.** Only the user query is embedded at query time (1 API call). Never re-embed ingested chunks.

5. **Australian data sovereignty.** All infra in `ap-southeast-2`. If tenant config has `data_sovereignty: "AU"`, enforce AWS Bedrock as LLM provider — not OpenAI.

6. **No hardcoded tenant logic.** Everything tenant-specific comes from `tenants.config`. Core RAG code must be completely tenant-agnostic.

---

## Build Order (Phase 1)

Complete in order. Do not skip ahead.

1. **Project scaffold** — structure, requirements.txt, docker-compose, config.py, main.py, `/health`
2. **Database** — SQLAlchemy models, setup_db.py, Alembic migration, seed EA tenant
3. **Ingestion pipeline** — pdf_extractor → metadata_parser → chunker → embedder → dedup → pipeline.py → `POST /ingest`
4. **Retrieval pipeline** — filter_extractor → keyword_generator → vector_store → bm25_ranker → retriever.py
5. **CRAG agent** — state.py, all nodes, crag_agent.py graph
6. **Chat API** — `POST /chat`, tenant system prompt, source citations
7. **Tests** — unit tests per module + integration test (ingest → query → verify)
8. **Validation** — run all queries in `docs/validation-queries.md` against EA sample docs
