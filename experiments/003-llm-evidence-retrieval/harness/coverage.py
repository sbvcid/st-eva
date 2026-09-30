"""
Three axes of coverage, because "we have the data" is three different claims.

2.6.5 produced a result that made this concrete. The archive holds a recorded
cross-source disagreement between a filing and a vendor figure, and P7 -- a probe
built to ask a model to read that record -- failed five runs out of five. The
model was not shown to be unable to interpret independence; it was shown to be
unable to *find* the record, because no search the surface offers returns it.

`cross_source DISCREPANT -> the archive has it -> a query does not surface it`

That gap is invisible in every number this project has reported so far, and it is
the most consequential thing left to measure. An archive's coverage is not one
figure:

    **evidence_coverage**        the archive holds it at all
    **query_discoverability**    a consumer can reach it without already
                                 knowing its identifier
    **semantic_interpretability** a model that found it reads it correctly

The three can disagree in every direction, and each disagreement has a different
remedy. Missing evidence is an ingestion problem. Undiscoverable evidence is a
*surface* problem, and it is the worst of the three: the data is there, so every
count of held rows says the archive is complete, and no consumer can find it
anyway. Unreadable evidence is a model or a labelling problem, and no amount of
ingestion touches it.

Measured here against the sealed AAPL snapshot, from three sources that already
exist: what the archive holds, what the eight operations return without an
identifier, and what the 2.6.5 probe runs found. No requests are sent.

This is the instrument TSM and NU will be measured with. The question those two
issuers pose is not "can it run" -- AAPL, MSFT, MU and NVDA answered that -- it
is whether the semantic model generalises past US-GAAP and past companies that
are ordinary industrials. A coverage axis that cannot say *which* of the three
is thin cannot answer that, and "0 IFRS mappings" on TSM is currently a silent
zero: it is not yet recorded whether that is because IFRS revenue is absent from
the archive, present but unmapped, or mapped and undiscoverable.
"""

from __future__ import annotations

from typing import Any, Dict, List

from .tools import OPERATIONS


def _query_support(query, operation: str) -> str:
    """One line per operation on whether it can be used to *search*."""
    return ""


def measure(
    connection,
    query,
    probe_rows: List[Dict[str, Any]],
    asset: str = "AAPL",
) -> Dict[str, Any]:
    """
    The three axes, for one asset, from the archive and the surface alone.

    Every number here is computed by asking the archive or the eight operations.
    None of it comes from a document, a comment, or an assumption about what the
    surface probably does -- the same discipline as every other measurement in
    this project, and the reason the `as_of` finding in 2.6.5 was findable at
    all.
    """
    asset_id = query._asset_id(asset)
    return {
        "asset": asset,
        "operations": list(OPERATIONS),
        "evidence_coverage": _evidence_coverage(connection, asset_id, asset),
        "query_discoverability": _discoverability(query, connection, asset),
        "semantic_interpretability": _interpretability(probe_rows),
    }


def _evidence_coverage(
    connection,
    asset_id: str,
    asset: str,
) -> Dict[str, Any]:
    """
    Axis one: what the archive holds, by framework and by metric.

    Framework first, because it is the question TSM asks. A metric with no
    observations is a different fact from a metric with observations under a
    framework the registry has never seen, and the second is the one that
    generalisation is actually being tested on.
    """
    by_framework: Dict[str, int] = {}
    for taxonomy, count in connection.execute(
        "SELECT COALESCE(taxonomy, 'NONE'), COUNT(*)"
        " FROM observations WHERE asset_id = ? GROUP BY taxonomy",
        (asset_id,),
    ):
        by_framework[taxonomy] = count

    held = connection.execute(
        "SELECT COUNT(*) FROM observations WHERE asset_id = ?", (asset_id,)
    ).fetchone()[0]
    # DISTINCT, and counted per observation rather than per joined row. A
    # concept can be mapped to more than one metric, so a plain join over the
    # mapping table multiplies observations and can report *more* mapped rows
    # than there are observations -- a coverage figure that comes out negative,
    # which is the fastest way to know a coverage figure is lying.
    mapped = connection.execute(
        "SELECT COUNT(DISTINCT o.observation_id) FROM observations o"
        " JOIN metric_concept_mapping m ON m.concept_id = o.source_concept_ref"
        " WHERE o.asset_id = ? AND o.source_concept_ref IS NOT NULL",
        (asset_id,),
    ).fetchone()[0]

    registered = [
        row[0]
        for row in connection.execute(
            "SELECT metric_id FROM metric_registry WHERE status = 'ACTIVE'"
            " ORDER BY metric_id"
        )
    ]
    with_observations = {
        row[0]
        for row in connection.execute(
            "SELECT DISTINCT metric FROM observations WHERE asset_id = ?",
            (asset_id,),
        )
    }
    without = [m for m in registered if m not in with_observations]
    return {
        "observations_held": held,
        "by_framework": by_framework,
        "observations_mapped_to_a_concept": mapped,
        "observations_unmapped": held - mapped,
        "registered_metrics": len(registered),
        "registered_metrics_with_observations": len(with_observations),
        "registered_metrics_without_observations": without,
        "note": (
            "`registered_metrics_without_observations` is not a gap in the "
            "archive. It is the applicability surface: a metric the registry "
            "declares inapplicable to this issuer's business model is supposed "
            "to have no observations, and the reason it is absent is a finding "
            "rather than a hole."
        ),
    }


def _discoverability(query, connection, asset: str) -> Dict[str, Any]:
    """
    Axis two: what a consumer can reach without already knowing an identifier.

    Every fact class the archive holds about its own evidence, and whether one of
    the eight operations returns it from a search. This is where 2.6.5's P7 lives,
    and the measurement is deliberately blunt: a fact is discoverable if some
    supported query returns it without an observation id, because a consumer that
    has to already know the id to find the id is not searching.
    """
    findings: List[Dict[str, Any]] = []

    def probe(name, question, held, found, via):
        findings.append({
            "fact_class": name,
            "question": question,
            "held": held,
            "discoverable": found,
            "via": via,
        })

    # -- negative states, per metric -------------------------------------
    # `coverage_report` returns a list of per-metric rows, not a mapping.
    states = {
        entry["metric"]: entry
        for entry in query.coverage_report(asset).get("metrics", [])
    }
    negative = {
        metric: entry for metric, entry in states.items()
        if entry.get("state") != "SOURCE_REPORTED"
    }
    probe(
        "negative_states",
        "why is a figure absent for a metric?",
        len(negative),
        len(negative),
        "coverage_report(asset) names the state and its reason code per metric",
    )

    # -- ambiguity groups, per metric -------------------------------------
    total_groups = 0
    found_groups = 0
    for metric in sorted(states):
        rows = query.query_observations(
            asset=asset, metric=metric, period_start="1900-01-01",
            limit=2000,
        )
        seen: set = set()
        for row in rows:
            block = row.get("ambiguity")
            if not block:
                continue
            key = (
                row["metric"],
                row["period"]["start"],
                row["period"]["end"],
            )
            if key in seen:
                continue
            seen.add(key)
            total_groups += 1
            if block.get("reason") and block.get("basis"):
                found_groups += 1
    probe(
        "ambiguity_groups",
        "two figures the archive will not choose between",
        total_groups,
        found_groups,
        "query_observations(metric) attaches the classification and its basis",
    )

    # -- cross-source validation records ----------------------------------
    records = query.connection.execute(
        "SELECT record_id, observation_id, references_json FROM"
        " validation_records WHERE kind = 'cross_source'"
    ).fetchall()
    discoverable = 0
    via = []
    for record in records:
        reachable = False
        for status in (
            "DISCREPANT", "CONFLICTING", "CONSISTENT",
            "CURRENCY_MISMATCH", "UNIT_MISMATCH", "UNVERIFIED",
        ):
            try:
                found = query.query_observations(
                    asset=asset, validation_status=status, limit=1
                )
            except Exception:
                continue
            if found:
                via.append(f"validation_status={status}")
                reachable = True
                break
        if not reachable:
            via.append("get_validation(observation_id) only")
        discoverable += int(reachable)
    probe(
        "cross_source_validation_records",
        "a recorded cross-check between two sources",
        len(records),
        discoverable,
        "; ".join(sorted(set(via))) or "nothing",
    )

    # -- the conflict's own observations ---------------------------------
    conflict = query.connection.execute(
        "SELECT observation_id FROM validation_records"
        " WHERE kind = 'cross_source' ORDER BY record_id LIMIT 1"
    ).fetchone()
    conflict_reachable = False
    if conflict is not None:
        got = query.get_observation(conflict["observation_id"])
        conflict_reachable = got is not None
    probe(
        "the_conflicting_observations",
        "the two figures a cross-source record compares",
        2 if conflict is not None else 0,
        1 if conflict_reachable else 0,
        (
            "get_observation(observation_id) -- reachable only with the id"
            if conflict_reachable else "not reachable"
        ),
    )

    total = sum(f["held"] for f in findings)
    found = sum(f["discoverable"] for f in findings)
    return {
        "facts_held": total,
        "facts_discoverable_by_search": found,
        "rate": round(found / total, 3) if total else None,
        "by_fact_class": findings,
        "note": (
            "'By search' means an operation that does not already take an "
            "observation id. A fact reachable only through "
            "get_observation(observation_id) counts as undiscoverable here, "
            "because a consumer holding that id has already done the work the "
            "search was for."
        ),
    }


def _interpretability(probe_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Axis three: of what a model found, how much did it read correctly.

    Taken from the 2.6.5 probe runs rather than recomputed, because the split
    between understanding and encoding is already recorded per run by
    `split_probe_outcome`, and recomputing it here would be a second place for
    the two to disagree.
    """
    from .consumer import split_probe_outcome

    probes = [r for r in probe_rows if r["test_id"].startswith("probe-")]
    decided = [r for r in probes if r["verdict"] in ("PASS", "FAIL")]
    understood = [
        r for r in decided
        if r["verdict"] == "PASS"
        or split_probe_outcome(r.get("failed_checks", []), False) == "structured"
    ]
    encoded = [r for r in decided if r["verdict"] == "PASS"]
    by_outcome: Dict[str, int] = {}
    for row in decided:
        if row["verdict"] == "PASS":
            kind = "read_and_encoded"
        else:
            kind = split_probe_outcome(row.get("failed_checks", []), False)
        by_outcome[kind] = by_outcome.get(kind, 0) + 1
    for row in probes:
        if row["verdict"] == "E":
            by_outcome["no_answer"] = by_outcome.get("no_answer", 0) + 1
    return {
        "probe_runs": len(probes),
        "decided": len(decided),
        "read_correctly": len(understood),
        "read_rate": round(len(understood) / len(decided), 3) if decided else None,
        "encoded_correctly": len(encoded),
        "joint_rate": (
            round(len(encoded) / len(decided), 3) if decided else None
        ),
        "by_outcome": by_outcome,
        "note": (
            "`read_rate` above `joint_rate` is the finding this axis exists to "
            "make visible: a model whose readings are right and whose encodings "
            "are not needs a different remedy from a model whose readings are "
            "wrong, and the two produce the same pass count."
        ),
    }
