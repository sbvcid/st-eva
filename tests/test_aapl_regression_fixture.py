"""AAPL offline regression fixture tests.

AAPL runs end to end through the existing regression fixture mechanism with no
provider call: the fixture is a frozen sample of the values the live run
observed, and the trailing EPS keeps the source identity of the observation it
was captured from (YahooFinanceFundamentals / defaultKeyStatistics.trailingEps),
not the fixture's own. The promoted canonical production historical P/E dataset
supplies the exit multiples.
"""

import builtins
import os
import tempfile
import unittest
import urllib.request
from pathlib import Path

from data_contract import METRIC_TRAILING_EPS, SourceType
from st_eva_runner import REGRESSION_TEST_FIXTURES, CompanyResolver, YahooFinanceProvider
from web.service_adapter import AnalysisServiceAdapter

REPO_ROOT = Path(__file__).resolve().parents[1]
EPS_PROVIDER = "YahooFinanceFundamentals"
EPS_FIELD = "defaultKeyStatistics.trailingEps"
EPS_URL = "https://query2.finance.yahoo.com/v10/finance/quoteSummary/AAPL"


def _run_offline(ticker="AAPL"):
    with tempfile.TemporaryDirectory(prefix="aapl-regfix-") as tmp:
        dto = AnalysisServiceAdapter(archives_dir=tmp).run_analysis_pipeline(
            ticker=ticker, mode="regression"
        )
        return dto.model_dump()


class TestAaplFixtureResolution(unittest.TestCase):
    def test_fixture_is_registered_and_resolves(self):
        self.assertIn("AAPL", REGRESSION_TEST_FIXTURES)
        data = CompanyResolver.resolve("AAPL", mode="regression")
        self.assertIsNotNone(data)
        self.assertEqual(data.ticker, "AAPL")
        self.assertEqual(data.currency, "USD")
        self.assertEqual(data.price, 333.63)
        self.assertEqual(data.price_date, "2026-10-06")
        self.assertEqual(data.source_type, SourceType.REGRESSION_FIXTURE.value)
        self.assertEqual(data.current_eps, 8.72)

    def test_fixture_carries_the_captured_eps_observation(self):
        data = CompanyResolver.resolve("AAPL", mode="regression")
        matches = data.observations.for_metric(METRIC_TRAILING_EPS)
        self.assertTrue(matches, "fixture must carry a trailing-EPS observation")
        obs = matches[0]
        self.assertEqual(obs.value, 8.72)
        self.assertEqual(obs.provider, EPS_PROVIDER)
        self.assertEqual(obs.source_url, EPS_URL)
        self.assertEqual(obs.raw.get("field"), "trailingEps")
        self.assertEqual(obs.raw.get("module"), "defaultKeyStatistics")
        # The source declared no period, so none is fabricated.
        self.assertIsNone(obs.period_end)
        self.assertIsNone(obs.as_of)

    def test_resolution_does_not_call_the_live_provider(self):
        real_fetch = YahooFinanceProvider.fetch

        def _explode(self, ticker):
            raise AssertionError("regression resolution must not call the live provider")

        YahooFinanceProvider.fetch = _explode
        try:
            data = CompanyResolver.resolve("AAPL", mode="regression")
        finally:
            YahooFinanceProvider.fetch = real_fetch
        self.assertIsNotNone(data)


class TestAaplOfflinePipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = _run_offline()

    def test_pipeline_succeeds_without_network(self):
        real_urlopen = urllib.request.urlopen

        def _explode(*a, **kw):
            raise AssertionError("offline run must not open a network connection")

        urllib.request.urlopen = _explode
        try:
            result = _run_offline()
        finally:
            urllib.request.urlopen = real_urlopen
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["reverse_requirements"]["matrix_size"], 80)

    def test_matrix_structure_and_calculation_steps(self):
        rr = self.result["reverse_requirements"]
        self.assertEqual(rr["status"], "COMPUTED")
        self.assertEqual(rr["formula_version"], "reverse-requirements/1.1")
        matrix = rr["reverse_requirements_matrix"]
        self.assertEqual(len(matrix), 80)
        for row in matrix:
            self.assertTrue(row["evidence"]["sourced_facts"])
            self.assertTrue(row["calculation_steps"], "each row must carry its calculation steps")
        row0 = matrix[0]
        self.assertAlmostEqual(row0["required_exit_price"], 333.63 * 1.08, places=6)

    def test_production_historical_pe_is_the_tracked_canonical_dataset(self):
        summary = self.result["reverse_requirements"]["production_historical_pe_summary"]
        self.assertEqual(summary["status"], "USABLE_FOR_REFERENCE")
        self.assertEqual(summary["sample_count"], 30)
        self.assertEqual(summary["period_start"], "2018-05-03")
        self.assertTrue(summary["input_set_id"])
        # Exit multiples come from the production distribution, not a fixture band.
        row0 = self.result["reverse_requirements"]["reverse_requirements_matrix"][0]
        self.assertEqual(row0["exit_multiple"]["source"], "production_historical_pe_percentile")

    def test_starting_eps_provenance_is_preserved(self):
        row0 = self.result["reverse_requirements"]["reverse_requirements_matrix"][0]
        ev = row0["evidence"]
        eps_facts = [f for f in ev["sourced_facts"] if f.startswith("Starting EPS")]
        joined = " | ".join(eps_facts)
        self.assertIn(f"EPS provider: {EPS_PROVIDER}", joined)
        self.assertIn(EPS_FIELD, joined)
        self.assertIn(EPS_URL, joined)
        self.assertIn("source declared no period date", joined)
        # The fixture's market-data provider must not be presented as the EPS source.
        for fact in eps_facts:
            self.assertNotIn("RegressionFixture", fact)
        self.assertIsNone(ev["eps_evidence"]["sec_fact"])
        self.assertIn("Starting EPS period coverage was not declared by source", ev["missing_or_unvalidated"])
        self.assertTrue(any(
            "Direct SEC source of selected EPS not established" in item
            for item in ev["missing_or_unvalidated"]
        ))
        # The price date and the EPS retrieval date differ, so the run is stated
        # to be a cross-date input rather than a point-in-time snapshot.
        self.assertTrue(any(
            "retrieved on 2026-10-13" in item and "market price date 2026-10-06" in item
            for item in ev["missing_or_unvalidated"]
        ))

    def test_dividends_and_comparison_are_present(self):
        rr = self.result["reverse_requirements"]
        self.assertEqual(rr["dividend_basis"]["dividend_per_share"], 1.06)
        self.assertEqual(len(rr["price_vs_total_return_comparison"]), 80)

    def test_offline_run_does_not_touch_research_tree(self):
        research_root = REPO_ROOT / "research"
        real_exists, real_is_dir, real_open = Path.exists, Path.is_dir, builtins.open
        real_os_open = os.open

        def _under(path):
            return str(path).replace("\\", "/").startswith(str(research_root).replace("\\", "/"))

        def _exists(self):
            if _under(self):
                raise AssertionError(f"offline run touched research/: {self}")
            return real_exists(self)

        def _is_dir(self):
            if _under(self):
                raise AssertionError(f"offline run touched research/: {self}")
            return real_is_dir(self)

        def _py_open(file, *a, **kw):
            if _under(getattr(file, "__str__", lambda: file)()):
                raise AssertionError(f"offline run opened research/: {file}")
            return real_open(file, *a, **kw)

        def _os_open(file, *a, **kw):
            if _under(file):
                raise AssertionError(f"offline run opened research/: {file}")
            return real_os_open(file, *a, **kw)

        Path.exists, Path.is_dir = _exists, _is_dir
        builtins.open, os.open = _py_open, _os_open
        try:
            result = _run_offline()
        finally:
            Path.exists, Path.is_dir = real_exists, real_is_dir
            builtins.open, os.open = real_open, real_os_open
        self.assertEqual(result["reverse_requirements"]["matrix_size"], 80)

    def test_repeated_runs_are_reproducible(self):
        again = _run_offline()
        a, b = self.result, again
        self.assertEqual(a["reverse_requirements"]["fingerprint"], b["reverse_requirements"]["fingerprint"])
        self.assertEqual(
            a["reverse_requirements"]["production_historical_pe_summary"]["input_set_id"],
            b["reverse_requirements"]["production_historical_pe_summary"]["input_set_id"],
        )
        ra = a["reverse_requirements"]["reverse_requirements_matrix"][0]
        rb = b["reverse_requirements"]["reverse_requirements_matrix"][0]
        self.assertEqual(ra["required_terminal_eps"], rb["required_terminal_eps"])
        self.assertEqual(ra["required_eps_cagr"], rb["required_eps_cagr"])


if __name__ == "__main__":
    unittest.main()
