"""Phase 3C-C1 — SEC Taxonomy Catalog Acquisition (read-only, bytes-only).

This module acquires the exact byte payload of the SEC-maintained
https://www.sec.gov/info/edgar/edgartaxonomies.xml catalog and records
it through the existing immutable source_documents layer.

No XML parsing. No authority_taxonomy_namespaces insertion. No B2 change.
Uses existing provider HTTP conventions from sec_provider.py.
"""
from __future__ import annotations

import hashlib
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Optional

# Reuse existing provider identity and HTTP conventions (no new subsystem).
try:
    from sec_provider import DEFAULT_USER_AGENT
except Exception:  # defensive if module paths differ at import time
    DEFAULT_USER_AGENT = "ST-EVA/2.3 (research; contact st-eva@example.com)"

try:
    from archive import StoredDocument
except Exception:
    StoredDocument = None  # type: ignore

URL = "https://www.sec.gov/info/edgar/edgartaxonomies.xml"


def fetch_taxonomy_catalog_bytes(url: str = URL, timeout: int = 15) -> bytes:
    """Fetch exact uncompressed response bytes from the SEC taxonomy catalog.

    Reuses existing urllib/request machinery with the repository's
    DEFAULT_USER_AGENT and timeout. No parsing; raw bytes only.
    Raises on network error, timeout, or non-2xx status so that
    acquisition failure is explicit and does not fabricate evidence.
    """
    req = urllib.request.Request(
        url,
        headers={"User-Agent": DEFAULT_USER_AGENT},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        status = resp.getcode()
        if status is not None and (status < 200 or status >= 300):
            raise ValueError(f"taxonomy catalog fetch failed: HTTP {status} for {url}")
        payload: bytes = resp.read()
    if not payload:
        raise ValueError(f"taxonomy catalog fetch returned empty payload: {url}")
    return payload


def record_taxonomy_catalog(
    payload: bytes,
    archive,
    provider: str = "SecEdgar",
    document_type: str = "SEC_TAXONOMY_CATALOG",
    url: str = URL,
) -> str:
    """Record exact fetched bytes into source_documents via existing writer.

    Computes content_hash over uncompressed bytes (sqlite_archive.py convention);
    derives document_id = doc_ + sha256(content_hash)[:24]; uses existing
    idempotency (same bytes -> existing document_id returned, no duplicate blob).
    No authority rows written; no parsing.
    """
    if StoredDocument is None:
        raise RuntimeError("archive.StoredDocument not available; cannot record")

    content_hash = hashlib.sha256(payload).hexdigest()
    byte_size = len(payload)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    doc = StoredDocument(
        content_hash=content_hash,
        uri=url,
        canonical_uri=url,
        http_status=200,
        media_type="application/xml",
        byte_size=byte_size,
        fetched_at=now,
        first_seen_at=now,
        storage_path=None,
        compression=None,
        payload=payload,
        provider=provider,
        document_type=document_type,
    )
    # archive.record_source_document handles idempotency, inserts with
    # content_hash check, computes doc_... id, commits.
    return archive.record_source_document(doc)
