"""
Regression tests for the consensus EPS period provenance correction.

A vendor consensus estimate carries a fiscal-period end date. The acquisition
path used to discard it and the runner used to infer a twelve-month coverage
from the vendor's ``+1y`` label instead, which let a next-fiscal-year estimate
be differenced against a terminal EPS for a different year.

These tests pin the behaviour that replaced it:

* the declared date survives extraction, observation, runner and export;
* the comparison is decided on that date, at a stated tolerance;
* a missing declared date is never replaced by one inferred from the label;
* every published formula value is unchanged for identical inputs.
"""
from __future__ import annotations

import sys
import unittest

sys.path.insert(0, ".")

from data_contract import (
    METRIC_CONSENSUS_FORWARD_EPS,
    build_observation,
)
from fundamental_provider import (
    YahooFundamentalProvider,
    declared_date,
)
from reverse_requirements import (
    ANCHOR_FORWARD,
    CONSENSUS_COMPARABLE_HORIZON_YEARS,
    CONSENSUS_PERIOD_TOLERANCE_DAYS,
    FORMULA_VERSION,
    ReferenceMultiple,
    build_consensus_reference,
    build_matrix,
    build_reverse_requirements_report,
    build_scenario,
    terminal_period_end,
)
from st_eva_runner import MarketData, _apply_observations_to_view, _observation_raw


VALUATION_DATE = "2026-10-09"
TARGET_END = "2027-10-09"


def _trend(period: str = "+1y", avg=None, end_date=...):
    row = {"period": period, "earningsEstimate": {"avg": avg}}
    if end_date is not ...:
        row["endDate"] = end_date
    return {"trend": [row]}


def _anchor():
    from reverse_requirements import ANCHOR_TTM, EpsAnchor

    return EpsAnchor(
        value=17.95,
        basis=ANCHOR_TTM,
        months_covered=12.0,
        period_label="trailing twelve months (assumed; source stated no period)",
        provider="YahooFinanceFundamentals",
        currency="USD",
        period_undeclared_by_source=True,
    )


def _scenario(**overrides):
    payload = dict(
        price=535.07,
        horizon_years=1.0,
        required_return=0.08,
        exit_multiple=ReferenceMultiple(value=33.195873, source="production_historical_pe_percentile"),
        start_anchor=_anchor(),
        current_pe=29.81,
        consensus_eps=23.67732,
        consensus_basis=ANCHOR_FORWARD,
        consensus_months_covered=12.0,
        consensus_period_end="2028-06-30",
        as_of=VALUATION_DATE,
    )
    payload.update(overrides)
    return build_scenario(**payload)


def _report(**overrides):
    payload = dict(
        price=535.07,
        ticker="MSFT",
        currency="USD",
        as_of=VALUATION_DATE,
        price_source="Yahoo chart regularMarketPrice",
        horizons_years=[1.0],
        required_returns=[0.08],
        exit_multiples=[
            ReferenceMultiple(
                value=33.195873, source="production_historical_pe_percentile"
            )
        ],
        start_anchor=_anchor(),
        current_pe=29.81,
        consensus_eps=23.67732,
        consensus_basis=ANCHOR_FORWARD,
        consensus_months_covered=12.0,
        consensus_period_label="+1y",
        consensus_period_end="2028-06-30",
        consensus_target_period_end=TARGET_END,
        consensus_provider="YahooFinanceFundamentals",
    )
    payload.update(overrides)
    return build_reverse_requirements_report(**payload)


class TestDeclaredPeriodEndIsPreserved(unittest.TestCase):
    def test_extraction_returns_the_declared_end_of_the_winning_row(self):
        self.assertEqual(
            YahooFundamentalProvider._extract_consensus_forward_eps(
                _trend(avg=23.67732, end_date="2028-06-30")
            ),
            (23.67732, "+1y", "2028-06-30"),
        )

    def test_extraction_normalises_a_datetime_shaped_declaration(self):
        self.assertEqual(
            declared_date("2028-06-30T00:00:00Z"),
            "2028-06-30",
        )

    def test_extraction_normalises_a_raw_wrapped_declaration(self):
        self.assertEqual(
            declared_date({"raw": "2028-06-30"}),
            "2028-06-30",
        )

    def test_normalisation_refuses_anything_not_a_calendar_date(self):
        for value in ("", "   ", "not-a-date", "2028", None, 20280630, ["2028-06-30"]):
            with self.subTest(value=value):
                self.assertIsNone(declared_date(value))

    def test_the_row_that_wins_the_existing_priority_supplies_the_date(self):
        trend = {
            "trend": [
                {"period": "0q", "earningsEstimate": {"avg": 1.0}},
                {
                    "period": "+1y",
                    "earningsEstimate": {"avg": 23.67732},
                    "endDate": "2028-06-30",
                },
                {
                    "period": "0y",
                    "earningsEstimate": {"avg": 20.0},
                    "endDate": "2027-06-30",
                },
            ]
        }
        self.assertEqual(
            YahooFundamentalProvider._extract_consensus_forward_eps(trend),
            (23.67732, "+1y", "2028-06-30"),
        )

    def test_an_absent_declaration_stays_absent(self):
        self.assertEqual(
            YahooFundamentalProvider._extract_consensus_forward_eps(
                _trend(avg=4.0, end_date=None)
            ),
            (4.0, "+1y", None),
        )

    def test_a_blank_declaration_stays_absent(self):
        self.assertEqual(
            YahooFundamentalProvider._extract_consensus_forward_eps(
                _trend(avg=4.0, end_date="   ")
            ),
            (4.0, "+1y", None),
        )

    def test_the_consensus_observation_carries_the_declared_end(self):
        observation = YahooFundamentalProvider()._consensus_observation(
            clean="MSFT",
            value=23.67732,
            period="+1y",
            trend={},
            retrieved_at="2026-10-09T00:00:00Z",
            source_url=None,
            instrument_currency="USD",
            period_end="2028-06-30",
        )
        self.assertEqual(observation.metric, METRIC_CONSENSUS_FORWARD_EPS)
        self.assertEqual(observation.period_end, "2028-06-30")
        self.assertEqual(observation.raw["period"], "+1y")
        self.assertEqual(observation.raw["period_end"], "2028-06-30")
        # The source states no start date, so none is fabricated.
        self.assertIsNone(observation.period_start)
        self.assertIsNone(observation.as_of)

    def test_the_consensus_observation_leaves_an_undeclared_end_undeclared(self):
        observation = YahooFundamentalProvider()._consensus_observation(
            clean="MSFT",
            value=23.67732,
            period="+1y",
            trend={},
            retrieved_at="2026-10-09T00:00:00Z",
            source_url=None,
            instrument_currency="USD",
            period_end=None,
        )
        self.assertIsNone(observation.period_end)
        self.assertNotIn("period_start", observation.raw)

    def test_an_unavailable_consensus_keeps_no_period(self):
        observation = YahooFundamentalProvider()._consensus_observation(
            clean="MSFT",
            value=None,
            period=None,
            trend={},
            retrieved_at="2026-10-09T00:00:00Z",
            source_url=None,
            instrument_currency="USD",
            period_end=None,
        )
        self.assertIsNone(observation.value)
        self.assertIsNone(observation.raw)


class TestViewProjectionCarriesTheDeclaredEnd(unittest.TestCase):
    def _view(self, raw):
        data = MarketData(
            ticker="MSFT",
            company_name="Microsoft",
            exchange="NMS",
            currency="USD",
            price=535.07,
            price_date=VALUATION_DATE,
            price_source="Yahoo chart regularMarketPrice",
            price_source_url=None,
            price_history=[],
            volume_history=[],
        )
        as_of = VALUATION_DATE
        observations = [
            build_observation(
                metric="price",
                value=535.07,
                unit="USD",
                provider="YahooFinance",
                source_type="API_LIVE",
                definition="market price",
                methodology="Yahoo chart regularMarketPrice",
                retrieved_at="2026-10-09T00:00:00Z",
                period_end=VALUATION_DATE,
                as_of=VALUATION_DATE,
                observation_id="ev-price-001",
            ),
            build_observation(
                metric=METRIC_CONSENSUS_FORWARD_EPS,
                value=23.67732,
                unit="USD/shares",
                provider="YahooFinanceFundamentals",
                source_type="API_LIVE",
                definition="Consensus forward EPS. Never synthesized.",
                methodology=(
                    "Yahoo quoteSummary earningsTrend trend[period]"
                    ".earningsEstimate.avg"
                ),
                retrieved_at="2026-10-09T00:00:00Z",
                currency="USD",
                period_end="2028-06-30",
                available_at_basis="UNDECLARED",
                raw=raw,
                observation_id="consensus_forward_eps-001",
            ),
        ]
        projected = _apply_observations_to_view(data, observations, as_of=as_of)
        return data, projected, as_of

    def test_the_declared_end_reaches_the_view(self):
        data, projected, _ = self._view(
            {"period": "+1y", "period_end": "2028-06-30"}
        )
        self.assertEqual(data.consensus_forward_eps_period, "+1y")
        self.assertEqual(data.consensus_forward_eps_period_end, "2028-06-30")
        self.assertEqual(projected.consensus_forward_eps_period, "+1y")
        self.assertEqual(
            projected.consensus_forward_eps_period_end, "2028-06-30"
        )

    def test_the_observation_s_own_end_covers_an_older_archive_row(self):
        # A row archived before the raw payload carried the date still has the
        # observation's period_end, and the rebuild reads it rather than
        # dropping the declared year.
        _, projected, _ = self._view({"period": "+1y"})
        self.assertEqual(projected.consensus_forward_eps_period_end, "2028-06-30")

    def test_a_view_built_without_a_declared_end_keeps_it_absent(self):
        data = MarketData(
            ticker="MSFT",
            company_name="Microsoft",
            exchange="NMS",
            currency="USD",
            price=535.07,
            price_date=VALUATION_DATE,
            price_source="Yahoo chart regularMarketPrice",
            price_source_url=None,
            price_history=[],
            volume_history=[],
            consensus_forward_eps_period="+1y",
        )
        self.assertIsNone(data.consensus_forward_eps_period_end)

    def test_the_legacy_raw_fallback_preserves_both_facts(self):
        data = MarketData(
            ticker="MSFT",
            company_name="Microsoft",
            exchange="NMS",
            currency="USD",
            price=535.07,
            price_date=VALUATION_DATE,
            price_source="Yahoo chart regularMarketPrice",
            price_source_url=None,
            price_history=[],
            volume_history=[],
            consensus_forward_eps_period="+1y",
            consensus_forward_eps_period_end="2028-06-30",
        )
        raw = _observation_raw(
            data, METRIC_CONSENSUS_FORWARD_EPS, None, False
        )
        self.assertEqual(raw, {"period": "+1y", "period_end": "2028-06-30"})

    def test_the_legacy_raw_fallback_omits_an_absent_end(self):
        data = MarketData(
            ticker="MSFT",
            company_name="Microsoft",
            exchange="NMS",
            currency="USD",
            price=535.07,
            price_date=VALUATION_DATE,
            price_source="Yahoo chart regularMarketPrice",
            price_source_url=None,
            price_history=[],
            volume_history=[],
            consensus_forward_eps_period="+1y",
        )
        raw = _observation_raw(
            data, METRIC_CONSENSUS_FORWARD_EPS, None, False
        )
        self.assertEqual(raw, {"period": "+1y"})

    def test_the_legacy_raw_fallback_stays_the_archive_round_trip_source(self):
        # The archive stores and restores `raw` verbatim, so the payload the
        # legacy fallback writes is what a replayed view reads back and rebuilds
        # its declared date from.
        data = MarketData(
            ticker="MSFT",
            company_name="Microsoft",
            exchange="NMS",
            currency="USD",
            price=535.07,
            price_date=VALUATION_DATE,
            price_source="Yahoo chart regularMarketPrice",
            price_source_url=None,
            price_history=[],
            volume_history=[],
            consensus_forward_eps_period="+1y",
            consensus_forward_eps_period_end="2028-06-30",
        )
        archived_raw = _observation_raw(
            data, METRIC_CONSENSUS_FORWARD_EPS, None, False
        )
        observations = [
            build_observation(
                metric="price",
                value=535.07,
                unit="USD",
                provider="YahooFinance",
                source_type="API_LIVE",
                definition="market price",
                methodology="Yahoo chart regularMarketPrice",
                retrieved_at="2026-10-09T00:00:00Z",
                period_end=VALUATION_DATE,
                as_of=VALUATION_DATE,
            ),
            build_observation(
                metric=METRIC_CONSENSUS_FORWARD_EPS,
                value=23.67732,
                unit="USD/shares",
                provider="YahooFinanceFundamentals",
                source_type="API_LIVE",
                definition="Consensus forward EPS. Never synthesized.",
                methodology="m",
                retrieved_at="2026-10-09T00:00:00Z",
                currency="USD",
                available_at_basis="UNDECLARED",
                raw=archived_raw,
                observation_id="consensus_forward_eps-001",
            ),
        ]
        rebuilt = MarketData(
            ticker="MSFT",
            company_name="Microsoft",
            exchange="NMS",
            currency="USD",
            price=535.07,
            price_date=VALUATION_DATE,
            price_source="Yahoo chart regularMarketPrice",
            price_source_url=None,
            price_history=[],
            volume_history=[],
        )
        _apply_observations_to_view(rebuilt, observations, as_of=VALUATION_DATE)
        self.assertEqual(rebuilt.consensus_forward_eps_period, "+1y")
        self.assertEqual(rebuilt.consensus_forward_eps_period_end, "2028-06-30")


class TestTerminalPeriodEnd(unittest.TestCase):
    def test_one_calendar_year_from_the_valuation_date(self):
        self.assertEqual(
            terminal_period_end(VALUATION_DATE, 1.0), TARGET_END
        )

    def test_a_leap_day_is_not_lost(self):
        self.assertEqual(
            terminal_period_end("2028-02-29", 1.0), "2029-02-28"
        )

    def test_an_unreadable_date_yields_no_window(self):
        self.assertIsNone(terminal_period_end("not-a-date", 1.0))

    def test_a_non_positive_horizon_yields_no_window(self):
        self.assertIsNone(terminal_period_end(VALUATION_DATE, 0.0))
        self.assertIsNone(terminal_period_end(VALUATION_DATE, None))


class TestComparabilityIsDecidedOnTheDeclaredDate(unittest.TestCase):
    def test_msft_like_case_is_not_comparable_and_names_both_ends(self):
        scenario = _scenario()
        self.assertIn("CONSENSUS_PERIOD_NOT_COMPARABLE", scenario.flags)
        self.assertIsNone(scenario.gap_vs_consensus_terminal_eps)
        note = next(
            n for n in scenario.comparison_notes if "consensus period ends" in n
        )
        self.assertIn("2028-06-30", note)
        self.assertIn(TARGET_END, note)
        self.assertIn("265", note)

    def test_aapl_like_case_stays_comparable(self):
        scenario = _scenario(
            consensus_eps=9.58043, consensus_period_end="2027-09-30"
        )
        self.assertNotIn("CONSENSUS_PERIOD_NOT_COMPARABLE", scenario.flags)
        self.assertIsNotNone(scenario.gap_vs_consensus_terminal_eps)

    def test_exactly_the_tolerance_is_eligible(self):
        scenario = _scenario(consensus_period_end="2027-07-09")
        self.assertNotIn("CONSENSUS_PERIOD_NOT_COMPARABLE", scenario.flags)
        self.assertIsNotNone(scenario.gap_vs_consensus_terminal_eps)

    def test_one_day_past_the_tolerance_is_rejected(self):
        scenario = _scenario(consensus_period_end="2027-07-08")
        self.assertIn("CONSENSUS_PERIOD_NOT_COMPARABLE", scenario.flags)
        self.assertIsNone(scenario.gap_vs_consensus_terminal_eps)
        note = next(
            n for n in scenario.comparison_notes if "consensus period ends" in n
        )
        self.assertIn("93", note)

    def test_the_tolerance_and_horizon_are_declared(self):
        self.assertEqual(CONSENSUS_PERIOD_TOLERANCE_DAYS, 92)
        self.assertEqual(CONSENSUS_COMPARABLE_HORIZON_YEARS, 1.0)

    def test_a_declared_end_after_the_window_is_measured_not_truncated(self):
        # The offset is signed in the source and reported as a magnitude, so a
        # date on either side of the window end is judged the same way.
        late = _scenario(consensus_period_end="2028-06-30")
        early = _scenario(consensus_period_end="2027-04-09")
        for scenario in (late, early):
            self.assertIn("CONSENSUS_PERIOD_NOT_COMPARABLE", scenario.flags)
            self.assertIsNone(scenario.gap_vs_consensus_terminal_eps)


class TestUndeclaredPeriodIsNeverSynthesised(unittest.TestCase):
    def test_a_label_without_a_declared_end_is_not_compared(self):
        scenario = _scenario(consensus_period_end=None)
        self.assertIn("CONSENSUS_PERIOD_NOT_COMPARABLE", scenario.flags)
        self.assertIsNone(scenario.gap_vs_consensus_terminal_eps)
        self.assertTrue(
            any(
                "declares no readable period end" in n
                for n in scenario.comparison_notes
            )
        )

    def test_an_unreadable_declared_end_is_not_repaired(self):
        scenario = _scenario(consensus_period_end="not-a-date")
        self.assertIn("CONSENSUS_PERIOD_NOT_COMPARABLE", scenario.flags)
        self.assertIsNone(scenario.gap_vs_consensus_terminal_eps)

    def test_no_date_comes_from_the_label_alone(self):
        # With a declared end removed the label still says "+1y", and the
        # terminal window still ends 2027-10-09. Nothing derives one from the
        # other, so the comparison stays unavailable.
        reference = build_consensus_reference(
            consensus_eps=23.67732,
            consensus_basis=ANCHOR_FORWARD,
            consensus_months_covered=12.0,
            consensus_provider="YahooFinanceFundamentals",
            consensus_period_label="+1y",
            consensus_period_end=None,
            consensus_target_period_end=TARGET_END,
        )
        self.assertEqual(reference["source_period_label"], "+1y")
        self.assertIsNone(reference["period_end"])
        self.assertFalse(reference["period_end_declared_by_source"])
        self.assertEqual(reference["target_period_end"], TARGET_END)

    def test_a_missing_consensus_is_still_not_substituted(self):
        scenario = _scenario(consensus_eps=None)
        self.assertIn("NO_CONSENSUS_FOR_COMPARISON", scenario.flags)
        self.assertIsNone(scenario.gap_vs_consensus_terminal_eps)

    def test_a_non_positive_consensus_is_still_refused(self):
        scenario = _scenario(consensus_eps=-1.0)
        self.assertIn("CONSENSUS_NOT_USABLE_FOR_COMPARISON", scenario.flags)
        self.assertIsNone(scenario.gap_vs_consensus_terminal_eps)

    def test_an_undatable_price_leaves_the_comparison_unavailable(self):
        scenario = _scenario(as_of=None)
        self.assertIn("CONSENSUS_PERIOD_NOT_COMPARABLE", scenario.flags)
        self.assertIsNone(scenario.gap_vs_consensus_terminal_eps)


class TestLongerHorizonRejectionIsIntact(unittest.TestCase):
    def test_a_two_year_horizon_is_rejected_even_with_a_declared_end(self):
        scenario = _scenario(
            horizon_years=2.0, consensus_period_end="2028-09-30"
        )
        self.assertIn("CONSENSUS_PERIOD_NOT_COMPARABLE", scenario.flags)
        self.assertIsNone(scenario.gap_vs_consensus_terminal_eps)
        self.assertTrue(
            any("different periods" in n for n in scenario.comparison_notes)
        )

    def test_a_three_year_horizon_is_rejected(self):
        for years in (2.0, 3.0, 5.0):
            with self.subTest(years=years):
                scenario = _scenario(horizon_years=years)
                self.assertIn(
                    "CONSENSUS_PERIOD_NOT_COMPARABLE", scenario.flags
                )
                self.assertIsNone(scenario.gap_vs_consensus_terminal_eps)

    def test_a_trailing_basis_consensus_is_rejected_on_a_longer_horizon(self):
        from reverse_requirements import ANCHOR_TTM

        scenario = _scenario(
            horizon_years=3.0,
            consensus_basis=ANCHOR_TTM,
            consensus_period_end="2025-09-30",
        )
        self.assertIn("CONSENSUS_PERIOD_NOT_COMPARABLE", scenario.flags)


class TestReportAndFingerprint(unittest.TestCase):
    def test_the_report_carries_the_declared_facts(self):
        report = _report()
        self.assertEqual(report["formula_version"], FORMULA_VERSION)
        consensus = report["consensus_reference"]
        self.assertEqual(consensus["eps"], 23.67732)
        self.assertEqual(consensus["source_period_label"], "+1y")
        self.assertEqual(consensus["period_end"], "2028-06-30")
        self.assertTrue(consensus["period_end_declared_by_source"])
        self.assertEqual(consensus["target_period_end"], TARGET_END)
        self.assertEqual(consensus["provider"], "YahooFinanceFundamentals")
        self.assertEqual(consensus["comparison_tolerance_days"], 92)

    def test_the_report_explains_the_missing_gap_in_a_reading_note(self):
        report = _report()
        self.assertTrue(
            any(
                "period the source declared" in note
                for note in report["reading_notes"]
            )
        )

    def test_an_eligible_report_keeps_the_declared_date_checkable(self):
        report = _report(
            consensus_eps=9.58043, consensus_period_end="2027-09-30"
        )
        row = report["reverse_requirements_matrix"][0]
        self.assertEqual(row["gap_vs_consensus_terminal_eps"], row["required_terminal_eps"] / 9.58043 - 1.0)
        self.assertEqual(
            report["consensus_reference"]["period_end"], "2027-09-30"
        )

    def test_the_declared_end_is_part_of_the_fingerprint(self):
        base = _report()["fingerprint"]
        moved = _report(consensus_period_end="2027-09-30")["fingerprint"]
        self.assertNotEqual(base, moved)

    def test_a_changed_declared_period_label_changes_the_fingerprint(self):
        base = _report()["fingerprint"]
        moved = _report(consensus_period_label="0y")["fingerprint"]
        self.assertNotEqual(base, moved)

    def test_identical_inputs_reproduce_the_fingerprint(self):
        self.assertEqual(_report()["fingerprint"], _report()["fingerprint"])


class TestFormulaOutputsAreUnchanged(unittest.TestCase):
    """
    The correction changes only whether a consensus gap is reported. Every
    published figure has to stay identical for identical inputs, and the
    production P/E reference has to stay untouched.
    """

    def _matrix(self, **overrides):
        return build_matrix(
            price=535.07,
            horizons_years=[1.0, 2.0, 3.0, 5.0],
            required_returns=[0.08, 0.10, 0.12, 0.15],
            exit_multiples=[
                ReferenceMultiple(value=value, source="production_historical_pe_percentile")
                for value in (24.879538, 29.283776, 33.195873, 38.063518, 42.440328)
            ],
            start_anchor=_anchor(),
            current_pe=29.81,
            consensus_eps=23.67732,
            consensus_basis=ANCHOR_FORWARD,
            consensus_months_covered=12.0,
            as_of=VALUATION_DATE,
            **overrides,
        )

    def test_only_the_consensus_gap_changes(self):
        # Two runs that differ only in the declared consensus period end.
        # One is eligible and one is not, so this proves the declared period
        # reaches the comparability decision and nothing else it feeds.
        eligible = self._matrix(consensus_period_end="2027-09-30")
        rejected = self._matrix(consensus_period_end="2028-06-30")
        self.assertEqual(len(eligible), len(rejected))
        differing = set()
        for ok, bad in zip(eligible, rejected):
            self.assertEqual(ok.required_exit_price, bad.required_exit_price)
            self.assertEqual(ok.required_terminal_eps, bad.required_terminal_eps)
            self.assertEqual(
                ok.total_terminal_eps_growth, bad.total_terminal_eps_growth
            )
            self.assertEqual(ok.required_eps_cagr, bad.required_eps_cagr)
            self.assertEqual(ok.growth_years, bad.growth_years)
            self.assertEqual(
                ok.terminal_pe_change_vs_current_pe,
                bad.terminal_pe_change_vs_current_pe,
            )
            self.assertEqual(ok.required_return_basis, bad.required_return_basis)
            self.assertEqual(ok.start_anchor, bad.start_anchor)
            self.assertEqual(ok.exit_multiple, bad.exit_multiple)
            self.assertEqual(ok.calculation_steps, bad.calculation_steps)
            for key in set(ok.contract_view()) | set(bad.contract_view()):
                if key in ("gap_vs_consensus_terminal_eps", "flags",
                           "comparison_notes"):
                    continue
                self.assertEqual(
                    ok.contract_view()[key], bad.contract_view()[key], key
                )
            if ok.gap_vs_consensus_terminal_eps != bad.gap_vs_consensus_terminal_eps:
                differing.add(ok.horizon_years)
        # Only the one-year rows can differ: longer horizons never reach the
        # date comparison, so their gap stays unreported in both runs.
        self.assertEqual(differing, {1.0})

    def test_an_eligible_row_reports_the_gap_and_a_rejected_one_does_not(self):
        eligible = next(
            s for s in self._matrix(consensus_period_end="2027-09-30")
            if s.horizon_years == 1.0
        )
        rejected = next(
            s for s in self._matrix(consensus_period_end="2028-06-30")
            if s.horizon_years == 1.0
        )
        self.assertIsNotNone(eligible.gap_vs_consensus_terminal_eps)
        self.assertIsNone(rejected.gap_vs_consensus_terminal_eps)
        self.assertIn(
            "CONSENSUS_PERIOD_NOT_COMPARABLE", rejected.flags
        )

    def test_the_multi_year_rows_are_identical_either_way(self):
        eligible = self._matrix(consensus_period_end="2027-09-30")
        rejected = self._matrix(consensus_period_end="2028-06-30")
        for ok, bad in zip(eligible, rejected):
            if ok.horizon_years == 1.0:
                continue
            self.assertIsNone(ok.gap_vs_consensus_terminal_eps)
            self.assertIsNone(bad.gap_vs_consensus_terminal_eps)
            self.assertEqual(
                ok.gap_vs_consensus_terminal_eps,
                bad.gap_vs_consensus_terminal_eps,
            )

    def test_the_five_eligible_percentile_choices_are_unchanged(self):
        eligible = self._matrix(consensus_period_end="2027-09-30")
        rejected = self._matrix(consensus_period_end="2028-06-30")
        self.assertEqual(
            sorted({s.exit_multiple.value for s in eligible}),
            sorted({s.exit_multiple.value for s in rejected}),
        )
        self.assertEqual(
            {s.exit_multiple.eligibility_state for s in eligible},
            {s.exit_multiple.eligibility_state for s in rejected},
        )

    def test_start_eps_provenance_is_unchanged(self):
        eligible = self._matrix(consensus_period_end="2027-09-30")
        rejected = self._matrix(consensus_period_end="2028-06-30")
        for ok, bad in zip(eligible, rejected):
            anchor = ok.start_anchor
            self.assertEqual(anchor.basis, "TRAILING_TWELVE_MONTHS")
            self.assertTrue(anchor.period_undeclared_by_source)
            self.assertEqual(anchor.contract_view(), bad.start_anchor.contract_view())
            self.assertIsNone(anchor.sec_fact)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
