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

    def test_sofi_pipeline_produces_usable_reference(self):
        from historical_pe import (
            IssuerHistoricalPeConfig,
            load_issuer_historical_pe,
            MIN_OBSERVATIONS_FOR_REFERENCE,
            STATUS_USABLE_FOR_REFERENCE,
        )
        config = IssuerHistoricalPeConfig(
            ticker="SOFI",
            issuer_id="0001818874",
            fye_month=12,
            data_dir=Path("data/historical_pe/SOFI"),
            canonical_path=None,
        )
        res = load_issuer_historical_pe(
            config, enable_furnished=True, min_observations=MIN_OBSERVATIONS_FOR_REFERENCE
        )
        self.assertEqual(res.distribution.status, STATUS_USABLE_FOR_REFERENCE)
        self.assertTrue(res.distribution.usable_for_reference)
        self.assertGreaterEqual(res.distribution.sample_count, 20)
        self.assertIsNotNone(res.distribution.period_start)
        self.assertIsNotNone(res.distribution.period_end)
        self.assertIsNotNone(res.distribution.percentiles.get("median"))

    def test_sofi_pipeline_price_basis_is_as_traded(self):
        from historical_pe import (
            IssuerHistoricalPeConfig,
            load_issuer_historical_pe,
            MIN_OBSERVATIONS_FOR_REFERENCE,
            STATUS_AVAILABLE,
        )
        config = IssuerHistoricalPeConfig(
            ticker="SOFI",
            issuer_id="0001818874",
            fye_month=12,
            data_dir=Path("data/historical_pe/SOFI"),
            canonical_path=None,
        )
        res = load_issuer_historical_pe(
            config, enable_furnished=True, min_observations=MIN_OBSERVATIONS_FOR_REFERENCE
        )
        for obs in res.observations:
            if obs.status == STATUS_AVAILABLE:
                basis = obs.price_state.get("accounting_basis")
                self.assertEqual(basis, "as_traded", f"Price basis must be as_traded, got {basis}")

    def test_sofi_pipeline_pit_monotonicity(self):
        from historical_pe import (
            IssuerHistoricalPeConfig,
            load_issuer_historical_pe,
            MIN_OBSERVATIONS_FOR_REFERENCE,
            STATUS_AVAILABLE,
        )
        config = IssuerHistoricalPeConfig(
            ticker="SOFI",
            issuer_id="0001818874",
            fye_month=12,
            data_dir=Path("data/historical_pe/SOFI"),
            canonical_path=None,
        )
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
            IssuerHistoricalPeConfig,
            load_issuer_historical_pe,
            MIN_OBSERVATIONS_FOR_REFERENCE,
            STATUS_UNAVAILABLE,
        )
        config = IssuerHistoricalPeConfig(
            ticker="SOFI",
            issuer_id="0001818874",
            fye_month=12,
            data_dir=Path("data/historical_pe/SOFI"),
            canonical_path=None,
        )
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
