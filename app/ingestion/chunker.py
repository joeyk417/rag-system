from __future__ import annotations

import re
from dataclasses import dataclass

import tiktoken

from app.ingestion.pdf_extractor import PageContent

_ENCODER = tiktoken.get_encoding("cl100k_base")
_HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)


@dataclass
class ChunkData:
    page_number: int
    chunk_index: int  # always 0 for page-wise; reserved for sub-page splits
    heading: str | None
    content: str
    token_count: int


def chunk_pages(pages: list[PageContent]) -> list[ChunkData]:
    """Convert per-page markdown into ChunkData records (one chunk per non-empty page)."""
    chunks: list[ChunkData] = []
    for page in pages:
        content = page.markdown_text.strip()
        if not content:
            continue
        heading_match = _HEADING_RE.search(content)
        heading = heading_match.group(1).strip() if heading_match else None
        token_count = len(_ENCODER.encode(content))
        chunks.append(
            ChunkData(
                page_number=page.page_number,
                chunk_index=0,
                heading=heading,
                content=content,
                token_count=token_count,
            )
        )
    return chunks
