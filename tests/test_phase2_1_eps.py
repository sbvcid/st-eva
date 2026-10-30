from __future__ import annotations
import sys, types
sys.path.insert(0, ".")
from sec_xbrl_facts import parse_xbrl_document
from eps_anchor_evidence import (
    eps_fact_records_from_xbrl_document,
    build_eps_anchor_candidates,
    _supplier_candidate,
    SHARE_CLASS_SCOPE_UNKNOWN,
)

def _doc_and_recs(fiscal_period="FY"):
    payload = b'''<?xml version="1.0"?>
<html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL" xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:us-gaap="http://fasb.org/us-gaap/2026">
<body>
<xbrli:context id="c-1"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0001652044</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:context id="c-a"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0001652044</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period><xbrli:segment><xbrldi:explicitMember xmlns:xbrldi="http://xbrl.org/2006/xbrldi" dimension="us-gaap:StatementClassOfStockAxis">us-gaap:CommonClassAMember</xbrldi:explicitMember></xbrli:segment></xbrli:context>
<xbrli:context id="c-b"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0001652044</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period><xbrli:segment><xbrldi:explicitMember xmlns:xbrldi="http://xbrl.org/2006/xbrldi" dimension="us-gaap:StatementClassOfStockAxis">us-gaap:CommonClassBMember</xbrldi:explicitMember></xbrli:segment></xbrli:context>
<xbrli:context id="c-c"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0001652044</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period><xbrli:segment><xbrldi:explicitMember xmlns:xbrldi="http://xbrl.org/2006/xbrldi" dimension="us-gaap:StatementClassOfStockAxis">us-gaap:CapitalClassCMember</xbrldi:explicitMember></xbrli:segment></xbrli:context>
<xbrli:unit id="u"><xbrli:divide><xbrli:unitNumerator><xbrli:measure>USD</xbrli:measure></xbrli:unitNumerator><xbrli:unitDenominator><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unitDenominator></xbrli:divide></xbrli:unit>
<ix:nonFraction name="us-gaap:EarningsPerShareDiluted" contextRef="c-1" unitRef="u" decimals="2">10.81</ix:nonFraction>
<ix:nonFraction name="us-gaap:EarningsPerShareDiluted" contextRef="c-a" unitRef="u" decimals="2">10.82</ix:nonFraction>
<ix:nonFraction name="us-gaap:EarningsPerShareDiluted" contextRef="c-b" unitRef="u" decimals="2">10.81</ix:nonFraction>
<ix:nonFraction name="us-gaap:EarningsPerShareDiluted" contextRef="c-c" unitRef="u" decimals="2">10.80</ix:nonFraction>
</body></html>'''
    doc = parse_xbrl_document(payload)
    recs = eps_fact_records_from_xbrl_document(doc, accession="0001652044-26-000018", form="10-K", filed="2026-02-04", fiscal_year=2025, fiscal_period=fiscal_period, assurance_status="AUDITED")
    return recs

def test_googl_four_scopes():
    recs = _doc_and_recs()
    cat = build_eps_anchor_candidates(ticker="GOOGL", valuation_date="2026-03-01", currency="USD", records=recs)
    by = {c.anchor_id: c for c in cat.candidates if c.available}
    assert by["SEC_ANNUAL_DILUTED_EPS"].value == 10.81
    assert by["SEC_ANNUAL_DILUTED_EPS_CLASS_A"].value == 10.82
    assert by["SEC_ANNUAL_DILUTED_EPS_CLASS_B"].value == 10.81
    assert by["SEC_ANNUAL_DILUTED_EPS_CLASS_C"].value == 10.80

def test_missing_fiscal_period_rejects():
    recs = _doc_and_recs(fiscal_period=None)
    cat = build_eps_anchor_candidates(ticker="GOOGL", valuation_date="2026-03-01", currency="USD", records=recs)
    annuals = [c for c in cat.candidates if c.anchor_id.startswith("SEC_ANNUAL")]
    assert all(not c.available for c in annuals)

def test_supplier_scope_unknown():
    cand = _supplier_candidate(anchor_id="SUPPLIER_TRAILING_EPS", value=19.15, basis="TTM", months_covered=12.0, period_label="trailing", provider="Yahoo", source_field="trailingEps", source_url=None, source_observation_type=None, source_retrieved_at=None, currency="USD")
    assert cand.share_class_scope == SHARE_CLASS_SCOPE_UNKNOWN
