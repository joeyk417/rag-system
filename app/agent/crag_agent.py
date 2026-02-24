from __future__ import annotations

# TODO: implement in Task 5
# LangGraph StateGraph for CRAG:
#
# from langgraph.graph import StateGraph, START, END
#
# builder = StateGraph(AgentState)
# builder.add_node("retrieve", retrieve_node)
# builder.add_node("grade", grade_node)
# builder.add_node("rewrite", rewrite_node)
# builder.add_node("web_search", web_search_node)
# builder.add_node("generate", generate_node)
#
# builder.add_edge(START, "retrieve")
# builder.add_edge("retrieve", "grade")
# builder.add_conditional_edges("grade", should_rewrite, ["rewrite", "generate"])
# builder.add_edge("rewrite", "web_search")
# builder.add_edge("web_search", "generate")
# builder.add_edge("generate", END)
#
# crag_graph = builder.compile()
#
# Graph: START → retrieve → grade → [relevant] → generate → END
#                                 → [irrelevant] → rewrite → web_search → generate → END
#
# Reference: reference_notebooks/04. Corrective RAG (CRAG).ipynb
