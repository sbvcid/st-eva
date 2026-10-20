"""Reproducible tests for historical_pe_adapter.py.

Covers: successful Yahoo Finance fetch and parse, source failure (network /
HTTP error), incomplete data (null closes), min_observations_for_reference
enforcement, standardized output validation (count, coverage, source URL,
save location), hash consistency (raw response vs standardized file),
splits/events metadata preservation, SQLite archive read (secondary source),
and SEC source parsing.

Network-dependent tests are gated by ST_EVA_ADAPTER_LIVE=1 and never run
implicitly in CI.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
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


def _make_chart_result(closes, timestamps=None, currency="USD", symbol="SOFI", exchange="NMS", events=None, adjclose=None):
    if timestamps is None:
        base = int(datetime(2021, 10, 19, tzinfo=timezone.utc).timestamp())
        timestamps = [base + i * 86400 for i in range(len(closes))]
    quote = {"close": closes}
    if adjclose is not None:
        quote["adjclose"] = adjclose
    result = {
        "meta": {
            "currency": currency,
            "symbol": symbol,
            "exchangeName": exchange,
        },
        "timestamp": timestamps,
        "indicators": {
            "quote": [
                quote
            ]
        },
    }
    if events is not None:
        result["events"] = events
    return result


def _make_fetch_tuple(chart_result, raw_sha="abc123rawresponsehash"):
    """Return (chart_result, raw_response_sha256) as fetch_yahoo_daily_prices does."""
    return chart_result, raw_sha


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

        result, raw_sha = fetch_yahoo_daily_prices("SOFI")
        self.assertEqual(result["meta"]["symbol"], "SOFI")
        self.assertEqual(result["meta"]["currency"], "USD")
        self.assertIsNotNone(raw_sha)
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
            summary = save_standardized_prices(
                "SOFI", records, meta, output_dir=out_dir,
                raw_response_sha256="test_raw_hash_value",
            )

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
            self.assertIsNotNone(summary["standardized_content_sha256"])
            self.assertIsNotNone(summary["raw_response_sha256"])

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
            # historical_pe.py reads events.splits from this payload
            self.assertIn("events", chart_result)

    def test_manifest_hash_matches_actual_file(self):
        result = _make_chart_result([20.22, 21.05])
        records, meta = parse_yahoo_price_bars(result, "SOFI")
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = str(Path(tmpdir) / "data" / "historical_pe" / "{ticker}")
            summary = save_standardized_prices("SOFI", records, meta, output_dir=out_dir)

            prices_path = Path(summary["prices_path"])
            manifest_path = Path(summary["manifest_path"])

            # Actual file bytes and hash
            actual_bytes = prices_path.read_bytes()
            actual_sha = hashlib.sha256(actual_bytes).hexdigest()

            # Manifest must match
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["files"]["daily_prices.json"]["bytes"], len(actual_bytes))
            self.assertEqual(
                manifest["files"]["daily_prices.json"]["content_sha256"], actual_sha
            )
            self.assertEqual(
                manifest["source"]["standardized_content_sha256"], actual_sha
            )
            self.assertEqual(
                summary["standardized_content_sha256"], actual_sha
            )

    def test_raw_response_hash_distinct_from_standardized_hash(self):
        result = _make_chart_result([20.22, 21.05])
        records, meta = parse_yahoo_price_bars(result, "SOFI")
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = str(Path(tmpdir) / "data" / "historical_pe" / "{ticker}")
            summary = save_standardized_prices(
                "SOFI", records, meta, output_dir=out_dir,
                raw_response_sha256="raw_hash_distinct_value",
            )

            manifest = json.loads(Path(summary["manifest_path"]).read_text(encoding="utf-8"))
            self.assertEqual(
                manifest["source"]["raw_response_sha256"], "raw_hash_distinct_value"
            )
            self.assertNotEqual(
                manifest["source"]["raw_response_sha256"],
                manifest["source"]["standardized_content_sha256"],
            )

    def test_splits_events_preserved_in_output(self):
        splits = {
            "1672531200": {
                "numerator": 2,
                "denominator": 1,
                "splitRatio": "2:1",
            }
        }
        result = _make_chart_result([20.22, 21.05], events={"splits": splits})
        records, meta = parse_yahoo_price_bars(result, "SOFI")
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = str(Path(tmpdir) / "data" / "historical_pe" / "{ticker}")
            summary = save_standardized_prices(
                "SOFI", records, meta, output_dir=out_dir, raw_payload=result
            )

            prices_path = Path(summary["prices_path"])
            payload = json.loads(prices_path.read_text(encoding="utf-8"))
            chart_result = payload["chart"]["result"][0]
            self.assertIn("events", chart_result)
            self.assertIn("splits", chart_result["events"])
            self.assertEqual(
                chart_result["events"]["splits"], splits
            )
            self.assertTrue(summary["has_split_events"])

    def test_no_splits_recorded_as_empty_dict_not_omitted(self):
        result = _make_chart_result([20.22, 21.05])
        records, meta = parse_yahoo_price_bars(result, "SOFI")
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = str(Path(tmpdir) / "data" / "historical_pe" / "{ticker}")
            summary = save_standardized_prices(
                "SOFI", records, meta, output_dir=out_dir, raw_payload=result
            )

            prices_path = Path(summary["prices_path"])
            payload = json.loads(prices_path.read_text(encoding="utf-8"))
            chart_result = payload["chart"]["result"][0]
            self.assertIn("events", chart_result)
            self.assertEqual(chart_result["events"], {})
            self.assertFalse(summary["has_split_events"])

    def test_adjclose_preserved_when_present(self):
        adjclose = [20.50, 21.30]
        result = _make_chart_result([20.22, 21.05], adjclose=adjclose)
        records, meta = parse_yahoo_price_bars(result, "SOFI")
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = str(Path(tmpdir) / "data" / "historical_pe" / "{ticker}")
            save_standardized_prices(
                "SOFI", records, meta, output_dir=out_dir, raw_payload=result
            )

            prices_path = Path(tmpdir) / "data" / "historical_pe" / "SOFI" / "daily_prices.json"
            payload = json.loads(prices_path.read_text(encoding="utf-8"))
            chart_result = payload["chart"]["result"][0]
            quote = chart_result["indicators"]["quote"][0]
            self.assertEqual(quote["adjclose"], adjclose)

    def test_written_files_use_lf_line_endings(self):
        """Text mode would emit CRLF on Windows, making the recorded byte count
        and SHA-256 differ from a Linux checkout of the same content."""
        result = _make_chart_result([20.22, 21.05])
        records, meta = parse_yahoo_price_bars(result, "SOFI")
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = str(Path(tmpdir) / "data" / "historical_pe" / "{ticker}")
            summary = save_standardized_prices(
                "SOFI", records, meta, output_dir=out_dir,
                raw_response_sha256="test_raw_hash_value",
            )
            for path in (Path(summary["prices_path"]), Path(summary["manifest_path"])):
                raw = path.read_bytes()
                self.assertNotIn(b"\r", raw, f"{path.name} must use LF line endings")

            manifest = json.loads(Path(summary["manifest_path"]).read_text(encoding="utf-8"))
            prices_raw = Path(summary["prices_path"]).read_bytes()
            self.assertEqual(
                manifest["files"]["daily_prices.json"]["bytes"], len(prices_raw)
            )
            self.assertEqual(
                manifest["files"]["daily_prices.json"]["content_sha256"],
                hashlib.sha256(prices_raw).hexdigest(),
            )

    def test_manifest_records_forward_slash_paths(self):
        """A backslash path does not resolve on Linux."""
        result = _make_chart_result([20.22, 21.05])
        records, meta = parse_yahoo_price_bars(result, "SOFI")
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = str(Path(tmpdir) / "data" / "historical_pe" / "{ticker}")
            summary = save_standardized_prices(
                "SOFI", records, meta, output_dir=out_dir,
                raw_response_sha256="test_raw_hash_value",
            )
            manifest = json.loads(Path(summary["manifest_path"]).read_text(encoding="utf-8"))
            for name, meta_entry in manifest["files"].items():
                recorded = meta_entry["path"]
                self.assertNotIn(
                    "\\", recorded,
                    f"{name} records a backslash path, which does not resolve on Linux: {recorded}",
                )
                self.assertTrue(
                    Path(recorded).is_file(),
                    f"{name} records a path that does not resolve: {recorded}",
                )

    def test_source_timestamps_are_preserved(self):
        """The saved series must keep the source timestamps, so re-saving the
        parsed series reproduces the same file byte for byte."""
        result = _make_chart_result([20.22, 21.05])
        records, meta = parse_yahoo_price_bars(result, "SOFI")
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = str(Path(tmpdir) / "data" / "historical_pe" / "{ticker}")
            summary = save_standardized_prices(
                "SOFI", records, meta, output_dir=out_dir,
                raw_response_sha256="test_raw_hash_value",
            )
            payload = json.loads(Path(summary["prices_path"]).read_text(encoding="utf-8"))
            chart_result = payload["chart"]["result"][0]
            self.assertEqual(chart_result["timestamp"], result["timestamp"])


class TestAcquireStandardizedPrices(unittest.TestCase):
    """End-to-end: fetch, parse, validate, save. Min-observations gate."""

    @patch("historical_pe_adapter.fetch_yahoo_daily_prices")
    def test_successful_acquire_returns_summary(self, mock_fetch):
        mock_fetch.return_value = _make_fetch_tuple(_make_chart_result([20.22] * 25))
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = str(Path(tmpdir) / "data" / "historical_pe" / "{ticker}")
            summary = acquire_standardized_prices(
                "SOFI", output_dir=out_dir, min_observations_for_reference=20
            )
            self.assertEqual(summary["price_count"], 25)
            self.assertEqual(summary["ticker"], "SOFI")
            self.assertIsNotNone(summary["prices_path"])
            self.assertIsNotNone(summary["manifest_path"])
            self.assertIsNotNone(summary["standardized_content_sha256"])
            self.assertIsNotNone(summary["raw_response_sha256"])

    @patch("historical_pe_adapter.fetch_yahoo_daily_prices")
    def test_below_min_observations_raises(self, mock_fetch):
        mock_fetch.return_value = _make_fetch_tuple(_make_chart_result([20.22] * 5))
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


class TestSofiDatasetCanonicalBytes(unittest.TestCase):
    """The dataset files must carry canonical LF bytes on every platform.

    The manifests record the byte count and SHA-256 of these files, and the
    production loader derives input_set_id from the same bytes. A checkout that
    rewrote line endings would make a recorded digest platform-specific, so
    the same commit would verify on one platform and fail on another.
    """

    DATA_DIR = Path("data/historical_pe")

    def _tracked_dataset_files(self):
        """Tracked dataset files only.

        Some files under the dataset directory are gitignored local artifacts
        (generated outputs), so they are not part of the committed byte
        contract and must not be asserted on.
        """
        try:
            result = subprocess.run(
                ["git", "ls-files", "--", str(self.DATA_DIR).replace("\\", "/")],
                capture_output=True, text=True, timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            return
        if result.returncode != 0:
            return
        for line in result.stdout.splitlines():
            if line.strip():
                yield Path(line.strip())

    def test_every_dataset_file_has_canonical_lf_bytes(self):
        offenders = []
        for path in self._tracked_dataset_files():
            raw = path.read_bytes()
            if b"\r" in raw:
                offenders.append(f"{path} has {raw.count(13)} CR bytes")
        self.assertEqual(
            offenders, [],
            "dataset files must use LF endings so their digests are platform-independent: "
            + "; ".join(offenders),
        )

    def test_gitattributes_forces_lf_for_the_dataset_directory(self):
        attrs = Path(".gitattributes")
        self.assertTrue(attrs.is_file(), ".gitattributes must exist to keep dataset bytes stable")
        text = attrs.read_text(encoding="utf-8")
        self.assertIn("data/historical_pe/", text)
        self.assertIn("eol=lf", text)

    def test_manifest_paths_use_forward_slashes(self):
        for path in self._tracked_dataset_files():
            if path.name != "manifest.json":
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            for name, meta in (data.get("files") or {}).items():
                recorded = meta.get("path")
                self.assertIsNotNone(recorded, f"{path}: {name} has no path")
                self.assertNotIn(
                    "\\", recorded,
                    f"{path}: {name} records a backslash path, which does not resolve on Linux: {recorded}",
                )
                self.assertTrue(
                    Path(recorded).is_file(),
                    f"{path}: {name} records a path that does not resolve: {recorded}",
                )


class TestSofiManifestIntegrity(unittest.TestCase):
    """Both SOFI manifests must parse and their recorded digests must be true."""

    MANIFEST = Path("data/historical_pe/SOFI/manifest.json")
    PRICES_MANIFEST = Path("data/historical_pe/SOFI/prices_manifest.json")

    def test_main_manifest_parses_with_a_standard_json_parser(self):
        self.assertTrue(self.MANIFEST.exists(), "manifest.json must exist")
        text = self.MANIFEST.read_text(encoding="utf-8")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            self.fail(f"manifest.json must parse with a standard JSON parser: {exc}")
        self.assertIsInstance(data, dict)
        self.assertEqual(data["ticker"], "SOFI")

    def test_prices_manifest_parses_with_a_standard_json_parser(self):
        self.assertTrue(self.PRICES_MANIFEST.exists(), "prices_manifest.json must exist")
        text = self.PRICES_MANIFEST.read_text(encoding="utf-8")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            self.fail(f"prices_manifest.json must parse with a standard JSON parser: {exc}")
        self.assertIsInstance(data, dict)
        self.assertEqual(data["ticker"], "SOFI")

    def test_main_manifest_digests_match_the_actual_files(self):
        data = json.loads(self.MANIFEST.read_text(encoding="utf-8"))
        files = data.get("files") or {}
        self.assertGreater(len(files), 0, "main manifest must record the dataset files")
        for name, meta in files.items():
            path = Path(meta["path"])
            self.assertTrue(path.exists(), f"manifest references a missing file: {path}")
            raw = path.read_bytes()
            self.assertEqual(
                meta["bytes"], len(raw),
                f"manifest byte count is stale for {name}",
            )
            self.assertEqual(
                meta["content_sha256"], hashlib.sha256(raw).hexdigest(),
                f"manifest SHA-256 is stale for {name}",
            )

    def test_prices_manifest_digest_matches_the_actual_daily_prices_file(self):
        data = json.loads(self.PRICES_MANIFEST.read_text(encoding="utf-8"))
        meta = data["files"]["daily_prices.json"]
        path = Path(meta["path"])
        self.assertTrue(path.exists(), f"prices manifest references a missing file: {path}")
        raw = path.read_bytes()
        self.assertEqual(meta["bytes"], len(raw), "prices manifest byte count is stale")
        self.assertEqual(
            meta["content_sha256"], hashlib.sha256(raw).hexdigest(),
            "prices manifest SHA-256 is stale",
        )

    def test_main_manifest_does_not_duplicate_the_prices_manifest_digest(self):
        """The main manifest's own digest for daily_prices.json must equal the
        prices manifest's, so the two cannot drift apart silently."""
        main = json.loads(self.MANIFEST.read_text(encoding="utf-8"))
        prices = json.loads(self.PRICES_MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(
            main["files"]["daily_prices.json"]["content_sha256"],
            prices["files"]["daily_prices.json"]["content_sha256"],
        )
        self.assertEqual(
            main["files"]["daily_prices.json"]["bytes"],
            prices["files"]["daily_prices.json"]["bytes"],
        )

    def test_main_manifest_status_matches_the_saved_data(self):
        """The manifest's status must be the pipeline's own judgement, and the
        recorded counts must match what the saved evidence actually yields."""
        data = json.loads(self.MANIFEST.read_text(encoding="utf-8"))
        pipeline = data["production_pipeline"]

        # The status must be the qualified state, not a price-only state.
        self.assertEqual(data["status"], "USABLE_FOR_REFERENCE")
        self.assertEqual(pipeline["status"], data["status"])
        self.assertTrue(pipeline["usable_for_reference"])
        self.assertGreaterEqual(pipeline["sample_count"], pipeline["min_observations_required"])

        # The recorded SEC evidence counts must match the saved files.
        with open("data/historical_pe/SOFI/eps_diluted_concept.json", encoding="utf-8") as f:
            concept = json.load(f)
        fact_count = len(concept["units"]["USD/shares"])
        self.assertEqual(
            data["sec_evidence"]["eps_diluted_fact_count"], fact_count
        )

        with open("data/historical_pe/SOFI/filing_acceptance_evidence.json", encoding="utf-8") as f:
            acceptance = json.load(f)
        self.assertEqual(
            data["sec_evidence"]["filing_acceptance_row_count"], len(acceptance)
        )
        verified = sum(1 for r in acceptance if r.get("header_verified"))
        api_derived = sum(1 for r in acceptance if not r.get("header_verified"))
        self.assertEqual(data["sec_evidence"]["header_verified_row_count"], verified)
        self.assertEqual(data["sec_evidence"]["api_derived_row_count"], api_derived)
        self.assertEqual(verified + api_derived, len(acceptance))

        with open("data/historical_pe/SOFI/q4_evidence_records.json", encoding="utf-8") as f:
            q4 = json.load(f)
        self.assertEqual(
            data["sec_evidence"]["q4_evidence_record_count"], len(q4["records"])
        )
        self.assertEqual(
            data["sec_evidence"]["q4_evidence_fiscal_years"],
            sorted(r["fiscal_year"] for r in q4["records"]),
        )

        # The price count must match the saved price series.
        with open("data/historical_pe/SOFI/daily_prices.json", encoding="utf-8") as f:
            prices = json.load(f)
        chart = prices["chart"]["result"][0]
        self.assertEqual(data["price_count"], len(chart["timestamp"]))
        self.assertEqual(data["price_count"], len(chart["indicators"]["quote"][0]["close"]))

    def test_main_manifest_does_not_claim_missing_eps_evidence(self):
        """The stale 'no EPS evidence' wording must not survive."""
        data = json.loads(self.MANIFEST.read_text(encoding="utf-8"))
        blob = json.dumps(data).lower()
        self.assertNotIn("no eps evidence", blob)
        self.assertNotIn("price_data_acquired", blob)
        self.assertEqual(data["role"], "production_candidate_qualified")


class TestSofiAcceptanceTimeProvenance(unittest.TestCase):
    """The acceptance-time source must be stated honestly, per row."""

    PATH = Path("data/historical_pe/SOFI/filing_acceptance_evidence.json")
    HEADER_FORMS = ("10-K", "10-K/A", "10-Q", "8-K", "8-K/A")

    def setUp(self):
        with open(self.PATH, encoding="utf-8") as f:
            self.rows = json.load(f)
        self.by_accn = {r["accession"]: r for r in self.rows}

    def test_every_row_declares_its_acceptance_time_source(self):
        for row in self.rows:
            self.assertIn(
                row.get("acceptance_datetime_source"),
                ("SEC_EDGAR_SGML_HEADER_ACCEPTANCE_DATETIME", "SEC_SUBMISSIONS_API_DERIVED"),
                f"row does not state its acceptance-time source: {row}",
            )
            self.assertEqual(
                row.get("acceptance_datetime_precision"), "SECOND",
                f"row does not state acceptance-time precision: {row}",
            )
            self.assertIsNotNone(row.get("acceptance_datetime_header_et"))

    def test_header_verified_rows_carry_real_header_evidence(self):
        verified = [r for r in self.rows if r.get("header_verified")]
        self.assertGreater(len(verified), 0, "no header-verified rows present")
        for row in verified:
            self.assertEqual(
                row["acceptance_datetime_source"],
                "SEC_EDGAR_SGML_HEADER_ACCEPTANCE_DATETIME",
            )
            url = row.get("header_source_url")
            self.assertIsNotNone(url, f"verified row without a header URL: {row}")
            self.assertIn("index-headers.html", url)
            sha = row.get("header_source_sha256")
            self.assertIsNotNone(sha, f"verified row without a header hash: {row}")
            self.assertEqual(len(sha), 64, "header hash must be a SHA-256 hex digest")
            int(sha, 16)
            self.assertGreater(row.get("header_source_bytes") or 0, 0)

    def test_api_derived_rows_never_claim_header_verification(self):
        for row in self.rows:
            if row.get("acceptance_datetime_source") == "SEC_SUBMISSIONS_API_DERIVED":
                self.assertFalse(
                    row.get("header_verified"),
                    f"API-derived row claims header verification: {row}",
                )
                self.assertIsNone(
                    row.get("header_source_sha256"),
                    f"API-derived row carries a header hash: {row}",
                )
                self.assertIsNone(
                    row.get("header_source_url"),
                    f"API-derived row carries a header URL: {row}",
                )

    def test_pipeline_forms_are_all_header_verified(self):
        """Every 10-K / 10-Q / 8-K the pipeline can consume is header-verified."""
        for row in self.rows:
            if row["form"] in self.HEADER_FORMS:
                self.assertTrue(
                    row.get("header_verified"),
                    f"{row['form']} accession is not header-verified: {row['accession']}",
                )

    def test_accession_times_used_by_the_eps_and_q4_evidence_are_et(self):
        """Every acceptance instant the EPS/Q4 evidence relies on is Eastern with
        an explicit offset, and the API value is preserved beside it."""
        with open("data/historical_pe/SOFI/eps_diluted_concept.json", encoding="utf-8") as f:
            concept = json.load(f)
        used = {f["accn"] for f in concept["units"]["USD/shares"] if f.get("start")}
        with open("data/historical_pe/SOFI/q4_evidence_records.json", encoding="utf-8") as f:
            used |= {r["accession"] for r in json.load(f)["records"]}

        self.assertGreater(len(used), 0)
        for accn in used:
            row = self.by_accn.get(accn)
            self.assertIsNotNone(row, f"acceptance row missing for {accn}")
            value = row["acceptance_datetime_header_et"]
            self.assertTrue(
                value.endswith("-04:00") or value.endswith("-05:00"),
                f"acceptance time is not Eastern with an offset: {accn} -> {value}",
            )
            self.assertIsNotNone(
                row.get("acceptance_datetime_submissions_api"),
                f"the raw submissions API value must be preserved: {accn}",
            )

    def test_api_minus_header_offset_is_recorded_for_verified_rows(self):
        for row in self.rows:
            if row.get("header_verified"):
                self.assertIsNotNone(
                    row.get("api_minus_header_hours"),
                    f"verified row without the API-minus-header offset: {row['accession']}",
                )


class TestSofiSecEvidenceFiles(unittest.TestCase):
    """SEC evidence files for SOFI: format, content, and traceability."""

    def test_eps_diluted_concept_format(self):
        path = Path("data/historical_pe/SOFI/eps_diluted_concept.json")
        self.assertTrue(path.exists(), "eps_diluted_concept.json must exist")
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["cik"], "0001818874")
        self.assertEqual(data["entityName"], "SoFi Technologies, Inc.")
        self.assertEqual(data["tag"], "EarningsPerShareDiluted")
        units = data.get("units", {})
        self.assertIn("USD/shares", units)
        facts = units["USD/shares"]
        self.assertGreater(len(facts), 0)
        # Every fact must have start, end, val, accn, form
        for fact in facts:
            self.assertIsNotNone(fact.get("start"), f"Fact missing start: {fact}")
            self.assertIsNotNone(fact.get("end"), f"Fact missing end: {fact}")
            self.assertIsNotNone(fact.get("accn"), f"Fact missing accn: {fact}")
            self.assertIsNotNone(fact.get("form"), f"Fact missing form: {fact}")

    def test_filing_acceptance_evidence_format(self):
        path = Path("data/historical_pe/SOFI/filing_acceptance_evidence.json")
        self.assertTrue(path.exists(), "filing_acceptance_evidence.json must exist")
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)
        # Every row must have accession, form, acceptance_datetime_header_et
        # 10-K and 10-Q rows must also have period_end
        for row in data:
            self.assertIsNotNone(row.get("accession"), f"Row missing accession: {row}")
            self.assertIsNotNone(row.get("form"), f"Row missing form: {row}")
            aet = row.get("acceptance_datetime_header_et")
            self.assertIsNotNone(aet, f"Row missing acceptance_datetime_header_et: {row}")
            self.assertNotIn("Z", aet, f"Acceptance time should be ET not UTC Z: {aet}")
            if row["form"] in ("10-K", "10-Q"):
                self.assertIsNotNone(row.get("period_end"), f"10-K/10-Q row missing period_end: {row}")

    def test_filing_acceptance_has_10k_and_10q(self):
        path = Path("data/historical_pe/SOFI/filing_acceptance_evidence.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        forms = {row["form"] for row in data}
        self.assertIn("10-K", forms, "Must have 10-K filings")
        self.assertIn("10-Q", forms, "Must have 10-Q filings")

    def test_q4_evidence_records_format(self):
        path = Path("data/historical_pe/SOFI/q4_evidence_records.json")
        self.assertTrue(path.exists(), "q4_evidence_records.json must exist")
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertIn("records", data)
        records = data["records"]
        self.assertGreater(len(records), 0, "Must have at least one Q4 record")
        for rec in records:
            self.assertEqual(rec["source_type"], "SEC_8K_ITEM_2_02_EX_99_1")
            self.assertEqual(rec["form"], "8-K")
            self.assertEqual(rec["item"], "2.02")
            self.assertIsNotNone(rec.get("accession"), f"Record missing accession: {rec}")
            self.assertIsNotNone(rec.get("quarter_period_end"), f"Record missing period: {rec}")
            self.assertIsNotNone(rec.get("diluted_eps"), f"Record missing diluted_eps: {rec}")
            self.assertEqual(rec["currency"], "USD")
            self.assertTrue(rec.get("meets_st_eva_q4_evidence"), f"Record must meet Q4 evidence: {rec}")
            # Acceptance datetime must be ET with offset
            aet = rec.get("acceptance_datetime")
            self.assertIsNotNone(aet, f"Record missing acceptance_datetime: {rec}")
            self.assertNotIn("Z", aet, f"Acceptance time should be ET not UTC Z: {aet}")

    def test_q4_evidence_covers_multiple_fiscal_years(self):
        path = Path("data/historical_pe/SOFI/q4_evidence_records.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        records = data["records"]
        fiscal_years = {rec["fiscal_year"] for rec in records}
        self.assertGreaterEqual(len(fiscal_years), 2, "Q4 evidence should span multiple fiscal years")


class TestSofiHistoricalPePipeline(unittest.TestCase):
    """Run historical_pe.py production pipeline on SOFI and validate results."""

    def _run(self):
        from historical_pe import (
            ISSUER_CONFIGS,
            load_issuer_historical_pe,
            MIN_OBSERVATIONS_FOR_REFERENCE,
        )
        # Use the production issuer configuration, not a hand-built one: the
        # input set identity digests issuer_config, so a manifest recorded
        # against the registered configuration must be checked against that
        # same configuration.
        config = ISSUER_CONFIGS["SOFI"]
        return load_issuer_historical_pe(
            config, enable_furnished=True, min_observations=MIN_OBSERVATIONS_FOR_REFERENCE
        )

    def test_sofi_pipeline_produces_usable_reference(self):
        from historical_pe import (
            ISSUER_CONFIGS,
            load_issuer_historical_pe,
            MIN_OBSERVATIONS_FOR_REFERENCE,
            STATUS_USABLE_FOR_REFERENCE,
        )
        config = ISSUER_CONFIGS["SOFI"]
        res = load_issuer_historical_pe(
            config, enable_furnished=True, min_observations=MIN_OBSERVATIONS_FOR_REFERENCE
        )
        self.assertEqual(res.distribution.status, STATUS_USABLE_FOR_REFERENCE)
        self.assertTrue(res.distribution.usable_for_reference)
        self.assertGreaterEqual(res.distribution.sample_count, 20)
        self.assertIsNotNone(res.distribution.period_start)
        self.assertIsNotNone(res.distribution.period_end)
        self.assertIsNotNone(res.distribution.percentiles.get("median"))

    def test_manifest_pipeline_block_matches_the_live_pipeline_output(self):
        """The manifest's recorded production result must be the pipeline's own
        output for the saved data, not a stale or hand-written claim."""
        from historical_pe import STATUS_USABLE_FOR_REFERENCE

        res = self._run()
        with open("data/historical_pe/SOFI/manifest.json", encoding="utf-8") as f:
            manifest = json.load(f)
        recorded = manifest["production_pipeline"]

        self.assertEqual(recorded["status"], res.distribution.status)
        self.assertEqual(recorded["status"], STATUS_USABLE_FOR_REFERENCE)
        self.assertEqual(recorded["usable_for_reference"], res.distribution.usable_for_reference)
        self.assertEqual(recorded["sample_count"], res.distribution.sample_count)
        self.assertEqual(recorded["total_evaluations"], res.distribution.total_evaluations)
        self.assertEqual(recorded["excluded_observations"], len(res.distribution.excluded_observations))
        self.assertEqual(recorded["sample_period_start"], res.distribution.period_start)
        self.assertEqual(recorded["sample_period_end"], res.distribution.period_end)
        self.assertEqual(
            recorded["percentiles"], res.distribution.percentiles,
        )
        self.assertEqual(
            recorded["percentiles"]["median"], res.distribution.percentiles["median"]
        )
        self.assertEqual(recorded["mean"], res.distribution.mean)
        self.assertEqual(recorded["min"], res.distribution.min)
        self.assertEqual(recorded["max"], res.distribution.max)
        self.assertEqual(recorded["input_set_id"], res.input_set_id)
        self.assertEqual(recorded["content_hash"], res.content_hash)

        # The excluded-reason breakdown must be the pipeline's own.
        reasons = {}
        for obs in res.distribution.excluded_observations:
            reasons[obs["reason_code"]] = reasons.get(obs["reason_code"], 0) + 1
        self.assertEqual(recorded["excluded_reason_counts"], reasons)

        # The current snapshot must match too.
        self.assertIsNotNone(res.current_snapshot)
        self.assertEqual(recorded["current_snapshot_status"], res.current_snapshot.status)
        self.assertEqual(recorded["current_snapshot_date"], res.current_snapshot.evaluation_date)
        self.assertEqual(recorded["current_snapshot_value"], res.current_snapshot.value)

    def test_sofi_pipeline_price_basis_is_as_traded(self):
        from historical_pe import (
            ISSUER_CONFIGS,
            load_issuer_historical_pe,
            MIN_OBSERVATIONS_FOR_REFERENCE,
            STATUS_AVAILABLE,
        )
        config = ISSUER_CONFIGS["SOFI"]
        res = load_issuer_historical_pe(
            config, enable_furnished=True, min_observations=MIN_OBSERVATIONS_FOR_REFERENCE
        )
        for obs in res.observations:
            if obs.status == STATUS_AVAILABLE:
                basis = obs.price_state.get("accounting_basis")
                self.assertEqual(basis, "as_traded", f"Price basis must be as_traded, got {basis}")

    def test_sofi_pipeline_pit_monotonicity(self):
        from historical_pe import (
            ISSUER_CONFIGS,
            load_issuer_historical_pe,
            MIN_OBSERVATIONS_FOR_REFERENCE,
            STATUS_AVAILABLE,
        )
        config = ISSUER_CONFIGS["SOFI"]
        res = load_issuer_historical_pe(
            config, enable_furnished=True, min_observations=MIN_OBSERVATIONS_FOR_REFERENCE
        )
        for obs in res.observations:
            if obs.status == STATUS_AVAILABLE:
                for comp in obs.eps_state.get("components", []):
                    self.assertLessEqual(
                        comp["usable_date"], obs.evaluation_date,
                        f"PIT violation: usable_date {comp['usable_date']} > evaluation_date {obs.evaluation_date}",
                    )

    def test_sofi_unavailable_reasons_are_explicit(self):
        from historical_pe import (
            ISSUER_CONFIGS,
            load_issuer_historical_pe,
            MIN_OBSERVATIONS_FOR_REFERENCE,
            STATUS_UNAVAILABLE,
        )
        config = ISSUER_CONFIGS["SOFI"]
        res = load_issuer_historical_pe(
            config, enable_furnished=True, min_observations=MIN_OBSERVATIONS_FOR_REFERENCE
        )
        for obs in res.observations:
            if obs.status == STATUS_UNAVAILABLE:
                self.assertIsNotNone(obs.reason_code, f"Unavailable obs {obs.evaluation_date} must have reason_code")
                self.assertIsNotNone(obs.reason_detail, f"Unavailable obs {obs.evaluation_date} must have reason_detail")
                self.assertIn(obs.reason_code, (
                    "REASON_MISSING_Q4_EPS",
                    "REASON_NON_POSITIVE_EPS",
                    "REASON_INSUFFICIENT_QUARTERS",
                    "REASON_MISSING_PRICE",
                ), f"Unexpected reason code: {obs.reason_code}")


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
