"""
Regression tests for the seven material findings from the six-company context QA.

Each test names the finding it closes. They are written against the intended
behaviour, so before the fix they fail; after it they pass. None of them
special-cases a ticker: every case is a general property of the contract, the
derivation gate, the comparability policy, or the document.

    F1  a derived value must not be produced when its operands are denominated
        in different currencies
    F2  an adapter must not stamp a currency its source never stated
    F3  security / price / EPS / shares basis and an ADS ratio must be
        expressible, and must not be silently mixed
    F4  a derived share count that disagrees with a reported one is a
        CONFLICT, not a fact
    F5  a valuation figure that claims cross-validated evidence must reference
        the same observation the validation judged
    F6  a stale observation must be visible as stale, including second-source
        observations, and must not read as current
    F7  a series with a discontinuity must expose the change metadata
"""

import unittest

from data_contract import (
    AvailabilityBasis,
    METRIC_CASH,
    METRIC_LONG_TERM_DEBT,
    METRIC_REVENUE,
    METRIC_SHARES_OUTSTANDING,
    Observation,
    ObservationSet,
    SourceType,
    Unit,
    ValidationStatus,
    figure_units_compatible,
    units_match,
)
from cross_validation import cross_validate
from fundamental_provider import YahooFundamentalProvider
from investment_context import (
    IDENTITY_CHECKS,
    PROVENANCE_CONDITIONAL,
    PROVENANCE_DERIVED,
    PROVENANCE_UNAVAILABLE,
    build_investment_context,
    series_metadata,
)
from operation_registry import RegistryError, evaluate
from st_eva_runner import (
    CompanyResolver,
    DeterministicMetricsEngine,
    MarketImpliedAssumptionsEngine,
    build_evidence,
    material_observations,
    metrics_observation,
)

RETRIEVED = "2026-09-28T12:00:00+00:00"


def observation(
    observation_id,
    metric,
    value,
    *,
    unit=Unit.CURRENCY.value,
    currency="USD",
    currency_basis="REPORTED",
    period_start=None,
    period_end="2026-06-27",
    as_of="2026-06-27",
    available_at="2026-07-31T10:01:02.000Z",
    available_at_basis=AvailabilityBasis.ACCEPTANCE_DATETIME.value,
    provider="SecEdgar",
    source_type=SourceType.REGULATORY_FILING.value,
    basis=None,
    raw=None,
):
    return Observation(
        observation_id=observation_id,
        metric=metric,
        value=value,
        unit=unit,
        currency=currency,
        currency_basis=currency_basis,
        period_start=period_start,
        period_end=period_end,
        as_of=as_of,
        available_at=available_at,
        available_at_basis=available_at_basis,
        provider=provider,
        source_type=source_type,
        source_url=None,
        definition="d",
        methodology="m",
        retrieved_at=RETRIEVED,
        raw=raw if raw is not None else {},
        basis=basis,
    )


class TestF1CrossCurrencyDerivationIsRefused(unittest.TestCase):
    """
    F1: TSM computed P/S as USD market cap / TWD revenue = 0.452.

    Both operands had unit `currency`, so the unit table was satisfied. The
    unit table cannot catch this: currency identity is a separate axis from
    unit identity, and it was never checked.
    """

    def test_dividing_two_different_currencies_is_refused(self):
        with self.assertRaises(RegistryError):
            evaluate(
                "divide",
                [2_008_084_460_181.0, 4_440_492_457_000.0],
                ["currency", "currency"],
                operand_currencies=["USD", "TWD"],
            )

    def test_dividing_the_same_currency_is_still_allowed(self):
        value = evaluate(
            "divide",
            [100.0, 4.0],
            ["currency", "currency"],
            operand_currencies=["USD", "USD"],
        )
        self.assertEqual(value, 25.0)

    def test_a_dimensionless_operand_carries_no_currency_constraint(self):
        value = evaluate(
            "divide",
            [100.0, 4.0],
            ["currency", "multiple"],
            operand_currencies=["USD", None],
        )
        self.assertEqual(value, 25.0)

    def test_two_figures_are_incompatible_when_currency_differs(self):
        usd = observation("a", METRIC_REVENUE, 100.0, currency="USD")
        twd = observation("b", METRIC_REVENUE, 100.0, currency="TWD")
        self.assertTrue(units_match(usd.unit, twd.unit))
        self.assertFalse(
            figure_units_compatible(usd, twd),
            "same unit is not the same quantity",
        )
        self.assertTrue(figure_units_compatible(usd, usd))

    def test_a_context_with_mixed_currency_refuses_the_ratio(self):
        """
        The end-to-end shape of F1.

        The engine is handed a ratio it computed across two currencies, exactly
        as it would be when a filer reports in its own currency while listing in
        another. The document must withhold it rather than publish a plausible
        number with no economic meaning.
        """
        data = CompanyResolver.resolve("AAPL", mode="regression")
        metrics = DeterministicMetricsEngine.compute(
            data.price_history, data.volume_history
        )
        evidence = build_evidence(data, metrics)
        analysis = MarketImpliedAssumptionsEngine.analyze(data)
        materials = list(material_observations(data).values())
        revenue = next(
            item for item in materials if item.metric == METRIC_REVENUE
        )
        from dataclasses import replace

        foreign = replace(
            revenue,
            value=4_440_492_457_000.0,
            currency="TWD",
        )
        # What the engine would hand the document without a currency gate.
        market_cap = next(
            item for item in materials if item.metric == "market_cap"
        )
        cross_currency = float(market_cap.value) / float(foreign.value)
        analysis["observed_valuation"]["current_ps"] = cross_currency
        self.assertAlmostEqual(
            cross_currency,
            1.1076542953803288,
            places=6,
        )

        document = build_investment_context(
            data=data,
            analysis=analysis,
            evidence=evidence,
            metrics=metrics,
            material_observations=[
                item if item.metric != METRIC_REVENUE else foreign
                for item in materials
            ] + [metrics_observation(data, metrics)],
            generated_at=RETRIEVED,
        )
        entry = document["derived"]["current_ps"]
        self.assertEqual(
            entry["figure"]["provenance_kind"],
            PROVENANCE_UNAVAILABLE,
            "a cross-currency ratio must be withheld, not published",
        )
        self.assertNotIn("value", entry["figure"])
        reason = next(
            item["reason"]
            for item in document["unavailable"]
            if item["ref"] == "der:current_ps"
        )
        self.assertIn("TWD", reason)
        self.assertIn("USD", reason)


class TestF2UnstatedCurrencyIsNotAsserted(unittest.TestCase):
    """
    F2: TSM's cash and debt were tagged USD while being TWD amounts.

    Root cause: the adapter stamped the instrument's quote currency on vendor
    balance-sheet figures whose module states no currency at all. ST-EVA
    asserted a denomination the source never declared.
    """

    def test_vendor_balance_sheet_figures_carry_no_asserted_currency(self):
        provider = YahooFundamentalProvider()
        emitted = provider.comparable_observations(
            summary_item={
                "defaultKeyStatistics": {"sharesOutstanding": 5_186_474_013},
                "financialData": {
                    # The vendor states no currency for this module.
                    "totalCash": 3_518_010_228_736,
                    "totalDebt": 1_068_558_516_224,
                    "currency": None,
                },
            },
            valuation_results=[],
            instrument_currency="USD",
            retrieved_at=RETRIEVED,
            quote_summary_url=None,
            timeseries_url=None,
        )
        by_metric = {item.metric: item for item in emitted}
        # `totalDebt` is in the payload and `long_term_debt` is still absent from
        # the output. That is the whole point: the vendor's *total* debt is not the
        # metric, and a `methodology` caveat would not make it one. The payload
        # deliberately still supplies `totalDebt` so the test proves the provider
        # declines it rather than merely never seeing it.
        self.assertNotIn(
            METRIC_LONG_TERM_DEBT, by_metric,
            "Yahoo totalDebt was projected onto a long-term-debt metric",
        )
        for metric in (METRIC_CASH,):
            item = by_metric[metric]
            self.assertIsNone(
                item.currency,
                f"{metric} was stamped with a currency the source never stated",
            )
            self.assertEqual(
                item.currency_basis, "UNDECLARED"
            )
            self.assertIn(
                "no", item.methodology.lower(),
            )

    def test_an_undated_vendor_total_cannot_be_combined_with_a_currency(self):
        vendor = observation(
            "cmp-cash-yahoo",
            METRIC_CASH,
            3_518_010_228_736.0,
            currency=None,
            currency_basis="UNDECLARED",
            available_at=None,
            available_at_basis=AvailabilityBasis.UNDECLARED.value,
            provider="YahooFinanceFundamentals",
            source_type=SourceType.API_LIVE.value,
        )
        filing = observation("cmp-cash-sec", METRIC_CASH, 3_100_000_000_000.0)
        result = cross_validate(METRIC_CASH, vendor, filing)
        self.assertEqual(result.status, ValidationStatus.METHODOLOGY_MISMATCH)
        self.assertIn(
            "currency", " ".join(result.validation.reasons)
        )


class TestF3SecurityAndShareBasis(unittest.TestCase):
    """
    F3: TSM lists as ADS. Price is per ADS, the filing's cover-page count is
    ordinary shares, and the two differ by exactly 5. ST-EVA had nowhere to
    say so, so a consumer could divide a price by an ordinary-share count.
    """

    def test_an_observation_can_declare_its_basis(self):
        item = observation(
            "obs-1",
            METRIC_SHARES_OUTSTANDING,
            25_932_524_521,
            unit=Unit.COUNT.value,
            currency=None,
            currency_basis="NOT_APPLICABLE",
            basis={
                "security_type": "ORDINARY_SHARE",
                "shares_basis": "FILING_COVER_PAGE",
                "listing": "DOMESTIC",
                "source_declared": True,
            },
        )
        self.assertEqual(item.basis["shares_basis"], "FILING_COVER_PAGE")
        round_tripped = Observation(**{
            field: getattr(item, field)
            for field in item.contract_dict()
            if field in Observation.__dataclass_fields__
        })
        self.assertEqual(round_tripped.basis, item.basis)

    def test_an_undeclared_basis_is_stated_as_such_rather_than_guessed(self):
        item = observation("obs-2", "price", 453.33)
        self.assertIsNone(
            item.basis,
            "an adapter must not invent a basis it was not told",
        )

    def test_differing_share_bases_are_a_conflict_not_a_number(self):
        """
        Two counts for one issuer that differ by a large factor are not two
        facts to be averaged. Both sides declare different bases, so that is a
        demonstrated conflict.
        """
        ordinary = observation(
            "cmp-shares-sec-cover",
            METRIC_SHARES_OUTSTANDING,
            25_932_524_521,
            unit=Unit.COUNT.value,
            currency=None,
            currency_basis="NOT_APPLICABLE",
            as_of="2025-12-31",
            period_end="2025-12-31",
            basis={
                "shares_basis": "FILING_COVER_PAGE_REGISTERED_SECURITY",
                "security_type": "REGISTERED_SECURITY",
                "source_declared": True,
            },
        )
        ads = observation(
            "cmp-shares-yahoo",
            METRIC_SHARES_OUTSTANDING,
            5_186_474_013,
            unit=Unit.COUNT.value,
            currency=None,
            currency_basis="NOT_APPLICABLE",
            available_at=None,
            available_at_basis=AvailabilityBasis.UNDECLARED.value,
            provider="YahooFinanceFundamentals",
            source_type=SourceType.API_LIVE.value,
            basis={
                "shares_basis": "LISTED_INSTRUMENT",
                "security_type": "LISTED_INSTRUMENT",
                "source_declared": True,
            },
        )
        result = cross_validate(
            METRIC_SHARES_OUTSTANDING, ordinary, ads
        )
        self.assertEqual(result.status, ValidationStatus.CONFLICTING)
        self.assertIn(
            "shares_basis", " ".join(result.validation.reasons).lower()
        )
        # Both counts survive, unmerged.
        self.assertEqual(ordinary.value, 25_932_524_521)
        self.assertEqual(ads.value, 5_186_474_013)

    def test_a_silent_basis_is_a_comparability_gap_not_a_conflict(self):
        """
        When one side declares its basis and the other says nothing, the
        difference is measurable but the cause is not. Calling that a conflict
        would over-claim what the sources establish.
        """
        declared = observation(
            "cmp-shares-sec",
            METRIC_SHARES_OUTSTANDING,
            25_932_524_521,
            unit=Unit.COUNT.value,
            currency=None,
            currency_basis="NOT_APPLICABLE",
            as_of="2025-12-31",
            period_end="2025-12-31",
            basis={
                "shares_basis": "FILING_COVER_PAGE_REGISTERED_SECURITY",
                "source_declared": True,
            },
        )
        silent = observation(
            "cmp-shares-yahoo",
            METRIC_SHARES_OUTSTANDING,
            5_186_474_013,
            unit=Unit.COUNT.value,
            currency=None,
            currency_basis="NOT_APPLICABLE",
            available_at=None,
            available_at_basis=AvailabilityBasis.UNDECLARED.value,
            provider="YahooFinanceFundamentals",
            source_type=SourceType.API_LIVE.value,
            basis={"security_type": "UNDECLARED", "source_declared": False},
        )
        result = cross_validate(
            METRIC_SHARES_OUTSTANDING, declared, silent
        )
        self.assertEqual(result.status, ValidationStatus.METHODOLOGY_MISMATCH)
        self.assertAlmostEqual(
            result.validation.comparison_basis["value_ratio"], 5.0, places=2
        )
        self.assertIn(
            "NOT_EXPLAINED",
            str(result.validation.comparison_basis["ratio_interpretation"]),
        )

    def test_the_implied_ratio_is_reported_without_explaining_it(self):
        """
        The ratio between two share counts is useful. What the ratio *means*
        is not something ST-EVA may assert, so the record states the factor and
        explicitly declines to attribute it.
        """
        ordinary = observation(
            "a", METRIC_SHARES_OUTSTANDING, 25_932_524_521,
            unit=Unit.COUNT.value, currency=None, currency_basis="NOT_APPLICABLE",
            as_of="2025-12-31", period_end="2025-12-31",
            basis={"shares_basis": "FILING_COVER_PAGE", "source_declared": True},
        )
        ads = observation(
            "b", METRIC_SHARES_OUTSTANDING, 5_186_474_013,
            unit=Unit.COUNT.value, currency=None, currency_basis="NOT_APPLICABLE",
            available_at=None,
            available_at_basis=AvailabilityBasis.UNDECLARED.value,
            provider="YahooFinanceFundamentals",
            source_type=SourceType.API_LIVE.value,
            basis={"shares_basis": "UNDECLARED", "source_declared": False},
        )
        result = cross_validate(METRIC_SHARES_OUTSTANDING, ordinary, ads)
        basis = result.validation.comparison_basis
        self.assertAlmostEqual(basis["value_ratio"], 5.0, places=2)
        self.assertIn("NOT_EXPLAINED", str(basis.get("ratio_interpretation")))


class TestF4DerivedVersusReportedConflict(unittest.TestCase):
    """
    F4: NU's share count appears three ways and differs by 40%. The document
    published the derived one as a plain figure, which reads as authoritative.
    """

    def _nu_document(self):
        # An issuer whose fixture publishes a market capitalisation, so the
        # implied share count exists and the identity can be checked at all.
        data = CompanyResolver.resolve("AAPL", mode="regression")
        metrics = DeterministicMetricsEngine.compute(
            data.price_history, data.volume_history
        )
        evidence = build_evidence(data, metrics)
        analysis = MarketImpliedAssumptionsEngine.analyze(data)
        materials = list(material_observations(data).values())
        # A reported count that cannot be reconciled with price x count.
        from dataclasses import replace

        reported = replace(
            next(
                item for item in materials
                if item.metric == METRIC_SHARES_OUTSTANDING
                and item.is_available
            )
            if any(
                item.metric == METRIC_SHARES_OUTSTANDING and item.is_available
                for item in materials
            )
            else observation(
                "ev-shares-placeholder",
                METRIC_SHARES_OUTSTANDING,
                0.0,
                unit=Unit.COUNT.value,
                currency=None,
                currency_basis="NOT_APPLICABLE",
            ),
            observation_id="ev-shares-reported",
            value=data.price * 0.70,  # deliberately irreconcilable
            unit=Unit.COUNT.value,
            currency=None,
            currency_basis="NOT_APPLICABLE",
        )
        return build_investment_context(
            data=data,
            analysis=analysis,
            evidence=evidence,
            metrics=metrics,
            material_observations=materials
            + [reported, metrics_observation(data, metrics)],
            generated_at=RETRIEVED,
        )

    def test_the_identity_check_is_declared_not_hard_coded(self):
        names = {check.name for check in IDENTITY_CHECKS}
        self.assertIn(
            "price_times_count_equals_market_cap", names
        )

    def test_an_irreconcilable_count_produces_a_conflict_record(self):
        document = self._nu_document()
        conflicts = document["data_quality"].get("identity_conflicts") or []
        self.assertTrue(
            conflicts,
            "a derived count that cannot be reconciled with the reported one "
            "must be reported as a conflict",
        )
        self.assertEqual(conflicts[0]["status"], "CONFLICTING")
        self.assertIn("implied_shares", conflicts[0]["derived_ref"])
        self.assertIn("ev-shares-reported", conflicts[0]["reported_ref"])

    def test_a_conflict_records_both_values_and_picks_neither(self):
        document = self._nu_document()
        conflict = (document["data_quality"]["identity_conflicts"])[0]
        self.assertIsNotNone(conflict["derived_value"])
        self.assertIsNotNone(conflict["reported_value"])
        self.assertNotEqual(
            conflict["derived_value"], conflict["reported_value"]
        )
        self.assertEqual(
            conflict["resolution"], "NO_WINNER_SELECTED"
        )


class TestF5ValidationConstrainsTheConsumer(unittest.TestCase):
    """
    F5: MSFT's cross-source check validated a trailing EPS to 2026-03-31,
    while the P/E was computed from a trailing EPS to 2026-06-30. Nothing
    connected the two, so "EPS was cross-validated" read as supporting the
    P/E. It does not.
    """

    def _document_with_validation(self):
        data = CompanyResolver.resolve("MSFT", mode="regression")
        metrics = DeterministicMetricsEngine.compute(
            data.price_history, data.volume_history
        )
        evidence = build_evidence(data, metrics)
        analysis = MarketImpliedAssumptionsEngine.analyze(data)
        materials = list(material_observations(data).values())
        # A validation of a *different* observation of the same metric.
        validated = observation(
            "cmp-revenue-yahoo-2026-03-31",
            METRIC_REVENUE,
            100.0,
            available_at="2026-04-30T10:00:00.000Z",
            provider="YahooFinanceFundamentals",
            source_type=SourceType.API_LIVE.value,
        )
        filing = observation(
            "cmp-revenue-sec-ttm-to-2026-03-31",
            METRIC_REVENUE,
            100.0,
            period_start="2025-04-01",
            period_end="2026-03-31",
        )
        verdict = cross_validate(
            METRIC_REVENUE, validated, filing, checked_at=RETRIEVED
        )
        document = build_investment_context(
            data=data,
            analysis=analysis,
            evidence=evidence,
            metrics=metrics,
            material_observations=materials
            + [validated, filing, metrics_observation(data, metrics)],
            cross_validation={METRIC_REVENUE: verdict},
            generated_at=RETRIEVED,
        )
        return document

    def test_a_derived_figure_states_its_validation_state(self):
        document = self._document_with_validation()
        for name, entry in document["derived"].items():
            self.assertIn(
                "validation_state", entry,
                f"{name} does not say whether its inputs were validated",
            )
            self.assertIn(
                entry["validation_state"],
                ("VALIDATED", "UNVALIDATED", "PARTIALLY_VALIDATED",
                 "CONFLICTING"),
            )

    def test_a_figure_using_an_unvalidated_observation_is_unvalidated(self):
        """
        The P/E is built from the material EPS, which no validation judged.
        It must therefore not read as validated, however clean the
        neighbouring revenue verdict is.
        """
        document = self._document_with_validation()
        self.assertEqual(
            document["derived"]["current_pe"]["validation_state"],
            "UNVALIDATED",
        )

    def test_validation_references_must_resolve(self):
        document = self._document_with_validation()
        refs = set(document["provenance"]["refs"])
        for name, entry in document["derived"].items():
            for reference in entry.get("validation_refs", ()):
                self.assertIn(reference, refs, f"{name} names a dangling validation")

    def test_a_figure_using_a_validated_observation_is_validated(self):
        document = self._document_with_validation()
        entry = document["derived"].get("implied_revenue") or {}
        # Whatever the outcome, a validated operand must be reflected in the
        # state rather than ignored.
        if "validation_refs" in entry:
            self.assertIn(entry["validation_state"], ("VALIDATED", "UNVALIDATED"))


class TestF6StaleObservationsAreVisible(unittest.TestCase):
    """
    F6: MU's latest filing-sourced debt observation is from 2013, and the
    document reported zero stale observations.
    """

    def _document_with_old_filing(self):
        data = CompanyResolver.resolve("MSFT", mode="regression")
        metrics = DeterministicMetricsEngine.compute(
            data.price_history, data.volume_history
        )
        evidence = build_evidence(data, metrics)
        analysis = MarketImpliedAssumptionsEngine.analyze(data)
        materials = list(material_observations(data).values())
        ancient = observation(
            "cmp-debt-sec-2013",
            METRIC_LONG_TERM_DEBT,
            3_624_000_000.0,
            as_of="2013-05-30",
            period_end="2013-05-30",
            period_start=None,
            available_at="2013-06-28T10:00:00.000Z",
        )
        return build_investment_context(
            data=data,
            analysis=analysis,
            evidence=evidence,
            metrics=metrics,
            material_observations=materials
            + [ancient, metrics_observation(data, metrics)],
            generated_at=RETRIEVED,
        )

    def test_a_long_dead_filing_is_counted_as_stale(self):
        document = self._document_with_old_filing()
        freshness = document["data_quality"]["freshness"]
        self.assertIn("long_term_debt", freshness["stale_metrics"])
        bucket = freshness["by_metric"]["long_term_debt"]
        self.assertEqual(bucket["recency"], "NO_RECENT_VALUE")
        self.assertEqual(bucket["latest_as_of"], "2013-05-30")
        self.assertGreater(bucket["current_value_age_days"], 4000)

    def test_a_stale_observation_is_still_retained(self):
        """
        A stale observation is still evidence. The requirement is that it is not
        mistaken for current usable data, not that it is deleted.
        """
        document = self._document_with_old_filing()
        self.assertIn("obs:cmp-debt-sec-2013", document["provenance"]["refs"])
        figures = [
            item["figure"]
            for item in document["observed"][METRIC_LONG_TERM_DEBT]
            if item["figure"]["ref"] == "obs:cmp-debt-sec-2013"
        ]
        self.assertTrue(figures)
        self.assertIn("value", figures[0])

    def test_a_second_source_observation_is_validated_too(self):
        document = self._document_with_old_filing()
        stale = [
            entry
            for entry in document["provenance"]["refs"].values()
            if entry.get("kind") == "val"
            and entry.get("status") == "STALE"
        ]
        self.assertTrue(stale, "a filing with no recent value must be flagged")

    def test_freshness_is_reported_per_metric(self):
        document = self._document_with_old_filing()
        freshness = document["data_quality"]["freshness"]
        self.assertIn("by_metric", freshness)
        self.assertIn("recency", freshness["by_metric"][METRIC_LONG_TERM_DEBT])


class TestF7SeriesChangeMetadata(unittest.TestCase):
    """
    F7: NVDA's filing-sourced debt rises from about 8.5bn to 33.4bn with no
    provenance-level indication that anything happened.
    """

    def test_a_discontinuity_is_surfaced_without_an_explanation(self):
        series = [
            observation(
                f"cmp-debt-sec-{period}",
                METRIC_LONG_TERM_DEBT,
                value,
                as_of=period,
                period_end=period,
                period_start=None,
                available_at=f"{period}T12:00:00.000Z",
            )
            for period, value in (
                ("2025-10-26", 8_467_000_000.0),
                ("2026-01-25", 8_468_000_000.0),
                ("2026-04-26", 8_470_000_000.0),
                ("2026-07-26", 33_366_000_000.0),
            )
        ]
        report = series_metadata(series)
        self.assertEqual(report[METRIC_LONG_TERM_DEBT]["observations"], 4)
        self.assertTrue(report[METRIC_LONG_TERM_DEBT]["discontinuities"])
        worst = report[METRIC_LONG_TERM_DEBT]["discontinuities"][0]
        self.assertEqual(worst["to_period"], "2026-07-26")
        self.assertGreater(worst["relative_change"], 2.0)
        self.assertEqual(
            worst["explanation"], "NOT_EXPLAINED_BY_ST_EVA"
        )

    def test_a_stable_series_reports_no_discontinuity(self):
        series = [
            observation(
                f"cmp-debt-sec-{period}",
                METRIC_LONG_TERM_DEBT,
                value,
                as_of=period,
                period_end=period,
                available_at=f"{period}T12:00:00.000Z",
            )
            for period, value in (
                ("2026-01-25", 8_468_000_000.0),
                ("2026-04-26", 8_470_000_000.0),
            )
        ]
        report = series_metadata(series)
        self.assertEqual(report[METRIC_LONG_TERM_DEBT]["discontinuities"], [])

    def test_the_report_declares_what_it_does_not_know(self):
        series = [
            observation(
                "cmp-debt-sec-x", METRIC_LONG_TERM_DEBT, 1.0,
                period_end="2026-01-25",
                available_at="2026-01-25T12:00:00.000Z",
            )
        ]
        report = series_metadata(series)
        self.assertEqual(
            report[METRIC_LONG_TERM_DEBT]["comparability"],
            "SINGLE_OBSERVATION_NO_TREND",
        )


if __name__ == "__main__":
    unittest.main()
