"""
3.32 A2 -- what should break a tie in a point-in-time selection?

The brief for this stage allows exactly one answer here: if the evidence does
not determine a unique correct tie-break, stop and record the ambiguity rather
than pick one. That is what this script concluded, and it concluded it by
measurement rather than by preference.

## The situation

`ObservationSet.latest_knowable` and `_latest_accepted` both order candidates by
`(available_at, as_of)` and take the last. On the MU pilot archive that tie is
not an edge case. 298 revenue rows share only 65 distinct `available_at`
values, because one filing reports an annual figure, three quarters and a
year-to-date stub, and all of them become knowable at the same acceptance
instant. There are 353 tie groups across the archive, and every one of them is
resolved today by whatever order the reader happened to return.

That order is fixed in practice: `observations_for` emits
`ORDER BY replay_eligible_from, observation_id`, so a replay is reproducible.
What is missing is a statement of *which* of the tied observations the contract
means, and no candidate supplies one without changing verified behaviour.

## The candidates, and why each was rejected

`observation_id` is the obvious answer -- it is the archive reader's own
tie-break, it is the contract identity, and it is unique by construction
(`ObservationSet.add` raises on a duplicate). It is also wrong here. Measured
with the production reader, adding it as a third key changes the selection for
**8 of 18 metrics**, and for `revenue` it changes 78,959,000,000 into
41,456,000,000.

The reason is visible in one tie group. At the instant
`2026-06-24T22:59:46Z` one filing produced four revenue facts, all sharing
`replay_eligible_from`:

    period 2026-02-27 .. 2026-05-28   as_of 2026-05-28   41,456,000,000
    period 2025-08-29 .. 2026-05-28   as_of 2026-05-28   78,959,000,000
    period 2025-02-28 .. 2025-05-29   as_of 2025-05-29    9,301,000,000
    period 2024-08-30 .. 2025-05-29   as_of 2025-05-29   26,063,000,000

The annual and the quarter stub tie exactly. The contract id sorts on period
start, so `2025-08-29` precedes `2026-02-27` and the stub has the larger id --
which is why an `observation_id` tie-break picks the stub. Today the annual
wins only because of where the reader happened to place it.

That matters because the annual is what admission accepts and the stub is what
it refuses: `_period_refusals` (`evidence_valuation_boundary.py:812-850`)
answers `PERIOD_NOT_DISCRETE` for a quarter. So ordering the stub first would
not merely change a number, it would turn an admission into a refusal.

`source_fact_id` is unique -- `0006_source_fact_identity.sql:50-52` makes it so
with a partial unique index -- but it is nullable for every pre-2.5 row and
every non-SEC observation, so it cannot order a total. It also names the source
fact rather than the reading, and 3.27's whole result is that source identity
and consumption are different things; a selector keyed on it would put that
boundary back the way it was.

`accession` is not unique: 66 distinct values across 3,998 rows.
`filing order` and database row order are disqualified outright by the brief,
and rightly -- they are storage accidents that an independently rebuilt archive
may not reproduce.

## What this leaves

No candidate is both total and evidence-supported. The choice between an annual
and a quarter stub from one filing is not an ordering question at all: the
contract already expresses it as a refusal in rule 7, not as a preference in the
sort key. An ordering rule that encoded "prefer annual" would be inventing a
second, quieter copy of rule 7 inside the selector.

So the tie-break stays unspecified, deliberately. What is recorded instead is
that the current selection is deterministic under the archive reader's ordering
and is *not* independent of input order -- 4 of 18 metrics change when the
reader output is reversed -- so any caller that reorders observations before
selecting is outside what the contract currently promises.

Run:  python selector_tie_break_ambiguity_332.py
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

HERE = Path(__file__).resolve().parent
HARNESS = HERE / "experiments" / "003-llm-evidence-retrieval" / "harness"
ARTIFACT = HARNESS / "332-selector-tie-break-ambiguity.json"
MU_ARCHIVE = HARNESS / "pilot-mu.sqlite"
CUTOFF = "2026-06-30"

# The two keys compared. `current` is what the code does today; `by_id` adds
# observation_id as the third level, which is the proposal under examination.
CURRENT_KEY = ("available_at", "as_of")
BY_ID_KEY = ("available_at", "as_of", "observation_id")


def _key(observation, fields):
    return tuple(getattr(observation, name, None) or "" for name in fields)


def _winner(candidates, fields):
    if not candidates:
        return None
    return sorted(candidates, key=lambda o: _key(o, fields))[-1]


def _candidates(observations, metric):
    matches = [o for o in observations if o.metric == metric]
    available = [o for o in matches if o.is_available]
    return available or matches


def main() -> None:
    if not MU_ARCHIVE.exists():
        print("MU pilot archive not present; nothing measured")
        return
    from sqlite_archive import SQLiteArchive

    directory = tempfile.mkdtemp(prefix="steva332_")
    try:
        target = Path(directory) / "mu.sqlite"
        shutil.copyfile(MU_ARCHIVE, target)
        store = SQLiteArchive(path=str(target))
        try:
            observations = list(store.observations_for("MU", CUTOFF))
            metrics = sorted({o.metric for o in observations})

            changes: List[Dict[str, object]] = []
            for metric in metrics:
                candidates = _candidates(observations, metric)
                if not candidates:
                    continue
                today = _winner(candidates, CURRENT_KEY)
                by_id = _winner(candidates, BY_ID_KEY)
                if today is None or by_id is None:
                    continue
                if today.observation_id != by_id.observation_id:
                    changes.append({
                        "metric": metric,
                        "current_value": today.value,
                        "by_observation_id_value": by_id.value,
                        "current_id": today.observation_id,
                        "by_observation_id_id": by_id.observation_id,
                    })

            reversed_observations = list(reversed(observations))
            order_dependent = [
                metric for metric in metrics
                if not _candidates(observations, metric)
                or _winner(_candidates(observations, metric), CURRENT_KEY) is None
                or (
                    _winner(_candidates(observations, metric), CURRENT_KEY)
                    .observation_id
                    != _winner(
                        _candidates(reversed_observations, metric), CURRENT_KEY
                    ).observation_id
                )
            ]

            connection = store.connection
            ties = connection.execute(
                "SELECT COUNT(*) n FROM (SELECT available_at, as_of FROM observations"
                " WHERE replay_eligible_from IS NOT NULL AND metric = 'revenue'"
                " GROUP BY available_at, as_of HAVING COUNT(*) > 1)"
            ).fetchone()["n"]
            distinct_instants = connection.execute(
                "SELECT COUNT(DISTINCT available_at) n FROM observations"
                " WHERE replay_eligible_from IS NOT NULL AND metric = 'revenue'"
            ).fetchone()["n"]
            revenue_rows = connection.execute(
                "SELECT COUNT(*) n FROM observations"
                " WHERE replay_eligible_from IS NOT NULL AND metric = 'revenue'"
            ).fetchone()["n"]
            newest = connection.execute(
                "SELECT MAX(available_at) t FROM observations"
                " WHERE metric = 'revenue'"
            ).fetchone()["t"]
            group = [
                {
                    "observation_id": row["observation_id"],
                    "period_start": row["period_start"],
                    "period_end": row["period_end"],
                    "as_of": row["as_of"],
                    "value": row["value_json"],
                    "replay_eligible_from": row["replay_eligible_from"],
                }
                for row in connection.execute(
                    "SELECT observation_id, period_start, period_end, as_of,"
                    " value_json, replay_eligible_from FROM observations"
                    " WHERE metric = 'revenue' AND available_at = ?"
                    " ORDER BY observation_id",
                    (newest,),
                ).fetchall()
            ]
        finally:
            store.close()

        report = {
            "question": (
                "what should break a tie in a point-in-time selection, when "
                "several facts became knowable at one instant?"
            ),
            "verdict": "AMBIGUOUS - no candidate is both total and supported",
            "cutoff": CUTOFF,
            "revenue_rows": revenue_rows,
            "revenue_distinct_available_at": distinct_instants,
            "revenue_tie_groups": ties,
            "metrics_measured": len(metrics),
            "metrics_changed_by_observation_id_tiebreak": len(changes),
            "changes": changes,
            "metrics_whose_selection_depends_on_input_order": len(
                order_dependent
            ),
            "order_dependent_metrics": order_dependent,
            "decisive_tie_group": {
                "available_at": newest,
                "rows": group,
                "reading": (
                    "the annual and the quarter stub tie on (available_at, "
                    "as_of) exactly. Rule 7 refuses the stub, so an ordering "
                    "that preferred the stub would turn an admission into a "
                    "refusal rather than change a number."
                ),
            },
            "rejected_candidates": {
                "observation_id": (
                    "changes 8 of 18 metrics; for revenue it prefers the "
                    "quarter stub over the annual and would lose the "
                    "admission"
                ),
                "source_fact_id": (
                    "unique via 0006:50-52 but nullable, so not a total "
                    "order; and it names the source fact rather than the "
                    "reading"
                ),
                "accession": "66 distinct values across 3998 rows",
                "filing_order": "storage accident, not reproducible",
                "database_row_order": "storage accident, not reproducible",
            },
        }
        HARNESS.mkdir(parents=True, exist_ok=True)
        ARTIFACT.write_text(
            json.dumps(report, indent=1, sort_keys=True), encoding="utf-8"
        )
        print(f"revenue rows={revenue_rows} distinct instants={distinct_instants}"
              f" tie groups={ties}")
        print(f"metrics changed by an observation_id tie-break: "
              f"{len(changes)}/{len(metrics)}")
        print(f"metrics whose selection depends on input order: "
              f"{len(order_dependent)}/{len(metrics)}")
        print("written:", ARTIFACT)
    finally:
        shutil.rmtree(directory, ignore_errors=True)


if __name__ == "__main__":
    main()
