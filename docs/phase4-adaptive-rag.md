# Phase 4 — Adaptive RAG Agent

Start Phase 4 only after Phase 3 (Self-RAG) is complete and validated.

**Reference notebook:** `reference_notebooks/07. Adaptive RAG.ipynb`

## What This Phase Builds

Adds an **intelligent router** at the front of the agent graph. Instead of always hitting the vector store, the system first classifies the query intent and routes to the most appropriate data source:

- **`retrieve`** → Self-RAG flow against the tenant's vector store (technical documents)
- **`web_search`** → web search agent for general knowledge / current events
- **`sql_agent`** → structured data queries (future route, stubbed for now)

The routing decision is driven by LLM structured output and tenant config. Each tenant can enable/disable routes and provide routing hints.

## Agent Flow

```
START → route_question →
    [retrieve]      → Self-RAG flow (retrieve → grade_docs → generate → check quality) → END
    [web_search]    → web_search_agent → END
    [sql_agent]     → sql_agent (future stub) → END
```

## RouterQuery Schema

```python
class RouterQuery(BaseModel):
    datasource: Literal["retrieve", "web_search", "sql_agent"]
    reasoning: str = ""
```

## Routing Decision Logic

The router LLM is given:
- The user query
- Tenant-configured routing hints (from `tenant.config["routing"]`)
- List of enabled routes (from `tenant.config["enabled_routes"]`)

Default routing rules (overridable per tenant):
```json
{
  "routing": {
    "retrieve_keywords": ["document", "SOP", "drawing", "spec", "procedure", "formulation", "engineering"],
    "web_search_keywords": ["latest", "current", "news", "price", "today"],
    "sql_keywords": ["employee", "department", "salary", "count", "how many"]
  },
  "enabled_routes": ["retrieve", "web_search"]
}
```

## Nodes

| Node | Input | Output | Key behaviour |
|------|-------|--------|---------------|
| `route_question_node` | `query`, tenant config | `datasource` | LLM structured output → `RouterQuery`; only routes to enabled routes |
| `web_search_agent_node` | `query` | `answer`, `sources=[]` | LangChain agent with Tavily tool; formats answer in markdown |
| `sql_agent_node` | `query` | `answer`, `sources=[]` | **Stub only in Phase 4** — raises `NotImplementedError`; gated by `enabled_routes` so never called unless explicitly enabled |
| All Self-RAG nodes | — | — | Reused unchanged from Phase 3 |

## State

```python
class AdaptiveRAGState(TypedDict):
    query: str
    datasource: str                    # "retrieve" | "web_search" | "sql_agent"
    rewritten_queries: list[str]
    retrieved_docs: list[RetrievedChunk]
    answer: str
    sources: list[Source]
    usage: TokenUsage | None
```

## Multi-Turn Conversation Memory

The notebooks use SQLite for checkpointing. Production uses **PostgreSQL** via LangGraph's `AsyncPostgresSaver`:

```python
# app/agent/adaptive_rag_agent.py
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

async def create_adaptive_rag_graph(tenant, provider, db_session):
    checkpointer = AsyncPostgresSaver(db_session)
    # ... build graph with checkpointer
```

Thread IDs map to conversation sessions — pass `thread_id` from client in `ChatRequest`.

## Build Order

1. `app/agent/adaptive_rag_state.py` — `AdaptiveRAGState` + `RouterQuery` schema
2. `app/agent/adaptive_rag_nodes.py` — `make_route_question_node`, `make_web_search_agent_node`, `make_sql_agent_node` (stub)
3. `app/agent/adaptive_rag_agent.py` — `create_adaptive_rag_graph()` + `run_adaptive_rag()` → `(answer, sources, usage)`
4. Update `ChatRequest` schema — add optional `thread_id: str | None` for multi-turn memory
5. Wire into `POST /chat` — add `"adaptive_rag"` to `agent_type` enum
6. `tests/test_agent/test_adaptive_rag_agent.py` — router tests (retrieve path, web path, disabled route rejection) + graph flow tests
7. Run validation queries with `agent_type=adaptive_rag`; verify routing decisions match expected datasource

## Tenant Config for Routing

```json
{
  "enabled_routes": ["retrieve", "web_search"],
  "routing": {
    "retrieve_keywords": ["SOP", "drawing", "spec", "compound", "formulation", "installation"],
    "web_search_keywords": ["price", "news", "current", "market"]
  }
}
```

EA tenant: only `["retrieve"]` enabled by default — EA queries should always hit the internal document store.

## Production Notes

- **Web search agent** reuses the existing `TavilyClient` from CRAG's `web_search_node` — no new credentials needed
- **SQL agent** is explicitly stubbed with `NotImplementedError` until a tenant with structured data is onboarded
- **Routing fail-safe:** if LLM returns an invalid/disabled datasource, default to `"retrieve"`
- **Thread ID optional:** if no `thread_id` provided, graph runs without checkpointer (stateless, same as previous agents)
- **LLM call count per query:** route (1) + Self-RAG flow (4+) = 5+ calls minimum
