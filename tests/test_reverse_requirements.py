"""
Unit tests for the Reverse Requirements Report V1 formulas.

Known-answer tests use fixtures whose answers are worked out by hand, so a
change in behaviour has to be argued for rather than absorbed by a re-run.
Boundary tests cover the inputs that make a figure undefined: zero or negative
earnings, multiples that cannot invert, missing inputs, and currency or period
mismatches.
"""
from __future__ import annotations

import sys
import unittest

sys.path.insert(0, ".")

from reverse_requirements import (
    ANCHOR_FORWARD,
    ANCHOR_TTM,
    ANCHOR_USER,
    FORMULA_VERSION,
    MIN_GROWTH_YEARS,
    RETURN_BASIS_PRICE_ONLY,
    RETURN_BASIS_TOTAL,
    ReferenceMultiple,
    ReverseRequirementError,
    EpsAnchor,
    RiskFreeRate,
    build_matrix,
    build_reverse_requirements_report,
    build_scenario,
    capm_cost_of_equity,
    compute_fingerprint,
    dcf_feasibility,
    discount_present_value,
    fcf_yield,
    growth_window_years,
    implied_eps_at_multiple,
    implied_net_margin_at_multiples,
    required_ebitda_at_multiple,
    required_eps_cagr,
    required_exit_price,
    required_fcf_at_multiple,
    required_revenue_at_multiple,
    solve_implied_growth_rate,
    terminal_value,
)


def ttm_eps(value: float = 4.0) -> EpsAnchor:
    return EpsAnchor(
        value=value,
        basis=ANCHOR_TTM,
        months_covered=12.0,
        period_label="TTM to 2026-09-30",
        provider="fixture",
        currency="USD",
    )


def forward_eps(value: float = 4.0) -> EpsAnchor:
    return EpsAnchor(
        value=value,
        basis=ANCHOR_FORWARD,
        months_covered=12.0,
        period_label="NTM from 2026-09-30",
        provider="fixture",
        currency="USD",
    )


class TestRequiredExitPrice(unittest.TestCase):
    def test_known_answer_single_year(self):
        # 100 * 1.10**1 = 110
        self.assertAlmostEqual(required_exit_price(100.0, 0.10, 1.0), 110.0, places=10)

    def test_known_answer_three_years(self):
        # 100 * 1.08**3 = 125.9712
        self.assertAlmostEqual(required_exit_price(100.0, 0.08, 3.0), 125.9712, places=9)

    def test_zero_return_leaves_price_unchanged(self):
        self.assertAlmostEqual(required_exit_price(250.0, 0.0, 5.0), 250.0, places=10)

    def test_negative_return_compounds_down(self):
        # 200 * 0.9**2 = 162
        self.assertAlmostEqual(required_exit_price(200.0, -0.10, 2.0), 162.0, places=10)

    def test_non_positive_price_rejected(self):
        for price in (0.0, -1.0, None, "abc"):
            with self.assertRaises(ReverseRequirementError):
                required_exit_price(price, 0.10, 1.0)

    def test_return_at_total_loss_has_no_finite_compound(self):
        with self.assertRaises(ReverseRequirementError):
            required_exit_price(100.0, -1.0, 1.0)
        with self.assertRaises(ReverseRequirementError):
            required_exit_price(100.0, -1.5, 1.0)

    def test_non_positive_horizon_rejected(self):
        for horizon in (0.0, -1.0, None):
            with self.assertRaises(ReverseRequirementError):
                required_exit_price(100.0, 0.10, horizon)


class TestImpliedEpsAtMultiple(unittest.TestCase):
    def test_known_answer(self):
        # 200 / 20 = 10
        self.assertAlmostEqual(implied_eps_at_multiple(200.0, 20.0), 10.0, places=12)

    def test_zero_or_negative_multiple_rejected(self):
        # A zero or negative multiple inverts to an undefined EPS. Returning
        # infinity or a negative number would both be worse than refusing.
        for multiple in (0.0, -5.0, None):
            with self.assertRaises(ReverseRequirementError):
                implied_eps_at_multiple(200.0, multiple)

    def test_reference_multiple_object_enforces_positive(self):
        with self.assertRaises(ReverseRequirementError):
            ReferenceMultiple(value=0.0, source="user")
        with self.assertRaises(ReverseRequirementError):
            ReferenceMultiple(value=-3.0, source="user")

    def test_reference_multiple_records_its_provenance(self):
        multiple = ReferenceMultiple(
            value=28.0, source="user_supplied", sample_size=None
        )
        view = multiple.contract_view()
        self.assertEqual(view["source"], "user_supplied")
        self.assertIn("not a statement", view["conditionality"])

    def test_non_positive_price_rejected(self):
        with self.assertRaises(ReverseRequirementError):
            implied_eps_at_multiple(0.0, 20.0)


class TestGrowthWindow(unittest.TestCase):
    def test_trailing_anchor_keeps_the_whole_horizon(self):
        # A TTM EPS already covers the year that ended, so over a 3 year
        # horizon the growth window is the full 3 years.
        self.assertAlmostEqual(growth_window_years(ttm_eps(), 3.0), 3.0, places=12)

    def test_forward_anchor_is_subtracted_from_the_horizon(self):
        # A next-twelve-months EPS already reaches one year forward, so over a
        # 3 year horizon only 2 years of growth remain. Treating it as a
        # trailing figure would report a 3 year CAGR for a 2 year bridge.
        self.assertAlmostEqual(growth_window_years(forward_eps(), 3.0), 2.0, places=12)

    def test_forward_anchor_over_one_year_leaves_no_growth_window(self):
        self.assertAlmostEqual(growth_window_years(forward_eps(), 1.0), 0.0, places=12)

    def test_non_positive_horizon_rejected(self):
        with self.assertRaises(ReverseRequirementError):
            growth_window_years(ttm_eps(), 0.0)

    def test_anchor_must_declare_a_coverage_window(self):
        with self.assertRaises(ReverseRequirementError):
            EpsAnchor(value=4.0, basis=ANCHOR_TTM, months_covered=0.0)


class TestRequiredEpsCagr(unittest.TestCase):
    def test_known_answer_doubling_over_two_years(self):
        # (8 / 4) ** (1/2) - 1 = 0.41421356...
        result = required_eps_cagr(ttm_eps(4.0), 8.0, 2.0)
        self.assertAlmostEqual(result, 0.4142135623730951, places=12)

    def test_known_answer_flat_earnings(self):
        self.assertAlmostEqual(required_eps_cagr(ttm_eps(4.0), 4.0, 2.0), 0.0, places=12)

    def test_zero_start_eps_yields_no_rate(self):
        # A ratio against zero is undefined. Reporting infinity would be a
        # number, not an answer.
        self.assertIsNone(required_eps_cagr(ttm_eps(0.0), 8.0, 2.0))

    def test_negative_start_eps_yields_no_rate(self):
        self.assertIsNone(required_eps_cagr(ttm_eps(-2.0), 8.0, 2.0))

    def test_zero_or_negative_terminal_eps_yields_no_rate(self):
        for terminal in (0.0, -1.0):
            self.assertIsNone(required_eps_cagr(ttm_eps(4.0), terminal, 2.0))

    def test_window_shorter_than_the_minimum_yields_no_rate(self):
        self.assertIsNone(required_eps_cagr(ttm_eps(4.0), 8.0, MIN_GROWTH_YEARS - 0.01))

    def test_window_exactly_at_the_minimum_is_annualised(self):
        self.assertIsNotNone(required_eps_cagr(ttm_eps(4.0), 8.0, MIN_GROWTH_YEARS))


class TestCapmCostOfEquity(unittest.TestCase):
    def test_known_answer(self):
        # 0.04 + 1.2 * 0.05 = 0.10
        self.assertAlmostEqual(capm_cost_of_equity(0.04, 1.2, 0.05), 0.10, places=12)

    def test_known_answer_negative_beta(self):
        # 0.04 + (-0.5) * 0.06 = 0.01
        self.assertAlmostEqual(capm_cost_of_equity(0.04, -0.5, 0.06), 0.01, places=12)

    def test_zero_beta_collapses_to_the_risk_free_rate(self):
        self.assertAlmostEqual(capm_cost_of_equity(0.045, 0.0, 0.055), 0.045, places=12)

    def test_missing_component_rejected(self):
        for rf, beta, erp in ((None, 1.2, 0.05), (0.04, None, 0.05), (0.04, 1.2, None)):
            with self.assertRaises(ReverseRequirementError):
                capm_cost_of_equity(rf, beta, erp)


class TestCashFlowCrossChecks(unittest.TestCase):
    def test_fcf_yield_known_answer(self):
        # 50 / 1000 = 5%
        self.assertAlmostEqual(fcf_yield(50.0, 1000.0), 0.05, places=12)

    def test_fcf_yield_is_none_without_a_positive_market_cap(self):
        self.assertIsNone(fcf_yield(50.0, 0.0))
        self.assertIsNone(fcf_yield(50.0, None))

    def test_fcf_yield_preserves_a_negative_free_cash_flow(self):
        # A company burning cash has a negative yield. Zero is not the answer.
        self.assertAlmostEqual(fcf_yield(-50.0, 1000.0), -0.05, places=12)

    def test_required_amounts_at_multiples(self):
        # 1000 / 20 = 50
        self.assertAlmostEqual(required_fcf_at_multiple(1000.0, 20.0), 50.0, places=12)
        self.assertAlmostEqual(required_revenue_at_multiple(1000.0, 5.0), 200.0, places=12)
        self.assertAlmostEqual(required_ebitda_at_multiple(1200.0, 12.0), 100.0, places=12)

    def test_required_amounts_are_none_without_a_valid_multiple(self):
        self.assertIsNone(required_fcf_at_multiple(1000.0, 0.0))
        self.assertIsNone(required_fcf_at_multiple(1000.0, None))
        self.assertIsNone(required_revenue_at_multiple(0.0, 5.0))

    def test_implied_net_margin_known_answer(self):
        # EPS 2.00 on revenue 1000 over 100 shares -> revenue/share 10 -> 20%
        result = implied_net_margin_at_multiples(2.0, 1000.0, 100.0)
        self.assertAlmostEqual(result, 0.20, places=12)

    def test_implied_net_margin_none_on_degenerate_inputs(self):
        self.assertIsNone(implied_net_margin_at_multiples(2.0, 0.0, 100.0))
        self.assertIsNone(implied_net_margin_at_multiples(2.0, 1000.0, 0.0))
        self.assertIsNone(implied_net_margin_at_multiples(None, 1000.0, 100.0))


class TestBuildScenario(unittest.TestCase):
    multiple = ReferenceMultiple(value=20.0, source="user_supplied")

    def test_known_answer_chain(self):
        # price 100, 10% over 2y -> 121; at 20x that is EPS 6.05;
        # from a TTM 4.0 over a 2 year window -> (6.05/4)**0.5 - 1
        scenario = build_scenario(
            price=100.0,
            horizon_years=2.0,
            required_return=0.10,
            exit_multiple=self.multiple,
            start_anchor=ttm_eps(4.0),
            current_pe=25.0,
        )
        self.assertAlmostEqual(scenario.required_exit_price, 121.0, places=10)
        self.assertAlmostEqual(scenario.required_terminal_eps, 6.05, places=10)
        expected = (6.05 / 4.0) ** 0.5 - 1.0
        self.assertAlmostEqual(scenario.required_eps_cagr, expected, places=12)
        self.assertAlmostEqual(scenario.growth_years, 2.0, places=12)

    def test_required_return_is_labelled_a_price_return_without_a_dividend(self):
        scenario = build_scenario(
            price=100.0,
            horizon_years=1.0,
            required_return=0.10,
            exit_multiple=self.multiple,
            start_anchor=ttm_eps(),
        )
        self.assertEqual(scenario.required_return_basis, RETURN_BASIS_PRICE_ONLY)
        self.assertIn("REQUIRED_RETURN_EXCLUDES_DIVIDENDS", scenario.flags)
        self.assertEqual(
            scenario.contract_view()["required_exit_price_basis"],
            "PRICE_ONLY_EXCLUDES_DIVIDENDS",
        )

    def test_supplied_dividend_switches_the_basis(self):
        scenario = build_scenario(
            price=100.0,
            horizon_years=1.0,
            required_return=0.10,
            exit_multiple=self.multiple,
            start_anchor=ttm_eps(),
            dividend_per_share=1.0,
        )
        self.assertEqual(scenario.required_return_basis, RETURN_BASIS_TOTAL)
        self.assertNotIn("REQUIRED_RETURN_EXCLUDES_DIVIDENDS", scenario.flags)

    def test_forward_anchor_over_one_year_reports_no_cagr(self):
        # The forward EPS already speaks about the year that ends at the
        # horizon, so there is no growth window left to annualise. The raw
        # change is still reported.
        scenario = build_scenario(
            price=200.0,
            horizon_years=1.0,
            required_return=0.0,
            exit_multiple=self.multiple,
            start_anchor=forward_eps(9.0),
        )
        self.assertIsNone(scenario.required_eps_cagr)
        self.assertIn("GROWTH_WINDOW_TOO_SHORT_FOR_CAGR", scenario.flags)
        self.assertAlmostEqual(scenario.required_terminal_eps, 10.0, places=10)
        self.assertAlmostEqual(scenario.total_terminal_eps_growth, 10.0 / 9.0 - 1.0, places=12)

    def test_exit_multiple_compression_raises_the_required_eps(self):
        flat = build_scenario(
            price=100.0, horizon_years=1.0, required_return=0.0,
            exit_multiple=ReferenceMultiple(value=20.0, source="user"),
            start_anchor=ttm_eps(), current_pe=20.0,
        )
        compressed = build_scenario(
            price=100.0, horizon_years=1.0, required_return=0.0,
            exit_multiple=ReferenceMultiple(value=16.0, source="user"),
            start_anchor=ttm_eps(), current_pe=20.0,
        )
        self.assertGreater(compressed.required_terminal_eps, flat.required_terminal_eps)
        self.assertAlmostEqual(compressed.required_terminal_eps, 6.25, places=10)
        self.assertTrue(any("below the current P/E" in n for n in compressed.comparison_notes))

    def test_exit_multiple_expansion_lowers_the_required_eps(self):
        scenario = build_scenario(
            price=100.0, horizon_years=1.0, required_return=0.0,
            exit_multiple=ReferenceMultiple(value=25.0, source="user"),
            start_anchor=ttm_eps(), current_pe=20.0,
        )
        self.assertAlmostEqual(scenario.terminal_pe_change_vs_current_pe, 0.25, places=12)
        self.assertTrue(any("above the current P/E" in n for n in scenario.comparison_notes))

    def test_missing_consensus_is_reported_not_substituted(self):
        scenario = build_scenario(
            price=100.0, horizon_years=1.0, required_return=0.10,
            exit_multiple=self.multiple, start_anchor=ttm_eps(),
        )
        self.assertIn("NO_CONSENSUS_FOR_COMPARISON", scenario.flags)
        self.assertIsNone(scenario.gap_vs_consensus_terminal_eps)

    def test_non_positive_consensus_is_refused(self):
        scenario = build_scenario(
            price=100.0, horizon_years=1.0, required_return=0.10,
            exit_multiple=self.multiple, start_anchor=ttm_eps(),
            consensus_eps=-1.0, consensus_basis=ANCHOR_FORWARD,
        )
        self.assertIn("CONSENSUS_NOT_USABLE_FOR_COMPARISON", scenario.flags)
        self.assertIsNone(scenario.gap_vs_consensus_terminal_eps)

    def test_consensus_comparison_requires_matching_periods(self):
        # A next-twelve-months consensus taken today does not describe the year
        # ending three years out, so the two are not differenced.
        scenario = build_scenario(
            price=100.0, horizon_years=3.0, required_return=0.10,
            exit_multiple=self.multiple, start_anchor=ttm_eps(),
            consensus_eps=4.5, consensus_basis=ANCHOR_FORWARD,
            consensus_months_covered=12.0,
        )
        self.assertIn("CONSENSUS_PERIOD_NOT_COMPARABLE", scenario.flags)
        self.assertIsNone(scenario.gap_vs_consensus_terminal_eps)
        self.assertTrue(any("different periods" in n for n in scenario.comparison_notes))

    def test_consensus_comparison_accepted_on_matching_period(self):
        scenario = build_scenario(
            price=100.0, horizon_years=1.0, required_return=0.10,
            exit_multiple=self.multiple, start_anchor=ttm_eps(),
            consensus_eps=4.5, consensus_basis=ANCHOR_FORWARD,
            consensus_months_covered=12.0,
        )
        self.assertNotIn("CONSENSUS_PERIOD_NOT_COMPARABLE", scenario.flags)
        self.assertIsNotNone(scenario.gap_vs_consensus_terminal_eps)

    def test_consensus_without_a_declared_basis_is_not_compared(self):
        scenario = build_scenario(
            price=100.0, horizon_years=1.0, required_return=0.10,
            exit_multiple=self.multiple, start_anchor=ttm_eps(),
            consensus_eps=4.5, consensus_basis="",
        )
        self.assertIn("CONSENSUS_PERIOD_NOT_COMPARABLE", scenario.flags)

    def test_currency_mismatch_is_flagged(self):
        scenario = build_scenario(
            price=100.0, horizon_years=1.0, required_return=0.10,
            exit_multiple=self.multiple,
            start_anchor=ttm_eps(),
            currency="EUR",
        )
        self.assertIn("CURRENCY_MISMATCH", scenario.flags)
        self.assertTrue(any("not comparable" in n for n in scenario.comparison_notes))

    def test_scenario_view_carries_the_formula_version(self):
        scenario = build_scenario(
            price=100.0, horizon_years=1.0, required_return=0.10,
            exit_multiple=self.multiple, start_anchor=ttm_eps(),
        )
        self.assertEqual(scenario.contract_view()["formula_version"], FORMULA_VERSION)


class TestBuildMatrix(unittest.TestCase):
    def test_matrix_is_the_full_cross_product(self):
        scenarios = build_matrix(
            price=100.0,
            horizons_years=[1.0, 2.0],
            required_returns=[0.08, 0.10],
            exit_multiples=[
                ReferenceMultiple(value=18.0, source="user"),
                ReferenceMultiple(value=22.0, source="user"),
            ],
            start_anchor=ttm_eps(4.0),
        )
        self.assertEqual(len(scenarios), 8)

    def test_distinct_inputs_produce_distinct_required_eps(self):
        scenarios = build_matrix(
            price=100.0,
            horizons_years=[1.0, 2.0],
            required_returns=[0.08, 0.10],
            exit_multiples=[ReferenceMultiple(value=20.0, source="user")],
            start_anchor=ttm_eps(4.0),
        )
        terminal = sorted({round(s.required_terminal_eps, 10) for s in scenarios})
        self.assertEqual(len(terminal), 4)


class TestDiscountedCashFlow(unittest.TestCase):
    def test_present_value_known_answer(self):
        # 100/1.1 + 100/1.21 = 90.909090 + 82.644628 = 173.553719
        result = discount_present_value([100.0, 100.0], 0.10)
        self.assertAlmostEqual(result, 173.5537190082645, places=9)

    def test_present_value_rejects_a_rate_at_or_below_minus_one(self):
        for rate in (-1.0, -1.5):
            with self.assertRaises(ReverseRequirementError):
                discount_present_value([100.0], rate)

    def test_present_value_rejects_a_non_finite_flow(self):
        with self.assertRaises(ReverseRequirementError):
            discount_present_value([None], 0.10)

    def test_terminal_value_known_answer(self):
        # 100 * 1.02 / (0.08 - 0.02) = 1700
        self.assertAlmostEqual(terminal_value(100.0, 0.08, 0.02), 1700.0, places=9)

    def test_terminal_value_requires_growth_below_the_discount_rate(self):
        for growth in (0.08, 0.10):
            with self.assertRaises(ReverseRequirementError):
                terminal_value(100.0, 0.08, growth)

    def test_implied_growth_rate_reproduces_the_observed_value(self):
        # Solve for the growth rate that explains a 1000 value at a 10%
        # discount rate over 5 years with 2% terminal growth, starting from
        # 100 of cash flow. Whatever the solver returns must price back to
        # 1000 when run through the same model.
        present_value = 1000.0
        solved = solve_implied_growth_rate(
            present_value=present_value,
            base_cash_flow=100.0,
            discount_rate=0.10,
            explicit_years=5,
            terminal_growth=0.02,
        )
        self.assertIsNotNone(solved)
        flows = [100.0 * ((1.0 + solved) ** (i + 1)) for i in range(5)]
        modelled = discount_present_value(flows, 0.10) + (
            flows[-1] * 1.02 / (0.10 - 0.02)
        ) / (1.10 ** 5)
        self.assertAlmostEqual(modelled, present_value, places=4)

    def test_implied_growth_rate_is_none_when_growth_exceeds_discount_rate(self):
        self.assertIsNone(
            solve_implied_growth_rate(1000.0, 100.0, 0.05, 5, 0.06)
        )

    def test_implied_growth_rate_is_none_for_degenerate_inputs(self):
        self.assertIsNone(solve_implied_growth_rate(0.0, 100.0, 0.10, 5, 0.02))
        self.assertIsNone(solve_implied_growth_rate(1000.0, 0.0, 0.10, 5, 0.02))
        self.assertIsNone(solve_implied_growth_rate(1000.0, 100.0, 0.10, 0, 0.02))

    def test_implied_growth_rate_is_none_when_the_value_is_out_of_reach(self):
        # No constant growth rate inside the default bracket can produce a
        # trillion from a 100 base at these rates.
        self.assertIsNone(
            solve_implied_growth_rate(1_000_000.0, 100.0, 0.10, 5, 0.02)
        )


class TestDcfFeasibility(unittest.TestCase):
    def _complete(self, **overrides):
        base = dict(
            has_free_cash_flow=True,
            has_depreciation_amortisation=True,
            has_capex=True,
            has_working_capital_change=True,
            has_cost_of_debt=True,
            has_market_value_of_debt=True,
            has_tax_rate=True,
            cash_flow_basis="FCFF",
        )
        base.update(overrides)
        return dcf_feasibility(**base)

    def test_complete_inputs_are_supported(self):
        result = self._complete()
        self.assertTrue(result["supported"])
        self.assertEqual(result["missing_inputs"], [])

    def test_each_missing_input_is_named_individually(self):
        # A consumer has to be able to see which specific input is absent, so
        # each one is reported on its own rather than as a single "incomplete".
        for flag, expected_name in (
            ("has_free_cash_flow", "free_cash_flow"),
            ("has_depreciation_amortisation", "depreciation_amortisation"),
            ("has_capex", "capex"),
            ("has_working_capital_change", "working_capital_change"),
            ("has_cost_of_debt", "cost_of_debt"),
            ("has_market_value_of_debt", "market_value_of_debt"),
            ("has_tax_rate", "tax_rate"),
        ):
            result = self._complete(**{flag: False})
            self.assertFalse(result["supported"], flag)
            self.assertEqual(result["missing_inputs"], [expected_name], flag)

    def test_undeclared_cash_flow_basis_blocks(self):
        result = self._complete(cash_flow_basis="")
        self.assertFalse(result["supported"])
        self.assertEqual(result["cash_flow_basis_status"], "UNDECLARED")
        self.assertIn("cash_flow_basis", result["blocking_reasons"])

    def test_unsupported_cash_flow_basis_blocks(self):
        result = self._complete(cash_flow_basis="EBITDA")
        self.assertFalse(result["supported"])
        self.assertEqual(result["cash_flow_basis_status"], "UNSUPPORTED:EBITDA")

    def test_fcfe_is_a_recognised_basis(self):
        self.assertTrue(self._complete(cash_flow_basis="FCFE")["supported"])


class TestReportAssembly(unittest.TestCase):
    def _report(self, **overrides):
        base = dict(
            price=100.0,
            ticker="TEST",
            currency="USD",
            as_of="2026-09-30",
            price_source="fixture",
            horizons_years=[1.0, 2.0],
            required_returns=[0.10],
            exit_multiples=[ReferenceMultiple(value=20.0, source="user_supplied")],
            start_anchor=ttm_eps(4.0),
            current_pe=25.0,
            market_cap=1000.0,
            free_cash_flow=50.0,
            pfcf_multiple=20.0,
            risk_free_rates=[
                RiskFreeRate(
                    rate=4.25,
                    tenor_label="10_YEAR",
                    as_of="2026-09-30",
                    provider="fixture",
                )
            ],
        )
        base.update(overrides)
        return build_reverse_requirements_report(**base)

    def test_matrix_size_and_fingerprint_present(self):
        report = self._report()
        self.assertEqual(report["matrix_size"], 2)
        self.assertEqual(len(report["fingerprint"]), 64)

    def test_identical_inputs_reproduce_an_identical_fingerprint(self):
        self.assertEqual(self._report()["fingerprint"], self._report()["fingerprint"])

    def test_changed_input_changes_the_fingerprint(self):
        base = self._report()["fingerprint"]
        moved = self._report(price=101.0)["fingerprint"]
        self.assertNotEqual(base, moved)

    def test_changed_exit_multiple_changes_the_fingerprint(self):
        base = self._report()["fingerprint"]
        other = self._report(
            exit_multiples=[ReferenceMultiple(value=22.0, source="user_supplied")]
        )["fingerprint"]
        self.assertNotEqual(base, other)

    def test_changed_formula_version_changes_the_fingerprint(self):
        # The fingerprint must discriminate on the formula version, not only on
        # the inputs: identical inputs under two formula versions are two
        # different calculations and must not share a fingerprint.
        import reverse_requirements as module

        original = module.FORMULA_VERSION
        try:
            before = compute_fingerprint({"a": 1})
            module.FORMULA_VERSION = "reverse-requirements/9.9"
            after = compute_fingerprint({"a": 1})
        finally:
            module.FORMULA_VERSION = original
        self.assertNotEqual(before, after)
        self.assertEqual(compute_fingerprint({"a": 1}), before)

    def test_rate_families_are_kept_separate(self):
        report = self._report()
        families = report["rate_families"]
        self.assertEqual(families["risk_free_rate"]["kind"], "OBSERVATION")
        self.assertEqual(len(families["risk_free_rate"]["observations"]), 1)
        self.assertEqual(families["cost_of_equity"]["status"], "NOT_COMPUTED")
        self.assertIsNone(families["cost_of_equity"]["value"])
        self.assertEqual(families["investor_required_return"]["status"], "NOT_SUPPLIED")

    def test_cost_of_equity_computed_when_inputs_are_complete(self):
        report = self._report(
            cost_of_equity_inputs={
                "risk_free_rate_decimal": 0.0425,
                "risk_free_rate_source": "fixture",
                "risk_free_rate_as_of": "2026-09-30",
                "beta": 1.2,
                "beta_source": "fixture",
                "beta_estimation_window": "5y weekly",
                "equity_risk_premium_decimal": 0.05,
                "equity_risk_premium_source": "fixture",
                "equity_risk_premium_estimation_window": "declared assumption",
            }
        )
        block = report["rate_families"]["cost_of_equity"]
        self.assertEqual(block["status"], "COMPUTED")
        self.assertAlmostEqual(block["value"], 0.1025, places=12)
        self.assertTrue(block["is_estimate"])
        self.assertEqual(block["inputs"]["beta_estimation_window"], "5y weekly")

    def test_cost_of_equity_names_missing_inputs(self):
        report = self._report(cost_of_equity_inputs={"risk_free_rate_decimal": 0.04})
        block = report["rate_families"]["cost_of_equity"]
        self.assertEqual(block["status"], "INCOMPLETE_INPUTS")
        self.assertEqual(sorted(block["missing_inputs"]), ["beta", "equity_risk_premium_decimal"])

    def test_investor_target_return_is_recorded_as_a_scenario_input(self):
        report = self._report(investor_required_returns={"base": 0.10, "stretch": 0.15})
        block = report["rate_families"]["investor_required_return"]
        self.assertEqual(block["status"], "SUPPLIED")
        self.assertFalse(block["is_estimate"])
        self.assertEqual(block["values"]["stretch"], 0.15)

    def test_cash_flow_cross_checks_report_both_directions(self):
        block = self._report()["cash_flow_cross_checks"]
        self.assertAlmostEqual(block["observed"]["p_fcf"], 20.0, places=12)
        self.assertAlmostEqual(block["observed"]["fcf_yield"], 0.05, places=12)
        self.assertAlmostEqual(
            block["required_at_reference_multiple"]["fcf"]["required_fcf"], 50.0, places=12
        )
        self.assertAlmostEqual(
            block["required_at_reference_multiple"]["fcf"]["gap_vs_observed_fcf"], 0.0, places=12
        )

    def test_missing_reference_multiples_leave_the_reverse_side_empty(self):
        block = self._report(pfcf_multiple=None)["cash_flow_cross_checks"]
        self.assertIsNone(block["required_at_reference_multiple"]["fcf"]["required_fcf"])

    def test_dcf_block_not_attempted_without_inputs(self):
        block = self._report()["dcf"]
        self.assertEqual(block["status"], "NOT_ATTEMPTED")
        self.assertFalse(block["feasibility"]["supported"])

    def test_dcf_block_computes_when_everything_is_supplied(self):
        report = self._report(
            dcf_inputs={
                "cash_flow_basis": "FCFF",
                "free_cash_flow": 50.0,
                "depreciation_amortisation": 10.0,
                "capex": 12.0,
                "working_capital_change": 1.0,
                "cost_of_debt": 0.04,
                "market_value_of_debt": 500.0,
                "tax_rate": 0.21,
                "discount_rate_decimal": 0.09,
                "discount_rate_source": "fixture",
                "explicit_years": 5,
                "terminal_growth_decimal": 0.02,
                "terminal_growth_source": "fixture",
                "present_value": 1000.0,
                "present_value_source": "fixture",
                "base_cash_flow": 50.0,
            }
        )
        block = report["dcf"]
        self.assertEqual(block["status"], "COMPUTED")
        self.assertIsNotNone(block["implied_explicit_growth_rate"])
        self.assertTrue(block["feasibility"]["supported"])

    def test_dcf_block_names_missing_inputs_instead_of_guessing(self):
        report = self._report(
            dcf_inputs={
                "cash_flow_basis": "FCFF",
                "free_cash_flow": 50.0,
                "discount_rate_decimal": 0.09,
                "explicit_years": 5,
                "terminal_growth_decimal": 0.02,
                "present_value": 1000.0,
                "base_cash_flow": 50.0,
            }
        )
        block = report["dcf"]
        self.assertEqual(block["status"], "NOT_COMPUTED")
        self.assertIsNone(block["implied_explicit_growth_rate"])
        self.assertIn("capex", block["feasibility"]["missing_inputs"])
        self.assertIn("depreciation_amortisation", block["feasibility"]["missing_inputs"])

    def test_dcf_block_rejects_terminal_growth_above_the_discount_rate(self):
        report = self._report(
            dcf_inputs={
                "cash_flow_basis": "FCFF",
                "free_cash_flow": 50.0,
                "depreciation_amortisation": 10.0,
                "capex": 12.0,
                "working_capital_change": 1.0,
                "cost_of_debt": 0.04,
                "market_value_of_debt": 500.0,
                "tax_rate": 0.21,
                "discount_rate_decimal": 0.05,
                "explicit_years": 5,
                "terminal_growth_decimal": 0.06,
                "present_value": 1000.0,
                "base_cash_flow": 50.0,
            }
        )
        self.assertEqual(report["dcf"]["status"], "INVALID_DISCOUNT_PARAMETERS")

    def test_dcf_block_rejects_a_fractional_explicit_period(self):
        report = self._report(
            dcf_inputs={
                "cash_flow_basis": "FCFF",
                "free_cash_flow": 50.0,
                "depreciation_amortisation": 10.0,
                "capex": 12.0,
                "working_capital_change": 1.0,
                "cost_of_debt": 0.04,
                "market_value_of_debt": 500.0,
                "tax_rate": 0.21,
                "discount_rate_decimal": 0.09,
                "explicit_years": 4.5,
                "terminal_growth_decimal": 0.02,
                "present_value": 1000.0,
                "base_cash_flow": 50.0,
            }
        )
        self.assertEqual(report["dcf"]["status"], "INVALID_EXPLICIT_PERIOD")

    def test_unavailable_items_are_carried_through(self):
        report = self._report(
            unavailable=[{"item": "x", "reason": "not observed", "reason_kind": "MISSING"}]
        )
        self.assertEqual(len(report["unavailable"]), 1)


class TestRiskFreeRate(unittest.TestCase):
    def test_percent_rate_is_converted_to_a_decimal(self):
        rate = RiskFreeRate(
            rate=4.25, tenor_label="10_YEAR", as_of="2026-09-30", provider="fixture"
        )
        view = rate.contract_view()
        self.assertAlmostEqual(view["rate_decimal"], 0.0425, places=12)
        self.assertEqual(view["as_of"], "2026-09-30")
        self.assertEqual(view["unit"], "percent_per_annum")


if __name__ == "__main__":
    unittest.main(verbosity=2)
