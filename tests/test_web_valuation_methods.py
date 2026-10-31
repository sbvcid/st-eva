"""
Web-path exposure of the non-earnings valuation methods (P/S, P/FCF,
EV/EBITDA): the engine result must reach the typed web DTO and the browser
must be able to re-verify each implied figure from the response's own
operands, with explicit refusals where an input is missing.
"""

import tempfile
import unittest
from pathlib import Path

PRICES_EXIST = (Path("data/historical_pe/AAPL/daily_prices.json")).exists()
PRICES_SKIP = "AAPL daily_prices.json excluded per C-1 / DATA-DELIVERY.md"

from web.service_adapter import AnalysisServiceAdapter
from web.schemas import AnalyzeRequest


class TestWebValuationMethods(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="st_eva_val_methods_")
        self.adapter = AnalysisServiceAdapter(archives_dir=self.tmp)

    def _run(self, ticker: str):
        return self.adapter.run_analysis_pipeline(ticker=ticker, mode="regression")

    def test_request_accepts_non_earnings_multiples(self):
        req = AnalyzeRequest(
            ticker="AAPL",
            ps_multiple=7.0,
            ev_ebitda_multiple=13.0,
            pfcf_multiple=25.0,
        )
        self.assertEqual(req.ps_multiple, 7.0)
        self.assertEqual(req.ev_ebitda_multiple, 13.0)
        self.assertEqual(req.pfcf_multiple, 25.0)

    @unittest.skipUnless(PRICES_EXIST, PRICES_SKIP)
    def test_aep_matrix_uncomputed_but_ev_ebitda_method_computed(self):
        dto = self._run("AEP")
        self.assertEqual(dto.status, "success")
        report = dto.reverse_requirements
        self.assertIsNotNone(report)
        self.assertEqual(report.status, "NOT_COMPUTED")
        self.assertEqual(report.matrix_size, 0)

        vm = report.valuation_methods
        self.assertIsNotNone(vm)
        ev = vm.methods["enterprise_value_multiple"]
        self.assertEqual(ev.status, "COMPUTED")
        self.assertIsNotNone(ev.reference_multiple)
        self.assertEqual(ev.reference_multiple["value"], 13.221693)
        self.assertEqual(
            ev.reference_multiple["source"], "production_historical_ev_ebitda_median"
        )
        self.assertFalse(ev.reference_multiple["is_user_assumption"])

        # Implied EBITDA must be independently re-computable from the response's
        # own operands: enterprise_value / adopted multiple.
        ev_operand = dto.valuation_summary.enterprise_value
        self.assertIsNotNone(ev_operand)
        expected = ev_operand / ev.reference_multiple["value"]
        self.assertAlmostEqual(ev.implied, expected, places=2)

        # Observed EBITDA and the gap travel beside it.
        self.assertIsNotNone(ev.observed)
        self.assertIsNotNone(ev.gap_implied_vs_observed)

        # The matrix being uncomputed must not hide a computed method.
        self.assertEqual(ev.status, "COMPUTED")

    @unittest.skipUnless(PRICES_EXIST, PRICES_SKIP)
    def test_aep_ps_shows_insufficient_observations(self):
        dto = self._run("AEP")
        vm = dto.reverse_requirements.valuation_methods
        ps = vm.methods["revenue_multiple"]
        self.assertEqual(ps.status, "NOT_COMPUTED")
        summary = dto.reverse_requirements.production_historical_multiples_summary
        self.assertIsNotNone(summary)
        dist = summary.distributions or {}
        ps_dist = dist.get("P_S_RATIO_REFERENCE")
        self.assertIsNotNone(ps_dist)
        # Four observations -> explicitly insufficient, never zero or blank.
        self.assertEqual(ps_dist.sample_count, 4)
        self.assertFalse(ps_dist.usable_for_reference)
        rm = ps.reference_multiple
        self.assertTrue(rm is None or rm.get("value") is None)

    @unittest.skipUnless(PRICES_EXIST, PRICES_SKIP)
    def test_aapl_ps_and_ev_ebitda_references_present(self):
        dto = self._run("AAPL")
        vm = dto.reverse_requirements.valuation_methods
        ps = vm.methods["revenue_multiple"]
        self.assertEqual(ps.status, "NOT_COMPUTED")
        self.assertEqual(ps.reference_multiple["value"], 7.257709)
        self.assertTrue(ps.reference_multiple["usable_for_reference"])

        ev = vm.methods["enterprise_value_multiple"]
        self.assertEqual(ev.reference_multiple["value"], 22.326)
        summary = dto.reverse_requirements.production_historical_multiples_summary
        self.assertIsNotNone(summary)
        dist = summary.distributions or {}
        self.assertEqual(dist["P_S_RATIO_REFERENCE"].sample_count, 28)
        self.assertEqual(dist["EV_EBITDA_RATIO_REFERENCE"].sample_count, 27)

    def test_msft_ev_ebitda_unavailable_not_fabricated(self):
        dto = self._run("MSFT")
        vm = dto.reverse_requirements.valuation_methods
        ev = vm.methods["enterprise_value_multiple"]
        self.assertEqual(ev.status, "NOT_COMPUTED")
        rm = ev.reference_multiple
        self.assertTrue(rm is None or rm.get("value") is None)
        summary = dto.reverse_requirements.production_historical_multiples_summary
        self.assertIsNotNone(summary)
        dist = summary.distributions or {}
        ev_dist = dist.get("EV_EBITDA_RATIO_REFERENCE")
        self.assertIsNotNone(ev_dist)
        self.assertEqual(ev_dist.sample_count, 0)

    @unittest.skipUnless(PRICES_EXIST, PRICES_SKIP)
    def test_historical_references_stay_non_user_assumption(self):
        dto = self._run("AAPL")
        # No user multiple supplied in regression: references stay historical.
        ps = dto.reverse_requirements.valuation_methods.methods["revenue_multiple"]
        self.assertFalse(ps.reference_multiple["is_user_assumption"])

    def test_valid_multiples_pass_through(self):
        req = AnalyzeRequest(
            ticker="AAPL",
            ps_multiple=7.0,
            ev_ebitda_multiple=13.0,
            pfcf_multiple=25.0,
            reference_multiple=20.0,
        )
        self.assertEqual(req.ps_multiple, 7.0)
        self.assertEqual(req.ev_ebitda_multiple, 13.0)
        self.assertEqual(req.pfcf_multiple, 25.0)
        self.assertEqual(req.reference_multiple, 20.0)

    def test_invalid_multiples_are_rejected(self):
        from pydantic import ValidationError

        invalid_values = [0, -1.0, float("nan"), float("inf"), float("-inf")]
        for value in invalid_values:
            for name in (
                "ps_multiple",
                "ev_ebitda_multiple",
                "pfcf_multiple",
                "reference_multiple",
            ):
                with self.assertRaises(ValidationError):
                    AnalyzeRequest(ticker="AAPL", **{name: value})

    def test_none_multiples_are_accepted(self):
        # Absent multiples fall back to historical references; None is not an
        # invalid value.
        req = AnalyzeRequest(ticker="AAPL")
        self.assertIsNone(req.ps_multiple)
        self.assertIsNone(req.ev_ebitda_multiple)
        self.assertIsNone(req.pfcf_multiple)
        self.assertIsNone(req.reference_multiple)

    @unittest.skipUnless(PRICES_EXIST, PRICES_SKIP)
    def test_input_provenance_observed_ebitda_sec_derived_ttm(self):
        # The web path loads the filed income statement, so the observed EBITDA
        # the enterprise-value multiple is computed from is the qualified filed
        # TTM figure (SEC-derived), not the vendor's undeclared trailing figure.
        dto = self._run("AEP")
        prov = dto.reverse_requirements.input_provenance
        self.assertIsNotNone(prov)
        ebitda = prov.get("current_ebitda")
        self.assertIsNotNone(ebitda)
        self.assertEqual(ebitda.source, "SEC_DERIVED")
        self.assertEqual(ebitda.basis, "TTM")
        self.assertEqual(ebitda.currency, "USD")
        self.assertTrue(ebitda.used_by_engine)
        self.assertEqual(ebitda.value, 8849200000.0)
        self.assertEqual(ebitda.period_start, "2025-06-30")
        self.assertEqual(ebitda.period_end, "2026-03-31")
        # The vendor's undeclared trailing figure is preserved as the
        # cross-check, not substituted for the observed figure.
        self.assertIsNotNone(ebitda.provider_figure)
        self.assertEqual(ebitda.provider_figure["value"], 9751000000.0)
        self.assertEqual(ebitda.provider_figure["source"], "VENDOR_REPORTED")
        self.assertEqual(ebitda.provider_figure["basis"], "UNDECLARED")

    @unittest.skipUnless(PRICES_EXIST, PRICES_SKIP)
    def test_implied_and_observed_share_one_run(self):
        # Implied EBITDA = enterprise value / selected EV/EBITDA; observed
        # EBITDA = the qualified filed TTM figure. Both come from the same run
        # and are reproducible for the same input.
        dto = self._run("AEP")
        ev = dto.reverse_requirements.valuation_methods.methods[
            "enterprise_value_multiple"
        ]
        self.assertEqual(ev.status, "COMPUTED")
        ev_operand = dto.valuation_summary.enterprise_value
        self.assertIsNotNone(ev_operand)
        expected_implied = ev_operand / ev.reference_multiple["value"]
        self.assertAlmostEqual(ev.implied, expected_implied, places=2)
        self.assertEqual(ev.observed, 8849200000.0)
        # The gap is a relative ratio (implied / observed - 1), not an
        # absolute currency difference.
        self.assertAlmostEqual(
            ev.gap_implied_vs_observed,
            ev.implied / ev.observed - 1.0,
            places=6,
        )

    @unittest.skipUnless(PRICES_EXIST, PRICES_SKIP)
    def test_aapl_and_msft_historical_references_unchanged(self):
        for ticker, ps_value, ps_count, ev_value, ev_count in (
            ("AAPL", 7.257709, 28, 22.326, 27),
            ("MSFT", 11.783822, 23, None, 0),
        ):
            dto = self._run(ticker)
            vm = dto.reverse_requirements.valuation_methods
            ps = vm.methods["revenue_multiple"]
            self.assertEqual(ps.status, "NOT_COMPUTED")
            self.assertEqual(ps.reference_multiple["value"], ps_value)
            self.assertTrue(ps.reference_multiple["usable_for_reference"])
            summary = dto.reverse_requirements.production_historical_multiples_summary
            self.assertIsNotNone(summary)
            dist = summary.distributions or {}
            self.assertEqual(dist["P_S_RATIO_REFERENCE"].sample_count, ps_count)
            ev = vm.methods["enterprise_value_multiple"]
            if ev_value is None:
                self.assertEqual(ev.status, "NOT_COMPUTED")
                rm = ev.reference_multiple
                self.assertTrue(rm is None or rm.get("value") is None)
                self.assertEqual(dist["EV_EBITDA_RATIO_REFERENCE"].sample_count, ev_count)
            else:
                self.assertEqual(ev.reference_multiple["value"], ev_value)
                self.assertEqual(dist["EV_EBITDA_RATIO_REFERENCE"].sample_count, ev_count)
