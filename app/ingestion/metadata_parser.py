from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DocumentMetadata:
    doc_number: str | None = None
    doc_type: str | None = None
    revision: str | None = None
    title: str | None = None
    classification: str | None = None
    extra_metadata: dict = field(default_factory=dict)


def _derive_doc_type(doc_number: str) -> str | None:
    """Derive doc_type by stripping the tenant prefix and trailing numeric ID.

    Example: 'EA-SOP-001' → 'SOP', 'EA-ENG-DRW-7834' → 'ENG-DRW'
    """
    # Strip leading word prefix (e.g. 'EA-') — everything before the first type segment
    # Split on '-', drop first token (company prefix) and last token (numeric ID)
    parts = doc_number.split("-")
    if len(parts) < 3:
        return None
    # Last part is the numeric ID; first part is the company prefix
    type_parts = parts[1:-1]
    return "-".join(type_parts) if type_parts else None


def parse_filename(filename: str, tenant_config: dict) -> DocumentMetadata:
    """Extract doc_number, doc_type, and title from the filename.

    Uses `tenant_config["doc_number_pattern"]` regex to locate the doc_number.
    Falls back gracefully when the pattern does not match.
    """
    stem = Path(filename).stem  # strip .pdf
    pattern = tenant_config.get("doc_number_pattern")

    if pattern:
        match = re.search(pattern, stem)
        if match:
            doc_number = match.group(1)
            doc_type = _derive_doc_type(doc_number)
            # Title is everything after the doc_number in the stem, dashes → spaces
            after = stem[match.end():].lstrip("-")
            title = after.replace("-", " ").strip() or None
            return DocumentMetadata(doc_number=doc_number, doc_type=doc_type, title=title)

    return DocumentMetadata()


# Patterns for page-1 structured header fields (case-insensitive)
_HEADER_PATTERNS: dict[str, str] = {
    "doc_number": r"(?:document\s+(?:number|no\.?)|doc\.?\s*(?:no\.?|number))\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-]+)",
    "revision": r"(?:revision|rev\.?)\s*[:\-]?\s*([A-Z0-9][A-Z0-9\.\-]*)",
    "classification": r"(?:classification|security\s+classification)\s*[:\-]?\s*([A-Z][A-Z\s]+?)(?:\n|$)",
}


def parse_page1_header(page1_markdown: str, tenant_config: dict) -> dict:  # noqa: ARG001
    """Extract structured fields from page-1 header markdown.

    `tenant_config` is accepted for future extensibility (custom patterns).
    Returns a dict with keys: doc_number, revision, classification (any may be None).
    """
    result: dict[str, str | None] = {}
    for field_name, pattern in _HEADER_PATTERNS.items():
        m = re.search(pattern, page1_markdown, re.IGNORECASE)
        result[field_name] = m.group(1).strip() if m else None
    return result


def parse(filename: str, page1_markdown: str, tenant_config: dict) -> DocumentMetadata:
    """Full metadata parse: filename first, page-1 header overrides revision/classification."""
    meta = parse_filename(filename, tenant_config)
    header = parse_page1_header(page1_markdown, tenant_config)

    # Page-1 header takes precedence for fields it can supply
    if header.get("doc_number") and not meta.doc_number:
        meta.doc_number = header["doc_number"]
    if header.get("revision"):
        meta.revision = header["revision"]
    if header.get("classification"):
        meta.classification = header["classification"]

    return meta
