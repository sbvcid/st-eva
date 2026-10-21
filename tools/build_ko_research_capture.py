"""Build the committed KO research capture for the research calculation lane.

The capture holds exactly the inputs the four KO research lanes read: the
daily price series, the filing acceptance index, the cover-page share counts,
and the filed concept elements each lane's roles are read from. It is a
research capture: it lives under ``data/research_multiples/`` and touches no
production path.

Every file records where it came from, how it was retrieved, and the SHA-256
of the bytes it was built from. The same inputs produce the same bytes.

Usage
-----
    python tools/build_ko_research_capture.py [--cache-dir DIR] [--as-of DATE]

``--cache-dir`` keeps the retrieved source documents so a rebuild does not
refetch them. The capture is a snapshot of the issuer's filings as they stood
at the recorded capture date; a later rebuild may legitimately see filings
that did not exist then, which is why the capture date is recorded in every
file and in the manifest.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "research_multiples" / "KO"

TICKER = "KO"
CIK = "0000021344"
CIK_BARE = CIK
ENTITY_NAME = "The Coca-Cola Company"
FISCAL_YEAR_END = "12-31"
USER_AGENT = "ST-EVA research capture (research; st-eva@example.com)"

MIN_FILED_DATE = "2010-01-01"
PERIODIC_FORMS = ("10-K", "10-Q")
REQUEST_INTERVAL_SECONDS = 0.15
MAX_ATTEMPTS = 5

COMPANYFACTS_URL = (
    f"https://data.sec.gov/api/xbrl/companyfacts/CIK{CIK}.json"
)
SUBMISSIONS_URL = f"https://data.sec.gov/submissions/CIK{CIK}.json"
SUBMISSIONS_ARCHIVE_URL = (
    f"https://data.sec.gov/submissions/CIK{CIK}-submissions-001.json"
)
PRICES_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/KO"
    "?period1=1262304000&period2=1790000000&interval=1d&events=div%2Csplit"
)

# The roles the four lanes read, and the elements each role may be read from,
# in the issuer's own chronology. A role names a quantity; the element is the
# issuer's own choice of how to file it.
ROLE_ELEMENTS = {
    "revenue": ("us-gaap", ("Revenues",)),
    "operating_income": ("us-gaap", ("OperatingIncomeLoss",)),
    "depreciation": ("us-gaap", ("DepreciationDepletionAndAmortization",)),
    "cash": ("us-gaap", ("CashAndCashEquivalentsAtCarryingValue",)),
    "marketable_securities_current": (
        "us-gaap",
        ("MarketableSecuritiesCurrent", "MarketableSecurities"),
    ),
    "commercial_paper": ("us-gaap", ("CommercialPaper",)),
    "notes_and_loans_payable": (
        "us-gaap",
        ("NotesAndLoansPayableCurrent", "NotesAndLoansPayable"),
    ),
    "long_term_debt_noncurrent": (
        "us-gaap",
        ("LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations"),
    ),
    "long_term_debt_current": (
        "us-gaap",
        ("LongTermDebtCurrent", "LongTermDebtAndCapitalLeaseObligationsCurrent"),
    ),
    "shares_outstanding": ("dei", ("EntityCommonStockSharesOutstanding",)),
}

# Elements the companyconcept endpoint serves with no facts for this filer.
# The SEC facts payload is used for them, and the substitution is recorded in
# the capture rather than left silent.
COMPANYCONCEPT_EMPTY = {
    "us-gaap:Revenues": (
        "The companyconcept endpoint serves this element with empty units for "
        "this filer, so the rows come from the issuer's XBRL fact set in the "
        "companyfacts payload instead."
    ),
}

CONTEXT_POLICY = (
    "The SEC facts APIs publish facts without dimensional qualifiers, so "
    "every row in this capture is a fact with no dimensions. They do not "
    "publish the filing's contextRef, so each row's context is pinned by "
    "(accession, element, period, unit) with no dimensions, which identifies "
    "exactly one fact in that filing."
)


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------


def fetch_bytes(url: str, cache_dir: Path | None) -> bytes:
    """Fetch a source document, preferring a local cache copy."""
    cache_path = None
    if cache_dir is not None:
        cache_path = cache_dir / re.sub(r"[^A-Za-z0-9._-]+", "_", url)[-120:]
        if cache_path.exists():
            return cache_path.read_bytes()
    last: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=180) as response:
                payload = response.read()
            if cache_path is not None:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_bytes(payload)
            time.sleep(REQUEST_INTERVAL_SECONDS)
            return payload
        except urllib.error.HTTPError as error:
            if error.code == 404:
                raise
            last = error
        except (urllib.error.URLError, OSError) as error:
            last = error
        time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"failed to fetch {url}: {last}")


def sha256_of(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def write_json(path: Path, payload: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)
    # LF, because the manifest pins this file's SHA-256 and a checkout that
    # rewrote the line endings would change the bytes the digest names.
    path.write_text(text + "\n", encoding="utf-8", newline="\n")
    return sha256_of(path.read_bytes())


# ---------------------------------------------------------------------------
# The acceptance index
# ---------------------------------------------------------------------------


def build_acceptance_index(cache_dir: Path | None) -> list[dict]:
    """One record per periodic filing, with the acceptance time it was filed."""
    rows: list[tuple[str, str, str, str, str]] = []
    for url in (SUBMISSIONS_URL, SUBMISSIONS_ARCHIVE_URL):
        payload = json.loads(fetch_bytes(url, cache_dir).decode("utf-8"))
        recent = payload["filings"]["recent"] if "filings" in payload else payload
        rows.extend(
            zip(
                recent["accessionNumber"],
                recent["form"],
                recent["reportDate"],
                recent["filingDate"],
                recent["acceptanceDateTime"],
            )
        )
    seen: set[str] = set()
    filings = []
    for accession, form, report_date, filing_date, acceptance in rows:
        if form not in PERIODIC_FORMS or filing_date < MIN_FILED_DATE:
            continue
        if accession in seen:
            continue
        seen.add(accession)
        filings.append((accession, form, report_date, filing_date, acceptance))
    filings.sort(key=lambda row: row[4])

    records = []
    for accession, form, report_date, filing_date, acceptance in filings:
        bare = accession.replace("-", "")
        base = f"https://www.sec.gov/Archives/edgar/data/{CIK_BARE}/{bare}"
        header_url = f"{base}/{accession}-index-headers.html"
        text = ""
        try:
            text = fetch_bytes(header_url, cache_dir).decode("utf-8", "replace")
        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise
        if "ACCEPTANCE-DATETIME" not in text:
            # Older filings predate the index-headers page; their submission
            # text file carries the same SGML header.
            header_url = f"{base}/{accession}.txt"
            text = fetch_bytes(header_url, cache_dir).decode("utf-8", "replace")

        def grab(pattern: str) -> str | None:
            found = re.search(pattern, text)
            return found.group(1) if found else None

        raw = grab(r"ACCEPTANCE-DATETIME[&gt;:\s]+(\d{14})")
        api_utc = datetime.datetime.fromisoformat(acceptance.replace("Z", "+00:00"))
        if raw:
            header_et = datetime.datetime.strptime(raw, "%Y%m%d%H%M%S").replace(
                tzinfo=datetime.timezone(datetime.timedelta(hours=-4))
            )
            basis = "SGML header ACCEPTANCE-DATETIME"
            effective_et = header_et
        else:
            header_et = None
            effective_et = api_utc.astimezone(
                datetime.timezone(datetime.timedelta(hours=-4))
            )
            basis = (
                "submissions API acceptanceDateTime, converted to America/New_York; "
                "no SGML header was retrievable for this filing"
            )
        records.append(
            {
                "accession": accession,
                "form": form,
                "period_end": report_date,
                "filed_date_submissions": filing_date,
                "acceptance_datetime_header_et": (
                    header_et.isoformat() if header_et else None
                ),
                "acceptance_datetime_effective_et": effective_et.isoformat(),
                "acceptance_datetime_submissions_api": acceptance,
                "acceptance_basis": basis,
                "api_minus_header_hours": round(
                    (api_utc - effective_et).total_seconds() / 3600.0, 3
                ),
                "conformed_period_of_report_header": grab(
                    r"CONFORMED PERIOD OF REPORT:\s*(\d{8})"
                ),
                "date_as_of_change_header": grab(r"DATE AS OF CHANGE:\s*(\d{8})"),
                "filed_as_of_date_header": grab(r"FILED AS OF DATE:\s*(\d{8})"),
                "fiscal_year_end_header": grab(r"FISCAL YEAR END:\s*(\d{4})"),
                "header_source_url": header_url,
                "header_source_sha256": sha256_of(text.encode("utf-8")),
            }
        )
    return records


# ---------------------------------------------------------------------------
# The concept captures
# ---------------------------------------------------------------------------


def build_role_captures(
    companyfacts: dict, companyfacts_sha: str, captured_at: str
) -> dict[str, dict]:
    """One capture file per role, holding the elements the role may be read from."""
    captures: dict[str, dict] = {}
    for role, (taxonomy, tags) in ROLE_ELEMENTS.items():
        elements = []
        for tag in tags:
            body = (companyfacts.get("facts") or {}).get(taxonomy, {}).get(tag)
            if body is None:
                raise SystemExit(
                    f"{taxonomy}:{tag} is absent from the companyfacts payload; "
                    "the capture cannot be built"
                )
            units = {}
            for unit, rows in (body.get("units") or {}).items():
                units[unit] = [
                    {
                        "start": row.get("start"),
                        "end": row.get("end"),
                        "val": row.get("val"),
                        "accn": row.get("accn"),
                        "fy": row.get("fy"),
                        "fp": row.get("fp"),
                        "form": row.get("form"),
                        "filed": row.get("filed"),
                        "frame": row.get("frame"),
                    }
                    for row in rows
                ]
            concept = f"{taxonomy}:{tag}"
            elements.append(
                {
                    "taxonomy": taxonomy,
                    "tag": tag,
                    "label": body.get("label"),
                    "description": body.get("description"),
                    "units": units,
                    "fact_count": sum(len(rows) for rows in units.values()),
                    "source": {
                        "concept": concept,
                        "companyconcept_endpoint": (
                            "https://data.sec.gov/api/xbrl/companyconcept/"
                            f"CIK{CIK}/{taxonomy}/{tag}.json"
                        ),
                        "facts_endpoint": COMPANYFACTS_URL,
                        "source_document_sha256": companyfacts_sha,
                        "dimensions": (
                            "none; the SEC facts payloads publish only facts "
                            "with no dimensional qualifiers"
                        ),
                        "context_ref": (
                            "not published by the SEC facts APIs; the fact is "
                            "pinned by (accession, element, period, unit) with "
                            "no dimensions"
                        ),
                        "substitution_note": COMPANYCONCEPT_EMPTY.get(concept),
                    },
                }
            )
        captures[role] = {
            "issuer_id": f"CIK{CIK}",
            "ticker": TICKER,
            "role": role,
            "taxonomy": taxonomy,
            "captured_at": captured_at,
            "context_policy": CONTEXT_POLICY,
            "elements": elements,
        }
    return captures


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, default=None)
    parser.add_argument(
        "--as-of",
        default=datetime.date.today().isoformat(),
        help="the capture date recorded in every file",
    )
    arguments = parser.parse_args()
    captured_at = arguments.as_of
    cache_dir = arguments.cache_dir

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    companyfacts_bytes = fetch_bytes(COMPANYFACTS_URL, cache_dir)
    companyfacts_sha = sha256_of(companyfacts_bytes)
    companyfacts = json.loads(companyfacts_bytes.decode("utf-8"))
    print(f"companyfacts: {len(companyfacts_bytes)} bytes sha={companyfacts_sha}")

    prices_bytes = fetch_bytes(PRICES_URL, cache_dir)
    prices_sha = sha256_of(prices_bytes)
    price_result = json.loads(prices_bytes.decode("utf-8"))["chart"]["result"][0]
    print(
        f"prices: {len(price_result['timestamp'])} bars "
        f"granularity={price_result['meta'].get('dataGranularity')}"
    )

    acceptance = build_acceptance_index(cache_dir)
    print(f"acceptance records: {len(acceptance)}")

    files: dict[str, dict] = {}
    prices_path = OUT_DIR / "daily_prices.json"
    prices_path.write_bytes(prices_bytes)
    files["daily_prices.json"] = {
        "sha256": prices_sha,
        "bytes": len(prices_bytes),
        "role": "prices",
        "source": {
            "url": PRICES_URL,
            "retrieval": (
                "one daily-granularity chart request for the issuer's ticker; "
                "the payload is stored verbatim, including its split events"
            ),
            "source_document_sha256": prices_sha,
            "note": (
                "The provider's close series reflects later split events. The "
                "lane restores the as-traded close from the split events in "
                "this payload before it pairs a price with a share count."
            ),
        },
    }
    files["filing_acceptance_evidence.json"] = {
        "sha256": write_json(
            OUT_DIR / "filing_acceptance_evidence.json", acceptance
        ),
        "bytes": (OUT_DIR / "filing_acceptance_evidence.json").stat().st_size,
        "role": "acceptance index",
        "source": {
            "url": (
                "https://www.sec.gov/Archives/edgar/data/"
                f"{CIK_BARE}/<accession>/<accession>-index-headers.html"
            ),
            "retrieval": (
                "one request per periodic filing for the filing's SGML header; "
                "the acceptance datetime is read from the header's "
                "ACCEPTANCE-DATETIME field, which is America/New_York local time"
            ),
            "source_document_sha256": None,
            "note": (
                "The acceptance datetime decides when a filing's facts first "
                "become knowable, which is the point-in-time rule the lane "
                "applies."
            ),
        },
    }

    captures = build_role_captures(companyfacts, companyfacts_sha, captured_at)
    for role, capture in captures.items():
        filename = f"{role}_concept.json"
        digest = write_json(OUT_DIR / filename, capture)
        files[filename] = {
            "sha256": digest,
            "bytes": (OUT_DIR / filename).stat().st_size,
            "role": role,
            "source": {
                "url": COMPANYFACTS_URL,
                "retrieval": (
                    "one request for the issuer's XBRL fact set; the rows of "
                    "each element are taken verbatim and re-keyed to the "
                    "companyconcept shape the production loaders read"
                ),
                "source_document_sha256": companyfacts_sha,
                "note": CONTEXT_POLICY,
            },
        }
        print(
            f"  {filename:44s} "
            + ", ".join(
                f"{element['tag']}={element['fact_count']}"
                for element in capture["elements"]
            )
        )

    manifest = {
        "dataset": "KO research capture",
        "purpose": (
            "Research calculation lane inputs for The Coca-Cola Company. "
            "Research use only: these files are not production inputs, they "
            "are not read by the production runner, and no figure computed "
            "from them is a production reference."
        ),
        "issuer": {
            "ticker": TICKER,
            "cik": f"CIK{CIK}",
            "entity_name": ENTITY_NAME,
            "fiscal_year_end": FISCAL_YEAR_END,
        },
        "captured_at": captured_at,
        "capture_policy": {
            "periodic_filings": list(PERIODIC_FORMS),
            "earliest_filed_date": MIN_FILED_DATE,
            "facts_endpoint": COMPANYFACTS_URL,
            "facts_endpoint_sha256": companyfacts_sha,
            "context_policy": CONTEXT_POLICY,
            "dimensions": (
                "The SEC facts payloads publish only facts with no "
                "dimensional qualifiers, so every row here is a consolidated "
                "fact and the capture carries no segment or member variants."
            ),
            "companyconcept_substitutions": COMPANYCONCEPT_EMPTY,
        },
        "files": files,
    }
    write_json(OUT_DIR / "manifest.json", manifest)
    print(f"\nwritten {OUT_DIR}")


if __name__ == "__main__":
    main()
