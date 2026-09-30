"""
Three consumer classes, and a gate for each.

The sealed suite reports one number, and 2.6.3 showed what one number hides.
`nvidia/nemotron-3-ultra-550b-a55b:free` scored 15/15 on retrieval, pagination
and temporal discipline across three runs -- no failures, no flips -- and 0/3 on
each of reported-vs-derived and negative states, also stable. Both halves are
real, they are different facts, and `9/15` cannot express either.

2.6.5 then showed that one number hides a third thing. On the point-in-time
probe the model stated the correct figure, cited the correct observation, and
then wrote `PARTIALLY_KNOWABLE` when the code was `PARTIALLY_KNOWNABLE` --
three runs out of three. It *understood* and it could not *encode what it
understood*. Folding that into "Semantic Consumer" is what made the 2.6.5 report
hard to act on: the remedy for a model that reads a figure correctly and labels
it wrongly is not a different archive, and it is not more supervision over its
judgements either. It is a different thing entirely.

So three classes, each answering a different question:

    **Evidence Consumer** -- can it find the evidence and cite it truthfully?
        The question is about grounding: identifiers that exist, citations that
        were actually retrieved, no claim of a figure no tool returned, and a
        series read to the end rather than to the first page. A model that fails
        here is worse than useless, because an invented citation looks
        checkable to whoever reads the answer.

    **Semantic Consumer** -- does its *judgement* match the archive's?
        Credit is given for getting the underlying fact right: the figure, the
        concept, the state, the observation. Asked what was knowable at an
        instant, a model that retrieved the knowable figure and cited the
        knowable observation has understood the question whatever it writes in
        the code field.

    **Structured Consumer** -- can it *encode* that judgement in the schema it
        was given?
        Measured only over runs where the judgement was right. A model that is
        right and cannot say so in the required vocabulary is a real and
        separable limitation, and it is separable precisely because the two
        things are measured apart.

The split matters for what to do next. A model that cannot ground is unusable.
A model that cannot judge is a capability ceiling, addressable by supervision.
A model that can judge and cannot encode has a narrow, mechanical fault that no
amount of archive work will touch -- and mistaking it for the second would mean
sending that model back for more evidence, which is the wrong remedy.

**A gate is a gate.** Each class has named criteria, each criterion is decided
from a run series rather than from a judgement call, and a model that fails any
criterion of a class is not that class. Nothing here produces a ranking, and
nothing here compares two models: the output is three verdicts per model, each
with the evidence that decided it.

`stability` is a criterion in its own right and not a nicety. A capability that
passes in one run of three and fails in the other two is not a capability the
consumer can rely on, and averaging it into a rate would say it was.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# The two citation checks, by name.
#
# Named rather than matched on their capability code, because F5 is also the
# provenance chain's capability: matching the code would report a model as
# fabricating citations every time it failed to name an accession, and the gate
# would then be asserting something it has no evidence for. The two checks are
# also different faults, which is why they are two criteria and not one.
FABRICATED_CHECK = "every cited observation exists"
MISFILED_CHECK = "cited observations were actually retrieved"

# Criteria per class, and where each is decided from.
#
# `tests` names the probes/tests; `min_passes` is how many runs must pass. A
# criterion is decided by the run series, never by a single run, which is why
# nothing here can be answered by one number.
EVIDENCE_CRITERIA: List[Dict[str, Any]] = [
    {
        "id": "uses_the_tool_surface",
        "question": "does it answer through the eight typed operations?",
        "tests": None,  # every test
        "min_call_ratio": 0.5,
        "note": (
            "the ratio of tests in which at least one tool call succeeded. A "
            "model that answers most questions from memory is not an evidence "
            "consumer whatever else it gets right"
        ),
    },
    {
        "id": "retrieval_and_pagination",
        "question": "does it find the evidence, and read a series to the end?",
        "tests": ("T1_exact_value", "T2_series", "T3_pagination",
                  "T14_truncation_trap"),
        "min_passes": 3,
        "require_stable": True,
    },
    {
        "id": "temporal_discipline",
        "question": "does it respect a historical cutoff?",
        "tests": ("T4_point_in_time",),
        "min_passes": 3,
        "require_stable": True,
    },
    {
        "id": "no_fabricated_identifiers",
        "question": "does it ever cite an identifier the archive does not hold?",
        "tests": None,
        "note": (
            "Zero tolerance, and the tolerance is the point. An identifier that "
            "does not exist is a false statement about the archive, it looks "
            "checkable to whoever reads the answer, and a model that does it "
            "once is a model that will do it again -- which is the failure the "
            "local runs showed and the reason a fabricated citation is worse "
            "than no citation. This is a fact about the model and no rate "
            "averages it away."
        ),
    },
    {
        "id": "citations_are_retrieved_and_in_namespace",
        "question": (
            "does it cite observations it actually retrieved, in the field that "
            "means observation?"
        ),
        "tests": None,
        "min_rate": 0.95,
        "note": (
            "A different fault from fabrication, and a rate rather than a veto. "
            "An identifier that exists but was not retrieved, or that is a "
            "document id placed in the observation field, is a real error and a "
            "much milder one: the reader can still open it and see the model got "
            "the pointer slightly wrong. One in eighty is a presentation defect; "
            "one in ten means the citation layer is unreliable. The bar is "
            "chosen rather than derived, and it is recorded so a reader can "
            "disagree with the bar instead of having to reverse-engineer it."
        ),
    },
    {
        "id": "citation_slots_hold_identifiers",
        "question": (
            "does it put identifiers in the citation field rather than "
            "transcript lines?"
        ),
        "tests": None,
        "min_rate": 0.95,
        "note": (
            "A contract fault rather than a grounding one, and kept apart for "
            "that reason. One model in this round filled `evidence_refs` with "
            "lines copied out of tool output -- `coverage_report:AAPL -> metric "
            "'operating_margin_bank': state NOT_APPLICABLE` -- which is not a "
            "false statement about the archive but is a broken citation field, "
            "and a downstream system trusting that field cannot tell the two "
            "apart. Counting it as fabrication would be a false accusation; "
            "ignoring it would hide that the one machine-readable field in the "
            "answer was being used as a notepad."
        ),
    },
    {
        "id": "no_off_surface_calls",
        "question": "does it stay inside the eight operations?",
        "tests": None,
        "note": (
            "a single off-surface call fails the class. Not a rate: the point "
            "of the constraint is that a model *can* try to leave, and one "
            "attempt is the whole finding"
        ),
    },
]

# The two halves of a probe, named so the split is mechanical rather than read.
#
# `MEANING_CHECKS` are the checks that ask whether the model got the underlying
# fact right: the figure it retrieved, the observation or concept it cited. The
# `CODE_FIELDS` are the vocabulary slots.
#
# A run in which every MEANING check passed and a CODE field failed is a run where
# the model understood and could not encode. Found by being wrong, twice: P1 was
# read as a model failure for five runs when the defect was a case-sensitive
# comparison, and P6 was read as a model failure for three runs when the figure
# and the citation were both right and only the code was wrong. The first was my
# fault and the second was the model's, and nothing in the recorded verdict told
# them apart -- which is why the split is recorded per run rather than decided by
# whoever is reading the report.
MEANING_CHECKS = (
    "probe field stated_value",
    "probe cites the subject's own identifiers",
    "probe cites a figure filed under",
    "cites at least one observation",
)
CODE_FIELDS = (
    "probe field claim_type",
    "probe field semantic_state",
    "probe field reason_code",
    "probe field operation_ref",
)


def split_probe_outcome(failed_checks: List[str], stopped: bool) -> str:
    """
    Which of the three things a probe failure is, from the checks alone.

        `structured`  the meaning was right and the encoding was not
        `semantic`    the meaning itself was wrong
        `tool_use`    there was no answer to be wrong

    Mechanical, and it is the whole point. Deciding this by reading the prose
    would be the thing this project has refused to do for six rounds, and it
    would put a judgement in the place of a fact. Two of the three cases are
    decidable from the check names, and the third -- "the figure was wrong" --
    is decidable because it means a MEANING check failed.
    """
    if stopped:
        return "tool_use"
    meaning_failed = any(
        any(name.startswith(prefix) for prefix in MEANING_CHECKS)
        for name in failed_checks
    )
    code_failed = any(
        name in CODE_FIELDS for name in failed_checks
    )
    if not meaning_failed and code_failed:
        return "structured"
    return "semantic"


SEMANTIC_CRITERIA: List[Dict[str, Any]] = [    {
        "id": "reads_a_derived_figure",
        "question": "does it tell a calculated figure from a reported one?",
        "tests": ("probe-P1_reported_or_derived", "T6_reported_vs_derived"),
        "min_passes": 3,
    },
    {
        "id": "reads_a_negative_state",
        "question": "does it say why a figure is absent?",
        "tests": ("probe-P2_negative_state_cause", "T9_unavailable"),
        "min_passes": 3,
    },
    {
        "id": "reads_a_disagreement",
        "question": "does it say what kind of disagreement it is looking at?",
        "tests": ("probe-P3_disagreement_meaning", "T8_conflict"),
        "min_passes": 2,
    },
    {
        "id": "reads_concept_semantics",
        "question": (
            "does it know a PARTIAL mapping is not an EXACT one, and that two "
            "concepts are not one series?"
        ),
        "tests": ("probe-P4_partial_mapping_meaning",
                  "probe-P5_two_concepts_one_series",
                  "T10_concept_evolution", "T11_partial_mapping",
                  "T12_non_comparable"),
    },
    {
        "id": "reads_point_in_time",
        "question": (
            "does it distinguish what was knowable at an instant from what the "
            "archive holds now?"
        ),
        "tests": ("probe-P6_point_in_time_availability", "T4_point_in_time"),
    },
    {
        "id": "reads_source_independence",
        "question": (
            "does it separate two sources disagreeing from two sources being "
            "independent witnesses, and does it keep a disagreement unresolved?"
        ),
        "tests": ("probe-P7_source_consistency_not_truth",),
    },
]


def _verdicts_by_test(rows: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for row in rows:
        out.setdefault(row["test_id"], []).append(row["verdict"])
    return out


def assess(
    rows: List[Dict[str, Any]],
    run_count: int,
    excluded_attempts: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Both gates, decided from a run series.

    `rows` is the per-test rows a variance phase produced: `test_id`, `verdict`,
    `stability`, `tool_calls`, `failed_tool_calls`, and for the audit-derived
    criteria the recorded check outcomes.
    """
    by_test = _verdicts_by_test(rows)
    findings: List[Dict[str, Any]] = []

    for criterion in EVIDENCE_CRITERIA:
        findings.append(
            _decide_evidence_criterion(criterion, rows, by_test, run_count, findings)
        )
    # A criterion that was not exercised is `None` and carries no weight. Only
    # an outright `False` fails the class.
    evidence_ok = not any(f["passed"] is False for f in findings)

    semantic_findings: List[Dict[str, Any]] = []
    for criterion in SEMANTIC_CRITERIA:
        semantic_findings.append(
            _decide_semantic_criterion(criterion, by_test, run_count)
        )
    semantic_ok = not any(f["passed"] is False for f in semantic_findings)

    structured = _structured_gate(rows, run_count)

    return {
        "run_count": run_count,
        "excluded_attempts": excluded_attempts or [],
        "evidence_consumer": {
            "verdict": "ACCEPTED" if evidence_ok else "REJECTED",
            "criteria": findings,
        },
        "semantic_consumer": {
            # Evidence first, for the same reason as `classification`. A model
            # that invents citations may well read semantics beautifully, and
            # calling it a Semantic Consumer would say its semantic accuracy
            # transfers to claims that do not exist.
            "verdict": (
                "ACCEPTED" if semantic_ok and evidence_ok
                else "NOT_YET" if evidence_ok
                else "NOT_REACHED"
            ),
            "criteria": semantic_findings,
            "note": (
                "NOT_YET is the useful answer, not a failure. A model that "
                "grounds but cannot read semantics is a bounded consumer: "
                "usable with a second reader on the semantics. NOT_REACHED "
                "means the evidence gate failed, so there is nothing to build "
                "on and no reason to measure semantics yet."
            ),
        },
        "classification": (
            # Evidence first, always. A model that invents a citation is not a
            # consumer whatever else it gets right, so the semantics verdict
            # must never promote it.
            "not a consumer" if not evidence_ok
            else "candidate autonomous consumer" if semantic_ok
            else "bounded / supervised consumer"
        ),
        "structured_consumer": structured,
    }


def _decide_evidence_criterion(
    criterion: Dict[str, Any],
    rows: List[Dict[str, Any]],
    by_test: Dict[str, List[str]],
    run_count: int,
    _prior: List[Dict[str, Any]],
) -> Dict[str, Any]:
    tests = criterion.get("tests")
    selected = [r for r in rows if tests is None or r["test_id"] in tests]

    if criterion["id"] == "uses_the_tool_surface":
        with_calls = [
            r for r in selected
            if r.get("tool_calls", 0) > 0
            and r.get("failed_tool_calls", 0) < r.get("tool_calls", 0)
        ]
        ratio = len(with_calls) / len(selected) if selected else 0.0
        return {
            "id": criterion["id"],
            "question": criterion["question"],
            "passed": ratio >= criterion["min_call_ratio"],
            "observed": f"{len(with_calls)}/{len(selected)} test-runs used a tool",
            "threshold": f">= {criterion['min_call_ratio']}",
            "note": criterion.get("note"),
        }

    if criterion["id"] == "no_off_surface_calls":
        offenders = sorted(
            {
                call
                for r in selected
                for call in r.get("off_surface_calls", [])
            }
        )
        return {
            "id": criterion["id"],
            "question": criterion["question"],
            "passed": not offenders,
            "observed": offenders or "no off-surface call in any run",
            "threshold": "zero",
            "note": criterion.get("note"),
        }

    if criterion["id"] == "no_fabricated_identifiers":
        # Decided against the archive, not against a check name.
        #
        # This distinction is the whole criterion. The auditor emits one check
        # called "every cited observation exists" for *any* citation that is not
        # an observation id, so reading that check as fabrication rejects a
        # model for citing a real source-fact id or a real document id in the
        # observation column. Reading it as fabrication was a live mistake in
        # this round: it produced a REJECTED verdict for a model that had
        # fabricated nothing at all, and every identifier it cited was in the
        # database.
        broken = sorted({
            f"{row['test_id']}: {ref}"
            for row in selected
            for ref in row.get("fabricated_identifiers", [])
        })
        return {
            "id": criterion["id"],
            "question": criterion["question"],
            "passed": not broken,
            "observed": (
                f"{sum(row.get('identifiers_cited', 0) for row in selected)} "
                f"identifiers cited, {len(broken)} the archive does not hold"
            ),
            "threshold": "zero",
            "failures": broken,
            "note": criterion.get("note"),
        }

    if criterion["id"] == "citations_are_retrieved_and_in_namespace":
        misfiled = [
            f"{row['test_id']}: {item['identifier']} ({item['kind']})"
            for row in selected
            for item in row.get("misfiled_identifiers", [])
        ]
        unretrieved = [
            f"{row['test_id']}: {name}"
            for row in selected
            for name in row.get("provenance_check_failures", [])
            if name == MISFILED_CHECK
        ]
        defects = misfiled + unretrieved
        return _rate_finding(criterion, selected, defects, "misfiled or "
                             "unretrieved", defects)

    if criterion["id"] == "citation_slots_hold_identifiers":
        prose = [
            f"{row['test_id']}: {ref[:70]}"
            for row in selected
            for ref in row.get("non_identifier_citations", [])
        ]
        return _rate_finding(criterion, selected, prose, "not an identifier",
                             prose)

    return _decide_passes(criterion, by_test, run_count)


def _decide_semantic_criterion(
    criterion: Dict[str, Any],
    by_test: Dict[str, List[str]],
    run_count: int,
) -> Dict[str, Any]:
    return _decide_passes(criterion, by_test, run_count)


def _structured_gate(
    rows: List[Dict[str, Any]],
    run_count: int,
) -> Dict[str, Any]:
    """
    The third class: can it encode what it understood, in the schema it was given?

    Measured **only over runs where the understanding was right**. That is the
    definition, and it is what makes the class separable: a model that reaches
    the wrong figure and also writes the wrong code has not demonstrated anything
    about encoding, and counting it would dilute the class with failures that
    belong to the Semantic one.

    Two denominators, both reported, because they answer different questions:

        `given the right answer, how often is it encoded correctly?`
            the encoding rate, over runs whose meaning was right.
        `of everything it was asked, how often did right-and-encoded coincide?`
            the joint rate, which is the number a consumer actually experiences.
    """
    probes = [row for row in rows if row["test_id"].startswith("probe-")]
    if not probes:
        return {
            "verdict": "NOT_REACHED",
            "criteria": [],
            "note": (
                "No probes in this run set. A Structured Consumer is measured "
                "over structured questions, and a run that asked none has said "
                "nothing about it."
            ),
        }

    majority = run_count // 2 + 1
    per_probe: Dict[str, Dict[str, int]] = {}
    for row in probes:
        entry = per_probe.setdefault(
            row["test_id"], {"right_and_encoded": 0, "right_but_misencoded": 0,
                             "wrong": 0, "no_answer": 0}
        )
        if row["verdict"] in ("E", "NOT_RUN"):
            entry["no_answer"] += 1
        elif row["verdict"] == "PASS":
            entry["right_and_encoded"] += 1
        else:
            kind = split_probe_outcome(
                row.get("failed_checks", []),
                row["verdict"] == "E",
            )
            if kind == "structured":
                entry["right_but_misencoded"] += 1
            else:
                entry["wrong"] += 1

    understood = [
        p for p in probes if p["verdict"] == "PASS"
        or split_probe_outcome(p.get("failed_checks", []), False) == "structured"
    ]
    encoded = [p for p in probes if p["verdict"] == "PASS"]
    decided = [p for p in probes if p["verdict"] in ("PASS", "FAIL")]
    encoding_rate = (
        len(encoded) / len(understood) if understood else 1.0
    )
    joint_rate = (
        len([p for p in probes if p["verdict"] == "PASS"]) / len(decided)
        if decided else 0.0
    )
    weakest = sorted(
        (
            (name, e["right_but_misencoded"])
            for name, e in per_probe.items()
            if e["right_but_misencoded"]
        ),
        key=lambda kv: -kv[1],
    )
    return {
        "verdict": (
            "ACCEPTED" if encoding_rate >= 0.95
            else "NOT_YET" if evidence_gate_is_reachable(rows)
            else "NOT_REACHED"
        ),
        "encoding_rate": round(encoding_rate, 3),
        "joint_rate": round(joint_rate, 3),
        "runs_where_understanding_was_right": len(understood),
        "runs_where_it_was_encoded": len(encoded),
        "probes_misencoded_after_a_correct_reading": weakest,
        "criteria": [{
            "id": "encodes_a_correct_reading",
            "question": (
                "when it retrieved and cited the right thing, did it say so in "
                "the vocabulary it was given?"
            ),
            "passed": encoding_rate >= 0.95,
            "observed": (
                f"{len(encoded)}/{len(understood)} correct readings encoded "
                f"correctly ({encoding_rate:.1%})"
            ),
            "threshold": ">= 95%",
            "note": (
                "95% rather than 100% because a code misspelled once in fifty "
                "is a reliability figure and not a capability boundary, and a "
                "gate that demands perfection reports noise as a finding."
            ),
        }],
        "note": (
            "Measured over runs where the judgement was right. A model that is "
            "wrong about a figure has not demonstrated anything about encoding, "
            "and counting it here would dilute the class."
        ),
    }


def evidence_gate_is_reachable(rows: List[Dict[str, Any]]) -> bool:
    """
    Whether the model even got as far as having an understanding to encode.

    Every probe that was refused by the transport, or that the model never
    answered, is a run with no judgement in it, and a Structured Consumer
    verdict over runs where nothing was understood says nothing about encoding.
    """
    return any(row["verdict"] in ("PASS", "FAIL") for row in rows)


def _rate_finding(
    criterion: Dict[str, Any],
    selected: List[Dict[str, Any]],
    defects: List[str],
    label: str,
    failures: List[str],
) -> Dict[str, Any]:
    """
    A rate criterion, over citations rather than over test-runs.

    The denominator is the citation count and not the number of tests, because
    the fault is a property of a citation: a model that cites three things and
    gets one wrong is not better than one that cites one thing and gets it
    wrong, and a per-test rate would say the opposite.
    """
    cited = sum(row.get("identifiers_cited", 0) for row in selected)
    rate = (1.0 - (len(defects) / cited)) if cited else 1.0
    return {
        "id": criterion["id"],
        "question": criterion["question"],
        "passed": rate >= criterion["min_rate"],
        "observed": (
            f"{len(defects)}/{cited} citations {label} ({rate:.1%} clean)"
        ),
        "threshold": f">= {criterion['min_rate']:.0%} clean",
        "failures": failures,
        "note": criterion.get("note"),
    }


def _decide_passes(
    criterion: Dict[str, Any],
    by_test: Dict[str, List[str]],
    run_count: int,
) -> Dict[str, Any]:
    """
    A criterion is a conjunction over its tests, not a sum over them.

    Summing is the tempting version and it is wrong here. Two ways of testing
    the same reading -- a sealed prose test and a structured probe, say -- are
    there because neither alone is enough, and a sum lets the one that happens
    to be easy carry the one that is hard. A model that reads a derived figure
    in prose three times out of three and picks the right field once out of three
    would pass a summed criterion, and the thing a consumer needs to know about
    it is precisely the second number.

    So every test in a criterion must independently reach a majority of the runs.
    A majority rather than all of them, because a provider is going to have a bad
    minute and a criterion that demands perfection reports the provider as a
    finding about the model. The bar is derived from `run_count` rather than
    tuned per criterion, so it cannot be adjusted until a model passes.
    """
    tests = criterion.get("tests") or ()
    majority = run_count // 2 + 1
    detail: Dict[str, List[str]] = {}
    weak: List[str] = []
    absent: List[str] = []
    for test in tests:
        verdicts = by_test.get(test, [])
        detail[test] = verdicts
        if not verdicts:
            # The run set did not contain this test. That is not a failure and
            # must never be scored as one: a screening run that carries five
            # sealed tests would otherwise report that the model fails
            # point-in-time because point-in-time was never asked. An
            # inapplicable criterion is reported as one and carries no weight.
            absent.append(test)
            continue
        passes = sum(1 for v in verdicts if v == "PASS")
        if passes < majority:
            weak.append(f"{test} ({passes}/{len(verdicts)})")

    if not detail or all(not v for v in detail.values()):
        # Nothing in this criterion was exercised at all.
        return {
            "id": criterion["id"],
            "question": criterion["question"],
            "passed": None,
            "observed": f"not exercised: {', '.join(absent) or 'nothing in it'}",
            "threshold": f"each test >= {majority} passes",
            "per_test": detail,
            "not_applicable": absent,
        }
    if not weak:
        # Every test that *was* exercised reached a majority. A criterion that
        # was only half run is weaker evidence than a fully run one and says so,
        # but it is not a failure -- and reporting it as unexercised would throw
        # away a probe that passed five times out of five because its sealed
        # partner was not in the run set.
        return {
            "id": criterion["id"],
            "question": criterion["question"],
            "passed": True,
            "observed": (
                "every exercised test reached a majority of runs"
                + (f"; not exercised: {', '.join(absent)}" if absent else "")
            ),
            "threshold": f"each exercised test >= {majority} passes",
            "per_test": detail,
            "not_applicable": absent,
            "partial_coverage": bool(absent),
        }
    return {
        "id": criterion["id"],
        "question": criterion["question"],
        "passed": False,
        "observed": (
            "short: " + ", ".join(weak)
            + (f"; not exercised: {', '.join(absent)}" if absent else "")
        ),
        "threshold": f"each exercised test >= {majority} passes",
        "per_test": detail,
        "not_applicable": absent,
    }
