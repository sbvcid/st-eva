from __future__ import annotations
import sys
sys.path.insert(0, ".")
from sec_xbrl_facts import parse_xbrl_document
from eps_anchor_evidence import eps_fact_records_from_xbrl_document

GOOGL_FIXTURE = b'''<?xml version="1.0"?>
<html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL" xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:us-gaap="http://fasb.org/us-gaap/2026">
<body>
<xbrli:context id="c-1"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0001652044</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:context id="c-2"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0001652044</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period><xbrli:segment><xbrldi:explicitMember xmlns:xbrldi="http://xbrl.org/2006/xbrldi" dimension="us-gaap:StatementClassOfStockAxis">us-gaap:CommonClassAMember</xbrldi:explicitMember></xbrli:segment></xbrli:context>
<xbrli:unit id="u"><xbrli:divide><xbrli:unitNumerator><xbrli:measure>USD</xbrli:measure></xbrli:unitNumerator><xbrli:unitDenominator><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unitDenominator></xbrli:divide></xbrli:unit>
<ix:nonFraction name="us-gaap:EarningsPerShareDiluted" contextRef="c-1" unitRef="u" decimals="2">10.81</ix:nonFraction>
<ix:nonFraction name="us-gaap:EarningsPerShareDiluted" contextRef="c-2" unitRef="u" decimals="2">10.82</ix:nonFraction>
</body></html>'''

def _load(payload=GOOGL_FIXTURE):
    return parse_xbrl_document(payload)

def test_identity_match():
    doc = _load()
    rejs = []
    recs = eps_fact_records_from_xbrl_document(doc, accession="0001652044-26-000018", form="10-K", filed="2026-02-04", fiscal_year=2025, fiscal_period="FY", expected_cik="0001652044", rejections=rejs)
    assert len(recs) == 2
    assert rejs == []

def test_identity_mismatch():
    doc = _load()
    rejs = []
    recs = eps_fact_records_from_xbrl_document(doc, accession="0001652044-26-000018", form="10-K", filed="2026-02-04", fiscal_year=2025, fiscal_period="FY", expected_cik="0000320193", rejections=rejs)
    assert recs == []
    assert rejs and rejs[0]["reason_code"] in ("ISSUER_IDENTITY_MISMATCH", "ACCESSION_CIK_MISMATCH")

def test_missing_identifier():
    payload = GOOGL_FIXTURE.replace(b"<xbrli:identifier scheme=\"http://www.sec.gov/CIK\">0001652044</xbrli:identifier>", b"")
    doc = _load(payload)
    rejs = []
    recs = eps_fact_records_from_xbrl_document(doc, accession="0001652044-26-000018", form="10-K", filed="2026-02-04", fiscal_year=2025, fiscal_period="FY", expected_cik="0001652044", rejections=rejs)
    assert recs == []
    # parser drops contexts without entity identifier, so no qualifying facts remain
    assert any(r["reason_code"] == "NO_QUALIFYING_EPS_FACTS" for r in rejs) or len(recs) == 0
