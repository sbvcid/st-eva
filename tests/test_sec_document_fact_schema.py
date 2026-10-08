"""
ST-EVA 0021 - XBRL document-fact provenance schema conformance.

Every assertion here is about what the archive *does now*, and each one is
anchored to a decision frozen in
`docs/ADR-XBRL-SOURCE-DOCUMENT-PROVENANCE.md` Amendment 2 rather than to a
preference:

    §1.1  two additive relations, their keys, their evidence payload
    §1.3  the `observation_sources` guard, and the gate that refuses to apply it
          over data it would contradict
    §2    "occurrence" is a LOGICAL fact in a document, not a physical byte
          span -- so `ix:continuation` does not split one fact into two
    §3    the eight-field preimage, every field kept out of it, and Cases A-F
    §4    five distinct uniqueness notions, counted at document grain
    §8    the amendment-2 correction: a document-route observation carries the
          accession-scoped `sfid_`, never NULL and never a `dfid_`

Nothing here fetches anything, reads `%TEMP%`, or touches the network. The
archive is in-memory and every value is a literal.

`dfid_` is recomputed *in this file*, not imported, for the same reason
`test_sec_provenance_schema.py` reimplements every other identity locally: the
point of a schema test is that the key is reproducible from the stored preimage
by someone who never saw a writer. 0021 is a schema migration and 3C-B is not
authorised, so there is no writer to import from.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple

import sqlite_archive as archive_module
from archive import ArchiveError, StoredDocument
from data_contract import Observation, Unit, ValidationStatus
from sqlite_archive import SQLiteArchive

ASSET = "AAPL"
CIK = "0000320193"
ACCESSION = "0000320193-26-000018"

MANIFEST_DIRECTORY = "EDGAR_FILING_DIRECTORY_INDEX_JSON"

FILENAME_PRIMARY = "aapl-20260730.htm"
FILENAME_EXTRACTED_XML = "aapl-20260730_htm.xml"

PROVIDER = "SecEdgar"
TAXONOMY = "us-gaap"
TAG = "EarningsPerShareDiluted"
CONTEXT_REF = "ixt-c-2026q2"
UNIT_REF = "u-usd-per-share"

CAPTURED_AT = "2026-08-01T00:00:00Z"

OCCURRENCES = "filing_document_fact_occurrences"
LINKS = "observation_filing_document_facts"
NODE_UNIQUE_INDEX = "fact_occurrences_node_unique"

#: The eight fields Amendment 2 §3 freezes as the identity, and nothing else.
IDENTITY_FIELDS: Tuple[str, ...] = (
    "provider", "asset_id", "accession", "document_id",
    "taxonomy", "tag", "context_ref", "unit_ref",
)

#: The five columns of the node-uniqueness index. Amendment 2 §1.1/§3 name
#: them; the test reads them back out of `sqlite_master` rather than restating
#: them, so a wrong index fails here even when the SQL was written to match.
NODE_UNIQUE_COLUMNS: Tuple[str, ...] = (
    "document_id", "taxonomy", "tag", "context_ref", "unit_ref",
)

#: Every column Amendment 2 §1.1 specifies, mapped to whether SQLite reports it
#: NOT NULL. Nothing else may appear.
#:
#: `document_fact_id` is the one `False`: it is a TEXT PRIMARY KEY and this
#: SQLite reports a primary key column as nullable in `PRAGMA table_info`, which
#: is a long-standing SQLite reporting quirk and not a hole here -- the primary
#: key itself refuses a NULL.
OCCURRENCE_NOT_NULL: Dict[str, bool] = {
    "document_fact_id": False,
    "document_fact_identity": True,
    "provider": True,
    "asset_id": True,
    "accession": True,
    "filename": True,
    "document_id": True,
    "taxonomy": True,
    "tag": True,
    "context_ref": True,
    "unit_ref": True,
    "entity_identifier": True,
    "entity_scheme": False,
    "period_kind": True,
    "period_start": False,
    "period_end": False,
    "dimensions_json": True,
    "unit_measures_json": True,
    "value_text": True,
    "resolved_value": True,
    "sign": False,
    "scale": False,
    "format_": False,
    "decimals": False,
    "language": False,
    "locators_json": True,
    "context_locator_json": True,
    "unit_locator_json": True,
    "captured_at": True,
    "capture_kind": True,
}

#: Fields Amendment 2 §3 excludes from the preimage. Excluded from identity is
#: not excluded from the archive, so each must still be stored.
EXCLUDED_FROM_IDENTITY: Tuple[str, ...] = (
    "value_text", "filename", "period_start", "period_end",
    "locators_json", "context_locator_json", "unit_locator_json",
    "captured_at", "capture_kind",
)

#: Invariant 19. No column anywhere in this layer may classify a document's
#: provenance role.
CLASSIFIER_COLUMNS: Tuple[str, ...] = (
    "evidence_class", "audit_status", "filer_authored", "provenance_role",
    "is_primary", "precedence", "confidence",
)

DEFAULT_SPANS = [{"start": 30537, "end": 30926, "xpath": "//ix:nonFraction[1]"}]

#: The approved schema head, frozen. A regression that drops, reorders or
#: renames any approved migration must fail here rather than silently follow
#: the file count. Moving to 0023 is a new phase and must amend this number
#: deliberately; the test must not adopt a future head on its own.
EXPECTED_MIGRATION_HEAD = 22


# ---------------------------------------------------------------------------
# Identity, in the repository's own convention
# ---------------------------------------------------------------------------


def canonical_json(payload: Any) -> str:
    """One rendering, so the same assertion hashes the same way on any machine.

    Byte-for-byte what `evidence_model.canonical_json` does
    (`evidence_model.py:162-166`), which is what `sfid_` and `dfid_` hash.
    """
    return json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )


def document_fact_identity(**fields: str) -> str:
    """The canonical preimage: exactly the eight identity fields, nothing else."""
    return canonical_json({name: fields[name] for name in IDENTITY_FIELDS})


def document_fact_id(**fields: str) -> str:
    return "dfid_" + hashlib.sha256(
        document_fact_identity(**fields).encode("utf-8")
    ).hexdigest()[:32]


def digest_of(identity: str) -> str:
    return "dfid_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]


def locator(start: int, end: int, xpath: str) -> Dict[str, Any]:
    return {"start": start, "end": end, "xpath": xpath}


def occurrence_insert_sql(store: SQLiteArchive) -> str:
    """An `INSERT` naming every column, so a test never depends on column order."""
    columns = [row["name"] for row in store.connection.execute(
        f"PRAGMA table_info({OCCURRENCES})")]
    return (
        f"INSERT INTO {OCCURRENCES} (" + ", ".join(columns) + ") VALUES ("
        + ", ".join("?" * len(columns)) + ")"
    )


# ---------------------------------------------------------------------------
# The fixture
# ---------------------------------------------------------------------------


class FactOccurrenceArchive(unittest.TestCase):
    """An in-memory archive at 0021, with one asset, one filing, one document."""

    def setUp(self) -> None:
        self.store = SQLiteArchive(":memory:")
        self.store.record_asset(ASSET, cik=CIK, name="Apple Inc.")
        self.asset_id = self.asset_id_of(ASSET)
        self.add_filing()
        self.document_id = self.declare_and_capture(
            FILENAME_PRIMARY, b"<html>inline xbrl</html>")
        self._insert_sql = occurrence_insert_sql(self.store)

    def tearDown(self) -> None:
        self.store.close()

    # -- access -----------------------------------------------------------

    @property
    def connection(self):
        return self.store.connection

    def asset_id_of(self, ticker: str) -> str:
        return self.connection.execute(
            "SELECT asset_id FROM assets WHERE ticker = ?", (ticker,)
        ).fetchone()["asset_id"]

    def columns(self, table: str) -> Tuple[str, ...]:
        return tuple(
            row["name"] for row in self.connection.execute(
                f"PRAGMA table_info({table})")
        )

    def columns_of(self, table: str) -> Dict[str, bool]:
        return {
            row["name"]: bool(row["notnull"])
            for row in self.connection.execute(
                f"PRAGMA table_info({table})")
        }

    def count(self, table: str, where: str = "", *args: Any) -> int:
        clause = f" WHERE {where}" if where else ""
        return self.connection.execute(
            f"SELECT COUNT(*) AS n FROM {table}{clause}", args
        ).fetchone()["n"]

    # -- provenance scaffolding -------------------------------------------

    def add_filing(self, accession: str = ACCESSION) -> None:
        self.connection.execute(
            "INSERT OR IGNORE INTO filings (asset_id, accession,"
            " first_archived_at) VALUES (?, ?, ?)",
            (self.asset_id, accession, "2026-07-31T00:30:28Z"),
        )
        self.connection.commit()

    def declare_and_capture(self, filename: str, payload: bytes,
                            accession: str = ACCESSION,
                            ordinal: int = 1) -> str:
        """Directory declaration -> document identity -> bytes -> capture."""
        self.connection.execute(
            "INSERT OR IGNORE INTO filing_document_declarations"
            " (declaration_id, asset_id, accession, manifest_source,"
            " source_ordinal, filename, mime_type, byte_size,"
            " captured_at, capture_kind)"
            " VALUES (?, ?, ?, ?, ?, ?, 'text.gif', ?, ?,"
            " 'FIRST_HAND')",
            (f"fdd-0021-{accession}-{ordinal}", self.asset_id, accession,
             MANIFEST_DIRECTORY, ordinal, filename, len(payload),
             CAPTURED_AT),
        )
        self.connection.execute(
            "INSERT OR IGNORE INTO filing_documents (asset_id, accession,"
            " filename, first_declared_at) VALUES (?, ?, ?, ?)",
            (self.asset_id, accession, filename, CAPTURED_AT),
        )
        document_id = self.store.record_source_document(StoredDocument(
            content_hash="sha256:" + hashlib.sha256(payload).hexdigest(),
            uri=("https://www.sec.gov/Archives/edgar/data/320193/"
                 f"{accession.replace('-', '')}/{filename}"),
            canonical_uri=None, http_status=200, media_type="text/html",
            byte_size=len(payload), fetched_at=CAPTURED_AT,
            first_seen_at=CAPTURED_AT, payload=payload,
            provider=PROVIDER, document_type="SEC_FILING_DOCUMENT",
        ))
        self.connection.execute(
            "INSERT OR IGNORE INTO filing_document_captures (asset_id,"
            " accession, filename, document_id, acquisition_class,"
            " captured_at, capture_kind)"
            " VALUES (?, ?, ?, ?, 'SEC_FILING_DOCUMENT', ?, 'FIRST_HAND')",
            (self.asset_id, accession, filename, document_id, CAPTURED_AT),
        )
        self.connection.commit()
        return document_id

    def capture_endpoint_response(self, payload: bytes) -> str:
        """A `source_documents` row that is *not* a filing-document capture.

        This is what the `companyconcept` route reads, so it is the legitimate
        `observation_sources` target.
        """
        document_id = self.store.record_source_document(StoredDocument(
            content_hash="sha256:" + hashlib.sha256(payload).hexdigest(),
            uri=("https://data.sec.gov/api/xbrl/companyconcept/CIK"
                 f"{CIK}/us-gaap/{TAG}.json"),
            canonical_uri=None, http_status=200,
            media_type="application/json",
            byte_size=len(payload), fetched_at=CAPTURED_AT,
            first_seen_at=CAPTURED_AT, payload=payload,
            provider=PROVIDER, document_type="SEC_COMPANY_CONCEPT",
        ))
        self.connection.commit()
        return document_id

    # -- the occurrence writer --------------------------------------------

    def occurrence_row(
        self,
        document_id: Optional[str] = None,
        filename: str = FILENAME_PRIMARY,
        accession: str = ACCESSION,
        context_ref: str = CONTEXT_REF,
        unit_ref: str = UNIT_REF,
        tag: str = TAG,
        taxonomy: str = TAXONOMY,
        value_text: str = "1.65",
        resolved_value: float = 1.65,
        spans: Optional[Sequence[Dict[str, Any]]] = None,
        period_kind: str = "DURATION",
        period_start: Optional[str] = "2026-04-01",
        period_end: Optional[str] = "2026-06-27",
        dimensions: str = "[]",
        captured_at: str = CAPTURED_AT,
        capture_kind: str = "FIRST_HAND",
    ) -> Dict[str, Any]:
        """One occurrence row, with its eight preimage fields filled in."""
        identity = {
            "provider": PROVIDER,
            "asset_id": self.asset_id,
            "accession": accession,
            "document_id": document_id or self.document_id,
            "taxonomy": taxonomy,
            "tag": tag,
            "context_ref": context_ref,
            "unit_ref": unit_ref,
        }
        return {
            "document_fact_id": document_fact_id(**identity),
            "document_fact_identity": document_fact_identity(**identity),
            "provider": PROVIDER,
            "asset_id": self.asset_id,
            "accession": accession,
            "filename": filename,
            "document_id": identity["document_id"],
            "taxonomy": taxonomy,
            "tag": tag,
            "context_ref": context_ref,
            "unit_ref": unit_ref,
            "entity_identifier": CIK,
            "entity_scheme": "http://www.sec.gov/CIK",
            "period_kind": period_kind,
            "period_start": period_start,
            "period_end": period_end,
            "dimensions_json": dimensions,
            "unit_measures_json": '{"measures":["USD","shares"],"divide":1}',
            "value_text": value_text,
            "resolved_value": resolved_value,
            "sign": None,
            "scale": None,
            "format_": None,
            "decimals": "INF",
            "language": None,
            "locators_json": canonical_json(
                list(spans) if spans is not None else DEFAULT_SPANS),
            "context_locator_json": canonical_json(
                [locator(20010, 20640, "//xbrli:context[1]")]),
            "unit_locator_json": canonical_json(
                [locator(19800, 19920, "//xbrli:unit[1]")]),
            "captured_at": captured_at,
            "capture_kind": capture_kind,
        }

    def insert_occurrence(self, **overrides: Any) -> str:
        row = self.occurrence_row(**overrides)
        self.connection.execute(
            self._insert_sql,
            tuple(row[name] for name in self.columns(OCCURRENCES)),
        )
        self.connection.commit()
        return row["document_fact_id"]

    def stored_occurrence(self, document_fact_id: str) -> sqlite3.Row:
        return self.connection.execute(
            f"SELECT * FROM {OCCURRENCES} WHERE document_fact_id = ?",
            (document_fact_id,),
        ).fetchone()

    def insert_observation(self, document_id: str) -> str:
        """An observation read from an endpoint response, never a filing doc.

        The returned value is the archive's own row id, which is what
        `observations.observation_id` holds and what the link's foreign key
        names. The dataclass field called `observation_id` is in fact the
        *contract* id (`sqlite_archive._row_to_observation` reads it back from
        `contract_id`), so returning the constructor argument would name a row
        that does not exist.
        """
        row_id = self.store.record_observation(
            asset=ASSET,
            observation=Observation(
                observation_id="obs-0021-1",
                metric="eps_diluted",
                value=1.65,
                unit=Unit.RATIO.value,
                currency="USD",
                currency_basis="REPORTED",
                period_start="2026-04-01",
                period_end="2026-06-27",
                as_of="2026-06-27",
                available_at="2026-07-30T20:30:28Z",
                available_at_basis="ACCEPTANCE_DATETIME",
                provider=PROVIDER,
                source_type="REGULATORY_FILING",
                source_url=None,
                retrieved_at="2026-08-01T00:00:00Z",
                definition="eps_diluted",
                methodology="fixture",
                status=ValidationStatus.UNVERIFIABLE,
                status_reasons=(
                    "a single official source cannot cross-validate itself",),
            ),
            availability_class="SOURCE_DECLARED",
            document_hashes=[document_id],
            accession=ACCESSION,
        )
        return row_id


# ---------------------------------------------------------------------------
# A / B / C / O / P -- the migration itself
# ---------------------------------------------------------------------------


class TestMigrationApplies(FactOccurrenceArchive):
    def test_both_relations_exist(self):
        for table in (OCCURRENCES, LINKS):
            self.assertTrue(
                self.connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                    (table,),
                ).fetchone(),
                f"{table} was not created",
            )

    def test_the_version_is_recorded_and_contiguous(self):
        versions = [
            row["version"] for row in self.connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version")
        ]
        self.assertEqual(len(versions), EXPECTED_MIGRATION_HEAD,
                         "the migration ledger must hold exactly the approved"
                         " head")
        self.assertEqual(versions,
                         list(range(1, EXPECTED_MIGRATION_HEAD + 1)))
        self.assertEqual(
            self.connection.execute("PRAGMA user_version").fetchone()[0],
            EXPECTED_MIGRATION_HEAD)

    def test_migration_0022_is_present_and_applied(self):
        """The approved head is 0022: on disk, in the ledger, applied."""
        migration_file = Path(archive_module.MIGRATIONS_DIR) / (
            "0022_authority_taxonomy_namespaces.sql")
        self.assertTrue(
            migration_file.is_file(),
            "0022_authority_taxonomy_namespaces.sql is missing from"
            " the migration directory")
        row = self.connection.execute(
            "SELECT version, name FROM schema_migrations WHERE version = ?",
            (EXPECTED_MIGRATION_HEAD,)).fetchone()
        self.assertIsNotNone(
            row, "0022 is not recorded in the migration ledger")
        self.assertEqual("authority_taxonomy_namespaces", row["name"])
        self.assertTrue(
            self.connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table'"
                " AND name = 'authority_taxonomy_namespaces'").fetchone(),
            "0022 did not apply its relation")

    def test_reopening_applies_nothing_further(self):
        self.store.close()
        reopened = SQLiteArchive(":memory:")
        try:
            self.assertEqual(EXPECTED_MIGRATION_HEAD,
                             self.connection_count_of(reopened))
            self.assertEqual(
                EXPECTED_MIGRATION_HEAD,
                reopened.connection.execute(
                    "PRAGMA user_version").fetchone()[0])
        finally:
            reopened.close()

    @staticmethod
    def connection_count_of(store: SQLiteArchive) -> int:
        return store.connection.execute(
            "SELECT COUNT(*) FROM schema_migrations").fetchone()[0]

    def test_the_gate_helper_does_not_survive(self):
        """The assertion table exists for exactly one statement."""
        self.assertEqual(0, self.count(
            "sqlite_master", "name = '_migration_0021_gate'"))

    def test_the_columns_are_exactly_the_frozen_set(self):
        self.assertEqual(set(OCCURRENCE_NOT_NULL),
                         set(self.columns(OCCURRENCES)))
        self.assertEqual(("observation_id", "document_fact_id"),
                         self.columns(LINKS))

    def test_the_nullability_is_exactly_the_frozen_set(self):
        self.assertEqual(OCCURRENCE_NOT_NULL, self.columns_of(OCCURRENCES))

    def test_no_backfill_happened(self):
        """Schema only. The tables are empty because nothing has read a document."""
        self.assertEqual(0, self.count(OCCURRENCES))
        self.assertEqual(0, self.count(LINKS))
        self.assertEqual(0, self.count("observation_filing_documents"))

    def test_no_classifier_column_exists(self):
        for forbidden in CLASSIFIER_COLUMNS:
            self.assertNotIn(forbidden, self.columns(OCCURRENCES))
            self.assertNotIn(forbidden, self.columns(LINKS))

    def test_observations_was_not_touched(self):
        columns = self.columns("observations")
        for preserved in ("observation_id", "content_hash", "source_fact_id",
                          "accession", "taxonomy", "concept"):
            self.assertIn(preserved, columns)
        self.assertEqual(0, self.count("observations"))

    def test_the_two_new_relations_are_append_only_at_the_schema(self):
        for table in (OCCURRENCES, LINKS):
            self.assertEqual(2, self.count(
                "sqlite_master",
                "type = 'trigger' AND name IN (?, ?)",
                f"{table}_no_update", f"{table}_no_delete"))


# ---------------------------------------------------------------------------
# D + Amendment 2 §3 Cases A-F -- the preimage
# ---------------------------------------------------------------------------


class TestIdentityPreimage(FactOccurrenceArchive):
    def test_the_preimage_holds_exactly_eight_fields(self):
        stored = json.loads(
            self.stored_occurrence(self.insert_occurrence())[
                "document_fact_identity"])
        self.assertEqual(set(IDENTITY_FIELDS), set(stored))

    def test_the_stored_preimage_recomputes_the_key(self):
        row = self.stored_occurrence(self.insert_occurrence())
        self.assertEqual(row["document_fact_id"],
                         digest_of(row["document_fact_identity"]))

    def test_case_a_the_same_fact_is_the_same_identity(self):
        first = self.occurrence_row()
        second = self.occurrence_row()
        self.assertEqual(first["document_fact_id"], second["document_fact_id"])
        self.assertEqual(first["document_fact_identity"],
                         second["document_fact_identity"])

    def test_case_b_changed_bytes_are_a_different_identity(self):
        """Same filename, different captured bytes, therefore a different key."""
        recaptured = self.declare_and_capture(
            FILENAME_PRIMARY, b"<html>inline xbrl, as re-captured</html>")
        self.assertNotEqual(self.document_id, recaptured)
        first = self.insert_occurrence()
        second = self.insert_occurrence(document_id=recaptured)
        self.assertNotEqual(first, second)
        self.assertEqual(2, self.count(
            "filing_document_captures", "filename = ?", FILENAME_PRIMARY))
        self.assertEqual(2, self.count(OCCURRENCES))

    def test_case_c_a_different_context_is_a_different_identity(self):
        undimensioned = self.insert_occurrence()
        dimensioned = self.insert_occurrence(
            context_ref="ixt-c-2026q2-segment",
            dimensions=canonical_json([{
                "axis": "us-gaap:StatementBusinessSegmentsAxis",
                "domain": "us-gaap:StatementBusinessSegmentsDomain",
                "member": "us-gaap:SegmentOneMember",
            }]),
        )
        self.assertNotEqual(undimensioned, dimensioned)
        self.assertEqual(2, self.count(OCCURRENCES))

    def test_case_d_the_value_is_not_in_the_identity(self):
        """One fact, two readings: one identity, and the second row is refused."""
        first = self.insert_occurrence()
        second = self.occurrence_row(value_text="1.66", resolved_value=1.66)
        self.assertEqual(first, second["document_fact_id"],
                         "value exclusion is what makes the collision visible")
        with self.assertRaises(sqlite3.IntegrityError):
            self.insert_occurrence(value_text="1.66", resolved_value=1.66)
        self.assertEqual(1, self.count(OCCURRENCES))

    def test_case_e_several_spans_are_one_logical_fact(self):
        """Inline `ix:continuation` lets one fact span several byte ranges."""
        spans = [
            locator(30537, 30640, "//ix:nonFraction[1]"),
            locator(31880, 31906, "//ix:continuation[1]"),
        ]
        document_fact_id = self.insert_occurrence(spans=spans)
        self.assertEqual(1, self.count(OCCURRENCES))
        self.assertEqual(spans, json.loads(
            self.stored_occurrence(document_fact_id)["locators_json"]))

    def test_case_f_two_documents_are_two_identities(self):
        primary = self.insert_occurrence()
        extracted = self.insert_occurrence(
            document_id=self.declare_and_capture(
                FILENAME_EXTRACTED_XML, b"<xbrl>extracted instance</xbrl>",
                ordinal=7),
            filename=FILENAME_EXTRACTED_XML,
        )
        self.assertNotEqual(primary, extracted)
        self.assertEqual(2, self.count(OCCURRENCES))
        self.assertEqual(2, len({row["filename"] for row in self.connection.execute(
            f"SELECT filename FROM {OCCURRENCES}")}))
        self.assertEqual(
            0, self.count("observation_filing_documents"),
            "case F exists so the 0/1 assertion can be withheld, and this "
            "migration does not write it",
        )

    def test_every_excluded_field_leaves_the_identity_alone(self):
        baseline = self.occurrence_row()
        variations = {
            "the value": dict(value_text="9.99", resolved_value=9.99),
            "the filename": dict(filename=FILENAME_EXTRACTED_XML),
            "the period": dict(period_start="2026-01-01",
                               period_end="2026-03-28"),
            "the locators": dict(spans=[locator(1, 2, "//elsewhere")]),
            "the acquisition": dict(captured_at="2030-01-01T00:00:00Z",
                                    capture_kind="LATER_ACQUISITION"),
        }
        for name, overrides in variations.items():
            varied = self.occurrence_row(**overrides)
            self.assertEqual(
                baseline["document_fact_id"], varied["document_fact_id"],
                f"{name} is excluded from the preimage (Amendment 2 §3)",
            )

    def test_every_excluded_field_is_still_stored(self):
        """Excluded from identity is not excluded from the archive."""
        row = self.stored_occurrence(self.insert_occurrence())
        for field in EXCLUDED_FROM_IDENTITY:
            self.assertIsNotNone(row[field], f"{field} was not persisted")


# ---------------------------------------------------------------------------
# E / F / G -- uniqueness and foreign keys
# ---------------------------------------------------------------------------


class TestNodeUniqueness(FactOccurrenceArchive):
    def index_columns(self, name: str) -> Tuple[str, ...]:
        return tuple(
            row["name"] for row in self.connection.execute(
                f"PRAGMA index_info({name})")
        )

    def test_the_node_uniqueness_index_is_exactly_five_columns(self):
        self.assertEqual(NODE_UNIQUE_COLUMNS,
                         self.index_columns(NODE_UNIQUE_INDEX))

    def test_the_node_uniqueness_index_is_unique(self):
        flagged = [
            row for row in self.connection.execute(
                f"PRAGMA index_list({OCCURRENCES})")
            if row["name"] == NODE_UNIQUE_INDEX
        ]
        self.assertEqual(1, len(flagged))
        self.assertEqual(1, flagged[0]["unique"])

    def test_a_duplicate_node_is_refused(self):
        self.insert_occurrence()
        with self.assertRaises(sqlite3.IntegrityError):
            self.insert_occurrence()
        self.assertEqual(1, self.count(OCCURRENCES))

    def test_a_different_context_in_the_same_document_is_allowed(self):
        self.insert_occurrence(context_ref="ixt-c-a")
        self.insert_occurrence(context_ref="ixt-c-b")
        self.assertEqual(2, self.count(OCCURRENCES))

    def test_the_same_node_in_another_document_is_allowed(self):
        self.insert_occurrence()
        self.insert_occurrence(
            document_id=self.declare_and_capture(
                FILENAME_EXTRACTED_XML, b"<xbrl>other instance</xbrl>",
                ordinal=7),
            filename=FILENAME_EXTRACTED_XML,
        )
        self.assertEqual(2, self.count(OCCURRENCES))

    def test_a_second_reading_with_a_different_preimage_is_refused(self):
        """One node, one identity: `document_fact_identity` is UNIQUE too."""
        self.insert_occurrence()
        tampered = dict(self.occurrence_row())
        tampered["document_fact_id"] = "dfid_" + "0" * 32
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                self._insert_sql,
                tuple(tampered[name] for name in self.columns(OCCURRENCES)),
            )
        self.connection.commit()
        self.assertEqual(1, self.count(OCCURRENCES))

    def test_an_unknown_document_id_is_refused(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.insert_occurrence(document_id="doc_does_not_exist")
        self.assertEqual(0, self.count(OCCURRENCES))

    def test_an_uncaptured_document_id_is_refused(self):
        """Captured bytes but no capture of *this* document under this filename.

        The four-column composite foreign key is the enforcement point, so an
        occurrence cannot be attributed to bytes this filing never captured
        under that name.
        """
        orphan = self.store.record_source_document(StoredDocument(
            content_hash="sha256:" + hashlib.sha256(b"orphan").hexdigest(),
            uri="https://www.sec.gov/Archives/orphan.htm",
            canonical_uri=None, http_status=200, media_type="text/html",
            byte_size=6, fetched_at=CAPTURED_AT, first_seen_at=CAPTURED_AT,
            payload=b"orphan", provider=PROVIDER,
            document_type="SEC_FILING_DOCUMENT",
        ))
        self.connection.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.insert_occurrence(document_id=orphan)
        self.assertEqual(0, self.count(OCCURRENCES))


# ---------------------------------------------------------------------------
# H / I -- append-only
# ---------------------------------------------------------------------------


class TestAppendOnly(FactOccurrenceArchive):
    def setUp(self) -> None:
        super().setUp()
        self.document_fact_id = self.insert_occurrence()

    def test_an_occurrence_cannot_be_updated(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                f"UPDATE {OCCURRENCES} SET value_text = '9.99'"
                " WHERE document_fact_id = ?", (self.document_fact_id,))
        self.connection.commit()
        self.assertEqual(
            "1.65",
            self.stored_occurrence(self.document_fact_id)["value_text"])

    def test_an_occurrence_cannot_be_deleted(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                f"DELETE FROM {OCCURRENCES} WHERE document_fact_id = ?",
                (self.document_fact_id,))
        self.connection.commit()
        self.assertEqual(1, self.count(OCCURRENCES))


# ---------------------------------------------------------------------------
# J -- vocabulary and consistency
# ---------------------------------------------------------------------------


class TestTriggers(FactOccurrenceArchive):
    def test_period_kind_is_a_closed_vocabulary(self):
        with self.assertRaises(sqlite3.IntegrityError) as raised:
            self.insert_occurrence(period_kind="SOMETIME")
        self.assertIn("closed vocabulary", str(raised.exception))
        self.assertEqual(0, self.count(OCCURRENCES))

    def test_capture_kind_is_a_closed_vocabulary(self):
        with self.assertRaises(sqlite3.IntegrityError) as raised:
            self.insert_occurrence(capture_kind="GUESSED")
        self.assertIn("closed vocabulary", str(raised.exception))
        self.assertEqual(0, self.count(OCCURRENCES))

    def test_the_vocabularies_accept_what_they_declare(self):
        self.insert_occurrence(period_kind="INSTANT", period_start=None,
                               period_end="2026-06-27")
        self.insert_occurrence(period_kind="FOREVER", period_start=None,
                               period_end=None, context_ref="ixt-forever")
        self.insert_occurrence(context_ref="ixt-later",
                               capture_kind="LATER_ACQUISITION")
        self.assertEqual(3, self.count(OCCURRENCES))

    def test_a_non_deterministic_reread_is_visible(self):
        """`0020:423-432` in the fact layer: one identity, two readings, refuse."""
        self.insert_occurrence()
        reread = dict(self.occurrence_row(value_text="1.66",
                                          resolved_value=1.66))
        with self.assertRaises(sqlite3.DatabaseError) as raised:
            self.connection.execute(
                self._insert_sql,
                tuple(reread[name] for name in self.columns(OCCURRENCES)),
            )
        self.connection.rollback()
        self.assertIn("not deterministic", str(raised.exception))
        self.assertEqual(1, self.count(OCCURRENCES))

    def test_a_matching_reread_reports_the_key_conflict_not_the_parser(self):
        """Identical evidence is idempotent-by-conflict, and says why."""
        self.insert_occurrence()
        with self.assertRaises(sqlite3.DatabaseError) as raised:
            self.insert_occurrence()
        self.assertNotIn("not deterministic", str(raised.exception))


# ---------------------------------------------------------------------------
# K -- the observation link
# ---------------------------------------------------------------------------


class TestObservationLink(FactOccurrenceArchive):
    def setUp(self) -> None:
        super().setUp()
        self.endpoint_document_id = self.capture_endpoint_response(
            b'{"units":{"USD/shares":[]}}')
        self.observation_id = self.insert_observation(self.endpoint_document_id)

    def link(self, observation_id: str, document_fact_id: str) -> None:
        self.connection.execute(
            f"INSERT INTO {LINKS} (observation_id, document_fact_id)"
            " VALUES (?, ?)", (observation_id, document_fact_id))

    def test_a_link_can_be_written(self):
        self.link(self.observation_id, self.insert_occurrence())
        self.connection.commit()
        self.assertEqual(1, self.count(LINKS))

    def test_several_document_facts_may_hang_off_one_observation(self):
        """Two contexts, one observation: `observation_id` has no dimension."""
        first = self.insert_occurrence(context_ref="ixt-c-a")
        second = self.insert_occurrence(context_ref="ixt-c-b")
        self.link(self.observation_id, first)
        self.link(self.observation_id, second)
        self.connection.commit()
        self.assertEqual(2, self.count(LINKS))

    def test_there_is_no_unique_on_observation_id(self):
        for flagged in self.connection.execute(f"PRAGMA index_list({LINKS})"):
            if not flagged["unique"] or flagged["origin"] == "pk":
                continue
            names = [
                row["name"] for row in self.connection.execute(
                    f"PRAGMA index_info({flagged['name']})")
            ]
            self.assertNotEqual(["observation_id"], names)

    def test_an_unknown_observation_is_refused(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.link("obs_absent", self.insert_occurrence())
        self.connection.commit()

    def test_an_unknown_document_fact_is_refused(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.link(self.observation_id, "dfid_absent")
        self.connection.commit()

    def test_the_link_is_append_only(self):
        self.link(self.observation_id, self.insert_occurrence())
        self.connection.commit()
        for statement in (
                f"UPDATE {LINKS} SET document_fact_id = 'dfid_x'",
                f"DELETE FROM {LINKS}"):
            with self.assertRaises(sqlite3.IntegrityError):
                self.connection.execute(statement)
            self.connection.commit()
        self.assertEqual(1, self.count(LINKS))

    def test_the_link_is_not_a_candidate_document_relation(self):
        """Amendment 2 §1.2: it never creates a source-document assertion."""
        self.link(self.observation_id, self.insert_occurrence())
        self.connection.commit()
        self.assertEqual(0, self.count("observation_filing_documents"))

    def test_it_supplements_rather_than_re_keys_the_existing_route(self):
        before = self.connection.execute(
            "SELECT observation_id, content_hash, source_fact_id FROM observations"
        ).fetchall()
        self.link(self.observation_id, self.insert_occurrence())
        self.connection.commit()
        after = self.connection.execute(
            "SELECT observation_id, content_hash, source_fact_id FROM observations"
        ).fetchall()
        self.assertEqual([tuple(row) for row in before],
                         [tuple(row) for row in after])


# ---------------------------------------------------------------------------
# L -- the frozen relation is untouched
# ---------------------------------------------------------------------------


class TestObservationFilingDocumentsUntouched(FactOccurrenceArchive):
    EXPECTED = (
        "observation_id", "asset_id", "accession", "filename",
        "captured_at", "capture_kind",
    )

    def test_the_columns_are_unchanged(self):
        self.assertEqual(self.EXPECTED,
                         self.columns("observation_filing_documents"))

    def test_it_is_still_append_only(self):
        self.assertEqual(2, self.count(
            "sqlite_master",
            "type = 'trigger' AND name IN"
            " ('observation_filing_documents_no_update',"
            " 'observation_filing_documents_no_delete')"))

    def test_it_still_carries_no_confidence_or_precedence(self):
        columns = self.columns("observation_filing_documents")
        for forbidden in ("confidence", "precedence", "rank", "ordinal",
                          "evidence_class", "audit_status"):
            self.assertNotIn(forbidden, columns)

    def test_0021_created_no_candidate_row_for_it(self):
        self.insert_occurrence()
        self.assertEqual(0, self.count("observation_filing_documents"))


# ---------------------------------------------------------------------------
# M -- the observation_sources guard
# ---------------------------------------------------------------------------


class TestObservationSourcesGuard(FactOccurrenceArchive):
    def setUp(self) -> None:
        super().setUp()
        self.endpoint_document_id = self.capture_endpoint_response(
            b'{"units":{"USD/shares":[]}}')
        self.observation_id = self.insert_observation(self.endpoint_document_id)

    def assert_filing_reference_refused(self) -> None:
        with self.assertRaises(sqlite3.DatabaseError) as raised:
            self.connection.execute(
                "INSERT INTO observation_sources (observation_id, document_id,"
                " accession) VALUES (?, ?, ?)",
                (self.observation_id, self.document_id, ACCESSION))
        self.connection.rollback()
        self.assertIn("observation_filing_documents", str(raised.exception))

    def test_the_guard_is_a_database_trigger(self):
        self.assertTrue(
            self.connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'trigger'"
                " AND name = 'observation_sources_excludes_filing_documents'"
            ).fetchone(),
            "the guard must be schema-level, not a Python convention")

    def test_a_non_filing_source_document_is_still_allowed(self):
        self.assertEqual(1, self.count(
            "observation_sources", "document_id = ?",
            self.endpoint_document_id))

    def test_a_filing_document_is_refused(self):
        self.assert_filing_reference_refused()
        self.assertEqual(0, self.count(
            "observation_sources", "document_id = ?", self.document_id))

    def test_the_refusal_happens_at_the_statement(self):
        """No archive method is consulted; the INSERT itself fails."""
        self.assert_filing_reference_refused()
        self.assertEqual(1, self.count("observation_sources"))

    def test_the_refusal_leaves_the_legitimate_link_alone(self):
        self.assert_filing_reference_refused()
        self.assertEqual(1, self.count(
            "observation_sources", "document_id = ?",
            self.endpoint_document_id))

    def test_an_exact_source_document_still_has_its_own_relation(self):
        """The guard redirects the claim rather than forbidding provenance."""
        self.connection.execute(
            "INSERT INTO observation_filing_documents (observation_id,"
            " asset_id, accession, filename, captured_at, capture_kind)"
            " VALUES (?, ?, ?, ?, ?, 'FIRST_HAND')",
            (self.observation_id, self.asset_id, ACCESSION, FILENAME_PRIMARY,
             CAPTURED_AT))
        self.connection.commit()
        self.assertEqual(1, self.count("observation_filing_documents"))

    def test_the_guard_does_not_disturb_the_second_document_fact(self):
        """A captured filing document may still hold several logical facts."""
        first = self.insert_occurrence(context_ref="ixt-c-a")
        second = self.insert_occurrence(context_ref="ixt-c-b")
        self.assertNotEqual(first, second)
        self.assertEqual(2, self.count(OCCURRENCES))
        self.assertEqual(0, self.count("observation_sources", "1=0"))


# ---------------------------------------------------------------------------
# N -- the pre-migration gate
# ---------------------------------------------------------------------------


class TestPreMigrationGate(unittest.TestCase):
    """A violating archive must be refused, not repaired.

    The repository holds no production archive, so the violating state is built
    deliberately rather than assumed absent. That is the point of the test: the
    gate's job is to refuse, so a refusal has to be exercised, and the archive
    the tests normally use is clean by construction.
    """

    def setUp(self) -> None:
        self.directory = tempfile.mkdtemp(prefix="steva-0021-gate-")
        self.path = str(Path(self.directory) / "gate.sqlite")
        self.real_migrations = archive_module.MIGRATIONS_DIR
        self.through_0020 = Path(self.directory) / "migrations"
        self.through_0020.mkdir()
        for source in sorted(self.real_migrations.glob("*.sql")):
            if int(source.stem.partition("_")[0]) <= 20:
                shutil.copy2(source, self.through_0020 / source.name)

    def tearDown(self) -> None:
        archive_module.MIGRATIONS_DIR = self.real_migrations
        shutil.rmtree(self.directory, ignore_errors=True)

    def open_at_0020(self) -> SQLiteArchive:
        archive_module.MIGRATIONS_DIR = self.through_0020
        store = SQLiteArchive(self.path)
        self.assertEqual(20, store.connection.execute(
            "PRAGMA user_version").fetchone()[0])
        return store

    def seed_violation(self, store: SQLiteArchive) -> str:
        """An `observation_sources` row pointing at a filing document.

        Only constructible before 0021: the guard does not exist yet. That is
        exactly why the gate must run before the guard is installed.
        """
        connection = store.connection
        store.record_asset(ASSET, cik=CIK, name="Apple Inc.")
        asset_id = connection.execute(
            "SELECT asset_id FROM assets WHERE ticker = ?", (ASSET,)
        ).fetchone()["asset_id"]
        connection.execute(
            "INSERT INTO filings (asset_id, accession, first_archived_at)"
            " VALUES (?, ?, '2026-07-31T00:30:28Z')", (asset_id, ACCESSION))
        # A capture is only legal for a document the directory manifest declared
        # exactly once, so the violating state is built through the real chain
        # rather than by inserting a document identity directly.
        connection.execute(
            "INSERT INTO filing_document_declarations (declaration_id,"
            " asset_id, accession, manifest_source, source_ordinal, filename,"
            " mime_type, byte_size, captured_at, capture_kind)"
            " VALUES ('fdd-gate', ?, ?, ?, 1, 'x.htm', 'text.gif', 12, ?,"
            " 'FIRST_HAND')",
            (asset_id, ACCESSION, MANIFEST_DIRECTORY, CAPTURED_AT))
        connection.execute(
            "INSERT INTO filing_documents (asset_id, accession, filename,"
            " first_declared_at) VALUES (?, ?, 'x.htm', ?)",
            (asset_id, ACCESSION, CAPTURED_AT))
        filing_document_id = store.record_source_document(StoredDocument(
            content_hash="sha256:" + hashlib.sha256(b"filing bytes").hexdigest(),
            uri="https://www.sec.gov/Archives/x.htm",
            canonical_uri=None, http_status=200, media_type="text/html",
            byte_size=12, fetched_at=CAPTURED_AT, first_seen_at=CAPTURED_AT,
            payload=b"filing bytes", provider=PROVIDER,
            document_type="SEC_FILING_DOCUMENT",
        ))
        connection.execute(
            "INSERT INTO filing_document_captures (asset_id, accession,"
            " filename, document_id, acquisition_class, captured_at,"
            " capture_kind) VALUES (?, ?, 'x.htm', ?,"
            " 'SEC_FILING_DOCUMENT', ?, 'FIRST_HAND')",
            (asset_id, ACCESSION, filing_document_id, CAPTURED_AT))
        # The violation is produced through the real ingestion path, not by
        # hand: `record_observation(document_hashes=[filing hash])` is exactly
        # what a document route would do, and at 0020 nothing refuses it. That
        # is why the gate has to exist before the guard does.
        store.record_observation(
            asset=ASSET,
            observation=Observation(
                observation_id="obs-gate",
                metric="eps_diluted",
                value=1.65,
                unit=Unit.RATIO.value,
                currency="USD",
                currency_basis="REPORTED",
                period_start="2026-04-01",
                period_end="2026-06-27",
                as_of="2026-06-27",
                available_at="2026-07-30T20:30:28Z",
                available_at_basis="ACCEPTANCE_DATETIME",
                provider=PROVIDER,
                source_type="REGULATORY_FILING",
                source_url=None,
                retrieved_at=CAPTURED_AT,
                definition="eps_diluted",
                methodology="fixture",
                status=ValidationStatus.UNVERIFIABLE,
                status_reasons=(
                    "a single official source cannot cross-validate itself",),
            ),
            availability_class="SOURCE_DECLARED",
            document_hashes=[filing_document_id],
            accession=ACCESSION,
        )
        connection.commit()
        return filing_document_id

    def read_sources(self, path: Optional[str] = None) -> list:
        connection = sqlite3.connect(path or self.path)
        connection.row_factory = sqlite3.Row
        try:
            return [tuple(row) for row in connection.execute(
                "SELECT observation_id, document_id, accession"
                " FROM observation_sources ORDER BY observation_id")]
        finally:
            connection.close()

    def master_names(self, path: Optional[str] = None) -> list:
        connection = sqlite3.connect(path or self.path)
        try:
            return [row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")]
        finally:
            connection.close()

    def test_a_clean_archive_at_0020_migrates(self):
        store = self.open_at_0020()
        store.close()
        archive_module.MIGRATIONS_DIR = self.real_migrations
        reopened = SQLiteArchive(self.path)
        try:
            self.assertEqual(EXPECTED_MIGRATION_HEAD,
                             reopened.connection.execute(
                                 "PRAGMA user_version").fetchone()[0])
            self.assertIn(OCCURRENCES, self.master_names())
            self.assertIn("authority_taxonomy_namespaces", self.master_names())
        finally:
            reopened.close()

    def test_a_violating_archive_is_refused(self):
        store = self.open_at_0020()
        self.seed_violation(store)
        store.close()
        archive_module.MIGRATIONS_DIR = self.real_migrations
        with self.assertRaises(sqlite3.DatabaseError) as raised:
            SQLiteArchive(self.path)
        self.assertIn("migration_0021", str(raised.exception))

    def test_the_refusal_repairs_nothing(self):
        store = self.open_at_0020()
        document_id = self.seed_violation(store)
        before = self.read_sources()
        self.assertEqual(1, len(before))
        self.assertEqual(document_id, before[0][1],
                         "the seeded row must actually violate the guard")
        store.close()

        archive_module.MIGRATIONS_DIR = self.real_migrations
        with self.assertRaises(sqlite3.DatabaseError):
            SQLiteArchive(self.path)

        after = self.read_sources()
        self.assertEqual(before, after,
                         "the gate refuses; it never repairs, never deletes "
                         "and never rewrites")
        self.assertEqual(1, len(after))
        self.assertEqual(document_id, after[0][1])

    def test_the_refusal_creates_nothing_and_records_nothing(self):
        store = self.open_at_0020()
        self.seed_violation(store)
        store.close()
        archive_module.MIGRATIONS_DIR = self.real_migrations
        with self.assertRaises(sqlite3.DatabaseError):
            SQLiteArchive(self.path)

        names = self.master_names()
        self.assertNotIn(OCCURRENCES, names)
        self.assertNotIn(LINKS, names)
        self.assertNotIn("_migration_0021_gate", names)

        connection = sqlite3.connect(self.path)
        try:
            self.assertIsNone(connection.execute(
                "SELECT 1 FROM schema_migrations WHERE version = 21"
            ).fetchone(), "a refused migration is not recorded")
            self.assertEqual(20, connection.execute(
                "PRAGMA user_version").fetchone()[0],
                "user_version must not advance past a refused migration")
        finally:
            connection.close()

    def test_forward_only_integrity_is_unchanged(self):
        """Editing an applied migration is still refused after 0021 exists."""
        store = self.open_at_0020()
        store.close()
        connection = sqlite3.connect(self.path)
        with connection:
            connection.execute(
                "UPDATE schema_migrations SET checksum = 'tampered'"
                " WHERE version = 20")
        connection.close()
        archive_module.MIGRATIONS_DIR = self.real_migrations
        with self.assertRaises(ArchiveError):
            SQLiteArchive(self.path)


if __name__ == "__main__":
    unittest.main()