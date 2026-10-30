from __future__ import annotations
import sys, types
sys.path.insert(0, ".")
from eps_anchor_evidence import _records_from_run_observations, SHARE_CLASS_SCOPE_UNKNOWN

def _obs(unit="USD/shares", include_unit=True):
    raw_fact = {"tag": "EarningsPerShareDiluted", "unit": unit if include_unit else None, "value": 1.0, "start": "2025-01-01", "end": "2025-12-31", "accession": "a-1", "form": "10-K", "filed": "2026-01-01", "fy": 2025, "fp": "FY"}
    raw = {"sec_fact": raw_fact, "accession": "a-1", "form": "10-K", "filed": "2026-01-01", "reported_currency_unit": unit if include_unit else None}
    o = types.SimpleNamespace(metric="eps_diluted", raw=raw, period_end="2025-12-31", period_start="2025-01-01", value=1.0, available_at="2026-01-01T00:00:00Z", available_at_basis="ACCEPTANCE_DATETIME", source_url=None)
    return o

def test_unit_correct():
    recs = _records_from_run_observations([_obs("USD/shares")])
    assert len(recs) == 1

def test_unit_wrong():
    recs = _records_from_run_observations([_obs("USD")])
    assert len(recs) == 0

def test_unit_missing():
    recs = _records_from_run_observations([_obs(include_unit=False)])
    assert len(recs) == 0

def test_no_nameerror():
    recs = _records_from_run_observations([_obs("USD/shares")])
    assert recs[0].unit == "USD/shares"
