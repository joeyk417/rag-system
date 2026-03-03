# Phase 3 — Self-RAG Agent

Start Phase 3 only after Phase 2 (Reflexion) is complete and validated.

**Reference notebook:** `reference_notebooks/06. Self-RAG.ipynb`

## What This Phase Builds

Upgrades the Reflexion agent to a **Self-RAG** agent. Adds three independent quality checks after each stage of the pipeline: document relevance grading (before generation), hallucination detection (after generation), and answer completeness grading (after hallucination check). Failed checks trigger targeted recovery actions rather than blind retries.

This is the right upgrade when answer quality guarantees matter — the system can detect and recover from hallucinations without manual intervention.

## Agent Flow

```
START → retrieve → grade_documents →
    [irrelevant / empty] → transform_query → retrieve (loop back)
    [relevant]           → generate →
        [hallucinating]              → generate (retry, same docs)
        [grounded + incomplete]      → transform_query → retrieve (loop back)
        [grounded + complete]        → END
```

## Grading Schemas (Pydantic, binary output)

```python
class GradeDocuments(BaseModel):
    binary_score: Literal["yes", "no"]   # "yes" = docs relevant to question

class GradeHallucinations(BaseModel):
    binary_score: Literal["yes", "no"]   # "yes" = answer grounded in facts

class GradeAnswer(BaseModel):
    binary_score: Literal["yes", "no"]   # "yes" = answer addresses the question

class SearchQueries(BaseModel):
    queries: list[str]  # 1-3 specific sub-queries; must differ from previous
```

## Nodes

| Node | Input | Output | Key behaviour |
|------|-------|--------|---------------|
| `retrieve_node` | `query` or `rewritten_queries` | `retrieved_docs` | Calls `retriever.retrieve()` per query; dedup by `chunk_id` |
| `grade_documents_node` | `query`, `retrieved_docs` | `retrieved_docs` (filtered or empty) | Filters out irrelevant docs; empty list triggers `transform_query` |
| `generate_node` | `query`, `retrieved_docs` | `answer`, `sources`, `usage` | Same as CRAG generate_node; 200-300 words with [1],[2] citations |
| `transform_query_node` | `query`, `rewritten_queries` | `rewritten_queries` | Decomposes into 1-3 specific sub-queries; avoids repeating previous ones |
| `check_answer_quality` | `query`, `answer`, `retrieved_docs` | routing decision | Runs hallucination check then completeness check; see routing below |

## Routing Functions

```python
def should_generate(state) -> str:
    # Empty retrieved_docs after grading → transform_query
    # Non-empty → generate
    return "generate" if state["retrieved_docs"] else "transform_query"

def check_answer_quality(state) -> str:
    # 1. Grade hallucinations: if not grounded → "generate" (retry same docs)
    # 2. Grade answer quality: if grounded but incomplete → "transform_query"
    # 3. Grounded + complete → END
```

## Key Design Notes

- **Permissive document grading:** Grade leniently — only filter out clearly irrelevant docs ("erroneous retrievals"), not borderline ones. Avoids unnecessary transform_query loops.
- **Hallucination retry stays in generate:** If hallucinating, regenerate using the same docs (don't re-retrieve). Only incomplete answers trigger new retrieval.
- **Query expansion in transform_query:** Expand abbreviations ("rev" → "revenue"), fix company name variants ("GOOGL" → "Google"), add domain context.
- **Dedup on rewritten_queries:** `SearchQueries` prompt explicitly says "do not generate queries already tried".

## State

```python
class SelfRAGState(TypedDict):
    query: str
    rewritten_queries: list[str]   # accumulates across transform_query calls
    retrieved_docs: list[RetrievedChunk]
    answer: str
    sources: list[Source]
    usage: TokenUsage | None
```

## Build Order

1. `app/agent/self_rag_state.py` — `SelfRAGState` TypedDict + `GradeDocuments`, `GradeHallucinations`, `GradeAnswer`, `SearchQueries` Pydantic schemas
2. `app/agent/self_rag_nodes.py` — all node factories + `should_generate` and `check_answer_quality` routing functions
3. `app/agent/self_rag_agent.py` — `create_self_rag_graph()` + `run_self_rag()` → `(answer, sources, usage)`
4. Wire into `POST /chat` — add `"self_rag"` to `agent_type` enum in `ChatRequest`
5. `tests/test_agent/test_self_rag_agent.py` — schema validation tests + node unit tests + routing tests + full graph flow
6. Run validation queries with `agent_type=self_rag` against EA sample docs

## Production Notes

- **Reuses existing retrieval pipeline** — no changes to `app/retrieval/`
- **LLM call count per query:** retrieve (0 LLM) + grade_docs (1) + generate (1) + grade_hallucinations (1) + grade_answer (1) = 4 LLM calls minimum; up to ~8 with one retry cycle
- **No infinite loop risk:** `rewritten_queries` accumulation ensures transform_query always generates fresh queries; grade_documents permissive setting keeps the loop short
- **Same citation format** as CRAG: `[1]`, `[2]` inline + `## Sources` at end
