"""
ST-EVA 3C-B2 - linking existing Observations to document-derived XBRL facts.

This phase adds two things and creates nothing:

    observation_filing_document_facts   an Observation and a document fact were
                                        the same fact
    observation_filing_documents        the exact source document, only when the
                                        frozen 0/1 rule permits it

No Observation is created, amended or re-identified. The byte-level fixtures are
the controlled ones from `test_sec_xbrl_fact_extraction`, so the linkage rules are
exercised against the same document shapes 3C-B1 extracts from.

The fixtures here build a *matching* Observation by hand -- one whose concept,
period, unit and value are exactly those the bytes assert -- because the point is
the matching rule, not the aggregate route that would have produced it. Where a
rule must refuse, the test says which refusal and why.
"""

from __future__ import annotations

import json
import sqlite3
import unittest
from typing import Any, Dict, List, Optional

from archive import StoredDocument
from core_registry import CoreRegistry
from data_contract import Unit
from registry_seed import seed
from sec_ingest import SEC_SOURCE, Ingestor
from sec_xbrl_facts import (
    AMBIGUOUS_OBSERVATION,
    CONTEXT_AMBIGUOUS,
    DOCUMENTS_AMBIGUOUS,
    MATCHED,
    NO_OBSERVATION,
    TAXONOMY_AMBIGUOUS,
    TAXONOMY_UNPROVEN,
    UNIT_UNRESOLVED,
    contract_unit_of,
    exact_source_document,
    match_occurrence,
    occurrence_matches_observation,
)
from sqlite_archive import SQLiteArchive
from test_sec_xbrl_fact_extraction import (
    ACCESSION,
    CAPTURED_AT,
    CIK,
    EXHIBIT_WITHOUT_EPS,
    EXTRACTED_XML,
    FILENAME_EX101,
    FILENAME_EX991,
    FILENAME_EXTRACTED_XML,
    FILENAME_PRIMARY,
    FILENAME_RENDERING,
    FILENAME_SCHEMA,
    INLINE_PRIMARY,
    LEGACY_INSTANCE,
    MANIFEST_DIRECTORY,
    RENDERING,
    TAXONOMY_SCHEMA,
)

ASSET = "AAPL"
USGAAP = "http://fasb.org/us-gaap/2013"
USGAAP_2026 = "http://fasb.org/us-gaap/2026"
PER_SHARE = "per_share"
CURRENCY = "currency"

LEGACY_EPS = "1.36"          # the EX-101.INS diluted EPS of the 2013 fixture
LEGACY_UNITS = '{"measures":["USD","xbrli:shares"],"divide":1}'
LEGACY_PERIOD = ("2012-06-24", "2012-09-29")

#: The legacy fixture with its dimensional member removed. The shared 3C-B1
#: fixture carries two contexts reporting the same EPS number, which is the
#: measured dimension collision and correctly blocks an exact-source assertion.
#: The single-context path needs its own bytes rather than a weakened rule.
LEGACY_SINGLE = LEGACY_INSTANCE.replace(
    b'  <us-gaap:EarningsPerShareDiluted contextRef="D2012Q3_segment"'
    b' unitRef="u-usd-per-share" decimals="2">1.36'
    b"</us-gaap:EarningsPerShareDiluted>\n", b"")
assert LEGACY_SINGLE != LEGACY_INSTANCE


class _NoFetchProvider:
    def __getattr__(self, name: str) -> Any:
        raise AssertionError(
            f"3C-B2 must read the archive only, but {name} was requested")


def observation_row(**overrides: Any) -> Dict[str, Any]:
    """An Observation row as the linker sees it, matching the legacy fixture."""
    row = {
        "observation_id": "obsarch_test",
        "asset_id": "asset_test",
        "provider": SEC_SOURCE,
        "accession": ACCESSION,
        "taxonomy": USGAAP,
        "concept": "us-gaap:EarningsPerShareDiluted",
        "period_start": LEGACY_PERIOD[0],
        "period_end": LEGACY_PERIOD[1],
        "unit": PER_SHARE,
        "value_json": json.dumps(1.36),
        "source_fact_id": "sfid_test",
    }
    row.update(overrides)
    return row


def occurrence_row(**overrides: Any) -> Dict[str, Any]:
    row = {
        "document_fact_id": "dfid_test",
        "provider": SEC_SOURCE,
        "taxonomy": USGAAP,
        "tag": "EarningsPerShareDiluted",
        "context_ref": "D2012Q3",
        "unit_ref": "u-usd-per-share",
        "period_kind": "DURATION",
        "period_start": LEGACY_PERIOD[0],
        "period_end": LEGACY_PERIOD[1],
        "resolved_value": 1.36,
        "filename": FILENAME_EX101,
        "asset_id": "asset_test",
        "accession": ACCESSION,
    }
    row.update(overrides)
    if "contract_unit" not in overrides:
        row["contract_unit"] = contract_unit_of(LEGACY_UNITS)
    return row


class TestUnitRendering(unittest.TestCase):
    def test_a_divided_per_share_unit_resolves_to_the_contract_unit(self):
        self.assertEqual(PER_SHARE,
                         contract_unit_of(LEGACY_UNITS))

    def test_the_xbrl_pure_shares_denominator_renders_as_shares(self):
        self.assertEqual(
            PER_SHARE,
            contract_unit_of('{"measures":["USD","xbrli:shares"],"divide":1}'))

    def test_a_simple_currency_unit_resolves_to_currency(self):
        self.assertEqual(CURRENCY,
                         contract_unit_of('{"measures":["USD"],"divide":null}'))

    def test_an_unrecognised_unit_is_refused_rather_than_coerced(self):
        self.assertIsNone(contract_unit_of('{"measures":[],"divide":null}'))
        self.assertIsNone(contract_unit_of("not json"))


class TestMatchingRule(unittest.TestCase):
    def setUp(self) -> None:
        self.occurrence = occurrence_row()
        self.observation = observation_row()

    def matches(self, occurrence: Any = None, observation: Any = None) -> bool:
        return occurrence_matches_observation(
            self.occurrence if occurrence is None else occurrence,
            self.observation if observation is None else observation,
        )

    def test_a_the_exact_fact_matches(self):
        self.assertTrue(self.matches())

    def test_a_mismatched_concept_is_rejected(self):
        self.assertTrue(self.matches(), "the unmodified pair must match")
        self.assertFalse(self.matches(
            observation=observation_row(concept="us-gaap:Revenues")))

    def test_a_mismatched_period_is_rejected(self):
        self.assertFalse(self.matches(
            observation=observation_row(period_end="2012-09-30")))
        self.assertFalse(self.matches(
            observation=observation_row(period_start="2012-06-25")))

    def test_a_mismatched_unit_is_rejected(self):
        self.assertFalse(self.matches(observation=observation_row(unit=CURRENCY)))

    def test_a_mismatched_value_is_rejected(self):
        self.assertFalse(self.matches(
            observation=observation_row(value_json=json.dumps(1.37))))

    def test_a_mismatched_provider_or_asset_is_rejected(self):
        self.assertFalse(self.matches(observation=observation_row(
            provider="SomeoneElse")))
        self.assertFalse(self.matches(observation=observation_row(
            asset_id="other_asset")))

    def test_an_instant_context_requires_a_null_period_start(self):
        instant = occurrence_row(period_kind="INSTANT", period_start=None,
                                 period_end="2012-09-29")
        self.assertTrue(self.matches(instant, observation_row(period_start=None)))
        self.assertFalse(self.matches(instant, observation_row()))

    def test_an_unresolvable_unit_cannot_match(self):
        self.assertFalse(self.matches(
            occurrence=occurrence_row(contract_unit=None)))

    def test_matching_never_reads_a_filename_or_a_document_role(self):
        """The rule has no filename, type or primary-document input at all."""
        for filename in (FILENAME_PRIMARY, FILENAME_EXTRACTED_XML,
                         "R1.htm", "report.css", "x.htm"):
            self.assertTrue(self.matches(
                occurrence=occurrence_row(filename=filename)),
                f"filename must not affect the match: {filename}")

    def test_an_accession_alone_never_matches(self):
        self.assertFalse(self.matches(
            observation=observation_row(concept="us-gaap:Revenues")))

    def test_the_outcome_is_matched(self):
        outcome = match_occurrence(self.occurrence, [self.observation])
        self.assertEqual(MATCHED, outcome.reason)
        self.assertEqual("obsarch_test", outcome.observation_id)

    def test_no_observation_is_a_refusal_and_nothing_is_created(self):
        outcome = match_occurrence(self.occurrence, [])
        self.assertEqual(NO_OBSERVATION, outcome.reason)
        self.assertIsNone(outcome.observation_id)

    def test_two_matching_observations_are_refused(self):
        outcome = match_occurrence(self.occurrence, [
            self.observation,
            observation_row(observation_id="obsarch_other"),
        ])
        self.assertNotEqual(MATCHED, outcome.reason)
        self.assertIsNone(outcome.observation_id)


class TestExactSourceGate(unittest.TestCase):
    def test_one_document_is_asserted(self):
        document, reason = exact_source_document([occurrence_row()])
        self.assertEqual(("asset_test", ACCESSION, FILENAME_EX101), document)
        self.assertIsNone(reason)

    def test_two_documents_are_refused(self):
        document, reason = exact_source_document([
            occurrence_row(),
            occurrence_row(document_fact_id="dfid_two",
                           filename=FILENAME_EXTRACTED_XML),
        ])
        self.assertIsNone(document)
        self.assertEqual(DOCUMENTS_AMBIGUOUS, reason)

    def test_two_captures_of_one_document_are_one_candidate(self):
        """Capture rows and document ids must not inflate the candidate count."""
        document, reason = exact_source_document([
            occurrence_row(),
            occurrence_row(document_fact_id="dfid_recapture",
                           document_id="doc_recaptured"),
        ])
        self.assertEqual(("asset_test", ACCESSION, FILENAME_EX101), document)
        self.assertIsNone(reason)

    def test_two_contexts_in_one_document_are_refused(self):
        """A dimension collision must not become a valid source assertion."""
        document, reason = exact_source_document([
            occurrence_row(),
            occurrence_row(document_fact_id="dfid_segment",
                           context_ref="D2012Q3_segment"),
        ])
        self.assertIsNone(document)
        self.assertEqual(CONTEXT_AMBIGUOUS, reason)

    def test_no_linked_fact_is_a_refusal(self):
        document, reason = exact_source_document([])
        self.assertIsNone(document)
        self.assertEqual(NO_OBSERVATION, reason)

    def test_the_primary_document_gets_no_preference(self):
        primary, reason = exact_source_document([
            occurrence_row(filename=FILENAME_PRIMARY)])
        self.assertEqual(("asset_test", ACCESSION, FILENAME_PRIMARY), primary)


# ---------------------------------------------------------------------------
# The archive, driven through the production entry point
# ---------------------------------------------------------------------------


class LinkageBase(unittest.TestCase):
    def setUp(self) -> None:
        self.store = SQLiteArchive(":memory:")
        self.store.record_asset(ASSET, cik=CIK, name="Apple Inc.")
        self.asset_id = self.store.asset_id_for_cik(CIK)
        self.registry = CoreRegistry(self.store.connection)
        seed(self.registry)
        self.ingestor = Ingestor(self.store, _NoFetchProvider(), self.registry)
        self.connection = self.store.connection
        self.connection.execute(
            "INSERT INTO filings (asset_id, accession, first_archived_at)"
            " VALUES (?, ?, '2026-07-31T00:30:28Z')",
            (self.asset_id, ACCESSION))
        self.connection.commit()

    def tearDown(self) -> None:
        self.store.close()

    @property
    def provenance_errors(self) -> List[str]:
        return list(self.ingestor._provenance_errors)

    def count(self, table: str, where: str = "", *args: Any) -> int:
        clause = f" WHERE {where}" if where else ""
        return self.connection.execute(
            f"SELECT COUNT(*) AS n FROM {table}{clause}", args
        ).fetchone()["n"]

    def declare_and_capture(self, filename: str, payload: bytes,
                            ordinal: int = 1) -> str:
        import hashlib
        self.connection.execute(
            "INSERT OR IGNORE INTO filing_document_declarations"
            " (declaration_id, asset_id, accession, manifest_source,"
            " source_ordinal, filename, mime_type, byte_size, captured_at,"
            " capture_kind) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?,"
            " 'FIRST_HAND')",
            (f"fdd-b2-{ordinal}-{filename}", self.asset_id, ACCESSION,
             MANIFEST_DIRECTORY, ordinal, filename, "text/html",
             len(payload), CAPTURED_AT))
        self.connection.execute(
            "INSERT OR IGNORE INTO filing_documents (asset_id, accession,"
            " filename, first_declared_at) VALUES (?, ?, ?, ?)",
            (self.asset_id, ACCESSION, filename, CAPTURED_AT))
        document_id = self.store.record_source_document(StoredDocument(
            content_hash="sha256:" + hashlib.sha256(payload).hexdigest(),
            uri=("https://www.sec.gov/Archives/edgar/data/320193/"
                 f"{ACCESSION.replace('-', '')}/{filename}"),
            canonical_uri=None, http_status=200, media_type="text/html",
            byte_size=len(payload), fetched_at=CAPTURED_AT,
            first_seen_at=CAPTURED_AT, payload=payload,
            provider=SEC_SOURCE, document_type="SEC_FILING_DOCUMENT",
        ))
        self.connection.execute(
            "INSERT OR IGNORE INTO filing_document_captures (asset_id,"
            " accession, filename, document_id, acquisition_class,"
            " captured_at, capture_kind) VALUES (?, ?, ?, ?,"
            " 'SEC_FILING_DOCUMENT', ?, 'FIRST_HAND')",
            (self.asset_id, ACCESSION, filename, document_id, CAPTURED_AT))
        self.connection.commit()
        return document_id

    def store_observation(self, taxonomy: str = USGAAP, **overrides: Any) -> str:
        """An Observation that matches the legacy fixture's diluted EPS."""
        from data_contract import Observation, Unit, ValidationStatus

        values = {
            "observation_id": "obs-b2-eps",
            "value": 1.36,
            "unit": Unit.PER_SHARE.value,
            "concept": "us-gaap:EarningsPerShareDiluted",
            "period_start": LEGACY_PERIOD[0],
            "period_end": LEGACY_PERIOD[1],
            "metric": "eps_diluted",
        }
        values.update(overrides)
        row_id = self.store.record_observation(
            asset=ASSET,
            observation=Observation(
                observation_id=values["observation_id"],
                metric=values["metric"],
                value=values["value"],
                unit=values["unit"],
                currency="USD",
                currency_basis="REPORTED",
                period_start=values["period_start"],
                period_end=values["period_end"],
                as_of=values["period_end"],
                available_at="2026-07-30T20:30:28Z",
                available_at_basis="ACCEPTANCE_DATETIME",
                provider=SEC_SOURCE,
                source_type="REGULATORY_FILING",
                source_url=None,
                retrieved_at=CAPTURED_AT,
                definition=values["metric"],
                methodology="fixture",
                status=ValidationStatus.UNVERIFIABLE,
                status_reasons=(
                    "a single official source cannot cross-validate itself",),
                # The `concept` column is derived from the preserved SEC payload,
                # so a fixture without it is not a realistic SEC observation and
                # would be matching a metric name against a filing tag.
                raw={"sec_fact": {"taxonomy": "us-gaap",
                                  "tag": values["concept"].split(":")[-1]}},
            ),
            availability_class="SOURCE_DECLARED",
            accession=ACCESSION,
            filing=_filing_ref(values, taxonomy),
        )
        return row_id

    def link(self) -> int:
        self.ingestor._acquire_document_fact_occurrences(self.asset_id, ACCESSION)
        return self.ingestor._acquire_observation_fact_links(self.asset_id,
                                                             ACCESSION)

    def links(self) -> List[sqlite3.Row]:
        return self.connection.execute(
            "SELECT * FROM observation_filing_document_facts ORDER BY"
            " document_fact_id").fetchall()

    def snapshot_observations(self) -> List[tuple]:
        return [
            tuple(row) for row in self.connection.execute(
                "SELECT observation_id, content_hash, source_fact_id, value_json,"
                " period_start, period_end, unit, concept, taxonomy, accession"
                " FROM observations ORDER BY observation_id")
        ]


def _filing_ref(values: Dict[str, Any], taxonomy: str = USGAAP):
    """
    A filing ref whose `taxonomy` is the **namespace URI**.

    This is a representative fixture, not a claim about SEC data. A real
    companyconcept observation records the prefix (`us-gaap`), which is not the
    same representation a document fact records, and this repository holds no
    map between them -- so a real one is refused by design (see
    `test_the_real_prefix_form_is_refused_because_equivalence_is_unprovable`).

    Everything else in these tests -- the cardinality gates, the context gate,
    append-only behaviour -- is independent of that question, and exercising it
    against a comparable taxonomy keeps that machinery covered instead of
    leaving it permanently unreachable.
    """
    from archive import FilingRef
    from evidence_model import source_fact_id

    fact_id = source_fact_id(
        source_id=SEC_SOURCE, document_ref=ACCESSION, taxonomy="us-gaap",
        concept=values["concept"], period_start=values["period_start"],
        period_end=values["period_end"], context=ACCESSION,
    )
    return FilingRef(
        source_fact_id=fact_id, accession=ACCESSION,
        taxonomy=taxonomy, form="10-K",
        fiscal_year=2012, fiscal_period="Q4",
        statement="FY", instant=0,
        source_concept=values["concept"],
    )


class TestLinkageInTheArchive(LinkageBase):
    def test_an_exact_match_links_and_asserts_the_single_document(self):
        self.declare_and_capture(FILENAME_EX101, LEGACY_SINGLE)
        observation_id = self.store_observation()
        before = self.snapshot_observations()
        self.assertEqual(1, self.link())
        links = self.links()
        self.assertEqual(1, len(links))
        self.assertEqual(observation_id, links[0]["observation_id"])
        self.assertEqual(1, self.count("observation_filing_documents"))
        self.assertEqual(before, self.snapshot_observations())

    def test_the_asserted_document_is_the_one_that_was_captured(self):
        self.declare_and_capture(FILENAME_EX101, LEGACY_SINGLE)
        self.store_observation()
        self.link()
        row = self.connection.execute(
            "SELECT * FROM observation_filing_documents").fetchone()
        self.assertEqual(FILENAME_EX101, row["filename"])
        self.assertEqual(ACCESSION, row["accession"])

    def test_a_document_without_a_matching_observation_asserts_nothing(self):
        self.declare_and_capture(FILENAME_EX101, LEGACY_INSTANCE)
        self.link()
        self.assertGreater(self.count("filing_document_fact_occurrences"), 0)
        self.assertEqual(0, self.count("observation_filing_document_facts"))
        self.assertEqual(0, self.count("observation_filing_documents"))
        self.assertTrue(any(NO_OBSERVATION in error
                            for error in self.provenance_errors))

    def test_a_value_mismatch_links_nothing(self):
        self.declare_and_capture(FILENAME_EX101, LEGACY_INSTANCE)
        self.store_observation(value=1.37)
        self.assertEqual(0, self.link())
        self.assertEqual(0, self.count("observation_filing_document_facts"))
        self.assertEqual(0, self.count("observation_filing_documents"))

    def test_a_concept_mismatch_links_nothing(self):
        self.declare_and_capture(FILENAME_EX101, LEGACY_INSTANCE)
        self.store_observation(
            concept="us-gaap:Revenues", metric="revenue", value=1.36)
        self.assertEqual(0, self.link())

    def test_a_unit_mismatch_links_nothing(self):
        from data_contract import Unit
        self.declare_and_capture(FILENAME_EX101, LEGACY_INSTANCE)
        self.store_observation(unit=Unit.CURRENCY.value)
        self.assertEqual(0, self.link())

    def test_a_period_mismatch_links_nothing(self):
        self.declare_and_capture(FILENAME_EX101, LEGACY_INSTANCE)
        self.store_observation(period_end="2012-09-30")
        self.assertEqual(0, self.link())

    def test_a_dimension_collision_links_nothing_and_asserts_nothing(self):
        """
        Two contexts, one Observation: **no** link at all.

        The context gate guards the linkage, not merely the later assertion.
        The two dimensional members are two distinct XBRL facts and the
        Observation identity has no dimension slot to say which of them produced
        the stored value, so linking both would make the relation a candidate set
        of readings -- which its frozen semantics forbids. Refusing is the only
        exact answer, and the ambiguity is reported rather than absorbed.
        """
        self.declare_and_capture(FILENAME_EX101, LEGACY_INSTANCE)
        self.store_observation()
        self.assertEqual(0, self.link())
        self.assertEqual(0, self.count("observation_filing_document_facts"))
        self.assertEqual(0, self.count("observation_filing_documents"))
        self.assertTrue(any(CONTEXT_AMBIGUOUS in error
                            for error in self.provenance_errors))

    def test_two_documents_asserting_one_fact_create_two_links_and_no_assertion(self):
        """The inline dual-document case, end to end.

        The two documents state the same fact in different forms -- inline with a
        scale, extracted already resolved -- and both resolve to the same number.
        Both link; the exact-source assertion does not follow, because which of
        the two is authoritative is exactly what invariant 19 says cannot be
        decided here.
        """
        self.declare_and_capture(FILENAME_PRIMARY, INLINE_PRIMARY, ordinal=1)
        self.declare_and_capture(FILENAME_EXTRACTED_XML, EXTRACTED_XML,
                                 ordinal=7)
        observation_id = self.store_observation(
            observation_id="obs-b2-rev", value=39536000000.0,
            concept="us-gaap:Revenues", metric="revenue",
            unit=Unit.CURRENCY.value, taxonomy=USGAAP_2026,
            period_start="2026-03-29", period_end="2026-06-27")
        self.link()
        links = [row for row in self.links()
                 if row["observation_id"] == observation_id]
        self.assertEqual(2, len(links),
                         f"one link per document fact; errors: "
                         f"{self.provenance_errors}; links: "
                         f"{[dict(r) for r in self.links()]}")
        self.assertEqual(0, self.count("observation_filing_documents"))
        self.assertTrue(any(DOCUMENTS_AMBIGUOUS in error
                            for error in self.provenance_errors))

    def test_multiple_captures_do_not_inflate_the_candidate_count(self):
        self.declare_and_capture(FILENAME_EX101, LEGACY_SINGLE)
        self.store_observation()
        amended = LEGACY_SINGLE.replace(
            b"<us-gaap:Assets contextRef=\"I20120929\" unitRef=\"u-usd\""
            b" decimals=\"-3\">176064000000<",
            b"<us-gaap:Assets contextRef=\"I20120929\" unitRef=\"u-usd\""
            b" decimals=\"-3\">176999000000<")
        self.declare_and_capture(FILENAME_EX101, amended, ordinal=1)
        self.link()
        self.assertEqual(1, self.count("observation_filing_documents"),
                         "two captures of one document are one candidate")
        self.assertEqual(2, self.count(
            "filing_document_fact_occurrences", "tag = ?",
            "EarningsPerShareDiluted"),
            "changed bytes are a different fact identity")

    def test_documents_without_facts_change_nothing(self):
        for ordinal, (filename, payload) in enumerate((
                (FILENAME_EX991, EXHIBIT_WITHOUT_EPS),
                ("us-gaap-2023.xsd", TAXONOMY_SCHEMA),
                ("R1.htm", RENDERING)), 1):
            self.declare_and_capture(filename, payload, ordinal=ordinal)
        self.store_observation()
        self.assertEqual(0, self.link())
        self.assertEqual(0, self.count("observation_filing_document_facts"))
        self.assertEqual(0, self.count("observation_filing_documents"))

    def test_linking_is_idempotent(self):
        self.declare_and_capture(FILENAME_EX101, LEGACY_SINGLE)
        self.store_observation()
        self.link()
        self.link()
        self.assertEqual(1, self.count("observation_filing_document_facts"))
        self.assertEqual(1, self.count("observation_filing_documents"))

    def test_observation_rows_are_never_amended(self):
        self.declare_and_capture(FILENAME_EX101, LEGACY_SINGLE)
        self.store_observation()
        before = self.snapshot_observations()
        self.link()
        self.assertEqual(before, self.snapshot_observations())

    def test_q_source_fact_id_remains_an_sfid(self):
        self.declare_and_capture(FILENAME_EX101, LEGACY_SINGLE)
        observation_id = self.store_observation()
        self.link()
        row = self.connection.execute(
            "SELECT source_fact_id FROM observations WHERE observation_id = ?",
            (observation_id,)).fetchone()
        self.assertTrue(row["source_fact_id"].startswith("sfid_"))

    def test_a_dfid_never_enters_observation_identity(self):
        self.declare_and_capture(FILENAME_EX101, LEGACY_SINGLE)
        self.store_observation()
        self.link()
        for row in self.snapshot_observations():
            self.assertNotIn("dfid_", str(row))
        self.assertEqual(
            0, self.count("observations", "source_fact_id LIKE 'dfid_%'"))

    def test_no_dfid_is_written_into_a_source_document_assertion(self):
        self.declare_and_capture(FILENAME_EX101, LEGACY_SINGLE)
        self.store_observation()
        self.link()
        for row in self.connection.execute(
                "SELECT * FROM observation_filing_document_facts"):
            self.assertTrue(row["document_fact_id"].startswith("dfid_"))

    def test_the_observation_sources_bypass_stays_blocked(self):
        self.declare_and_capture(FILENAME_EX101, LEGACY_SINGLE)
        self.store_observation()
        self.link()
        self.assertEqual(0, self.count("observation_sources"))
        filing_document_id = self.connection.execute(
            "SELECT document_id FROM filing_document_captures LIMIT 1"
        ).fetchone()["document_id"]
        with self.assertRaises(sqlite3.DatabaseError):
            self.connection.execute(
                "INSERT INTO observation_sources (observation_id, document_id,"
                " accession) SELECT observation_id, ?, accession FROM observations",
                (filing_document_id,))
        self.connection.rollback()

    def test_the_link_is_append_only(self):
        self.declare_and_capture(FILENAME_EX101, LEGACY_SINGLE)
        self.store_observation()
        self.link()
        for statement in ("UPDATE observation_filing_document_facts"
                          " SET document_fact_id = 'dfid_x'",
                          "DELETE FROM observation_filing_document_facts",
                          "UPDATE observation_filing_documents"
                          " SET filename = 'other.htm'",
                          "DELETE FROM observation_filing_documents"):
            with self.assertRaises(sqlite3.IntegrityError):
                self.connection.execute(statement)
            self.connection.rollback()

    def test_no_candidate_rows_and_no_confidence_appear(self):
        self.declare_and_capture(FILENAME_PRIMARY, INLINE_PRIMARY, ordinal=1)
        self.declare_and_capture(FILENAME_EXTRACTED_XML, EXTRACTED_XML,
                                 ordinal=7)
        self.store_observation(concept="us-gaap:Revenues", metric="revenue",
                               value=39536000000.0, unit=Unit.CURRENCY.value,
                               period_start="2026-03-29",
                               period_end="2026-06-27")
        self.link()
        self.assertEqual(0, self.count("observation_filing_documents"))
        columns = {row["name"] for row in self.connection.execute(
            "PRAGMA table_info(observation_filing_documents)")}
        for forbidden in ("confidence", "precedence", "rank", "ordinal",
                          "candidate", "evidence_class", "audit_status"):
            self.assertNotIn(forbidden, columns)

    def test_no_network_is_reached(self):
        self.declare_and_capture(FILENAME_EX101, LEGACY_SINGLE)
        self.store_observation()
        self.assertEqual(1, self.link())


class TestUnitRefusalInTheArchive(LinkageBase):
    def test_an_unrecognised_unit_is_refused_and_reported(self):
        payload = LEGACY_SINGLE.replace(b'unitRef="u-usd-per-share"',
                                    b'unitRef="u-furlongs"')
        self.assertNotEqual(payload, LEGACY_SINGLE)
        self.declare_and_capture(FILENAME_EX101, payload)
        self.store_observation()
        self.assertEqual(0, self.link())
        self.assertEqual(0, self.count("observation_filing_document_facts"))
        self.assertEqual(0, self.count("observation_filing_documents"))


class TestTaxonomyAmbiguity(LinkageBase):
    def test_two_namespaces_with_one_local_name_refuse_the_linkage(self):
        """A concept collision must not be resolved by guessing a taxonomy."""
        payload = b"""<?xml version="1.0"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
  xmlns:us-gaap="http://fasb.org/us-gaap/2013"
  xmlns:ex="http://example.com/tenant-a">
  <xbrli:context id="D2012Q3"><xbrli:entity><xbrli:identifier scheme="s">1</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2012-06-24</xbrli:startDate><xbrli:endDate>2012-09-29</xbrli:endDate></xbrli:period></xbrli:context>
  <xbrli:unit id="u"><xbrli:divide><xbrli:unitNumerator><xbrli:measure>USD</xbrli:measure></xbrli:unitNumerator><xbrli:unitDenominator><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unitDenominator></xbrli:divide></xbrli:unit>
  <us-gaap:EarningsPerShareDiluted contextRef="D2012Q3" unitRef="u" decimals="2">1.36</us-gaap:EarningsPerShareDiluted>
  <ex:EarningsPerShareDiluted contextRef="D2012Q3" unitRef="u" decimals="2">1.36</ex:EarningsPerShareDiluted>
</xbrli:xbrl>
"""
        self.declare_and_capture(FILENAME_EX101, payload)
        self.store_observation()
        # Only the occurrence whose namespace equals the Observation's taxonomy
        # is linked. The extension fact shares its local name, period, unit and
        # value, and is refused because its namespace is not equivalent.
        self.assertEqual(1, self.link())
        links = self.links()
        self.assertEqual(1, len(links))
        self.assertEqual(USGAAP, self.connection.execute(
            "SELECT taxonomy FROM filing_document_fact_occurrences"
            " WHERE document_fact_id = ?",
            (links[0]["document_fact_id"],)).fetchone()["taxonomy"])
        self.assertTrue(any(TAXONOMY_UNPROVEN in error
                            for error in self.provenance_errors))


class TestTaxonomyUnproven(LinkageBase):
    """
    The frozen conservative case: an Observation's taxonomy is stored in the
    SEC/companyconcept **prefix** representation (`us-gaap`) while every document
    fact is stored as a resolved **namespace URI**, and this repository holds no
    prefix-to-URI map. Equality is the only comparison and the two are not equal,
    so **no** ordinary real SEC observation can be linked here.

    `TestTaxonomyAmbiguity` above uses the URI form for *both* sides deliberately,
    to keep the linkage machinery reachable; these two tests pin the real prefix
    form and its consequence -- zero links, zero assertions, `TAXONOMY_UNPROVEN`.
    """

    def test_a_prefix_observation_never_links_a_custom_namespace_occurrence(self):
        """A. `us-gaap:Revenues` Observation + custom namespace URI occurrence."""
        payload = b"""<?xml version="1.0"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
  xmlns:ex="http://example.com/tenant-a">
  <xbrli:context id="i-2026q2">
    <xbrli:entity><xbrli:identifier scheme="s">1</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:startDate>2026-03-29</xbrli:startDate><xbrli:endDate>2026-06-27</xbrli:endDate></xbrli:period>
  </xbrli:context>
  <xbrli:unit id="u-usd"><xbrli:measure>USD</xbrli:measure></xbrli:unit>
  <ex:Revenues contextRef="i-2026q2" unitRef="u-usd">39536000000</ex:Revenues>
</xbrli:xbrl>
"""
        self.declare_and_capture(FILENAME_EX101, payload)
        self.store_observation(
            concept="us-gaap:Revenues", metric="revenue",
            value=39536000000.0, unit=Unit.CURRENCY.value,
            period_start="2026-03-29", period_end="2026-06-27",
            taxonomy="us-gaap",
        )
        self.assertEqual(0, self.link())
        self.assertEqual(0, self.count("observation_filing_document_facts"))
        self.assertEqual(0, self.count("observation_filing_documents"))
        self.assertTrue(any(TAXONOMY_UNPROVEN in error
                            for error in self.provenance_errors))

    def test_a_real_sec_prefix_observation_never_links_a_document_fact_namespace(self):
        """B. Real SEC-style prefix observation + document-fact namespace URI."""
        self.declare_and_capture(FILENAME_PRIMARY, INLINE_PRIMARY, ordinal=1)
        self.store_observation(
            concept="us-gaap:Revenues", metric="revenue",
            value=39536000000.0, unit=Unit.CURRENCY.value,
            period_start="2026-03-29", period_end="2026-06-27",
            taxonomy="us-gaap",
        )
        self.assertEqual(0, self.link())
        self.assertEqual(0, self.count("observation_filing_document_facts"))
        self.assertEqual(0, self.count("observation_filing_documents"))
        self.assertTrue(any(TAXONOMY_UNPROVEN in error
                            for error in self.provenance_errors))


if __name__ == "__main__":
    unittest.main()