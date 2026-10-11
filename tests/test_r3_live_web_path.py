"""R3: the live-data web path, exercised deterministically and offline.

The real AAPL live acceptance evidence lives in `docs/PROJECT-STATUS.md`. These
tests pin the *wiring* the acceptance run depends on, without depending on
today's market: the market provider is replaced by a live-shaped (API_LIVE)
acquisition, the SEC evidence layer is kept empty, and the archive directory is
a temporary directory so no persistent database is touched.

They assert the contract rather than market values: that a `mode="live"`
submission reaches the engine, that the selected assumptions decide the scenario
cross-product and the derived outputs, that price/EPS evidence keeps its live
provider identity, that the historical band declares its observation count and
eligibility instead of being used as a reference, that a vendor EPS keeps no SEC
source attribution, and that unavailable scenarios stay visible with reasons.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from st_eva_runner import (
    MarketData,
    UNAVAILABLE,
    _apply_observations_to_view,
    price_observations,
)
from web.service_adapter import AnalysisServiceAdapter

LIVE_PRICE = 271.44
LIVE_TRAILING_EPS = 7.31
LIVE_FORWARD_EPS = 8.02


def _live_market_data(ticker: str) -> MarketData:
    """The shape of a live acquisition, not a regression fixture."""
    data = MarketData(
        ticker=ticker,
        company_name="Live Acquired Co",
        exchange="NMS",
        currency="USD",
        price=LIVE_PRICE,
        price_date="2026-10-09",
        price_source="Yahoo Finance chart API",
        price_source_url="https://query1.finance.yahoo.com/v8/finance/chart/",
        current_eps=LIVE_TRAILING_EPS,
        forward_eps=LIVE_FORWARD_EPS,
        consensus_forward_eps=LIVE_FORWARD_EPS * 1.05,
        next_event=UNAVAILABLE,
        next_event_status="Unconfirmed",
        historical_pe_band={
            "percentile_5": 12.0,
            "percentile_10": 15.0,
            "percentile_25": 18.0,
            "median": 22.0,
            "percentile_75": 26.0,
            "percentile_90": 30.0,
            "observations": 4,
        },
        current_fcf=110.4e9,
        current_ebitda=145.9e9,
        current_revenue=402.7e9,
        current_enterprise_value=3.9e12,
        current_market_cap=3.8e12,
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
    def fetch(self, _ticker: str) -> MarketData:
        return _live_market_data(_ticker)


class TestLiveWebPathWiring(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="r3-live-web-")
        self.archives_dir = Path(self._tmp.name)
        self.adapter = AnalysisServiceAdapter(archives_dir=str(self.archives_dir))
        # The market provider is the only live boundary under test; the SEC
        # evidence layer is left empty so the test never needs the network.
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

    def test_live_submission_uses_the_selected_assumptions(self):
        dto = self.adapter.run_analysis_pipeline(
            ticker="LIVECO",
            mode="live",
            reference_multiple=24.0,
            reverse_horizons=[2.0, 3.0],
            required_returns=[0.10, 0.12],
        )
        self.assertEqual(dto.source_identifiers[0], "YahooFinance+YahooFinanceFundamentals")
        self.assertEqual(dto.valuation_summary.current_price, LIVE_PRICE)
        self.assertEqual(dto.valuation_summary.currency, "USD")
        self.assertEqual(dto.as_of, "2026-10-09")

        rr = dto.reverse_requirements
        self.assertIsNotNone(rr)
        self.assertEqual(rr.formula_version, "reverse-requirements/1.1")
        self.assertEqual(rr.status, "COMPUTED")
        # The cross-product of the requested assumptions: 1 multiple x 2 horizons x 2 returns.
        self.assertEqual(rr.matrix_size, 4)
        self.assertEqual(len(rr.reverse_requirements_matrix), 4)

        for row in rr.reverse_requirements_matrix:
            self.assertAlmostEqual(row.price, LIVE_PRICE, places=9)
            self.assertAlmostEqual(row.start_eps.value, LIVE_TRAILING_EPS, places=9)
            self.assertIn(row.horizon_years, (2.0, 3.0))
            self.assertIn(row.required_return, (0.10, 0.12))
            self.assertAlmostEqual(row.exit_multiple.value, 24.0, places=9)
            self.assertEqual(row.exit_multiple.source, "user_supplied")
            self.assertEqual(row.exit_multiple.eligibility_state, "USER_SPECIFIED")
            self.assertTrue(row.exit_multiple.is_user_assumption)
            self.assertEqual(row.evidence.eps_evidence.source_type, "API_LIVE")
            self.assertEqual(
                row.evidence.price_evidence.source_type, "API_LIVE"
            )
            self.assertIn("YahooFinance", row.evidence.eps_evidence.provider)
            self.assertIsNone(
                row.evidence.eps_evidence.sec_fact,
                "a vendor EPS must not inherit a filing as its source",
            )
            self.assertTrue(
                any(
                    "Direct SEC source of selected EPS not established" in item
                    for item in row.evidence.missing_or_unvalidated
                ),
                row.evidence.missing_or_unvalidated,
            )

        # Deterministic outputs from the row's own operands.
        by_key = {
            (row.horizon_years, row.required_return): row for row in rr.reverse_requirements_matrix
        }
        row = by_key[(3.0, 0.12)]
        expected_exit_price = LIVE_PRICE * (1.12 ** 3)
        self.assertAlmostEqual(
            row.required_exit_price, expected_exit_price, places=6
        )
        self.assertAlmostEqual(
            row.required_terminal_eps, expected_exit_price / 24.0, places=6
        )
        steps = {s.step_id: s for s in row.calculation_steps}
        self.assertEqual(len(steps), 4)
        for step in steps.values():
            self.assertTrue(step.reproducible)
        self.assertAlmostEqual(
            steps["required_exit_price"].output_value, expected_exit_price, places=6
        )
        self.assertEqual(
            steps["required_exit_price"].operands["required_return"], 0.12
        )

    def test_live_run_reports_band_eligibility_and_unavailable_scenarios(self):
        dto = self.adapter.run_analysis_pipeline(
            ticker="LIVECO",
            mode="live",
            reverse_horizons=[3.0],
            required_returns=[0.10],
        )
        rr = dto.reverse_requirements
        self.assertIsNotNone(rr)
        # No reference multiple was supplied, so the band below 20 usable
        # observations is reported as ineligible and the matrix is uncomputable
        # rather than silently built on a descriptive statistic.
        self.assertEqual(rr.status, "NOT_COMPUTED")
        self.assertEqual(rr.matrix_size, 0)
        self.assertEqual(len(rr.reverse_requirements_matrix), 0)
        unavailable = rr.unavailable or []
        band_items = [
            item
            for item in unavailable
            if isinstance(item, dict) and item.get("item") == "exit_multiple.band_scenarios"
        ]
        self.assertTrue(band_items, "the band's exclusion must be stated")
        self.assertEqual(band_items[0].get("reason_kind"), "INSUFFICIENT_OBSERVATIONS")
        self.assertIn("4", band_items[0].get("reason") or "")
        self.assertIn("descriptive statistic only", band_items[0].get("reason") or "")

    def test_live_run_stays_inside_the_isolated_archive(self):
        dto = self.adapter.run_analysis_pipeline(
            ticker="LIVECO",
            mode="live",
            reference_multiple=24.0,
            reverse_horizons=[3.0],
            required_returns=[0.10],
        )
        self.assertIsNotNone(dto.reverse_requirements)
        archive_path = self.adapter.get_archive_path("LIVECO")
        self.assertTrue(archive_path.exists())
        # The isolated directory is the only place this run wrote to.
        self.assertEqual(archive_path.parent, self.archives_dir)
        self.assertIn(str(self.archives_dir), str(archive_path))
        self.assertFalse(Path("data/archives/LIVECO.sqlite").exists())
        # No stray context file survives next to the archive.
        self.assertEqual(len(list(self.archives_dir.glob("*.context.json"))), 0)


if __name__ == "__main__":
    unittest.main()
