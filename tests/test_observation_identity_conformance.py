"""
ST-EVA Historical P/E productionization, gate §J: data-layer conformance.

`docs/ST-EVA-DATA-ADMISSION-RECONCILIATION.md` §J names this test as the one
minimal next engineering step, and it is deliberately a test rather than a
migration. The reconciliation read the writer and concluded that
`observation_content_hash()` does not cover `basis_json` or `raw_json`, so a
classification parked only in those blobs would be invisible to the fact's own
identity and would be absorbed on write. That was a reading of the code. This
file is the measurement of it, on one real fact, through the writer that
production actually uses.

Nothing here changes behaviour. Every assertion states what the archive does
today. If a future change to the preimage, the schema or the writer makes one
of these fail, that is the change announcing itself, and the test has to be
read again rather than deleted.

## The fact

One real furnished-quarter EPS fact from the existing frozen MSFT input set,
restated as values rather than read from disk. The whole repository suite has to
be runnable from what Git holds, and `research/` is ignored, so a test that
opened the frozen payload would error in a clean checkout.

    issuer          MSFT, CIK 789019
    concept         us-gaap:EarningsPerShareDiluted, unit USD/shares
    period          2011-07-01 .. 2011-09-30, 91 days, a quarter
    value           0.68
    accession       0001193125-13-455144, form 8-K, filed 2013-11-26
    frame           CY2011Q3

Provenance: `raw/eps_diluted.json` in
`research/experiments/aapl-historical-pe-poc/contract/msft_validation/`, the
companyconcept payload for `EarningsPerShareDiluted`. Of its 340 facts, 25 are
reported in an 8-K and 16 of those are quarter-length. That is Finding J.3 of
the reconciliation: MSFT tags quarter-length diluted EPS inside 8-K filings for
2011-2015, so deciding `evidence_class` by `form` would have called all sixteen
`filed`. This fact is the first of them.

The acceptance datetime for that accession is not in the frozen
`submissions.json` -- the 2013 filing predates the recent-filings window and the
older submission shards were not captured -- so availability resolves to the
filed-date fallback, `FILED_AS_OF_DATE`, at `PRECISION_DATE`. That is what the
existing path does with this input and it is asserted rather than worked around.

## What is measured

1. `observation_content_hash()` is unchanged when two observations differ only
   in `basis_json` and in `raw_json` classification keys, holding `accession`
   and `concept` constant, because `_accession_of` and `_concept_of` do read
   `raw`.
2. `record_observation` returns the first row's id for a second, differently
   classified insert, and the archive holds one row.
3. The second reading's classification is therefore lost. `EvidenceQuery`
   surfaces none of it.

One correction to how point 3 is easy to state. The archive does not strip a
classification: `basis` is passed through verbatim, so a classification written
on the *first* insert reaches the reader in full, all five values. What is
missing is any way to hold two readings of one fact, and any statement of which
reading won -- the surviving reading is decided by call order. Both halves are
asserted, so the file cannot be read as claiming the archive has no place for a
classification at all.
"""

import copy
import unittest
from dataclasses import replace

from archive import StoredDocument
from core_registry import CoreRegistry
from data_contract import METRIC_EPS_DILUTED
from evidence_model import source_fact_id
from evidence_query import EvidenceQuery
from registry_seed import seed
from sec_ingest import SEC_SOURCE, Ingestor
from sqlite_archive import SQLiteArchive, observation_content_hash

MSFT = "MSFT"
CIK = "789019"
CONCEPT = "EarningsPerShareDiluted"
TAXONOMY = "us-gaap"
UNIT = "USD/shares"
ACCESSION = "0001193125-13-455144"
PERIOD_START = "2011-07-01"
PERIOD_END = "2011-09-30"
VALUE = 0.68
FILED = "2013-11-26"
FRAME = "CY2011Q3"

# The acceptance datetime the 2013-11-26 8-K actually carried in SEC header
# data, frozen here for readability. Not used by the writer path because the
# frozen submissions payload predates the window this accession sits in.
HEADER_ACCEPTANCE_DATETIME = "2013-11-26T21:30:19.000Z"

CLASSIFICATION_FIELDS = (
    "evidence_class",
    "legal_status_note",
    "audit_status",
    "accounting_basis",
    "fiscal_year_end_month",
)

FURNISHED_CLASSIFICATION = {
    "evidence_class": "furnished",
    "legal_status_note": (
        "the furnishing 8-K states the exhibit shall not be deemed filed for"
        " purposes of Section 18"
    ),
    "audit_status": "unaudited",
    "accounting_basis": "as_traded",
    "fiscal_year_end_month": 6,
}
FURNISHED_ITEM_CODE = "2.02,9.01"

EXHIBIT_URI = (
    "https://www.sec.gov/Archives/edgar/data/789019/000119312513455144/dex991.htm"
)
EXHIBIT_SHA256 = (
    "sha256:9f9f9f9f9f9f9f9f9f9f9f9f9f9f9f9f9f9f9f9f9f9f9f9f9f9f9f9f9f9f9f9f"
)


def frozen_fact_entry() -> dict:
    """The raw XBRL entry, exactly as the frozen payload carries it."""
    return {
        "start": PERIOD_START,
        "end": PERIOD_END,
        "val": VALUE,
        "accn": ACCESSION,
        "fy": 2013,
        "fp": "FY",
        "frame": FRAME,
        "form": "8-K",
        "filed": FILED,
    }


def frozen_concept_payload() -> dict:
    """The concept-level metadata the frozen payload carries."""
    return {
        "cik": CIK,
        "taxonomy": TAXONOMY,
        "tag": CONCEPT,
        "label": "Earnings Per Share, Diluted",
        "description": (
            "The amount of net income (loss) for the period available to each"
            " share of common stock or common unit outstanding during the reporting period."
        ),
        "entityName": "MICROSOFT CORPORATION",
    }


def classify(observation, classification, item_code):
    """
    The same observation with a classification attached to its metadata.

    Only `basis` and `raw` move. The eleven fields the hash covers, and the
    accession and concept that `_accession_of` and `_concept_of` read out of
    `raw`, are untouched, so the two observations are one fact under two
    readings rather than two facts.
    """
    basis = dict(observation.basis or {})
    basis.update(classification)
    raw = copy.deepcopy(observation.raw or {})
    raw["items"] = item_code
    raw["legal_status_note"] = classification["legal_status_note"]
    return replace(observation, basis=basis, raw=raw)


class FurnishedQuarterEpsFacts(unittest.TestCase):
    def setUp(self):
        self.store = SQLiteArchive(":memory:")
        self.registry = CoreRegistry(self.store.connection)
        seed(self.registry)
        self.ingestor = Ingestor(self.store, object(), self.registry)
        self.entry = frozen_fact_entry()
        self.payload = frozen_concept_payload()
        self.mapping = next(
            mapping
            for mapping in self.registry.mappings_for_metric(METRIC_EPS_DILUTED)
            if mapping.concept_id == f"{TAXONOMY}:{CONCEPT}"
        )
        self.available_at, self.available_basis, self.available_precision = (
            self.ingestor._availability_for(self.entry, {})
        )
        self.observation = self.ingestor._observation(
            METRIC_EPS_DILUTED,
            TAXONOMY,
            CONCEPT,
            self.mapping,
            self.payload,
            self.entry,
            UNIT,
            PERIOD_START,
            PERIOD_END,
            self.available_at,
            self.available_basis,
            self.available_precision,
            ACCESSION,
        )
        self.classified = classify(
            self.observation,
            FURNISHED_CLASSIFICATION,
            FURNISHED_ITEM_CODE,
        )
        self.fact_id = source_fact_id(
            source_id=SEC_SOURCE,
            document_ref=ACCESSION,
            taxonomy=TAXONOMY,
            concept=CONCEPT,
            period_start=PERIOD_START,
            period_end=PERIOD_END,
            context=ACCESSION,
        )
        self.filing = self.ingestor._filing(
            self.fact_id,
            TAXONOMY,
            CONCEPT,
            ACCESSION,
            self.entry,
            PERIOD_START,
        )

    def tearDown(self):
        self.store.close()

    def write(self, observation, document_hashes=(), filing=None):
        return self.store.record_observation(
            asset=MSFT,
            observation=observation,
            availability_class="SOURCE_DECLARED",
            document_hashes=document_hashes,
            filing=filing if filing is not None else self.filing,
        )

    def row_count(self):
        return self.store.connection.execute(
            "SELECT COUNT(*) FROM observations"
        ).fetchone()[0]

    def stored(self, observation_id):
        return self.store.connection.execute(
            "SELECT * FROM observations WHERE observation_id = ?",
            (observation_id,),
        ).fetchone()

    def test_the_fact_is_a_furnished_quarter_and_the_path_reads_it_as_one(self):
        """
        Guards the fixture. If this fails the measurement below is about a
        different fact than the one named in the reconciliation.
        """
        self.assertEqual(0.68, self.observation.value)
        self.assertEqual(PERIOD_START, self.observation.period_start)
        self.assertEqual(PERIOD_END, self.observation.period_end)
        self.assertEqual("8-K", self.entry["form"])
        self.assertEqual(ACCESSION, self.entry["accn"])
        self.assertEqual("CY2011Q3", self.entry["frame"])
        self.assertEqual(91, _days(PERIOD_START, PERIOD_END))
        self.assertEqual(
            "FILED_AS_OF_DATE",
            self.observation.available_at_basis,
        )
        self.assertEqual(FILED, self.observation.available_at)

    def test_the_concept_is_mapped_to_the_metric_this_fact_is_written_under(self):
        self.assertEqual(METRIC_EPS_DILUTED, self.mapping.metric_id)
        self.assertEqual("EXACT", self.mapping.mapping_type)
        self.assertEqual(
            f"{TAXONOMY}:{CONCEPT}",
            self.filing.source_concept,
        )

    def test_the_hash_is_identical_under_a_changed_classification(self):
        """
        The preimage is twelve keys: `observation_id`, `metric`, `provider`,
        `concept`, `value`, `unit`, `currency`, `period_start`, `period_end`,
        `as_of`, `available_at`, `accession`. (`concept` and `accession` are
        resolved out of `raw`, so `raw` is read -- but only those two keys of
        it.) `basis` is not in the preimage at all, and no other key of `raw`
        is.
        """
        self.assertNotEqual(
            self.observation.basis,
            self.classified.basis,
        )
        self.assertNotEqual(
            self.observation.raw,
            self.classified.raw,
        )
        self.assertEqual(
            observation_content_hash(self.observation),
            observation_content_hash(self.classified),
        )

    def test_the_hash_still_moves_when_the_fact_itself_moves(self):
        """
        The control for the assertion above. Two observations sharing a hash is
        only a finding about classification if a changed fact still produces a
        changed hash.
        """
        self.assertNotEqual(
            observation_content_hash(self.observation),
            observation_content_hash(replace(self.observation, value=0.69)),
        )
        self.assertNotEqual(
            observation_content_hash(self.observation),
            observation_content_hash(
                replace(self.observation, available_at="2013-11-27")
            ),
        )

    def test_the_concept_and_accession_the_hash_reads_out_of_raw_are_held(self):
        """
        The one place `raw` does reach the preimage. Both readers -- the
        accession and the concept -- are unchanged by `classify`, so the hash
        equality above is not an artefact of the fact identity having moved.
        """
        from sqlite_archive import _accession_of, _concept_of

        self.assertEqual(
            _accession_of(self.observation),
            _accession_of(self.classified),
        )
        self.assertEqual(
            _concept_of(self.observation),
            _concept_of(self.classified),
        )
        self.assertEqual(ACCESSION, _accession_of(self.classified))
        self.assertEqual(
            f"{TAXONOMY}:{CONCEPT}",
            _concept_of(self.classified),
        )

    def test_the_second_write_returns_the_first_rows_id(self):
        first = self.write(self.observation)
        second = self.write(self.classified)
        self.assertEqual(first, second)

    def test_the_archive_holds_one_row_after_both_writes(self):
        self.write(self.observation)
        self.write(self.classified)
        self.assertEqual(1, self.row_count())

    def test_the_row_that_survives_is_the_first_one_written(self):
        """
        First-write-wins, with nothing recorded about the second reading.

        The order is what decides the answer and the archive states no order
        rule, so two ingestion runs over the same filings can leave the same
        fact classified differently and neither can tell from the row why. No
        error, no refusal, no marker: `record_observation` returned a row id and
        the caller has no signal that a reading was dropped.
        """
        first = self.write(self.observation)
        self.write(self.classified)
        row = self.stored(first)
        self.assertEqual("0.68", row["value_json"])
        self.assertNotIn("evidence_class", row["basis_json"])
        self.assertNotIn("items", row["raw_json"])

    def test_the_reversed_order_keeps_the_classified_row(self):
        """
        The same two readings, written the other way round. The archive keeps
        whichever arrived first either way, so the outcome is a function of
        call order rather than of anything either observation declares.
        """
        first = self.write(self.classified)
        second = self.write(self.observation)
        self.assertEqual(first, second)
        self.assertEqual(1, self.row_count())
        row = self.stored(first)
        self.assertIn("evidence_class", row["basis_json"])
        self.assertIn("items", row["raw_json"])

    def test_a_restatement_is_still_a_separate_fact(self):
        """
        The archive's deduplication is on fact identity, not on similarity. A
        genuine restatement of the same period in a different accession is a
        different fact and must not be absorbed -- otherwise the finding above
        would be reported as "the archive deduplicates", which is not what it
        does.
        """
        other_entry = dict(
            self.entry,
            accn="0001193125-13-310206",
            form="10-K",
        )
        available_at, basis, precision = self.ingestor._availability_for(
            other_entry,
            {},
        )
        restated = self.ingestor._observation(
            METRIC_EPS_DILUTED,
            TAXONOMY,
            CONCEPT,
            self.mapping,
            self.payload,
            other_entry,
            UNIT,
            PERIOD_START,
            PERIOD_END,
            available_at,
            basis,
            precision,
            other_entry["accn"],
        )
        self.assertNotEqual(
            observation_content_hash(self.observation),
            observation_content_hash(restated),
        )
        first = self.write(self.observation)
        second = self.write(
            restated,
            filing=self.ingestor._filing(
                source_fact_id(
                    source_id=SEC_SOURCE,
                    document_ref=other_entry["accn"],
                    taxonomy=TAXONOMY,
                    concept=CONCEPT,
                    period_start=PERIOD_START,
                    period_end=PERIOD_END,
                    context=other_entry["accn"],
                ),
                TAXONOMY,
                CONCEPT,
                other_entry["accn"],
                other_entry,
                PERIOD_START,
            ),
        )
        self.assertNotEqual(first, second)
        self.assertEqual(2, self.row_count())

    def test_the_second_readings_classification_is_absent_from_the_row(self):
        """
        The loss, stated on the row. The unclassified reading was written first,
        so the classified one is the reading that gets absorbed -- and the row
        ends up carrying no classification at all, rather than carrying the
        wrong one. A reader is not misled; a reader is left unable to tell.
        """
        row_id = self.write(self.observation)
        self.write(self.classified)
        row = self.stored(row_id)
        self.assertNotIn("evidence_class", row["basis_json"])
        self.assertNotIn("items", row["raw_json"])
        for field in CLASSIFICATION_FIELDS:
            self.assertNotIn(field, row["basis_json"], field)

    def test_the_query_surface_surfaces_none_of_the_five_fields(self):
        """
        The same loss at the read surface, for the order above.

        Worth being precise about what this does and does not show. It shows
        that the second reading's classification is invisible, not that the
        archive cannot represent one: `basis` is passed through verbatim, so a
        classification written on the *first* insert does reach the reader. See
        `test_the_first_readings_classification_is_readable`. What is missing
        is any way to hold two readings of one fact, and any writer-side
        guarantee about which reading wins.
        """
        row_id = self.write(self.observation)
        self.write(self.classified)
        package = EvidenceQuery(self.store.connection).get_observation(row_id)
        self.assertIsNotNone(package)
        flat = _flatten(package)
        for field in CLASSIFICATION_FIELDS:
            self.assertNotIn(field, flat, field)

    def test_the_first_readings_classification_is_readable(self):
        """
        The control for the assertion above, and the correction to a plausible
        misreading of it.

        `EvidenceQuery` echoes `basis_json` verbatim, so a classification
        present on the surviving row is fully readable -- including its five
        values. The writer does not strip it and the query surface does not
        filter it. The gap is that the second reading never reaches storage, so
        which classification a reader sees is decided by write order rather than
        by anything the archive states.
        """
        row_id = self.write(self.classified)
        self.write(self.observation)
        package = EvidenceQuery(self.store.connection).get_observation(row_id)
        basis = package["basis"]
        self.assertEqual("furnished", basis["evidence_class"])
        self.assertEqual("unaudited", basis["audit_status"])
        self.assertEqual("as_traded", basis["accounting_basis"])
        self.assertEqual(6, basis["fiscal_year_end_month"])
        self.assertIn("Section 18", basis["legal_status_note"])
        self.assertNotIn("items", _flatten(package))

    def test_the_query_surface_surfaces_the_fields_it_does_hold(self):
        """
        The other half of the same measurement. What a reader can see is the
        form, the accession and the concept -- which is exactly why `form` is
        the wrong discriminator for `evidence_class`.
        """
        row_id = self.write(self.observation)
        self.write(self.classified)
        source = EvidenceQuery(self.store.connection).get_observation(row_id)["source"]
        self.assertEqual("8-K", source["form"])
        self.assertEqual(ACCESSION, source["accession"])
        self.assertEqual(f"{TAXONOMY}:{CONCEPT}", source["concept"])
        flat = _flatten(source)
        self.assertNotIn("items", flat)
        self.assertNotIn("2.02", flat)

    def test_only_one_observation_is_readable_for_this_metric_and_period(self):
        self.write(self.observation)
        self.write(self.classified)
        found = EvidenceQuery(self.store.connection).query_observations(
            asset=MSFT,
            metric=METRIC_EPS_DILUTED,
            period_start=PERIOD_START,
            period_end=PERIOD_END,
        )
        self.assertEqual(1, len(found))


class DocumentsStillLinkOntoTheAbsorbedRow(unittest.TestCase):
    def setUp(self):
        self.store = SQLiteArchive(":memory:")
        self.registry = CoreRegistry(self.store.connection)
        seed(self.registry)
        self.ingestor = Ingestor(self.store, object(), self.registry)
        self.entry = frozen_fact_entry()
        self.payload = frozen_concept_payload()
        self.mapping = next(
            mapping
            for mapping in self.registry.mappings_for_metric(METRIC_EPS_DILUTED)
            if mapping.concept_id == f"{TAXONOMY}:{CONCEPT}"
        )
        available_at, basis, precision = self.ingestor._availability_for(
            self.entry,
            {},
        )
        self.observation = self.ingestor._observation(
            METRIC_EPS_DILUTED,
            TAXONOMY,
            CONCEPT,
            self.mapping,
            self.payload,
            self.entry,
            UNIT,
            PERIOD_START,
            PERIOD_END,
            available_at,
            basis,
            precision,
            ACCESSION,
        )
        self.classified = classify(
            self.observation,
            FURNISHED_CLASSIFICATION,
            FURNISHED_ITEM_CODE,
        )
        self.document_id = self.store.record_source_document(
            StoredDocument(
                content_hash=EXHIBIT_SHA256,
                uri=EXHIBIT_URI,
                http_status=200,
                media_type="text/html",
                byte_size=4096,
                fetched_at=FILED,
                first_seen_at=FILED,
                provider=SEC_SOURCE,
                document_type="SEC_DOCUMENT",
            )
        )

    def tearDown(self):
        self.store.close()

    def test_the_second_writes_document_is_linked_to_the_first_rows_row(self):
        first = self.store.record_observation(
            asset=MSFT,
            observation=self.observation,
            availability_class="SOURCE_DECLARED",
        )
        second = self.store.record_observation(
            asset=MSFT,
            observation=self.classified,
            availability_class="SOURCE_DECLARED",
            document_hashes=[EXHIBIT_SHA256],
        )
        self.assertEqual(first, second)
        self.assertEqual(
            [self.document_id],
            self.store.documents_for(first),
        )
        self.assertEqual([], self.store.dangling_document_references())

    def test_the_reader_follows_the_document_link_and_still_sees_no_class(self):
        """
        The absorbed write contributes its bytes and nothing else. The row ends
        up with the exhibit captured and linked, and with no classification
        from either reading beyond what the first insert happened to carry.
        """
        row_id = self.store.record_observation(
            asset=MSFT,
            observation=self.observation,
            availability_class="SOURCE_DECLARED",
        )
        self.store.record_observation(
            asset=MSFT,
            observation=self.classified,
            availability_class="SOURCE_DECLARED",
            document_hashes=[EXHIBIT_SHA256],
        )
        package = EvidenceQuery(self.store.connection).get_observation(row_id)
        documents = package["source"]["documents"]
        self.assertEqual(
            [EXHIBIT_SHA256],
            [d["content_hash"] for d in documents],
        )
        flat = _flatten(package)
        for field in CLASSIFICATION_FIELDS:
            self.assertNotIn(field, flat, field)


def _days(start: str, end: str) -> int:
    from datetime import date

    ya, ma, da = (int(part) for part in start.split("-"))
    yb, mb, db = (int(part) for part in end.split("-"))
    return (date(yb, mb, db) - date(ya, ma, da)).days


def _flatten(payload) -> set:
    """Every key and every string leaf in a query package, as one set."""
    found = set()
    stack = [payload]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            for key, value in node.items():
                found.add(key)
                stack.append(value)
        elif isinstance(node, (list, tuple)):
            stack.extend(node)
        elif isinstance(node, str):
            found.add(node)
    return found


if __name__ == "__main__":
    unittest.main()
