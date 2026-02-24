from __future__ import annotations

# TODO: implement in Task 5
# LangGraph node functions for CRAG flow:
#
# retrieve_node(state) → update state with retrieved_docs
#   → calls retriever.retrieve(state["query"] or state["rewritten_query"])
#
# grade_node(state) → update state with is_relevant
#   → llm.with_structured_output(GradeDecision) on retrieved_docs vs query
#   → GradeDecision(is_relevant: bool, reasoning: str)
#
# rewrite_node(state) → update state with rewritten_query
#   → LLM rewrites query for better retrieval
#
# web_search_node(state) → update state with retrieved_docs (from Tavily)
#   → TavilySearchResults(k=3).invoke(state["rewritten_query"])
#
# generate_node(state) → update state with answer + sources
#   → LLM generates answer from retrieved_docs with tenant system prompt
#   → Formats source citations (doc_number, page_number, title)
#
# Reference: reference_notebooks/04. Corrective RAG (CRAG).ipynb
