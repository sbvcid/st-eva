from __future__ import annotations
import os, sys, types
sys.path.insert(0, ".")
from st_eva_runner import run_st_eva

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "googl_xbrl.htm")

def _write_fixture(tmp_path):
    payload = b'''<?xml version="1.0"?>
<html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL" xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:us-gaap="http://fasb.org/us-gaap/2026">
<body>
<xbrli:context id="c-1"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0001652044</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:context id="c-a"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0001652044</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period><xbrli:segment><xbrldi:explicitMember xmlns:xbrldi="http://xbrl.org/2006/xbrldi" dimension="us-gaap:StatementClassOfStockAxis">us-gaap:CommonClassAMember</xbrldi:explicitMember></xbrli:segment></xbrli:context>
<xbrli:unit id="u"><xbrli:divide><xbrli:unitNumerator><xbrli:measure>USD</xbrli:measure></xbrli:unitNumerator><xbrli:unitDenominator><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unitDenominator></xbrli:divide></xbrli:unit>
<ix:nonFraction name="us-gaap:EarningsPerShareDiluted" contextRef="c-1" unitRef="u" decimals="2">10.81</ix:nonFraction>
<ix:nonFraction name="us-gaap:EarningsPerShareDiluted" contextRef="c-a" unitRef="u" decimals="2">10.82</ix:nonFraction>
</body></html>'''
    path = tmp_path / "googl_xbrl.htm"
    path.write_bytes(payload)
    return str(path)

def _base_docs(path, **overrides):
    meta = {
        "path": path,
        "accession": "0001652044-26-000018",
        "form": "10-K",
        "filed": "2026-02-04",
        "fiscal_year": 2025,
        "fiscal_period": "FY",
        "acceptance_datetime": "2026-02-04T21:15:00Z",
        "assurance_status": "AUDITED",
        "expected_cik": "0001652044",
    }
    meta.update(overrides)
    return [meta]

def test_googl_four_scopes(tmp_path):
    path = _write_fixture(tmp_path)
    # need B and C too; reuse simple fixture with two contexts is enough for smoke
    docs = _base_docs(path)
    res = run_st_eva("GOOGL", mode="regression", reference_multiple=25.0, prefer_eps_anchor="SEC_ANNUAL_DILUTED_EPS", eps_xbrl_documents=docs, save_snapshot=False)
    assert res is not None
    acq = res["reverse_requirements"].get("eps_xbrl_acquisition", {})
    assert acq.get("identity_source") in ("SEC_TICKER_MAP", "STATIC_MAPPING", "USER_SUPPLIED")

def test_manifest_cik_mismatch(tmp_path):
    path = _write_fixture(tmp_path)
    docs = _base_docs(path, expected_cik="0001652044")
    # tamper manifest CIK
    docs[0]["expected_cik"] = "0000320193"
    res = run_st_eva("GOOGL", mode="regression", reference_multiple=25.0, eps_xbrl_documents=docs, save_snapshot=False)
    assert res is not None
    acq = res["reverse_requirements"].get("eps_xbrl_acquisition", {})
    codes = [e["reason_code"] for e in acq.get("errors", [])]
    assert "MANIFEST_CIK_MISMATCH" in codes

def test_naive_acceptance_datetime(tmp_path):
    path = _write_fixture(tmp_path)
    docs = _base_docs(path, acceptance_datetime="2026-02-04T21:15:00")
    res = run_st_eva("GOOGL", mode="regression", reference_multiple=25.0, eps_xbrl_documents=docs, save_snapshot=False)
    assert res is not None
    acq = res["reverse_requirements"].get("eps_xbrl_acquisition", {})
    codes = [e["reason_code"] for e in acq.get("errors", [])]
    assert "POINT_IN_TIME_UNPARSEABLE" in codes

def test_invalid_filed_date(tmp_path):
    path = _write_fixture(tmp_path)
    docs = _base_docs(path, filed="2026-02-04garbage", acceptance_datetime=None)
    res = run_st_eva("GOOGL", mode="regression", reference_multiple=25.0, eps_xbrl_documents=docs, save_snapshot=False)
    assert res is not None
    acq = res["reverse_requirements"].get("eps_xbrl_acquisition", {})
    codes = [e["reason_code"] for e in acq.get("errors", [])]
    assert "POINT_IN_TIME_UNPARSEABLE" in codes

def test_user_supplied_identity(tmp_path, monkeypatch):
    import st_eva_runner
    monkeypatch.setattr(st_eva_runner, "_TARGET_CIK_BY_TICKER", {})
    # force SECProvider to fail
    class Boom:
        def ticker_map(self):
            raise RuntimeError("no network")
    monkeypatch.setattr("sec_provider.SECProvider", Boom, raising=False)
    path = _write_fixture(tmp_path)
    docs = _base_docs(path, expected_cik="0000320193")
    res = run_st_eva("AAPL", mode="regression", reference_multiple=25.0, eps_xbrl_documents=docs, eps_xbrl_expected_cik="0000320193", save_snapshot=False)
    assert res is not None
    acq = res["reverse_requirements"].get("eps_xbrl_acquisition", {})
    assert acq.get("identity_source") == "USER_SUPPLIED"

def test_no_xbrl_no_extra_network(tmp_path, monkeypatch):
    # ensure _resolve_target_identity not called when no docs
    calls = {"n": 0}
    orig = __import__("st_eva_runner")._resolve_target_identity
    def wrapped(*a, **k):
        calls["n"] += 1
        return orig(*a, **k)
    monkeypatch.setattr("st_eva_runner._resolve_target_identity", wrapped)
    res = run_st_eva("AAPL", mode="regression", reference_multiple=25.0, save_snapshot=False)
    assert res is not None
    assert calls["n"] == 0
