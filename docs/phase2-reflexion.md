# Phase 2 — Reflexion Agent

Start Phase 2 only after all Phase 1 validation queries pass locally.

**Reference notebook:** `reference_notebooks/05. Reflexion Agentic RAG.ipynb`

## What This Phase Builds

Upgrades the CRAG agent to a **Reflexion** agent. Instead of a single retrieve-grade-generate cycle, the agent iteratively drafts an answer, retrieves supporting evidence via multiple targeted sub-queries, revises based on reflection, and repeats until it judges the answer complete (or hits the iteration cap).

This is the right upgrade for queries that need multi-hop reasoning — e.g. "compare the cure temperature of NR-35-SA with the tensile strength spec in the PU panel drawing".

## Agent Flow

```
START → draft → retrieve (multi-query) → revise → should_continue?
                    ↑                                     |
                    └─────────── [incomplete] ────────────┘
                                                          |
                                                   [complete OR max_iter]
                                                          ↓
                                                         END
```

## State

Extends `AgentState` with new fields:

```python
class ReflexionState(TypedDict):
    query: str
    answer: str
    reflection: str          # what is still missing / what was superfluous
    search_queries: list[str] # sub-queries for next retrieval round
    retrieved_docs: list[RetrievedChunk]
    sources: list[Source]
    is_complete: bool
    iteration_count: int
    usage: TokenUsage | None
```

## Answer Schema (LLM structured output)

```python
class ReflexionAnswer(BaseModel):
    answer: str              # 250-300 words, markdown
    reflection: str          # what information is still missing
    search_queries: list[str] # 1-3 specific sub-queries for next iteration
    is_complete: bool        # True when answer fully addresses the question
```

## Nodes

| Node | Input | Output | Key behaviour |
|------|-------|--------|---------------|
| `draft_node` | `query` | `answer`, `reflection`, `search_queries`, `iteration_count=1` | Initial answer attempt with reflection and sub-queries |
| `retrieve_node` | `search_queries` | `retrieved_docs` (accumulated) | Each sub-query retrieved separately via existing `retriever.retrieve()`; results combined |
| `revise_node` | `query`, `answer`, `retrieved_docs`, `reflection` | `answer`, `reflection`, `search_queries`, `is_complete`, `iteration_count++` | Revises answer using new evidence; decides if complete |
| `should_continue` | `is_complete`, `search_queries`, `iteration_count` | `"retrieve"` or `"END"` | END if: `is_complete=True` OR no `search_queries` OR `iteration_count >= MAX_ITERATIONS` |

## Key Parameters

```python
MAX_ITERATIONS = 3          # cap on retrieve-revise cycles
ANSWER_WORDS = "250-300"    # target length in system prompts
```

## Reflexion Prompt Rules

**draft_node system prompt:**
- Generate initial answer with honest gaps identified in `reflection`
- `search_queries` must be company-name + time-period + metric specific
- Set `is_complete: false` if retrieval would help

**revise_node system prompt:**
- Use newly retrieved docs to fill gaps noted in previous `reflection`
- Do not repeat previously used `search_queries`
- Set `is_complete: true` when all sub-questions answered

**WARNING guard:** If `is_complete=False` but `search_queries=[]`, force `is_complete=True` to prevent infinite loop.

## Build Order

1. `app/agent/reflexion_state.py` — `ReflexionState` TypedDict + `ReflexionAnswer` Pydantic model
2. `app/agent/reflexion_nodes.py` — `make_draft_node`, `make_retrieve_node`, `make_revise_node`, `should_continue` router
3. `app/agent/reflexion_agent.py` — `create_reflexion_graph()` + `run_reflexion()` → `(answer, sources, usage)`
4. Wire into `POST /chat` — add `agent_type` param to `ChatRequest` (`"crag"` | `"reflexion"`); default stays `"crag"`
5. `tests/test_agent/test_reflexion_agent.py` — node unit tests + graph flow tests
6. Run validation queries with `agent_type=reflexion` against EA sample docs

## Production Notes

- **Reuses existing retrieval pipeline** — `retriever.retrieve()` is called once per sub-query per iteration; no new retrieval code needed
- **Multi-query retrieval deduplication:** combine results from all sub-queries; deduplicate by `chunk_id` before passing to revise_node
- **LLM call count:** draft (1) + revise per iteration (1) = up to `1 + MAX_ITERATIONS` calls per query
- **Token budget:** truncate accumulated `retrieved_docs` context to `_MAX_CONTEXT_CHARS` same as CRAG generate_node
