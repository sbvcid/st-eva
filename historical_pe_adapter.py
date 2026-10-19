"""
Reusable historical price data acquisition adapter.

Provides a generic ticker interface for acquiring daily historical price
observations from an external source (Yahoo Finance chart API), saving them
as standardized, source-traceable JSON, and validating sufficiency against
a minimum-observation threshold.

Not a valuation engine: acquisition, normalization, and persistence only.
SQLite archive reading is retained as a secondary, clearly-labelled source
and is never repackaged as newly acquired external data.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
DEFAULT_RANGE = "5y"
DEFAULT_INTERVAL = "1d"
USER_AGENT = "Mozilla/5.0 ST-EVA/2.1"
REQUEST_TIMEOUT = 20
DEFAULT_MIN_OBSERVATIONS = 20


class HistoricalPriceAdapterError(Exception):
    """Raised when price acquisition or persistence fails."""


# ---------------------------------------------------------------------------
# External source: Yahoo Finance chart API
# ---------------------------------------------------------------------------

def fetch_yahoo_daily_prices(
    ticker: str,
    *,
    range_param: str = DEFAULT_RANGE,
    interval: str = DEFAULT_INTERVAL,
    timeout: int = REQUEST_TIMEOUT,
) -> Dict[str, Any]:
    """
    Fetch daily historical price bars for a ticker from Yahoo Finance chart API.

    Returns the raw chart result dict. Raises HistoricalPriceAdapterError on
    network failure, HTTP error, or an empty/malformed response.
    """
    url = YAHOO_CHART_URL.format(ticker=ticker.upper()) + f"?range={range_param}&interval={interval}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise HistoricalPriceAdapterError(
            f"Yahoo Finance HTTP {exc.code} for {ticker}: {exc.reason}"
        ) from exc
    except urllib.error.URLError as exc:
        raise HistoricalPriceAdapterError(
            f"Yahoo Finance network error for {ticker}: {exc.reason}"
        ) from exc
    except Exception as exc:
        raise HistoricalPriceAdapterError(
            f"Yahoo Finance request failed for {ticker}: {exc}"
        ) from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HistoricalPriceAdapterError(
            f"Yahoo Finance returned invalid JSON for {ticker}: {exc}"
        ) from exc

    result = (payload.get("chart") or {}).get("result") or []
    if not result:
        error = (payload.get("chart") or {}).get("error")
        if error:
            raise HistoricalPriceAdapterError(
                f"Yahoo Finance API error for {ticker}: {error}"
            )
        raise HistoricalPriceAdapterError(
            f"Yahoo Finance returned no chart result for {ticker}"
        )

    return result[0]


def parse_yahoo_price_bars(
    chart_result: Dict[str, Any],
    ticker: str,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Parse a Yahoo Finance chart result into standardized daily price records.

    Returns (records, meta). Each record has price_date, close, currency,
    accounting_basis, price_source, price_source_url.

    Raises HistoricalPriceAdapterError when no usable closes are present.
    """
    meta = chart_result.get("meta") or {}
    timestamps = chart_result.get("timestamp") or []
    quote = (chart_result.get("indicators") or {}).get("quote") or [{}]
    closes = quote[0].get("close") or [] if quote else []

    currency = meta.get("currency", "USD")
    symbol = meta.get("symbol", ticker.upper())
    exchange = meta.get("exchangeName")
    source_url = YAHOO_CHART_URL.format(ticker=ticker.upper())

    records: List[Dict[str, Any]] = []
    for idx, stamp in enumerate(timestamps):
        close = closes[idx] if idx < len(closes) else None
        if close is None:
            continue
        try:
            close_val = float(close)
        except (TypeError, ValueError):
            continue
        price_date = datetime.fromtimestamp(int(stamp), tz=timezone.utc).date().isoformat()
        records.append({
            "price_date": price_date,
            "close": round(close_val, 6),
            "currency": currency,
            "accounting_basis": "as_traded",
            "price_source": "Yahoo Finance chart API v8 close",
            "price_source_url": source_url,
        })

    if not records:
        raise HistoricalPriceAdapterError(
            f"No usable daily close prices parsed for {ticker}"
        )

    meta_summary = {
        "symbol": symbol,
        "exchange": exchange,
        "currency": currency,
        "source_url": source_url,
        "record_count": len(records),
        "first_date": records[0]["price_date"],
        "last_date": records[-1]["price_date"],
    }
    return records, meta_summary


# ---------------------------------------------------------------------------
# Persistence: standardized price JSON + manifest
# ---------------------------------------------------------------------------

def save_standardized_prices(
    ticker: str,
    records: List[Dict[str, Any]],
    meta: Dict[str, Any],
    output_dir: str = "data/historical_pe/{ticker}",
    raw_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Save standardized daily price records as JSON with full source traceability.

    Writes:
      - daily_prices.json: normalized records in the Yahoo-chart shape consumed
        by historical_pe.py (chart.wrapped with meta/timestamp/indicators).
      - prices_manifest.json: source, count, coverage period, save location,
        currency, and content digests.

    Returns a summary dict with count, coverage period, source URL, and save paths.
    """
    out_dir = Path(output_dir.format(ticker=ticker.upper()))
    out_dir.mkdir(parents=True, exist_ok=True)

    prices_path = out_dir / "daily_prices.json"
    manifest_path = out_dir / "prices_manifest.json"

    timestamp_ints = [
        int(datetime.fromisoformat(r["price_date"]).replace(tzinfo=timezone.utc).timestamp())
        for r in records
    ]
    chart_payload = {
        "chart": {
            "result": [
                {
                    "meta": {
                        "currency": meta.get("currency", "USD"),
                        "symbol": meta.get("symbol", ticker.upper()),
                        "exchangeName": meta.get("exchange"),
                    },
                    "timestamp": timestamp_ints,
                    "indicators": {
                        "quote": [
                            {
                                "close": [r["close"] for r in records],
                            }
                        ]
                    },
                }
            ]
        }
    }
    payload_bytes = json.dumps(chart_payload, indent=2, ensure_ascii=False).encode("utf-8")
    content_sha256 = hashlib.sha256(payload_bytes).hexdigest()
    prices_path.write_bytes(payload_bytes)

    source_url = meta.get("source_url") or YAHOO_CHART_URL.format(ticker=ticker.upper())
    manifest = {
        "ticker": ticker.upper(),
        "symbol": meta.get("symbol", ticker.upper()),
        "exchange": meta.get("exchange"),
        "currency": meta.get("currency", "USD"),
        "role": "price_acquisition",
        "source": {
            "provider": "Yahoo Finance chart API v8",
            "url": source_url,
            "content_sha256": content_sha256,
        },
        "price_count": len(records),
        "coverage": {
            "first_date": records[0]["price_date"],
            "last_date": records[-1]["price_date"],
        },
        "saved_at": str(datetime.now(timezone.utc)),
        "files": {
            "daily_prices.json": {
                "path": str(prices_path),
                "bytes": len(payload_bytes),
                "content_sha256": content_sha256,
            },
            "prices_manifest.json": {
                "path": str(manifest_path),
            },
        },
        "note": "Standardized daily close prices acquired from Yahoo Finance. "
                "Source-traceable, date and currency semantics explicit. "
                "Not repackaged from existing SQLite observations.",
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return {
        "ticker": ticker.upper(),
        "price_count": len(records),
        "first_date": records[0]["price_date"],
        "last_date": records[-1]["price_date"],
        "currency": meta.get("currency", "USD"),
        "source_url": source_url,
        "prices_path": str(prices_path),
        "manifest_path": str(manifest_path),
        "content_sha256": content_sha256,
    }


# ---------------------------------------------------------------------------
# End-to-end acquisition
# ---------------------------------------------------------------------------

def acquire_standardized_prices(
    ticker: str,
    *,
    range_param: str = DEFAULT_RANGE,
    interval: str = DEFAULT_INTERVAL,
    output_dir: str = "data/historical_pe/{ticker}",
    min_observations_for_reference: int = DEFAULT_MIN_OBSERVATIONS,
    timeout: int = REQUEST_TIMEOUT,
) -> Dict[str, Any]:
    """
    End-to-end: fetch, parse, validate, and save standardized daily prices.

    Raises HistoricalPriceAdapterError on any failure (network, parse,
    insufficient observations).
    """
    chart_result = fetch_yahoo_daily_prices(
        ticker, range_param=range_param, interval=interval, timeout=timeout
    )
    records, meta = parse_yahoo_price_bars(chart_result, ticker)

    if len(records) < min_observations_for_reference:
        raise HistoricalPriceAdapterError(
            f"{ticker}: only {len(records)} daily price observations, "
            f"below the {min_observations_for_reference} required for a reference series."
        )

    return save_standardized_prices(
        ticker, records, meta, output_dir=output_dir, raw_payload=chart_result
    )


# ---------------------------------------------------------------------------
# Secondary source: SQLite archive read (clearly labelled, not new acquisition)
# ---------------------------------------------------------------------------

def read_sqlite_price_observations(
    archive_path: str,
    ticker: str = "SOFI",
) -> Dict[str, Any]:
    """
    Read historical price observations from an existing SQLite archive.

    This is a read-only inspection of pre-existing observations. It is NOT
    external acquisition and must not be represented as newly fetched data.
    """
    result: Dict[str, Any] = {
        "ticker": ticker,
        "source": f"SQLite archive: {archive_path}",
        "archive_price_observations": 0,
        "archive_price_dates": [],
        "note": "Pre-existing archive observations only; no external data acquired.",
    }

    try:
        conn = sqlite3.connect(archive_path)
        conn.row_factory = sqlite3.Row

        price_obs = conn.execute(
            "SELECT observation_id, value_json, currency, currency_basis, as_of "
            "FROM observations WHERE metric='price' ORDER BY as_of DESC"
        ).fetchall()

        result["archive_price_observations"] = len(price_obs)
        result["archive_price_dates"] = [
            {
                "observation_id": r["observation_id"],
                "as_of": r["as_of"],
                "value_json": r["value_json"],
                "currency": r["currency"],
                "currency_basis": r["currency_basis"],
            }
            for r in price_obs
        ]
        conn.close()
    except sqlite3.Error as exc:
        result["status"] = "ERROR"
        result["blocking_reason"] = f"Archive read error: {exc}"

    return result


# ---------------------------------------------------------------------------
# Legacy entry point (kept for compatibility, delegates to acquisition)
# ---------------------------------------------------------------------------

def build_sofi_historical_pe_dataset(
    archive_path: str = "data/archives/SOFI.sqlite",
    output_dir: str = "data/historical_pe/SOFI",
    min_observations_for_reference: int = DEFAULT_MIN_OBSERVATIONS,
) -> Dict[str, Any]:
    """
    Legacy SOFI entry point. Reads the SQLite archive (secondary source) and
    reports its observations. Does NOT acquire external data.

    Use acquire_standardized_prices("SOFI", ...) for actual external price
    acquisition from Yahoo Finance.
    """
    archive_info = read_sqlite_price_observations(archive_path, ticker="SOFI")
    price_count = archive_info.get("archive_price_observations", 0)

    result = {
        "ticker": "SOFI",
        "status": "INSUFFICIENT_OBSERVATIONS",
        "sample_count": 0,
        "effective_observations": 0,
        "qualifying_observations": 0,
        "archive_price_observations": price_count,
        "archive_price_dates": archive_info.get("archive_price_dates", []),
        "sources_attempted": [
            f"{archive_path} (SQLite archive, secondary source)",
        ],
        "note": "Archive-only read. No external price data acquired. "
                "Use acquire_standardized_prices() to fetch from Yahoo Finance.",
    }

    if archive_info.get("status") == "ERROR":
        result["status"] = "ERROR"
        result["blocking_reasons"] = [archive_info.get("blocking_reason", "Unknown archive error")]
    elif price_count >= min_observations_for_reference:
        result["status"] = "ARCHIVE_OBSERVATIONS_AVAILABLE"
        result["qualifying_observations"] = price_count
        result["sample_count"] = price_count
        result["effective_observations"] = price_count
    else:
        result["status"] = "INSUFFICIENT_OBSERVATIONS"
        result["blocking_reasons"] = [
            f"Only {price_count} historical price observations in archive (need {min_observations_for_reference} for a reference series).",
            "No external price source queried by this legacy entry point.",
        ]

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    manifest_path = Path(output_dir) / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({
            "ticker": "SOFI",
            "ticker_identifier": "SOFI",
            "role": "production_candidate_checked",
            "status": result["status"],
            "sample_count": result["sample_count"],
            "effective_observations": result["effective_observations"],
            "qualifying_observations": result["qualifying_observations"],
            "sources_attempted": result["sources_attempted"],
            "archive_observation_summary": price_count,
            "note": "Archive-only read. Not promoted to production reference.",
            "derived_at": str(datetime.now(timezone.utc)),
        }, f, indent=2, ensure_ascii=False)

    return result


if __name__ == "__main__":
    print("SOFI archive-only audit:")
    res = build_sofi_historical_pe_dataset()
    print(f"Status: {res['status']}")
    print(f"Archive price obs: {res.get('archive_price_observations', 'N/A')}")
    print(f"Blocking reasons: {res.get('blocking_reasons', [])}")
