"""
ST-EVA 2.3-A data contract tests.

These cover the contract itself rather than the valuation arithmetic: the
provenance fields, the validation semantics, the raw-preservation rule, the
deterministic recomputation guarantee, and the provider-agnostic engine
boundary. The 2.2.3 regression suite in test_st_eva_runner.py continues to
cover the arithmetic and the existing output behaviour.
"""

import dataclasses
import unittest

from data_contract import (
    AvailabilityBasis,
    CONTRACT_METRICS,
    CONTRACT_OBSERVATION_IDS,
    CONTRACT_SOURCE_TYPES,
    CONTRACT_UNITS,
    CurrencyBasis,
    DEFAULT_STALE_AFTER_DAYS,
    DERIVED_METRICS,
    EVIDENCE_METRICS,
    Evidence,
    EvidenceStore,
    LegacyEvidenceRow,
    MATERIAL_METRICS,
    METRIC_CONSENSUS_FORWARD_EPS,
    METRIC_DEFINITIONS,
    METRIC_PE_BAND,
    METRIC_PRICE,
    METRIC_PRICE_VOLUME_METRICS,
    METRIC_TRAILING_EPS,
    METRIC_UNITS,
    MIN_BAND_OBSERVATIONS_FOR_REFERENCE,
    ObservationSet,
    SourceType,
    UNAVAILABLE,
    Unit,
    ValidationStatus,
    ValuationInputs,
    build_observation,
    compute_price_volume_metrics,
    contract_vocabulary_is_safe,
    currencies_match,
    distribution_from_samples,
    escalate_status,
    observation_id_for,
    recompute_distribution,
    recompute_price_volume_metrics,
    unavailable_observation,
    validate_observation,
)
from st_eva_runner import (
    CompanyResolver,
    DeterministicMetricsEngine,
    MarketImpliedAssumptionsEngine,
    build_evidence,
    material_observations,
    metrics_observation,
    run_st_eva,
)

RETRIEVED = "2026-09-28T09:00:00+00:00"


def make_observation(**overrides):
    """A valid EPS observation, with any field overridable per test."""
    fields = dict(
        metric=METRIC_TRAILING_EPS,
        value=5.0,
        unit=Unit.PER_SHARE.value,
        provider="StubProvider",
        source_type=SourceType.API_LIVE.value,
        definition="Current/trailing EPS. Never synthesized.",
        methodology="stub source field",
        retrieved_at=RETRIEVED,
        currency="USD",
        currency_basis=CurrencyBasis.REPORTED.value,
        period_start="2025-10-01",
        period_end="2026-09-30",
        as_of="2026-09-30",
        available_at=None,
        source_url="https://example.invalid/eps",
        raw={"field": "trailingEps"},
    )
    fields.update(overrides)
    return build_observation(**fields)


def make_band(samples, **overrides):
    fields = dict(
        metric=METRIC_PE_BAND,
        value=distribution_from_samples(samples),
        unit=Unit.MULTIPLE.value,
        currency=None,
        currency_basis=CurrencyBasis.NOT_APPLICABLE.value,
        period_start="2020-01-01",
        period_end="2024-01-01",
        as_of="2024-01-01",
        methodology="percentile band over stub samples",
        raw={"samples": list(samples), "as_of_dates": []},
        observation_count=len(samples),
    )
    fields.update(overrides)
    return make_observation(**fields)


class TestObservationImmutability(unittest.TestCase):
    def test_observation_is_frozen(self):
        observation = make_observation()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            observation.value = 99.0

    def test_validation_cannot_overwrite_the_raw_value(self):
        """
        The central rule of 2.3-A: validation labels a value, it never edits it.
        """
        observation = make_observation(value=5.0)
        record = validate_observation(observation, now=RETRIEVED)

        # The value is untouched, and the raw payload is still there.
        self.assertEqual(observation.value, 5.0)
        self.assertEqual(observation.raw, {"field": "trailingEps"})

        # The single-source caveat is an acquisition-time status, and the
        # record only adds what the validator detected. Neither one holds a
        # value, and neither one can write to the observation.
        self.assertEqual(observation.status, ValidationStatus.UNVERIFIABLE)
        self.assertEqual(record.status, ValidationStatus.VALID)
        self.assertEqual(
            escalate_status(observation.status, record.status),
            ValidationStatus.UNVERIFIABLE,
        )

    def test_validation_escalates_without_touching_the_value(self):
        observation = make_observation(
            value=5.0,
            period_start="2026-01-01",
            period_end="2025-01-01",
        )
        record = validate_observation(observation, now=RETRIEVED)
        self.assertEqual(record.status, ValidationStatus.PERIOD_INVALID)
        self.assertEqual(observation.value, 5.0)
        self.assertEqual(observation.status, ValidationStatus.UNVERIFIABLE)

    def test_evidence_value_is_the_observation_value(self):
        observation = make_observation()
        evidence = Evidence(
            evidence_id=observation.observation_id,
            observation=observation,
            validation=validate_observation(observation, now=RETRIEVED),
            legacy=LegacyEvidenceRow(
                provider="StubProvider",
                source="Input data",
                source_url=None,
                as_of="2026-09-30",
                unit="USD",
                currency="USD",
                quality="Medium",
                traceability="Medium",
            ),
        )
        self.assertEqual(evidence.value, 5.0)
        self.assertEqual(evidence.observation.raw, {"field": "trailingEps"})

    def test_raw_payload_is_preserved_verbatim(self):
        payload = {"samples": [1.0, 2.0], "as_of_dates": ["2020-01-01", "2021-01-01"]}
        observation = make_band([1.0, 2.0], raw=payload)
        self.assertEqual(observation.raw, payload)
        self.assertEqual(observation.contract_dict()["raw_preserved"], True)


class TestPeriodContract(unittest.TestCase):
    def test_period_fields_round_trip(self):
        observation = make_observation(
            period_start="2024-01-01",
            period_end="2024-12-31",
            as_of="2024-12-31",
        )
        self.assertEqual(observation.period_start, "2024-01-01")
        self.assertEqual(observation.period_end, "2024-12-31")
        self.assertEqual(observation.as_of, "2024-12-31")

    def test_point_in_time_observation_has_no_period(self):
        observation = make_observation(
            metric=METRIC_PRICE,
            unit=Unit.CURRENCY.value,
            period_start=None,
            period_end="2026-09-28",
            as_of="2026-09-28",
        )
        self.assertIsNone(observation.period_start)
        self.assertEqual(observation.period_end, "2026-09-28")

    def test_reversed_period_is_invalid(self):
        observation = make_observation(
            period_start="2025-01-01",
            period_end="2024-01-01",
        )
        record = validate_observation(observation, now=RETRIEVED)
        self.assertEqual(record.status, ValidationStatus.PERIOD_INVALID)
        self.assertTrue(any("period_start" in reason for reason in record.reasons))

    def test_unparseable_period_is_invalid(self):
        observation = make_observation(period_start="01/01/2024")
        record = validate_observation(observation, now=RETRIEVED)
        self.assertEqual(record.status, ValidationStatus.PERIOD_INVALID)


class TestAvailabilityContract(unittest.TestCase):
    def test_undisclosed_availability_stays_none(self):
        """
        A retrieval timestamp is not a publication timestamp. The engine must
        not pretend it knows when a figure became knowable.
        """
        observation = make_observation(available_at=None)
        self.assertIsNone(observation.available_at)
        self.assertEqual(
            observation.available_at_basis,
            AvailabilityBasis.UNDECLARED.value,
        )
    def test_daily_close_is_available_at_its_own_instant(self):
        observation = make_observation(
            metric=METRIC_PRICE,
            unit=Unit.CURRENCY.value,
            as_of="2026-09-28",
            available_at="2026-09-28",
        )
        self.assertEqual(
            observation.available_at_basis,
            AvailabilityBasis.OBSERVATION_INSTANT.value,
        )
        record = validate_observation(observation, now=RETRIEVED)
        self.assertNotEqual(record.status, ValidationStatus.STALE)

    def test_availability_never_precedes_as_of(self):
        observation = make_observation(
            as_of="2026-09-30",
            available_at="2026-01-01",
            available_at_basis=AvailabilityBasis.REPORTED.value,
        )
        record = validate_observation(observation, now=RETRIEVED)
        self.assertEqual(record.status, ValidationStatus.PERIOD_INVALID)
        self.assertTrue(
            any("available_at precedes as_of" in reason for reason in record.reasons)
        )

    def test_stale_value_is_labelled_for_live_data(self):
        observation = make_observation(
            metric=METRIC_PRICE,
            unit=Unit.CURRENCY.value,
            as_of="2026-01-01",
            available_at="2026-01-01",
            available_at_basis=AvailabilityBasis.REPORTED.value,
        )
        record = validate_observation(
            observation, now=RETRIEVED, stale_after_days=DEFAULT_STALE_AFTER_DAYS
        )
        self.assertEqual(record.status, ValidationStatus.STALE)
        self.assertTrue(any("freshness window" in reason for reason in record.reasons))

    def test_undisclosed_availability_is_not_called_stale(self):
        """
        Freshness is undetermined when availability is hidden. Labelling that
        STALE would punish the source for being honest.
        """
        observation = make_observation(available_at=None)
        record = validate_observation(observation, now=RETRIEVED)
        self.assertNotEqual(record.status, ValidationStatus.STALE)

    def test_validation_is_reproducible_for_a_given_now(self):
        observation = make_observation(
            metric=METRIC_PRICE,
            unit=Unit.CURRENCY.value,
            as_of="2026-01-01",
            available_at="2026-01-01",
            available_at_basis=AvailabilityBasis.REPORTED.value,
        )
        first = validate_observation(observation, now=RETRIEVED)
        second = validate_observation(observation, now=RETRIEVED)
        self.assertEqual(first, second)


class TestCurrencyContract(unittest.TestCase):
    def test_multiple_carries_no_currency(self):
        """A valuation band is a multiple, never a currency amount."""
        observation = make_band([10.0, 20.0, 30.0])
        self.assertEqual(observation.unit, Unit.MULTIPLE.value)
        self.assertIsNone(observation.currency)
        self.assertEqual(
            observation.currency_basis,
            CurrencyBasis.NOT_APPLICABLE.value,
        )
        self.assertIn(Unit.MULTIPLE.value, CONTRACT_UNITS)

    def test_currency_declared_by_the_instrument_is_marked_as_such(self):
        observation = make_observation(
            currency="TWD",
            currency_basis=CurrencyBasis.INSTRUMENT_DEFAULT.value,
        )
        self.assertEqual(observation.currency, "TWD")
        self.assertEqual(
            observation.currency_basis,
            CurrencyBasis.INSTRUMENT_DEFAULT.value,
        )

    def test_currency_mismatch_is_refused_not_computed(self):
        self.assertFalse(currencies_match("USD", "TWD"))
        self.assertFalse(currencies_match("USD", None))
        self.assertFalse(currencies_match(None, "USD"))
        self.assertTrue(currencies_match("usd", "USD"))

    def test_mismatched_sample_is_dropped_from_a_derived_band(self):
        results = [
            {
                "trailingMarketCap": [
                    {
                        "asOfDate": "2025-06-30",
                        "currencyCode": "USD",
                        "reportedValue": {"raw": 1000.0},
                    }
                ]
            },
            {
                "trailingFreeCashFlow": [
                    {
                        "asOfDate": "2025-06-30",
                        "currencyCode": "TWD",
                        "reportedValue": {"raw": 50.0},
                    }
                ]
            },
        ]
        from fundamental_provider import YahooFundamentalProvider

        self.assertEqual(
            YahooFundamentalProvider._derived_ratio_band(
                results, "trailingMarketCap", "trailingFreeCashFlow"
            ),
            {},
        )


class TestProvenanceContract(unittest.TestCase):
    def test_provenance_survives_serialization(self):
        observation = make_observation()
        record = observation.contract_dict()
        for field in (
            "metric",
            "unit",
            "currency",
            "currency_basis",
            "period_start",
            "period_end",
            "as_of",
            "available_at",
            "available_at_basis",
            "provider",
            "source_type",
            "source_url",
            "definition",
            "methodology",
            "retrieved_at",
        ):
            self.assertIn(field, record, f"{field} missing from the contract view")

        self.assertEqual(record["metric"], METRIC_TRAILING_EPS)
        self.assertEqual(record["unit"], Unit.PER_SHARE.value)
        self.assertEqual(record["provider"], "StubProvider")
        self.assertEqual(record["source_type"], SourceType.API_LIVE.value)
        self.assertEqual(
            record["source_url"], "https://example.invalid/eps"
        )
        self.assertEqual(record["methodology"], "stub source field")
        self.assertEqual(record["retrieved_at"], RETRIEVED)

    def test_methodology_names_the_upstream_field_not_the_metric(self):
        """
        A provider field name is allowed to survive as methodology. It is never
        allowed to become a metric the engine reads.
        """
        observation = make_observation(
            methodology="Yahoo quoteSummary defaultKeyStatistics.trailingEps"
        )
        self.assertEqual(observation.metric, METRIC_TRAILING_EPS)
        self.assertIn(METRIC_TRAILING_EPS, CONTRACT_METRICS)
        self.assertNotIn("trailingEps", CONTRACT_METRICS)

    def test_evidence_exposes_both_the_legacy_row_and_the_contract(self):
        data = CompanyResolver.resolve("MSFT", mode="regression")
        metrics = DeterministicMetricsEngine.compute(
            data.price_history, data.volume_history
        )
        store = build_evidence(data, metrics)
        evidence = store.get(CONTRACT_OBSERVATION_IDS[METRIC_PE_BAND])
        self.assertIsNotNone(evidence)

        legacy = evidence.as_dict()
        self.assertEqual(list(legacy.keys()), [
            "evidence_id", "value", "provider", "source", "source_url",
            "as_of", "unit", "currency", "definition", "source_type",
            "quality", "traceability",
        ])
        contract = evidence.contract_dict()
        self.assertEqual(contract["evidence_id"], "ev-pe-band-001")
        self.assertEqual(contract["metric"], METRIC_PE_BAND)
        self.assertIn("validation", contract)
        self.assertIn("evidence_status", contract)


class TestMissingDataContract(unittest.TestCase):
    def test_unavailable_observation_has_no_value(self):
        observation = unavailable_observation(
            metric=METRIC_TRAILING_EPS,
            provider="StubProvider",
            source_type=SourceType.API_LIVE.value,
            definition="Current/trailing EPS. Never synthesized.",
            methodology="stub source field",
            retrieved_at=RETRIEVED,
            unit=Unit.PER_SHARE.value,
        )
        self.assertIsNone(observation.value)
        self.assertFalse(observation.is_available)
        self.assertEqual(observation.status, ValidationStatus.UNAVAILABLE)
        self.assertTrue(observation.status_reasons)

    def test_missing_data_is_never_filled_with_zero(self):
        result = run_st_eva("MSFT", mode="regression", save_snapshot=False)
        # The fixture has no current EPS, so the engine must not invent one.
        self.assertIn("current_eps", result["missing_data"])
        # The 2.2.3 raw layer keeps the UNAVAILABLE sentinel; the derived
        # layer is null. Neither ever becomes a number.
        self.assertEqual(
            result["fundamental_snapshot"]["current_fcf"], UNAVAILABLE
        )
        self.assertIsNone(result["observed_valuation"]["current_pe"])
        self.assertIsNone(
            result["market_implied_assumptions"]["required_eps_cagr_from_current_eps"]
        )
        # A ratio whose inputs are unavailable stays null rather than becoming
        # zero, a median, or any other filler.
        self.assertIsNone(result["observed_valuation"]["current_pfcf"])
        self.assertIsNone(result["observed_valuation"]["current_ev_ebitda"])
        self.assertIsNone(result["observed_valuation"]["current_ps"])

    def test_absent_observation_reaches_the_engine_as_unavailable(self):
        """
        A provider that reports nothing must produce the same engine input as
        an explicit null: no value, no guess.
        """
        observations = ObservationSet(
            ticker="STUB",
            observations=[
                make_observation(
                    metric=METRIC_PRICE,
                    value=100.0,
                    unit=Unit.CURRENCY.value,
                    period_start=None,
                    period_end="2026-09-28",
                    as_of="2026-09-28",
                )
            ],
        )
        inputs = ValuationInputs.from_observations(observations)
        self.assertEqual(inputs.price, 100.0)
        self.assertEqual(inputs.current_eps, UNAVAILABLE)
        self.assertEqual(inputs.consensus_forward_eps, UNAVAILABLE)
        self.assertEqual(inputs.historical_pe_band, {})

        analysis = MarketImpliedAssumptionsEngine.analyze(
            inputs, reference_multiple=20.0
        )
        self.assertEqual(
            analysis["implied_assumptions"]["forward_eps_at_reference_multiple"],
            5.0,
        )
        self.assertIsNone(analysis["implied_assumptions"]["eps_gap_vs_consensus"])


class TestDuplicateEvidenceContract(unittest.TestCase):
    def test_duplicate_observation_id_is_refused(self):
        observations = ObservationSet()
        observations.add(make_observation())
        with self.assertRaises(ValueError):
            observations.add(make_observation())

    def test_duplicate_metric_from_two_providers_is_preserved(self):
        """
        Two providers reporting the same metric is evidence, not a conflict.
        Collapsing it here would destroy what 2.3-B has to compare.
        """
        first = make_observation(
            observation_id="obs-trailing-eps-source-a",
            provider="SourceA",
            value=5.0,
        )
        second = make_observation(
            observation_id="obs-trailing-eps-source-b",
            provider="SourceB",
            value=5.2,
        )
        observations = ObservationSet(observations=[first, second])

        self.assertEqual(len(observations.for_metric(METRIC_TRAILING_EPS)), 2)
        self.assertEqual(
            observations.value_for(METRIC_TRAILING_EPS), 5.0
        )
        self.assertEqual(
            sorted(observations.providers()), ["SourceA", "SourceB"]
        )
        self.assertEqual(
            [o.value for o in observations.for_metric(METRIC_TRAILING_EPS)],
            [5.0, 5.2],
        )

    def test_duplicate_evidence_id_is_refused(self):
        observation = make_observation()
        store = EvidenceStore()
        store.add(
            Evidence(
                evidence_id=observation.observation_id,
                observation=observation,
                validation=validate_observation(observation, now=RETRIEVED),
                legacy=LegacyEvidenceRow(
                    provider="StubProvider",
                    source="Input data",
                    source_url=None,
                    as_of="2026-09-30",
                    unit="USD",
                    currency="USD",
                    quality="Medium",
                    traceability="Medium",
                ),
            )
        )
        with self.assertRaises(ValueError):
            store.add(
                Evidence(
                    evidence_id=observation.observation_id,
                    observation=observation,
                    validation=validate_observation(observation, now=RETRIEVED),
                    legacy=LegacyEvidenceRow(
                        provider="StubProvider",
                        source="Input data",
                        source_url=None,
                        as_of="2026-09-30",
                        unit="USD",
                        currency="USD",
                        quality="Medium",
                        traceability="Medium",
                    ),
                )
            )

    def test_evidence_ids_and_order_are_unchanged_from_223(self):
        data = CompanyResolver.resolve("MSFT", mode="regression")
        metrics = DeterministicMetricsEngine.compute(
            data.price_history, data.volume_history
        )
        self.assertEqual(
            build_evidence(data, metrics).ids(),
            [
                "ev-price-001",
                "ev-current-eps-001",
                "ev-forward-eps-001",
                "ev-consensus-eps-001",
                "ev-pe-band-001",
                "ev-pfcf-band-001",
                "ev-ps-band-001",
                "ev-ev-ebitda-band-001",
                "ev-fcf-001",
                "ev-ebitda-001",
                "ev-revenue-001",
                "ev-enterprise-value-001",
                "ev-market-cap-001",
                "ev-metrics-001",
            ],
        )


class TestDeterministicRecompute(unittest.TestCase):
    def test_distribution_is_recomputable_from_preserved_samples(self):
        samples = [float(x) for x in range(10, 35)]
        observation = make_band(samples)
        self.assertEqual(recompute_distribution(observation), observation.value)

    def test_recompute_reports_the_gap_when_samples_are_absent(self):
        observation = make_band([1.0, 2.0], raw=None)
        self.assertEqual(recompute_distribution(observation), {})

    def test_live_bands_are_recomputable(self):
        from fundamental_provider import YahooFundamentalProvider

        class StubProvider(YahooFundamentalProvider):
            def _bootstrap_crumb(self):
                return None

            def _timeseries(self, ticker, types, years=5):
                result = []
                for field in ("trailingPeRatio", "trailingPsRatio"):
                    result.append(
                        {
                            field: [
                                {
                                    "asOfDate": "2020-01-%02d" % (index + 1),
                                    "currencyCode": "USD",
                                    "reportedValue": {"raw": 20.0 + index},
                                }
                                for index in range(25)
                            ]
                        }
                    )
                return {"timeseries": {"result": result}}

        acquisition = StubProvider().fetch_acquisition("STUB")
        for observation in acquisition.observations:
            if observation.is_band and observation.is_available:
                self.assertEqual(
                    recompute_distribution(observation),
                    observation.value,
                    f"{observation.metric} is not recomputable from its raw samples",
                )

    def test_price_volume_metrics_are_recomputable(self):
        prices = [float(x) for x in range(100, 140)]
        volumes = [float(x) * 1000 for x in range(40)]
        metrics = compute_price_volume_metrics(prices, volumes)

        data = CompanyResolver.resolve("MSFT", mode="regression")
        data.price_history = prices
        data.volume_history = volumes
        from st_eva_runner import metrics_observation

        observation = metrics_observation(data, metrics)
        self.assertEqual(
            recompute_price_volume_metrics(observation), observation.value
        )
        self.assertEqual(
            set(observation.inputs),
            {"obs-price-history-001", "obs-volume-history-001"},
        )

    def test_metrics_observation_records_its_inputs(self):
        data = CompanyResolver.resolve("MSFT", mode="regression")
        metrics = DeterministicMetricsEngine.compute(
            data.price_history, data.volume_history
        )
        from st_eva_runner import metrics_observation

        observation = metrics_observation(data, metrics)
        self.assertEqual(observation.metric, METRIC_PRICE_VOLUME_METRICS)
        self.assertEqual(observation.source_type, "DETERMINISTIC_CALCULATION")
        self.assertTrue(observation.inputs)


class TestValidationStatusContract(unittest.TestCase):
    def test_every_status_is_a_declared_string(self):
        for status in ValidationStatus:
            self.assertIsInstance(status.value, str)
            self.assertTrue(status.value)

    def test_cross_source_statuses_are_declared_but_not_computed(self):
        """
        2.3-B states exist in the vocabulary so it is stable, and 2.3-A must
        not emit them: doing so needs a second source.
        """
        for status in (
            ValidationStatus.VERIFIED,
            ValidationStatus.CONSISTENT,
            ValidationStatus.DISCREPANT,
            ValidationStatus.METHODOLOGY_MISMATCH,
        ):
            self.assertIsInstance(status.value, str)
        data = CompanyResolver.resolve("MSFT", mode="regression")
        metrics = DeterministicMetricsEngine.compute(
            data.price_history, data.volume_history
        )
        statuses = set(build_evidence(data, metrics).statuses().values())
        self.assertEqual(
            statuses
            & {
                ValidationStatus.VERIFIED.value,
                ValidationStatus.CONSISTENT.value,
                ValidationStatus.DISCREPANT.value,
                ValidationStatus.METHODOLOGY_MISMATCH.value,
            },
            set(),
        )

    def test_escalation_takes_the_stronger_caveat(self):
        self.assertEqual(
            escalate_status(ValidationStatus.VALID, ValidationStatus.STALE),
            ValidationStatus.STALE,
        )
        self.assertEqual(
            escalate_status(ValidationStatus.UNAVAILABLE, ValidationStatus.VALID),
            ValidationStatus.UNAVAILABLE,
        )

    def test_thin_band_is_insufficient_observations(self):
        observation = make_band([float(x) for x in range(5)])
        record = validate_observation(observation, now=RETRIEVED)
        self.assertEqual(
            record.status, ValidationStatus.INSUFFICIENT_OBSERVATIONS
        )
        self.assertEqual(observation.observation_count, 5)
        self.assertLess(observation.observation_count, MIN_BAND_OBSERVATIONS_FOR_REFERENCE)

    def test_band_without_a_declared_count_is_not_refused(self):
        """
        A static fixture that declares no sample size stays usable. Refusing
        honest data for not publishing a count would be a defect.
        """
        band = {
            "10th": 22.0,
            "25th": 26.0,
            "median": 30.0,
            "75th": 34.0,
            "90th": 38.0,
        }
        observation = make_observation(
            metric=METRIC_PE_BAND,
            value=band,
            unit=Unit.MULTIPLE.value,
            currency=None,
            currency_basis=CurrencyBasis.NOT_APPLICABLE.value,
            raw=None,
        )
        record = validate_observation(observation, now=RETRIEVED)
        self.assertNotEqual(
            record.status, ValidationStatus.INSUFFICIENT_OBSERVATIONS
        )

    def test_missing_metadata_is_reported(self):
        observation = make_observation(definition="")
        record = validate_observation(observation, now=RETRIEVED)
        self.assertEqual(record.status, ValidationStatus.MISSING_METADATA)
        self.assertTrue(any("definition" in reason for reason in record.reasons))

    def test_source_type_must_be_a_contract_source_type(self):
        observation = make_observation(source_type="SOME_OTHER_API")
        record = validate_observation(observation, now=RETRIEVED)
        self.assertEqual(record.status, ValidationStatus.MISSING_METADATA)


class TestProviderAgnosticEngine(unittest.TestCase):
    def test_engine_matches_from_observations_and_from_the_view(self):
        data = CompanyResolver.resolve("MSFT", mode="regression")
        observations = ObservationSet(
            ticker=data.ticker,
            observations=list(material_observations(data).values()),
        )
        inputs = ValuationInputs.from_observations(
            observations,
            price=data.price,
            currency=data.currency,
        )
        from_view = MarketImpliedAssumptionsEngine.analyze(data)
        from_contract = MarketImpliedAssumptionsEngine.analyze(inputs)
        self.assertEqual(from_view, from_contract)

    def test_engine_runs_on_a_non_yahoo_provider(self):
        """
        Requirement 8: the engine cannot depend on a Yahoo structure, because
        it never sees one. A different source needs no engine change at all.
        """
        observations = ObservationSet(
            ticker="STUB",
            observations=[
                make_observation(
                    metric=METRIC_PRICE,
                    observation_id="ev-price-001",
                    value=500.0,
                    unit=Unit.CURRENCY.value,
                    provider="OtherProvider",
                    source_type=SourceType.API_LIVE.value,
                    methodology="other provider quote",
                    period_start=None,
                    period_end="2026-09-28",
                    as_of="2026-09-28",
                ),
                make_observation(
                    metric=METRIC_CONSENSUS_FORWARD_EPS,
                    observation_id="ev-consensus-eps-001",
                    value=20.0,
                    provider="OtherProvider",
                ),
                make_band(
                    [float(x) for x in range(40, 61)],
                    observation_id="ev-pe-band-001",
                    provider="OtherProvider",
                ),
            ],
        )
        inputs = ValuationInputs.from_observations(observations)
        analysis = MarketImpliedAssumptionsEngine.analyze(inputs)

        self.assertEqual(analysis["reference"]["method"], "historical_pe_median")
        self.assertEqual(analysis["reference"]["multiple"], 50.0)
        self.assertAlmostEqual(
            analysis["implied_assumptions"][
                "forward_eps_at_reference_multiple"
            ],
            10.0,
            places=10,
        )

    def test_valuation_inputs_carry_no_provider_structure(self):
        inputs = ValuationInputs(
            price=100.0,
            current_eps=5.0,
            historical_pe_band={"median": 20.0},
        )
        serialized = str(inputs)
        for forbidden in ("yahoo", "trailingEps", "quoteSummary", "http"):
            self.assertNotIn(forbidden, serialized.lower())


class TestScopeGuard(unittest.TestCase):
    def test_contract_vocabulary_excludes_investment_verdicts(self):
        """
        Requirements 10 to 12: no comparison, ranking, score, probability, or
        buy/sell vocabulary may enter the contract.
        """
        self.assertTrue(contract_vocabulary_is_safe())

    def test_cross_source_statuses_are_absent_from_the_vocabulary(self):
        self.assertNotIn("compare", " ".join(CONTRACT_SOURCE_TYPES).lower())

    def test_no_band_observation_carries_a_currency(self):
        data = CompanyResolver.resolve("MSFT", mode="regression")
        data.historical_pe_band = {
            "10th": 10.0, "25th": 15.0, "median": 20.0,
            "75th": 30.0, "90th": 40.0, "observations": 120,
        }
        observations = material_observations(data)
        for metric in ("pe_band", "ps_band", "pfcf_band", "ev_ebitda_band"):
            observation = observations[metric]
            self.assertEqual(observation.unit, Unit.MULTIPLE.value)
            self.assertIsNone(observation.currency)

    def test_observation_ids_are_unique_per_metric(self):
        ids = [observation_id_for(metric) for metric in EVIDENCE_METRICS]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), set(CONTRACT_OBSERVATION_IDS.values()))

    def test_every_material_metric_has_a_unit_and_definition(self):
        for metric in MATERIAL_METRICS:
            self.assertIn(metric, METRIC_UNITS)
            self.assertIn(metric, METRIC_DEFINITIONS)
            self.assertIn(METRIC_UNITS[metric], CONTRACT_UNITS)

    def test_derived_metrics_are_separate_from_sourced_metrics(self):
        self.assertNotIn(METRIC_PRICE_VOLUME_METRICS, MATERIAL_METRICS)
        self.assertIn(METRIC_PRICE_VOLUME_METRICS, DERIVED_METRICS)
        self.assertIn(METRIC_PRICE_VOLUME_METRICS, EVIDENCE_METRICS)


if __name__ == "__main__":
    unittest.main()
