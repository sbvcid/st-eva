from __future__ import annotations

"""
ST-EVA research runner.

Purpose:
    Answer "What assumptions are embedded in the current price?"

The runner acquires market and financial evidence, validates observations,
performs deterministic valuation and reverse calculations, and optionally
builds a Research Dossier, Investment Context, or archive record.

Data flow:

    Provider -> Observation -> Evidence -> Validation -> Derived

The engine consumes `ValuationInputs`, a provider-agnostic projection of the
observations. It never reads a provider's own field names.

Observed inputs remain distinct from deterministic calculations and
conditional inferences. Missing values are not fabricated, and validation
labels a value without rewriting the source observation.
"""

import argparse
import json
import os
import sys
import tempfile
import urllib.request
import uuid
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from data_contract import (
    AvailabilityBasis,
    BAND_METRICS,
    CurrencyBasis,
    DERIVED_METRICS,
    DerivedValue,
    EVIDENCE_METRICS,
    Evidence,
    EvidenceStore,
    LegacyEvidenceRow,    MATERIAL_METRICS,
    METRIC_CONSENSUS_FORWARD_EPS,
    METRIC_CONSENSUS_FORWARD_EPS_30D_AGO,
    METRIC_CONSENSUS_FORWARD_EPS_60D_AGO,
    METRIC_CONSENSUS_FORWARD_EPS_7D_AGO,
    METRIC_CONSENSUS_FORWARD_EPS_90D_AGO,
    METRIC_CONSENSUS_FORWARD_EPS_ANALYST_COUNT,
    METRIC_CONSENSUS_FORWARD_EPS_HIGH,
    METRIC_CONSENSUS_FORWARD_EPS_LOW,
    METRIC_CONSENSUS_FORWARD_EPS_TREND_CURRENT,
    METRIC_CONSENSUS_REVISION_AMOUNT_30D,
    METRIC_CONSENSUS_REVISION_AMOUNT_60D,
    METRIC_CONSENSUS_REVISION_AMOUNT_7D,
    METRIC_CONSENSUS_REVISION_AMOUNT_90D,
    METRIC_CONSENSUS_REVISIONS_DOWN_30D,
    METRIC_CONSENSUS_REVISIONS_DOWN_7D,
    METRIC_CONSENSUS_REVISIONS_DOWN_90D,
    METRIC_CONSENSUS_REVISIONS_UP_30D,
    METRIC_CONSENSUS_REVISIONS_UP_7D,
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
    effective_currency,
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
from reverse_requirements import ANCHOR_FORWARD, ANCHOR_TTM
from sec_derived_inputs import TTM_WINDOW_METRICS
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
    consensus_forward_eps_analyst_count: Any = UNAVAILABLE
    consensus_forward_eps_low: Any = UNAVAILABLE
    consensus_forward_eps_high: Any = UNAVAILABLE
    consensus_forward_eps_up_revisions_7d: Any = UNAVAILABLE
    consensus_forward_eps_up_revisions_30d: Any = UNAVAILABLE
    consensus_forward_eps_down_revisions_7d: Any = UNAVAILABLE
    consensus_forward_eps_down_revisions_30d: Any = UNAVAILABLE
    consensus_forward_eps_down_revisions_90d: Any = UNAVAILABLE
    consensus_forward_eps_trend_current: Any = UNAVAILABLE
    consensus_forward_eps_7d_ago: Any = UNAVAILABLE
    consensus_forward_eps_30d_ago: Any = UNAVAILABLE
    consensus_forward_eps_60d_ago: Any = UNAVAILABLE
    consensus_forward_eps_90d_ago: Any = UNAVAILABLE
    consensus_forward_eps_change_7d: Any = UNAVAILABLE
    consensus_forward_eps_change_30d: Any = UNAVAILABLE
    consensus_forward_eps_change_60d: Any = UNAVAILABLE
    consensus_forward_eps_change_90d: Any = UNAVAILABLE
    consensus_forward_eps_period: Optional[str] = None
    # The fiscal-period end the source declared for that consensus estimate.
    # None when the source declared none; never inferred from the label.
    consensus_forward_eps_period_end: Optional[str] = None
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
    chart_events: Optional[Dict[str, Any]] = None

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
        "company_name": "擉啗??扯 (Tencent Holdings Limited)",
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
    # AAPL is a frozen sample of the values the live run observed, so the offline
    # research flow reproduces the same market-implied assumptions without a
    # provider call. The price is the canonical historical P/E dataset's last
    # daily close (verifiable and tracked); the trailing EPS carries the source
    # identity of the observation it was captured from, not the fixture's.
    "AAPL": {
        "ticker": "AAPL",
        "company_name": "Apple Inc.",
        "exchange": "NASDAQ",
        "currency": "USD",
        "price": 333.63,
        "price_date": "2026-10-06",
        "price_source": "YahooFinance chart API daily close (canonical AAPL historical P/E dataset)",
        "price_source_url": "https://query1.finance.yahoo.com/v8/finance/chart/AAPL",
        "current_eps": 8.72,
        "forward_eps": UNAVAILABLE,
        "consensus_forward_eps": UNAVAILABLE,
        "next_event": UNAVAILABLE,
        "next_event_status": "Unconfirmed",
        # No synthetic band: the exit multiples come from the promoted canonical
        # production historical P/E distribution loaded via include_historical_pe.
        "historical_pe_band": {},
        "price_history": [329.40, 333.02, 330.32, 333.69, 332.89, 333.63],
        "volume_history": [38478000, 49988600, 36306300, 33278600, 34400900, 30425700],
        "source_type": "REGRESSION_FIXTURE",
        "provider": "RegressionFixture",
        "retrieved_at": "2026-10-13",
        "observations": [
            {
                "metric": "trailing_eps",
                "value": 8.72,
                "unit": "per_share",
                "provider": "YahooFinanceFundamentals",
                "source_type": "API_LIVE",
                "source_url": "https://query2.finance.yahoo.com/v10/finance/quoteSummary/AAPL",
                "definition": "Current/trailing EPS. Never synthesized.",
                "methodology": "Yahoo quoteSummary defaultKeyStatistics.trailingEps",
                "currency": "USD",
                "currency_basis": "PER_SHARE",
                "available_at_basis": "UNDECLARED",
                "raw": {"module": "defaultKeyStatistics", "field": "trailingEps", "asOfDate": None},
            }
        ],
    },
    # SOFI is a frozen sample of the values the live run observed, so the
    # offline research flow reproduces the same market-implied assumptions
    # without a provider call. The price is the canonical historical P/E
    # dataset's last daily close (verifiable and tracked); the EPS values
    # carry the source identity of the observations they were captured from,
    # not the fixture's. The vendor historical P/E band is carried exactly as
    # captured: at five observations it is below the reference threshold, so
    # the exit multiples must come from the production historical P/E
    # distribution rather than from the band.
    "SOFI": {
        "ticker": "SOFI",
        "company_name": "SoFi Technologies, Inc.",
        "exchange": "NASDAQ",
        "currency": "USD",
        "price": 14.505,
        "price_date": "2026-10-19",
        "price_source": "YahooFinance chart API daily close (canonical SOFI historical P/E dataset)",
        "price_source_url": "https://query1.finance.yahoo.com/v8/finance/chart/SOFI",
        "current_eps": 0.49,
        "forward_eps": 0.82459,
        "consensus_forward_eps": 0.82459,
        "next_event": UNAVAILABLE,
        "next_event_status": "Unconfirmed",
        "historical_pe_band": {
            "10th": 34.012244800000005,
            "25th": 34.367347,
            "median": 37.183673,
            "75th": 45.04,
            "90th": 49.17999999999999,
            "observations": 5,
        },
        "price_history": [15.23, 15.24, 14.22, 15.09, 14.55, 14.505],
        "volume_history": [40615900, 31007100, 92173600, 62946600, 59576000, 39614900],
        "source_type": "REGRESSION_FIXTURE",
        "provider": "RegressionFixture",
        "retrieved_at": "2026-10-20",
        "observations": [
            {
                "metric": "trailing_eps",
                "value": 0.49,
                "unit": "per_share",
                "provider": "YahooFinanceFundamentals",
                "source_type": "API_LIVE",
                "source_url": "https://query2.finance.yahoo.com/v10/finance/quoteSummary/SOFI",
                "definition": "Current/trailing EPS. Never synthesized.",
                "methodology": "Yahoo quoteSummary defaultKeyStatistics.trailingEps",
                "currency": "USD",
                "currency_basis": "INSTRUMENT_DEFAULT",
                "available_at_basis": "UNDECLARED",
                "raw": {"module": "defaultKeyStatistics", "field": "trailingEps", "asOfDate": None},
            },
            {
                "metric": "forward_eps",
                "value": 0.82459,
                "unit": "per_share",
                "provider": "YahooFinanceFundamentals",
                "source_type": "API_LIVE",
                "source_url": "https://query2.finance.yahoo.com/v10/finance/quoteSummary/SOFI",
                "definition": "Forward EPS. Used only when explicitly supplied.",
                "methodology": "Yahoo quoteSummary defaultKeyStatistics.forwardEps",
                "currency": "USD",
                "currency_basis": "INSTRUMENT_DEFAULT",
                "available_at_basis": "UNDECLARED",
                "raw": {"module": "defaultKeyStatistics", "field": "forwardEps", "asOfDate": None},
            },
            {
                "metric": "consensus_forward_eps",
                "value": 0.82459,
                "unit": "per_share",
                "provider": "YahooFinanceFundamentals",
                "source_type": "API_LIVE",
                "source_url": "https://query2.finance.yahoo.com/v10/finance/quoteSummary/SOFI",
                "definition": "Consensus forward EPS. Never synthesized.",
                "methodology": "Yahoo quoteSummary earningsTrend trend[period].earningsEstimate.avg",
                "currency": "USD",
                "currency_basis": "INSTRUMENT_DEFAULT",
                "available_at_basis": "UNDECLARED",
                "period_end": "2027-12-31",
                "raw": {
                    "module": "earningsTrend",
                    "field": "trend[].earningsEstimate.avg",
                    "period": "+1y",
                    "period_end": "2027-12-31",
                },
            },
        ],
    },
    # MUFG is a frozen sample of the values the live run observed, so the
    # cross-currency analysis is reproducible without a provider call. The
    # price, the market cap and the EPS are the ADR's USD figures; the revenue
    # is the issuer's JPY figure, and it is declared in JPY on purpose: the
    # unconverted ratio of a USD market cap to a JPY revenue is not a
    # same-currency ratio and must be refused rather than computed. The
    # SEC diluted EPS the analysis converts is a filing fact, and it is
    # packaged under data/cross_currency/MUFG/ with the filing that reported
    # it.
    "MUFG": {
        "ticker": "MUFG",
        "company_name": "Mitsubishi UFJ Financial Group, Inc.",
        "exchange": "NYQ",
        "currency": "USD",
        "price": 21.86,
        "price_date": "2026-10-19",
        "price_source": "Yahoo Finance chart API (captured live)",
        "price_source_url": "https://query1.finance.yahoo.com/v8/finance/chart/MUFG",
        "current_eps": 1.53,
        "forward_eps": 1.03,
        "consensus_forward_eps": 1.73994,
        "next_event": UNAVAILABLE,
        "next_event_status": "Unconfirmed",
        "historical_pe_band": {
            "10th": 12.1810018,
            "25th": 13.0091245,
            "75th": 15.22507525,
            "90th": 15.3911782,
            "median": 14.349626,
            "observations": 8,
        },
        "historical_ps_band": {
            "10th": 3.2336862,
            "25th": 3.363264,
            "75th": 5.177896,
            "90th": 5.2410038000000005,
            "median": 3.917369,
            "observations": 9,
        },
        "current_revenue": 7863006000000.0,
        "current_market_cap": 258756499250.0,
        "price_history": [22.35, 22.4, 21.88, 21.86, 21.88, 21.86],
        "volume_history": [2407600.0, 3452000.0, 3197000.0, 2998500.0, 2755500.0, 38314.0],
        "source_type": "REGRESSION_FIXTURE",
        "provider": "RegressionFixture",
        "retrieved_at": "2026-10-19",
        "observations": [
            {
                "metric": "trailing_eps",
                "value": 1.53,
                "unit": "per_share",
                "provider": "YahooFinanceFundamentals",
                "source_type": "API_LIVE",
                "source_url": "https://query2.finance.yahoo.com/v10/finance/quoteSummary/MUFG",
                "definition": "Current/trailing EPS. Never synthesized.",
                "methodology": "Yahoo quoteSummary defaultKeyStatistics.trailingEps",
                "currency": "USD",
                "currency_basis": "INSTRUMENT_DEFAULT",
                "available_at_basis": "UNDECLARED",
                "raw": {"module": "defaultKeyStatistics", "field": "trailingEps", "asOfDate": None},
            },
            {
                "metric": "forward_eps",
                "value": 1.03,
                "unit": "per_share",
                "provider": "YahooFinanceFundamentals",
                "source_type": "API_LIVE",
                "source_url": "https://query2.finance.yahoo.com/v10/finance/quoteSummary/MUFG",
                "definition": "Forward EPS. Used only when explicitly supplied.",
                "methodology": "Yahoo quoteSummary defaultKeyStatistics.forwardEps",
                "currency": "USD",
                "currency_basis": "INSTRUMENT_DEFAULT",
                "available_at_basis": "UNDECLARED",
                "raw": {"module": "defaultKeyStatistics", "field": "forwardEps", "asOfDate": None},
            },
            {
                "metric": "consensus_forward_eps",
                "value": 1.73994,
                "unit": "per_share",
                "provider": "YahooFinanceFundamentals",
                "source_type": "API_LIVE",
                "source_url": "https://query2.finance.yahoo.com/v10/finance/quoteSummary/MUFG",
                "definition": "Consensus forward EPS. Never synthesized.",
                "methodology": "Yahoo quoteSummary earningsTrend trend[period].earningsEstimate.avg",
                "currency": "USD",
                "currency_basis": "INSTRUMENT_DEFAULT",
                "available_at_basis": "UNDECLARED",
                "period_end": "2028-03-31",
                "raw": {
                    "module": "earningsTrend",
                    "field": "trend[].earningsEstimate.avg",
                    "period": "+1y",
                    "period_end": "2028-03-31",
                },
            },
            {
                "metric": "revenue",
                "value": 7863006000000.0,
                "unit": "currency",
                "provider": "YahooFinanceFundamentals",
                "source_type": "API_LIVE",
                "source_url": "https://query1.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/MUFG",
                "definition": "Observed trailing revenue. Never synthesized.",
                "methodology": "Yahoo fundamentals-timeseries trailingTotalRevenue",
                "currency": "JPY",
                "currency_basis": "REPORTED",
                "available_at_basis": "UNDECLARED",
                "period_end": "2026-06-30",
                "raw": {"module": "fundamentals-timeseries", "field": "trailingTotalRevenue"},
            },
            {
                "metric": "market_cap",
                "value": 258756499250.0,
                "unit": "currency",
                "provider": "YahooFinanceFundamentals",
                "source_type": "API_LIVE",
                "source_url": "https://query1.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/MUFG",
                "definition": "Observed market capitalisation.",
                "methodology": "Yahoo fundamentals-timeseries trailingMarketCap",
                "currency": "USD",
                "currency_basis": "REPORTED",
                "available_at_basis": "UNDECLARED",
                "period_end": "2026-09-23",
                "raw": {"module": "fundamentals-timeseries", "field": "trailingMarketCap"},
            },
        ],
    },
}


def _derive_discrepancy_status(data: "MarketData") -> str:
    """
    Classify the evidence quality of an acquired dataset.

    This is an evidence state, not an investment rating. A single provider
    cannot verify itself, so a successful live single-source acquisition is
    reported as SINGLE_SOURCE rather than silently trusted; acquisition
    failure or missing required data remains UNVERIFIABLE.
    """
    if data.errors:
        return ValidationStatus.UNVERIFIABLE.value
    if data.discrepancy_status == ValidationStatus.DISCREPANT.value:
        return "DATA_DISCREPANCY"
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
    METRIC_CONSENSUS_FORWARD_EPS_ANALYST_COUNT: "consensus_forward_eps_analyst_count",
    METRIC_CONSENSUS_FORWARD_EPS_LOW: "consensus_forward_eps_low",
    METRIC_CONSENSUS_FORWARD_EPS_HIGH: "consensus_forward_eps_high",
    METRIC_CONSENSUS_REVISIONS_UP_7D: "consensus_forward_eps_up_revisions_7d",
    METRIC_CONSENSUS_REVISIONS_UP_30D: "consensus_forward_eps_up_revisions_30d",
    METRIC_CONSENSUS_REVISIONS_DOWN_7D: "consensus_forward_eps_down_revisions_7d",
    METRIC_CONSENSUS_REVISIONS_DOWN_30D: "consensus_forward_eps_down_revisions_30d",
    METRIC_CONSENSUS_REVISIONS_DOWN_90D: "consensus_forward_eps_down_revisions_90d",
    METRIC_CONSENSUS_FORWARD_EPS_TREND_CURRENT: (
        "consensus_forward_eps_trend_current"
    ),
    METRIC_CONSENSUS_FORWARD_EPS_7D_AGO: "consensus_forward_eps_7d_ago",
    METRIC_CONSENSUS_FORWARD_EPS_30D_AGO: "consensus_forward_eps_30d_ago",
    METRIC_CONSENSUS_FORWARD_EPS_60D_AGO: "consensus_forward_eps_60d_ago",
    METRIC_CONSENSUS_FORWARD_EPS_90D_AGO: "consensus_forward_eps_90d_ago",
    METRIC_CONSENSUS_REVISION_AMOUNT_7D: "consensus_forward_eps_change_7d",
    METRIC_CONSENSUS_REVISION_AMOUNT_30D: "consensus_forward_eps_change_30d",
    METRIC_CONSENSUS_REVISION_AMOUNT_60D: "consensus_forward_eps_change_60d",
    METRIC_CONSENSUS_REVISION_AMOUNT_90D: "consensus_forward_eps_change_90d",
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

# The consensus estimate's own sample: the analyst count and the low/high ends of
# the range, which the source states on the same trend row as the average it
# publishes. Carried to the context as extra observations rather than as material
# evidence, so the 2.2.3 evidence array and its order are unchanged.
CONSENSUS_SAMPLE_METRICS: Tuple[str, ...] = (
    METRIC_CONSENSUS_FORWARD_EPS_ANALYST_COUNT,
    METRIC_CONSENSUS_FORWARD_EPS_LOW,
    METRIC_CONSENSUS_FORWARD_EPS_HIGH,
)

# The revision counts, the same row's trend series, and the deterministic
# differences inside that series. Each is tied to the forecast period and the
# declared period end of the selected consensus row, so it travels with the
# estimate it belongs to, as extra observations that never enter the evidence
# array. A revision count and an EPS amount are different quantities and stay
# in different metrics.
CONSENSUS_REVISION_METRICS: Tuple[str, ...] = (
    METRIC_CONSENSUS_REVISIONS_UP_7D,
    METRIC_CONSENSUS_REVISIONS_UP_30D,
    METRIC_CONSENSUS_REVISIONS_DOWN_7D,
    METRIC_CONSENSUS_REVISIONS_DOWN_30D,
    METRIC_CONSENSUS_REVISIONS_DOWN_90D,
)

CONSENSUS_TREND_METRICS: Tuple[str, ...] = (
    METRIC_CONSENSUS_FORWARD_EPS_TREND_CURRENT,
    METRIC_CONSENSUS_FORWARD_EPS_7D_AGO,
    METRIC_CONSENSUS_FORWARD_EPS_30D_AGO,
    METRIC_CONSENSUS_FORWARD_EPS_60D_AGO,
    METRIC_CONSENSUS_FORWARD_EPS_90D_AGO,
)

CONSENSUS_REVISION_AMOUNT_METRICS: Tuple[str, ...] = (
    METRIC_CONSENSUS_REVISION_AMOUNT_7D,
    METRIC_CONSENSUS_REVISION_AMOUNT_30D,
    METRIC_CONSENSUS_REVISION_AMOUNT_60D,
    METRIC_CONSENSUS_REVISION_AMOUNT_90D,
)

CONSENSUS_EXTRA_METRICS: Tuple[str, ...] = (
    CONSENSUS_SAMPLE_METRICS
    + CONSENSUS_REVISION_METRICS
    + CONSENSUS_TREND_METRICS
    + CONSENSUS_REVISION_AMOUNT_METRICS
)

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


def _packaged_sec_diluted_eps(ticker: str) -> Optional[Dict[str, Any]]:
    """
    The ticker's packaged SEC diluted-EPS fact, if it has one.

    The per-ticker archive under `data/archives/` is a local, gitignored
    directory. A CI checkout does not have one, so a product fact read from
    there is present on one machine and missing on another, and the analysis
    that needs it is silently incomplete rather than loudly wrong. The
    packaged dataset is the tracked copy of the same facts: the value, the
    filing that reported it, the fiscal period and the acceptance instant.

    The selection is the same one the archive query made: the latest fact by
    period end. A missing dataset is not an error here; the caller falls back
    to the archive.
    """
    path = Path("data/cross_currency") / ticker.upper() / "sec_filing_facts.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    facts = payload.get("facts") or []
    if not facts:
        return None
    ordered = sorted(
        facts,
        key=lambda f: (f.get("period_end") or "", f.get("accession") or ""),
        reverse=True,
    )
    return ordered[0]


def _observed_currency(
    data: "MarketData",
    source: Optional[Observation],
) -> Tuple[Optional[str], str]:
    """
    The currency a value is denominated in, and how that was determined.

    The rule is the contract's `effective_currency`, the one the engine also
    uses to judge a ratio between two figures. The archive and the engine
    therefore cannot mint a currency for a figure and then judge a different
    one for it, which is what would let a faithful rebuild differ from the run
    it is rebuilding.
    """
    return effective_currency(source, data.currency)


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
    if metric == METRIC_CONSENSUS_FORWARD_EPS and (
        data.consensus_forward_eps_period
        or data.consensus_forward_eps_period_end
    ):
        # The estimate period is the source's own label, not a fiscal period,
        # and the period end is the date the same source declared. Neither is
        # derived from the other.
        payload: Dict[str, Any] = {
            "period": data.consensus_forward_eps_period
        }
        if data.consensus_forward_eps_period_end:
            payload["period_end"] = data.consensus_forward_eps_period_end
        return payload
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

        # Only a monetary value is denominated in something. A band is a
        # multiple and a count is a count, so the instrument's currency is not
        # theirs to carry -- stamping it onto them would assert a denomination
        # the value does not have.
        if unit in (Unit.CURRENCY.value, Unit.PER_SHARE.value):
            currency, currency_basis = _observed_currency(data, source)
        else:
            currency, currency_basis = None, CurrencyBasis.NOT_APPLICABLE.value

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
        # The declared fiscal-period end is read from the archived raw payload
        # and falls back to the observation's own period_end, so a replayed
        # view rebuilds the same declared date the live run recorded rather
        # than dropping it.
        declared_end = (
            consensus.raw.get("period_end") or consensus.period_end
        )
        data.consensus_forward_eps_period_end = (
            str(declared_end) if declared_end else None
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

            # Acquire dividend (and split) events from a longer window so the
            # dividend package is populated for issuers that pay dividends.
            # The price series above stays on its own short window; only the
            # event payload is taken from this request, so price history and
            # momentum metrics are unaffected.
            dividend_events = None
            try:
                div_url = (
                    "https://query1.finance.yahoo.com/v8/finance/chart/"
                    f"{clean}?range=2y&interval=1d&events=div,splits"
                )
                div_request = urllib.request.Request(
                    div_url,
                    headers={"User-Agent": "Mozilla/5.0 ST-EVA/2.0"},
                )
                with urllib.request.urlopen(div_request, timeout=8) as response:
                    div_payload = json.loads(response.read().decode("utf-8"))
                div_result = (div_payload.get("chart", {}).get("result") or [None])[0]
                if div_result:
                    dividend_events = div_result.get("events")
            except Exception:
                dividend_events = None

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
                chart_events=(
                    dividend_events if dividend_events is not None
                    else result.get("events")
                ),
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


def _fixture_declared_observations(data: Dict[str, Any]) -> List[Observation]:
    """Observations a regression fixture declares with their own provenance.

    A fixture is a frozen sample. A value it reproduces may carry the source
    identity of the real observation it was captured from -- provider, source
    type, endpoint, definition, methodology and raw field. Those are declared
    per observation rather than assumed from the fixture's run-level provider,
    so a fixture cannot silently reattribute a value to a different source, and
    a value whose source declared no period stays undeclared.
    """
    result: List[Observation] = []
    for spec in data.get("observations") or []:
        result.append(
            build_observation(
                metric=str(spec["metric"]),
                value=spec.get("value"),
                unit=str(spec.get("unit") or Unit.PER_SHARE.value),
                provider=str(spec.get("provider") or data.get("provider") or "RegressionFixture"),
                source_type=str(
                    spec.get("source_type")
                    or data.get("source_type")
                    or SourceType.REGRESSION_FIXTURE.value
                ),
                definition=str(spec.get("definition") or FIXTURE_METHODOLOGY),
                methodology=str(spec.get("methodology") or FIXTURE_METHODOLOGY),
                retrieved_at=str(spec.get("retrieved_at") or data.get("retrieved_at") or ""),
                currency=spec.get("currency") or data.get("currency"),
                currency_basis=spec.get("currency_basis"),
                period_start=spec.get("period_start"),
                period_end=spec.get("period_end"),
                as_of=spec.get("as_of"),
                available_at=spec.get("available_at"),
                available_at_basis=spec.get("available_at_basis"),
                source_url=spec.get("source_url"),
                raw=spec.get("raw"),
            )
        )
    return result


class CompanyResolver:
    @staticmethod
    def resolve(query: str, mode: str = "auto") -> Optional[MarketData]:
        key = query.upper().strip()

        if mode != "live":
            aliases = {
                "0700.HK": "TENCENT",
                "TENCENT": "TENCENT",
                "擉啗?": "TENCENT",
                "MSFT": "MSFT",
                "MICROSOFT": "MSFT",
                "NU": "NU",
                "NU HOLDINGS": "NU",
                "AAPL": "AAPL",
                "APPLE": "AAPL",
                "SOFI": "SOFI",
                "MUFG": "MUFG",
            }
            fixture_key = aliases.get(key)
            if fixture_key:
                return CompanyResolver._from_fixture(
                    REGRESSION_TEST_FIXTURES[fixture_key]
                )

        return YahooFinanceProvider().fetch(key) or MarketData(
            ticker=key,
            company_name=f"{key} (Live Acquired)",
            exchange="Unknown",
            currency="USD",
            price=UNAVAILABLE,
            price_date="",
            price_source="Yahoo Finance chart API",
            price_source_url=None,
            price_history=[],
            volume_history=[],
            source_type=SourceType.API_LIVE.value,
            provider="YahooFinance",
            errors=["price fetch failed: no price data returned"],
        )

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
            retrieved_at=data.get("retrieved_at", ""),
        )
        return _apply_observations_to_view(
            market_data,
            price_observations(market_data) + _fixture_declared_observations(data),
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
    """A band is usable only when its positive median and sample size are verifiable.

    Delegates to the shared eligibility rule in `reverse_requirements`, so the
    summary's gate and the matrix's scenario gate are one rule, not two.
    """
    from reverse_requirements import band_reference_eligibility

    usable, _ = band_reference_eligibility(
        band, min_observations=MIN_BAND_OBSERVATIONS_FOR_REFERENCE
    )
    return usable


def band_median_for_reference(
    band: Optional[Dict[str, Any]],
) -> Optional[float]:
    if not band_is_usable_for_reference(band):
        return None
    return safe_float((band or {}).get("median"))


def production_pe_for_reference(
    production_historical_pe: Optional[Dict[str, Any]],
) -> Tuple[Optional[float], str]:
    """
    The production historical P/E distribution as a summary reference.

    Returns the distribution's median and its status, or (None, status) when
    the distribution cannot serve as a reference.

    Two things are deliberate here. The gate is the distribution's own
    `usable_for_reference` flag rather than the vendor band's
    `observations >= 20` rule, because the distribution is gated once, where it
    is built, and applying a second and differently-shaped gate here could admit
    a reference the matrix's exit multiples were refused under. And the median
    is read from the distribution's own percentiles rather than recomputed from
    the vendor band or from today's price, so the summary reports the figure
    the reconstruction actually produced.

    A distribution that is merely descriptive stays (None, status): it keeps
    its descriptive status everywhere else and never becomes a qualifying
    reference here.
    """
    distribution = (production_historical_pe or {}).get("distribution") or {}
    status = str(distribution.get("status") or "UNAVAILABLE")
    if distribution.get("usable_for_reference") is not True:
        return None, status
    median = safe_float((distribution.get("percentiles") or {}).get("median"))
    if median is None or median <= 0:
        return None, status
    return median, status


def production_pfcf_for_reference(
    production_historical_pfcf: Optional[Dict[str, Any]],
) -> Tuple[Optional[float], str]:
    """
    The production historical P/FCF distribution as a summary reference.

    The same gate and the same median rule as `production_pe_for_reference`,
    applied to the market-cap-to-free-cash-flow reconstruction: the
    distribution's own `usable_for_reference` flag decides, the median is read
    from the distribution's own percentiles, and a descriptive-only
    distribution keeps (None, status) everywhere.
    """
    distribution = (production_historical_pfcf or {}).get("distribution") or {}
    status = str(distribution.get("status") or "UNAVAILABLE")
    if distribution.get("usable_for_reference") is not True:
        return None, status
    median = safe_float((distribution.get("percentiles") or {}).get("median"))
    if median is None or median <= 0:
        return None, status
    return median, status


def _production_multiples_median_for_reference(
    production_historical_multiples: Optional[Dict[str, Any]],
    metric_id: str,
) -> Tuple[Optional[float], str]:
    """
    One production historical multiples distribution as a summary reference.

    The same gate and the same median rule as `production_pe_for_reference`,
    applied to the P/S and EV/EBITDA distributions the point-in-time
    reconstruction builds: the distribution's own `usable_for_reference` flag
    decides, the median is read from the distribution's own percentiles, and a
    descriptive-only distribution keeps (None, status) everywhere.
    """
    distribution = ((production_historical_multiples or {}).get("distributions") or {}).get(
        metric_id
    ) or {}
    status = str(distribution.get("status") or "UNAVAILABLE")
    if distribution.get("usable_for_reference") is not True:
        return None, status
    median = safe_float((distribution.get("percentiles") or {}).get("median"))
    if median is None or median <= 0:
        return None, status
    return median, status


def production_ps_for_reference(
    production_historical_multiples: Optional[Dict[str, Any]],
) -> Tuple[Optional[float], str]:
    """
    The production historical P/S distribution as a summary reference.

    The same gate and median rule as every other production reference: the
    distribution's own `usable_for_reference` flag decides and the median is
    read from the distribution's own percentiles, never recomputed from the
    vendor band or from today's price.
    """
    return _production_multiples_median_for_reference(
        production_historical_multiples, "P_S_RATIO_REFERENCE"
    )


def production_ev_ebitda_for_reference(
    production_historical_multiples: Optional[Dict[str, Any]],
) -> Tuple[Optional[float], str]:
    """
    The production historical EV/EBITDA distribution as a summary reference.

    The same gate and median rule as the P/S reference above, applied to the
    EV/EBITDA distribution whose bridge evidence the dataset requires.
    """
    return _production_multiples_median_for_reference(
        production_historical_multiples, "EV_EBITDA_RATIO_REFERENCE"
    )


def band_status(
    band: Optional[Dict[str, Any]],
) -> str:
    median = safe_float((band or {}).get("median"))
    if not band or median is None or median <= 0:
        return "UNAVAILABLE"
    observations = safe_float(band.get("observations"))
    if observations is None or observations < 0 or not observations.is_integer():
        return "DESCRIPTIVE_ONLY_UNVERIFIED_SAMPLE_COUNT"
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
        production_historical_pe: Optional[Dict[str, Any]] = None,
        production_historical_pfcf: Optional[Dict[str, Any]] = None,
        production_historical_multiples: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Reverse-engineer the assumptions implied by the observed price.

        `data` is either a `ValuationInputs`, which is the provider-agnostic
        contract projection, or a 2.2.3 `MarketData` view, which is converted.
        The arithmetic below is identical in both cases: the engine cannot tell
        which provider the numbers came from, because it never sees one.

        `production_historical_pe` is the point-in-time historical P/E
        distribution for this asset, as the dedicated reconstruction builds it.
        The engine reads the distribution's own eligibility and its own median,
        and never re-derives either from the vendor band, so the reference the
        summary reports and the reference the matrix's exit multiples were
        admitted under cannot drift apart.

        `production_historical_pfcf` is the same thing for P/FCF: the
        point-in-time market-cap-to-free-cash-flow reconstruction's own
        distribution, gated by its own >= 20 observation rule. It competes for
        the cash-flow reference only when the operator supplied none.

        `production_historical_multiples` is the same thing for P/S and
        EV/EBITDA: the point-in-time sales and enterprise-value
        reconstruction's own distributions, each gated by the shared
        >= 20 observation rule, the EV/EBITDA one additionally requiring the
        complete filed bridge evidence. They compete for their references only
        when the operator supplied none.
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

        # The summary's reference multiple, in precedence order:
        #
        #   1. an explicitly supplied multiple, which is the operator's own
        #      assumption and is never displaced by anything the data says;
        #   2. the production historical P/E distribution's median, when that
        #      distribution is eligible as a reference;
        #   3. the vendor historical P/E band's median, under the existing
        #      >= 20 declared observations rule;
        #   4. nothing, reported as unavailable.
        #
        # The matrix and the summary are different calculations and stay that
        # way, but they cannot disagree about whether a qualified reference
        # exists: when the production distribution is eligible, its median is
        # the reference here and the median of its percentiles is the centre of
        # the matrix's eligible exit multiples.
        production_pe_median, production_pe_status = production_pe_for_reference(
            production_historical_pe
        )
        production_pfcf_median, production_pfcf_status = production_pfcf_for_reference(
            production_historical_pfcf
        )
        production_ps_median, production_ps_status = production_ps_for_reference(
            production_historical_multiples
        )
        production_ev_ebitda_median, production_ev_ebitda_status = (
            production_ev_ebitda_for_reference(production_historical_multiples)
        )
        # The registry's basis for the multiples the references may come from.
        # It travels with the reference so that an archive keeps the standing
        # under which the denominator was read, and so that a later change to
        # the registry's decisions is visible rather than silent.
        from historical_multiples import multiples_qualification_basis

        production_multiples_qualification = multiples_qualification_basis(
            production_historical_multiples
        )

        if reference_multiple is not None:
            selected_pe = reference_multiple
            selected_pe_method = "user_supplied_multiple"
        elif production_pe_median is not None:
            selected_pe = production_pe_median
            selected_pe_method = "production_historical_pe_median"
        elif historical_median is not None:
            selected_pe = historical_median
            selected_pe_method = "historical_pe_median"
        else:
            selected_pe = None
            selected_pe_method = "none"

        # How many observations the selected reference is actually based on, so a
        # consumer never has to guess it from a different object's sample size.
        # Taken from the distribution only when the distribution *is* the
        # reference; a supplier that is not in force has no count to report here.
        production_pe_sample_count = None
        if selected_pe_method == "production_historical_pe_median":
            raw_sample_count = safe_float(
                ((production_historical_pe or {}).get("distribution") or {}).get(
                    "sample_count"
                )
            )
            production_pe_sample_count = (
                int(raw_sample_count) if raw_sample_count is not None else None
            )
        # The cash-flow reference follows the same precedence: an operator's
        # multiple first, then the eligible production historical P/FCF
        # distribution's median, then the vendor band's median. Each rung is
        # labelled with its own method so the context layer never records a
        # production median as a vendor-band figure.
        if pfcf_multiple is not None:
            selected_pfcf = pfcf_multiple
            selected_pfcf_method = "user_supplied_multiple"
        elif production_pfcf_median is not None:
            selected_pfcf = production_pfcf_median
            selected_pfcf_method = "production_historical_pfcf_median"
        elif historical_pfcf_median is not None:
            selected_pfcf = historical_pfcf_median
            selected_pfcf_method = "historical_pfcf_median"
        else:
            selected_pfcf = None
            selected_pfcf_method = "none"

        # The observation count behind the selected cash-flow reference, read
        # only from the distribution when the distribution *is* the reference
        # -- the same rule the P/E reference follows.
        production_pfcf_sample_count = None
        if selected_pfcf_method == "production_historical_pfcf_median":
            raw_pfcf_sample_count = safe_float(
                ((production_historical_pfcf or {}).get("distribution") or {}).get(
                    "sample_count"
                )
            )
            production_pfcf_sample_count = (
                int(raw_pfcf_sample_count) if raw_pfcf_sample_count is not None else None
            )

        # The sales and enterprise-value references follow the same
        # precedence: an operator's multiple first, then the eligible
        # production historical P/S / EV/EBITDA distribution's median, then
        # the vendor band's median. Each rung is labelled with its own method
        # so the context layer never records a production median as a
        # vendor-band figure.
        if ps_multiple is not None:
            selected_ps = ps_multiple
            selected_ps_method = "user_supplied_multiple"
        elif production_ps_median is not None:
            selected_ps = production_ps_median
            selected_ps_method = "production_historical_ps_median"
        elif historical_ps_median is not None:
            selected_ps = historical_ps_median
            selected_ps_method = "historical_ps_median"
        else:
            selected_ps = None
            selected_ps_method = "none"

        if ev_ebitda_multiple is not None:
            selected_ev_ebitda = ev_ebitda_multiple
            selected_ev_ebitda_method = "user_supplied_multiple"
        elif production_ev_ebitda_median is not None:
            selected_ev_ebitda = production_ev_ebitda_median
            selected_ev_ebitda_method = "production_historical_ev_ebitda_median"
        elif historical_ev_ebitda_median is not None:
            selected_ev_ebitda = historical_ev_ebitda_median
            selected_ev_ebitda_method = "historical_ev_ebitda_median"
        else:
            selected_ev_ebitda = None
            selected_ev_ebitda_method = "none"

        # The observation count behind the selected sales and enterprise-value
        # references, read only from the distribution when the distribution
        # *is* the reference -- the same rule the P/E and P/FCF references
        # follow.
        production_ps_sample_count = None
        production_ev_ebitda_sample_count = None
        if selected_ps_method == "production_historical_ps_median":
            raw_ps_sample_count = safe_float(
                (
                    ((production_historical_multiples or {}).get("distributions") or {})
                    .get("P_S_RATIO_REFERENCE")
                    or {}
                ).get("sample_count")
            )
            production_ps_sample_count = (
                int(raw_ps_sample_count) if raw_ps_sample_count is not None else None
            )
        if selected_ev_ebitda_method == "production_historical_ev_ebitda_median":
            raw_ev_sample_count = safe_float(
                (
                    ((production_historical_multiples or {}).get("distributions") or {})
                    .get("EV_EBITDA_RATIO_REFERENCE")
                    or {}
                ).get("sample_count")
            )
            production_ev_ebitda_sample_count = (
                int(raw_ev_sample_count) if raw_ev_sample_count is not None else None
            )

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

        # P/S requires market cap and revenue in the same currency. A
        # cross-currency ratio (e.g. USD market cap / JPY revenue) is refused,
        # not computed, and the converted figure is reported separately in
        # cross_currency.revenue_conversion instead.
        #
        # The two currencies are contract data, read from the projection, so
        # the engine reaches the same verdict whether it was handed a
        # `ValuationInputs` or a 2.2.3 view.
        _currencies_compatible = inputs.ratio_currencies_compatible()
        current_ps = (
            market_cap / current_revenue
            if market_cap and current_revenue and current_revenue > 0 and _currencies_compatible
            else None
        )
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
                "method": selected_pe_method,
                "multiple": selected_pe,
                "conditional_statement": "Implied fundamentals are conditional on the selected valuation multiple. Price alone does not identify a unique fundamental path.",
                # The production distribution's own eligibility status, so a
                # reader can tell an eligible reference from a descriptive one
                # without re-deriving it.
                "production_historical_pe_status": production_pe_status,
                # The observation count behind the selected reference, for the
                # basis that has one. The full breakdown and observation period
                # stay in the report's production-distribution summary; this is
                # the single figure the reference's own provenance reports, and
                # the context layer cannot read it from any other object.
                "production_historical_pe_sample_count": production_pe_sample_count,
                # The cash-flow reference's own basis and status, so the P/FCF
                # reference the context records names where its number came
                # from the same way the P/E reference does.
                "pfcf_method": selected_pfcf_method,
                "pfcf_multiple": selected_pfcf,
                "production_historical_pfcf_status": production_pfcf_status,
                "production_historical_pfcf_sample_count": production_pfcf_sample_count,
                # The sales and enterprise-value references' own bases and
                # statuses, so the context records where each number came from
                # the same way it does for the P/E and P/FCF references.
                "ps_method": selected_ps_method,
                "ps_multiple": selected_ps,
                "production_historical_ps_status": production_ps_status,
                "production_historical_ps_sample_count": production_ps_sample_count,
                "ev_ebitda_method": selected_ev_ebitda_method,
                "ev_ebitda_multiple": selected_ev_ebitda,
                "production_historical_ev_ebitda_status": production_ev_ebitda_status,
                "production_historical_ev_ebitda_sample_count": production_ev_ebitda_sample_count,
                # The registry's basis for the production multiples, per
                # metric. It is the standing under which the denominator was
                # read, and it is kept with the reference so that the archive
                # holds it and a later change to the registry's decisions is
                # visible rather than silent.
                "production_historical_multiples_qualification": (
                    production_multiples_qualification
                ),
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
            # Where each of those inputs came from and on what basis, so a
            # reader can tell a filed figure from a provider's, and a trailing
            # figure from a year's or a quarter's.
            "input_provenance": inputs.input_provenance or {},
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


def load_production_historical_references(
    ticker: str,
    include_historical_pe: bool = False,
    include_historical_pfcf: bool = False,
    include_historical_multiples: bool = False,
    enable_furnished_pe: bool = True,
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    The committed production historical P/E, P/FCF and multiples
    distributions.

    All are read from the frozen datasets under `data/historical_pe`,
    `data/historical_pfcf` and `data/historical_multiples`. Nothing is fetched
    and nothing is written, so the load is pure and can happen before the
    engine runs -- the engine's reference precedence reads the distribution's
    own eligibility.

    A ticker with no established dataset gets an explicit unavailable payload
    rather than a silent absence, so a caller can tell "not established" from
    "not asked for".

    The same function serves a live run and a rebuild. A replay that has to
    reproduce a run's reference reads the same committed dataset the run read,
    so the reference the rebuild selects is the reference the run selected.
    """
    production_historical_pe = None
    if include_historical_pe:
        try:
            from historical_pe import ISSUER_CONFIGS, load_issuer_historical_pe

            if ticker in ISSUER_CONFIGS:
                config = ISSUER_CONFIGS[ticker]
                pe_result = load_issuer_historical_pe(
                    config,
                    enable_furnished=enable_furnished_pe,
                )
                production_historical_pe = pe_result.to_dict()
            else:
                production_historical_pe = {
                    "distribution": {
                        "status": "UNAVAILABLE",
                        "usable_for_reference": False,
                        "sample_count": 0,
                        "reason_code": "REASON_INSUFFICIENT_OBSERVATIONS",
                        "reason_detail": f"Production historical P/E dataset is not yet established for {ticker}.",
                    }
                }
        except Exception as exc:
            production_historical_pe = {
                "distribution": {
                    "status": "UNAVAILABLE",
                    "usable_for_reference": False,
                    "sample_count": 0,
                    "reason_code": "REASON_INSUFFICIENT_OBSERVATIONS",
                    "reason_detail": str(exc),
                }
            }

    # The point-in-time historical P/FCF reconstruction, gated and loaded the
    # same way as the P/E distribution. It is opt-in on its own flag, so a run
    # that does not ask for it is computed exactly as before; when the
    # reconstruction is not established for the ticker, the payload states
    # that instead of inventing a band.
    production_historical_pfcf = None
    if include_historical_pfcf:
        try:
            from historical_pfcf import ISSUER_CONFIGS as PFCF_ISSUER_CONFIGS
            from historical_pfcf import load_issuer_historical_pfcf

            if ticker in PFCF_ISSUER_CONFIGS:
                pfcf_result = load_issuer_historical_pfcf(
                    PFCF_ISSUER_CONFIGS[ticker]
                )
                production_historical_pfcf = pfcf_result.to_dict()
            else:
                production_historical_pfcf = {
                    "distribution": {
                        "status": "UNAVAILABLE",
                        "usable_for_reference": False,
                        "sample_count": 0,
                        "reason_code": "REASON_INSUFFICIENT_OBSERVATIONS",
                        "reason_detail": (
                            f"Production historical P/FCF dataset is not yet established "
                            f"for {ticker}."
                        ),
                    }
                }
        except Exception as exc:
            production_historical_pfcf = {
                "distribution": {
                    "status": "UNAVAILABLE",
                    "usable_for_reference": False,
                    "sample_count": 0,
                    "reason_code": "REASON_INSUFFICIENT_OBSERVATIONS",
                    "reason_detail": str(exc),
                }
            }

    # The point-in-time historical P/S and EV/EBITDA reconstructions, gated
    # and loaded the same way as the P/E and P/FCF distributions. They are
    # opt-in on their own flag, so a run that does not ask for them is
    # computed exactly as before; when the reconstruction is not established
    # for the ticker, the payload states that instead of inventing a
    # distribution.
    production_historical_multiples = None
    if include_historical_multiples:
        from historical_multiples import (
            ISSUER_CONFIGS as MULTIPLES_ISSUER_CONFIGS,
            REASON_DATASET_LOAD_FAILED,
            REASON_DATASET_NOT_ESTABLISHED,
            load_issuer_historical_multiples,
        )

        try:
            if ticker in MULTIPLES_ISSUER_CONFIGS:
                multiples_result = load_issuer_historical_multiples(
                    MULTIPLES_ISSUER_CONFIGS[ticker]
                )
                production_historical_multiples = multiples_result.to_dict()
            else:
                # The dataset does not exist for this issuer. That is a
                # different condition from a dataset that exists and holds
                # too few observations, and it is reported as the condition it
                # is: an absent dataset is not a thin sample, and it never
                # becomes a reference by way of another source.
                production_historical_multiples = {
                    "distributions": {
                        "P_S_RATIO_REFERENCE": {
                            "metric_id": "P_S_RATIO_REFERENCE",
                            "status": "UNAVAILABLE",
                            "usable_for_reference": False,
                            "sample_count": 0,
                            "reason_code": REASON_DATASET_NOT_ESTABLISHED,
                            "reason_detail": (
                                f"Production historical P/S dataset is not yet established "
                                f"for {ticker}."
                            ),
                        },
                        "EV_EBITDA_RATIO_REFERENCE": {
                            "metric_id": "EV_EBITDA_RATIO_REFERENCE",
                            "status": "UNAVAILABLE",
                            "usable_for_reference": False,
                            "sample_count": 0,
                            "reason_code": REASON_DATASET_NOT_ESTABLISHED,
                            "reason_detail": (
                                f"Production historical EV/EBITDA dataset is not yet "
                                f"established for {ticker}."
                            ),
                        },
                    }
                }
        except Exception as exc:
            # The dataset exists but could not be read. It is reported as the
            # condition it is, and it never becomes a reference.
            production_historical_multiples = {
                "distributions": {
                    "P_S_RATIO_REFERENCE": {
                        "metric_id": "P_S_RATIO_REFERENCE",
                        "status": "UNAVAILABLE",
                        "usable_for_reference": False,
                        "sample_count": 0,
                        "reason_code": REASON_DATASET_LOAD_FAILED,
                        "reason_detail": str(exc),
                    },
                    "EV_EBITDA_RATIO_REFERENCE": {
                        "metric_id": "EV_EBITDA_RATIO_REFERENCE",
                        "status": "UNAVAILABLE",
                        "usable_for_reference": False,
                        "sample_count": 0,
                        "reason_code": REASON_DATASET_LOAD_FAILED,
                        "reason_detail": str(exc),
                    },
                }
            }

    return (
        production_historical_pe,
        production_historical_pfcf,
        production_historical_multiples,
    )


def load_production_historical_income(
    ticker: str,
) -> Optional[Dict[str, Any]]:
    """
    The committed production income-statement dataset for this ticker.

    The dataset holds the issuer's filed quarterly revenue, operating income
    and depreciation facts, and the trailing windows they make. A ticker with
    no established dataset gets None: there is no window to qualify, and the
    engine keeps whatever it had.
    """
    try:
        from historical_income import ISSUER_CONFIGS, load_issuer_historical_income
    except Exception:
        return None
    config = ISSUER_CONFIGS.get(ticker)
    if config is None:
        return None
    try:
        return load_issuer_historical_income(config).to_dict()
    except Exception:
        return None


def run_st_eva(
    ticker: str,
    horizon: str = "1-8 weeks",
    event: Optional[str] = None,
    mode: str = "auto",
    reference_multiple: Optional[float] = None,
    reference_multiples: Optional[Sequence[float]] = None,
    horizon_years: float = 1.0,
    pfcf_multiple: Optional[float] = None,
    ev_ebitda_multiple: Optional[float] = None,
    ps_multiple: Optional[float] = None,
    save_snapshot: bool = True,
    history_dir: str = "history",
    context_path: Optional[str] = None,
    context_sources: Sequence[str] = ("yahoo", "sec"),
    archive: Optional[Any] = None,
    reverse_horizons: Sequence[float] = (1.0, 2.0, 3.0, 5.0),
    required_returns: Sequence[float] = (0.08, 0.10, 0.12, 0.15),
    include_risk_free_rates: bool = False,
    include_dcf: bool = True,
    beta: Optional[float] = None,
    equity_risk_premium: Optional[float] = None,
    risk_free_tenor: str = "10_YEAR",
    include_financial_history: bool = False,
    dossier_path: Optional[str] = None,
    render_dossier_report: bool = False,
    include_historical_pe: bool = False,
    enable_furnished_pe: bool = True,
    include_historical_pfcf: bool = False,
    include_historical_multiples: bool = False,
    include_historical_income: bool = False,
    prefer_eps_anchor: Optional[str] = None,
    user_eps: Optional[float] = None,
    fx_rate_usd_per_jpy: Optional[float] = None,
    fx_analysis_date_usd_per_jpy: Optional[float] = None,
    adr_underlying_shares_per_adr: Optional[float] = None,
    eps_xbrl_documents: Optional[Sequence[Any]] = None,
    eps_xbrl_inputs: Optional[Sequence[Any]] = None,
    xbrl_documents: Optional[Sequence[Any]] = None,
    eps_xbrl_paths: Optional[Sequence[Any]] = None,
    eps_xbrl_expected_cik: Optional[str] = None,
    **kwargs: Any,
) -> Optional[Dict[str, Any]]:
    data = CompanyResolver.resolve(ticker, mode=mode)
    if data is None:
        return None

    # Price fetch failure: the run could not acquire price data at all.
    # Return None so the caller can report "could not acquire usable market data."
    # Other validation errors (e.g., DATA_DISCREPANCY) are NOT converted here:
    # they still raise ValueError as before.
    if data.errors and data.price == UNAVAILABLE:
        return None

    data_errors = Validator.validate_data(data)
    if data_errors:
        raise ValueError("; ".join(data_errors))

    metrics = DeterministicMetricsEngine.compute(
        data.price_history,
        data.volume_history,
    )

    evidence = build_evidence(data, metrics)

    # Loaded before the summary engine, because the engine's reference
    # precedence reads the distribution's eligibility. The load is pure -- it
    # reads the committed dataset and writes nothing -- so hoisting it above the
    # engine changes no other ordering.
    production_historical_pe, production_historical_pfcf, production_historical_multiples = (
        load_production_historical_references(
            data.ticker,
            include_historical_pe=include_historical_pe,
            include_historical_pfcf=include_historical_pfcf,
            include_historical_multiples=include_historical_multiples,
            enable_furnished_pe=enable_furnished_pe,
        )
    )
    # The filed income-statement dataset. It carries no reference
    # distribution -- only the trailing revenue and EBITDA the multiples are
    # computed from -- so it is loaded on its own flag.
    production_historical_income = (
        load_production_historical_income(data.ticker)
        if include_historical_income
        else None
    )

    # The engine's own inputs.
    #
    # The view carries what the market data provider reported. Where a filed,
    # qualified figure on the basis the multiple needs exists, it is the
    # engine's input, and the vendor's figure is recorded beside it as the
    # cross-check it is. Where no such figure exists, the engine keeps the
    # provider's and says so -- a fiscal year's figure and a quarter's figure
    # are different quantities and neither may stand in for a trailing one.
    engine_inputs = ValuationInputs.from_legacy_view(data)
    engine_inputs, input_provenance, ttm_windows = _engine_inputs_with_filed_figures(
        engine_inputs,
        data=data,
        production_historical_pe=production_historical_pe,
        production_historical_pfcf=production_historical_pfcf,
        production_historical_income=production_historical_income,
        ticker=data.ticker,
    )

    analysis = MarketImpliedAssumptionsEngine.analyze(
        data=engine_inputs,
        reference_multiple=reference_multiple,
        horizon_years=horizon_years,
        pfcf_multiple=pfcf_multiple,
        ev_ebitda_multiple=ev_ebitda_multiple,
        ps_multiple=ps_multiple,
        production_historical_pe=production_historical_pe,
        production_historical_pfcf=production_historical_pfcf,
        production_historical_multiples=production_historical_multiples,
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
    context_extra_observations: List[Any] = []
    captured_documents: List[Any] = []

    # One SEC pass feeds both the financial history and the Investment
    # Context, so a run that wants both reaches the filings once and the two
    # cannot disagree. Either can be asked for on its own. The default asks for
    # neither, so an ordinary run still touches no filing endpoint and the
    # analysis output is unchanged by the context flag.
    # A regression fixture is a frozen, offline sample: acquiring a live filing
    # context for it would make the run network-dependent and non-reproducible,
    # so the SEC context source is never consulted for a fixture.
    wants_sec = (
        (context_path is not None or include_financial_history)
        and data.source_type != SourceType.REGRESSION_FIXTURE.value
    )
    sec_evidence = (
        _acquire_sec_evidence(data, context_sources) if wants_sec else _empty_sec_evidence()
    )

    eps_xbrl_records = []
    eps_xbrl_errors = []
    doc_inputs = []
    for candidate in (eps_xbrl_documents, eps_xbrl_inputs, xbrl_documents, eps_xbrl_paths):
        if candidate is None:
            continue
        if isinstance(candidate, (str, os.PathLike)):
            doc_inputs.append({"path": str(candidate)})
        elif isinstance(candidate, dict):
            doc_inputs.append(dict(candidate))
        else:
            for item in candidate:
                if isinstance(item, (str, os.PathLike)):
                    doc_inputs.append({"path": str(item)})
                elif isinstance(item, dict):
                    doc_inputs.append(dict(item))
                else:
                    doc_inputs.append(item)
    for key, value in (kwargs or {}).items():
        if "xbrl" in str(key).lower() or "document" in str(key).lower():
            if isinstance(value, (str, os.PathLike)):
                doc_inputs.append({"path": str(value)})
            elif isinstance(value, dict):
                doc_inputs.append(dict(value))
            elif isinstance(value, (list, tuple)):
                for item in value:
                    if isinstance(item, (str, os.PathLike)):
                        doc_inputs.append({"path": str(item)})
                    elif isinstance(item, dict):
                        doc_inputs.append(dict(item))
                    else:
                        doc_inputs.append(item)
    if doc_inputs:
        from sec_xbrl_facts import parse_xbrl_document
        from eps_anchor_evidence import eps_fact_records_from_xbrl_document
        for item in doc_inputs:
            if not isinstance(item, dict):
                item = {"value": item}
            path = item.get("path") or item.get("document") or item.get("file") or item.get("filename")
            if not path:
                continue
            try:
                with open(str(path), "rb") as handle:
                    payload = handle.read()
                document = parse_xbrl_document(payload)
                accession = item.get("accession")
                if accession is None or str(accession).strip().lower() in ("", "none", "null"):
                    raise ValueError("EPS XBRL document missing required accession")
                form = item.get("form") or "10-K"
                if not str(form).strip():
                    raise ValueError("EPS XBRL document missing required form")
                expected_cik = (
                    item.get("expected_cik")
                    or item.get("issuer_cik")
                    or item.get("target_cik")
                    or item.get("cik")
                    or eps_xbrl_expected_cik
                )
                doc_rejections = []
                recs = eps_fact_records_from_xbrl_document(
                    document,
                    accession=accession,
                    form=form,
                    filed=item.get("filed"),
                    acceptance_datetime=item.get("acceptance_datetime"),
                    fiscal_year=item.get("fiscal_year"),
                    fiscal_period=item.get("fiscal_period"),
                    assurance_status=item.get("assurance_status") or "UNKNOWN",
                    source_url=item.get("source_url"),
                    expected_cik=expected_cik,
                    rejections=doc_rejections,
                )
                eps_xbrl_errors.extend(doc_rejections)
                if not recs and not doc_rejections:
                    eps_xbrl_errors.append(
                        {
                            "reason_code": "NO_QUALIFYING_EPS_FACTS",
                            "detail": f"document {path} produced no qualifying EPS fact",
                            "context_ref": None,
                        }
                    )
                eps_xbrl_records.extend(recs)
            except OSError as exc:
                raise ValueError(f"EPS XBRL document not found or unreadable: {path}: {exc}")

    reverse_requirements = _build_reverse_requirements(
        data,
        analysis,
        horizons_years=reverse_horizons,
        required_returns=required_returns,
        reference_multiple=reference_multiple,
        reference_multiples=reference_multiples,
        pfcf_multiple=pfcf_multiple,
        ev_ebitda_multiple=ev_ebitda_multiple,
        ps_multiple=ps_multiple,
        include_risk_free_rates=include_risk_free_rates,
        include_dcf=include_dcf,
        beta=beta,
        equity_risk_premium=equity_risk_premium,
        risk_free_tenor=risk_free_tenor,
        sec_observations=sec_evidence.get("observations") if include_financial_history else None,
        # The run's own filing evidence, when the SEC source actually ran. It
        # carries the declared diluted-EPS facts the report states, and the
        # related cross-check each scenario row shows; it is not a valuation
        # input and its presence changes no calculation. A run that consulted
        # no filing endpoint passes None and keeps the packaged-dataset
        # fallback it always had.
        sec_eps_evidence=(
            {
                "observations": list(sec_evidence.get("observations") or []),
                "cik": sec_evidence.get("cik"),
            }
            if wants_sec and sec_evidence.get("acquired")
            else None
        ),
        cross_validation=sec_evidence.get("cross_validation") if wants_sec else None,
        production_historical_pe=production_historical_pe,
        production_historical_pfcf=production_historical_pfcf,
        production_historical_multiples=production_historical_multiples,
        prefer_eps_anchor=prefer_eps_anchor,
        user_eps=user_eps,
        eps_xbrl_records=eps_xbrl_records,
    )
    if isinstance(reverse_requirements, dict):
        reverse_requirements["eps_xbrl_acquisition"] = {
            "documents": len(doc_inputs),
            "errors": list(eps_xbrl_errors),
        }

    if context_path is not None:
        # Opt-in only. Nothing above this line changes when a context is not
        # requested, so the default path is byte-identical to 2.2.3.
        (
            investment_context,
            context_extra_observations,
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
            sec_evidence=sec_evidence,
            ttm_windows=ttm_windows,
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
                context_extra_observations=context_extra_observations,
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

    # ------------------------------------------------------------------
    # Cross-currency processing for MUFG (USD price/market cap vs JPY
    # financials). No implicit conversion: every converted figure names the
    # FX rate, ADR ratio, and original amounts.
    # ------------------------------------------------------------------
    # Cross-currency processing for MUFG (USD price/market cap vs JPY
    # financials). Two distinct FX scopes are maintained:
    #
    #   1. Analysis-date spot rate (fx_analysis_date_usd_per_jpy):
    #      ECB-derived rate for 2026-10-16 (0.0063283095 USD/JPY).
    #      Used to convert JPY financial data to USD for current
    #      valuation comparison.
    #
    #   2. Fiscal-period rate (fx_rate_usd_per_jpy):
    #      Federal Reserve H.10 observation for 2026-10-09
    #      (0.006316 USD/JPY). Kept as a separate reference observation;
    #      NOT used as a proxy for the analysis-date rate.
    #
    # No implicit conversion: every converted figure names the FX rate,
    # ADR ratio, as_of date, and original amounts.
    # ------------------------------------------------------------------
    cross_currency: Dict[str, Any] = {
        "applicable": False,
        "reason": None,
        "fx_rate_fiscal_period": None,
        "fx_rate_analysis_date": None,
        "adr_ratio": None,
        "revenue_conversion": None,
        "eps_conversion": None,
        "ps_ratio": None,
        "ttm_eps": None,
        "corporate_target_comparison": None,
    }

    fx_rate = None
    fx_analysis_date = None
    adr = None

    # Historical reference FX rate (Fed H.10, 2026-10-09) - reference only,
    # not an actual fiscal-period conversion rate.
    if fx_rate_usd_per_jpy is not None:
        try:
            from fx_rates import FxRate, convert_jpy_to_usd, convert_usd_to_jpy

            fx_rate = FxRate(
                rate_usd_per_jpy=fx_rate_usd_per_jpy,
                as_of="2026-10-09",
                provider="operator-supplied",
                source_url="operator-supplied",
                quote_direction="USD per JPY",
            )
        except Exception:
            fx_rate = None

    # Analysis-date FX rate (ECB, 2026-10-16) - used for conversions
    if fx_analysis_date_usd_per_jpy is not None:
        try:
            from fx_rates import FxRate, convert_jpy_to_usd, convert_usd_to_jpy

            fx_analysis_date = FxRate(
                rate_usd_per_jpy=fx_analysis_date_usd_per_jpy,
                as_of="2026-10-16",
                provider="European Central Bank (ECB)",
                source_url="https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_rates/html/index.en.html",
                quote_direction="USD per JPY",
            )
        except Exception:
            fx_analysis_date = None

    if adr_underlying_shares_per_adr is not None:
        try:
            from adr_ratio import AdrRatio

            adr = AdrRatio(
                underlying_shares_per_adr=float(adr_underlying_shares_per_adr),
                as_of=data.price_date,
                provider="operator-supplied",
                source_url="operator-supplied",
                exchange=data.exchange,
            )
        except Exception:
            adr = None

    # Determine which FX rate to use for conversions: analysis-date rate
    # takes precedence; fiscal-period rate is reference-only.
    fx_for_conversion = fx_analysis_date if fx_analysis_date is not None else fx_rate
    fx_scope = "analysis_date" if fx_analysis_date is not None else "reference_only"

    if fx_for_conversion is not None or adr is not None:
        cross_currency["applicable"] = True

        if fx_rate is not None:
            cross_currency["fx_rate_fiscal_period"] = {
                "rate_usd_per_jpy": fx_rate.rate_usd_per_jpy,
                "as_of": fx_rate.as_of,
                "provider": fx_rate.provider,
                "source_url": fx_rate.source_url,
                "quote_direction": fx_rate.quote_direction,
                "scope": "reference_only",
                "note": "Historical reference FX observation (Fed H.10, 2026-10-09). "
                        "Reference only ??not a fiscal-period conversion rate and "
                        "must not be used for period conversion.",
            }

        if fx_analysis_date is not None:
            cross_currency["fx_rate_analysis_date"] = {
                "rate_usd_per_jpy": fx_analysis_date.rate_usd_per_jpy,
                "as_of": fx_analysis_date.as_of,
                "provider": fx_analysis_date.provider,
                "source_url": fx_analysis_date.source_url,
                "quote_direction": fx_analysis_date.quote_direction,
                "scope": "analysis_date",
                "note": "Analysis-date spot reference (ECB, 2026-10-16). "
                        "Derived from 1 EUR = 1.1253 USD and 1 EUR = 177.82 JPY "
                        "(USD/JPY = 1.1253 / 177.82). Used for converting JPY "
                        "financial data to USD for current valuation comparison.",
            }

        if adr is not None:
            cross_currency["adr_ratio"] = {
                "underlying_shares_per_adr": adr.underlying_shares_per_adr,
                "as_of": adr.as_of,
                "provider": adr.provider,
                "source_url": adr.source_url,
                "exchange": adr.exchange,
                "note": "1 MUFG ADR = N underlying ordinary shares.",
            }

        # Revenue conversion: JPY revenue -> USD using the analysis-date FX rate.
        # The Yahoo revenue observation is flagged CURRENCY_MISMATCH against
        # the USD market cap; the SEC revenue observations are also JPY.
        # Convert each JPY revenue figure explicitly with the named FX rate.
        revenue_jpy = safe_float(data.current_revenue)
        if revenue_jpy is not None and fx_for_conversion is not None:
            revenue_usd = convert_jpy_to_usd(revenue_jpy, fx_for_conversion)
            market_cap_usd = safe_float(data.current_market_cap)
            ps_ratio_usd = (
                market_cap_usd / revenue_usd
                if market_cap_usd and revenue_usd
                else None
            )
            cross_currency["revenue_conversion"] = {
                "revenue_jpy": revenue_jpy,
                "revenue_usd_converted": revenue_usd,
                "fx_rate_used": fx_for_conversion.rate_usd_per_jpy,
                "fx_scope": fx_scope,
                "fx_as_of": fx_for_conversion.as_of,
                "market_cap_usd": market_cap_usd,
                "ps_ratio_usd_converted": ps_ratio_usd,
                "note": "P/S computed as USD market cap / USD-converted JPY "
                        "revenue using the explicit analysis-date FX rate. The "
                        "raw JPY revenue / USD market cap ratio (P/S 0.03x) "
                        "mixes currencies and is not reported as a valid "
                        "multiple. Revenue period (Yahoo: as_of 2026-06-30) "
                        "differs from market cap as_of (2026-09-23); periods "
                        "are not reconciled.",
            }

        # EPS conversion: JPY diluted EPS -> USD using FX rate + ADR ratio.
        # Yahoo trailing EPS (1.53 USD) is already USD; SEC diluted EPS
        # (瞼108.18 / 瞼151.09) is JPY per underlying share.
        # Read SEC diluted EPS directly from the per-ticker archive so it is
        # available even when no SEC context was acquired in this run.
        #
        # The archive is a local, gitignored directory, so a CI checkout does
        # not have one and the read below would fail and silently leave the
        # conversion empty. The packaged filing facts are the tracked copy of
        # the same facts, so they are consulted first and the archive is only a
        # fallback for a ticker that has no packaged dataset.
        sec_diluted_eps_jpy = None
        sec_diluted_eps_period = None
        sec_diluted_eps_accession = None
        sec_diluted_eps_fiscal_year = None
        packaged = _packaged_sec_diluted_eps(data.ticker)
        if packaged is not None:
            sec_diluted_eps_jpy = safe_float(packaged.get("value"))
            sec_diluted_eps_period = (
                f"{packaged['period_start']} to {packaged['period_end']}"
                if packaged.get("period_start") and packaged.get("period_end")
                else None
            )
            sec_diluted_eps_accession = packaged.get("accession")
            sec_diluted_eps_fiscal_year = packaged.get("fiscal_year")
        else:
            try:
                import sqlite3
                archive_path = f"data/archives/{data.ticker}.sqlite"
                conn = sqlite3.connect(archive_path)
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    """
                    SELECT value_json, period_start, period_end, fiscal_year,
                           accession, source_url, raw_json
                    FROM observations
                    WHERE metric = 'eps_diluted' AND value_json IS NOT NULL
                      AND value_json != 'null'
                    ORDER BY period_end DESC
                    LIMIT 1
                    """
                ).fetchone()
                if row is not None:
                    raw_value = row["value_json"]
                    # value_json may be stored as a JSON string; coerce to number.
                    if isinstance(raw_value, str):
                        try:
                            raw_value = json.loads(raw_value)
                        except Exception:
                            try:
                                raw_value = float(raw_value)
                            except Exception:
                                raw_value = None
                    sec_diluted_eps_jpy = safe_float(raw_value)
                    sec_diluted_eps_period = (
                        f"{row['period_start']} to {row['period_end']}"
                        if row["period_start"] and row["period_end"]
                        else None
                    )
                    sec_diluted_eps_accession = row["accession"]
                    sec_diluted_eps_fiscal_year = row["fiscal_year"]
                    raw = json.loads(row["raw_json"]) if row["raw_json"] else {}
                    sec_fact = raw.get("sec_fact", {}) if isinstance(raw, dict) else {}
                    if sec_diluted_eps_accession is None:
                        sec_diluted_eps_accession = sec_fact.get("accession")
                conn.close()
            except Exception:
                sec_diluted_eps_jpy = None
                sec_diluted_eps_period = None
                sec_diluted_eps_accession = None
                sec_diluted_eps_fiscal_year = None

        if fx_for_conversion is not None and sec_diluted_eps_jpy is not None:
            eps_usd_per_share = convert_jpy_to_usd(
                sec_diluted_eps_jpy, fx_for_conversion
            )
            if adr is not None:
                eps_usd_per_adr = eps_usd_per_share * adr.underlying_shares_per_adr
            else:
                eps_usd_per_adr = None
            cross_currency["eps_conversion"] = {
                "eps_jpy_per_share": sec_diluted_eps_jpy,
                "eps_usd_per_share_converted": eps_usd_per_share,
                "eps_usd_per_adr_converted": eps_usd_per_adr,
                "fx_rate_used": fx_for_conversion.rate_usd_per_jpy,
                "fx_scope": fx_scope,
                "fx_as_of": fx_for_conversion.as_of,
                "adr_ratio_used": (
                    adr.underlying_shares_per_adr if adr else None
                ),
                "period": sec_diluted_eps_period,
                "fiscal_year": sec_diluted_eps_fiscal_year,
                "accession": sec_diluted_eps_accession,
                "note": "SEC diluted EPS (JPY per underlying share) "
                        "converted to USD using the explicit analysis-date FX "
                        "rate and ADR ratio. Not mixed with Yahoo USD EPS "
                        "without explicit disclosure.",
            }

        # TTM EPS derivation from SEC annual diluted EPS.
        # True TTM requires quarterly data; only annual SEC observations are
        # available for MUFG. The latest annual diluted EPS is the closest
        # available figure; it is labelled as annual, not TTM.
        if fx_for_conversion is not None and sec_diluted_eps_jpy is not None:
            ttm_eps_usd = convert_jpy_to_usd(sec_diluted_eps_jpy, fx_for_conversion)
            if adr is not None:
                ttm_eps_usd_per_adr = ttm_eps_usd * adr.underlying_shares_per_adr
            else:
                ttm_eps_usd_per_adr = None
            cross_currency["ttm_eps"] = {
                "eps_jpy_per_share": sec_diluted_eps_jpy,
                "eps_usd_per_share": ttm_eps_usd,
                "eps_usd_per_adr": ttm_eps_usd_per_adr,
                "basis": "Latest annual diluted EPS (SEC 20-F), not true TTM "
                         "(quarterly SEC data not available in archive).",
                "currency": "JPY (original) / USD (converted)",
                "fx_rate_used": fx_for_conversion.rate_usd_per_jpy,
                "fx_scope": fx_scope,
                "fx_as_of": fx_for_conversion.as_of,
                "adr_ratio_used": (
                    adr.underlying_shares_per_adr if adr else None
                ),
                "period": sec_diluted_eps_period,
                "accession": sec_diluted_eps_accession,
                "note": "Derived EPS is the latest annual diluted EPS "
                        "converted to USD. It is labelled annual, not TTM, "
                        "because quarterly SEC observations are not available "
                        "in the archive.",
            }

        # Corporate target comparison: FY2026 瞼2.7T target vs FY2025 瞼2.427T
        # actual vs derived TTM EPS. Net income target and EPS back-out
        # threshold are shown separately; net income target is NOT converted
        # to EPS growth rate without share count.
        net_income_fy2025_jpy = 2427000000000.0  # 瞼2.427T actual FY2025
        net_income_target_fy2026_jpy = 2700000000000.0  # 瞼2.7T target FY2026
        if fx_for_conversion is not None:
            net_income_fy2025_usd = convert_jpy_to_usd(
                net_income_fy2025_jpy, fx_for_conversion
            )
            net_income_target_fy2026_usd = convert_jpy_to_usd(
                net_income_target_fy2026_jpy, fx_for_conversion
            )
            cross_currency["corporate_target_comparison"] = {
                "net_income_fy2025_actual_jpy": net_income_fy2025_jpy,
                "net_income_fy2025_actual_usd": net_income_fy2025_usd,
                "net_income_target_fy2026_jpy": net_income_target_fy2026_jpy,
                "net_income_target_fy2026_usd": net_income_target_fy2026_usd,
        "fx_rate_used": fx_for_conversion.rate_usd_per_jpy,
        "fx_scope": fx_scope,
        "fx_as_of": fx_for_conversion.as_of,
        "derived_ttm_eps_usd_per_share": (
                    cross_currency["ttm_eps"]["eps_usd_per_share"]
                    if cross_currency["ttm_eps"] else None
                ),
                "note": "Management FY2026 net income target (瞼2.7T) and "
                        "FY2025 actual (瞼2.427T) are shown separately from the "
                        "derived EPS. The net income target is NOT converted to "
                        "an EPS growth rate because the share count needed for "
                        "that conversion is not available in this run.",
            }

    # The currency-compatibility rule for the P/S ratio lives on the contract,
    # so the reason reported here and the engine's own verdict are the same
    # rule applied to the same projection.
    _valuation_inputs = ValuationInputs.from_legacy_view(data)

    result = {
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
            "consensus_forward_eps_period_end": (
                data.consensus_forward_eps_period_end
            ),
        },
        "observed_valuation": analysis["observed_valuation"],
        "input_provenance": analysis.get("input_provenance") or {},
        "market_implied_assumptions": analysis["implied_assumptions"],
        "consensus_cross_check": analysis["consensus_cross_check"],
        "fundamental_snapshot": analysis["fundamental_snapshot"],
        "reference": analysis["reference"],
        "market_metrics": metrics,
        "reverse_requirements": reverse_requirements,
        "production_historical_pe": production_historical_pe,
        "production_historical_pfcf": production_historical_pfcf,
        "production_historical_multiples": production_historical_multiples,
        "missing_data": missing_data,
        "cross_currency": cross_currency,
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
        ]
        + (
            [
                "P/S not reported: market cap currency and revenue currency differ "
                "(cross-currency ratio is not a valid valuation multiple). "
                "A currency-converted P/S is shown separately in the cross-currency section."
            ]
            if _valuation_inputs.ratio_currencies_differ()
            else []
        ),
        "version_metadata": VERSION_METADATA,
    }

    if dossier_path is not None or render_dossier_report:
        # Assembled from the finished result rather than from the intermediate
        # values, so the dossier and the JSON package cannot disagree about
        # what this run produced.
        from research_dossier import build_dossier, render_dossier

        dossier = build_dossier(result)
        result["research_dossier"] = dossier
        if dossier_path == "-":
            print(render_dossier(dossier))
        elif dossier_path is not None:
            atomic_json_write(Path(dossier_path), dossier)
        if render_dossier_report:
            report_text = render_dossier(dossier)
            result["dossier_report_text"] = report_text
            if dossier_path is not None and dossier_path != "-":
                report_file = Path(dossier_path).with_name(f"{Path(dossier_path).stem}_report.txt")
                with open(report_file, "w", encoding="utf-8") as f:
                    f.write(report_text)

    return result


def _build_exit_multiple_scenarios(
    *,
    historical_band: Optional[Dict[str, Any]],
    user_multiples: Sequence[Optional[float]],
    min_observations: int,
    production_historical_pe: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Any], List[Dict[str, Any]]]:
    """
    The exit multiples the matrix runs over.

    A usable historical band contributes its percentile set; each explicitly
    supplied multiple contributes its own labelled point. They are kept as one
    ordered list rather than collapsed, so a reader can see which rows came from
    a distribution and which from a stated assumption, and a single fixed
    multiple cannot silently stand in for a sensitivity range.
    """
    from reverse_requirements import (
        ReferenceMultiple,
        exit_multiples_from_band,
        exit_multiples_from_production_distribution,
    )

    scenarios: List[Any] = []
    unavailable: List[Dict[str, Any]] = []

    # Production historical P/E distribution if provided
    prod_dist = (
        production_historical_pe.get("distribution")
        if isinstance(production_historical_pe, dict)
        else None
    )
    if prod_dist:
        prod_scenarios, prod_unavailable = exit_multiples_from_production_distribution(
            prod_dist, min_observations=min_observations
        )
        unavailable.extend(prod_unavailable)
        scenarios.extend(prod_scenarios)

    band_scenarios, band_unavailable = exit_multiples_from_band(
        historical_band, min_observations=min_observations
    )
    unavailable.extend(band_unavailable)
    seen = {round(m.value, 10) for m in scenarios}
    for cand in band_scenarios:
        if round(cand.value, 10) not in seen:
            seen.add(round(cand.value, 10))
            scenarios.append(cand)
    for candidate in user_multiples or ():
        number = safe_float(candidate)
        if number is None or number <= 0:
            unavailable.append(
                {
                    "item": "exit_multiple.user_supplied",
                    "reason": (
                        "The supplied exit multiple %r is not a positive number, so it "
                        "cannot invert a price into an EPS and was not used." % (candidate,)
                    ),
                    "reason_kind": "NOT_POSITIVE",
                    "blocks": ["exit_multiple"],
                }
            )
            continue
        if round(number, 10) in seen:
            continue
        seen.add(round(number, 10))
        scenarios.append(
            ReferenceMultiple(
                value=number,
                source="user_supplied",
                is_user_assumption=True,
                eligibility_state="USER_SPECIFIED",
                usable_for_reference=True,
            )
        )

    if not scenarios:
        unavailable.append(
            {
                "item": "exit_multiple",
                "reason": (
                    "No exit multiple is available. The historical band did not carry "
                    "enough observations and none was supplied, so the reverse "
                    "requirements matrix cannot be built."
                ),
                "reason_kind": "MISSING",
                "blocks": ["reverse_requirements_matrix"],
            }
        )
    return scenarios, unavailable


def _representative_multiple(scenarios: Sequence[Any]) -> Optional[Any]:
    """
    The multiple the single-reference methods use when a range is supplied.

    The median of the scenario set, so the earnings-method figure is not taken
    from whichever end of the range happens to be listed first. It stays
    labelled with its own source rather than being presented as neutral.
    """
    if not scenarios:
        return None
    ordered = sorted(scenarios, key=lambda m: m.value)
    return ordered[len(ordered) // 2]


def _build_valuation_multiples(
    *,
    reference_multiple: Optional[float],
    pfcf_multiple: Optional[float],
    ev_ebitda_multiple: Optional[float],
    ps_multiple: Optional[float],
    historical_band: Optional[Dict[str, Any]],
    min_observations: int,
    production_historical_pe: Optional[Dict[str, Any]] = None,
    production_historical_multiples: Optional[Dict[str, Any]] = None,
    representative: Optional[Any] = None,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    The reference multiple for each valuation method, keyed by method.

    Each method gets its own multiple and its own provenance. A P/E and a P/S
    are not interchangeable, and a method with no multiple supplied is left
    absent rather than filled from another method's number.

    `representative` is the scenario set's representative multiple object, when
    one was selected. When its value is what would otherwise be recorded as the
    operator's P/E, its own labels travel instead: a median read from the
    production historical distribution is recorded as exactly that, never as a
    user assumption, for the same reason the context layer refuses to record a
    production median as a vendor-band figure.
    """
    from reverse_requirements import (
        ReferenceMultiple,
        exit_multiples_from_band,
        exit_multiples_from_production_distribution,
        reference_multiple_from_production_distribution,
    )

    multiples: Dict[str, Any] = {}
    unavailable: List[Dict[str, Any]] = []

    prod_scenarios: List[Any] = []
    prod_dist = (
        production_historical_pe.get("distribution")
        if isinstance(production_historical_pe, dict)
        else None
    )
    if prod_dist:
        prod_scenarios, _ = exit_multiples_from_production_distribution(
            prod_dist, min_observations=min_observations
        )

    band_scenarios, band_unavailable = exit_multiples_from_band(
        historical_band, min_observations=min_observations
    )
    # The band warning is already reported by the scenario builder for the
    # matrix. Emitting it again here would double-count one gap in the
    # limitations section and make the totals misleading.
    unavailable.extend(
        entry for entry in band_unavailable if entry["item"] != "exit_multiple.band_scenarios"
    )

    user_pe = safe_float(reference_multiple)
    if user_pe is not None and user_pe > 0:
        if (
            representative is not None
            and not getattr(representative, "is_user_assumption", False)
            and safe_float(getattr(representative, "value", None)) == user_pe
        ):
            multiples["pe"] = representative
        else:
            multiples["pe"] = ReferenceMultiple(
                value=user_pe,
                source="user_supplied",
                is_user_assumption=True,
                eligibility_state="USER_SPECIFIED",
                usable_for_reference=True,
            )
    elif prod_scenarios:
        # Use median from production historical distribution
        median = next(
            (m for m in prod_scenarios if "median" in m.period_label or "median" in m.source),
            prod_scenarios[len(prod_scenarios) // 2],
        )
        multiples["pe"] = median
    elif band_scenarios:
        # The median percentile is the single representative the method view
        # uses; the full percentile set is returned separately as scenarios.
        median = next(
            (m for m in band_scenarios if m.period_label == "" and m.sample_size is not None),
            band_scenarios[len(band_scenarios) // 2],
        )
        multiples["pe"] = median
    else:
        unavailable.append(
            {
                "item": "valuation_method.earnings_multiple",
                "reason": (
                    "No P/E reference is available: none was supplied and neither the production "
                    "historical distribution nor the historical band carried enough observations."
                ),
                "reason_kind": "NO_REFERENCE_MULTIPLE",
                "blocks": ["valuation_methods"],
            }
        )

    # The production historical P/S and EV/EBITDA distributions, when the run
    # loaded them, supply the sales and enterprise-value methods' own
    # reference multiple in the same way the production historical P/E
    # distribution supplies the earnings method's: the operator's own multiple
    # first, then the eligible distribution's median, and never a number from
    # another method. Each keeps its own labels, so a production median is
    # never recorded as a user assumption.
    multiples_distributions = (
        (production_historical_multiples or {}).get("distributions") or {}
    )

    for key, value, label in (
        ("cash_flow", pfcf_multiple, "P/FCF"),
        ("enterprise_value", ev_ebitda_multiple, "EV/EBITDA"),
        ("revenue", ps_multiple, "P/S"),
    ):
        number = safe_float(value)
        if number is not None and number > 0:
            multiples[key] = ReferenceMultiple(
                value=number,
                source="user_supplied",
                is_user_assumption=True,
                eligibility_state="USER_SPECIFIED",
                usable_for_reference=True,
            )
            continue

        distribution = None
        source = None
        if label == "EV/EBITDA":
            distribution = multiples_distributions.get("EV_EBITDA_RATIO_REFERENCE")
            source = "production_historical_ev_ebitda_median"
        elif label == "P/S":
            distribution = multiples_distributions.get("P_S_RATIO_REFERENCE")
            source = "production_historical_ps_median"

        if distribution:
            production_multiple, refusal = (
                reference_multiple_from_production_distribution(
                    distribution,
                    source=source,
                    metric_label=label,
                    min_observations=min_observations,
                )
            )
            if production_multiple is not None:
                multiples[key] = production_multiple
                continue
            if refusal is not None:
                unavailable.append(refusal)
                continue

        unavailable.append(
            {
                "item": "valuation_method.%s" % key,
                "reason": (
                    "No %s reference multiple was supplied, so this method produces no "
                    "implied figure. It is not filled from another method's multiple."
                    % label
                ),
                "reason_kind": "NO_REFERENCE_MULTIPLE",
                "blocks": ["valuation_methods.%s" % key],
            }
        )

    return multiples, unavailable


SEC_EPS_DILUTED_METRICS = (
    "eps_diluted",
    "METRIC_EPS_DILUTED",
    "EarningsPerShareDiluted",
)
SEC_EPS_CONCEPT = "us-gaap:EarningsPerShareDiluted"
SEC_EPS_UNIT = "USD/shares"

# The absolute agreement allowed when a value is used to confirm a record that
# identity has already selected. It is a confirmation tolerance, never a match
# criterion: no amount of numerical agreement on its own binds a source.
_EPS_VALUE_TOLERANCE = 0.005

# The observation metric whose value the engine read for each anchor basis.
# A forward anchor may have been built from either the vendor forward figure or
# the vendor consensus figure, because `build_start_anchor` labels both
# FORWARD_TWELVE_MONTHS; the value tells them apart downstream.
_EPS_METRIC_FOR_ANCHOR_BASIS: Dict[str, Tuple[str, ...]] = {
    ANCHOR_TTM: (METRIC_TRAILING_EPS,),
    ANCHOR_FORWARD: (METRIC_FORWARD_EPS, METRIC_CONSENSUS_FORWARD_EPS),
}


def _is_sec_filing_observation(observation: Any) -> bool:
    """
    Whether an observation's own declared identity says it came from a filing.

    The observation must carry the accession of a filing and declare itself a
    regulatory-filing source. A vendor observation that happens to hold the same
    number is not a filing observation, and neither is a static fixture.
    """
    raw = getattr(observation, "raw", None)
    if not isinstance(raw, dict):
        raw = {}
    accession = raw.get("accession") or raw.get("accn") or raw.get("accession_number")
    source_type = str(getattr(observation, "source_type", "") or "")
    return bool(accession) and source_type == SourceType.REGULATORY_FILING.value


def _observation_projecting_view_field(data: Any, metric: str) -> Optional[Observation]:
    """
    The observation `_apply_observations_to_view` used to fill one view field.

    It mirrors that projection's own selection (first available observation for
    the metric, else the first observed one), so "which observation supplied
    this field" is answered by the same rule that filled it rather than by a
    second guess.
    """
    observations = getattr(data, "observations", None)
    if observations is None:
        return None
    try:
        matches = observations.for_metric(metric)
    except Exception:
        return None
    if not matches:
        return None
    available = [item for item in matches if item.is_available]
    return (available or matches)[0]


def _vendor_source_reference(observation: Any) -> Tuple[Optional[str], Optional[str]]:
    """The provider field and endpoint that recorded a vendor-sourced value.

    Read from the observation's own recorded provenance -- the module/field it
    was read out of and the endpoint URL it came from -- never parsed out of the
    value and never taken from a related filing. Returns (None, None) when the
    observation carries no such provenance, so a caller leaves the field absent
    rather than inventing one.
    """
    if observation is None:
        return None, None
    raw = getattr(observation, "raw", None)
    raw = raw if isinstance(raw, dict) else {}
    module = raw.get("module")
    field = raw.get("field")
    if module and field:
        source_field: Optional[str] = f"{module}.{field}"
    elif field:
        source_field = str(field)
    else:
        source_field = None
    source_url = getattr(observation, "source_url", None)
    if not source_field and not source_url:
        return None, None
    return source_field, (str(source_url) if source_url else None)


def _vendor_eps_provenance(data: Any, metric: str) -> Dict[str, Any]:
    """
    The run-context provenance of one supplier EPS field.

    Read from the observation that projected the engine's own view field, by the
    same selection rule that filled it. The catalogue's supplier entries carry
    this identity so a requested supplier anchor is the same traceable figure
    the default path would have served.
    """
    observation = _observation_projecting_view_field(data, metric)
    source_field, source_url = _vendor_source_reference(observation)
    return {
        "observation": observation,
        "source_field": source_field,
        "source_url": source_url,
        "provider": getattr(observation, "provider", None) if observation is not None else None,
        "observation_type": getattr(observation, "source_type", None) if observation is not None else None,
        "retrieved_at": getattr(observation, "retrieved_at", None) if observation is not None else None,
        "observation_id": getattr(observation, "observation_id", None) if observation is not None else None,
    }


def _sec_observation_supplying_anchor(
    data: Any,
    anchor: Any,
    sec_observations: Optional[Sequence[Any]] = None,
    metrics: Optional[Sequence[str]] = None,
) -> Optional[Observation]:
    """
    The SEC observation that actually supplied the anchor's value, if any.

    The linkage is established by observation identity, not by value: the
    observation that projected the engine's own input field must be one of this
    run's acquired filing observations. When it is, the value really came out of
    that filing and the filing fact may be named as its source. When the field
    was projected from a vendor or fixture observation, no filing fact may be
    named, however close a historical figure's value is to it.

    ``metrics`` narrows the projection metrics checked, for a caller that
    already knows which engine field its figure came from; the default reads
    the mapping from the anchor's basis.
    """
    if anchor is None or getattr(anchor, "is_user_assumption", False):
        return None
    if metrics is None:
        metrics = _EPS_METRIC_FOR_ANCHOR_BASIS.get(str(getattr(anchor, "basis", "") or ""))
    if not metrics:
        return None
    anchor_value = safe_float(getattr(anchor, "value", None))
    if anchor_value is None:
        return None

    acquired: Dict[str, Any] = {}
    for observation in sec_observations or ():
        observation_id = getattr(observation, "observation_id", None)
        if observation_id:
            acquired[observation_id] = observation

    for metric in metrics:
        projecting = _observation_projecting_view_field(data, metric)
        if projecting is None:
            continue
        observation = acquired.get(getattr(projecting, "observation_id", None))
        if observation is None:
            continue
        if not _is_sec_filing_observation(observation):
            continue
        observed_value = safe_float(getattr(observation, "value", None))
        if observed_value is None or abs(observed_value - anchor_value) >= _EPS_VALUE_TOLERANCE:
            continue
        return observation
    return None


def _resolve_sec_eps_fact(
    target_value: Optional[float] = None,
    *,
    source_observation: Any = None,
) -> Optional[Dict[str, Any]]:
    """Return the SEC filing fact that actually supplied a selected EPS value.

    ``source_observation`` is the acquisition observation the value came from,
    identified by the caller through `_sec_observation_supplying_anchor`. The
    fact is built from that observation's own identity: concept, accession,
    form, filed date, period, unit and document reference. ``target_value`` is
    used only as a confirming compatibility check on the record already
    identified by identity; it never selects a record. Numerical equality
    between a vendor figure and a historical filing is not provenance, and the
    existence of filings for a ticker says nothing about where a value came
    from. With no linked observation this returns None and the caller must
    leave the direct SEC source absent rather than invent one.
    """
    if source_observation is None:
        return None
    return _sec_filing_fact_from_observation(source_observation, target_value)


def _sec_filing_fact_from_observation(
    observation: Any,
    target_value: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Build the filing fact from the observation that supplied the value."""
    raw = getattr(observation, "raw", None)
    if not isinstance(raw, dict):
        raw = {}
    metric = str(getattr(observation, "metric", "") or "")

    # The observation must name the diluted EPS concept, either by metric or by
    # the filing fact it was read out of. A figure the filing did not report as
    # diluted EPS is a different fact, whatever its value.
    sec_fact = raw.get("sec_fact")
    fact_tag = str(sec_fact.get("tag")) if isinstance(sec_fact, dict) else ""
    fact_taxonomy = str(sec_fact.get("taxonomy") or "us-gaap") if isinstance(sec_fact, dict) else ""
    declared_concept = f"{fact_taxonomy}:{fact_tag}" if (fact_taxonomy and fact_tag) else ""
    if metric in SEC_EPS_DILUTED_METRICS:
        concept = declared_concept or SEC_EPS_CONCEPT
    elif declared_concept == SEC_EPS_CONCEPT:
        # An acquisition that maps a filing fact onto the engine's own EPS
        # metric still names the concept it read, and that naming is what makes
        # the fact identifiable.
        concept = SEC_EPS_CONCEPT
    else:
        return None

    if not _is_sec_filing_observation(observation):
        return None

    accession = raw.get("accession") or raw.get("accn") or raw.get("accession_number")
    form = raw.get("form") or raw.get("form_type")
    filed = (
        raw.get("filed")
        or raw.get("filed_date")
        or raw.get("filing_date")
        or getattr(observation, "as_of", None)
    )
    period_start = getattr(observation, "period_start", None) or raw.get("start")
    period_end = getattr(observation, "period_end", None) or raw.get("end")
    if not (accession and form and filed and period_end):
        # Without the filing's own identity there is nothing to point at, and a
        # half-identified fact is not a source.
        return None

    # A confirming check only: the identified record must carry the selected
    # value, otherwise the input-to-fact linkage is not established after all.
    reported_value = safe_float(getattr(observation, "value", None))
    if target_value is not None and (
        reported_value is None
        or abs(reported_value - float(target_value)) >= _EPS_VALUE_TOLERANCE
    ):
        return None

    # The per-share unit is part of the fact's identity: a filing figure stated
    # in another unit is a different fact.
    reported_unit = str(raw.get("reported_currency_unit") or "")
    if reported_unit and reported_unit not in ("USD/shares", "USD-per-shares"):
        return None

    document_url = None
    source_document = raw.get("source_document")
    if isinstance(source_document, str) and source_document:
        document_url = (
            f"{source_document}{str(accession)}-index.htm"
            if source_document.endswith("/")
            else source_document
        )

    return {
        "accession": str(accession),
        "form": str(form),
        "filed_date": str(filed),
        "concept": concept,
        "unit": reported_unit or SEC_EPS_UNIT,
        "period_start": str(period_start or ""),
        "period_end": str(period_end),
        "document_url": document_url,
    }


# -- declared diluted-EPS evidence -------------------------------------------
#
# The vendor EPS anchor carries no declared period, and the issuer's own answer
# to "which period does this figure cover, and on which accounting basis" is in
# its filings. The SEC acquisition path already reads the filed
# us-gaap:EarningsPerShareDiluted facts for a run; these helpers publish the
# latest *directly stated* annual and interim facts from that acquisition so a
# reader can line the vendor figure up against declared periods and a declared
# GAAP basis.
#
# Two boundaries this evidence never crosses:
#
#   * It is cross-check evidence. It does not become the source of the
#     selected anchor -- that requires the input-to-fact linkage R2.1 defines --
#     and its presence never implies the vendor figure equals it.
#   * Only the filer's own statement counts. Derived windows (FY-minus-YTD
#     roll-forwards and summed discrete quarters) are the acquisition's own
#     arithmetic, not the filer's declaration, and are excluded by the presence
#     of `derivation` on the observation's raw payload.

DECLARED_EPS_SELECTION_RULE = (
    "Latest annual 10-K fiscal-year fact and latest discrete interim 10-Q "
    "quarter fact of us-gaap:EarningsPerShareDiluted, by period end; directly "
    "stated facts only (no FY-minus-YTD or summed-quarter derivations)."
)


def _declared_eps_fact_record(
    observation: Any,
    cik: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    A declared diluted-EPS fact, built from the observation's own identity.

    The record requires the filing's own identity (accession, form, filed
    date, period end) and the declared per-share unit; anything less is not a
    declared fact and is refused rather than half-identified. No value is ever
    matched or compared here: a record's identity is what it is, independent of
    whether the run's selected anchor happens to share its number.
    """
    if observation is None:
        return None
    if str(getattr(observation, "metric", "") or "") not in SEC_EPS_DILUTED_METRICS:
        return None
    raw = getattr(observation, "raw", None)
    raw = raw if isinstance(raw, dict) else {}
    if raw.get("derivation"):
        # The acquisition's own arithmetic is not the filer's statement.
        return None
    if not _is_sec_filing_observation(observation):
        return None

    sec_fact = raw.get("sec_fact") if isinstance(raw.get("sec_fact"), dict) else {}
    accession = raw.get("accession") or sec_fact.get("accession")
    form = raw.get("form") or sec_fact.get("form")
    filed = raw.get("filed") or sec_fact.get("filed")
    period_start = getattr(observation, "period_start", None) or sec_fact.get("start")
    period_end = getattr(observation, "period_end", None) or sec_fact.get("end")
    value = safe_float(getattr(observation, "value", None))
    unit = str(sec_fact.get("unit") or "")
    if unit and unit not in ("USD/shares", "USD-per-shares"):
        # A figure stated in another unit is a different fact.
        return None
    if not (accession and form and filed and period_end and value is not None):
        # Without the filing's own identity there is nothing to point at.
        return None

    document_url = None
    if cik and accession:
        cik_digits = str(cik).lstrip("0") or "0"
        document_url = (
            f"https://www.sec.gov/Archives/edgar/data/{cik_digits}/"
            f"{str(accession).replace('-', '')}/{accession}-index.htm"
        )

    return {
        "value": value,
        "currency": getattr(observation, "currency", None) or "USD",
        "unit": unit or SEC_EPS_UNIT,
        "concept": SEC_EPS_CONCEPT,
        "taxonomy": str(sec_fact.get("taxonomy") or "us-gaap"),
        "tag": str(sec_fact.get("tag") or "EarningsPerShareDiluted"),
        "accession": str(accession),
        "form": str(form),
        "fiscal_year": sec_fact.get("fy"),
        "fiscal_period": str(sec_fact.get("fp") or "") or None,
        "filed_date": str(filed),
        "available_at": getattr(observation, "available_at", None),
        "available_at_basis": getattr(observation, "available_at_basis", None),
        "period_start": str(period_start or ""),
        "period_end": str(period_end),
        "observation_id": getattr(observation, "observation_id", None),
        "source_url": getattr(observation, "source_url", None),
        "document_url": document_url,
    }


def _declared_eps_span_days(record: Dict[str, Any]) -> int:
    """The record's covered span, for ordering facts that share a period end."""
    start = str(record.get("period_start") or "")
    end = str(record.get("period_end") or "")
    if not start or not end:
        return 0
    try:
        return (date.fromisoformat(end) - date.fromisoformat(start)).days
    except ValueError:
        return 0


def _declared_eps_facts_from_observations(
    observations: Optional[Sequence[Any]],
    cik: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    The latest declared annual and interim diluted-EPS facts, or None each.

    Selection is deterministic: facts are ordered by period end, then by
    covered span (a cumulative fact wins over a shorter one ending the same
    day), then by filed date and accession. Derived observations never enter
    the candidate set (see `_declared_eps_fact_record`).
    """
    records: List[Dict[str, Any]] = []
    for observation in observations or ():
        record = _declared_eps_fact_record(observation, cik)
        if record is not None:
            records.append(record)

    def _order(record: Dict[str, Any]) -> Tuple[str, int, str, str]:
        return (
            str(record.get("period_end") or ""),
            _declared_eps_span_days(record),
            str(record.get("filed_date") or ""),
            str(record.get("accession") or ""),
        )

    annuals = [
        record
        for record in records
        if record.get("form") == "10-K"
        and str(record.get("fiscal_period") or "") == "FY"
    ]
    interims = [record for record in records if record.get("form") == "10-Q"]
    latest_annual = max(annuals, key=_order) if annuals else None
    latest_interim = max(interims, key=_order) if interims else None
    return latest_annual, latest_interim


def _frozen_declared_eps_evidence(ticker: str) -> Optional[Dict[str, Any]]:
    """
    The packaged dataset's latest annual diluted-EPS fact, as a full record.

    This reads the frozen instrument under `data/historical_pe/{ticker}` that
    the production research paths ship. It exists so a run that acquired no
    live filing evidence keeps the cross-check it always had; it is never
    preferred over the run's own acquisition, and a ticker without a packaged
    dataset has no fallback (the absence is stated, not filled).
    """
    concept_file = Path(f"data/historical_pe/{ticker}/eps_diluted_concept.json")
    if not concept_file.exists():
        return None
    try:
        with open(concept_file, "r", encoding="utf-8") as f:
            cdata = json.load(f)
        units = (cdata.get("units") or {}).get("USD/shares") or []
        annual_10k = [x for x in units if x.get("form") == "10-K" and x.get("fp") == "FY"]
        cand = annual_10k[-1] if annual_10k else (units[-1] if units else None)
        if not cand:
            return None
        accn = cand.get("accn")
        cik = cdata.get("cik")
        url = None
        if cik and accn:
            url = (
                f"https://www.sec.gov/Archives/edgar/data/{str(cik)}/"
                f"{str(accn).replace('-', '')}/{str(accn)}-index.htm"
            )
        return {
            "value": cand.get("val"),
            "currency": "USD",
            "unit": "USD/shares",
            "concept": SEC_EPS_CONCEPT,
            "taxonomy": "us-gaap",
            "tag": "EarningsPerShareDiluted",
            "accession": str(accn) if accn else None,
            "form": str(cand.get("form", "10-K")),
            "fiscal_year": cand.get("fy"),
            "fiscal_period": str(cand.get("fp") or "") or None,
            "filed_date": str(cand.get("filed") or ""),
            "available_at": None,
            "available_at_basis": None,
            "period_start": str(cand.get("start") or ""),
            "period_end": str(cand.get("end") or ""),
            "observation_id": None,
            "source_url": (
                f"https://data.sec.gov/api/xbrl/companyconcept/CIK{str(cik).zfill(10)}"
                f"/us-gaap/EarningsPerShareDiluted.json"
                if cik
                else None
            ),
            "document_url": url,
        }
    except Exception:
        return None


def _find_related_sec_evidence(
    ticker: str,
    sec_observations: Optional[Sequence[Any]] = None,
    cik: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Related SEC filing evidence for cross-check (not direct provenance).

    Prefers the latest declared annual fact from this run's own SEC
    acquisition; falls back to the packaged dataset's fact when the run
    acquired no filing evidence (the behaviour every existing caller had).
    The record shape is unchanged.
    """
    latest_annual: Optional[Dict[str, Any]] = None
    if sec_observations:
        latest_annual, _ = _declared_eps_facts_from_observations(
            sec_observations, cik
        )
    if latest_annual is None:
        latest_annual = _frozen_declared_eps_evidence(ticker)
    if latest_annual is None:
        return None
    return {
        "accession": latest_annual.get("accession"),
        "form": str(latest_annual.get("form") or "10-K"),
        "filed_date": str(latest_annual.get("filed_date") or ""),
        "concept": SEC_EPS_CONCEPT,
        "unit": SEC_EPS_UNIT,
        "period_start": str(latest_annual.get("period_start") or ""),
        "period_end": str(latest_annual.get("period_end") or ""),
        "document_url": latest_annual.get("document_url"),
        "note": "Related SEC filing (cross-check); not verified as direct source of selected EPS value",
    }


def _build_declared_eps_evidence_block(
    ticker: str,
    sec_eps_evidence: Optional[Dict[str, Any]],
    selected_anchor_is_sec_filing: bool = False,
) -> Dict[str, Any]:
    """
    The report-level statement of the declared diluted-EPS facts.

    Three states, stated rather than implied: `AVAILABLE` names the facts and
    where they came from, `UNAVAILABLE` says the acquisition asked and the
    source reported none, and `NOT_ACQUIRED` says this run never asked (and no
    packaged dataset exists to fall back on). Nothing is filled in.

    When the run's selected starting anchor is itself a filing figure, the
    cross-check note says so: the block then restates the same filing record's
    report-level view rather than claiming the facts are unrelated to the
    selection.
    """
    block: Dict[str, Any] = {
        "selection_rule": DECLARED_EPS_SELECTION_RULE,
        "basis": "GAAP_DILUTED_EPS",
        "concept": SEC_EPS_CONCEPT,
        "status": "NOT_ACQUIRED",
        "source": None,
        "provider": None,
        "source_type": None,
        "latest_annual": None,
        "latest_interim": None,
        "cross_check_note": (
            "The selected starting EPS is itself an issuer-reported filing "
            "anchor, so the declared facts below restate the filing record the "
            "anchor was adopted from."
            if selected_anchor_is_sec_filing
            else (
                "Declared filing facts are shown for cross-check only: they are not "
                "the source of the selected starting EPS, and no input-to-fact "
                "linkage is claimed. The vendor figure's own period coverage is "
                "declared by its source or explicitly reported as undeclared."
            )
        ),
        "unavailable": [],
    }

    if sec_eps_evidence is not None:
        observations = list(sec_eps_evidence.get("observations") or [])
        cik = sec_eps_evidence.get("cik")
        latest_annual, latest_interim = _declared_eps_facts_from_observations(
            observations, cik
        )
        if latest_annual is None and latest_interim is None:
            block["status"] = "UNAVAILABLE"
            block["source"] = "RUN_ACQUISITION"
            block["provider"] = "SecEdgar"
            block["source_type"] = SourceType.REGULATORY_FILING.value
            block["unavailable"].append(
                {
                    "item": "declared_eps_evidence",
                    "reason": (
                        "The SEC acquisition ran and reported no directly "
                        "stated diluted-EPS fact for this issuer, so no "
                        "declared period or basis can be shown for the EPS "
                        "anchor."
                    ),
                    "reason_kind": "SOURCE_SILENT",
                    "blocks": ["declared_eps_evidence"],
                }
            )
            return block
        block["status"] = "AVAILABLE"
        block["source"] = "RUN_ACQUISITION"
        block["provider"] = "SecEdgar"
        block["source_type"] = SourceType.REGULATORY_FILING.value
        block["latest_annual"] = latest_annual
        block["latest_interim"] = latest_interim
        if latest_annual is None:
            block["unavailable"].append(
                {
                    "item": "declared_eps_evidence.latest_annual",
                    "reason": (
                        "The acquired filing evidence carried no directly "
                        "stated 10-K fiscal-year diluted-EPS fact, so no "
                        "declared annual fact is shown."
                    ),
                    "reason_kind": "SOURCE_SILENT",
                    "blocks": ["declared_eps_evidence.latest_annual"],
                }
            )
        if latest_interim is None:
            block["unavailable"].append(
                {
                    "item": "declared_eps_evidence.latest_interim",
                    "reason": (
                        "The acquired filing evidence carried no directly "
                        "stated 10-Q quarterly diluted-EPS fact, so no "
                        "declared interim fact is shown."
                    ),
                    "reason_kind": "SOURCE_SILENT",
                    "blocks": ["declared_eps_evidence.latest_interim"],
                }
            )
        return block

    # This run acquired no filing evidence. The packaged dataset, where one
    # exists, keeps the cross-check it always supplied; nothing new is
    # fetched to fill the block, so the default path's network envelope is
    # unchanged.
    frozen = _frozen_declared_eps_evidence(ticker)
    if frozen is not None:
        block["status"] = "AVAILABLE"
        block["source"] = "PACKAGED_DATASET"
        block["provider"] = "SecEdgar"
        block["source_type"] = SourceType.REGULATORY_FILING.value
        block["latest_annual"] = frozen
        block["unavailable"].append(
            {
                "item": "declared_eps_evidence.latest_interim",
                "reason": (
                    "The packaged dataset supplies the latest annual fact "
                    "only; no interim fact is packaged. Run with --context to "
                    "acquire the issuer's filing evidence."
                ),
                "reason_kind": "NOT_AVAILABLE_IN_DATASET",
                "blocks": ["declared_eps_evidence.latest_interim"],
            }
        )
        return block

    block["unavailable"].append(
        {
            "item": "declared_eps_evidence",
            "reason": (
                "No SEC filing evidence was acquired in this run and no "
                "packaged dataset exists for this ticker, so no declared "
                "period or basis can be shown for the EPS anchor. Run with "
                "--context to acquire the issuer's filing evidence."
            ),
            "reason_kind": "NOT_ACQUIRED",
            "blocks": ["declared_eps_evidence"],
        }
    )
    return block


def _build_reverse_requirements(
    data: Any,
    analysis: Dict[str, Any],
    *,
    horizons_years: Sequence[float],
    required_returns: Sequence[float],
    reference_multiple: Optional[float] = None,
    reference_multiples: Optional[Sequence[Optional[float]]] = None,
    pfcf_multiple: Optional[float] = None,
    ev_ebitda_multiple: Optional[float],
    ps_multiple: Optional[float],
    include_risk_free_rates: bool,
    include_dcf: bool,
    beta: Optional[float],
    equity_risk_premium: Optional[float],
    risk_free_tenor: str,
    sec_observations: Optional[Sequence[Any]] = None,
    sec_eps_evidence: Optional[Dict[str, Any]] = None,
    cross_validation: Optional[Dict[str, Any]] = None,
    production_historical_pe: Optional[Dict[str, Any]] = None,
    production_historical_pfcf: Optional[Dict[str, Any]] = None,
    production_historical_multiples: Optional[Dict[str, Any]] = None,
    prefer_eps_anchor: Optional[str] = None,
    user_eps: Optional[float] = None,
    eps_xbrl_records: Optional[Sequence[Any]] = None,
    xbrl_records: Optional[Sequence[Any]] = None,
) -> Dict[str, Any]:
    """
    Assemble the V1 reverse requirements package from what this run observed.

    Nothing here re-derives a number the acquisition stage already produced; it
    selects among observed values, names what is missing, and hands the result
    to the pure module. Every optional input that was not supplied leaves its
    figure absent rather than defaulted.
    """
    from capital_structure import build_capital_structure
    from financial_history import build_financial_history
    from reverse_requirements import (
        build_consensus_reference,
        build_reverse_requirements_report,
        build_start_anchor,
        terminal_period_end,
    )
    from risk_free_rate_provider import (
        fetch_risk_free_rates,
        rate_as_decimal,
        select_rate,
    )
    from eps_anchor_evidence import (
        ANCHOR_SUPPLIER_CONSENSUS,
        ANCHOR_SUPPLIER_FORWARD,
        ANCHOR_SUPPLIER_TRAILING,
        NATURE_DERIVED,
        NATURE_DIRECT_FILING,
        NATURE_PROVIDER_REPORTED,
        SELECTION_RULE,
        build_eps_anchor_candidates,
        candidate_to_eps_anchor,
        is_explicit_anchor_id,
        is_legacy_anchor_preference,
        select_anchor,
        unknown_anchor_request_refusal,
    )
    import dataclasses

    unavailable: List[Dict[str, Any]] = []
    eps_anchor_catalogue: Optional[Dict[str, Any]] = None
    eps_anchor_selection: Optional[Dict[str, Any]] = None

    trailing_eps = safe_float(data.current_eps)
    forward_eps = safe_float(data.forward_eps)
    consensus_eps = safe_float(data.consensus_forward_eps)

    user_eps_val = safe_float(user_eps)
    if user_eps_val is not None:
        if user_eps_val > 0:
            from reverse_requirements import EpsAnchor, ANCHOR_USER
            anchor = EpsAnchor(
                value=user_eps_val,
                basis=ANCHOR_USER,
                months_covered=12.0,
                period_label="user supplied",
                provider="user",
                currency=data.currency,
                period_undeclared_by_source=False,
                source_type="USER_SUPPLIED",
                observation_id=None,
                is_user_assumption=True,
                sec_fact=None,
                sec_related_evidence=None,
            )
            anchor_unavailable = []
        else:
            anchor = None
            anchor_unavailable = [
                {
                    "item": "start_eps_candidate.user",
                    "reason": f"The supplied user EPS is {user_eps_val}, which is not positive.",
                    "reason_kind": "NOT_POSITIVE",
                    "blocks": ["start_anchor"],
                }
            ]
    elif (
        prefer_eps_anchor
        and not is_explicit_anchor_id(prefer_eps_anchor)
        and not is_legacy_anchor_preference(prefer_eps_anchor)
    ):
        # A request that names no catalogue anchor and no legacy preference is
        # refused outright: reinterpreting it as a preference would start the
        # growth bridge from a figure the caller did not ask for.
        requested_name = str(prefer_eps_anchor)
        refusal = unknown_anchor_request_refusal(requested_name)
        eps_anchor_selection = {
            "requested": requested_name,
            "mode": "EXPLICIT",
            "rule": SELECTION_RULE,
            "selected_anchor_id": None,
            "refused": [dict(refusal)],
        }
        anchor = None
        anchor_unavailable = [dict(refusal)]
    elif is_explicit_anchor_id(prefer_eps_anchor):
        # An explicit catalogue request names one anchor and is satisfied only
        # by that anchor: the catalogue is built from what this run observed
        # and what the tracked SEC datasets hold, the named entry is selected
        # or refused with its reason, and a refused anchor is never replaced by
        # a different figure.
        trailing_prov = _vendor_eps_provenance(data, METRIC_TRAILING_EPS)
        forward_prov = _vendor_eps_provenance(data, METRIC_FORWARD_EPS)
        consensus_prov = _vendor_eps_provenance(data, METRIC_CONSENSUS_FORWARD_EPS)
        catalogue = build_eps_anchor_candidates(
            ticker=data.ticker,
            valuation_date=data.price_date,
            currency=data.currency,
            trailing_eps=trailing_eps,
            forward_eps=forward_eps,
            consensus_eps=consensus_eps,
            provider=data.provider,
            trailing_source_field=trailing_prov["source_field"],
            trailing_source_url=trailing_prov["source_url"],
            trailing_observation_type=trailing_prov["observation_type"],
            trailing_retrieved_at=trailing_prov["retrieved_at"],
            trailing_observation_id=trailing_prov["observation_id"],
            forward_source_field=forward_prov["source_field"],
            forward_source_url=forward_prov["source_url"],
            forward_observation_type=forward_prov["observation_type"],
            forward_retrieved_at=forward_prov["retrieved_at"],
            forward_observation_id=forward_prov["observation_id"],
            consensus_source_field=consensus_prov["source_field"],
            consensus_source_url=consensus_prov["source_url"],
            consensus_observation_type=consensus_prov["observation_type"],
            consensus_retrieved_at=consensus_prov["retrieved_at"],
            consensus_observation_id=consensus_prov["observation_id"],
            run_observations=sec_observations,
            records=list(eps_xbrl_records or []) + list(xbrl_records or []),
        )
        selection = select_anchor(catalogue, str(prefer_eps_anchor))
        eps_anchor_catalogue = catalogue.contract_view()
        eps_anchor_selection = selection.contract_view()
        if selection.candidate is None:
            anchor = None
            anchor_unavailable = [dict(item) for item in selection.refused]
        else:
            candidate = selection.candidate
            anchor_unavailable = []
            anchor = candidate_to_eps_anchor(candidate, currency=data.currency)
            if candidate.nature == NATURE_PROVIDER_REPORTED:
                # A supplier entry is the same kind of figure the default path
                # serves, so it keeps the same run-context provenance, and the
                # direct-filing linkage follows the same identity rule.
                prov = {
                    ANCHOR_SUPPLIER_TRAILING: trailing_prov,
                    ANCHOR_SUPPLIER_FORWARD: forward_prov,
                    ANCHOR_SUPPLIER_CONSENSUS: consensus_prov,
                }[candidate.anchor_id]
                supplying = _sec_observation_supplying_anchor(
                    data,
                    anchor,
                    sec_observations,
                    metrics=(METRIC_TRAILING_EPS,)
                    if candidate.anchor_id == ANCHOR_SUPPLIER_TRAILING
                    else (METRIC_FORWARD_EPS,)
                    if candidate.anchor_id == ANCHOR_SUPPLIER_FORWARD
                    else (METRIC_CONSENSUS_FORWARD_EPS,),
                )
                sec_fact = _resolve_sec_eps_fact(
                    anchor.value, source_observation=supplying
                )
                sec_related = _find_related_sec_evidence(
                    data.ticker,
                    (sec_eps_evidence or {}).get("observations")
                    if sec_eps_evidence
                    else None,
                    (sec_eps_evidence or {}).get("cik") if sec_eps_evidence else None,
                )
                anchor = dataclasses.replace(
                    anchor,
                    source_type=str(
                        getattr(prov["observation"], "source_type", None)
                        or data.source_type
                        or "OBSERVED"
                    ),
                    observation_id=prov["observation_id"] or candidate.observation_id,
                    sec_fact=sec_fact,
                    sec_related_evidence=sec_related,
                    source_field=prov["source_field"],
                    source_url=prov["source_url"],
                    source_provider=prov["provider"],
                    source_observation_type=prov["observation_type"],
                    source_retrieved_at=prov["retrieved_at"],
                )
            else:
                # A filing anchor's source is the filing itself; the catalogue
                # entry already carries its accession, period and availability.
                anchor = dataclasses.replace(
                    anchor,
                    source_type=SourceType.REGULATORY_FILING.value,
                )
    else:
        anchor, anchor_unavailable = build_start_anchor(
            trailing_eps=trailing_eps,
            forward_eps=forward_eps,
            consensus_eps=consensus_eps,
            currency=data.currency,
            provider=data.provider,
            prefer=prefer_eps_anchor or "trailing",
        )
        if anchor is not None:
            obs_id = "ev-current-eps-001"
            if anchor.basis == "FORWARD_TWELVE_MONTHS":
                obs_id = "ev-forward-eps-001"
            elif anchor.basis == "CONSENSUS_FORWARD_TWELVE_MONTHS":
                obs_id = "ev-consensus-eps-001"
            # Strict source binding: the filing fact is the source of this value
            # only when the observation that projected the engine's input field
            # is one of this run's acquired SEC observations. A vendor forward
            # or consensus figure, or any value merely equal to a historical
            # filing figure, gets no SEC source attribution.
            supplying = _sec_observation_supplying_anchor(
                data, anchor, sec_observations
            )
            sec_fact = _resolve_sec_eps_fact(
                anchor.value, source_observation=supplying
            )
            # Related/cross-check evidence stays separate and must never be labeled direct source.
            # The run's own SEC acquisitions are preferred (they are identically
            # identified and current); the packaged dataset is the fallback for
            # runs that acquired none, which is the behaviour every existing
            # caller had.
            sec_related = _find_related_sec_evidence(
                data.ticker,
                (sec_eps_evidence or {}).get("observations")
                if sec_eps_evidence
                else None,
                (sec_eps_evidence or {}).get("cik") if sec_eps_evidence else None,
            )
            # The observation that projected this value is the value's actual
            # source. When it is a vendor observation, record its provider field
            # and endpoint so a provider-sourced EPS is traceable to its raw
            # material; a SEC filing observation is named by `sec_fact` instead.
            projecting = None
            for metric in _EPS_METRIC_FOR_ANCHOR_BASIS.get(str(anchor.basis or ""), ()):
                projecting = _observation_projecting_view_field(data, metric)
                if projecting is not None:
                    break
            source_field, source_url = _vendor_source_reference(projecting)
            source_provider = getattr(projecting, "provider", None) if projecting is not None else None
            source_observation_type = getattr(projecting, "source_type", None) if projecting is not None else None
            source_retrieved_at = getattr(projecting, "retrieved_at", None) if projecting is not None else None
            anchor = dataclasses.replace(
                anchor,
                source_type=str(data.source_type or "OBSERVED"),
                observation_id=obs_id,
                is_user_assumption=False,
                sec_fact=sec_fact,
                sec_related_evidence=sec_related,
                source_field=source_field,
                source_url=source_url,
                source_provider=source_provider,
                source_observation_type=source_observation_type,
                source_retrieved_at=source_retrieved_at,
            )
    unavailable.extend(anchor_unavailable)

    # When the adopted anchor is itself a filing figure, the declared-EPS
    # block's cross-check note must not claim the opposite. The flag is read
    # from the anchor's declared nature, never inferred from a value.
    adopted_sec_anchor = bool(
        anchor is not None
        and getattr(anchor, "anchor_id", None)
        and getattr(anchor, "anchor_nature", "") in (NATURE_DIRECT_FILING, NATURE_DERIVED)
    )

    if not reference_multiples:
        reference_multiples = [reference_multiple] if reference_multiple is not None else []
    reference_multiples = [value for value in reference_multiples if value is not None]
    if reference_multiple is not None and reference_multiple not in reference_multiples:
        reference_multiples = [reference_multiple] + list(reference_multiples)

    # Scenario exit multiples. A usable historical band contributes its
    # percentile set; every explicitly supplied multiple contributes its own
    # labelled point. Both are kept so a reader can tell a distribution
    # scenario from a stated assumption.
    scenario_multiples, scenario_unavailable = _build_exit_multiple_scenarios(
        historical_band=data.historical_pe_band,
        user_multiples=reference_multiples,
        min_observations=MIN_BAND_OBSERVATIONS_FOR_REFERENCE,
        production_historical_pe=production_historical_pe,
    )
    for entry in scenario_unavailable:
        if entry["item"] not in {item["item"] for item in unavailable}:
            unavailable.append(entry)

    # The earnings-multiple method takes a single representative reference. It
    # is the median of whatever the scenario set contains, and it is labelled
    # as such rather than being one arbitrary member of the range.
    representative = _representative_multiple(scenario_multiples)

    valuation_multiples, method_unavailable = _build_valuation_multiples(
        reference_multiple=(representative.value if representative is not None else None),
        representative=representative,
        pfcf_multiple=pfcf_multiple,
        ev_ebitda_multiple=ev_ebitda_multiple,
        ps_multiple=ps_multiple,
        historical_band=data.historical_pe_band,
        min_observations=MIN_BAND_OBSERVATIONS_FOR_REFERENCE,
        production_historical_pe=production_historical_pe,
        production_historical_multiples=production_historical_multiples,
    )
    unavailable.extend(method_unavailable)

    risk_free_rates = []
    cost_of_equity_inputs: Optional[Dict[str, Any]] = None
    if include_risk_free_rates:
        fetched = fetch_risk_free_rates()
        risk_free_rates = list(fetched.rates)
        unavailable.extend(
            dict(item) for item in fetched.unavailable
        )
        selected_rate = select_rate(risk_free_rates, risk_free_tenor)
        if selected_rate is None:
            unavailable.append(
                {
                    "item": f"risk_free_rate.{risk_free_tenor}",
                    "reason": (
                        f"The {risk_free_tenor} Treasury yield was not observed for "
                        f"{data.price_date}, so no cost of equity is modelled."
                    ),
                    "reason_kind": "MISSING",
                    "blocks": ["cost_of_equity"],
                }
            )
        cost_of_equity_inputs = {
            "risk_free_rate_decimal": rate_as_decimal(selected_rate),
            "risk_free_rate_source": (
                f"{selected_rate.provider} {selected_rate.instrument}"
                if selected_rate
                else ""
            ),
            "risk_free_rate_as_of": selected_rate.as_of if selected_rate else "",
            "beta": beta,
            "beta_source": "user_supplied",
            "beta_estimation_window": "not declared by the user",
            "equity_risk_premium_decimal": equity_risk_premium,
            "equity_risk_premium_source": "user_supplied",
            "equity_risk_premium_estimation_window": "not declared by the user",
        }
        if beta is None or equity_risk_premium is None or selected_rate is None:
            # Some but not all inputs arrived. Passing them through lets the
            # package name exactly which ones are absent, instead of reporting
            # the whole cost of equity as unavailable.
            missing = []
            if selected_rate is None:
                missing.append("risk_free_rate")
            if beta is None:
                missing.append("beta")
            if equity_risk_premium is None:
                missing.append("equity_risk_premium_decimal")
            unavailable.append(
                {
                    "item": "cost_of_equity",
                    "reason": (
                        "A CAPM cost of equity needs a risk-free rate, a beta and an equity "
                        f"risk premium. Missing: {', '.join(missing)}."
                    ),
                    "reason_kind": "MISSING",
                    "blocks": ["cost_of_equity"],
                }
            )
    else:
        unavailable.append(
            {
                "item": "risk_free_rate",
                "reason": (
                    "No risk-free rate was requested, so no cost of equity is modelled and "
                    "the rate family is empty. Pass --risk-free-rates with --beta and "
                    "--equity-risk-premium to compute one."
                ),
                "reason_kind": "NOT_REQUESTED",
                "blocks": ["cost_of_equity"],
            }
        )

    current_pe = safe_float(analysis["observed_valuation"].get("current_pe"))
    consensus_basis = ""
    consensus_months: Optional[float] = None
    consensus_period_end = data.consensus_forward_eps_period_end
    consensus_target_period_end: Optional[str] = None
    consensus_observations = (
        data.observations.for_metric(METRIC_CONSENSUS_FORWARD_EPS)
        if hasattr(data, "observations")
        else []
    )
    consensus_provider = (
        str(consensus_observations[0].provider) if consensus_observations else ""
    )
    if consensus_eps is not None:
        if data.consensus_forward_eps_period:
            # The vendor stated a period label. That label is not a period, so
            # the coverage this claim rests on is the fiscal-period end the
            # same row declared; when it declared one, that is what lines the
            # consensus up against a terminal EPS.
            consensus_basis = "FORWARD_TWELVE_MONTHS"
            consensus_months = 12.0
            if consensus_period_end:
                consensus_target_period_end = terminal_period_end(
                    data.price_date, 1.0
                )
            else:
                unavailable.append(
                    {
                        "item": "consensus_forward_eps_period_end",
                        "reason": (
                            "The consensus EPS carries a period label but no declared "
                            "period end, so no calendar year can be identified to line it "
                            "up against a terminal EPS."
                        ),
                        "reason_kind": "UNDECLARED",
                        "blocks": ["consensus_comparison"],
                    }
                )
        else:
            # The vendor returned a figure without stating which period it
            # covers. Comparing it against a terminal EPS would silently assume
            # it, so it is recorded as unusable for period comparison.
            unavailable.append(
                {
                    "item": "consensus_forward_eps_period",
                    "reason": (
                        "The consensus EPS carries no declared period, so it cannot be "
                        "lined up against a terminal EPS for a specific horizon."
                    ),
                    "reason_kind": "UNDECLARED",
                    "blocks": ["consensus_comparison"],
                }
            )

    dcf_inputs: Optional[Dict[str, Any]] = None
    if include_dcf:
        dcf_inputs = _dcf_inputs_from_run(
            data=data,
            analysis=analysis,
            cost_of_equity_inputs=cost_of_equity_inputs,
            required_returns=required_returns,
        )

    market_cap = safe_float(analysis["fundamental_snapshot"].get("current_market_cap"))
    enterprise_value = safe_float(
        analysis["fundamental_snapshot"].get("current_enterprise_value")
    )
    free_cash_flow = safe_float(analysis["fundamental_snapshot"].get("current_fcf"))
    ebitda = safe_float(analysis["fundamental_snapshot"].get("current_ebitda"))
    revenue = safe_float(analysis["fundamental_snapshot"].get("current_revenue"))

    observed_net_margin: Optional[float] = None
    observed_net_margin_period: Optional[str] = None
    history_observations = list(sec_observations or [])
    if history_observations:
        latest = _latest_net_margin(history_observations)
        if latest is not None:
            observed_net_margin, observed_net_margin_period = latest

    # The observed share count is read back out of the capital structure so
    # the implied margin can offer an observed-share variant beside the
    # original derived one.
    observed_shares: Optional[float] = None
    observed_shares_date: Optional[str] = None
    capital_early = build_capital_structure(
        history_observations,
        price=data.price,
        price_date=data.price_date,
        currency=data.currency,
        observed_market_cap=market_cap,
        observed_enterprise_value=enterprise_value,
        observed_ebitda=ebitda,
    )
    shares_latest = ((capital_early.get("observations") or {}).get("shares_outstanding") or {}).get("latest") or {}
    if shares_latest.get("present"):
        observed_shares = safe_float(shares_latest.get("value"))
        observed_shares_date = shares_latest.get("effective_date")

    # Sourced dividend observations and total-return inputs.
    from dividend_history import build_dividend_package
    from pathlib import Path
    chart_events = getattr(data, "chart_events", None)
    if not chart_events:
        daily_json = Path(f"data/historical_pe/{data.ticker}/daily_prices.json")
        if daily_json.exists():
            try:
                with open(daily_json, "r", encoding="utf-8") as f:
                    pdata = json.load(f)
                    chart_events = (((pdata.get("chart") or {}).get("result") or [{}])[0] or {}).get("events")
            except Exception:
                chart_events = None

    dividend_pkg = build_dividend_package(
        ticker=data.ticker,
        price=data.price,
        as_of=data.price_date,
        currency=data.currency,
        chart_events=chart_events,
        sec_observations=history_observations,
    )
    div_per_share = safe_float((dividend_pkg.get("summary") or {}).get("trailing_twelve_month_dividends"))
    div_source = str((dividend_pkg.get("summary") or {}).get("trailing_dividends_source") or "")

    # Keep financial history and capital structure available even when the
    # matrix cannot be built, so a missing starting EPS does not hide the
    # filed balance-sheet and income history that were acquired for the run.
    _early_history_observations = list(sec_observations or [])
    if _early_history_observations:
        from financial_history import build_financial_history as _bfh
        _early_financial_history = _bfh(
            _early_history_observations,
            instant_metrics=("assets", "cash", "long_term_debt", "shares_outstanding"),
        )
        _early_financial_history["observation_count"] = len(_early_history_observations)
        _early_financial_history["source_provider"] = str(
            getattr(_early_history_observations[0], "provider", "")
        )
    else:
        _early_financial_history = {
            "formula_version": "financial-history/1.0",
            "series": {},
            "growth": {},
            "margins": {},
            "observation_count": 0,
            "source_provider": None,
            "unavailable": [
                {
                    "item": "financial_history",
                    "reason": (
                        "No filing observations were acquired for this run, so no financial "
                        "history is presented. Pass --financial-history to acquire them."
                    ),
                    "reason_kind": "NOT_ACQUIRED",
                    "blocks": ["financial_history"],
                }
            ],
        }
    if _early_history_observations:
        from capital_structure import build_capital_structure as _bcs
        _early_capital_structure = _bcs(
            _early_history_observations,
            price=data.price,
            price_date=data.price_date,
            currency=data.currency,
            observed_market_cap=market_cap,
            observed_enterprise_value=enterprise_value,
            observed_ebitda=ebitda,
            cross_source=None,
        )
    else:
        _early_capital_structure = {
            "formula_version": "capital-structure/2.0",
            "status": "NOT_ACQUIRED",
            "observations": {},
            "observed": {},
            "reconstructed_market_cap": {"status": "NOT_COMPUTED", "value": None},
            "reconstructed_enterprise_value": {"status": "NOT_COMPUTED", "value": None},
            "observed_vs_reconstructed": [],
            "unavailable": [
                {
                    "item": "capital_structure",
                    "reason": (
                        "No filing observations were acquired for this run, so no balance "
                        "sheet or share count is presented."
                    ),
                    "reason_kind": "NOT_ACQUIRED",
                    "blocks": ["capital_structure"],
                }
            ],
        }

    if anchor is None:
        report = {
            "report": "reverse_requirements_v1",
            "formula_version": "reverse-requirements/1.1",
            "fingerprint": None,
            "asset": {"ticker": data.ticker, "currency": data.currency},
            "as_of": data.price_date,
            "market_price": {"value": data.price, "currency": data.currency, "source": data.price_source},
            "reverse_requirements_matrix": [],
            "matrix_size": 0,
            "cash_flow_cross_checks": {},
            "valuation_methods": {},
            "rate_families": {},
            "dcf": {},
            "production_historical_pe": production_historical_pe,
            "consensus_reference": build_consensus_reference(
                consensus_eps=consensus_eps,
                consensus_basis=consensus_basis,
                consensus_months_covered=consensus_months,
                consensus_provider=consensus_provider,
                consensus_period_label=data.consensus_forward_eps_period,
                consensus_period_end=consensus_period_end,
                consensus_target_period_end=consensus_target_period_end,
            ),
            "total_return_scenarios": None,
            "price_vs_total_return_comparison": [],
            "dividend_basis": None,
            "unavailable": list(unavailable),
            **(
                {
                    "eps_anchor_catalogue": eps_anchor_catalogue,
                    "eps_anchor_selection": eps_anchor_selection,
                }
                if eps_anchor_catalogue is not None or eps_anchor_selection is not None
                else {}
            ),
            "reading_notes": [
                "The baseline reverse-requirements matrix is strictly price-return-only; required returns exclude dividends.",
                "When a dividend per share is supplied, two additional scenario sets are computed: cash dividends retained and dividends reinvested at the target return.",
                "A required terminal EPS is the EPS that the chosen exit multiple corresponds to, not a forecast and not a market expectation.",
                "A CAGR is reported only when the gap between the two EPS anchors is long enough to annualise; otherwise the raw EPS change is reported without a rate.",
                "Risk-free rates, modelled cost of equity and investor target returns are three separate kinds of number and are never merged into one figure.",
            ],
            "financial_history": _early_financial_history,
            "capital_structure": _early_capital_structure,
            "dividends": dividend_pkg,
            "status": "NOT_COMPUTED",
            "status_reason": (
                "The reverse requirements matrix needs a positive starting EPS. "
                "See `unavailable` for what was missing."
            ),
            "declared_eps_evidence": _build_declared_eps_evidence_block(
                data.ticker,
                sec_eps_evidence,
                selected_anchor_is_sec_filing=adopted_sec_anchor,
            ),
        }
        return report

    price_obs = data.observations.get("ev-price-001") if hasattr(data, "observations") else None
    price_evidence = {
        "value": data.price,
        "currency": data.currency,
        "as_of": data.price_date,
        "provider": data.provider or data.price_source or "market",
        "source_type": str(data.source_type or "OBSERVED"),
        "observation_id": "ev-price-001" if price_obs is not None else "ev-price-001",
        "is_user_assumption": False,
    }

    report = build_reverse_requirements_report(
        price=data.price,
        ticker=data.ticker,
        currency=data.currency,
        as_of=data.price_date,
        price_source=data.price_source,
        horizons_years=horizons_years,
        required_returns=required_returns,
        exit_multiples=scenario_multiples,
        start_anchor=anchor,
        current_pe=current_pe,
        consensus_eps=consensus_eps,
        consensus_basis=consensus_basis,
        consensus_months_covered=consensus_months,
        consensus_period_label=data.consensus_forward_eps_period,
        consensus_period_end=consensus_period_end,
        consensus_target_period_end=consensus_target_period_end,
        consensus_provider=consensus_provider,
        dividend_per_share=div_per_share,
        dividend_source=div_source,
        market_cap=market_cap,
        enterprise_value=enterprise_value,
        free_cash_flow=free_cash_flow,
        ebitda=ebitda,
        revenue=revenue,
        pfcf_multiple=pfcf_multiple,
        ev_ebitda_multiple=ev_ebitda_multiple,
        ps_multiple=ps_multiple,
        observed_net_margin=observed_net_margin,
        observed_net_margin_period=observed_net_margin_period,
        observed_shares_outstanding=observed_shares,
        observed_shares_date=observed_shares_date,
        valuation_multiples=valuation_multiples,
        risk_free_rates=risk_free_rates,
        cost_of_equity_inputs=cost_of_equity_inputs,
        investor_required_returns={f"scenario_{index:02d}": value for index, value in enumerate(required_returns)},
        dcf_inputs=dcf_inputs,
        unavailable=unavailable,
        production_historical_pe=production_historical_pe,
        production_historical_pfcf=production_historical_pfcf,
        production_historical_multiples=production_historical_multiples,
        price_evidence=price_evidence,
        eps_anchor_catalogue=eps_anchor_catalogue,
        eps_anchor_selection=eps_anchor_selection,
    )

    report["dividends"] = dividend_pkg
    if dividend_pkg.get("unavailable"):
        for unav in dividend_pkg["unavailable"]:
            if unav["item"] not in {it.get("item") for it in report.get("unavailable", [])}:
                report["unavailable"].append(dict(unav))

    # The declared diluted-EPS facts the run's own SEC acquisition read, stated
    # as their own evidence block: declared period, form/accession and GAAP
    # concept, with the vendor anchor's undeclared coverage left as the vendor
    # stated it. Cross-check evidence only; it feeds no calculation.
    report["declared_eps_evidence"] = _build_declared_eps_evidence_block(
        data.ticker,
        sec_eps_evidence,
        selected_anchor_is_sec_filing=adopted_sec_anchor,
    )

    # Financial history from the same run's sourced observations. When no SEC
    # observations were acquired the block reports that rather than showing an
    # empty history that reads like a company with no filings.
    history_observations = list(sec_observations or [])
    if history_observations:
        report["financial_history"] = build_financial_history(
            history_observations,
            instant_metrics=("assets", "cash", "long_term_debt", "shares_outstanding"),
        )
        report["financial_history"]["observation_count"] = len(history_observations)
        report["financial_history"]["source_provider"] = str(
            getattr(history_observations[0], "provider", "")
        )
    else:
        report["financial_history"] = {
            "formula_version": "financial-history/1.0",
            "series": {},
            "growth": {},
            "margins": {},
            "observation_count": 0,
            "source_provider": None,
            "unavailable": [
                {
                    "item": "financial_history",
                    "reason": (
                        "No filing observations were acquired for this run, so no financial "
                        "history is presented. Pass --financial-history to acquire them."
                    ),
                    "reason_kind": "NOT_ACQUIRED",
                    "blocks": ["financial_history"],
                }
            ],
        }

    # Cross-source verdicts. These were already computed by the filing pass on
    # this path; without this they would be discarded, and the report would
    # continue to describe a single-source run while holding two.
    report["cross_source_validation"] = _serialise_cross_validation(cross_validation)

    # Capital structure is built only where the balance-sheet evidence was
    # actually acquired. Without it there is nothing to present, and an empty
    # section would read as a company with no balance sheet. It reads the
    # cross-source verdicts computed just above.
    if history_observations:
        from capital_structure import build_capital_structure

        report["capital_structure"] = build_capital_structure(
            history_observations,
            price=data.price,
            price_date=data.price_date,
            currency=data.currency,
            observed_market_cap=market_cap,
            observed_enterprise_value=enterprise_value,
            observed_ebitda=ebitda,
            cross_source=report.get("cross_source_validation"),
        )
        unavailable.extend(report["capital_structure"]["unavailable"])
    else:
        report["capital_structure"] = {
            "formula_version": "capital-structure/2.0",
            "status": "NOT_ACQUIRED",
            "observations": {},
            "observed": {},
            "reconstructed_market_cap": {"status": "NOT_COMPUTED", "value": None},
            "reconstructed_enterprise_value": {"status": "NOT_COMPUTED", "value": None},
            "observed_vs_reconstructed": [],
            "unavailable": [
                {
                    "item": "capital_structure",
                    "reason": (
                        "No filing observations were acquired for this run, so no balance "
                        "sheet or share count is presented."
                    ),
                    "reason_kind": "NOT_ACQUIRED",
                    "blocks": ["capital_structure"],
                }
            ],
        }

    if anchor is None or not scenario_multiples:
        # The matrix could not be built. Say so at the top level rather than
        # leaving an empty list to be read as "no scenarios were interesting".
        report["status"] = "NOT_COMPUTED"
        report["status_reason"] = (
            "The reverse requirements matrix needs a positive starting EPS and at least "
            "one exit multiple. See `unavailable` for what was missing."
        )
    else:
        report["status"] = "COMPUTED"
        report["status_reason"] = None
    return report


def _dcf_inputs_from_run(
    *,
    data: Any,
    analysis: Dict[str, Any],
    cost_of_equity_inputs: Optional[Dict[str, Any]],
    required_returns: Sequence[float],
) -> Dict[str, Any]:
    """
    Gather what a discounted cash flow model would need from this run.

    The inputs that a run can genuinely observe are filled in. The ones it
    cannot observe are left absent, which is what makes the feasibility check
    report the gap instead of the model quietly assuming a value.
    """
    snapshot = analysis.get("fundamental_snapshot") or {}
    free_cash_flow = safe_float(snapshot.get("current_fcf"))
    market_cap = safe_float(snapshot.get("current_market_cap"))
    enterprise_value = safe_float(snapshot.get("current_enterprise_value"))

    discount_rate = None
    discount_rate_source = ""
    if cost_of_equity_inputs and cost_of_equity_inputs.get("risk_free_rate_decimal") is not None:
        discount_rate = cost_of_equity_inputs.get("risk_free_rate_decimal")
        discount_rate_source = "not set from CAPM here; equity discount rate pending"

    if enterprise_value and market_cap and market_cap > 0:
        present_value = enterprise_value
        present_value_source = "observed enterprise value"
    elif market_cap:
        present_value = market_cap
        present_value_source = "observed market capitalization"
    else:
        present_value = None
        present_value_source = ""

    return {
        # Present, but the bridge from reported earnings to unlevered cash flow
        # is not observable from a vendor free cash flow figure alone.
        "cash_flow_basis": "",
        "free_cash_flow": free_cash_flow,
        "depreciation_amortisation": None,
        "capex": None,
        "working_capital_change": None,
        "cost_of_debt": None,
        "market_value_of_debt": None,
        "tax_rate": None,
        "discount_rate_decimal": discount_rate,
        "discount_rate_source": discount_rate_source,
        "explicit_years": 5,
        "terminal_growth_decimal": None,
        "terminal_growth_source": "",
        "present_value": present_value,
        "present_value_source": present_value_source,
        "base_cash_flow": free_cash_flow,
    }


def _latest_net_margin(
    observations: Sequence[Any],
) -> Optional[Tuple[float, str]]:
    """
    The most recent margin the filings support, and the period it covers.

    The implied net margin answers a question about net income per unit of
    revenue, so it is only meaningful beside a margin computed the same way from
    reported figures. Taking the latest annual one keeps the two on the same
    basis; where no margin exists the value stays absent rather than being
    borrowed from a different period.
    """
    from financial_history import build_financial_history

    history = build_financial_history(list(observations))
    rows = (history.get("margins") or {}).get("net_margin.annual") or []
    comparable = [row for row in rows if row.get("comparable") and row.get("margin") is not None]
    if not comparable:
        return None
    latest = comparable[-1]
    return float(latest["margin"]), str(latest.get("period_end") or "")


def _serialise_cross_validation(verdicts: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Flatten the cross-source verdicts into the run result.

    The verdicts are objects; the result is JSON. Each entry keeps its status,
    its explanation, the two observation ids it compared, and the basis it
    compared on, so a reader can see *why* two figures agree rather than only
    that they do. A metric that could not be compared keeps its reason instead
    of being dropped.
    """
    if not verdicts:
        return {
            "performed": False,
            "reason": (
                "No second source was consulted for this run, so no metric was "
                "cross-checked. A single-source figure is reported as such rather "
                "than presented as corroborated."
            ),
            "verdicts": {},
            "counts": {},
        }

    flattened: Dict[str, Any] = {}
    for metric, verdict in verdicts.items():
        record = getattr(verdict, "validation", None)
        if record is not None and hasattr(record, "contract_dict"):
            flattened[metric] = record.contract_dict()
        else:
            flattened[metric] = {
                "status": str(getattr(verdict, "status", "UNKNOWN")),
                "reasons": [],
                "comparison_basis": {},
                "explanation": "",
                "references": [],
            }
        basis = flattened[metric].get("comparison_basis") or {}
        flattened[metric]["vendor_observation"] = basis.get("vendor_observation")
        flattened[metric]["filing_observation"] = basis.get("filing_observation")
        flattened[metric]["vendor_value"] = basis.get("vendor_value")
        flattened[metric]["filing_value"] = basis.get("filing_value")
        flattened[metric]["period_offset_days"] = basis.get("period_offset_days")
        flattened[metric]["independence"] = basis.get("independence")

    counts: Dict[str, int] = {}
    for entry in flattened.values():
        status = str(entry.get("status") or "UNKNOWN")
        counts[status] = counts.get(status, 0) + 1

    return {
        "performed": True,
        "reason": "",
        "verdicts": flattened,
        "counts": counts,
        "summary": (
            "%d of %d metrics were cross-checked against a second source: %s."
            % (
                len(flattened),
                len(flattened),
                ", ".join("%d %s" % (count, status) for status, count in sorted(counts.items())),
            )
        ),
    }


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_regression_tests() -> None:
    print("=== ST-EVA 2.0 Regression Tests ===")

    for ticker, fixture_multiple in (("TENCENT", 18.5), ("MSFT", 30.0), ("NU", 20.0)):
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
        # The fixtures' historical P/E bands declare no sample count, so under
        # the unified eligibility rule they are descriptive only: they are
        # neither the summary's reference nor matrix scenarios. A reference-free
        # run therefore states that no reference exists, and the implied EPS
        # becomes computable only from an explicitly supplied multiple.
        assert_true(
            result["reference"]["historical_band_status"]["pe"]
            == "DESCRIPTIVE_ONLY_UNVERIFIED_SAMPLE_COUNT",
            f"{ticker}: the fixture band must stay descriptive-only",
        )
        assert_true(
            result["reference"]["method"] == "none",
            f"{ticker}: an undeclared-count band must not become the reference",
        )
        assert_true(
            result["market_implied_assumptions"][
                "forward_eps_at_reference_multiple"
            ] is None,
            f"{ticker}: no implied EPS may be fabricated without a reference",
        )

        explicit = run_st_eva(
            ticker,
            mode="regression",
            reference_multiple=fixture_multiple,
            save_snapshot=False,
        )
        assert_true(explicit is not None, f"{ticker}: explicit-multiple run missing")
        assert_true(
            abs(
                explicit["market_implied_assumptions"][
                    "forward_eps_at_reference_multiple"
                ]
                - (explicit["market_snapshot"]["price"] / fixture_multiple)
            ) < 1e-9,
            f"{ticker}: implied EPS from the supplied multiple failed",
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
    context_extra_observations: Sequence[Any] = (),
    captured_documents: Sequence[Any] = (),
) -> Any:
    """
    Persist one run: its observations, then its context.

    Every observation the context registered beyond the material set is
    archived here -- the facts a second source contributed and the consensus
    sample the selected estimate carries. Archiving a subset would leave the
    snapshot referencing facts the archive has never seen, and it could not be
    replayed.

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
    for observation in context_extra_observations:
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

    # 3.34: Persist admission decisions by identity if archive supports admissions table.
    # Persistence errors must be visible: returning a completed run without its
    # admission records would make the archive look more complete than it is.
    crossing_derivations: Optional[Dict[str, Any]] = None
    if getattr(archive, "_has_admissions", lambda: False)():
        from evidence_valuation_boundary import (
            admit,
            crossing_derivations as _crossing_derivations,
            V1_CROSSING_METRICS,
        )
        from registry_identity import registry_state_identity, resolver_policy_identity

        connection = getattr(archive, "connection", None)
        if connection is not None:
            reg_id = registry_state_identity(connection)
            pol_id = resolver_policy_identity(connection)
            price_obs = data.observations.get("ev-price-001")
            if price_obs is not None:
                as_of_date = data.price_date
                _, run_admissions = admit(
                    archive, asset, as_of_date, price_obs, metrics=V1_CROSSING_METRICS
                )
                for adm in run_admissions:
                    archive.record_admission(
                        asset, as_of_date, adm, reg_id, pol_id, price_obs
                    )
                # The figures the crossing derived, with the inputs and the rule
                # each was derived by. They are what the run's own filing
                # evidence produced, and they are reported so a reader can
                # check them rather than take them.
                crossing_derivations = _crossing_derivations(run_admissions)

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

    # Persist the context only after every supporting record succeeded.
    # Otherwise a failed admission/validation write could leave a replayable
    # snapshot that appears complete despite a missing part of its audit trail.
    if context is not None:
        fidelity = (
            "OBSERVATIONAL"
            if _uses_first_seen_observations(archive, context)
            else "SOURCE_DECLARED"
        )
        archive.record_context(asset, context, replay_fidelity=fidelity)

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
    # silently replace the engine's input with another provider's figure ??
    # which would silently replace an engine input with another provider's value.
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
    # The observation set carries comparable observations too, allowing the
    # context to preserve both sources. View fields stay material-derived, so
    # another source can never replace the engine's input.
    projected.observations = ObservationSet(
        ticker=ticker, observations=list(observations)
    )
    return projected


def ttm_window_observations(
    observations: Iterable[Observation],
) -> List[Observation]:
    """
    The trailing figures' source windows, as observations.

    A trailing figure the valuation used is the sum of the quarters its window
    holds, and the document recomputes that sum from the window rather than
    taking the engine's number on trust. So the window has to travel with the
    context, and a rebuild has to find it in the archive -- the same rule every
    other context observation obeys.
    """
    return [
        observation
        for observation in observations
        if observation is not None
        and observation.metric in TTM_WINDOW_METRICS
    ]


def consensus_sample_observations(
    observations: Iterable[Observation],
) -> List[Observation]:
    """
    The consensus sample the selected estimate carries, as observations.

    The source states `numberOfAnalysts`, a low/high range, revision counts and
    a trend series alongside the consensus average it aggregates. The engine
    reads only the average, so these are not material evidence and do not enter
    `EVIDENCE_METRICS`. The context registers them, though, so a snapshot that
    carries them can only be replayed when the archive holds them too -- the
    same rule every other context observation obeys. Selecting them here keeps
    the live context and its replay from drifting apart.
    """
    return [
        observation
        for observation in observations
        if observation is not None
        and observation.metric in CONSENSUS_EXTRA_METRICS
    ]


def build_context_from_observations(
    observations: Sequence[Observation],
    ticker: str,
    as_of: str,
    generated_at: str,
    company_name: str = "",
    exchange: str = "",
    asset_metadata: Optional[Dict[str, Any]] = None,
    production_historical_pe: Optional[Dict[str, Any]] = None,
    production_historical_pfcf: Optional[Dict[str, Any]] = None,
    production_historical_multiples: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build an Investment Context over an archived observation set.

    Replay calls this, so a replayed document is produced by exactly the code a
    live run uses. Nothing about the pipeline knows it is replaying; that is the
    point.

    `asset_metadata` carries what the archive knows about the instrument, so a
    replayed context does not diverge from the archived one over a company
    name.

    `production_historical_pe`, `production_historical_pfcf` and
    `production_historical_multiples` are the committed production historical
    distributions, read by the caller with the same loader a live run uses. A
    run that selected one of them as its reference is rebuilt with it in
    force, so the rebuild cannot report a reference the archived run did not
    use, nor miss the one it did.
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

    # A trailing figure the archived run used travels with the archive as its
    # source window, and the rebuild takes the figure from that window rather
    # than from the provider. The live path and the rebuild read it the same
    # way, so they cannot disagree about what the valuation used.
    from sec_derived_inputs import (
        ttm_value_from_window,
    )

    engine_inputs = ValuationInputs.from_legacy_view(data)
    window_updates: Dict[str, Any] = {}
    for observation in observations:
        metric = getattr(observation, "metric", None)
        if metric == "ttm_eps_window":
            value = ttm_value_from_window(observation)
            if value is not None:
                window_updates["current_eps"] = value
        elif metric == "ttm_fcf_window":
            value = ttm_value_from_window(observation)
            if value is not None:
                window_updates["current_fcf"] = value
        elif metric == "ttm_revenue_window":
            value = ttm_value_from_window(observation)
            if value is not None:
                window_updates["current_revenue"] = value
                currency = (observation.value or {}).get("currency")
                if currency:
                    window_updates["current_revenue_currency"] = currency
        elif metric == "ttm_ebitda_window":
            value = ttm_value_from_window(observation)
            if value is not None:
                window_updates["current_ebitda"] = value
    if window_updates:
        engine_inputs = replace(engine_inputs, **window_updates)
    analysis = MarketImpliedAssumptionsEngine.analyze(
        data=engine_inputs,
        production_historical_pe=production_historical_pe,
        production_historical_pfcf=production_historical_pfcf,
        production_historical_multiples=production_historical_multiples,
    )

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

    # The consensus sample travels with the estimate it belongs to, exactly as
    # it does on the live path: the rebuild must register the same
    # non-material observations the archived run did, or the two documents
    # cannot describe the same knowledge. The trailing figures' source windows
    # travel the same way, for the same reason: the document recomputes a
    # trailing figure from the window it holds.
    extra_observations = (
        filing
        + consensus_sample_observations(observations)
        + ttm_window_observations(observations)
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
        extra_observations=extra_observations,
        cross_validation=cross_validation,
        generated_at=generated_at,
        cik=metadata.get("cik"),
        sec_entity_name=metadata.get("sec_entity_name"),
    )


def _empty_sec_evidence() -> Dict[str, Any]:
    """The no-SEC shape, so callers never branch on whether it was fetched."""
    return {
        "observations": [],
        "documents": [],
        "cik": None,
        "entity_name": None,
        "cross_validation": {},
        "acquired": False,
    }


def _acquire_sec_evidence(
    data: MarketData,
    context_sources: Sequence[str],
) -> Dict[str, Any]:
    """
    Reach the SEC once and return what it contributed.

    Both the Investment Context and the financial history need the same filing
    observations. Fetching them in one place keeps a single answer to "what did
    the filings say" and avoids two network passes that could disagree if the
    upstream data changed between them.

    The cross-source pass is network-bound, so it happens only on the opt-in
    path. A run without it is still complete: the cross-source verdicts are
    simply absent, and the consumer can see that because the report states
    which sources it covers.
    """
    sources = {str(source).lower() for source in (context_sources or ())}
    empty: Dict[str, Any] = {
        "observations": [],
        "documents": [],
        "cik": None,
        "entity_name": None,
        "cross_validation": {},
        "acquired": False,
    }
    if "sec" not in sources:
        return empty

    from cross_validation import cross_validate_all
    from sec_provider import SECProvider

    acquisition = SECProvider().fetch(data.ticker)
    observations = list(acquisition.observations)
    vendor = [
        observation
        for observation in (
            data.observations.get(identifier)
            for identifier in data.observations.ids()
        )
        if observation is not None
        and is_comparable_observation(observation)
    ]
    return {
        "observations": observations,
        "documents": list(acquisition.documents),
        "cik": acquisition.company.cik if acquisition.company is not None else None,
        "entity_name": acquisition.company.name if acquisition.company is not None else None,
        "cross_validation": cross_validate_all(vendor, acquisition.observations),
        "acquired": True,
    }


def _ttm_window_period(
    qualified: Optional[Dict[str, Any]],
) -> Tuple[Optional[str], Optional[str]]:
    """
    The period a trailing window covers, as its first and last quarter's ends.

    A window is a trailing twelve months, so the period it covers is the
    quarters' own boundaries rather than the date the figure was computed on.
    """
    if not qualified:
        return None, None
    components = qualified.get("components") or []
    if not components:
        return None, None
    return components[0].get("period_end"), components[-1].get("period_end")


def _engine_inputs_with_filed_figures(
    inputs: ValuationInputs,
    *,
    data: "MarketData",
    production_historical_pe: Optional[Dict[str, Any]],
    production_historical_pfcf: Optional[Dict[str, Any]],
    production_historical_income: Optional[Dict[str, Any]] = None,
    ticker: str = "",
) -> Tuple[ValuationInputs, Dict[str, Any], List[Any]]:
    """
    The engine's inputs, and where each of them came from.

    Where a filed, qualified figure exists on the basis the multiple needs, it
    is the engine's input, and the provider's figure is recorded beside it as
    the cross-check it is. Where no such figure exists, the engine keeps the
    provider's and says so -- a fiscal year's figure and a quarter's figure
    are different quantities and neither may stand in for a trailing one.

    The returned windows are the trailing figures' source windows, as
    observations. They are handed to the document so it holds the quarters a
    trailing figure was built from and can recompute the sum itself, rather
    than taking the engine's number on trust.
    """
    from sec_derived_inputs import (
        BASIS_ANNUAL,
        BASIS_TTM,
        SOURCE_SEC_DERIVED,
        SOURCE_VENDOR,
        income_window_observation,
        qualified_ttm_ebitda,
        qualified_ttm_eps,
        qualified_ttm_fcf,
        qualified_ttm_revenue,
        ttm_value_from_window,
        window_observation,
    )

    as_of = data.price_date
    provenance: Dict[str, Any] = {}
    updates: Dict[str, Any] = {}
    windows: List[Any] = []

    def _vendor(metric, value, note):
        provenance[metric] = {
            "value": value,
            "source": SOURCE_VENDOR,
            "basis": "UNDECLARED",
            "used_by_engine": True,
            "note": note,
        }

    ttm_eps = qualified_ttm_eps(production_historical_pe, as_of)
    if ttm_eps is not None:
        # The qualified filed trailing figure becomes the engine's earnings
        # anchor. It is the same quantity the provider reported, on a basis
        # that is now stated, and the document recomputes it from the four
        # quarters it holds.
        window = window_observation(ttm_eps, metric="ttm_eps_window")
        ttm_value = ttm_value_from_window(window)
        if window is not None and ttm_value is not None:
            windows.append(window)
            updates["current_eps"] = ttm_value
        provenance["current_eps"] = {
            "value": updates.get("current_eps", inputs.current_eps),
            "source": SOURCE_SEC_DERIVED,
            "basis": BASIS_TTM,
            "used_by_engine": "current_eps" in updates,
            "currency": ttm_eps.get("currency"),
            "derivation": ttm_eps.get("derivation"),
            "usable_from": ttm_eps.get("usable_from"),
            "window": ttm_eps.get("window_anchor"),
            "components": ttm_eps.get("components"),
            "q4_evidence": ttm_eps.get("q4_evidence"),
            "derived_not_issuer_declared": bool(
                ttm_eps.get("derived_not_issuer_declared")
            ),
            "provider_figure": {
                "value": inputs.current_eps,
                "source": SOURCE_VENDOR,
                "basis": "UNDECLARED",
                "note": (
                    "the provider's trailing figure carries no declared period; "
                    "it is recorded as the cross-check it is and is not the "
                    "figure the multiple is computed from"
                ),
            },
            "note": (
                "a sum of four directly stated quarterly figures, the figure the "
                "earnings multiple is computed from, recomputed by the document "
                "from the quarters it holds"
            ),
        }
    else:
        _vendor(
            "current_eps",
            inputs.current_eps,
            "no qualified filed trailing diluted EPS is knowable at this cut, so "
            "the provider's undeclared trailing figure is what the engine used",
        )

    ttm_fcf = qualified_ttm_fcf(production_historical_pfcf, as_of)
    if ttm_fcf is not None:
        # The qualified filed trailing free cash flow becomes the engine's cash
        # flow input, on the same trailing basis the historical P/FCF reference
        # is computed on. The latest quarter's free cash flow stays a separate,
        # separately-labelled figure in the admission summary.
        window = window_observation(
            ttm_fcf,
            metric="ttm_fcf_window",
            requires_furnished_quarter=False,
            unit=Unit.CURRENCY.value,
        )
        ttm_value = ttm_value_from_window(window)
        if window is not None and ttm_value is not None:
            windows.append(window)
            updates["current_fcf"] = ttm_value
        provenance["current_fcf"] = {
            "value": updates.get("current_fcf", inputs.current_fcf),
            "source": SOURCE_SEC_DERIVED,
            "basis": BASIS_TTM,
            "used_by_engine": "current_fcf" in updates,
            "currency": ttm_fcf.get("currency"),
            "derivation": ttm_fcf.get("derivation"),
            "usable_from": ttm_fcf.get("usable_from"),
            "window": ttm_fcf.get("window_anchor"),
            "components": ttm_fcf.get("components"),
            "provider_figure": {
                "value": inputs.current_fcf,
                "source": SOURCE_VENDOR,
                "basis": "UNDECLARED",
                "note": (
                    "the provider's trailing figure carries no declared window; "
                    "it is recorded as the cross-check it is and is not the "
                    "figure the multiple is computed from"
                ),
            },
            "note": (
                "four consecutive quarters, the figure the cash-flow multiple is "
                "computed from, recomputed by the document from the quarters it "
                "holds; the latest quarter's free cash flow is a different "
                "quantity and is reported on its own in the admission summary"
            ),
        }
    else:
        _vendor(
            "current_fcf",
            inputs.current_fcf,
            "no qualified filed trailing free cash flow is knowable at this cut, so "
            "the provider's undeclared trailing figure is what the engine used",
        )

    # The trailing revenue and EBITDA, when a filed window qualifies. They are
    # the denominators of the sales and enterprise-value multiples, and a
    # vendor figure with no declared period is not one.
    ttm_revenue = qualified_ttm_revenue(production_historical_income, as_of, ticker)
    if ttm_revenue is not None:
        window = income_window_observation(
            ttm_revenue,
            metric="ttm_revenue_window",
            unit=Unit.CURRENCY.value,
        )
        ttm_value = ttm_value_from_window(window)
        if window is not None and ttm_value is not None:
            windows.append(window)
            updates["current_revenue"] = ttm_value
            updates["current_revenue_currency"] = ttm_revenue.get("currency")
        provenance["current_revenue"] = {
            "value": updates.get("current_revenue", inputs.current_revenue),
            "source": SOURCE_SEC_DERIVED,
            "basis": BASIS_TTM,
            "used_by_engine": "current_revenue" in updates,
            "currency": ttm_revenue.get("currency"),
            "derivation": ttm_revenue.get("derivation"),
            "usable_from": ttm_revenue.get("usable_from"),
            "window": ttm_revenue.get("window_anchor"),
            "period_start": _ttm_window_period(ttm_revenue)[0],
            "period_end": _ttm_window_period(ttm_revenue)[1],
            "components": ttm_revenue.get("components"),
            "provider_figure": {
                "value": inputs.current_revenue,
                "source": SOURCE_VENDOR,
                "basis": "UNDECLARED",
                "note": (
                    "the provider's trailing figure carries no declared period; "
                    "it is recorded as the cross-check it is and is not the "
                    "figure the sales multiple is computed from"
                ),
            },
            "note": (
                "four consecutive quarters of filed revenue, the figure the sales "
                "multiple is computed from, recomputed by the document from the "
                "quarters it holds; the filed annual revenue stays a separate "
                "figure in the admission summary with its own period"
            ),
        }
    else:
        _vendor(
            "current_revenue",
            inputs.current_revenue,
            "no qualified filed trailing revenue is knowable at this cut, so the "
            "provider's undeclared trailing figure is what the engine used; the "
            "filed annual figure for this metric is in the admission summary with "
            "its own period, and a fiscal year's revenue is not a trailing revenue",
        )

    ttm_ebitda = qualified_ttm_ebitda(production_historical_income, as_of, ticker)
    if ttm_ebitda is not None:
        window = income_window_observation(
            ttm_ebitda,
            metric="ttm_ebitda_window",
            unit=Unit.CURRENCY.value,
        )
        ttm_value = ttm_value_from_window(window)
        if window is not None and ttm_value is not None:
            windows.append(window)
            updates["current_ebitda"] = ttm_value
        provenance["current_ebitda"] = {
            "value": updates.get("current_ebitda", inputs.current_ebitda),
            "source": SOURCE_SEC_DERIVED,
            "basis": BASIS_TTM,
            "used_by_engine": "current_ebitda" in updates,
            "currency": ttm_ebitda.get("currency"),
            "derivation": ttm_ebitda.get("derivation"),
            "usable_from": ttm_ebitda.get("usable_from"),
            "window": ttm_ebitda.get("window_anchor"),
            "period_start": _ttm_window_period(ttm_ebitda)[0],
            "period_end": _ttm_window_period(ttm_ebitda)[1],
            "components": ttm_ebitda.get("components"),
            "provider_figure": {
                "value": inputs.current_ebitda,
                "source": SOURCE_VENDOR,
                "basis": "UNDECLARED",
                "note": (
                    "the provider's trailing figure carries no declared period; "
                    "it is recorded as the cross-check it is and is not the "
                    "figure the enterprise-value multiple is computed from"
                ),
            },
            "note": (
                "four consecutive quarters of operating income plus depreciation "
                "and amortization, the figure the enterprise-value multiple is "
                "computed from, recomputed by the document from the quarters it "
                "holds; the filed annual EBITDA stays a separate figure in the "
                "admission summary with its own period"
            ),
        }
    else:
        _vendor(
            "current_ebitda",
            inputs.current_ebitda,
            "no qualified filed trailing EBITDA is knowable at this cut, so the "
            "provider's undeclared trailing figure is what the engine used; the "
            "filed annual figure for this metric is in the admission summary with "
            "its own period, and a fiscal year's EBITDA is not a trailing EBITDA",
        )

    for metric in ("current_market_cap", "current_enterprise_value", "price"):
        provenance[metric] = {
            "value": getattr(inputs, metric, None),
            "source": SOURCE_VENDOR,
            "basis": "POINT_IN_TIME",
            "used_by_engine": True,
        }

    if updates:
        inputs = replace(inputs, **updates)
    inputs = replace(inputs, input_provenance=provenance)
    return inputs, provenance, windows


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
    sec_evidence: Dict[str, Any],
    ttm_windows: Sequence[Any] = (),
) -> Any:
    """
    Assemble an Investment Context from evidence already acquired.

    Returns the document, every observation the context registered beyond the
    material set (the second source's facts, the consensus sample and the
    trailing figures' source windows), and the source documents fetched. All go
    to the archive: a snapshot that references facts the archive never saw
    cannot be replayed, and an observation that does not name the document it
    came from is a number with an unverifiable origin.
    """
    from investment_context import build_investment_context

    sec_observations = list(sec_evidence.get("observations") or [])

    # The consensus sample travels with the estimate it belongs to. It is not
    # material evidence, so it is selected from the view's own observation set
    # and passed alongside rather than added to the evidence array. The
    # revision counts, trend series and in-series differences travel the same
    # way: each names the selected consensus row's period and declared end.
    consensus_sample = consensus_sample_observations(
        data.observations.get(identifier)
        for identifier in data.observations.ids()
    )
    # The trailing figures' source windows travel the same way. The document
    # recomputes a trailing figure from the quarters it holds, so it has to
    # hold them.
    context_extra_observations = (
        list(sec_observations) + list(consensus_sample) + list(ttm_windows)
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
        extra_observations=context_extra_observations,
        horizon_years=horizon_years,
        reference_multiple=reference_multiple,
        pfcf_multiple=pfcf_multiple,
        ev_ebitda_multiple=ev_ebitda_multiple,
        ps_multiple=ps_multiple,
        cross_validation=sec_evidence.get("cross_validation") or {},
        cik=sec_evidence.get("cik"),
        sec_entity_name=sec_evidence.get("entity_name"),
    ), context_extra_observations, list(sec_evidence.get("documents") or [])


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
        "--reference-multiples",
        type=float,
        nargs="+",
        default=None,
        metavar="PE",
        help=(
            "Several exit P/E values, each becoming its own axis of the reverse "
            "requirements matrix, so the result is a sensitivity range rather than "
            "one fixed multiple. Every value is recorded as a user assumption; none "
            "is treated as objectively correct. When a usable historical "
            "distribution exists, its percentiles join the same matrix and are "
            "labelled with their sample size."
        ),
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
    parser.add_argument(
        "--reverse-horizons",
        type=float,
        nargs="+",
        default=(1.0, 2.0, 3.0, 5.0),
        metavar="YEARS",
        help="Holding periods, in years, the reverse requirements matrix is built over.",
    )
    parser.add_argument(
        "--required-returns",
        type=float,
        nargs="+",
        default=(0.08, 0.10, 0.12, 0.15),
        metavar="RATE",
        help=(
            "Required price returns, as decimals, the matrix is built over. "
            "These are the investor's own hurdles, not a modelled cost of equity."
        ),
    )
    parser.add_argument(
        "--risk-free-rates",
        action="store_true",
        help="Fetch observed US Treasury yields for the valuation date.",
    )
    parser.add_argument(
        "--risk-free-tenor",
        default="10_YEAR",
        choices=("13_WEEK", "5_YEAR", "10_YEAR", "30_YEAR"),
        help="Which observed yield a CAPM cost of equity would use.",
    )
    parser.add_argument(
        "--beta",
        type=float,
        default=None,
        help=(
            "Beta for a CAPM cost of equity. A user-supplied assumption, not an "
            "observation; it is recorded with that provenance in the output."
        ),
    )
    parser.add_argument(
        "--equity-risk-premium",
        type=float,
        default=None,
        help="Equity risk premium for a CAPM cost of equity, as a decimal.",
    )
    parser.add_argument(
        "--dossier",
        dest="dossier_path",
        nargs="?",
        const="-",
        default=None,
        metavar="PATH",
        help=(
            "Opt-in: write the ordered research dossier. Use '-' for stdout. "
            "Built from the same result as --json, so the two cannot disagree."
        ),
    )
    parser.add_argument(
        "--dossier-report",
        action="store_true",
        help="Also render the dossier as readable text alongside the standard report.",
    )
    parser.add_argument(
        "--financial-history",
        action="store_true",
        help=(
            "Acquire SEC filings and present revenue, earnings and EPS history "
            "with growth rates and margins. Off by default because it reaches the "
            "network. When combined with --context the filings are fetched once "
            "and both use them."
        ),
    )
    parser.add_argument(
        "--no-dcf",
        dest="include_dcf",
        action="store_false",
        help=(
            "Skip the discounted cash flow feasibility check. The check reports "
            "which inputs are missing; it does not estimate them."
        ),
    )
    parser.add_argument("--no-snapshot", action="store_true")
    parser.add_argument("--test", action="store_true")
    parser.add_argument(
        "--prefer-eps-anchor",
        dest="prefer_eps_anchor",
        default=None,
        metavar="ANCHOR_ID",
        help="Select a specific EPS anchor from the issuer catalogue.",
    )
    parser.add_argument(
        "--eps-xbrl-document",
        dest="eps_xbrl_document",
        action="append",
        default=None,
        metavar="PATH",
        help="Parse a raw Inline XBRL document for dimensional EPS facts.",
    )
    parser.add_argument(
        "--eps-xbrl-manifest",
        dest="eps_xbrl_manifest",
        default=None,
        metavar="PATH",
        help="JSON manifest of raw Inline XBRL documents with per-file metadata.",
    )
    parser.add_argument(
        "--eps-xbrl-accession",
        dest="eps_xbrl_accession",
        default=None,
        metavar="ACCESSION",
    )
    parser.add_argument(
        "--eps-xbrl-form",
        dest="eps_xbrl_form",
        default="10-K",
        metavar="FORM",
    )
    parser.add_argument(
        "--eps-xbrl-filed",
        dest="eps_xbrl_filed",
        default=None,
        metavar="DATE",
    )
    parser.add_argument(
        "--eps-xbrl-fiscal-year",
        dest="eps_xbrl_fiscal_year",
        type=int,
        default=None,
        metavar="YEAR",
    )
    parser.add_argument(
        "--eps-xbrl-fiscal-period",
        dest="eps_xbrl_fiscal_period",
        default=None,
        metavar="PERIOD",
    )
    parser.add_argument(
        "--eps-xbrl-acceptance-datetime",
        dest="eps_xbrl_acceptance_datetime",
        default=None,
        metavar="DATETIME",
    )
    parser.add_argument(
        "--eps-xbrl-assurance-status",
        dest="eps_xbrl_assurance_status",
        default="UNKNOWN",
        metavar="STATUS",
    )
    parser.add_argument(
        "--eps-xbrl-expected-cik",
        dest="eps_xbrl_expected_cik",
        default=None,
        metavar="CIK",
    )
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
            "Opt-in: also write an Investment Context. Use '-' for "
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
    parser.add_argument(
        "--historical-pe",
        dest="historical_pe",
        action="store_true",
        help=(
            "Opt-in: build production point-in-time historical P/E series and reference "
            "distribution from SEC filings and pricing history."
        ),
    )
    parser.add_argument(
        "--no-furnished-pe",
        dest="no_furnished_pe",
        action="store_true",
        help="Negative path: disable Form 8-K Item 2.02 furnished evidence in historical P/E.",
    )
    parser.add_argument(
        "--historical-pfcf",
        dest="historical_pfcf",
        action="store_true",
        help=(
            "Opt-in: build the production point-in-time historical P/FCF reference "
            "distribution from filed cash-flow statements, the canonical daily price "
            "series and cover-page shares outstanding."
        ),
    )
    parser.add_argument(
        "--historical-multiples",
        dest="historical_multiples",
        action="store_true",
        help=(
            "Opt-in: build the production point-in-time historical P/S and "
            "EV/EBITDA reference distributions from the filed trailing "
            "revenue and EBITDA windows, the canonical daily price series, "
            "cover-page shares outstanding and filed balance-sheet components."
        ),
    )
    parser.add_argument(
        "--historical-income",
        dest="historical_income",
        action="store_true",
        help=(
            "Opt-in: load the production filed income-statement dataset, so the "
            "trailing revenue and trailing EBITDA the sales and enterprise-value "
            "multiples are computed from are the filed four-quarter figures."
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
        reference_multiples=args.reference_multiples,
        horizon_years=args.horizon_years,
        pfcf_multiple=args.pfcf_multiple,
        ev_ebitda_multiple=args.ev_ebitda_multiple,
        ps_multiple=args.ps_multiple,
        save_snapshot=not args.no_snapshot,
        context_path=args.context_path,
        context_sources=args.context_sources,
        archive=archive,
        reverse_horizons=tuple(args.reverse_horizons),
        required_returns=tuple(args.required_returns),
        include_risk_free_rates=args.risk_free_rates,
        include_dcf=args.include_dcf,
        beta=args.beta,
        equity_risk_premium=args.equity_risk_premium,
        risk_free_tenor=args.risk_free_tenor,
        include_financial_history=args.financial_history,
        dossier_path=args.dossier_path,
        render_dossier_report=args.dossier_report,
        include_historical_pe=args.historical_pe,
        enable_furnished_pe=not args.no_furnished_pe,
        include_historical_pfcf=args.historical_pfcf,
        include_historical_multiples=args.historical_multiples,
        include_historical_income=args.historical_income,
        prefer_eps_anchor=args.prefer_eps_anchor,
        user_eps=args.user_eps if hasattr(args, "user_eps") else None,
        eps_xbrl_documents=_cli_eps_xbrl_documents(args),
        eps_xbrl_expected_cik=getattr(args, "eps_xbrl_expected_cik", None),
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
        if args.dossier_report and result.get("dossier_report_text"):
            print("\n" + result["dossier_report_text"])


def _cli_eps_xbrl_documents(args: Any) -> Optional[List[Dict[str, Any]]]:
    documents: List[Dict[str, Any]] = []
    if getattr(args, "eps_xbrl_manifest", None):
        try:
            with open(str(args.eps_xbrl_manifest), "r", encoding="utf-8") as handle:
                import json as _json
                payload = _json.load(handle)
            if isinstance(payload, list):
                for item in payload:
                    if isinstance(item, dict):
                        documents.append(dict(item))
                    elif isinstance(item, str):
                        documents.append({"path": item})
        except (OSError, ValueError) as exc:
            raise ValueError(f"EPS XBRL manifest unreadable or invalid JSON: {args.eps_xbrl_manifest}: {exc}")
    if getattr(args, "eps_xbrl_document", None):
        for path in args.eps_xbrl_document:
            documents.append(
                {
                    "path": path,
                    "accession": getattr(args, "eps_xbrl_accession", None),
                    "form": getattr(args, "eps_xbrl_form", None) or "10-K",
                    "filed": getattr(args, "eps_xbrl_filed", None),
                    "fiscal_year": getattr(args, "eps_xbrl_fiscal_year", None),
                    "fiscal_period": getattr(args, "eps_xbrl_fiscal_period", None),
                    "acceptance_datetime": getattr(args, "eps_xbrl_acceptance_datetime", None),
                    "assurance_status": getattr(args, "eps_xbrl_assurance_status", None) or "UNKNOWN",
                    "expected_cik": getattr(args, "eps_xbrl_expected_cik", None),
                }
            )
    return documents or None


if __name__ == "__main__":
    main()
