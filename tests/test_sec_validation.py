"""
ST-EVA 2.3-B tests.

Two kinds of test live here, and the distinction matters.

Offline tests build observations by hand and exercise the comparability policy,
the discrete-fact filter, the trailing constructions, and the point-in-time
selector. They never touch the network, so they are deterministic and fast.

Live tests are skipped unless ST_EVA_LIVE=1. They prove the adapters work
against the real SEC and Yahoo, which is the only way to know the field names
and the shapes have not drifted.

The central guarantee, tested repeatedly and from several angles: a comparison
produces a third object and overwrites nothing.
"""

import inspect
import os
import unittest

from cross_validation import (
    DEFINITION_DIVERGENT_METRICS,
    INDEPENDENCE_NONE,
    PERIOD_ALIGNMENT_WINDOW_DAYS,
    Tolerance,
    cross_validate,
    cross_validate_all,
    cross_validate_metric,
    spec_for,
)
from data_contract import (
    AvailabilityBasis,
    COMPARABLE_METRICS,
    CONTRACT_METRICS,
    METRIC_ASSETS,
    METRIC_CASH,
    METRIC_DEBT,
    METRIC_EPS_DILUTED,
    METRIC_REVENUE,
    METRIC_SHARES_OUTSTANDING,
    METRIC_UNITS,
    Observation,
    ObservationSet,
    SOURCE_SEC,
    SOURCE_YAHOO,
    SourceType,
    Unit,
    ValidationStatus,
    comparable_observation_id,
    contract_vocabulary_is_safe,
    is_comparable_observation,
    validate_observation,
)
from data_contract import (
    QUARTER_MAX_DAYS,
    QUARTER_MIN_DAYS,
    duration_days,
)
from fundamental_provider import YahooFundamentalProvider
from st_eva_runner import run_st_eva
from sec_provider import (
    SECProvider,
    SecFact,
    is_annual,
    is_cumulative,
    is_discrete_period,
    is_quarter,
    normalize_cik,
    xbrl_unit_to_contract_unit,
)

RETRIEVED = "2026-09-28T12:00:00+00:00"


def make_vendor(
    metric: str,
    value: float,
    unit: str = Unit.CURRENCY.value,
    currency: str = "USD",
    as_of: str = "2026-06-30",
    period_start=None,
    period_end=None,
    basis: str = "TRAILING_AGGREGATE",
    period_type: str = "duration",
    available_at: str = None,
) -> Observation:
    return Observation(
        observation_id=comparable_observation_id(
            metric, SOURCE_YAHOO, period=as_of or "undated"
        ),
        metric=metric,
        value=value,
        unit=unit,
        currency=currency,
        currency_basis="REPORTED" if currency else "NOT_APPLICABLE",
        period_start=period_start,
        period_end=period_end,
        as_of=as_of,
        available_at=available_at,
        available_at_basis=(
            AvailabilityBasis.UNDECLARED.value
            if available_at is None
            else AvailabilityBasis.OBSERVATION_INSTANT.value
        ),
        provider="YahooFinance",
        source_type=SourceType.API_LIVE.value,
        source_url="https://query1.finance.yahoo.com/ws/fundamentals-timeseries/",
        definition="vendor observation",
        methodology="Yahoo fundamentals-timeseries trailing field",
        retrieved_at=RETRIEVED,
        raw={
            "yahoo_field": "trailingTotalRevenue",
            "window_published_by_vendor": False,
            "period_type": period_type,
            "vendor_basis": basis,
        },
    )


def make_filing(
    metric: str,
    value: float,
    unit: str = Unit.CURRENCY.value,
    currency: str = "USD",
    period_start: str = "2025-06-29",
    period_end: str = "2026-06-27",
    accession: str = "0000320193-26-000020",
    ttm: bool = False,
    available_at: str = "2026-07-31T10:01:02.000Z",
    extra_raw: dict = None,
) -> Observation:
    raw = {
        "acceptance_datetime": available_at,
        "filing_date": "2026-07-31",
        "report_date": period_end,
        "time_of_day_known": True,
    }
    if ttm:
        # A trailing aggregate is a flow over a window. It declares that, and
        # it keeps the window it spans, which is information the vendor side
        # does not publish.
        raw["derivation"] = "ANNUAL_ROLL_FORWARD"
        raw["constituents"] = []
        raw["span_days"] = 363
        raw["period_type"] = "duration"
    if extra_raw:
        raw.update(extra_raw)
    return Observation(
        observation_id=comparable_observation_id(
            metric, SOURCE_SEC, period="ttm" if ttm else period_end,
            accession=accession,
        ),
        metric=metric,
        value=value,
        unit=unit,
        currency=currency,
        currency_basis="REPORTED" if currency else "NOT_APPLICABLE",
        period_start=period_start,
        period_end=period_end,
        as_of=period_end,
        available_at=available_at,
        available_at_basis=AvailabilityBasis.ACCEPTANCE_DATETIME.value,
        provider="SecEdgar",
        source_type=SourceType.REGULATORY_FILING.value,
        source_url="https://data.sec.gov/api/xbrl/companyconcept/CIK0000320193/us-gaap/X.json",
        definition="filing observation",
        methodology="SEC XBRL us-gaap:X as reported in 10-Q",
        retrieved_at=RETRIEVED,
        raw=raw,
    )


class TestContractSurface(unittest.TestCase):
    def test_all_seven_metrics_are_contract_metrics(self):
        self.assertEqual(len(COMPARABLE_METRICS), 7)
        for metric in COMPARABLE_METRICS:
            self.assertIn(metric, CONTRACT_METRICS)
            self.assertIn(metric, METRIC_UNITS)
            self.assertIsNotNone(spec_for(metric))

    def test_every_metric_declares_a_comparability_spec(self):
        for metric in COMPARABLE_METRICS:
            spec = spec_for(metric)
            self.assertIn(
                spec.period_type,
                ("duration", "instant"),
                f"{metric} has no period type",
            )
            self.assertIn(
                spec.measurement_basis,
                ("TTM", "INSTANT"),
                f"{metric} has no measurement basis",
            )
            self.assertGreater(spec.tolerance.relative, 0)

    def test_period_mismatch_is_a_declared_status(self):
        self.assertEqual(
            ValidationStatus.PERIOD_MISMATCH.value, "PERIOD_MISMATCH"
        )

    def test_regulatory_filing_and_sec_bases_are_declared(self):
        self.assertEqual(
            SourceType.REGULATORY_FILING.value, "REGULATORY_FILING"
        )
        self.assertEqual(
            AvailabilityBasis.ACCEPTANCE_DATETIME.value,
            "ACCEPTANCE_DATETIME",
        )
        self.assertEqual(
            AvailabilityBasis.FILED_AS_OF_DATE.value, "FILED_AS_OF_DATE"
        )

    def test_vocabulary_still_excludes_investment_verdicts(self):
        self.assertTrue(contract_vocabulary_is_safe())

    def test_source_qualified_ids_cannot_collide_with_223(self):
        for metric in COMPARABLE_METRICS:
            identifier = comparable_observation_id(
                metric, SOURCE_SEC, period="2026-06-27", accession="1-2"
            )
            self.assertTrue(identifier.startswith("cmp-"))
            self.assertTrue(is_comparable_observation(
                _observation_with_id(identifier, metric)
            ))


def _observation_with_id(identifier: str, metric: str) -> Observation:
    return Observation(
        observation_id=identifier,
        metric=metric,
        value=1.0,
        unit=Unit.CURRENCY.value,
        currency="USD",
        currency_basis="REPORTED",
        period_start=None,
        period_end="2026-06-27",
        as_of="2026-06-27",
        available_at=None,
        available_at_basis=AvailabilityBasis.UNDECLARED.value,
        provider="SecEdgar",
        source_type=SourceType.REGULATORY_FILING.value,
        source_url=None,
        definition="x",
        methodology="x",
        retrieved_at=RETRIEVED,
    )


class TestTolerance(unittest.TestCase):
    def test_both_bounds_must_hold_for_a_large_value(self):
        tolerance = Tolerance("RELATIVE_AND_ABSOLUTE_BOUND", 0.005, 50_000_000.0)
        self.assertTrue(tolerance.allows(466_823_000_000, 466_800_000_000))
        self.assertFalse(tolerance.allows(466_823_000_000, 464_000_000_000))

    def test_the_absolute_bound_governs_a_small_value(self):
        tolerance = Tolerance("RELATIVE_AND_ABSOLUTE_BOUND", 0.01, 0.01)
        self.assertTrue(tolerance.allows(8.72, 8.725))
        self.assertFalse(tolerance.allows(8.72, 8.90))

    def test_a_relative_bound_alone_would_be_useless_on_revenue(self):
        """
        The reason both bounds exist, asserted so the absolute bound cannot be
        quietly dropped: 0.5% of a 466 billion revenue figure is 2.3 billion
        dollars, which nobody would call agreement.
        """
        relative_only = Tolerance("RELATIVE", 0.005, float("inf"))
        self.assertTrue(
            relative_only.allows(466_823_000_000, 466_000_000_000),
            "a relative-only rule would accept an 823 million difference",
        )
        both = Tolerance("RELATIVE_AND_ABSOLUTE_BOUND", 0.005, 50_000_000.0)
        self.assertFalse(
            both.allows(466_823_000_000, 466_000_000_000),
            "the absolute bound must reject it",
        )

    def test_an_absolute_bound_alone_would_be_useless_on_eps(self):
        absolute_only = Tolerance("ABSOLUTE", float("inf"), 0.5)
        self.assertTrue(
            absolute_only.allows(8.72, 9.20),
            "an absolute-only rule would accept any two EPS figures",
        )


class TestDiscreteFactFilter(unittest.TestCase):
    def _fact(self, start, end, value=1.0, frame=None) -> SecFact:
        return SecFact(
            metric="revenue",
            concept=None,
            taxonomy="us-gaap",
            tag="Revenues",
            label="",
            description="",
            unit="USD",
            value=value,
            start=start,
            end=end,
            accession="0000320193-26-000020",
            form="10-Q",
            fiscal_year=2026,
            fiscal_period="Q3",
            frame=frame,
            filed="2026-07-31",
        )

    def test_a_quarter_is_discrete(self):
        self.assertTrue(is_discrete_period(
            self._fact("2026-03-29", "2026-06-27", frame="CY2026Q2")
        ))

    def test_year_to_date_is_not_discrete(self):
        """
        The YTD filter is the single most important guard in the provider. A
        nine-month figure compared against a trailing figure is a category
        error that would be reported as a discrepancy.
        """
        ytd = self._fact("2025-09-28", "2026-06-27")
        self.assertFalse(is_discrete_period(ytd))
        self.assertFalse(is_quarter(ytd))
        self.assertTrue(is_cumulative(ytd))

    def test_an_annual_period_is_discrete(self):
        self.assertTrue(is_discrete_period(
            self._fact("2024-09-29", "2025-09-27")
        ))
        self.assertTrue(is_annual(self._fact("2024-09-29", "2025-09-27")))

    def test_an_instant_fact_is_discrete(self):
        instant = self._fact(None, "2026-06-27")
        self.assertTrue(is_discrete_period(instant))
        self.assertFalse(is_quarter(instant))
        self.assertFalse(is_annual(instant))
        self.assertFalse(is_cumulative(instant))

    def test_a_retail_calendar_quarter_counts(self):
        self.assertTrue(is_quarter(self._fact("2024-12-29", "2025-03-29")))
        self.assertTrue(is_quarter(self._fact("2022-09-26", "2022-12-31")))

    def test_period_bounds_are_the_documented_ones(self):
        self.assertEqual(QUARTER_MIN_DAYS, 60)
        self.assertEqual(QUARTER_MAX_DAYS, 130)


class TestTrailingConstruction(unittest.TestCase):
    def _fact(self, start, end, value, tag="Revenues") -> SecFact:
        return SecFact(
            metric="revenue",
            concept=None,
            taxonomy="us-gaap",
            tag=tag,
            label="",
            description="",
            unit="USD",
            value=value,
            start=start,
            end=end,
            accession=f"acc-{end}",
            form="10-K" if start else "10-Q",
            fiscal_year=2026,
            fiscal_period="FY",
            frame=None,
            filed="2026-07-31",
        )

    def setUp(self) -> None:
        self.provider = SECProvider(request_interval=0.0)

    def test_four_contiguous_quarters_sum(self):
        facts = [
            self._fact("2025-03-30", "2025-06-28", 100.0),
            self._fact("2025-06-29", "2025-09-27", 200.0),
            self._fact("2025-09-28", "2025-12-27", 300.0),
            self._fact("2025-12-28", "2026-03-28", 400.0),
        ]
        ttm = self.provider.ttm_from_quarters(facts)
        self.assertIsNotNone(ttm)
        self.assertEqual(ttm["construction"], "SUM_OF_DISCRETE_QUARTERS")
        self.assertEqual(ttm["value"], 1000.0)
        self.assertEqual(ttm["start"], "2025-03-30")
        self.assertEqual(ttm["end"], "2026-03-28")

    def test_a_hole_in_the_quarters_refuses_the_sum(self):
        """
        A retail filer reports its fiscal Q3 only inside the annual context.
        Summing across that hole would omit a quarter of revenue, so the
        provider refuses rather than returns a wrong total.
        """
        facts = [
            self._fact("2024-12-29", "2025-03-29", 100.0),
            self._fact("2025-03-30", "2025-06-28", 200.0),
            # fiscal Q3 missing: only the 363-day annual exists
            self._fact("2025-09-28", "2025-12-27", 300.0),
            self._fact("2025-12-28", "2026-03-28", 400.0),
        ]
        self.assertIsNone(self.provider.ttm_from_quarters(facts))

    def test_roll_forward_is_the_fallback_when_no_annual_matches(self):
        """
        A roll-forward only makes sense against the annual it rolls from, so an
        annual whose end does not coincide with the cumulative period's start
        is not a candidate.
        """
        facts = [
            self._fact("2024-09-29", "2025-09-27", 416_161_000_000.0),
            self._fact("2024-09-29", "2025-06-28", 313_695_000_000.0),
            self._fact("2025-09-28", "2026-06-27", 364_357_000_000.0),
        ]
        built = self.provider.build_ttm(facts, anchor="2026-06-27")
        # The FY2025 annual ends 2025-09-27, which is not the requested anchor,
        # so it cannot answer for it; the cumulative period can.
        self.assertIsNotNone(built)
        self.assertEqual(built["construction"], "ANNUAL_ROLL_FORWARD")
        self.assertEqual(built["value"], 466_823_000_000.0)
        self.assertEqual(built["start"], "2025-06-29")
        self.assertEqual(built["end"], "2026-06-27")
        self.assertEqual(len(built["constituents"]), 3)

    def test_a_filed_annual_is_preferred_over_a_stale_quarter_sum(self):
        """
        A filer whose fiscal year has just closed has a fresher twelve-month
        figure than any quarter sum, which necessarily ends a quarter earlier.
        The annual is the more direct answer and is not second-best.
        """
        facts = [
            self._fact("2025-07-01", "2026-06-30", 400.0),
            self._fact("2025-03-30", "2025-06-29", 100.0),
            self._fact("2025-06-30", "2025-09-28", 100.0),
            self._fact("2025-09-29", "2025-12-27", 100.0),
            self._fact("2025-12-28", "2026-03-29", 100.0),
        ]
        built = self.provider.build_ttm(facts)
        self.assertEqual(
            built["construction"], "ANNUAL_FACT_AS_TRAILING_WINDOW"
        )
        self.assertEqual(built["value"], 400.0)
        self.assertEqual(built["end"], "2026-06-30")

    def test_the_anchor_is_the_window_end_not_an_upper_bound(self):
        """
        A trailing view ending a quarter before the anchor would misalign the
        comparison, so it is refused rather than returned as a near match.
        """
        facts = [
            self._fact("2025-07-01", "2026-06-30", 400.0),
            self._fact("2024-09-29", "2025-09-27", 390.0),
            self._fact("2025-03-30", "2025-06-29", 100.0),
            self._fact("2025-06-30", "2025-09-28", 100.0),
            self._fact("2025-09-29", "2025-12-27", 100.0),
            self._fact("2025-12-28", "2026-03-29", 100.0),
        ]
        at_anchor = self.provider.build_ttm(facts, anchor="2026-06-30")
        self.assertEqual(at_anchor["end"], "2026-06-30")
        self.assertEqual(at_anchor["value"], 400.0)

        # A window ending a quarter before the anchor must not be returned as
        # a near match, even when a newer window exists.
        self.assertIsNone(
            self.provider.build_ttm(
                [
                    self._fact("2025-07-01", "2026-06-30", 400.0),
                    self._fact("2025-09-29", "2025-12-27", 100.0),
                ],
                anchor="2026-01-31",
            ),
            "a window that does not end at the anchor must be refused",
        )

    def test_trailing_anchors_offer_more_than_the_newest_window(self):
        facts = [
            self._fact("2025-07-01", "2026-06-30", 400.0),
            self._fact("2024-09-29", "2025-09-27", 390.0),
            self._fact("2025-12-28", "2026-03-29", 100.0),
            self._fact("2025-09-29", "2025-12-27", 100.0),
        ]
        anchors = self.provider.trailing_anchors(facts, limit=4)
        self.assertEqual(
            anchors,
            ["2026-06-30", "2026-03-29", "2025-12-27", "2025-09-27"],
            "a vendor may be quoting a window older than the newest filing",
        )

    def test_roll_forward_rejects_a_cumulative_period_that_changed_length(self):
        facts = [
            self._fact("2024-09-29", "2025-09-27", 416.0),
            self._fact("2024-01-01", "2025-06-28", 200.0),
            self._fact("2025-09-28", "2026-06-27", 300.0),
        ]
        self.assertIsNone(self.provider.ttm_by_roll_forward(facts))

    def test_roll_forward_rejects_a_mismatched_prior_period(self):
        facts = [
            self._fact("2024-09-29", "2025-09-27", 416.0),
            self._fact("2023-01-01", "2024-03-30", 200.0),
            self._fact("2025-09-28", "2026-06-27", 300.0),
        ]
        self.assertIsNone(self.provider.ttm_by_roll_forward(facts))

    def test_prefers_a_constructed_window_over_an_unrelated_annual(self):
        """
        The quarter sum is preferred when no annual covers the same window,
        because summing four disclosed quarters is more auditable than a
        roll-forward through cumulative figures.
        """
        facts = [
            self._fact("2025-03-30", "2025-06-28", 100.0),
            self._fact("2025-06-29", "2025-09-27", 200.0),
            self._fact("2025-09-28", "2025-12-27", 300.0),
            self._fact("2025-12-28", "2026-03-28", 400.0),
            # An annual that ends before the four quarters do, so it cannot
            # answer for a window ending 2026-03-28.
            self._fact("2022-09-25", "2023-09-30", 10_000.0),
        ]
        built = self.provider.build_ttm(facts, anchor="2026-03-28")
        self.assertEqual(built["construction"], "SUM_OF_DISCRETE_QUARTERS")
        self.assertEqual(built["value"], 1000.0)


class TestXBRLUnits(unittest.TestCase):
    def test_documented_and_observed_unit_spellings_both_map(self):
        self.assertEqual(
            xbrl_unit_to_contract_unit("USD"), Unit.CURRENCY.value
        )
        self.assertEqual(
            xbrl_unit_to_contract_unit("USD/shares"),
            Unit.PER_SHARE.value,
        )
        self.assertEqual(
            xbrl_unit_to_contract_unit("USD-per-shares"),
            Unit.PER_SHARE.value,
        )
        self.assertEqual(
            xbrl_unit_to_contract_unit("shares"), Unit.COUNT.value
        )

    def test_an_unmapped_unit_is_refused_not_coerced(self):
        self.assertIsNone(xbrl_unit_to_contract_unit("JPY"))
        self.assertIsNone(xbrl_unit_to_contract_unit("USD/shares/diluted"))

    def test_cik_is_zero_padded_to_ten_digits(self):
        self.assertEqual(normalize_cik(320193), "0000320193")
        self.assertEqual(normalize_cik("0000320193"), "0000320193")


class TestComparabilityPolicy(unittest.TestCase):
    def test_agreement_is_consistent_and_changes_nothing(self):
        vendor = make_vendor(METRIC_REVENUE, 466_823_000_000.0)
        filing = make_filing(METRIC_REVENUE, 466_800_000_000.0, ttm=True)
        result = cross_validate(METRIC_REVENUE, vendor, filing)

        self.assertEqual(result.status, ValidationStatus.CONSISTENT)
        self.assertTrue(result.comparable)
        # Both observations survive untouched.
        self.assertEqual(vendor.value, 466_823_000_000.0)
        self.assertEqual(filing.value, 466_800_000_000.0)
        self.assertEqual(
            set(result.validation.references),
            {vendor.observation_id, filing.observation_id},
        )

    def test_disagreement_is_reported_without_overwriting(self):
        vendor = make_vendor(METRIC_REVENUE, 466_823_000_000.0)
        filing = make_filing(METRIC_REVENUE, 400_000_000_000.0, ttm=True)
        result = cross_validate(METRIC_REVENUE, vendor, filing)

        self.assertEqual(result.status, ValidationStatus.DISCREPANT)
        self.assertTrue(result.is_disagreement)
        self.assertEqual(vendor.value, 466_823_000_000.0)
        self.assertEqual(filing.value, 400_000_000_000.0)
        self.assertEqual(
            result.validation.value_snapshot,
            (466_823_000_000.0, 400_000_000_000.0),
        )
        self.assertAlmostEqual(
            result.validation.comparison_basis["relative_difference"],
            0.1428,
            places=3,
        )

    def test_period_mismatch_when_anchors_are_too_far_apart(self):
        vendor = make_vendor(METRIC_REVENUE, 466.0, as_of="2026-06-30")
        filing = make_filing(
            METRIC_REVENUE, 466.0, period_end="2025-06-27", ttm=True
        )
        result = cross_validate(METRIC_REVENUE, vendor, filing)
        self.assertEqual(result.status, ValidationStatus.PERIOD_MISMATCH)
        self.assertFalse(result.comparable)
        self.assertGreater(
            result.validation.comparison_basis["period_offset_days"],
            PERIOD_ALIGNMENT_WINDOW_DAYS,
        )

    def test_a_fiscal_calendar_offset_within_the_window_is_aligned(self):
        """Apple's fiscal Q3 ends 2026-06-27; a vendor stamps 2026-06-30."""
        vendor = make_vendor(METRIC_REVENUE, 466.0, as_of="2026-06-30")
        filing = make_filing(METRIC_REVENUE, 466.0, period_end="2026-06-27", ttm=True)
        result = cross_validate(METRIC_REVENUE, vendor, filing)
        self.assertEqual(result.status, ValidationStatus.CONSISTENT)
        self.assertEqual(
            result.validation.comparison_basis["period_basis"], "AS_OF_ONLY"
        )

    def test_a_flow_is_never_compared_with_a_stock(self):
        vendor = make_vendor(
            METRIC_REVENUE, 466.0, period_type="duration", as_of="2026-06-27"
        )
        filing = make_filing(METRIC_REVENUE, 466.0, period_start=None, ttm=True)
        filing = filing.__class__(**{**filing.__dict__, "raw": {**filing.raw, "derivation": None}})
        result = cross_validate(METRIC_REVENUE, vendor, filing)
        self.assertIn(
            result.status,
            (
                ValidationStatus.METHODOLOGY_MISMATCH,
                ValidationStatus.PERIOD_MISMATCH,
            ),
        )

    def test_a_single_quarter_is_not_compared_with_a_trailing_figure(self):
        vendor = make_vendor(METRIC_REVENUE, 466.0)
        filing = make_filing(
            METRIC_REVENUE,
            109_417_000_000.0,
            period_start="2026-03-29",
            period_end="2026-06-27",
        )
        result = cross_validate(METRIC_REVENUE, vendor, filing)
        self.assertEqual(result.status, ValidationStatus.METHODOLOGY_MISMATCH)
        self.assertIn(
            "single reported period",
            " ".join(result.validation.reasons),
        )

    def test_unit_mismatch_is_a_methodology_mismatch(self):
        vendor = make_vendor(
            METRIC_EPS_DILUTED,
            8.72,
            unit=Unit.CURRENCY.value,
            as_of="2026-06-27",
        )
        filing = make_filing(
            METRIC_EPS_DILUTED,
            8.72,
            unit=Unit.PER_SHARE.value,
            period_start="2025-06-29",
            period_end="2026-06-27",
            ttm=True,
        )
        result = cross_validate(METRIC_EPS_DILUTED, vendor, filing)
        self.assertEqual(result.status, ValidationStatus.METHODOLOGY_MISMATCH)

    def test_currency_mismatch_is_a_methodology_mismatch(self):
        vendor = make_vendor(METRIC_REVENUE, 100.0, currency="USD", as_of="2026-06-27")
        filing = make_filing(METRIC_REVENUE, 100.0, currency="TWD", ttm=True)
        result = cross_validate(METRIC_REVENUE, vendor, filing)
        self.assertEqual(result.status, ValidationStatus.METHODOLOGY_MISMATCH)
        self.assertIn("currency differs", " ".join(result.validation.reasons))

    def test_known_definition_divergence_is_refused_before_arithmetic(self):
        vendor = make_vendor(
            METRIC_CASH,
            62_399_000_576.0,
            as_of=None,
            basis="UNDATED_INSTANT",
            period_type="instant",
        )
        filing = make_filing(
            METRIC_CASH, 39_544_000_000.0, period_start=None
        )
        result = cross_validate(METRIC_CASH, vendor, filing)
        self.assertEqual(result.status, ValidationStatus.METHODOLOGY_MISMATCH)
        self.assertIsNone(
            result.validation.comparison_basis.get("difference"),
            "a definition mismatch must not compute a difference",
        )
        self.assertEqual(vendor.value, 62_399_000_576.0)
        self.assertEqual(filing.value, 39_544_000_000.0)

    def test_missing_side_is_unavailable_not_wrong(self):
        vendor = make_vendor(METRIC_ASSETS, 383.0, as_of="2026-06-27", period_type="instant")
        result = cross_validate(METRIC_ASSETS, vendor, None)
        self.assertEqual(result.status, ValidationStatus.UNAVAILABLE)
        self.assertFalse(result.comparable)

    def test_an_undated_vendor_value_cannot_be_period_aligned(self):
        vendor = make_vendor(
            METRIC_SHARES_OUTSTANDING,
            14_594_180_000.0,
            unit=Unit.COUNT.value,
            currency=None,
            as_of=None,
            basis="UNDATED_INSTANT",
            period_type="instant",
        )
        filing = make_filing(
            METRIC_SHARES_OUTSTANDING,
            14_594_180_000.0,
            unit=Unit.COUNT.value,
            currency=None,
            period_start=None,
            period_end="2026-07-17",
        )
        result = cross_validate(METRIC_SHARES_OUTSTANDING, vendor, filing)
        self.assertEqual(result.status, ValidationStatus.PERIOD_MISMATCH)
        self.assertIn(
            "identical",
            result.validation.explanation,
            "an identical but undated value must be reported honestly",
        )

    def test_a_composed_total_records_its_composition(self):
        """
        Debt has no single standard concept, so the filing side composes one.
        The verdict is a definition mismatch, but the composition is still
        reported so a reader can see how the figure was built.
        """
        vendor = make_vendor(
            METRIC_DEBT,
            84_343_996_416.0,
            as_of="2026-06-27",
            basis="UNDATED_INSTANT",
            period_type="instant",
        )
        declared = make_filing(
            METRIC_DEBT,
            82_347_000_000.0,
            period_start=None,
            extra_raw={
                "composition": {
                    "concepts": [
                        "us-gaap:LongTermDebtCurrent",
                        "us-gaap:LongTermDebtNoncurrent",
                    ]
                }
            },
        )
        result = cross_validate(METRIC_DEBT, vendor, declared)
        self.assertEqual(result.status, ValidationStatus.METHODOLOGY_MISMATCH)
        self.assertEqual(
            result.validation.comparison_basis["filing_composition"],
            [
                "us-gaap:LongTermDebtCurrent",
                "us-gaap:LongTermDebtNoncurrent",
            ],
        )
        # No difference is computed for a definition mismatch.
        self.assertIsNone(
            result.validation.comparison_basis.get("difference")
        )
        # Both values survive.
        self.assertEqual(vendor.value, 84_343_996_416.0)
        self.assertEqual(declared.value, 82_347_000_000.0)

    def test_a_metric_with_no_vendor_counterpart_is_unavailable(self):
        """
        Yahoo publishes no total assets. The declared guard fires even if a
        vendor observation is somehow present, rather than reporting a
        comparison that means nothing.
        """
        vendor = make_vendor(
            METRIC_ASSETS,
            383_266_000_000.0,
            as_of="2026-06-27",
            basis="UNDATED_INSTANT",
            period_type="instant",
        )
        filing = make_filing(
            METRIC_ASSETS, 383_266_000_000.0, period_start=None
        )
        result = cross_validate(METRIC_ASSETS, vendor, filing)
        self.assertEqual(result.status, ValidationStatus.UNAVAILABLE)
        self.assertIn("no vendor counterpart", " ".join(result.validation.reasons))


class TestNoMergeGuarantee(unittest.TestCase):
    """
    The guarantee 2.3-B exists to protect, asserted structurally.

    A reviewer should be able to see that these tests are checking the absence
    of a capability, not the presence of a check.
    """

    def test_cross_validation_exposes_no_reconciliation_helper(self):
        import cross_validation as module

        forbidden = (
            "merge",
            "merge_values",
            "average",
            "average_values",
            "blend",
            "reconcile",
            "reconcile_values",
            "resolve",
            "pick_winner",
            "choose_source",
            "authoritative_value",
            "consensus_value",
        )
        for name in forbidden:
            self.assertFalse(
                hasattr(module, name),
                f"cross_validation must not offer {name!r}",
            )

    def test_cross_validation_defines_no_merging_functions(self):
        import cross_validation as module

        for name, member in vars(module).items():
            if name.startswith("_") or not inspect.isfunction(member):
                continue
            parameters = list(inspect.signature(member).parameters)
            self.assertNotIn(
                "merged",
                parameters,
                f"{name} must not accept a merged value",
            )

    def test_no_module_offers_a_source_priority(self):
        import cross_validation as module

        for name in dir(module):
            lowered = name.lower()
            self.assertNotIn("priority", lowered)
            self.assertNotIn("preference", lowered)
            self.assertNotIn("winner", lowered)

    def test_both_observations_survive_a_disagreement(self):
        observations = [
            make_vendor(METRIC_REVENUE, 100.0, as_of="2026-06-27"),
            make_filing(METRIC_REVENUE, 200.0, ttm=True),
        ]
        observation_set = ObservationSet(observations=observations)
        before = {
            identifier: observation.value
            for identifier, observation in (
                (o.observation_id, o) for o in observation_set.for_metric(
                    METRIC_REVENUE
                )
            )
        }
        result = cross_validate_metric(
            METRIC_REVENUE, observations[:1], observations[1:]
        )
        self.assertEqual(result.status, ValidationStatus.DISCREPANT)
        after = {
            identifier: observation.value
            for identifier, observation in (
                (o.observation_id, o) for o in observation_set.for_metric(
                    METRIC_REVENUE
                )
            )
        }
        self.assertEqual(before, after)
        self.assertEqual(len(after), 2, "neither side may be discarded")

    def test_a_comparison_cannot_reach_the_engine(self):
        """
        The valuation engine consumes Yahoo exactly as it did in 2.2.3, and
        nothing a second source produces can change a number it produced.

        The guarantee is checked structurally rather than by string search,
        because `st_eva_runner` does legitimately import the comparison on the
        opt-in Investment Context path. What must never happen is the engine
        class, the evidence builder, or the legacy result path touching it.
        """
        import ast
        import inspect

        import st_eva_runner

        source = inspect.getsource(st_eva_runner)
        tree = ast.parse(source)

        consumers = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [
                    alias.name
                    for alias in node.names
                ]
                if isinstance(node, ast.ImportFrom) and node.module:
                    names.append(node.module)
                if any(
                    name.split(".")[0] in ("cross_validation", "sec_provider")
                    for name in names
                ):
                    consumer = getattr(node, "_st_eva_enclosing", None)
                    for parent in ast.walk(tree):
                        if isinstance(
                            parent, (ast.FunctionDef, ast.AsyncFunctionDef)
                        ) and any(
                            child is node for child in ast.walk(parent)
                        ):
                            consumer = parent.name
                            break
                    consumers.add(consumer or "<module level>")

        self.assertTrue(
            consumers,
            "the comparison is not imported at all, which would mean the "
            "2.3-C context cannot carry cross-source verdicts",
        )
        # Two legitimate call sites. `_build_context_if_requested` assembles a
        # live context. `build_context_from_observations` reassembles one
        # during a 2.4 replay, and it *must* recompute the verdicts rather than
        # reuse the archived ones: a replayed document that reported a verdict
        # computed from data the replay did not have would be lying. Neither
        # is the valuation engine, and neither feeds it.
        allowed = ("_build_context_if_requested", "build_context_from_observations")
        for consumer in consumers:
            self.assertIn(
                consumer,
                allowed,
                f"cross-source code is reachable from {consumer!r}; the "
                "valuation engine must not depend on a second source",
            )

        engine_source = inspect.getsource(
            st_eva_runner.MarketImpliedAssumptionsEngine
        )
        for forbidden in ("cross_validation", "sec_provider", "cmp-"):
            self.assertNotIn(
                forbidden,
                engine_source,
                "the valuation engine must not reference a second source",
            )

        evidence_source = inspect.getsource(st_eva_runner.build_evidence)
        for forbidden in ("cross_validation", "sec_provider", "cmp-"):
            self.assertNotIn(forbidden, evidence_source)

    def test_the_legacy_result_carries_no_cross_source_verdict(self):
        result = run_st_eva("MSFT", mode="regression", save_snapshot=False)
        for forbidden in (
            "validated_evidence",
            "cross_source",
            "investment_context",
        ):
            self.assertNotIn(
                forbidden,
                result,
                f"the 2.2.3 result must not gain a {forbidden!r} key",
            )

class TestPointInTime(unittest.TestCase):
    def _restatement_set(self) -> ObservationSet:
        return ObservationSet(
            observations=[
                make_filing(
                    METRIC_REVENUE,
                    4_834_000_000.0,
                    period_end="2008-09-27",
                    accession="0000320193-09-000001",
                    available_at="2009-10-27T16:30:00.000Z",
                ),
                make_filing(
                    METRIC_REVENUE,
                    6_119_000_000.0,
                    period_end="2008-09-27",
                    accession="0000320193-10-000002",
                    available_at="2010-01-25T16:30:00.000Z",
                ),
            ]
        )

    def test_a_restatement_does_not_rewrite_the_earlier_observation(self):
        observations = self._restatement_set()
        self.assertEqual(len(observations.for_metric(METRIC_REVENUE)), 2)
        values = sorted(
            observation.value
            for observation in observations.for_metric(METRIC_REVENUE)
        )
        self.assertEqual(values, [4_834_000_000.0, 6_119_000_000.0])

    def test_the_value_knowable_at_a_cutoff_is_the_earlier_filing(self):
        observations = self._restatement_set()
        latest = observations.latest_knowable("2009-12-31", METRIC_REVENUE)
        self.assertEqual(latest.value, 4_834_000_000.0)

        after = observations.latest_knowable("2010-06-30", METRIC_REVENUE)
        self.assertEqual(after.value, 6_119_000_000.0)

    def test_an_undated_observation_is_never_asserted_as_knowable(self):
        observations = ObservationSet(
            observations=[make_vendor(METRIC_REVENUE, 100.0, as_of="2026-06-30")]
        )
        self.assertEqual(
            observations.knowable_at("2030-01-01"), [],
            "an undisclosed availability time cannot be asserted",
        )
        self.assertIsNone(
            observations.latest_knowable("2030-01-01", METRIC_REVENUE)
        )

    def test_availability_precedes_period_is_impossible(self):
        filing = make_filing(METRIC_REVENUE, 100.0, ttm=True)
        self.assertGreater(filing.available_at[:10], filing.period_end)
        record = validate_observation(filing, now=RETRIEVED)
        self.assertNotEqual(record.status, ValidationStatus.PERIOD_INVALID)


class TestSevenMetricsAlwaysAccountedFor(unittest.TestCase):
    def test_every_metric_is_classified_even_with_nothing_available(self):
        results = cross_validate_all([], [], checked_at=RETRIEVED)
        self.assertEqual(len(results), 7)
        for metric in COMPARABLE_METRICS:
            self.assertIn(metric, results)
            self.assertEqual(
                results[metric].status, ValidationStatus.UNAVAILABLE
            )

    def test_a_223_material_observation_never_enters_a_comparison(self):
        engine_observation = make_vendor(METRIC_REVENUE, 466.0)
        engine_observation = engine_observation.__class__(
            **{
                **engine_observation.__dict__,
                "observation_id": "ev-revenue-001",
            }
        )
        self.assertFalse(is_comparable_observation(engine_observation))
        results = cross_validate_all([engine_observation], [])
        self.assertEqual(
            results[METRIC_REVENUE].status, ValidationStatus.UNAVAILABLE
        )

    def test_definition_divergent_metrics_are_declared(self):
        self.assertIn(METRIC_CASH, DEFINITION_DIVERGENT_METRICS)
        self.assertIn(METRIC_DEBT, DEFINITION_DIVERGENT_METRICS)
        # shares is the same concept on both sides; its problem is a missing
        # date, and mislabelling that would be worse than not labelling it.
        self.assertNotIn(METRIC_SHARES_OUTSTANDING, DEFINITION_DIVERGENT_METRICS)

    def test_every_spec_declares_its_independence(self):
        for metric in COMPARABLE_METRICS:
            self.assertTrue(spec_for(metric).independence)
        self.assertEqual(
            spec_for(METRIC_SHARES_OUTSTANDING).independence,
            INDEPENDENCE_NONE,
        )


@unittest.skipUnless(
    os.environ.get("ST_EVA_LIVE") == "1",
    "live adapter tests need ST_EVA_LIVE=1",
)
class TestLiveAdapters(unittest.TestCase):
    def test_sec_provider_resolves_and_emits_observations(self):
        acquisition = SECProvider().fetch("AAPL")
        self.assertIsNotNone(acquisition.company)
        self.assertEqual(acquisition.company.cik, "0000320193")
        self.assertTrue(acquisition.observations)
        for observation in acquisition.observations:
            self.assertTrue(observation.observation_id.startswith("cmp-"))
            self.assertTrue(is_comparable_observation(observation))
            self.assertEqual(
                observation.source_type,
                SourceType.REGULATORY_FILING.value,
            )

    def test_sec_availability_is_a_provable_time_and_never_the_period_end(self):
        acquisition = SECProvider().fetch("AAPL")
        dated = [
            observation
            for observation in acquisition.observations
            if observation.available_at
        ]
        self.assertTrue(dated)
        for observation in dated:
            self.assertIn(
                observation.available_at_basis,
                (
                    AvailabilityBasis.ACCEPTANCE_DATETIME.value,
                    AvailabilityBasis.FILED_AS_OF_DATE.value,
                ),
            )
            self.assertGreater(
                observation.available_at[:10],
                observation.period_end,
                "a filing cannot be accepted before the period it reports",
            )

    def test_an_unknown_ticker_is_unavailable_not_an_exception(self):
        acquisition = SECProvider().fetch("NOT_A_REAL_TICKER_XYZ")
        self.assertIsNone(acquisition.company)
        self.assertEqual(acquisition.observations, ())
        self.assertTrue(acquisition.errors)

    def test_cross_validating_a_real_issuer_never_overwrites(self):
        sec = SECProvider().fetch("AAPL")
        yahoo = YahooFundamentalProvider().fetch_acquisition(
            "AAPL", instrument_currency="USD"
        )
        vendor = [
            observation
            for observation in yahoo.observations
            if is_comparable_observation(observation)
        ]
        results = cross_validate_all(vendor, sec.observations)

        self.assertEqual(len(results), 7)
        for metric, result in results.items():
            self.assertIsInstance(result.status, ValidationStatus)
            if result.left_observation_id:
                for observation in vendor:
                    if observation.observation_id == result.left_observation_id:
                        self.assertIsNotNone(observation.value)
            if result.right_observation_id:
                for observation in sec.observations:
                    if observation.observation_id == result.right_observation_id:
                        self.assertIsNotNone(observation.value)


if __name__ == "__main__":
    unittest.main()
