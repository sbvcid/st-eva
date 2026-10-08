"""Phase 3C-C3 — Minimal integration workflow for C1 -> C2A -> C2B.

Thin orchestration. No new domain semantics. No parser change. No DB creation.
No B2 activation. No scheduler / CLI / pipeline.
"""
from __future__ import annotations

import importlib.util
import sys
from typing import Optional

# Load C1 acquisition module (archive/ directory, not package)
_acq_spec = importlib.util.spec_from_file_location("acquire_taxonomy_catalog", "archive/acquire_taxonomy_catalog.py")
_acq_mod = importlib.util.module_from_spec(_acq_spec)
sys.modules["acquire_taxonomy_catalog"] = _acq_mod
_acq_spec.loader.exec_module(_acq_mod)

# Load C2B writer (loads parser via its own import mechanism)
_writer_spec = importlib.util.spec_from_file_location("record_authority_taxonomy_assertion", "archive/record_authority_taxonomy_assertion.py")
_writer_mod = importlib.util.module_from_spec(_writer_spec)
sys.modules["record_authority_taxonomy_assertion"] = _writer_mod
_writer_spec.loader.exec_module(_writer_mod)

# Reference actual writer function
record_authority_taxonomy_assertion = _writer_mod.record_authority_taxonomy_assertion

# Reference C1 acquisition functions
fetch_taxonomy_catalog_bytes = _acq_mod.fetch_taxonomy_catalog_bytes
record_taxonomy_catalog = _acq_mod.record_taxonomy_catalog

# C2A parser reference (loaded via writer's mechanism; expose directly)
parse_edgar_taxonomies_catalog = sys.modules.get("parse_edgar_taxonomies_catalog").parse_edgar_taxonomies_catalog

# Default URL from C1
URL = _acq_mod.URL


def run_authority_taxonomy_workflow(
    archive,
    payload_bytes: Optional[bytes] = None,
    provider: str = "SecEdgar",
    document_type: str = "SEC_TAXONOMY_CATALOG",
    url: str = URL,
    captured_at: Optional[str] = None,
) -> dict:
    """Minimal C1 -> C2A -> C2B workflow.

    If payload_bytes is provided (fixture / replay / existing capture), uses it
    directly for source-document recording and parsing (no network).
    If None, acquires from live URL (only for operational / manual use).

    Returns minimal result dict with document identity and assertion count/ids.
    Does not establish B2, does not create CLI, does not alter 0022.
    """
    # 1. Acquisition / source-document persistence (C1 layer)
    if payload_bytes is None:
        payload_bytes = fetch_taxonomy_catalog_bytes(url=url)

    document_id = record_taxonomy_catalog(
        payload_bytes, archive, provider=provider,
        document_type=document_type, url=url,
    )

    # 2. Parser (C2A layer) — pure bytes, no network, no DB
    assertions = parse_edgar_taxonomies_catalog(payload_bytes)

    # 3. Persistence (C2B layer) — one assertion at a time with shared document_id
    atn_ids = []
    for assertion in assertions:
        atn_id = record_authority_taxonomy_assertion(
            archive, assertion, document_id, captured_at=captured_at
        )
        atn_ids.append(atn_id)

    return {
        "document_id": document_id,
        "assertion_count": len(atn_ids),
        "authority_taxonomy_ids": atn_ids,
    }
