from __future__ import annotations

"""
ST-EVA 2.1 - Yahoo fundamental data provider.

This module only acquires and normalizes source data. It never estimates or
fills missing financial values. Historical P/E percentiles are calculated only
from observed Yahoo time-series observations.
"""

import json
import math
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from http.cookiejar import CookieJar
from statistics import median
from typing import Any, Dict, List, Optional


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
    forward_eps: Any = UNAVAILABLE
    consensus_forward_eps: Any = UNAVAILABLE
    historical_pe_band: Optional[Dict[str, Any]] = None
    provider: str = "YahooFinanceFundamentals"
    source_type: str = "API_LIVE"
    as_of: Optional[str] = None
    source_urls: Optional[List[str]] = None

    def __post_init__(self) -> None:
        if self.historical_pe_band is None:
            object.__setattr__(self, "historical_pe_band", {})
        if self.source_urls is None:
            object.__setattr__(self, "source_urls", [])


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
        try:
            with self.opener.open(url, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception:
            return None

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

    def _timeseries_pe(
        self,
        ticker: str,
    ) -> Dict[str, Any]:
        end = int(time.time())
        start = end - 5 * 365 * 24 * 60 * 60
        params = urllib.parse.urlencode(
            {
                "symbol": ticker,
                "type": "trailingPeRatio",
                "period1": start,
                "period2": end,
            }
        )
        url = (
            "https://query2.finance.yahoo.com/ws/fundamentals-timeseries/"
            f"v1/finance/timeseries/{urllib.parse.quote(ticker)}?{params}"
        )
        return self._get(url) or {}

    @staticmethod
    def _extract_consensus_forward_eps(
        earnings_trend: Dict[str, Any],
    ) -> Optional[float]:
        rows = earnings_trend.get("trend") or []
        candidates: List[tuple[int, float]] = []

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
            candidates.append((priority, avg))

        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0])
        return candidates[0][1]

    def fetch(self, ticker: str) -> FundamentalData:
        clean = ticker.upper().strip()
        source_urls: List[str] = []

        crumb = self._bootstrap_crumb()
        summary = self._quote_summary(clean, crumb) if crumb else None

        current_eps = None
        forward_eps = None
        consensus_eps = None
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
            consensus_eps = self._extract_consensus_forward_eps(trend)

            for key in ("trailingEps", "forwardEps"):
                node = stats.get(key)
                if isinstance(node, dict) and node.get("asOfDate"):
                    as_of = str(node["asOfDate"])
                    break

            if summary is not None:
                source_urls.append(
                    "https://query2.finance.yahoo.com/v10/finance/quoteSummary/"
                    + clean
                )
        except Exception:
            pass

        pe_band: Dict[str, float] = {}
        try:
            payload = self._timeseries_pe(clean)
            source_urls.append(
                "https://query1.finance.yahoo.com/ws/fundamentals-timeseries/"
                "v1/finance/timeseries/" + clean
            )
            results = (payload.get("timeseries") or {}).get("result") or []
            values: List[float] = []
            for result in results:
                for row in result.get("trailingPeRatio", []) or []:
                    value = raw_value(row.get("reportedValue"))
                    if value is not None and value > 0 and value < 500:
                        values.append(value)

            if values:
                pe_band = {
                    "10th": percentile(values, 0.10),
                    "25th": percentile(values, 0.25),
                    "median": median(values),
                    "75th": percentile(values, 0.75),
                    "90th": percentile(values, 0.90),
                    "observations": len(values),
                }
        except Exception:
            pass

        return FundamentalData(
            current_eps=current_eps if current_eps is not None else UNAVAILABLE,
            forward_eps=forward_eps if forward_eps is not None else UNAVAILABLE,
            consensus_forward_eps=(
                consensus_eps if consensus_eps is not None else UNAVAILABLE
            ),
            historical_pe_band=pe_band,
            as_of=as_of,
            source_urls=source_urls,
        )
