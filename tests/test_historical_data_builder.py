import json
from unittest.mock import patch, MagicMock
from historical_data_builder import build_acceptance_index_from_submissions, fetch_daily_prices


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
    fake = {"chart": {"result": [{"meta": {"symbol": "GOOGL"}}]}}
    with patch("historical_data_builder.urllib.request.urlopen") as m:
        cm = MagicMock()
        cm.__enter__.return_value.read.return_value = json.dumps(fake).encode()
        m.return_value = cm
        res = fetch_daily_prices("GOOGL", years=3)
    assert res["chart"]["result"][0]["meta"]["symbol"] == "GOOGL"

