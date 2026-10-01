from __future__ import annotations

"""
ST-EVA 2.3-A - Yahoo fundamental data provider.

This module acquires and normalizes source data. It never estimates or fills a
missing financial value, and it never computes a valuation ratio.

Its output type is the provider-agnostic Observation defined in
data_contract. A Yahoo field name such as trailingEps survives only as the
`methodology` of an observation; it is never a metric the engine reads.

The 2.2.3 FundamentalData shape is still produced by `fetch()` so existing
callers and tests keep working, but it is now a projection of the acquisition
result rather than the provider's output type.
"""

import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from http.cookiejar import CookieJar
from typing import Any, Dict, List, Optional, Tuple

from data_contract import (
    AvailabilityBasis,
    CurrencyBasis,
    METRIC_CASH,
    METRIC_CONSENSUS_FORWARD_EPS,
    METRIC_DEFINITIONS,
    METRIC_EBITDA,
    METRIC_ENTERPRISE_VALUE,
    METRIC_EPS_DILUTED,
    METRIC_EV_EBITDA_BAND,
    METRIC_FORWARD_EPS,
    METRIC_FREE_CASH_FLOW,
    METRIC_MARKET_CAP,
    METRIC_NET_INCOME,
    METRIC_PE_BAND,
    METRIC_PFCF_BAND,
    METRIC_PS_BAND,
    METRIC_REVENUE,
    METRIC_SHARES_OUTSTANDING,
    METRIC_TRAILING_EPS,
    Observation,
    ObservationSet,
    SOURCE_YAHOO,
    SourceType,
    UNAVAILABLE,
    UNIT_CURRENCY,
    UNIT_MULTIPLE,
    UNIT_PER_SHARE,
    Unit,
    ValidationStatus,
    build_observation,
    comparable_observation_id,
    currencies_match,
    distribution_from_samples,
    is_number,
    observation_id_for,
    safe_float,
    unavailable_observation,
    utc_now,
)


QUOTE_SUMMARY_URL = (
    "https://query2.finance.yahoo.com/v10/finance/quoteSummary/"
)
TIMESERIES_URL = (
    "https://query1.finance.yahoo.com/ws/fundamentals-timeseries/"
    "v1/finance/timeseries/"
)

EPS_DEFINITION = "Current/trailing EPS. Never synthesized."
FORWARD_EPS_DEFINITION = "Forward EPS. Used only when explicitly supplied."
CONSENSUS_EPS_DEFINITION = "Consensus forward EPS. Never synthesized."
FCF_DEFINITION = "Observed trailing free cash flow. Never synthesized."
EBITDA_DEFINITION = "Observed trailing EBITDA. Never synthesized."
REVENUE_DEFINITION = "Observed trailing revenue. Never synthesized."
EV_DEFINITION = "Observed enterprise value. Never synthesized."
MARKET_CAP_DEFINITION = "Observed market capitalization. Never synthesized."

BAND_DEFINITIONS = {
    METRIC_PE_BAND: "Historical P/E reference band.",
    METRIC_PFCF_BAND: "Historical P/FCF reference band.",
    METRIC_PS_BAND: "Historical P/S reference band.",
    METRIC_EV_EBITDA_BAND: "Historical EV/EBITDA reference band.",
}


def raw_value(value: Any) -> Optional[float]:
    if isinstance(value, dict):
        value = value.get("raw")
    return float(value) if is_number(value) else None


def distribution_from_series(series: List[Tuple[str, float]]) -> Dict[str, Any]:
    """
    Band statistics for a dated sample.

    A dated sample keeps its dates so the period the band covers stays
    visible. An empty sample yields an empty band, never a band of zeros.
    """
    return distribution_from_samples([value for _, value in series])


@dataclass(frozen=True)
class FundamentalData:
    """
    Deprecated 2.2.3 projection of a fundamental acquisition.

    Retained for backward compatibility only. New code reads
    `FundamentalAcquisition.observations`.
    """

    current_eps: Any = UNAVAILABLE
    current_eps_as_of: Optional[str] = None
    forward_eps: Any = UNAVAILABLE
    forward_eps_as_of: Optional[str] = None
    consensus_forward_eps: Any = UNAVAILABLE
    consensus_forward_eps_period: Optional[str] = None
    historical_pe_band: Optional[Dict[str, Any]] = None
    current_fcf: Any = UNAVAILABLE
    current_fcf_currency: Optional[str] = None
    current_fcf_as_of: Optional[str] = None
    current_ebitda: Any = UNAVAILABLE
    current_ebitda_currency: Optional[str] = None
    current_ebitda_as_of: Optional[str] = None
    current_revenue: Any = UNAVAILABLE
    current_revenue_currency: Optional[str] = None
    current_revenue_as_of: Optional[str] = None
    current_enterprise_value: Any = UNAVAILABLE
    current_enterprise_value_currency: Optional[str] = None
    current_enterprise_value_as_of: Optional[str] = None
    current_market_cap: Any = UNAVAILABLE
    current_market_cap_currency: Optional[str] = None
    current_market_cap_as_of: Optional[str] = None
    historical_ps_band: Optional[Dict[str, Any]] = None
    historical_pfcf_band: Optional[Dict[str, Any]] = None
    historical_ev_ebitda_band: Optional[Dict[str, Any]] = None
    provider: str = "YahooFinanceFundamentals"
    source_type: str = "API_LIVE"
    as_of: Optional[str] = None
    source_urls: Optional[List[str]] = None
    errors: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.historical_pe_band is None:
            object.__setattr__(self, "historical_pe_band", {})
        if self.source_urls is None:
            object.__setattr__(self, "source_urls", [])
        if self.historical_ps_band is None:
            object.__setattr__(self, "historical_ps_band", {})
        if self.historical_pfcf_band is None:
            object.__setattr__(self, "historical_pfcf_band", {})
        if self.historical_ev_ebitda_band is None:
            object.__setattr__(self, "historical_ev_ebitda_band", {})


@dataclass(frozen=True)
class FundamentalAcquisition:
    """
    What the Yahoo fundamentals adapter produced for one ticker.

    `observations` is the contract-native output. The remaining fields exist
    only to project the deprecated 2.2.3 shape without a second acquisition
    path.
    """

    ticker: str
    provider: str
    source_type: str
    retrieved_at: str
    observations: Tuple[Observation, ...] = ()
    errors: Tuple[str, ...] = ()
    source_urls: Tuple[str, ...] = ()
    as_of: Optional[str] = None
    legacy_fields: Tuple[Tuple[str, Any], ...] = ()

    def observation_set(self) -> ObservationSet:
        return ObservationSet(
            ticker=self.ticker,
            observations=self.observations,
        )

    def errors_for_legacy(self) -> List[str]:
        return list(self.errors)

    def to_fundamental_data(self) -> FundamentalData:
        values: Dict[str, Any] = dict(self.legacy_fields)
        values.setdefault("provider", self.provider)
        values.setdefault("source_type", self.source_type)
        values.setdefault("as_of", self.as_of)
        values.setdefault("source_urls", list(self.source_urls))
        values.setdefault("errors", list(self.errors))
        return FundamentalData(**values)


class YahooFundamentalProvider:
    """
    Acquires Yahoo fundamentals as provider-agnostic observations.

    Never synthesizes: a metric the source does not return becomes an
    UNAVAILABLE observation, not a default.
    """

    name = "YahooFinanceFundamentals"
    source_type = SourceType.API_LIVE.value

    def __init__(self, timeout: int = 8) -> None:
        self.timeout = timeout
        self.cookie_jar = CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookie_jar)
        )
        self.opener.addheaders = [("User-Agent", "Mozilla/5.0 ST-EVA/2.1")]

    def _get(self, url: str) -> Optional[Dict[str, Any]]:
        with self.opener.open(url, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _bootstrap_crumb(self) -> Optional[str]:
        try:
            self.opener.open("https://fc.yahoo.com", timeout=self.timeout).read()
        except Exception:
            pass

        try:
            with self.opener.open(
                "https://query1.finance.yahoo.com/v1/test/getcrumb",
                timeout=self.timeout,
            ) as response:
                crumb = response.read().decode("utf-8").strip()
                return crumb or None
        except Exception:
            return None

    def _quote_summary(
        self,
        ticker: str,
        crumb: str,
    ) -> Optional[Dict[str, Any]]:
        modules = "defaultKeyStatistics,earningsTrend,financialData"
        query = urllib.parse.urlencode(
            {
                "modules": modules,
                "crumb": crumb,
                "formatted": "false",
                "lang": "en-US",
                "region": "US",
            }
        )
        url = (
            "https://query2.finance.yahoo.com/v10/finance/quoteSummary/"
            f"{urllib.parse.quote(ticker)}?{query}"
        )
        return self._get(url)

    def _timeseries(self, ticker: str, types: List[str], years: int = 5) -> Dict[str, Any]:
        end = int(time.time())
        start = end - years * 365 * 24 * 60 * 60
        params = urllib.parse.urlencode({
            "symbol": ticker,
            "type": ",".join(types),
            "period1": start,
            "period2": end,
        })
        url = (
            "https://query1.finance.yahoo.com/ws/fundamentals-timeseries/"
            f"v1/finance/timeseries/{urllib.parse.quote(ticker)}?{params}"
        )
        return self._get(url) or {}

    # -- sample extraction -------------------------------------------------

    @staticmethod
    def _series_from_result(
        results: List[Dict[str, Any]],
        field_name: str,
        minimum: float = 0.0,
        maximum: float = 500.0,
    ) -> List[Tuple[str, float]]:
        """
        Dated samples for one timeseries field.

        The date is retained so the band can declare the period it covers.
        Rows without a usable value are dropped rather than zero-filled.
        """
        series: List[Tuple[str, float]] = []
        for result in results:
            for row in result.get(field_name, []) or []:
                value = raw_value(row.get("reportedValue"))
                if value is not None and minimum < value < maximum:
                    series.append((str(row.get("asOfDate") or ""), value))
        return series

    @staticmethod
    def _band_from_result(
        results: List[Dict[str, Any]],
        field_name: str,
        minimum: float = 0.0,
        maximum: float = 500.0,
    ) -> Dict[str, Any]:
        return distribution_from_series(
            YahooFundamentalProvider._series_from_result(
                results, field_name, minimum, maximum
            )
        )

    @staticmethod
    def _paired_ratio_series(
        results: List[Dict[str, Any]],
        numerator_field: str,
        denominator_field: str,
        maximum: float = 500.0,
    ) -> List[Tuple[str, float]]:
        """
        Dated samples for a ratio the source does not publish directly.

        Numerator and denominator must share an exact date and an explicitly
        equal currency. A mismatch drops the sample; it never produces a
        ratio computed across two currencies.
        """
        numerator: Dict[str, tuple[float, Optional[str]]] = {}
        denominator: Dict[str, tuple[float, Optional[str]]] = {}
        for result in results:
            for row in result.get(numerator_field, []) or []:
                value = raw_value(row.get("reportedValue"))
                date = row.get("asOfDate")
                curr = row.get("currencyCode")
                if value is not None and date:
                    numerator[str(date)] = (value, curr)
            for row in result.get(denominator_field, []) or []:
                value = raw_value(row.get("reportedValue"))
                date = row.get("asOfDate")
                curr = row.get("currencyCode")
                if value is not None and date:
                    denominator[str(date)] = (value, curr)

        series: List[Tuple[str, float]] = []
        for date, (num, num_curr) in numerator.items():
            den_tuple = denominator.get(date)
            if den_tuple is None:
                continue
            den, den_curr = den_tuple
            if den is None or den <= 0:
                continue
            if not currencies_match(num_curr, den_curr):
                continue
            ratio = num / den
            if 0 < ratio < maximum:
                series.append((date, ratio))
        return series

    @staticmethod
    def _derived_ratio_band(
        results: List[Dict[str, Any]],
        numerator_field: str,
        denominator_field: str,
        maximum: float = 500.0,
    ) -> Dict[str, Any]:
        return distribution_from_series(
            YahooFundamentalProvider._paired_ratio_series(
                results, numerator_field, denominator_field, maximum
            )
        )

    @staticmethod
    def _latest_value(results: List[Dict[str, Any]], field_name: str) -> Optional[Tuple[float, Optional[str], Optional[str]]]:
        values: List[tuple[str, float, Optional[str]]] = []
        for result in results:
            for row in result.get(field_name, []) or []:
                value = raw_value(row.get("reportedValue"))
                date = row.get("asOfDate") or ""
                curr = row.get("currencyCode")
                if value is not None:
                    values.append((str(date), value, curr))
        if not values:
            return None
        values.sort(key=lambda item: item[0])
        return values[-1][1], values[-1][2], values[-1][0]

    @staticmethod
    def _extract_consensus_forward_eps(
        earnings_trend: Dict[str, Any],
    ) -> Optional[Tuple[float, str]]:
        rows = earnings_trend.get("trend") or []
        candidates: List[tuple[int, float, str]] = []

        # Prefer the next fiscal-year estimate (+1y), then current year (0y),
        # and never substitute a historical actual.
        for row in rows:
            period = row.get("period")
            estimate = row.get("earningsEstimate") or {}
            avg = raw_value(estimate.get("avg"))
            if avg is None:
                continue
            priority = {"+1y": 0, "0y": 1, "+1q": 2, "0q": 3}.get(
                period, 99
            )
            candidates.append((priority, avg, period))

        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0])
        return candidates[0][1], candidates[0][2]

    # -- acquisition -------------------------------------------------------

    def fetch_acquisition(
        self,
        ticker: str,
        instrument_currency: Optional[str] = None,
    ) -> FundamentalAcquisition:
        """
        Acquire Yahoo fundamentals as observations.

        `instrument_currency` is applied to per-share figures with the
        INSTRUMENT_DEFAULT basis, because Yahoo does not state a currency for
        EPS. Applying it is declared, not silent.
        """
        clean = ticker.upper().strip()
        retrieved_at = utc_now()
        source_urls: List[str] = []
        errors: List[str] = []
        observations: List[Observation] = []
        summary_item: Dict[str, Any] = {}
        valuation_results: List[Dict[str, Any]] = []

        current_eps = None
        forward_eps = None
        consensus_eps = None
        consensus_period: Optional[str] = None
        eps_as_of: Optional[str] = None
        current_fcf = None
        current_ebitda = None
        current_revenue = None
        current_enterprise_value = None
        current_market_cap = None
        as_of: Optional[str] = None

        try:
            crumb = self._bootstrap_crumb()
            summary = self._quote_summary(clean, crumb) if crumb else None
        except Exception as e:
            errors.append(f"Bootstrapping/Summary error: {e}")
            crumb = None
            summary = None

        quote_summary_url: Optional[str] = None
        consensus_raw: Any = None
        eps_as_of_by_key: Dict[str, Optional[str]] = {
            "trailing_eps": None,
            "forward_eps": None,
        }

        try:
            result = (
                (summary or {}).get("quoteSummary", {}).get("result") or []
            )
            item = result[0] if result else {}
            summary_item = item if isinstance(item, dict) else {}
            stats = item.get("defaultKeyStatistics") or {}
            trend = item.get("earningsTrend") or {}

            current_eps = raw_value(stats.get("trailingEps"))
            forward_eps = raw_value(stats.get("forwardEps"))
            consensus_info = self._extract_consensus_forward_eps(trend)
            consensus_eps = consensus_info[0] if consensus_info else None
            consensus_period = consensus_info[1] if consensus_info else None
            consensus_raw = trend

            # Find EPS as-of date
            eps_as_of = None
            for key in ("trailingEps", "forwardEps"):
                node = stats.get(key)
                if isinstance(node, dict) and node.get("asOfDate"):
                    eps_as_of = str(node["asOfDate"])
                    break

            # The observations keep each figure's own as-of date. The legacy
            # projection keeps the first available date, unchanged from 2.2.3.
            for key, holder in (
                ("trailingEps", "trailing_eps"),
                ("forwardEps", "forward_eps"),
            ):
                node = stats.get(key)
                if isinstance(node, dict) and node.get("asOfDate"):
                    eps_as_of_by_key[holder] = str(node["asOfDate"])

            if summary is not None:
                quote_summary_url = QUOTE_SUMMARY_URL + clean
                source_urls.append(quote_summary_url)
        except Exception as e:
            errors.append(f"Quote summary error: {e}")

        observations.append(
            build_observation(
                metric=METRIC_TRAILING_EPS,
                value=current_eps,
                unit=UNIT_PER_SHARE,
                provider=self.name,
                source_type=self.source_type,
                definition=EPS_DEFINITION,
                methodology=(
                    "Yahoo quoteSummary defaultKeyStatistics.trailingEps"
                ),
                retrieved_at=retrieved_at,
                currency=instrument_currency,
                currency_basis=self._per_share_currency_basis(
                    instrument_currency
                ),
                period_end=eps_as_of_by_key["trailing_eps"],
                as_of=eps_as_of_by_key["trailing_eps"],
                available_at_basis=AvailabilityBasis.UNDECLARED.value,
                source_url=quote_summary_url,
                raw=None if summary is None else {
                    "module": "defaultKeyStatistics",
                    "field": "trailingEps",
                    "asOfDate": eps_as_of_by_key["trailing_eps"],
                },
            )
        )
        observations.append(
            build_observation(
                metric=METRIC_FORWARD_EPS,
                value=forward_eps,
                unit=UNIT_PER_SHARE,
                provider=self.name,
                source_type=self.source_type,
                definition=FORWARD_EPS_DEFINITION,
                methodology=(
                    "Yahoo quoteSummary defaultKeyStatistics.forwardEps"
                ),
                retrieved_at=retrieved_at,
                currency=instrument_currency,
                currency_basis=self._per_share_currency_basis(
                    instrument_currency
                ),
                period_end=eps_as_of_by_key["forward_eps"],
                as_of=eps_as_of_by_key["forward_eps"],
                available_at_basis=AvailabilityBasis.UNDECLARED.value,
                source_url=quote_summary_url,
                raw=None if summary is None else {
                    "module": "defaultKeyStatistics",
                    "field": "forwardEps",
                    "asOfDate": eps_as_of_by_key["forward_eps"],
                },
            )
        )
        observations.append(
            self._consensus_observation(
                clean=clean,
                value=consensus_eps,
                period=consensus_period,
                trend=consensus_raw,
                retrieved_at=retrieved_at,
                source_url=quote_summary_url,
                instrument_currency=instrument_currency,
            )
        )

        valuation_types = [
            "trailingFreeCashFlow",
            "trailingEBITDA",
            "trailingTotalRevenue",
            "trailingEnterpriseValue",
            "trailingMarketCap",
            "trailingPsRatio",
            "trailingEnterprisesValueEBITDARatio",
            # 2.3-B cross-source metrics. Added to the same request rather than
            # to a second one, so no extra round trip and no change to what the
            # existing seven types return.
            "trailingNetIncomeCommonStockholders",
            "trailingDilutedEPS",
        ]

        valuation_url: Optional[str] = None
        band_url: Optional[str] = None
        try:
            payload = self._timeseries(clean, valuation_types)
            if not payload:
                raise Exception("Failed to fetch fundamentals timeseries")
            valuation_url = TIMESERIES_URL + clean
            source_urls.append(valuation_url)
            results = (payload.get("timeseries") or {}).get("result") or []
            valuation_results = results

            fcf_tuple = self._latest_value(results, "trailingFreeCashFlow")
            ebitda_tuple = self._latest_value(results, "trailingEBITDA")
            rev_tuple = self._latest_value(results, "trailingTotalRevenue")
            ev_tuple = self._latest_value(results, "trailingEnterpriseValue")
            mc_tuple = self._latest_value(results, "trailingMarketCap")

            current_fcf, fcf_curr, current_fcf_as_of = fcf_tuple if fcf_tuple else (None, None, None)
            current_ebitda, ebitda_curr, current_ebitda_as_of = ebitda_tuple if ebitda_tuple else (None, None, None)
            current_revenue, rev_curr, current_revenue_as_of = rev_tuple if rev_tuple else (None, None, None)
            current_enterprise_value, ev_curr, current_enterprise_value_as_of = ev_tuple if ev_tuple else (None, None, None)
            current_market_cap, mc_curr, current_market_cap_as_of = mc_tuple if mc_tuple else (None, None, None)

            # Currency consistency protection. A ratio across two currencies is
            # refused, not computed, and the refusal is recorded on the
            # observation rather than left as a silent absence.
            refused: Dict[str, str] = {}
            if current_market_cap is not None:
                if current_fcf is not None and not currencies_match(mc_curr, fcf_curr):
                    refused[METRIC_FREE_CASH_FLOW] = (
                        "Free cash flow currency does not match market cap "
                        "currency."
                    )
                    current_fcf = None
                if current_revenue is not None and not currencies_match(mc_curr, rev_curr):
                    refused[METRIC_REVENUE] = (
                        "Revenue currency does not match market cap currency."
                    )
                    current_revenue = None
            if current_enterprise_value is not None and current_ebitda is not None and not currencies_match(ev_curr, ebitda_curr):
                refused[METRIC_EBITDA] = (
                    "EBITDA currency does not match enterprise value currency."
                )
                current_ebitda = None

        except Exception as e:
            errors.append(str(e))
            current_fcf = current_ebitda = current_revenue = current_enterprise_value = current_market_cap = None
            fcf_curr = ebitda_curr = rev_curr = ev_curr = mc_curr = None
            current_fcf_as_of = current_ebitda_as_of = current_revenue_as_of = current_enterprise_value_as_of = current_market_cap_as_of = None
            refused = {}

        for metric, value, currency, value_as_of, field_name, definition in (
            (
                METRIC_FREE_CASH_FLOW,
                current_fcf,
                fcf_curr,
                current_fcf_as_of,
                "trailingFreeCashFlow",
                FCF_DEFINITION,
            ),
            (
                METRIC_EBITDA,
                current_ebitda,
                ebitda_curr,
                current_ebitda_as_of,
                "trailingEBITDA",
                EBITDA_DEFINITION,
            ),
            (
                METRIC_REVENUE,
                current_revenue,
                rev_curr,
                current_revenue_as_of,
                "trailingTotalRevenue",
                REVENUE_DEFINITION,
            ),
            (
                METRIC_ENTERPRISE_VALUE,
                current_enterprise_value,
                ev_curr,
                current_enterprise_value_as_of,
                "trailingEnterpriseValue",
                EV_DEFINITION,
            ),
            (
                METRIC_MARKET_CAP,
                current_market_cap,
                mc_curr,
                current_market_cap_as_of,
                "trailingMarketCap",
                MARKET_CAP_DEFINITION,
            ),
        ):
            observations.append(
                self._timeseries_observation(
                    metric=metric,
                    value=value,
                    currency=currency,
                    as_of=value_as_of,
                    field_name=field_name,
                    definition=definition,
                    retrieved_at=retrieved_at,
                    source_url=valuation_url,
                    refusal=refused.get(metric),
                )
            )

        band_series: Dict[str, List[Tuple[str, float]]] = {}
        try:
            payload = self._timeseries(
                clean,
                ["trailingPeRatio", "trailingPsRatio", "trailingEnterprisesValueEBITDARatio", "trailingMarketCap", "trailingFreeCashFlow"],
            )
            band_url = TIMESERIES_URL + clean
            source_urls.append(band_url)
            results = (payload.get("timeseries") or {}).get("result") or []
            band_series[METRIC_PE_BAND] = self._series_from_result(
                results, "trailingPeRatio"
            )
            band_series[METRIC_PS_BAND] = self._series_from_result(
                results, "trailingPsRatio"
            )
            band_series[METRIC_PFCF_BAND] = self._paired_ratio_series(
                results, "trailingMarketCap", "trailingFreeCashFlow"
            )
            band_series[METRIC_EV_EBITDA_BAND] = self._series_from_result(
                results, "trailingEnterprisesValueEBITDARatio"
            )
        except Exception as e:
            errors.append(f"Band calculation error: {e}")

        for metric, series in (
            (METRIC_PE_BAND, band_series.get(METRIC_PE_BAND)),
            (METRIC_PFCF_BAND, band_series.get(METRIC_PFCF_BAND)),
            (METRIC_PS_BAND, band_series.get(METRIC_PS_BAND)),
            (METRIC_EV_EBITDA_BAND, band_series.get(METRIC_EV_EBITDA_BAND)),
        ):
            observations.append(
                self._band_observation(
                    metric=metric,
                    series=series or [],
                    retrieved_at=retrieved_at,
                    source_url=band_url,
                )
            )

        legacy_fields = (
            (
                "current_eps",
                current_eps if current_eps is not None else UNAVAILABLE,
            ),
            ("current_eps_as_of", eps_as_of),
            (
                "forward_eps",
                forward_eps if forward_eps is not None else UNAVAILABLE,
            ),
            ("forward_eps_as_of", eps_as_of),
            (
                "consensus_forward_eps",
                consensus_eps if consensus_eps is not None else UNAVAILABLE,
            ),
            ("consensus_forward_eps_period", consensus_period),
            (
                "historical_pe_band",
                distribution_from_series(band_series.get(METRIC_PE_BAND) or []),
            ),
            (
                "current_fcf",
                current_fcf if current_fcf is not None else UNAVAILABLE,
            ),
            ("current_fcf_currency", fcf_curr),
            ("current_fcf_as_of", current_fcf_as_of),
            (
                "current_ebitda",
                current_ebitda if current_ebitda is not None else UNAVAILABLE,
            ),
            ("current_ebitda_currency", ebitda_curr),
            ("current_ebitda_as_of", current_ebitda_as_of),
            (
                "current_revenue",
                current_revenue if current_revenue is not None else UNAVAILABLE,
            ),
            ("current_revenue_currency", rev_curr),
            ("current_revenue_as_of", current_revenue_as_of),
            (
                "current_enterprise_value",
                current_enterprise_value
                if current_enterprise_value is not None
                else UNAVAILABLE,
            ),
            ("current_enterprise_value_currency", ev_curr),
            ("current_enterprise_value_as_of", current_enterprise_value_as_of),
            (
                "current_market_cap",
                current_market_cap if current_market_cap is not None else UNAVAILABLE,
            ),
            ("current_market_cap_currency", mc_curr),
            ("current_market_cap_as_of", current_market_cap_as_of),
            (
                "historical_ps_band",
                distribution_from_series(band_series.get(METRIC_PS_BAND) or []),
            ),
            (
                "historical_pfcf_band",
                distribution_from_series(band_series.get(METRIC_PFCF_BAND) or []),
            ),
            (
                "historical_ev_ebitda_band",
                distribution_from_series(
                    band_series.get(METRIC_EV_EBITDA_BAND) or []
                ),
            ),
        )

        return FundamentalAcquisition(
            ticker=clean,
            provider=self.name,
            source_type=self.source_type,
            retrieved_at=retrieved_at,
            observations=tuple(observations)
            + tuple(
                self.comparable_observations(
                    summary_item,
                    valuation_results,
                    instrument_currency,
                    retrieved_at,
                    quote_summary_url,
                    valuation_url,
                )
            ),
            errors=tuple(errors),
            source_urls=tuple(source_urls),
            as_of=as_of,
            legacy_fields=legacy_fields,
        )

    def fetch(
        self,
        ticker: str,
        instrument_currency: Optional[str] = None,
    ) -> FundamentalData:
        """
        Deprecated 2.2.3 entry point.

        Retained so existing callers and tests keep working against the
        familiar shape. New code calls `fetch_acquisition()`, which returns
        provider-agnostic observations.
        """
        return self.fetch_acquisition(
            ticker,
            instrument_currency=instrument_currency,
        ).to_fundamental_data()

    # -- observation construction -----------------------------------------

    @staticmethod
    def _per_share_currency_basis(
        instrument_currency: Optional[str],
    ) -> str:
        if instrument_currency:
            return CurrencyBasis.INSTRUMENT_DEFAULT.value
        return CurrencyBasis.UNDECLARED.value

    @staticmethod
    def _band_bounds(series: List[Tuple[str, float]]) -> Tuple[Optional[str], Optional[str]]:
        dates = sorted(date for date, _ in series if date)
        if not dates:
            return None, None
        return dates[0], dates[-1]

    def _band_observation(
        self,
        metric: str,
        series: List[Tuple[str, float]],
        retrieved_at: str,
        source_url: Optional[str],
    ) -> Observation:
        """
        A distribution observation that keeps the samples it was built from.

        The samples are the evidence. A median computed from them can be
        recomputed, which a stored median alone could never support.
        """
        band = distribution_from_series(series)
        period_start, period_end = self._band_bounds(series)
        upstream = {
            METRIC_PE_BAND: "trailingPeRatio",
            METRIC_PFCF_BAND: "trailingMarketCap / trailingFreeCashFlow",
            METRIC_PS_BAND: "trailingPsRatio",
            METRIC_EV_EBITDA_BAND: "trailingEnterprisesValueEBITDARatio",
        }[metric]

        if not band:
            return unavailable_observation(
                metric=metric,
                provider=self.name,
                source_type=self.source_type,
                definition=BAND_DEFINITIONS[metric],
                methodology=(
                    f"percentile band over Yahoo fundamentals-timeseries "
                    f"{upstream} samples"
                ),
                retrieved_at=retrieved_at,
                unit=UNIT_MULTIPLE,
                source_url=source_url,
            )

        count = int(band["observations"])
        if count < 20:
            status = ValidationStatus.INSUFFICIENT_OBSERVATIONS
            reasons = (
                f"{metric} carries {count} samples, below the 20 required for "
                "a reference multiple.",
            )
        else:
            status = None
            reasons = ()

        return build_observation(
            metric=metric,
            value=band,
            unit=UNIT_MULTIPLE,
            provider=self.name,
            source_type=self.source_type,
            definition=BAND_DEFINITIONS[metric],
            methodology=(
                f"percentile band over Yahoo fundamentals-timeseries "
                f"{upstream} samples"
            ),
            retrieved_at=retrieved_at,
            currency=None,
            currency_basis=CurrencyBasis.NOT_APPLICABLE.value,
            period_start=period_start,
            period_end=period_end,
            as_of=period_end,
            available_at_basis=AvailabilityBasis.UNDECLARED.value,
            source_url=source_url,
            raw={
                "samples": [value for _, value in series],
                "as_of_dates": [date for date, _ in series],
                "upstream_field": upstream,
            },
            observation_count=count,
            status=status,
            status_reasons=reasons,
        )

    def _timeseries_observation(
        self,
        metric: str,
        value: Optional[float],
        currency: Optional[str],
        as_of: Optional[str],
        field_name: str,
        definition: str,
        retrieved_at: str,
        source_url: Optional[str],
        refusal: Optional[str] = None,
    ) -> Observation:
        """
        A scalar fundamentals observation.

        A currency refusal is reported as UNAVAILABLE with an explicit reason
        instead of yielding a number computed across two currencies.
        """
        currency_basis = (
            CurrencyBasis.REPORTED.value
            if currency
            else CurrencyBasis.UNDECLARED.value
        )

        if value is None and refusal:
            return Observation(
                observation_id=observation_id_for(metric),
                metric=metric,
                value=None,
                unit=UNIT_CURRENCY,
                currency=currency,
            currency_basis=currency_basis,
            period_start=None,
            period_end=as_of,
            as_of=as_of,
            available_at=None,
            available_at_basis=AvailabilityBasis.UNDECLARED.value,
            provider=self.name,
            source_type=self.source_type,
            source_url=source_url,
            definition=definition,
            methodology=(
                f"Yahoo fundamentals-timeseries {field_name}"
            ),
            retrieved_at=retrieved_at,
            raw=None,
            observation_count=None,
            status=ValidationStatus.CURRENCY_MISMATCH,
            status_reasons=(refusal,),
        )

        return build_observation(
            metric=metric,
            value=value,
            unit=UNIT_CURRENCY,
            provider=self.name,
            source_type=self.source_type,
            definition=definition,
            methodology=f"Yahoo fundamentals-timeseries {field_name}",
            retrieved_at=retrieved_at,
            currency=currency,
            currency_basis=currency_basis,
            period_end=as_of,
            as_of=as_of,
            available_at_basis=AvailabilityBasis.UNDECLARED.value,
            source_url=source_url,
            raw=None if value is None else {
                "field": field_name,
                "asOfDate": as_of,
                "currencyCode": currency,
            },
        )

    def comparable_observations(
        self,
        summary_item: Dict[str, Any],
        valuation_results: List[Dict[str, Any]],
        instrument_currency: Optional[str],
        retrieved_at: str,
        quote_summary_url: Optional[str],
        timeseries_url: Optional[str],
    ) -> List[Observation]:
        """
        The vendor side of the 2.3-B cross-source metrics.

        These are additional observations with `cmp-` IDs. Nothing here changes
        the 2.2.3 material evidence, the legacy projection, or the engine's
        input, and no `assets` observation is produced because the vendor
        publishes no counterpart for it.

        Each observation records what the vendor did and did not tell us. A
        trailing figure arrives with an as-of date and no window; an
        undated `financialData` total arrives with neither. Those gaps are
        recorded rather than filled in, because they are the reason a later
        comparison may be refused.
        """
        emitted: List[Observation] = []
        stats = (summary_item or {}).get("defaultKeyStatistics") or {}
        financial = (summary_item or {}).get("financialData") or {}

        # Trailing aggregates, from the fundamentals timeseries.
        for metric, field_name in (
            (METRIC_REVENUE, "trailingTotalRevenue"),
            (METRIC_NET_INCOME, "trailingNetIncomeCommonStockholders"),
            (METRIC_EPS_DILUTED, "trailingDilutedEPS"),
        ):
            latest = self._latest_value(valuation_results, field_name)
            if latest is None:
                continue
            value, currency, as_of = latest
            unit = (
                Unit.PER_SHARE.value
                if metric == METRIC_EPS_DILUTED
                else Unit.CURRENCY.value
            )
            emitted.append(
                build_observation(
                    metric=metric,
                    value=value,
                    unit=unit,
                    provider=self.name,
                    source_type=self.source_type,
                    definition=(
                        METRIC_DEFINITIONS.get(metric, "")
                    ),
                    methodology=(
                        f"Yahoo fundamentals-timeseries {field_name}; a "
                        "trailing aggregate whose window the vendor does not "
                        "publish"
                    ),
                    retrieved_at=retrieved_at,
                    currency=currency or instrument_currency,
                    currency_basis=(
                        CurrencyBasis.REPORTED.value
                        if currency
                        else (
                            CurrencyBasis.INSTRUMENT_DEFAULT.value
                            if instrument_currency
                            else CurrencyBasis.UNDECLARED.value
                        )
                    ),
                    # No window: the vendor states only the as-of date.
                    period_start=None,
                    period_end=None,
                    as_of=as_of,
                    available_at=None,
                    available_at_basis=AvailabilityBasis.UNDECLARED.value,
                    source_url=timeseries_url,
                    raw={
                        "yahoo_field": field_name,
                        "as_of": as_of,
                        "reported_currency": currency,
                        "window_published_by_vendor": False,
                        # The vendor does not publish the window, but the field
                        # is a trailing aggregate and that is a declared fact
                        # about it. Declaring it is what lets the comparison be
                        # made at all; inferring period type from the absent
                        # window would misread a flow as a stock.
                        "period_type": "duration",
                        "vendor_basis": "TRAILING_AGGREGATE",
                    },
                    basis={
                        "measurement_basis": "TRAILING_AGGREGATE",
                        "reporting_currency": currency or "UNDECLARED",
                        "period_window": "UNDECLARED_BY_SOURCE",
                        "source_declared": True,
                    },
                    observation_id=comparable_observation_id(
                        metric,
                        SOURCE_YAHOO,
                        period=as_of,
                    ),
                )
            )

        # Undated balance-sheet totals from the financialData module.
        #
        # This module states no currency for these figures. It is tempting to
        # apply the instrument's quote currency, and it is wrong: a vendor
        # normalises some fields to the quote currency and leaves others in the
        # reporting currency, and nothing in the response says which. Asserting
        # the quote currency turns an unknown into a false fact, and a false
        # currency is worse than a missing one because it combines silently
        # with everything else in that currency.
        #
        # **`totalDebt` is deliberately absent, and its absence is the finding.**
        # It used to project here, and it must not any more. This module's
        # `totalDebt` is the vendor's *total* debt; Core `long_term_debt` (2.33) is
        # long-term debt specifically and **excludes short-term borrowings by its
        # own definition**. Projecting one into the other is not a defensible
        # mismatch with a caveat in `methodology` -- it puts a different quantity
        # in the same metric under the same name, and every Core consumer would
        # read it as long-term debt.
        #
        # This provider acquires three modules -- `defaultKeyStatistics`,
        # `earningsTrend`, `financialData` -- and **no balance-sheet module**, so it
        # holds no field whose semantics it has verified as long-term debt. It was
        # not going to assume one exists on the strength of a field name: 2.29
        # established that a name is not a definition, four times over.
        #
        # So `long_term_debt` is simply **unavailable from this source**, which is
        # what "the source does not report it" looks like from the provider side,
        # and cross-validation reads as a missing vendor figure rather than a
        # disagreement.
        #
        # Retiring it cost no history: every `debt` observation in every archive
        # on disk, the sealed 2.2.3 snapshot included, is provider `SecEdgar`. The
        # projection had never written one.
        for metric, field_name in (
            (METRIC_CASH, "totalCash"),
        ):
            value = safe_float(financial.get(field_name))
            if value is None:
                continue
            emitted.append(
                build_observation(
                    metric=metric,
                    value=value,
                    unit=Unit.CURRENCY.value,
                    provider=self.name,
                    source_type=self.source_type,
                    definition=METRIC_DEFINITIONS[metric],
                    methodology=(
                        f"Yahoo quoteSummary financialData.{field_name}; the "
                        "module states no currency and no balance-sheet date "
                        "for this figure, so neither is asserted"
                    ),
                    retrieved_at=retrieved_at,
                    currency=None,
                    currency_basis=CurrencyBasis.UNDECLARED.value,
                    period_start=None,
                    period_end=None,
                    as_of=None,
                    available_at=None,
                    available_at_basis=AvailabilityBasis.UNDECLARED.value,
                    source_url=quote_summary_url,
                    raw={
                        "yahoo_field": f"financialData.{field_name}",
                        "module_currency": financial.get("currency"),
                        "balance_sheet_date_published": False,
                        "currency_published": False,
                        "period_type": "instant",
                        "vendor_basis": "UNDATED_INSTANT",
                    },
                    basis={
                        "security_type": "UNDECLARED",
                        "reporting_currency": "UNDECLARED",
                        "source_declared": False,
                    },
                    observation_id=comparable_observation_id(
                        metric,
                        SOURCE_YAHOO,
                        period="undated",
                    ),
                )
            )

        # Cover-page share count. Undated here, and materially different from a
        # period-average diluted count, which is a different concept.
        shares = safe_float(stats.get("sharesOutstanding"))
        if shares is not None:
            emitted.append(
                build_observation(
                    metric=METRIC_SHARES_OUTSTANDING,
                    value=shares,
                    unit=Unit.COUNT.value,
                    provider=self.name,
                    source_type=self.source_type,
                    definition=METRIC_DEFINITIONS[METRIC_SHARES_OUTSTANDING],
                    methodology=(
                        "Yahoo quoteSummary defaultKeyStatistics."
                        "sharesOutstanding; undated, and sourced from the same "
                        "regulatory cover page the filing source reads, so "
                        "agreement is not independent corroboration"
                    ),
                    retrieved_at=retrieved_at,
                    currency=None,
                    currency_basis=CurrencyBasis.NOT_APPLICABLE.value,
                    period_start=None,
                    period_end=None,
                    as_of=None,
                    available_at=None,
                    available_at_basis=AvailabilityBasis.UNDECLARED.value,
                    source_url=quote_summary_url,
                    raw={
                        "yahoo_field": "defaultKeyStatistics.sharesOutstanding",
                        "as_of_published": False,
                        "period_type": "instant",
                        "vendor_basis": "UNDATED_INSTANT",
                    },
                    basis={
                        # The vendor does not say whether this is a count of
                        # the listed instrument or of the underlying security.
                        # For an issuer whose listed unit differs from its
                        # registered security that is not a distinction worth
                        # guessing at, so it is declared undeclared.
                        "security_type": "UNDECLARED",
                        "shares_basis": "UNDECLARED",
                        "source_declared": False,
                    },
                    observation_id=comparable_observation_id(
                        METRIC_SHARES_OUTSTANDING,
                        SOURCE_YAHOO,
                        period="undated",
                    ),
                )
            )

        return emitted

    def _consensus_observation(
        self,
        clean: str,
        value: Optional[float],
        period: Optional[str],
        trend: Any,
        retrieved_at: str,
        source_url: Optional[str],
        instrument_currency: Optional[str],
    ) -> Observation:
        """
        The consensus estimate observation.

        The estimate period is Yahoo's own label ("+1y", "0y", ...) and is kept
        verbatim. It is not a fiscal period, so it is not turned into
        period_start/period_end that the source never stated.
        """
        return build_observation(
            metric=METRIC_CONSENSUS_FORWARD_EPS,
            value=value,
            unit=UNIT_PER_SHARE,
            provider=self.name,
            source_type=self.source_type,
            definition=CONSENSUS_EPS_DEFINITION,
            methodology=(
                "Yahoo quoteSummary earningsTrend trend[period]"
                ".earningsEstimate.avg"
            ),
            retrieved_at=retrieved_at,
            currency=instrument_currency,
            currency_basis=self._per_share_currency_basis(
                instrument_currency
            ),
            as_of=None,
            available_at_basis=AvailabilityBasis.UNDECLARED.value,
            source_url=source_url,
            raw=None if value is None else {
                "module": "earningsTrend",
                "field": "trend[].earningsEstimate.avg",
                "period": period,
            },
        )
