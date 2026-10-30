from __future__ import annotations
import sys, json, os, types
sys.path.insert(0, ".")
from sec_xbrl_facts import parse_xbrl_document
from eps_anchor_evidence import eps_fact_records_from_xbrl_document

FIXTURE = r"C:\Users\sbvci\AppData\Local\Temp\kilo\sec_xbrl_googl\goog-20251231.htm"

def _load():
    payload = open(FIXTURE, "rb").read()
    return parse_xbrl_document(payload)

def test_identity_match():
    doc = _load()
    rejs = []
    recs = eps_fact_records_from_xbrl_document(doc, accession="a", form="10-K", filed="2026-02-04", fiscal_year=2025, fiscal_period="FY", expected_cik="0001652044", rejections=rejs)
    assert len(recs) == 4
    assert rejs == []

def test_identity_mismatch():
    doc = _load()
    rejs = []
    recs = eps_fact_records_from_xbrl_document(doc, accession="a", form="10-K", filed="2026-02-04", fiscal_year=2025, fiscal_period="FY", expected_cik="0000320193", rejections=rejs)
    assert recs == []
    assert rejs and rejs[0]["reason_code"] == "ISSUER_IDENTITY_MISMATCH"

def test_missing_identifier():
    # parse a doc without identifier by removing from payload
    payload = open(FIXTURE, "rb").read().replace(b"<xbrli:identifier scheme=\"http://www.sec.gov/CIK\">0001652044</xbrli:identifier>", b"")
    doc = parse_xbrl_document(payload)
    rejs = []
    recs = eps_fact_records_from_xbrl_document(doc, accession="a", form="10-K", filed="2026-02-04", fiscal_year=2025, fiscal_period="FY", expected_cik="0001652044", rejections=rejs)
    assert recs == []
    # contexts without identifier are dropped by parser; no qualifying facts
    assert True
