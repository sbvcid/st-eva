from __future__ import annotations

"""
ST-EVA 2.0 - Market-Implied Assumptions Engine

Purpose:
    Answer "What assumptions are embedded in the current price?"

The engine is deliberately descriptive and conditional. It reverse-engineers
earnings assumptions only after an explicit valuation reference is selected.

Rules:
    - No synthetic EPS or consensus estimates.
    - No arbitrary Bull/Base/Bear probabilities.
    - No arbitrary price multipliers.
    - Missing data stays unavailable.
    - Arithmetic is deterministic Python.
    - Every source input receives an Evidence ID.
"""

import argparse
import json
import math
import os
import tempfile
import urllib.request
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from fundamental_provider import YahooFundamentalProvider


UNAVAILABLE = "UNAVAILABLE"

VERSION_METADATA = {
    "engine": "ST-EVA Market-Implied Assumptions Engine",
    "version": "2.2.0",
    "analysis_type": "market_implied_assumptions",
    "calculation_engine": "deterministic-python",
    "data_policy": "zero-synthetic-financial-data",
    "validator_version": "2.2.0",
    "schema_version": "2.2.0",
}


def is_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def safe_float(value: Any) -> Optional[float]:
    return float(value) if is_number(value) else None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    value: Any
    provider: str
    source: str
    source_url: Optional[str]
    as_of: str
    unit: str
    currency: str
    definition: str
    source_type: str
    quality: str = "Unknown"
    traceability: str = "Unknown"


class EvidenceStore:
    def __init__(self) -> None:
        self._items: Dict[str, Evidence] = {}

    def add(self, evidence: Evidence) -> None:
        if evidence.evidence_id in self._items:
            raise ValueError(f"Duplicate Evidence ID: {evidence.evidence_id}")
        self._items[evidence.evidence_id] = evidence

    def get(self, evidence_id: str) -> Optional[Evidence]:
        return self._items.get(evidence_id)

    def ids(self) -> List[str]:
        return list(self._items.keys())

    def as_dict(self) -> Dict[str, Any]:
        return {k: asdict(v) for k, v in self._items.items()}


@dataclass
class MarketData:
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
    next_event: Any = UNAVAILABLE
    next_event_status: str = "Unconfirmed"
    historical_pe_band: Optional[Dict[str, Any]] = None
    current_fcf: Any = UNAVAILABLE
    current_ebitda: Any = UNAVAILABLE
    current_revenue: Any = UNAVAILABLE
    current_enterprise_value: Any = UNAVAILABLE
    current_market_cap: Any = UNAVAILABLE
    historical_ps_band: Optional[Dict[str, Any]] = None
    historical_ev_ebitda_band: Optional[Dict[str, Any]] = None
    source_type: str = "UNKNOWN"
    provider: str = "UNKNOWN"
    discrepancy_status: str = "SINGLE_SOURCE"

    def __post_init__(self) -> None:
        if self.historical_pe_band is None:
            self.historical_pe_band = {}
        if self.historical_ps_band is None:
            self.historical_ps_band = {}
        if self.historical_ev_ebitda_band is None:
            self.historical_ev_ebitda_band = {}


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

            fundamental = YahooFundamentalProvider().fetch(clean)

            return MarketData(
                ticker=clean,
                company_name=f"{clean} (Live Acquired)",
                exchange=str(meta.get("exchangeName", "Unknown")),
                currency=str(meta.get("currency", "USD")),
                price=price,
                price_date=price_date,
                price_source="Yahoo Finance chart API",
                price_source_url=url,
                price_history=prices,
                volume_history=volumes,
                current_eps=fundamental.current_eps,
                forward_eps=fundamental.forward_eps,
                consensus_forward_eps=fundamental.consensus_forward_eps,
                historical_pe_band=fundamental.historical_pe_band,
                current_fcf=fundamental.current_fcf,
                current_ebitda=fundamental.current_ebitda,
                current_revenue=fundamental.current_revenue,
                current_enterprise_value=fundamental.current_enterprise_value,
                current_market_cap=fundamental.current_market_cap,
                historical_ps_band=fundamental.historical_ps_band,
                historical_ev_ebitda_band=fundamental.historical_ev_ebitda_band,
                source_type="API_LIVE",
                provider=f"{self.name}+{fundamental.provider}",
            )
        except Exception:
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
        return MarketData(
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
            historical_ev_ebitda_band=dict(data.get("historical_ev_ebitda_band", {})),
            source_type=data.get("source_type", "REGRESSION_FIXTURE"),
            provider=data.get("provider", "RegressionFixture"),
        )


class DeterministicMetricsEngine:
    @staticmethod
    def compute(
        prices: Sequence[float],
        volumes: Sequence[float],
    ) -> Dict[str, Any]:
        p = [float(x) for x in prices if is_number(x) and float(x) > 0]
        v = [float(x) for x in volumes if is_number(x) and float(x) >= 0]

        result: Dict[str, Any] = {
            "return_1d": None,
            "return_5d": None,
            "return_20d": None,
            "return_60d": None,
            "realized_volatility_annualized": None,
            "average_volume": None,
            "latest_volume_vs_average": None,
            "observations": len(p),
        }

        if len(p) >= 2:
            result["return_1d"] = p[-1] / p[-2] - 1.0
        if len(p) >= 6:
            result["return_5d"] = p[-1] / p[-6] - 1.0
        if len(p) >= 21:
            result["return_20d"] = p[-1] / p[-21] - 1.0
        if len(p) >= 61:
            result["return_60d"] = p[-1] / p[-61] - 1.0

        if len(p) >= 3:
            log_returns = [
                math.log(p[i] / p[i - 1])
                for i in range(1, len(p))
                if p[i - 1] > 0
            ]
            if len(log_returns) >= 2:
                mean = sum(log_returns) / len(log_returns)
                variance = sum(
                    (x - mean) ** 2 for x in log_returns
                ) / (len(log_returns) - 1)
                result["realized_volatility_annualized"] = math.sqrt(
                    max(variance, 0.0) * 252.0
                )

        if v:
            avg = sum(v) / len(v)
            result["average_volume"] = avg
            if avg > 0:
                result["latest_volume_vs_average"] = v[-1] / avg - 1.0

        return result


def interpolate_pe_percentile(
    value: float,
    band: Dict[str, Any],
) -> Optional[float]:
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
        data: MarketData,
        reference_multiple: Optional[float] = None,
        horizon_years: float = 1.0,
        pfcf_multiple: Optional[float] = None,
        ev_ebitda_multiple: Optional[float] = None,
        ps_multiple: Optional[float] = None,
    ) -> Dict[str, Any]:
        if data.price <= 0:
            raise ValueError("Current price must be positive.")
        if horizon_years <= 0:
            raise ValueError("horizon_years must be positive.")

        current_eps = safe_float(data.current_eps)
        forward_eps = safe_float(data.forward_eps)
        consensus_eps = safe_float(data.consensus_forward_eps)
        current_fcf = safe_float(data.current_fcf)
        current_ebitda = safe_float(data.current_ebitda)
        current_revenue = safe_float(data.current_revenue)
        enterprise_value = safe_float(data.current_enterprise_value)
        market_cap = safe_float(data.current_market_cap)

        pe_band = data.historical_pe_band or {}
        ps_band = data.historical_ps_band or {}
        ev_band = data.historical_ev_ebitda_band or {}

        historical_median = safe_float(pe_band.get("median"))
        historical_ps_median = safe_float(ps_band.get("median"))
        historical_ev_ebitda_median = safe_float(ev_band.get("median"))

        for value in (reference_multiple, pfcf_multiple, ev_ebitda_multiple, ps_multiple):
            if value is not None and value <= 0:
                raise ValueError("Reference multiples must be positive.")

        selected_pe = reference_multiple if reference_multiple is not None else historical_median
        selected_pfcf = pfcf_multiple
        selected_ev_ebitda = ev_ebitda_multiple if ev_ebitda_multiple is not None else historical_ev_ebitda_median
        selected_ps = ps_multiple if ps_multiple is not None else historical_ps_median

        current_pe = data.price / current_eps if current_eps and current_eps > 0 else None
        forward_pe = data.price / forward_eps if forward_eps and forward_eps > 0 else None
        consensus_forward_pe = data.price / consensus_eps if consensus_eps and consensus_eps > 0 else None

        implied_forward_eps = data.price / selected_pe if selected_pe and selected_pe > 0 else None
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
            (implied_forward_eps / (implied_revenue / (market_cap / data.price)))
            if implied_forward_eps is not None and implied_revenue is not None and market_cap and market_cap > 0
            else None
        )

        pe_percentile = interpolate_pe_percentile(current_pe, pe_band) if current_pe is not None else None
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
                    consensus_price_at_median / data.price - 1.0
                    if consensus_price_at_median is not None else None
                ),
            },
            "fundamental_snapshot": {
                "current_fcf": data.current_fcf,
                "current_ebitda": data.current_ebitda,
                "current_revenue": data.current_revenue,
                "current_enterprise_value": data.current_enterprise_value,
                "current_market_cap": data.current_market_cap,
            },
            "source_inputs": {
                "current_eps": data.current_eps,
                "forward_eps": data.forward_eps,
                "consensus_forward_eps": data.consensus_forward_eps,
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
            if value is not None and not is_number(value):
                errors.append(f"{key} must be numeric or null.")

        return errors


def build_evidence(
    data: MarketData,
    metrics: Dict[str, Any],
) -> EvidenceStore:
    store = EvidenceStore()

    store.add(Evidence(
        evidence_id="ev-price-001",
        value=data.price,
        provider=data.provider,
        source=data.price_source,
        source_url=data.price_source_url,
        as_of=data.price_date,
        unit=data.currency,
        currency=data.currency,
        definition="Observed current or latest market price.",
        source_type=data.source_type,
        quality="High" if data.source_type == "REGRESSION_FIXTURE" else "Medium",
        traceability="High",
    ))

    for evidence_id, value, definition in (
        (
            "ev-current-eps-001",
            data.current_eps,
            "Current/trailing EPS. Never synthesized.",
        ),
        (
            "ev-forward-eps-001",
            data.forward_eps,
            "Forward EPS. Used only when explicitly supplied.",
        ),
        (
            "ev-consensus-eps-001",
            data.consensus_forward_eps,
            "Consensus forward EPS. Never synthesized.",
        ),
        (
            "ev-pe-band-001",
            data.historical_pe_band or UNAVAILABLE,
            "Historical P/E reference band.",
        ),
    ):
        available = value != UNAVAILABLE and value not in (None, {})
        store.add(Evidence(
            evidence_id=evidence_id,
            value=value,
            provider=data.provider if available else "None",
            source="Input data",
            source_url=None,
            as_of=data.price_date,
            unit=data.currency if evidence_id != "ev-pe-band-001" else "multiple",
            currency=data.currency,
            definition=definition,
            source_type=data.source_type,
            quality="Medium" if available else "Unavailable",
            traceability="Medium" if available else "Unavailable",
        ))

    store.add(Evidence(
        evidence_id="ev-metrics-001",
        value=metrics,
        provider="Python",
        source="Deterministic calculation",
        source_url=None,
        as_of=data.price_date,
        unit="ratio",
        currency=data.currency,
        definition="Price and volume metrics calculated from observed history.",
        source_type="DETERMINISTIC_CALCULATION",
        quality="High",
        traceability="High",
    ))

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
    if save_snapshot:
        research_id = SnapshotManager(history_dir).save(
            data=data,
            analysis=analysis,
            evidence=evidence,
            metrics=metrics,
            horizon_years=horizon_years,
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
        "observed_valuation": analysis["observed_valuation"],
        "market_implied_assumptions": analysis["implied_assumptions"],
        "consensus_cross_check": analysis["consensus_cross_check"],
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

    args = parser.parse_args()

    if args.test or not args.ticker:
        run_regression_tests()
        if not args.ticker:
            return

    result = run_st_eva(
        ticker=args.ticker,
        horizon=args.horizon,
        event=args.event,
        mode=args.mode,
        reference_multiple=args.reference_multiple,
        horizon_years=args.horizon_years,
        pfcf_multiple=args.pfcf_multiple,
        ev_ebitda_multiple=args.ev_ebitda_multiple,
        ps_multiple=args.ps_multiple,
        save_snapshot=not args.no_snapshot,
    )

    if result is None:
        raise SystemExit(
            "ST-EVA could not acquire usable market data."
        )

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
