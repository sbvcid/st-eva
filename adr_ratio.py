"""
ADR ratio data source for ST-EVA cross-currency analysis.

Provides the ADR ratio for MUFG (Mitsubishi UFJ Financial Group), whose USD
ADR price must be converted to underlying JPY share price using the ADR
deposit ratio.

Every ADR ratio observation carries:
  - ratio: number of underlying ordinary shares per one ADR
  - as_of: the date the ratio was observed
  - provider: the data provider
  - source_url: the source document
  - exchange: the exchange where the ADR trades

This module does NOT perform implicit conversion. Callers must explicitly
request an ADR-converted figure and name the ADR ratio used.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AdrRatio:
    """One ADR ratio observation: underlying shares per one ADR."""

    underlying_shares_per_adr: float
    as_of: str
    provider: str
    source_url: str
    exchange: str = "NYSE"
    original_amounts: Optional[dict] = None


# MUFG ADR ratio: 1 MUFG ADR (NYSE: MUFG) = 2 underlying ordinary shares
# (TSE: 8309). Source: MUFG ADR deposit agreement / BNY Mellon ADR directory.
MUFG_ADR_RATIO = AdrRatio(
    underlying_shares_per_adr=2.0,
    as_of="2026-10-16",
    provider="ST-EVA MUFG Cross-Currency Reference",
    source_url="https://www.bnymellon.com/us/en/adrs/directory.html",
    exchange="NYSE",
    original_amounts={
        "note": "1 MUFG ADR = 2 underlying ordinary shares. "
        "ADR price in USD ÷ 2 = underlying share price in USD. "
        "Then apply USD/JPY FX rate to get JPY share price.",
    },
)


def mufg_adr_ratio() -> Optional[AdrRatio]:
    """Return the MUFG ADR ratio reference, or None if unavailable."""
    return MUFG_ADR_RATIO


def adr_price_to_underlying_usd(adr_price_usd: float, adr: AdrRatio) -> float:
    """Convert ADR price in USD to underlying share price in USD.

    underlying_usd = adr_price_usd / underlying_shares_per_adr
    """
    return adr_price_usd / adr.underlying_shares_per_adr


def underlying_usd_to_jpy(underlying_usd: float, fx_rate) -> float:
    """Convert underlying share price from USD to JPY using the FX rate.

    underlying_jpy = underlying_usd / fx_rate.rate_usd_per_jpy
    """
    return underlying_usd / fx_rate.rate_usd_per_jpy
