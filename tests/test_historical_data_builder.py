import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from historical_data_builder import (
    build_acceptance_index_from_submissions,
    fetch_daily_prices,
    _validate_ticker,
    _validate_cik,
    _validate_years,
    build_sgml_header_url,
    build_filing_index_url,
    build_manifest,
    assert_promotion_ready,
    BuilderValidationError,
)


def test_build_acceptance_index_from_submissions():
    subs = {
        "filings": {
            "recent": {
                "accessionNumber": ["0001652044-26-000084", "0001652044-26-000018"],
                "form": ["10-Q", "10-K"],
                "filingDate": ["2026-10-29", "2026-02-05"],
                "reportDate": ["2026-09-30", "2025-12-31"],
            }
        }
    }
    out = build_acceptance_index_from_submissions(subs)
    assert len(out) == 2
    assert out[0]["form"] == "10-Q"
    assert out[0]["acceptance_datetime_header_et"] is None
    assert out[0]["acceptance_source"] == "SUBMISSIONS_API_ONLY_UNVERIFIED"


def test_fetch_daily_prices_uses_yahoo_chart():
    fake = {"chart": {"result": [{"meta": {"symbol": "GOOGL"}, "timestamp": [1], "indicators": {"quote": [{"close": [1.0]}], "adjclose": [{"adjclose": [1.0]}]}}]}}
    with patch("historical_data_builder.urllib.request.urlopen") as m:
        cm = MagicMock()
        cm.__enter__.return_value.read.return_value = json.dumps(fake).encode()
        m.return_value = cm
        res = fetch_daily_prices("GOOGL", years=3)
    assert res["chart"]["result"][0]["meta"]["symbol"] == "GOOGL"


def test_input_validation():
    assert _validate_ticker(" googl ") == "GOOGL"
    with pytest.raises(BuilderValidationError):
        _validate_ticker("")
    assert _validate_cik("1652044") == "0001652044"
    with pytest.raises(BuilderValidationError):
        _validate_cik("abc")
    assert _validate_years(6) == 6
    with pytest.raises(BuilderValidationError):
        _validate_years(0)
    with pytest.raises(BuilderValidationError):
        _validate_years(True)


def test_url_builders():
    assert "index-headers.html" in build_sgml_header_url("0001652044", "0001652044-26-000084")
    assert "index.json" in build_filing_index_url("0001652044", "0001652044-26-000084")


def test_manifest_generation_and_promotion_refusal(tmp_path):
    (tmp_path / "daily_prices.json").write_text("{}", encoding="utf-8")
    (tmp_path / "eps_diluted_concept.json").write_text("{}", encoding="utf-8")
    build_manifest("GOOGL", "0001652044", tmp_path, 6)
    assert (tmp_path / "manifest.json").exists()
    with pytest.raises(BuilderValidationError):
        assert_promotion_ready(tmp_path)
