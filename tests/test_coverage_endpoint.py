"""
First-use coverage: the /api/coverage summary and the quick-example contract.

The coverage states are read from the committed production datasets with the
same loaders `run_st_eva` uses, and gated by each distribution's own
`usable_for_reference` flag -- the engine's own qualification. A thin sample
keeps its INSUFFICIENT_OBSERVATIONS refusal, a missing dataset keeps
UNAVAILABLE, and neither is ever reported as an available reference.
"""

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from web.app import create_app
from web.job_manager import JobManager
from web.service_adapter import AnalysisServiceAdapter, coverage_summary

PRICES_EXIST = (
    Path("data/historical_pe/AAPL/daily_prices.json").exists()
    and Path("data/historical_pe/MSFT/daily_prices.json").exists()
)


class TestCoverageSummary(unittest.TestCase):
    def setUp(self) -> None:
        self.issuers = coverage_summary().issuers

    def test_tickers_come_from_the_datasets_not_a_second_list(self):
        # Every issuer the three loaders establish, including one whose
        # dataset files are incomplete (NKE, all families UNAVAILABLE).
        # TSM has no committed dataset and no registered config, so it is
        # absent entirely and can never surface as a quick example.
        for ticker in ("AAPL", "MSFT", "MU", "AEP", "SOFI", "NKE"):
            self.assertIn(ticker, self.issuers)
        self.assertNotIn("TSM", self.issuers)

    def test_aapl_all_four_families_eligible(self):
        aapl = self.issuers["AAPL"]
        if PRICES_EXIST:
            for family in (aapl.pe, aapl.ps, aapl.pfcf, aapl.ev_ebitda):
                self.assertTrue(family.usable_for_reference)
                self.assertEqual(family.status, "USABLE_FOR_REFERENCE")
            self.assertEqual(aapl.pe.sample_count, 36)
            self.assertEqual(aapl.ps.sample_count, 28)
            self.assertEqual(aapl.pfcf.sample_count, 35)
            self.assertEqual(aapl.ev_ebitda.sample_count, 27)
        else:
            for family in (aapl.pe, aapl.ps, aapl.pfcf, aapl.ev_ebitda):
                self.assertFalse(family.usable_for_reference)
                self.assertEqual(family.status, "UNAVAILABLE")
                self.assertEqual(family.sample_count, 0)

    def test_msft_ev_ebitda_unavailable_not_zero(self):
        msft = self.issuers["MSFT"]
        if PRICES_EXIST:
            for family in (msft.pe, msft.ps, msft.pfcf):
                self.assertTrue(family.usable_for_reference)
        else:
            for family in (msft.pe, msft.ps, msft.pfcf):
                self.assertFalse(family.usable_for_reference)
        ev = msft.ev_ebitda
        self.assertFalse(ev.usable_for_reference)
        self.assertEqual(ev.status, "UNAVAILABLE")
        self.assertEqual(ev.sample_count, 0)

    def test_mu_earnings_and_cash_flow_only(self):
        mu = self.issuers["MU"]
        if PRICES_EXIST:
            self.assertTrue(mu.pe.usable_for_reference)
            self.assertTrue(mu.pfcf.usable_for_reference)
        else:
            self.assertFalse(mu.pe.usable_for_reference)
            self.assertFalse(mu.pfcf.usable_for_reference)
        for family in (mu.ps, mu.ev_ebitda):
            self.assertFalse(family.usable_for_reference)
            self.assertEqual(family.status, "UNAVAILABLE")

    def test_aep_ev_ebitda_eligible_ps_insufficient(self):
        aep = self.issuers["AEP"]
        if PRICES_EXIST and Path("data/historical_pe/AEP/daily_prices.json").exists():
            self.assertTrue(aep.ev_ebitda.usable_for_reference)
            self.assertEqual(aep.ev_ebitda.sample_count, 24)
            ps = aep.ps
            self.assertFalse(ps.usable_for_reference)
            self.assertEqual(ps.status, "INSUFFICIENT_OBSERVATIONS")
            self.assertEqual(ps.sample_count, 4)
            self.assertIsNotNone(ps.reason_detail)
        else:
            self.assertFalse(aep.ev_ebitda.usable_for_reference)
            self.assertEqual(aep.ev_ebitda.status, "UNAVAILABLE")
        self.assertEqual(aep.pe.status, "UNAVAILABLE")
        self.assertEqual(aep.pfcf.status, "UNAVAILABLE")

    def test_sofi_earnings_only(self):
        sofi = self.issuers["SOFI"]
        if PRICES_EXIST and Path("data/historical_pe/SOFI/daily_prices.json").exists():
            self.assertTrue(sofi.pe.usable_for_reference)
            self.assertEqual(sofi.pe.sample_count, 130)
        else:
            self.assertFalse(sofi.pe.usable_for_reference)
            self.assertEqual(sofi.pe.status, "UNAVAILABLE")
        for family in (sofi.ps, sofi.pfcf, sofi.ev_ebitda):
            self.assertFalse(family.usable_for_reference)
            self.assertEqual(family.status, "UNAVAILABLE")

    def test_no_ineligible_family_reports_usable(self):
        # Global invariant: a family is usable exactly when its own gate says
        # so, and every ineligible state keeps an explicit refusal status
        # rather than a fabricated zero.
        for issuer in self.issuers.values():
            for family in (issuer.pe, issuer.ps, issuer.pfcf, issuer.ev_ebitda):
                if family.usable_for_reference:
                    self.assertEqual(family.status, "USABLE_FOR_REFERENCE")
                    self.assertGreater(family.sample_count, 0)
                else:
                    self.assertNotEqual(family.status, "USABLE_FOR_REFERENCE")
                    if family.status == "INSUFFICIENT_OBSERVATIONS":
                        self.assertIsNotNone(family.reason_detail)

    def test_coverage_consistent_with_analysis_path(self):
        # The homepage summary and a real regression run must agree on the
        # same committed datasets: same eligibility, same sample counts.
        adapter = AnalysisServiceAdapter(
            archives_dir=tempfile.mkdtemp(prefix="st_eva_cov_")
        )
        for ticker in ("AAPL", "AEP"):
            dto = adapter.run_analysis_pipeline(ticker=ticker, mode="regression")
            report = dto.reverse_requirements
            cov = self.issuers[ticker]

            pe_summary = report.production_historical_pe_summary
            if pe_summary is not None:
                self.assertEqual(cov.pe.sample_count, pe_summary.sample_count)
                self.assertEqual(
                    cov.pe.usable_for_reference,
                    bool(pe_summary.usable_for_reference),
                )

            pfcf_summary = report.production_historical_pfcf_summary
            if pfcf_summary is not None:
                self.assertEqual(cov.pfcf.sample_count, pfcf_summary.sample_count)
                self.assertEqual(
                    cov.pfcf.usable_for_reference,
                    bool(pfcf_summary.usable_for_reference),
                )

            mult = report.production_historical_multiples_summary
            if mult is not None:
                dists = mult.distributions or {}
                ps_dist = dists.get("P_S_RATIO_REFERENCE")
                if ps_dist is not None:
                    self.assertEqual(cov.ps.sample_count, ps_dist.sample_count)
                    self.assertEqual(
                        cov.ps.usable_for_reference,
                        bool(ps_dist.usable_for_reference),
                    )
                ev_dist = dists.get("EV_EBITDA_RATIO_REFERENCE")
                if ev_dist is not None:
                    self.assertEqual(cov.ev_ebitda.sample_count, ev_dist.sample_count)
                    self.assertEqual(
                        cov.ev_ebitda.usable_for_reference,
                        bool(ev_dist.usable_for_reference),
                    )


class TestCoverageEndpoint(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_get_coverage_returns_verified_states(self):
        response = self.client.get("/api/coverage")
        self.assertEqual(response.status_code, 200)
        issuers = response.json()["issuers"]
        self.assertIn("AAPL", issuers)
        self.assertNotIn("TSM", issuers)
        if PRICES_EXIST:
            self.assertTrue(issuers["AAPL"]["pe"]["usable_for_reference"])
            self.assertTrue(issuers["AAPL"]["ev_ebitda"]["usable_for_reference"])
        else:
            self.assertFalse(issuers["AAPL"]["pe"]["usable_for_reference"])
            self.assertFalse(issuers["AAPL"]["ev_ebitda"]["usable_for_reference"])
        aep = issuers["AEP"]
        if PRICES_EXIST and Path("data/historical_pe/AEP/daily_prices.json").exists():
            self.assertEqual(aep["ps"]["status"], "INSUFFICIENT_OBSERVATIONS")
            self.assertFalse(aep["ps"]["usable_for_reference"])
            self.assertTrue(aep["ev_ebitda"]["usable_for_reference"])
        else:
            self.assertEqual(aep["ev_ebitda"]["status"], "UNAVAILABLE")
        msft = issuers["MSFT"]
        self.assertFalse(msft["ev_ebitda"]["usable_for_reference"])
        self.assertEqual(msft["ev_ebitda"]["status"], "UNAVAILABLE")


class TestNonEarningsMultipleForwarding(unittest.TestCase):
    """
    The user-supplied non-earnings multiples must survive the HTTP layer:
    AnalyzeRequest accepts them, the route forwards them, and the job manager
    hands them to the engine -- a dropped value would silently fall back to a
    historical reference the user never chose.
    """

    def setUp(self) -> None:
        self.mock_adapter = MagicMock(spec=AnalysisServiceAdapter)
        self.job_manager = JobManager(adapter=self.mock_adapter, max_workers=2)
        self.client = TestClient(create_app(job_manager=self.job_manager))

    def tearDown(self) -> None:
        self.job_manager.shutdown(wait=False)

    def test_post_analyze_forwards_non_earnings_multiples(self):
        response = self.client.post(
            "/api/analyze",
            json={
                "ticker": "AAPL",
                "ps_multiple": 7.0,
                "ev_ebitda_multiple": 13.0,
                "pfcf_multiple": 25.0,
            },
        )
        self.assertEqual(response.status_code, 202)
        for _ in range(100):
            if self.mock_adapter.run_analysis_pipeline.called:
                break
            time.sleep(0.05)
        self.mock_adapter.run_analysis_pipeline.assert_called_once()
        kwargs = self.mock_adapter.run_analysis_pipeline.call_args.kwargs
        self.assertEqual(kwargs.get("ps_multiple"), 7.0)
        self.assertEqual(kwargs.get("ev_ebitda_multiple"), 13.0)
        self.assertEqual(kwargs.get("pfcf_multiple"), 25.0)


if __name__ == "__main__":
    unittest.main()
