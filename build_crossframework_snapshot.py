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

import argparse
import hashlib
import json
import os
import sys
from typing import Dict, List, Optional, Sequence, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
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
    ("TSM", ("20-F",)),
    ("NU", ("20-F",)),
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
) -> Dict[str, Dict[str, object]]:
    if fresh and os.path.exists(target):
        os.remove(target)
    store = SQLiteArchive(target)
    registry = CoreRegistry(store.connection)
    seeded = seed(registry)
    reports: Dict[str, Dict[str, object]] = {}
    for issuer, forms in issuers:
        report = Ingestor(store, SECProvider(), registry).ingest(
            issuer, metrics=tuple(metrics), forms=tuple(forms)
        )
        reports[issuer.upper()] = report.contract_dict()
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
    parser.add_argument("--json", help="write the ingestion reports here")
    args = parser.parse_args(argv)

    before = None
    if os.path.exists(SEALED):
        before = sha256(SEALED)
        print(f"sealed AAPL snapshot before: {before[:16]}")

    result = build(args.target, fresh=not args.append)
    print(f"seeded: {result['seeded']}")
    for issuer, report in sorted(result["ingested"].items()):
        print(f"\n=== {issuer}")
        for key in sorted(report):
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