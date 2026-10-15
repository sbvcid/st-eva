"""
Regression tests for the consensus revision and trend extraction.

The Yahoo quoteSummary ``earningsTrend`` module states, on every trend row,
two blocks the acquisition path did not extract:

* ``epsRevisions`` -- how many analyst estimates were revised up or down
  inside a window the source labels itself ("last 7 days");
* ``epsTrend`` -- the estimate as presently published and the same estimate
  as it stood 7/30/60/90 days before acquisition, per the source's own
  relative labels.

These tests pin the extraction against a frozen sample of the real payload
(AAPL, captured 2026-10-15), the period separation between rows, the
deterministic differences computed inside one row's trend series, the units
and currencies each value carries, and the publication path: view, context
selection, JSON serialization and the SQLite archive.

Nothing here may invent a value. An empty ``downLast90days`` block is an
absent value, never a zero; a revision count is never used to produce an EPS
amount; and two values are differenced only inside one forecast period's own
trend series.
"""
from __future__ import annotations

import json
import sys
import unittest

sys.path.insert(0, ".")

from data_contract import (
    CONTRACT_METRICS,
    CONTRACT_OBSERVATION_IDS,
    CurrencyBasis,
    METRIC_CONSENSUS_FORWARD_EPS,
    METRIC_CONSENSUS_FORWARD_EPS_30D_AGO,
    METRIC_CONSENSUS_FORWARD_EPS_60D_AGO,
    METRIC_CONSENSUS_FORWARD_EPS_7D_AGO,
    METRIC_CONSENSUS_FORWARD_EPS_90D_AGO,
    METRIC_CONSENSUS_FORWARD_EPS_ANALYST_COUNT,
    METRIC_CONSENSUS_FORWARD_EPS_HIGH,
    METRIC_CONSENSUS_FORWARD_EPS_LOW,
    METRIC_CONSENSUS_FORWARD_EPS_TREND_CURRENT,
    METRIC_CONSENSUS_REVISION_AMOUNT_30D,
    METRIC_CONSENSUS_REVISION_AMOUNT_60D,
    METRIC_CONSENSUS_REVISION_AMOUNT_7D,
    METRIC_CONSENSUS_REVISION_AMOUNT_90D,
    METRIC_CONSENSUS_REVISIONS_DOWN_30D,
    METRIC_CONSENSUS_REVISIONS_DOWN_7D,
    METRIC_CONSENSUS_REVISIONS_DOWN_90D,
    METRIC_CONSENSUS_REVISIONS_UP_30D,
    METRIC_CONSENSUS_REVISIONS_UP_7D,
    METRIC_DEFINITIONS,
    METRIC_UNITS,
    UNIT_PER_SHARE,
    UNAVAILABLE,
    Unit,
)
from fundamental_provider import YahooFundamentalProvider
from sqlite_archive import SQLiteArchive
from st_eva_runner import (
    CONSENSUS_EXTRA_METRICS,
    CONSENSUS_REVISION_AMOUNT_METRICS,
    CONSENSUS_REVISION_METRICS,
    CONSENSUS_SAMPLE_METRICS,
    CONSENSUS_TREND_METRICS,
    MarketData,
    _apply_observations_to_view,
)

# A frozen sample of the row the live acquisition selected on 2026-10-15
# (AAPL +1y, next fiscal year), verbatim from the quoteSummary payload
# including the fields this task does not read, so the tests exercise the
# same structure the source serves.
AAPL_PLUS_1Y_ROW = {
    "maxAge": 1,
    "period": "+1y",
    "endDate": "2027-09-30",
    "growth": {"raw": 0.086, "fmt": "8.60%"},
    "earningsEstimate": {
        "avg": {"raw": 9.58335, "fmt": "9.58"},
        "low": {"raw": 8.69, "fmt": "8.69"},
        "high": {"raw": 10.67, "fmt": "10.67"},
        "yearAgoEps": {"raw": 8.82006, "fmt": "8.82"},
        "numberOfAnalysts": {"raw": 40, "fmt": "40", "longFmt": "40"},
        "growth": {"raw": 0.0865, "fmt": "8.65%"},
        "earningsCurrency": "USD",
    },
    "revenueEstimate": {
        "avg": {"raw": 528641081619, "fmt": "528.64B", "longFmt": "528,641,081,619"},
        "low": {"raw": 497900000000, "fmt": "497.9B", "longFmt": "497,900,000,000"},
        "high": {"raw": 594863000000, "fmt": "594.86B", "longFmt": "594,863,000,000"},
        "numberOfAnalysts": {"raw": 40, "fmt": "40", "longFmt": "40"},
        "yearAgoRevenue": {"raw": 478214889500, "fmt": "478.21B", "longFmt": "478,214,889,500"},
        "growth": {"raw": 0.105399996, "fmt": "10.54%"},
        "revenueCurrency": "USD",
    },
    "epsTrend": {
        "current": {"raw": 9.58335, "fmt": "9.58"},
        "7daysAgo": {"raw": 9.57579, "fmt": "9.58"},
        "30daysAgo": {"raw": 9.57254, "fmt": "9.57"},
        "60daysAgo": {"raw": 9.53948, "fmt": "9.54"},
        "90daysAgo": {"raw": 9.69285, "fmt": "9.69"},
        "epsTrendCurrency": "USD",
    },
    "epsRevisions": {
        "upLast7days": {"raw": 0, "fmt": None, "longFmt": "0"},
        "upLast30days": {"raw": 4, "fmt": "4", "longFmt": "4"},
        "downLast30days": {"raw": 3, "fmt": "3", "longFmt": "3"},
        "downLast7Days": {"raw": 2, "fmt": "2", "longFmt": "2"},
        "downLast90days": {},
        "epsRevisionsCurrency": "USD",
    },
}

# The current-fiscal-year row of the same payload, kept for the tests that
# prove different forecast periods never merge.
AAPL_0Y_ROW = {
    "maxAge": 1,
    "period": "0y",
    "endDate": "2026-09-30",
    "growth": {"raw": 0.1838, "fmt": "18.38%"},
    "earningsEstimate": {
        "avg": {"raw": 8.82006, "fmt": "8.82"},
        "low": {"raw": 8.28, "fmt": "8.28"},
        "high": {"raw": 8.94, "fmt": "8.94"},
        "yearAgoEps": {"raw": 7.46, "fmt": "7.46"},
        "numberOfAnalysts": {"raw": 39, "fmt": "39", "longFmt": "39"},
        "growth": {"raw": 0.1823, "fmt": "18.23%"},
        "earningsCurrency": "USD",
    },
    "epsTrend": {
        "current": {"raw": 8.82006, "fmt": "8.82"},
        "7daysAgo": {"raw": 8.82022, "fmt": "8.82"},
        "30daysAgo": {"raw": 8.81509, "fmt": "8.82"},
        "60daysAgo": {"raw": 8.80708, "fmt": "8.81"},
        "90daysAgo": {"raw": 8.76613, "fmt": "8.77"},
        "epsTrendCurrency": "USD",
    },
    "epsRevisions": {
        "upLast7days": {"raw": 1, "fmt": "1", "longFmt": "1"},
        "upLast30days": {"raw": 2, "fmt": "2", "longFmt": "2"},
        "downLast30days": {"raw": 1, "fmt": "1", "longFmt": "1"},
        "downLast7Days": {"raw": 0, "fmt": None, "longFmt": "0"},
        "downLast90days": {},
        "epsRevisionsCurrency": "USD",
    },
}

REVISION_METRICS = (
    (METRIC_CONSENSUS_REVISIONS_UP_7D, "upLast7days"),
    (METRIC_CONSENSUS_REVISIONS_UP_30D, "upLast30days"),
    (METRIC_CONSENSUS_REVISIONS_DOWN_7D, "downLast7Days"),
    (METRIC_CONSENSUS_REVISIONS_DOWN_30D, "downLast30days"),
    (METRIC_CONSENSUS_REVISIONS_DOWN_90D, "downLast90days"),
)

TREND_METRICS = (
    (METRIC_CONSENSUS_FORWARD_EPS_TREND_CURRENT, "current"),
    (METRIC_CONSENSUS_FORWARD_EPS_7D_AGO, "7daysAgo"),
    (METRIC_CONSENSUS_FORWARD_EPS_30D_AGO, "30daysAgo"),
    (METRIC_CONSENSUS_FORWARD_EPS_60D_AGO, "60daysAgo"),
    (METRIC_CONSENSUS_FORWARD_EPS_90D_AGO, "90daysAgo"),
)

CHANGE_METRICS = (
    (METRIC_CONSENSUS_REVISION_AMOUNT_7D, "7daysAgo", 9.58335 - 9.57579),
    (METRIC_CONSENSUS_REVISION_AMOUNT_30D, "30daysAgo", 9.58335 - 9.57254),
    (METRIC_CONSENSUS_REVISION_AMOUNT_60D, "60daysAgo", 9.58335 - 9.53948),
    (METRIC_CONSENSUS_REVISION_AMOUNT_90D, "90daysAgo", 9.58335 - 9.69285),
)


def _trend(*rows):
    return {"trend": list(rows)}


class ExtractionHarness:
    """
    The observations the extraction produces for one trend payload.

    Everything is read through the same selection rule the consensus average
    uses, so the blocks below can never come from a different row than the
    published estimate.
    """

    def __init__(self, trend, instrument_currency="USD"):
        provider = YahooFundamentalProvider()
        selected = provider._select_consensus_row(trend)
        self.selected = selected
        self.observations = []
        if selected is None:
            return
        row = selected[5]
        self.observations.extend(
            provider._consensus_sample_observations(
                clean="AAPL",
                estimate=selected[4],
                period=selected[2],
                period_end=selected[3],
                retrieved_at="2026-10-15T07:50:06+00:00",
                source_url="https://query2.finance.yahoo.com/v10/finance/quoteSummary/AAPL",
                instrument_currency=instrument_currency,
            )
        )
        self.observations.extend(
            provider._consensus_revision_observations(
                revisions=row.get("epsRevisions"),
                period=selected[2],
                period_end=selected[3],
                retrieved_at="2026-10-15T07:50:06+00:00",
                source_url="https://query2.finance.yahoo.com/v10/finance/quoteSummary/AAPL",
            )
        )
        self.observations.extend(
            provider._consensus_trend_observations(
                trend_block=row.get("epsTrend"),
                period=selected[2],
                period_end=selected[3],
                retrieved_at="2026-10-15T07:50:06+00:00",
                source_url="https://query2.finance.yahoo.com/v10/finance/quoteSummary/AAPL",
                instrument_currency=instrument_currency,
            )
        )
        self.observations.extend(
            provider._consensus_change_observations(
                trend_block=row.get("epsTrend"),
                period=selected[2],
                period_end=selected[3],
                retrieved_at="2026-10-15T07:50:06+00:00",
                source_url="https://query2.finance.yahoo.com/v10/finance/quoteSummary/AAPL",
                instrument_currency=instrument_currency,
            )
        )

    def by_metric(self):
        return {observation.metric: observation for observation in self.observations}

    def available(self):
        return {
            observation.metric: observation
            for observation in self.observations
            if observation.is_available
        }


class TestRevisionCountsAreExtractedFromTheRealPayload(unittest.TestCase):
    """Each count equals the field the source stated, key spelled exactly."""

    def setUp(self):
        self.observations = ExtractionHarness(
            _trend(AAPL_PLUS_1Y_ROW)
        ).by_metric()

    def test_each_count_equals_the_source_field(self):
        expected = {
            METRIC_CONSENSUS_REVISIONS_UP_7D: 0.0,
            METRIC_CONSENSUS_REVISIONS_UP_30D: 4.0,
            METRIC_CONSENSUS_REVISIONS_DOWN_7D: 2.0,
            METRIC_CONSENSUS_REVISIONS_DOWN_30D: 3.0,
        }
        for metric, value in expected.items():
            with self.subTest(metric=metric):
                self.assertEqual(self.observations[metric].value, value)

    def test_a_declared_zero_is_a_zero(self):
        # ``upLast7days`` states 0 with ``fmt: null``. The count the source
        # stated is zero, not missing.
        observation = self.observations[METRIC_CONSENSUS_REVISIONS_UP_7D]
        self.assertEqual(observation.value, 0.0)
        self.assertTrue(observation.is_available)

    def test_an_empty_block_is_absent_never_zero(self):
        # ``downLast90days`` is an empty object in the real payload: the
        # source declares the window but states no count. The gap is kept.
        observation = self.observations[METRIC_CONSENSUS_REVISIONS_DOWN_90D]
        self.assertIsNone(observation.value)
        self.assertFalse(observation.is_available)

    def test_counts_carry_the_count_unit_and_no_currency(self):
        for metric, _ in REVISION_METRICS:
            with self.subTest(metric=metric):
                observation = self.observations[metric]
                self.assertEqual(observation.unit, Unit.COUNT.value)
                self.assertIsNone(
                    observation.currency,
                    "a count of analysts is not denominated in anything, "
                    "even though the source attaches a currency to the block",
                )
                self.assertEqual(
                    observation.currency_basis,
                    CurrencyBasis.NOT_APPLICABLE.value,
                )

    def test_each_count_names_its_exact_source_path(self):
        for metric, source_key in REVISION_METRICS:
            observation = self.observations[metric]
            if not observation.is_available:
                # An absent value is published without a raw payload, the
                # same as the consensus sample's absent values: nothing is
                # attributed to a field the source left empty.
                self.assertIsNone(observation.raw)
                continue
            with self.subTest(metric=metric):
                self.assertEqual(
                    observation.methodology,
                    "Yahoo quoteSummary earningsTrend trend[period]"
                    f".epsRevisions.{source_key}",
                )
                self.assertEqual(
                    observation.raw["field"],
                    f"trend[].epsRevisions.{source_key}",
                )

    def test_counts_carry_the_selected_row_s_period(self):
        for metric, _ in REVISION_METRICS:
            observation = self.observations[metric]
            if not observation.is_available:
                # The absent downLast90days block fabricates no period.
                self.assertIsNone(observation.period_end)
                continue
            with self.subTest(metric=metric):
                self.assertEqual(observation.period_end, "2027-09-30")
                self.assertEqual(observation.raw["period"], "+1y")
                self.assertEqual(observation.raw["period_end"], "2027-09-30")
                self.assertIsNone(observation.period_start)


class TestTrendSeriesIsExtractedFromTheRealPayload(unittest.TestCase):
    def setUp(self):
        self.observations = ExtractionHarness(
            _trend(AAPL_PLUS_1Y_ROW)
        ).by_metric()

    def test_each_snapshot_equals_the_source_field(self):
        expected = {
            METRIC_CONSENSUS_FORWARD_EPS_TREND_CURRENT: 9.58335,
            METRIC_CONSENSUS_FORWARD_EPS_7D_AGO: 9.57579,
            METRIC_CONSENSUS_FORWARD_EPS_30D_AGO: 9.57254,
            METRIC_CONSENSUS_FORWARD_EPS_60D_AGO: 9.53948,
            METRIC_CONSENSUS_FORWARD_EPS_90D_AGO: 9.69285,
        }
        for metric, value in expected.items():
            with self.subTest(metric=metric):
                self.assertEqual(self.observations[metric].value, value)

    def test_snapshots_are_per_share_in_the_block_s_declared_currency(self):
        for metric, _ in TREND_METRICS:
            with self.subTest(metric=metric):
                observation = self.observations[metric]
                self.assertEqual(observation.unit, UNIT_PER_SHARE)
                self.assertEqual(observation.currency, "USD")
                self.assertEqual(
                    observation.currency_basis,
                    CurrencyBasis.REPORTED.value,
                    "the block declares epsTrendCurrency, and that is the "
                    "currency the values are reported in",
                )

    def test_every_snapshot_keeps_the_row_s_period_and_reference_label(self):
        for metric, source_key in TREND_METRICS:
            with self.subTest(metric=metric):
                observation = self.observations[metric]
                self.assertEqual(observation.period_end, "2027-09-30")
                self.assertIsNone(observation.period_start)
                self.assertIsNone(
                    observation.as_of,
                    "the source states no absolute reference date, so none "
                    "is derived from the relative label",
                )
                self.assertEqual(
                    observation.raw["field"],
                    f"trend[].epsTrend.{source_key}",
                )

    def test_a_row_without_a_trend_block_leaves_every_snapshot_absent(self):
        row = {
            "period": "+1y",
            "endDate": "2027-09-30",
            "earningsEstimate": {"avg": {"raw": 9.0, "fmt": "9.00"}},
        }
        observations = ExtractionHarness(_trend(row)).by_metric()
        for metric, _ in TREND_METRICS:
            with self.subTest(metric=metric):
                observation = observations[metric]
                self.assertIsNone(observation.value)
                self.assertFalse(observation.is_available)


class TestForecastPeriodsAndReferenceDatesNeverMerge(unittest.TestCase):
    def test_only_the_selected_row_s_blocks_are_extracted(self):
        harness = ExtractionHarness(_trend(AAPL_0Y_ROW, AAPL_PLUS_1Y_ROW))
        available = harness.available()

        # The selection prefers +1y, so every extracted value is the +1y
        # row's own; the 0y row's 8.82 series and its upLast7days=1 count
        # must not appear anywhere.
        self.assertEqual(
            available[METRIC_CONSENSUS_FORWARD_EPS_TREND_CURRENT].value, 9.58335
        )
        self.assertEqual(available[METRIC_CONSENSUS_REVISIONS_UP_7D].value, 0.0)
        self.assertEqual(
            available[METRIC_CONSENSUS_REVISIONS_UP_30D].value, 4.0
        )
        self.assertNotIn(8.82006, [o.value for o in harness.observations])
        self.assertNotIn(1.0, [o.value for o in harness.observations])

    def test_the_0y_row_s_values_come_out_when_it_is_the_one_selected(self):
        harness = ExtractionHarness(_trend(AAPL_0Y_ROW))
        available = harness.available()
        self.assertEqual(
            available[METRIC_CONSENSUS_FORWARD_EPS_TREND_CURRENT].value, 8.82006
        )
        for observation in harness.observations:
            if not observation.is_available:
                continue
            self.assertEqual(observation.period_end, "2026-09-30")
            self.assertEqual(observation.raw["period"], "0y")

    def test_two_rows_keep_their_own_declared_ends(self):
        first = ExtractionHarness(_trend(AAPL_PLUS_1Y_ROW))
        second = ExtractionHarness(_trend(AAPL_0Y_ROW))
        ends = {
            "+1y": first.by_metric()[METRIC_CONSENSUS_REVISIONS_UP_30D].period_end,
            "0y": second.by_metric()[METRIC_CONSENSUS_REVISIONS_UP_30D].period_end,
        }
        self.assertEqual(ends, {"+1y": "2027-09-30", "0y": "2026-09-30"})

    def test_a_change_operand_never_crosses_rows(self):
        # The change is computed inside one row's block only: its raw records
        # the operands of the row it belongs to, so a 0y snapshot can never
        # enter a +1y difference.
        observations = ExtractionHarness(
            _trend(AAPL_0Y_ROW, AAPL_PLUS_1Y_ROW)
        ).by_metric()
        for metric, source_key, _ in CHANGE_METRICS:
            with self.subTest(metric=metric):
                raw = observations[metric].raw
                self.assertEqual(
                    raw["operands"]["current"]["value"], 9.58335
                )
                self.assertEqual(
                    raw["operands"][source_key]["value"],
                    AAPL_PLUS_1Y_ROW["epsTrend"][source_key]["raw"],
                )


class TestDeterministicChangeAmounts(unittest.TestCase):
    """
    The change metrics are computed, not stated. Each is verified here with
    an independently written difference of the two published operands.
    """

    def setUp(self):
        self.observations = ExtractionHarness(
            _trend(AAPL_PLUS_1Y_ROW)
        ).by_metric()

    def test_each_change_equals_the_difference_of_its_two_operands(self):
        for metric, _, expected in CHANGE_METRICS:
            with self.subTest(metric=metric):
                self.assertAlmostEqual(
                    self.observations[metric].value, expected, places=12
                )

    def test_the_published_value_matches_the_operands_in_raw(self):
        # Independent recomputation: the operands are read back from the
        # observation's raw record and the difference is formed again here,
        # never copied from the published value.
        for metric, source_key, _ in CHANGE_METRICS:
            with self.subTest(metric=metric):
                observation = self.observations[metric]
                current = observation.raw["operands"]["current"]["value"]
                ago = observation.raw["operands"][source_key]["value"]
                self.assertAlmostEqual(
                    observation.value, current - ago, places=12
                )
                self.assertEqual(
                    observation.raw["expression"],
                    f"trend[].epsTrend.current - trend[].epsTrend.{source_key}",
                )

    def test_changes_name_the_observations_they_were_computed_from(self):
        for metric, source_key, _ in CHANGE_METRICS:
            with self.subTest(metric=metric):
                observation = self.observations[metric]
                self.assertEqual(
                    observation.inputs,
                    (
                        "obs-consensus-eps-trend-current-001",
                        f"obs-consensus-eps-{source_key.replace('daysAgo', 'd-ago')}-001",
                    ),
                )

    def test_a_change_is_per_share_in_the_series_currency(self):
        for metric, _, _ in CHANGE_METRICS:
            with self.subTest(metric=metric):
                observation = self.observations[metric]
                self.assertEqual(observation.unit, UNIT_PER_SHARE)
                self.assertEqual(observation.currency, "USD")
                self.assertEqual(
                    observation.currency_basis, CurrencyBasis.REPORTED.value
                )
                self.assertEqual(observation.period_end, "2027-09-30")

    def test_a_missing_operand_disables_only_its_own_change(self):
        row = json.loads(json.dumps(AAPL_PLUS_1Y_ROW))
        del row["epsTrend"]["90daysAgo"]
        observations = ExtractionHarness(_trend(row)).by_metric()

        missing = observations[METRIC_CONSENSUS_REVISION_AMOUNT_90D]
        self.assertIsNone(missing.value)
        self.assertFalse(missing.is_available)
        for metric, _, _ in CHANGE_METRICS:
            if metric == METRIC_CONSENSUS_REVISION_AMOUNT_90D:
                continue
            with self.subTest(metric=metric):
                self.assertIsNotNone(observations[metric].value)

    def test_a_missing_current_disables_every_change(self):
        row = json.loads(json.dumps(AAPL_PLUS_1Y_ROW))
        del row["epsTrend"]["current"]
        observations = ExtractionHarness(_trend(row)).by_metric()
        for metric, _, _ in CHANGE_METRICS:
            with self.subTest(metric=metric):
                self.assertIsNone(observations[metric].value)

    def test_nothing_derives_a_change_from_revision_counts(self):
        # The counts say how many estimates moved. They are never an input
        # to the amounts: with the trend block deleted but the counts
        # intact, no change survives.
        row = json.loads(json.dumps(AAPL_PLUS_1Y_ROW))
        del row["epsTrend"]
        observations = ExtractionHarness(_trend(row)).by_metric()
        for metric, _, _ in CHANGE_METRICS:
            with self.subTest(metric=metric):
                self.assertIsNone(observations[metric].value)
        self.assertEqual(
            observations[METRIC_CONSENSUS_REVISIONS_UP_30D].value, 4.0
        )


class TestMissingAndUnselectableDataKeepsItsSemantics(unittest.TestCase):
    def test_a_row_without_blocks_yields_no_values_and_no_zeros(self):
        row = {
            "period": "+1y",
            "endDate": "2027-09-30",
            "earningsEstimate": {"avg": {"raw": 9.0}},
        }
        observations = ExtractionHarness(_trend(row)).by_metric()
        extracted = (
            [metric for metric, _ in REVISION_METRICS]
            + [metric for metric, _ in TREND_METRICS]
            + [metric for metric, _, _ in CHANGE_METRICS]
        )
        for metric in extracted:
            with self.subTest(metric=metric):
                observation = observations[metric]
                self.assertIsNone(observation.value)
                self.assertFalse(observation.is_available)

    def test_no_selected_row_yields_no_observations_at_all(self):
        harness = ExtractionHarness({"trend": []})
        self.assertIsNone(harness.selected)
        self.assertEqual(harness.observations, [])

    def test_a_row_with_only_an_estimate_yields_the_sample_and_gaps(self):
        # The source served no epsRevisions or epsTrend on this row. The
        # existing sample still extracts; the new metrics stay absent
        # rather than zero.
        row = {
            "period": "+1y",
            "endDate": "2027-09-30",
            "earningsEstimate": {"avg": {"raw": 9.0}},
        }
        observations = ExtractionHarness(_trend(row)).by_metric()
        self.assertEqual(
            observations[METRIC_CONSENSUS_FORWARD_EPS_ANALYST_COUNT].value,
            None,
        )
        self.assertIsNone(observations[METRIC_CONSENSUS_REVISIONS_UP_30D].value)
        self.assertIsNone(
            observations[METRIC_CONSENSUS_FORWARD_EPS_TREND_CURRENT].value
        )


class TestCurrencyBasisFollowsTheSource(unittest.TestCase):
    def test_a_declared_block_currency_is_reported(self):
        observations = ExtractionHarness(
            _trend(AAPL_PLUS_1Y_ROW), instrument_currency="USD"
        ).by_metric()
        snapshot = observations[METRIC_CONSENSUS_FORWARD_EPS_7D_AGO]
        self.assertEqual(snapshot.currency, "USD")
        self.assertEqual(snapshot.currency_basis, CurrencyBasis.REPORTED.value)

    def test_an_undeclared_block_falls_back_to_the_instrument(self):
        row = json.loads(json.dumps(AAPL_PLUS_1Y_ROW))
        del row["epsTrend"]["epsTrendCurrency"]
        observations = ExtractionHarness(
            _trend(row), instrument_currency="EUR"
        ).by_metric()
        snapshot = observations[METRIC_CONSENSUS_FORWARD_EPS_7D_AGO]
        self.assertEqual(snapshot.currency, "EUR")
        self.assertEqual(
            snapshot.currency_basis, CurrencyBasis.INSTRUMENT_DEFAULT.value
        )
        change = observations[METRIC_CONSENSUS_REVISION_AMOUNT_7D]
        self.assertEqual(change.currency, "EUR")

    def test_no_currency_anywhere_stays_undeclared(self):
        row = json.loads(json.dumps(AAPL_PLUS_1Y_ROW))
        del row["epsTrend"]["epsTrendCurrency"]
        observations = ExtractionHarness(
            _trend(row), instrument_currency=None
        ).by_metric()
        snapshot = observations[METRIC_CONSENSUS_FORWARD_EPS_7D_AGO]
        self.assertIsNone(snapshot.currency)
        self.assertEqual(
            snapshot.currency_basis, CurrencyBasis.UNDECLARED.value
        )

    def test_revision_counts_ignore_the_block_s_currency_quirk(self):
        # The payload attaches "USD" to epsRevisions. A revision count is a
        # count of estimates, not a monetary amount, so it is published
        # currency-less regardless.
        observations = ExtractionHarness(
            _trend(AAPL_PLUS_1Y_ROW)
        ).by_metric()
        for metric, _ in REVISION_METRICS:
            with self.subTest(metric=metric):
                self.assertIsNone(observations[metric].currency)


class TestTheExistingConsensusMetricsAreUnchanged(unittest.TestCase):
    def test_the_sample_still_extracts_from_the_same_row(self):
        # d1ef0a6 pinned the analyst count and the estimate range. The new
        # extraction must not move them.
        observations = ExtractionHarness(
            _trend(AAPL_PLUS_1Y_ROW)
        ).by_metric()
        self.assertEqual(
            observations[METRIC_CONSENSUS_FORWARD_EPS_ANALYST_COUNT].value, 40.0
        )
        self.assertEqual(observations[METRIC_CONSENSUS_FORWARD_EPS_LOW].value, 8.69)
        self.assertEqual(
            observations[METRIC_CONSENSUS_FORWARD_EPS_HIGH].value, 10.67
        )
        for metric in (
            METRIC_CONSENSUS_FORWARD_EPS_ANALYST_COUNT,
            METRIC_CONSENSUS_FORWARD_EPS_LOW,
            METRIC_CONSENSUS_FORWARD_EPS_HIGH,
        ):
            with self.subTest(metric=metric):
                observation = observations[metric]
                self.assertEqual(observation.period_end, "2027-09-30")
                self.assertEqual(
                    observation.raw["period_end"], "2027-09-30"
                )


class TestContractRegistration(unittest.TestCase):
    NEW_METRICS = (
        [metric for metric, _ in REVISION_METRICS]
        + [metric for metric, _ in TREND_METRICS]
        + [metric for metric, _, _ in CHANGE_METRICS]
    )

    def test_every_new_metric_is_registered_with_definition_and_unit(self):
        for metric in self.NEW_METRICS:
            with self.subTest(metric=metric):
                self.assertIn(metric, CONTRACT_METRICS)
                self.assertIn(metric, METRIC_DEFINITIONS)
                self.assertIn(metric, METRIC_UNITS)
                self.assertTrue(METRIC_DEFINITIONS[metric])
                self.assertIn(METRIC_UNITS[metric], (Unit.COUNT.value, UNIT_PER_SHARE))

    def test_counts_are_count_and_amounts_are_per_share(self):
        for metric, _ in REVISION_METRICS:
            self.assertEqual(METRIC_UNITS[metric], Unit.COUNT.value)
        for metric in (
            [metric for metric, _ in TREND_METRICS]
            + [metric for metric, _, _ in CHANGE_METRICS]
        ):
            self.assertEqual(METRIC_UNITS[metric], UNIT_PER_SHARE)

    def test_available_observations_use_their_contract_ids(self):
        ids = {
            observation.observation_id
            for observation in ExtractionHarness(
                _trend(AAPL_PLUS_1Y_ROW)
            ).observations
            if observation.is_available
        }
        expected = {
            "obs-consensus-eps-up-revisions-7d-001",
            "obs-consensus-eps-up-revisions-30d-001",
            "obs-consensus-eps-down-revisions-7d-001",
            "obs-consensus-eps-down-revisions-30d-001",
            "obs-consensus-eps-trend-current-001",
            "obs-consensus-eps-7d-ago-001",
            "obs-consensus-eps-30d-ago-001",
            "obs-consensus-eps-60d-ago-001",
            "obs-consensus-eps-90d-ago-001",
            "obs-consensus-eps-change-7d-001",
            "obs-consensus-eps-change-30d-001",
            "obs-consensus-eps-change-60d-001",
            "obs-consensus-eps-change-90d-001",
        }
        self.assertTrue(expected <= ids, expected - ids)
        # The contract's own id map is untouched by the new metrics: the
        # 2.2.3 material evidence ids are exactly what they were.
        self.assertEqual(
            sorted(CONTRACT_OBSERVATION_IDS.values()),
            sorted(
                {
                    "ev-price-001",
                    "ev-current-eps-001",
                    "ev-forward-eps-001",
                    "ev-consensus-eps-001",
                    "ev-pe-band-001",
                    "ev-pfcf-band-001",
                    "ev-ps-band-001",
                    "ev-ev-ebitda-band-001",
                    "ev-fcf-001",
                    "ev-ebitda-001",
                    "ev-revenue-001",
                    "ev-enterprise-value-001",
                    "ev-market-cap-001",
                    "ev-metrics-001",
                }
            ),
        )


class TestViewAndContextPublication(unittest.TestCase):
    def _market_data(self, trend):
        harness = ExtractionHarness(trend)
        data = MarketData(
            ticker="AAPL",
            company_name="Apple Inc.",
            exchange="NASDAQ",
            currency="USD",
            price=333.63,
            price_date="2026-10-15",
            price_source="test",
            price_source_url=None,
            price_history=[],
            volume_history=[],
        )
        projected = _apply_observations_to_view(
            data,
            [
                observation
                for observation in harness.observations
                if observation.metric
                in set(CONSENSUS_EXTRA_METRICS) | {METRIC_CONSENSUS_FORWARD_EPS}
            ],
        )
        return data, projected, harness

    def test_the_view_fields_are_projected_from_the_observations(self):
        data, projected, harness = self._market_data(_trend(AAPL_PLUS_1Y_ROW))
        expected = {
            "consensus_forward_eps_up_revisions_7d": 0.0,
            "consensus_forward_eps_up_revisions_30d": 4.0,
            "consensus_forward_eps_down_revisions_7d": 2.0,
            "consensus_forward_eps_down_revisions_30d": 3.0,
            "consensus_forward_eps_down_revisions_90d": UNAVAILABLE,
            "consensus_forward_eps_trend_current": 9.58335,
            "consensus_forward_eps_7d_ago": 9.57579,
            "consensus_forward_eps_30d_ago": 9.57254,
            "consensus_forward_eps_60d_ago": 9.53948,
            "consensus_forward_eps_90d_ago": 9.69285,
        }
        for field, value in expected.items():
            with self.subTest(field=field):
                self.assertEqual(getattr(projected, field), value)

    def test_the_runner_selects_the_new_metrics_for_the_context(self):
        # The context carries the revision counts, the trend series and the
        # in-series differences as extra observations, exactly like the
        # consensus sample, so evidence_ids is untouched.
        self.assertTrue(
            set(CONSENSUS_REVISION_METRICS)
            <= set(CONSENSUS_EXTRA_METRICS)
        )
        self.assertTrue(
            set(CONSENSUS_TREND_METRICS) <= set(CONSENSUS_EXTRA_METRICS)
        )
        self.assertTrue(
            set(CONSENSUS_REVISION_AMOUNT_METRICS)
            <= set(CONSENSUS_EXTRA_METRICS)
        )
        self.assertTrue(
            set(CONSENSUS_SAMPLE_METRICS) <= set(CONSENSUS_EXTRA_METRICS)
        )
        data, _, _ = self._market_data(_trend(AAPL_PLUS_1Y_ROW))
        selected = [
            observation
            for observation in (
                data.observations.get(identifier)
                for identifier in data.observations.ids()
            )
            if observation is not None
            and observation.metric in CONSENSUS_EXTRA_METRICS
        ]
        selected_metrics = {observation.metric for observation in selected}
        self.assertEqual(selected_metrics, set(CONSENSUS_EXTRA_METRICS))
        self.assertTrue(selected)


class TestSerializationAndArchive(unittest.TestCase):
    def setUp(self):
        self.observations = [
            observation
            for observation in ExtractionHarness(
                _trend(AAPL_PLUS_1Y_ROW)
            ).observations
            if observation.is_available
        ]

    def test_contract_dicts_serialize_to_json_and_back(self):
        for observation in self.observations:
            with self.subTest(metric=observation.metric):
                payload = json.loads(
                    json.dumps(observation.contract_dict())
                )
                self.assertEqual(
                    payload["value"], observation.value
                )
                self.assertEqual(payload["unit"], observation.unit)
                self.assertEqual(payload["currency"], observation.currency)
                self.assertEqual(
                    payload["currency_basis"], observation.currency_basis
                )
                self.assertEqual(
                    payload["inputs"], list(observation.inputs)
                )

    def test_every_new_observation_survives_the_archive_round_trip(self):
        store = SQLiteArchive(":memory:")
        try:
            for observation in self.observations:
                store.record_observation("AAPL", observation)
            store.connection.commit()
            restored = {
                item.observation_id: item
                for item in store.all_observations("AAPL")
            }
            for observation in self.observations:
                with self.subTest(metric=observation.metric):
                    self.assertEqual(
                        restored[observation.observation_id], observation
                    )
        finally:
            store.close()

    def test_an_unavailable_observation_keeps_its_gap_through_the_context(
        self,
    ):
        # The absent downLast90days block is published as unavailable in the
        # context's observed section, not dropped and not zero-filled.
        harness = ExtractionHarness(_trend(AAPL_PLUS_1Y_ROW))
        absent = harness.by_metric()[METRIC_CONSENSUS_REVISIONS_DOWN_90D]
        self.assertFalse(absent.is_available)
        payload = absent.contract_dict()
        self.assertIsNone(payload["value"])
        self.assertEqual(payload["status"], "UNAVAILABLE")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
