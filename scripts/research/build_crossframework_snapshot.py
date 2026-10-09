"""
Build the cross-framework archive, and prove the sealed one is untouched.

Two archives, for a reason that is easy to get wrong. The sealed evaluation
snapshot is AAPL-only and every number in 2.1 through 2.6 was read out of it; the
expected answers in the sealed dataset are *derived from the archive*, so
extending that file changes the ground truth under a closed evaluation. The
cross-framework archive is therefore a separate file, and the sealed one is
hashed before and after so that "we did not disturb the baseline" is a
checkable claim rather than an assurance.

Issuers and forms come in as arguments because the forms are not the same for
every issuer and that is the point. A foreign private issuer filing on Form 20-F
has nothing in a 10-K index, so ingesting one without saying so produces an
*empty* archive rather than a thin one -- which looks like a semantic failure and
is a filing-form mismatch.

The synthetic single-issuer evidence the evaluation snapshot appends is left out
(`include_fixture=False`). Those rows are evaluation scaffolding for one issuer's
difficult shapes, and putting one issuer's synthetic disagreement inside a
cross-framework archive would leave a reader unable to tell which rows came from
EDGAR.
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
import hashlib
import json
import os
import sys
from typing import Dict, List, Optional, Sequence, Tuple

HERE = str(_REPO_ROOT)
if HERE not in sys.path:
    sys.path.insert(0, HERE)
sys.path.insert(
    0,
    os.path.join(
        HERE, "experiments", "003-llm-evidence-retrieval"
    ),
)

from core_registry import CoreRegistry  # noqa: E402
from registry_seed import seed  # noqa: E402
from sec_ingest import Ingestor  # noqa: E402
from sec_provider import SECProvider  # noqa: E402
from sqlite_archive import SQLiteArchive  # noqa: E402

SEALED = os.path.join(
    HERE, "experiments", "003-llm-evidence-retrieval", "harness", "snapshot.sqlite"
)
DEFAULT_TARGET = os.path.join(
    HERE,
    "experiments",
    "003-llm-evidence-retrieval",
    "harness",
    "snapshot-crossframework.sqlite",
)

# The metrics the 2.7 brief put in scope. Not the ingestion default of eight:
# `capex` is already a Core metric so ingesting it would be harmless, but a run
# that quietly tests more than it says is a run whose scope nobody wrote down.
DEFAULT_METRICS = (
    "revenue",
    "net_income",
    "eps_diluted",
    "assets",
    "cash",
    "debt",
    "shares_outstanding",
)

# The issuers, each with the forms it actually files. AAPL's live evidence is
# included so the regression can be read against the sealed baseline and so the
# same registry demonstrably serves both frameworks in one file.
DEFAULT_ISSUERS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("AAPL", ("10-K", "10-Q")),
    ("MSFT", ("10-K", "10-Q")),
    ("MU", ("10-K", "10-Q")),
    ("NVDA", ("10-K", "10-Q")),
    ("TSM", ("20-F",)),
    ("NU", ("20-F",)),
)

# The full Core metric set, not the 2.7 subset. 2.9 is the round that fills the
# database, and the seven metrics that held nothing in 2.8 had no declared
# concept to ask the source about -- so this is a registry round as much as a
# collection one.
ALL_METRICS = (
    "revenue",
    "net_income",
    "gross_profit",
    "operating_income",
    "r_and_d",
    "interest_expense",
    "income_tax",
    "cash",
    "debt",
    "assets",
    "equity",
    "operating_cash_flow",
    "capex",
    "sbc",
    "eps_diluted",
    "weighted_average_diluted_shares",
    "shares_outstanding",
    "sga",
    "long_term_debt_current",
    "long_term_debt_noncurrent",
)


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build(
    target: str,
    issuers: Sequence[Tuple[str, Sequence[str]]] = DEFAULT_ISSUERS,
    metrics: Sequence[str] = DEFAULT_METRICS,
    fresh: bool = True,
    chain_dir: Optional[str] = None,
) -> Dict[str, Dict[str, object]]:
    if fresh and os.path.exists(target):
        os.remove(target)
    store = SQLiteArchive(target)
    registry = CoreRegistry(store.connection)
    seeded = seed(registry)
    reports: Dict[str, Dict[str, object]] = {}
    for issuer, forms in issuers:
        ingestor = Ingestor(store, SECProvider(), registry)
        report = ingestor.ingest(
            issuer, metrics=tuple(metrics), forms=tuple(forms)
        )
        # The collection chain is written per run, not summarised at the end, so
        # that a later run can be compared with an earlier one rather than only
        # with the current state of the archive.
        chain = ingestor.collection_chain(issuer)
        if chain_dir:
            os.makedirs(chain_dir, exist_ok=True)
            path = os.path.join(chain_dir, f"{issuer.upper()}.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(chain, handle, indent=2, sort_keys=True, default=str)
        reports[issuer.upper()] = {
            **report.contract_dict(),
            "collection_chain": chain["totals"],
        }
    store.close()
    return {"seeded": seeded, "ingested": reports}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", default=DEFAULT_TARGET)
    parser.add_argument(
        "--append",
        action="store_true",
        help="add issuers to an existing archive instead of rebuilding",
    )
    parser.add_argument(
        "--chain-dir",
        default=os.path.join(os.path.dirname(DEFAULT_TARGET), "collection"),
        help="where to write the per-run collection chain, one file per issuer",
    )
    parser.add_argument(
        "--metrics",
        help="comma-separated metrics; defaults to the full Core set",
    )
    parser.add_argument("--json", help="write the ingestion reports here")
    parser.add_argument(
        "--issuer",
        action="append",
        help="ingest this ticker through the API path, instead of the built-in "
             "cross-framework six. Forms come from --reference, so the form "
             "policy is the filer's own recorded set rather than a hand-written "
             "one: a coverage difference that is really a form-policy difference "
             "is not a finding about coverage.",
    )
    parser.add_argument(
        "--reference",
        help="archive to read each issuer's recorded forms and CIK from, when "
             "--issuer is used",
    )
    args = parser.parse_args(argv)

    metrics = (
        tuple(m.strip() for m in args.metrics.split(",") if m.strip())
        if args.metrics else ALL_METRICS
    )

    issuers = DEFAULT_ISSUERS
    if args.issuer:
        if not args.reference:
            raise SystemExit(
                "--issuer needs --reference: the forms and the CIK are read from "
                "an archive, not guessed, because 2.13's empty-map incident was "
                "a run that reported no errors and collected nothing"
            )
        import sqlite3 as _sqlite3

        connection = _sqlite3.connect(args.reference)
        connection.row_factory = _sqlite3.Row
        resolved = []
        for ticker in args.issuer:
            row = connection.execute(
                "SELECT cik FROM assets WHERE ticker = ?",
                (ticker.upper(),),
            ).fetchone()
            if row is None:
                raise SystemExit(
                    f"the reference archive holds no asset for {ticker!r}"
                )
            if not row["cik"]:
                raise SystemExit(
                    f"the reference archive holds no CIK for {ticker!r}"
                )
            forms = tuple(dict.fromkeys(
                str(r["form"]) for r in connection.execute(
                    "SELECT DISTINCT h.form FROM held_filings h"
                    " JOIN assets a ON a.asset_id = h.asset_id"
                    " WHERE a.ticker = ? AND h.form IS NOT NULL",
                    (ticker.upper(),),
                ) if r["form"]
            )) or ("10-K", "10-Q")
            resolved.append((ticker.upper(), forms))
        connection.close()
        issuers = tuple(resolved)

    before = None
    if os.path.exists(SEALED):
        before = sha256(SEALED)
        print(f"sealed AAPL snapshot before: {before[:16]}")

    result = build(
        args.target, issuers=issuers, metrics=metrics, fresh=not args.append,
        chain_dir=args.chain_dir,
    )
    print(f"seeded: {result['seeded']}")
    print(f"metrics in scope: {len(metrics)}")
    for issuer, report in sorted(result["ingested"].items()):
        print(f"\n=== {issuer}")
        for key in sorted(report):
            if key in ("errors", "concept_fetches", "network_fetches",
                       "documents_reused", "documents_stored",
                       "filings_already_held", "filings_ingested",
                       "filings_seen", "source_facts_skipped",
                       "source_facts_stored", "concepts_unresolved",
                       "dimension_collisions", "observations_skipped",
                       "observations_stored", "run_id", "status", "asset",
                       "cik", "collection_chain"):
                print(f"  {key}: {report[key]}")

    if before is not None:
        after = sha256(SEALED)
        print(f"\nsealed AAPL snapshot after:  {after[:16]}")
        print(f"UNCHANGED: {before == after}")
        if before != after:
            raise SystemExit(
                "the sealed snapshot changed; every 2.1-2.6 result is now "
                "reading a different ground truth"
            )
    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2, sort_keys=True, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())