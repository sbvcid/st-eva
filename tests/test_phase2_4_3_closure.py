from __future__ import annotations
import os
import sys
import types
from pathlib import Path
import pytest

sys.path.insert(0, ".")
from st_eva_runner import run_st_eva, _resolve_target_identity, _cli_eps_xbrl_documents
from eps_anchor_evidence import (
    eps_fact_records_from_xbrl_document,
    SHARE_CLASS_SCOPE_CONSOLIDATED,
    SHARE_CLASS_SCOPE_CLASS_A,
    SHARE_CLASS_SCOPE_CLASS_B,
    SHARE_CLASS_SCOPE_CLASS_C,
    ANCHOR_SEC_ANNUAL,
    ANCHOR_SEC_TTM_FOUR_QUARTERS,
    ANCHOR_FISCAL_YEAR,
    ANCHOR_TTM,
    NATURE_DIRECT_FILING,
    NATURE_DERIVED,
)
from sec_xbrl_facts import parse_xbrl_document


def _write_fixture_4scopes(tmp_path: Path) -> str:
    payload = b"""<?xml version="1.0"?>
<html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL" xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:us-gaap="http://fasb.org/us-gaap/2026">
<body>
<xbrli:context id="c-1"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0001652044</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:context id="c-a"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0001652044</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period><xbrli:segment><xbrldi:explicitMember xmlns:xbrldi="http://xbrl.org/2006/xbrldi" dimension="us-gaap:StatementClassOfStockAxis">us-gaap:CommonClassAMember</xbrldi:explicitMember></xbrli:segment></xbrli:context>
<xbrli:context id="c-b"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0001652044</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period><xbrli:segment><xbrldi:explicitMember xmlns:xbrldi="http://xbrl.org/2006/xbrldi" dimension="us-gaap:StatementClassOfStockAxis">us-gaap:CommonClassBMember</xbrldi:explicitMember></xbrli:segment></xbrli:context>
<xbrli:context id="c-c"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0001652044</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period><xbrli:segment><xbrldi:explicitMember xmlns:xbrldi="http://xbrl.org/2006/xbrldi" dimension="us-gaap:StatementClassOfStockAxis">us-gaap:CommonClassCMember</xbrldi:explicitMember></xbrli:segment></xbrli:context>
<xbrli:unit id="u"><xbrli:divide><xbrli:unitNumerator><xbrli:measure>USD</xbrli:measure></xbrli:unitNumerator><xbrli:unitDenominator><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unitDenominator></xbrli:divide></xbrli:unit>
<ix:nonFraction name="us-gaap:EarningsPerShareDiluted" contextRef="c-1" unitRef="u" decimals="2">10.81</ix:nonFraction>
<ix:nonFraction name="us-gaap:EarningsPerShareDiluted" contextRef="c-a" unitRef="u" decimals="2">10.82</ix:nonFraction>
<ix:nonFraction name="us-gaap:EarningsPerShareDiluted" contextRef="c-b" unitRef="u" decimals="2">10.83</ix:nonFraction>
<ix:nonFraction name="us-gaap:EarningsPerShareDiluted" contextRef="c-c" unitRef="u" decimals="2">10.84</ix:nonFraction>
</body></html>"""
    path = tmp_path / "googl_xbrl_4scopes.htm"
    path.write_bytes(payload)
    return str(path)


def _write_fixture_with_rejections(tmp_path: Path) -> str:
    payload = b"""<?xml version="1.0"?>
<html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL" xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:us-gaap="http://fasb.org/us-gaap/2026">
<body>
<xbrli:context id="c-1"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0001652044</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:unit id="u"><xbrli:divide><xbrli:unitNumerator><xbrli:measure>USD</xbrli:measure></xbrli:unitNumerator><xbrli:unitDenominator><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unitDenominator></xbrli:divide></xbrli:unit>
<ix:nonFraction name="us-gaap:EarningsPerShareDiluted" contextRef="c-1" unitRef="u" decimals="2">10.81</ix:nonFraction>
<ix:nonFraction name="us-gaap:EarningsPerShareDiluted" contextRef="missing-ctx" unitRef="u" decimals="2">99.99</ix:nonFraction>
</body></html>"""
    path = tmp_path / "googl_with_rejections.htm"
    path.write_bytes(payload)
    return str(path)


def _base_docs(path: str, **overrides) -> list[dict]:
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


def test_form_and_period_compatibility(tmp_path):
    path = _write_fixture_4scopes(tmp_path)

    # Valid combinations
    for form, fp in [("10-K", "FY"), ("10-K/A", "FY"), ("10-Q", "Q1"), ("10-Q", "Q2"), ("10-Q", "Q3"), ("10-Q/A", "Q1")]:
        docs = _base_docs(path, form=form, fiscal_period=fp)
        res = run_st_eva("GOOGL", mode="regression", reference_multiple=25.0, eps_xbrl_documents=docs, save_snapshot=False)
        doc_res = res["reverse_requirements"]["eps_xbrl_acquisition"]["document_results"][0]
        assert doc_res["final_status"] == "ACCEPTED", f"Expected ACCEPTED for {form} with {fp}"

    # Incompatible combinations: 10-K with Q1, 10-Q with FY, 10-Q with Q4
    for form, fp in [("10-K", "Q1"), ("10-K/A", "Q2"), ("10-Q", "FY"), ("10-Q/A", "FY"), ("10-Q", "Q4")]:
        docs = _base_docs(path, form=form, fiscal_period=fp)
        res = run_st_eva("GOOGL", mode="regression", reference_multiple=25.0, eps_xbrl_documents=docs, save_snapshot=False)
        doc_res = res["reverse_requirements"]["eps_xbrl_acquisition"]["document_results"][0]
        assert doc_res["final_status"] == "METADATA_REJECTED", f"Expected METADATA_REJECTED for {form} with {fp}"
        rejection_codes = [r["reason_code"] for r in doc_res["rejections"]]
        assert "FISCAL_PERIOD_INCOMPATIBLE" in rejection_codes


def test_cli_missing_form(tmp_path):
    path = _write_fixture_4scopes(tmp_path)
    # Simulate CLI args without eps_xbrl_form
    args = types.SimpleNamespace(
        eps_xbrl_manifest=None,
        eps_xbrl_document=[path],
        eps_xbrl_accession="0001652044-26-000018",
        eps_xbrl_form=None,
        eps_xbrl_filed="2026-02-04",
        eps_xbrl_fiscal_year=2025,
        eps_xbrl_fiscal_period="FY",
        eps_xbrl_acceptance_datetime="2026-02-04T21:15:00Z",
        eps_xbrl_assurance_status="AUDITED",
        eps_xbrl_expected_cik="0001652044",
    )
    docs = _cli_eps_xbrl_documents(args)
    assert docs is not None
    assert docs[0]["form"] is None, "CLI document builder must not default form to 10-K"

    res = run_st_eva("GOOGL", mode="regression", reference_multiple=25.0, eps_xbrl_documents=docs, save_snapshot=False)
    doc_res = res["reverse_requirements"]["eps_xbrl_acquisition"]["document_results"][0]
    assert doc_res["final_status"] == "METADATA_REJECTED"
    rejection_codes = [r["reason_code"] for r in doc_res["rejections"]]
    assert "FORM_MISSING" in rejection_codes


def test_helper_direct_call_missing_form(tmp_path):
    path = _write_fixture_4scopes(tmp_path)
    with open(path, "rb") as f:
        doc = parse_xbrl_document(f.read())
    rejs = []
    # Call directly without form argument (form omitted completely)
    recs = eps_fact_records_from_xbrl_document(
        doc,
        accession="0001652044-26-000018",
        filed="2026-02-04",
        acceptance_datetime="2026-02-04T21:15:00Z",
        fiscal_year=2025,
        fiscal_period="FY",
        expected_cik="0001652044",
        rejections=rejs,
    )
    assert recs == []
    assert any(r["reason_code"] == "FORM_MISSING" for r in rejs)


def test_identity_sources(monkeypatch):
    import st_eva_runner

    # 1. SEC_TICKER_MAP (mock SECProvider.ticker_map with fixed GOOGL entry)
    class MockSECProvider:
        def ticker_map(self):
            return {"GOOGL": {"cik": 1652044, "ticker": "GOOGL", "title": "Alphabet Inc."}}

    monkeypatch.setattr("sec_provider.SECProvider", MockSECProvider, raising=False)
    id1 = _resolve_target_identity("GOOGL", None)
    assert id1["identity_source"] == "SEC_TICKER_MAP"
    assert id1["verification_status"] == "SEC_VERIFIED"
    assert id1["canonical_cik"] == "0001652044"

    # 2. STATIC_MAPPING (when SECProvider fails, uses static mapping fallback)
    class FailingSECProvider:
        def ticker_map(self):
            raise RuntimeError("network unavailable")

    monkeypatch.setattr("sec_provider.SECProvider", FailingSECProvider, raising=False)
    id2 = _resolve_target_identity("GOOGL", None)
    assert id2["identity_source"] == "STATIC_MAPPING"
    assert id2["verification_status"] == "STATIC_FALLBACK"
    assert id2["canonical_cik"] == "0001652044"

    # 3. USER_SUPPLIED (when SECProvider fails and static mapping empty)
    monkeypatch.setattr(st_eva_runner, "_TARGET_CIK_BY_TICKER", {})
    id3 = _resolve_target_identity("UNKNOWNCO", "0000123456")
    assert id3["identity_source"] == "USER_SUPPLIED"
    assert id3["verification_status"] == "USER_SUPPLIED"
    assert id3["canonical_cik"] == "0000123456"

    # Explicit CIK format validation: cannot treat string with non-digits as valid CIK
    id_invalid = _resolve_target_identity("UNKNOWNCO", "0000123456x")
    assert id_invalid["canonical_cik"] is None
    assert id_invalid["identity_source"] is None
    assert id_invalid["conflict"] is True


def test_identity_conflict_stops_promotion(tmp_path):
    path = _write_fixture_4scopes(tmp_path)
    docs = _base_docs(path)
    # Explicit CIK conflicts with GOOGL canonical CIK (0001652044)
    res = run_st_eva("GOOGL", mode="regression", reference_multiple=25.0, eps_xbrl_documents=docs, eps_xbrl_expected_cik="0000320193", save_snapshot=False)
    acq = res["reverse_requirements"]["eps_xbrl_acquisition"]
    assert acq["identity_conflict"] is True
    doc_res = acq["document_results"][0]
    assert doc_res["final_status"] == "IDENTITY_REJECTED"
    assert doc_res["record_count"] == 0
    rejection_codes = [r["reason_code"] for r in doc_res["rejections"]]
    assert "IDENTITY_CONFLICT" in rejection_codes
    # Verify no records promoted into candidates
    catalogue = res["reverse_requirements"].get("eps_anchor_catalogue") or {}
    candidates = {c["anchor_id"]: c for c in catalogue.get("candidates", [])}
    annual = candidates.get(ANCHOR_SEC_ANNUAL)
    if annual is not None:
        assert not annual["available"]


def test_manifest_cik_validation(tmp_path):
    path = _write_fixture_4scopes(tmp_path)

    # 1. Non-digits
    docs = _base_docs(path, expected_cik="invalid_abc")
    res = run_st_eva("GOOGL", mode="regression", reference_multiple=25.0, eps_xbrl_documents=docs, save_snapshot=False)
    doc_res = res["reverse_requirements"]["eps_xbrl_acquisition"]["document_results"][0]
    assert doc_res["final_status"] == "IDENTITY_REJECTED"
    assert any(r["reason_code"] == "MANIFEST_CIK_INVALID" for r in doc_res["rejections"])

    # 2. Too long / wrong format
    docs = _base_docs(path, expected_cik="00016520449999")
    res = run_st_eva("GOOGL", mode="regression", reference_multiple=25.0, eps_xbrl_documents=docs, save_snapshot=False)
    doc_res = res["reverse_requirements"]["eps_xbrl_acquisition"]["document_results"][0]
    assert doc_res["final_status"] == "IDENTITY_REJECTED"
    assert any(r["reason_code"] == "MANIFEST_CIK_INVALID" for r in doc_res["rejections"])

    # 3. Empty string
    docs = _base_docs(path, expected_cik="")
    res = run_st_eva("GOOGL", mode="regression", reference_multiple=25.0, eps_xbrl_documents=docs, save_snapshot=False)
    doc_res = res["reverse_requirements"]["eps_xbrl_acquisition"]["document_results"][0]
    assert doc_res["final_status"] == "IDENTITY_REJECTED"
    assert any(r["reason_code"] == "MANIFEST_CIK_INVALID" for r in doc_res["rejections"])

    # 4. Mismatch
    docs = _base_docs(path, expected_cik="0000320193")
    res = run_st_eva("GOOGL", mode="regression", reference_multiple=25.0, eps_xbrl_documents=docs, save_snapshot=False)
    doc_res = res["reverse_requirements"]["eps_xbrl_acquisition"]["document_results"][0]
    assert doc_res["final_status"] == "IDENTITY_REJECTED"
    assert any(r["reason_code"] == "MANIFEST_CIK_MISMATCH" for r in doc_res["rejections"])


def test_date_and_point_in_time_strictness(tmp_path):
    path = _write_fixture_4scopes(tmp_path)

    # 1. Compact date (20260204)
    docs = _base_docs(path, filed="20260204", acceptance_datetime=None)
    res = run_st_eva("GOOGL", mode="regression", reference_multiple=25.0, eps_xbrl_documents=docs, save_snapshot=False)
    doc_res = res["reverse_requirements"]["eps_xbrl_acquisition"]["document_results"][0]
    assert doc_res["final_status"] == "METADATA_REJECTED"
    assert any(r["reason_code"] == "POINT_IN_TIME_UNPARSEABLE" for r in doc_res["rejections"])

    # 2. Week date (2026-W05-3)
    docs = _base_docs(path, filed="2026-W05-3", acceptance_datetime=None)
    res = run_st_eva("GOOGL", mode="regression", reference_multiple=25.0, eps_xbrl_documents=docs, save_snapshot=False)
    doc_res = res["reverse_requirements"]["eps_xbrl_acquisition"]["document_results"][0]
    assert doc_res["final_status"] == "METADATA_REJECTED"
    assert any(r["reason_code"] == "POINT_IN_TIME_UNPARSEABLE" for r in doc_res["rejections"])

    # 3. Invalid calendar date (2026-02-31)
    docs = _base_docs(path, filed="2026-02-31", acceptance_datetime=None)
    res = run_st_eva("GOOGL", mode="regression", reference_multiple=25.0, eps_xbrl_documents=docs, save_snapshot=False)
    doc_res = res["reverse_requirements"]["eps_xbrl_acquisition"]["document_results"][0]
    assert doc_res["final_status"] == "METADATA_REJECTED"
    assert any(r["reason_code"] == "POINT_IN_TIME_UNPARSEABLE" for r in doc_res["rejections"])

    # 4. Timezone-naive datetime (2026-02-04T21:15:00)
    docs = _base_docs(path, acceptance_datetime="2026-02-04T21:15:00", filed=None)
    res = run_st_eva("GOOGL", mode="regression", reference_multiple=25.0, eps_xbrl_documents=docs, save_snapshot=False)
    doc_res = res["reverse_requirements"]["eps_xbrl_acquisition"]["document_results"][0]
    assert doc_res["final_status"] == "METADATA_REJECTED"
    assert any(r["reason_code"] == "POINT_IN_TIME_UNPARSEABLE" for r in doc_res["rejections"])

    # 5. Valid filed date does NOT mask invalid acceptance datetime
    docs = _base_docs(path, filed="2026-02-04", acceptance_datetime="2026-02-04T21:15:00")
    res = run_st_eva("GOOGL", mode="regression", reference_multiple=25.0, eps_xbrl_documents=docs, save_snapshot=False)
    doc_res = res["reverse_requirements"]["eps_xbrl_acquisition"]["document_results"][0]
    assert doc_res["final_status"] == "METADATA_REJECTED"
    assert any(r["reason_code"] == "POINT_IN_TIME_UNPARSEABLE" for r in doc_res["rejections"])

    # 6. Valid acceptance datetime does NOT mask invalid filed date
    docs = _base_docs(path, filed="2026-02-04garbage", acceptance_datetime="2026-02-04T21:15:00Z")
    res = run_st_eva("GOOGL", mode="regression", reference_multiple=25.0, eps_xbrl_documents=docs, save_snapshot=False)
    doc_res = res["reverse_requirements"]["eps_xbrl_acquisition"]["document_results"][0]
    assert doc_res["final_status"] == "METADATA_REJECTED"
    assert any(r["reason_code"] == "POINT_IN_TIME_UNPARSEABLE" for r in doc_res["rejections"])


def test_multiple_documents_independent_statuses(tmp_path):
    path_valid = _write_fixture_4scopes(tmp_path)
    path_rejections = _write_fixture_with_rejections(tmp_path)

    unparseable_path = tmp_path / "bad.xml"
    unparseable_path.write_bytes(b"not valid xml at all <<>>")

    empty_facts_path = tmp_path / "empty_facts.htm"
    empty_facts_path.write_bytes(b'<html><body><p>No XBRL</p></body></html>')

    doc_valid = _base_docs(path_valid)[0]
    doc_with_rej = _base_docs(path_rejections)[0]
    doc_no_facts = _base_docs(str(empty_facts_path))[0]
    doc_meta_rej = _base_docs(path_valid, form="10-K", fiscal_period="Q1")[0]
    doc_ident_rej = _base_docs(path_valid, expected_cik="0000320193")[0]
    doc_unreadable = _base_docs(str(tmp_path / "nonexistent.htm"))[0]
    doc_unparseable = _base_docs(str(unparseable_path))[0]

    all_docs = [
        doc_valid,
        doc_with_rej,
        doc_no_facts,
        doc_meta_rej,
        doc_ident_rej,
        doc_unreadable,
        doc_unparseable,
    ]

    res = run_st_eva("GOOGL", mode="regression", reference_multiple=25.0, eps_xbrl_documents=all_docs, save_snapshot=False)
    acq = res["reverse_requirements"]["eps_xbrl_acquisition"]
    assert acq["documents"] == 7
    doc_results = acq["document_results"]
    assert len(doc_results) == 7

    # Verify all seven statuses
    statuses = [d["final_status"] for d in doc_results]
    assert statuses[0] == "ACCEPTED"
    assert statuses[1] == "ACCEPTED_WITH_REJECTIONS"
    assert statuses[2] == "NO_QUALIFYING_EPS_FACTS"
    assert statuses[3] == "METADATA_REJECTED"
    assert statuses[4] == "IDENTITY_REJECTED"
    assert statuses[5] == "UNREADABLE"
    assert statuses[6] == "UNPARSEABLE"

    # Verify record counts
    assert doc_results[0]["record_count"] == 4
    assert doc_results[1]["record_count"] == 1
    assert doc_results[2]["record_count"] == 0
    assert doc_results[3]["record_count"] == 0
    assert doc_results[4]["record_count"] == 0
    assert doc_results[5]["record_count"] == 0
    assert doc_results[6]["record_count"] == 0

    # Verify rejections consistency with global errors
    global_errors = acq["errors"]
    for d in doc_results:
        for r in d["rejections"]:
            assert r in global_errors


def test_googl_four_scopes_provenance(tmp_path):
    path = _write_fixture_4scopes(tmp_path)
    docs = _base_docs(path)
    res = run_st_eva("GOOGL", mode="regression", reference_multiple=25.0, prefer_eps_anchor="SEC_ANNUAL_DILUTED_EPS", eps_xbrl_documents=docs, save_snapshot=False)
    acq = res["reverse_requirements"]["eps_xbrl_acquisition"]
    assert acq["canonical_cik"] == "0001652044"
    assert acq["identity_source"] in ("SEC_TICKER_MAP", "STATIC_MAPPING")
    assert acq["verification_status"] in ("SEC_VERIFIED", "STATIC_FALLBACK")

    doc_res = acq["document_results"][0]
    assert doc_res["final_status"] == "ACCEPTED"
    assert doc_res["record_count"] == 4
    assert doc_res["accession"] == "0001652044-26-000018"
    assert doc_res["canonical_cik"] == "0001652044"

    catalogue = res["reverse_requirements"].get("eps_anchor_catalogue") or {}
    candidates = {c["anchor_id"]: c for c in catalogue.get("candidates", [])}

    annual = candidates.get(ANCHOR_SEC_ANNUAL)
    assert annual is not None and annual["available"]
    assert annual["value"] == 10.81
    assert annual["share_class_scope"] == SHARE_CLASS_SCOPE_CONSOLIDATED
    assert annual["sec_fact"]["taxonomy"] == "http://fasb.org/us-gaap/2026"
    assert annual["sec_fact"]["concept_local_name"] == "EarningsPerShareDiluted"
    assert annual["sec_fact"]["unit"] == "USD/shares"
    assert annual["sec_fact"]["filed_date"] == "2026-02-04"
    assert annual["sec_fact"]["acceptance_datetime"] == "2026-02-04T21:15:00+00:00"

    cla = candidates.get("SEC_ANNUAL_DILUTED_EPS_CLASS_A")
    assert cla is not None and cla["available"]
    assert cla["value"] == 10.82
    assert cla["share_class_scope"] == SHARE_CLASS_SCOPE_CLASS_A

    clb = candidates.get("SEC_ANNUAL_DILUTED_EPS_CLASS_B")
    assert clb is not None and clb["available"]
    assert clb["value"] == 10.83
    assert clb["share_class_scope"] == SHARE_CLASS_SCOPE_CLASS_B

    clc = candidates.get("SEC_ANNUAL_DILUTED_EPS_CLASS_C")
    assert clc is not None and clc["available"]
    assert clc["value"] == 10.84
    assert clc["share_class_scope"] == SHARE_CLASS_SCOPE_CLASS_C


def test_googl_annual_vs_ttm_evidence_identity(tmp_path):
    path = _write_fixture_4scopes(tmp_path)
    docs = _base_docs(path)
    res = run_st_eva("GOOGL", mode="regression", reference_multiple=25.0, prefer_eps_anchor="SEC_ANNUAL_DILUTED_EPS", eps_xbrl_documents=docs, save_snapshot=False)
    catalogue = res["reverse_requirements"].get("eps_anchor_catalogue") or {}
    candidates = {c["anchor_id"]: c for c in catalogue.get("candidates", [])}

    annual = candidates.get(ANCHOR_SEC_ANNUAL)
    assert annual is not None and annual["available"]
    assert annual["basis"] == ANCHOR_FISCAL_YEAR
    assert annual["nature"] == NATURE_DIRECT_FILING

    ttm = candidates.get(ANCHOR_SEC_TTM_FOUR_QUARTERS)
    assert ttm is not None
    assert ttm["nature"] == NATURE_DERIVED
    assert ttm["anchor_id"] == ANCHOR_SEC_TTM_FOUR_QUARTERS
    # TTM must NOT be fulfilled by FY figure; with only one annual fact, TTM is unavailable
    assert not ttm["available"]
    assert ttm.get("value") != annual.get("value") or ttm.get("value") is None


def test_no_xbrl_no_extra_network(monkeypatch):
    calls = {"n": 0}
    orig = __import__("st_eva_runner")._resolve_target_identity
    def wrapped(*a, **k):
        calls["n"] += 1
        return orig(*a, **k)
    monkeypatch.setattr("st_eva_runner._resolve_target_identity", wrapped)
    res = run_st_eva("AAPL", mode="regression", reference_multiple=25.0, save_snapshot=False)
    assert res is not None
    assert calls["n"] == 0
