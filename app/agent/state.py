from __future__ import annotations

# TODO: implement in Task 5
# LangGraph AgentState TypedDict for CRAG flow:
#
# from typing import Annotated
# from typing_extensions import TypedDict
# import operator
#
# class AgentState(TypedDict):
#     query: str                              # original user query
#     rewritten_query: str                    # rewritten query (if retrieval fails grade)
#     retrieved_docs: list[RetrievedChunk]    # output of retriever.py
#     is_relevant: bool                       # output of grade node
#     answer: str                             # final generated answer
#     sources: list[Source]                   # citations for response
#     messages: Annotated[list, operator.add] # for LangGraph message accumulation
#
# Reference: reference_notebooks/04. Corrective RAG (CRAG).ipynb
