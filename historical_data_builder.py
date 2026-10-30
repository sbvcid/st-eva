"""Generic, reusable acquisition helpers for ST-EVA production historical datasets.

This module automates only the parts of the production historical dataset that
can be obtained directly from authoritative public sources with full
provenance. It never synthesises EPS, prices, acceptance times or share
counts, and it never fills a missing value with zero or an estimate.

Automated (full provenance, deterministic):
  - daily_prices.json        Yahoo Finance chart response (as-traded, split-aware)
  - eps_diluted_concept.json SEC company-concept response for
                            us-gaap:EarningsPerShareDiluted

Semi-automated (requires manual verification before promotion):
  - filing_acceptance_evidence.json  submissions API gives filed dates; exact
                            ET acceptance timestamps require the SGML header
                            of each filing and must be checked by a human.

Manual (not automated here, must be sourced from the filing text):
  - q4_evidence_records.json 8-K Item 2.02 EX-99.1 furnished Q4 GAAP EPS facts
  - manifest.json            hashes and promotion metadata
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range={range}&interval=1d&events=div,splits"
SEC_CONCEPT_URL = "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/EarningsPerShareDiluted.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"

USER_AGENT = "ST-EVA/2.2 historical-data-builder"


def fetch_daily_prices(ticker: str, years: int = 6) -> Dict[str, Any]:
    """Return the raw Yahoo chart response for ``ticker`` over ``years`` years."""
    rng = "%dy" % years if years < 10 else "max"
    url = YAHOO_CHART_URL.format(ticker=ticker.upper(), range=rng)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_eps_concept(cik: str) -> Dict[str, Any]:
    """Return the SEC company-concept response for diluted EPS."""
    url = SEC_CONCEPT_URL.format(cik=cik.lstrip("0").zfill(10))
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_submissions(cik: str) -> Dict[str, Any]:
    """Return the SEC submissions document for ``cik``."""
    url = SEC_SUBMISSIONS_URL.format(cik=cik.lstrip("0").zfill(10))
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def build_acceptance_index_from_submissions(submissions: Dict[str, Any]) -> list:
    """Build a lower-fidelity acceptance list from the submissions API.

    Each entry carries the filed date and form. The exact ET acceptance time
    is intentionally left as None: it must be filled from the SGML header
    before the evidence is promoted to a production dataset.
    """
    recent = (submissions.get("filings") or {}).get("recent") or {}
    out = []
    for accn, form, filed, period in zip(
        recent.get("accessionNumber", []),
        recent.get("form", []),
        recent.get("filingDate", []),
        recent.get("reportDate", []),
    ):
        if form not in ("10-K", "10-Q", "8-K"):
            continue
        out.append({
            "accession": accn,
            "form": form,
            "filed_date_submissions": filed,
            "period_end": period,
            "acceptance_datetime_header_et": None,
            "acceptance_source": "SUBMISSIONS_API_ONLY_UNVERIFIED",
        })
    return out


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def generate_base_inputs(ticker: str, cik: str, out_dir: Path, years: int = 6) -> Dict[str, Path]:
    """Generate the automatable base inputs into ``out_dir``.

    Returns the paths written. Does not create a production dataset and does
    not register the ticker in any ISSUER_CONFIGS.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    prices = fetch_daily_prices(ticker, years=years)
    concept = fetch_eps_concept(cik)
    subs = fetch_submissions(cik)
    acceptance = build_acceptance_index_from_submissions(subs)

    paths = {
        "daily_prices.json": out_dir / "daily_prices.json",
        "eps_diluted_concept.json": out_dir / "eps_diluted_concept.json",
        "filing_acceptance_evidence.submissions.json": out_dir / "filing_acceptance_evidence.submissions.json",
    }
    write_json(paths["daily_prices.json"], prices)
    write_json(paths["eps_diluted_concept.json"], concept)
    write_json(paths["filing_acceptance_evidence.submissions.json"], acceptance)
    return paths

