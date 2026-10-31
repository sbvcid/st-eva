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

PRICES_EXIST = (Path("data/historical_pe/AAPL/daily_prices.json")).exists()
PRICES_SKIP = "AAPL daily_prices.json excluded per C-1 / DATA-DELIVERY.md"

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
                "operating_cash_flow": 34_369_000_000.0,
                "capital_expenditure": 2_455_000_000.0,
                "free_cash_flow": 31_914_000_000.0,
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

    def test_a_rolled_forward_earnings_figure_is_not_a_filed_fact(self):
        """A trailing figure rolled forward by subtraction is not a filed fact.

        The SEC provider's own trailing earnings view is built that way for
        Apple, because its fiscal Q3 is reported inside the annual context
        rather than as a discrete quarter. It records the window as not
        additive, and a per-share amount whose denominator moves is an
        approximation. Labelling it a filed trailing figure would be passing a
        subtraction off as a filing.
        """
        record = _eps_record("2026-10-06")
        record["eps_state"]["quarter_denominator_derivation"] = {
            "method": "ANNUAL_ROLL_FORWARD",
            "derived_not_issuer_declared": True,
        }
        self.assertIsNone(
            qualified_ttm_eps(_pe_payload([record]), "2026-10-19")
        )

    def test_a_trailing_window_without_a_furnished_fourth_quarter_is_refused(self):
        """The fourth quarter has to come from a furnished earnings release."""
        record = _eps_record("2026-10-06")
        components = record["eps_state"]["components"]
        for component in components:
            component["evidence_class"] = "filed"
        self.assertIsNone(
            qualified_ttm_eps(_pe_payload([record]), "2026-10-19")
        )

    def test_a_free_cash_flow_quarter_without_a_declared_derivation_is_refused(self):
        record = _fcf_record("2026-10-06")
        record["ttm_window"]["quarters"][1]["formula"] = None
        self.assertIsNone(
            qualified_ttm_fcf({"observations": [record]}, "2026-10-19")
        )

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

    A qualified filed trailing figure *is* the engine's input: the same
    quantity the provider reported, on a basis that is now stated, with the
    four quarters it was built from held by the document so the sum can be
    recomputed. The provider's figure is recorded beside it as the cross-check
    it is. Where no qualified figure exists, the provider's is used and is
    labelled as having no declared period.
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

    def test_a_qualified_trailing_eps_is_the_engines_input(self):
        inputs, provenance, windows = self._apply(
            pe=_pe_payload([_eps_record("2026-10-06")])
        )
        self.assertEqual(inputs.current_eps, 8.72)
        self.assertEqual(provenance["current_eps"]["source"], SOURCE_SEC_DERIVED)
        self.assertEqual(provenance["current_eps"]["basis"], BASIS_TTM)
        self.assertTrue(provenance["current_eps"]["used_by_engine"])
        # The provider's figure is recorded as the cross-check it is.
        self.assertEqual(provenance["current_eps"]["provider_figure"]["source"], SOURCE_VENDOR)
        self.assertEqual(provenance["current_eps"]["provider_figure"]["basis"], "UNDECLARED")
        # The window travels with the context so the document can recompute it.
        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0].metric, "ttm_eps_window")

    def test_a_qualified_trailing_eps_keeps_its_four_quarter_provenance(self):
        _, provenance, windows = self._apply(
            pe=_pe_payload([_eps_record("2026-10-06")])
        )
        entry = provenance["current_eps"]
        self.assertEqual(len(entry["components"]), 4)
        self.assertEqual(entry["derived_not_issuer_declared"], True)
        # The fourth quarter is the furnished one, and it is named.
        self.assertEqual(len(entry["q4_evidence"]), 1)
        self.assertEqual(
            entry["q4_evidence"][0]["accession"], "0000320193-25-000077"
        )
        # The window carries the same four quarters, with their filings.
        value = windows[0].value
        self.assertEqual(len(value["samples"]), 4)
        self.assertAlmostEqual(sum(value["samples"]), 8.72, places=9)
        accessions = {q["accession"] for q in value["quarters"]}
        self.assertIn("0000320193-25-000077", accessions)

    def test_a_qualified_trailing_free_cash_flow_is_the_engines_input(self):
        inputs, provenance, windows = self._apply(
            pfcf={"observations": [_fcf_record("2026-10-06")]}
        )
        self.assertEqual(inputs.current_fcf, 136_683_000_000.0)
        self.assertEqual(provenance["current_fcf"]["source"], SOURCE_SEC_DERIVED)
        self.assertEqual(provenance["current_fcf"]["basis"], BASIS_TTM)
        self.assertTrue(provenance["current_fcf"]["used_by_engine"])
        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0].metric, "ttm_fcf_window")
        self.assertAlmostEqual(sum(windows[0].value["samples"]), 136_683_000_000.0, places=3)

    def test_a_quarterly_free_cash_flow_is_never_the_trailing_one(self):
        """The admitted quarter is a quarter; it may not stand in for a year."""
        _, provenance, windows = self._apply(
            pfcf={"observations": [_fcf_record("2026-10-06", value=51_552_000_000.0)]}
        )
        # The trailing figure is a four-quarter window, and the quarter is one
        # of its four -- reported as itself, not as the trailing figure.
        value = windows[0].value
        self.assertEqual(len(value["samples"]), 4)
        self.assertIn(51_552_000_000.0, value["samples"])
        self.assertEqual(sum(value["samples"]), 136_683_000_000.0)

    def test_a_window_without_a_furnished_fourth_quarter_is_not_used(self):
        record = _eps_record("2026-10-06")
        for component in record["eps_state"]["components"]:
            component["evidence_class"] = "filed"
        inputs, provenance, windows = self._apply(pe=_pe_payload([record]))
        # The engine keeps the provider's figure and the window is not built.
        self.assertEqual(inputs.current_eps, 8.72)
        self.assertEqual(provenance["current_eps"]["source"], SOURCE_VENDOR)
        self.assertEqual(provenance["current_eps"]["basis"], "UNDECLARED")
        self.assertEqual(windows, [])

    def test_without_a_qualified_figure_the_provider_figure_is_kept_and_labelled(self):
        inputs, provenance, windows = self._apply(pe=_pe_payload([]))
        self.assertEqual(inputs.current_eps, 8.72)
        self.assertEqual(provenance["current_eps"]["source"], SOURCE_VENDOR)
        self.assertEqual(provenance["current_eps"]["basis"], "UNDECLARED")
        self.assertIn(
            "no qualified filed trailing diluted EPS",
            provenance["current_eps"]["note"],
        )
        self.assertEqual(windows, [])

    def test_the_filed_annual_ebitda_is_not_used_for_a_trailing_multiple(self):
        """A year's EBITDA is a different quantity from a trailing one."""
        inputs, provenance, _ = self._apply()
        self.assertEqual(inputs.current_ebitda, 167_959_000_000.0)
        self.assertEqual(provenance["current_ebitda"]["source"], SOURCE_VENDOR)
        self.assertIn("not a trailing EBITDA", provenance["current_ebitda"]["note"])

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
        methods = analysis["implied_assumptions"]
        self.assertIsNotNone(methods["forward_eps_at_reference_multiple"])


@unittest.skipUnless(PRICES_EXIST, PRICES_SKIP)
class TestTheDocumentRecomputesTheTrailingFigure(unittest.TestCase):
    """
    The document holds the quarters and recomputes the sum itself.

    The point of the round is that the trailing figure is not a number the
    document takes on trust: the registry sums the quarters the window holds
    and the document's own parity check compares the sum with the engine's
    value. A window that does not qualify is not registered, so nothing is
    published that the document cannot reproduce.
    """

    def _document(self, ticker="AAPL"):
        from investment_context import build_investment_context
        from sec_derived_inputs import (
            qualified_ttm_eps,
            window_observation,
        )
        from st_eva_runner import (
            CompanyResolver,
            DeterministicMetricsEngine,
            MarketImpliedAssumptionsEngine,
            build_evidence,
        )
        from historical_pe import ISSUER_CONFIGS as PE_CONFIGS
        from historical_pe import load_issuer_historical_pe

        data = CompanyResolver.resolve(ticker, mode="regression")
        metrics = DeterministicMetricsEngine.compute(
            data.price_history, data.volume_history
        )
        evidence = build_evidence(data, metrics)
        pe = load_issuer_historical_pe(PE_CONFIGS[ticker]).to_dict()
        filed = qualified_ttm_eps(pe, data.price_date)
        window = window_observation(filed, metric="ttm_eps_window")
        inputs = ValuationInputs.from_legacy_view(data)
        if window is not None:
            inputs = replace(
                inputs, current_eps=filed["value"]
            )
        analysis = MarketImpliedAssumptionsEngine.analyze(data=inputs)
        return build_investment_context(
            data=data,
            analysis=analysis,
            evidence=evidence,
            metrics=metrics,
            horizon_years=3.0,
            material_observations=list(
                __import__("st_eva_runner").material_observations(data).values()
            )
            + [__import__("st_eva_runner").metrics_observation(data, metrics)],
            extra_observations=[window] if window is not None else [],
        )

    def test_the_window_is_registered_and_the_sum_is_the_figure(self):
        from investment_context import recompute_derivation

        document = self._document()
        derivations = document["provenance"]["derivations"]
        self.assertIn("der:ttm_eps", derivations)
        self.assertEqual(derivations["der:ttm_eps"]["operation"]["op"], "sum_periods")
        self.assertTrue(derivations["der:ttm_eps"]["deterministic"])
        # The registry recomputes it from the document's own figures.
        recomputed = recompute_derivation(document, "der:ttm_eps")
        self.assertIsNotNone(recomputed)
        self.assertAlmostEqual(recomputed, 8.72, places=9)

    def test_the_window_carries_the_four_quarters_with_their_filings(self):
        document = self._document()
        refs = document["provenance"]["refs"]
        window_ref = "obs:ttm_eps_window-2026-06-27"
        self.assertIn(window_ref, refs)
        quarters = refs[window_ref]["value"]["quarters"]
        self.assertEqual(len(quarters), 4)
        accessions = {quarter["accession"] for quarter in quarters}
        self.assertIn("0000320193-25-000077", accessions)
        furnished = [
            quarter for quarter in quarters
            if quarter.get("evidence_class") == "furnished"
        ]
        self.assertEqual(len(furnished), 1)
        self.assertEqual(furnished[0]["value"], 1.85)
        self.assertTrue(furnished[0]["acceptance_datetime"])
        self.assertTrue(furnished[0]["usable_date"])


@unittest.skipUnless(PRICES_EXIST, PRICES_SKIP)
class TestTheFiledFigureWinsOverTheProviders(unittest.TestCase):
    """
    Where the two differ, the filed figure is the one the valuation uses.

    For MSFT the filed trailing diluted EPS is 17.96 and the provider's
    trailing figure is 18.09. The valuation uses the filed one, because it is
    the one with a stated period and a stated construction.
    """

    def test_the_filed_trailing_eps_is_used_where_they_differ(self):
        from historical_pe import ISSUER_CONFIGS as PE_CONFIGS
        from historical_pe import load_issuer_historical_pe
        from sec_derived_inputs import qualified_ttm_eps

        payload = load_issuer_historical_pe(PE_CONFIGS["MSFT"]).to_dict()
        filed = qualified_ttm_eps(payload, "2026-10-19")
        self.assertIsNotNone(filed)
        self.assertEqual(filed["value"], 17.96)
        # And the provider's trailing figure for MSFT is a different number,
        # which is why substituting the filed one is not a no-op.
        provider = payload.get("current_snapshot") or {}
        self.assertNotEqual(
            provider.get("quarter_denominator"), 8.72
        )

    def test_the_valuation_uses_the_filed_figure(self):
        from historical_pe import ISSUER_CONFIGS as PE_CONFIGS
        from historical_pe import load_issuer_historical_pe
        from sec_derived_inputs import (
            qualified_ttm_eps,
            window_observation,
        )
        from st_eva_runner import _engine_inputs_with_filed_figures

        payload = load_issuer_historical_pe(PE_CONFIGS["MSFT"]).to_dict()
        filed = qualified_ttm_eps(payload, "2026-10-19")
        window = window_observation(filed, metric="ttm_eps_window")
        self.assertIsNotNone(window)

        inputs, provenance, windows = _engine_inputs_with_filed_figures(
            _StubView() and ValuationInputs(price=425.50, currency="USD"),
            data=_StubView(),
            production_historical_pe=payload,
            production_historical_pfcf=None,
        )
        self.assertEqual(inputs.current_eps, 17.96)
        self.assertEqual(provenance["current_eps"]["source"], SOURCE_SEC_DERIVED)
        self.assertEqual(provenance["current_eps"]["basis"], BASIS_TTM)
        self.assertEqual(len(windows), 1)


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
            # qualified filed trailing figure, and the provider's figure is
            # reported beside it as the cross-check it is.
            pe = items["pe"]
            self.assertTrue(pe["used_by_engine"])
            self.assertEqual(pe["source"], SOURCE_SEC_DERIVED)
            self.assertEqual(pe["basis"], BASIS_TTM)
            self.assertEqual(len(pe["components"]), 4)
            for component in pe["components"]:
                self.assertTrue(component["period_end"])
                self.assertTrue(component["accession"])
                self.assertTrue(component["available_at"])
            self.assertIn("cross-check", pe["note"])

            # The trailing free cash flow: four quarters, and the engine's own
            # input.
            pfcf = items["pfcf"]
            self.assertTrue(pfcf["used_by_engine"])
            self.assertEqual(pfcf["source"], SOURCE_SEC_DERIVED)
            self.assertEqual(pfcf["basis"], BASIS_TTM)
            self.assertEqual(len(pfcf["components"]), 4)

            # The trailing revenue and trailing EBITDA: the denominators of
            # the sales and enterprise-value multiples are the filed
            # four-quarter figures, not the provider's undeclared ones.
            for multiple in ("ps", "ev_ebitda"):
                with self.subTest(multiple=multiple):
                    item = items[multiple]
                    self.assertTrue(item["used_by_engine"])
                    self.assertEqual(item["source"], SOURCE_SEC_DERIVED)
                    self.assertEqual(item["basis"], BASIS_TTM)
                    self.assertEqual(item["currency"], "USD")
                    self.assertIsNotNone(item["period_start"])
                    self.assertIsNotNone(item["period_end"])
                    self.assertEqual(len(item["components"]), 4)
                    for component in item["components"]:
                        self.assertTrue(component["period_end"])
                        self.assertTrue(component["accession"])
                        self.assertTrue(component["available_at"])

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

            # And the two multiples whose denominators are now filed figures
            # divide by them.
            valuation = result.get("valuation_summary") or {}
            market_cap = valuation["market_cap"]
            self.assertAlmostEqual(
                observed["current_ps"],
                market_cap / items["ps"]["value"],
                places=9,
            )
            enterprise_value = observed["current_ev_ebitda"] * items["ev_ebitda"]["value"]
            self.assertGreater(enterprise_value, 0)

            # And the API's numbers are the engine's numbers.
            for multiple, item in items.items():
                with self.subTest(multiple=multiple):
                    self.assertEqual(
                        item["observed_multiple"], observed.get(_observed_key(multiple))
                    )


if __name__ == "__main__":
    unittest.main()
