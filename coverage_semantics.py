"""
Coverage semantics: where exactly is coverage low.

A coverage figure answers "how much". It does not answer "why", and without the
why the number cannot be acted on — "3.0% of this filer's concepts" and "3.0% of
the concepts ST-EVA promised to provide" are different sentences with the same
number in them, and 2.7 produced both.

So this module is deliberately narrow. It does **not** redefine coverage against
the source's full concept count, and that refusal is the design:

    XBRL reports 334 concepts for a filer
        -> collecting them all is not the goal and never was
        -> "coverage" measured against that number rewards the wrong behaviour,
           because the cheapest way to raise it is to collect concepts nobody
           asked for, which is the opposite of the product's premise

    ST-EVA's Core Metric Universe
        -> each ACTIVE metric, and the source concepts declared to express it
        -> a coverage figure over that is answerable, and every row in it has an
           owner and a reason

Two universes, and the difference between them is the whole phase:

    **scoped**  the metric and its declared concepts. Computable from the
                archive alone, because the archive holds the declarations.
    **source**  everything the filer actually reports. NOT computable from the
                archive, because ingestion only fetches concepts the registry
                maps. Supplied from outside, and where it is absent the ledger
                says so instead of guessing.

The statuses are all derived from recorded facts. None of them is inferred from
"we have no rows", because "no rows" is the ambiguity this module exists to
remove, and re-deriving it would reproduce the problem in a new file.

    COLLECTED                     the archive holds observations for this issuer
                                  and metric
    MAPPED_NO_CURRENT_OBSERVATION  a concept the issuer was observed reporting,
                                  and the archive holds nothing for it now
    SOURCE_SILENT                  we asked the source, it has nothing
    NOT_YET_COLLECTED              applicable, nothing held, and no run ever
                                  asked for it. A backlog item, and the only
                                  status that is one
    DELIBERATELY_DECLINED           a recorded decision, with a reason code
    UNMAPPED                       the source inventory reports a concept for
                                  this metric and no declaration claims it
    SOURCE_UNAVAILABLE             the source inventory reports no concept for
                                  this metric at all
    NOT_APPLICABLE                 the registry rules the metric out for this
                                  kind of company

The pair the phase was written to keep apart is `NOT_YET_COLLECTED` against
`DELIBERATELY_DECLINED`, and the second against `UNMAPPED`. All three mean "no
observations", all three call for different work, and collapsing them is how a
backlog turns into an argument.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from core_registry import CoreRegistry
from evidence_model import NOT_APPLICABLE, SOURCE_REPORTED

APPLICABLE = "APPLICABLE"

COLLECTED = "COLLECTED"
MAPPED_NO_CURRENT_OBSERVATION = "MAPPED_NO_CURRENT_OBSERVATION"
SOURCE_SILENT = "SOURCE_SILENT"
NOT_YET_COLLECTED = "NOT_YET_COLLECTED"
DELIBERATELY_DECLINED = "DELIBERATELY_DECLINED"
UNMAPPED = "UNMAPPED"
SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
NOT_APPLICABLE_STATUS = NOT_APPLICABLE
# Used only on an archive that cannot record what was asked, and only for
# metrics with nothing held.
#
# Without it such an archive would report every uncollected metric as
# NOT_YET_COLLECTED -- "nobody has ever looked" -- about a metric it plainly
# holds observations for and plainly collected years ago. That is the exact
# confusion this module exists to remove, reappearing as a default. An archive
# that predates the scope record cannot tell "not asked" from "asked and nothing
# came back", and saying UNDETERMINED is the only honest answer it has.
UNDETERMINED = "UNDETERMINED"

# The universe this ledger is measured over. Named, not derived, so a reader
# knows what the denominator was without having to infer it.
SCOPED = "SCOPED_CORE_UNIVERSE"

COVERAGE_STATUSES = (
    COLLECTED,
    MAPPED_NO_CURRENT_OBSERVATION,
    SOURCE_SILENT,
    NOT_YET_COLLECTED,
    DELIBERATELY_DECLINED,
    UNMAPPED,
    SOURCE_UNAVAILABLE,
    NOT_APPLICABLE_STATUS,
    UNDETERMINED,
)

# The only status that is a to-do item. Everything else is either a result or a
# decision, and treating a decision as a backlog item is how an archive ends up
# collecting things somebody already thought about and rejected.
BACKLOG_STATUS = NOT_YET_COLLECTED


def collection_chain(
    connection,
    registry: CoreRegistry,
    asset_id: str,
    ticker: str,
) -> Dict[str, Any]:
    """
    The whole chain for one issuer, per metric, in one object.

    Written after every ingestion run, because the question this phase exists for
    is *"can collection coverage be maintained over ten thousand companies?"*
    and a question about maintenance cannot be answered from a one-off
    measurement. Each metric reports, as separate numbers:

        declared concepts      what the registry says might express it
        adopted concepts       what this filer was observed using
        observed facts         how many facts produced that observation
        collected observations what the archive holds now
        declined               what was considered and rejected, with reasons
        applicability          whether the metric applies to this issuer at all
        status                 where it lands

    The four concept and fact counts are the ones that move between runs, and
    they move for different reasons: a mapping is a decision, adoption is
    evidence about the filer, and observations are what is actually in hand.
    Collapsing them into a coverage percentage is what makes a coverage figure
    impossible to act on.
    """
    ledger = scoped_ledger(connection, registry, asset_id, ticker)
    adoption = {
        row["concept_id"]: row
        for row in connection.execute(
            "SELECT concept_id, first_used, last_used, fact_count, filing_count"
            " FROM issuer_concept_adoption WHERE asset_id = ?", (asset_id,)
        )
    }
    by_metric: Dict[str, Any] = {}
    for row in ledger["rows"]:
        metric = row["metric"]
        used = row["expected_concepts_used"]
        by_metric[metric] = {
            "metric": metric,
            "status": row["status"],
            "is_backlog_item": row["is_backlog_item"],
            "declared_concepts": len(row["expected_concepts"]),
            "adopted_concepts": len(used),
            "observed_facts": sum(
                (adoption[c]["fact_count"] or 0) for c in used
            ),
            "observed_filings": sum(
                (adoption[c]["filing_count"] or 0) for c in used
            ),
            "collected_observations": row["observations_held"],
            "declined_concepts": len(row["declined"]),
            "declined": [
                {"concept_id": d["concept_id"], "reason_code": d["reason_code"]}
                for d in row["declined"]
            ],
            "applicability": (
                NOT_APPLICABLE_STATUS
                if row["status"] == NOT_APPLICABLE_STATUS else APPLICABLE
            ),
            "why": row["why"],
        }
    return {
        "asset": ticker.upper(),
        "business_model": ledger["business_model"],
        "metrics": by_metric,
        "totals": {
            "metrics": ledger["metrics_total"],
            "applicable": ledger["metrics_applicable"],
            "collected": ledger["status_counts"][COLLECTED],
            "backlog": len(ledger["backlog_items"]),
            "declined_concepts": sum(
                len(r["declined"]) for r in ledger["rows"]
            ),
        },
        "note": (
            "Every status except UNDETERMINED is a result or a decision rather "
            "than a gap, and a NOT_APPLICABLE and a SOURCE_SILENT are both "
            "successes. The one status that is work to do is NOT_YET_COLLECTED, "
            "and it is the only one flagged `is_backlog_item`."
        ),
    }


def _scope_rows(connection, asset_id: str):
    """
    The scope records this archive holds, or none at all.

    Reads `NO_CHANGE` runs too, because a run that returned early has asked
    nothing and must not silence the evidence that another run did. The
    `ever_asked` set downstream filters those back out, so a `NOT_ATTEMPTED`
    row recorded by a later run cannot erase an earlier run that reached the
    source.
    """
    has_table = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table'"
        " AND name = 'ingestion_scope'"
    ).fetchone() is not None
    if not has_table:
        return ()
    return connection.execute(
        "SELECT s.metric_id AS metric_id, s.status AS status,"
        " s.mapping_count AS mapping_count"
        " FROM ingestion_scope s JOIN ingestion_runs r ON r.run_id = s.run_id"
        " WHERE s.asset_id = ? ORDER BY s.run_id",
        (asset_id,),
    )


def scoped_ledger(
    connection,
    registry: CoreRegistry,
    asset_id: str,
    ticker: str,
    source_inventory: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    One row per metric in ST-EVA's own Core universe, for one issuer.

    `source_inventory` is the set of concepts the filer actually reports, from
    outside the archive. Optional, and where it is absent the ledger says
    `SOURCE_UNAVAILABLE_UNKNOWN` rather than concluding the filer reports
    nothing — 2.7 established that a registry-driven archive cannot see a
    concept it never asked for, and a coverage ledger that quietly assumed it
    could would report the same confident zero the ingest loop already reports
    for unmapped concepts.
    """
    metric_rows = connection.execute(
        "SELECT metric_id, display_name, status FROM metric_registry"
        " WHERE status = 'ACTIVE' ORDER BY metric_id"
    ).fetchall()
    business = registry.business_model_of(asset_id)
    model = business["business_model"] if business else None

    held = {
        row["metric"]: row["n"]
        for row in connection.execute(
            "SELECT metric, COUNT(*) AS n FROM observations"
            " WHERE asset_id = ? GROUP BY metric", (asset_id,),
        )
    }
    adoption = {
        row["concept_id"]
        for row in connection.execute(
            "SELECT concept_id FROM issuer_concept_adoption"
            " WHERE asset_id = ?", (asset_id,)
        )
    }
    declines: Dict[str, List[Dict[str, Any]]] = {}
    for row in registry.all_declines():
        declines.setdefault(row["considered_for_metric"], []).append(row)

    # The most recent run's scope, per metric, across all runs: "have we ever
    # looked" rather than "did the last run look", because a run that returned
    # early because nothing was new asked nothing and must not silence the
    # evidence that an earlier run did.
    #
    # Absent on an archive predating migration 0012, and empty for the same
    # reason a decline list is: an archive that cannot have recorded what was
    # asked has recorded nothing, so every metric reads as a backlog item rather
    # than as silence.
    scope: Dict[str, Dict[str, Any]] = {}
    scope_rows = _scope_rows(connection, asset_id)
    scope_known = bool(scope_rows)
    for row in scope_rows:
        scope.setdefault(row["metric_id"], {
            "metric_id": row["metric_id"],
            "status": row["status"],
            "mapping_count": row["mapping_count"],
        })
    ever_asked = {
        metric for metric, row in scope.items() if row["status"] != "NOT_ATTEMPTED"
    }
    inventory = set(source_inventory or ())
    inventory_known = source_inventory is not None

    # A decline explains a metric's status only for issuers whose filings could
    # have contained the concept.
    #
    # A US-GAAP segment-reporting element declined for `operating_income` says
    # nothing about an IFRS filer, which has no such element to decline -- and
    # without this filter that filer reported its operating income as
    # DELIBERATELY_DECLINED on the strength of a decision made about another
    # framework's vocabulary. A decision is about a concept, and a concept
    # belongs to a taxonomy; applying a taxonomy-scoped decision to an issuer
    # that never uses that taxonomy attributes a judgement to somebody who did
    # not make it.
    #
    # Filtered only when the taxonomies are actually known. Absent an inventory
    # the declines are left in place, because a decline is a recorded fact about
    # the metric and dropping it would hide a decision that was genuinely made.
    issuer_taxonomies = {
        concept.split(":", 1)[0] for concept in (inventory or ())
    }
    if inventory_known and issuer_taxonomies:
        declines = {
            metric: [
                decline for decline in entries
                if decline["concept_id"].split(":", 1)[0]
                in issuer_taxonomies
            ]
            for metric, entries in declines.items()
        }

    rows: List[Dict[str, Any]] = []
    for metric in metric_rows:
        metric_id = metric["metric_id"]
        definition = registry.metric(metric_id)
        applies = definition.applies_to(model) if definition else True
        mappings = registry.mappings_for_metric(metric_id)
        concepts = sorted({m.concept_id for m in mappings})
        observation_count = held.get(metric_id, 0)
        status, why = _status(
            applies=applies,
            observation_count=observation_count,
            concepts=concepts,
            adoption=adoption,
            scope_row=scope.get(metric_id),
            scope_known=scope_known,
            asked=metric_id in ever_asked,
            declines=declines.get(metric_id, []),
            inventory=inventory,
            inventory_known=inventory_known,
        )
        rows.append({
            "metric": metric_id,
            "display_name": metric["display_name"],
            "status": status,
            "is_backlog_item": status == BACKLOG_STATUS,
            "observations_held": observation_count,
            "expected_concepts": concepts,
            "expected_concepts_used": sorted(
                c for c in concepts if c in adoption
            ),
            # A decline is a fact about a *concept*, so it coexists with the
            # metric being collected through a different one. AAPL's revenue is
            # collected through US-GAAP concepts while four IFRS revenue
            # elements are declined; reporting only the first would say the
            # declines do not apply here, and they are framework judgements, not
            # per-issuer ones.
            "declined": declines.get(metric_id, []) or (
                registry.declines_for_metric(metric_id)
                if not inventory_known else []
            ),
            "mapping_types": sorted({m.mapping_type for m in mappings}),
            "why": why,
        })

    counts: Dict[str, int] = {status: 0 for status in COVERAGE_STATUSES}
    for row in rows:
        counts[row["status"]] += 1
    scored = [r for r in rows if r["status"] != NOT_APPLICABLE_STATUS]
    return {
        "asset": ticker.upper(),
        "universe": SCOPED,
        "universe_note": (
            "ST-EVA's own Core Metric Universe: every ACTIVE metric, and the "
            "source concepts declared to express it. Not the filer's full "
            "concept count, and deliberately so -- measuring against that would "
            "reward collecting concepts nobody asked for."
        ),
        "business_model": model,
        "source_inventory_known": inventory_known,
        "source_inventory_size": len(inventory) if inventory_known else None,
        "scope_known": scope_known,
        "metrics_total": len(rows),
        "metrics_applicable": len(scored),
        "status_counts": counts,
        "backlog_items": sorted(
            r["metric"] for r in rows if r["is_backlog_item"]
        ),
        "collected_rate": (
            round(
                sum(1 for r in scored if r["status"] == COLLECTED) / len(scored),
                3,
            ) if scored else None
        ),
        "rows": rows,
    }


def _status(
    *,
    applies: bool,
    observation_count: int,
    concepts: List[str],
    adoption,
    scope_row: Optional[Dict[str, Any]],
    scope_known: bool,
    asked: bool,
    declines: List[Dict[str, Any]],
    inventory,
    inventory_known: bool,
):
    """
    The derivation, in one place, and ordered so the answer is the *strongest*
    thing known rather than the first thing that happens to be true.

    The order is the argument. `COLLECTED` first because it is the only positive
    fact, and a metric collected through one concept keeps that status even when
    other concepts have been declined against it -- a decline and a collection
    are facts about different concepts, and making them compete would let one
    hide the other. `NOT_APPLICABLE` next because it is a decision about the
    company and outranks anything about collection. Then a decline, which is a
    decision about a concept. Only then what we asked for, and only then what we
    have not.

    Putting the decisions above the fetches is what stops a deliberate refusal
    from being reported as a gap to be filled.
    """
    if not applies:
        return NOT_APPLICABLE_STATUS, (
            "the registry rules this metric out for this issuer's business "
            "model; a statement about the company, not about what has been "
            "collected"
        )
    if observation_count:
        return COLLECTED, (
            f"{observation_count} observations held for this metric"
        )
    if declines:
        named = ", ".join(d["concept_id"] for d in declines)
        return DELIBERATELY_DECLINED, (
            f"no observations, and {named} "
            f"{'was' if len(declines) == 1 else 'were'} considered for this "
            f"metric and declined: "
            f"{declines[0]['reason']}"
        )
    used = [c for c in concepts if c in adoption]
    if used:
        return MAPPED_NO_CURRENT_OBSERVATION, (
            f"{', '.join(used)} was observed reported by this filer and the "
            "archive holds no observation for it now; the mapping window, or "
            "deduplication, or a later concept change accounts for the gap"
        )
    if concepts and asked and scope_row is not None:
        status = scope_row.get("status")
        if status == "SOURCE_SILENT":
            return SOURCE_SILENT, (
                "the source was asked for "
                f"{', '.join(concepts)} and reported nothing for this filer"
            )
    if inventory_known and not concepts:
        if not inventory:
            return SOURCE_UNAVAILABLE, (
                "the source inventory records no concept for this metric for "
                "this filer"
            )
    if not scope_known:
        return UNDETERMINED, (
            "this archive predates the record of what ingestion asked for, so "
            "it cannot say whether this metric was never collected or was "
            "collected and the rows are not here. Reporting it as never asked "
            "would be a confident answer the archive does not have"
        )
    if not asked:
        return NOT_YET_COLLECTED, (
            "applicable, nothing held, and no ingestion run has ever asked for "
            "it. A backlog item."
        )
    if not concepts:
        return UNMAPPED, (
            "no declaration claims a source concept for this metric, and the "
            "run that asked found none"
        )
    return NOT_YET_COLLECTED, (
        "applicable, nothing held, and the concepts that were asked for "
        "returned nothing this filer reports"
    )
