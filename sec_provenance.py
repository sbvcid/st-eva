"""
ST-EVA - identity for SEC provenance assertions.

Every relation added by migration `0020_sec_provenance.sql` is content-derived
from what a source *asserted*, and this module is where that identity is
computed. It is deliberately the smallest thing in the provenance layer: seven
pure functions, the closed vocabularies the migration's triggers enforce, and no
I/O of any kind.

Why the identity is a digest of the assertion
----------------------------------------------

A key that names the producer rather than the assertion turns any changed
assertion into a discarded one: the second acquisition hits the same primary key
and is conflict-ignored, so the record of the change is lost. That is the exact
failure `admission_identity` (`sqlite_archive.py:283-308`) names when it puts
`registry_state_identity` and `resolver_policy_identity` inside the key,
"because a key that omitted either would make a change of interpretation
invisible".

So every preimage here is the full asserted payload and nothing else:

* **`captured_at`, `capture_kind`, `declared_at`, `extracted_at` and every
  migration timestamp are excluded.** Re-confirming an assertion later must be a
  no-op, and the first acquisition is the first-hand one. A timestamp inside a
  preimage would make every re-read manufacture a new identity.
* **A NULL is written as `null`, never omitted.** Omitted-versus-null is a
  difference in *what the source said*, so it has to change the digest. Every
  preimage below therefore spells out every key, passing `None` through.
* **`quote_text` is excluded from a statement's identity** while `quote_locator`
  is included. The locator is position, and position is what distinguishes one
  quotation of a kind from another; the text is payload and would drift.

There is one hash framework in this repository and this module joins it rather
than starting another: `canonical_json` is imported from `evidence_model`, the
same function that `sfid_` (`evidence_model.py:199`), `adm_`
(`sqlite_archive.py:1615`) and `line_` hash. No filename or label is used to
derive any identity here, because none of them is a fact about the filing.

Nothing in this module reads an SEC resource, parses a payload, or classifies
anything. It cannot tell a filed document from a furnished one, and that is the
point: classification is a derivation over persisted assertions, and it belongs
to a reader.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional, Tuple

from evidence_model import canonical_json

# The closed vocabularies below are the Python-side statement of what
# `0020_sec_provenance.sql`'s triggers enforce. They exist so that a writer can
# refuse a bad value with a message naming the field, instead of surfacing a
# bare `sqlite3.IntegrityError`. The triggers are not removed: they remain the
# authority for anything that reaches the database by another route.

DECLARATION_SOURCES = (
    "MIGRATION_PROJECTION_HELD_FILINGS",
    "SUBMISSIONS_API_FILING_INDEX",
    "SGML_SUBMISSION_HEADER",
    "FACT_RECORD",
)

ITEM_DECLARATION_SOURCES = (
    "SUBMISSIONS_API_ITEMS",
    "SGML_ITEM_INFORMATION",
)

MANIFEST_SOURCES = (
    "EDGAR_FILING_DIRECTORY_INDEX_JSON",
    "EDGAR_FULL_SUBMISSION_TEXT",
)

ACQUISITION_CLASSES = (
    "SEC_FILING_DOCUMENT",
)

# Exactly two, and deliberately. `FACT_FILED_DATE` is not an acceptance
# datetime: it is a fact's own claim about the day it was filed, it lives on
# `observations.available_at_basis` as `FILED_AS_OF_DATE`, and it is a different
# statement about a different object. Naming it here would make a filed-date
# availability fallback readable as filing-level provenance.
ACCEPTANCE_SOURCES = (
    "SGML_HEADER_ACCEPTANCE_DATETIME",
    "SUBMISSIONS_API_ACCEPTANCE_DATETIME",
)

ACCEPTANCE_PRECISIONS = ("INSTANT", "DATE", "NONE")

STATEMENT_KINDS = ("SECTION_18_NOT_DEEMED_FILED",)

EXTRACTION_METHODS = ("DECLARED_VERBATIM_QUOTE",)

CAPTURE_KINDS = (
    "FIRST_HAND",
    "LATER_ACQUISITION",
    "DECLARED_NOT_CAPTURED",
)

FISCAL_CALENDAR_DECLARATION_SOURCES = (
    "SUBMISSIONS_API_FISCAL_YEAR_END",
    "SGML_HEADER_FISCAL_YEAR_END",
)

# The directory manifest is the only writer that may mint a `filing_documents`
# identity row. A filename is a filesystem identity inside a filing's EDGAR
# directory, so the directory listing's uniqueness is structural; the SGML
# `<DOCUMENT>` sequence is an enumeration the filer authored, and its uniqueness
# is not. `0020_sec_provenance.sql` enforces this with two triggers, and
# `filing_documents_identity_is_declared` is what refuses a write from any other
# manifest.
IDENTITY_MINTING_MANIFEST_SOURCE = "EDGAR_FILING_DIRECTORY_INDEX_JSON"


def _assertion_id(prefix: str, payload: Dict[str, Any], width: int = 32) -> str:
    """The one place a provenance identity is built.

    `canonical_json` sorts keys and fixes the separators, so the same assertion
    renders the same way on any machine and the same assertion therefore hashes
    to the same identity.
    """
    return prefix + hashlib.sha256(
        canonical_json(payload).encode("utf-8")
    ).hexdigest()[:width]


def _check(field: str, value: Any, vocabulary: tuple) -> None:
    if value not in vocabulary:
        raise ValueError(
            f"{field} must be one of {', '.join(vocabulary)}; got {value!r}"
        )


def parse_items(raw_items_text: str) -> Tuple[Tuple[int, str], ...]:
    """
    Split a source's verbatim item string into `(ordinal, code)` pairs.

    A pure function of the string, so the same declaration always parses to the
    same items and a re-run is a no-op. Splitting on `,`, trimming each segment
    and discarding the empty ones is the whole rule; ordinals are then assigned
    over the *kept* items, so a stray or trailing comma renumbers nothing.

    This is the only place the Submissions API's `items` is read. The SGML
    header's `ITEM INFORMATION` carries item *titles* rather than codes and is
    never merged with them here: pairing a code with a title would be an
    inference from list order, and this module makes inferences about nothing.
    """
    items: List[Tuple[int, str]] = []
    for segment in raw_items_text.split(","):
        code = segment.strip()
        if not code:
            continue
        items.append((len(items) + 1, code))
    return tuple(items)


def project_held_filings(store: Any) -> Dict[str, int]:
    """
    Project the ingestion ledger into the provenance relations.

    Four columns, and the four are not negotiable. `asset_id` and `accession`
    identify the filing, `form` and `filed_at` are values both writers of
    `held_filings` record correctly. Everything else in that table is excluded on
    purpose:

        period_end       `_ensure_filing_identity` runs before `_record_filing`
                         and `INSERT OR IGNORE` means first write wins, so this
                         column is NULL on every row.
        report_date      the same writer stores `str(fact["fy"])` here -- the XBRL
                         fiscal *year*, run-verified as '2026'. It is a year, not a
                         date, and no row records which writer produced it, so the
                         column cannot be trusted without knowing that.
        primary_document NULL on every fact-path row.
        document_id      the empty string at both writers.

    Projecting any of those would launder a known ledger defect into an
    authoritative filing fact, and '2026' becoming a filing report date is exactly
    the failure that would be hardest to notice later.

    `capture_kind` is `FIRST_HAND` and `captured_at` is the ledger's own
    `first_seen_at`, never this function's clock. The value genuinely was
    captured when the ingest that wrote the ledger row saw the filing; stamping
    it with the migration time instead would make the archive claim it could not
    know a filing's form until upgrade day.

    Idempotent: the identities are digests of the assertion, so a second run over
    the same ledger writes nothing.
    """
    created = 0
    rows = store.connection.execute(
        "SELECT asset_id, accession, form, filed_at, first_seen_at"
        " FROM held_filings"
    ).fetchall()
    for row in rows:
        identity = filing_declaration_id(
            row["asset_id"], row["accession"],
            "MIGRATION_PROJECTION_HELD_FILINGS",
            form=row["form"], filing_date=row["filed_at"],
        )
        if store.connection.execute(
            "SELECT 1 FROM filing_declarations WHERE declaration_id = ?",
            (identity,),
        ).fetchone() is None:
            created += 1
        store.record_filing(
            row["asset_id"], row["accession"], row["first_seen_at"]
        )
        store.record_filing_declaration(
            identity, row["asset_id"], row["accession"],
            "MIGRATION_PROJECTION_HELD_FILINGS", row["first_seen_at"],
            "FIRST_HAND", form=row["form"], filing_date=row["filed_at"],
        )
    return {
        "rows_seen": len(rows),
        "created": created,
        "declarations_held": store.connection.execute(
            "SELECT COUNT(*) FROM filing_declarations"
            " WHERE declaration_source = 'MIGRATION_PROJECTION_HELD_FILINGS'"
        ).fetchone()[0],
    }


def filing_declaration_id(
    asset_id: str,
    accession: str,
    declaration_source: str,
    form: Optional[str] = None,
    filing_date: Optional[str] = None,
    report_date: Optional[str] = None,
    conformed_period_of_report: Optional[str] = None,
    public_document_count: Optional[int] = None,
    is_xbrl: Optional[int] = None,
    primary_document: Optional[str] = None,
) -> str:
    """
    The identity of one filing-level assertion by one source.

    The preimage is the whole assertion, so a source that changes what it says
    produces a second row rather than amending the first. Every metadata field is
    a key here even when it is `None`, because "the source said nothing about the
    report date" is a different assertion from one that said it.
    """
    _check("declaration_source", declaration_source, DECLARATION_SOURCES)
    return _assertion_id("decl_", {
        "asset_id": asset_id,
        "accession": accession,
        "declaration_source": declaration_source,
        "form": form,
        "filing_date": filing_date,
        "report_date": report_date,
        "conformed_period_of_report": conformed_period_of_report,
        "public_document_count": public_document_count,
        "is_xbrl": is_xbrl,
        "primary_document": primary_document,
    })


def filing_item_declaration_id(
    asset_id: str,
    accession: str,
    declaration_source: str,
    raw_items_text: str,
) -> str:
    """
    The identity of one verbatim item declaration.

    The unsplit string is the assertion, so `raw_items_text` is the preimage and
    not a derived item count. Two sources declaring the same codes are two
    declarations, and neither merges into the other.
    """
    _check("declaration_source", declaration_source, ITEM_DECLARATION_SOURCES)
    return _assertion_id("fid_", {
        "asset_id": asset_id,
        "accession": accession,
        "declaration_source": declaration_source,
        "raw_items_text": raw_items_text,
    })


def filing_item_id(
    declaration_id: str,
    item_ordinal: int,
    item_code: str,
    item_title: Optional[str] = None,
    title_source: Optional[str] = None,
) -> str:
    """
    The identity of one parsed item inside one declaration.

    The ordinal is scoped to its declaration and not to the filing. The same
    ordinal under two declaring sources is two different assertions, and an
    accession-scoped key could not tell them apart -- which is the collision that
    `filing_item_declarations` having its own `declaration_id` exists to remove.

    `item_code` is in the preimage as well as the ordinal so that a changed parse
    produces a second row instead of overwriting the first.
    """
    return _assertion_id("fit_", {
        "declaration_id": declaration_id,
        "item_ordinal": item_ordinal,
        "item_code": item_code,
        "item_title": item_title,
        "title_source": title_source,
    })


def filing_document_declaration_id(
    asset_id: str,
    accession: str,
    manifest_source: str,
    source_ordinal: int,
    filename: Optional[str],
    sec_document_type: Optional[str] = None,
    mime_type: Optional[str] = None,
    byte_size: Optional[int] = None,
    description: Optional[str] = None,
) -> str:
    """
    The identity of one entry in one manifest.

    `source_ordinal` is the position within *one* manifest and means nothing
    across manifests. Measured: an `index.json` listing and the SGML `<DOCUMENT>`
    sequence of the same filing agree at zero of seventeen positions, so the two
    ordinals are never equated and both ordinals coexist for one document.

    `sec_document_type` is the SEC SGML `<TYPE>` (`8-K`, `EX-99.1`) and
    `mime_type` is what `index.json` supplies (`text.gif`). Two columns, two
    vocabularies, two sources. A directory-sourced declaration leaves
    `sec_document_type` `None` and is therefore not classifiable, which is the
    honest result rather than a guess.

    `last_modified` is deliberately absent: it describes the read, not the
    document, so a re-read whose only change is an mtime stays a no-op.
    """
    _check("manifest_source", manifest_source, MANIFEST_SOURCES)
    return _assertion_id("fdd_", {
        "asset_id": asset_id,
        "accession": accession,
        "manifest_source": manifest_source,
        "source_ordinal": source_ordinal,
        "filename": filename,
        "sec_document_type": sec_document_type,
        "mime_type": mime_type,
        "byte_size": byte_size,
        "description": description,
    })


def filing_acceptance_id(
    asset_id: str,
    accession: str,
    acceptance_source: str,
    acceptance_datetime: Optional[str],
    acceptance_precision: str,
    raw_value: Optional[str] = None,
) -> str:
    """
    The identity of one acceptance assertion by one producer.

    Both producers persist for the same filing: the SGML header publishes the ET
    wall clock and the Submissions API publishes the same instant as UTC, and
    neither overwrites the other. Which one a reader prefers is not decided here
    and is not a column.

    `acceptance_source` is checked against a two-member vocabulary, so naming a
    fact's filed date here raises rather than storing a filed-date fallback as if
    it were a dissemination instant.
    """
    _check("acceptance_source", acceptance_source, ACCEPTANCE_SOURCES)
    _check("acceptance_precision", acceptance_precision, ACCEPTANCE_PRECISIONS)
    return _assertion_id("fac_", {
        "asset_id": asset_id,
        "accession": accession,
        "acceptance_source": acceptance_source,
        "acceptance_datetime": acceptance_datetime,
        "acceptance_precision": acceptance_precision,
        "raw_value": raw_value,
    })


def fiscal_calendar_declaration_id(
    asset_id: str,
    fiscal_year_end_mmdd: str,
    declaration_source: str,
    declaring_accession: Optional[str] = None,
) -> str:
    """
    The identity of one declared fiscal year end.

    A declaration, not a resolved calendar. There is no fiscal-year component in
    the preimage and no `fiscal_year` column anywhere, because Contract section
    K.4 leaves per-fiscal-year resolution open and a key that committed to one
    answer would freeze an undecided semantic into the schema.

    The four-character form is the preimage rather than a month integer, because
    '0929' and '0926' differ in the day as well as the month: an issuer whose year
    end moved is two declarations, and storing only the month would let them
    compare equal.
    """
    _check(
        "declaration_source",
        declaration_source,
        FISCAL_CALENDAR_DECLARATION_SOURCES,
    )
    return _assertion_id("ifc_", {
        "asset_id": asset_id,
        "fiscal_year_end_mmdd": fiscal_year_end_mmdd,
        "declaration_source": declaration_source,
        "declaring_accession": declaring_accession,
    })


def filing_document_statement_identity(
    asset_id: str,
    accession: str,
    filename: str,
    document_id: str,
    statement_kind: str,
    quote_locator: str,
) -> str:
    """
    The canonical preimage of a statement, persisted beside its digest.

    The same shape `0019:78` uses for a decision's identity: store the preimage
    so the key can be recomputed rather than trusted.
    """
    _check("statement_kind", statement_kind, STATEMENT_KINDS)
    return canonical_json({
        "asset_id": asset_id,
        "accession": accession,
        "filename": filename,
        "document_id": document_id,
        "statement_kind": statement_kind,
        "quote_locator": quote_locator,
    })


def filing_document_statement_id(
    asset_id: str,
    accession: str,
    filename: str,
    document_id: str,
    statement_kind: str,
    quote_locator: str,
) -> str:
    """
    The identity of one quotation, bound to one captured byte sequence.

    `document_id` is inside the preimage, which is what makes the identity
    capture-scoped. A filing document may be captured more than once, so naming
    the document alone would let a later capture's quotation collide with an
    earlier one. Naming the byte sequence instead means a re-fetch of changed
    bytes yields a different statement and leaves the original untouched.

    `quote_locator` is position -- byte offsets into the decoded capture -- and
    belongs in the key. `quote_text` does not: it is payload, and
    `admission_identity` already established that identity must not carry data
    that can drift from the row it names.

    Two quotations of one kind from one capture at different locators are two
    statements. One quotation re-extracted at a later time is the same statement,
    because `extracted_at` is not in the preimage.
    """
    _check("statement_kind", statement_kind, STATEMENT_KINDS)
    return "fds_" + hashlib.sha256(
        filing_document_statement_identity(
            asset_id, accession, filename, document_id, statement_kind,
            quote_locator,
        ).encode("utf-8")
    ).hexdigest()[:32]


# ---------------------------------------------------------------------------
# 0021 - one logical XBRL fact asserted by one captured document
# ---------------------------------------------------------------------------

#: The eight fields that make a `dfid_`. Frozen by ADR Amendment 2 §3; the test
#: reads them back out of the stored preimage rather than restating them.
DOCUMENT_FACT_IDENTITY_FIELDS: Tuple[str, ...] = (
    "provider", "asset_id", "accession", "document_id",
    "taxonomy", "tag", "context_ref", "unit_ref",
)


def document_fact_identity(
    provider: str,
    asset_id: str,
    accession: str,
    document_id: str,
    taxonomy: str,
    tag: str,
    context_ref: str,
    unit_ref: str,
) -> str:
    """
    The canonical preimage of a document-fact occurrence.

    Unlike a statement, an occurrence has **no filename** in the key even though
    `filing_document_fact_occurrences` carries the column: the fact lives in the
    bytes, and two byte-identical filenames in one filing are two
    `filing_documents` rows and one `document_id`. `filename` is stored beside
    the digest because the foreign keys need it, and kept out of the digest
    because putting it in would fork one fact into two.

    Nor is there a `period_start`/`period_end` pair. In XBRL the period lives
    *inside* the context, so `context_ref` already determines it; carrying it a
    second time invites two derivations of one field to disagree and fork the
    identity. Nor a value, a byte locator, `captured_at` or `capture_kind`: each
    is evidence about the reading, and identity must not carry data that can
    drift from the row it names.

    `dfid_` and `sfid_` are different grains and must never be compared: this one
    names a fact node a document asserts, the other names a reading ST-EVA took
    from a source. Their preimages differ, so they cannot collide by accident.
    """
    return canonical_json({
        "provider": provider,
        "asset_id": asset_id,
        "accession": accession,
        "document_id": document_id,
        "taxonomy": taxonomy,
        "tag": tag,
        "context_ref": context_ref,
        "unit_ref": unit_ref,
    })


def document_fact_id(
    provider: str,
    asset_id: str,
    accession: str,
    document_id: str,
    taxonomy: str,
    tag: str,
    context_ref: str,
    unit_ref: str,
) -> str:
    """
    The identity of one logical fact in one captured document.

    `document_id` is what makes the identity document-scoped: a filed primary
    HTML, an EDGAR-generated `_htm.xml` and a legacy `EX-101.INS` are three
    different byte sequences, so the same concept reported in each is three
    occurrences. That is deliberate and is the whole reason the relation is not a
    source-document assertion -- deciding which of the three is *the* source is a
    question the current evidence cannot answer (invariant 19), and this phase
    does not answer it.

    `context_ref` is in the key because two contexts can carry the same concept,
    the same period and the *same value* and still be two reporting facts. The
    measured case is `ifrs_capex_context_237.py:21-25`, where a dimensional and
    an undimensional context agree numerically: under concept+period+value they
    are one fact, and only `context_ref` tells them apart.
    """
    return "dfid_" + hashlib.sha256(
        document_fact_identity(
            provider, asset_id, accession, document_id, taxonomy, tag,
            context_ref, unit_ref,
        ).encode("utf-8")
    ).hexdigest()[:32]