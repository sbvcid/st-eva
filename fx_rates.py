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


# MUFG explicit FX rate: USD/JPY as observed on 2026-10-16.
# Source: publicly available FX reference (e.g. Federal Reserve H.10 or
# equivalent). This rate is a reference input for MUFG cross-currency
# calculations only; it is not introduced as a general ST-EVA FX facility.
#
# Quote direction: USD per JPY means 1 JPY = rate USD.
#   To convert JPY -> USD: usd = jpy * rate_usd_per_jpy
#   To convert USD -> JPY: jpy = usd / rate_usd_per_jpy
MUFG_FX_RATE_USD_PER_JPY = FxRate(
    rate_usd_per_jpy=0.0067,
    as_of="2026-10-16",
    provider="ST-EVA MUFG Cross-Currency Reference",
    source_url="https://www.federalreserve.gov/releases/h10/",
    quote_direction="USD per JPY",
    original_amounts={
        "note": "1 JPY = 0.0067 USD (i.e. 1 USD = ~149.25 JPY). "
        "Rate is illustrative; replace with a sourced rate for production.",
    },
)


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
