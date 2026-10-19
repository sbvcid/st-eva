"""Reproducible tests for historical_pe_adapter.py.

Covers: successful Yahoo Finance fetch and parse, source failure (network /
HTTP error), incomplete data (null closes), min_observations_for_reference
enforcement, standardized output validation (count, coverage, source URL,
save location), and SQLite archive read (secondary source).

Network-dependent tests are gated by ST_EVA_ADAPTER_LIVE=1 and never run
implicitly in CI.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

from historical_pe_adapter import (
    HistoricalPriceAdapterError,
    acquire_standardized_prices,
    fetch_yahoo_daily_prices,
    parse_yahoo_price_bars,
    read_sqlite_price_observations,
    save_standardized_prices,
    YAHOO_CHART_URL,
)

LIVE = os.environ.get("ST_EVA_ADAPTER_LIVE") == "1"


def _make_chart_result(closes, timestamps=None, currency="USD", symbol="SOFI", exchange="NMS"):
    if timestamps is None:
        base = int(datetime(2021, 10, 19, tzinfo=timezone.utc).timestamp())
        timestamps = [base + i * 86400 for i in range(len(closes))]
    return {
        "meta": {
            "currency": currency,
            "symbol": symbol,
            "exchangeName": exchange,
        },
        "timestamp": timestamps,
        "indicators": {
            "quote": [
                {
                    "close": closes,
                }
            ]
        },
    }


class TestFetchYahooDailyPrices(unittest.TestCase):
    """External-source fetch: success, HTTP error, network error, empty result."""

    @patch("historical_pe_adapter.urllib.request.urlopen")
    def test_successful_fetch_returns_chart_result(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "chart": {
                "result": [
                    {
                        "meta": {"currency": "USD", "symbol": "SOFI", "exchangeName": "NMS"},
                        "timestamp": [1634601600],
                        "indicators": {"quote": [{"close": [20.22]}]},
                    }
                ]
            }
        }).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = False
        mock_urlopen.return_value = mock_response

        result = fetch_yahoo_daily_prices("SOFI")
        self.assertEqual(result["meta"]["symbol"], "SOFI")
        self.assertEqual(result["meta"]["currency"], "USD")
        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        self.assertIn("SOFI", req.full_url)
        headers = {k.lower(): v for k, v in req.header_items()}
        self.assertIn("user-agent", headers)
        self.assertEqual(headers["user-agent"], "Mozilla/5.0 ST-EVA/2.1")

    @patch("historical_pe_adapter.urllib.request.urlopen")
    def test_http_error_raises_adapter_error(self, mock_urlopen):
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError(
            YAHOO_CHART_URL.format(ticker="SOFI"), 404, "Not Found", {}, None
        )
        with self.assertRaises(HistoricalPriceAdapterError) as ctx:
            fetch_yahoo_daily_prices("SOFI")
        self.assertIn("HTTP 404", str(ctx.exception))

    @patch("historical_pe_adapter.urllib.request.urlopen")
    def test_network_error_raises_adapter_error(self, mock_urlopen):
        mock_urlopen.side_effect = OSError("network unreachable")
        with self.assertRaises(HistoricalPriceAdapterError) as ctx:
            fetch_yahoo_daily_prices("SOFI")
        self.assertIn("request failed", str(ctx.exception).lower())

    @patch("historical_pe_adapter.urllib.request.urlopen")
    def test_invalid_json_raises_adapter_error(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b"not json"
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = False
        mock_urlopen.return_value = mock_response
        with self.assertRaises(HistoricalPriceAdapterError) as ctx:
            fetch_yahoo_daily_prices("SOFI")
        self.assertIn("invalid JSON", str(ctx.exception))

    @patch("historical_pe_adapter.urllib.request.urlopen")
    def test_empty_result_raises_adapter_error(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"chart": {"result": []}}).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = False
        mock_urlopen.return_value = mock_response
        with self.assertRaises(HistoricalPriceAdapterError) as ctx:
            fetch_yahoo_daily_prices("SOFI")
        self.assertIn("no chart result", str(ctx.exception))


class TestParseYahooPriceBars(unittest.TestCase):
    """Parse: valid bars, null closes dropped, empty result raises."""

    def test_valid_bars_parsed_with_date_currency_source(self):
        result = _make_chart_result([20.22, 21.05, 20.99])
        records, meta = parse_yahoo_price_bars(result, "SOFI")
        self.assertEqual(len(records), 3)
        self.assertEqual(records[0]["price_date"], "2021-10-19")
        self.assertEqual(records[0]["close"], 20.22)
        self.assertEqual(records[0]["currency"], "USD")
        self.assertEqual(records[0]["accounting_basis"], "as_traded")
        self.assertEqual(records[0]["price_source"], "Yahoo Finance chart API v8 close")
        self.assertIn("query1.finance.yahoo.com/v8/finance/chart/SOFI", records[0]["price_source_url"])
        self.assertEqual(meta["symbol"], "SOFI")
        self.assertEqual(meta["record_count"], 3)

    def test_null_closes_dropped(self):
        result = _make_chart_result([20.22, None, 20.99])
        records, _ = parse_yahoo_price_bars(result, "SOFI")
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["close"], 20.22)
        self.assertEqual(records[1]["close"], 20.99)

    def test_all_null_closes_raises(self):
        result = _make_chart_result([None, None, None])
        with self.assertRaises(HistoricalPriceAdapterError) as ctx:
            parse_yahoo_price_bars(result, "SOFI")
        self.assertIn("No usable daily close prices", str(ctx.exception))

    def test_mismatched_lengths_handled(self):
        result = _make_chart_result([20.22], timestamps=[1634601600, 1634688000])
        records, _ = parse_yahoo_price_bars(result, "SOFI")
        self.assertEqual(len(records), 1)


class TestSaveStandardizedPrices(unittest.TestCase):
    """Persistence: writes daily_prices.json and prices_manifest.json, returns summary."""

    def test_writes_both_files_and_returns_summary(self):
        result = _make_chart_result([20.22, 21.05])
        records, meta = parse_yahoo_price_bars(result, "SOFI")
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = str(Path(tmpdir) / "data" / "historical_pe" / "{ticker}")
            summary = save_standardized_prices("SOFI", records, meta, output_dir=out_dir)

            prices_path = Path(tmpdir) / "data" / "historical_pe" / "SOFI" / "daily_prices.json"
            manifest_path = Path(tmpdir) / "data" / "historical_pe" / "SOFI" / "prices_manifest.json"
            self.assertTrue(prices_path.exists())
            self.assertTrue(manifest_path.exists())

            self.assertEqual(summary["ticker"], "SOFI")
            self.assertEqual(summary["price_count"], 2)
            self.assertEqual(summary["currency"], "USD")
            self.assertIn("query1.finance.yahoo.com/v8/finance/chart/SOFI", summary["source_url"])
            self.assertEqual(summary["prices_path"], str(prices_path))
            self.assertEqual(summary["manifest_path"], str(manifest_path))
            self.assertIsNotNone(summary["content_sha256"])

            # Manifest content validation
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["price_count"], 2)
            self.assertEqual(manifest["coverage"]["first_date"], "2021-10-19")
            self.assertEqual(manifest["coverage"]["last_date"], "2021-10-20")
            self.assertEqual(manifest["currency"], "USD")
            self.assertEqual(manifest["source"]["provider"], "Yahoo Finance chart API v8")
            self.assertEqual(manifest["source"]["url"], "https://query1.finance.yahoo.com/v8/finance/chart/SOFI")
            self.assertIn("Not repackaged from existing SQLite observations", manifest["note"])

    def test_daily_prices_json_consumable_by_historical_pe(self):
        result = _make_chart_result([20.22, 21.05])
        records, meta = parse_yahoo_price_bars(result, "SOFI")
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = str(Path(tmpdir) / "data" / "historical_pe" / "{ticker}")
            save_standardized_prices("SOFI", records, meta, output_dir=out_dir)
            prices_path = Path(tmpdir) / "data" / "historical_pe" / "SOFI" / "daily_prices.json"
            payload = json.loads(prices_path.read_text(encoding="utf-8"))
            self.assertIn("chart", payload)
            self.assertIn("result", payload["chart"])
            chart_result = payload["chart"]["result"][0]
            self.assertEqual(len(chart_result["timestamp"]), 2)
            self.assertEqual(len(chart_result["indicators"]["quote"][0]["close"]), 2)
            self.assertEqual(chart_result["meta"]["symbol"], "SOFI")


class TestAcquireStandardizedPrices(unittest.TestCase):
    """End-to-end: fetch, parse, validate, save. Min-observations gate."""

    @patch("historical_pe_adapter.fetch_yahoo_daily_prices")
    def test_successful_acquire_returns_summary(self, mock_fetch):
        mock_fetch.return_value = _make_chart_result([20.22] * 25)
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = str(Path(tmpdir) / "data" / "historical_pe" / "{ticker}")
            summary = acquire_standardized_prices(
                "SOFI", output_dir=out_dir, min_observations_for_reference=20
            )
            self.assertEqual(summary["price_count"], 25)
            self.assertEqual(summary["ticker"], "SOFI")
            self.assertIsNotNone(summary["prices_path"])
            self.assertIsNotNone(summary["manifest_path"])

    @patch("historical_pe_adapter.fetch_yahoo_daily_prices")
    def test_below_min_observations_raises(self, mock_fetch):
        mock_fetch.return_value = _make_chart_result([20.22] * 5)
        with self.assertRaises(HistoricalPriceAdapterError) as ctx:
            acquire_standardized_prices("SOFI", min_observations_for_reference=20)
        self.assertIn("below the 20 required", str(ctx.exception))

    @patch("historical_pe_adapter.fetch_yahoo_daily_prices")
    def test_fetch_error_propagates(self, mock_fetch):
        mock_fetch.side_effect = HistoricalPriceAdapterError("Yahoo Finance network error for SOFI")
        with self.assertRaises(HistoricalPriceAdapterError):
            acquire_standardized_prices("SOFI")


class TestReadSqlitePriceObservations(unittest.TestCase):
    """Secondary source: SQLite archive read, clearly labelled."""

    def test_reads_existing_archive(self):
        result = read_sqlite_price_observations(
            "data/archives/SOFI.sqlite", ticker="SOFI"
        )
        self.assertEqual(result["ticker"], "SOFI")
        self.assertIn("SQLite archive", result["source"])
        self.assertIsInstance(result["archive_price_observations"], int)
        self.assertIsInstance(result["archive_price_dates"], list)
        self.assertIn("no external data acquired", result["note"].lower())

    def test_missing_archive_returns_error(self):
        result = read_sqlite_price_observations("data/archives/NONEXISTENT.sqlite", ticker="XXX")
        self.assertEqual(result.get("status"), "ERROR")
        self.assertIn("Archive read error", result.get("blocking_reason", ""))


@unittest.skipUnless(LIVE, "ST_EVA_ADAPTER_LIVE=1 required for live network test")
class TestLiveAcquireSOFI(unittest.TestCase):
    """Live end-to-end acquisition of SOFI from Yahoo Finance."""

    def test_live_acquire_sofi_returns_real_data(self):
        summary = acquire_standardized_prices("SOFI", min_observations_for_reference=20)
        self.assertEqual(summary["ticker"], "SOFI")
        self.assertGreaterEqual(summary["price_count"], 20)
        self.assertEqual(summary["currency"], "USD")
        self.assertEqual(summary["source_url"], "https://query1.finance.yahoo.com/v8/finance/chart/SOFI")
        self.assertTrue(Path(summary["prices_path"]).exists())
        self.assertTrue(Path(summary["manifest_path"]).exists())
        self.assertLess(summary["first_date"], summary["last_date"])
