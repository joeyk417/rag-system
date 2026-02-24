from __future__ import annotations

# TODO: implement in Task 6
# Pydantic v2 schemas:
#
# class Source(BaseModel):
#     doc_number: str
#     title: str
#     page_number: int
#     s3_key: str
#
# class ChatRequest(BaseModel):
#     query: str = Field(min_length=1, max_length=2000)
#
# class ChatResponse(BaseModel):
#     answer: str
#     sources: list[Source]
#     query: str
