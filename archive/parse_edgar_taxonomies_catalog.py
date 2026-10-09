"""Phase 3C-C2A — Offline deterministic parser for captured edgartaxonomies.xml.

Pure function: bytes -> structured assertions. No DB. No network. No identity.
Preserves source-declared values verbatim (Family, Version, Namespace, Prefix,
FileTypeName, Href, root version). Reports conflicts deterministically.

Not authorized to write authority_taxonomy_namespaces, compute atn_,
activate B2, or alter 0022.
"""
from __future__ import annotations

from typing import List, Optional, NamedTuple, Tuple, Dict, Union
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
    source_loc_index: Optional[int] = None


class NonAssertionLoc(NamedTuple):
    """Representation of a source <Loc> record ineligible for authority assertion.

    Preserves source position, missing fields, reason, and source-declared values
    without inferring or fabricating missing identity fields.
    """
    source_loc_index: int
    missing_fields: Tuple[str, ...]
    reason: str
    taxonomy_family: Optional[str] = None
    taxonomy_version: Optional[str] = None
    namespace_uri: Optional[str] = None
    standard_prefix: Optional[str] = None
    file_type_name: Optional[str] = None
    schema_href: Optional[str] = None
    att_type: Optional[str] = None
    elements: Optional[str] = None
    authority_source: str = "https://www.sec.gov/info/edgar/edgartaxonomies.xml"
    authority_source_class: str = "MACHINE_READABLE_CATALOG"
    authority_source_version: str = ""


# Alias for compatibility with draft vocabulary
NonAssertionRecord = NonAssertionLoc


class CatalogParseResult(list):
    """Result of parsing edgartaxonomies.xml catalog.

    Behaves as a list of ParsedAuthorityAssertion for complete backwards compatibility
    with callers expecting List[ParsedAuthorityAssertion], while providing structured
    access to assertions, non-assertions, all records, and counts.
    """
    def __init__(
        self,
        assertions: List[ParsedAuthorityAssertion],
        non_assertions: List[NonAssertionLoc],
        root_version: str,
        records: Optional[List[Union[ParsedAuthorityAssertion, NonAssertionLoc]]] = None,
    ):
        super().__init__(assertions)
        self.assertions: List[ParsedAuthorityAssertion] = list(assertions)
        self.non_assertions: List[NonAssertionLoc] = list(non_assertions)
        self.root_version: str = root_version
        self.records: List[Union[ParsedAuthorityAssertion, NonAssertionLoc]] = (
            records if records is not None else []
        )

    @property
    def total_loc_count(self) -> int:
        return len(self.records) if self.records else (len(self.assertions) + len(self.non_assertions))

    @property
    def assertion_eligible_count(self) -> int:
        return len(self.assertions)

    @property
    def non_assertion_count(self) -> int:
        return len(self.non_assertions)

    @property
    def reason_distribution(self) -> Dict[str, int]:
        dist: Dict[str, int] = {}
        for r in self.non_assertions:
            dist[r.reason] = dist.get(r.reason, 0) + 1
        return dist


class CatalogParseError(ValueError):
    """Explicit failure for syntactically or structurally invalid catalog."""
    pass


def parse_edgar_taxonomies_catalog(payload: bytes) -> CatalogParseResult:
    """Parse raw uncompressed edgartaxonomies.xml bytes.

    Returns CatalogParseResult containing assertions and non-assertions in source order.
    Behaves as List[ParsedAuthorityAssertion] for backwards compatibility.
    No silent dedup; duplicates preserved as separate entries for evidence reproducibility;
    writer enforces identity idempotency via unique constraint on authority_taxonomy_identity.

    Raises CatalogParseError for malformed XML or missing required document-level metadata.
    Records lacking required identity fields (Family, Version, Namespace) are classified as
    non-assertions (NonAssertionLoc) rather than failing the entire catalog.

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
    non_assertions: List[NonAssertionLoc] = []
    records: List[Union[ParsedAuthorityAssertion, NonAssertionLoc]] = []

    # Source-order iteration over <Loc>; no precedence assigned to first.
    for idx, loc in enumerate(root.findall("Loc")):
        family_el = loc.find("Family")
        version_el = loc.find("Version")
        namespace_el = loc.find("Namespace")

        family_text = (family_el.text or "").strip() if family_el is not None else ""
        version_text = (version_el.text or "").strip() if version_el is not None else ""
        namespace_text = (namespace_el.text or "").strip() if namespace_el is not None else ""

        # Identity fields required to form authority assertion
        missing_fields: List[str] = []
        if family_el is None or family_text == "":
            missing_fields.append("Family")
        if version_el is None or version_text == "":
            missing_fields.append("Version")
        if namespace_el is None or namespace_text == "":
            missing_fields.append("Namespace")

        # Optional fields — preserved if present; None if absent/empty.
        prefix_el = loc.find("Prefix")
        file_el = loc.find("FileTypeName")
        href_el = loc.find("Href")
        att_el = loc.find("AttType")
        elements_el = loc.find("Elements")

        standard_prefix = (prefix_el.text or "").strip() if prefix_el is not None else None
        if standard_prefix == "":
            standard_prefix = None

        file_type_name = (file_el.text or "").strip() if file_el is not None else None
        if file_type_name == "":
            file_type_name = None

        schema_href = (href_el.text or "").strip() if href_el is not None else None
        if schema_href == "":
            schema_href = None

        att_type = (att_el.text or "").strip() if att_el is not None else None
        if att_type == "":
            att_type = None

        elements = (elements_el.text or "").strip() if elements_el is not None else None
        if elements == "":
            elements = None

        if missing_fields:
            reasons = []
            for f in missing_fields:
                el = loc.find(f)
                if el is None:
                    reasons.append(f"{f.lower()}_absent")
                else:
                    reasons.append(f"{f.lower()}_empty")
            reason = ", ".join(reasons)

            non_assertion = NonAssertionLoc(
                source_loc_index=idx,
                missing_fields=tuple(missing_fields),
                reason=reason,
                taxonomy_family=family_text if family_text else None,
                taxonomy_version=version_text if version_text else None,
                namespace_uri=namespace_text if namespace_text else None,
                standard_prefix=standard_prefix,
                file_type_name=file_type_name,
                schema_href=schema_href,
                att_type=att_type,
                elements=elements,
                authority_source="https://www.sec.gov/info/edgar/edgartaxonomies.xml",
                authority_source_class="MACHINE_READABLE_CATALOG",
                authority_source_version=root_version,
            )
            non_assertions.append(non_assertion)
            records.append(non_assertion)
        else:
            assertion = ParsedAuthorityAssertion(
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
                source_loc_index=idx,
            )
            assertions.append(assertion)
            records.append(assertion)

    return CatalogParseResult(
        assertions=assertions,
        non_assertions=non_assertions,
        root_version=root_version,
        records=records,
    )
