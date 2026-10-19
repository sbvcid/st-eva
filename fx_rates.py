"""
FX rate data source for ST-EVA cross-currency analysis.

Provides explicit USD/JPY FX rate observations for MUFG (Mitsubishi UFJ
Financial Group), whose market price and market cap are quoted in USD (ADR)
while its SEC financial statements are reported in JPY.

Every FX observation carries:
  - rate: USD per 1 JPY (quote direction: USD/JPY inverse, i.e. how many USD
    one JPY buys; the reciprocal is JPY per USD)
  - as_of: the date the rate was observed
  - provider: the data provider
  - source_url: the source document
  - original_amounts: the raw amounts before conversion, kept for audit

This module does NOT perform implicit conversion. Callers must explicitly
request an FX-converted figure and name the FX rate used. The rate is a
reference input, not a licence to silently mix currencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class FxRate:
    """One FX observation: USD per JPY, observed at a stated instant."""

    rate_usd_per_jpy: float
    as_of: str
    provider: str
    source_url: str
    quote_direction: str = "USD per JPY"
    original_amounts: Optional[dict] = None


# ---------------------------------------------------------------------------
# Historical reference FX rate: Federal Reserve H.10 observation for 2026-10-09.
#
# This rate is a historical reference observation tied to a specific H.10
# publication date (2026-10-09). It is reference-only and must NOT be used
# as a fiscal-period conversion rate or as a proxy for the analysis-date rate.
# ---------------------------------------------------------------------------
# Source: Federal Reserve H.10 daily bilateral exchange rate, Japanese Yen
# per U.S. dollar = 158.3400, i.e. 1 JPY = 1/158.3400 = 0.006316 USD.
MUFG_FX_RATE_USD_PER_JPY = FxRate(
    rate_usd_per_jpy=0.006316,
    as_of="2026-10-09",
    provider="Federal Reserve Board H.10",
    source_url="https://www.federalreserve.gov/releases/h10/hist/dat00_ja.htm",
    quote_direction="USD per JPY",
    original_amounts={
        "note": "158.3400 JPY per USD (Federal Reserve H.10, 2026-10-09). "
        "1 JPY = 0.006316 USD. Reciprocal: 1 USD = 158.3400 JPY. "
        "Historical reference observation date: 2026-10-09. "
        "Reference only — not a fiscal-period conversion rate and not an "
        "analysis-date proxy.",
    },
)

# ---------------------------------------------------------------------------
# Analysis-date FX rate: ECB reference rates for 2026-10-16.
#
# Derived from ECB reference rates published on 2026-10-16:
#   1 EUR = 1.1253 USD
#   1 EUR = 177.82 JPY
#   => 1 JPY = 1.1253 / 177.82 USD = 0.0063283095... USD
#
# This is the analysis-date spot reference rate used for converting JPY
# financial data to USD for current valuation comparison. It is distinct from
# the fiscal-period H.10 rate above.
# ---------------------------------------------------------------------------
# Source: ECB reference rates, 2026-10-16.
MUFG_FX_RATE_ANALYSIS_DATE_USD_PER_JPY = FxRate(
    rate_usd_per_jpy=1.1253 / 177.82,
    as_of="2026-10-16",
    provider="European Central Bank (ECB)",
    source_url="https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_rates/html/index.en.html",
    quote_direction="USD per JPY",
    original_amounts={
        "note": "Derived from ECB reference rates 2026-10-16: "
        "1 EUR = 1.1253 USD, 1 EUR = 177.82 JPY. "
        "Derived USD/JPY = 1.1253 / 177.82 = 0.0063283095... USD per JPY. "
        "Analysis-date spot reference rate for cross-currency valuation "
        "comparison. Distinct from the fiscal-period H.10 rate "
        "(2026-10-09, 0.006316 USD/JPY). "
        "Rate carried unrounded; do not use rounded display values as inputs.",
    },
)


def mufg_fx_rate() -> Optional[FxRate]:
    """Return the MUFG historical reference FX rate (Fed H.10, 2026-10-09),
    or None if unavailable. Reference only — not a fiscal-period rate."""
    return MUFG_FX_RATE_USD_PER_JPY


def mufg_fx_rate_analysis_date() -> Optional[FxRate]:
    """Return the MUFG analysis-date FX rate reference (ECB, 2026-10-16),
    or None if unavailable."""
    return MUFG_FX_RATE_ANALYSIS_DATE_USD_PER_JPY


def mufg_fx_rate() -> Optional[FxRate]:
    """Return the MUFG USD/JPY FX rate reference, or None if unavailable."""
    return MUFG_FX_RATE_USD_PER_JPY


def convert_jpy_to_usd(jpy_amount: float, fx: FxRate) -> float:
    """Convert a JPY amount to USD using the explicit FX rate.

    The caller must name the FX rate and disclose it alongside the result.
    """
    return jpy_amount * fx.rate_usd_per_jpy


def convert_usd_to_jpy(usd_amount: float, fx: FxRate) -> float:
    """Convert a USD amount to JPY using the explicit FX rate."""
    return usd_amount / fx.rate_usd_per_jpy
