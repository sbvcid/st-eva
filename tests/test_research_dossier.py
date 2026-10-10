"""
Tests for the research dossier and the multi-scenario valuation layers.

These check the properties a research reader depends on: that every figure
carries its condition, that methods are reported separately rather than
blended, that scenarios are never given a probability or a ranking, and that
identical inputs reproduce an identical dossier.
"""
from __future__ import annotations

import json
import sys
import unittest

sys.path.insert(0, ".")

from data_contract import Observation, ValidationStatus
from financial_history import HISTORY_FORMULA_VERSION
from report_formatter import render_report
from research_dossier import (
    DOSSIER_VERSION,
    SECTION_ORDER,
    build_dossier,
    render_dossier,
)
from reverse_requirements import (
    FORMULA_VERSION,
    ReferenceMultiple,
    build_reverse_requirements_report,
    exit_multiples_from_band,
    valuation_method_scenarios,
)
from reverse_requirements import EpsAnchor, ANCHOR_TTM
from st_eva_runner import run_st_eva


def _anchor(value: float = 4.0) -> EpsAnchor:
    return EpsAnchor(
        value=value,
        basis=ANCHOR_TTM,
        months_covered=12.0,
        period_label="TTM to 2026-09-30",
        provider="fixture",
        currency="USD",
    )


def _report(**overrides):
    base = dict(
        price=100.0,
        ticker="TEST",
        currency="USD",
        as_of="2026-09-30",
        price_source="fixture",
        horizons_years=[1.0, 2.0],
        required_returns=[0.10],
        exit_multiples=[ReferenceMultiple(value=20.0, source="user_supplied")],
        start_anchor=_anchor(),
        current_pe=25.0,
        market_cap=1000.0,
        enterprise_value=1200.0,
        free_cash_flow=50.0,
        ebitda=100.0,
        revenue=400.0,
        pfcf_multiple=20.0,
        ev_ebitda_multiple=12.0,
        ps_multiple=2.5,
        valuation_multiples={
            "pe": ReferenceMultiple(value=20.0, source="user_supplied"),
            "revenue": ReferenceMultiple(value=2.5, source="user_supplied"),
            "cash_flow": ReferenceMultiple(value=20.0, source="user_supplied"),
            "enterprise_value": ReferenceMultiple(value=12.0, source="user_supplied"),
        },
        dcf_inputs=None,
    )
    base.update(overrides)
    report = build_reverse_requirements_report(**base)
    # The runner stamps these two after assembly; the fixture mirrors that so
    # the dossier is exercised against the shape it actually receives.
    report["status"] = "COMPUTED"
    report["status_reason"] = None
    report.setdefault(
        "financial_history",
        {
            "formula_version": HISTORY_FORMULA_VERSION,
            "series": {},
            "growth": {},
            "margins": {},
            "observation_count": 0,
            "source_provider": None,
            "unavailable": [],
        },
    )
    return report


def _result(**overrides):
    """A minimal run-result shape, as the runner would produce it."""
    base = {
        "ticker": "TEST",
        "company_name": "Test Co",
        "as_of": "2026-09-30",
        "market_snapshot": {
            "price": 100.0,
            "currency": "USD",
            "exchange": "TEST",
            "provider": "fixture",
            "source": "fixture source",
            "source_type": "API_LIVE",
        },
        "data_quality": {
            "discrepancy_status": "SINGLE_SOURCE",
            "acquisition_errors": [],
            "consensus_forward_eps_period": "+1y",
        },
        "observed_valuation": {
            "current_pe": 25.0,
            "forward_pe": 22.0,
            "consensus_forward_pe": 21.5,
            "current_ps": 2.5,
            "current_pfcf": 20.0,
            "current_ev_ebitda": 12.0,
            "historical_pe_band": {"median": 22.0, "observations": 40},
            "historical_ps_band": None,
            "historical_pfcf_band": None,
            "historical_ev_ebitda_band": None,
        },
        "consensus_cross_check": {
            "consensus_forward_eps": 4.6,
            "price_at_historical_median_pe": 101.2,
            "price_gap_vs_historical_median_on_consensus_eps": 0.012,
        },
        "fundamental_snapshot": {
            "current_market_cap": 1000.0,
            "current_enterprise_value": 1200.0,
            "current_fcf": 50.0,
            "current_ebitda": 100.0,
            "current_revenue": 400.0,
        },
        "reference": {
            "historical_band_status": {"pe": "USABLE_FOR_REFERENCE"},
            "min_observations_for_reference": 20,
        },
        "market_metrics": {},
        "reverse_requirements": _report(),
        "missing_data": ["historical_pfcf_band"],
        "limitations": ["A price does not identify one forecast."],
    }
    base.update(overrides)
    return base


class TestBandScenarioMultiples(unittest.TestCase):
    def test_adequate_band_yields_percentile_scenarios(self):
        multiples, unavailable = exit_multiples_from_band(
            {"10th": 15.0, "25th": 18.0, "median": 22.0, "75th": 26.0, "90th": 30.0, "observations": 40},
            min_observations=20,
        )
        self.assertEqual(unavailable, [])
        self.assertEqual([m.value for m in multiples], [15.0, 18.0, 22.0, 26.0, 30.0])
        self.assertTrue(all(m.source == "historical_pe_band_percentile" for m in multiples))
        self.assertTrue(all(m.sample_size == 40 for m in multiples))

    def test_thin_band_produces_no_scenario_and_says_why(self):
        multiples, unavailable = exit_multiples_from_band(
            {"median": 35.6, "observations": 8}, min_observations=20
        )
        self.assertEqual(multiples, [])
        self.assertEqual(unavailable[0]["reason_kind"], "INSUFFICIENT_OBSERVATIONS")
        self.assertIn("descriptive statistic only", unavailable[0]["reason"])

    def test_band_without_declared_count_is_usable(self):
        multiples, unavailable = exit_multiples_from_band(
            {"median": 22.0}, min_observations=20
        )
        self.assertEqual(len(multiples), 1)
        self.assertEqual(unavailable, [])

    def test_non_positive_percentiles_are_skipped(self):
        multiples, _ = exit_multiples_from_band(
            {"10th": 0.0, "25th": 18.0, "median": 22.0, "observations": 40},
            min_observations=20,
        )
        self.assertNotIn(0.0, [m.value for m in multiples])

    def test_absent_band_yields_nothing_without_an_error(self):
        multiples, unavailable = exit_multiples_from_band(None, min_observations=20)
        self.assertEqual(multiples, [])
        self.assertEqual(unavailable, [])


class TestValuationMethods(unittest.TestCase):
    def test_each_method_computes_independently(self):
        block = valuation_method_scenarios(
            price=100.0,
            shares=10.0,
            market_cap=1000.0,
            enterprise_value=1200.0,
            free_cash_flow=50.0,
            ebitda=100.0,
            revenue=400.0,
            trailing_eps=4.0,
            multiples={
                "pe": ReferenceMultiple(value=20.0, source="user"),
                "revenue": ReferenceMultiple(value=2.5, source="user"),
                "cash_flow": ReferenceMultiple(value=20.0, source="user"),
                "enterprise_value": ReferenceMultiple(value=12.0, source="user"),
            },
        )
        methods = block["methods"]
        self.assertAlmostEqual(methods["earnings_multiple"]["implied"], 5.0, places=12)
        self.assertAlmostEqual(methods["revenue_multiple"]["implied"], 400.0, places=12)
        self.assertAlmostEqual(methods["cash_flow_multiple"]["implied"], 50.0, places=12)
        self.assertAlmostEqual(methods["enterprise_value_multiple"]["implied"], 100.0, places=12)
        for name in ("earnings_multiple", "revenue_multiple", "cash_flow_multiple", "enterprise_value_multiple"):
            self.assertEqual(methods[name]["status"], "COMPUTED", name)

    def test_method_without_a_multiple_is_reported_not_filled(self):
        block = valuation_method_scenarios(
            price=100.0, shares=10.0, market_cap=1000.0, enterprise_value=1200.0,
            free_cash_flow=50.0, ebitda=100.0, revenue=400.0, trailing_eps=4.0,
            multiples={"pe": ReferenceMultiple(value=20.0, source="user")},
        )
        self.assertEqual(block["methods"]["revenue_multiple"]["status"], "NOT_COMPUTED")
        self.assertIsNone(block["methods"]["revenue_multiple"]["implied"])
        items = [entry["item"] for entry in block["unavailable"]]
        self.assertIn("valuation_method.revenue_multiple", items)

    def test_missing_input_is_distinguished_from_a_missing_multiple(self):
        block = valuation_method_scenarios(
            price=100.0, shares=None, market_cap=None, enterprise_value=None,
            free_cash_flow=50.0, ebitda=100.0, revenue=400.0, trailing_eps=4.0,
            multiples={"revenue": ReferenceMultiple(value=2.5, source="user")},
        )
        entry = [e for e in block["unavailable"] if e["item"] == "valuation_method.revenue_multiple"][0]
        self.assertEqual(entry["reason_kind"], "MISSING_INPUT")

    def test_no_winner_is_selected_and_nothing_is_averaged(self):
        block = valuation_method_scenarios(
            price=100.0, shares=10.0, market_cap=1000.0, enterprise_value=1200.0,
            free_cash_flow=50.0, ebitda=100.0, revenue=400.0, trailing_eps=4.0,
            multiples={
                "pe": ReferenceMultiple(value=20.0, source="user"),
                "revenue": ReferenceMultiple(value=2.5, source="user"),
            },
        )
        self.assertIn("disagreement", block)
        self.assertIn("no winner is selected", block["disagreement"]["note"])
        # There is no composite or average field anywhere in the block.
        self.assertNotIn("composite", block)
        self.assertNotIn("average", block)
        self.assertNotIn("blended", block)

    def test_each_method_carries_its_own_multiple_provenance(self):
        block = valuation_method_scenarios(
            price=100.0, shares=10.0, market_cap=1000.0, enterprise_value=1200.0,
            free_cash_flow=50.0, ebitda=100.0, revenue=400.0, trailing_eps=4.0,
            multiples={
                "pe": ReferenceMultiple(value=20.0, source="user"),
                "revenue": ReferenceMultiple(value=2.5, source="band_median", sample_size=40),
            },
        )
        self.assertEqual(block["methods"]["earnings_multiple"]["reference_multiple"]["source"], "user")
        self.assertEqual(block["methods"]["revenue_multiple"]["reference_multiple"]["sample_size"], 40)

    def test_implied_net_margin_needs_both_multiples_and_shares(self):
        with_shares = valuation_method_scenarios(
            price=100.0, shares=10.0, market_cap=1000.0, enterprise_value=1200.0,
            free_cash_flow=50.0, ebitda=100.0, revenue=400.0, trailing_eps=4.0,
            multiples={
                "pe": ReferenceMultiple(value=20.0, source="user"),
                "revenue": ReferenceMultiple(value=2.5, source="user"),
            },
        )
        self.assertEqual(with_shares["methods"]["implied_net_margin"]["status"], "COMPUTED")

        without_price = valuation_method_scenarios(
            price=0.0, shares=None, market_cap=1000.0, enterprise_value=1200.0,
            free_cash_flow=50.0, ebitda=100.0, revenue=400.0, trailing_eps=4.0,
            multiples={"pe": ReferenceMultiple(value=20.0, source="user")},
        )
        self.assertEqual(without_price["methods"]["implied_net_margin"]["status"], "NOT_COMPUTED")


def _all_keys(value, seen=None):
    """Every mapping key anywhere in a nested structure."""
    if seen is None:
        seen = set()
    if isinstance(value, dict):
        for key, child in value.items():
            seen.add(str(key).lower())
            _all_keys(child, seen)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _all_keys(child, seen)
    return seen


class TestScenarioSemantics(unittest.TestCase):
    def test_scenarios_carry_no_probability_or_ranking(self):
        # Checked on field names rather than on prose: the disclaimers
        # legitimately contain words like "ranked" and "probability" in the
        # negative, so a substring search over the text would fail on the very
        # sentences that do the work.
        report = _report()
        forbidden = {
            "probability",
            "likelihood",
            "rank",
            "ranking",
            "weight",
            "weighting",
            "expected_value",
            "score",
            "confidence",
            "best_case",
            "most_likely",
        }
        self.assertEqual(_all_keys(report) & forbidden, set())

    def test_no_numeric_weighting_field_exists_on_a_scenario(self):
        row = _report()["reverse_requirements_matrix"][0]
        for key in row:
            self.assertNotIn("weight", key.lower())
            self.assertNotIn("probab", key.lower())

    def test_matrix_is_not_presented_as_a_forecast(self):
        report = _report()
        text = " ".join(report["reading_notes"]).lower()
        self.assertIn("not a forecast", text)

    def test_each_row_names_its_condition(self):
        report = _report()
        for row in report["reverse_requirements_matrix"]:
            self.assertIn("conditionality", row["exit_multiple"])
            self.assertEqual(row["required_return_basis"], "PRICE_RETURN_ONLY")


class TestDossierStructure(unittest.TestCase):
    def test_sections_appear_in_the_declared_order(self):
        dossier = build_dossier(_result())
        self.assertEqual(dossier["section_order"], list(SECTION_ORDER))
        self.assertEqual(list(dossier["sections"].keys()), list(SECTION_ORDER))

    def test_every_section_is_present_even_when_empty(self):
        dossier = build_dossier(_result())
        for key in SECTION_ORDER:
            self.assertIn(key, dossier["sections"])
            self.assertIn("title", dossier["sections"][key])

    def test_dossier_records_every_formula_version(self):
        dossier = build_dossier(_result())
        self.assertEqual(dossier["formula_versions"]["reverse_requirements"], FORMULA_VERSION)
        self.assertEqual(dossier["formula_versions"]["financial_history"], HISTORY_FORMULA_VERSION)
        self.assertEqual(dossier["formula_versions"]["dossier"], DOSSIER_VERSION)

    def test_dossier_carries_the_run_fingerprint(self):
        dossier = build_dossier(_result())
        self.assertEqual(dossier["fingerprint"], _report()["fingerprint"])

    def test_scope_statement_disclaims_probabilities(self):
        statement = build_dossier(_result())["scope_statement"]
        for phrase in ("probabilit", "rank", "single expected value"):
            self.assertIn(phrase, statement.lower())

    def test_dossier_is_deterministic(self):
        self.assertEqual(build_dossier(_result()), build_dossier(_result()))

    def test_dossier_is_json_serialisable(self):
        json.dumps(build_dossier(_result()), ensure_ascii=False)

    def test_dossier_contains_no_stance_or_verdict_vocabulary(self):
        text = render_dossier(build_dossier(_result()))
        for forbidden in ("目標價", "買進", "賣出", "偏多", "觀望", "評等", "建議", "probability of"):
            self.assertNotIn(forbidden, text)


class TestDossierRendering(unittest.TestCase):
    def test_renders_all_sections(self):
        text = render_dossier(build_dossier(_result()))
        for key in SECTION_ORDER:
            self.assertIn(build_dossier(_result())["sections"][key]["title"].split(" /")[0], text)

    def test_renders_the_matrix(self):
        text = render_dossier(build_dossier(_result()))
        self.assertIn("所需EPS", text)
        self.assertIn("所需CAGR", text)

    def test_renders_the_rate_families_separately(self):
        text = render_dossier(build_dossier(_result()))
        self.assertIn("[1] 無風險利率", text)
        self.assertIn("[2] CAPM 股權要求報酬", text)
        self.assertIn("[3] 投資人設定報酬率", text)

    def test_renders_missing_data_with_reasons(self):
        text = render_dossier(build_dossier(_result()))
        self.assertIn("不可計算", text)
        self.assertIn("historical_pfcf_band", text)

    def test_renders_without_a_computed_matrix(self):
        empty = _report(start_anchor=_anchor())
        empty["status"] = "NOT_COMPUTED"
        empty["status_reason"] = "no positive starting EPS"
        text = render_dossier(build_dossier(_result(reverse_requirements=empty)))
        self.assertIn("未計算", text)
        self.assertIn("no positive starting EPS", text)

    def test_renders_a_history_that_was_not_acquired(self):
        dossier = build_dossier(_result())
        dossier["sections"]["financial_history"]["acquired"] = False
        text = render_dossier(dossier)
        self.assertIn("未取得財報資料", text)

    def test_rendering_is_deterministic(self):
        dossier = build_dossier(_result())
        self.assertEqual(render_dossier(dossier), render_dossier(dossier))


class TestDossierInARealRun(unittest.TestCase):
    """The dossier must be reachable from an actual run, not only in isolation."""

    def test_run_produces_a_dossier_when_requested(self):
        result = run_st_eva(
            "MSFT", mode="regression", save_snapshot=False, render_dossier_report=True
        )
        self.assertIn("research_dossier", result)
        self.assertIn("dossier_report_text", result)
        self.assertIn("研究資料冊", result["dossier_report_text"])

    def test_run_without_the_flag_has_no_dossier(self):
        result = run_st_eva("MSFT", mode="regression", save_snapshot=False)
        self.assertNotIn("research_dossier", result)

    def test_dossier_reflects_the_runs_own_matrix(self):
        result = run_st_eva(
            "MSFT", mode="regression", save_snapshot=False, render_dossier_report=True
        )
        dossier = result["research_dossier"]
        self.assertEqual(
            dossier["fingerprint"], result["reverse_requirements"]["fingerprint"]
        )
        self.assertEqual(
            len(dossier["sections"]["reverse_requirements"]["matrix"]),
            result["reverse_requirements"]["matrix_size"],
        )

    def test_financial_history_is_absent_by_default(self):
        result = run_st_eva("MSFT", mode="regression", save_snapshot=False)
        history = result["reverse_requirements"]["financial_history"]
        self.assertEqual(history["observation_count"], 0)
        self.assertEqual(history["unavailable"][0]["reason_kind"], "NOT_ACQUIRED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
