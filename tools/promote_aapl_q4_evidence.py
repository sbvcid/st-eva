"""One-off packaging tool: promote the verified AAPL Q4 EPS evidence records into
the canonical tracked production layout at data/historical_pe/AAPL/.

This mirrors tools/package_msft_canonical.py: it derives filing acceptance
evidence from the primary SGML headers (never from a self-declared field) and
records the promotion provenance in the canonical manifest.

Build-time only. It reads the git-ignored research/ working tree to parse the
frozen raw headers/submissions, and writes only into data/historical_pe/AAPL/.
It never touches any other issuer, and it does not run at load time. Run from
the repository root:

    python tools/promote_aapl_q4_evidence.py
"""
import hashlib
import json
import pathlib
import re
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from historical_pe import canonical_json_hash
CANON = ROOT / "data" / "historical_pe" / "AAPL"
Q4_HEADERS = ROOT / "research/experiments/aapl-historical-pe-poc/q4_study/raw/headers"
SUBMISSIONS = ROOT / "research/experiments/aapl-historical-pe-poc/raw/submissions.json"

CIK_INT = "320193"
CIK = "0000320193"
ISSUER = "AAPL"
PROMOTED_ON = "2026-10-13"
SOURCE_TYPE = "SEC_8K_ITEM_2_02_EX_99_1"

# Must match historical_pe.ET so the stored offset reproduces the point-in-time
# cutoff exactly, including DST (a hard-coded -04:00 would mis-date winter EST).
ET = ZoneInfo("America/New_York")

ACCEPT_RE = re.compile(r"ACCEPTANCE-DATETIME(?:&gt;|>)(\d{14})")
TYPE_RE = re.compile(r"<TYPE>([^\s<]+)")
ACCESSION_RE = re.compile(r"<ACCESSION-NUMBER>([0-9-]+)")
ITEMS_RE = re.compile(r"<ITEMS>([0-9.]+)")


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def write_json(path: pathlib.Path, payload, sort_keys: bool) -> None:
    text = json.dumps(payload, indent=2, sort_keys=sort_keys, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {path.relative_to(ROOT)} ({len(text)} bytes)")


# ------------------------------------------------------------------ inputs
# The canonical file is produced from the frozen source study, which retains the
# full candidate set (adopted + non-adopted refusal records). Only the records
# that pass the loader evidence gate are promoted into the canonical file; the
# remaining candidates stay in this source study file.
q4_path = CANON / "q4_evidence_records.json"
STUDY_REL = "research/experiments/aapl-historical-pe-poc/q4_study/out/q4_evidence_records.json"
study_path = ROOT / STUDY_REL
study = json.loads(study_path.read_text(encoding="utf-8"))
all_records = study["records"]

adopted = [
    r for r in all_records
    if r.get("source_type") == SOURCE_TYPE and r.get("meets_st_eva_q4_evidence")
]
adopted.sort(key=lambda r: (r["fiscal_year"], r["fiscal_quarter"]))
adopted_accessions = [r["accession"] for r in adopted]
print(f"source study records: {len(all_records)}; adopted (gate-pass): {len(adopted)} -> {adopted_accessions}")

submissions = json.loads(SUBMISSIONS.read_text(encoding="utf-8"))
recent = submissions["filings"]["recent"]
sub_by_accession = {}
for accn, form, report_date, items in zip(
    recent.get("accessionNumber", []),
    recent.get("form", []),
    recent.get("reportDate", []),
    recent.get("items", []),
):
    sub_by_accession[accn] = {"form": form, "report_date": report_date, "items": items or ""}

# -------------------------------------- derive acceptance rows from raw headers
new_rows = []
for rec in adopted:
    accn = rec["accession"]
    header_file = Q4_HEADERS / f"{accn}.txt"
    if not header_file.exists():
        raise FileNotFoundError(f"missing primary SGML header for {accn}: {header_file}")
    raw = header_file.read_bytes()
    text = raw.decode("utf-8", errors="replace")

    m = ACCEPT_RE.search(text)
    if not m:
        raise ValueError(f"no ACCEPTANCE-DATETIME in header for {accn}")
    raw_accept = m.group(1)
    acceptance_dt = datetime.strptime(raw_accept, "%Y%m%d%H%M%S").replace(tzinfo=ET)

    type_m = TYPE_RE.search(text)
    acc_m = ACCESSION_RE.search(text)
    if not type_m or type_m.group(1) != "8-K":
        raise ValueError(f"header TYPE is not 8-K for {accn}: {type_m and type_m.group(1)}")
    if not acc_m or acc_m.group(1) != accn:
        raise ValueError(f"header ACCESSION-NUMBER mismatch for {accn}: {acc_m and acc_m.group(1)}")

    meta = sub_by_accession.get(accn)
    if not meta:
        raise ValueError(f"{accn} not present in submissions.json")
    if meta["form"] != "8-K":
        raise ValueError(f"submissions form for {accn} is {meta['form']}, expected 8-K")
    if not meta["items"].startswith("2.02"):
        raise ValueError(f"submissions items for {accn} is {meta['items']!r}, expected Item 2.02")

    row = {
        "acceptance_datetime_header_et": acceptance_dt.isoformat(),
        "acceptance_datetime_header_raw": raw_accept,
        "accession": accn,
        "form": "8-K",
        "header_source_sha256": sha256_bytes(raw),
        "header_source_url": (
            f"https://www.sec.gov/Archives/edgar/data/{CIK_INT}/"
            f"{accn.replace('-', '')}/{accn}-index-headers.html"
        ),
        "period_end": meta["report_date"],
        "sec_items": meta["items"],
    }
    new_rows.append(row)
    print(f"  {accn}: {acceptance_dt.isoformat()}  usable-rule-input  period_end={meta['report_date']} items={meta['items']}")

# ----------------------------- merge into the tracked acceptance evidence file
acceptance_path = CANON / "filing_acceptance_evidence.json"
existing = json.loads(acceptance_path.read_text(encoding="utf-8"))
existing_accessions = {r["accession"] for r in existing}
new_accessions = {r["accession"] for r in new_rows}
overlap = existing_accessions & new_accessions
print(f"existing acceptance rows: {len(existing)}; new 8-K rows: {len(new_rows)}; overlap: {sorted(overlap)}")

merged = [r for r in existing if r["accession"] not in new_accessions] + new_rows
merged.sort(key=lambda r: (r["acceptance_datetime_header_et"], r["accession"]))
write_json(acceptance_path, merged, sort_keys=False)
print(f"acceptance rows: {len(existing)} -> {len(merged)}")

# -------------------------------------------------------------- q4 canonical
q4 = {k: v for k, v in study.items() if k != "not_production"}
q4["records"] = adopted
q4["metadata"] = {
    "issuer": ISSUER,
    "cik": CIK,
    "source": "AAPL FY2021+ Q4 diluted EPS evidence source study (promoted to canonical production layout)",
    "source_file": STUDY_REL,
    "canonical_role": "production",
    "promoted_on": PROMOTED_ON,
    "total_q4_records": len(adopted),
    "source_study_candidate_records": len(all_records),
    "rejected_records_retained_at": STUDY_REL,
    "evidence_class": "furnished",
    "form_type": "8-K",
    "sec_item": "Item 2.02",
    "schema_notes": (
        "Records carry 'document_identifier'; the production loader reads this field into "
        "evidence source_document. Do not rename to 'source_document'. This canonical file "
        "contains only the records that pass the loader evidence gate "
        "(source_type='SEC_8K_ITEM_2_02_EX_99_1' and meets_st_eva_q4_evidence=true); the "
        "non-adopted candidate/refusal records remain in the source study file named by "
        "'rejected_records_retained_at' (indexed by research/RESEARCH-ARCHIVE-MANIFEST.json)."
    ),
}
q4["content_hash"] = canonical_json_hash({k: v for k, v in q4.items() if k != "content_hash"})
write_json(q4_path, q4, sort_keys=False)

# ------------------------------------------------------------------- manifest
files = {
    "daily_prices.json": {
        "bytes": (CANON / "daily_prices.json").stat().st_size,
        "content_sha256": sha256_bytes((CANON / "daily_prices.json").read_bytes()),
        "source": "YahooFinance as-traded and split history",
    },
    "eps_diluted_concept.json": {
        "bytes": (CANON / "eps_diluted_concept.json").stat().st_size,
        "content_sha256": sha256_bytes((CANON / "eps_diluted_concept.json").read_bytes()),
        "source": "SEC EDGAR company facts EarningsPerShareDiluted (CIK0000320193)",
    },
    "filing_acceptance_evidence.json": {
        "row_count": len(merged),
        "content_sha256": sha256_bytes(acceptance_path.read_bytes()),
        "source": "SEC EDGAR SGML header ACCEPTANCE-DATETIME index (10-K/10-Q/8-K Item 2.02)",
    },
    "q4_evidence_records.json": {
        "record_count": len(q4["records"]),
        "content_sha256": sha256_bytes(q4_path.read_bytes()),
        "source": "SEC Form 8-K Item 2.02 EX-99.1 earnings release furnished Q4 EPS records",
    },
}

manifest = {
    "ticker": ISSUER,
    "issuer_id": f"CIK{CIK}",
    "entity_name": submissions.get("name"),
    "fiscal_year_end": submissions.get("fiscalYearEnd"),
    "role": "production",
    "provenance": {
        "canonical_layout": (
            "Packaged from the AAPL FY2021+ Q4 diluted EPS evidence source study "
            "(aapl-q4-evidence-study/0.1.0). Inputs were validated against their original "
            "SEC sources before promotion."
        ),
        "research_source": (
            "research/experiments/aapl-historical-pe-poc/q4_study and .../raw "
            "(git-ignored working tree, not required at runtime)"
        ),
        "promoted_on": PROMOTED_ON,
        "issuer_facts": {
            "cik": CIK,
            "fye_month": 9,
            "source_url": f"https://data.sec.gov/submissions/CIK{CIK}.json",
            "content_sha256": sha256_bytes(SUBMISSIONS.read_bytes()),
        },
        "files": files,
        "point_in_time_rule": (
            "usable_date is derived from acceptance_datetime_header_et using the 16:00 ET "
            "cutoff rule at load time; acceptance timestamps are preserved verbatim from the "
            "EDGAR SGML headers."
        ),
    },
}
write_json(CANON / "manifest.json", manifest, sort_keys=False)
print("\ncanonical AAPL dataset promoted.")
