"""
Targeted tests for ST-EVA Historical P/E Engine (Phase E).

Methodology: docs/ADR-HISTORICAL-PE-METHODOLOGY.md (Amendment 1, Decisions 10-14)
Contract: docs/methodology/CONTRACT-HISTORICAL-PE.md
"""

from __future__ import annotations

import datetime
from pathlib import Path
import unittest
from zoneinfo import ZoneInfo

from historical_pe import (
    AUDIT_STATUS_AUDITED,
    AUDIT_STATUS_REVIEWED,
    AUDIT_STATUS_UNAUDITED,
    CLOSED_REASON_CODES,
    CUTOFF_ET,
    EVIDENCE_CLASS_FILED,
    EVIDENCE_CLASS_FURNISHED,
    ET,
    HistoricalPeDistribution,
    HistoricalPeObservation,
    HistoricalPriceEvidence,
    LOGIC_VERSION,
    METRIC_ANNUAL_GAAP_DILUTED_PE,
    METRIC_CURRENT_PE,
    METRIC_TTM_GAAP_DILUTED_PE,
    MIN_OBSERVATIONS_FOR_REFERENCE,
    QuarterEpsEvidence,
    REASON_CORPORATE_ACTION_UNRESOLVED,
    REASON_INSUFFICIENT_OBSERVATIONS,
    REASON_INSUFFICIENT_QUARTERS,
    REASON_MISSING_PRICE,
    REASON_MISSING_Q4_EPS,
    REASON_NON_POSITIVE_EPS,
    STATUS_AVAILABLE,
    STATUS_INSUFFICIENT_OBSERVATIONS,
    STATUS_UNAVAILABLE,
    STATUS_USABLE_FOR_REFERENCE,
    build_historical_pe,
    compute_historical_pe_distribution,
    fiscal_year_of,
    load_aapl_historical_pe,
    quarter_number,
    resolve_usable_date,
)
from reverse_requirements import (
    exit_multiples_from_production_distribution,
    ReferenceMultiple,
)
from research_dossier import build_dossier, render_dossier
from st_eva_runner import run_st_eva


class TestCutoffAndCalendarRules(unittest.TestCase):
    """Test 16:00 ET convention (ADR Decision 3) and fiscal calendar resolver (Invariant F-3)."""

    def test_cutoff_rule_before_1600_et(self):
        # 15:30 ET -> same day close
        trading_days = ["2024-10-31", "2024-11-01", "2024-11-04"]
        t = datetime.datetime(2024, 10, 31, 15, 30, tzinfo=ET)
        usable, rule = resolve_usable_date(t, trading_days)
        self.assertEqual(usable, "2024-10-31")
        self.assertEqual(rule, "acceptance_before_1600ET_same_day")

    def test_cutoff_rule_at_or_after_1600_et(self):
        # 16:30 ET -> next trading day close
        trading_days = ["2024-10-31", "2024-11-01", "2024-11-04"]
        t = datetime.datetime(2024, 10, 31, 16, 30, tzinfo=ET)
        usable, rule = resolve_usable_date(t, trading_days)
        self.assertEqual(usable, "2024-11-01")
        self.assertEqual(rule, "acceptance_at_or_after_1600ET_next_trading_day")

    def test_cutoff_rule_over_weekend(self):
        # Friday 18:00 ET -> Monday next trading day
        trading_days = ["2024-11-01", "2024-11-04"]
        t = datetime.datetime(2024, 11, 1, 18, 0, tzinfo=ET)
        usable, rule = resolve_usable_date(t, trading_days)
        self.assertEqual(usable, "2024-11-04")
        self.assertEqual(rule, "acceptance_at_or_after_1600ET_next_trading_day")

    def test_fiscal_calendar_derivation_independent_of_10k_list(self):
        # F-3: September fiscal year end (fye_month=9)
        # Q1 ends in late December: month 12 -> FY is current year + 1, quarter 1
        d_q1 = datetime.date(2023, 12, 30)
        self.assertEqual(fiscal_year_of(d_q1, 9), 2024)
        self.assertEqual(quarter_number(d_q1, 9), 1)

        # Q2 ends in late March: month 3 -> FY is 2024, quarter 2
        d_q2 = datetime.date(2024, 3, 30)
        self.assertEqual(fiscal_year_of(d_q2, 9), 2024)
        self.assertEqual(quarter_number(d_q2, 9), 2)

        # Q3 ends in late June: month 6 -> FY is 2024, quarter 3
        d_q3 = datetime.date(2024, 6, 29)
        self.assertEqual(fiscal_year_of(d_q3, 9), 2024)
        self.assertEqual(quarter_number(d_q3, 9), 3)

        # Q4 ends in late September: month 9 -> FY is 2024, quarter 4
        d_q4 = datetime.date(2024, 9, 28)
        self.assertEqual(fiscal_year_of(d_q4, 9), 2024)
        self.assertEqual(quarter_number(d_q4, 9), 4)


class TestInvariants(unittest.TestCase):
    """Test invariants F-1 through F-15."""

    def test_f1_evidence_stated_directly_enforced(self):
        # Attempting to construct evidence with stated_directly=False raises ValueError
        with self.assertRaises(ValueError):
            QuarterEpsEvidence(
                evidence_id="ev-test",
                issuer_id="TEST",
                evidence_class=EVIDENCE_CLASS_FILED,
                form="10-Q",
                accession="0001",
                period_end="2024-03-31",
                fiscal_year=2024,
                fiscal_quarter=1,
                value=1.5,
                audit_status=AUDIT_STATUS_REVIEWED,
                acceptance_datetime="2024-04-01T15:00:00-04:00",
                usable_date="2024-04-01",
                usable_date_rule="acceptance_before_1600ET_same_day",
                stated_directly=False,
            )

    def test_f2_f3_ttm_window_requires_4_consecutive_quarters_and_q4(self):
        # 3 quarters only -> REASON_INSUFFICIENT_QUARTERS
        trading_days = ["2024-04-01", "2024-07-01", "2024-10-01"]
        prices = {
            "2024-10-01": HistoricalPriceEvidence(
                price_evidence_id="p-1",
                issuer_id="TEST",
                instrument_id="TEST",
                price_date="2024-10-01",
                close=100.0,
            )
        }
        # Only Q1, Q2, Q3 of FY2024 (missing Q4)
        ev1 = QuarterEpsEvidence(
            evidence_id="e1", issuer_id="TEST", evidence_class=EVIDENCE_CLASS_FILED,
            form="10-Q", accession="01", period_end="2023-12-31", fiscal_year=2024,
            fiscal_quarter=1, value=1.0, audit_status=AUDIT_STATUS_REVIEWED,
            acceptance_datetime="2024-01-15T15:00:00-04:00", usable_date="2024-04-01",
            usable_date_rule="rule",
        )
        ev2 = QuarterEpsEvidence(
            evidence_id="e2", issuer_id="TEST", evidence_class=EVIDENCE_CLASS_FILED,
            form="10-Q", accession="02", period_end="2024-03-31", fiscal_year=2024,
            fiscal_quarter=2, value=1.0, audit_status=AUDIT_STATUS_REVIEWED,
            acceptance_datetime="2024-04-15T15:00:00-04:00", usable_date="2024-07-01",
            usable_date_rule="rule",
        )
        ev3 = QuarterEpsEvidence(
            evidence_id="e3", issuer_id="TEST", evidence_class=EVIDENCE_CLASS_FILED,
            form="10-Q", accession="03", period_end="2024-06-30", fiscal_year=2024,
            fiscal_quarter=3, value=1.0, audit_status=AUDIT_STATUS_REVIEWED,
            acceptance_datetime="2024-07-15T15:00:00-04:00", usable_date="2024-10-01",
            usable_date_rule="rule",
        )
        res = build_historical_pe(
            issuer_id="TEST",
            instrument_id="TEST",
            quarter_evidence=[ev1, ev2, ev3],
            annual_evidence=[],
            prices=prices,
            fye_month=9,
            trading_days=trading_days,
            evaluation_dates=["2024-10-01"],
        )
        obs = res.observations[0]
        self.assertEqual(obs.status, STATUS_UNAVAILABLE)
        self.assertEqual(obs.reason_code, REASON_MISSING_Q4_EPS)
        self.assertIn("fiscal_quarter", obs.eps_state["missing_quarters"][0])

    def test_f4_annual_never_fills_ttm(self):
        # When TTM is unavailable, annual P/E is reported separately as ANNUAL_GAAP_DILUTED_PE
        trading_days = ["2024-11-01"]
        prices = {
            "2024-11-01": HistoricalPriceEvidence(
                price_evidence_id="p-1",
                issuer_id="TEST",
                instrument_id="TEST",
                price_date="2024-11-01",
                close=100.0,
            )
        }
        ann_ev = QuarterEpsEvidence(
            evidence_id="a1", issuer_id="TEST", evidence_class=EVIDENCE_CLASS_FILED,
            form="10-K", accession="00-10k", period_end="2024-09-30", fiscal_year=2024,
            fiscal_quarter=4, value=4.0, audit_status=AUDIT_STATUS_AUDITED,
            acceptance_datetime="2024-10-31T15:00:00-04:00", usable_date="2024-11-01",
            usable_date_rule="rule",
        )
        res = build_historical_pe(
            issuer_id="TEST",
            instrument_id="TEST",
            quarter_evidence=[],  # No quarters
            annual_evidence=[ann_ev],
            prices=prices,
            fye_month=9,
            trading_days=trading_days,
            evaluation_dates=["2024-11-01"],
        )
        ttm_obs = res.observations[0]
        ann_obs = res.annual_observations[0]
        self.assertEqual(ttm_obs.status, STATUS_UNAVAILABLE)
        self.assertIsNone(ttm_obs.value)
        self.assertEqual(ann_obs.status, STATUS_AVAILABLE)
        self.assertEqual(ann_obs.value, 25.0)
        self.assertFalse(ann_obs.eps_state["substituted_for_ttm"])

    def test_f6_unaligned_accounting_basis_rejected(self):
        # If price accounting_basis is not "as_traded", observation is REASON_CORPORATE_ACTION_UNRESOLVED
        trading_days = ["2024-11-01"]
        prices = {
            "2024-11-01": HistoricalPriceEvidence(
                price_evidence_id="p-1",
                issuer_id="TEST",
                instrument_id="TEST",
                price_date="2024-11-01",
                close=100.0,
                accounting_basis="split_adjusted",  # Unaligned!
            )
        }
        dates = ["2024-03-31", "2024-06-30", "2024-09-30", "2024-12-31"]
        quarters = [
            QuarterEpsEvidence(
                evidence_id=f"e{i}", issuer_id="TEST", evidence_class=EVIDENCE_CLASS_FILED,
                form="10-Q" if i < 4 else "10-K", accession=f"0{i}",
                period_end=dates[i - 1], fiscal_year=2024, fiscal_quarter=i,
                value=1.0, audit_status=AUDIT_STATUS_REVIEWED,
                acceptance_datetime="2024-01-01T15:00:00-04:00", usable_date="2024-11-01",
                usable_date_rule="rule",
            )
            for i in (1, 2, 3, 4)
        ]
        res = build_historical_pe(
            issuer_id="TEST",
            instrument_id="TEST",
            quarter_evidence=quarters,
            annual_evidence=[],
            prices=prices,
            fye_month=12,
            trading_days=trading_days,
            evaluation_dates=["2024-11-01"],
        )
        self.assertEqual(res.observations[0].status, STATUS_UNAVAILABLE)
        self.assertEqual(res.observations[0].reason_code, REASON_CORPORATE_ACTION_UNRESOLVED)

    def test_f7_lookahead_rejection(self):
        # Invariant F-7: Point-in-time monotonicity: usable_date <= evaluation_date
        # If an evidence item's usable_date > evaluation_date, resolver raises error if fed
        # but in normal resolution it is simply not knowable at date day
        trading_days = ["2024-05-01", "2024-11-01"]
        prices = {
            "2024-05-01": HistoricalPriceEvidence(
                price_evidence_id="p-1", issuer_id="TEST", instrument_id="TEST",
                price_date="2024-05-01", close=100.0,
            )
        }
        # Evidence usable on 2024-11-01 must not participate in evaluation on 2024-05-01
        ev_future = QuarterEpsEvidence(
            evidence_id="e-future", issuer_id="TEST", evidence_class=EVIDENCE_CLASS_FILED,
            form="10-Q", accession="fut", period_end="2024-09-30", fiscal_year=2024,
            fiscal_quarter=4, value=2.0, audit_status=AUDIT_STATUS_REVIEWED,
            acceptance_datetime="2024-10-31T15:00:00-04:00", usable_date="2024-11-01",
            usable_date_rule="rule",
        )
        res = build_historical_pe(
            issuer_id="TEST",
            instrument_id="TEST",
            quarter_evidence=[ev_future],
            annual_evidence=[],
            prices=prices,
            fye_month=12,
            trading_days=trading_days,
            evaluation_dates=["2024-05-01"],
        )
        self.assertEqual(res.observations[0].status, STATUS_UNAVAILABLE)
        self.assertEqual(len(res.observations[0].eps_state["components"]), 0)

    def test_f11_reason_codes_in_closed_enumeration(self):
        for code in CLOSED_REASON_CODES:
            self.assertTrue(code.startswith("REASON_"))
        # Invalid code raises ValueError in post_init
        with self.assertRaises(ValueError):
            HistoricalPeObservation(
                observation_id="test",
                issuer_id="TEST",
                instrument_id="TEST",
                metric_id=METRIC_TTM_GAAP_DILUTED_PE,
                evaluation_date="2024-10-01",
                evaluation_date_is_trading_day=True,
                status=STATUS_UNAVAILABLE,
                reason_code="INVALID_REASON_CODE",
                reason_detail="Invalid",
                value=None,
                unit="multiple",
                currency=None,
                eps_state={},
                price_state={},
                pe_state={},
                source_lineage={},
            )

    def test_f13_determinism_identical_content_hash(self):
        # Two identical runs produce identical content hashes
        res1 = load_aapl_historical_pe(enable_furnished=True)
        res2 = load_aapl_historical_pe(enable_furnished=True)
        self.assertEqual(res1.content_hash, res2.content_hash)
        self.assertEqual(
            res1.distribution.percentiles["median"],
            res2.distribution.percentiles["median"],
        )


class TestSufficiencyGate(unittest.TestCase):
    """Test ADR Decision 9 & CONTRACT §K.1/§K.2: >= 20 observations gate."""

    def test_fewer_than_20_observations_refuses_reference_distribution(self):
        # 15 observations (< 20)
        observations = [
            HistoricalPeObservation(
                observation_id=f"obs-{i}",
                issuer_id="TEST",
                instrument_id="TEST",
                metric_id=METRIC_TTM_GAAP_DILUTED_PE,
                evaluation_date=f"2020-0{i % 9 + 1}-01",
                evaluation_date_is_trading_day=True,
                status=STATUS_AVAILABLE,
                reason_code=None,
                reason_detail=None,
                value=20.0 + i,
                unit="multiple",
                currency=None,
                eps_state={},
                price_state={},
                pe_state={},
                source_lineage={},
            )
            for i in range(15)
        ]
        dist = compute_historical_pe_distribution(observations, min_observations=20)
        self.assertEqual(dist.status, STATUS_INSUFFICIENT_OBSERVATIONS)
        self.assertFalse(dist.usable_for_reference)
        self.assertEqual(dist.sample_count, 15)
        self.assertIsNotNone(dist.percentiles.get("median"))  # Descriptive stats present
        self.assertEqual(dist.reason_code, REASON_INSUFFICIENT_OBSERVATIONS)

        # Scenarios generator must refuse it
        multiples, unavail = exit_multiples_from_production_distribution(dist.to_dict(), min_observations=20)
        self.assertEqual(len(multiples), 0)
        self.assertEqual(len(unavail), 1)
        self.assertEqual(unavail[0]["reason_kind"], "INSUFFICIENT_OBSERVATIONS")

    def test_20_or_more_observations_qualifies_as_reference_distribution(self):
        observations = [
            HistoricalPeObservation(
                observation_id=f"obs-{i}",
                issuer_id="TEST",
                instrument_id="TEST",
                metric_id=METRIC_TTM_GAAP_DILUTED_PE,
                evaluation_date=f"2020-0{i % 9 + 1}-01",
                evaluation_date_is_trading_day=True,
                status=STATUS_AVAILABLE,
                reason_code=None,
                reason_detail=None,
                value=20.0 + i,
                unit="multiple",
                currency=None,
                eps_state={},
                price_state={},
                pe_state={},
                source_lineage={},
            )
            for i in range(25)
        ]
        dist = compute_historical_pe_distribution(observations, min_observations=20)
        self.assertEqual(dist.status, STATUS_USABLE_FOR_REFERENCE)
        self.assertTrue(dist.usable_for_reference)
        self.assertEqual(dist.sample_count, 25)
        self.assertIsNone(dist.reason_code)

        multiples, unavail = exit_multiples_from_production_distribution(dist.to_dict(), min_observations=20)
        self.assertEqual(len(multiples), 5)  # 10th, 25th, median, 75th, 90th
        self.assertEqual(len(unavail), 0)
        for m in multiples:
            self.assertEqual(m.source, "production_historical_pe_percentile")
            self.assertEqual(m.sample_size, 25)

    def test_distribution_min_max_agree_with_underlying_observations(self):
        obs_values = [14.5, 18.2, 22.0, 25.5, 28.0, 31.2, 35.8, 39.4] * 3
        observations = [
            HistoricalPeObservation(
                observation_id=f"obs-{i}",
                issuer_id="TEST",
                instrument_id="TEST",
                metric_id=METRIC_TTM_GAAP_DILUTED_PE,
                evaluation_date=f"2020-0{i % 9 + 1}-01",
                evaluation_date_is_trading_day=True,
                status=STATUS_AVAILABLE,
                reason_code=None,
                reason_detail=None,
                value=val,
                unit="multiple",
                currency=None,
                eps_state={},
                price_state={},
                pe_state={},
                source_lineage={},
            )
            for i, val in enumerate(obs_values)
        ]
        dist = compute_historical_pe_distribution(observations, min_observations=20)
        self.assertEqual(dist.min, min(obs_values))
        self.assertEqual(dist.max, max(obs_values))



class TestAaplEndToEndAndNegativePath(unittest.TestCase):
    """AAPL real dataset end-to-end and negative-path verification."""

    def test_aapl_with_furnished_enabled_produces_31_valid_observations(self):
        res = load_aapl_historical_pe(enable_furnished=True)
        self.assertEqual(res.distribution.sample_count, 31)
        self.assertEqual(len(res.observations), 31)
        self.assertEqual(res.distribution.status, STATUS_USABLE_FOR_REFERENCE)
        self.assertTrue(res.distribution.usable_for_reference)

        # Median around 28.95
        median = res.distribution.percentiles.get("median")
        self.assertIsNotNone(median)
        self.assertAlmostEqual(median, 28.948598, places=4)

        # 0 excluded
        self.assertEqual(len(res.distribution.excluded_observations), 0)

    def test_aapl_distribution_min_max_agree_with_eligible_observations(self):
        res = load_aapl_historical_pe(enable_furnished=True)
        dist = res.distribution
        self.assertEqual(dist.status, STATUS_USABLE_FOR_REFERENCE)
        self.assertTrue(dist.usable_for_reference)

        eligible_values = [o.value for o in res.observations if o.value is not None and o.status == STATUS_AVAILABLE]
        self.assertEqual(len(eligible_values), 31)

        expected_min = min(eligible_values)
        expected_max = max(eligible_values)

        # Reported min and max must strictly equal the min and max of underlying eligible observations
        self.assertEqual(dist.min, expected_min)
        self.assertEqual(dist.max, expected_max)

        # Audited canonical values for AAPL: 13.6875 to 37.4603
        self.assertAlmostEqual(dist.min, 13.6875, places=4)
        self.assertAlmostEqual(dist.max, 37.460317, places=4)


    def test_aapl_with_furnished_disabled_negative_path(self):
        # Negative path per CONTRACT §I.3: Disabling furnished path reproduces 12 valid, 19 missing Q4
        res = load_aapl_historical_pe(enable_furnished=False)
        self.assertEqual(res.distribution.sample_count, 12)
        self.assertEqual(len(res.observations), 31)
        self.assertEqual(res.distribution.status, STATUS_INSUFFICIENT_OBSERVATIONS)
        self.assertFalse(res.distribution.usable_for_reference)

        # Exactly 19 excluded, all with REASON_MISSING_Q4_EPS
        excluded = res.distribution.excluded_observations
        self.assertEqual(len(excluded), 19)
        for item in excluded:
            self.assertEqual(item["reason_code"], REASON_MISSING_Q4_EPS)

    def test_aapl_runner_wiring_generates_multi_multiple_matrix(self):
        # Test full runner invocation
        res = run_st_eva(
            "AAPL",
            mode="regression",
            include_historical_pe=True,
            render_dossier_report=True,
            save_snapshot=False,
        )
        self.assertIsNotNone(res)
        self.assertIn("production_historical_pe", res)
        prod_pe = res["production_historical_pe"]
        self.assertEqual(prod_pe["distribution"]["status"], STATUS_USABLE_FOR_REFERENCE)

        # Reverse requirements matrix should carry 80 scenarios (4 horizons * 4 returns * 5 multiples)
        matrix = res["reverse_requirements"]["reverse_requirements_matrix"]
        self.assertEqual(len(matrix), 80)
        multiples_sources = {row["exit_multiple"]["source"] for row in matrix}
        self.assertIn("production_historical_pe_percentile", multiples_sources)

        # Dossier should contain the production historical P/E block
        dossier = build_dossier(res)
        metrics_sec = dossier["sections"]["valuation_metrics"]
        self.assertIn("production_historical_pe", metrics_sec)

        rendered_text = render_dossier(dossier)
        self.assertIn("PRODUCTION PIT HISTORICAL P/E", rendered_text)
        self.assertIn("USABLE_FOR_REFERENCE", rendered_text)
        self.assertIn("28.95", rendered_text)


if __name__ == "__main__":
    unittest.main()
