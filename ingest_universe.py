"""
Ingest a population of issuers, and measure what a company actually costs.

2.11's question is not "how much data" and not a success rate. It is:

    **can ST-EVA accumulate ten, twenty years of traceable evidence for a
    thousand companies, cheaply and incrementally, without changing what
    evidence means?**

So this does three things and reports them separately.

**Discovery.** The issuer set is not a list of ours. It is drawn from EDGAR's own
company map and stratified by the filer's *own* SIC classification, so the sample
contains what the mix was supposed to contain: US-GAAP and IFRS filers,
manufacturers and software houses and banks and insurers, and issuers whose
filings are structured differently. A sample of names somebody picked is a
sample of what that person was interested in.

**Forms derived, not assumed.** A 20-F filer has nothing in a 10-K index and a
bank files a 10-K. Asking for 10-K/10-Q across the population would report every
foreign private issuer as `SOURCE_SILENT` -- a fact about our request, dressed
as a fact about the filer. Each issuer's forms come from its own submission
history, and that is the same call the evidence layer would make.

**Cost, per company and per filing.** Requests, bytes, seconds, documents, facts,
observations, duplicate rate, and the derived ratios that decide whether a
population is reachable. The rates that matter are *super-linear or not*; a
linear cost per company extrapolates, and anything worse does not.

And the acceptance criterion is the classified absence rather than a percentage:
every issuer that produced no evidence says which of the nine kinds it was, so
"94% collected" comes with an explanation for the six percent.

Second-pass cost is measured too, because **incremental is the whole claim**. A
first pass pays for history; a second pass must not, and the ratio between them
is the number that says whether ten thousand companies is reachable or whether it
is ten thousand full refetches.

The credential is not involved: SEC data is public and unauthenticated, and the
provider self-throttles to 4 requests per second, well under the SEC's ceiling
of ten.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Sequence, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from core_registry import CoreRegistry  # noqa: E402
from coverage_semantics import scoped_ledger  # noqa: E402
from registry_seed import seed  # noqa: E402
from sec_ingest import DEFAULT_METRICS, Ingestor  # noqa: E402
from sec_provider import SECProvider  # noqa: E402
from sqlite_archive import SQLiteArchive  # noqa: E402

# SIC major group -> the shape of company, used to stratify the sample so the
# mix is a decision rather than an accident. The groups are SEC's, and the labels
# are ours; the point is that a sample claiming to cover "banks and software" is
# checked against what was actually drawn.
STRATA: Tuple[Tuple[str, str], ...] = (
    ("35", "industrial_technology"),
    ("36", "semiconductor"),
    ("37", "software"),
    ("49", "utilities_transport"),
    ("20", "manufacturing"),
    ("28", "chemicals"),
    ("29", "petroleum"),
    ("40", "utilities"),
    ("52", "retail"),
    ("60", "bank"),
    ("61", "insurance"),
    ("65", "reit"),
    ("70", "services"),
)

# Filing forms worth asking for, most specific first. `ALL_FORMS` is a fallback
# for a filer whose history we could not read, and it is deliberately broad --
# because the cost of asking for a form a filer does not use is one request, and
# the cost of assuming is reporting a filer as silent.
ALL_FORMS = ("10-K", "10-Q", "20-F", "40-F", "8-K", "10-K/A", "20-F/A")


def _forms_in(submissions: Dict[str, Any]) -> List[str]:
    """
    The filing forms a filer actually uses, most common first.

    Read from the submission history rather than assumed, because assuming
    10-K/10-Q across a population reports every foreign private issuer as
    SOURCE_SILENT -- which is a fact about our request dressed as a fact about
    the filer, and exactly the confusion this round exists to remove.
    """
    recent = ((submissions.get("filings") or {}).get("recent") or {})
    counts: Counter = Counter()
    for form in recent.get("form") or []:
        if form:
            counts[str(form).upper()] += 1
    return [form for form, _ in counts.most_common()]


def _history(submissions: Dict[str, Any]) -> Dict[str, Any]:
    """
    How deep this filer's readable history goes, from the payload already held.

    Two numbers, and the second is the one that matters. Counting readable
    filings picks the wrong filers: a mega-cap's recent window is mostly Form 4
    and Form 8-K, so a thinly-filed small cap with four 10-Qs outranks a filer
    with twenty years of them, and the sample becomes cheap companies -- the
    opposite of what a cost question needs.

    The oldest readable filing date is the honest difficulty signal, and it is
    free: the submission payload already carries a filing date per filing, so
    depth costs no request and selects the filers that actually make a
    population expensive.
    """
    recent = ((submissions.get("filings") or {}).get("recent") or {})
    readable = {
        "10-K", "10-K/A", "10-KT", "10-Q", "10-Q/A", "10-QT", "10QSB",
        "20-F", "20-F/A", "20-FT", "40-F", "40-F/A", "40-FT",
    }
    dates: List[str] = []
    forms = recent.get("form") or []
    filing_dates = recent.get("filingDate") or []
    for form, filing_date in zip(forms, filing_dates):
        if form and str(form).upper() in readable and filing_date:
            dates.append(str(filing_date))
    if not dates:
        return {"depth": None, "count": 0}
    return {"depth": min(dates), "count": len(dates)}


def _filing_relevance(forms: List[str]) -> int:
    """
    How many of a filer's filings could actually carry XBRL financial facts.

    A raw form count is the wrong measure and picks the wrong companies. Form 4
    is an insider transaction and Form 144 is a proposed sale; a filer that makes
    thousands of them and two annual reports ranks above a filer with two decades
    of 10-Qs, and warrants and shell issuers rank above both. The first version
    of this sample was exactly that failure: 73 issuers drawn from the first nine
    letters of the ticker map, none of them a company anyone would name.
    """
    relevant = set(ALL_FORMS) | {"10-KT", "10-QT", "20-FT", "40-FT"}
    return sum(1 for form in forms if form in relevant)


def discover(provider: SECProvider, candidates: int) -> List[Dict[str, Any]]:
    """
    A stratified sample of the EDGAR company map.

    **Strided, not a prefix.** The universe is sorted for reproducibility and
    then sampled at an even stride, because a contiguous prefix is an alphabetical
    slice and an alphabetical slice is a sample of tickers that happen to start
    with A. Striding costs nothing and is the difference between a sample of the
    map and a sample of its first page.

    One request per candidate for its own submission history, which is where the
    SIC comes from. That is the price of not hand-picking, paid once per candidate
    rather than once per issuer we end up ingesting.
    """
    entries = provider.ticker_map()
    universe = [
        {"ticker": ticker, "cik": row["cik"], "name": row["name"]}
        for ticker, row in entries.items()
    ]
    # A stable, reproducible order: EDGAR's map has no order of its own, and a
    # sample that differs between runs cannot be compared with the last one.
    universe.sort(key=lambda row: (row["ticker"], row["cik"]))
    if candidates < len(universe):
        stride = len(universe) // candidates
        universe = universe[::max(stride, 1)][:candidates]

    by_stratum: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in universe:
        try:
            submissions = provider.submissions(row["cik"])
        except Exception:  # noqa: BLE001
            continue
        if not submissions:
            continue
        sic = str(submissions.get("sic") or "")
        major = sic[:2]
        for prefix, stratum in STRATA:      # second element is the label
            if major == prefix:
                row["stratum"] = stratum
                row["sic"] = sic
                row["sic_description"] = submissions.get("sicDescription")
                row["entity_type"] = submissions.get("entityType")
                row["forms"] = _forms_in(submissions)
                history = _history(submissions)
                row["history_depth"] = history["depth"]
                row["readable_filings"] = history["count"]
                row["relevance"] = _filing_relevance(row["forms"])
                by_stratum[stratum].append(row)
                break

    return [
        row
        for _, stratum in STRATA
        for row in by_stratum[stratum]
    ]


def select(
    provider: SECProvider,
    per_stratum: int,
    candidate_pool: int,
) -> List[Dict[str, Any]]:
    """
    Take `per_stratum` issuers from each stratum, the ones with the most filings.

    The busiest filer in a stratum is the hard case, deliberately: a filer with a
    decade of annual and quarterly reports is what makes a population expensive,
    and a sample of thinly-filed companies would report a per-company cost a real
    population would not pay.
    """
    rows = discover(provider, candidate_pool)
    by_stratum: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_stratum[row["stratum"]].append(row)
    chosen: List[Dict[str, Any]] = []
    seen_ciks: set = set()
    for _, stratum in STRATA:            # second element is the label
        # Only filers that actually file something we can read, and the ones
        # that file the most of it. A filer with no annual or quarterly report
        # cannot be a source of anything, and including it would spend a
        # request per company to learn what its absence already says.
        pool = [
            row for row in by_stratum.get(stratum, [])
            if row.get("readable_filings")
            and row["cik"] not in seen_ciks
        ]
        # Deepest readable history first, then the most readable filings, then
        # the ticker for a stable order. Depth is the difficulty signal: a filer
        # with twenty years of annual reports is what makes a population
        # expensive, and a sample of thinly-filed companies would report a
        # per-company cost that a real population would not pay.
        pool.sort(key=lambda r: (
            r.get("history_depth") or "9999",   # oldest first; none last
            -r.get("readable_filings", 0),
            r["ticker"],
        ))
        # One issuer once, whatever tickers it trades under.
        #
        # Found by running, at issuer thirty of seventy-six: a preferred share
        # and its common both mapped to one CIK, and `record_asset` refused the
        # second with a UNIQUE violation. A ticker is not an issuer -- the EDGAR
        # map lists 10,431 tickers for far fewer companies -- so a population
        # drawn from tickers over-counts, and the cost per *company* would be
        # understated by however many share classes a company trades.
        for row in pool[:per_stratum]:
            seen_ciks.add(row["cik"])
            chosen.append(row)
    return chosen


def forms_for(row: Dict[str, Any]) -> Tuple[str, ...]:
    """
    The forms to ask this issuer for, from its own history.

    An issuer whose history lists no forms we recognise gets the full set, so the
    run reports `SOURCE_SILENT` against a real question rather than skipping it.
    """
    known = [
        form for form in row.get("forms", [])
        if form in ALL_FORMS
    ]
    return tuple(dict.fromkeys(known)) if known else ALL_FORMS


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, help="archive to build")
    parser.add_argument("--per-stratum", type=int, default=8)
    parser.add_argument(
        "--candidate-pool",
        type=int,
        default=1400,
        help="company-map entries to read submissions for",
    )
    parser.add_argument(
        "--select-only",
        action="store_true",
        help="print the sample and stop, without ingesting",
    )
    parser.add_argument(
        "--selection",
        help="read the issuer sample from here instead of discovering it",
    )
    parser.add_argument(
        "--save-selection",
        help="write the issuer sample here, so a later run need not re-discover",
    )
    parser.add_argument(
        "--out", help="write the machine-readable result here"
    )
    args = parser.parse_args(argv)

    provider = SECProvider()
    if args.selection and os.path.exists(args.selection):
        with open(args.selection, encoding="utf-8") as handle:
            chosen = json.load(handle)
        print(f"loaded {len(chosen)} issuers from {args.selection}")
    else:
        print("discovering issuers from EDGAR's own map...", flush=True)
        started = time.monotonic()
        chosen = select(provider, args.per_stratum, args.candidate_pool)
        print(f"  discovered in {time.monotonic() - started:.0f}s")
        if args.save_selection:
            with open(args.save_selection, "w", encoding="utf-8") as handle:
                json.dump(chosen, handle, indent=2, sort_keys=True)
    mix = Counter(row["stratum"] for row in chosen)
    print(f"{len(chosen)} issuers across {len(mix)} strata")
    for name, n in sorted(mix.items()):
        print(f"    {name:<24} {n}")
    if args.select_only:
        for row in chosen:
            print(f"    {row['ticker']:<6} {row['stratum']:<24} "
                  f"SIC {row.get('sic')}  depth={row.get('history_depth')} "
                  f"readable={row.get('readable_filings')} "
                  f"forms={','.join(row.get('forms', [])[:4])}")
        return 0

    if os.path.exists(args.target):
        os.remove(args.target)
    store = SQLiteArchive(args.target)
    registry = CoreRegistry(store.connection)
    seeded = seed(registry)

    reports: List[Dict[str, Any]] = []
    totals = Counter()
    started = time.monotonic()
    for index, row in enumerate(chosen, 1):
        before = provider.requests_made
        before_bytes = provider.bytes_downloaded
        tick = time.monotonic()
        report = Ingestor(store, provider, registry).ingest(
            row["ticker"], metrics=DEFAULT_METRICS, forms=forms_for(row)
        )
        payload = report.contract_dict()
        payload["stratum"] = row["stratum"]
        payload["sic"] = row.get("sic")
        payload["requests"] = provider.requests_made - before
        payload["bytes"] = provider.bytes_downloaded - before_bytes
        reports.append(payload)
        for key in (
            "filings_seen", "filings_ingested", "documents_stored",
            "source_facts_stored", "source_facts_skipped",
            "observations_stored", "observations_skipped",
        ):
            totals[key] += payload[key]
        print(
            f"  [{index:>3}/{len(chosen)}] {row['ticker']:<6}"
            f" {payload['outcome']:<22}"
            f" obs={payload['observations_stored']:<6}"
            f" req={payload['requests']:<4}"
            f" {time.monotonic() - tick:>6.1f}s",
            flush=True,
        )
    elapsed = time.monotonic() - started

    # -- second pass: the incremental claim ------------------------------
    print("\nsecond pass over the same population, to measure incrementality",
          flush=True)
    second_started = time.monotonic()
    second_before = provider.requests_made
    second_bytes = provider.bytes_downloaded
    second: List[Dict[str, Any]] = []
    for row in chosen:
        before = provider.requests_made
        report = Ingestor(store, provider, registry).ingest(
            row["ticker"], metrics=DEFAULT_METRICS, forms=forms_for(row)
        )
        second.append({
            "ticker": row["ticker"],
            "requests": provider.requests_made - before,
            "outcome": report.outcome,
            "observations_stored": report.observations_stored,
            "filings_ingested": report.filings_ingested,
        })
    second_elapsed = time.monotonic() - second_started
    second_requests = provider.requests_made - second_before
    second_bytes_delta = provider.bytes_downloaded - second_bytes

    size = os.path.getsize(args.target)
    first_requests = sum(r["requests"] for r in reports)
    first_bytes = sum(r["bytes"] for r in reports)
    companies = len(reports)
    filings = totals["filings_ingested"] or 1

    summary = {
        "seeded": seeded,
        "companies": companies,
        "strata": dict(mix),
        "totals": dict(totals),
        "outcomes": dict(Counter(r["outcome"] for r in reports)),
        "classified_failures": dict(Counter(
            failure["outcome"]
            for r in reports for failure in r.get("failures", [])
        )),
        "elapsed_seconds": round(elapsed, 1),
        "archive_bytes": size,
        "first_pass": {
            "requests": first_requests,
            "bytes": first_bytes,
            "requests_per_company": round(first_requests / max(companies, 1), 2),
            "bytes_per_company": int(first_bytes / max(companies, 1)),
            "seconds_per_company": round(elapsed / max(companies, 1), 2),
            "seconds_per_filing": round(elapsed / filings, 2),
            "observations_per_company": round(
                totals["observations_stored"] / max(companies, 1), 1
            ),
            "megabytes_per_company": round(
                size / 1e6 / max(companies, 1), 2
            ),
        },
        "second_pass": {
            "requests": second_requests,
            "bytes": second_bytes_delta,
            "elapsed_seconds": round(second_elapsed, 1),
            "requests_per_company": round(
                second_requests / max(companies, 1), 2
            ),
            "filings_ingested": sum(r["filings_ingested"] for r in second),
            "observations_stored": sum(
                r["observations_stored"] for r in second
            ),
            "request_ratio": round(
                second_requests / max(first_requests, 1), 4
            ),
        },
        "transport": provider.transport_stats(),
        "reports": reports,
        "second_pass_reports": second,
    }
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=2, sort_keys=True, default=str)
    print("\n" + json.dumps(
        {k: v for k, v in summary.items()
         if k not in ("reports", "second_pass_reports")},
        indent=2, sort_keys=True, default=str,
    ))
    store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())