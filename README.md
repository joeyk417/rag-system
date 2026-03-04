# RAG System

Multi-tenant document intelligence system. Companies upload PDFs; users query them in natural language. Each tenant gets an isolated knowledge base.

## Key Differences from Existing Agents

| Concern                | CRAG                  | Reflexion                | Self-RAG                                        |
| ---------------------- | --------------------- | ------------------------ | ----------------------------------------------- |
| Document grading       | Batch all-or-nothing  | None                     | Per-document (N LLM calls, filter individually) |
| Query rewriting        | Single rewrite string | search_queries replaces  | rewritten_queries accumulates                   |
| Hallucination check    | None                  | None                     | Post-generate LLM grade                         |
| Answer completeness    | None S                | elf-reported is_complete | Separate LLM grade                              |
| Iteration guard        | None                  | iteration_count in state | iteration_count in state                        |
| Async conditional edge | No                    | No                       | Yes — check_answer_quality is async             |

## Running Locally

### Prerequisites

- Python 3.12
- Node.js 18+
- Docker

### 1. Start the database

```bash
docker compose up -d postgres
python scripts/setup_db.py
python scripts/seed_tenant.py
```

### 2. Configure environment

```bash
cp .env.example .env
# Fill in OPENAI_API_KEY, TAVILY_API_KEY, ADMIN_API_KEY, etc.
```

### 3. Terminal 1 — Backend

```bash
source venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

### 4. Terminal 2 — Frontend

```bash
cd frontend && npm run dev
# → http://localhost:3000
```

### Keys

| Key         | Value                                |
| ----------- | ------------------------------------ |
| Tenant (EA) | `ea-dev-key-local-testing-only`      |
| Admin       | value of `ADMIN_API_KEY` from `.env` |

### Ingest sample documents

```bash
EA_API_KEY=ea-dev-key-local-testing-only python scripts/ingest_sample_docs.py
```

### Run tests

```bash
pytest tests/ -v
```
