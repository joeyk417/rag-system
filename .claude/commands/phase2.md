Read CLAUDE.md, docs/phase2-reflexion.md, and MEMORY.md for current project state.

All Phase 1 validation queries (docs/validation-queries.md) must pass before starting Phase 2.

Then start Phase 2 — Reflexion Agent — following the build order in docs/phase2-reflexion.md:
1. app/agent/reflexion_state.py — ReflexionState TypedDict + ReflexionAnswer Pydantic model
2. app/agent/reflexion_nodes.py — make_draft_node, make_retrieve_node, make_revise_node, should_continue router
3. app/agent/reflexion_agent.py — create_reflexion_graph() + run_reflexion() → (answer, sources, usage)
4. Wire agent_type param into POST /chat (ChatRequest: "crag" | "reflexion", default "crag")
5. tests/test_agent/test_reflexion_agent.py — node unit tests + graph flow tests
6. Run all validation queries with agent_type=reflexion against EA sample docs

Reference notebook: reference_notebooks/05. Reflexion Agentic RAG.ipynb

Ask before making any assumptions not covered in CLAUDE.md or docs/phase2-reflexion.md.
