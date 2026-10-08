"""Phase 3C-C2A — Offline deterministic parser for captured edgartaxonomies.xml.

Pure function: bytes -> structured assertions. No DB. No network. No identity.
Preserves source-declared values verbatim (Family, Version, Namespace, Prefix,
FileTypeName, Href, root version). Reports conflicts deterministically.

Not authorized to write authority_taxonomy_namespaces, compute atn_,
activate B2, or alter 0022.
"""
from __future__ import annotations

from typing import List, Optional, NamedTuple
from xml.etree import ElementTree as ET


class ParsedAuthorityAssertion(NamedTuple):
    """Intermediate pure representation of one source-backed authority assertion.

    Identity fields (per Amendment 6 / frozen schema) are preserved from source
    but NOT persisted here; persistence identity is computed at write time.
    Required fields first; defaults after.
    """
    taxonomy_family: str
    taxonomy_version: str
    namespace_uri: str
    provider: str = "SecEdgar"
    standard_prefix: Optional[str] = None
    file_type_name: Optional[str] = None
    schema_href: Optional[str] = None
    authority_source: str = "https://www.sec.gov/info/edgar/edgartaxonomies.xml"
    authority_source_class: str = "MACHINE_READABLE_CATALOG"
    authority_source_version: str = ""


class CatalogParseError(ValueError):
    """Explicit failure for syntactically or structurally invalid catalog."""
    pass


def parse_edgar_taxonomies_catalog(payload: bytes) -> List[ParsedAuthorityAssertion]:
    """Parse raw uncompressed edgartaxonomies.xml bytes.

    Returns assertions in source order (no silent dedup; duplicates preserved
    as separate entries for evidence reproducibility; writer enforces identity
    idempotency via unique constraint on authority_taxonomy_identity).

    Raises CatalogParseError for malformed XML or missing required fields.
    Returns empty list for valid catalog with zero <Loc> assertions.

    Source-declared values preserved verbatim; no URI inference; no family
    inferred from prefix; no version derived from namespace URI.
    """
    if not isinstance(payload, bytes):
        raise CatalogParseError("payload must be bytes")
    if len(payload) == 0:
        raise CatalogParseError("empty payload")

    # Parse XML deterministically; fail explicitly on syntax errors.
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as e:
        raise CatalogParseError(f"malformed XML: {e}") from e

    # Root element check (structural validation).
    if root.tag != "Erxl":
        # Allow namespace-qualified root if present (defensive); but source uses unqualified.
        # If qualified, extract local name.
        if root.tag.startswith("{"):
            root_tag = root.tag.split("}")[-1]
        else:
            root_tag = root.tag
        if root_tag != "Erxl":
            raise CatalogParseError(f"expected root <Erxl>, got <{root_tag}>")

    # Root release version — must be preserved separately from taxonomy versions.
    root_version = root.get("version")
    if root_version is None or root_version == "":
        raise CatalogParseError("missing root <Erxl version=...>")

    assertions: List[ParsedAuthorityAssertion] = []

    # Source-order iteration over <Loc>; no precedence assigned to first.
    for loc in root.findall("Loc"):
        # Required fields — must exist and have non-empty text.
        family_el = loc.find("Family")
        version_el = loc.find("Version")
        namespace_el = loc.find("Namespace")

        if family_el is None or version_el is None or namespace_el is None:
            raise CatalogParseError(
                "missing required <Family>, <Version>, or <Namespace> in <Loc>"
            )

        family_text = (family_el.text or "").strip()
        version_text = (version_el.text or "").strip()
        namespace_text = (namespace_el.text or "").strip()

        if family_text == "" or version_text == "" or namespace_text == "":
            raise CatalogParseError(
                "required <Family>, <Version>, or <Namespace> is empty"
            )

        # Optional fields — preserved if present; None if absent.
        prefix_el = loc.find("Prefix")
        file_el = loc.find("FileTypeName")
        href_el = loc.find("Href")

        standard_prefix = (prefix_el.text or "").strip() if prefix_el is not None else None
        if standard_prefix == "":
            standard_prefix = None

        file_type_name = (file_el.text or "").strip() if file_el is not None else None
        if file_type_name == "":
            file_type_name = None

        schema_href = (href_el.text or "").strip() if href_el is not None else None
        if schema_href == "":
            schema_href = None

        assertions.append(ParsedAuthorityAssertion(
            provider="SecEdgar",
            taxonomy_family=family_text,
            taxonomy_version=version_text,
            namespace_uri=namespace_text,
            standard_prefix=standard_prefix,
            file_type_name=file_type_name,
            schema_href=schema_href,
            authority_source="https://www.sec.gov/info/edgar/edgartaxonomies.xml",
            authority_source_class="MACHINE_READABLE_CATALOG",
            authority_source_version=root_version,
        ))

    # Zero Loc is a valid catalog (e.g., empty catalog or only comments).
    # Do not treat as error; return empty list deterministically.
    return assertions
