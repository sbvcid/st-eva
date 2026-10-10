"""
US Treasury yield observations for the risk-free rate family.

Why this exists separately from ``fundamental_provider``: a risk-free rate is
not a company fundamental. It has no fiscal period, no reporting currency
attached to a filer, and no cross-source validation partner. It is a published
market observation for a sovereign, and conflating it with a company metric
would let a consumer treat a benchmark yield as something the issuer reported.

What this module guarantees:

* Every rate carries its own observation date, tenor, source and unit. A rate
  substituted from a different date silently rewrites a historical valuation,
  so the date travels with the number.
* A tenor that the source did not return is reported as missing. It is never
  filled with a shorter tenor's number, because a 13-week yield and a 10-year
  yield answer different questions about what "the risk-free rate" means.
* Values arrive in percent per annum and stay that way in the observation.
  Consumers convert; this module does not decide for them which tenor to use.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from reverse_requirements import RiskFreeRate


CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

# The symbols are the CBOE-published Treasury yield index series, quoted in
# percent per annum. The tenor each one represents is declared here rather than
# inferred from the symbol name, so a consumer never has to parse a ticker.
TREASURY_SERIES: Tuple[Tuple[str, str, str], ...] = (
    ("^IRX", "13_WEEK", "US Treasury bill yield (13 week discount basis)"),
    ("^FVX", "5_YEAR", "US Treasury note yield (5 year)"),
    ("^TNX", "10_YEAR", "US Treasury note yield (10 year)"),
    ("^TYX", "30_YEAR", "US Treasury bond yield (30 year)"),
)

USER_AGENT = "Mozilla/5.0 ST-EVA/2.3 (research)"

UNIT = "percent_per_annum"
PROVIDER = "CBOETreasuryYieldIndex"


@dataclass(frozen=True)
class RateFetchResult:
    """What one fetch attempt produced, including what it could not produce."""

    rates: Tuple[RiskFreeRate, ...]
    unavailable: Tuple[Dict[str, Any], ...]
    as_of: Optional[str]
    errors: Tuple[str, ...]


def _fetch_symbol(symbol: str, timeout: int) -> Optional[Dict[str, Any]]:
    request = urllib.request.Request(
        CHART_URL.format(symbol=symbol) + "?range=1mo&interval=1d",
        headers={"User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _latest_observation(payload: Dict[str, Any]) -> Optional[Tuple[str, float]]:
    """
    The most recent dated close in the payload.

    The date comes from the series' own timestamps rather than from "today",
    so a rate carries the date the market actually printed it and not the date
    the request happened to run.
    """
    results = ((payload or {}).get("chart") or {}).get("result") or []
    if not results:
        return None
    result = results[0]
    timestamps = result.get("timestamp") or []
    closes = (((result.get("indicators") or {}).get("quote") or [{}])[0]).get("close") or []
    import datetime as _dt

    latest: Optional[Tuple[str, float]] = None
    for stamp, close in zip(timestamps, closes):
        if close is None:
            continue
        day = _dt.datetime.fromtimestamp(stamp, _dt.timezone.utc).strftime("%Y-%m-%d")
        if latest is None or day > latest[0]:
            latest = (day, float(close))
    return latest


def fetch_risk_free_rates(
    series: Sequence[Tuple[str, str, str]] = TREASURY_SERIES,
    timeout: int = 10,
) -> RateFetchResult:
    """
    Fetch every requested tenor.

    A tenor that cannot be fetched is recorded as unavailable with the reason.
    It is never substituted from another tenor and never defaulted to zero.
    """
    rates: List[RiskFreeRate] = []
    unavailable: List[Dict[str, Any]] = []
    errors: List[str] = []
    as_of: Optional[str] = None

    for symbol, tenor_label, instrument in series:
        try:
            payload = _fetch_symbol(symbol, timeout)
        except (urllib.error.URLError, OSError, ValueError) as error:
            reason = f"{tenor_label} yield could not be retrieved: {error}"
            errors.append(reason)
            unavailable.append(
                {
                    "item": f"risk_free_rate.{tenor_label}",
                    "reason": reason,
                    "reason_kind": "RETRIEVAL_FAILED",
                    "blocks": ["cost_of_equity"],
                }
            )
            continue

        latest = _latest_observation(payload)
        if latest is None:
            reason = f"{tenor_label} yield returned no dated observation"
            errors.append(reason)
            unavailable.append(
                {
                    "item": f"risk_free_rate.{tenor_label}",
                    "reason": reason,
                    "reason_kind": "NO_OBSERVATION",
                    "blocks": ["cost_of_equity"],
                }
            )
            continue

        observed_date, value = latest
        if as_of is None or observed_date > as_of:
            as_of = observed_date

        meta = (((payload.get("chart") or {}).get("result") or [{}])[0]).get("meta") or {}
        rates.append(
            RiskFreeRate(
                rate=value,
                tenor_label=tenor_label,
                as_of=observed_date,
                provider=PROVIDER,
                source_url=CHART_URL.format(symbol=symbol),
                unit=UNIT,
                currency=str(meta.get("currency") or "USD"),
                instrument=instrument,
            )
        )

    return RateFetchResult(
        rates=tuple(rates),
        unavailable=tuple(unavailable),
        as_of=as_of,
        errors=tuple(errors),
    )


def select_rate(rates: Sequence[RiskFreeRate], tenor_label: str) -> Optional[RiskFreeRate]:
    """The rate for one named tenor, or None when it was not observed."""
    for rate in rates:
        if rate.tenor_label == tenor_label:
            return rate
    return None


def rate_as_decimal(rate: Optional[RiskFreeRate]) -> Optional[float]:
    """A percent-per-annum rate as a decimal, or None when there is no rate."""
    if rate is None:
        return None
    if rate.unit == UNIT:
        return rate.rate / 100.0
    return rate.rate
