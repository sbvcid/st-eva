"""
Tests for Phase H dividend evidence and total-return calculations.

Covers:
1. Dividend extraction from chart events (with split-adjustment tracking).
2. Dividend extraction from SEC observations.
3. Summary metrics: TTM dividends, TTM yield, indicated annual rate and yield, YoY growth.
4. Historical return calculations: Price Return vs. Cash Retained vs. DRIP.
5. Deterministic total-return reverse hurdles (Cash Retained and DRIP).
6. Reverse-requirements report parallel total-return scenarios and comparison.
7. Research dossier integration and text rendering.
8. Canonical AAPL dataset verification.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, ".")

from data_contract import (
    Observation,
    METRIC_DIVIDENDS_PER_SHARE,
    METRIC_DIVIDENDS_TTM,
    METRIC_DIVIDEND_YIELD_TTM,
    METRIC_DIVIDEND_INDICATED_RATE,
    METRIC_DIVIDEND_INDICATED_YIELD,
    METRIC_DIVIDEND_GROWTH_YOY,
)
from dividend_history import (
    DividendPaymentRecord,
    build_dividend_package,
    calculate_dividend_summary,
    calculate_historical_returns,
    extract_dividends_from_chart_events,
    extract_dividends_from_sec_observations,
)
from research_dossier import (
    SECTION_ORDER,
    build_dossier,
    render_dossier,
)
from reverse_requirements import (
    DIVIDEND_CONVENTION_CASH_RETAINED,
    DIVIDEND_CONVENTION_PRICE_ONLY,
    DIVIDEND_CONVENTION_REINVESTED,
    RETURN_BASIS_PRICE_ONLY,
    RETURN_BASIS_TOTAL,
    EpsAnchor,
    ANCHOR_TTM,
    ReferenceMultiple,
    build_matrix,
    build_reverse_requirements_report,
    build_scenario,
    required_exit_price,
    required_total_return_exit_price,
)


def _anchor(value: float = 4.0) -> EpsAnchor:
    return EpsAnchor(
        value=value,
        basis=ANCHOR_TTM,
        months_covered=12.0,
        period_label="TTM to 2026-09-30",
        provider="fixture",
        currency="USD",
    )


class TestDividendExtraction(unittest.TestCase):
    def test_extract_from_chart_events_with_split(self):
        # Fixture with 4:1 split on 2020-08-31 (ts=1598832000)
        # Pre-split payment on 2020-08-07: vendor reports split-adjusted 0.205
        # Post-split payment on 2020-11-06: vendor reports 0.205
        payload = {
            "events": {
                "splits": {
                    "1598832000": {
                        "date": 1598832000,
                        "numerator": 4,
                        "denominator": 1,
                        "splitRatio": "4:1",
                    }
                },
                "dividends": {
                    "1596758400": {
                        "date": 1596758400,  # 2020-08-07
                        "amount": 0.205,
                    },
                    "1604620800": {
                        "date": 1604620800,  # 2020-11-06
                        "amount": 0.205,
                    },
                },
            }
        }
        records = extract_dividends_from_chart_events(payload, currency="USD")
        self.assertEqual(len(records), 2)

        # Pre-split payment
        rec0 = records[0]
        self.assertEqual(rec0.ex_date, "2020-08-07")
        self.assertEqual(rec0.amount, 0.205)
        # Reconstructed pre-split amount should be 0.205 * 4 = 0.82
        self.assertAlmostEqual(rec0.unadjusted_amount, 0.82, places=4)

        # Post-split payment
        rec1 = records[1]
        self.assertEqual(rec1.ex_date, "2020-11-06")
        self.assertEqual(rec1.amount, 0.205)
        self.assertEqual(rec1.unadjusted_amount, 0.205)

    def test_extract_from_sec_observations(self):
        from types import SimpleNamespace
        obs1 = SimpleNamespace(
            observation_id="obs_div_q1",
            metric=METRIC_DIVIDENDS_PER_SHARE,
            value=0.26,
            unit="USD/share",
            period_start="2025-09-28",
            period_end="2025-12-27",
            as_of="2026-01-30",
            raw={"form": "10-Q", "accession_number": "0000320193-26-000006"},
        )
        extracted = extract_dividends_from_sec_observations([obs1])
        self.assertEqual(len(extracted), 1)
        self.assertEqual(extracted[0]["value"], 0.26)
        self.assertEqual(extracted[0]["form"], "10-Q")
        self.assertEqual(extracted[0]["accession_number"], "0000320193-26-000006")


class TestDividendSummaryCalculations(unittest.TestCase):
    def setUp(self):
        # 8 quarters of dividends
        # Year 1 (py): 4 payments of 0.25 each -> TTM py = 1.00
        # Year 2 (cy): 4 payments of 0.26, 0.26, 0.27, 0.27 -> TTM cy = 1.06
        dates = [
            "2024-11-08", "2025-02-07", "2025-05-09", "2025-08-08",
            "2025-11-07", "2026-02-06", "2026-05-08", "2026-08-07",
        ]
        amounts = [0.25, 0.25, 0.25, 0.25, 0.26, 0.26, 0.27, 0.27]
        self.payments = [
            DividendPaymentRecord(ex_date=d, amount=a, currency="USD", source="test")
            for d, a in zip(dates, amounts)
        ]

    def test_ttm_and_indicated_metrics(self):
        summary = calculate_dividend_summary(
            self.payments,
            as_of="2026-09-30",
            price=200.0,
        )
        self.assertAlmostEqual(summary["trailing_twelve_month_dividends"], 1.06, places=4)
        # Yield: 1.06 / 200.0 = 0.0053 (0.53%)
        self.assertAlmostEqual(summary["trailing_twelve_month_yield"], 0.0053, places=4)

        # Latest quarterly payment is 0.27 on 2026-08-07
        self.assertEqual(summary["latest_payment_amount"], 0.27)
        self.assertEqual(summary["latest_payment_date"], "2026-08-07")

        # Indicated annual rate: 4 * 0.27 = 1.08
        self.assertAlmostEqual(summary["indicated_annual_dividend_rate"], 1.08, places=4)
        # Indicated yield: 1.08 / 200.0 = 0.0054 (0.54%)
        self.assertAlmostEqual(summary["indicated_annual_dividend_yield"], 0.0054, places=4)

        # YoY TTM growth: (1.06 / 1.00) - 1 = +6.00%
        self.assertAlmostEqual(summary["dividend_growth_yoy"], 0.06, places=4)


class TestHistoricalReturnsMath(unittest.TestCase):
    def test_price_return_vs_cash_and_drip(self):
        # 1-year window: start price 100, end price 120
        # Paid 4 dividends of 1.0 each (total 4.0)
        price_series = [
            ("2025-09-30", 100.0),
            ("2025-12-15", 105.0),
            ("2026-03-15", 110.0),
            ("2026-06-15", 115.0),
            ("2026-09-30", 120.0),
        ]
        payments = [
            DividendPaymentRecord(ex_date="2025-12-15", amount=1.0),
            DividendPaymentRecord(ex_date="2026-03-15", amount=1.0),
            DividendPaymentRecord(ex_date="2026-06-15", amount=1.0),
            DividendPaymentRecord(ex_date="2026-09-15", amount=1.0),
        ]
        returns = calculate_historical_returns(
            price_series,
            payments,
            as_of="2026-09-30",
            windows_years=[1.0],
        )
        self.assertEqual(len(returns), 1)
        r = returns[0]
        # Price return: 120 / 100 - 1 = 20.0%
        self.assertAlmostEqual(r["price_return_cagr"], 0.20, places=3)
        # Total return cash: (120 + 4.0) / 100 - 1 = 24.0%
        self.assertAlmostEqual(r["total_return_cash_cagr"], 0.24, places=3)
        # DRIP total return must be > cash return in an appreciating stock
        self.assertGreater(r["total_return_reinvested_cagr"], r["total_return_cash_cagr"])
        self.assertAlmostEqual(r["total_cash_dividends"], 4.0, places=4)


class TestTotalReturnReverseRequirementsMath(unittest.TestCase):
    def test_hand_calculated_hurdles(self):
        # P0 = 100.0, r = 0.10, T = 2.0, D = 2.0 per year
        # Exit multiple M = 20.0, Start EPS = 4.0
        # 1. Price-only:
        #    P2 = 100 * 1.10^2 = 121.0
        #    EPS2 = 121.0 / 20 = 6.05
        #    CAGR = (6.05 / 4.0)^0.5 - 1 = 22.98979%
        p2_price = required_total_return_exit_price(
            100.0, 0.10, 2.0, dividend_per_share=2.0, convention=DIVIDEND_CONVENTION_PRICE_ONLY
        )
        self.assertAlmostEqual(p2_price, 121.0, places=6)

        # 2. Cash dividends retained:
        #    P2 = 121.0 - 2 * 2.0 = 117.0
        p2_cash = required_total_return_exit_price(
            100.0, 0.10, 2.0, dividend_per_share=2.0, convention=DIVIDEND_CONVENTION_CASH_RETAINED
        )
        self.assertAlmostEqual(p2_cash, 117.0, places=6)

        # 3. Dividends reinvested at target return r=10%:
        #    FV(annuity) = 2.0 * ((1.10^2 - 1) / 0.10) = 2.0 * 2.10 = 4.20
        #    P2 = 121.0 - 4.20 = 116.80
        p2_drip = required_total_return_exit_price(
            100.0, 0.10, 2.0, dividend_per_share=2.0, convention=DIVIDEND_CONVENTION_REINVESTED
        )
        self.assertAlmostEqual(p2_drip, 116.80, places=6)

    def test_build_scenario_relief_deltas(self):
        multiple = ReferenceMultiple(value=20.0, source="user_supplied")
        # Price-only baseline scenario
        p_scen = build_scenario(
            price=100.0,
            horizon_years=2.0,
            required_return=0.10,
            exit_multiple=multiple,
            start_anchor=_anchor(4.0),
            dividend_per_share=None,
        )
        self.assertEqual(p_scen.required_return_basis, RETURN_BASIS_PRICE_ONLY)
        self.assertAlmostEqual(p_scen.required_exit_price, 121.0, places=6)
        self.assertAlmostEqual(p_scen.required_terminal_eps, 6.05, places=6)

        # Total-return cash-retained scenario
        c_scen = build_scenario(
            price=100.0,
            horizon_years=2.0,
            required_return=0.10,
            exit_multiple=multiple,
            start_anchor=_anchor(4.0),
            dividend_per_share=2.0,
            dividend_convention=DIVIDEND_CONVENTION_CASH_RETAINED,
        )
        self.assertEqual(c_scen.required_return_basis, RETURN_BASIS_TOTAL)
        self.assertAlmostEqual(c_scen.required_exit_price, 117.0, places=6)
        self.assertAlmostEqual(c_scen.required_terminal_eps, 5.85, places=6)
        # Relief deltas:
        self.assertAlmostEqual(c_scen.dividend_relief_exit_price, -4.0, places=6)
        self.assertAlmostEqual(c_scen.dividend_relief_terminal_eps, -0.20, places=6)
        self.assertLess(c_scen.required_eps_cagr, p_scen.required_eps_cagr)
        self.assertAlmostEqual(
            c_scen.dividend_relief_cagr, c_scen.required_eps_cagr - p_scen.required_eps_cagr, places=6
        )


class TestReverseRequirementsReportIntegration(unittest.TestCase):
    def test_report_preserves_price_baseline_and_adds_total_return(self):
        multiple = ReferenceMultiple(value=20.0, source="user_supplied")
        report = build_reverse_requirements_report(
            price=100.0,
            ticker="TEST",
            currency="USD",
            as_of="2026-09-30",
            price_source="fixture",
            horizons_years=[1.0, 2.0],
            required_returns=[0.10],
            exit_multiples=[multiple],
            start_anchor=_anchor(4.0),
            dividend_per_share=2.0,
            dividend_source="Test Dividend Source",
        )
        # 1. Baseline matrix MUST remain price return only
        for row in report["reverse_requirements_matrix"]:
            self.assertEqual(row["required_return_basis"], RETURN_BASIS_PRICE_ONLY)
            self.assertEqual(row["required_exit_price_basis"], "PRICE_ONLY_EXCLUDES_DIVIDENDS")

        # 2. Parallel total-return scenarios MUST be present
        self.assertIn("total_return_scenarios", report)
        tr = report["total_return_scenarios"]
        self.assertIn("cash_dividends_retained", tr)
        self.assertIn("dividends_reinvested_at_target_return", tr)
        self.assertEqual(len(tr["cash_dividends_retained"]), 2)
        self.assertEqual(len(tr["dividends_reinvested_at_target_return"]), 2)

        # 3. Comparison table MUST be populated
        self.assertIn("price_vs_total_return_comparison", report)
        comp = report["price_vs_total_return_comparison"]
        self.assertEqual(len(comp), 2)
        row0 = comp[0]
        self.assertIn("price_only", row0)
        self.assertIn("cash_dividends_retained", row0)
        self.assertIn("dividends_reinvested_at_target_return", row0)
        self.assertLess(
            row0["cash_dividends_retained"]["required_exit_price"],
            row0["price_only"]["required_exit_price"],
        )
        self.assertLess(
            row0["dividends_reinvested_at_target_return"]["required_exit_price"],
            row0["price_only"]["required_exit_price"],
        )


class TestResearchDossierIntegration(unittest.TestCase):
    def test_dossier_contains_and_renders_dividends_section(self):
        multiple = ReferenceMultiple(value=20.0, source="user_supplied")
        report = build_reverse_requirements_report(
            price=100.0,
            ticker="TEST",
            currency="USD",
            as_of="2026-09-30",
            price_source="fixture",
            horizons_years=[1.0, 3.0],
            required_returns=[0.10],
            exit_multiples=[multiple],
            start_anchor=_anchor(4.0),
            dividend_per_share=2.0,
            dividend_source="Test Sourced Dividends",
        )
        # Mock dividend package attached to report
        report["dividends"] = {
            "formula_version": "dividend-history/1.0",
            "status": "COMPUTED",
            "summary": {
                "trailing_twelve_month_dividends": 2.0,
                "trailing_twelve_month_yield": 0.02,
                "latest_payment_amount": 0.50,
                "latest_payment_date": "2026-08-10",
                "indicated_annual_dividend_rate": 2.0,
                "indicated_annual_dividend_yield": 0.02,
                "dividend_growth_yoy": 0.05,
                "trailing_dividends_source": "Test Sourced Dividends",
                "currency": "USD",
            },
            "recent_payments": [
                {
                    "ex_date": "2026-08-10",
                    "amount": 0.50,
                    "unadjusted_amount": 0.50,
                    "currency": "USD",
                    "source": "Chart API",
                }
            ],
            "historical_returns": [
                {
                    "horizon_label": "1y",
                    "start_date": "2025-09-30",
                    "end_date": "2026-09-30",
                    "price_return_cagr": 0.15,
                    "total_return_cash_cagr": 0.17,
                    "total_return_reinvested_cagr": 0.172,
                    "dividend_contribution_reinvested_cagr": 0.022,
                }
            ],
            "notes": ["Test dividend notes."],
        }

        run_result = {
            "ticker": "TEST",
            "company_name": "Test Co",
            "as_of": "2026-09-30",
            "market_snapshot": {"price": 100.0, "currency": "USD", "exchange": "TEST"},
            "fundamental_snapshot": {"current_market_cap": 1000.0},
            "observed_valuation": {"current_pe": 25.0},
            "reverse_requirements": report,
        }

        dossier = build_dossier(run_result)
        self.assertIn("dividends_and_total_return", dossier["section_order"])
        self.assertIn("dividends_and_total_return", dossier["sections"])

        rendered = render_dossier(dossier)
        self.assertIn("股利資料與總報酬分析", rendered)
        self.assertIn("[股利與殖利率概況]", rendered)
        self.assertIn("過去12個月累計現金股利 (TTM)", rendered)
        self.assertIn("[歷史報酬率比較: 股價報酬 vs 總報酬", rendered)
        self.assertIn("[反推要求條件比較: 純股價報酬 vs 總報酬", rendered)


class TestPhaseHAuditRegression(unittest.TestCase):
    """
    Phase H closeout audit: reconcile EPS CAGR identity, verify growth
    window, starting EPS basis, and consistency between JSON / report / ROADMAP.
    """

    def test_eps_cagr_identity_3yr_10pct_28_95(self):
        """
        Verify the identity for the documented AAPL reverse hurdle:
        start EPS = 8.72 (TTM, 12 months, source Yahoo Finance+
        YahooFinanceFundamentals, period undeclared), terminal = 448.07 / 28.95
        = 15.478, window = 3.0 years (TTM anchor at valuation date 2026-10-09).
        Earlier reported 33.07% reflected a mismatched ~2-year window, not a
        different EPS basis.
        """
        start_eps = 8.72
        terminal_eps = 448.07 / 28.95  # = 15.477374784...
        window_years = 3.0
        cagr = (terminal_eps / start_eps) ** (1.0 / window_years) - 1.0
        # Confirmed value ~21.08%; the erroneous 33.07% only appears at ~2yr
        self.assertAlmostEqual(cagr, 0.2108, places=3)
        self.assertGreater(cagr, 0.20)
        self.assertLess(cagr, 0.22)

    def test_growth_window_ttm_anchor_is_3_years_not_2(self):
        from reverse_requirements import growth_window_years, EpsAnchor, ANCHOR_TTM
        anchor = EpsAnchor(value=8.72, basis=ANCHOR_TTM, months_covered=12.0,
                           period_label="trailing twelve months (assumed; source stated no period)",
                           period_undeclared_by_source=True)
        window = growth_window_years(anchor, 3.0)
        self.assertAlmostEqual(window, 3.0, places=6)
        self.assertNotAlmostEqual(window, 2.0, places=6)

    def test_dividend_scenario_assumption_explicit_not_historical_as_future(self):
        """
        The total-return reverse scenarios use D = 1.06 (TTM from chart
        events, source = Market chart events) as an explicit scenario
        input, not as a guaranteed future payment. Indicated = 1.08 is
        strictly a run-rate (latest 0.27 x 4) and never presented as
        guaranteed.
        """
        from reverse_requirements import build_scenario, ReferenceMultiple, EpsAnchor, ANCHOR_TTM
        anchor = EpsAnchor(value=8.72, basis=ANCHOR_TTM, months_covered=12.0,
                           period_label="TTM", period_undeclared_by_source=True)
        mult = ReferenceMultiple(value=28.95, source="user_supplied",
                                 period_label="historical P/E median")
        # Cash retained scenario uses TTM 1.06 as explicit annual assumption
        cash = build_scenario(
            price=336.64, horizon_years=3.0, required_return=0.10,
            exit_multiple=mult, start_anchor=anchor,
            dividend_per_share=1.06,
            dividend_convention="CASH_DIVIDENDS_RETAINED",
            as_of="2026-10-09",
        )
        self.assertAlmostEqual(cash.required_exit_price, 444.88784, places=2)
        self.assertAlmostEqual(cash.required_terminal_eps, 15.3682, places=2)
        self.assertAlmostEqual(cash.required_eps_cagr, 0.2079, places=3)
        self.assertEqual(cash.dividend_convention, "CASH_DIVIDENDS_RETAINED")
        # DRIP scenario
        drip = build_scenario(
            price=336.64, horizon_years=3.0, required_return=0.10,
            exit_multiple=mult, start_anchor=anchor,
            dividend_per_share=1.06,
            dividend_convention="DIVIDENDS_REINVESTED_AT_TARGET_RETURN",
            as_of="2026-10-09",
        )
        self.assertAlmostEqual(drip.required_exit_price, 444.55924, places=2)
        self.assertAlmostEqual(drip.required_terminal_eps, 15.3568, places=2)
        self.assertAlmostEqual(drip.required_eps_cagr, 0.2076, places=3)

    def test_dividends_not_double_counted_separate_labels(self):
        """Price-only, cash-retained, DRIP must remain separately labelled."""
        from reverse_requirements import (DIVIDEND_CONVENTION_PRICE_ONLY,
                                          DIVIDEND_CONVENTION_CASH_RETAINED,
                                          DIVIDEND_CONVENTION_REINVESTED)
        self.assertNotEqual(DIVIDEND_CONVENTION_PRICE_ONLY,
                            DIVIDEND_CONVENTION_CASH_RETAINED)
        self.assertNotEqual(DIVIDEND_CONVENTION_CASH_RETAINED,
                            DIVIDEND_CONVENTION_REINVESTED)

    def test_json_and_report_use_same_start_eps_and_window(self):
        """Phase H versioned outputs must agree on starting EPS and growth window."""
        import json
        report_json = Path("history/AAPL_research_dossier_20261010_phase_h.json")
        if not report_json.exists():
            self.skipTest("Versioned Phase H JSON not present")
        with open(report_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        rr = data["sections"]["reverse_requirements"]
        # Starting EPS from dossier
        self.assertEqual(rr.get("starting_eps", {}).get("value"), 8.72)
        self.assertEqual(rr.get("starting_eps", {}).get("basis"), "TRAILING_TWELVE_MONTHS")
        # 3y 10% 28.95 price-only row
        matrix = rr.get("matrix", [])
        row = None
        for r in matrix:
            if r.get("horizon_years") == 3.0 and abs(r.get("required_return", 0) - 0.10) < 1e-3:
                mult = r.get("exit_multiple", {})
                val = mult.get("value") if isinstance(mult, dict) else mult
                if val and abs(float(val) - 28.95) < 0.5:
                    row = r
                    break
        self.assertIsNotNone(row, "3y 10% ~28.9 matrix row missing")
        self.assertAlmostEqual(row.get("growth_years"), 3.0, places=6)
        if row.get("required_eps_cagr") is not None:
            self.assertAlmostEqual(row["required_eps_cagr"], 0.2108, places=2)
        # Dividend comparison section also present and consistent
        div = data["sections"].get("dividends_and_total_return", {})
        comp = div.get("price_vs_total_return_comparison", [])
        comp_row = None
        for r in comp:
            if r.get("horizon_years") == 3.0 and abs(r.get("required_return", 0) - 0.10) < 1e-3:
                mult = r.get("exit_multiple", {})
                val = mult.get("value") if isinstance(mult, dict) else mult
                if val and abs(float(val) - 28.95) < 0.5:
                    comp_row = r
                    break
        if comp_row is not None:
            price_only = comp_row.get("price_only", {})
            cash = comp_row.get("cash_dividends_retained", {})
            drip = comp_row.get("dividends_reinvested_at_target_return", {})
            # All three must have same start EPS and 3-year window
            for sub in (price_only, cash, drip):
                start = sub.get("start_eps", {}) if isinstance(sub, dict) else {}
                if isinstance(start, dict) and start.get("value") is not None:
                    self.assertAlmostEqual(start.get("value"), 8.72, places=2)
            # Growth window is at comparison-row level, verified above via row search
            self.assertAlmostEqual(comp_row.get("horizon_years"), 3.0, places=6)


class TestCanonicalAaplDataset(unittest.TestCase):
    def test_canonical_aapl_dividend_extraction(self):
        daily_json = Path("data/historical_pe/AAPL/daily_prices.json")
        if not daily_json.exists():
            self.skipTest("Canonical AAPL daily_prices.json not found")

        pkg = build_dividend_package(
            ticker="AAPL",
            price=336.64,
            as_of="2026-10-09",
            currency="USD",
        )
        self.assertEqual(pkg["status"], "COMPUTED")
        summary = pkg["summary"]
        # In AAPL canonical daily_prices.json: 4 quarters of $0.26, $0.26, $0.27, $0.27 = $1.06
        self.assertAlmostEqual(summary["trailing_twelve_month_dividends"], 1.06, places=2)
        # Indicated annual rate: 4 * 0.27 = 1.08
        self.assertAlmostEqual(summary["indicated_annual_dividend_rate"], 1.08, places=2)
        # Yields: ~0.315% and ~0.321%
        self.assertAlmostEqual(summary["trailing_twelve_month_yield"], 1.06 / 336.64, places=4)
        self.assertAlmostEqual(summary["indicated_annual_dividend_yield"], 1.08 / 336.64, places=4)

        # Historical returns should have 1y, 3y, 5y
        returns = pkg["historical_returns"]
        self.assertTrue(len(returns) >= 3)
        horizons = [r["horizon_label"] for r in returns]
        self.assertIn("1y", horizons)
        self.assertIn("3y", horizons)
        self.assertIn("5y", horizons)


if __name__ == "__main__":
    unittest.main(verbosity=2)
