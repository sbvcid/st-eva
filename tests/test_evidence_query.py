"""
ST-EVA 2.5 - Query Surface tests.

The surface is read-only and the database is the record, so most of these
assert two things a naive read layer gets wrong:

    a value is never returned without the state that says whether it is
        reported, absent, inapplicable, conflicting or stale
    a figure is never returned without a path to the document that contains it

The 2.4.3 semantics are asserted explicitly, because a query surface that
returns `None` for four different meanings has thrown away the distinction the
whole project exists to preserve.
"""

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from archive import StoredDocument
from evidence_model import (
    CONFLICTING,
    EVIDENCE_STATES,
    NEGATIVE_STATES,
    NOT_APPLICABLE,
    SOURCE_DID_NOT_REPORT,
    SOURCE_REPORTED,
    STALE,
    UNAVAILABLE,
    EvidenceState,
    EvidenceStateError,
)
from evidence_query import (
    AMBIGUITY_CROSS_PROVIDER,
    AMBIGUITY_DIMENSION,
    AMBIGUITY_MULTIPLE_CONCEPTS,
    AMBIGUITY_MULTIPLE_FILINGS,
    AMBIGUITY_MULTIPLE_OBSERVATIONS,
    AMBIGUITY_REASONS,
    ORDER_ASC,
    ORDER_AVAILABLE,
    ORDER_DESC,
    EvidenceQuery,
    QueryError,
    UnknownMetricError,
    classify_ambiguity,
)
from sqlite_archive import SQLiteArchive

REPO = Path(__file__).resolve().parent.parent

AAPL = "AAPL"
ACME = "BANKCO"
FILING_ACCESSION = "0000320193-24-000069"
DOC_HASH = "sha256:" + "ab" * 32
OTHER_DOC_HASH = "sha256:" + "cd" * 32


def add_observation(
    connection,
    contract_id,
    metric,
    value_json,
    *,
    asset="asset_aapl",
    unit="currency",
    currency="USD",
    period_start="2023-12-31",
    period_end="2024-03-30",
    available_at="2024-05-02T22:04:25.000Z",
    available_basis="ACCEPTANCE_DATETIME",
    availability_class="SOURCE_DECLARED",
    replay_eligible="2024-05-02T22:04:25.000Z",
    first_archived="2024-05-03T00:00:00+00:00",
    provider="SecEdgar",
    source_type="REGULATORY_FILING",
    status="UNVERIFIABLE",
    concept="us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
    source_concept_ref="same-as-concept",
    accession=FILING_ACCESSION,
    form="10-Q",
    taxonomy="us-gaap",
    statement="INCOME",
    source_fact=None,
    raw=None,
    document="doc_filing",
):
    """
    One observation, built from a column tuple.

    Module level rather than a closure inside `build_archive`, because a test that
    needs a case the shared fixture does not contain should add the case to the
    same fixture rather than grow a second copy of a forty-column insert. A
    second copy is a second thing to keep in step, and this one has a
    `source_concept_ref` that the ambiguity classification depends on.
    """
    # Each fact in the fixture is a distinct raw fact, so each gets its
    # own source_fact_id. Reusing one would trip the unique index, which
    # is exactly the deduplication rule under test.
    fact_id = source_fact or ("sfid_" + contract_id)
    payload = {
        "sec_fact": {
            "taxonomy": taxonomy,
            "tag": concept.split(":")[-1] if concept else None,
            "accession": accession,
            "form": form,
            "fy": 2024,
            "fp": "Q2",
        }
    }
    if raw is not None:
        payload = raw
    # Built from a column tuple rather than counted: a hand-written
    # placeholder list is a silent way to shift every value by one.
    columns = (
        "observation_id", "contract_id", "asset_id", "lineage_id", "metric",
        "provider", "source_type", "source_url", "concept", "value_json",
        "unit", "currency", "currency_basis", "period_start", "period_end",
        "as_of", "available_at", "available_at_basis",
        "availability_class", "retrieved_at", "first_archived_at",
        "replay_eligible_from", "definition", "methodology", "status",
        "status_reasons_json", "inputs_json", "observation_count",
        "raw_json", "content_hash", "basis_json", "taxonomy", "accession",
        "form", "fiscal_year", "fiscal_period", "statement", "instant",
        "source_fact_id", "source_concept_ref",
    )
    values = {
        "observation_id": "obs_" + contract_id,
        "contract_id": contract_id,
        "asset_id": asset,
        "lineage_id": "line_1",
        "metric": metric,
        "provider": provider,
        "source_type": source_type,
        "source_url": None,
        "concept": concept,
        "value_json": value_json,
        "unit": unit,
        "currency": currency,
        "currency_basis": "REPORTED" if currency else "NOT_APPLICABLE",
        "period_start": period_start,
        "period_end": period_end,
        "as_of": period_end,
        "available_at": available_at,
        "available_at_basis": available_basis,
        "availability_class": availability_class,
        "retrieved_at": "2024-05-03T00:00:00+00:00",
        "first_archived_at": first_archived,
        "replay_eligible_from": replay_eligible,
        "definition": "def",
        "methodology": "m",
        "status": status,
        "status_reasons_json": "[]",
        "inputs_json": "[]",
        "observation_count": None,
        "raw_json": json.dumps(payload),
        "content_hash": "h_" + contract_id,
        "basis_json": json.dumps(
            {
                "reporting_framework": taxonomy,
                "statement": statement,
                "source_declared": True,
            }
        ),
        "taxonomy": taxonomy,
        "accession": accession,
        "form": form,
        "fiscal_year": 2024,
        "fiscal_period": "Q2",
        "statement": statement,
        "instant": 0 if period_start else 1,
        "source_fact_id": fact_id,
        # The registry-resolved source concept, which is not the same thing as
        # the filed tag and is NULL whenever nothing was mapped. A vendor figure
        # gets no concept at all rather than a borrowed one, and the ambiguity
        # classification relies on that distinction.
        "source_concept_ref": (
            concept if source_concept_ref == "same-as-concept"
            else source_concept_ref
        ),
    }
    connection.execute(
        "INSERT INTO observations ({}) VALUES ({})".format(
            ", ".join(columns),
            ", ".join("?" for _ in columns),
        ),
        tuple(values[column] for column in columns),
    )
    if document:
        connection.execute(
            "INSERT INTO observation_sources (observation_id, document_id,"
            " accession) VALUES (?, ?, ?)",
            ("obs_" + contract_id, document, accession),
        )
    return "obs_" + contract_id


def build_archive() -> SQLiteArchive:
    """
    A small archive with the cases that matter.

    Synthetic rather than live so the semantics are pinned, and shaped so each
    state appears: a reported quarterly series, an undated vendor value, a
    bank with no operating income, a stale filing, and two sources that
    disagree about a share count.
    """
    store = SQLiteArchive(":memory:")
    connection = store.connection

    aapl = store.record_asset(AAPL, name="Apple Inc.", cik="0000320193")
    bank = store.record_asset(ACME, name="Bank Co.")
    connection.execute(
        "INSERT INTO observation_lineage (lineage_id, asset_id, metric, concept,"
        " period_start, period_end, created_at, note)"
        " VALUES ('line_1', ?, 'revenue',"
        " 'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',"
        " NULL, NULL, '2024-05-03T00:00:00+00:00', 'fixture')",
        (aapl,),
    )

    store.record_source(
        "SecEdgar", "REGULATORY_FILING", base_url="https://data.sec.gov"
    )
    store.record_source("YahooFinance", "API_LIVE")
    connection.execute(
        "UPDATE sources SET redistribution_tier = 'A',"
        " fair_access_policy = 'declared User-Agent, <=10 req/s',"
        " contact_identity = 'declared User-Agent' WHERE provider = 'SecEdgar'"
    )
    connection.execute(
        "UPDATE sources SET redistribution_tier = 'B' WHERE provider ="
        " 'YahooFinance'"
    )

    connection.execute(
        "INSERT INTO source_documents (document_id, content_hash, uri,"
        " canonical_uri, http_status, media_type, byte_size, fetched_at,"
        " first_seen_at, provider, document_type, content, content_encoding)"
        " VALUES ('doc_filing', ?, ?, ?, 200, 'application/json', 1024,"
        " '2024-05-02T22:04:25.000Z', '2024-05-02T22:05:00.000Z', 'SecEdgar',"
        " 'SEC_COMPANY_CONCEPT', ?, 'gzip')",
        (DOC_HASH, "https://data.sec.gov/x.json", "https://data.sec.gov/x.json",
         b"gzip-bytes"),
    )
    connection.execute(
        "INSERT INTO source_documents (document_id, content_hash, uri,"
        " canonical_uri, http_status, media_type, byte_size, fetched_at,"
        " first_seen_at, provider, document_type, content, content_encoding)"
        " VALUES ('doc_vendor', ?, ?, ?, 200, 'application/json', 512,"
        " '2024-05-02T22:06:00.000Z', '2024-05-02T22:06:00.000Z',"
        " 'YahooFinance', 'VENDOR_QUOTE', ?, 'gzip')",
        (OTHER_DOC_HASH, "https://vendor/x.json", "https://vendor/x.json",
         b"vendor-bytes"),
    )

    def observation(contract_id, metric, value_json, **kwargs):
        kwargs.setdefault("asset", aapl)
        return add_observation(
            connection, contract_id, metric, value_json, **kwargs
        )

    # A reported quarterly revenue series, one declared filing each.
    for index, (period, value) in enumerate(
        (
            ("2023-12-31", "90356000000.0"),
            ("2024-03-30", "90753000000.0"),
            ("2023-09-30", "89498000000.0"),
        )
    ):
        observation(
            f"cmp-revenue-sec-q-{period}-{index}",
            "revenue",
            value,
            period_start="2023-09-30",
            period_end=period,
        )

    # A vendor figure with no stated publication time. The 2.4.2 rule: its
    # recency cannot be established, so it is not knowable at any instant.
    observation(
        "cmp-revenue-yahoo-2024-06-30",
        "revenue",
        "95000000000.0",
        period_start="2023-07-01",
        period_end="2024-06-30",
        available_at=None,
        available_basis="UNDECLARED",
        availability_class="ARCHIVE_FIRST_SEEN",
        # Archive-dated: eligible from when the archive first held it, which is
        # neither its period end nor a retrieval time.
        replay_eligible="2024-05-03T00:00:00+00:00",
        first_archived="2024-05-03T00:00:00+00:00",
        provider="YahooFinance",
        source_type="API_LIVE",
        concept="vendor:trailingTotalRevenue",
        accession="none",
        form=None,
        taxonomy="vendor",
        statement=None,
        
        document="doc_vendor",
    )

    # Two sources disagreeing about a share count, which is exactly the 2.4.2
    # finding that a content-addressed row per value would have destroyed.
    observation(
        "cmp-shares-sec-2024",
        "shares_outstanding",
        "15504000000.0",
        unit="count", currency=None, period_start=None,
        period_end="2023-11-03", concept="dei:EntityCommonStockSharesOutstanding",
        accession="0000320193-23-000105", form="10-K", statement="MARKET",
        
    )
    observation(
        "cmp-shares-yahoo-2024",
        "shares_outstanding",
        "14640000000.0",
        unit="count", currency=None, period_start=None,
        period_end="2023-11-03", available_at=None,
        available_basis="UNDECLARED", availability_class="UNDECLARED",
        replay_eligible=None, first_archived="2024-05-03T00:00:00+00:00",
        provider="YahooFinance", source_type="API_LIVE",
        concept="vendor:sharesOutstanding", accession="none", form=None,
        taxonomy="vendor", statement="MARKET", 
        document="doc_vendor",
    )

    # An instant balance-sheet figure, to prove `instant` is distinguishable.
    observation(
        "cmp-assets-sec-2024", "assets", "35258300000.0",
        period_start=None, period_end="2023-09-30", statement="BALANCE_SHEET",
        concept="us-gaap:Assets", accession="0000320193-23-000105",
        form="10-K", 
    )

    # A second reporting framework on the same metric, so the series is
    # genuinely not one comparable line.
    observation(
        "cmp-revenue-ifrs-2024",
        "revenue",
        "100.0",
        period_start="2023-07-01",
        period_end="2024-06-30",
        concept="ifrs-full:Revenue",
        accession="0000320193-24-000900",
        form="10-Q",
        taxonomy="ifrs-full",
        source_fact="sfid_ifrs",
    )

    # A context snapshot, so a derived value has something to belong to.
    connection.execute(
        "INSERT INTO context_snapshots (context_id, asset_id, as_of,"
        " knowledge_cutoff, replay_fidelity, built_from_json, document_json,"
        " document_hash, supersedes, archived_at)"
        " VALUES ('ctx_1', ?, '2024-05-03', '2024-05-03T00:00:00+00:00',"
        " 'OBSERVATIONAL', '{}', '{}', 'sha256:ctx', NULL,"
        " '2024-05-03T00:00:00+00:00')",
        (aapl,),
    )

    # A derived figure and a validation record.
    connection.execute(
        "INSERT INTO derived_values (context_id, ref, operation_json,"
        " expression, value_json, unit, deterministic, depends_on_json)"
        " VALUES ('ctx_1', 'der:current_ps', ?, ?, '367.4', 'multiple', 1, ?)",
        (
            json.dumps(
                {
                    "op": "divide",
                    "version": "1",
                    "operands": ["obs:obs_cmp-revenue-sec-q-2023-12-31-0"],
                }
            ),
            "market_cap / revenue",
            json.dumps(
                # 2.3-C writes dependencies as a list of refs, so the fixture
                # does the same rather than a richer shape the archive never
                # produces.
                ["obs:obs_cmp-revenue-sec-q-2023-12-31-0"]
            ),
        ),
    )
    connection.execute(
        "INSERT INTO validation_records (record_id, observation_id, kind,"
        " status, reasons_json, comparison_basis_json, tolerance_json,"
        " explanation, references_json, value_snapshot_json, checked_at)"
        " VALUES ('val_1', 'obs_cmp-shares-sec-2024', 'cross_source',"
        " 'DISCREPANT', ?, ?, '{}', ?, ?, ?, ?)",
        (
            json.dumps(["counts differ by 5.9%"]),
            json.dumps(
                {
                    "vendor_observation": "obs:cmp-shares-yahoo-2024",
                    "filing_observation": "obs:cmp-shares-sec-2024",
                    "provider": "YahooFinance",
                    "vendor_unit": "count",
                    "filing_unit": "count",
                    "vendor_currency": None,
                    "filing_currency": None,
                    "independence": "NOT_INDEPENDENT",
                    "period_offset_days": 0,
                }
            ),
            "the two sources report different share counts",
            json.dumps(
                ["obs_cmp-shares-sec-2024", "obs_cmp-shares-yahoo-2024"]
            ),
            json.dumps([15504000000.0, 14640000000.0]),
            "2024-05-03T00:00:00+00:00",
        ),
    )

    # A second, clean validation: two comparable sources that agree. Included
    # in the fixture rather than inserted during the test, because the query
    # surface refuses writes and that refusal is the guarantee.
    connection.execute(
        "INSERT INTO validation_records (record_id, observation_id, kind,"
        " status, reasons_json, comparison_basis_json, tolerance_json,"
        " explanation, references_json, value_snapshot_json, checked_at)"
        " VALUES ('val_2', 'obs_cmp-revenue-sec-q-2023-12-31-0',"
        " 'cross_source', 'CONSISTENT', ?, ?, '{}', 'agree', ?, ?, ?)",
        (
            json.dumps([]),
            json.dumps(
                {
                    "vendor_observation": "obs:cmp-revenue-yahoo-2024-06-30",
                    "filing_observation":
                        "obs:cmp-revenue-sec-q-2023-12-31-0",
                    "independence": "UNVERIFIED_INDEPENDENCE",
                    "vendor_unit": "currency",
                    "filing_unit": "currency",
                    "vendor_currency": "USD",
                    "filing_currency": "USD",
                }
            ),
            json.dumps(["obs_cmp-revenue-sec-q-2023-12-31-0"]),
            json.dumps([90356000000.0, 90356000000.0]),
            "2024-05-03T00:00:00+00:00",
        ),
    )

    # Evidence states, including the two that must never be conflated.
    for metric, state, code, detail in (
        ("revenue", SOURCE_REPORTED, "SOURCE_STATED_VALUE",
         "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"),
        ("operating_income", NOT_APPLICABLE, "BUSINESS_MODEL_NOT_MEANINGFUL", None),
        ("ebitda", NOT_APPLICABLE, "BUSINESS_MODEL_NOT_MEANINGFUL", None),
        ("inventory", SOURCE_DID_NOT_REPORT, "SOURCE_OMITS_CONCEPT", None),
        ("shares_outstanding", CONFLICTING, "SOURCES_DISAGREE", None),
        ("debt", STALE, "NO_RECENT_VALUE", None),
    ):
        connection.execute(
            "INSERT INTO evidence_state (asset_id, metric, state, reason_kind,"
            " reason_code, detail, as_of, updated_at)"
            " VALUES (?, ?, ?, NULL, ?, ?, NULL, '2024-05-03T00:00:00+00:00')",
            (bank if metric in ("operating_income", "ebitda", "inventory")
             else aapl, metric, state, code, detail),
        )

    connection.commit()
    return store


class QueryFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.store = build_archive()
        self.connection = self.store.connection
        self.query = EvidenceQuery(connection=self.connection)

    def tearDown(self) -> None:
        self.store.close()

    def add(self, contract_id, metric, value_json, **kwargs):
        """
        Add a case the shared fixture does not contain.

        A test that needs a case should add it to the fixture it already has.
        Writing its own forty-column insert instead is how two copies drift.
        """
        kwargs.setdefault("asset", self.connection.execute(
            "SELECT asset_id FROM assets WHERE ticker = ?", (AAPL,)
        ).fetchone()["asset_id"])
        # `EvidenceQuery` puts the shared connection into `query_only`, which is
        # the right guarantee for the read surface and the wrong one for a test
        # that is building the archive it will read. Lifted for the write and
        # put straight back, so the guarantee the rest of these tests rely on is
        # exactly the one the production surface provides.
        self.connection.execute("PRAGMA query_only = OFF")
        try:
            observation_id = add_observation(
                self.connection, contract_id, metric, value_json, **kwargs
            )
            self.connection.commit()
        finally:
            self.connection.execute("PRAGMA query_only = ON")
        return observation_id


class TestSingleObservation(QueryFixture):
    def test_query_one_observation(self):
        rows = self.query.query_observations(asset=AAPL, metric="revenue")
        self.assertTrue(rows)
        row = rows[0]
        self.assertEqual(row["asset"], AAPL)
        self.assertEqual(row["metric"], "revenue")
        self.assertIn("value", row)

    def test_get_observation_by_identity(self):
        rows = self.query.query_observations(asset=AAPL, metric="revenue")
        found = self.query.get_observation(rows[0]["observation_id"])
        self.assertIsNotNone(found)
        self.assertEqual(found["observation_id"], rows[0]["observation_id"])

    def test_get_observation_by_contract_id(self):
        found = self.query.get_observation("cmp-revenue-sec-q-2023-12-31-0")
        self.assertIsNotNone(found)
        self.assertEqual(found["metric"], "revenue")

    def test_an_unknown_observation_is_absent_not_a_null_row(self):
        self.assertIsNone(self.query.get_observation("obs_does_not_exist"))


class TestHistoricalSeries(QueryFixture):
    def test_query_historical_series(self):
        rows = self.query.query_observations(
            asset=AAPL, metric="revenue", order=ORDER_ASC
        )
        periods = [row["period"]["end"] for row in rows]
        self.assertEqual(periods, sorted(periods))

    def test_a_period_filter_narrows_the_series(self):
        rows = self.query.query_observations(
            asset=AAPL,
            metric="revenue",
            period_start="2024-01-01",
            period_end="2024-12-31",
        )
        for row in rows:
            end = row["period"]["end"]
            self.assertTrue("2024-01-01" <= end <= "2024-12-31", end)

    def test_the_status_filter_is_named_for_what_it_filters(self):
        """
        A2, from the first real model run.

        The filter was called `status` while every observation carried both a
        `status.validation_status` and a `status.evidence_state.state` beside
        each other. A model that had been told the distinction in a prompt
        passed `SOURCE_REPORTED` anyway -- an evidence state, to a parameter that
        filters cross-check status -- and got an empty list back.

        The rename is the fix. A parameter whose meaning has to be recovered
        from prose is not self-describing, and a vocabulary a surface invites
        you to use in the wrong parameter is worse than no vocabulary.
        """
        import inspect

        parameters = inspect.signature(
            EvidenceQuery.query_observations
        ).parameters
        self.assertIn("validation_status", parameters)
        self.assertNotIn(
            "status",
            parameters,
            "the ambiguous name is back; it collides with the evidence state "
            "that sits beside it in every payload",
        )

    def test_a_validation_status_is_refused_with_an_explanation(self):
        """
        An unmatched status returns `[]`, and an empty list reads as "no such
        data". So an evidence state passed here is refused *by name*, with the
        distinction the caller needs to act on.
        """
        with self.assertRaises(QueryError) as caught:
            self.query.query_observations(
                asset=AAPL,
                metric="revenue",
                validation_status="SOURCE_REPORTED",
            )
        message = str(caught.exception)
        self.assertIn("evidence state", message)
        self.assertIn("SOURCE_REPORTED", message)

    def test_the_status_keyword_is_no_longer_accepted(self):
        """
        Renaming without removing the old name would leave the ambiguity in
        place with a deprecation notice nobody reads.
        """
        with self.assertRaises(TypeError):
            self.query.query_observations(
                asset=AAPL, metric="revenue", status="UNVERIFIABLE"
            )

    def test_a_numeric_string_limit_is_accepted(self):
        """
        The first run spent four failed calls on `limit: "1"`. Refusing it
        taught nothing and cost a round trip; the caller wanted one.
        """
        self.assertEqual(
            len(
                self.query.query_observations(
                    asset=AAPL, metric="revenue", limit="1"
                )
            ),
            1,
        )

    def test_a_negative_limit_is_still_refused(self):
        for bad in ("0", -1, "abc"):
            with self.assertRaises(QueryError):
                self.query.query_observations(
                    asset=AAPL, metric="revenue", limit=bad
                )

    def test_query_by_asset_and_metric(self):
        self.assertTrue(
            self.query.query_observations(asset=AAPL, metric="assets")
        )
        # A metric ST-EVA has never heard of now raises rather than returning
        # an empty list. It used to return `[]`, identically to a metric that
        # exists and has no rows for the filter, and the first real model run
        # could not tell a typo from an absence -- it reported "no data exists"
        # seven times against an archive holding 1,922 revenue observations.
        # The two cases are different questions and now answer differently.
        with self.assertRaises(UnknownMetricError) as caught:
            self.query.query_observations(asset=AAPL, metric="nonexistent")
        # The recovery has to be in the error, or the caller is left guessing.
        self.assertIn("nonexistent", str(caught.exception))
        self.assertIn("revenue", str(caught.exception))
        self.assertIn("assets", str(caught.exception))
        self.assertIn("nonexistent", caught.exception.requested)
        self.assertIn("revenue", caught.exception.available)

    def test_a_known_metric_with_no_observations_is_not_an_error(self):
        """
        The other half of the distinction, and the reason it is worth making.

        `debt` is registered as STALE, which is exactly the case where holding
        no observations is the true answer. Refusing the name would turn a
        correct empty result into an error and lose the state that explains it.
        """
        self.assertEqual(
            self.query.query_observations(asset=AAPL, metric="debt"), []
        )
        self.assertEqual(
            self.query.get_metric_history(AAPL, "debt")["state"]["state"],
            STALE,
        )

    def test_ordering_is_explicit(self):
        ascending = self.query.query_observations(
            asset=AAPL, metric="revenue", order=ORDER_ASC
        )
        descending = self.query.query_observations(
            asset=AAPL, metric="revenue", order=ORDER_DESC
        )
        ascending_periods = [row["period"]["end"] for row in ascending]
        descending_periods = [row["period"]["end"] for row in descending]
        self.assertEqual(ascending_periods, sorted(ascending_periods))
        self.assertEqual(
            descending_periods, list(reversed(sorted(descending_periods)))
        )

    def test_limit_is_bounded(self):
        self.assertEqual(
            len(
                self.query.query_observations(
                    asset=AAPL, metric="revenue", limit=1
                )
            ),
            1,
        )
        for bad in (0, -1, 10**9, "ten", True):
            with self.assertRaises(QueryError):
                self.query.query_observations(
                    asset=AAPL, metric="revenue", limit=bad
                )


class TestPointInTime(QueryFixture):
    def test_query_by_knowable_at(self):
        rows = self.query.query_observations(
            asset=AAPL, metric="revenue", knowable_at="2024-05-02T22:04:25.000Z"
        )
        self.assertTrue(rows)
        for row in rows:
            self.assertLessEqual(
                row["available_at"]["knowable_at"], "2024-05-02T22:04:25.000Z"
            )

    def test_an_archive_dated_value_is_knowable_from_archival_not_before(self):
        """
        A source that published no date still has one thing we can state: when
        *we* first held it. That is archive-dated, not source-dated, and it is
        the archive's timestamp rather than the figure's period.
        """
        before = self.query.query_observations(
            asset=AAPL, metric="revenue", knowable_at="2024-05-01T00:00:00+00:00"
        )
        ids = {row["contract_id"] for row in before}
        self.assertNotIn("cmp-revenue-yahoo-2024-06-30", ids)

        after = self.query.query_observations(
            asset=AAPL, metric="revenue", knowable_at="2024-05-04T00:00:00+00:00"
        )
        classes = {
            row["contract_id"]: row["available_at"]["class"]
            for row in after
        }
        self.assertEqual(
            classes.get("cmp-revenue-yahoo-2024-06-30"), "ARCHIVE_FIRST_SEEN"
        )

    def test_a_never_knowable_value_is_excluded_at_every_instant(self):
        """
        UNDECLARED is different again: the source published no time and the
        archive is not permitted to invent one, so the value is not knowable at
        any instant, and not even in the far future.
        """
        for cutoff in ("2024-05-04T00:00:00+00:00", "2030-01-01"):
            rows = self.query.query_observations(
                asset=AAPL,
                metric="shares_outstanding",
                knowable_at=cutoff,
            )
            ids = {row["contract_id"] for row in rows}
            self.assertNotIn("cmp-shares-yahoo-2024", ids, cutoff)

    def test_a_rejected_date_never_reaches_the_database(self):
        for field in ("as_of", "period_start", "period_end", "knowable_at"):
            with self.assertRaises(QueryError):
                self.query.query_observations(
                    asset=AAPL, metric="revenue", **{field: "not-a-date"}
                )

    def test_reversed_period_is_rejected(self):
        with self.assertRaises(QueryError):
            self.query.query_observations(
                asset=AAPL, metric="revenue",
                period_start="2025-01-01", period_end="2024-01-01",
            )

    def test_an_unknown_asset_is_rejected(self):
        with self.assertRaises(QueryError):
            self.query.query_observations(asset="NOPE", metric="revenue")

    def test_an_unknown_order_is_rejected(self):
        with self.assertRaises(QueryError):
            self.query.query_observations(
                asset=AAPL, metric="revenue", order="; DROP TABLE observations"
            )


class TestSourceMetadata(QueryFixture):
    def test_query_source_metadata(self):
        document = self.query.get_source_document("doc_filing")
        self.assertIsNotNone(document)
        self.assertEqual(document["content_hash"], DOC_HASH)
        self.assertEqual(document["provider"], "SecEdgar")
        self.assertEqual(document["redistribution_tier"], "A")
        self.assertTrue(document["content_available"])

    def test_source_document_is_found_by_content_hash(self):
        self.assertIsNotNone(self.query.get_source_document(DOC_HASH))

    def test_source_document_is_found_by_canonical_uri(self):
        found = self.query.get_source_document("https://data.sec.gov/x.json")
        self.assertIsNotNone(found)
        self.assertEqual(found["source_document_id"], "doc_filing")

    def test_document_payload_is_never_returned(self):
        """
        A consumer may be told whether the bytes exist; it may not be handed
        them. The tier decides that, and the surface does not second-guess it.
        """
        document = self.query.get_source_document("doc_filing")
        self.assertFalse(document["content_returned"])
        self.assertNotIn("content", document)
        self.assertNotIn("content_bytes", document)

    def test_document_links_back_to_its_observations(self):
        document = self.query.get_source_document("doc_filing")
        self.assertTrue(document["observations"])
        for entry in document["observations"]:
            self.assertIsNotNone(entry["observation_id"])

    def test_unknown_source_document_is_absent(self):
        self.assertIsNone(self.query.get_source_document("doc_nope"))


class TestValidationMetadata(QueryFixture):
    def test_query_validation_metadata(self):
        records = self.query.get_validation("obs_cmp-shares-sec-2024")
        self.assertTrue(records)
        record = records[0]
        self.assertEqual(record["status"], "DISCREPANT")
        self.assertEqual(record["comparison"]["independence"], "NOT_INDEPENDENT")
        self.assertEqual(record["comparison"]["provider"], "YahooFinance")

    def test_validation_is_never_a_boolean(self):
        record = self.query.get_validation("obs_cmp-shares-sec-2024")[0]
        self.assertIsNone(record["trusted"])
        self.assertIn("Validation is a record", record["trusted_note"])

    def test_consistent_does_not_become_verified(self):
        """
        Agreement between two sources is agreement. Whether that is
        corroboration depends on independence, which the surface reports and
        does not interpret.
        """
        records = self.query.get_validation(
            "obs_cmp-revenue-sec-q-2023-12-31-0"
        )
        self.assertTrue(records)
        record = records[0]
        self.assertEqual(record["status"], "CONSISTENT")
        self.assertEqual(
            record["comparison"]["independence"], "UNVERIFIED_INDEPENDENCE"
        )
        self.assertNotEqual(record["status"], "VERIFIED")

    def test_validation_keeps_its_comparisons(self):
        record = self.query.get_validation("obs_cmp-shares-sec-2024")[0]
        comparison = record["comparison"]
        self.assertTrue(comparison["filing_ref"])
        self.assertTrue(comparison["vendor_ref"])
        self.assertEqual(comparison["unit_match"], True)
        self.assertEqual(comparison["currency_match"], True)

    def test_unknown_observation_has_no_validation(self):
        self.assertEqual(self.query.get_validation("obs_nope"), [])


class TestLineage(QueryFixture):
    def test_lineage_for_an_observed_fact(self):
        lineage = self.query.get_lineage("obs_cmp-revenue-sec-q-2023-12-31-0")
        self.assertEqual(lineage["kind"], "OBSERVED")
        steps = [item["step"] for item in lineage["chain"]]
        self.assertEqual(
            steps[:3], ["SOURCE_DOCUMENT", "SOURCE_FACT", "OBSERVATION"]
        )
        document = lineage["chain"][0]
        self.assertEqual(document["content_hash"], DOC_HASH)
        self.assertEqual(document["redistribution_tier"], "A")

    def test_lineage_for_a_derived_value(self):
        lineage = self.query.get_lineage("der:current_ps")
        self.assertEqual(lineage["kind"], "DERIVED")
        self.assertEqual(lineage["chain"][0]["step"], "DERIVED")
        self.assertEqual(lineage["chain"][1]["step"], "OPERATION")
        self.assertEqual(lineage["chain"][1]["operation_id"], "divide")
        self.assertEqual(lineage["chain"][1]["operation_version"], "1")
        self.assertTrue(lineage["operands"])
        self.assertTrue(lineage["operands"][0]["ref"])

    def test_derived_lineage_reaches_its_operands(self):
        lineage = self.query.get_lineage("der:current_ps")
        operand_steps = [i for i in lineage["chain"] if i["step"] == "OPERAND"]
        self.assertTrue(operand_steps)
        self.assertEqual(operand_steps[0]["kind"], "OBSERVED")

    def test_derived_value_is_not_recomputed_by_the_surface(self):
        lineage = self.query.get_lineage("der:current_ps")
        self.assertFalse(lineage["recomputation"]["recomputed_by_query"])

    def test_lineage_of_an_unknown_reference_is_unavailable(self):
        lineage = self.query.get_lineage("obs_nope")
        self.assertEqual(lineage["kind"], "UNAVAILABLE")
        self.assertTrue(lineage["reason"])

    def test_lineage_depth_is_validated(self):
        with self.assertRaises(QueryError):
            self.query.get_lineage("obs_cmp-revenue-sec-q-2023-12-31-0", depth=0)

    def test_a_derived_value_states_its_stored_value_at_the_top_level(self):
        """
        The reference names a number, so the payload names the number.

        It was already in the chain at step DERIVED, one level down, and both
        2.6.2 cloud models asked "what is this derived figure and how was it
        made" without reaching for this operation. A consumer should not have to
        walk a chain to read the value the reference is for.
        """
        lineage = self.query.get_lineage("der:current_ps")
        chain_value = lineage["chain"][0]["value"]
        self.assertIsNotNone(lineage["value"])
        self.assertEqual(lineage["value"], chain_value)
        self.assertEqual(lineage["expression"], lineage["chain"][0]["expression"])
        self.assertEqual(lineage["unit"], lineage["chain"][0]["unit"])

    def test_returning_the_stored_value_is_not_recomputing_it(self):
        """
        Reading the archived value back must not read as calculating it.
        """
        lineage = self.query.get_lineage("der:current_ps")
        self.assertFalse(lineage["recomputation"]["recomputed_by_query"])
        self.assertEqual(
            lineage["recomputation"]["value_source"], "STORED_DERIVED_VALUE"
        )


class TestAmbiguityIsClassified(QueryFixture):
    """
    Why two figures share a metric and a period, decided from the rows.

    The block used to return one sentence for every case — that the rows "share
    this metric, period and source concept" and that "the source endpoint
    aggregates dimension members". Against the AAPL snapshot that sentence was
    wrong for all 107 ambiguity groups, including the FY2007 revenue its own
    docstring used as the worked example, which is a 10-K against a 10-K/A and
    therefore two filings rather than two dimension members. Both free cloud
    models repeated it as the archive's finding.

    These tests pin the classification as a function of evidence, so the
    sentence cannot come back without one of them failing.
    """

    def ambiguity_for(self, observation_id):
        found = self.query.get_observation(observation_id)
        self.assertIsNotNone(found)
        return found.get("ambiguity")

    def test_two_filings_of_one_concept_are_not_a_dimension_collision(self):
        """
        The case the old sentence got wrong, and the one it was written for.

        A 10-K and a 10-K/A are two filings. Reading them as one aggregate over
        dimension members the filing never returned is a fabricated mechanism.
        """
        observation_id = self.add(
            "amb-filings", "revenue", "24006000000.0",
            accession="0001193125-09-214859", form="10-K",
        )
        self.add(
            "amb-filings-amended", "revenue", "24578000000.0",
            accession="0001193125-10-012091", form="10-K/A",
        )
        block = self.ambiguity_for(observation_id)
        self.assertEqual(block["reason"], AMBIGUITY_MULTIPLE_FILINGS)
        self.assertNotEqual(block["reason"], AMBIGUITY_DIMENSION)
        self.assertIn("0001193125-10-012091", block["basis"]["accessions"])

    def test_different_concepts_are_different_measures_not_a_choice(self):
        """
        The 68-group case: two concepts mapped to one metric.

        This is the change with the most weight. The figures are not competing
        answers, and the block has to say so, or a consumer picks one of them
        and reports it as the value of a metric it is a component of.
        """
        observation_id = self.add(
            "amb-concepts-a", "cash", "37988000000.0",
            concept="us-gaap:CashAndCashEquivalentsAtCarryingValue",
            source_concept_ref="us-gaap:CashAndCashEquivalentsAtCarryingValue",
        )
        self.add(
            "amb-concepts-b", "cash", "39817000000.0",
            concept="us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCash"
                    "Equivalents",
            source_concept_ref="us-gaap:CashCashEquivalentsRestrictedCashAnd"
                               "RestrictedCashEquivalents",
        )
        block = self.ambiguity_for(observation_id)
        self.assertEqual(block["reason"], AMBIGUITY_MULTIPLE_CONCEPTS)
        self.assertFalse(block["same_measure_established"])
        self.assertEqual(len(block["basis"]["source_concepts"]), 2)
        self.assertIn("different measures", block["explanation"])

    def test_one_filing_reporting_one_concept_twice_is_a_dimension_collision(self):
        """
        The only shape that licenses the aggregation story, kept because it is
        real and provable rather than because it is the easy answer.
        """
        observation_id = self.add(
            "amb-dimension-a", "revenue", "100.0", accession="0001193125-09-1",
        )
        self.add(
            "amb-dimension-b", "revenue", "200.0", accession="0001193125-09-1",
        )
        block = self.ambiguity_for(observation_id)
        self.assertEqual(block["reason"], AMBIGUITY_DIMENSION)
        self.assertEqual(block["basis"]["accessions"], ["0001193125-09-1"])
        self.assertTrue(block["same_measure_established"])

    def test_different_providers_outrank_everything_else(self):
        """
        Two sources are not two readings of one source's aggregate, whatever
        else is true of them, so this branch is taken first.
        """
        observation_id = self.add(
            "amb-cross-provider-filing", "shares_outstanding", "15504000000.0",
            concept="dei:EntityCommonStockSharesOutstanding",
            source_concept_ref="dei:EntityCommonStockSharesOutstanding",
        )
        self.add(
            "amb-cross-provider-vendor", "shares_outstanding", "14640000000.0",
            provider="VendorApi", source_type="API_LIVE",
            # The vendor's own column holds the metric id rather than an XBRL
            # tag, and the registry mapped no concept for it. That is exactly
            # what production does, and it is why the classification reads
            # `source_concept_ref` and not `concept`: a borrowed metric id is not
            # a source concept, and treating it as one would invent a second
            # measure that does not exist.
            concept="shares_outstanding", source_concept_ref=None,
            taxonomy=None, accession=None, form=None, document=None,
        )
        block = self.ambiguity_for(observation_id)
        self.assertEqual(block["reason"], AMBIGUITY_CROSS_PROVIDER)
        # The vendor figure has no source concept, so the evidence does not
        # establish that the two measure the same thing, and saying so is
        # better than inferring it from their sharing a metric.
        self.assertFalse(block["same_measure_established"])

    def test_the_archive_never_names_a_cause_it_cannot_see(self):
        """
        The explanation is written from the class, so it cannot claim a
        mechanism the classification did not establish.
        """
        self.add("amb-explain-a", "revenue", "100.0", accession="acc-1")
        self.add("amb-explain-b", "revenue", "200.0", accession="acc-2")
        block = self.ambiguity_for("obs_amb-explain-a")
        self.assertNotIn("aggregates dimension members", block["explanation"])
        self.assertEqual(block["determination"], "FROM_EVIDENCE")
        self.assertEqual(block["resolution"], "NO_WINNER_SELECTED")

    def test_same_values_are_not_an_ambiguity(self):
        """
        A restatement is not a choice, and the block has to stay quiet.
        """
        self.add("amb-restate-a", "revenue", "100.0", accession="acc-3")
        self.add("amb-restate-b", "revenue", "100.0", accession="acc-4")
        self.assertIsNone(self.ambiguity_for("obs_amb-restate-a"))

    def test_the_classification_is_a_closed_vocabulary(self):
        for basis in (
            {"providers": ["a", "b"], "source_concepts": ["x"]},
            {"providers": ["a"], "source_concepts": ["x", "y"]},
            {"providers": ["a"], "source_concepts": ["x"], "accessions": ["1"]},
            {"providers": ["a"], "source_concepts": ["x"], "accessions": []},
        ):
            self.assertIn(classify_ambiguity(basis), AMBIGUITY_REASONS)

    def test_a_missing_basis_does_not_raise(self):
        """
        The classifier is called on whatever was gathered, and an evidence
        database must not raise because a row is thin.
        """
        self.assertEqual(classify_ambiguity({}), AMBIGUITY_MULTIPLE_OBSERVATIONS)


class TestUnresolvedConflicts(QueryFixture):
    def test_a_conflict_returns_both_sides_and_picks_neither(self):
        rows = self.query.query_observations(
            asset=AAPL, metric="shares_outstanding", order=ORDER_ASC
        )
        self.assertEqual(len(rows), 2)
        values = {row["value"] for row in rows}
        self.assertEqual(values, {15504000000.0, 14640000000.0})

    def test_the_conflicting_metric_reports_the_conflicting_state(self):
        rows = self.query.query_observations(
            asset=AAPL, metric="shares_outstanding"
        )
        state = rows[0]["status"]["evidence_state"]
        self.assertEqual(state["state"], CONFLICTING)
        self.assertEqual(state["reason_code"], "SOURCES_DISAGREE")

    def test_the_surface_does_not_resolve_a_conflict(self):
        history = self.query.get_metric_history(
            AAPL, "shares_outstanding"
        )
        self.assertEqual(len(history["points"]), 2)
        self.assertEqual(history["state"]["state"], CONFLICTING)

    def test_an_incomparable_series_is_not_silently_merged(self):
        """
        Two points on different reporting frameworks are not one series. The
        2.4.3 rule applied on the read path: report the incomparability
        instead of splicing the points together.
        """
        history = self.query.get_metric_history(AAPL, "revenue")
        self.assertFalse(history["series_comparability"]["comparable"])
        self.assertIn("ifrs-full", str(
            history["series_comparability"]["reporting_frameworks"]
        ))
        # Every point is still returned, with the incomparability stated.
        self.assertGreaterEqual(len(history["points"]), 4)


class TestRefusalStates(QueryFixture):
    def test_unavailable_observations_preserve_their_reason(self):
        history = self.query.get_metric_history(AAPL, "debt")
        self.assertEqual(history["state"]["state"], STALE)
        self.assertEqual(history["state"]["reason_code"], "NO_RECENT_VALUE")

    def test_not_applicable_is_not_a_retrieval_failure(self):
        history = self.query.get_metric_history(ACME, "operating_income")
        self.assertEqual(history["state"]["state"], NOT_APPLICABLE)
        self.assertEqual(
            history["state"]["reason_code"], "BUSINESS_MODEL_NOT_MEANINGFUL"
        )
        self.assertNotEqual(
            history["state"]["state"], UNAVAILABLE
        )

    def test_source_did_not_report_is_not_not_applicable(self):
        history = self.query.get_metric_history(ACME, "inventory")
        self.assertEqual(history["state"]["state"], SOURCE_DID_NOT_REPORT)
        self.assertEqual(
            history["state"]["state"] in NEGATIVE_STATES, True
        )
        self.assertNotEqual(history["state"]["state"], NOT_APPLICABLE)

    def test_a_negative_state_never_carries_a_value(self):
        for metric in ("debt", "operating_income", "inventory"):
            history = self.query.get_metric_history(ACME, metric)
            for point in history["points"]:
                self.assertFalse(point["has_value"])

    def test_a_metric_with_no_state_row_falls_back_safely(self):
        history = self.query.get_metric_history(AAPL, "assets")
        self.assertEqual(history["state"]["state"], SOURCE_REPORTED)
        self.assertEqual(history["state"]["resolved_from"], "observation_status")

    def test_the_state_vocabulary_is_closed(self):
        self.assertEqual(len(EVIDENCE_STATES), 6)
        with self.assertRaises(EvidenceStateError):
            EvidenceState(asset=AAPL, metric="revenue", state="MAYBE")


class TestCoverage(QueryFixture):
    def test_coverage_counts_states_and_never_scores(self):
        report = self.query.coverage_report(AAPL)
        self.assertEqual(sum(report["state_counts"].values()),
                         report["metric_count"])
        for state in EVIDENCE_STATES:
            self.assertIn(state, report["state_counts"])

    def test_coverage_has_no_single_completeness_number(self):
        report = self.query.coverage_report(AAPL)
        self.assertNotIn("completeness", report)
        self.assertNotIn("score", report)
        self.assertNotIn("quality", report)


class TestReadOnly(QueryFixture):
    def test_the_connection_refuses_writes(self):
        with self.assertRaises(sqlite3.OperationalError):
            self.query.connection.execute(
                "DELETE FROM observations"
            )

    def test_no_query_method_mutates(self):
        before = self.connection.execute(
            "SELECT COUNT(*) AS n FROM observations"
        ).fetchone()["n"]
        self.query.query_observations(asset=AAPL)
        self.query.get_metric_history(AAPL, "revenue")
        self.query.coverage_report(AAPL)
        self.query.get_lineage("der:current_ps")
        after = self.connection.execute(
            "SELECT COUNT(*) AS n FROM observations"
        ).fetchone()["n"]
        self.assertEqual(before, after)

    def test_the_surface_exposes_no_raw_sql_entry_point(self):
        for forbidden in ("execute", "query", "sql", "raw_sql"):
            self.assertFalse(
                hasattr(EvidenceQuery, forbidden),
                f"the public surface must not offer {forbidden!r}",
            )

    def test_opened_queries_are_query_only(self):
        """A surface opened on a file refuses writes at the SQLite level."""
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "archive.sqlite")
            fixture = build_archive()
            target = SQLiteArchive(path)
            # Copy the fixture into the file with SQLite's own backup, rather
            # than by reading `main`, which is the file and not the fixture.
            # backup() copies source to destination, so the fixture is the
            # source and the file is the destination.
            fixture.connection.backup(target.connection)
            fixture.close()
            target.close()

            query = EvidenceQuery.open(path)
            try:
                with self.assertRaises(sqlite3.OperationalError):
                    query.connection.execute(
                        "UPDATE observations SET value_json = '0'"
                    )
                with self.assertRaises(sqlite3.OperationalError):
                    query.connection.execute("DELETE FROM observations")
                # Reads still work, which is the point of a read surface.
                self.assertTrue(
                    query.query_observations(asset=AAPL, metric="revenue")
                )
            finally:
                query.close()


class TestDeterminism(QueryFixture):
    def test_repeated_identical_queries_are_identical(self):
        first = self.query.get_metric_history(AAPL, "revenue")
        second = self.query.get_metric_history(AAPL, "revenue")
        self.assertEqual(
            json.dumps(first, sort_keys=True),
            json.dumps(second, sort_keys=True),
        )

    def test_output_is_json_serialisable(self):
        for row in self.query.query_observations(asset=AAPL):
            json.dumps(row)


@unittest.skipUnless(
    os.environ.get("ST_EVA_LIVE") == "1",
    "the AAPL end-to-end test needs ST_EVA_LIVE=1",
)
class TestAapplEndToEnd(unittest.TestCase):
    """
    AAPL, from a figure to the document that contains it.

    The point is not that the numbers are right. It is that a consumer can
    walk the chain without ever touching the SQLite schema, which is the
    promise the Query Surface makes.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.directory = tempfile.mkdtemp(prefix="steva-query-")
        cls.archive = os.path.join(cls.directory, "aapl.sqlite")
        cls.context = os.path.join(cls.directory, "aapl.context.json")
        import st_eva_runner

        st_eva_runner.run_st_eva(
            "AAPL",
            mode="live",
            save_snapshot=False,
            context_path=cls.context,
            context_sources=("yahoo", "sec"),
            archive=SQLiteArchive(cls.archive),
        )
        cls.query = EvidenceQuery.open(cls.archive)

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            cls.query.close()
        finally:
            import shutil

            shutil.rmtree(cls.directory, ignore_errors=True)

    def test_aapl_revenue_is_queryable_as_a_series(self):
        history = self.query.get_metric_history("AAPL", "revenue")
        self.assertGreater(history["point_count"], 0)
        self.assertEqual(history["state"]["state"], SOURCE_REPORTED)
        first = history["points"][0]
        self.assertTrue(first["has_value"])
        self.assertEqual(first["unit"], "currency")
        self.assertEqual(first["currency"], "USD")
        self.assertIsNotNone(first["period"]["end"])
        self.assertTrue(first["source"]["accession"])
        self.assertTrue(first["source"]["concept"])
        self.assertTrue(first["source"]["content_hashes"])

    def test_a_figure_traces_to_its_source_document(self):
        rows = self.query.query_observations(
            asset="AAPL", metric="revenue", order=ORDER_ASC, limit=1
        )
        self.assertTrue(rows)
        lineage = self.query.get_lineage(rows[0]["observation_id"])
        self.assertEqual(lineage["kind"], "OBSERVED")
        steps = [item["step"] for item in lineage["chain"]]
        self.assertIn("SOURCE_DOCUMENT", steps)
        self.assertIn("OBSERVATION", steps)
        document = lineage["chain"][0]
        self.assertTrue(document["content_hash"].startswith("sha256:"))
        self.assertTrue(document["canonical_uri"].startswith("https://"))

    def test_the_document_holds_the_bytes_and_says_so(self):
        rows = self.query.query_observations(
            asset="AAPL", metric="revenue", order=ORDER_ASC, limit=1
        )
        documents = rows[0]["source"]["documents"]
        self.assertTrue(documents)
        document = self.query.get_source_document(documents[0]["document_id"])
        self.assertIsNotNone(document)
        self.assertTrue(document["content_available"])
        self.assertFalse(document["content_returned"])
        self.assertIn(document["redistribution_tier"], ("A", "B", "C"))
        self.assertTrue(document["observations"])

    def test_a_derived_figure_reaches_its_operands(self):
        derived = self.query.query_observations(
            asset="AAPL", metric="price", order=ORDER_ASC, limit=1
        )
        self.assertTrue(derived)
        context = json.loads(
            open(self.context, encoding="utf-8").read()
        )
        ref = "der:" + sorted(context["derived"])[0]
        lineage = self.query.get_lineage(ref)
        if lineage["kind"] == "UNAVAILABLE":
            self.skipTest("this run archived no derived value")
        self.assertEqual(lineage["kind"], "DERIVED")
        self.assertTrue(lineage["operands"])
        self.assertEqual(lineage["chain"][1]["step"], "OPERATION")
        self.assertTrue(lineage["chain"][1]["operation_id"])
        self.assertFalse(lineage["recomputation"]["recomputed_by_query"])

    def test_point_in_time_hides_later_filings(self):
        cutoff = "2025-01-01"
        rows = self.query.query_observations(
            asset="AAPL", metric="revenue", knowable_at=cutoff
        )
        for row in rows:
            self.assertLessEqual(
                row["available_at"]["knowable_at"], cutoff
            )
        all_rows = self.query.query_observations(
            asset="AAPL", metric="revenue"
        )
        self.assertGreaterEqual(len(all_rows), len(rows))

    def test_a_consumer_needs_no_schema_knowledge(self):
        """
        Everything an LLM is asked about, reachable from the returned object
        alone. If any of these needs a table name, the surface has leaked.
        """
        row = self.query.query_observations(
            asset="AAPL", metric="revenue", order=ORDER_ASC, limit=1
        )[0]
        for key in (
            "observation_id", "asset", "metric", "value", "has_value", "unit",
            "currency", "period", "as_of", "available_at", "status", "source",
            "definition", "methodology", "basis", "validation", "lineage",
        ):
            self.assertIn(key, row, f"{key} is not exposed")
        self.assertNotIn("raw_json", row, "internal storage leaked")
        self.assertEqual(row["status"]["evidence_state"]["state"],
                         SOURCE_REPORTED)

    def test_coverage_reports_states_not_a_score(self):
        report = self.query.coverage_report("AAPL")
        self.assertIn("state_counts", report)
        for state in EVIDENCE_STATES:
            self.assertIn(state, report["state_counts"])
        # The check is on field names, not on prose: the report explains why
        # there is no single completeness figure, and that explanation is
        # allowed to use the word it refuses to publish.
        for entry in report["metrics"]:
            for key in entry:
                for word in ("score", "grade", "completeness", "quality"):
                    self.assertNotIn(word, key.lower())
        for key in report:
            for word in ("score", "grade", "completeness", "quality"):
                self.assertNotIn(word, key.lower())


if __name__ == "__main__":
    unittest.main()
