"""R4: the web path uses the production point-in-time historical P/E reference.

R3 left a demonstrated gap: a live web submission for AAPL without an exit
multiple returned `NOT_COMPUTED` because only the vendor P/E band was consulted,
and that band is below the eligibility threshold. The runner already supports the
production point-in-time distribution; the web adapter did not ask for it.

These tests pin the wiring and the rules that surround it, deterministically and
without a network:

* a web request actually reaches the production historical P/E path,
* a qualified distribution is eligible and produces the expected scenario set,
* an under-qualified or unavailable distribution is never upgraded by having a
  median, and the vendor band is never silently substituted for it,
* user multiples stay separately labelled alongside production distribution rows,
* the compact summary the API reports matches the full dataset,
* unsupported tickers report the real unavailable state.

The live AAPL acceptance evidence lives in `docs/PROJECT-STATUS.md` and is
produced by `tests/test_r3_live_aapl_acceptance.py` with `ST_EVA_R3_LIVE=1`.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, ".")

from data_contract import (
    AvailabilityBasis,
    CurrencyBasis,
    METRIC_TRAILING_EPS,
    ObservationSet,
    SourceType,
    Unit,
    build_observation,
)
from historical_pe import (
    ISSUER_CONFIGS,
    STATUS_USABLE_FOR_REFERENCE,
    load_issuer_historical_pe,
    production_distribution_summary,
)
from reverse_requirements import exit_multiples_from_production_distribution
from st_eva_runner import (
    REGRESSION_TEST_FIXTURES,
    CompanyResolver,
    MarketData,
    UNAVAILABLE,
    _apply_observations_to_view,
    _build_reverse_requirements,
    price_observations,
)
from web.service_adapter import AnalysisServiceAdapter

AUDIT_DATASET = ISSUER_CONFIGS["AAPL"].data_dir


def _loading_patch(ticker: str):
    """Point a production issuer config at the frozen dataset copy in the repo."""
    config = ISSUER_CONFIGS[ticker]
    return patch.object(
        type(config),
        "data_dir",
        AUDIT_DATASET,
    )


class TestProductionDistributionSummary(unittest.TestCase):
    """The compact statement the API reports describes the same dataset."""

    def setUp(self):
        self.payload = load_issuer_historical_pe(ISSUER_CONFIGS["AAPL"]).to_dict()

    def test_summary_reports_identity_eligibility_and_provenance(self):
        summary = production_distribution_summary(self.payload)
        distribution = self.payload["distribution"]
        self.assertEqual(summary["status"], STATUS_USABLE_FOR_REFERENCE)
        self.assertTrue(summary["usable_for_reference"])
        self.assertEqual(summary["sample_count"], distribution["sample_count"])
        self.assertEqual(summary["total_evaluations"], distribution["total_evaluations"])
        self.assertEqual(
            summary["min_observations_required"], distribution["min_observations_required"]
        )
        self.assertEqual(summary["period_start"], distribution["period_start"])
        self.assertEqual(summary["period_end"], distribution["period_end"])
        self.assertTrue(summary["evaluation_schedule_description"])
        self.assertEqual(summary["issuer_id"], self.payload["issuer_id"])
        self.assertEqual(summary["instrument_id"], self.payload["instrument_id"])
        self.assertEqual(summary["input_set_id"], self.payload["input_set_id"])
        self.assertEqual(summary["percentiles"], distribution["percentiles"])
        # The per-evaluation detail is what the summary exists to leave out.
        self.assertNotIn("observations", summary)

    def test_summary_of_missing_payload_is_none(self):
        self.assertIsNone(production_distribution_summary(None))
        self.assertIsNone(production_distribution_summary({}))

    def test_summary_of_unavailable_state_keeps_the_reason(self):
        summary = production_distribution_summary(
            {
                "distribution": {
                    "status": "UNAVAILABLE",
                    "usable_for_reference": False,
                    "sample_count": 0,
                    "reason_code": "REASON_INSUFFICIENT_OBSERVATIONS",
                    "reason_detail": "Production historical P/E dataset is not yet established.",
                }
            }
        )
        self.assertEqual(summary["status"], "UNAVAILABLE")
        self.assertFalse(summary["usable_for_reference"])
        self.assertEqual(
            summary["reason_detail"],
            "Production historical P/E dataset is not yet established.",
        )


class TestProductionDistributionEligibility(unittest.TestCase):
    """The existing eligibility gate is not relaxed by the web path."""

    def setUp(self):
        self.payload = load_issuer_historical_pe(ISSUER_CONFIGS["AAPL"]).to_dict()
        self.quarterly_payload = load_issuer_historical_pe(
            ISSUER_CONFIGS["AAPL"], enable_furnished=False
        ).to_dict()

    def test_qualified_distribution_produces_labeled_scenarios(self):
        multiples, unavailable = exit_multiples_from_production_distribution(
            self.payload["distribution"]
        )
        self.assertEqual(unavailable, [])
        self.assertTrue(multiples)
        for multiple in multiples:
            self.assertEqual(multiple.source, "production_historical_pe_percentile")
            self.assertEqual(multiple.eligibility_state, "ELIGIBLE_PRODUCTION_DISTRIBUTION")
            self.assertTrue(multiple.usable_for_reference)
            self.assertFalse(multiple.is_user_assumption)
            self.assertEqual(multiple.sample_size, self.payload["distribution"]["sample_count"])
            self.assertIn("production historical P/E", multiple.sample_period)

    def test_insufficient_distribution_is_never_upgraded_by_a_median(self):
        distribution = self.quarterly_payload["distribution"]
        # The negative path keeps a median but under-qualifies the sample.
        self.assertIsNotNone((distribution.get("percentiles") or {}).get("median"))
        self.assertLess(distribution["sample_count"], distribution["min_observations_required"])
        multiples, unavailable = exit_multiples_from_production_distribution(distribution)
        self.assertEqual(multiples, [])
        self.assertEqual(len(unavailable), 1)
        item = unavailable[0]
        self.assertEqual(item["reason_kind"], "INSUFFICIENT_OBSERVATIONS")
        self.assertEqual(
            item["item"], "exit_multiple.production_historical_pe_scenarios"
        )
        self.assertIn("descriptive statistic only", item["reason"])

    def test_missing_distribution_produces_nothing(self):
        multiples, unavailable = exit_multiples_from_production_distribution(None)
        self.assertEqual(multiples, [])
        self.assertEqual(unavailable, [])


class TestProductionDistributionInReport(unittest.TestCase):
    """The engine report carries the compact summary beside the full dataset."""

    def _market_data(self):
        data = CompanyResolver._from_fixture(REGRESSION_TEST_FIXTURES["MSFT"])
        data.ticker = "MSFT"
        data.current_eps = 12.40
        data.forward_eps = UNAVAILABLE
        data.consensus_forward_eps = UNAVAILABLE
        # An undersized vendor band, the state a live AAPL acquisition reports.
        data.historical_pe_band = {
            "percentile_10": 15.0,
            "percentile_25": 18.0,
            "median": 22.0,
            "percentile_75": 26.0,
            "percentile_90": 30.0,
            "observations": 8,
        }
        return data

    def _build(self, production_payload, reference_multiple=None):
        data = self._market_data()
        analysis = {"observed_valuation": {}, "fundamental_snapshot": {}}
        return _build_reverse_requirements(
            data,
            analysis,
            horizons_years=(2.0,),
            required_returns=(0.10,),
            reference_multiple=reference_multiple,
            reference_multiples=None,
            pfcf_multiple=None,
            ev_ebitda_multiple=None,
            ps_multiple=None,
            include_risk_free_rates=False,
            include_dcf=False,
            beta=None,
            equity_risk_premium=None,
            risk_free_tenor="10_YEAR",
            production_historical_pe=production_payload,
            prefer_eps_anchor="trailing",
            user_eps=None,
        )

    def test_report_carries_summary_and_matrix_from_the_distribution(self):
        payload = load_issuer_historical_pe(ISSUER_CONFIGS["MSFT"]).to_dict()
        report = self._build(payload)
        summary = report["production_historical_pe_summary"]
        self.assertIsNotNone(summary)
        self.assertEqual(summary["instrument_id"], "MSFT")
        self.assertEqual(summary["sample_count"], payload["distribution"]["sample_count"])

        rows = report["reverse_requirements_matrix"]
        if summary["usable_for_reference"]:
            self.assertEqual(report["status"], "COMPUTED")
            self.assertTrue(rows)
            # Only the production distribution contributes: the undersized band
            # is not silently substituted for it.
            sources = {row["exit_multiple"]["source"] for row in rows}
            self.assertEqual(sources, {"production_historical_pe_percentile"})
            for row in rows:
                self.assertFalse(row["exit_multiple"]["is_user_assumption"])
                self.assertEqual(
                    row["exit_multiple"]["eligibility_state"],
                    "ELIGIBLE_PRODUCTION_DISTRIBUTION",
                )
                self.assertEqual(
                    row["exit_multiple"]["sample_size"],
                    payload["distribution"]["sample_count"],
                )
            band_items = [
                item
                for item in report["unavailable"]
                if item.get("item") == "exit_multiple.band_scenarios"
            ]
            self.assertTrue(
                band_items, "the undersized band must be reported as excluded"
            )
            self.assertEqual(band_items[0].get("reason_kind"), "INSUFFICIENT_OBSERVATIONS")
        else:
            self.assertEqual(rows, [])
            items = [
                item
                for item in report["unavailable"]
                if item.get("item") == "exit_multiple.production_historical_pe_scenarios"
            ]
            self.assertTrue(items)

    def test_report_keeps_user_multiple_apart_from_distribution_rows(self):
        payload = load_issuer_historical_pe(ISSUER_CONFIGS["MSFT"]).to_dict()
        report = self._build(payload, reference_multiple=41.0)
        rows = report["reverse_requirements_matrix"]
        self.assertTrue(rows)
        by_source = {}
        for row in rows:
            by_source.setdefault(row["exit_multiple"]["source"], []).append(row)
        self.assertIn("user_supplied", by_source)
        for row in by_source["user_supplied"]:
            self.assertTrue(row["exit_multiple"]["is_user_assumption"])
            self.assertEqual(
                row["exit_multiple"]["eligibility_state"], "USER_SPECIFIED"
            )
            self.assertAlmostEqual(row["exit_multiple"]["value"], 41.0, places=9)
        for row in by_source.get("production_historical_pe_percentile", []):
            self.assertFalse(row["exit_multiple"]["is_user_assumption"])
            self.assertNotEqual(row["exit_multiple"]["value"], 41.0)

    def test_report_with_under_qualified_distribution_leaves_matrix_uncomputed(self):
        # A distribution with a median but an under-qualified sample. Constructed
        # here rather than taken from a dataset so the shape of the ineligible
        # state is stated explicitly and is not tied to one issuer's file.
        payload = {
            "issuer_id": "CIK0000789019",
            "instrument_id": "MSFT",
            "input_set_id": "test-input-set",
            "content_hash": "0" * 64,
            "distribution": {
                "metric_id": "TTM_GAAP_DILUTED_PE",
                "status": "DESCRIPTIVE_ONLY_INSUFFICIENT_OBSERVATIONS",
                "usable_for_reference": False,
                "sample_count": 17,
                "total_evaluations": 36,
                "min_observations_required": 20,
                "percentiles": {
                    "10th": 18.70,
                    "25th": 21.00,
                    "median": 24.50,
                    "75th": 27.00,
                    "90th": 29.10,
                },
                "period_start": "2018-01-02",
                "period_end": "2026-07-31",
                "sampling_cadence": "PERIODIC_FILING_USABLE_DATES",
                "evaluation_schedule_description": (
                    "Evaluated on periodic SEC filing and earnings release usable dates."
                ),
                "excluded_observations": [{"reason_code": "REASON_MISSING_Q4_EPS"}],
            },
        }
        report = self._build(payload)
        self.assertEqual(report["status"], "NOT_COMPUTED")
        self.assertEqual(report["matrix_size"], 0)
        self.assertEqual(report["reverse_requirements_matrix"], [])
        items = [
            item
            for item in report["unavailable"]
            if item.get("item") == "exit_multiple.production_historical_pe_scenarios"
        ]
        self.assertTrue(items)
        self.assertEqual(items[0].get("reason_kind"), "INSUFFICIENT_OBSERVATIONS")
        self.assertIn("17", items[0]["reason"])
        self.assertIn("descriptive statistic only", items[0]["reason"])


LIVE_PRICE = 271.44
LIVE_TRAILING_EPS = 7.31


def _live_market_data(ticker: str) -> MarketData:
    """A live-shaped acquisition, so no fixture stands in for a market quote."""
    data = MarketData(
        ticker=ticker,
        company_name=f"{ticker} (Live Acquired)",
        exchange="NMS",
        currency="USD",
        price=LIVE_PRICE,
        price_date="2026-10-09",
        price_source="Yahoo Finance chart API",
        price_source_url="https://query1.finance.yahoo.com/v8/finance/chart/",
        current_eps=LIVE_TRAILING_EPS,
        forward_eps=UNAVAILABLE,
        consensus_forward_eps=UNAVAILABLE,
        next_event=UNAVAILABLE,
        next_event_status="Unconfirmed",
        current_market_cap=3.8e12,
        # The undersized vendor band a live acquisition reports. It is kept in
        # the stub so the band and the production distribution stay distinct.
        historical_pe_band={
            "percentile_10": 15.0,
            "percentile_25": 18.0,
            "median": 22.0,
            "percentile_75": 26.0,
            "percentile_90": 30.0,
            "observations": 8,
        },
        price_history=[
            (f"2026-10-{day:02d}", 265.0 + 2.0 * index)
            for index, day in enumerate(range(1, 10), start=1)
        ],
        volume_history=[float(40_000_000 + 1_000_000 * index) for index in range(9)],
        source_type="API_LIVE",
        provider="YahooFinance+YahooFinanceFundamentals",
    )
    return _apply_observations_to_view(data, price_observations(data))


class _StubProvider:
    def fetch(self, ticker: str) -> MarketData:
        return _live_market_data(ticker)


class TestWebPathUsesProductionDistribution(unittest.TestCase):
    """The web request reaches the production path and reports its state."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="r4-web-")
        self.archives_dir = Path(self._tmp.name)
        self.adapter = AnalysisServiceAdapter(archives_dir=str(self.archives_dir))
        self._provider_patch = patch(
            "st_eva_runner.YahooFinanceProvider", return_value=_StubProvider()
        )
        self._sec_patch = patch(
            "st_eva_runner._acquire_sec_evidence",
            return_value={
                "observations": [],
                "documents": [],
                "cik": None,
                "entity_name": None,
                "cross_validation": {},
                "acquired": False,
            },
        )
        self._provider_patch.start()
        self._sec_patch.start()
        self.addCleanup(self._provider_patch.stop)
        self.addCleanup(self._sec_patch.stop)
        self.addCleanup(self._tmp.cleanup)

    def test_web_request_passes_through_the_production_path(self):
        calls = []

        def loader(config, enable_furnished=True):
            calls.append((config.ticker, enable_furnished))
            return load_issuer_historical_pe(config, enable_furnished)

        with patch("historical_pe.load_issuer_historical_pe", loader):
            dto = self.adapter.run_analysis_pipeline(
                ticker="MSFT", mode="live"
            )
        # The run loads the production distribution, and the replay that
        # reconciles the archived run against the archive loads it again: the
        # rebuild reads the same committed dataset the run read, so the
        # reference the rebuild selects is the reference the run selected.
        # Every call is the same issuer under the same furnished-quarter rule.
        self.assertTrue(calls, "the web request must reach the production path")
        self.assertEqual(set(calls), {("MSFT", True)})
        self.assertIsNotNone(
            dto.production_historical_pe,
            "the API must report the distribution state from the production path",
        )

    def test_undersized_vendor_band_is_not_substituted_for_the_distribution(self):
        dto = self.adapter.run_analysis_pipeline(ticker="MSFT", mode="live")
        rr = dto.reverse_requirements
        self.assertIsNotNone(rr)
        summary = dto.production_historical_pe
        self.assertIsNotNone(summary)
        band_items = [
            item for item in rr.unavailable if item.get("item") == "exit_multiple.band_scenarios"
        ]
        self.assertTrue(
            band_items, "the vendor band's exclusion must be reported, not hidden"
        )
        self.assertEqual(band_items[0].get("reason_kind"), "INSUFFICIENT_OBSERVATIONS")

        if summary.usable_for_reference:
            self.assertEqual(rr.status, "COMPUTED")
            rows = rr.reverse_requirements_matrix
            self.assertTrue(rows)
            sources = {row.exit_multiple.source for row in rows}
            # Only the production distribution, never the band.
            self.assertEqual(sources, {"production_historical_pe_percentile"})
        else:
            self.assertEqual(rr.status, "NOT_COMPUTED")
            self.assertEqual(rr.matrix_size, 0)

    def test_unsupported_ticker_reports_unavailable_state(self):
        dto = self.adapter.run_analysis_pipeline(ticker="ZZQNOSUCH", mode="live")
        summary = dto.production_historical_pe
        self.assertIsNotNone(summary)
        self.assertEqual(summary.status, "UNAVAILABLE")
        self.assertFalse(summary.usable_for_reference)
        self.assertIn("not yet established", summary.reason_detail or "")

        rr = dto.reverse_requirements
        self.assertIsNotNone(rr)
        self.assertEqual(rr.status, "NOT_COMPUTED")
        items = {item.get("item") for item in rr.unavailable}
        self.assertIn("exit_multiple", items)

    def test_user_multiple_stays_a_separate_assumption(self):
        dto = self.adapter.run_analysis_pipeline(
            ticker="MSFT", mode="live", reference_multiple=55.0
        )
        rr = dto.reverse_requirements
        self.assertIsNotNone(rr)
        summary = dto.production_historical_pe
        by_source = {}
        for row in rr.reverse_requirements_matrix:
            by_source.setdefault(row.exit_multiple.source, []).append(row)
        user_rows = by_source.get("user_supplied") or []
        self.assertTrue(user_rows, "the supplied multiple must appear as its own rows")
        for row in user_rows:
            self.assertTrue(row.exit_multiple.is_user_assumption)
            self.assertEqual(
                row.exit_multiple.eligibility_state, "USER_SPECIFIED"
            )
            self.assertAlmostEqual(row.exit_multiple.value, 55.0, places=9)
        if summary and summary.usable_for_reference:
            distributed = by_source.get("production_historical_pe_percentile") or []
            self.assertTrue(distributed, "production rows must survive alongside a user value")
            for row in distributed:
                self.assertFalse(row.exit_multiple.is_user_assumption)


if __name__ == "__main__":
    unittest.main()
