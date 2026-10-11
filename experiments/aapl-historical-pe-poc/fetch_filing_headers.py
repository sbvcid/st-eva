"""POC fetch stage 2: capture per-filing acceptance evidence from EDGAR.

The submissions API carries `acceptanceDateTime`, and EDGAR's own SGML header
carries `ACCEPTANCE-DATETIME`. The POC needs both, because the two disagree on
the timestamp's timezone basis and the ADR's 16:00 ET rule depends on which
reading is right. Every value here is stored verbatim next to the URL it came
from, so the disagreement can be re-measured rather than argued about.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"

CIK = "320193"
ET = ZoneInfo("America/New_York")
UTC = datetime.timezone.utc
USER_AGENT = "ST-EVA Historical P/E POC (research; st-eva@example.com)"

MIN_FILED_DATE = "2016-01-01"
FORMS = ("10-Q", "10-K")
REQUEST_INTERVAL_SECONDS = 0.4
MAX_ATTEMPTS = 5


def fetch_text(url: str) -> str:
    last = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": USER_AGENT}
            )
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read().decode("utf-8", "replace")
        except (urllib.error.URLError, OSError) as error:
            last = error
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"failed to fetch {url}: {last}")


def header_url(accession: str) -> str:
    bare = accession.replace("-", "")
    return (
        f"https://www.sec.gov/Archives/edgar/data/{CIK}/{bare}/"
        f"{accession}-index-headers.html"
    )


def read_header(accession: str) -> dict:
    url = header_url(accession)
    target = RAW / "headers" / f"{accession}.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        text = target.read_text(encoding="utf-8", errors="replace")
    else:
        text = fetch_text(url)
        target.write_text(text, encoding="utf-8")
        time.sleep(REQUEST_INTERVAL_SECONDS)

    def grab(pattern: str) -> str | None:
        import re

        found = re.search(pattern, text)
        return found.group(1) if found else None

    return {
        "acceptance_datetime_raw": grab(r"ACCEPTANCE-DATETIME&gt;(\d{14})"),
        "filed_as_of_date": grab(r"FILED AS OF DATE:\s*(\d{8})"),
        "date_as_of_change": grab(r"DATE AS OF CHANGE:\s*(\d{8})"),
        "conformed_period_of_report": grab(
            r"CONFORMED PERIOD OF REPORT:\s*(\d{8})"
        ),
        "conformed_submission_type": grab(
            r"CONFORMED SUBMISSION TYPE:\s*(\S+)"
        ),
        "accession_number": grab(r"ACCESSION NUMBER:\s*(\S+)"),
        "fiscal_year_end_header": grab(r"FISCAL YEAR END:\s*(\d{4})"),
        "source_url": url,
        "source_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def main() -> None:
    submissions = json.loads(
        (RAW / "submissions.json").read_text(encoding="utf-8")
    )
    recent = submissions["filings"]["recent"]
    rows = list(
        zip(
            recent["accessionNumber"],
            recent["form"],
            recent["reportDate"],
            recent["filingDate"],
            recent["acceptanceDateTime"],
        )
    )
    filings = [row for row in rows if row[1] in FORMS and row[3] >= MIN_FILED_DATE]
    filings.sort(key=lambda row: row[4])

    evidence = []
    for accession, form, report_date, filing_date, acceptance in filings:
        header = read_header(accession)
        header_et = None
        if header["acceptance_datetime_raw"]:
            header_et = datetime.datetime.strptime(
                header["acceptance_datetime_raw"], "%Y%m%d%H%M%S"
            ).replace(tzinfo=ET)
        api_utc = datetime.datetime.fromisoformat(
            acceptance.replace("Z", "+00:00")
        )
        entry = {
            "accession": accession,
            "form": form,
            "period_end": report_date,
            "filed_date_submissions": filing_date,
            "acceptance_datetime_submissions_api": acceptance,
            "acceptance_datetime_header_et": (
                header_et.isoformat() if header_et else None
            ),
            "api_minus_header_hours": (
                round(
                    (
                        api_utc
                        - header_et.astimezone(UTC)
                        if header_et
                        else None
                    ).total_seconds()
                    / 3600.0,
                    4,
                )
                if header_et
                else None
            ),
            "conformed_period_of_report_header": header[
                "conformed_period_of_report"
            ],
            "filed_as_of_date_header": header["filed_as_of_date"],
            "date_as_of_change_header": header["date_as_of_change"],
            "fiscal_year_end_header": header["fiscal_year_end_header"],
            "header_source_url": header["source_url"],
            "header_source_sha256": header["source_sha256"],
        }
        evidence.append(entry)
        print(
            f"{form} {accession} hdr_ET={entry['acceptance_datetime_header_et']} "
            f"api={acceptance} delta_h={entry['api_minus_header_hours']} "
            f"filedAsOf={entry['filed_as_of_date_header']}"
        )

    (RAW / "filing_acceptance_evidence.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(f"captured {len(evidence)} filings")


if __name__ == "__main__":
    main()
