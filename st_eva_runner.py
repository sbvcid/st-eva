from __future__ import annotations

"""
ST-EVA 2.3-A - Market-Implied Assumptions Engine

Purpose:
    Answer "What assumptions are embedded in the current price?"

The engine is deliberately descriptive and conditional. It reverse-engineers
earnings assumptions only after an explicit valuation reference is selected.

Data flow (2.3-A):

    Provider -> Observation -> Evidence -> Validation -> Derived

The engine consumes `ValuationInputs`, a provider-agnostic projection of the
observations. It never reads a provider's own field names.

Rules:
    - No synthetic EPS or consensus estimates.
    - No arbitrary Bull/Base/Bear probabilities.
    - No arbitrary price multipliers.
    - Missing data stays unavailable.
    - Arithmetic is deterministic Python.
    - Every source input receives an Evidence ID.
    - Validation labels a value; it never rewrites one.
"""

import argparse
import json
import os
import sys
import tempfile
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from data_contract import (
    AvailabilityBasis,
    BAND_METRICS,
    CurrencyBasis,
    DERIVED_METRICS,
    DerivedValue,
    EVIDENCE_METRICS,
    Evidence,
    EvidenceStore,
    LegacyEvidenceRow,
    MATERIAL_METRICS,
    METRIC_CONSENSUS_FORWARD_EPS,
    METRIC_DEFINITIONS,
    METRIC_ENTERPRISE_VALUE,
    METRIC_EBITDA,
    METRIC_EV_EBITDA_BAND,
    METRIC_FORWARD_EPS,
    METRIC_FREE_CASH_FLOW,
    METRIC_MARKET_CAP,
    METRIC_PE_BAND,
    METRIC_PFCF_BAND,
    METRIC_PRICE,
    METRIC_PRICE_HISTORY,
    METRIC_PRICE_VOLUME_METRICS,
    METRIC_PS_BAND,
    METRIC_REVENUE,
    METRIC_TRAILING_EPS,
    METRIC_UNITS,
    METRIC_VOLUME_HISTORY,
    MIN_BAND_OBSERVATIONS_FOR_REFERENCE,
    OBSERVATION_ID_PRICE_HISTORY,
    OBSERVATION_ID_VOLUME_HISTORY,
    Observation,
    ObservationSet,
    SourceType,
    UNAVAILABLE,
    Unit,
    ValidationStatus,
    ValuationInputs,
    build_observation,
    compute_price_volume_metrics,
    is_comparable_observation,
    is_number,
    observation_id_for,
    recompute_distribution,
    safe_float,
    unavailable_observation,
    utc_now,
    validate_observation,
)
from fundamental_provider import YahooFundamentalProvider
from report_formatter import (
    normalize_ticker,
    print_report,
    resolve_console_encoding,
)


UNAVAILABLE = UNAVAILABLE

VERSION_METADATA = {
    "engine": "ST-EVA Market-Implied Assumptions Engine",
    "version": "2.2.3",
    "analysis_type": "market_implied_assumptions",
    "calculation_engine": "deterministic-python",
    "data_policy": "zero-synthetic-financial-data",
    "validator_version": "2.2.3",
    "schema_version": "2.2.3",
}


def atomic_json_write(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=".st_eva_", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)


PRICE_DEFINITION = METRIC_DEFINITIONS[METRIC_PRICE]
PRICE_SOURCE = "Yahoo Finance chart API"
PRICE_METHODOLOGY = "Yahoo chart API regularMarketPrice or last daily close"
METRICS_METHODOLOGY = (
    "deterministic-python price and volume statistics from observed history"
)


@dataclass
class MarketData:
    """
    The 2.2.3 engine view of one instrument.

    This shape is kept because the CLI, the report, the fixtures, and existing
    callers depend on it. It is a projection: every material field is read from
    the observation set, which is the actual source of truth. `observations`
    holds the raw, provenance-carrying values the view was built from.
    """

    ticker: str
    company_name: str
    exchange: str
    currency: str
    price: float
    price_date: str
    price_source: str
    price_source_url: Optional[str]
    price_history: List[float]
    volume_history: List[float]
    current_eps: Any = UNAVAILABLE
    forward_eps: Any = UNAVAILABLE
    consensus_forward_eps: Any = UNAVAILABLE
    consensus_forward_eps_period: Optional[str] = None
    errors: List[str] = field(default_factory=list)
    next_event: Any = UNAVAILABLE
    next_event_status: str = "Unconfirmed"
    historical_pe_band: Optional[Dict[str, Any]] = None
    current_fcf: Any = UNAVAILABLE
    current_ebitda: Any = UNAVAILABLE
    current_revenue: Any = UNAVAILABLE
    current_enterprise_value: Any = UNAVAILABLE
    current_market_cap: Any = UNAVAILABLE
    historical_ps_band: Optional[Dict[str, Any]] = None
    historical_pfcf_band: Optional[Dict[str, Any]] = None
    historical_ev_ebitda_band: Optional[Dict[str, Any]] = None
    source_type: str = "UNKNOWN"
    provider: str = "UNKNOWN"
    discrepancy_status: str = "SINGLE_SOURCE"
    observations: ObservationSet = field(default_factory=ObservationSet)
    retrieved_at: str = ""

    def __post_init__(self) -> None:
        if self.historical_pe_band is None:
            self.historical_pe_band = {}
        if self.historical_ps_band is None:
            self.historical_ps_band = {}
        if self.historical_pfcf_band is None:
            self.historical_pfcf_band = {}
        if self.historical_ev_ebitda_band is None:
            self.historical_ev_ebitda_band = {}
        if not self.retrieved_at:
            self.retrieved_at = utc_now()

    def valuation_inputs(self) -> ValuationInputs:
        """The provider-agnostic input surface the engine consumes."""
        return ValuationInputs.from_legacy_view(self)

    def contract_view(
        self,
        analysis: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """The 2.3-A contract view of this run, for the snapshot artifact."""
        observations = material_observations(self)
        derived = describe_derived_values(self, analysis)
        return {
            "contract_version": CONTRACT_VERSION,
            "ticker": self.ticker,
            "currency": self.currency,
            "retrieved_at": self.retrieved_at,
            "observations": [
                observations[metric].contract_dict()
                for metric in EVIDENCE_METRICS
                if metric in observations
            ],
            "validation": {
                observations[metric].observation_id: validate_for_snapshot(
                    observations[metric]
                )
                for metric in EVIDENCE_METRICS
                if metric in observations
            },
            "derived": [
                value.contract_dict() for value in derived
            ],
        }


CONTRACT_VERSION = "2.3-A"


# Static test fixtures. They are not live market data.
REGRESSION_TEST_FIXTURES: Dict[str, Dict[str, Any]] = {
    "TENCENT": {
        "ticker": "0700.HK",
        "company_name": "騰訊控股 (Tencent Holdings Limited)",
        "exchange": "SEHK",
        "currency": "HKD",
        "price": 432.20,
        "price_date": "2026-09-18",
        "price_source": "Regression fixture",
        "price_source_url": "https://www.hkex.com.hk",
        "current_eps": UNAVAILABLE,
        "forward_eps": 31.50,
        "consensus_forward_eps": 31.50,
        "next_event": "2026-11-14",
        "next_event_status": "Estimated fixture date; not live",
        "historical_pe_band": {"10th": 12.0, "25th": 15.0, "median": 18.5, "75th": 23.0, "90th": 28.0},
        "price_history": [405.0, 410.0, 415.0, 420.0, 425.0, 432.2],
        "volume_history": [30000000, 32000000, 31000000, 33000000, 32500000, 32000000],
        "source_type": "REGRESSION_FIXTURE",
        "provider": "RegressionFixture",
    },
    "MSFT": {
        "ticker": "MSFT",
        "company_name": "Microsoft Corporation",
        "exchange": "NASDAQ",
        "currency": "USD",
        "price": 425.50,
        "price_date": "2026-09-18",
        "price_source": "Regression fixture",
        "price_source_url": "https://www.nasdaq.com",
        "current_eps": UNAVAILABLE,
        "forward_eps": 13.20,
        "consensus_forward_eps": 13.20,
        "next_event": "2026-10-22",
        "next_event_status": "Estimated fixture date; not live",
        "historical_pe_band": {"10th": 22.0, "25th": 26.0, "median": 30.0, "75th": 34.0, "90th": 38.0},
        "price_history": [410.0, 412.0, 415.0, 418.0, 422.0, 425.5],
        "volume_history": [20000000, 21000000, 20500000, 22000000, 21500000, 21000000],
        "source_type": "REGRESSION_FIXTURE",
        "provider": "RegressionFixture",
    },
    "NU": {
        "ticker": "NU",
        "company_name": "Nu Holdings Ltd.",
        "exchange": "NYSE",
        "currency": "USD",
        "price": 12.80,
        "price_date": "2026-09-18",
        "price_source": "Regression fixture",
        "price_source_url": "https://www.nyse.com",
        "current_eps": UNAVAILABLE,
        "forward_eps": 0.48,
        "consensus_forward_eps": 0.48,
        "next_event": "2026-11-10",
        "next_event_status": "Estimated fixture date; not live",
        "historical_pe_band": {"10th": 14.0, "25th": 17.0, "median": 20.0, "75th": 25.0, "90th": 32.0},
        "price_history": [11.8, 12.0, 12.2, 12.4, 12.6, 12.8],
        "volume_history": [40000000, 42000000, 41000000, 45000000, 43000000, 44000000],
        "source_type": "REGRESSION_FIXTURE",
        "provider": "RegressionFixture",
    },
}


def _derive_discrepancy_status(data: "MarketData") -> str:
    """
    Classify the evidence quality of an acquired dataset.

    This is an evidence state, not an investment rating. A single provider
    cannot verify itself, so a live single-source acquisition is reported as
    UNVERIFIABLE rather than silently trusted.
    """
    if data.errors:
        return ValidationStatus.UNVERIFIABLE.value
    if data.discrepancy_status == ValidationStatus.DISCREPANT.value:
        return "DATA_DISCREPANCY"
    if data.source_type == SourceType.API_LIVE.value:
        return ValidationStatus.UNVERIFIABLE.value
    return ValidationStatus.SINGLE_SOURCE.value


# ---------------------------------------------------------------------------
# Observation construction
#
# Values are always read from the 2.2.3 view fields, so a caller that sets a
# field directly stays authoritative. Provenance is carried over from the
# provider observation, so the raw payload and the declared period survive
# into the contract view.
# ---------------------------------------------------------------------------

VIEW_FIELD_FOR_METRIC: Dict[str, str] = {
    METRIC_PRICE: "price",
    METRIC_TRAILING_EPS: "current_eps",
    METRIC_FORWARD_EPS: "forward_eps",
    METRIC_CONSENSUS_FORWARD_EPS: "consensus_forward_eps",
    METRIC_PE_BAND: "historical_pe_band",
    METRIC_PFCF_BAND: "historical_pfcf_band",
    METRIC_PS_BAND: "historical_ps_band",
    METRIC_EV_EBITDA_BAND: "historical_ev_ebitda_band",
    METRIC_FREE_CASH_FLOW: "current_fcf",
    METRIC_EBITDA: "current_ebitda",
    METRIC_REVENUE: "current_revenue",
    METRIC_ENTERPRISE_VALUE: "current_enterprise_value",
    METRIC_MARKET_CAP: "current_market_cap",
}

FIXTURE_METHODOLOGY = "static regression fixture value; not live market data"
FIXTURE_HISTORY_METHODOLOGY = (
    "static regression fixture price/volume series; not live market data"
)


def _normalize_observed_value(value: Any) -> Any:
    """
    Map the 2.2.3 view sentinels onto the contract's absent value.

    A missing input is None in the contract, never zero and never a median.
    """
    if value is None or value == UNAVAILABLE or value == {}:
        return None
    return value


def _observations_by_metric(
    data: "MarketData",
) -> Dict[str, Observation]:
    """
    Index the acquisition's observations by metric, as provenance sources.

    A second source reports the same metric names, and `latest()` is a
    time-based selector, not a materiality selector: with a filing-sourced
    observation in the same set it can return the filing's figure and silently
    replace the engine's own input. The material observation is the one the
    engine actually read, so it wins; a comparable one is used only when
    nothing material exists.
    """
    indexed: Dict[str, Observation] = {}
    for metric in list(MATERIAL_METRICS) + list(DERIVED_METRICS) + [
        METRIC_PRICE_HISTORY,
        METRIC_VOLUME_HISTORY,
    ]:
        found = list(data.observations.for_metric(metric))
        if not found:
            continue
        material = [
            observation
            for observation in found
            if not is_comparable_observation(observation)
        ]
        available = [
            observation
            for observation in (material or found)
            if observation.is_available
        ]
        indexed[metric] = (available or material or found)[0]
    return indexed


def price_observations(
    data: "MarketData",
    timestamps: Optional[Sequence[int]] = None,
) -> List[Observation]:
    """
    The price, price history and volume history of one acquisition.

    A daily close is knowable at its own close, so `available_at` is the
    observation instant. The history observations keep the raw series so the
    derived price/volume metrics can be recomputed from them.
    """
    dates = [
        datetime.fromtimestamp(int(stamp), tz=timezone.utc)
        .date()
        .isoformat()
        for stamp in (timestamps or [])
    ]
    period_start = dates[0] if dates else None
    period_end = dates[-1] if dates else data.price_date

    price_raw: Dict[str, Any] = {
        "regular_market_price": data.price,
        "closes": list(data.price_history),
    }

    return [
        build_observation(
            metric=METRIC_PRICE,
            value=data.price,
            unit=Unit.CURRENCY.value,
            provider=data.provider,
            source_type=data.source_type,
            definition=PRICE_DEFINITION,
            methodology=data.price_source or PRICE_METHODOLOGY,
            retrieved_at=data.retrieved_at,
            currency=data.currency,
            currency_basis=(
                CurrencyBasis.REPORTED.value
                if data.currency
                else CurrencyBasis.UNDECLARED.value
            ),
            period_start=None,
            period_end=data.price_date,
            as_of=data.price_date,
            available_at=data.price_date,
            available_at_basis=AvailabilityBasis.OBSERVATION_INSTANT.value,
            source_url=data.price_source_url,
            raw=price_raw,
        ),
        Observation(
            observation_id=OBSERVATION_ID_PRICE_HISTORY,
            metric=METRIC_PRICE_HISTORY,
            value=list(data.price_history),
            unit=Unit.CURRENCY.value,
            currency=data.currency or None,
            currency_basis=(
                CurrencyBasis.REPORTED.value
                if data.currency
                else CurrencyBasis.UNDECLARED.value
            ),
            period_start=period_start,
            period_end=period_end,
            as_of=data.price_date,
            available_at=data.price_date,
            available_at_basis=AvailabilityBasis.OBSERVATION_INSTANT.value,
            provider=data.provider,
            source_type=data.source_type,
            source_url=data.price_source_url,
            definition="Observed daily closing price series.",
            methodology=(
                PRICE_METHODOLOGY
                if data.source_type == SourceType.API_LIVE.value
                else FIXTURE_HISTORY_METHODOLOGY
            ),
            retrieved_at=data.retrieved_at,
            raw={"prices": list(data.price_history), "dates": dates},
            observation_count=len(data.price_history),
            status=(
                ValidationStatus.UNVERIFIABLE
                if data.source_type == SourceType.API_LIVE.value
                else ValidationStatus.SINGLE_SOURCE
            ),
        ),
        Observation(
            observation_id=OBSERVATION_ID_VOLUME_HISTORY,
            metric=METRIC_VOLUME_HISTORY,
            value=list(data.volume_history),
            unit=Unit.COUNT.value,
            currency=None,
            currency_basis=CurrencyBasis.NOT_APPLICABLE.value,
            period_start=period_start,
            period_end=period_end,
            as_of=data.price_date,
            available_at=data.price_date,
            available_at_basis=AvailabilityBasis.OBSERVATION_INSTANT.value,
            provider=data.provider,
            source_type=data.source_type,
            source_url=data.price_source_url,
            definition="Observed daily traded volume series.",
            methodology=(
                PRICE_METHODOLOGY
                if data.source_type == SourceType.API_LIVE.value
                else FIXTURE_HISTORY_METHODOLOGY
            ),
            retrieved_at=data.retrieved_at,
            raw={"volumes": list(data.volume_history), "dates": dates},
            observation_count=len(data.volume_history),
            status=(
                ValidationStatus.UNVERIFIABLE
                if data.source_type == SourceType.API_LIVE.value
                else ValidationStatus.SINGLE_SOURCE
            ),
        ),
    ]


def _acquisition_status(data: "MarketData") -> ValidationStatus:
    """
    The acquisition-time status for a value no adapter reported.

    A live acquisition is UNVERIFIABLE because one source cannot cross-validate
    itself. A fixture is SINGLE_SOURCE because it declares what it is.
    """
    return (
        ValidationStatus.UNVERIFIABLE
        if data.source_type == SourceType.API_LIVE.value
        else ValidationStatus.SINGLE_SOURCE
    )


def _observed_currency(
    data: "MarketData",
    source: Optional[Observation],
) -> Tuple[Optional[str], str]:
    """The currency a value is denominated in, and how that was determined."""
    if source is not None:
        if source.currency:
            return source.currency, source.currency_basis
        if source.currency_basis == CurrencyBasis.INSTRUMENT_DEFAULT.value:
            return (source.currency, source.currency_basis)
    if data.currency:
        return data.currency, CurrencyBasis.REPORTED.value
    return None, CurrencyBasis.UNDECLARED.value


def _observation_raw(
    data: "MarketData",
    metric: str,
    source: Optional[Observation],
    is_band: bool,
) -> Any:
    """
    The payload behind a value, so it can be recomputed or audited.

    An adapter's raw payload is preferred. A band that arrived as a static
    fixture has no samples, and that absence is stated rather than implied.
    """
    if source is not None and source.raw is not None:
        return source.raw
    if metric == METRIC_CONSENSUS_FORWARD_EPS and data.consensus_forward_eps_period:
        # The estimate period is the source's own label, not a fiscal period.
        return {"period": data.consensus_forward_eps_period}
    if is_band:
        band = getattr(data, VIEW_FIELD_FOR_METRIC[metric], None)
        return {
            "fixture_as_of": data.price_date,
            "samples_preserved": False,
            "declared_observations": (
                band.get("observations") if isinstance(band, dict) else None
            ),
        }
    return None


def _absent_observation(
    data: "MarketData",
    metric: str,
    source: Optional[Observation],
    unit: str,
    is_band: bool,
) -> Observation:
    """
    The observation for a metric the source did not return.

    The value is None and stays None. No default, no related metric, no zero.
    An absent multiple is still dimensionless, so its currency basis is
    NOT_APPLICABLE rather than UNDECLARED.
    """
    if is_band:
        currency: Optional[str] = None
        currency_basis = CurrencyBasis.NOT_APPLICABLE.value
    elif source is not None:
        currency = source.currency
        currency_basis = source.currency_basis
    else:
        currency = None
        currency_basis = CurrencyBasis.UNDECLARED.value

    return unavailable_observation(
        metric=metric,
        provider=(source.provider if source is not None else data.provider),
        # The source observation's own source_type, for the same reason the
        # five arguments beside it already read `source`: a figure that came
        # from a filing is a filed figure, and stamping it with the view's
        # source_type would misreport where it came from. Absent a source
        # observation there is nothing else to read, so the view's stands.
        source_type=(
            source.source_type if source is not None else data.source_type
        ),
        definition=METRIC_DEFINITIONS[metric],
        methodology=(
            source.methodology
            if source is not None
            else FIXTURE_METHODOLOGY
        ),
        retrieved_at=data.retrieved_at,
        unit=unit,
        currency=currency,
        currency_basis=currency_basis,
        source_url=(
            source.source_url if source is not None else data.price_source_url
        ),
    )


def material_observations(data: "MarketData") -> Dict[str, Observation]:
    """
    The observation behind every material metric, in evidence order.

    The value always comes from the view field the engine reads, so a direct
    assignment to a MarketData field stays authoritative. The provenance always
    comes from the adapter's observation, so the raw payload, the declared
    period, the source URL, and the availability basis survive into the
    contract view.
    """
    indexed = _observations_by_metric(data)
    result: Dict[str, Observation] = {}

    for metric in MATERIAL_METRICS:
        if metric == METRIC_PRICE:
            result[metric] = price_observations(data)[0]
            continue

        field_name = VIEW_FIELD_FOR_METRIC[metric]
        value = _normalize_observed_value(getattr(data, field_name, None))
        source = indexed.get(metric)
        is_band = metric in BAND_METRICS
        unit = Unit.MULTIPLE.value if is_band else METRIC_UNITS[metric]

        if value is None:
            result[metric] = _absent_observation(
                data, metric, source, unit, is_band
            )
            continue

        if is_band:
            currency, currency_basis = None, CurrencyBasis.NOT_APPLICABLE.value
        else:
            currency, currency_basis = _observed_currency(data, source)

        # A band is computed by us from samples, so it has no single moment at
        # which it became available. The samples' own availability is what is
        # undetermined, and that is recorded in the payload.
        available_at = (
            None
            if is_band
            else (source.available_at if source is not None else None)
        )
        available_at_basis = (
            AvailabilityBasis.UNDECLARED.value
            if is_band
            else (
                source.available_at_basis
                if source is not None
                else AvailabilityBasis.UNDECLARED.value
            )
        )

        result[metric] = build_observation(
            metric=metric,
            value=dict(value) if is_band else value,
            unit=unit,
            provider=(source.provider if source is not None else data.provider),
            # The source observation's own source_type. `status` and
            # `status_reasons` immediately below already come from the source
            # for the same reason, and `provider`, `methodology`, `currency`
            # and `source_url` all read it too: when an adapter supplied this
            # figure, the source it declared is the provenance of record, and
            # the view's own source_type describes a different acquisition.
            source_type=(
                source.source_type if source is not None else data.source_type
            ),
            definition=METRIC_DEFINITIONS[metric],
            methodology=(
                source.methodology
                if source is not None
                else FIXTURE_METHODOLOGY
            ),
            retrieved_at=data.retrieved_at,
            currency=currency,
            currency_basis=currency_basis,
            period_start=(source.period_start if source is not None else None),
            period_end=(source.period_end if source is not None else None),
            as_of=(source.as_of if source is not None else None),
            available_at=available_at,
            available_at_basis=available_at_basis,
            source_url=(
                source.source_url
                if source is not None
                else data.price_source_url
            ),
            raw=_observation_raw(data, metric, source, is_band),
            observation_count=(
                _declared_observations(value, source) if is_band else None
            ),
            status=(
                source.status if source is not None else _acquisition_status(data)
            ),
            status_reasons=(
                source.status_reasons if source is not None else ()
            ),
        )

    return result


def _declared_observations(band: Any, source: Optional[Observation]) -> Optional[int]:
    """
    The sample size a band declares.

    A band that declares no count stays None, which is what keeps a static
    regression fixture usable as a reference: refusing a fixture for not
    declaring its sample size would be refusing honest data.
    """
    declared = band.get("observations") if isinstance(band, dict) else None
    if is_number(declared):
        return int(declared)
    if source is not None and source.observation_count is not None:
        return source.observation_count
    return None


def metrics_observation(
    data: "MarketData",
    metrics: Dict[str, Any],
) -> Observation:
    """
    The derived price/volume metrics observation.

    It records the raw series it was computed from and names the observations
    those series came from, so the numbers can be recomputed rather than
    trusted.
    """
    indexed = _observations_by_metric(data)
    price_history = indexed.get(METRIC_PRICE_HISTORY)
    volume_history = indexed.get(METRIC_VOLUME_HISTORY)

    inputs = tuple(
        observation_id
        for observation_id in (
            OBSERVATION_ID_PRICE_HISTORY if price_history else None,
            OBSERVATION_ID_VOLUME_HISTORY if volume_history else None,
        )
        if observation_id
    )

    return build_observation(
        metric=METRIC_PRICE_VOLUME_METRICS,
        value=metrics,
        unit=Unit.RATIO.value,
        provider="Python",
        source_type=SourceType.DETERMINISTIC_CALCULATION.value,
        definition=METRIC_DEFINITIONS[METRIC_PRICE_VOLUME_METRICS],
        methodology=METRICS_METHODOLOGY,
        retrieved_at=data.retrieved_at,
        currency=data.currency or None,
        currency_basis=(
            CurrencyBasis.REPORTED.value
            if data.currency
            else CurrencyBasis.UNDECLARED.value
        ),
        available_at=data.price_date,
        available_at_basis=AvailabilityBasis.OBSERVATION_INSTANT.value,
        raw={
            "prices": list(data.price_history),
            "volumes": list(data.volume_history),
        },
        status=ValidationStatus.VALID,
        inputs=inputs,
    )


def validation_record(observation: Observation) -> Any:
    """
    The validation outcome for an observation.

    It is a record, not a serializer: it labels the observation and carries no
    value of its own. `now` is the retrieval instant, so the result is
    reproducible rather than dependent on when the test happens to run.
    """
    return validate_observation(observation, now=observation.retrieved_at)


def validate_for_snapshot(observation: Observation) -> Dict[str, Any]:
    return validation_record(observation).contract_dict()


def legacy_evidence_row(
    data: "MarketData",
    metric: str,
    observation: Observation,
) -> LegacyEvidenceRow:
    """
    The 2.2.3 evidence row for one observation.

    Reproduced field for field so existing snapshots and existing evidence
    assertions do not change. See `LegacyEvidenceRow` for why the currency
    stamp and the shared `as_of` are a presentation projection rather than the
    contract view.
    """
    if metric == METRIC_PRICE:
        return LegacyEvidenceRow(
            provider=data.provider,
            source=data.price_source,
            source_url=data.price_source_url,
            as_of=data.price_date,
            unit=data.currency,
            currency=data.currency,
            quality=(
                "High"
                if data.source_type == SourceType.REGRESSION_FIXTURE.value
                else "Medium"
            ),
            traceability="High",
        )

    if metric == METRIC_PRICE_VOLUME_METRICS:
        return LegacyEvidenceRow(
            provider="Python",
            source="Deterministic calculation",
            source_url=None,
            as_of=data.price_date,
            unit="ratio",
            currency=data.currency,
            quality="High",
            traceability="High",
        )

    available = observation.is_available
    return LegacyEvidenceRow(
        provider=data.provider if available else "None",
        source="Input data",
        source_url=None,
        as_of=data.price_date,
        unit="multiple" if metric in BAND_METRICS else data.currency,
        currency=data.currency,
        quality="Medium" if available else "Unavailable",
        traceability="Medium" if available else "Unavailable",
    )


def describe_derived_values(
    data: "MarketData",
    analysis: Optional[Dict[str, Any]] = None,
) -> List[DerivedValue]:
    """
    The derived values of a run, with the observations each one consumed.

    This describes the numbers the engine already produced. It adds no formula
    and changes no result; it records which observations a derived value came
    from so the arithmetic is auditable.
    """
    observations = material_observations(data)
    derived: List[DerivedValue] = []

    for metric in BAND_METRICS:
        observation = observations.get(metric)
        if observation is None or not observation.is_available:
            continue
        recomputed = recompute_distribution(observation)
        derived.append(
            DerivedValue(
                name=metric,
                value=observation.value,
                unit=Unit.MULTIPLE.value,
                currency=None,
                method=(
                    "distribution_from_samples(raw.samples)"
                    if recomputed
                    else "static band; samples not preserved, not recomputable"
                ),
                inputs=(observation.observation_id,),
            )
        )

    price_observation = observations.get(METRIC_PRICE)
    indexed = _observations_by_metric(data)
    price_history = indexed.get(METRIC_PRICE_HISTORY)
    volume_history = indexed.get(METRIC_VOLUME_HISTORY)
    metrics_value = data.observations.value_for(
        METRIC_PRICE_VOLUME_METRICS, default=None
    )
    if metrics_value is None:
        metrics_value = compute_price_volume_metrics(
            data.price_history,
            data.volume_history,
        )
    derived.append(
        DerivedValue(
            name=METRIC_PRICE_VOLUME_METRICS,
            value=metrics_value,
            unit=Unit.RATIO.value,
            currency=data.currency or None,
            method="compute_price_volume_metrics(raw.prices, raw.volumes)",
            inputs=tuple(
                observation_id
                for observation_id in (
                    OBSERVATION_ID_PRICE_HISTORY if price_history else None,
                    OBSERVATION_ID_VOLUME_HISTORY if volume_history else None,
                )
                if observation_id
            ),
        )
    )

    if analysis is None or price_observation is None:
        return derived

    implied = analysis.get("implied_assumptions") or {}
    currency = data.currency or None
    price_evidence_id = price_observation.observation_id

    def implied_value(name: str, value: Any, method: str) -> None:
        derived.append(
            DerivedValue(
                name=name,
                value=value,
                unit=Unit.PER_SHARE.value,
                currency=currency,
                method=method,
                inputs=(price_evidence_id,),
            )
        )

    implied_value(
        "forward_eps_at_reference_multiple",
        implied.get("forward_eps_at_reference_multiple"),
        "price / reference.multiple",
    )
    implied_value(
        "eps_gap_vs_consensus",
        implied.get("eps_gap_vs_consensus"),
        "forward_eps_at_reference_multiple / consensus_forward_eps - 1",
    )
    implied_value(
        "required_eps_cagr_from_current_eps",
        implied.get("required_eps_cagr_from_current_eps"),
        "(forward_eps_at_reference_multiple / current_eps)"
        " ** (1 / horizon_years) - 1",
    )

    for name, method, base in (
        (
            "fcf_at_reference_multiple",
            "market_cap / implied_assumptions.reference_multiples.pfcf",
            METRIC_MARKET_CAP,
        ),
        (
            "ebitda_at_reference_multiple",
            "enterprise_value / implied_assumptions.reference_multiples.ev_ebitda",
            METRIC_ENTERPRISE_VALUE,
        ),
        (
            "revenue_at_reference_multiple",
            "market_cap / implied_assumptions.reference_multiples.ps",
            METRIC_MARKET_CAP,
        ),
    ):
        derived.append(
            DerivedValue(
                name=name,
                value=implied.get(name),
                unit=Unit.CURRENCY.value,
                currency=currency,
                method=method,
                inputs=(price_evidence_id, observation_id_for(base)),
            )
        )

    return derived


def _latest_accepted(candidates: Sequence[Observation]) -> Optional[Observation]:
    """
    The most recently accepted of `candidates`, by the contract's own key.

    The key is the one `ObservationSet.latest_knowable` sorts on --
    `(available_at, as_of)` -- reused here *without* its two filters, because a
    view projection must not have them.

    `latest_knowable` was the obvious choice for this and is wrong here, which
    this function's existence records. It excludes an observation whose
    `available_at` is undeclared, and it excludes one that is not
    `is_available`, and it returns None rather than falling back. Both filters
    are right for deciding which fact crosses into the engine -- undeclared data
    must not look contemporaneous, and an unavailable row must not be presented
    as a value -- and both are wrong for rebuilding the view, because the view's
    field *is* what the live run wrote, including the fields it wrote as
    UNAVAILABLE. Substituting it dropped two replay-fidelity tests
    (`test_archive_replay.py:662` and `:739`, which assert a live run
    reproduces) by discarding archived rows that faithfully recorded an
    unavailable or undated field.

    So the ordering is taken from the contract's selector and the candidate set
    from `latest`, and this function is the only place that distinction lives.

    The tie-break matches `latest_knowable` exactly -- sort, then take the last
    of equals -- and that matters. On the MU archive 298 revenue rows share
    only 65 distinct `available_at` values, because one filing reports an
    annual, three quarters and year-to-date figures that all become knowable at
    the same acceptance instant, so almost every selection is a tie. Taking the
    first of equals instead of the last picks a different fact: at 2026-06-30 it
    yields 41,456,000,000 where `latest_knowable`, and therefore admission,
    yields 78,959,000,000. Two selectors that disagree under a tie are exactly
    the second answer that 2.14 measured, so the tie-break is reproduced rather
    than improved.

    Making the tie-break *total* -- by `observation_id`, say -- would remove the
    remaining dependence on input order, but it would change
    `latest_knowable`, and therefore admission rules 9 and 10. It is recorded
    here rather than taken.

    3.32 examined that proposal and rejected it on evidence. Measured on the MU
    archive, `observation_id` as a third level changes the selection for 8 of 18
    metrics, and for `revenue` it prefers a quarter stub over the annual from the
    same filing -- a selection rule 7 then refuses with `PERIOD_NOT_DISCRETE`,
    so the change would turn an admission into a refusal. The exposure is
    quantified in `selector_tie_break_ambiguity_332.py` and its committed
    record; the candidate is still the obvious next question, and it is still
    the wrong answer for this reason.
    """
    if not candidates:
        return None
    ordered = sorted(
        candidates,
        key=lambda observation: (
            observation.available_at or "",
            observation.as_of or "",
        ),
    )
    return ordered[-1]


def _apply_observations_to_view(
    data: "MarketData",
    observations: Sequence[Observation],
    as_of: Optional[str] = None,
) -> "MarketData":
    """
    Project an observation set onto the 2.2.3 view fields.

    The view stays authoritative for the engine and for the JSON, and the
    observations stay authoritative for provenance. A field the observation
    set does not carry keeps the sentinel it already had, so nothing is
    invented here either.

    `as_of` says whether this is a point-in-time rebuild. Given a cutoff, a
    metric may have several contract ids competing -- SEC ingest mints an id
    per fact, so the per-`contract_id` collapse in `observations_for` cannot
    reduce them -- and the field is filled by the most recently accepted
    candidate rather than the first. Without a cutoff the caller is projecting
    one acquisition's own observations back onto the view they came from, where
    canonical per-metric ids leave one row per metric and first-match is
    unchanged.
    """
    observation_set = ObservationSet(ticker=data.ticker, observations=observations)

    def select(metric: str) -> Optional[Observation]:
        matches = [item for item in observations if item.metric == metric]
        available = [item for item in matches if item.is_available]
        candidates = available or matches
        if as_of is None:
            return candidates[0] if candidates else None
        return _latest_accepted(candidates)

    for metric, field_name in VIEW_FIELD_FOR_METRIC.items():
        if metric == METRIC_PRICE:
            continue
        observation = select(metric)
        if observation is None:
            continue
        if observation.is_band:
            value = observation.value if isinstance(observation.value, dict) else {}
            setattr(data, field_name, dict(value))
        else:
            setattr(
                data,
                field_name,
                observation.value
                if observation.is_available
                else UNAVAILABLE,
            )

    consensus = select(METRIC_CONSENSUS_FORWARD_EPS)
    if consensus is not None and isinstance(consensus.raw, dict):
        period = consensus.raw.get("period")
        data.consensus_forward_eps_period = (
            str(period) if period is not None else None
        )

    data.observations = observation_set
    return data


class YahooFinanceProvider:
    name = "YahooFinance"

    def fetch(self, ticker: str) -> Optional[MarketData]:
        clean = ticker.upper().strip()
        url = (
            "https://query1.finance.yahoo.com/v8/finance/chart/"
            f"{clean}?range=3mo&interval=1d"
        )
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 ST-EVA/2.0"},
        )

        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                payload = json.loads(response.read().decode("utf-8"))

            result = (payload.get("chart", {}).get("result") or [None])[0]
            if not result:
                return None

            meta = result.get("meta", {})
            timestamps = result.get("timestamp") or []
            quote = (result.get("indicators", {}).get("quote") or [{}])[0]

            prices = [float(x) for x in quote.get("close", []) if is_number(x)]
            volumes = [float(x) for x in quote.get("volume", []) if is_number(x)]

            price = safe_float(meta.get("regularMarketPrice"))
            if price is None and prices:
                price = prices[-1]
            if price is None:
                return None

            if timestamps:
                price_date = datetime.fromtimestamp(
                    int(timestamps[-1]), tz=timezone.utc
                ).date().isoformat()
            else:
                price_date = datetime.now(timezone.utc).date().isoformat()

            currency = str(meta.get("currency", "USD"))
            retrieved_at = utc_now()

            # The fundamentals adapter is the only component that knows Yahoo
            # field names. It returns provider-agnostic observations.
            acquisition = YahooFundamentalProvider().fetch_acquisition(
                clean,
                instrument_currency=currency,
            )

            market_data = MarketData(
                ticker=clean,
                company_name=f"{clean} (Live Acquired)",
                exchange=str(meta.get("exchangeName", "Unknown")),
                currency=currency,
                price=price,
                price_date=price_date,
                price_source="Yahoo Finance chart API",
                price_source_url=url,
                price_history=prices,
                volume_history=volumes,
                source_type=SourceType.API_LIVE.value,
                provider=f"{self.name}+{acquisition.provider}",
                errors=list(acquisition.errors),
                retrieved_at=retrieved_at,
            )

            _apply_observations_to_view(
                market_data,
                price_observations(market_data, timestamps)
                + list(acquisition.observations),
            )

            market_data.discrepancy_status = _derive_discrepancy_status(market_data)
            return market_data
        except Exception as error:
            print(
                f"[ST-EVA] Yahoo acquisition failed for {clean}: {error}",
                file=sys.stderr,
            )
            return None


class CompanyResolver:
    @staticmethod
    def resolve(query: str, mode: str = "auto") -> Optional[MarketData]:
        key = query.upper().strip()

        if mode != "live":
            aliases = {
                "0700.HK": "TENCENT",
                "TENCENT": "TENCENT",
                "騰訊": "TENCENT",
                "MSFT": "MSFT",
                "MICROSOFT": "MSFT",
                "NU": "NU",
                "NU HOLDINGS": "NU",
            }
            fixture_key = aliases.get(key)
            if fixture_key:
                return CompanyResolver._from_fixture(
                    REGRESSION_TEST_FIXTURES[fixture_key]
                )

        return YahooFinanceProvider().fetch(key)

    @staticmethod
    def _from_fixture(data: Dict[str, Any]) -> MarketData:
        market_data = MarketData(
            ticker=data["ticker"],
            company_name=data["company_name"],
            exchange=data["exchange"],
            currency=data["currency"],
            price=float(data["price"]),
            price_date=data["price_date"],
            price_source=data["price_source"],
            price_source_url=data.get("price_source_url"),
            price_history=list(data.get("price_history", [])),
            volume_history=list(data.get("volume_history", [])),
            current_eps=data.get("current_eps", UNAVAILABLE),
            forward_eps=data.get("forward_eps", UNAVAILABLE),
            consensus_forward_eps=data.get("consensus_forward_eps", UNAVAILABLE),
            next_event=data.get("next_event", UNAVAILABLE),
            next_event_status=data.get("next_event_status", "Unconfirmed"),
            historical_pe_band=dict(data.get("historical_pe_band", {})),
            current_fcf=data.get("current_fcf", UNAVAILABLE),
            current_ebitda=data.get("current_ebitda", UNAVAILABLE),
            current_revenue=data.get("current_revenue", UNAVAILABLE),
            current_enterprise_value=data.get("current_enterprise_value", UNAVAILABLE),
            current_market_cap=data.get("current_market_cap", UNAVAILABLE),
            historical_ps_band=dict(data.get("historical_ps_band", {})),
            historical_pfcf_band=dict(data.get("historical_pfcf_band", {})),
            historical_ev_ebitda_band=dict(data.get("historical_ev_ebitda_band", {})),
            source_type=data.get("source_type", "REGRESSION_FIXTURE"),
            provider=data.get("provider", "RegressionFixture"),
        )
        return _apply_observations_to_view(
            market_data,
            price_observations(market_data),
        )


class DeterministicMetricsEngine:
    """
    Price and volume statistics.

    The arithmetic lives in the contract module so the derived metrics can be
    recomputed from the raw series recorded in the metrics observation, rather
    than being trusted because a summary was stored.
    """

    @staticmethod
    def compute(
        prices: Sequence[float],
        volumes: Sequence[float],
    ) -> Dict[str, Any]:
        return compute_price_volume_metrics(prices, volumes)


def band_is_usable_for_reference(
    band: Optional[Dict[str, Any]],
) -> bool:
    """
    A band is usable as a valuation reference only when it carries enough
    observations to support a percentile reading.

    A band that declares no observation count is treated as usable, which
    preserves existing regression fixtures and explicit user input.
    """
    if not band:
        return False
    observations = safe_float(band.get("observations"))
    if observations is None:
        return True
    return observations >= MIN_BAND_OBSERVATIONS_FOR_REFERENCE


def band_median_for_reference(
    band: Optional[Dict[str, Any]],
) -> Optional[float]:
    if not band_is_usable_for_reference(band):
        return None
    return safe_float((band or {}).get("median"))


def band_status(
    band: Optional[Dict[str, Any]],
) -> str:
    if not band or not safe_float((band or {}).get("median")):
        return "UNAVAILABLE"
    if band_is_usable_for_reference(band):
        return "USABLE_FOR_REFERENCE"
    return "DESCRIPTIVE_ONLY_INSUFFICIENT_OBSERVATIONS"


def interpolate_pe_percentile(
    value: float,
    band: Dict[str, Any],
) -> Optional[float]:
    if not band_is_usable_for_reference(band):
        return None

    points = [
        (10.0, safe_float(band.get("10th"))),
        (25.0, safe_float(band.get("25th"))),
        (50.0, safe_float(band.get("median"))),
        (75.0, safe_float(band.get("75th"))),
        (90.0, safe_float(band.get("90th"))),
    ]

    observed = [(p, v) for p, v in points if v is not None]
    if len(observed) < 2:
        return None

    for index in range(1, len(observed)):
        left_p, left_v = observed[index - 1]
        right_p, right_v = observed[index]
        if left_v >= right_v:
            return None
        if value <= right_v:
            if value <= left_v:
                return left_p
            return left_p + (right_p - left_p) * (
                (value - left_v) / (right_v - left_v)
            )

    return observed[-1][0]



class MarketImpliedAssumptionsEngine:
    """
    Reverse valuation engine.

    Price alone does not reveal one unique fundamental forecast.
    Every implied earnings/growth result is therefore conditional on
    an explicitly reported valuation multiple.
    """

    @staticmethod
    def analyze(
        data: Any,
        reference_multiple: Optional[float] = None,
        horizon_years: float = 1.0,
        pfcf_multiple: Optional[float] = None,
        ev_ebitda_multiple: Optional[float] = None,
        ps_multiple: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Reverse-engineer the assumptions implied by the observed price.

        `data` is either a `ValuationInputs`, which is the provider-agnostic
        contract projection, or a 2.2.3 `MarketData` view, which is converted.
        The arithmetic below is identical in both cases: the engine cannot tell
        which provider the numbers came from, because it never sees one.
        """
        inputs = (
            data
            if isinstance(data, ValuationInputs)
            else ValuationInputs.from_legacy_view(data)
        )

        if inputs.price <= 0:
            raise ValueError("Current price must be positive.")
        if horizon_years <= 0:
            raise ValueError("horizon_years must be positive.")

        current_eps = safe_float(inputs.current_eps)
        forward_eps = safe_float(inputs.forward_eps)
        consensus_eps = safe_float(inputs.consensus_forward_eps)
        current_fcf = safe_float(inputs.current_fcf)
        current_ebitda = safe_float(inputs.current_ebitda)
        current_revenue = safe_float(inputs.current_revenue)
        enterprise_value = safe_float(inputs.current_enterprise_value)
        market_cap = safe_float(inputs.current_market_cap)

        pe_band = inputs.historical_pe_band or {}
        ps_band = inputs.historical_ps_band or {}
        pfcf_band = inputs.historical_pfcf_band or {}
        ev_band = inputs.historical_ev_ebitda_band or {}

        historical_median = band_median_for_reference(pe_band)
        historical_ps_median = band_median_for_reference(ps_band)
        historical_pfcf_median = band_median_for_reference(pfcf_band)
        historical_ev_ebitda_median = band_median_for_reference(ev_band)

        for value in (reference_multiple, pfcf_multiple, ev_ebitda_multiple, ps_multiple):
            if value is not None and value <= 0:
                raise ValueError("Reference multiples must be positive.")

        selected_pe = reference_multiple if reference_multiple is not None else historical_median
        selected_pfcf = pfcf_multiple if pfcf_multiple is not None else historical_pfcf_median
        selected_ev_ebitda = ev_ebitda_multiple if ev_ebitda_multiple is not None else historical_ev_ebitda_median
        selected_ps = ps_multiple if ps_multiple is not None else historical_ps_median

        current_pe = inputs.price / current_eps if current_eps and current_eps > 0 else None
        forward_pe = inputs.price / forward_eps if forward_eps and forward_eps > 0 else None
        consensus_forward_pe = inputs.price / consensus_eps if consensus_eps and consensus_eps > 0 else None

        implied_forward_eps = inputs.price / selected_pe if selected_pe and selected_pe > 0 else None
        eps_gap_vs_consensus = (
            implied_forward_eps / consensus_eps - 1.0
            if implied_forward_eps is not None and consensus_eps and consensus_eps > 0 else None
        )
        required_eps_cagr = (
            (implied_forward_eps / current_eps) ** (1.0 / horizon_years) - 1.0
            if implied_forward_eps is not None and current_eps and current_eps > 0 else None
        )

        current_pfcf = market_cap / current_fcf if market_cap and current_fcf and current_fcf > 0 else None
        implied_fcf = market_cap / selected_pfcf if market_cap and selected_pfcf and selected_pfcf > 0 else None

        current_ev_ebitda = (
            enterprise_value / current_ebitda
            if enterprise_value and current_ebitda and current_ebitda > 0 else None
        )
        implied_ebitda = (
            enterprise_value / selected_ev_ebitda
            if enterprise_value and selected_ev_ebitda and selected_ev_ebitda > 0 else None
        )

        current_ps = market_cap / current_revenue if market_cap and current_revenue and current_revenue > 0 else None
        implied_revenue = market_cap / selected_ps if market_cap and selected_ps and selected_ps > 0 else None
        implied_net_margin = (
            (implied_forward_eps / (implied_revenue / (market_cap / inputs.price)))
            if implied_forward_eps is not None and implied_revenue is not None and market_cap and market_cap > 0
            else None
        )

        pe_percentile = interpolate_pe_percentile(selected_pe, pe_band) if selected_pe is not None else None
        ps_percentile = interpolate_pe_percentile(current_ps, ps_band) if current_ps is not None else None
        ev_ebitda_percentile = interpolate_pe_percentile(current_ev_ebitda, ev_band) if current_ev_ebitda is not None else None

        consensus_price_at_median = (
            consensus_eps * historical_median
            if consensus_eps and historical_median else None
        )

        return {
            "reference": {
                "method": "user_supplied_multiple" if reference_multiple is not None else ("historical_pe_median" if historical_median is not None else "none"),
                "multiple": selected_pe,
                "conditional_statement": "Implied fundamentals are conditional on the selected valuation multiple. Price alone does not identify a unique fundamental path.",
                "historical_band_status": {
                    "pe": band_status(pe_band),
                    "ps": band_status(ps_band),
                    "pfcf": band_status(pfcf_band),
                    "ev_ebitda": band_status(ev_band),
                },
                "min_observations_for_reference": MIN_BAND_OBSERVATIONS_FOR_REFERENCE,
            },
            "observed_valuation": {
                "current_pe": current_pe,
                "forward_pe": forward_pe,
                "consensus_forward_pe": consensus_forward_pe,
                "current_pfcf": current_pfcf,
                "current_ev_ebitda": current_ev_ebitda,
                "current_ps": current_ps,
                "historical_pe_band": pe_band,
                "historical_ps_band": ps_band,
                "historical_pfcf_band": pfcf_band,
                "historical_ev_ebitda_band": ev_band,
                "approx_historical_pe_percentile": pe_percentile,
                "approx_historical_ps_percentile": ps_percentile,
                "approx_historical_ev_ebitda_percentile": ev_ebitda_percentile,
            },
            "implied_assumptions": {
                "forward_eps_at_reference_multiple": implied_forward_eps,
                "eps_gap_vs_consensus": eps_gap_vs_consensus,
                "required_eps_cagr_from_current_eps": required_eps_cagr,
                "required_eps_growth": required_eps_cagr,
                "fcf_at_reference_multiple": implied_fcf,
                "ebitda_at_reference_multiple": implied_ebitda,
                "revenue_at_reference_multiple": implied_revenue,
                "implied_net_margin": implied_net_margin,
                "reference_multiples": {
                    "pe": selected_pe,
                    "pfcf": selected_pfcf,
                    "ev_ebitda": selected_ev_ebitda,
                    "ps": selected_ps,
                },
            },
            "consensus_cross_check": {
                "consensus_forward_eps": consensus_eps,
                "price_at_historical_median_pe": consensus_price_at_median,
                "price_gap_vs_historical_median_on_consensus_eps": (
                    consensus_price_at_median / inputs.price - 1.0
                    if consensus_price_at_median is not None else None
                ),
            },
            "fundamental_snapshot": {
                "current_fcf": inputs.current_fcf,
                "current_ebitda": inputs.current_ebitda,
                "current_revenue": inputs.current_revenue,
                "current_enterprise_value": inputs.current_enterprise_value,
                "current_market_cap": inputs.current_market_cap,
            },
            "source_inputs": {
                "current_eps": inputs.current_eps,
                "forward_eps": inputs.forward_eps,
                "consensus_forward_eps": inputs.consensus_forward_eps,
                "historical_pe_band": pe_band,
                "historical_ps_band": ps_band,
                "historical_ev_ebitda_band": ev_band,
            },
        }



class Validator:
    @staticmethod
    def validate_data(data: MarketData) -> List[str]:
        errors: List[str] = []

        if not data.ticker:
            errors.append("Ticker is empty.")
        if not is_number(data.price) or data.price <= 0:
            errors.append("Price must be a positive finite number.")
        if not data.currency:
            errors.append("Currency is missing.")
        if data.discrepancy_status == "DATA_DISCREPANCY":
            errors.append("DATA_DISCREPANCY detected; analysis stopped.")

        return errors

    @staticmethod
    def validate_evidence(
        evidence: EvidenceStore,
        referenced_ids: Sequence[str],
    ) -> List[str]:
        return [
            f"Unknown Evidence ID: {evidence_id}"
            for evidence_id in referenced_ids
            if evidence.get(evidence_id) is None
        ]

    @staticmethod
    def validate_analysis(analysis: Dict[str, Any]) -> List[str]:
        errors: List[str] = []

        reference_multiple = analysis["reference"]["multiple"]
        if reference_multiple is not None:
            if not is_number(reference_multiple) or reference_multiple <= 0:
                errors.append("Reference multiple must be positive.")

        for key, value in analysis["implied_assumptions"].items():
            if key == "reference_multiples":
                if not isinstance(value, dict):
                    errors.append("reference_multiples must be an object.")
                else:
                    for name, multiple in value.items():
                        if multiple is not None and not is_number(multiple):
                            errors.append(f"reference_multiples.{name} must be numeric or null.")
                continue
            if value is not None and not is_number(value):
                errors.append(f"{key} must be numeric or null.")

        return errors


def build_evidence(
    data: MarketData,
    metrics: Dict[str, Any],
) -> EvidenceStore:
    """
    Bind every material observation to its evidence identity.

    Registration order, evidence IDs, and the 2.2.3 row contents are unchanged.
    What changed is where the values come from: each row now references an
    observation that carries its own provenance and a validation record,
    instead of a value copied out of the view with provenance invented here.
    """
    store = EvidenceStore()
    observations = material_observations(data)

    for metric in EVIDENCE_METRICS:
        if metric == METRIC_PRICE_VOLUME_METRICS:
            observation = metrics_observation(data, metrics)
        else:
            observation = observations[metric]

        store.add(
            Evidence(
                evidence_id=observation.observation_id,
                observation=observation,
                validation=validation_record(observation),
                legacy=legacy_evidence_row(data, metric, observation),
            )
        )

    return store


class SnapshotManager:
    def __init__(self, root: str = "history") -> None:
        self.root = Path(root)

    @staticmethod
    def safe_ticker(ticker: str) -> str:
        return (
            ticker.replace("/", "_")
            .replace(".", "_")
            .replace(":", "_")
        )

    def save(
        self,
        data: MarketData,
        analysis: Dict[str, Any],
        evidence: EvidenceStore,
        metrics: Dict[str, Any],
        horizon_years: float,
        contract: Optional[Dict[str, Any]] = None,
        investment_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        self.root.mkdir(parents=True, exist_ok=True)
        research_id = f"RES-{uuid.uuid4().hex[:10].upper()}"

        record = {
            "research_id": research_id,
            "analysis_type": VERSION_METADATA["analysis_type"],
            "created_at": utc_now(),
            "ticker": data.ticker,
            "company_name": data.company_name,
            "price_date": data.price_date,
            "current_price": data.price,
            "currency": data.currency,
            "horizon_years": horizon_years,
            "version_metadata": VERSION_METADATA,
            "analysis": analysis,
            "market_metrics": metrics,
            "evidence": evidence.as_dict(),
            "limitations": [
                "This is reverse valuation, not a price target.",
                "Implied earnings/growth are conditional on the selected multiple.",
                "Missing financial data is not estimated.",
            ],
        }

        # Additive 2.3-A block. The 2.2.3 keys above are untouched, so an
        # existing snapshot reader and update_outcome keep working.
        if contract is not None:
            record["data_contract"] = contract

        # Additive 2.3-C block, present only when a context was requested.
        if investment_context is not None:
            record["investment_context"] = investment_context

        filename = (
            f"{self.safe_ticker(data.ticker)}_{research_id}_"
            "market_implied_assumptions.json"
        )
        atomic_json_write(self.root / filename, record)
        return research_id

    def update_outcome(
        self,
        research_id: str,
        outcome_data: Dict[str, Any],
    ) -> bool:
        matches = list(
            self.root.glob(
                f"*_{research_id}_market_implied_assumptions.json"
            )
        )
        if not matches:
            return False

        prediction_path = matches[0]
        with prediction_path.open("r", encoding="utf-8") as handle:
            prediction = json.load(handle)

        outcome = {
            "research_id": research_id,
            "analysis_type": prediction.get("analysis_type"),
            "recorded_at": utc_now(),
            "source_snapshot": prediction_path.name,
            "outcome_data": outcome_data,
        }

        timestamp = datetime.now(timezone.utc).strftime(
            "%Y%m%dT%H%M%S%fZ"
        )
        filename = (
            f"{self.safe_ticker(prediction['ticker'])}_"
            f"{research_id}_outcome_{timestamp}.json"
        )
        atomic_json_write(self.root / filename, outcome)
        return True


def run_st_eva(
    ticker: str,
    horizon: str = "1-8 weeks",
    event: Optional[str] = None,
    mode: str = "auto",
    reference_multiple: Optional[float] = None,
    horizon_years: float = 1.0,
    pfcf_multiple: Optional[float] = None,
    ev_ebitda_multiple: Optional[float] = None,
    ps_multiple: Optional[float] = None,
    save_snapshot: bool = True,
    history_dir: str = "history",
    context_path: Optional[str] = None,
    context_sources: Sequence[str] = ("yahoo", "sec"),
    archive: Optional[Any] = None,
) -> Optional[Dict[str, Any]]:
    data = CompanyResolver.resolve(ticker, mode=mode)
    if data is None:
        return None

    data_errors = Validator.validate_data(data)
    if data_errors:
        raise ValueError("; ".join(data_errors))

    metrics = DeterministicMetricsEngine.compute(
        data.price_history,
        data.volume_history,
    )

    evidence = build_evidence(data, metrics)

    analysis = MarketImpliedAssumptionsEngine.analyze(
        data=data,
        reference_multiple=reference_multiple,
        horizon_years=horizon_years,
        pfcf_multiple=pfcf_multiple,
        ev_ebitda_multiple=ev_ebitda_multiple,
        ps_multiple=ps_multiple,
    )

    analysis_errors = Validator.validate_analysis(analysis)
    if analysis_errors:
        raise ValueError("; ".join(analysis_errors))

    evidence_errors = Validator.validate_evidence(
        evidence,
        evidence.ids(),
    )
    if evidence_errors:
        raise ValueError("; ".join(evidence_errors))

    research_id = None
    investment_context = None
    cross_source_observations: List[Any] = []
    captured_documents: List[Any] = []
    if context_path is not None:
        # Opt-in only. Nothing above this line changes when a context is not
        # requested, so the default path is byte-identical to 2.2.3.
        (
            investment_context,
            cross_source_observations,
            captured_documents,
        ) = _build_context_if_requested(
            data=data,
            analysis=analysis,
            evidence=evidence,
            metrics=metrics,
            horizon_years=horizon_years,
            reference_multiple=reference_multiple,
            pfcf_multiple=pfcf_multiple,
            ev_ebitda_multiple=ev_ebitda_multiple,
            ps_multiple=ps_multiple,
            context_sources=context_sources,
        )
        if context_path == "-":
            print(json.dumps(investment_context, ensure_ascii=False, indent=2))
        else:
            atomic_json_write(Path(context_path), investment_context)

        if archive is not None:
            # Opt-in persistence. The archive is a consumer of this run's
            # output, so a failure here is reported rather than swallowed, and
            # it cannot change any number the run already produced.
            _archive_run(
                archive=archive,
                data=data,
                analysis=analysis,
                evidence=evidence,
                metrics=metrics,
                context=investment_context,
                cross_source_observations=cross_source_observations,
                captured_documents=captured_documents,
            )

    if save_snapshot:
        research_id = SnapshotManager(history_dir).save(
            data=data,
            analysis=analysis,
            evidence=evidence,
            metrics=metrics,
            horizon_years=horizon_years,
            contract=data.contract_view(analysis),
            investment_context=investment_context,
        )

    missing_data = []
    for name, value in (
        ("current_eps", data.current_eps),
        ("forward_eps", data.forward_eps),
        ("consensus_forward_eps", data.consensus_forward_eps),
        ("historical_pe_band", data.historical_pe_band),
        ("current_fcf", data.current_fcf),
        ("current_ebitda", data.current_ebitda),
        ("current_revenue", data.current_revenue),
        ("current_enterprise_value", data.current_enterprise_value),
        ("current_market_cap", data.current_market_cap),
        ("historical_ps_band", data.historical_ps_band),
        ("historical_pfcf_band", data.historical_pfcf_band),
        ("historical_ev_ebitda_band", data.historical_ev_ebitda_band),
    ):
        if value in (None, UNAVAILABLE, {}):
            missing_data.append(name)

    return {
        "analysis_type": VERSION_METADATA["analysis_type"],
        "research_id": research_id,
        "ticker": data.ticker,
        "company_name": data.company_name,
        "as_of": data.price_date,
        "horizon": horizon,
        "event": {
            "name": event,
            "date": data.next_event,
            "status": data.next_event_status,
        },
        "market_snapshot": {
            "price": data.price,
            "currency": data.currency,
            "exchange": data.exchange,
            "provider": data.provider,
            "source": data.price_source,
            "source_type": data.source_type,
        },
        "data_quality": {
            "discrepancy_status": data.discrepancy_status,
            "acquisition_errors": data.errors,
            "consensus_forward_eps_period": data.consensus_forward_eps_period,
        },
        "observed_valuation": analysis["observed_valuation"],
        "market_implied_assumptions": analysis["implied_assumptions"],
        "consensus_cross_check": analysis["consensus_cross_check"],
        "fundamental_snapshot": analysis["fundamental_snapshot"],
        "reference": analysis["reference"],
        "market_metrics": metrics,
        "missing_data": missing_data,
        "evidence_ids": evidence.ids(),
        "validation": {
            "status": "PASSED",
            "validator_version": VERSION_METADATA["validator_version"],
        },
        "limitations": [
            "Current price does not uniquely identify one future fundamental path.",
            "Reverse-engineered earnings/growth are conditional on the selected valuation multiple.",
            "ST-EVA does not invent EPS, consensus, probabilities, or target prices.",
            "This output is descriptive valuation analysis, not a buy/sell signal.",
        ],
        "version_metadata": VERSION_METADATA,
    }


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_regression_tests() -> None:
    print("=== ST-EVA 2.0 Regression Tests ===")

    for ticker in ("TENCENT", "MSFT", "NU"):
        result = run_st_eva(
            ticker,
            mode="regression",
            save_snapshot=False,
        )
        assert_true(result is not None, f"{ticker}: result missing")
        assert_true(
            result["analysis_type"] == "market_implied_assumptions",
            f"{ticker}: wrong analysis type",
        )
        assert_true(
            result["market_implied_assumptions"][
                "forward_eps_at_reference_multiple"
            ] is not None,
            f"{ticker}: implied EPS missing",
        )
        print(f"[PASS] {ticker}")

    data = CompanyResolver.resolve("MSFT", mode="regression")
    assert_true(data is not None, "MSFT fixture missing")

    analysis = MarketImpliedAssumptionsEngine.analyze(
        data,
        reference_multiple=30.0,
    )

    assert_true(
        abs(
            analysis["implied_assumptions"][
                "forward_eps_at_reference_multiple"
            ]
            - (425.50 / 30.0)
        ) < 1e-9,
        "Implied EPS arithmetic failed",
    )

    assert_true(
        abs(
            analysis["observed_valuation"]["consensus_forward_pe"]
            - (425.50 / 13.20)
        ) < 1e-9,
        "Consensus P/E arithmetic failed",
    )

    print("[PASS] Reverse valuation arithmetic")

    no_fundamental_data = MarketData(
        ticker="TEST",
        company_name="Test",
        exchange="TEST",
        currency="USD",
        price=100.0,
        price_date="2026-01-01",
        price_source="test",
        price_source_url=None,
        price_history=[100.0, 101.0],
        volume_history=[1000.0, 1100.0],
    )

    analysis = MarketImpliedAssumptionsEngine.analyze(
        no_fundamental_data,
        reference_multiple=20.0,
    )

    assert_true(
        analysis["implied_assumptions"][
            "forward_eps_at_reference_multiple"
        ] == 5.0,
        "Reference-multiple implied EPS failed",
    )

    assert_true(
        analysis["implied_assumptions"]["eps_gap_vs_consensus"] is None,
        "Synthetic consensus was created",
    )

    print("[PASS] Zero synthetic financial data")

    assert_true(
        run_st_eva(
            "UNKNOWN_XYZ",
            mode="live",
            save_snapshot=False,
        )
        is None,
        "Unknown ticker should return None",
    )

    print("[PASS] Unknown ticker handling")
    print("=== ALL TESTS PASSED ===")


def _archive_run(
    archive: Any,
    data: MarketData,
    analysis: Dict[str, Any],
    evidence: EvidenceStore,
    metrics: Dict[str, Any],
    context: Optional[Dict[str, Any]],
    cross_source_observations: Sequence[Any] = (),
    captured_documents: Sequence[Any] = (),
) -> Any:
    """
    Persist one run: its observations, then its context.

    Every observation the context used is archived, including the ones a second
    source contributed. Archiving a subset would leave the snapshot referencing
    facts the archive has never seen, and it could not be replayed.

    The context is archived after the observations, because a snapshot that
    references facts the archive has never seen is a snapshot that cannot be
    replayed.
    """
    from archive import ArchiveStats, StoredDocument

    asset = data.ticker
    archive.record_asset(
        asset,
        name=data.company_name,
        exchange=data.exchange,
        currency=data.currency,
    )
    archive.record_source(
        data.provider,
        data.source_type,
        base_url=data.price_source_url,
    )

    # The documents first: an observation may only link to a document that was
    # captured, and a dangling link looks like evidence and is not.
    documents_recorded = 0
    for document in captured_documents:
        archive.record_source_document(
            StoredDocument(
                content_hash=document.content_hash,
                uri=document.uri,
                canonical_uri=document.uri,
                http_status=document.http_status,
                media_type=document.media_type,
                byte_size=document.byte_size,
                fetched_at=document.fetched_at,
                first_seen_at=document.fetched_at,
                payload=document.payload,
                provider=document.provider,
                document_type=document.document_type,
            )
        )
        documents_recorded += 1

    recorded = 0
    for observation in material_observations(data).values():
        archive.record_observation(asset, observation)
        recorded += 1
    archive.record_observation(asset, metrics_observation(data, metrics))
    recorded += 1
    for identifier in (
        OBSERVATION_ID_PRICE_HISTORY,
        OBSERVATION_ID_VOLUME_HISTORY,
    ):
        observation = data.observations.get(identifier)
        if observation is not None:
            archive.record_observation(asset, observation)
            recorded += 1
    for observation in cross_source_observations:
        archive.record_observation(
            asset, observation, document_hashes=_document_hashes_of(observation)
        )
        recorded += 1
    for observation in (
        data.observations.get(identifier)
        for identifier in data.observations.ids()
    ):
        if observation is not None and is_comparable_observation(observation):
            archive.record_observation(
                asset,
                observation,
                document_hashes=_document_hashes_of(observation),
            )
            recorded += 1

    if context is not None:
        fidelity = (
            "OBSERVATIONAL"
            if _uses_first_seen_observations(archive, context)
            else "SOURCE_DECLARED"
        )
        archive.record_context(asset, context, replay_fidelity=fidelity)

    for evidence_id in evidence.ids():
        entry = evidence.get(evidence_id)
        if entry is None:
            continue
        archive.record_validation(
            {
                "observation_id": entry.observation.observation_id,
                "kind": "single_source",
                "status": entry.validation.status.value,
                "reasons": list(entry.validation.reasons),
                "explanation": entry.validation.explanation,
                "references": [evidence_id],
                "checked_at": entry.validation.checked_at,
            }
        )

    stats = ArchiveStats(
        observations_recorded=recorded,
        documents_recorded=documents_recorded,
    )
    return stats


def _document_hashes_of(observation: Observation) -> List[str]:
    """
    The documents an observation was read out of.

    Recorded by the adapter that read them. A URL is not a stable reference to
    a fact: SEC data is updated as filings are disseminated and a filing can
    be corrected after acceptance, so only the exact version served can say
    what the number came from.
    """
    raw = observation.raw if isinstance(observation.raw, dict) else {}
    hashes = raw.get("source_document_hashes")
    if not isinstance(hashes, (list, tuple)):
        return []
    return [str(item) for item in hashes if item]


def _uses_first_seen_observations(
    archive: Any,
    context: Dict[str, Any],
) -> bool:
    """
    Whether any observation the context used was archive-dated rather than
    source-dated.

    A single flag on the document would be a scalar over provenance, so it is
    computed here from the per-observation classes and the per-observation
    class remains the source of truth.
    """
    classes = getattr(archive, "availability_classes", None)
    if not callable(classes):
        return False
    available = classes(context["asset"]["ticker"])
    for ref in (context.get("provenance", {}).get("refs") or {}):
        kind, _, identifier = ref.partition(":")
        if kind != "obs":
            continue
        if available.get(identifier) == "ARCHIVE_FIRST_SEEN":
            return True
    return False


def market_data_from_observations(
    observations: Sequence[Observation],
    ticker: str,
    company_name: str = "",
    exchange: str = "",
    as_of: Optional[str] = None,
) -> Optional[MarketData]:
    """
    Rebuild the 2.2.3 view from an archived observation set.

    The inverse of `material_observations`, and the seam that lets a replay run
    the ordinary pipeline instead of a second implementation of it.

    Every material field is read from an observation, so a replayed run sees the
    same inputs the archived run did. A field no observation carries keeps the
    sentinel it had; nothing is invented here either.

    Returns None when no price observation is present, because a view without a
    price is not a view. The caller decides what an absent price means.

    `as_of` is the replay cutoff. It is threaded from the caller that has one,
    and it is what turns the first-match read below into a most-recently-
    accepted one. See `_latest_accepted` for why the contract's
    `latest_knowable` is the wrong selector at this site.

    The rows handed in are expected to be the ones the archive returned for
    `as_of`. `archive.replay` obtains them from `observations_for(asset,
    as_of)`, which has already dropped everything not eligible at the cutoff,
    and this function does not filter again -- filtering here is what
    `latest_knowable` does, and it is the half of that behaviour that breaks a
    rebuild. A caller passing rows the archive would not have returned at that
    instant is passing rows this cannot recognise as ineligible.
    """
    if not observations:
        return None

    # The view is built from the *material* observations only. A second source
    # reports the same metric names, and letting one of those win here would
    # silently replace the engine's input with another provider's figure —
    # exactly the dependency 2.3-B exists to prevent.
    material = [
        item for item in observations if not is_comparable_observation(item)
    ] or list(observations)

    def latest(metric: str) -> Optional[Observation]:
        matches = [item for item in material if item.metric == metric]
        available = [item for item in matches if item.is_available]
        candidates = available or matches
        if as_of is None:
            return candidates[0] if candidates else None
        return _latest_accepted(candidates)

    price_observation = latest(METRIC_PRICE)
    if price_observation is None or not is_number(price_observation.value):
        return None

    history_observation = latest(METRIC_PRICE_HISTORY)
    volume_observation = latest(METRIC_VOLUME_HISTORY)
    price_history = (
        list(history_observation.value)
        if history_observation is not None
        and isinstance(history_observation.value, list)
        else []
    )
    volume_history = (
        list(volume_observation.value)
        if volume_observation is not None
        and isinstance(volume_observation.value, list)
        else []
    )

    market_data = MarketData(
        ticker=ticker,
        company_name=company_name or ticker,
        exchange=exchange,
        currency=str(price_observation.currency or ""),
        price=float(price_observation.value),
        price_date=str(price_observation.as_of or price_observation.period_end),
        # The 2.3-A price observation records `methodology` from the view's
        # `price_source`, so reading it back is what makes the round trip
        # faithful. Using the provider id instead would silently rewrite the
        # provenance of every replayed price.
        price_source=price_observation.methodology or price_observation.provider,
        price_source_url=price_observation.source_url,
        price_history=price_history,
        volume_history=volume_history,
        source_type=price_observation.source_type,
        provider=price_observation.provider,
        retrieved_at=price_observation.retrieved_at,
    )
    projected = _apply_observations_to_view(market_data, material, as_of=as_of)
    # The observation set carries the comparable observations too, so the 2.3-C
    # builder can register them and resolve the cross-source references, exactly
    # as a live run does. The view *fields* stay material-derived, so a second
    # source can never replace the engine's input.
    projected.observations = ObservationSet(
        ticker=ticker, observations=list(observations)
    )
    return projected


def build_context_from_observations(
    observations: Sequence[Observation],
    ticker: str,
    as_of: str,
    generated_at: str,
    company_name: str = "",
    exchange: str = "",
    asset_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Run the ordinary 2.3-C pipeline over an archived observation set.

    Replay calls this, so a replayed document is produced by exactly the code a
    live run uses. Nothing about the pipeline knows it is replaying; that is the
    point.

    `asset_metadata` carries what the archive knows about the instrument, so a
    replayed context does not diverge from the archived one over a company
    name.
    """
    from investment_context import build_investment_context

    metadata = asset_metadata or {}
    data = market_data_from_observations(
        observations,
        ticker=ticker,
        company_name=company_name or (metadata.get("name") or ""),
        exchange=exchange or (metadata.get("exchange") or ""),
        # The cutoff travels with the rebuild, so a metric with competing
        # contract ids is resolved by most recently accepted rather than by
        # position in the archive's ordering. It was already an argument here
        # and reached nothing.
        as_of=as_of,
    )
    if data is None:
        raise ValueError(
            "the archived observation set carries no price, so no context can "
            "be built. A replay must not substitute one."
        )

    metrics = DeterministicMetricsEngine.compute(
        data.price_history,
        data.volume_history,
    )
    evidence = build_evidence(data, metrics)
    analysis = MarketImpliedAssumptionsEngine.analyze(data=data)

    # The cross-source verdicts are recomputed from whichever comparable
    # observations were eligible, so a replay reaches the same verdict the
    # archived run did rather than a stale one.
    cross_validation: Dict[str, Any] = {}
    comparable = [
        observation
        for observation in observations
        if is_comparable_observation(observation)
    ]
    # A filing-sourced observation is the second-source set. A market-data
    # one is the vendor side, which feeds the comparison but is not itself a
    # document section; mixing them in would make a replayed context carry
    # observations the original run did not include.
    filing = [
        observation
        for observation in comparable
        if observation.source_type == SourceType.REGULATORY_FILING.value
    ]
    vendor = [
        observation
        for observation in comparable
        if observation.source_type != SourceType.REGULATORY_FILING.value
    ]
    if comparable:
        from cross_validation import cross_validate_all

        cross_validation = cross_validate_all(vendor, filing)

    return build_investment_context(
        data=data,
        analysis=analysis,
        evidence=evidence,
        metrics=metrics,
        # The price/volume metrics observation is built inside build_evidence
        # rather than living in the view, so it is passed explicitly. Using the
        # same constructor guarantees the two agree on its identity.
        material_observations=list(material_observations(data).values())
        + [metrics_observation(data, metrics)],
        extra_observations=filing,
        cross_validation=cross_validation,
        generated_at=generated_at,
        cik=metadata.get("cik"),
        sec_entity_name=metadata.get("sec_entity_name"),
    )


def _build_context_if_requested(
    data: MarketData,
    analysis: Dict[str, Any],
    evidence: EvidenceStore,
    metrics: Dict[str, Any],
    horizon_years: float,
    reference_multiple: Optional[float],
    pfcf_multiple: Optional[float],
    ev_ebitda_multiple: Optional[float],
    ps_multiple: Optional[float],
    context_sources: Sequence[str],
) -> Any:
    """
    Assemble an Investment Context, reaching the SEC only when asked to.

    Returns the document, the observations a second source contributed, and the
    source documents fetched. All three go to the archive: a snapshot that
    references facts the archive never saw cannot be replayed, and an
    observation that does not name the document it came from is a number with
    an unverifiable origin.

    The cross-source pass is network-bound, so it happens on the opt-in path
    only. A context built without it is still a valid document: the
    cross-source verdicts are simply absent, and the consumer can see that
    because the section reports which sources it covers.
    """
    from investment_context import build_investment_context

    sources = {str(source).lower() for source in (context_sources or ())}
    cross_validation: Dict[str, Any] = {}
    sec_observations: List[Any] = []
    sec_documents: List[Any] = []
    cik: Optional[str] = None
    sec_entity_name: Optional[str] = None

    if "sec" in sources:
        from cross_validation import cross_validate_all
        from sec_provider import SECProvider

        acquisition = SECProvider().fetch(data.ticker)
        if acquisition.company is not None:
            cik = acquisition.company.cik
            sec_entity_name = acquisition.company.name
        sec_observations = list(acquisition.observations)
        sec_documents = list(acquisition.documents)
        vendor = [
            observation
            for observation in (
                data.observations.get(identifier)
                for identifier in data.observations.ids()
            )
            if observation is not None
            and is_comparable_observation(observation)
        ]
        cross_validation = cross_validate_all(
            vendor,
            acquisition.observations,
        )

    return build_investment_context(
        data=data,
        analysis=analysis,
        evidence=evidence,
        metrics=metrics,
        # The price/volume metrics observation is built inside build_evidence
        # rather than living in the view, so it is passed explicitly. Using the
        # same constructor guarantees the two agree on its identity.
        material_observations=list(material_observations(data).values())
        + [metrics_observation(data, metrics)],
        extra_observations=sec_observations,
        horizon_years=horizon_years,
        reference_multiple=reference_multiple,
        pfcf_multiple=pfcf_multiple,
        ev_ebitda_multiple=ev_ebitda_multiple,
        ps_multiple=ps_multiple,
        cross_validation=cross_validation,
        cik=cik,
        sec_entity_name=sec_entity_name,
    ), sec_observations, sec_documents


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "ST-EVA: reverse-engineer market-implied assumptions "
            "from the current price."
        )
    )
    parser.add_argument(
        "ticker",
        nargs="?",
        help="Ticker, e.g. AAPL, MSFT, 0700.HK",
    )
    parser.add_argument(
        "--mode",
        choices=("auto", "live", "regression"),
        default="auto",
    )
    parser.add_argument(
        "--reference-multiple",
        type=float,
        default=None,
        help="Explicit P/E reference used for reverse valuation.",
    )
    parser.add_argument(
        "--horizon-years",
        type=float,
        default=1.0,
        help="Horizon used for required EPS CAGR.",
    )
    parser.add_argument("--pfcf-multiple", type=float, default=None)
    parser.add_argument("--ev-ebitda-multiple", type=float, default=None)
    parser.add_argument("--ps-multiple", type=float, default=None)
    parser.add_argument("--event", default=None)
    parser.add_argument("--horizon", default="1-8 weeks")
    parser.add_argument("--no-snapshot", action="store_true")
    parser.add_argument("--test", action="store_true")
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Print machine-readable JSON instead of the readable report.",
    )
    parser.add_argument(
        "--context",
        dest="context_path",
        nargs="?",
        const="-",
        default=None,
        metavar="PATH",
        help=(
            "Opt-in: also write a 2.3-C Investment Context. Use '-' for "
            "stdout. Without this flag the output is unchanged."
        ),
    )
    parser.add_argument(
        "--context-sources",
        dest="context_sources",
        nargs="+",
        choices=("yahoo", "sec"),
        default=("yahoo", "sec"),
        metavar="SOURCE",
        help=(
            "Which acquired sources feed the Investment Context. 'sec' "
            "enables the cross-source comparison and is the only part that "
            "uses the network."
        ),
    )
    parser.add_argument(
        "--archive",
        dest="archive_path",
        nargs="?",
        const="data/st-eva.sqlite",
        default=None,
        metavar="PATH",
        help=(
            "Opt-in: persist this run's observations and context to a "
            "persistent archive for point-in-time replay. Without this flag "
            "the output is unchanged."
        ),
    )

    args = parser.parse_args()

    resolve_console_encoding()

    if args.test or not args.ticker:
        run_regression_tests()
        if not args.ticker:
            return

    archive = None
    if args.archive_path:
        from sqlite_archive import SQLiteArchive

        archive = SQLiteArchive(args.archive_path)

    result = run_st_eva(
        ticker=normalize_ticker(args.ticker),
        horizon=args.horizon,
        event=args.event,
        mode=args.mode,
        reference_multiple=args.reference_multiple,
        horizon_years=args.horizon_years,
        pfcf_multiple=args.pfcf_multiple,
        ev_ebitda_multiple=args.ev_ebitda_multiple,
        ps_multiple=args.ps_multiple,
        save_snapshot=not args.no_snapshot,
        context_path=args.context_path,
        context_sources=args.context_sources,
        archive=archive,
    )

    if result is None:
        raise SystemExit(
            f"ST-EVA could not acquire usable market data for "
            f"'{args.ticker}'. Check the ticker symbol, or use --mode regression "
            f"for a static fixture."
        )

    if args.context_path == "-":
        # The context was already written to stdout; printing the report as
        # well would corrupt the document for a consumer piping it.
        return

    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_report(result)


if __name__ == "__main__":
    main()
