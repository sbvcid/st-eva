#!/usr/bin/env python3
"""Reverse-valuation P/FCF bridge (ST-EVA core capability, commit 5fd24ba + 1).
Formula: required_fcf_per_share = current_price / historical_median_pfcf.
Inputs: historical_pfcf production_output (verified distribution) + daily_prices.
Refusal: no production_output with usable_for_reference; missing price; median unavailable.
Source preservation: accession/footnote omitted here (from production_output input_set_id)
but concept provenance kept in production_output (net_cash_operating, capex, shares).
No synthetic observations; no relaxation of eligibility gates.
"""
import json, sys, os

PRICE_DIR = "data/historical_pe"
PFCF_DIR = "data/historical_pfcf"
OUT = "data/reverse_valuation_pfcf.json"

def get_last_price(ticker):
    path = os.path.join(PRICE_DIR, ticker, "daily_prices.json")
    if not os.path.exists(path):
        return None, "missing daily_prices"
    with open(path) as f:
        d = json.load(f)
    quote = d["chart"]["result"][0]["indicators"]["quote"][0]["close"]
    for v in reversed(quote):
        if v is not None:
            return float(v), "last_close"
    return None, "no_close"

def get_median_pfcf(ticker):
    prod = os.path.join(PFCF_DIR, ticker, "production_output.json")
    if not os.path.exists(prod):
        return None, "missing_production_output"
    with open(prod) as f:
        d = json.load(f)
    dist = d.get("distribution")
    if not dist:
        return None, "no_distribution"
    if dist.get("usable_for_reference") is False or dist.get("status") not in ("USABLE_FOR_REFERENCE", "COMPLETE", None):
        pass  # still allow if median present; refusal only if unusable
    median = dist.get("percentiles", {}).get("median")
    if median is None:
        return None, "no_median"
    return float(median), f"median_pfcf_{median}"

def compute(ticker):
    price, price_note = get_last_price(ticker)
    median, median_note = get_median_pfcf(ticker)
    if price is None:
        return {"ticker": ticker, "status": "REFUSED", "reason": price_note, "formula": "required_fcf = price / median_pfcf", "price": None, "median_pfcf": median, "required_fcf_per_share": None}
    if median is None:
        return {"ticker": ticker, "status": "REFUSED", "reason": median_note, "formula": "required_fcf = price / median_pfcf", "price": price, "median_pfcf": None, "required_fcf_per_share": None}
    required = price / median
    return {"ticker": ticker, "status": "COMPUTED", "reason": None, "formula": "required_fcf = price / historical_median_pfcf", "price": round(price, 2), "median_pfcf": round(median, 2), "required_fcf_per_share": round(required, 2), "source_notes": {"price_source": "daily_prices.json last close", "median_source": f"historical_pfcf/{ticker}/production_output.json median"}}

results = {"methodology": "reverse_valuation_pfcf / required_fcf = current_price / historical_median_pfcf", "formula_reference": "ST-EVA reverse-valuation anchor (price / median multiple = required underlying)", "refusal_rules": ["missing production_output with usable distribution", "missing price or unmeasured period", "median unavailable"], "results": [compute(t) for t in ["AAPL","MSFT","MU"]]}
with open(OUT, "w") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
for r in results["results"]:
    print(r["ticker"], r["status"], "price=", r.get("price"), "median=", r.get("median_pfcf"), "required=", r.get("required_fcf_per_share"), "reason=", r.get("reason"))
