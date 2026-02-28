from __future__ import annotations

from app.ingestion.chunker import chunk_pages
from app.ingestion.pdf_extractor import PageContent


def test_single_page_single_chunk() -> None:
    pages = [PageContent(page_number=1, markdown_text="Hello world")]
    chunks = chunk_pages(pages)
    assert len(chunks) == 1
    assert chunks[0].page_number == 1
    assert chunks[0].chunk_index == 0
    assert chunks[0].content == "Hello world"


def test_heading_extracted_from_markdown() -> None:
    pages = [PageContent(page_number=1, markdown_text="## Installation Guide\n\nStep 1: do this")]
    chunks = chunk_pages(pages)
    assert len(chunks) == 1
    assert chunks[0].heading == "Installation Guide"


def test_h1_heading_extracted() -> None:
    pages = [PageContent(page_number=2, markdown_text="# Top Level Heading\n\nContent here")]
    chunks = chunk_pages(pages)
    assert chunks[0].heading == "Top Level Heading"


def test_no_heading_returns_none() -> None:
    pages = [PageContent(page_number=1, markdown_text="Just plain text, no heading.")]
    chunks = chunk_pages(pages)
    assert chunks[0].heading is None


def test_empty_page_skipped() -> None:
    pages = [
        PageContent(page_number=1, markdown_text="   \n  \n  "),
        PageContent(page_number=2, markdown_text="Real content here"),
    ]
    chunks = chunk_pages(pages)
    assert len(chunks) == 1
    assert chunks[0].page_number == 2


def test_token_count_populated() -> None:
    pages = [PageContent(page_number=1, markdown_text="This is a sentence with some words.")]
    chunks = chunk_pages(pages)
    assert chunks[0].token_count > 0


def test_multi_page_preserves_page_numbers() -> None:
    pages = [
        PageContent(page_number=1, markdown_text="Page one content"),
        PageContent(page_number=2, markdown_text="Page two content"),
        PageContent(page_number=3, markdown_text="Page three content"),
    ]
    chunks = chunk_pages(pages)
    assert len(chunks) == 3
    assert [c.page_number for c in chunks] == [1, 2, 3]
