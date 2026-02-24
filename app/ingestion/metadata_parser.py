from __future__ import annotations

# TODO: implement in Task 3
# Parses document metadata from:
#   1. Filename: {DOC-NUMBER}-{Title}.pdf → doc_number, doc_type, title
#   2. Page 1 header: Document Number, Revision, Effective Date, Classification
# Rules are tenant-configurable via tenants.config (not hardcoded to EA patterns)
# Returns DocumentMetadata(doc_number, doc_type, revision, title, classification, ...)
