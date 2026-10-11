"""One-off packaging tool: promote verified MSFT POC research inputs into the
canonical tracked production layout at data/historical_pe/MSFT/.

Run from the repository root. Writes only into data/historical_pe/MSFT/.
It does not modify anything under research/.
"""
import hashlib
import json
import pathlib
import re
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "research/experiments/aapl-historical-pe-poc/contract/msft_validation/raw"
OUT = ROOT / "data/historical_pe/MSFT"
CIK_INT = "789019"
CIK = "0000789019"

# Must match historical_pe.ET so the stored offset reproduces the point-in-time
# cutoff exactly, including DST: filings accepted after 16:00 ET roll to the next
# trading day, and a hard-coded -04:00 would mis-date every winter (EST) filing.
ET = ZoneInfo("America/New_York")

OUT.mkdir(parents=True, exist_ok=True)


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def write_json(path: pathlib.Path, payload) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {path.relative_to(ROOT)} ({len(text)} bytes)")


# ---------------------------------------------------------------- prices
prices_raw = (RAW / "prices.json").read_bytes()
prices = json.loads(prices_raw.decode("utf-8"))
meta = prices["chart"]["result"][0]["meta"]
price_sha = sha256_bytes(prices_raw)
print(f"prices: {len(prices['chart']['result'][0]['timestamp'])} bars, sha={price_sha[:16]}...")

canonical_prices = {
    "chart": prices["chart"],
    "_st_eva_provenance": {
        "source": "Yahoo Finance chart API response",
        "source_url": (
            "https://query1.finance.yahoo.com/v8/finance/chart/MSFT"
            "?period1=1451865600&period2=1785196800&interval=1d"
        ),
        "symbol": meta.get("symbol"),
        "currency": meta.get("currency"),
        "exchange_timezone_name": meta.get("exchangeTimezoneName"),
        "granularity": meta.get("dataGranularity"),
        "content_sha256": price_sha,
        "accounting_basis": "as_traded",
        "note": (
            "Verbatim vendor payload retained so price evidence, trading-day "
            "calendar and split events are reproducible from a clean checkout."
        ),
    },
}
write_json(OUT / "daily_prices.json", canonical_prices)

# ------------------------------------------------- diluted EPS XBRL facts
eps_raw = (RAW / "eps_diluted.json").read_bytes()
eps = json.loads(eps_raw.decode("utf-8"))
eps_sha = sha256_bytes(eps_raw)
units = eps["units"]["USD/shares"]
print(f"eps: {len(units)} facts, sha={eps_sha[:16]}...")

canonical_eps = dict(eps)
canonical_eps["_st_eva_provenance"] = {
    "source": "SEC XBRL companyconcept API",
    "source_url": f"https://data.sec.gov/api/xbrl/companyconcept/CIK{CIK}/us-gaap/EarningsPerShareDiluted.json",
    "cik": eps.get("cik"),
    "taxonomy": eps.get("taxonomy"),
    "tag": eps.get("tag"),
    "content_sha256": eps_sha,
    "note": "Verbatim SEC payload; production derives content_sha256 from this file.",
}
write_json(OUT / "eps_diluted_concept.json", canonical_eps)

# ------------------------------------- filing acceptance / fiscal metadata
submissions = json.loads((RAW / "submissions.json").read_text(encoding="utf-8"))
recent = submissions["filings"]["recent"]

by_accession = {}
for accn, form, report_date, items in zip(
    recent.get("accessionNumber", []),
    recent.get("form", []),
    recent.get("reportDate", []),
    recent.get("items", []),
):
    by_accession[accn] = {"form": form, "report_date": report_date, "items": items or ""}

accept_re = re.compile(r"ACCEPTANCE-DATETIME&gt;(\d{14})")
filed_re = re.compile(r"FILED-AS-OF-DATE&gt;(\d{8})")
changed_re = re.compile(r"DATE-AS-OF-CHANGE&gt;(\d{8})")
period_re = re.compile(r"CONFORMED-PERIOD-OF-REPORT&gt;(\d{8})")
fye_re = re.compile(r"FISCAL-YEAR-END&gt;(\d{4})")

rows = []
unparsed = []
for header_file in sorted((RAW / "headers").glob("*.txt")):
    accession = header_file.stem
    if accession not in by_accession:
        continue
    text = header_file.read_text(encoding="utf-8", errors="replace")
    m = accept_re.search(text)
    if not m:
        unparsed.append(accession)
        continue
    raw_header = header_file.read_bytes()
    digest = sha256_bytes(raw_header)
    # Build the ISO timestamp through the same America/New_York zone the loader
    # uses, so DST-aware offsets are preserved verbatim.
    acceptance_dt = datetime.strptime(m.group(1), "%Y%m%d%H%M%S").replace(tzinfo=ET)
    row = {
        "accession": accession,
        "form": by_accession[accession]["form"],
        "period_end": by_accession[accession]["report_date"],
        "acceptance_datetime_header_et": acceptance_dt.isoformat(),
        "acceptance_datetime_header_raw": m.group(1),
        "header_source_sha256": digest,
        "header_source_url": (
            f"https://www.sec.gov/Archives/edgar/data/{CIK_INT}/"
            f"{accession.replace('-', '')}/{accession}-index-headers.html"
        ),
        "sec_items": by_accession[accession]["items"],
    }
    for key, rx, width in (
        ("filed_as_of_date_header", filed_re, 8),
        ("date_as_of_change_header", changed_re, 8),
        ("conformed_period_of_report_header", period_re, 8),
        ("fiscal_year_end_header", fye_re, 4),
    ):
        mm = rx.search(text)
        if mm:
            row[key] = mm.group(1) if width == 4 else mm.group(1)
    rows.append(row)

print(f"acceptance rows: {len(rows)} (unparsed headers skipped: {len(unparsed)})")

acceptance_rows = sorted(rows, key=lambda x: (x["acceptance_datetime_header_et"], x["accession"]))
write_json(OUT / "filing_acceptance_evidence.json", acceptance_rows)

# ------------------------------------------------------------- manifest
manifest = {
    "ticker": "MSFT",
    "issuer_id": f"CIK{CIK}",
    "entity_name": submissions.get("name"),
    "fiscal_year_end": submissions.get("fiscalYearEnd"),
    "role": "production",
    "provenance": {
        "canonical_layout": (
            "Packaged from the verified MSFT contract-validation research run "
            "(msft-historical-pe-contract-validation/0.1.0). Inputs were validated "
            "against their original SEC sources before promotion."
        ),
        "research_source": (
            "research/experiments/aapl-historical-pe-poc/contract/"
            "msft_validation (git-ignored working tree, not required at runtime)"
        ),
        "promoted_on": "2026-10-11",
        "issuer_facts": {
            "cik": CIK,
            "fye_month": 6,
            "source_url": f"https://data.sec.gov/submissions/CIK{CIK}.json",
            "content_sha256": sha256_bytes((RAW / "submissions.json").read_bytes()),
        },
        "files": {
            "daily_prices.json": {
                "content_sha256": price_sha,
                "bytes": len(prices_raw),
            },
            "eps_diluted_concept.json": {
                "content_sha256": eps_sha,
                "bytes": len(eps_raw),
            },
            "filing_acceptance_evidence.json": {
                "row_count": len(acceptance_rows),
                "content_sha256": sha256_bytes(
                    (OUT / "filing_acceptance_evidence.json").read_bytes()
                ),
            },
            "q4_evidence_records.json": {
                "record_count": json.loads(
                    (OUT / "q4_evidence_records.json").read_text(encoding="utf-8")
                )["metadata"]["total_q4_records"],
            },
        },
        "point_in_time_rule": (
            "usable_date is derived from acceptance_datetime_header_et using the "
            "16:00 ET cutoff rule at load time; acceptance timestamps are preserved "
            "verbatim from the EDGAR SGML headers."
        ),
    },
}
write_json(OUT / "manifest.json", manifest)
print("\ncanonical MSFT dataset packaged.")