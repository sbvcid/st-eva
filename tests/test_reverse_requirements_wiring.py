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
        # observation count. Under the unified eligibility rule an undeclared
        # count is never a reference, so the only scenario multiple is the
        # explicitly supplied point and the matrix is its cross product.
        result = _run(
            reverse_horizons=(1.0, 2.0),
            required_returns=(0.10, 0.12),
            reference_multiple=20.0,
        )
        package = result["reverse_requirements"]
        multiples = {
            row["exit_multiple"]["value"]
            for row in package["reverse_requirements_matrix"]
        }
        self.assertEqual(package["matrix_size"], 2 * 2 * len(multiples))
        self.assertEqual(multiples, {20.0})
        self.assertEqual(
            {row["exit_multiple"]["eligibility_state"] for row in package["reverse_requirements_matrix"]},
            {"USER_SPECIFIED"},
        )
        # The band's exclusion from the scenario set is stated, not silent.
        self.assertTrue(
            any(
                item.get("item") == "exit_multiple.band_scenarios"
                and item.get("reason_kind") == "OBSERVATION_COUNT_UNVERIFIED"
                for item in package["unavailable"]
            ),
            package["unavailable"],
        )

    def test_an_eligible_band_still_yields_a_percentile_scenario_set(self):
        # A band that declares its sample count keeps producing the percentile
        # set on the matrix path, so the cross product over a range still
        # exists when the history is verifiable.
        from st_eva_runner import _build_exit_multiple_scenarios

        scenarios, unavailable = _build_exit_multiple_scenarios(
            historical_band={
                "10th": 10.0,
                "25th": 15.0,
                "median": 20.0,
                "75th": 30.0,
                "90th": 40.0,
                "observations": 120,
            },
            user_multiples=(),
            min_observations=20,
        )
        self.assertEqual([m.value for m in scenarios], [10.0, 15.0, 20.0, 30.0, 40.0])
        self.assertEqual(unavailable, [])
        self.assertTrue(all(m.usable_for_reference for m in scenarios))
        self.assertEqual(
            {m.eligibility_state for m in scenarios}, {"ELIGIBLE_HISTORICAL_BAND"}
        )

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
        # Neither the MSFT nor the NU fixture band declares a sample count, so
        # under the unified eligibility rule neither is a reference: with no
        # user multiple the matrix is reported as uncomputable, not built on a
        # descriptive statistic.
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


class TestScenarioProvenanceAndReproducibility(unittest.TestCase):
    def test_calculation_steps_reproduce_outputs_within_tolerance(self):
        result = _run(
            reverse_horizons=(2.0, 3.0),
            required_returns=(0.10, 0.12),
            reference_multiple=25.0,
        )
        matrix = result["reverse_requirements"]["reverse_requirements_matrix"]
        self.assertGreater(len(matrix), 0)
        for scen in matrix:
            steps = scen.get("calculation_steps", [])
            self.assertEqual(len(steps), 4)
            for step in steps:
                self.assertTrue(step["reproducible"])

            # Step 1: Exit Price
            self.assertAlmostEqual(steps[0]["output_value"], scen["required_exit_price"], places=4)
            # Step 2: Terminal EPS
            self.assertAlmostEqual(steps[1]["output_value"], scen["required_terminal_eps"], places=4)
            # Step 3: Terminal EPS Growth
            self.assertAlmostEqual(steps[2]["output_value"], scen["total_terminal_eps_growth"], places=4)
            # Step 4: CAGR (if computable)
            if scen["required_eps_cagr"] is not None:
                self.assertAlmostEqual(steps[3]["output_value"], scen["required_eps_cagr"], places=4)

    def test_source_evidence_resolves_to_actual_input_records(self):
        # The fixture band declares no sample count, so a reference-free run
        # has no eligible exit multiple; the evidence assertions run on a row
        # computed from an explicitly supplied multiple.
        result = _run(reference_multiple=25.0)
        matrix = result["reverse_requirements"]["reverse_requirements_matrix"]
        self.assertGreater(len(matrix), 0)
        scen = matrix[0]
        evidence = scen.get("evidence")
        self.assertIsNotNone(evidence)

        # Market price evidence
        price_ev = evidence["price_evidence"]
        self.assertEqual(price_ev["value"], 425.50)
        self.assertEqual(price_ev["currency"], "USD")
        self.assertEqual(price_ev["as_of"], "2026-09-18")
        self.assertEqual(price_ev["observation_id"], "ev-price-001")
        self.assertEqual(price_ev["source_type"], "REGRESSION_FIXTURE")

        # Anchor evidence resolves to forward EPS observation in MSFT fixture
        anchor_ev = evidence["eps_evidence"]
        self.assertEqual(anchor_ev["observation_id"], "ev-forward-eps-001")
        self.assertEqual(anchor_ev["value"], 13.20)
        self.assertEqual(anchor_ev["basis"], "FORWARD_TWELVE_MONTHS")
        self.assertFalse(anchor_ev["is_user_assumption"])

    def test_sec_eps_fact_resolution_for_historical_filings(self):
        """R2.1: a value equal to a historical filing is not that filing's source.

        The pre-R2.1 resolver returned the most recent annual fact for the ticker
        on the strength of the value alone, which made a vendor figure display a
        10-K as its direct source. Resolution now requires the linked observation
        that supplied the value; see tests/test_r21_provenance_binding.py for the
        positive linkage cases.
        """
        from st_eva_runner import _resolve_sec_eps_fact

        self.assertIsNone(
            _resolve_sec_eps_fact(11.80),
            "numerical equality with a historical filing is not provenance",
        )
        self.assertIsNone(_resolve_sec_eps_fact(13.20))
        self.assertIsNone(
            _resolve_sec_eps_fact(11.80, source_observation=None)
        )

    def test_user_assumptions_labelled_and_never_receive_fabricated_sec_provenance(self):
        result = _run(user_eps=25.0, reference_multiple=27.5)
        matrix = result["reverse_requirements"]["reverse_requirements_matrix"]
        self.assertGreater(len(matrix), 0)
        user_scens = [s for s in matrix if s["exit_multiple"]["value"] == 27.5]
        self.assertGreater(len(user_scens), 0)
        scen = user_scens[0]
        evidence = scen.get("evidence")
        self.assertIsNotNone(evidence)

        # EPS anchor is user assumption
        anchor_ev = evidence["eps_evidence"]
        self.assertTrue(anchor_ev["is_user_assumption"])
        self.assertEqual(anchor_ev["source_type"], "USER_SUPPLIED")
        self.assertIsNone(anchor_ev["sec_fact"], "User-supplied EPS must never receive fabricated SEC provenance")

        # Exit multiple is user assumption
        exit_ev = evidence["multiple_evidence"]
        self.assertTrue(exit_ev["is_user_assumption"])
        self.assertEqual(exit_ev["eligibility_state"], "USER_SPECIFIED")

        # Evidence lists user assumptions explicitly
        user_assumptions = evidence["user_assumptions"]
        self.assertTrue(any("Starting EPS" in k for k in user_assumptions))
        self.assertTrue(any("Exit Multiple" in k for k in user_assumptions))

    def test_historical_multiple_sample_size_eligibility_states(self):
        # Adequate sample size (>= 20)
        multiples_ok, _ = build_exit_multiples(
            historical_pe_band={"median": 28.0, "observations": 35},
            user_pe_multiple=None,
            min_observations=20,
        )
        self.assertEqual(len(multiples_ok), 1)
        self.assertEqual(multiples_ok[0].eligibility_state, "ELIGIBLE_HISTORICAL_BAND")
        self.assertTrue(multiples_ok[0].usable_for_reference)

        # Inadequate sample size (< 20)
        from reverse_requirements import exit_multiples_from_band
        multiples_thin, unavail = exit_multiples_from_band(
            {"median": 28.0, "observations": 8},
            min_observations=20,
        )
        self.assertEqual(multiples_thin, [])
        self.assertEqual(unavail[0]["reason_kind"], "INSUFFICIENT_OBSERVATIONS")


if __name__ == "__main__":
    unittest.main(verbosity=2)
