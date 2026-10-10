"""
Targeted tests for Phase D:
- Point-in-time (INSTANT) financial observations
- Distinction between INSTANT and DURATION in classification, validation, comparison, and serialization
- Refusal of invalid instant-versus-duration growth and margin calculations
- Multi-exit-multiple reverse requirements matrix across holding periods and required returns
- Preserving full provenance: price, as_of time, exit multiple origin, starting EPS basis, formula version
- Implied net margin with both derived and observed share-count variants
"""
from __future__ import annotations

import unittest

from data_contract import Observation, ValidationStatus
from financial_history import (
    HISTORY_FORMULA_VERSION,
    build_financial_history,
    build_series,
    classify_window,
    growth_against_prior_year,
    margin_for_periods,
)
from reverse_requirements import (
    ANCHOR_TTM,
    FORMULA_VERSION,
    EpsAnchor,
    ReferenceMultiple,
    build_matrix,
    build_reverse_requirements_report,
    build_scenario,
    exit_multiples_from_band,
    valuation_method_scenarios,
)


def make_obs(
    metric: str,
    value: float,
    period_start: str | None,
    period_end: str | None,
    *,
    unit: str = "currency",
    currency: str = "USD",
    provider: str = "SecEdgar",
    form: str = "10-Q",
    accession: str = "0000320193-26-000100",
    fy: int | None = 2026,
    fp: str | None = "Q3",
) -> Observation:
    return Observation(
        observation_id=f"obs-{metric}-{period_end}",
        metric=metric,
        value=value,
        unit=unit,
        currency=currency,
        currency_basis="REPORTED",
        period_start=period_start,
        period_end=period_end,
        as_of=period_end,
        available_at=(period_end + "T14:00:00Z") if period_end else None,
        available_at_basis="ACCEPTANCE_DATETIME",
        provider=provider,
        source_type="REGULATORY_FILING",
        source_url=None,
        definition=f"Observed {metric}",
        methodology="SEC XBRL",
        retrieved_at="2026-10-10T00:00:00Z",
        raw={"form": form, "accession": accession, "fy": fy, "fp": fp},
        status=ValidationStatus.UNVERIFIABLE,
    )


class TestInstantObservationContracts(unittest.TestCase):
    def test_instant_has_effective_date_and_no_period_start(self):
        obs = make_obs("cash", 40.0, None, "2026-06-27")
        self.assertIsNone(obs.period_start)
        self.assertEqual(obs.period_end, "2026-06-27")
        self.assertEqual(classify_window(obs), "INSTANT")

    def test_instant_with_equal_start_and_end_is_also_instant(self):
        obs = make_obs("cash", 40.0, "2026-06-27", "2026-06-27")
        self.assertEqual(classify_window(obs), "INSTANT")

    def test_missing_date_is_rejected(self):
        no_end = make_obs("cash", 40.0, None, None)
        self.assertEqual(classify_window(no_end), "MISSING_DATE")

        unparseable = make_obs("cash", 40.0, None, "not-a-date")
        self.assertEqual(classify_window(unparseable), "MISSING_DATE")

    def test_inverted_period_is_rejected(self):
        inverted = make_obs("revenue", 100.0, "2026-06-27", "2025-06-27")
        self.assertEqual(classify_window(inverted), "INVALID_PERIOD")

    def test_serialization_preserves_period_type_and_fiscal_context(self):
        instant_obs = make_obs("assets", 383.0, None, "2026-06-27", fy=2026, fp="Q3")
        series = build_series([instant_obs], "assets", "INSTANT")
        self.assertEqual(len(series.points), 1)
        point = series.points[0]
        view = point.contract_view()

        self.assertEqual(view["period_type"], "INSTANT")
        self.assertEqual(view["window"], "INSTANT")
        self.assertIsNone(view["period_start"])
        self.assertEqual(view["period_end"], "2026-06-27")
        self.assertEqual(view["fiscal_year"], 2026)
        self.assertEqual(view["fiscal_period"], "Q3")
        self.assertEqual(view["available_at_basis"], "ACCEPTANCE_DATETIME")
        self.assertEqual(view["formula_version"], HISTORY_FORMULA_VERSION)

        # Duration fact maintains period_type DURATION
        duration_obs = make_obs("revenue", 100.0, "2025-06-28", "2026-06-27", fy=2026, fp="FY")
        dur_series = build_series([duration_obs], "revenue", "ANNUAL")
        dur_view = dur_series.points[0].contract_view()
        self.assertEqual(dur_view["period_type"], "DURATION")
        self.assertEqual(dur_view["window"], "ANNUAL")
        self.assertEqual(dur_view["fiscal_year"], 2026)


class TestArithmeticRejectionOfInvalidComparisons(unittest.TestCase):
    def test_growth_rejects_instant_observation(self):
        p1 = build_series([make_obs("cash", 30.0, None, "2025-06-28")], "cash", "INSTANT").points[0]
        p2 = build_series([make_obs("cash", 40.0, None, "2026-06-27")], "cash", "INSTANT").points[0]

        rows = growth_against_prior_year([p1, p2])
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertFalse(row["comparable"])
            self.assertIsNone(row["growth"])
            self.assertIn("point-in-time balance", row["reason"])

    def test_growth_candidate_search_rejects_mixed_instant_and_duration(self):
        instant_prior = build_series([make_obs("revenue", 90.0, None, "2025-06-28")], "revenue", "INSTANT").points[0]
        duration_current = build_series([make_obs("revenue", 100.0, "2025-06-28", "2026-06-27")], "revenue", "ANNUAL").points[0]

        rows = growth_against_prior_year([instant_prior, duration_current])
        self.assertEqual(len(rows), 2)
        # The duration current must not match against the instant prior
        self.assertFalse(rows[1]["comparable"])
        self.assertIsNone(rows[1]["growth"])
        self.assertIn("No observation of this metric covering a comparable window", rows[1]["reason"])

    def test_margin_rejects_instant_numerator(self):
        cash_instant = build_series([make_obs("cash", 40.0, None, "2026-06-27")], "cash", "INSTANT").points
        rev_annual = build_series([make_obs("revenue", 100.0, "2025-06-28", "2026-06-27")], "revenue", "ANNUAL").points

        rows = margin_for_periods(cash_instant, rev_annual, "cash_margin")
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["comparable"])
        self.assertIsNone(rows[0]["margin"])
        self.assertIn("point-in-time balance", rows[0]["reason"])

    def test_margin_rejects_instant_denominator(self):
        ni_annual = build_series([make_obs("net_income", 25.0, "2025-06-28", "2026-06-27")], "net_income", "ANNUAL").points
        assets_instant = build_series([make_obs("assets", 380.0, None, "2026-06-27")], "assets", "INSTANT").points

        rows = margin_for_periods(ni_annual, assets_instant, "roa")
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["comparable"])
        self.assertIsNone(rows[0]["margin"])
        self.assertIn("point-in-time balance", rows[0]["reason"])

    def test_margin_rejects_instant_over_instant(self):
        cash_instant = build_series([make_obs("cash", 40.0, None, "2026-06-27")], "cash", "INSTANT").points
        debt_instant = build_series([make_obs("long_term_debt", 80.0, None, "2026-06-27")], "long_term_debt", "INSTANT").points

        rows = margin_for_periods(cash_instant, debt_instant, "cash_debt_ratio")
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["comparable"])
        self.assertIsNone(rows[0]["margin"])
        self.assertIn("point-in-time balance", rows[0]["reason"])


class TestMultiExitMultipleMatrix(unittest.TestCase):
    def setUp(self):
        self.anchor = EpsAnchor(
            value=8.72,
            basis=ANCHOR_TTM,
            months_covered=12.0,
            period_label="trailing twelve months",
            provider="fixture",
            currency="USD",
        )

    def test_matrix_produces_independent_cells_across_multiple_multiples(self):
        horizons = [1.0, 3.0]
        rates = [0.08, 0.12]
        multiples = [
            ReferenceMultiple(value=25.0, source="user_supplied"),
            ReferenceMultiple(value=32.0, source="user_supplied"),
            ReferenceMultiple(value=40.0, source="user_supplied"),
        ]

        scenarios = build_matrix(
            price=336.64,
            horizons_years=horizons,
            required_returns=rates,
            exit_multiples=multiples,
            start_anchor=self.anchor,
            current_pe=38.61,
            currency="USD",
            as_of="2026-10-09",
        )

        # 2 horizons * 2 returns * 3 multiples = 12 cells
        self.assertEqual(len(scenarios), 12)

        pe_set = {s.exit_multiple.value for s in scenarios}
        self.assertEqual(pe_set, {25.0, 32.0, 40.0})

        # Check preservation of every scenario's provenance
        first = scenarios[0]
        self.assertEqual(first.price, 336.64)
        self.assertEqual(first.as_of, "2026-10-09")
        self.assertEqual(first.exit_multiple.source, "user_supplied")
        self.assertEqual(first.start_anchor.basis, ANCHOR_TTM)
        self.assertEqual(first.start_anchor.value, 8.72)
        self.assertEqual(first.required_return_basis, "PRICE_RETURN_ONLY")

        view = first.contract_view()
        self.assertEqual(view["price"], 336.64)
        self.assertEqual(view["as_of"], "2026-10-09")
        self.assertEqual(view["formula_version"], FORMULA_VERSION)

    def test_refuses_8_sample_pe_band_under_20_policy(self):
        thin_band = {
            "10th": 31.0,
            "25th": 33.0,
            "median": 35.0,
            "75th": 37.0,
            "90th": 39.0,
            "observations": 8,
        }
        multiples, unavailable = exit_multiples_from_band(thin_band, min_observations=20)
        self.assertEqual(multiples, [])
        self.assertEqual(len(unavailable), 1)
        self.assertEqual(unavailable[0]["reason_kind"], "INSUFFICIENT_OBSERVATIONS")
        self.assertIn("8 observations", unavailable[0]["reason"])


class TestImpliedNetMarginShareVariants(unittest.TestCase):
    def test_implied_net_margin_reports_both_derived_and_observed_share_counts(self):
        pe = ReferenceMultiple(value=32.0, source="user_supplied")
        ps = ReferenceMultiple(value=10.0, source="user_supplied")

        report = valuation_method_scenarios(
            price=300.0,
            shares=None,
            market_cap=4_500_000_000_000.0,
            enterprise_value=None,
            free_cash_flow=None,
            ebitda=None,
            revenue=450_000_000_000.0,
            trailing_eps=8.0,
            observed_net_margin=0.25,
            observed_net_margin_period="2026-06-27",
            observed_shares_outstanding=14_000_000_000.0,
            observed_shares_date="2026-07-17",
            multiples={"pe": pe, "revenue": ps},
        )

        inm = report["methods"]["implied_net_margin"]
        self.assertEqual(inm["status"], "COMPUTED")
        variants = inm.get("share_basis_variants")
        self.assertIsNotNone(variants)
        self.assertEqual(len(variants), 2)

        # First variant is original derived: 4.5T / 300 = 15B shares
        derived_var = variants[0]
        self.assertEqual(derived_var["shares_source"], "derived")
        self.assertEqual(derived_var["shares"], 15_000_000_000.0)
        self.assertTrue(derived_var["is_original_formula"])

        # Second variant is observed point-in-time shares: 14B shares
        observed_var = variants[1]
        self.assertEqual(observed_var["shares_source"], "observed")
        self.assertEqual(observed_var["shares"], 14_000_000_000.0)
        self.assertEqual(observed_var["shares_date"], "2026-07-17")
        self.assertFalse(observed_var["is_original_formula"])
        self.assertIn("cover-page", observed_var["note"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
