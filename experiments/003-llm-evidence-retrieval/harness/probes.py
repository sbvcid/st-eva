"""
Semantic probes: can the model say what the evidence *means*.

The sealed fifteen ask a question and look for a right answer. That measures
retrieval and grounding well -- 2.6.3 had Nemotron at 15/15 and 79 of 79
citations real -- and it measures understanding badly, for a reason that is
about the harness rather than the model: the answer arrives as prose, so the
grader has to infer the claim from the wording.

That inference is the weak link. "This seems to be saying it is not reported" is
a guess, and it has a false-pass direction that matters: a model which understood
a negative state completely and phrased it unconventionally scores the same as
one which did not understand it. 2.6.3's T6 and T9 results -- 0/3 each, both
stable -- are exactly the shape this weakness produces, and they cannot be told
apart from a genuine semantic failure without going to the trace.

So a probe states its claim as a **field**. The model returns a code from a
closed vocabulary, the operation id, the reason code, the number, and the
citations; the auditor compares values. No English is interpreted anywhere.

**Probes are an experiment protocol, not ST-EVA.** Nothing here is a field on an
observation, a section of the archive's answer schema, or a property of the query
surface. The tool surface the model is given is byte-identical to the one the
sealed fifteen are given, and the archive is unchanged by any of it.

**Every probe is unguessable in at least one field.** A probe whose only
requirement is a choice between two codes is worth nothing: a coin beats it. So
each probe also requires something that can only be obtained by reading the
archive -- an operation id from the operation registry, a reason code from the
coverage report, a figure from the lineage, or the specific observation ids of a
group. The guessable fraction is recorded per probe, so a result can be read
against the floor rather than against zero.

**Every expectation is derived from the archive at build time.** Nothing is
hard-coded to a value the archive happens to hold today; a rebuilt snapshot
yields a different but still correct probe, and a probe whose subject has
disappeared is not run rather than run with a stale answer key.

What the probes are for, stated before the results so the results cannot be read
as something else: the question is whether a model that can already find and
correctly cite evidence can also *read* the distinctions the archive already
makes. Three of the five probe the exact vocabulary the surface now exposes
after 2.6.3, which makes them the first direct test of whether that fix is usable
by a consumer rather than merely correct.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .auditor import CLASS_TARGET, Audit, Auditor, Check
from .target import PROBE_FIELDS, TargetAnswer, _as_code

# Re-exported so the probe layer can be asked "what fields does a probe add"
# without a caller knowing which module they live in. They are defined in
# `target` because that is where the answer is parsed, and parsing is where they
# have to be correct.
__all__ = [
    "PROBE_FIELDS",
    "PROBE_INSTRUCTIONS",
    "Probe",
    "as_tests",
    "audit_probe",
    "build_probes",
    "probe_dataset",
]

# -- closed vocabularies -----------------------------------------------------
#
# Stated to the model in the probe instructions, and used by the auditor as the
# only accepted values. Stating them is not hinting: the codes describe the
# distinctions that exist in the archive, and withholding them would measure
# whether a model can guess a naming convention. Which code is *correct* is
# derived from the data and is never in the instructions.
#
# The provenance vocabulary is deliberately wider than the two answers the
# archive can produce for any one subject. A vocabulary padded with implausible
# codes would flatter the model, so every code here is one the archive can
# actually emit for some figure.

PROVENANCE_VOCABULARY = (
    "REPORTED",
    "DERIVED",
    "REPORTED_AND_ESTIMATED",
    "REPORTED_AND_DERIVED",
    "UNAVAILABLE",
    "NOT_APPLICABLE",
    "CONFLICTING",
)

SEMANTIC_STATE_VOCABULARY = (
    "SOURCE_REPORTED",
    "SOURCE_DID_NOT_REPORT",
    "UNAVAILABLE",
    "NOT_APPLICABLE",
    "STALE",
    "CONFLICTING",
    "EXACT",
    "PARTIAL",
    "NOT_COMPARABLE",
)

REASON_CODES = (
    "SOURCE_STATED_VALUE",
    "SOURCE_OMITS_CONCEPT",
    "RETRIEVAL_FAILED",
    "NO_RECENT_VALUE",
    "BUSINESS_MODEL_NOT_MEANINGFUL",
    "STALE_SOURCE_VALUE",
    "SOURCES_DISAGREE",
)

# The 2.6.3 ambiguity vocabulary, copied rather than imported.
#
# Copied on purpose. If the probe imported the production constant, then a change
# to the production vocabulary would silently change the answer key, and the
# probe would stop measuring the model and start measuring the edit. A probe that
# disagrees with the surface is a finding; a probe that is rewritten to agree
# with it is not.
AMBIGUITY_VOCABULARY = (
    "CROSS_PROVIDER_DISCREPANCY",
    "MULTIPLE_SOURCE_CONCEPTS",
    "DIMENSION_COLLISION",
    "MULTIPLE_FILINGS",
    "MULTIPLE_OBSERVATIONS",
)

# Point-in-time: how much of a period's evidence existed at a given instant.
#
# The middle value is the one that matters and the one a model almost never
# produces. `FULLY_KNOWNABLE` and `NOT_YET_KNOWNABLE` are the comfortable
# answers; the honest one for most periods in an archive built incrementally is
# that some of the evidence existed and some of it did not, and a consumer who
# reports the archive's present-day figure as what was known at the time has
# imported hindsight.
POINT_IN_TIME_VOCABULARY = (
    "FULLY_KNOWNABLE",
    "PARTIALLY_KNOWNABLE",
    "NOT_YET_KNOWNABLE",
)

# Source consistency is not truth.
#
# Two sources agreeing is not corroboration unless they are independent, and two
# sources disagreeing is not a verdict. An archive that reports both facts
# separately is saying something a single boolean cannot, and this is the
# vocabulary that says it.
INDEPENDENCE_VOCABULARY = (
    "INDEPENDENT",
    "NOT_INDEPENDENT",
    "UNKNOWN",
)

# What each probe's instruction block tells the model. Kept as data so the
# instruction a probe sent can be diffed against the code that graded it.
PROBE_INSTRUCTIONS = """
This question is answered with the same JSON object as every other question, plus
these additional keys. They are part of the answer format, not a hint about the
answer.

{
  "claim_type":      one code from: <<vocabulary>>
  "semantic_state":  one code from: <<states>>   (omit if the question does not ask)
  "reason_code":     one code from: <<reasons>>  (omit if the question does not ask)
  "operation_ref":   the operation id, if the question asks how a figure was produced
  "stated_value":    the number, if the question asks for a figure
}

The codes above are every code the archive can emit for any figure. Choose the
one that matches this question. Do not copy a code that merely appears in the
tool output if it does not answer what was asked.

Report what the tools returned. If the tools do not settle the question, put the
reason in "uncertainties" and leave the field you could not determine empty --
an empty field is an honest answer and is scored as one.
""".strip()


def _instructions(vocabulary, states=(), reasons=()) -> str:
    """
    Fill the instruction template.

    Substituted by token rather than by `str.format`, because the template
    contains a JSON example and `format` would read its braces as replacement
    fields. That is a silly way to lose a probe.
    """
    return (
        PROBE_INSTRUCTIONS
        .replace("<<vocabulary>>", ", ".join(vocabulary))
        .replace("<<states>>", ", ".join(states) or "(not asked here)")
        .replace("<<reasons>>", ", ".join(reasons) or "(not asked here)")
    )


# -- the probe ---------------------------------------------------------------


class Probe:
    """
    One probe: a question, a structured answer, and an answer key.

    Not a `Test`, and deliberately so. The sealed fifteen share a `Test` shape
    whose audit functions take an auditor and read expectations out of a dict;
    a probe's audit has to say which *field* is wrong, which is a different kind
    of check. Keeping the two apart means a change to either cannot silently
    change the other, and the sealed baseline stays exactly as sealed.
    """

    def __init__(
        self,
        probe_id: str,
        question: str,
        expected: Dict[str, Any],
        vocabulary: tuple,
        *,
        states: tuple = (),
        reasons: tuple = (),
        required_refs: Optional[List[str]] = None,
        required_concepts: tuple = (),
        citation_required: bool = True,
        unguessable_fields: Optional[List[str]] = None,
        notes: str = "",
    ) -> None:
        self.probe_id = probe_id
        self.question = question
        self.expected = expected
        self.vocabulary = vocabulary
        self.states = states
        self.reasons = reasons
        self.required_refs = list(required_refs or [])
        self.required_concepts = tuple(required_concepts)
        # Whether a correct answer must cite something.
        #
        # False for a subject the archive holds no observation for, and derived
        # from the archive rather than set by hand. The rule that an ungrounded
        # answer fails is right in general and wrong here: asked why a figure is
        # absent, the correct answer cites nothing, and a check that demands a
        # citation makes the question unanswerable. That is what happened --
        # five runs answered P2 correctly on state, reason code and citation
        # semantics, cited nothing, and were failed by a rule their answer could
        # not satisfy.
        self.citation_required = citation_required
        self.unguessable_fields = list(unguessable_fields or [])
        self.notes = notes

    def instructions(self) -> str:
        return _instructions(self.vocabulary, self.states, self.reasons)

    def full_question(self) -> str:
        return f"{self.question}\n\n{self.instructions()}"

    def contract_dict(self) -> Dict[str, Any]:
        return {
            "probe_id": self.probe_id,
            "question": self.question,
            "expected": self.expected,
            "vocabulary": list(self.vocabulary),
            "semantic_state_vocabulary": list(self.states),
            "reason_code_vocabulary": list(self.reasons),
            "required_refs": self.required_refs,
            "required_concepts": list(self.required_concepts),
            "citation_required": self.citation_required,
            # Recorded so a result can be read against the floor rather than
            # against zero: a probe with one guessable binary field and one
            # unguessable id is not a coin toss.
            "unguessable_fields": self.unguessable_fields,
            "notes": self.notes,
        }


# -- audit -------------------------------------------------------------------


def _field_check(
    result: Audit,
    name: str,
    capability: str,
    expected: Any,
    actual: Any,
    *,
    unguessable: bool = False,
) -> None:
    """
    One structured field, compared as a value.

    An empty answer is a failure and is reported as one, not as unverifiable. The
    distinction that matters here is between "wrong" and "did not say", and both
    are failures of the same claim: the probe asked for a field and the field
    does not carry the right content. Reporting "did not say" as unverifiable
    would let a model opt out of a probe by omitting one key.
    """
    if actual in (None, "", []):
        result.checks.append(
            Check(
                capability=capability,
                name=name,
                passed=False,
                expected=expected,
                actual="(not stated)",
                detail="the field was left empty, which is not an answer",
                classification=CLASS_TARGET,
            )
        )
        return
    passed = actual == expected
    result.checks.append(
        Check(
            capability=capability,
            name=name,
            passed=passed,
            expected=expected,
            actual=actual,
            detail=(
                "" if passed else
                f"{'unguessable' if unguessable else 'guessable'} field wrong"
            ),
            classification=None if passed else CLASS_TARGET,
        )
    )


def audit_probe(
    auditor: Auditor,
    result: Audit,
    answer: TargetAnswer,
    tools,
    retrieved: set,
    probe: Probe,
) -> None:
    """
    Grade one probe.

    Three kinds of check, all mechanical: the structured claim against the answer
    key, the citations against what was actually retrieved, and -- because a probe
    that passed its fields could still have done it without touching the archive
    -- that the cited identifiers exist and came back from a tool.
    """
    for field in ("claim_type", "semantic_state", "reason_code", "operation_ref"):
        if field not in probe.expected:
            continue
        # Both sides folded, not just the answer.
        #
        # `TargetAnswer` case-folds every code it reads, so an answer that
        # echoes `divide` from the tool output arrives as `DIVIDE` and was
        # compared against a lowercase key. Folding the answer alone fixes the
        # model and breaks the grader; a code is a code whichever way round it
        # is written, and the archive issues it lowercase.
        _field_check(
            result,
            f"probe field {field}",
            "S1",
            _as_code(probe.expected[field]),
            getattr(answer, field),
            unguessable=field in probe.unguessable_fields,
        )
    if "stated_value" in probe.expected:
        expected_value = probe.expected["stated_value"]
        actual = answer.stated_value
        passed = (
            actual is not None
            and abs(float(actual) - float(expected_value)) <= 1e-9
        )
        result.checks.append(
            Check(
                capability="S1",
                name="probe field stated_value",
                passed=passed,
                expected=expected_value,
                actual=actual if actual is not None else "(not stated)",
                detail="" if passed else "the figure the archive holds was not "
                                          "stated, or a different figure was",
                classification=None if passed else CLASS_TARGET,
            )
        )

    if probe.required_refs:
        cited = set(answer.evidence_refs)
        missing = [ref for ref in probe.required_refs if ref not in cited]
        result.checks.append(
            Check(
                capability="S1",
                name="probe cites the subject's own identifiers",
                passed=not missing,
                expected=probe.required_refs,
                actual=sorted(cited),
                detail="" if not missing else f"missing: {missing}",
                classification=None if not missing else CLASS_TARGET,
            )
        )

    for concept in probe.required_concepts:
        # A concept, not an identifier.
        #
        # The first version of P4 and P5 demanded one *specific* observation id
        # and failed a model that cited the right concept at a different period
        # -- and on P5, whose question literally says "cite one observation from
        # each", a model that cited exactly one of each was failed. The question
        # is about concepts, so the citation requirement is at concept
        # granularity: the model has to have gone and found figures filed under
        # the concept it is making a claim about, and which period it looked at
        # is not what is being tested.
        cited = set(answer.evidence_refs)
        found = [
            ref for ref in cited
            if _concept_of(auditor, ref) == concept
        ]
        result.checks.append(
            Check(
                capability="S1",
                name=f"probe cites a figure filed under {concept.split(':')[-1]}",
                passed=bool(found),
                expected=concept,
                actual=sorted(cited),
                detail=(
                    "" if found
                    else "no cited observation is filed under this concept"
                ),
                classification=None if found else CLASS_TARGET,
            )
        )

    # A probe is a semantic question about specific figures, so a correct claim
    # with no evidence behind it is an unsupported claim -- except where the
    # archive holds no figure to cite, in which case citing nothing is the
    # correct answer and the check is skipped rather than failed.
    auditor.check_citations_exist(
        result, set(answer.evidence_refs),
        require_at_least_one=probe.citation_required,
    )
    auditor.check_citations_were_retrieved(
        result, set(answer.evidence_refs), set(retrieved)
    )
    result.checks.append(
        Check(
            capability="S1",
            name="the answer parsed into the contract",
            passed=answer.parse_error is None,
            expected="a JSON answer object",
            actual=answer.parse_error or "parsed",
            detail=answer.parse_error or "",
            classification=None if answer.parse_error is None else CLASS_TARGET,
        )
    )


def _concept_of(auditor, observation_id: str) -> Optional[str]:
    if getattr(auditor, "connection", None) is None:
        return None
    row = auditor.connection.execute(
        "SELECT source_concept_ref FROM observations WHERE observation_id = ?",
        (observation_id,),
    ).fetchone()
    return row["source_concept_ref"] if row is not None else None


# -- construction ------------------------------------------------------------


def _group_with_multiple_concepts(connection, asset: str) -> Optional[Dict[str, Any]]:
    """
    A metric and period the archive holds several values for, under more than one
    source concept.

    Chosen by asking the data, and by the same rule the surface uses: distinct
    `source_concept_ref` at one metric and period, with distinct values. This is
    the case 2.6.3 exists for, and it is the one the old surface got most
    confidently wrong.
    """
    rows = connection.execute(
        "SELECT o.metric, o.period_start, o.period_end FROM observations o"
        " JOIN assets a ON a.asset_id = o.asset_id WHERE a.ticker = ?"
        " AND o.period_end IS NOT NULL",
        (asset,),
    ).fetchall()
    groups: Dict[Any, Dict[str, List[str]]] = {}
    details: Dict[Any, Dict[str, List[Dict[str, Any]]]] = {}
    for row in rows:
        key = (row["metric"], row["period_start"], row["period_end"])
        detail = connection.execute(
            "SELECT o.observation_id, o.value_json, o.source_concept_ref,"
            " o.accession FROM observations o"
            " JOIN assets a ON a.asset_id = o.asset_id"
            " WHERE a.ticker = ? AND o.metric = ?"
            " AND o.period_start IS ? AND o.period_end IS ?",
            (asset, *key),
        ).fetchall()
        by_value: Dict[str, List[str]] = {}
        for item in detail:
            by_value.setdefault((item["value_json"] or "").strip(), []).append(
                item["observation_id"]
            )
        if len([v for v in by_value if v]) < 2:
            continue
        concepts = {
            item["source_concept_ref"]
            for item in detail if item["source_concept_ref"]
        }
        unmapped = sum(1 for item in detail if not item["source_concept_ref"])
        if len(concepts) > 1 and not unmapped:
            groups[key] = by_value
            details[key] = [dict(item) for item in detail]
    for key in sorted(groups, key=lambda k: (str(k[0]), str(k[2]))):
        members = details[key]
        return {
            "metric": key[0],
            "period_start": key[1],
            "period_end": key[2],
            "source_concepts": sorted(
                {m["source_concept_ref"] for m in members if m["source_concept_ref"]}
            ),
            "observation_ids": sorted(m["observation_id"] for m in members),
            "values": sorted(
                {m["value_json"] for m in members if m["value_json"]}
            ),
        }
    return None


def _partial_knowable_period(connection, asset: str) -> Optional[Dict[str, Any]]:
    """
    A period where the archive holds several figures and they were not all
    available at the same time, and a cutoff that falls between them.

    Found by asking the data. The subject has to be one where a cutoff genuinely
    separates evidence from evidence, because a period whose figures all arrived
    together cannot test anything about point-in-time discipline -- there is
    nothing to get wrong. The answer and the figure that was knowable are read
    out of the rows rather than computed by this module's own rule, so the probe
    cannot disagree with the surface about what was knowable when.
    """
    rows = connection.execute(
        "SELECT o.metric, o.period_end, o.observation_id, o.value_json,"
        " o.available_at FROM observations o"
        " JOIN assets a ON a.asset_id = o.asset_id"
        " WHERE a.ticker = ? AND o.period_end IS NOT NULL"
        " AND o.available_at IS NOT NULL"
        " ORDER BY o.metric, o.period_end, o.available_at",
        (asset,),
    ).fetchall()
    groups: Dict[Any, List[Any]] = {}
    for row in rows:
        groups.setdefault((row["metric"], row["period_end"]), []).append(row)
    for key in sorted(groups, key=lambda k: (str(k[0]), str(k[1]))):
        members = groups[key]
        if len(members) < 2:
            continue
        instants = sorted({m["available_at"] for m in members})
        if len(instants) < 2:
            continue
        cutoff = _day_after(instants[0])
        if cutoff >= instants[1]:
            continue
        knowable = [m for m in members if m["available_at"] <= cutoff]
        later = [m for m in members if m["available_at"] > cutoff]
        if not knowable or not later:
            continue
        chosen = sorted(knowable, key=lambda m: m["observation_id"])[0]
        return {
            "metric": key[0],
            "period_end": key[1],
            "cutoff": cutoff,
            "knowable_observation_id": chosen["observation_id"],
            "knowable_value": json.loads(chosen["value_json"] or "null"),
            "knowable_at": chosen["available_at"],
            "not_yet_observation_ids": sorted(
                m["observation_id"] for m in later
            ),
            "total_observations": len(members),
        }
    return None


def _day_after(instant: str) -> str:
    """
    A cutoff a day after an instant, in the archive's own format.

    A day is the smallest honest gap. A cutoff exactly on the boundary would
    make "was it available" a question about comparison strictness rather than
    about the model's understanding of point-in-time.
    """
    moment = datetime.fromisoformat(instant.replace("Z", "+00:00"))
    return (moment + timedelta(days=1)).isoformat().replace("+00:00", "Z")


def _cross_source_record(connection) -> Optional[Dict[str, Any]]:
    """
    A recorded cross-source check between two observations, read from the record.

    The point of P7 is what the archive *recorded* about independence, so the
    answer key is the recorded value. Reading it from the record rather than
    inferring it from the two providers is the difference between asking whether
    a model can read a distinction and asking whether it can guess one.
    """
    row = connection.execute(
        "SELECT record_id, observation_id, kind, status,"
        " comparison_basis_json, references_json, explanation"
        " FROM validation_records WHERE kind = 'cross_source'"
        " ORDER BY record_id LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    basis = json.loads(row["comparison_basis_json"] or "{}")
    return {
        "record_id": row["record_id"],
        "status": row["status"],
        "independence": basis.get("independence") or "UNKNOWN",
        "provider": basis.get("provider"),
        "observation_ids": sorted(json.loads(row["references_json"] or "[]")),
        "explanation": row["explanation"],
    }


def build_probes(
    connection,
    asset: str = "AAPL",
    registry: Any = None,
) -> List[Probe]:
    """
    Build the probe set from this snapshot.

    A probe whose subject is absent is not built, rather than built with a
    hard-coded answer. An archive that stops holding two concepts for one metric
    has nothing to ask about comparability, and asking anyway would grade a
    model on a question the archive cannot answer.

    `registry` is the core registry, passed rather than a second copy of its
    rules. Whether a series is comparable is the registry's call, not this
    module's, and P4 and P5 read their answer key from `series_breaks` so that a
    probe cannot disagree with the thing it is about. Without it those two
    probes are not built, because the alternative is guessing at a rule that
    lives somewhere else.
    """
    probes: List[Probe] = []

    # -- P1: was this figure reported or derived? -------------------------
    derived = connection.execute(
        "SELECT ref, expression, operation_json, value_json, unit,"
        " depends_on_json FROM derived_values ORDER BY ref LIMIT 1"
    ).fetchone()
    if derived is not None:
        operation = json.loads(derived["operation_json"] or "{}")
        operands = json.loads(derived["depends_on_json"] or "[]")
        operand_ids = sorted(
            ref.split(":", 1)[-1] for ref in operands if isinstance(ref, str)
        )
        stored = json.loads(derived["value_json"] or "null")
        probes.append(
            Probe(
                probe_id="P1_reported_or_derived",
                question=(
                    f"ST-EVA holds a reference `{derived['ref']}`. Is the "
                    f"figure behind that reference a figure the source reported, "
                    f"or one ST-EVA calculated? State the figure, name the "
                    f"operation that produced it, and cite the observation it "
                    f"was calculated from."
                ),
                expected={
                    "claim_type": "DERIVED",
                    "operation_ref": str(operation.get("op") or ""),
                    "stated_value": stored,
                },
                vocabulary=PROVENANCE_VOCABULARY,
                # Three independent assertions, only one of which is a
                # two-way choice, and the operation id cannot be guessed by
                # anyone who has not read the operation registry.
                unguessable_fields=["operation_ref", "stated_value"],
                required_refs=operand_ids,
                notes=(
                    "The probe that the 2.6.2 and 2.6.3 runs could not "
                    "distinguish: three runs failed T6, and the trace showed the "
                    "model never called get_lineage. 2.6.3 gave that operation a "
                    "top-level stored value, so the question is now answerable "
                    "in one call."
                ),
            )
        )

    # -- P2: why is this figure not there? --------------------------------
    negative = connection.execute(
        "SELECT e.metric, e.state, e.reason_code FROM evidence_state e"
        " JOIN assets a ON a.asset_id = e.asset_id"
        " WHERE a.ticker = ? AND e.state IN"
        " ('SOURCE_DID_NOT_REPORT', 'UNAVAILABLE', 'NOT_APPLICABLE', 'STALE')"
        " ORDER BY e.state, e.metric LIMIT 1",
        (asset,),
    ).fetchone()
    if negative is not None:
        # Whether a correct answer must cite something, read from the archive
        # rather than decided here. A metric the archive holds no observation
        # for is precisely the case where the right answer cites nothing, and a
        # probe that demands a citation in that case is unanswerable.
        held = connection.execute(
            "SELECT COUNT(*) FROM observations o"
            " JOIN assets a ON a.asset_id = o.asset_id"
            " WHERE a.ticker = ? AND o.metric = ?",
            (asset, negative["metric"]),
        ).fetchone()[0]
        probes.append(
            Probe(
                probe_id="P2_negative_state_cause",
                question=(
                    f"ST-EVA holds no figure for {asset}'s "
                    f"{negative['metric'].replace('_', ' ')}. Which of the "
                    f"archive's non-reported states applies, and what is the "
                    f"archive's reason code for it?"
                ),
                expected={
                    "claim_type": negative["state"],
                    "reason_code": negative["reason_code"],
                },
                vocabulary=(
                    "SOURCE_REPORTED",
                    "SOURCE_DID_NOT_REPORT",
                    "UNAVAILABLE",
                    "NOT_APPLICABLE",
                    "STALE",
                    "CONFLICTING",
                ),
                states=SEMANTIC_STATE_VOCABULARY,
                reasons=REASON_CODES,
                # The reason code is a string from an external vocabulary of
                # seven, and getting it right means reading it rather than
                # inferring it: SOURCE_OMITS_CONCEPT and NO_RECENT_VALUE are
                # different facts about the world.
                unguessable_fields=["reason_code"],
                citation_required=bool(held),
                notes=(
                    "Every negative state is a different claim about why a "
                    "figure is absent. A model that reports the right number "
                    "as zero has lost the distinction entirely. The archive "
                    f"holds {held} observations for this metric, so a correct "
                    "answer cites nothing and the citation check is scoped "
                    "accordingly."
                ),
            )
        )

    # -- P3: what does this disagreement mean? ----------------------------
    group = _group_with_multiple_concepts(connection, asset)
    if group is not None:
        probes.append(
            Probe(
                probe_id="P3_disagreement_meaning",
                question=(
                    f"The archive holds more than one value for {asset}'s "
                    f"{group['metric'].replace('_', ' ')} for the period ending "
                    f"{group['period_end']}, and it declines to choose between "
                    f"them. Which of the archive's ambiguity reasons applies, "
                    f"and are the competing figures measuring the same thing?"
                ),
                expected={
                    "claim_type": "MULTIPLE_SOURCE_CONCEPTS",
                },
                vocabulary=AMBIGUITY_VOCABULARY,
                # The observation ids cannot be guessed, so this is not a
                # five-way multiple choice in disguise.
                unguessable_fields=["required_refs"],
                required_refs=group["observation_ids"],
                notes=(
                    "The direct test of 2.6.3. Before the fix the surface called "
                    "this 'the endpoint aggregates dimension members' and both "
                    "cloud models repeated it; after the fix the surface names "
                    "the concepts. This probe asks whether a consumer can read "
                    "the corrected vocabulary, which is a different question "
                    "from whether the surface is right -- and 2.6.3 could not "
                    "answer it from prose answers at all."
                ),
            )
        )

    # -- P4: what does a PARTIAL mapping mean? ----------------------------
    #
    # Only for a PARTIAL concept the registry has actually recorded a series
    # break for. The comparability half of the answer is the registry's own
    # statement, read rather than re-derived, so the probe cannot hold a rule
    # the registry has moved on from.
    broken: List[Dict[str, Any]] = []
    if registry is not None:
        for metric in sorted(
            row["metric_id"]
            for row in connection.execute(
                "SELECT DISTINCT metric_id FROM metric_concept_mapping"
                " WHERE mapping_type = 'PARTIAL' AND concept_id IS NOT NULL"
            )
        ):
            for entry in registry.series_breaks(metric) or []:
                if entry.get("kind") != "CONCEPT_MAPPING_BREAK":
                    continue
                if entry.get("explanation") == "NOT_EXPLAINED_BY_ST_EVA":
                    # The registry names the break and says it cannot explain
                    # it. That is still a recorded break, and the comparability
                    # answer does not depend on the cause -- but it is worth
                    # knowing that the cause is unknown, so the probe asks about
                    # comparability and not about why.
                    pass
                broken.append({**entry, "metric_id": metric})
            if broken:
                break
    if broken:
        subject = broken[0]
        probes.append(
            Probe(
                probe_id="P4_partial_mapping_meaning",
                question=(
                    f"Figures filed under "
                    f"{subject['concept_id'].split(':')[-1]} are held for "
                    f"{asset} and mapped to the "
                    f"{subject['metric_id'].replace('_', ' ')} metric. How "
                    f"faithfully does that concept express the metric, and "
                    f"can its figures be read as one continuous comparable "
                    f"series with the metric's other concepts? Cite a figure "
                    f"filed under that concept."
                ),
                expected={
                    "claim_type": str(subject["mapping_type"]),
                    "semantic_state": "NOT_COMPARABLE",
                },
                vocabulary=("EXACT", "PARTIAL", "NON_COMPARABLE", "UNKNOWN"),
                states=SEMANTIC_STATE_VOCABULARY,
                # At concept granularity, not by identifier. See `audit_probe`.
                unguessable_fields=["required_concepts"],
                required_concepts=(subject["concept_id"],),
                notes=(
                    "PARTIAL is not a weaker EXACT. It is a statement that "
                    "the concept does not express the whole metric, and the "
                    "consequence -- a series break the registry records -- "
                    "is what a consumer has to carry. The two fields are "
                    "deliberately different vocabularies: a model that puts "
                    "PARTIAL in both has answered one question twice."
                ),
            )
        )

    # -- P5: can two concepts be read as one series? ----------------------
    if registry is not None and broken:
        metric = broken[0]["metric_id"]
        concepts = connection.execute(
            "SELECT concept_id FROM metric_concept_mapping WHERE metric_id = ?"
            " AND concept_id IS NOT NULL ORDER BY concept_id",
            (metric,),
        ).fetchall()
        witnesses: List[str] = []
        for concept in concepts[:2]:
            row = connection.execute(
                "SELECT o.observation_id FROM observations o"
                " JOIN assets a ON a.asset_id = o.asset_id"
                " WHERE a.ticker = ? AND o.source_concept_ref = ?"
                " ORDER BY o.observation_id LIMIT 1",
                (asset, concept["concept_id"]),
            ).fetchone()
            if row is not None:
                witnesses.append(row["observation_id"])
        if len(concepts) >= 2:
            probes.append(
                Probe(
                    probe_id="P5_two_concepts_one_series",
                    question=(
                        f"The archive holds two "
                        f"{metric.replace('_', ' ')} concepts for {asset}: "
                        f"{concepts[0]['concept_id'].split(':')[-1]} and "
                        f"{concepts[1]['concept_id'].split(':')[-1]}. Can figures "
                        f"from the two be read as one continuous comparable "
                        f"series? Answer with one code, and cite one observation "
                        f"from each."
                    ),
                    expected={
                        "claim_type": "NOT_COMPARABLE",
                    },
                    vocabulary=("COMPARABLE", "NOT_COMPARABLE", "UNKNOWN"),
                    states=SEMANTIC_STATE_VOCABULARY,
                    # One of each, at concept granularity. A model that cited
                    # one figure of each of the two concepts was failed by the
                    # first version of this check for not citing two specific
                    # ids, which is the question being asked of it backwards.
                    unguessable_fields=["required_concepts"],
                    required_concepts=tuple(
                        concept["concept_id"] for concept in concepts[:2]
                    ),
                    notes=(
                        "The complement of P4. P4 asks what a fidelity means; "
                        "this asks whether two concepts can be joined, which is "
                        "the question a consumer has to answer before splicing a "
                        "series."
                    ),
                )
            )

    # -- P6: what was knowable at a cutoff, not what exists now ----------
    #
    # The most easily failed probe in the set, and the one that most looks like
    # a retrieval question. It is not: every figure is one call away, and a
    # model that answers with the archive's present-day figure has imported
    # hindsight into a question about what a researcher could have known. The
    # comfortable answers are `FULLY_KNOWNABLE` and `NOT_YET_KNOWNABLE`; the
    # honest one here is the middle, and a model that can only produce the
    # comfortable two is not doing point-in-time at all.
    partial = _partial_knowable_period(connection, asset)
    if partial is not None:
        probes.append(
            Probe(
                probe_id="P6_point_in_time_availability",
                question=(
                    f"A researcher is writing as of {partial['cutoff'][:10]} and "
                    f"wants {asset}'s {partial['metric'].replace('_', ' ')} for "
                    f"the period ending {partial['period_end']}. The archive "
                    f"holds {partial['total_observations']} observations for "
                    f"that period today. How much of that period was knowable at "
                    f"the researcher's date, and which figure is the one they "
                    f"could have had? Cite that observation and state its value. "
                    f"Do not use a figure that became available after their "
                    f"date."
                ),
                expected={
                    "claim_type": "PARTIALLY_KNOWNABLE",
                    "stated_value": partial["knowable_value"],
                },
                vocabulary=POINT_IN_TIME_VOCABULARY,
                states=SEMANTIC_STATE_VOCABULARY,
                # The figure and the observation id are the probe. Both come
                # from filtering on availability, which is the capability, and
                # neither can be produced by picking the newest or the oldest.
                unguessable_fields=["stated_value", "required_refs"],
                required_refs=[partial["knowable_observation_id"]],
                notes=(
                    "Answering this with the archive's present-day figure is the "
                    "failure. The figure is easy to retrieve and easy to get "
                    "wrong, which is what makes it a probe and not a test of "
                    "retrieval."
                ),
            )
        )

    # -- P7: does a second source corroborate, and is it true? ------------
    cross = _cross_source_record(connection)
    if cross is not None:
        probes.append(
            Probe(
                probe_id="P7_source_consistency_not_truth",
                question=(
                    f"The archive holds a recorded cross-check for {asset} "
                    f"between two sources. Do the two corroborate each other "
                    f"independently? And does the archive select one of them? "
                    f"Cite both observations the check compares."
                ),
                expected={
                    "claim_type": cross["independence"],
                    "semantic_state": "NO_WINNER_SELECTED",
                },
                vocabulary=INDEPENDENCE_VOCABULARY,
                states=SEMANTIC_STATE_VOCABULARY,
                # Two observations, and the separation of two ideas a model
                # usually fuses: that sources disagreeing is not a verdict, and
                # that two sources are not two independent witnesses.
                unguessable_fields=["required_refs"],
                required_refs=cross["observation_ids"],
                notes=(
                    "The distinction is that consistency is not truth. A model "
                    "that says 'two sources disagree, so the figure is "
                    "unreliable' has answered a different question, and a model "
                    "that says 'an SEC filing beats a vendor quote' has invented "
                    "a rule the archive does not have. The recorded comparison "
                    f"says the two are {cross['independence']} and that neither "
                    "is selected."
                ),
            )
        )

    return probes


def probe_dataset(
    connection,
    asset: str = "AAPL",
    registry: Any = None,
) -> Dict[str, Any]:
    """The probe set, and a fingerprint of the facts it was built from."""
    probes = build_probes(connection, asset, registry)
    return {
        "dataset_id": "steva-003a-semantic-probes",
        "version": "1",
        "asset": asset,
        "probe_count": len(probes),
        "probes": [probe.contract_dict() for probe in probes],
        "vocabularies": {
            "provenance": list(PROVENANCE_VOCABULARY),
            "semantic_state": list(SEMANTIC_STATE_VOCABULARY),
            "point_in_time": list(POINT_IN_TIME_VOCABULARY),
            "independence": list(INDEPENDENCE_VOCABULARY),
            "reason_code": list(REASON_CODES),
            "ambiguity": list(AMBIGUITY_VOCABULARY),
        },
    }


def probe_test_id(probe_id: str) -> str:
    """
    A test id that can also be a filename.

    A `test_id` is both an identifier and a path: the runner writes
    `audit/<test_id>.json` per test, and the re-audit and variance phases find
    tests by globbing that directory. So the two uses have to agree, and on
    Windows a colon in a filename does not fail -- it silently redirects the
    write to an NTFS alternate data stream.

    That is the worst kind of bug. `open("audit/probe:P1_x.json", "w")` raises
    nothing, `os.listdir` shows a zero-byte file called `probe`, and the content
    is in a stream that glob cannot see and git will not commit and a reviewer
    will never find. Five probes' worth of audit records vanished from a run
    that reported them as passing.

    The prefix uses `-` rather than `:` for that reason, and
    `test_id_must_be_a_filename` exists so the next person who names something
    with a colon, a slash, or a reserved character gets a failure instead of a
    quiet disappearance.
    """
    return f"probe-{probe_id}"


def test_id_must_be_a_filename(test_id: str) -> None:
    """
    Refuse a test id that would not survive being written as a path.

    A cheap guard against a silent loss, checked where the id is minted rather
    than at write time: by the time the write has gone wrong the run is over and
    nothing says so.
    """
    if not test_id or not test_id.strip():
        raise ValueError("a test id may not be empty")
    reserved = set('<>:"/\\|?*')
    bad = sorted(reserved.intersection(test_id))
    if bad:
        raise ValueError(
            f"test id {test_id!r} contains {bad}, which cannot round-trip "
            "through audit/<test_id>.json on every platform; the write would be "
            "redirected or refused and the record would be lost"
        )


def as_tests(
    connection,
    asset: str = "AAPL",
    registry: Any = None,
) -> List[Any]:
    """
    Present the probes as `Test`s, so the sealed runner is reused unchanged.

    The wrapper is deliberately thin. The sealed runner already knows how to
    give a target a question, hand it a toolbox, record every call and every
    result, parse the answer, call an audit and write a trace — and reimplementing
    any of that for probes would give the two sets different plumbing and make a
    difference in the results uninterpretable. What the wrapper adds is a
    `test_id` prefixed `probe-` so a probe can never be mistaken for a sealed
    test in a report, the capability `S1` for semantic, and an audit that closes
    over the probe.
    """
    from .dataset import Test

    tests = []
    for probe in build_probes(connection, asset, registry):
        def audit_for(probe: Probe):
            def audit(auditor, audit, answer, tools, retrieved):
                return audit_probe(
                    auditor, audit, answer, tools, retrieved, probe
                )
            return audit

        test_id = probe_test_id(probe.probe_id)
        test_id_must_be_a_filename(test_id)
        tests.append(
            Test(
                test_id=test_id,
                class_name=probe.probe_id,
                capability="S1",
                question=probe.full_question(),
                audit=audit_for(probe),
                expectations={
                    "probe": probe.contract_dict(),
                },
                rubric=(
                    "every field compared as a value; no prose is interpreted"
                ),
            )
        )
    return tests
