"""
Tests for the financial history module.

Known-answer fixtures check the arithmetic; the rest check the rules that keep a
history honest: growth only between comparable windows, margins only inside one
period, duplicates collapsed only when they agree, and conflicts preserved.
"""
from __future__ import annotations

import sys
import unittest
from dataclasses import replace

sys.path.insert(0, ".")

from data_contract import Observation, ValidationStatus
from financial_history import (
    HISTORY_FORMULA_VERSION,
    build_financial_history,
    build_series,
    classify_window,
    growth_against_prior_year,
    margin_for_periods,
)


def obs(
    metric: str,
    value: float,
    period_start: str,
    period_end: str,
    *,
    unit: str = "currency",
    currency: str = "USD",
    derivation: str = "",
    form: str = "",
    accession: str = "",
    available_at: str = "",
):
    return Observation(
        observation_id="obs-%s-%s" % (metric, period_end),
        metric=metric,
        value=value,
        unit=unit,
        currency=currency,
        currency_basis="REPORTED",
        period_start=period_start,
        period_end=period_end,
        as_of=period_end,
        available_at=available_at or (period_end + "T00:00:00Z"),
        available_at_basis="ACCEPTANCE_DATETIME",
        provider="SecEdgar",
        source_type="REGULATORY_FILING",
        source_url=None,
        definition="test",
        methodology="test",
        retrieved_at="2026-01-01T00:00:00Z",
        raw={"derivation": derivation, "constituents": [{"form": form, "accession": accession}]},
        status=ValidationStatus.UNVERIFIABLE,
    )


ANNUAL_2023 = obs("revenue", 100.0, "2022-09-25", "2023-09-24", derivation="ANNUAL_FACT_AS_TRAILING_WINDOW", form="10-K")
ANNUAL_2024 = obs("revenue", 120.0, "2023-09-25", "2024-09-28", derivation="ANNUAL_FACT_AS_TRAILING_WINDOW", form="10-K")
ANNUAL_2025 = obs("revenue", 150.0, "2024-09-29", "2025-09-27", derivation="ANNUAL_ROLL_FORWARD", form="10-K")
Q1_2025 = obs("revenue", 20.0, "2024-12-29", "2025-03-29")
Q1_2026 = obs("revenue", 25.0, "2025-12-28", "2026-03-28")


class TestWindowClassification(unittest.TestCase):
    def test_annual_window(self):
        self.assertEqual(classify_window(ANNUAL_2024), "ANNUAL")

    def test_quarterly_window(self):
        self.assertEqual(classify_window(Q1_2026), "QUARTERLY")

    def test_instant_has_no_period_start(self):
        instant = obs("cash", 5.0, None, "2024-09-28")
        self.assertEqual(classify_window(instant), "INSTANT")

    def test_irregular_span_is_labelled_rather_than_guessed(self):
        odd = obs("revenue", 1.0, "2024-01-01", "2024-03-01")
        self.assertEqual(classify_window(odd), "OTHER_60_DAYS")


class TestSeriesOrdering(unittest.TestCase):
    def test_series_is_ordered_by_period_end(self):
        series = build_series([ANNUAL_2025, ANNUAL_2023, ANNUAL_2024], "revenue", "ANNUAL")
        self.assertEqual(
            [p.period_end for p in series.points],
            ["2023-09-24", "2024-09-28", "2025-09-27"],
        )

    def test_series_keeps_quarters_and_years_apart(self):
        series = build_series([ANNUAL_2024, Q1_2026], "revenue", "ANNUAL")
        self.assertEqual(len(series.points), 1)

    def test_absent_series_is_reported_not_empty(self):
        series = build_series([ANNUAL_2024], "ebitda", "ANNUAL")
        self.assertEqual(series.points, [])
        self.assertTrue(series.unavailable)
        self.assertEqual(series.unavailable[0]["reason_kind"], "MISSING")

    def test_point_carries_its_own_provenance(self):
        series = build_series([ANNUAL_2025], "revenue", "ANNUAL")
        view = series.points[0].contract_view()
        self.assertEqual(view["provider"], "SecEdgar")
        self.assertEqual(view["form"], "10-K")
        self.assertEqual(view["derivation"], "ANNUAL_ROLL_FORWARD")
        self.assertEqual(view["formula_version"], HISTORY_FORMULA_VERSION)
        self.assertEqual(view["currency"], "USD")
        self.assertTrue(view["available_at"])


class TestDeduplication(unittest.TestCase):
    def test_agreeing_duplicates_collapse_to_the_better_documented_one(self):
        plain = obs("revenue", 416.0, "2024-09-29", "2025-09-27")
        rich = obs(
            "revenue", 416.0, "2024-09-29", "2025-09-27",
            derivation="ANNUAL_FACT_AS_TRAILING_WINDOW", form="10-K", accession="acc-1",
        )
        series = build_series([plain, rich], "revenue", "ANNUAL")
        self.assertEqual(len(series.points), 1)
        self.assertEqual(series.points[0].form, "10-K")

    def test_the_losing_derivation_is_recorded_rather_than_lost(self):
        plain = obs("revenue", 416.0, "2024-09-29", "2025-09-27")
        rich = obs("revenue", 416.0, "2024-09-29", "2025-09-27", derivation="ROLL", form="10-K")
        series = build_series([plain, rich], "revenue", "ANNUAL")
        self.assertEqual(series.points[0].alternate_derivations, ())

    def test_disagreeing_values_are_both_kept_and_the_conflict_reported(self):
        a = obs("revenue", 416.0, "2024-09-29", "2025-09-27", form="10-K")
        b = obs("revenue", 420.0, "2024-09-29", "2025-09-27", form="10-K")
        series = build_series([a, b], "revenue", "ANNUAL")
        self.assertEqual(len(series.points), 2)
        conflicts = [e for e in series.unavailable if e["reason_kind"] == "SOURCE_CONFLICT"]
        self.assertEqual(len(conflicts), 1)
        self.assertIn("no winner is selected", conflicts[0]["reason"])


class TestGrowth(unittest.TestCase):
    def test_known_answer_year_over_year(self):
        points = build_series([ANNUAL_2023, ANNUAL_2024, ANNUAL_2025], "revenue", "ANNUAL").points
        rows = growth_against_prior_year(points)
        by_end = {r["period_end"]: r for r in rows}
        # 120/100 - 1
        self.assertAlmostEqual(by_end["2024-09-28"]["growth"], 0.2, places=12)
        # 150/120 - 1
        self.assertAlmostEqual(by_end["2025-09-27"]["growth"], 0.25, places=12)

    def test_first_period_has_no_growth_and_says_why(self):
        points = build_series([ANNUAL_2023], "revenue", "ANNUAL").points
        row = growth_against_prior_year(points)[0]
        self.assertIsNone(row["growth"])
        self.assertFalse(row["comparable"])
        self.assertIn("No observation", row["reason"])

    def test_quarterly_is_never_compared_to_annual(self):
        # An annual and a quarterly figure about a year apart are different
        # measurements; differencing them would produce a number that looks
        # like growth and is not.
        points = build_series([ANNUAL_2024, Q1_2026], "revenue", "ANNUAL").points
        self.assertEqual(len(points), 1)

    def test_zero_prior_value_yields_no_rate(self):
        zero = obs("revenue", 0.0, "2022-09-25", "2023-09-24")
        points = build_series([zero, ANNUAL_2024], "revenue", "ANNUAL").points
        rows = {r["period_end"]: r for r in growth_against_prior_year(points)}
        self.assertIsNone(rows["2024-09-28"]["growth"])
        self.assertIn("zero", rows["2024-09-28"]["reason"])

    def test_52_week_calendar_drift_is_noted(self):
        # A retail 52/53-week calendar makes a "year" 364 or 373 days. The
        # rate is still computed over the declared span, but a drift beyond
        # five days is stated rather than silently normalised away.
        shifted = obs("revenue", 200.0, "2023-09-24", "2024-10-01")
        points = build_series([ANNUAL_2023, shifted], "revenue", "ANNUAL").points
        row = {r["period_end"]: r for r in growth_against_prior_year(points)}["2024-10-01"]
        self.assertIsNotNone(row["growth"])
        self.assertEqual(row["period_gap_days"], 373)
        self.assertIn("52/53-week", row["reason"])

    def test_small_calendar_drift_is_not_over_reported(self):
        # Four days is ordinary filing drift, not a 53-week year. Reporting it
        # on every row would bury the cases that matter.
        shifted = obs("revenue", 200.0, "2023-09-24", "2024-09-27")
        points = build_series([ANNUAL_2023, shifted], "revenue", "ANNUAL").points
        row = {r["period_end"]: r for r in growth_against_prior_year(points)}["2024-09-27"]
        self.assertEqual(row["reason"], "")


class TestMargin(unittest.TestCase):
    def test_known_answer_margin(self):
        revenue = build_series([ANNUAL_2024, ANNUAL_2025], "revenue", "ANNUAL").points
        earnings = build_series(
            [
                obs("net_income", 30.0, "2023-09-25", "2024-09-28"),
                obs("net_income", 45.0, "2024-09-29", "2025-09-27"),
            ],
            "net_income",
            "ANNUAL",
        ).points
        rows = {r["period_end"]: r for r in margin_for_periods(earnings, revenue, "net_margin")}
        self.assertAlmostEqual(rows["2024-09-28"]["margin"], 30.0 / 120.0, places=12)
        self.assertAlmostEqual(rows["2025-09-27"]["margin"], 45.0 / 150.0, places=12)

    def test_period_without_a_counterpart_is_not_computed(self):
        revenue = build_series([ANNUAL_2024], "revenue", "ANNUAL").points
        earnings = build_series(
            [obs("net_income", 30.0, "2024-09-29", "2025-09-27")], "net_income", "ANNUAL"
        ).points
        rows = margin_for_periods(earnings, revenue, "net_margin")
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["margin"])
        self.assertIn("different periods", rows[0]["reason"])

    def test_zero_denominator_is_refused(self):
        revenue = build_series(
            [obs("revenue", 0.0, "2023-09-25", "2024-09-28")], "revenue", "ANNUAL"
        ).points
        earnings = build_series(
            [obs("net_income", 30.0, "2023-09-25", "2024-09-28")], "net_income", "ANNUAL"
        ).points
        row = margin_for_periods(earnings, revenue, "net_margin")[0]
        self.assertIsNone(row["margin"])

    def test_currency_mismatch_is_flagged(self):
        revenue = build_series([ANNUAL_2024], "revenue", "ANNUAL").points
        earnings = build_series(
            [obs("net_income", 30.0, "2023-09-25", "2024-09-28", currency="EUR")],
            "net_income",
            "ANNUAL",
        ).points
        row = margin_for_periods(earnings, revenue, "net_margin")[0]
        self.assertIn("CURRENCY_MISMATCH", row["currency_match"])


class TestFullHistoryBlock(unittest.TestCase):
    def test_block_has_every_declared_key(self):
        block = build_financial_history([ANNUAL_2024, ANNUAL_2025])
        for key in ("formula_version", "series", "growth", "margins", "unavailable", "reading_notes"):
            self.assertIn(key, block)

    def test_quarterly_and_annual_are_separate_series(self):
        block = build_financial_history([ANNUAL_2024, ANNUAL_2025, Q1_2025, Q1_2026])
        self.assertIn("revenue.annual", block["series"])
        self.assertIn("revenue.quarterly", block["series"])
        self.assertEqual(block["series"]["revenue.quarterly"]["count"], 2)

    def test_missing_metric_is_reported_with_a_reason(self):
        block = build_financial_history([ANNUAL_2024])
        items = [entry["item"] for entry in block["unavailable"]]
        self.assertIn("net_income.annual", items)

    def test_empty_input_produces_a_block_that_says_so(self):
        block = build_financial_history([])
        self.assertEqual(block["series"]["revenue.annual"]["count"], 0)
        self.assertTrue(block["unavailable"])
        self.assertTrue(block["reading_notes"])

    def test_block_is_deterministic(self):
        observations = [ANNUAL_2023, ANNUAL_2024, ANNUAL_2025, Q1_2025, Q1_2026]
        first = build_financial_history(observations)
        second = build_financial_history(observations)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main(verbosity=2)
