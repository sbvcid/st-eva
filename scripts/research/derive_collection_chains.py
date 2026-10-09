"""
Derive collection chains for an archive that has none, without re-ingesting.

`Ingestor.collection_chain` writes one chain per issuer after every run, and
`score_collection_gates.py` consumes them. That works until an archive is built
by a path that does not write them: `ingest_universe.py` built
`snapshot-universe.sqlite`, 75 issuers and 54,602 observations, and **no chains**.
So the largest population archive in this repository could not be put through the
same eight gates as every other one, which is exactly the archive whose coverage
most needs measuring.

The chains are recoverable. `coverage_semantics.collection_chain` is a pure
function of the archive and the registry -- the ledger, the adoption rows, the
declines, the applicability ruling -- and every one of those is already stored.
What is *not* recoverable is the transport accounting a real run recorded: how
many requests it made, how many concepts it fetched, whether it returned early
for want of new filings. `collection_chain` does not carry those, so nothing is
reconstructed here that was not measured. The chains this writes are the coverage
chain, not a run log, and they say so.

The archive is opened **read-only**. Deriving a measurement must not be able to
change the thing measured, and `record_asset` -- which the ingestor path calls on
its way here -- would create an asset row if the ticker were unknown.

    derive_collection_chains.py --snapshot <archive> --out <chain dir>
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
from typing import Dict, List, Optional

HERE = str(_REPO_ROOT)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from core_registry import CoreRegistry  # noqa: E402
from coverage_semantics import collection_chain  # noqa: E402


def open_read_only(path: str) -> sqlite3.Connection:
    """
    A connection that cannot write.

    Not `sqlite3.connect(path)`, which would happily create the file and accept
    writes. A measurement that can alter its subject is not a measurement, and the
    only reliable way to say otherwise is to make it impossible.
    """
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def derive(
    snapshot: str, out_dir: str, issuers: Optional[List[str]] = None
) -> Dict[str, object]:
    connection = open_read_only(snapshot)
    registry = CoreRegistry(connection)

    if issuers:
        wanted = [ticker.upper() for ticker in issuers]
        rows = [
            row for row in connection.execute(
                "SELECT asset_id, ticker FROM assets ORDER BY ticker"
            ) if str(row["ticker"]).upper() in wanted
        ]
        missing = sorted(
            set(wanted) - {str(row["ticker"]).upper() for row in rows}
        )
    else:
        rows = list(connection.execute(
            "SELECT asset_id, ticker FROM assets ORDER BY ticker"
        ))
        missing = []

    os.makedirs(out_dir, exist_ok=True)
    written: List[str] = []
    skipped: List[Dict[str, str]] = []
    totals = {"metrics": 0, "collected": 0, "backlog": 0}

    for row in rows:
        asset_id = str(row["asset_id"])
        ticker = str(row["ticker"]).upper()
        chain = collection_chain(connection, registry, asset_id, ticker)
        with open(
            os.path.join(out_dir, f"{ticker}.json"), "w", encoding="utf-8"
        ) as handle:
            json.dump(chain, handle, indent=2, sort_keys=True, default=str)
        written.append(ticker)
        for key in totals:
            totals[key] += int(chain["totals"].get(key, 0) or 0)

    connection.close()

    # A missing ticker is named, not dropped. The whole point of this tool is that
    # a broken input and an empty input must not look alike -- 2.13's empty
    # `tickers.json` produced a run that reported no errors and collected nothing.
    for ticker in missing:
        skipped.append({
            "ticker": ticker,
            "reason": "the archive holds no asset with this ticker",
        })

    return {
        "snapshot": snapshot,
        "out_dir": out_dir,
        "issuers_written": len(written),
        "issuers_skipped": skipped,
        "metric_issuers": totals["metrics"],
        "collected": totals["collected"],
        "backlog_items": totals["backlog"],
        "note": (
            "coverage chain only. No transport accounting is reconstructed: "
            "request counts and early returns are properties of a run, and this "
            "derives them from stored evidence."
        ),
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--issuer", action="append")
    parser.add_argument("--json")
    args = parser.parse_args(argv)

    result = derive(args.snapshot, args.out, args.issuer)
    print(f"archive:  {os.path.basename(args.snapshot)}")
    print(f"written:  {result['issuers_written']} chains to {args.out}")
    print(
        f"metrics:  {result['metric_issuers']} metric-issuers, "
        f"{result['collected']} collected, "
        f"{result['backlog_items']} backlog items"
    )
    if result["issuers_skipped"]:
        print("skipped, by reason:")
        for entry in result["issuers_skipped"]:
            print(f"   {entry['ticker']}: {entry['reason']}")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2, sort_keys=True, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
