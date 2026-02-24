# CLAUDE.md — Multi-Tenant Document Intelligence RAG System
## AI-Assisted Development Guide for Claude Code

---

## 1. PROJECT OVERVIEW

Build a **multi-tenant, PDF-based RAG (Retrieval-Augmented Generation) system** that allows B2B industrial companies to query their internal document archives using natural language. Each company (tenant) gets an isolated knowledge base fed by their own PDFs — engineering drawings, SOPs, specifications, formulation registers, maintenance manuals, and other technical documents.

### Reference Implementation: Elastomers Australia
The first tenant is Elastomers Australia (EA), a mining screen media manufacturer with:
- 30,000+ engineering drawings accumulated over 40 years
- SOPs for field technicians doing screen installations at remote mine sites
- Rubber compound formulation registers (highly confidential IP)
- Product specifications for polyurethane and rubber modular panels
- Equipment assembly and maintenance manuals

**Primary use cases:**
- Field technician asks: *"What torque do I use for M20 Grade 10.9 bolts on the HF-2472?"*
- Engineer asks: *"Do we have a spec for a 305×305 PU panel rated for 300mm feed size?"*
- Sales asks: *"What's the temperature range for our PU-500 series panels?"*
- R&D asks: *"What was the NR-55-HA formulation cure temperature?"*

### Target Scale
- Phase 1: 1 tenant, local dev, up to ~500 documents
- Phase 2: Multi-tenant, AWS production, up to 50 tenants × 10,000 documents each

---

## 2. ARCHITECTURE DECISION RECORDS

### 2.1 Database: AWS RDS PostgreSQL + pgvector (NOT Supabase cloud)

**Decision:** Use AWS RDS PostgreSQL (Sydney region, `ap-southeast-2`) with the `pgvector` extension for both vector storage and relational metadata.

**Why not Supabase cloud:**
The reference client (Elastomers Australia) has an explicit Australian data sovereignty requirement in their strategy document (EA-STRAT-002): *"Processing of Elastomers Australia's proprietary engineering drawings, client data, and operational data will occur exclusively on Australian-hosted infrastructure."* Supabase's managed cloud is US-based. This rules it out for this client and likely for other Australian B2B clients.

**Why RDS + pgvector over a dedicated vector DB (Pinecone, Weaviate, etc.):**
- Single managed service for both vector and relational data — simpler ops
- pgvector on RDS is production-grade and well-supported
- Keeps all data within AWS Sydney region
- Cost-effective at the scale we're building to
- SQL gives us flexible metadata filtering without needing a separate query layer

**For local development:** Use PostgreSQL via Docker with the pgvector extension (see setup below). Schema is identical to production — zero migration friction.

### 2.2 LLM & Embeddings: OpenAI API (Phase 1), Claude via AWS Bedrock (Phase 2)

**Phase 1:** OpenAI `gpt-4o-mini` for generation, `text-embedding-3-small` for embeddings (1536 dimensions).

**Important caveat:** OpenAI processes data in the US. For clients with strict Australian data sovereignty requirements, flag this upfront. The architecture is designed to swap models via a provider abstraction layer.

**Phase 2 migration path:** AWS Bedrock (Sydney region) supports Claude models natively and keeps all AI processing within AWS Australia. The model provider abstraction in the code makes this a config change, not a rewrite.

### 2.3 PDF Ingestion: Docling

Use `docling` for PDF-to-markdown conversion (same as the reference notebooks). It handles:
- Multi-column layouts
- Tables (extracts as markdown tables)
- Headers and hierarchical structure
- Page-level extraction

### 2.4 Chunking Strategy: Hybrid Page + Section

Do NOT chunk by fixed token count. Instead:
1. Extract full page text via Docling
2. Within each page, split on markdown headings (##, ###) to create section-level chunks
3. Store BOTH the page-level document AND section-level chunks
4. Section chunks are used for retrieval; page context is available for answer generation

This preserves document structure (critical for SOPs with numbered steps, spec sheets with tables, formulation registers with chemical data).

### 2.5 Retrieval: Hybrid Vector + BM25 Re-ranking

Directly implements the pattern from the reference notebooks (02 — Data Retrieval and ReRanking):
1. Extract metadata filters from query using LLM structured output
2. Vector similarity search against pgvector (with metadata filter conditions)
3. BM25Plus re-ranking on heading+content chunks
4. Return top-k re-ranked results

### 2.6 Agent Pattern: Corrective RAG (CRAG) for Phase 1

Start with CRAG (Notebook 04 pattern) as the agent architecture:
- Retrieve → Grade relevance → If relevant: answer; If not: rewrite query → fallback to web search
- Single retry cycle prevents infinite loops
- Simpler to debug and tune than Self-RAG or Reflexion

Phase 2 will layer in Self-RAG and Adaptive RAG routing (to SQL for structured data queries, web search for general knowledge).

### 2.7 Multi-Tenancy: Schema-per-tenant in PostgreSQL

Each tenant gets:
- Their own PostgreSQL schema (e.g., `tenant_elastomers_au`) containing their documents and embeddings table
- Row-level security (RLS) policies enforced at DB level as defence-in-depth
- Their own S3 prefix (`s3://bucket/tenants/{tenant_id}/pdfs/`)
- Their own config row in the shared `tenants` table

**Why schema-per-tenant over a single table with tenant_id:**
- Easier to delete/export a single tenant's data
- pgvector indices can be optimised per tenant
- Cleaner isolation for compliance audits
- No risk of accidental cross-tenant data leakage via missing WHERE clause

---

## 3. TECH STACK

```
Language:          Python 3.12
API Framework:     FastAPI 0.115+
AI/LLM:            OpenAI API (gpt-4o-mini + text-embedding-3-small)
Agent Framework:   LangGraph 0.2+ / LangChain 0.3+
PDF Processing:    Docling 2.x
Vector DB:         pgvector on PostgreSQL 16
ORM:               SQLAlchemy 2.x (async) + asyncpg
Re-ranking:        rank-bm25 (BM25Plus)
Storage:           AWS S3 (boto3)
Auth:              API key (X-API-Key header) — simple for Phase 1
Validation:        Pydantic v2
Config:            pydantic-settings (.env files)
Testing:           pytest + pytest-asyncio
Containerisation:  Docker + docker-compose (local dev)
AWS (Phase 2):     ECS Fargate, API Gateway, RDS, S3, Secrets Manager, CloudWatch
```

---

## 4. PROJECT FOLDER STRUCTURE

```
rag-system/
│
├── CLAUDE.md                          # This file
├── README.md
├── .env.example                       # Template — never commit .env
├── .env                               # Local secrets — gitignored
├── docker-compose.yml                 # Local dev: postgres + pgvector
├── Dockerfile
├── requirements.txt
├── requirements-dev.txt               # pytest, black, ruff, etc.
│
├── app/
│   ├── __init__.py
│   ├── main.py                        # FastAPI app factory
│   ├── config.py                      # pydantic-settings config
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── deps.py                    # Shared dependencies (DB session, auth)
│   │   ├── v1/
│   │   │   ├── __init__.py
│   │   │   ├── router.py              # Aggregates all v1 routes
│   │   │   ├── chat.py                # POST /chat — main query endpoint
│   │   │   ├── ingest.py              # POST /ingest — upload + process PDF
│   │   │   ├── documents.py           # GET /documents — list, delete
│   │   │   └── tenants.py             # GET/POST /tenants — admin only
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── ingestion/
│   │   │   ├── __init__.py
│   │   │   ├── pipeline.py            # Orchestrates full ingest flow
│   │   │   ├── pdf_extractor.py       # Docling wrapper — PDF → pages
│   │   │   ├── chunker.py             # Page → section chunks
│   │   │   ├── metadata_parser.py     # Filename + header → structured metadata
│   │   │   ├── embedder.py            # OpenAI embeddings wrapper
│   │   │   └── deduplication.py       # SHA-256 hash check (skip re-ingested files)
│   │   │
│   │   ├── retrieval/
│   │   │   ├── __init__.py
│   │   │   ├── vector_store.py        # pgvector query wrapper
│   │   │   ├── filter_extractor.py    # LLM extracts metadata filters from query
│   │   │   ├── keyword_generator.py   # LLM generates domain keywords for BM25
│   │   │   ├── bm25_ranker.py         # BM25Plus re-ranking
│   │   │   └── retriever.py           # Orchestrates full retrieval pipeline
│   │   │
│   │   ├── agents/
│   │   │   ├── __init__.py
│   │   │   ├── crag_agent.py          # Phase 1: Corrective RAG agent (LangGraph)
│   │   │   ├── self_rag_agent.py      # Phase 2: Self-RAG agent
│   │   │   ├── adaptive_agent.py      # Phase 2: Adaptive RAG with routing
│   │   │   ├── nodes/
│   │   │   │   ├── retrieve.py
│   │   │   │   ├── grade.py
│   │   │   │   ├── rewrite.py
│   │   │   │   ├── generate.py
│   │   │   │   └── web_search.py
│   │   │   └── state.py               # LangGraph AgentState TypedDict
│   │   │
│   │   └── providers/
│   │       ├── __init__.py
│   │       ├── base.py                # Abstract LLMProvider interface
│   │       ├── openai_provider.py     # OpenAI implementation
│   │       └── bedrock_provider.py    # Phase 2: AWS Bedrock / Claude
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── database.py                # Async SQLAlchemy engine + session factory
│   │   ├── migrations/                # Alembic migrations
│   │   └── models/
│   │       ├── __init__.py
│   │       ├── tenant.py              # Tenant config model
│   │       ├── document.py            # Document metadata model
│   │       └── chunk.py               # Chunk + embedding model
│   │
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── chat.py                    # ChatRequest, ChatResponse Pydantic models
│   │   ├── ingest.py                  # IngestRequest, IngestResponse
│   │   ├── document.py                # Document metadata schemas
│   │   ├── tenant.py                  # Tenant schemas
│   │   └── rag.py                     # Internal RAG schemas (filters, chunks, etc.)
│   │
│   └── utils/
│       ├── __init__.py
│       ├── s3.py                      # S3 upload/download helpers
│       ├── hashing.py                 # SHA-256 file hashing
│       └── logging.py                 # Structured logging setup
│
├── tests/
│   ├── conftest.py                    # pytest fixtures (test DB, test client)
│   ├── test_ingestion/
│   │   ├── test_pdf_extractor.py
│   │   ├── test_chunker.py
│   │   └── test_metadata_parser.py
│   ├── test_retrieval/
│   │   ├── test_filter_extractor.py
│   │   ├── test_bm25_ranker.py
│   │   └── test_retriever.py
│   ├── test_agents/
│   │   └── test_crag_agent.py
│   └── test_api/
│       ├── test_chat.py
│       └── test_ingest.py
│
├── scripts/
│   ├── setup_db.py                    # Create schemas, enable pgvector, run migrations
│   ├── ingest_sample_docs.py          # Bulk ingest the EA sample PDFs for testing
│   └── test_query.py                  # Quick CLI query test without HTTP
│
├── sample_docs/
│   ├── EA-STRAT-002-Digital-AI-Strategy.pdf
│   ├── EA-SOP-001-Screen-Installation.pdf
│   ├── EA-ENG-MAT-019-Compound-Formulation-Register.pdf
│   ├── EA-ENG-DRW-7834-HF-Banana-Screen-Manual.pdf
│   └── EA-ENG-DRW-4281-PU-Panel-Specification.pdf
│
└── infra/                             # Phase 2: AWS infrastructure
    ├── terraform/                     # Or CDK — TBD
    └── task-definition.json           # ECS task definition
```

---

## 5. DATABASE SCHEMA

### 5.1 Shared (public) Schema

```sql
-- Enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- Tenants registry
CREATE TABLE public.tenants (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT UNIQUE NOT NULL,          -- e.g. 'elastomers_au'
    name            TEXT NOT NULL,                 -- e.g. 'Elastomers Australia'
    api_key_hash    TEXT NOT NULL,                 -- SHA-256 of their API key
    schema_name     TEXT NOT NULL,                 -- e.g. 'tenant_elastomers_au'
    s3_prefix       TEXT NOT NULL,                 -- e.g. 'tenants/elastomers_au/pdfs/'
    config          JSONB NOT NULL DEFAULT '{}',   -- system prompt, doc types, etc.
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 5.2 Per-Tenant Schema (e.g., `tenant_elastomers_au`)

```sql
-- Documents (one row per PDF file)
CREATE TABLE documents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_hash       TEXT NOT NULL UNIQUE,          -- SHA-256 — prevents re-ingestion
    filename        TEXT NOT NULL,
    s3_key          TEXT NOT NULL,
    doc_number      TEXT,                          -- e.g. 'EA-SOP-001'
    doc_type        TEXT,                          -- e.g. 'SOP', 'ENG-DRW', 'ENG-MAT'
    revision        TEXT,                          -- e.g. '4.2'
    title           TEXT,
    issued_date     DATE,
    classification  TEXT,                          -- e.g. 'CONFIDENTIAL', 'Internal Use'
    extra_metadata  JSONB NOT NULL DEFAULT '{}',
    page_count      INTEGER,
    status          TEXT NOT NULL DEFAULT 'pending',  -- pending/processing/complete/error
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Chunks (one row per section chunk — what gets embedded and retrieved)
CREATE TABLE chunks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_number     INTEGER NOT NULL,
    chunk_index     INTEGER NOT NULL,              -- position within page
    heading         TEXT,                          -- extracted markdown heading
    content         TEXT NOT NULL,                 -- chunk text content
    embedding       vector(1536),                  -- OpenAI text-embedding-3-small
    token_count     INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for vector similarity search
CREATE INDEX idx_chunks_embedding ON chunks USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Index for metadata filtering
CREATE INDEX idx_chunks_document_id ON chunks(document_id);
CREATE INDEX idx_documents_doc_type ON documents(doc_type);
CREATE INDEX idx_documents_doc_number ON documents(doc_number);
```

---

## 6. ENVIRONMENT VARIABLES

```bash
# .env.example

# === OpenAI ===
OPENAI_API_KEY=sk-...
OPENAI_LLM_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_EMBEDDING_DIMENSIONS=1536

# === Database ===
DATABASE_URL=postgresql+asyncpg://raguser:ragpass@localhost:5432/ragdb

# === AWS ===
AWS_REGION=ap-southeast-2
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
S3_BUCKET_NAME=rag-system-docs-dev

# === App ===
APP_ENV=development                    # development | production
ADMIN_API_KEY=...                      # For tenant management endpoints
LOG_LEVEL=INFO
MAX_RETRIEVAL_K=5                      # Number of chunks to return after re-ranking
RETRIEVAL_FETCH_MULTIPLIER=20          # Fetch k*20 for MMR before re-ranking
```

---

## 7. DOCUMENT METADATA PARSING

### 7.1 EA Document Numbering Convention

EA filenames follow a consistent pattern:
`{DOC-NUMBER}-{Title-Words}.pdf`

Examples:
- `EA-SOP-001-Screen-Installation.pdf` → doc_type=SOP, doc_number=EA-SOP-001
- `EA-ENG-DRW-7834-HF-Banana-Screen-Manual.pdf` → doc_type=ENG-DRW, doc_number=EA-ENG-DRW-7834
- `EA-ENG-MAT-019-Compound-Formulation-Register.pdf` → doc_type=ENG-MAT, doc_number=EA-ENG-MAT-019
- `EA-STRAT-002-Digital-AI-Strategy.pdf` → doc_type=STRAT, doc_number=EA-STRAT-002

### 7.2 Doc Type Classification

```python
DOC_TYPE_MAP = {
    "SOP":      "Standard Operating Procedure",
    "ENG-DRW":  "Engineering Drawing / Manual",
    "ENG-MAT":  "Material / Compound Specification",
    "STRAT":    "Strategy / Business Document",
    "ENG-FDN":  "Foundation Drawing",
    "QMS":      "Quality Management System",
    "SWMS":     "Safe Work Method Statement",
    "FORM":     "Form / Template",
}
```

### 7.3 First-Page Header Extraction

Each EA document has a consistent header block on page 1:
```
Document Number    EA-SOP-001
Revision           4.2
Effective Date     15 January 2026
Classification     Internal Use — Controlled Document
```

Use Docling to extract page 1, then regex or LLM structured output to parse these fields.

### 7.4 Multi-Tenant Configurability

Each tenant will have different filename conventions and header formats. The `config` JSONB column in the `tenants` table stores:

```json
{
  "doc_number_regex": "^(EA-[A-Z]+-[A-Z]+-?\\d+)",
  "doc_type_map": { "SOP": "Standard Operating Procedure" },
  "header_fields": ["Document Number", "Revision", "Classification"],
  "system_prompt": "You are an engineering assistant for Elastomers Australia...",
  "restricted_doc_types": ["STRAT"],
  "domain_keywords_context": "screen media, polyurethane panels, rubber compounds, mining equipment"
}
```

---

## 8. DOCUMENT TYPE HANDLING NOTES

These are critical — different document types need different extraction treatment.

### SOPs (EA-SOP-001 style)
- Contain numbered safety steps — preserve step numbers in chunks
- Safety notices (⚠️ CRITICAL) must stay with their parent section
- Tables (torque specs, PPE lists) — Docling extracts as markdown tables — preserve as-is
- Cross-references to other documents (e.g. "refer EA-DRW-418") — extract and store as metadata for link resolution

### Engineering Manuals (EA-ENG-DRW-7834 style)
- Model specification tables (HF-1848 vs HF-2160 vs HF-2472 etc.) — keep entire table in one chunk
- Assembly stages are sequential — do not split mid-stage
- References to sibling documents (EA-ENG-DRW-4281 for panel spec, EA-ENG-ELEC-7834 for wiring) — store as cross-reference metadata

### Formulation Registers (EA-ENG-MAT-019 style)
- **HIGHEST SENSITIVITY** — do not expose to non-authorised roles
- Each compound section (NR-35-SA, NR-55-HA, etc.) should be its own chunk with compound code as metadata
- Ingredient tables must be kept intact — do not split across chunks
- Processing parameters and mechanical properties tables — keep together with their parent compound heading

### Specification Sheets (EA-ENG-DRW-4281 style)
- Panel family tables — keep entire comparison table in one chunk
- Dimensional tolerance tables — keep with parent section
- Chemical resistance tables — one chunk per table

---

## 9. API ENDPOINTS

### Phase 1 Endpoints

```
POST   /api/v1/ingest
       Body: multipart/form-data (file, tenant_id)
       Auth: X-API-Key header
       Action: Upload PDF to S3, trigger async ingestion pipeline
       Returns: { job_id, document_id, status }

GET    /api/v1/ingest/{job_id}
       Auth: X-API-Key
       Returns: { status, page_count, chunk_count, errors }

POST   /api/v1/chat
       Body: { tenant_id, query, conversation_id? }
       Auth: X-API-Key
       Returns: { answer, sources, conversation_id, tokens_used }

GET    /api/v1/documents
       Auth: X-API-Key
       Query params: tenant_id, doc_type, limit, offset
       Returns: paginated document list

DELETE /api/v1/documents/{document_id}
       Auth: X-API-Key
       Action: Delete document, all chunks, and S3 object

GET    /api/v1/health
       No auth
       Returns: { status, version, db_connected }
```

### Admin Endpoints (ADMIN_API_KEY only)

```
POST   /api/v1/admin/tenants          Create new tenant
GET    /api/v1/admin/tenants          List all tenants
PATCH  /api/v1/admin/tenants/{id}     Update tenant config
```

---

## 10. PHASE 1 BUILD PLAN — LOCAL DEVELOPMENT

Build and validate fully locally before touching AWS. Everything runs via Docker Compose.

### Task 1: Project Scaffold
- [ ] Create folder structure as defined in Section 4
- [ ] `requirements.txt` with pinned versions
- [ ] `docker-compose.yml` with `postgres:16` + `pgvector/pgvector:pg16` image
- [ ] `.env.example` and `.env` (from example)
- [ ] `app/config.py` using `pydantic-settings` — loads all env vars with validation
- [ ] `app/main.py` — FastAPI app with CORS, lifespan events, router mounting
- [ ] Basic `GET /health` endpoint

### Task 2: Database Setup
- [ ] `app/db/database.py` — async SQLAlchemy engine using `asyncpg`
- [ ] `app/db/models/` — SQLAlchemy models matching schema in Section 5
- [ ] `scripts/setup_db.py` — creates public schema, enables pgvector, creates tenant schemas
- [ ] Alembic init and first migration
- [ ] Create first tenant record for Elastomers Australia via seed script

### Task 3: PDF Ingestion Pipeline
- [ ] `app/core/ingestion/pdf_extractor.py` — Docling wrapper
  - Input: local file path or S3 key
  - Output: list of `PageContent` (page_number, markdown_text, raw_text)
- [ ] `app/core/ingestion/metadata_parser.py` — parse doc_number, doc_type, revision from filename + page 1 header
  - Unit test with all 5 sample EA PDFs
- [ ] `app/core/ingestion/chunker.py` — split page text on markdown headings
  - Handles: heading + content pairs, preserves tables intact, minimum chunk size threshold
- [ ] `app/core/ingestion/embedder.py` — OpenAI embeddings
  - Batch API calls (max 2048 inputs per call)
  - Retry with exponential backoff on rate limits
- [ ] `app/core/ingestion/deduplication.py` — SHA-256 hash check against `documents.file_hash`
- [ ] `app/core/ingestion/pipeline.py` — orchestrates all steps:
  1. Hash check → skip if already ingested
  2. Upload to S3
  3. Extract pages with Docling
  4. Parse metadata
  5. Chunk pages
  6. Generate embeddings (batched)
  7. Insert document + chunks to DB
  8. Update document status
- [ ] `app/utils/s3.py` — upload, download, presigned URL helpers
- [ ] `POST /api/v1/ingest` endpoint — accepts multipart upload, triggers pipeline
- [ ] `scripts/ingest_sample_docs.py` — bulk ingest all 5 EA sample PDFs

### Task 4: Retrieval Pipeline
- [ ] `app/core/retrieval/filter_extractor.py` — LLM extracts structured filters from query
  - Pydantic schema for filter output (doc_type, doc_number, date range, keyword hints)
  - Uses `gpt-4o-mini` with `with_structured_output()`
  - Include EA-specific examples in prompt (SOP, ENG-DRW, ENG-MAT, STRAT)
- [ ] `app/core/retrieval/keyword_generator.py` — LLM generates 5 domain-specific keywords for BM25
  - Prompt calibrated to EA domain terms (screen media, polyurethane, rubber compounds, torque specs, installation procedures)
- [ ] `app/core/retrieval/vector_store.py` — pgvector similarity search
  - Builds `WHERE` conditions from extracted filters
  - Cosine similarity via `<=>` operator
  - Supports `LIMIT k * RETRIEVAL_FETCH_MULTIPLIER` for MMR pool
- [ ] `app/core/retrieval/bm25_ranker.py` — BM25Plus re-ranking
  - Extracts heading + first paragraph from each chunk
  - Scores against domain keywords
  - Returns top-k ranked chunks
- [ ] `app/core/retrieval/retriever.py` — orchestrates full retrieval:
  1. Extract filters from query
  2. Generate ranking keywords
  3. Vector search with filters (fetch k*20)
  4. BM25Plus re-rank → return top k

### Task 5: CRAG Agent (Phase 1 Agent)
- [ ] `app/core/agents/state.py` — `AgentState` TypedDict with messages, retrieved_docs, is_relevant, rewritten_query
- [ ] `app/core/agents/nodes/retrieve.py` — calls retriever, formats results with metadata
- [ ] `app/core/agents/nodes/grade.py` — LLM grades document relevance (yes/no + reasoning)
- [ ] `app/core/agents/nodes/rewrite.py` — rewrites query with better domain keywords
- [ ] `app/core/agents/nodes/generate.py` — generates final answer with inline citations
- [ ] `app/core/agents/nodes/web_search.py` — fallback web search (for when docs don't answer)
- [ ] `app/core/agents/crag_agent.py` — LangGraph graph:
  ```
  START → retrieve → grade → [relevant] → generate → END
                           → [not relevant] → rewrite → web_search → generate → END
  ```
- [ ] System prompt per tenant (loaded from `tenants.config.system_prompt`)

### Task 6: Chat API
- [ ] `POST /api/v1/chat` endpoint
  - Validates tenant API key
  - Loads tenant config from DB
  - Invokes CRAG agent
  - Returns answer + source citations (doc_number, page, chunk heading)
- [ ] `app/schemas/chat.py` — ChatRequest, ChatResponse, Source Pydantic models
- [ ] Basic conversation_id support (pass message history via state)

### Task 7: Testing
- [ ] Unit tests for metadata_parser with all 5 EA sample filenames
- [ ] Unit tests for chunker with real extracted page content
- [ ] Unit tests for filter_extractor with 10+ EA-specific queries
- [ ] Integration test: ingest EA-SOP-001 → query "M20 bolt torque" → verify correct page retrieved
- [ ] Integration test: ingest EA-ENG-DRW-7834 → query "HF-2472 motor mounting bolts" → verify correct model spec
- [ ] API test: full ingest → chat flow via test client
- [ ] Test tenant isolation: two tenants, query from tenant A does not return tenant B docs

### Task 8: Local Validation Queries
After ingesting all 5 EA sample PDFs, validate these specific queries return correct answers:

| Query | Expected Source | Expected Content |
|---|---|---|
| "What torque for M20 Grade 10.9 bolts lubricated?" | EA-SOP-001 Table 7.1 | 370 Nm |
| "What PPE is required for screen installation?" | EA-SOP-001 Section 4.1 | Full PPE list |
| "What are the slope angles on HF-2160?" | EA-ENG-DRW-7834 Table | 35/25/18/12/6° |
| "Motor bolt size for HF-2472?" | EA-ENG-DRW-7834 Stage 2 | M24 Grade 10.9 |
| "Shore A hardness for PU-500 panels?" | EA-ENG-DRW-4281 | 80-85A |
| "Max feed size for PU-600?" | EA-ENG-DRW-4281 | 400mm |
| "What is NR-35-SA used for?" | EA-ENG-MAT-019 | Heavy-duty wear liners, iron ore/gold |
| "Cure temperature for NR-55-HA?" | EA-ENG-MAT-019 | 155°C ± 2°C |
| "How many technicians does EA have?" | EA-STRAT-002 | 350+ field technicians |
| "What is the 90-day competency pathway?" | EA-SOP-001 Section 11 | Week 1-13 breakdown |

---

## 11. PHASE 2 BUILD PLAN — AWS PRODUCTION

Do not start Phase 2 until Phase 1 is fully working and all validation queries pass.

### Task 9: Containerisation
- [ ] `Dockerfile` — multi-stage build:
  - Stage 1: install Python deps
  - Stage 2: copy app, non-root user, health check
- [ ] Verify Docker build runs locally
- [ ] Verify docker-compose runs full stack (app + postgres) locally

### Task 10: AWS Infrastructure Setup
- [ ] Create AWS account / IAM user with least-privilege policy
- [ ] Create S3 bucket in `ap-southeast-2` (Sydney):
  - Server-side encryption (AES-256)
  - Block all public access
  - Lifecycle policy: move to Glacier after 365 days
- [ ] Create RDS PostgreSQL 16 instance in `ap-southeast-2`:
  - Instance: `db.t3.medium` (start small, scale later)
  - Enable pgvector extension
  - Multi-AZ: No (Phase 1), Yes (Phase 2 production)
  - Automated backups: 7 day retention
  - VPC with private subnet — not publicly accessible
- [ ] Create ECR repository for Docker image
- [ ] Create ECS Cluster (Fargate)
- [ ] Create ECS Task Definition:
  - Container: FastAPI app from ECR
  - CPU: 1 vCPU, Memory: 2GB (start)
  - Environment variables sourced from Secrets Manager
  - CloudWatch log group
- [ ] Create ECS Service (Fargate):
  - Desired count: 2 (for basic HA)
  - ALB target group
- [ ] Create Application Load Balancer
- [ ] Create API Gateway (HTTP API):
  - Route all traffic to ALB
  - HTTPS only
  - Throttling: 100 req/s per tenant (configurable)

### Task 11: Secrets & Config
- [ ] Move all secrets to AWS Secrets Manager:
  - `OPENAI_API_KEY`
  - `DATABASE_URL`
  - `ADMIN_API_KEY`
- [ ] Update app to load from Secrets Manager in production (`APP_ENV=production`)
- [ ] IAM role for ECS task: read-only Secrets Manager + S3 read/write for bucket

### Task 12: CI/CD Pipeline
- [ ] GitHub Actions workflow:
  - On push to `main`:
    1. Run pytest
    2. Docker build
    3. Push to ECR
    4. Update ECS service (rolling deploy)
- [ ] Environment: `staging` branch → staging environment, `main` → production

### Task 13: Model Provider Abstraction (Bedrock Migration)
- [ ] `app/core/providers/base.py` — abstract `LLMProvider` interface:
  - `generate(messages, system_prompt) → str`
  - `embed(texts) → list[list[float]]`
- [ ] `app/core/providers/openai_provider.py` — implements interface using OpenAI SDK
- [ ] `app/core/providers/bedrock_provider.py` — implements interface using `boto3` Bedrock client
  - Models: `anthropic.claude-sonnet-4-5` for generation, `amazon.titan-embed-text-v2` for embeddings
  - All in `ap-southeast-2` (Sydney) — satisfies Australian data sovereignty requirement
- [ ] Tenant config can specify `llm_provider: "openai" | "bedrock"` per tenant
- [ ] Migrate EA tenant to Bedrock once validated

### Task 14: Phase 2 Agent Upgrades
- [ ] `app/core/agents/self_rag_agent.py` — Self-RAG with hallucination detection (Notebook 06 pattern)
  - Grade documents → Generate → Check hallucinations → Check answer quality
  - Three binary quality gates before returning answer
- [ ] `app/core/agents/adaptive_agent.py` — Adaptive RAG with query routing (Notebook 07 pattern)
  - Route to: vector docs (RAG), web search (general knowledge)
  - Tenant config controls which routes are enabled
  - Extensible for SQL database route in future
- [ ] LangGraph SQLite checkpointer → migrate to PostgreSQL checkpointer for production conversation memory

### Task 15: Monitoring & Observability
- [ ] CloudWatch metrics: request count, latency P50/P95/P99, error rate, token usage per tenant
- [ ] Structured logging: every request logs tenant_id, query hash, retrieval count, agent steps, total latency
- [ ] Alerts: error rate > 5%, latency P99 > 10s, DB connection failures
- [ ] Cost tracking: tag all resources with `tenant_id` for per-tenant cost attribution

---

## 12. CODING CONVENTIONS

### Python Style
- Python 3.12+
- Type hints everywhere — no untyped functions
- Pydantic v2 for all data validation and schemas
- `async/await` throughout — no synchronous DB or HTTP calls in request path
- Use `from __future__ import annotations` in all files

### Error Handling
- FastAPI `HTTPException` for user-facing errors
- Custom exception classes in `app/core/exceptions.py`
- Never expose internal stack traces in API responses
- Log exceptions with `structlog` including tenant_id and request_id

### Database
- Always use the async session from `app/api/deps.py` — never create sessions manually in route handlers
- All DB operations must be within a transaction
- Never use `tenant_id` as a filter — use the tenant schema directly (defence-in-depth)

### LLM Calls
- Always wrap in try/except with specific error handling for rate limits, context limits, API errors
- Log all LLM calls: model, token counts, latency
- Cache filter extraction results where the same query string is repeated (Redis in Phase 2, simple dict in Phase 1)

### Configuration
- All configuration via `app/config.py` — never `os.environ.get()` directly in business logic
- Sensitive values never logged, never returned in API responses

---

## 13. LOCAL DEV SETUP SEQUENCE

```bash
# 1. Clone and set up Python environment
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# 2. Copy env file and fill in your values
cp .env.example .env
# Edit .env: add OPENAI_API_KEY, AWS credentials

# 3. Start PostgreSQL with pgvector via Docker
docker-compose up -d postgres

# 4. Set up database schemas
python scripts/setup_db.py

# 5. Create the Elastomers Australia tenant
python scripts/seed_tenant.py

# 6. Ingest sample documents
python scripts/ingest_sample_docs.py

# 7. Start FastAPI dev server
uvicorn app.main:app --reload --port 8000

# 8. Test a query
python scripts/test_query.py "What torque for M20 lubricated bolts?"

# 9. Run tests
pytest tests/ -v
```

---

## 14. KEY DESIGN CONSTRAINTS — DO NOT VIOLATE

1. **Tenant isolation is absolute.** Every database query must operate within the correct tenant schema. There must be no shared tables that contain document content or embeddings across tenants.

2. **Never ingest the same file twice.** The SHA-256 hash check in `deduplication.py` must run before Docling extraction — extraction is expensive. If hash exists in `documents.file_hash`, return the existing document_id immediately.

3. **Confidential documents must be access-controlled.** EA-ENG-MAT-019 (formulation register) is marked "HIGHEST CONFIDENTIALITY". The tenant config `restricted_doc_types` list must be checked before returning chunks from those documents. Implement at the retrieval layer, not just the API layer.

4. **OpenAI API calls are the cost driver.** Embedding generation is called once per chunk at ingest time, not at query time. At query time, only the user query is embedded (1 API call). Never re-embed already-ingested chunks.

5. **Australian data sovereignty.** All infrastructure in `ap-southeast-2`. If a tenant has `data_sovereignty: "AU"` in config, enforce Bedrock (not OpenAI) as the LLM provider.

6. **No hardcoded tenant logic.** Everything tenant-specific comes from the database `tenants.config` column. The core RAG code must be completely tenant-agnostic.

---

## 15. REFERENCE NOTEBOOK PATTERNS (source of truth for RAG logic)

The RAG patterns implemented in this project are derived from the following reference notebooks (included in `reference_notebooks/` directory). When implementing agent logic, refer to these directly:

| Notebook | Pattern | Used In |
|---|---|---|
| 01 — PageRAG Data Ingestion | Page-level PDF chunking, hash deduplication | `app/core/ingestion/` |
| 02 — Data Retrieval and ReRanking | Filter extraction + BM25Plus re-ranking | `app/core/retrieval/` |
| 03 — Agentic PageRAG | Basic tool-calling agent loop | Base agent pattern |
| 04 — Corrective RAG (CRAG) | Document grading + query rewrite + web fallback | `app/core/agents/crag_agent.py` (Phase 1) |
| 05 — Reflexion RAG | Iterative self-improvement with reflection | Future Phase 2 |
| 06 — Self-RAG | Hallucination detection + answer quality grading | `app/core/agents/self_rag_agent.py` (Phase 2) |
| 07 — Adaptive RAG | Multi-source routing (docs / SQL / web) | `app/core/agents/adaptive_agent.py` (Phase 2) |

Key differences from notebooks to production code:
- Notebooks use ChromaDB → we use pgvector on RDS
- Notebooks use Ollama (local models) → we use OpenAI API (Phase 1) / Bedrock (Phase 2)
- Notebooks are single-tenant → we are multi-tenant with schema isolation
- Notebooks have no auth → we use API key auth per tenant
- Notebooks use synchronous code → we use async throughout

---

## 16. DOCUMENT CROSS-REFERENCE GRAPH (future capability)

The EA documents contain rich cross-references:
- EA-SOP-001 Section 7.2 references "EA Drawing EA-DRW-418"
- EA-ENG-DRW-7834 references EA-ENG-DRW-4281 (panel spec) and EA-ENG-ELEC-7834 (wiring)
- EA-STRAT-002 references EA-SOP-001 (VR training initiative)

**Future Phase 2 feature:** Extract cross-references during ingestion and store in a `document_links` table. When a chunk is retrieved, automatically surface the linked documents as additional context. This transforms the system from a flat search into a knowledge graph-aware RAG.

---

*Last updated: February 2026*
*System version: 1.0.0-phase1*
