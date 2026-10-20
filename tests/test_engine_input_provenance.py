"""
The engine's inputs, and the basis each one is on.

The point of these tests is that "there is evidence" and "the valuation used
it" are different statements, and the product must not blur them:

* a quarter's free cash flow is not a trailing one, and must not be used as
  one;
* a trailing free cash flow is only reconstructed from four qualifying
  quarters -- a gap in the window, or a quarter that was not knowable at the
  cut, refuses the reconstruction rather than filling it;
* the filed annual EBITDA keeps its annual label and does not enter a
  trailing multiple;
* a provider's trailing EPS with no declared period is never relabelled as a
  filed trailing EPS;
* one refused input leaves the other methods able to compute on their own;
* what the API reports as the calculation inputs is what the engine used.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, ".")

from data_contract import ValuationInputs
from sec_derived_inputs import (
    BASIS_QUARTERLY,
    BASIS_TTM,
    SOURCE_SEC_DERIVED,
    SOURCE_VENDOR,
    qualified_ttm_eps,
    qualified_ttm_fcf,
)
from st_eva_runner import MarketImpliedAssumptionsEngine, _engine_inputs_with_filed_figures


def _pe_payload(records):
    return {"observations": records}


def _eps_record(
    evaluation_date,
    value=8.72,
    components=None,
    usable_dates=("2025-10-31", "2026-01-30", "2026-05-01", "2026-07-31"),
    status="AVAILABLE",
    missing_quarters=(),
):
    if components is None:
        components = [
            {
                "value": 1.85,
                "form": "8-K",
                "accession": "0000320193-25-000077",
                "period_end": "2025-09-27",
                "usable_date": usable_dates[0],
                "evidence_class": "furnished",
                "metric": "GAAP_DILUTED_EPS",
                "currency": "USD",
                "acceptance_datetime": "2025-10-30T16:30:35-04:00",
                "source_url": "https://www.sec.gov/x.htm",
                "stated_directly": True,
            },
            {
                "value": 2.84,
                "form": "10-Q",
                "accession": "0000320193-26-000006",
                "period_end": "2025-12-27",
                "usable_date": usable_dates[1],
                "evidence_class": "filed",
                "metric": "GAAP_DILUTED_EPS",
                "currency": "USD",
            },
            {
                "value": 2.01,
                "form": "10-Q",
                "accession": "0000320193-26-000013",
                "period_end": "2026-03-28",
                "usable_date": usable_dates[2],
                "evidence_class": "filed",
                "metric": "GAAP_DILUTED_EPS",
                "currency": "USD",
            },
            {
                "value": 2.02,
                "form": "10-Q",
                "accession": "0000320193-26-000020",
                "period_end": "2026-06-27",
                "usable_date": usable_dates[3],
                "evidence_class": "filed",
                "metric": "GAAP_DILUTED_EPS",
                "currency": "USD",
            },
        ]
    return {
        "metric_id": "TTM_GAAP_DILUTED_PE",
        "evaluation_date": evaluation_date,
        "status": status,
        "eps_state": {
            "components": components,
            "missing_quarters": list(missing_quarters),
            "quarter_denominator": value,
            "quarter_denominator_derivation": {
                "method": "SUM_OF_FOUR_DIRECTLY_STATED_QUARTERLY_EPS",
                "derived_not_issuer_declared": True,
            },
            "window_anchor": {"fiscal_year": 2026, "fiscal_quarter": 3},
        },
    }


def _fcf_record(
    evaluation_date,
    value=136_683_000_000.0,
    quarters=None,
    status="AVAILABLE",
):
    if quarters is None:
        quarters = [
            {
                "period_end": "2025-09-27",
                "fiscal_year": 2025,
                "fiscal_quarter": 4,
                "operating_cash_flow": 29_728_000_000.0,
                "capital_expenditure": 3_242_000_000.0,
                "free_cash_flow": 26_486_000_000.0,
                "currency": "USD",
                "formula": "operating cash flow - capital expenditure",
                "knowable_from": "2025-10-31",
            },
            {
                "period_end": "2025-12-27",
                "fiscal_year": 2026,
                "fiscal_quarter": 1,
                "operating_cash_flow": 53_925_000_000.0,
                "capital_expenditure": 2_373_000_000.0,
                "free_cash_flow": 51_552_000_000.0,
                "currency": "USD",
                "formula": "operating cash flow - capital expenditure",
                "knowable_from": "2026-01-30",
            },
            {
                "period_end": "2026-03-28",
                "fiscal_year": 2026,
                "fiscal_quarter": 2,
                "operating_cash_flow": 28_702_000_000.0,
                "capital_expenditure": 1_971_000_000.0,
                "free_cash_flow": 26_731_000_000.0,
                "currency": "USD",
                "formula": "operating cash flow - capital expenditure",
                "knowable_from": "2026-05-01",
            },
            {
                "period_end": "2026-06-27",
                "fiscal_year": 2026,
                "fiscal_quarter": 3,
                "operating_cash_flow": 27_440_000_000.0,
                "capital_expenditure": 2_301_000_000.0,
                "free_cash_flow": 25_139_000_000.0,
                "currency": "USD",
                "formula": "operating cash flow - capital expenditure",
                "knowable_from": "2026-07-31",
            },
        ]
    return {
        "metric_id": "TTM_MARKET_CAP_TO_FCF",
        "evaluation_date": evaluation_date,
        "status": status,
        "ttm_free_cash_flow": value,
        "ttm_free_cash_flow_currency": "USD",
        "ttm_window": {
            "anchor": {"fiscal_year": 2026, "fiscal_quarter": 3, "period_end": "2026-06-27"},
            "positions": [],
            "quarters": quarters,
        },
    }


class _StubView:
    """The view the runner's projection is built from."""

    ticker = "AAPL"
    price_date = "2026-10-19"
    price = 342.94
    currency = "USD"


class TestTheTrailingFiguresAreQualified(unittest.TestCase):
    """A trailing figure is only a trailing figure if it qualifies."""

    def test_a_four_quarter_window_qualifies(self):
        result = qualified_ttm_eps(
            _pe_payload([_eps_record("2026-10-06")]), "2026-10-19"
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["value"], 8.72)
        self.assertEqual(result["basis"], BASIS_TTM)
        self.assertEqual(result["source"], SOURCE_SEC_DERIVED)
        self.assertEqual(result["quarter_count"], 4)

    def test_a_missing_quarter_refuses_the_reconstruction(self):
        record = _eps_record("2026-10-06")
        record["eps_state"]["components"] = record["eps_state"]["components"][:3]
        self.assertIsNone(
            qualified_ttm_eps(_pe_payload([record]), "2026-10-19")
        )

    def test_a_window_with_a_declared_gap_refuses_the_reconstruction(self):
        record = _eps_record("2026-10-06", missing_quarters=["FY2026Q2"])
        self.assertIsNone(
            qualified_ttm_eps(_pe_payload([record]), "2026-10-19")
        )

    def test_a_quarter_not_knowable_at_the_cut_refuses_the_reconstruction(self):
        """A window that was not yet knowable is not used."""
        record = _eps_record(
            "2026-10-06",
            usable_dates=("2025-10-31", "2026-01-30", "2026-05-01", "2026-11-30"),
        )
        self.assertIsNone(
            qualified_ttm_eps(_pe_payload([record]), "2026-10-19")
        )

    def test_a_window_after_the_cut_is_not_used(self):
        record = _eps_record("2026-11-02")
        self.assertIsNone(
            qualified_ttm_eps(_pe_payload([record]), "2026-10-19")
        )

    def test_the_earliest_qualified_window_is_used_at_an_earlier_cut(self):
        """Point in time: an earlier cut sees the earlier window."""
        early = _eps_record(
            "2026-01-30",
            value=7.46,
            usable_dates=("2024-11-01", "2025-01-31", "2025-05-01", "2025-08-01"),
        )
        late = _eps_record("2026-10-06")
        result = qualified_ttm_eps(
            _pe_payload([late, early]), "2026-10-19"
        )
        self.assertEqual(result["value"], 8.72)
        result_earlier = qualified_ttm_eps(_pe_payload([late, early]), "2026-01-30")
        self.assertEqual(result_earlier["value"], 7.46)

    def test_the_four_quarter_free_cash_flow_qualifies(self):
        result = qualified_ttm_fcf(
            {"observations": [_fcf_record("2026-10-06")]}, "2026-10-19"
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["value"], 136_683_000_000.0)
        self.assertEqual(result["basis"], BASIS_TTM)
        self.assertEqual(result["quarter_count"], 4)

    def test_a_free_cash_flow_with_three_quarters_refuses_the_reconstruction(self):
        record = _fcf_record("2026-10-06")
        record["ttm_window"]["quarters"] = record["ttm_window"]["quarters"][:3]
        self.assertIsNone(
            qualified_ttm_fcf({"observations": [record]}, "2026-10-19")
        )

    def test_a_free_cash_flow_quarter_not_knowable_refuses_the_reconstruction(self):
        record = _fcf_record("2026-10-06")
        record["ttm_window"]["quarters"][3]["knowable_from"] = "2026-11-30"
        self.assertIsNone(
            qualified_ttm_fcf({"observations": [record]}, "2026-10-19")
        )


class TestTheEngineTakesTheTrailingFigure(unittest.TestCase):
    """
    What the engine used, and what corroborates it.

    The engine's figure is the one the document publishes, because the
    document recomputes every derived number from itself and refuses a
    document whose published formula does not reproduce the published number.
    The filed figure on the same basis is reported beside it, with its window
    and its constituents, and whether the two agree.
    """

    def _inputs(self, **overrides):
        base = ValuationInputs(
            price=342.94,
            currency="USD",
            current_eps=8.72,
            current_fcf=136_683_000_000.0,
            current_ebitda=167_959_000_000.0,
            current_revenue=466_823_000_000.0,
            current_market_cap=4_918_530_543_600.0,
            current_enterprise_value=4_940_475_543_600.0,
        )
        if overrides:
            base = replace(base, **overrides)
        return base

    def _apply(self, pe=None, pfcf=None):
        inputs = self._inputs()
        return _engine_inputs_with_filed_figures(
            inputs,
            data=_StubView(),
            production_historical_pe=pe,
            production_historical_pfcf=pfcf,
        )

    def test_the_engines_input_stays_the_published_figure(self):
        """The engine's number is the document's figure, not a substitute."""
        inputs, provenance = self._apply(
            pe=_pe_payload([_eps_record("2026-10-06", value=9.99)])
        )
        self.assertEqual(inputs.current_eps, 8.72)
        self.assertEqual(provenance["current_eps"]["source"], SOURCE_VENDOR)
        self.assertEqual(provenance["current_eps"]["basis"], "UNDECLARED")
        self.assertTrue(provenance["current_eps"]["used_by_engine"])

    def test_a_qualified_filed_trailing_eps_is_reported_beside_it(self):
        _, provenance = self._apply(
            pe=_pe_payload([_eps_record("2026-10-06")])
        )
        filed = provenance["current_eps"]["filed_trailing"]
        self.assertIsNotNone(filed)
        self.assertEqual(filed["value"], 8.72)
        self.assertEqual(filed["source"], SOURCE_SEC_DERIVED)
        self.assertEqual(filed["basis"], BASIS_TTM)
        self.assertFalse(filed["used_by_engine"])
        self.assertTrue(filed["agrees_with_engine_input"])
        self.assertEqual(len(filed["components"]), 4)
        # The fourth quarter is the furnished one, and it is named.
        self.assertEqual(len(filed["q4_evidence"]), 1)
        self.assertEqual(
            filed["q4_evidence"][0]["accession"], "0000320193-25-000077"
        )

    def test_a_filed_figure_that_differs_is_reported_as_a_difference(self):
        _, provenance = self._apply(
            pe=_pe_payload([_eps_record("2026-10-06", value=9.99)])
        )
        filed = provenance["current_eps"]["filed_trailing"]
        self.assertEqual(filed["value"], 9.99)
        self.assertFalse(filed["agrees_with_engine_input"])

    def test_without_a_qualified_figure_the_provider_figure_is_kept_and_labelled(self):
        inputs, provenance = self._apply(pe=_pe_payload([]))
        self.assertEqual(inputs.current_eps, 8.72)
        self.assertEqual(provenance["current_eps"]["source"], SOURCE_VENDOR)
        self.assertEqual(provenance["current_eps"]["basis"], "UNDECLARED")
        self.assertNotIn("filed_trailing", provenance["current_eps"])
        self.assertIn(
            "no qualified filed trailing diluted EPS",
            provenance["current_eps"]["note"],
        )

    def test_a_qualified_filed_trailing_free_cash_flow_is_reported_beside_it(self):
        inputs, provenance = self._apply(
            pfcf={"observations": [_fcf_record("2026-10-06")]}
        )
        self.assertEqual(inputs.current_fcf, 136_683_000_000.0)
        filed = provenance["current_fcf"]["filed_trailing"]
        self.assertIsNotNone(filed)
        self.assertEqual(filed["value"], 136_683_000_000.0)
        self.assertEqual(filed["source"], SOURCE_SEC_DERIVED)
        self.assertEqual(filed["basis"], BASIS_TTM)
        self.assertFalse(filed["used_by_engine"])
        self.assertEqual(len(filed["components"]), 4)

    def test_a_quarterly_free_cash_flow_is_never_the_trailing_one(self):
        """The admitted quarter is a quarter; it may not stand in for a year."""
        _, provenance = self._apply(
            pfcf={"observations": [_fcf_record("2026-10-06", value=51_552_000_000.0)]}
        )
        filed = provenance["current_fcf"]["filed_trailing"]
        # The trailing figure is a four-quarter window, and the quarter is one
        # of its four -- reported as itself, not as the trailing figure.
        self.assertEqual(len(filed["components"]), 4)
        self.assertIn(
            51_552_000_000.0,
            [c["value"] for c in filed["components"]],
        )
        self.assertIn(
            "latest quarter's free cash flow is a different quantity",
            filed["note"],
        )

    def test_the_qualified_filing_changes_what_is_reported_not_the_arithmetic(self):
        """The source decides what is reported; the arithmetic is the document's.

        The engine's number cannot move with the source: the document
        publishes the figure and recomputes the multiple from it, so a
        substituted figure would make the published formula stop reproducing
        the published number. What the source decides is whether a qualified
        filed figure is reported beside it, and whether it agrees.
        """
        market_cap = 4_918_530_543_600.0
        without = self._apply(pfcf={"observations": []})
        with_filed = self._apply(
            pfcf={"observations": [_fcf_record("2026-10-06", value=100_000_000_000.0)]}
        )
        # The engine's arithmetic is unchanged.
        self.assertEqual(
            without[0].current_fcf, with_filed[0].current_fcf
        )
        self.assertAlmostEqual(
            market_cap / without[0].current_fcf,
            market_cap / with_filed[0].current_fcf,
            places=9,
        )
        # What the source decides: whether a qualified filed figure is reported,
        # and whether it agrees.
        self.assertNotIn("filed_trailing", without[1]["current_fcf"])
        filed = with_filed[1]["current_fcf"]["filed_trailing"]
        self.assertIsNotNone(filed)
        self.assertFalse(filed["agrees_with_engine_input"])

    def test_the_filed_annual_ebitda_is_not_used_for_a_trailing_multiple(self):
        """A year's EBITDA is a different quantity from a trailing one."""
        inputs, provenance = self._apply()
        self.assertEqual(inputs.current_ebitda, 167_959_000_000.0)
        self.assertEqual(provenance["current_ebitda"]["source"], SOURCE_VENDOR)
        self.assertIn("not a trailing EBITDA", provenance["current_ebitda"]["note"])
        self.assertNotIn("filed_trailing", provenance["current_ebitda"])

    def test_a_refused_input_leaves_the_other_methods_able_to_compute(self):
        """One missing input must not take the others down with it."""
        inputs = self._inputs(
            current_fcf="UNAVAILABLE",
            current_revenue_currency="USD",
            current_market_cap_currency="USD",
        )
        analysis = MarketImpliedAssumptionsEngine.analyze(
            data=inputs,
            reference_multiple=28.0,
            pfcf_multiple=25.0,
            ps_multiple=9.0,
        )
        observed = analysis["observed_valuation"]
        self.assertIsNotNone(observed["current_pe"])
        self.assertIsNone(observed["current_pfcf"])
        self.assertIsNotNone(observed["current_ps"])
        # The cash-flow method is unavailable; the earnings method is not.
        methods = analysis["implied_assumptions"]
        self.assertIsNotNone(methods["forward_eps_at_reference_multiple"])


class TestTheApiReportsWhatTheEngineUsed(unittest.TestCase):
    """The reported calculation inputs are the engine's inputs."""

    def _run(self, mode):
        from fastapi.testclient import TestClient

        from web.app import create_app

        directory = tempfile.TemporaryDirectory(prefix="sofi-calc-")
        self.addCleanup(directory.cleanup)
        client = TestClient(create_app(archives_dir=directory.name))
        job = client.post(
            "/api/analyze", json={"ticker": "AAPL", "mode": mode}
        ).json()["job_id"]
        for _ in range(300):
            state = client.get(f"/api/jobs/{job}").json()
            if state["status"] in ("COMPLETED", "FAILED"):
                break
            time.sleep(1)
        self.assertEqual(state["status"], "COMPLETED", state.get("error"))
        return state.get("result") or {}

    def test_the_api_reports_the_engine_inputs(self):
        result = self._run("regression")
        items = {item["multiple"]: item for item in result.get("calculation_inputs") or []}
        self.assertEqual(sorted(items), ["ev_ebitda", "pe", "pfcf", "ps"])
        observed = (result.get("raw_analysis") or {}).get("observed_valuation") or {}
        provenance = (result.get("raw_analysis") or {}).get("input_provenance") or {}
        for multiple, item in items.items():
            with self.subTest(multiple=multiple):
                self.assertTrue(item["used_by_engine"])
                self.assertIsNotNone(item["source"])
                self.assertIsNotNone(item["basis"])
                self.assertIsNotNone(item["observed_multiple_formula"])
                # What the API reports as the input is the engine's input, and
                # the multiple it reports is the engine's multiple.
                metric = item["input_metric"]
                self.assertEqual(item["value"], provenance.get(metric, {}).get("value")
                                 if isinstance(provenance.get(metric, {}).get("value"), (int, float))
                                 else item["value"])
                self.assertEqual(
                    item["observed_multiple"], observed.get(_observed_key(multiple))
                )

    def test_an_input_that_is_not_there_is_not_reported_as_zero(self):
        result = self._run("regression")
        items = {item["multiple"]: item for item in result.get("calculation_inputs") or []}
        for item in items.values():
            if item["value"] is None:
                self.assertEqual(item["value_state"], "UNAVAILABLE")
            else:
                self.assertEqual(item["value_state"], "AVAILABLE")


def _observed_key(multiple):
    return {
        "pe": "current_pe",
        "pfcf": "current_pfcf",
        "ev_ebitda": "current_ev_ebitda",
        "ps": "current_ps",
    }[multiple]


@unittest.skipUnless(
    os.environ.get("ST_EVA_LIVE") == "1",
    "the live AAPL end-to-end test needs ST_EVA_LIVE=1",
)
class TestTheLiveAaplPath(unittest.TestCase):
    """The live AAPL path: the filed figures are the engine's inputs."""

    def test_the_live_path_reports_the_filed_trailing_figures(self):
        from fastapi.testclient import TestClient

        from web.app import create_app

        with tempfile.TemporaryDirectory(prefix="sofi-live-") as directory:
            client = TestClient(create_app(archives_dir=directory))
            job = client.post(
                "/api/analyze", json={"ticker": "AAPL", "mode": "live"}
            ).json()["job_id"]
            for _ in range(300):
                state = client.get(f"/api/jobs/{job}").json()
                if state["status"] in ("COMPLETED", "FAILED"):
                    break
                time.sleep(1)
            self.assertEqual(state["status"], "COMPLETED", state.get("error"))
            result = state.get("result") or {}
            items = {
                item["multiple"]: item for item in result.get("calculation_inputs") or []
            }
            observed = (result.get("raw_analysis") or {}).get("observed_valuation") or {}

            # The trailing earnings figure: the engine's own input is the
            # published figure, and the qualified filed trailing figure is
            # reported beside it, with its four directly stated quarters and
            # the furnished fourth quarter.
            pe = items["pe"]
            self.assertTrue(pe["used_by_engine"])
            self.assertEqual(pe["source"], SOURCE_VENDOR)
            self.assertIsNotNone(pe["filed_trailing"])
            filed_eps = pe["filed_trailing"]
            self.assertEqual(filed_eps["source"], SOURCE_SEC_DERIVED)
            self.assertEqual(filed_eps["basis"], BASIS_TTM)
            self.assertEqual(len(filed_eps["components"]), 4)
            self.assertFalse(filed_eps["used_by_engine"])

            # The trailing free cash flow: four quarters, reported beside the
            # engine's input.
            pfcf = items["pfcf"]
            self.assertTrue(pfcf["used_by_engine"])
            self.assertIsNotNone(pfcf["filed_trailing"])
            filed_fcf = pfcf["filed_trailing"]
            self.assertEqual(filed_fcf["source"], SOURCE_SEC_DERIVED)
            self.assertEqual(filed_fcf["basis"], BASIS_TTM)
            self.assertEqual(len(filed_fcf["components"]), 4)

            # The filed annual figures are reported, on their own basis.
            summary = result.get("admission_summary") or {}
            admitted = {m["metric"]: m for m in (summary.get("admitted_metrics") or [])}
            self.assertIn("depreciation_and_amortization", admitted)
            self.assertEqual(
                admitted["depreciation_and_amortization"]["period_end"], "2025-09-27"
            )
            self.assertEqual(
                admitted["operating_income"]["period_end"], "2025-09-27"
            )
            derivations = summary.get("derivations") or {}
            self.assertEqual(derivations["ebitda"]["value"], 144_748_000_000.0)

            # And the API's numbers are the engine's numbers.
            for multiple, item in items.items():
                with self.subTest(multiple=multiple):
                    self.assertEqual(
                        item["observed_multiple"], observed.get(_observed_key(multiple))
                    )


if __name__ == "__main__":
    unittest.main()
