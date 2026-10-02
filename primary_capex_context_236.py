"""
Primary-source capex context resolution -- 2.36.

Resolves the semantic blockers 2.34 and 2.35 left open by going to the filing
rather than to the aggregate. 2.35 proved that no amount of further
`companyfacts` will answer the question: those documents carry no label and no
description for the IFRS concepts, and no filer reporting any of the three
candidates also reports a declared `capex` concept. So the context has to come
from where presentation lives.

## What is fetched, and why this is the right layer

`companyfacts` is the *aggregated* view. The semantic anchor -- which statement,
which note, what a row is called when a human reads it, whether a line sits under
investing activities -- is in the filing's presentation, exposed by EDGAR as the
Financial Report renderings. One `FilingSummary.xml` names every statement and
note; the R-files render each one. That is the layer where "is this a cash-flow
line or a note movement?" is actually written down.

## The evidence rule, enforced

The filing context is the semantic anchor. Names, period shape, positive values,
value equality and co-movement are **supporting observations only** and none of
them can produce SUPPORTED. `PaymentsForCapitalImprovements` and
`AdditionsOtherThanThroughBusinessCombinationsPropertyPlantAndEquipment` both
already have arithmetic pointing the way their owners want them to go, and the
round is worth running precisely because the presentation may not agree.

Nothing is mapped, promoted, renamed or written back. The registry, the
definitions, the historical observations and the refusal surface are all read
only.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from sec_provider import SECProvider  # noqa: E402

H = os.path.join(HERE, "experiments", "003-llm-evidence-retrieval", "harness")

CANDIDATES = {
    "us-gaap:PaymentsForCapitalImprovements": {
        "label": "A", "taxonomy": "us-gaap",
        "local_name": "PaymentsForCapitalImprovements",
        "presented_as": ["Payments for Capital Improvements",
                          "Capital improvements"],
        "priority_filers": ["EFC", "HPP", "CCXIU"],
    },
    "ifrs-full:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities": {
        "label": "B", "taxonomy": "ifrs-full",
        "local_name": "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
        "presented_as": ["Purchase of property, plant and equipment",
                          "Purchase of property, plant and equipment "
                          "classified as investing activities"],
        "priority_filers": ["TSM", "BHP", "PAAS", "TECK"],
    },
    "ifrs-full:AdditionsOtherThanThroughBusinessCombinationsPropertyPlantAndEquipment": {
        "label": "C", "taxonomy": "ifrs-full",
        "local_name": "AdditionsOtherThanThroughBusinessCombinationsPropertyPlantAndEquipment",
        "presented_as": ["Additions other than through business combinations",
                          "Additions"],
        "priority_filers": ["BHP", "PAAS", "TECK", "RIO"],
    },
}


def fetcher():
    """
    A text fetcher that borrows the provider's identity, not its own.

    `SECProvider._get` is JSON-only by construction -- it raises on a non-JSON
    document, which is the right behaviour for the endpoints it was written for.
    The archives are XML and HTML, so this reuses the provider's opener, its
    User-Agent, its throttle and its fetch log rather than opening a second,
    unaccounted connection to EDGAR. The request count below therefore covers
    everything this round asked of the SEC.
    """
    provider = SECProvider(timeout=60)

    def get_text(url: str):
        provider._throttle()
        provider._fetch_log.append(url)
        provider.requests_made += 1
        request = urllib.request.Request(url, headers={
            "User-Agent": provider.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate",
        })
        try:
            with urllib.request.urlopen(request,
                                        timeout=provider.timeout) as response:
                body = response.read()
                provider.bytes_downloaded += len(body)
                encoding = response.headers.get("Content-Encoding", "")
                if encoding == "gzip":
                    import gzip
                    body = gzip.decompress(body)
                return body.decode("utf-8", "replace")
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            raise

    return provider, get_text


def held_documents() -> dict:
    out = {}
    for d in ("bulkfacts-227a-orig", "bulkfacts-227b", "bulkfacts-ins-min",
              "bulkfacts-fs", "bulkfacts-banks-2", "inventory", "bulkfacts",
              "bulkfacts-banks"):
        p = os.path.join(H, d)
        if not os.path.isdir(p):
            continue
        for name in sorted(os.listdir(p)):
            if name.endswith(".json") and name != "tickers.json":
                out.setdefault(name.split("_")[0].upper(),
                               os.path.join(p, name))
    return out


def accessions_for(path: str, taxonomy: str, local_name: str) -> list:
    doc = json.load(open(path, encoding="utf-8"))
    body = (doc.get("facts") or {}).get(taxonomy, {}).get(local_name)
    if not body:
        return []
    seen = []
    for unit, rows in (body.get("units") or {}).items():
        for r in rows:
            a = r.get("accn")
            if a and a not in seen:
                seen.append(a)
    return seen


def reports(get_text, cik: int, accession: str) -> list:
    base = ("https://www.sec.gov/Archives/edgar/data/"
            f"{cik}/{accession.replace('-', '')}")
    summary = get_text(f"{base}/FilingSummary.xml")
    if not summary:
        return []
    out = []
    for block in re.findall(r"<Report[^>]*>(.*?)</Report>", summary, re.S):
        short = re.search(r"<ShortName>(.*?)</ShortName>", block, re.S)
        html = re.search(r"<HtmlFileName>(.*?)</HtmlFileName>", block, re.S)
        menu = re.search(r"<MenuCategory>(.*?)</MenuCategory>", block, re.S)
        role = re.search(r"<MenuCategory>(.*?)</MenuCategory>", block, re.S)
        if short and html:
            out.append({
                "file": html.group(1),
                "short_name": short.group(1).strip(),
                "menu_category": (role.group(1).strip() if role else ""),
                "url": f"{base}/{html.group(1)}",
            })
    return out


CASH_KEYWORDS = (
    "cash flow", "cash flow statement", "statement of cash flow",
    "operating activities", "investing activities", "financing activities",
)
PPE_NOTE_KEYWORDS = (
    "property, plant and equipment", "property plant and equipment",
    "fixed asset", "changes in property",
)

# A rendered fact is anchored like this, and the third argument is `window`
# rather than a value reference:
#
#   <td class="pl"><a onclick="Show.showAR( this,
#       'defref_us-gaap_PaymentsForCapitalImprovements', window );">
#       Payments for Capital Improvements</a></td>
#
# Two things follow, and both are load-bearing. The **row label is the anchor's own
# text**, so it cannot be mis-associated with a neighbouring cell. And the defref
# is `defref_<taxonomy>_<LocalName>`, which is the one identifier in the document
# that is unambiguous -- matching the English word "Additions", which the first
# version did, flagged a Leases note that merely contained the word.
TAG = re.compile(r"<[^>]+>")
FACT_ANCHOR = re.compile(
    r"Show\.showAR\(\s*this\s*,\s*'(?P<defref>defref_[^']+)'\s*,", re.I)
ROW = re.compile(r"<tr\b.*?</tr>", re.S | re.I)
ANCHOR_TEXT = re.compile(
    r"Show\.showAR\([^>]*>\s*(?P<label>.*?)</a>", re.S | re.I)
NUMERIC_CELL = re.compile(
    r"<td class=\"num[^\"]*\"[^>]*>(.*?)</td>", re.S | re.I)
SECTION = re.compile(
    r"<strong>(.*?)</strong>", re.S | re.I)


def _plain(fragment: str) -> str:
    text = TAG.sub(" ", fragment)
    text = (text.replace("&#160;", " ").replace("&amp;", "&")
            .replace("&#8217;", "'").replace("&nbsp;", " ")
            .replace("&lt;", "<").replace("&gt;", ">"))
    return re.sub(r"\s+", " ", text).strip()


# Only these reports can answer a capex question, so only these are fetched. The
# first version fetched every R-file in every filing -- 1,535 requests for a
# question three documents answer -- which is both slow and a discourtesy.
def _interesting(report) -> bool:
    name = (report["short_name"] or "").lower()
    return any(k in name for k in (
        "cash flow", "cash flows", "property, plant", "property plant",
        "fixed asset", "investing activit"))


def locate(get_text, report_list, local_name) -> list:
    """
    Which statements and notes render this concept, on which line, under which
    section, and with what values.

    The section is the part that decides it. "Cash Flows from Investing Activities"
    is a measurement basis; a "Property, plant and equipment" note is an asset
    roll-forward. A concept can sit in either and mean something entirely
    different, and only the presentation says which.
    """
    hits = []
    for report in report_list:
        if not _interesting(report):
            continue
        body = get_text(report["url"])
        if not body or local_name not in body:
            continue
        # Section headers are positional, so collect them once with their offsets
        # and take the nearest preceding one for each fact.
        sections = [(m.start(), _plain(m.group(1)))
                    for m in SECTION.finditer(body)]
        sections = [(pos, text) for pos, text in sections
                    if text and len(text) < 90]
        rows = []
        for row_match in ROW.finditer(body):
            row = row_match.group(0)
            found = [m for m in FACT_ANCHOR.finditer(row)
                     if m.group("defref").rsplit("_", 1)[-1] == local_name]
            if not found:
                continue
            label = ""
            for anchor in ANCHOR_TEXT.finditer(row):
                if (anchor.string if hasattr(anchor, "string") else row
                        ).find(found[0].group("defref")) >= 0 or True:
                    candidate = _plain(anchor.group("label"))
                    if candidate:
                        label = candidate
                        break
            section = ""
            for pos, text in sections:
                if pos < row_match.start():
                    section = text
                else:
                    break
            values = [_plain(c) for c in NUMERIC_CELL.findall(row)]
            rows.append({"row_label": label, "section": section,
                         "values": values})
        if rows:
            lowered = report["short_name"].lower()
            hits.append({
                "report_file": report["file"],
                "short_name": report["short_name"],
                "menu_category": report["menu_category"],
                "is_cash_flow_statement": any(
                    k in lowered for k in ("cash flow", "cash flows")),
                "is_ppe_note": any(
                    k in lowered for k in
                    ("property, plant", "property plant", "fixed asset")),
                "sections_found": sorted({r["section"] for r in rows if
                                          r["section"]}),
                "rows": rows,
            })
    return hits


def main():
    provider, get_text = fetcher()
    docs = held_documents()
    results = {}
    substitutions = []

    for concept, spec in CANDIDATES.items():
        per_filer = []
        used_filer = None
        for filer in spec["priority_filers"]:
            path = docs.get(filer)
            if not path:
                continue
            doc = json.load(open(path, encoding="utf-8"))
            cik = int(str(doc["cik"]).zfill(10))
            accessions = accessions_for(path, spec["taxonomy"],
                                        spec["local_name"])
            if not accessions:
                continue
            accession = accessions[-1]
            report_list = reports(get_text, cik, accession)
            if not report_list:
                continue
            hits = locate(get_text, report_list, spec["local_name"])
            if not hits:
                continue
            per_filer.append({
                "filer": filer, "cik": cik, "accession": accession,
                "reports_in_filing": len(report_list),
                "reports_mentioning_the_concept": hits,
            })
            if used_filer is None:
                used_filer = filer
            break
        results[concept] = {
            "label": spec["label"],
            "priority_filers_considered": spec["priority_filers"],
            "filer_resolved": used_filer,
            "filings": per_filer,
        }
        if not per_filer:
            substitutions.append({
                "candidate": concept,
                "outcome": "no primary document could be retrieved for any "
                           "priority filer",
            })

    result = {
        "experiment": "2.36 primary-source capex context resolution",
        "evidence_rule": "filing presentation is the semantic anchor; names, "
                         "period shape, sign, value equality and co-movement "
                         "are supporting observations only",
        "requests_made": provider.requests_made,
        "bytes_downloaded": provider.bytes_downloaded,
        "candidates": results,
        "substitutions_recorded": substitutions,
    }
    with open(os.path.join(H, "236-primary-capex-context.json"), "w",
              encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, sort_keys=True, default=str)
    return result


if __name__ == "__main__":
    r = main()
    print(f"requests: {r['requests_made']}   "
          f"bytes: {r['bytes_downloaded']/1e6:.1f} MB\n")
    for concept, row in r["candidates"].items():
        print(f"[{row['label']}] {concept}")
        if not row["filings"]:
            print("   no primary document retrieved")
            continue
        for filing in row["filings"]:
            print(f"   filer {filing['filer']} (cik {filing['cik']}) "
                  f"accession {filing['accession']}  "
                  f"{filing['reports_in_filing']} reports in the filing")
            for hit in filing["reports_mentioning_the_concept"]:
                print(f"      {hit['report_file']:<10} "
                      f"[{hit['menu_category'] or '?':<20}] "
                      f"{hit['short_name'][:58]}")
                print(f"          cash_flow_statement="
                      f"{hit['is_cash_flow_statement']}"
                      f"  ppe_note={hit['is_ppe_note']}")
                print(f"          sections: {hit['sections_found']}")
                for row in hit["rows"][:4]:
                    print(f"          [{row['section'] or '(none)':<42}]"
                          f" {row['row_label'][:42]:<44} {row['values']}")
        print()