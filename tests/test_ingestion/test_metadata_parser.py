from __future__ import annotations

from app.ingestion.metadata_parser import parse_filename

_EA_CONFIG = {
    "doc_number_pattern": r"^(EA-[A-Z-]+-\d+)",
    "restricted_doc_types": ["ENG-MAT"],
    "data_sovereignty": "AU",
}


def test_sop_filename_parsed() -> None:
    meta = parse_filename("EA-SOP-001-Screen-Installation.pdf", _EA_CONFIG)
    assert meta.doc_number == "EA-SOP-001"
    assert meta.doc_type == "SOP"
    assert meta.title == "Screen Installation"


def test_eng_drw_filename_parsed() -> None:
    meta = parse_filename("EA-ENG-DRW-7834-HF-Banana-Screen-Manual.pdf", _EA_CONFIG)
    assert meta.doc_number == "EA-ENG-DRW-7834"
    assert meta.doc_type == "ENG-DRW"
    assert meta.title == "HF Banana Screen Manual"


def test_eng_mat_filename_parsed() -> None:
    meta = parse_filename("EA-ENG-MAT-019-Compound-Formulation-Register.pdf", _EA_CONFIG)
    assert meta.doc_number == "EA-ENG-MAT-019"
    assert meta.doc_type == "ENG-MAT"
    assert meta.title == "Compound Formulation Register"


def test_strat_filename_parsed() -> None:
    meta = parse_filename("EA-STRAT-002-Digital-AI-Strategy.pdf", _EA_CONFIG)
    assert meta.doc_number == "EA-STRAT-002"
    assert meta.doc_type == "STRAT"
    assert meta.title == "Digital AI Strategy"


def test_unknown_format_returns_none_fields() -> None:
    meta = parse_filename("random-document.pdf", _EA_CONFIG)
    assert meta.doc_number is None
    assert meta.doc_type is None
    assert meta.title is None


def test_no_pattern_config_returns_none_fields() -> None:
    meta = parse_filename("EA-SOP-001-Screen-Installation.pdf", {})
    assert meta.doc_number is None
    assert meta.doc_type is None
