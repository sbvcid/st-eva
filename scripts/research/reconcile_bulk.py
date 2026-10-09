"""
Fetch the source inventory a bulk bootstrap would be built from, and reconcile a
bulk-built archive against an API-built one.

Two things, and the second is the one that matters.

**Fetch.** The nightly `companyfacts` archive is one file per issuer and contains
every concept that issuer has ever tagged. Per company that is **one document**
where the API path spends twenty-three requests, and that ratio is the entire
economic argument for bulk at population scale. This fetches the same
per-issuer documents the archive contains, so the reconciliation can run against
real data rather than a fixture.

**Reconcile.** 2.11 measured the incremental path at 23.4 requests per company
and a second pass at zero, and said the untested link was the one between a bulk
bootstrap and an incremental archive. So: build an archive through the bulk
source, build the same archive through the API source, and say **precisely**
where they agree and where they do not.

The classification is the deliverable, and it has to distinguish four things
rather than count differences:

    MATCHED        the same observation, from both paths
    ONLY_IN_API    an observation the API path produced and bulk did not
    ONLY_IN_BULK   an observation bulk produced and the API path did not
    DIVERGENT      the same metric, period and source fact, different value

`DIVERGENT` is the one that must never be tolerated silently, and it is the one
a naive diff would bury under tens of thousands of `MATCHED`. Two sources
disagreeing about a *value* is either a corrected filing -- which this archive
represents as a new observation rather than an update, by design -- or a bug, and
the reconciliation says which it found rather than leaving it to a reader.

`PROVENANCE_ONLY` is the expected difference and is reported separately: the same
fact read from two different documents is attributed to two different provenance
bytes, which is honest on both sides and is not a disagreement about anything.
"""

from __future__ import annotations

# Keep repository modules, repository-relative data paths, and sibling research
# scripts available after this utility is stored under scripts/research/.
import os as _os
import sys as _sys
from pathlib import Path as _Path

_SCRIPT_DIR = _Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parents[1]
for _path in (str(_REPO_ROOT), str(_SCRIPT_DIR)):
    if _path not in _sys.path:
        _sys.path.insert(0, _path)

import argparse
import json
import os
import sqlite3
import sys
import time
from collections import Counter
from typing import Any, Dict, List, Optional, Sequence, Tuple

HERE = str(_REPO_ROOT)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from core_registry import CoreRegistry  # noqa: E402
from registry_seed import seed  # noqa: E402
from sec_bulk import TICKER_MAP_NAME, BulkFactsSource  # noqa: E402
from sec_ingest import Ingestor  # noqa: E402
from sec_provider import SECProvider, normalize_cik  # noqa: E402
from sqlite_archive import SQLiteArchive  # noqa: E402


def canonical_metrics(registry: CoreRegistry) -> Tuple[str, ...]:
    """
    `status = 'ACTIVE'` from the registry, read at run time.

    The same predicate the coverage universe, the cross-framework verifier and the
    evidence surface apply. It replaces leaving the metric list to `Ingestor`'s
    parameter default, which still names `debt` -- superseded in 2.33 and
    permanently closed as a canonical target -- and omits thirteen metrics the
    canonical universe contains.

    A query and not a frozen tuple, because a frozen list and a registry can only
    agree until the registry moves.
    """
    return tuple(
        row["metric_id"]
        for row in registry.connection.execute(
            "SELECT metric_id FROM metric_registry WHERE status = 'ACTIVE'"
            " ORDER BY metric_id"
        )
    )

MATCHED = "MATCHED"
ONLY_IN_API = "ONLY_IN_API"
ONLY_IN_BULK = "ONLY_IN_BULK"
DIVERGENT = "DIVERGENT"
PROVENANCE_ONLY = "PROVENANCE_ONLY"

VERDICTS = (MATCHED, ONLY_IN_API, ONLY_IN_BULK, DIVERGENT)


def fetch_inventory(
    tickers: Sequence[str],
    out_dir: str,
    user_agent: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    One `companyfacts` document per issuer, which is what a bulk archive delivers.

    Written one file per issuer rather than assembled into an archive because the
    *interface* under test is "a directory of documents a bulk source reads", and
    building a zip here would test the zip rather than the reconciliation. The zip
    is a delivery format; the question is whether two delivery formats produce
    the same evidence.
    """
    from sec_provider import SECProvider as _Provider

    provider = _Provider(user_agent=user_agent) if user_agent else _Provider()
    os.makedirs(out_dir, exist_ok=True)
    written: Dict[str, Dict[str, Any]] = {}
    ticker_map: Dict[str, str] = {}
    for ticker in tickers:
        company = provider.resolve_company(ticker)
        if company is None:
            written[ticker] = {"ok": False, "detail": "unresolved ticker"}
            continue
        url = (
            "https://data.sec.gov/api/xbrl/companyfacts/"
            f"CIK{normalize_cik(company.cik)}.json"
        )
        path = os.path.join(out_dir, f"{company.cik}.json")
        try:
            import urllib.request

            request = urllib.request.Request(
                url, headers={"User-Agent": provider.user_agent}
            )
            with urllib.request.urlopen(request, timeout=300) as response:
                body = response.read()
        except Exception as error:  # noqa: BLE001
            written[ticker] = {
                "ok": False, "detail": f"{type(error).__name__}: {error}",
            }
            continue
        with open(path, "wb") as handle:
            handle.write(body)
        written[ticker] = {
            "ok": True,
            "cik": normalize_cik(company.cik),
            "bytes": len(body),
            "path": path,
        }
        ticker_map[ticker.upper()] = normalize_cik(company.cik)
    # Written beside the documents, because a bulk archive is keyed by CIK and
    # says nothing about tickers. The bulk source must not invent that mapping
    # from a company name.
    with open(
        os.path.join(out_dir, TICKER_MAP_NAME), "w", encoding="utf-8"
    ) as handle:
        json.dump(ticker_map, handle, indent=2, sort_keys=True)
    return written


def build_bulk_archive(
    target: str,
    facts_dir: str,
    tickers: Sequence[str],
    submissions_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    An archive built entirely through the bulk source.

    The same `Ingestor`, unmodified. If a bulk bootstrap needed its own ingestion
    path then a bulk-built archive and an API-built one would be two different
    archives that happened to share a name, and reconciling them would prove
    nothing.

    The metric scope is read from the registry rather than left to `Ingestor`'s
    parameter default, for the same reason the reconciliation has to be meaningful
    at all: this archive has to cover the same canonical metric set as the API-built
    one it is compared against. A default-driven bulk pass would cover a different
    set -- one naming `debt`, which 2.33 superseded, and omitting thirteen metrics
    the canonical universe contains -- and the reconciliation would then be
    comparing two different questions.
    """
    if os.path.exists(target):
        os.remove(target)
    store = SQLiteArchive(target)
    registry = CoreRegistry(store.connection)
    seeded = seed(registry)
    metrics_in_scope = canonical_metrics(registry)
    source = BulkFactsSource(
        facts_dir, submissions_directory=submissions_dir, label="bulk"
    )
    reports = []
    started = time.monotonic()
    for ticker in tickers:
        report = Ingestor(store, source, registry).ingest(
            ticker, metrics=metrics_in_scope)
        reports.append(report.contract_dict())
    elapsed = time.monotonic() - started
    size = os.path.getsize(target)
    store.close()
    return {
        "seeded": seeded,
        "target": target,
        "companies": len(reports),
        "elapsed_seconds": round(elapsed, 1),
        "archive_bytes": size,
        "megabytes_per_company": round(size / 1e6 / max(len(reports), 1), 2),
        "outcomes": dict(Counter(r["outcome"] for r in reports)),
        "totals": {
            key: sum(r[key] for r in reports)
            for key in (
                "filings_ingested", "observations_stored",
                "source_facts_stored", "documents_stored",
            )
        },
        "transport": source.transport_stats(),
        "reports": reports,
    }


def _observations_by_key(path: str) -> Dict[Tuple[str, str, str, str], Dict[str, Any]]:
    """
    Index an archive's observations by what makes them *the same observation*.

    Keyed on asset, metric, period end and source fact id. Deliberately not on
    the value: including it would turn every legitimate correction into a match
    with itself and hide the one disagreement that matters.
    """
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    index: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {}
    for row in connection.execute(
        "SELECT a.ticker AS ticker, o.metric AS metric, o.period_end AS period_end,"
        " o.source_fact_id AS source_fact_id, o.value_json AS value_json,"
        " o.accession AS accession, o.source_concept_ref AS source_concept_ref,"
        " (SELECT os.document_id FROM observation_sources os"
        "  WHERE os.observation_id = o.observation_id LIMIT 1) AS document_id"
        " FROM observations o JOIN assets a ON a.asset_id = o.asset_id"
    ):
        index[
            (
                str(row["ticker"]).upper(),
                str(row["metric"]),
                str(row["period_end"]),
                str(row["source_fact_id"]),
            )
        ] = dict(row)
    connection.close()
    return index


def reconcile(api_archive: str, bulk_archive: str) -> Dict[str, Any]:
    """
    Compare two archives over the issuers they share, and classify every
    difference.
    """
    api = _observations_by_key(api_archive)
    bulk = _observations_by_key(bulk_archive)
    shared_assets = {key[0] for key in api} & {key[0] for key in bulk}

    verdicts: Counter = Counter()
    differences: List[Dict[str, Any]] = []
    provenance_only = 0
    for key in sorted(shared_assets and api or api):
        if key[0] not in shared_assets:
            continue
        if key not in bulk:
            verdicts[ONLY_IN_API] += 1
            if len(differences) < 200:
                differences.append({"verdict": ONLY_IN_API, "key": list(key),
                                   "api": api[key]})
            continue
        left, right = api[key], bulk[key]
        if left["value_json"] != right["value_json"]:
            verdicts[DIVERGENT] += 1
            if len(differences) < 200:
                differences.append({"verdict": DIVERGENT, "key": list(key),
                                   "api": left, "bulk": right})
            continue
        if left["document_id"] != right["document_id"]:
            # The same value, read from two different documents. Expected, and
            # not a disagreement about anything.
            provenance_only += 1
            verdicts[MATCHED] += 1
            continue
        verdicts[MATCHED] += 1
    for key in bulk:
        if key[0] in shared_assets and key not in api:
            verdicts[ONLY_IN_BULK] += 1
            if len(differences) < 200:
                differences.append({"verdict": ONLY_IN_BULK, "key": list(key),
                                   "bulk": bulk[key]})

    return {
        "api_observations": len(api),
        "bulk_observations": len(bulk),
        "issuers_compared": sorted(shared_assets),
        "verdicts": dict(verdicts),
        "provenance_only_differences": provenance_only,
        "differences_sample": differences[:40],
        "unexplained": {
            "only_in_api": verdicts[ONLY_IN_API],
            "only_in_bulk": verdicts[ONLY_IN_BULK],
            "divergent_values": verdicts[DIVERGENT],
        },
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--facts-dir",
        help="directory of companyfacts documents, one per issuer",
    )
    parser.add_argument(
        "--submissions-dir", help="optional directory of submissions documents"
    )
    parser.add_argument("--issuer", action="append", default=[])
    parser.add_argument(
        "--api-archive",
        help="an existing archive built through the API source",
    )
    parser.add_argument(
        "--reconcile-only",
        action="store_true",
        help="compare two archives and stop",
    )
    parser.add_argument("--out", help="write the result here")
    args = parser.parse_args(argv)

    if args.reconcile_only:
        if not args.facts_dir:
            parser.error("--facts-dir is required for a bulk archive")
        bulk_target = os.path.join(
            os.path.dirname(args.facts_dir.rstrip("\\/")) or ".",
            "snapshot-bulk.sqlite",
        )
        build = build_bulk_archive(
            bulk_target, args.facts_dir, args.issuer, args.submissions_dir
        )
        result: Dict[str, Any] = {"bulk": build}
        if args.api_archive:
            result["reconciliation"] = reconcile(
                args.api_archive, build["target"]
            )
        print(json.dumps(
            {k: v for k, v in result.items() if k != "bulk"}
            | {"bulk": {k: v for k, v in build.items() if k != "reports"}},
            indent=2, sort_keys=True, default=str,
        ))
        if args.out:
            with open(args.out, "w", encoding="utf-8") as handle:
                json.dump(result, handle, indent=2, sort_keys=True, default=str)
        return 0

    if not args.issuer:
        parser.error("--issuer is required")
    written = fetch_inventory(args.issuer, args.facts_dir)
    print(json.dumps(written, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())