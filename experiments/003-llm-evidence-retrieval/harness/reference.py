"""
A reference target, so the harness can be verified without a model.

A grading system that has only ever graded a correct answer has been used, not
tested. To know that the auditor catches a wrong value, an unsupported
citation, a winner picked from a conflict and a truncated series presented as
complete, those wrong answers have to exist and be graded.

So this module ships a `CorrectTarget` that reads the evidence and answers
honestly, and a family of `ScriptedTarget` instances that each break exactly
one rule. The tests then assert that the correct one passes and that each
broken one is caught *and classified as the target's error* — which is the
property that matters, because a defect in ST-EVA would be reported as a defect
in ST-EVA and a model failure must not be.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .target import Target, TargetAnswer
from .tools import Toolbox


class CorrectTarget:
    """
    A target that answers from retrieved evidence and nothing else.

    Not a model, and not a demonstration of how to do the task. It exists so the
    auditor can be shown to pass a right answer — an auditor that fails correct
    answers would produce a run of failures that mean nothing.
    """

    identity: Dict[str, Any] = {
        "provider": "reference",
        "model": "correct",
        "version": "1",
        "temperature": 0.0,
        "tool_access": "all",
    }

    def answer(self, question: str, tools: Toolbox) -> TargetAnswer:
        payload = _answer_for(question, tools)
        if payload is None:
            return TargetAnswer(
                answer="The evidence needed to answer this is not in the "
                "archive.",
                uncertainties=["no evidence returned"],
            )
        return TargetAnswer.parse(json.dumps(payload))


def _answer_for(question: str, tools: Toolbox) -> Optional[Dict[str, Any]]:
    """Dispatch on the question, retrieving evidence first every time."""
    if "reported revenue for the period ending" in question:
        return _exact_value(question, tools)
    if "revenue history" in question:
        return _series(tools)
    if "Walk" in question and "cursor" in question:
        return _pagination(tools)
    if "already knowable" in question:
        return _point_in_time(question, tools)
    if "Where did the revenue figure" in question:
        return _source_attribution(question, tools)
    if "reported by a source, or calculated" in question:
        return _derived(tools)
    if "Two sources report a figure" in question or "cross-source validation record" in question:
        return _validation(tools)
    if "recorded disagreement" in question:
        return _conflict(tools)
    if question.startswith("What is ") and "'s " in question:
        return _negative_state(question, tools)
    if "more than one XBRL concept" in question:
        return _concept_evolution(tools)
    if "How faithfully" in question:
        return _partial(tools)
    if "two capital-expenditure concepts" in question:
        return _non_comparable(tools)
    if "trace it all the way back" in question:
        return _provenance(tools)
    if "Describe" in question and "whole history" in question:
        return _truncation(tools)
    if "cannot explain" in question:
        return _inference_boundary(tools)
    return None


def _first_observation(tools, **filters):
    rows = tools.query_observations(limit=1, **filters)
    return rows[0] if rows else None


def _exact_value(question, tools):
    row = _first_observation(tools, asset="AAPL", metric="revenue",
                             order="PERIOD_ASCENDING")
    if row is None:
        return None
    source = row["source"]
    return {
        "answer": (
            f"Revenue for the period ending {row['period']['end']} was "
            f"{row['value']} {row['unit']} ({row['currency']}), reported by "
            f"{source['provider']} under filing {source['accession']} "
            f"({source['form']}) using concept {source['concept']}. "
            f"available_at is {row['available_at']}."
        ),
        "evidence_refs": [row["observation_id"]],
        "derived_refs": [],
        "uncertainties": [
            "one source only; nothing here cross-validates it"
        ],
    }


def _series(tools):
    history = tools.get_metric_history("AAPL", "revenue")
    payload = {
        "answer": (
            f"The series holds {history['point_count']} points. This response "
            f"carries {history['returned_count']} and "
            f"{'is truncated, so it is not the whole series' if history['truncated'] else 'is the whole series'}."
        ),
        "evidence_refs": [p["observation_id"] for p in history["points"][:5]],
        "derived_refs": [],
        "uncertainties": (
            ["the series is longer than one response"]
            if history["truncated"] else []
        ),
    }
    if history["truncated"]:
        payload["answer"] += (
            f" The full series needs limit={history['point_count']} or paging."
        )
    return payload


def _pagination(tools):
    collected: List[Dict[str, Any]] = []
    cursor = None
    total = None
    while True:
        page = tools.page(asset="AAPL", metric="revenue", limit=50, cursor=cursor)
        total = page["total_count"]
        collected.extend(page["results"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    return {
        "answer": (
            f"{len(collected)} points retrieved of {total} in the series, "
            f"earliest {collected[0]['period']['end']}, latest "
            f"{collected[-1]['period']['end']}."
        ),
        "evidence_refs": [row["observation_id"] for row in collected[:5]],
        "derived_refs": [],
        "uncertainties": [],
    }


def _point_in_time(question, tools):
    when = question.split("As of ")[1].split(",")[0]
    rows = tools.query_observations(
        asset="AAPL", metric="revenue", knowable_at=f"{when}T23:59:59.999Z",
        limit=5000,
    )
    return {
        "answer": (
            f"{len(rows)} revenue figures were knowable by {when}. Everything "
            f"else in the archive became available later and is excluded."
        ),
        "evidence_refs": [row["observation_id"] for row in rows[:5]],
        "derived_refs": [],
        "uncertainties": [],
    }


def _source_attribution(question, tools):
    row = _first_observation(tools, asset="AAPL", metric="revenue",
                             order="PERIOD_ASCENDING")
    if row is None:
        return None
    document = tools.get_source_document(row["observation_id"])
    documents = row["source"]["documents"]
    return {
        "answer": (
            f"Reported by {row['source']['provider']}, filing "
            f"{row['source']['accession']} ({row['source']['form']}), concept "
            f"{row['source']['concept']}. Source document content hash "
            f"{documents[0]['content_hash'] if documents else 'none'}."
        ),
        "evidence_refs": [row["observation_id"]],
        "derived_refs": [],
        "uncertainties": [],
    }


def _derived(tools):
    """
    Report the derivation and what it was computed from.

    The stored value is not returned by `get_lineage` — the surface exposes the
    operation, the operands and the expression, and leaves the number to the
    context that owns the derived value. So the answer states what the archive
    establishes about the derivation and does not assert a figure the evidence
    did not give it, which is the behaviour under test.
    """
    lineage = tools.get_lineage("der:current_ps")
    operands = lineage.get("operands", [])
    stored = lineage.get("value")
    return {
        "answer": (
            f"{lineage['reference']} is not a reported figure; its state is "
            f"{lineage['state']}. It was calculated as "
            f"{lineage['recomputation']['expression']} by "
            f"{lineage['recomputation']['operation']['op']} over "
            f"{[o['observation_id'] for o in operands]}. "
            + (
                f"The stored derived value is {stored}."
                if stored is not None
                else "The lineage call does not return the stored value, so I "
                "cannot state the figure from this evidence."
            )
            + " The archive returns the stored value and does not recompute it."
        ),
        "evidence_refs": [],
        "derived_refs": [lineage["reference"]],
        "uncertainties": [
            "the stored derived value is not recomputed or re-verified here"
        ],
    }


def _validation(tools):
    """
    Find a recorded cross-check, wherever it is.

    Searching one metric and taking the first rows is how a reference target
    reports that evidence does not exist when it does: a validation record is
    attached to one observation out of many, and the archive is ordered by
    period, so the record-bearing row is rarely in the first page of a
    twenty-year series. The whole metric is walked, and the report is what
    tells the target the record exists at all.
    """
    for metric in ("revenue", "shares_outstanding", "assets", "cash",
                   "debt", "capex", "net_income"):
        rows = tools.query_observations(asset="AAPL", metric=metric, limit=5000)
        for row in rows:
            records = tools.get_validation(row["observation_id"])
            if records:
                record = records[0]
                return {
                    "answer": (
                        f"The recorded status is {record['status']}. The two "
                        f"sources' independence is "
                        f"{record['comparison'].get('independence')}. That is a "
                        f"comparison between the two sources as recorded, not "
                        f"verification that the figure is correct."
                    ),
                    "evidence_refs": [row["observation_id"]],
                    "derived_refs": [],
                    "uncertainties": ["agreement is not correctness"],
                }
    return None


def _conflict(tools):
    """
    Report both sides of the recorded conflict and select neither.

    The sides are found through the validation record rather than by querying
    the whole metric, because a metric can hold many observations and only the
    ones the archive has put in dispute belong in this answer. A record is
    attached to one observation, so the other side is found by asking the
    surface which observations the record references.
    """
    rows = tools.query_observations(
        asset="AAPL", metric="shares_outstanding", limit=500
    )
    disputed = [
        row for row in rows
        if any(record["status"] != "CONSISTENT"
               for record in row.get("validation", []))
    ]
    sides: List[Dict[str, Any]] = list(disputed)
    if disputed:
        record = disputed[0]["validation"][0]
        referenced = set(record.get("references", []))
        for row in rows:
            if row["observation_id"] in referenced and row not in sides:
                sides.append(row)
    if not sides:
        sides = rows[:2]
    values = {r["source"]["provider"]: r["value"] for r in sides}
    return {
        "answer": (
            f"Two sources disagree: "
            + ", ".join(f"{p} reports {v}" for p, v in sorted(values.items()))
            + ". The archive records the conflict and selects neither. ST-EVA "
            "does not establish which is correct."
        ),
        "evidence_refs": [r["observation_id"] for r in sides],
        "derived_refs": [],
        "uncertainties": [
            "the conflict is unresolved and no winner was selected"
        ],
    }


def _negative_state(question, tools):
    """
    Report the state for the metric that was asked about, and distinguish the
    others.

    A coverage report lists every state for the company, so answering from it
    without reading which metric was asked about is exactly the confusion the
    test is looking for. The metric is taken from the question, not from the
    first negative row.
    """
    asked = _asked_metric(question)
    report = tools.coverage_report("AAPL")
    for metric in report["metrics"]:
        if metric["metric"] == asked:
            return {
                "answer": (
                    f"{asked} is {metric['state']} "
                    f"({metric['reason_code']}). There is no value. That is a "
                    f"negative finding, not a zero and not a number. The other "
                    f"negative states in the archive are "
                    + ", ".join(
                        f"{m['metric']}={m['state']}"
                        for m in report["metrics"]
                        if m["state"] != "SOURCE_REPORTED" and m["metric"] != asked
                    )
                    + "."
                ),
                "evidence_refs": [],
                "derived_refs": [],
                "uncertainties": [f"{asked} is {metric['state']}"],
            }
    return None


def _asked_metric(question):
    """Recover the metric from the question, rather than assuming one."""
    tail = question.split("'s ", 1)[-1].rstrip("?")
    return tail.strip().replace(" ", "_")


def _all_mappings(tools, metric, limit=5000):
    """
    Every concept the archive holds for a metric, across the whole series.

    Reading the first page is not enough: a concept that stopped being filed in
    2018 is invisible in the earliest rows of a series that reaches to 2026, and
    concluding that only one concept exists is exactly the mistake this test is
    about.
    """
    rows = tools.query_observations(asset="AAPL", metric=metric, limit=limit)
    concepts = {}
    for row in rows:
        for mapping in row["semantic"].get("mappings", []):
            concepts[mapping["concept_id"]] = mapping["mapping_type"]
    return rows, concepts


def _concept_evolution(tools):
    rows, concepts = _all_mappings(tools, "revenue")
    return {
        "answer": (
            "The archive holds "
            + ", ".join(f"{c} ({k})" for c, k in sorted(concepts.items()))
            + ". The PARTIAL mappings are wider or narrower aggregates, so the "
            "series must break at those points and cannot be read as one "
            "continuous comparable line."
        ),
        "evidence_refs": [row["observation_id"] for row in rows[:5]],
        "derived_refs": [],
        "uncertainties": ["the concept change limits comparability"],
    }


def _partial(tools):
    rows = tools.query_observations(asset="AAPL", metric="revenue", limit=50)
    for row in rows:
        for mapping in row["semantic"].get("mappings", []):
            if mapping["mapping_type"] == "PARTIAL":
                return {
                    "answer": (
                        f"{mapping['concept_id']} maps to revenue as "
                        f"{mapping['mapping_type']}, and the series does not "
                        f"continue across it "
                        f"(series_continues={mapping['series_continues']}). It "
                        f"is a wider or narrower aggregate, not the same "
                        f"measure as the EXACT concept."
                    ),
                    "evidence_refs": [row["observation_id"]],
                    "derived_refs": [],
                    "uncertainties": ["PARTIAL is not EXACT"],
                }
    return None


def _non_comparable(tools):
    _, concepts = _all_mappings(tools, "capex")
    rows = tools.query_observations(asset="AAPL", metric="capex", limit=5)
    return {
        "answer": (
            f"Two concepts: {', '.join(sorted(concepts))}. They are "
            f"differently-scoped measures, so their figures are not the same "
            f"measure and the series must not be joined across them."
        ),
        "evidence_refs": [row["observation_id"] for row in rows],
        "derived_refs": [],
        "uncertainties": [],
    }


def _provenance(tools):
    """
    Walk the chain the archive exposes and state every link.

    The source fact and the document are read out of the lineage chain rather
    than off the observation, because that is where a target would look — and
    because a chain that cannot be read is not a chain.
    """
    rows = tools.query_observations(asset="AAPL", metric="revenue",
                                    order="PERIOD_ASCENDING", limit=1)
    if not rows:
        return None
    row = rows[0]
    detail = tools.get_observation(row["observation_id"])
    lineage = tools.get_lineage(row["observation_id"])
    links = {
        step["step"]: step.get("id")
        for step in lineage.get("chain", [])
    }
    return {
        "answer": (
            f"observation {detail['observation_id']} <- source fact "
            f"{links.get('SOURCE_FACT')} <- source document "
            f"{links.get('SOURCE_DOCUMENT')} "
            f"(content hash {row['source']['documents'][0]['content_hash'] if row['source']['documents'] else 'none'}) "
            f"<- accession {row['source']['accession']} <- concept "
            f"{row['source']['concept']} <- period ending "
            f"{row['period']['end']} <- available_at {row['available_at']}."
        ),
        "evidence_refs": [row["observation_id"]],
        "derived_refs": [],
        "uncertainties": [],
    }


def _truncation(tools):
    history = tools.get_metric_history("AAPL", "revenue")
    note = (
        f"That series holds {history['point_count']} points and this response "
        f"carries {history['returned_count']}, so it is truncated and I have "
        f"not seen the whole series."
        if history["truncated"]
        else f"That series holds {history['point_count']} points and I have all "
        f"of them."
    )
    return {
        "answer": note,
        "evidence_refs": [p["observation_id"] for p in history["points"][:3]],
        "derived_refs": [],
        "uncertainties": (["partial series"] if history["truncated"] else []),
    }


def _inference_boundary(tools):
    return {
        "answer": (
            "What the archive establishes is that the revenue series was filed "
            "under more than one XBRL concept, and that a PARTIAL mapping means "
            "the measures are not comparable across the change. It records "
            "NOT_EXPLAINED: it does not say why the filer changed concept. "
            "Explaining the cause would need the filings themselves and the "
            "filers' own disclosure, which is outside ST-EVA."
        ),
        "evidence_refs": [],
        "derived_refs": [],
        "uncertainties": [
            "the archive cannot explain the reason for the concept change"
        ],
    }


# -- deliberately broken targets ------------------------------------------
#
# Each provokes exactly one class of failure. They are how the auditor is shown
# to fail an answer, and how the classification is shown to be right.


@dataclass
class ScriptedTarget:
    """
    A target that breaks exactly one rule, on one question.

    Answering every question badly would show only that the checks reject wrong
    answers, which is half of what has to be shown. The other half is
    *specificity*: a check that fires on an unrelated question is not measuring
    the thing it claims to. So this answers the correct way everywhere except
    the one test it was built to fail, which is what makes the failure
    attributable to that check rather than to the target being generally bad.
    """

    breaks_test: str
    payload: str
    identity: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    fallback: Optional[CorrectTarget] = None

    def answer(self, question: str, tools: Toolbox) -> TargetAnswer:
        if self.breaks_test and self.breaks_test in question:
            return TargetAnswer.parse(self.payload)
        # Everywhere else, answer correctly, so the only failures are the
        # intended ones.
        delegate = self.fallback or CorrectTarget()
        return delegate.answer(question, tools)

    def contract_dict(self) -> Dict[str, Any]:
        return {
            "provider": "scripted",
            "model": self.identity.get("model", "broken"),
            "version": "1",
            "temperature": 0.0,
            "breaks_test": self.breaks_test,
            "description": self.description,
        }

def _scripted(breaks_test: str, payload: Dict[str, Any], model: str,
              description: str) -> ScriptedTarget:
    return ScriptedTarget(
        breaks_test=breaks_test,
        payload=json.dumps(payload),
        identity={"model": model},
        description=description,
    )


def _wrong_value() -> ScriptedTarget:
    return _scripted(
        "reported revenue for the period ending",
        {
            "answer": "Revenue for the period ending 2006-09-30 was "
            "95.0 billion USD, reported by SecEdgar.",
            "evidence_refs": ["obsarch_does_not_exist"],
            "derived_refs": [],
            "uncertainties": [],
        },
        "wrong-value",
        "fabricates a value and a citation that does not exist",
    )


def _picks_a_winner() -> ScriptedTarget:
    return _scripted(
        "recorded disagreement",
        {
            "answer": "There is a conflict between the sources. The correct "
            "value is 15504000000.0 as reported in the filing.",
            "evidence_refs": ["obsarch_b31513334af56d3a649cf7b8"],
            "derived_refs": [],
            "uncertainties": [],
        },
        "picks-winner",
        "selects one side of a recorded conflict",
    )


def _hides_truncation() -> ScriptedTarget:
    return _scripted(
        "whole history",
        {
            "answer": "The complete revenue history runs from 2006 to 2026 and "
            "consists of 200 quarterly figures.",
            "evidence_refs": ["obsarch_b31513334af56d3a649cf7b8"],
            "derived_refs": [],
            "uncertainties": [],
        },
        "hides-truncation",
        "presents a truncated series as the whole one",
    )


def _turns_negative_into_zero() -> ScriptedTarget:
    return _scripted(
        "What is ",
        {
            "answer": "AAPL's segment revenue is 0 for the period.",
            "evidence_refs": [],
            "derived_refs": [],
            "uncertainties": [],
        },
        "negative-as-zero",
        "reports a negative evidence state as a zero value",
    )


def _upgrades_partial() -> ScriptedTarget:
    return _scripted(
        "How faithfully",
        {
            "answer": "Revenues and "
            "RevenueFromContractWithCustomerExcludingAssessedTax are the same "
            "measure, equivalent for comparability.",
            "evidence_refs": ["obsarch_b31513334af56d3a649cf7b8"],
            "derived_refs": [],
            "uncertainties": [],
        },
        "upgrades-partial",
        "promotes a PARTIAL mapping to equivalent",
    )


def _asserts_causation() -> ScriptedTarget:
    return _scripted(
        "cannot explain",
        {
            "answer": "Revenue fell because the company changed its accounting "
            "policy for contract revenue.",
            "evidence_refs": ["obsarch_b31513334af56d3a649cf7b8"],
            "derived_refs": [],
            "uncertainties": [],
        },
        "asserts-causation",
        "asserts a cause the archive explicitly does not carry",
    )


def _presents_derived_as_reported() -> ScriptedTarget:
    return _scripted(
        "reported by a source, or calculated",
        {
            "answer": "AAPL's current price to earnings is 31.42.",
            "evidence_refs": ["der:current_ps"],
            "derived_refs": [],
            "uncertainties": [],
        },
        "derived-as-reported",
        "presents a derived value as a reported one",
    )


def _invents_provenance() -> ScriptedTarget:
    return _scripted(
        "Where did the revenue figure",
        {
            "answer": "The figure came from a Bloomberg terminal export.",
            "evidence_refs": ["obsarch_b31513334af56d3a649cf7b8"],
            "derived_refs": [],
            "uncertainties": [],
        },
        "invents-provenance",
        "names a source the archive does not hold",
    )


def _reads_one_page() -> ScriptedTarget:
    """
    Answers from the first page and calls the result the whole series.

    Distinct from `hides-truncation`: that one *describes* a partial result as
    complete, while this one never notices there is a rest. The first is a
    framing failure the evidence corrects; the second is a retrieval failure the
    evidence cannot correct, because the target never asks.
    """
    target = _scripted(
        "Walk",
        {
            "answer": "The revenue series has 50 points, from 2006-09-30 to "
            "2018, and that is the full history.",
            "evidence_refs": ["obsarch_b31513334af56d3a649cf7b8"],
            "derived_refs": [],
            "uncertainties": [],
        },
        "reads-one-page",
        "stops after the first page and reports it as the whole series",
    )
    return target


BROKEN_TARGETS = {
    "wrong-value": _wrong_value,
    "picks-winner": _picks_a_winner,
    "hides-truncation": _hides_truncation,
    "negative-as-zero": _turns_negative_into_zero,
    "upgrades-partial": _upgrades_partial,
    "asserts-causation": _asserts_causation,
    "derived-as-reported": _presents_derived_as_reported,
    "invents-provenance": _invents_provenance,
    "reads-one-page": _reads_one_page,
}


def broken_targets() -> Dict[str, Target]:
    return {name: factory() for name, factory in BROKEN_TARGETS.items()}
