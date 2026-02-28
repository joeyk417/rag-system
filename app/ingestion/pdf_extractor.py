from __future__ import annotations

import asyncio
import tempfile
from dataclasses import dataclass
from pathlib import Path

from docling.document_converter import DocumentConverter

_PAGE_BREAK = "<!-- page break -->"


@dataclass
class PageContent:
    page_number: int  # 1-indexed
    markdown_text: str


def _extract_sync(pdf_path: Path) -> list[PageContent]:
    converter = DocumentConverter()
    result = converter.convert(str(pdf_path))
    markdown = result.document.export_to_markdown(page_break_placeholder=_PAGE_BREAK)
    raw_pages = markdown.split(_PAGE_BREAK)
    pages: list[PageContent] = []
    for i, text in enumerate(raw_pages, start=1):
        pages.append(PageContent(page_number=i, markdown_text=text))
    return pages


async def extract_pages(pdf_bytes: bytes) -> list[PageContent]:
    """Extract per-page markdown from PDF bytes using Docling."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
        tmp.write(pdf_bytes)
        tmp.flush()
        pdf_path = Path(tmp.name)
        pages = await asyncio.to_thread(_extract_sync, pdf_path)
    return pages
