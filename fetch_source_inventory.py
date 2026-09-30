"""
Fetch what a filer actually reports, which the archive cannot tell us.

2.7 found the thing this exists for: **a registry-driven archive is blind to a
concept it never asked for.** Ingestion fetches only what the registry maps, so
the archive's own count of unmapped concepts is always zero and means nothing.
The honest number comes from the source, one request per issuer.

It is also what makes a coverage figure decomposable. Without an inventory the
ledger has to say `source_inventory_known: false` and report nothing about what
the filer reports that ST-EVA does not model. With one it can distinguish a
metric ST-EVA has no concept for from a concept the filer has and ST-EVA has not
considered — which are different pieces of work.

Output is a directory of `companyfacts` responses, one per issuer, written where
the caller says. Not committed: it is a moving EDGAR extract, and the *ledger* is
the artefact that matters. The numbers derived from it are committed.

One request per issuer. The endpoint is the same one ingestion already uses, and
`companyfacts` is the only single-request view of everything a filer has ever
tagged — asking concept by concept would be hundreds of requests to learn the
same thing.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from typing import Dict, List, Optional, Tuple

UA = (
    "ST-EVA research (contact: local development; "
    "st-eva coverage inventory)"
)
CIK_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"

# The taxonomies ST-EVA declares concepts against. A filer reporting anything
# outside this set is reporting filer-specific extension elements, which are a
# different kind of thing from a standard concept and are reported at taxonomy
# granularity rather than declined one by one.
DECLARED_TAXONOMIES = ("us-gaap", "ifrs-full", "dei")


def _get(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=300) as response:
        return response.read().decode("utf-8")


def resolve_ciks(wanted: List[str]) -> Dict[str, int]:
    """
    Ticker to CIK, through the provider ingestion already uses.

    Not through a second copy of EDGAR's ticker map. The first version fetched
    `company_tickers.json` directly and got a 403, because the SEC rate-limits
    unauthenticated callers and the provider already carries the headers, the
    retry discipline and a cache for exactly this call. A tool that resolves
    issuers should go through the one place that knows how, or it becomes a
    second thing to maintain and a second way to fail.
    """
    from sec_provider import SECProvider

    provider = SECProvider()
    out: Dict[str, int] = {}
    for ticker in wanted:
        company = provider.resolve_company(ticker)
        if company is None:
            raise SystemExit(f"the SEC does not list a ticker {ticker!r}")
        out[ticker] = int(company.cik)
    return out


def concepts(facts: Dict[str, object], *, reported_only: bool = True
             ) -> Dict[str, List[str]]:
    """
    Every concept the filer has reported, by taxonomy.

    `reported_only` skips an element that has appeared with no facts at all,
    which SEC includes for taxonomy completeness. An element nobody ever used is
    not something the filer reports, and counting it would put a number in the
    ledger that no filing supports.
    """
    out: Dict[str, List[str]] = {}
    for taxonomy, concepts in (facts.get("facts") or {}).items():
        names: List[str] = []
        for name, body in concepts.items():
            facts_count = sum(
                len(rows) for rows in (body.get("units") or {}).values()
            )
            if reported_only and not facts_count:
                continue
            names.append(f"{taxonomy}:{name}")
        if names:
            out[taxonomy] = sorted(names)
    return out


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issuer", action="append", required=True)
    parser.add_argument(
        "--out",
        required=True,
        help="directory for the companyfacts responses",
    )
    parser.add_argument(
        "--summary", help="write a summary here instead of printing it"
    )
    args = parser.parse_args(argv)

    os.makedirs(args.out, exist_ok=True)
    ciks = resolve_ciks(args.issuer)
    summary: Dict[str, object] = {}

    for ticker in args.issuer:
        raw = _get(CIK_URL.format(cik=ciks[ticker]))
        path = os.path.join(args.out, f"{ticker}_companyfacts.json")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(raw)
        found = concepts(json.loads(raw))
        summary[ticker] = {
            "cik": f"{ciks[ticker]:010d}",
            "taxonomies": {t: len(v) for t, v in sorted(found.items())},
            "concepts_reported": sum(len(v) for v in found.values()),
            "undeclared_taxonomies": sorted(
                t for t in found if t not in DECLARED_TAXONOMIES
            ),
            "undeclared_concepts": sum(
                len(v) for t, v in found.items()
                if t not in DECLARED_TAXONOMIES
            ),
        }
        print(f"{ticker}: "
              f"{summary[ticker]['concepts_reported']} concepts reported"
              + (f", {summary[ticker]['undeclared_concepts']} in undeclared "
                 f"taxonomies {summary[ticker]['undeclared_taxonomies']}"
                 if summary[ticker]["undeclared_concepts"] else ""))

    if args.summary:
        with open(args.summary, "w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=2, sort_keys=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())