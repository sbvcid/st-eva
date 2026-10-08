"""Phase 3C-C2B — Minimal persistence writer for authority_taxonomy_namespaces.

Writes to existing 0022 table using existing SQLiteArchive connection.
No schema change. No DB creation. No B2. No parser change.
Identity (atn_) derived from frozen Amendment 6 preimage using canonical_json + sha256[:32].
Idempotent by identity uniqueness; conflicts refused by existing triggers (update/delete abort; extraction consistency abort on conflicting reuse of atn_ with different fields).
"""
from __future__ import annotations

import hashlib
import importlib.util
import sys
from datetime import datetime, timezone
from typing import Optional

# Resolve parser module (archive/ directory, not package — load by file)
_parser_spec = importlib.util.spec_from_file_location(
    "parse_edgar_taxonomies_catalog", "archive/parse_edgar_taxonomies_catalog.py"
)
_parser_mod = importlib.util.module_from_spec(_parser_spec)
sys.modules["parse_edgar_taxonomies_catalog"] = _parser_mod
_parser_spec.loader.exec_module(_parser_mod)
ParsedAuthorityAssertion = _parser_mod.ParsedAuthorityAssertion
CatalogParseError = _parser_mod.CatalogParseError

try:
    from evidence_model import canonical_json
except Exception:
    # Defensive fallback matching evidence_model convention exactly
    import json
    def canonical_json(payload):
        return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _canonical_preimage(
    document_id: str,
    namespace_uri: str,
    provider: str,
    taxonomy_family: str,
    taxonomy_version: str,
) -> dict:
    return {
        "document_id": document_id,
        "namespace_uri": namespace_uri,
        "provider": provider,
        "taxonomy_family": taxonomy_family,
        "taxonomy_version": taxonomy_version,
    }


def _authority_taxonomy_id(preimage: dict) -> str:
    return "atn_" + hashlib.sha256(
        canonical_json(preimage).encode("utf-8")
    ).hexdigest()[:32]


def _authority_taxonomy_identity(preimage: dict) -> str:
    return canonical_json(preimage)


def record_authority_taxonomy_assertion(
    archive,
    assertion: ParsedAuthorityAssertion,
    document_id: str,
    captured_at: Optional[str] = None,
) -> str:
    """Write one source-backed authority assertion into 0022 authority_taxonomy_namespaces.

    Returns authority_taxonomy_id (atn_...). Idempotent: same identity already
    present returns existing id without second row (0022 UNIQUE on identity + PK).
    If document_id does not exist in source_documents, the FK violation propagates
    (no bypass, no fabricated row).

    Raises CatalogParseError only if assertion type is wrong; raises IntegrityError
    (FK or unique) naturally from database.
    """
    # Structural check (parser output is NamedTuple; allow duck-typed equivalent)
    required_attrs = ("taxonomy_family", "taxonomy_version", "namespace_uri",
                      "provider", "standard_prefix", "file_type_name",
                      "schema_href", "authority_source", "authority_source_class",
                      "authority_source_version")
    if not (hasattr(assertion, "taxonomy_family") and hasattr(assertion, "namespace_uri")):
        raise TypeError("assertion must provide taxonomy_family and namespace_uri (ParsedAuthorityAssertion-like)")

    # Frozen identity preimage — document_id included; no extra fields.
    preimage = _canonical_preimage(
        document_id=document_id,
        namespace_uri=assertion.namespace_uri,
        provider=assertion.provider,
        taxonomy_family=assertion.taxonomy_family,
        taxonomy_version=assertion.taxonomy_version,
    )
    identity = _authority_taxonomy_identity(preimage)
    atn_id = _authority_taxonomy_id(preimage)

    # Idempotency: same identity already written -> return existing identity.
    # The UNIQUE constraint on authority_taxonomy_identity guarantees this.
    existing = archive.connection.execute(
        "SELECT authority_taxonomy_id FROM authority_taxonomy_namespaces WHERE authority_taxonomy_identity = ?",
        (identity,),
    ).fetchone()
    if existing is not None:
        return existing["authority_taxonomy_id"]

    if captured_at is None:
        captured_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Evidence payload from parser output (preserved verbatim; None where source omitted)
    std_prefix = assertion.standard_prefix
    file_type = assertion.file_type_name
    schema_href = assertion.schema_href

    archive.connection.execute(
        "INSERT INTO authority_taxonomy_namespaces ("
        "authority_taxonomy_id, authority_taxonomy_identity, document_id, provider, "
        "taxonomy_family, taxonomy_version, namespace_uri, standard_prefix, "
        "file_type_name, schema_href, authority_source, authority_source_class, "
        "authority_source_version, captured_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            atn_id,
            identity,
            document_id,
            assertion.provider,
            assertion.taxonomy_family,
            assertion.taxonomy_version,
            assertion.namespace_uri,
            std_prefix,
            file_type,
            schema_href,
            assertion.authority_source,
            assertion.authority_source_class,
            assertion.authority_source_version,
            captured_at,
        ),
    )
    archive.connection.commit()
    return atn_id
