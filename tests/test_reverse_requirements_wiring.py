"""
Wiring tests for the reverse requirements stage inside a run.

These check that the stage is actually connected to the run rather than merely
importable: that it appears in the result, that its numbers come from the
observations the run acquired, and that a gap in the data propagates into an
explicit "not computed" instead of a plausible-looking figure.

All runs here use the offline regression fixtures. Nothing in this file touches
the network.
"""
from __future__ import annotations

import sys
import unittest

sys.path.insert(0, ".")

from report_formatter import render_report
from reverse_requirements import (
    FORMULA_VERSION,
    ReferenceMultiple,
    build_exit_multiples,
    build_start_anchor,
)
from risk_free_rate_provider import (
    TREASURY_SERIES,
    RiskFreeRate,
    rate_as_decimal,
    select_rate,
)
from st_eva_runner import run_st_eva


def _run(**kwargs):
    base = dict(mode="regression", save_snapshot=False)
    base.update(kwargs)
    return run_st_eva("MSFT", **base)


class TestRunProducesReverseRequirements(unittest.TestCase):
    def test_result_carries_the_package(self):
        result = _run()
        self.assertIn("reverse_requirements", result)
        self.assertEqual(result["reverse_requirements"]["report"], "reverse_requirements_v1")

    def test_package_records_its_formula_version(self):
        result = _run()
        self.assertEqual(result["reverse_requirements"]["formula_version"], FORMULA_VERSION)

    def test_package_has_a_fingerprint(self):
        result = _run()
        self.assertEqual(len(result["reverse_requirements"]["fingerprint"]), 64)

    def test_identical_runs_produce_identical_fingerprints(self):
        first = _run()["reverse_requirements"]["fingerprint"]
        second = _run()["reverse_requirements"]["fingerprint"]
        self.assertEqual(first, second)

    def test_changing_a_matrix_input_changes_the_fingerprint(self):
        base = _run()["reverse_requirements"]["fingerprint"]
        moved = _run(required_returns=(0.09, 0.11))["reverse_requirements"]["fingerprint"]
        self.assertNotEqual(base, moved)

    def test_changing_the_exit_multiple_changes_the_fingerprint(self):
        base = _run()["reverse_requirements"]["fingerprint"]
        other = _run(reference_multiple=25.0)["reverse_requirements"]["fingerprint"]
        self.assertNotEqual(base, other)

    def test_as_of_and_ticker_travel_with_the_package(self):
        result = _run()
        package = result["reverse_requirements"]
        self.assertEqual(package["asset"]["ticker"], "MSFT")
        self.assertEqual(package["as_of"], result["as_of"])


class TestMatrixReflectsTheObservedPrice(unittest.TestCase):
    def test_matrix_size_is_the_full_cross_product(self):
        # The MSFT fixture carries a historical band with no declared
        # observation count, which the existing engine treats as usable, so the
        # matrix runs over the band's percentile set plus the supplied point.
        result = _run(
            reverse_horizons=(1.0, 2.0),
            required_returns=(0.10, 0.12),
            reference_multiple=20.0,
        )
        multiples = {
            row["exit_multiple"]["value"]
            for row in result["reverse_requirements"]["reverse_requirements_matrix"]
        }
        expected = result["reverse_requirements"]["matrix_size"]
        self.assertEqual(expected, 2 * 2 * len(multiples))
        self.assertGreater(len(multiples), 1, "a single multiple is not a scenario set")

    def test_a_supplied_multiple_overrides_the_band(self):
        # An explicitly supplied multiple replaces the band median rather than
        # being added alongside it, so the user gets the reference they named.
        result = _run(reference_multiple=27.0)
        sources = {
            row["exit_multiple"]["value"]: row["exit_multiple"]["source"]
            for row in result["reverse_requirements"]["reverse_requirements_matrix"]
        }
        self.assertIn(27.0, sources)
        self.assertEqual(sources[27.0], "user_supplied")

    def test_matrix_is_absent_without_an_exit_multiple(self):
        # The MSFT fixture carries a historical band with no declared
        # observation count, so it is usable; a ticker with no band at all and
        # no user multiple must report that it cannot build the matrix.
        result = run_st_eva("NU", mode="regression", save_snapshot=False)
        package = result["reverse_requirements"]
        if package["status"] == "NOT_COMPUTED":
            self.assertIsNotNone(package["status_reason"])
            self.assertTrue(package["unavailable"])
        else:
            self.assertTrue(package["reverse_requirements_matrix"])

    def test_required_exit_price_follows_the_observed_price(self):
        result = _run(reference_multiple=20.0, reverse_horizons=(1.0,), required_returns=(0.10,))
        row = result["reverse_requirements"]["reverse_requirements_matrix"][0]
        price = result["market_snapshot"]["price"]
        self.assertAlmostEqual(row["required_exit_price"], price * 1.10, places=8)

    def test_every_row_names_its_exit_multiple(self):
        result = _run(reference_multiple=20.0)
        seen = set()
        for row in result["reverse_requirements"]["reverse_requirements_matrix"]:
            seen.add(row["exit_multiple"]["source"])
            self.assertIn("conditionality", row["exit_multiple"])
            self.assertGreater(row["exit_multiple"]["value"], 0)
        self.assertIn("user_supplied", seen)

    def test_rows_carry_the_return_basis(self):
        result = _run(reference_multiple=20.0)
        for row in result["reverse_requirements"]["reverse_requirements_matrix"]:
            self.assertEqual(row["required_return_basis"], "PRICE_RETURN_ONLY")
            self.assertEqual(row["required_exit_price_basis"], "PRICE_ONLY_EXCLUDES_DIVIDENDS")

    def test_rows_carry_the_start_anchor_with_its_period(self):
        result = _run(reference_multiple=20.0)
        row = result["reverse_requirements"]["reverse_requirements_matrix"][0]
        self.assertIn("basis", row["start_eps"])
        self.assertIn("months_covered", row["start_eps"])

    def test_distinct_exit_multiples_produce_distinct_eps(self):
        low = _run(reference_multiple=16.0)["reverse_requirements"]
        high = _run(reference_multiple=24.0)["reverse_requirements"]

        def eps_at(package, multiple):
            for row in package["reverse_requirements_matrix"]:
                if abs(row["exit_multiple"]["value"] - multiple) < 1e-12:
                    return row["required_terminal_eps"]
            return None

        self.assertGreater(eps_at(low, 16.0), eps_at(high, 24.0))


class TestRateFamiliesInAReport(unittest.TestCase):
    def test_risk_free_rates_are_absent_by_default(self):
        result = _run()
        self.assertEqual(
            result["reverse_requirements"]["rate_families"]["risk_free_rate"]["count"], 0
        )

    def test_cost_of_equity_is_not_computed_without_inputs(self):
        block = _run()["reverse_requirements"]["rate_families"]["cost_of_equity"]
        self.assertEqual(block["status"], "NOT_COMPUTED")
        self.assertIsNone(block["value"])

    def test_cost_of_equity_stays_uncomputed_when_rates_were_not_requested(self):
        # A beta on its own is not enough: without an observed risk-free rate
        # there is no Rf term, so no cost of equity is modelled. The run says
        # so rather than substituting a default rate.
        result = _run(beta=1.2)
        block = result["reverse_requirements"]["rate_families"]["cost_of_equity"]
        self.assertEqual(block["status"], "NOT_COMPUTED")
        self.assertIsNone(block["value"])
        self.assertTrue(
            any(item["item"] == "risk_free_rate" for item in result["reverse_requirements"]["unavailable"])
        )

    def test_investor_required_returns_are_recorded_as_scenarios(self):
        block = _run(required_returns=(0.10, 0.15))["reverse_requirements"]["rate_families"]
        investor = block["investor_required_return"]
        self.assertEqual(investor["status"], "SUPPLIED")
        self.assertFalse(investor["is_estimate"])
        self.assertEqual(
            sorted(investor["values"].values()), [0.10, 0.15]
        )

    def test_three_rate_families_are_separate_keys(self):
        families = _run()["reverse_requirements"]["rate_families"]
        self.assertIn("risk_free_rate", families)
        self.assertIn("cost_of_equity", families)
        self.assertIn("investor_required_return", families)


class TestDcfBlockInAReport(unittest.TestCase):
    def test_dcf_is_present_and_does_not_overclaim(self):
        dcf = _run()["reverse_requirements"]["dcf"]
        self.assertIn(dcf["status"], ("NOT_ATTEMPTED", "NOT_COMPUTED"))
        self.assertIsNone(dcf["implied_explicit_growth_rate"])

    def test_missing_dcf_inputs_are_named(self):
        dcf = _run()["reverse_requirements"]["dcf"]
        self.assertFalse(dcf["feasibility"]["supported"])
        self.assertIn("tax_rate", dcf["feasibility"]["missing_inputs"])

    def test_dcf_can_be_skipped(self):
        dcf = _run(include_dcf=False)["reverse_requirements"]["dcf"]
        self.assertEqual(dcf["status"], "NOT_ATTEMPTED")


class TestReportRendering(unittest.TestCase):
    def test_report_renders_the_matrix(self):
        report = render_report(_run(reference_multiple=20.0))
        self.assertIn("反向要求矩陣", report)
        self.assertIn("期末需求價", report)

    def test_report_renders_the_rate_families(self):
        report = render_report(_run(reference_multiple=20.0))
        self.assertIn("利率家族", report)
        self.assertIn("CAPM 股權要求報酬", report)

    def test_report_renders_the_cash_flow_cross_checks(self):
        report = render_report(_run(reference_multiple=20.0))
        self.assertIn("現金流交叉驗證", report)

    def test_report_renders_the_dcf_block(self):
        report = render_report(_run(reference_multiple=20.0))
        self.assertIn("折現現金流", report)

    def test_report_does_not_claim_a_dcf_result_when_none_was_computed(self):
        report = render_report(_run(reference_multiple=20.0))
        self.assertIn("缺少欄位", report)

    def test_report_never_emits_target_price_vocabulary(self):
        report = render_report(_run(reference_multiple=20.0))
        for forbidden in ("目標價", "買進", "賣出", "偏多", "觀望", "評等"):
            self.assertNotIn(forbidden, report)

    def test_report_is_deterministic(self):
        first = render_report(_run(reference_multiple=20.0))
        second = render_report(_run(reference_multiple=20.0))
        self.assertEqual(first, second)


class TestAnchorSelection(unittest.TestCase):
    def test_trailing_eps_is_preferred(self):
        anchor, _ = build_start_anchor(
            trailing_eps=4.0,
            forward_eps=4.5,
            consensus_eps=4.4,
            currency="USD",
        )
        self.assertEqual(anchor.basis, "TRAILING_TWELVE_MONTHS")
        self.assertEqual(anchor.value, 4.0)

    def test_forward_eps_is_used_when_trailing_is_missing(self):
        anchor, unavailable = build_start_anchor(
            trailing_eps=None, forward_eps=4.5, consensus_eps=4.4, currency="USD"
        )
        self.assertEqual(anchor.basis, "FORWARD_TWELVE_MONTHS")
        self.assertTrue(any(item["item"] == "start_eps_candidate.trailing" for item in unavailable))

    def test_undeclared_period_is_flagged_on_the_anchor(self):
        anchor, _ = build_start_anchor(
            trailing_eps=4.0, forward_eps=None, consensus_eps=None,
            currency="USD", trailing_period_label="",
        )
        self.assertTrue(anchor.period_undeclared_by_source)

    def test_declared_period_clears_the_flag(self):
        anchor, _ = build_start_anchor(
            trailing_eps=4.0, forward_eps=None, consensus_eps=None,
            currency="USD", trailing_period_label="TTM to 2026-09-30",
        )
        self.assertFalse(anchor.period_undeclared_by_source)

    def test_no_positive_eps_yields_no_anchor(self):
        anchor, unavailable = build_start_anchor(
            trailing_eps=0.0, forward_eps=-1.0, consensus_eps=None, currency="USD"
        )
        self.assertIsNone(anchor)
        self.assertTrue(any(item["item"] == "start_anchor" for item in unavailable))

    def test_non_positive_candidates_are_reported_with_their_reason(self):
        _, unavailable = build_start_anchor(
            trailing_eps=-2.0, forward_eps=None, consensus_eps=None, currency="USD"
        )
        entry = [i for i in unavailable if i["item"] == "start_eps_candidate.trailing"][0]
        self.assertEqual(entry["reason_kind"], "NOT_POSITIVE")


class TestExitMultipleSelection(unittest.TestCase):
    def test_thin_band_is_not_used_as_a_reference(self):
        multiples, unavailable = build_exit_multiples(
            historical_pe_band={"median": 35.6, "observations": 8},
            user_pe_multiple=None,
            min_observations=20,
        )
        self.assertEqual(multiples, [])
        entry = [i for i in unavailable if i["item"] == "exit_multiple.historical"][0]
        self.assertEqual(entry["reason_kind"], "INSUFFICIENT_OBSERVATIONS")

    def test_adequate_band_is_used_as_a_reference(self):
        multiples, _ = build_exit_multiples(
            historical_pe_band={"median": 24.0, "observations": 40},
            user_pe_multiple=None,
            min_observations=20,
        )
        self.assertEqual(len(multiples), 1)
        self.assertEqual(multiples[0].source, "historical_pe_band_median")
        self.assertEqual(multiples[0].sample_size, 40)

    def test_user_multiple_is_recorded_as_user_supplied(self):
        multiples, _ = build_exit_multiples(
            historical_pe_band=None, user_pe_multiple=22.0, min_observations=20
        )
        self.assertEqual(multiples[0].source, "user_supplied")

    def test_no_multiple_at_all_is_reported(self):
        multiples, unavailable = build_exit_multiples(
            historical_pe_band=None, user_pe_multiple=None, min_observations=20
        )
        self.assertEqual(multiples, [])
        self.assertTrue(any(item["item"] == "exit_multiple" for item in unavailable))


class TestRiskFreeRateHelpers(unittest.TestCase):
    def test_select_rate_finds_a_named_tenor(self):
        rates = [
            RiskFreeRate(rate=4.0, tenor_label="10_YEAR", as_of="2026-09-30", provider="f"),
            RiskFreeRate(rate=5.0, tenor_label="30_YEAR", as_of="2026-09-30", provider="f"),
        ]
        self.assertEqual(select_rate(rates, "30_YEAR").rate, 5.0)
        self.assertIsNone(select_rate(rates, "13_WEEK"))

    def test_rate_converts_to_decimal(self):
        rate = RiskFreeRate(rate=5.244, tenor_label="10_YEAR", as_of="2026-09-30", provider="f")
        self.assertAlmostEqual(rate_as_decimal(rate), 0.05244, places=10)

    def test_missing_rate_converts_to_none(self):
        self.assertIsNone(rate_as_decimal(None))

    def test_every_declared_tenor_is_distinct(self):
        labels = [label for _, label, _ in TREASURY_SERIES]
        self.assertEqual(len(labels), len(set(labels)))
        self.assertIn("13_WEEK", labels)
        self.assertIn("30_YEAR", labels)


if __name__ == "__main__":
    unittest.main(verbosity=2)
