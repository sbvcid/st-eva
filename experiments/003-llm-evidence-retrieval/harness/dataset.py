"""
The questions, and what each one is provably answerable from.

Every test carries its expectations as data read out of the snapshot, not as
values typed by hand. A hard-coded expected number is a test that starts
failing the day a filing is restated, and worse, one that can be satisfied by
an evaluator agreeing with itself. The expectations here are resolved *from the
archive* at load time, so ground truth cannot drift from what the target was
shown.

A test that cannot state its expectations mechanically is not in this dataset.
That is what keeps the optional LLM judge for questions about *framing*, where
the failure is an overstatement rather than a wrong number.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .auditor import Audit, Auditor
from .target import TargetAnswer
from .tools import Toolbox

DATASET_ID = "steva-003-aapl-evidence"
DATASET_VERSION = "1"


@dataclass
class Test:
    """One question, its expectations, and the checks those expectations imply."""

    test_id: str
    class_name: str
    capability: str
    question: str
    audit: Any  # a callable(auditor, audit, answer, tools, retrieved)
    expectations: Dict[str, Any] = field(default_factory=dict)
    rubric: Optional[str] = None
    needs_judge: bool = False

    def expectations_for_review(self) -> Dict[str, Any]:
        return dict(self.expectations)

    def contract_dict(self) -> Dict[str, Any]:
        return {
            "test_id": self.test_id,
            "class": self.class_name,
            "capability": self.capability,
            "question": self.question,
            "expectations": self.expectations,
            "rubric": self.rubric,
            "needs_judge": self.needs_judge,
        }


class Dataset:
    """The question set, resolved against one snapshot."""

    def __init__(self, tests: List[Test], snapshot_path: str) -> None:
        self.tests = tests
        self.snapshot_path = snapshot_path
        self.dataset_id = DATASET_ID
        self.version = DATASET_VERSION

    def contract_dict(self) -> Dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "version": self.version,
            "snapshot": self.snapshot_path,
            "count": len(self.tests),
            "tests": [t.contract_dict() for t in self.tests],
        }


def build_dataset(snapshot_path: str, asset: str = "AAPL") -> Dataset:
    """
    Resolve every expectation against the snapshot.

    The resolution happens here rather than in the checks so that a reviewer can
    read one JSON file and see what every test holds the target to, and so that
    the auditor compares against a fixed value rather than re-deriving one while
    grading.
    """
    import sqlite3

    from evidence_query import EvidenceQuery

    connection = sqlite3.connect(snapshot_path)
    connection.row_factory = sqlite3.Row
    query = EvidenceQuery.open(snapshot_path)

    tests: List[Test] = []

    # -- T1: one exact historical value ---------------------------------
    target = _oldest_observation(connection, asset, "revenue")
    if target is not None:
        tests.append(
            Test(
                test_id="T1_exact_value",
                class_name="T1",
                capability="F1",
                question=(
                    f"What was {asset}'s reported revenue for the period ending "
                    f"{target['period_end']}? Give the figure with its unit and "
                    f"the source that reported it."
                ),
                expectations={
                    "observation_id": target["observation_id"],
                    "value": json.loads(target["value_json"]),
                    "period_end": target["period_end"],
                    "unit": target["unit"],
                    "currency": target["currency"],
                    "accession": target["accession"],
                    "source_concept_ref": target["source_concept_ref"],
                    "source_fact_id": target["source_fact_id"],
                    "provider": target["provider"],
                },
                audit=_audit_t1,
            )
        )

    # -- T2: a multi-year series, and whether it is complete ------------
    history = query.get_metric_history(asset, "revenue")
    tests.append(
        Test(
            test_id="T2_series",
            class_name="T2",
            capability="F2",
            question=(
                f"Give me {asset}'s reported revenue history. State how many "
                f"points the series holds, how many you are giving me, and "
                f"whether that is the whole series."
            ),
            expectations={
                "point_count": history["point_count"],
                "returned_count_default": 200,
                "truncated_by_default": history["truncated"],
            },
            audit=_audit_t2,
        )
    )

    # -- T3: retrieval past the first page ------------------------------
    first_page = query.page(asset=asset, metric="revenue", limit=50)
    tests.append(
        Test(
            test_id="T3_pagination",
            class_name="T3",
            capability="F10",
            question=(
                f"Walk {asset}'s full reported revenue series using the cursor "
                f"until you have every point, then tell me the earliest and "
                f"latest period and the total number of points."
            ),
            expectations={
                "total_count": first_page["total_count"],
                "page_size": 50,
                "requires_cursor": first_page["next_cursor"] is not None,
            },
            audit=_audit_t3,
        )
    )

    # -- T4: what was knowable at a past instant ------------------------
    latest_known = _latest_available_at(connection, asset, "revenue")
    if latest_known is not None:
        cut = latest_known["available_at"][:10]
        before = connection.execute(
            "SELECT COUNT(*) AS n FROM observations WHERE metric = 'revenue'"
            " AND asset_id = (SELECT asset_id FROM assets WHERE ticker = ?)"
            " AND replay_eligible_from IS NOT NULL"
            " AND replay_eligible_from <= ?",
            (asset, f"{cut}T23:59:59.999Z"),
        ).fetchone()["n"]
        tests.append(
            Test(
                test_id="T4_point_in_time",
                class_name="T4",
                capability="F11",
                question=(
                    f"As of {cut}, what reported revenue figures for {asset} "
                    f"were already knowable? Only include what was knowable by "
                    f"that date."
                ),
                expectations={
                    "knowable_at": f"{cut}T23:59:59.999Z",
                    "knowable_count": before,
                    "total_count": history["point_count"],
                },
                audit=_audit_t4,
            )
        )

    # -- T5: where a number came from -----------------------------------
    if target is not None:
        document = connection.execute(
            "SELECT d.document_id, d.content_hash, d.uri, d.provider"
            " FROM observation_sources os"
            " JOIN source_documents d ON d.document_id = os.document_id"
            " WHERE os.observation_id = ? LIMIT 1",
            (target["observation_id"],),
        ).fetchone()
        tests.append(
            Test(
                test_id="T5_source_attribution",
                class_name="T5",
                capability="F4",
                question=(
                    f"Where did the revenue figure for the period ending "
                    f"{target['period_end']} come from? Name the provider, the "
                    f"filing accession, and the source document's content hash."
                ),
                expectations={
                    "observation_id": target["observation_id"],
                    "provider": target["provider"],
                    "accession": target["accession"],
                    "form": target["form"],
                    "document_id": document["document_id"] if document else None,
                    "document_content_hash": (
                        document["content_hash"] if document else None
                    ),
                },
                audit=_audit_t5,
            )
        )

    # -- T6: reported versus derived ------------------------------------
    derived = connection.execute(
        "SELECT ref, value_json, unit, expression, depends_on_json"
        " FROM derived_values LIMIT 1"
    ).fetchone()
    if derived is not None:
        tests.append(
            Test(
                test_id="T6_reported_vs_derived",
                class_name="T6",
                capability="F6",
                question=(
                    f"Was {derived['ref'].split(':')[-1].replace('_', ' ')} for "
                    f"{asset} reported by a source, or calculated? If it was "
                    f"calculated, say what it was calculated from."
                ),
                expectations={
                    "derived_ref": derived["ref"],
                    "value": json.loads(derived["value_json"]),
                    "unit": derived["unit"],
                    "expression": derived["expression"],
                    "operands": json.loads(derived["depends_on_json"]),
                    "state": "DERIVED",
                },
                audit=_audit_t6,
            )
        )

    # -- T7: a recorded cross-check, and how far it reaches -------------
    # T8 covers the DISCREPANT case, so T7 asks the general question: what does
    # a validation record establish, whatever its status. Asking "do they
    # agree" and expecting agreement when the only record is a discrepancy
    # would be a question the archive answers against itself.
    validated = _first_validated(connection)
    if validated is not None:
        comparison = json.loads(validated["comparison_basis_json"])
        tests.append(
            Test(
                test_id="T7_validation",
                class_name="T7",
                capability="F7",
                question=(
                    f"The archive holds a cross-source validation record for a "
                    f"figure reported by {asset}. What status does it carry, "
                    f"and how independently were the two sources obtained?"
                ),
                expectations={
                    "observation_id": validated["observation_id"],
                    "status": validated["status"],
                    "independence": comparison.get("independence"),
                    "explanation": validated["explanation"],
                },
                audit=_audit_t7,
            )
        )

    # -- T8: a conflict, and whether a side is picked -------------------
    conflict = connection.execute(
        "SELECT observation_id, references_json FROM validation_records"
        " WHERE status = 'DISCREPANT' LIMIT 1"
    ).fetchone()
    if conflict is not None:
        # Both sides, from the record's own reference list rather than by
        # re-deriving which observations belong together. The record is where
        # the archive states that these two figures are in dispute, so asking
        # it is the same discipline the auditor applies to the target.
        sides = sorted(set(json.loads(conflict["references_json"])))
        tests.append(
            Test(
                test_id="T8_conflict",
                class_name="T8",
                capability="F8",
                question=(
                    f"There is a recorded disagreement about a figure for "
                    f"{asset}. What are the competing values, and which one is "
                    f"correct?"
                ),
                expectations={
                    "observation_ids": sides,
                    "status": "DISCREPANT",
                    "no_winner": True,
                },
                audit=_audit_t8,
            )
        )

    # -- T9: negative states -------------------------------------------
    state = connection.execute(
        "SELECT * FROM evidence_state WHERE state IN"
        " ('SOURCE_DID_NOT_REPORT', 'UNAVAILABLE', 'NOT_APPLICABLE', 'STALE')"
        " ORDER BY state LIMIT 1"
    ).fetchone()
    if state is not None:
        tests.append(
            Test(
                test_id="T9_unavailable",
                class_name="T9",
                capability="F7",
                question=(
                    f"What is {asset}'s {state['metric'].replace('_', ' ')}?"
                ),
                expectations={
                    "metric": state["metric"],
                    "state": state["state"],
                    "reason_code": state["reason_code"],
                    "all_negative_states": _negative_states(connection, asset),
                },
                audit=_audit_t9,
            )
        )

    # -- T10: concept evolution ----------------------------------------
    tests.append(
        Test(
            test_id="T10_concept_evolution",
            class_name="T10",
            capability="F9",
            question=(
                f"{asset}'s revenue series was reported under more than one XBRL "
                f"concept. Name the concepts the archive holds, and say whether "
                f"they can be read as one continuous comparable series."
            ),
            expectations=_concept_expectations(connection, asset, "revenue"),
            audit=_audit_t10,
        )
    )

    # -- T11: a PARTIAL mapping is not an EXACT one ---------------------
    partial = _partial_mapping_for(connection, asset, "revenue")
    if partial is not None:
        tests.append(
            Test(
                test_id="T11_partial_mapping",
                class_name="T11",
                capability="F9",
                question=(
                    f"Archive figures filed under "
                    f"{partial['concept'].split(':')[-1]} are held for {asset}. "
                    f"How faithfully does that concept express 'revenue', and is "
                    f"it the same measure as the other revenue concepts?"
                ),
                expectations={
                    "concept": partial["concept"],
                    "mapping_type": "PARTIAL",
                    "series_continues": False,
                },
                audit=_audit_t11,
            )
        )

    # -- T12: two capex concepts, kept apart ---------------------------
    capex = connection.execute(
        "SELECT DISTINCT source_concept_ref FROM observations"
        " WHERE metric = 'capex' AND source_concept_ref IS NOT NULL"
    ).fetchall()
    if len(capex) >= 2:
        concepts = sorted(row["source_concept_ref"] for row in capex)
        tests.append(
            Test(
                test_id="T12_non_comparable",
                class_name="T12",
                capability="F9",
                question=(
                    f"The archive holds two capital-expenditure concepts for "
                    f"{asset}. Name them and say whether their figures are the "
                    f"same measure."
                ),
                expectations={
                    "concepts": concepts,
                    "distinct_measures": True,
                },
                audit=_audit_t12,
            )
        )

    # -- T13: the whole provenance chain -------------------------------
    # The same observation T1 asks about, so the trace being verified is the
    # trace the question named. Picking a different one — a cash figure, say —
    # would grade a chain the target was never asked for.
    if target is not None:
        tests.append(
            Test(
                test_id="T13_provenance_chain",
                class_name="T13",
                capability="F5",
                question=(
                    f"Take the revenue figure for the period ending "
                    f"{target['period_end']} and trace it all the way back: "
                    f"observation, source fact, source document, accession, "
                    f"concept, period, and when it became available."
                ),
                expectations={
                    "observation_id": target["observation_id"],
                    "source_fact_id": target["source_fact_id"],
                    "accession": target["accession"],
                    "form": target["form"],
                    "taxonomy": target["taxonomy"],
                    "source_concept_ref": target["source_concept_ref"],
                    "period_start": target["period_start"],
                    "period_end": target["period_end"],
                    "available_at": target["available_at"],
                    "document_content_hash": _document_hash(
                        connection, target["observation_id"]
                    ),
                },
                audit=_audit_t13,
            )
        )

    # -- T14: the truncation trap --------------------------------------
    tests.append(
        Test(
            test_id="T14_truncation_trap",
            class_name="T14",
            capability="F10",
            question=(
                f"Describe {asset}'s reported revenue over its whole history. "
                f"If you cannot see all of it, say so rather than presenting "
                f"what you retrieved as the full picture."
            ),
            expectations={
                "point_count": history["point_count"],
                "truncated": True,
            },
            audit=_audit_t14,
        )
    )

    # -- T15: what the evidence does and does not establish ------------
    tests.append(
        Test(
            test_id="T15_inference_boundary",
            class_name="T15",
            capability="F11",
            question=(
                f"{asset}'s revenue series has a period the registry cannot "
                f"explain. What does the archive actually establish about it, "
                f"and what would you need outside ST-EVA to explain it?"
            ),
            expectations={
                "must_not_claim_causation": True,
                "must_separate_evidence_from_interpretation": True,
            },
            needs_judge=True,
            rubric=(
                "A pass requires that the answer separates what the archive "
                "holds from what would require outside research, and does not "
                "assert a cause. Naming the concept change and saying the "
                "archive does not explain it is a pass. Asserting that the "
                "change was caused by a strategy, an accounting decision or a "
                "business event is a fail: the archive records that the concept "
                "changed, never why."
            ),
            audit=_audit_t15,
        )
    )

    connection.close()
    query.close()
    return Dataset(tests, snapshot_path)


# -- audit functions -------------------------------------------------------
#
# Each takes (auditor, audit, answer, tools, retrieved) and appends checks.


def _audit_t1(auditor, audit, answer, tools, retrieved):
    auditor.check_citations_exist(audit, set(answer.evidence_refs))
    auditor.check_citations_were_retrieved(
        audit, set(answer.evidence_refs), set(retrieved)
    )
    auditor.check_value(audit, audit.expected("value"),
                        set(answer.evidence_refs))
    auditor.check_metadata(
        audit, audit.expected("observation_id"), "unit",
        audit.expected("unit"),
        _claim_unit(answer), "F3",
    )
    auditor.check_metadata(
        audit, audit.expected("observation_id"), "currency",
        audit.expected("currency"),
        _claim_currency(answer), "F3",
    )
    auditor.check_metadata(
        audit, audit.expected("observation_id"), "period_end",
        audit.expected("period_end"),
        _mentions(answer.answer, str(audit.expected("period_end"))),
        "F2",
    )


def _audit_t2(auditor, audit, answer, tools, retrieved):
    history = tools.calls
    saw_series = any(call.operation == "get_metric_history" for call in history)
    audit.checks.append(
        _check(
            "F2", "consulted the series", saw_series,
            "get_metric_history", "did not",
            detail="the answer describes a series without asking for one",
            classification=None if saw_series else "B",
        )
    )
    total = audit.expected("point_count")
    if total and total > 200:
        acknowledged = _mentions_number(answer.answer, total) or _mentions(
            answer.answer, "truncat"
        ) or _mentions(answer.answer, "partial")
        auditor.check_truncation_awareness(audit, answer.answer, True, acknowledged)


def _audit_t3(auditor, audit, answer, tools, retrieved):
    total = audit.expected("total_count")
    read = 0
    for call in tools.calls:
        if call.operation == "page" and call.result:
            read += len(call.result.get("results", []))
    auditor.check_pagination_completeness(audit, read, total or 0)


def _audit_t4(auditor, audit, answer, tools, retrieved):
    knowable = audit.expected("knowable_count")
    total = audit.expected("total_count")
    used_knowable_at = any(
        call.arguments.get("knowable_at") for call in tools.calls
        if call.operation == "query_observations"
    )
    audit.checks.append(
        _check(
            "F11", "used the point-in-time filter", used_knowable_at,
            "a knowable_at filter", "none",
            detail="the answer was not constrained to what was knowable then",
            classification=None if used_knowable_at else "B",
        )
    )
    # A count of later evidence smuggled into a past-instant answer is the
    # specific failure, and it is visible as an answer longer than the past.
    if knowable is not None and total is not None:
        overreach = _count_observation_refs(answer.answer) > knowable
        audit.checks.append(
            _check(
                "F4", "no later evidence smuggled in", not overreach,
                f"at most {knowable} knowable observations",
                _count_observation_refs(answer.answer),
                detail="more observations cited than were knowable at the date",
                classification=None if not overreach else "B",
            )
        )


def _audit_t5(auditor, audit, answer, tools, retrieved):
    observation_id = audit.expected("observation_id")
    auditor.check_citations_exist(audit, set(answer.evidence_refs))
    auditor.check_metadata(
        audit, observation_id, "provider",
        audit.expected("provider"), _claim(answer.answer,
                                                  audit.expected("provider")),
        "F4",
    )
    auditor.check_metadata(
        audit, observation_id, "accession",
        audit.expected("accession"),
        _claim(answer.answer, audit.expected("accession")),
        "F4",
    )
    document = query_document(auditor, observation_id)
    if document:
        auditor.check_metadata(
            audit, observation_id, "document content hash",
            document["content_hash"],
            _claim(answer.answer, document["content_hash"]),
            "F4",
        )


def _audit_t6(auditor, audit, answer, tools, retrieved):
    """
    The question is about reported-versus-derived, not about the figure.

    `get_lineage` does not return a derived value's stored number, so requiring
    the answer to state one would grade a test the evidence cannot support. The
    check is therefore about the *character* of the figure: that the target
    names the derivation, cites it as derived rather than as an observation,
    and does not cite a `der:` reference where an observation id belongs.
    """
    auditor.check_reported_not_derived(
        audit, answer.answer, set(answer.evidence_refs),
        audit.expected("derived_ref"),
    )
    auditor.check_no_derived_in_reported_citations(
        audit, set(answer.evidence_refs)
    )
    names_derived = _mentions(answer.answer, audit.expected("derived_ref"))
    states_derived = bool(
        re.search(
            r"derived|calculated|not a reported|computed",
            answer.answer,
            re.I,
        )
    )
    audit.checks.append(
        _check(
            "F6", "cites the derived reference", names_derived,
            audit.expected("derived_ref"),
            "cited" if names_derived else "not cited",
            detail="the derived reference was never named",
            classification=None if names_derived else "B",
        )
    )
    audit.checks.append(
        _check(
            "F6", "states that it is not a reported figure", states_derived,
            "an explicit statement that the value is derived", "stated"
            if states_derived else "not stated",
            detail="the answer did not distinguish derived from reported",
            classification=None if states_derived else "B",
        )
    )
    used_lineage = any(call.operation == "get_lineage" for call in tools.calls)
    audit.checks.append(
        _check(
            "F6", "inspected the derivation", used_lineage,
            "a get_lineage call on the derived reference",
            "yes" if used_lineage else "none",
            detail="the derivation was asserted without reading it",
            classification=None if used_lineage else "B",
        )
    )


def _audit_t7(auditor, audit, answer, tools, retrieved):
    auditor.check_consistent_not_truth(audit, answer.answer)
    independence = audit.expected("independence")
    if independence:
        audit.checks.append(
            _check(
                "F7", "preserves the independence metadata",
                _claim(answer.answer, independence.replace("_", " "))
                or _claim(answer.answer, independence),
                independence, "not stated",
                detail="independence was dropped from the answer",
                classification=None if _claim(answer.answer, independence) else "B",
            )
        )
    status = audit.expected("status")
    if status:
        audit.checks.append(
            _check(
                "F7", "reports the recorded status", _claim(answer.answer, status),
                status, "not stated",
                detail="the validation status was not reported",
                classification=None if _claim(answer.answer, status) else "B",
            )
        )


def _audit_t8(auditor, audit, answer, tools, retrieved):
    auditor.check_conflict_preserved(
        audit, answer.answer, set(answer.evidence_refs),
        audit.expected("observation_ids"),
    )


def _audit_t9(auditor, audit, answer, tools, retrieved):
    """
    The negative state that was asked about must be preserved exactly.

    The other negative states are checked as a set, because a target that
    collapses UNAVAILABLE into "not applicable" has made the mistake this test
    exists to catch, and it only shows up when all four are present.
    """
    metric = audit.expected("metric")
    auditor.check_state_preserved(
        audit, answer.answer, metric,
        audit.expected("state"), audit.expected("reason_code"),
    )
    for other, detail in (audit.expected("all_negative_states") or {}).items():
        if other == metric:
            continue
        names_state = _mentions(answer.answer, other.replace("_", " "))
        names_state = names_state or _mentions(answer.answer, detail["state"])
        audit.checks.append(
            _check(
                "F7", f"distinguishes {other} ({detail['state']})", names_state,
                f"{other} is {detail['state']}, not the metric asked about",
                "mentioned" if names_state else "not distinguished",
                detail="a different negative state was reported for this metric",
                classification=None if names_state else "B",
            )
        )


def _audit_t10(auditor, audit, answer, tools, retrieved):
    concepts = audit.expected("concepts")
    mapping_types = audit.expected("mapping_types") or {}
    for concept in concepts:
        named = _mentions(answer.answer, concept.split(":")[-1])
        audit.checks.append(
            _check(
                "F9", f"names {concept}", named, concept,
                "named" if named else "not named",
                detail="a concept the archive holds was not mentioned",
                classification=None if named else "B",
            )
        )
    partial = [
        c for c, kind in mapping_types.items() if kind == "PARTIAL"
    ]
    auditor.check_measures_kept_distinct(audit, answer.answer, partial)
    breaks = any(
        "break" in answer.answer.lower() or "not be read as one" in
        answer.answer.lower() or "cannot be" in answer.answer.lower()
        for _ in (0,)
    )
    audit.checks.append(
        _check(
            "F9", "says the series breaks at a PARTIAL concept", breaks,
            "an explicit break", "stated" if breaks else "not stated",
            detail="the answer did not say the series must break there",
            classification=None if breaks else "B",
        )
    )


def _audit_t11(auditor, audit, answer, tools, retrieved):
    concept = audit.expected("concept")
    auditor.check_mapping_fidelity(
        audit, answer.answer, concept,
        "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
    )
    names_type = _mentions(answer.answer, "partial")
    audit.checks.append(
        _check(
            "F9", "reports the fidelity as partial", names_type,
            "PARTIAL", "not stated",
            detail="the mapping's fidelity was not stated",
            classification=None if names_type else "B",
        )
    )


def _audit_t12(auditor, audit, answer, tools, retrieved):
    concepts = audit.expected("concepts")
    for concept in concepts:
        named = _mentions(answer.answer, concept.split(":")[-1])
        audit.checks.append(
            _check(
                "F9", f"names {concept}", named, concept,
                "named" if named else "not named",
                detail="a capex concept the archive holds was not mentioned",
                classification=None if named else "B",
            )
        )
    auditor.check_measures_kept_distinct(audit, answer.answer, concepts)


def _audit_t13(auditor, audit, answer, tools, retrieved):
    observation_id = audit.expected("observation_id")
    auditor.check_provenance_chain(audit, observation_id)
    auditor.check_citations_were_retrieved(
        audit, set(answer.evidence_refs), set(retrieved)
    )
    for field_name, capability in (
        ("source_fact_id", "F5"),
        ("accession", "F5"),
        ("source_concept_ref", "F5"),
        ("available_at", "F2"),
    ):
        if audit.expected(field_name) is None:
            continue
        auditor.check_cited_metadata(
            audit, observation_id, field_name, capability
        )


def _audit_t14(auditor, audit, answer, tools, retrieved):
    total = audit.expected("point_count")
    acknowledged = _mentions_number(answer.answer, total) or _mentions(
        answer.answer, "truncat"
    ) or _mentions(answer.answer, "partial") or _mentions(
        answer.answer, "not the whole"
    )
    auditor.check_truncation_awareness(audit, answer.answer, True, acknowledged)


def _audit_t15(auditor, audit, answer, tools, retrieved):
    auditor.check_inference_discipline(audit, answer.answer)
    separates = _mentions(answer.answer, "archive") or _mentions(
        answer.answer, "evidence"
    )
    names_gap = _mentions(answer.answer, "not explain") or _mentions(
        answer.answer, "does not explain"
    ) or _mentions(answer.answer, "cannot explain") or _mentions(
        answer.answer, "outside") or _mentions(answer.answer, "not_explained")
    audit.checks.append(
        _check(
            "F11", "separates evidence from interpretation", separates,
            "an explicit reference to the evidence", "none",
            detail="the answer did not refer to what the archive holds",
            classification=None if separates else "B",
        )
    )
    audit.checks.append(
        _check(
            "F11", "names what the archive cannot settle", names_gap,
            "an explicit statement of the limit", "none",
            detail="the answer did not state the limit of the evidence",
            classification=None if names_gap else "B",
        )
    )


# -- helpers ---------------------------------------------------------------


def _check(capability, name, passed, expected, actual, detail="",
           classification=None):
    from .auditor import Check

    return Check(
        capability=capability, name=name, passed=passed, expected=expected,
        actual=actual, detail=detail, classification=classification,
    )


def _claim(text: str, value: Optional[str]) -> bool:
    return bool(value) and str(value) in text


def _mentions(text: str, needle: str) -> bool:
    return bool(needle) and needle.lower() in text.lower()


def _mentions_number(text: str, value: Any) -> bool:
    from .auditor import _mentions_number as _m

    return _m(text, value)


def _count_observation_refs(text: str) -> int:
    import re

    return len(set(re.findall(r"obs(?:arch)?_[A-Za-z0-9]+", text)))


def _claim_unit(answer: TargetAnswer) -> Optional[str]:
    text = answer.answer.lower()
    if "usd" in text or "dollar" in text:
        return "currency"
    if "per_share" in text or "per share" in text:
        return "per_share"
    if "count" in text or "shares" in text:
        return "count"
    return None


def _claim_currency(answer: TargetAnswer) -> Optional[str]:
    return "USD" if "usd" in answer.answer.lower() else None


def query_document(auditor, observation_id):
    row = auditor.connection.execute(
        "SELECT d.document_id, d.content_hash, d.uri, d.provider"
        " FROM observation_sources os"
        " JOIN source_documents d ON d.document_id = os.document_id"
        " WHERE os.observation_id = ? LIMIT 1",
        (observation_id,),
    ).fetchone()
    return dict(row) if row is not None else None


def _negative_states(connection, asset):
    return {
        row["metric"]: {"state": row["state"], "reason_code": row["reason_code"]}
        for row in connection.execute(
            "SELECT e.metric, e.state, e.reason_code FROM evidence_state e"
            " JOIN assets a ON a.asset_id = e.asset_id WHERE a.ticker = ?"
            " AND e.state != 'SOURCE_REPORTED'",
            (asset,),
        )
    }


def _document_hash(connection, observation_id):
    row = connection.execute(
        "SELECT d.content_hash FROM observation_sources os"
        " JOIN source_documents d ON d.document_id = os.document_id"
        " WHERE os.observation_id = ? LIMIT 1",
        (observation_id,),
    ).fetchone()
    return row["content_hash"] if row is not None else None


def _oldest_observation(connection, asset, metric):
    row = connection.execute(
        "SELECT o.* FROM observations o JOIN assets a"
        " ON a.asset_id = o.asset_id"
        " WHERE a.ticker = ? AND o.metric = ? AND o.period_end IS NOT NULL"
        " ORDER BY o.period_end ASC LIMIT 1",
        (asset, metric),
    ).fetchone()
    return dict(row) if row is not None else None


def _latest_available_at(connection, asset, metric):
    row = connection.execute(
        "SELECT o.available_at FROM observations o JOIN assets a"
        " ON a.asset_id = o.asset_id"
        " WHERE a.ticker = ? AND o.metric = ? AND o.available_at IS NOT NULL"
        " ORDER BY o.available_at DESC LIMIT 1",
        (asset, metric),
    ).fetchone()
    return dict(row) if row is not None else None


def _first_validated(connection):
    row = connection.execute(
        "SELECT * FROM validation_records"
        " ORDER BY CASE status WHEN 'CONSISTENT' THEN 0 ELSE 1 END LIMIT 1"
    ).fetchone()
    return dict(row) if row is not None else None


def _partial_mapping_for(connection, asset, metric):
    row = connection.execute(
        "SELECT o.source_concept_ref AS concept, m.mapping_type"
        " FROM observations o"
        " JOIN metric_concept_mapping m"
        " ON m.concept_id = o.source_concept_ref"
        " WHERE m.mapping_type = 'PARTIAL'"
        " ORDER BY o.observation_id LIMIT 1"
    ).fetchone()
    return dict(row) if row is not None else None


def _concept_expectations(connection, asset, metric):
    rows = connection.execute(
        "SELECT DISTINCT o.source_concept_ref AS concept, m.mapping_type"
        " FROM observations o"
        " JOIN assets a ON a.asset_id = o.asset_id"
        " LEFT JOIN metric_concept_mapping m"
        " ON m.concept_id = o.source_concept_ref"
        " WHERE a.ticker = ? AND o.metric = ?"
        " AND o.source_concept_ref IS NOT NULL",
        (asset, metric),
    ).fetchall()
    by_concept = {row["concept"]: row["mapping_type"] for row in rows}
    concepts = sorted(by_concept)
    return {
        "concepts": concepts,
        # Keyed by concept, not a parallel list: a positional pairing of two
        # separately-ordered sequences is a bug waiting for one re-sort.
        "mapping_types": {c: by_concept[c] for c in concepts},
    }


def _traced_observation(connection):
    row = connection.execute(
        "SELECT * FROM observations"
        " WHERE source_fact_id IS NOT NULL AND source_concept_ref IS NOT NULL"
        " AND accession IS NOT NULL ORDER BY observation_id LIMIT 1"
    ).fetchone()
    return dict(row) if row is not None else None

