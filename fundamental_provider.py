from __future__ import annotations

"""
ST-EVA 2.2.2 - Yahoo fundamental data provider.

This module only acquires and normalizes source data. It never estimates or
fills missing financial values. Historical P/E percentiles are calculated only
from observed Yahoo time-series observations.
"""

import json
import math
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.cookiejar import CookieJar
from statistics import median
from typing import Any, Dict, List, Optional, Tuple


UNAVAILABLE = "UNAVAILABLE"


def is_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def raw_value(value: Any) -> Optional[float]:
    if isinstance(value, dict):
        value = value.get("raw")
    return float(value) if is_number(value) else None


def percentile(values: List[float], p: float) -> Optional[float]:
    if not values:
        return None
    values = sorted(values)
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * p
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    weight = position - lower
    return values[lower] * (1 - weight) + values[upper] * weight


@dataclass(frozen=True)
class FundamentalData:
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


class YahooFundamentalProvider:
    name = "YahooFinanceFundamentals"

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
        modules = "defaultKeyStatistics,earningsTrend"
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

    @staticmethod
    def _band_from_result(results: List[Dict[str, Any]], field: str, minimum: float = 0.0, maximum: float = 500.0) -> Dict[str, Any]:
        values: List[float] = []
        for result in results:
            for row in result.get(field, []) or []:
                value = raw_value(row.get("reportedValue"))
                if value is not None and minimum < value < maximum:
                    values.append(value)
        if not values:
            return {}
        return {
            "10th": percentile(values, 0.10),
            "25th": percentile(values, 0.25),
            "median": median(values),
            "75th": percentile(values, 0.75),
            "90th": percentile(values, 0.90),
            "observations": len(values),
        }

    @staticmethod
    def _derived_ratio_band(
        results: List[Dict[str, Any]],
        numerator_field: str,
        denominator_field: str,
        maximum: float = 500.0,
    ) -> Dict[str, Any]:
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

        values = []
        for date, (num, num_curr) in numerator.items():
            den_tuple = denominator.get(date)
            if den_tuple is not None:
                den, den_curr = den_tuple
                if den is not None and den > 0:
                    if not num_curr or not den_curr or num_curr.upper() != den_curr.upper():
                        continue
                    ratio = num / den
                    if 0 < ratio < maximum:
                        values.append(ratio)

        if not values:
            return {}
        return {
            "10th": percentile(values, 0.10),
            "25th": percentile(values, 0.25),
            "median": median(values),
            "75th": percentile(values, 0.75),
            "90th": percentile(values, 0.90),
            "observations": len(values),
        }

    @staticmethod
    def _latest_value(results: List[Dict[str, Any]], field: str) -> Optional[Tuple[float, Optional[str], Optional[str]]]:
        values: List[tuple[str, float, Optional[str]]] = []
        for result in results:
            for row in result.get(field, []) or []:
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

    def fetch(self, ticker: str) -> FundamentalData:
        clean = ticker.upper().strip()
        source_urls: List[str] = []

        errors: List[str] = []

        try:
            crumb = self._bootstrap_crumb()
            summary = self._quote_summary(clean, crumb) if crumb else None
        except Exception as e:
            errors.append(f"Bootstrapping/Summary error: {e}")
            crumb = None
            summary = None

        current_eps = None
        forward_eps = None
        consensus_eps = None
        current_fcf = None
        current_ebitda = None
        current_revenue = None
        current_enterprise_value = None
        current_market_cap = None
        as_of: Optional[str] = None

        try:
            result = (
                (summary or {}).get("quoteSummary", {}).get("result") or []
            )
            item = result[0] if result else {}
            stats = item.get("defaultKeyStatistics") or {}
            trend = item.get("earningsTrend") or {}

            current_eps = raw_value(stats.get("trailingEps"))
            forward_eps = raw_value(stats.get("forwardEps"))
            consensus_info = self._extract_consensus_forward_eps(trend)
            consensus_eps = consensus_info[0] if consensus_info else None
            consensus_period = consensus_info[1] if consensus_info else None

            # Find EPS as-of date
            eps_as_of = None
            for key in ("trailingEps", "forwardEps"):
                node = stats.get(key)
                if isinstance(node, dict) and node.get("asOfDate"):
                    eps_as_of = str(node["asOfDate"])
                    break

            if summary is not None:
                source_urls.append(
                    "https://query2.finance.yahoo.com/v10/finance/quoteSummary/"
                    + clean
                )
        except Exception as e:
            errors.append(f"Quote summary error: {e}")

        # ... (similar changes for the timeseries part)


        valuation_types = [
            "trailingFreeCashFlow",
            "trailingEBITDA",
            "trailingTotalRevenue",
            "trailingEnterpriseValue",
            "trailingMarketCap",
            "trailingPsRatio",
            "trailingEnterprisesValueEBITDARatio",
        ]

        try:
            payload = self._timeseries(clean, valuation_types)
            if not payload:
                raise Exception("Failed to fetch fundamentals timeseries")
            source_urls.append(
                "https://query1.finance.yahoo.com/ws/fundamentals-timeseries/"
                "v1/finance/timeseries/" + clean
            )
            results = (payload.get("timeseries") or {}).get("result") or []
            
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

            # Currency consistency protection
            if current_market_cap is not None:
                if current_fcf is not None:
                    if not mc_curr or not fcf_curr or mc_curr.upper() != fcf_curr.upper():
                        current_fcf = None
                if current_revenue is not None:
                    if not mc_curr or not rev_curr or mc_curr.upper() != rev_curr.upper():
                        current_revenue = None

            if current_enterprise_value is not None and current_ebitda is not None:
                if not ev_curr or not ebitda_curr or ev_curr.upper() != ebitda_curr.upper():
                    current_ebitda = None

        except Exception as e:
            errors.append(str(e))
            current_fcf = current_ebitda = current_revenue = current_enterprise_value = current_market_cap = None
            fcf_curr = ebitda_curr = rev_curr = ev_curr = mc_curr = None
            current_fcf_as_of = current_ebitda_as_of = current_revenue_as_of = current_enterprise_value_as_of = current_market_cap_as_of = None


        pe_band: Dict[str, Any] = {}
        ps_band: Dict[str, Any] = {}
        ev_ebitda_band: Dict[str, Any] = {}
        try:
            payload = self._timeseries(
                clean,
                ["trailingPeRatio", "trailingPsRatio", "trailingEnterprisesValueEBITDARatio", "trailingMarketCap", "trailingFreeCashFlow"],
            )
            source_urls.append(
                "https://query1.finance.yahoo.com/ws/fundamentals-timeseries/"
                "v1/finance/timeseries/" + clean
            )
            results = (payload.get("timeseries") or {}).get("result") or []
            pe_band = self._band_from_result(results, "trailingPeRatio")
            ps_band = self._band_from_result(results, "trailingPsRatio")
            pfcf_band = self._derived_ratio_band(
                results, "trailingMarketCap", "trailingFreeCashFlow"
            )
            ev_ebitda_band = self._band_from_result(
                results, "trailingEnterprisesValueEBITDARatio"
            )
        except Exception as e:
            errors.append(f"Band calculation error: {e}")

        return FundamentalData(
            current_eps=current_eps if current_eps is not None else UNAVAILABLE,
            current_eps_as_of=eps_as_of,
            forward_eps=forward_eps if forward_eps is not None else UNAVAILABLE,
            forward_eps_as_of=eps_as_of,
            consensus_forward_eps=(
                consensus_eps if consensus_eps is not None else UNAVAILABLE
            ),
            consensus_forward_eps_period=consensus_period,
            historical_pe_band=pe_band,
            current_fcf=current_fcf if current_fcf is not None else UNAVAILABLE,
            current_fcf_currency=fcf_curr,
            current_fcf_as_of=current_fcf_as_of,
            current_ebitda=current_ebitda if current_ebitda is not None else UNAVAILABLE,
            current_ebitda_currency=ebitda_curr,
            current_ebitda_as_of=current_ebitda_as_of,
            current_revenue=current_revenue if current_revenue is not None else UNAVAILABLE,
            current_revenue_currency=rev_curr,
            current_revenue_as_of=current_revenue_as_of,
            current_enterprise_value=(
                current_enterprise_value
                if current_enterprise_value is not None
                else UNAVAILABLE
            ),
            current_enterprise_value_currency=ev_curr,
            current_enterprise_value_as_of=current_enterprise_value_as_of,
            current_market_cap=(
                current_market_cap if current_market_cap is not None else UNAVAILABLE
            ),
            current_market_cap_currency=mc_curr,
            current_market_cap_as_of=current_market_cap_as_of,
            historical_ps_band=ps_band,
            historical_pfcf_band=pfcf_band,
            historical_ev_ebitda_band=ev_ebitda_band,
            as_of=as_of,
            source_urls=source_urls,
            errors=errors,
        )
