"""
Regression tests for the point-in-time historical P/FCF pipeline.

The pipeline rebuilds a historical market-cap-to-free-cash-flow distribution
from filed SEC cash-flow statements, the canonical daily price series, and
cover-page shares outstanding -- with no vendor P/FCF band. These tests pin:

* the quarterly conversion of cumulative YTD cash-flow statements (Q2 = 6M -
  Q1, Q3 = 9M - 6M, Q4 = FY - 9M), so a cumulative duration is never summed
  as if it were a single quarter;
* point-in-time knowability: a fact is never used before its filing's usable
  date, a derived quarter is never knowable before both of its inputs, and a
  restatement takes over only on its own usable date;
* the TTM window rule (four consecutive fiscal quarters containing a Q4, no
  rollback, no synthesis);
* the multiple's units (as-traded close x actual cover-page shares, all USD,
  split-consistent across the 2020 4:1 boundary);
* every refusal: non-positive FCF, missing inputs, incomplete windows;
* the reference gate (>= 20, never relaxed) and the summary-engine
  precedence (user > production distribution > vendor band);
* the promoted AAPL dataset's real result, which is the only place the
  reference's actual usability is judged.
"""
from __future__ import annotations

import datetime
import json
import sys
import unittest

sys.path.insert(0, ".")

from historical_pe import MIN_OBSERVATIONS_FOR_REFERENCE
from historical_pfcf import (
    ISSUER_CONFIGS,
    REASON_INSUFFICIENT_QUARTERS,
    REASON_MISSING_PRICE,
    REASON_MISSING_SHARES,
    REASON_NON_POSITIVE_FCF,
    STATUS_AVAILABLE,
    STATUS_INSUFFICIENT_OBSERVATIONS,
    STATUS_UNAVAILABLE,
    STATUS_USABLE_FOR_REFERENCE,
    CashFlowSpanEvidence,
    HistoricalPfcfObservation,
    ShareCountEvidence,
    build_historical_pfcf,
    compute_historical_pfcf_distribution,
    derive_discrete_quarters_at,
    load_aapl_historical_pfcf,
    production_pfcf_summary,
    ttm_fcf_window_at,
)
from st_eva_runner import MarketImpliedAssumptionsEngine, production_pfcf_for_reference


# ---------------------------------------------------------------------------
# Synthetic evidence builders
# ---------------------------------------------------------------------------

_SPAN_SEQ = iter(range(1, 10_000))


def ocf_span(
    start,
    end,
    value,
    usable_date,
    accession=None,
    form="10-Q",
):
    """One operating-cash-flow span version, as one filing stated it."""
    start_d = datetime.date.fromisoformat(start)
    end_d = datetime.date.fromisoformat(end)
    return CashFlowSpanEvidence(
        evidence_id=f"cf-{next(_SPAN_SEQ)}",
        issuer_id="CIKTEST",
        concept_tag="NetCashProvidedByUsedInOperatingActivities",
        role="operating_cash_flow",
        start=start,
        end=end,
        duration_days=(end_d - start_d).days,
        value=value,
        accession=accession or f"000TEST-{next(_SPAN_SEQ):06d}",
        form=form,
        acceptance_datetime=f"{usable_date}T10:00:00-04:00",
        usable_date=usable_date,
        usable_date_rule="acceptance_before_1600ET_same_day",
        filed_date=usable_date,
        source_url="https://data.sec.gov/api/xbrl/companyconcept/test",
        content_sha256="test",
    )


def capex_span(start, end, value, usable_date, accession=None, form="10-Q"):
    start_d = datetime.date.fromisoformat(start)
    end_d = datetime.date.fromisoformat(end)
    return CashFlowSpanEvidence(
        evidence_id=f"cf-{next(_SPAN_SEQ)}",
        issuer_id="CIKTEST",
        concept_tag="PaymentsToAcquirePropertyPlantAndEquipment",
        role="capital_expenditure",
        start=start,
        end=end,
        duration_days=(end_d - start_d).days,
        value=value,
        accession=accession or f"000TEST-{next(_SPAN_SEQ):06d}",
        form=form,
        acceptance_datetime=f"{usable_date}T10:00:00-04:00",
        usable_date=usable_date,
        usable_date_rule="acceptance_before_1600ET_same_day",
        filed_date=usable_date,
        source_url="https://data.sec.gov/api/xbrl/companyconcept/test",
        content_sha256="test",
    )


def share_fact(shares, as_of_date, usable_date):
    return ShareCountEvidence(
        evidence_id=f"shares-{next(_SPAN_SEQ)}",
        issuer_id="CIKTEST",
        shares=shares,
        as_of_date=as_of_date,
        accession=f"000TEST-{next(_SPAN_SEQ):06d}",
        form="10-Q",
        usable_date=usable_date,
        usable_date_rule="acceptance_before_1600ET_same_day",
        source_url="https://data.sec.gov/api/xbrl/companyconcept/test",
        content_sha256="test",
    )


def _quarters_for_fy2020(fye_month=12):
    """
    One complete fiscal year of cash-flow spans on a December fiscal calendar.

    Cumulative YTD durations, exactly as a 10-Q series states them:
    Q1 (3 months), 6M, 9M, FY. The discrete quarters are derived, never
    stated, which is the whole point of the conversion under test.
    """
    spans = [
        # cumulative operating cash flow: 110, 240, 380, 520
        ocf_span("2020-01-01", "2020-03-31", 110.0, "2020-04-20"),
        ocf_span("2020-01-01", "2020-06-30", 240.0, "2020-07-20"),
        ocf_span("2020-01-01", "2020-09-30", 380.0, "2020-10-20"),
        ocf_span("2020-01-01", "2020-12-31", 520.0, "2021-01-20", form="10-K"),
        # cumulative capital expenditure: 10, 25, 40, 60
        capex_span("2020-01-01", "2020-03-31", 10.0, "2020-04-20"),
        capex_span("2020-01-01", "2020-06-30", 25.0, "2020-07-20"),
        capex_span("2020-01-01", "2020-09-30", 40.0, "2020-10-20"),
        capex_span("2020-01-01", "2020-12-31", 60.0, "2021-01-20", form="10-K"),
    ]
    return spans


def _in_force_all(spans, day="2030-01-01"):
    by_key = {}
    for span in spans:
        by_key.setdefault((span.role, span.start, span.end), []).append(span)
    in_force = {}
    for key, versions in by_key.items():
        usable = [v for v in versions if v.usable_date <= day]
        if usable:
            in_force[key] = sorted(usable, key=lambda v: v.usable_date)[-1]
    return in_force


class TestCumulativeToDiscreteConversion(unittest.TestCase):
    """M-2: discrete quarters are differences, never summed cumulatives."""

    def test_each_quarter_is_the_difference_of_its_cumulative_spans(self):
        quarters = derive_discrete_quarters_at(
            spans_in_force=_in_force_all(_quarters_for_fy2020()),
            ocf_role="operating_cash_flow",
            capex_role="capital_expenditure",
            fye_month=12,
            evaluation_date="2030-01-01",
            issuer_id="CIKTEST",
        )
        self.assertEqual(len(quarters), 4)
        expected = {
            # (fiscal_year, quarter): (ocf, capex, fcf)
            (2020, 1): (110.0, 10.0, 100.0),
            (2020, 2): (130.0, 15.0, 115.0),   # 240-110, 25-10
            (2020, 3): (140.0, 15.0, 125.0),   # 380-240, 40-25
            (2020, 4): (140.0, 20.0, 120.0),   # 520-380, 60-40
        }
        for end, quarter in quarters.items():
            with self.subTest(period_end=end):
                key = (quarter["fiscal_year"], quarter["fiscal_quarter"])
                ocf, capex, fcf = expected[key]
                self.assertEqual(quarter["operating_cash_flow"], ocf)
                self.assertEqual(quarter["capital_expenditure"], capex)
                self.assertEqual(quarter["free_cash_flow"], fcf)
                self.assertEqual(quarter["formula"], "operating cash flow - capital expenditure")

    def test_capex_is_subtracted_because_the_tag_is_a_payment_magnitude(self):
        # M-1: the raw tag values are positive magnitudes; FCF = OCF - capex.
        quarters = derive_discrete_quarters_at(
            spans_in_force=_in_force_all(_quarters_for_fy2020()),
            ocf_role="operating_cash_flow",
            capex_role="capital_expenditure",
            fye_month=12,
            evaluation_date="2030-01-01",
            issuer_id="CIKTEST",
        )
        q1 = quarters[datetime.date(2020, 3, 31)]
        self.assertEqual(q1["free_cash_flow"], 100.0)
        self.assertLess(q1["free_cash_flow"], q1["operating_cash_flow"])

    def test_a_quarter_missing_in_one_concept_stays_absent_not_zero(self):
        # Only OCF states the year; without the capex spans the quarters'
        # free cash flow is absent, never computed from one concept alone.
        spans = [s for s in _quarters_for_fy2020() if s.role == "operating_cash_flow"]
        quarters = derive_discrete_quarters_at(
            spans_in_force=_in_force_all(spans),
            ocf_role="operating_cash_flow",
            capex_role="capital_expenditure",
            fye_month=12,
            evaluation_date="2030-01-01",
            issuer_id="CIKTEST",
        )
        self.assertEqual(quarters, {})

    def test_cumulative_values_are_never_treated_as_single_quarters(self):
        # If the 6M span were (wrongly) read as a single quarter, Q2 would
        # carry 240 instead of the derived 130. The derived value pins the
        # differencing.
        quarters = derive_discrete_quarters_at(
            spans_in_force=_in_force_all(_quarters_for_fy2020()),
            ocf_role="operating_cash_flow",
            capex_role="capital_expenditure",
            fye_month=12,
            evaluation_date="2030-01-01",
            issuer_id="CIKTEST",
        )
        self.assertNotEqual(
            quarters[datetime.date(2020, 6, 30)]["operating_cash_flow"], 240.0
        )

    def test_a_cumulative_span_without_a_predecessor_yields_no_quarter(self):
        # The 6M span alone (its Q1 predecessor absent from the data) cannot
        # produce Q2, and nothing else about it is invented.
        spans = [
            ocf_span("2020-01-01", "2020-06-30", 240.0, "2020-07-20"),
            capex_span("2020-01-01", "2020-06-30", 25.0, "2020-07-20"),
        ]
        quarters = derive_discrete_quarters_at(
            spans_in_force=_in_force_all(spans),
            ocf_role="operating_cash_flow",
            capex_role="capital_expenditure",
            fye_month=12,
            evaluation_date="2030-01-01",
            issuer_id="CIKTEST",
        )
        self.assertEqual(quarters, {})

    def test_a_quarter_derived_from_spans_is_bound_to_both_inputs(self):
        quarters = derive_discrete_quarters_at(
            spans_in_force=_in_force_all(_quarters_for_fy2020()),
            ocf_role="operating_cash_flow",
            capex_role="capital_expenditure",
            fye_month=12,
            evaluation_date="2030-01-01",
            issuer_id="CIKTEST",
        )
        q2 = quarters[datetime.date(2020, 6, 30)]
        self.assertEqual(len(q2["operating_cash_flow_inputs"]), 2)
        self.assertEqual(len(q2["capital_expenditure_inputs"]), 2)
        self.assertIn("cumulative difference", q2["operating_cash_flow_derivation"])


class TestPointInTimeKnowability(unittest.TestCase):
    """M-3: nothing is used before it was knowable; versions supersede."""

    def test_a_quarter_is_not_knowable_before_its_own_filing(self):
        # The FY span (Q4's input) is filed with the 10-K on 2021-01-20.
        quarters_early = derive_discrete_quarters_at(
            spans_in_force=_in_force_all(_quarters_for_fy2020(), day="2020-12-31"),
            ocf_role="operating_cash_flow",
            capex_role="capital_expenditure",
            fye_month=12,
            evaluation_date="2020-12-31",
            issuer_id="CIKTEST",
        )
        self.assertNotIn(datetime.date(2020, 12, 31), quarters_early)
        quarters_late = derive_discrete_quarters_at(
            spans_in_force=_in_force_all(_quarters_for_fy2020(), day="2021-01-20"),
            ocf_role="operating_cash_flow",
            capex_role="capital_expenditure",
            fye_month=12,
            evaluation_date="2021-01-20",
            issuer_id="CIKTEST",
        )
        self.assertIn(datetime.date(2020, 12, 31), quarters_late)

    def test_a_derived_quarter_is_not_knowable_before_both_inputs(self):
        # Q2's inputs: the 6M span (usable 2020-07-20) and the Q1 span
        # (usable 2020-04-20). The quarter is knowable at the later date.
        spans = [
            ocf_span("2020-01-01", "2020-03-31", 110.0, "2020-04-20"),
            ocf_span("2020-01-01", "2020-06-30", 240.0, "2020-07-20"),
            capex_span("2020-01-01", "2020-03-31", 10.0, "2020-04-20"),
            capex_span("2020-01-01", "2020-06-30", 25.0, "2020-07-20"),
        ]
        quarters = derive_discrete_quarters_at(
            spans_in_force=_in_force_all(spans, day="2020-07-19"),
            ocf_role="operating_cash_flow",
            capex_role="capital_expenditure",
            fye_month=12,
            evaluation_date="2020-07-19",
            issuer_id="CIKTEST",
        )
        self.assertNotIn(datetime.date(2020, 6, 30), quarters)
        quarters = derive_discrete_quarters_at(
            spans_in_force=_in_force_all(spans, day="2020-07-20"),
            ocf_role="operating_cash_flow",
            capex_role="capital_expenditure",
            fye_month=12,
            evaluation_date="2020-07-20",
            issuer_id="CIKTEST",
        )
        self.assertIn(datetime.date(2020, 6, 30), quarters)
        self.assertEqual(quarters[datetime.date(2020, 6, 30)]["knowable_from"], "2020-07-20")

    def test_a_restatement_takes_over_only_on_its_own_usable_date(self):
        # The real ASU 2016-18 case, reduced: the FY2016 operating cash flow
        # is 65,824M as first known, and a later 10-K comparative restates it
        # to 66,231M. Each evaluation date sees the value visible then.
        spans = [
            ocf_span("2015-09-27", "2016-09-24", 65_824_000_000.0, "2017-11-03", form="10-K"),
            ocf_span("2015-09-27", "2016-09-24", 66_231_000_000.0, "2018-11-05", form="10-K"),
            capex_span("2015-09-27", "2016-06-25", 25_479_000_000.0, "2017-08-02"),
            ocf_span("2015-09-27", "2016-06-25", 49_698_000_000.0, "2017-08-02"),
            capex_span("2015-09-27", "2016-09-24", 29_500_000_000.0, "2017-11-03", form="10-K"),
        ]
        before = derive_discrete_quarters_at(
            spans_in_force=_in_force_all(spans, day="2018-11-04"),
            ocf_role="operating_cash_flow",
            capex_role="capital_expenditure",
            fye_month=9,
            evaluation_date="2018-11-04",
            issuer_id="CIKTEST",
        )
        after = derive_discrete_quarters_at(
            spans_in_force=_in_force_all(spans, day="2018-11-05"),
            ocf_role="operating_cash_flow",
            capex_role="capital_expenditure",
            fye_month=9,
            evaluation_date="2018-11-05",
            issuer_id="CIKTEST",
        )
        q4_before = before[datetime.date(2016, 9, 24)]
        q4_after = after[datetime.date(2016, 9, 24)]
        self.assertEqual(
            q4_before["free_cash_flow"],
            (65_824_000_000.0 - 49_698_000_000.0) - (29_500_000_000.0 - 25_479_000_000.0),
        )
        self.assertEqual(
            q4_after["free_cash_flow"],
            (66_231_000_000.0 - 49_698_000_000.0) - (29_500_000_000.0 - 25_479_000_000.0),
        )

    def test_a_fact_outside_the_acceptance_index_is_never_loaded(self):
        # The loader skips a fact whose accession has no acceptance evidence:
        # there is no knowability for it, so it cannot enter the dataset.
        from historical_pfcf import _concept_spans_from_payload

        payload = {
            "units": {
                "USD": [
                    {
                        "start": "2020-01-01",
                        "end": "2020-03-31",
                        "val": 110.0,
                        "accn": "000UNINDEXED",
                        "form": "10-Q",
                        "filed": "2020-04-20",
                    }
                ]
            }
        }
        spans = _concept_spans_from_payload(
            payload=payload,
            unit="USD",
            role="operating_cash_flow",
            concept_tag="test",
            issuer_id="CIKTEST",
            filings_index={},  # nothing is indexed
            content_sha256="x",
        )
        self.assertEqual(spans, [])


class TestTtmWindow(unittest.TestCase):
    """M-4: four consecutive fiscal quarters containing a Q4, no rollback."""

    def _quarters(self, fcf_by_end, knowable=None):
        quarters = {}
        for end, fcf in fcf_by_end.items():
            end_d = datetime.date.fromisoformat(end)
            quarters[end_d] = {
                "fiscal_year": end_d.year,
                "fiscal_quarter": ((end_d.month - 1) // 3) or 4,
                "period_end": end,
                "free_cash_flow": fcf,
                "knowable_from": (knowable or {}).get(end, "2000-01-01"),
            }
        return quarters

    def test_a_complete_window_sums_its_four_quarters(self):
        quarters = self._quarters(
            {
                "2019-12-31": 100.0,
                "2020-03-31": 110.0,
                "2020-06-30": 120.0,
                "2020-09-30": 130.0,
            }
        )
        window, reason, _ = ttm_fcf_window_at(quarters=quarters, day="2020-10-01", fye_month=12)
        self.assertIsNone(reason)
        self.assertEqual(window["total_free_cash_flow"], 460.0)
        self.assertEqual(window["anchor"]["fiscal_quarter"], 3)
        self.assertEqual(
            [p["fiscal_quarter"] for p in window["positions"]], [4, 1, 2, 3]
        )

    def test_a_missing_position_refuses_the_window_without_a_rollback(self):
        # Q4 FY2019 is missing, so the window anchored at Q3 FY2020 cannot be
        # completed. The pipeline refuses; it does not silently anchor one
        # quarter earlier.
        quarters = self._quarters(
            {
                "2020-03-31": 110.0,
                "2020-06-30": 120.0,
                "2020-09-30": 130.0,
            }
        )
        window, reason, _ = ttm_fcf_window_at(quarters=quarters, day="2020-10-01", fye_month=12)
        self.assertIsNone(window)
        self.assertEqual(reason, REASON_INSUFFICIENT_QUARTERS)

    def test_a_quarter_not_yet_knowable_is_missing_for_that_date(self):
        quarters = self._quarters(
            {
                "2019-12-31": 100.0,
                "2020-03-31": 110.0,
                "2020-06-30": 120.0,
                "2020-09-30": 130.0,
            },
            knowable={"2020-09-30": "2020-10-20"},
        )
        window, reason, _ = ttm_fcf_window_at(quarters=quarters, day="2020-10-19", fye_month=12)
        self.assertIsNone(window)
        self.assertEqual(reason, REASON_INSUFFICIENT_QUARTERS)
        window, reason, _ = ttm_fcf_window_at(quarters=quarters, day="2020-10-20", fye_month=12)
        self.assertIsNone(reason)
        self.assertEqual(window["total_free_cash_flow"], 460.0)


class TestMultipleUnitsAndSplitConsistency(unittest.TestCase):
    """M-5: the numerator is as-traded close times actual cover-page shares."""

    def _spans_for_two_years(self):
        spans = _quarters_for_fy2020()
        spans += [
            ocf_span("2021-01-01", "2021-03-31", 115.0, "2021-04-20"),
            capex_span("2021-01-01", "2021-03-31", 12.0, "2021-04-20"),
        ]
        return spans

    def test_the_multiple_recomputes_from_the_recorded_inputs(self):
        prices = {
            "2021-01-20": {"close": 100.0, "currency": "USD", "accounting_basis": "as_traded"},
            "2021-04-20": {"close": 110.0, "currency": "USD", "accounting_basis": "as_traded"},
        }
        shares = [share_fact(1_000_000.0, "2020-12-15", "2021-01-20")]
        result = build_historical_pfcf(
            issuer_id="CIKTEST",
            instrument_id="TEST",
            cash_flow_spans=self._spans_for_two_years(),
            share_counts=shares,
            prices=prices,
            fye_month=12,
            evaluation_dates=["2021-01-20", "2021-04-20"],
            min_observations=MIN_OBSERVATIONS_FOR_REFERENCE,
        )
        by_date = {obs.evaluation_date: obs for obs in result.observations}
        first = by_date["2021-01-20"]
        # TTM = 100+115+125+120 (Q4 FY2020 + first three quarters of the
        # window the anchor dictates) -- recomputed from the observation's
        # own window payload, independently of the published multiple.
        self.assertEqual(first.status, STATUS_AVAILABLE)
        window_total = sum(q["free_cash_flow"] for q in first.ttm_window["quarters"])
        expected = first.price * first.shares_outstanding / window_total
        self.assertAlmostEqual(first.value, expected, places=5)
        self.assertEqual(first.price_currency, "USD")
        self.assertEqual(first.ttm_free_cash_flow_currency, "USD")

    def test_split_boundary_keeps_price_and_shares_on_one_basis(self):
        # A 4:1 split between the two evaluations: the pre-split date pairs a
        # pre-split close with a pre-split cover count, the post-split date a
        # post-split close with a post-split count, so the multiple tracks
        # value, not the split.
        prices = {
            "2020-07-31": {"close": 400.0, "currency": "USD", "accounting_basis": "as_traded"},
            "2020-09-01": {"close": 100.0, "currency": "USD", "accounting_basis": "as_traded"},
        }
        shares = [
            share_fact(1_000_000_000.0, "2020-07-15", "2020-07-31"),
            share_fact(4_000_000_000.0, "2020-08-20", "2020-09-01"),
        ]
        result = build_historical_pfcf(
            issuer_id="CIKTEST",
            instrument_id="TEST",
            cash_flow_spans=self._spans_for_two_years(),
            share_counts=shares,
            prices=prices,
            fye_month=12,
            evaluation_dates=["2020-07-31", "2020-09-01"],
            min_observations=MIN_OBSERVATIONS_FOR_REFERENCE,
        )
        by_date = {obs.evaluation_date: obs for obs in result.observations}
        pre, post = by_date["2020-07-31"], by_date["2020-09-01"]
        self.assertEqual(pre.shares_outstanding, 1_000_000_000.0)
        self.assertEqual(post.shares_outstanding, 4_000_000_000.0)
        # The TTM windows are the same, so the multiples must agree.
        self.assertAlmostEqual(pre.value, post.value, places=9)
        self.assertAlmostEqual(pre.market_cap, post.market_cap, places=6)


class TestRefusals(unittest.TestCase):
    """Zero, negative and missing inputs never produce a multiple."""

    def _positive_spans(self):
        return _quarters_for_fy2020()

    def _evaluate(self, *, spans, shares, prices, day="2021-01-20"):
        result = build_historical_pfcf(
            issuer_id="CIKTEST",
            instrument_id="TEST",
            cash_flow_spans=spans,
            share_counts=shares,
            prices=prices,
            fye_month=12,
            evaluation_dates=[day],
            min_observations=MIN_OBSERVATIONS_FOR_REFERENCE,
        )
        return result.observations[0]

    def test_zero_ttm_fcf_produces_no_multiple(self):
        spans = [
            ocf_span("2020-01-01", "2020-03-31", 10.0, "2020-04-20"),
            capex_span("2020-01-01", "2020-03-31", 10.0, "2020-04-20"),
            # three more quarters so the window completes at zero total
            ocf_span("2020-01-01", "2020-06-30", 20.0, "2020-07-20"),
            capex_span("2020-01-01", "2020-06-30", 20.0, "2020-07-20"),
            ocf_span("2020-01-01", "2020-09-30", 30.0, "2020-10-20"),
            capex_span("2020-01-01", "2020-09-30", 30.0, "2020-10-20"),
            ocf_span("2020-01-01", "2020-12-31", 40.0, "2021-01-20", form="10-K"),
            capex_span("2020-01-01", "2020-12-31", 40.0, "2021-01-20", form="10-K"),
        ]
        observation = self._evaluate(
            spans=spans,
            shares=[share_fact(1_000.0, "2020-12-15", "2021-01-20")],
            prices={"2021-01-20": {"close": 50.0, "currency": "USD"}},
        )
        self.assertEqual(observation.status, STATUS_UNAVAILABLE)
        self.assertEqual(observation.reason_code, REASON_NON_POSITIVE_FCF)
        self.assertIsNone(observation.value)

    def test_negative_ttm_fcf_produces_no_multiple(self):
        spans = [
            ocf_span("2020-01-01", "2020-03-31", 5.0, "2020-04-20"),
            capex_span("2020-01-01", "2020-03-31", 50.0, "2020-04-20"),
            ocf_span("2020-01-01", "2020-06-30", 10.0, "2020-07-20"),
            capex_span("2020-01-01", "2020-06-30", 60.0, "2020-07-20"),
            ocf_span("2020-01-01", "2020-09-30", 15.0, "2020-10-20"),
            capex_span("2020-01-01", "2020-09-30", 70.0, "2020-10-20"),
            ocf_span("2020-01-01", "2020-12-31", 20.0, "2021-01-20", form="10-K"),
            capex_span("2020-01-01", "2020-12-31", 80.0, "2021-01-20", form="10-K"),
        ]
        observation = self._evaluate(
            spans=spans,
            shares=[share_fact(1_000.0, "2020-12-15", "2021-01-20")],
            prices={"2021-01-20": {"close": 50.0, "currency": "USD"}},
        )
        self.assertEqual(observation.reason_code, REASON_NON_POSITIVE_FCF)
        self.assertLess(observation.ttm_free_cash_flow, 0)
        self.assertIsNone(observation.value)

    def test_a_missing_price_is_a_closed_reason(self):
        observation = self._evaluate(
            spans=self._positive_spans(),
            shares=[share_fact(1_000.0, "2020-12-15", "2021-01-20")],
            prices={},
        )
        self.assertEqual(observation.reason_code, REASON_MISSING_PRICE)
        self.assertIsNone(observation.value)

    def test_missing_shares_is_a_closed_reason(self):
        observation = self._evaluate(
            spans=self._positive_spans(),
            shares=[],
            prices={"2021-01-20": {"close": 50.0, "currency": "USD"}},
        )
        self.assertEqual(observation.reason_code, REASON_MISSING_SHARES)
        self.assertIsNone(observation.value)

    def test_reason_codes_stay_in_the_closed_set(self):
        from historical_pfcf import CLOSED_REASON_CODES

        for code in (
            REASON_MISSING_PRICE,
            REASON_MISSING_SHARES,
            REASON_INSUFFICIENT_QUARTERS,
            REASON_NON_POSITIVE_FCF,
        ):
            self.assertIn(code, CLOSED_REASON_CODES)
        with self.assertRaises(ValueError):
            HistoricalPfcfObservation(
                observation_id="x",
                issuer_id="i",
                instrument_id="t",
                evaluation_date="2020-01-01",
                status=STATUS_UNAVAILABLE,
                reason_code="REASON_NOT_IN_THE_SET",
            )


class TestDistributionAndGate(unittest.TestCase):
    """M-7: the >= 20 gate, the sample counts, and the excluded records."""

    def _observations(self, valid_values, invalid_count=0):
        observations = []
        for index, value in enumerate(valid_values):
            observations.append(
                HistoricalPfcfObservation(
                    observation_id=f"obs-{index}",
                    issuer_id="CIKTEST",
                    instrument_id="TEST",
                    evaluation_date=f"2020-01-{index + 1:02d}",
                    status=STATUS_AVAILABLE,
                    value=value,
                    price=10.0,
                    shares_outstanding=1.0,
                    market_cap=10.0,
                    ttm_free_cash_flow=1.0,
                    ttm_window={"quarters": []},
                )
            )
        for index in range(invalid_count):
            observations.append(
                HistoricalPfcfObservation(
                    observation_id=f"obs-bad-{index}",
                    issuer_id="CIKTEST",
                    instrument_id="TEST",
                    evaluation_date=f"2019-01-{index + 1:02d}",
                    status=STATUS_UNAVAILABLE,
                    reason_code=REASON_INSUFFICIENT_QUARTERS,
                    reason_detail="window incomplete",
                )
            )
        return observations

    def test_twenty_valid_observations_qualify(self):
        dist = compute_historical_pfcf_distribution(
            self._observations([20.0 + index for index in range(20)])
        )
        self.assertEqual(dist.status, STATUS_USABLE_FOR_REFERENCE)
        self.assertTrue(dist.usable_for_reference)
        self.assertEqual(dist.sample_count, 20)

    def test_nineteen_valid_observations_stay_descriptive(self):
        dist = compute_historical_pfcf_distribution(
            self._observations([20.0 + index for index in range(19)])
        )
        self.assertEqual(dist.status, STATUS_INSUFFICIENT_OBSERVATIONS)
        self.assertFalse(dist.usable_for_reference)
        self.assertEqual(dist.reason_code, "REASON_INSUFFICIENT_OBSERVATIONS")
        self.assertIsNotNone(dist.percentiles.get("median"))

    def test_counts_distinguish_source_evaluations_from_valid_samples(self):
        dist = compute_historical_pfcf_distribution(
            self._observations([20.0 + index for index in range(22)], invalid_count=3)
        )
        self.assertEqual(dist.sample_count, 22)
        self.assertEqual(dist.total_evaluations, 25)
        self.assertEqual(len(dist.excluded_observations), 3)
        for excluded in dist.excluded_observations:
            self.assertEqual(excluded["reason_code"], REASON_INSUFFICIENT_QUARTERS)

    def test_the_gate_threshold_is_the_shared_one_and_not_relaxed(self):
        self.assertEqual(MIN_OBSERVATIONS_FOR_REFERENCE, 20)


class TestSummaryReferencePrecedence(unittest.TestCase):
    """The engine's cash-flow reference rungs, and the context's basis."""

    def _eligible_pfcf(self, median=25.343981):
        return {
            "distribution": {
                "status": STATUS_USABLE_FOR_REFERENCE,
                "usable_for_reference": True,
                "sample_count": 35,
                "total_evaluations": 36,
                "min_observations_required": 20,
                "period_start": "2018-02-02",
                "period_end": "2026-07-31",
                "percentiles": {
                    "10th": 16.081585,
                    "25th": 20.493527,
                    "median": median,
                    "75th": 29.789915,
                    "90th": 31.963623,
                },
            }
        }

    def _inputs(self, pfcf_band=None):
        from data_contract import ValuationInputs

        return ValuationInputs(
            price=333.63,
            currency="USD",
            current_eps=8.72,
            current_market_cap=5_050_000_000_000.0,
            historical_pfcf_band=pfcf_band or {},
        )

    def test_the_gate_reads_the_distribution_s_own_eligibility(self):
        median, status = production_pfcf_for_reference(self._eligible_pfcf())
        self.assertEqual(median, 25.343981)
        self.assertEqual(status, STATUS_USABLE_FOR_REFERENCE)
        self.assertEqual(production_pfcf_for_reference(None), (None, "UNAVAILABLE"))
        self.assertEqual(production_pfcf_for_reference({}), (None, "UNAVAILABLE"))

    def test_an_ineligible_distribution_never_qualifies(self):
        payload = self._eligible_pfcf()
        payload["distribution"]["usable_for_reference"] = False
        payload["distribution"]["status"] = STATUS_INSUFFICIENT_OBSERVATIONS
        median, status = production_pfcf_for_reference(payload)
        self.assertIsNone(median)
        self.assertEqual(status, STATUS_INSUFFICIENT_OBSERVATIONS)

    def test_the_production_median_is_the_cash_flow_reference(self):
        analysis = MarketImpliedAssumptionsEngine.analyze(
            self._inputs(), production_historical_pfcf=self._eligible_pfcf()
        )
        reference = analysis["reference"]
        self.assertEqual(reference["pfcf_method"], "production_historical_pfcf_median")
        self.assertEqual(reference["pfcf_multiple"], 25.343981)
        self.assertEqual(
            reference["production_historical_pfcf_status"], STATUS_USABLE_FOR_REFERENCE
        )
        self.assertEqual(reference["production_historical_pfcf_sample_count"], 35)
        self.assertEqual(
            analysis["implied_assumptions"]["reference_multiples"]["pfcf"], 25.343981
        )

    def test_a_user_supplied_pfcf_keeps_precedence(self):
        analysis = MarketImpliedAssumptionsEngine.analyze(
            self._inputs(),
            pfcf_multiple=12.0,
            production_historical_pfcf=self._eligible_pfcf(),
        )
        self.assertEqual(analysis["reference"]["pfcf_method"], "user_supplied_multiple")
        self.assertEqual(analysis["reference"]["pfcf_multiple"], 12.0)
        self.assertIsNone(analysis["reference"]["production_historical_pfcf_sample_count"])

    def test_without_the_distribution_the_band_fallback_is_unchanged(self):
        band = {"median": 22.0, "observations": 30.0}
        analysis = MarketImpliedAssumptionsEngine.analyze(self._inputs(pfcf_band=band))
        self.assertEqual(analysis["reference"]["pfcf_method"], "historical_pfcf_median")
        self.assertEqual(analysis["reference"]["pfcf_multiple"], 22.0)

    def test_without_anything_the_reference_stays_none(self):
        analysis = MarketImpliedAssumptionsEngine.analyze(self._inputs())
        self.assertEqual(analysis["reference"]["pfcf_method"], "none")
        self.assertIsNone(analysis["reference"]["pfcf_multiple"])


class TestContextRecordsTheProductionBasis(unittest.TestCase):
    """The context never records a production median as a vendor-band median."""

    def _document(self, production_historical_pfcf, pfcf_band=None):
        from st_eva_runner import (
            CompanyResolver,
            DeterministicMetricsEngine,
            build_evidence,
            material_observations,
            metrics_observation,
        )
        from investment_context import build_investment_context

        data = CompanyResolver.resolve("AAPL", mode="regression")
        if pfcf_band is not None:
            data.historical_pfcf_band = dict(pfcf_band)
        metrics = DeterministicMetricsEngine.compute(data.price_history, data.volume_history)
        evidence = build_evidence(data, metrics)
        analysis = MarketImpliedAssumptionsEngine.analyze(
            data, production_historical_pfcf=production_historical_pfcf
        )
        return build_investment_context(
            data=data,
            analysis=analysis,
            evidence=evidence,
            metrics=metrics,
            material_observations=list(material_observations(data).values())
            + [metrics_observation(data, metrics)],
            generated_at="2026-10-15T12:00:00+00:00",
        )

    def test_the_pfcf_reference_names_the_production_basis(self):
        payload = self._eligible_pfcf_payload()
        document = self._document(payload)
        ref = document["provenance"]["refs"]["refc:pfcf_reference"]
        self.assertEqual(ref["basis"], "PRODUCTION_PFCF_MEDIAN")
        self.assertEqual(ref["selection_method"], "production_historical_pfcf_median")
        self.assertEqual(ref["source_statistic"], "median")
        self.assertIsNone(
            ref["source_ref"],
            "a production median is not a band statistic, so it names no band",
        )
        self.assertTrue(ref["eligible_as_reference"])
        self.assertIn("usable_for_reference", ref["eligibility_rule"])
        self.assertEqual(ref["source_observation_count"], 35)

    def test_the_band_fallback_keeps_its_own_basis(self):
        band = {"median": 22.0, "observations": 30.0}
        document = self._document(None, pfcf_band=band)
        ref = document["provenance"]["refs"]["refc:pfcf_reference"]
        self.assertEqual(ref["basis"], "HISTORICAL_MEDIAN")
        self.assertEqual(ref["source_ref"], "obs:ev-pfcf-band-001")

    def _eligible_pfcf_payload(self):
        return {
            "distribution": {
                "status": STATUS_USABLE_FOR_REFERENCE,
                "usable_for_reference": True,
                "sample_count": 35,
                "total_evaluations": 36,
                "min_observations_required": 20,
                "period_start": "2018-02-02",
                "period_end": "2026-07-31",
                "percentiles": {
                    "10th": 16.081585,
                    "25th": 20.493527,
                    "median": 25.343981,
                    "75th": 29.789915,
                    "90th": 31.963623,
                },
            }
        }


class TestPromotedAaplDatasetRealResult(unittest.TestCase):
    """
    The reference's actual usability is judged here, on the real data.

    Everything else in this file uses synthetic fixtures for the boundaries;
    this class reads the promoted dataset and pins what the reconstruction
    actually produced, so a silent change to the data or the rules cannot
    pass unnoticed.
    """

    @classmethod
    def setUpClass(cls):
        cls.result = load_aapl_historical_pfcf()

    def test_the_dataset_directory_and_manifest_are_consistent(self):
        config = ISSUER_CONFIGS["AAPL"]
        manifest = json.loads((config.data_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["ticker"], "AAPL")
        self.assertEqual(manifest["role"], "production")
        files = manifest["provenance"]["files"]
        import hashlib

        for name in (
            "net_cash_operating_concept.json",
            "capex_concept.json",
            "shares_outstanding_concept.json",
        ):
            with self.subTest(file=name):
                path = config.data_dir / name
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                self.assertEqual(files[name]["content_sha256"], digest)

    def test_the_distribution_is_usable_for_reference(self):
        dist = self.result.distribution
        self.assertEqual(dist.status, STATUS_USABLE_FOR_REFERENCE)
        self.assertTrue(dist.usable_for_reference)
        self.assertGreaterEqual(dist.sample_count, MIN_OBSERVATIONS_FOR_REFERENCE)

    def test_the_sample_count_matches_the_source_evaluations(self):
        dist = self.result.distribution
        self.assertEqual(dist.sample_count, 35)
        self.assertEqual(dist.total_evaluations, 36)
        self.assertEqual(len(dist.excluded_observations), 1)
        excluded = dist.excluded_observations[0]
        self.assertEqual(excluded["evaluation_date"], "2018-01-02")
        self.assertEqual(excluded["reason_code"], REASON_INSUFFICIENT_QUARTERS)
        self.assertIn("missing positions", excluded["reason_detail"])

    def test_the_sample_period_matches_the_pe_window(self):
        dist = self.result.distribution
        self.assertEqual(dist.period_start, "2018-02-02")
        self.assertEqual(dist.period_end, "2026-07-31")
        self.assertEqual(dist.sampling_cadence, "PERIODIC_FILING_USABLE_DATES")

    def test_every_valid_observation_recomputes_from_its_recorded_inputs(self):
        for observation in self.result.observations:
            if observation.status != STATUS_AVAILABLE:
                continue
            with self.subTest(date=observation.evaluation_date):
                window_total = sum(
                    quarter["free_cash_flow"]
                    for quarter in observation.ttm_window["quarters"]
                )
                self.assertAlmostEqual(
                    observation.ttm_free_cash_flow, window_total, places=4
                )
                expected = (
                    observation.price
                    * observation.shares_outstanding
                    / window_total
                )
                self.assertAlmostEqual(observation.value, expected, places=6)
                self.assertEqual(observation.price_currency, "USD")
                self.assertEqual(observation.ttm_free_cash_flow_currency, "USD")
                # every quarter names the accessions it was built from
                for quarter in observation.ttm_window["quarters"]:
                    self.assertTrue(quarter["operating_cash_flow_inputs"])
                    self.assertTrue(quarter["capital_expenditure_inputs"])

    def test_the_window_positions_are_four_consecutive_quarters_with_a_q4(self):
        for observation in self.result.observations:
            if observation.status != STATUS_AVAILABLE:
                continue
            with self.subTest(date=observation.evaluation_date):
                positions = observation.ttm_window["positions"]
                self.assertEqual(len(positions), 4)
                self.assertIn(4, [p["fiscal_quarter"] for p in positions])
                # consecutive walk: each step is either the next quarter or
                # the first quarter of the next fiscal year
                for index in range(1, 4):
                    previous, current = positions[index - 1], positions[index]
                    expected_next_quarter = previous["fiscal_quarter"] % 4 + 1
                    expected_next_year = previous["fiscal_year"] + (
                        1 if expected_next_quarter == 1 else 0
                    )
                    self.assertEqual(current["fiscal_quarter"], expected_next_quarter)
                    self.assertEqual(current["fiscal_year"], expected_next_year)

    def test_the_2020_split_boundary_is_split_consistent(self):
        by_date = {obs.evaluation_date: obs for obs in self.result.observations}
        pre = by_date["2020-07-31"]
        post = by_date["2020-10-30"]
        # Pre-split: a pre-split close with a pre-split cover count.
        self.assertGreater(pre.price, 100.0)
        self.assertAlmostEqual(pre.shares_outstanding, 4_275_634_000.0, places=0)
        # Post-split: a post-split close with a post-split cover count.
        self.assertLess(post.price, 200.0)
        self.assertAlmostEqual(post.shares_outstanding, 17_001_802_000.0, places=0)
        # Mixing bases would jump the market cap by the 4x split factor: a
        # pre-split close times a post-split count (or the reverse) lands
        # four times away from the true value. The two adjacent quarters'
        # market caps continue across the boundary instead.
        ratio = pre.market_cap / post.market_cap
        self.assertGreater(ratio, 0.5)
        self.assertLess(ratio, 2.0)

    def test_the_percentiles_are_the_distribution_s_own(self):
        dist = self.result.distribution
        values = sorted(obs.value for obs in self.result.observations if obs.status == STATUS_AVAILABLE)
        self.assertAlmostEqual(dist.percentiles["median"], values[len(values) // 2], places=6)
        self.assertAlmostEqual(dist.min, min(values), places=6)
        self.assertAlmostEqual(dist.max, max(values), places=6)

    def test_the_current_snapshot_is_the_latest_trading_day(self):
        snapshot = self.result.current_snapshot
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.role, "current_snapshot")
        self.assertEqual(snapshot.evaluation_date, "2026-10-06")
        self.assertEqual(snapshot.status, STATUS_AVAILABLE)
        # The snapshot never enters the distribution sample.
        self.assertEqual(self.result.distribution.total_evaluations, 36)

    def test_the_input_set_id_digests_every_input(self):
        from historical_pe import canonical_json_hash

        config = ISSUER_CONFIGS["AAPL"]
        import hashlib

        expected_manifest = {
            "issuer_config": {
                "ticker": config.ticker,
                "issuer_id": config.issuer_id,
                "fye_month": config.fye_month,
            },
            "prices": hashlib.sha256(config.prices_path.read_bytes()).hexdigest(),
            "acceptances": hashlib.sha256(config.acceptance_path.read_bytes()).hexdigest(),
            "operating_cash_flow_concept": hashlib.sha256(
                (config.data_dir / "net_cash_operating_concept.json").read_bytes()
            ).hexdigest(),
            "capital_expenditure_concept": hashlib.sha256(
                (config.data_dir / "capex_concept.json").read_bytes()
            ).hexdigest(),
            "shares_outstanding_concept": hashlib.sha256(
                (config.data_dir / "shares_outstanding_concept.json").read_bytes()
            ).hexdigest(),
            "min_observations": MIN_OBSERVATIONS_FOR_REFERENCE,
        }
        self.assertEqual(
            self.result.input_set_id, canonical_json_hash(expected_manifest)
        )

    def test_the_payload_serializes_to_json_and_back(self):
        blob = json.dumps(self.result.to_dict())
        restored = json.loads(blob)
        self.assertEqual(
            restored["distribution"]["sample_count"],
            self.result.distribution.sample_count,
        )
        self.assertEqual(restored["input_set_id"], self.result.input_set_id)

    def test_the_summary_reports_the_same_gate(self):
        summary = production_pfcf_summary(self.result.to_dict())
        self.assertEqual(summary["status"], STATUS_USABLE_FOR_REFERENCE)
        self.assertTrue(summary["usable_for_reference"])
        self.assertEqual(summary["sample_count"], 35)
        self.assertEqual(summary["metric_id"], "TTM_MARKET_CAP_TO_FCF")
        self.assertEqual(summary["excluded_observation_count"], 1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
