"""
Merge a bulk bootstrap into an archive that incremental ingestion has already
touched, and prove the merge is irreversible-safe.

2.12 showed the two delivery paths produce the same evidence when they are the
*only* source. That is the easy direction: nothing existed to overwrite. The
harder one is a bulk bootstrap arriving into an archive an incremental run has
already built, where the two disagree about what exists.

**This is the irreversibility test.** Two asymmetries are created on purpose, both
from real data and neither simulated in the archive:

    metric scope     the incremental archive was built with the older, narrower
                     metric set; the bulk pass runs the full Core set. So the bulk
                     path sees evidence the incremental archive does not have.

    recency          the bulk payload is trimmed by removing each issuer's most
                     recent accessions, which is exactly what a nightly archive
                     built before those filings landed looks like. So the
                     incremental archive has evidence the bulk payload does not.

Both directions of difference are therefore real, and the assertions are:

    bulk-only evidence                added
    already-shared evidence           not duplicated
    incremental-new evidence          preserved, never removed
    same source_fact_id               same identity, across both paths
    different document representation  provenance may differ, semantics may not
    any existing observation          never updated, deleted, or re-identified

and finally the irreversible sequence, run in order against one archive:

    incremental -> bulk -> incremental

whose last step must find every earlier fact under the same
`source_fact_id` and the same `observation_id`.

**The archive already carries `observations_no_update` and `observations_no_delete`
triggers.** This does not trust them: it attempts both against a real row and
records that the database refused, because an append-only guarantee nobody has
watched refuse a write is a comment rather than a guarantee.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from collections import Counter
from typing import Any, Dict, List, Optional, Sequence, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from core_registry import CoreRegistry  # noqa: E402
from registry_seed import seed  # noqa: E402
from sec_bulk import TICKER_MAP_NAME, BulkFactsSource  # noqa: E402
from sec_ingest import DEFAULT_METRICS, Ingestor  # noqa: E402
from sec_provider import SECProvider  # noqa: E402
from sqlite_archive import SQLiteArchive  # noqa: E402

# The Core metric set the bulk pass runs. Deliberately wider than
# `DEFAULT_METRICS`, because a bulk bootstrap being able to deliver a metric an
# older incremental run did not ask for is not a hypothetical -- it is what
# happens the day the Core set grows.
FULL_CORE_METRICS = (
    "revenue", "net_income", "gross_profit", "operating_income", "r_and_d",
    "interest_expense", "income_tax", "cash", "debt", "assets", "equity",
    "operating_cash_flow", "capex", "sbc", "eps_diluted",
    "weighted_average_diluted_shares", "shares_outstanding", "sga",
    "long_term_debt_current", "long_term_debt_noncurrent",
)


def fingerprint(path: str) -> Dict[str, Tuple[str, ...]]:
    """
    Every observation, by identity, with everything that must never change.

    Identity first and value with it: the failure this test exists to catch is not
    a row changing value, it is a row changing *identity* for the same evidence,
    which is the defect 2.5 found once already when a mutable document reference
    was used as identity and the whole history was renumbered.
    """
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    rows = {
        str(row["observation_id"]): (
            str(row["source_fact_id"]),
            str(row["value_json"]),
            str(row["content_hash"]),
            str(row["metric"]),
            str(row["period_end"]),
            str(row["accession"]),
            str(row["source_concept_ref"]),
        )
        for row in connection.execute(
            "SELECT observation_id, source_fact_id, value_json, content_hash,"
            " metric, period_end, accession, source_concept_ref"
            " FROM observations"
        )
    }
    connection.close()
    return rows


def diff(
    before: Dict[str, Tuple[str, ...]],
    after: Dict[str, Tuple[str, ...]],
) -> Dict[str, Any]:
    """
    What changed, split by what the change *means*.

    `removed` and `changed` are the violations. `added` is only interesting when
    it should not have happened.
    """
    removed = sorted(set(before) - set(after))
    changed = sorted(
        key for key in set(before) & set(after) if before[key] != after[key]
    )
    return {
        "before": len(before),
        "after": len(after),
        "added": len(set(after) - set(before)),
        "removed": len(removed),
        "changed": len(changed),
        "removed_sample": removed[:10],
        "changed_sample": [
            {"observation_id": key, "before": before[key], "after": after[key]}
            for key in changed[:5]
        ],
        "irreversible": not removed and not changed,
    }


def duplicate_scan(path: str) -> Dict[str, Any]:
    """
    How many observations share an identity, which is how duplication shows up.

    The fingerprint counts rows, so a bulk pass that added a *second* row for the
    same evidence would look like a successful addition rather than a
    duplication. Duplication is a property of the identity, not of the row count,
    so it has to be asked about the identity.
    """
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    duplicates = [
        dict(row)
        for row in connection.execute(
            "SELECT a.ticker AS ticker, o.metric AS metric,"
            " o.period_end AS period_end, o.source_fact_id AS source_fact_id,"
            " COUNT(*) AS n FROM observations o"
            " JOIN assets a ON a.asset_id = o.asset_id"
            " GROUP BY a.ticker, o.metric, o.period_end, o.source_fact_id"
            " HAVING COUNT(*) > 1"
        )
    ]
    connection.close()
    return {
        "identities_with_more_than_one_observation": len(duplicates),
        "sample": duplicates[:10],
    }


def metrics_held(path: str) -> Dict[str, set]:
    """Which metrics each issuer holds, for the scope-widening measurement."""
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    rows: Dict[str, set] = {}
    for row in connection.execute(
        "SELECT a.ticker AS ticker, o.metric AS metric"
        " FROM observations o JOIN assets a ON a.asset_id = o.asset_id"
    ):
        rows.setdefault(str(row["ticker"]).upper(), set()).add(str(row["metric"]))
    connection.close()
    return rows


def trim_bulk_payload(
    source_dir: str,
    target_dir: str,
    drop_recent: int = 1,
) -> Dict[str, Any]:
    """
    Build a bulk payload that predates the most recent filings.

    By removing each issuer's most recent accessions from its `companyfacts`
    document, which is what an archive built before those filings landed looks
    like. The trimming happens in the *input*, not in the archive: nothing in the
    archive is edited to manufacture a difference, and the archive under test is
    built from the unedited incremental data.
    """
    os.makedirs(target_dir, exist_ok=True)
    ticker_map: Dict[str, str] = {}
    dropped: Counter = Counter()
    for name in sorted(os.listdir(source_dir)):
        if name == TICKER_MAP_NAME:
            continue
        if not name.endswith(".json"):
            continue
        with open(os.path.join(source_dir, name), encoding="utf-8") as handle:
            document = json.load(handle)
        cik = str(document.get("cik") or "").zfill(10)

        newest: List[Tuple[str, str]] = []
        for concepts in (document.get("facts") or {}).values():
            for body in concepts.values():
                for rows in (body.get("units") or {}).values():
                    for row in rows:
                        accn, filed = row.get("accn"), row.get("filed")
                        if accn and filed:
                            newest.append((str(filed), str(accn)))
        cut = sorted({a for _, a in newest}, reverse=True)[:drop_recent]
        dropped_ciks = set(cut)

        removed = 0
        for concepts in (document.get("facts") or {}).values():
            for tag, body in concepts.items():
                for unit, rows in list((body.get("units") or {}).items()):
                    kept = [
                        row for row in rows
                        if str(row.get("accn")) not in dropped_ciks
                    ]
                    removed += len(rows) - len(kept)
                    if kept:
                        body["units"][unit] = kept
                    else:
                        body["units"].pop(unit, None)
        with open(
            os.path.join(target_dir, name), "w", encoding="utf-8", newline="\n"
        ) as handle:
            json.dump(document, handle)
        dropped[cik] = removed

    # The ticker map is **copied, not rebuilt**. The trimmed payload is read by
    # a source that resolves tickers from a map beside the documents, and the
    # first version of this wrote an empty one -- so every issuer resolved to
    # nothing and the bulk pass ingested nothing at all, which is
    # indistinguishable from a merge that had nothing to merge. A source that
    # cannot resolve what it was given must say so, and the empty map is what
    # made the difference between those two invisible.
    source_map = os.path.join(source_dir, TICKER_MAP_NAME)
    if os.path.exists(source_map):
        with open(source_map, encoding="utf-8") as handle:
            ticker_map = json.load(handle)
        with open(os.path.join(target_dir, TICKER_MAP_NAME), "w",
                  encoding="utf-8") as handle:
            json.dump(ticker_map, handle, indent=2, sort_keys=True)

    return {
        "documents": len(dropped),
        "fact_rows_removed": sum(dropped.values()),
        "per_issuer_removed": dict(dropped),
        "note": (
            "The payload is trimmed, not the archive. Nothing in the archive "
            "under test was edited to manufacture a difference."
        ),
    }


def probe_append_only(path: str) -> Dict[str, Any]:
    """
    Try to update and delete a real observation, and record that both are refused.

    An append-only guarantee nobody has watched refuse a write is a comment.
    """
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    row = connection.execute(
        "SELECT observation_id FROM observations LIMIT 1"
    ).fetchone()
    out: Dict[str, Any] = {"row": None}
    if row is None:
        connection.close()
        return out
    observation_id = str(row["observation_id"])
    out["row"] = observation_id
    for label, statement in (
        ("update", "UPDATE observations SET value_json = '0' WHERE observation_id = ?"),
        ("delete", "DELETE FROM observations WHERE observation_id = ?"),
    ):
        try:
            connection.execute(statement, (observation_id,))
            out[label] = "ALLOWED"
            connection.rollback()
        except sqlite3.IntegrityError as error:
            out[label] = f"refused: {error}"
        except sqlite3.OperationalError as error:
            out[label] = f"refused: {error}"
    connection.close()
    return out


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts-dir", required=True)
    parser.add_argument(
        "--issuer", action="append", default=[],
        help="issuers the incremental run covers first",
    )
    parser.add_argument(
        "--bulk-issuer", action="append", default=[],
        help=(
            "issuers the bulk bootstrap covers; a name absent from --issuer is "
            "bulk-only evidence, which is the case a merge has to handle"
        ),
    )
    parser.add_argument("--target", required=True)
    parser.add_argument(
        "--drop-recent", type=int, default=1,
        help="accessions to remove from the bulk payload per issuer",
    )
    parser.add_argument("--out")
    args = parser.parse_args(argv)

    for path in (args.target,):
        if os.path.exists(path):
            os.remove(path)
    trimmed_dir = args.target + "-trimmed"
    if os.path.exists(trimmed_dir):
        for name in os.listdir(trimmed_dir):
            os.remove(os.path.join(trimmed_dir, name))

    trimming = trim_bulk_payload(
        args.facts_dir, trimmed_dir, args.drop_recent
    )
    print(f"trimmed bulk payload: {trimming['fact_rows_removed']} fact rows "
          f"removed from {trimming['documents']} documents", flush=True)

    steps: List[Dict[str, Any]] = []

    # -- step 1: the incremental archive, narrow scope, current data -----
    store = SQLiteArchive(args.target)
    registry = CoreRegistry(store.connection)
    seeded = seed(registry)
    api = SECProvider()
    ingestor = Ingestor(store, api, registry)
    started = time.monotonic()
    for ticker in args.issuer:
        ingestor.ingest(
            ticker, metrics=DEFAULT_METRICS,
            forms=("10-K", "10-Q", "20-F", "40-F"),
        )
    store.close()
    first = fingerprint(args.target)
    metrics_after_one = metrics_held(args.target)
    steps.append({
        "step": "1_incremental_api",
        "issuers": list(args.issuer),
        "metrics_in_scope": list(DEFAULT_METRICS),
        "elapsed_seconds": round(time.monotonic() - started, 1),
        "observations": len(first),
        "metrics_per_issuer": {
            k: len(v) for k, v in sorted(metrics_after_one.items())
        },
    })
    print(f"step 1 incremental (narrow scope): {len(first)} observations "
          f"over {len(args.issuer)} issuers", flush=True)

    # -- step 2: the bulk bootstrap, wider scope, more issuers ----------
    #
    # Two differences on purpose, and the second one is the one that turns out to
    # matter. The bulk pass runs the full Core metric set against issuers the
    # incremental run only partly covered: some issuers are new to it, and the
    # rest are held under a narrower metric scope. That is the ordinary shape of
    # a bulk bootstrap arriving into a live archive, and it is the only way to
    # produce bulk-only evidence that is genuinely bulk-only.
    before_bulk = fingerprint(args.target)
    store = SQLiteArchive(args.target)
    registry = CoreRegistry(store.connection)
    bulk = BulkFactsSource(trimmed_dir, label="bulk-trimmed")
    bulk_ingestor = Ingestor(store, bulk, registry)
    started = time.monotonic()
    for ticker in args.bulk_issuer or args.issuer:
        bulk_ingestor.ingest(
            ticker, metrics=FULL_CORE_METRICS,
            forms=("10-K", "10-Q", "20-F", "40-F"),
        )
    store.close()
    after_bulk = fingerprint(args.target)
    bulk_change = diff(before_bulk, after_bulk)
    metrics_after_bulk = metrics_held(args.target)
    duplicates_after_bulk = duplicate_scan(args.target)
    steps.append({
        "step": "2_bulk_into_incremental",
        "issuers": list(args.bulk_issuer or args.issuer),
        "metrics_in_scope": list(FULL_CORE_METRICS),
        "elapsed_seconds": round(time.monotonic() - started, 1),
        "observations": len(after_bulk),
        "change": bulk_change,
        "metrics_per_issuer": {
            k: len(v) for k, v in sorted(metrics_after_bulk.items())
        },
        "metrics_gained_for_already_held_issuers": {
            ticker: sorted(
                metrics_after_bulk.get(ticker.upper(), set())
                - metrics_after_one.get(ticker.upper(), set())
            )
            for ticker in args.issuer
        },
        "duplicates": duplicates_after_bulk,
    })
    gained = steps[-1]["metrics_gained_for_already_held_issuers"]
    print(f"step 2 bulk merged: +{bulk_change['added']} observations, "
          f"removed={bulk_change['removed']} changed={bulk_change['changed']}",
          flush=True)
    for ticker, metrics in gained.items():
        print(f"        {ticker}: metrics gained by the bulk pass "
              f"{len(metrics)}", flush=True)

    # -- step 3: incremental again, wider scope, identity must not move -
    before_again = fingerprint(args.target)
    store = SQLiteArchive(args.target)
    registry = CoreRegistry(store.connection)
    again = Ingestor(store, SECProvider(), registry)
    started = time.monotonic()
    for ticker in (args.bulk_issuer or args.issuer):
        again.ingest(
            ticker, metrics=FULL_CORE_METRICS,
            forms=("10-K", "10-Q", "20-F", "40-F"),
        )
    store.close()
    after_again = fingerprint(args.target)
    again_change = diff(before_again, after_again)
    metrics_after_three = metrics_held(args.target)
    steps.append({
        "step": "3_incremental_again",
        "issuers": list(args.bulk_issuer or args.issuer),
        "metrics_in_scope": list(FULL_CORE_METRICS),
        "elapsed_seconds": round(time.monotonic() - started, 1),
        "observations": len(after_again),
        "change": again_change,
        "metrics_per_issuer": {
            k: len(v) for k, v in sorted(metrics_after_three.items())
        },
        "duplicates": duplicate_scan(args.target),
    })
    print(f"step 3 incremental again (wider scope): "
          f"+{again_change['added']} observations, "
          f"removed={again_change['removed']} "
          f"changed={again_change['changed']}", flush=True)

    # -- step 4: the fact that survived all three -----------------------
    survived = {
        key: value for key, value in first.items() if key in after_again
    }
    identity_stable = all(
        after_again.get(key) == value for key, value in survived.items()
    )

    # -- step 5: append-only, attempted rather than assumed -------------
    append_only = probe_append_only(args.target)

    result = {
        "seeded": seeded,
        "incremental_issuers": list(args.issuer),
        "bulk_issuers": list(args.bulk_issuer or args.issuer),
        "bulk_only_issuers": sorted(
            set(args.bulk_issuer or args.issuer) - set(args.issuer)
        ),
        "bulk_payload": trimming,
        "steps": steps,
        "identity": {
            "observations_after_step_1": len(first),
            "survived_three_steps": len(survived),
            "lost": len(first) - len(survived),
            "identity_stable": identity_stable,
        },
        "append_only": append_only,
        "duplicates_final": duplicate_scan(args.target),
        "verdict": {
            "bulk_only_evidence_added": any(
                t.upper() in {k.upper() for k in metrics_after_bulk}
                for t in (args.bulk_issuer or args.issuer)
            ) and bulk_change["added"] > 0,
            "incremental_new_preserved": bulk_change["removed"] == 0,
            "nothing_changed": bulk_change["changed"] == 0
            and again_change["changed"] == 0,
            "nothing_removed": bulk_change["removed"] == 0
            and again_change["removed"] == 0,
            "identity_stable": identity_stable,
            "no_duplicate_identities": duplicate_scan(args.target)[
                "identities_with_more_than_one_observation"
            ] == 0,
            "update_refused": str(append_only.get("update", "")).startswith(
                "refused"
            ),
            "delete_refused": str(append_only.get("delete", "")).startswith(
                "refused"
            ),
            # The finding this round produced, stated as a verdict item because
            # it changes what the recommended architecture has to be.
            "bulk_widened_scope_for_held_issuers": any(
                gained.get(ticker) for ticker in gained
            ),
        },
    }
    print("\n" + json.dumps(
        {k: v for k, v in result.items() if k != "steps"}, indent=2,
        sort_keys=True, default=str,
    ))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2, sort_keys=True, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())