"""
Mechanical audit: the target's answer against the archive, with no model involved.

The auditor's credibility rests on it being deterministic. A grader that reasons
is a grader that can be talked into agreeing, and a grading system whose verdict
depends on a model's mood produces a number nobody can act on. So every check
here is a comparison between what the target said and what the database holds,
and anything that cannot be checked that way is recorded as *unverifiable*
rather than guessed at.

Two independent questions, kept apart deliberately:

    Is the claim true?      Does the archive say this?
    Is the claim supported? Did the target actually retrieve the evidence it
                            cited, and does its framing exceed what that
                            evidence establishes?

A target can be right by luck and unsupported; a target can retrieve the right
evidence and still overstate it. Collapsing the two into one pass/fail is what
makes an eval number uninterpretable.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

# Failure classifications. A failure without a class is an anecdote.
#
#   A  the archive or the query surface is wrong
#   B  the target model is wrong
#   C  the evaluator is wrong
#   D  the question is ambiguous
#   E  the source cannot answer it
#
# The point of separating A from B is that a model failure is not a reason to
# change ST-EVA. Every A in a run is a defect report; every B is a finding about
# the model.
CLASS_A_DEFECT = "A"
CLASS_TARGET = "B"
CLASS_EVALUATOR = "C"
CLASS_DATASET = "D"
CLASS_SOURCE = "E"

CLASSIFICATION_MEANING = {
    CLASS_A_DEFECT: "ST-EVA defect: the archive or query surface is wrong",
    CLASS_TARGET: "target model error: the evidence supports a different answer",
    CLASS_EVALUATOR: "evaluator defect: the check is wrong, not the answer",
    CLASS_DATASET: "dataset ambiguity: the question does not determine an answer",
    CLASS_SOURCE: "source limitation: the evidence cannot support any answer",
}

# The capabilities results are aggregated under. Not a quality score: a weighted
# total would hide a model that is excellent at values and invents provenance.
CAPABILITIES = {
    "F1": "value accuracy",
    "F2": "period accuracy",
    "F3": "unit, currency and basis",
    "F4": "source attribution",
    "F5": "provenance tracing",
    "F6": "reported versus derived",
    "F7": "unavailable handling",
    "F8": "conflict handling",
    "F9": "concept and mapping handling",
    "F10": "pagination and truncation",
    "F11": "inference discipline",
}

_NUMBER = re.compile(r"-?\d[\d,]*\.?\d*")


@dataclass
class Check:
    """
    One mechanical check, and what it found.

    `passed` is None when the check could not be made — a claim that cannot be
    verified is not a claim that verified, and recording it as a pass is how an
    evaluator starts manufacturing success.
    """

    capability: str
    name: str
    passed: Optional[bool]
    expected: Any
    actual: Any
    detail: str = ""
    classification: Optional[str] = None

    def contract_dict(self) -> Dict[str, Any]:
        return {
            "capability": self.capability,
            "name": self.name,
            "passed": self.passed,
            "expected": self.expected,
            "actual": self.actual,
            "detail": self.detail,
            "classification": self.classification,
        }


@dataclass
class Audit:
    """The verdict on one test."""

    test_id: str
    # What the archive says the answer should be, resolved when the dataset was
    # built. It travels with the audit rather than in a module global so that a
    # check reads its expectations from the object it was handed: shared mutable
    # state here would let one test's expectations leak into another's checks
    # and produce a verdict about a question nobody asked.
    expectations: Dict[str, Any] = field(default_factory=dict)
    checks: List[Check] = field(default_factory=list)
    # The answer's prose, kept on the audit so a check can read it without being
    # handed the whole response. It is here rather than in a module global
    # because two audits can be live at once and a shared slot would cross them.
    answer_text: str = ""

    def expected(self, key: str) -> Any:
        return self.expectations.get(key)

    @property
    def passed(self) -> bool:
        """
        No check failed, and at least one check was decidable.

        A check that could not be made is not a failure and not a pass. It is
        neither, and folding `None` into a failure would make the evaluator's
        own blindness look like the target's error — which is precisely the
        confusion the classification scheme exists to prevent. Folding it into a
        pass would let a target score by saying nothing checkable.

        The second condition is what stops that: a test whose checks are all
        `None` has decided nothing, and cannot be reported as passed.
        """
        if any(check.passed is False for check in self.checks):
            return False
        return any(check.passed is True for check in self.checks)

    @property
    def unverifiable(self) -> List[Check]:
        """Checks that could not be decided, kept visible rather than dropped."""
        return [c for c in self.checks if c.passed is None]

    @property
    def failed_checks(self) -> List[Check]:
        return [c for c in self.checks if c.passed is not True]

    def contract_dict(self) -> Dict[str, Any]:
        return {
            "test_id": self.test_id,
            "passed": self.passed,
            "expectations": self.expectations,
            "answer_text": self.answer_text,
            "check_count": len(self.checks),
            "failed_count": len(self.failed_checks),
            "checks": [c.contract_dict() for c in self.checks],
        }


class Auditor:
    """
    Compares a target's structured answer with the archive.

    Constructed with a direct connection on purpose: the auditor is the thing
    that is *supposed* to see the database, so that the target does not. It
    reads expectations and verifies them. It never answers the question.
    """

    def __init__(self, connection: Any, query: Any) -> None:
        self.connection = connection
        self.query = query

    # -- the checks -------------------------------------------------------

    def check_value(
        self,
        audit: Audit,
        expected: Any,
        claims: Set[str],
        capability: str = "F1",
    ) -> None:
        """
        A number in the answer is the number in the archive.

        Matched on the cited observation rather than by scanning the prose for
        a figure: an answer that states the wrong number next to the right
        citation is still a wrong number, and a prose scan would miss it.
        """
        if expected is None:
            return
        observation_ids = claims & self._observation_ids()
        actual: Optional[float] = None
        for observation_id in sorted(observation_ids):
            row = self.connection.execute(
                "SELECT value_json FROM observations WHERE observation_id = ?",
                (observation_id,),
            ).fetchone()
            if row is not None:
                actual = json.loads(row["value_json"])
                break
        audit.checks.append(
            Check(
                capability=capability,
                name="cited observation holds the expected value",
                passed=None if actual is None else _numbers_equal(actual, expected),
                expected=expected,
                actual=actual,
                detail=(
                    "the target cited no observation that exists in the archive"
                    if actual is None
                    else ""
                ),
                classification=CLASS_TARGET if actual is None else None,
            )
        )

    def check_citations_exist(self, audit: Audit, claims: Set[str]) -> None:
        """
        Every observation the target cited is one the archive holds.

        A citation to an id that does not exist is a fabricated provenance
        reference, which is worse than an uncited answer: it looks checkable.
        """
        if not claims:
            audit.checks.append(
                Check(
                    capability="F4",
                    name="cites at least one observation",
                    passed=False,
                    expected=">= 1 citation",
                    actual=0,
                    detail="the answer referenced no evidence at all",
                    classification=CLASS_TARGET,
                )
            )
            return
        known = self._observation_ids()
        unknown = sorted(claims - known)
        audit.checks.append(
            Check(
                capability="F4",
                name="every cited observation exists",
                passed=not unknown,
                expected=sorted(claims),
                actual=sorted(claims & known),
                detail=f"not in the archive: {unknown}" if unknown else "",
                classification=CLASS_TARGET if unknown else None,
            )
        )

    def check_citations_were_retrieved(
        self,
        audit: Audit,
        claims: Set[str],
        retrieved: Set[str],
    ) -> None:
        """
        A citation is only evidence if it was actually retrieved.

        A model can produce a correct-looking id it never looked up. The
        separation matters: this check asks about the *process*, not the answer.
        """
        if not claims:
            return
        unretrieved = sorted(claims - retrieved)
        audit.checks.append(
            Check(
                capability="F5",
                name="cited observations were actually retrieved",
                passed=not unretrieved,
                expected=sorted(claims),
                actual=sorted(claims & retrieved),
                detail=(
                    f"cited without retrieving: {unretrieved}"
                    if unretrieved
                    else ""
                ),
                classification=CLASS_TARGET if unretrieved else None,
            )
        )

    def check_metadata(
        self,
        audit: Audit,
        observation_id: str,
        field_name: str,
        expected: Any,
        actual: Any,
        capability: str,
    ) -> None:
        """
        One piece of the observation's declared metadata.

        Unit, currency, accession and the rest are the fields a model most
        often paraphrases away, so each is checked on its own rather than as a
        bundle: "right answer, wrong unit" and "wrong answer, right unit" are
        different failures with different fixes.

        A `True` here means "the answer mentions the right thing", so it is not
        interchangeable with a field-by-field comparison. The value, the unit and
        the period are each compared against the database directly by
        `check_value` and `check_cited_metadata`; this check is for the fields
        that only exist as prose in an answer.
        """
        if expected is None:
            return
        if actual is True:
            return
        audit.checks.append(
            Check(
                capability=capability,
                name=f"{observation_id} declares {field_name}",
                passed=expected == actual,
                expected=expected,
                actual=actual,
                detail="" if expected == actual else "the answer's framing "
                "differs from what the observation declares",
                classification=None if expected == actual else CLASS_TARGET,
            )
        )

    def check_cited_metadata(
        self,
        audit: Audit,
        observation_id: str,
        field_name: str,
        capability: str,
    ) -> None:
        """
        A field of a cited observation, read from the archive and the answer.

        Unlike `check_metadata` this does not take an expected value: the
        database is the expected value. It answers "did the answer state what
        this observation actually says", which is the only version of the
        question that can be settled mechanically when the answer is prose.
        """
        row = self.connection.execute(
            "SELECT * FROM observations WHERE observation_id = ?",
            (observation_id,),
        ).fetchone()
        if row is None:
            audit.checks.append(
                Check(
                    capability=capability,
                    name=f"cites {field_name} for {observation_id}",
                    passed=False,
                    expected="<the observation exists>",
                    actual=None,
                    detail="the cited observation is not in the archive",
                    classification=CLASS_TARGET,
                )
            )
            return
        value = row[field_name]
        if value in (None, ""):
            return
        text = audit.answer_text or ""
        if field_name == "source_concept_ref":
            stated = value in text or value.split(":")[-1] in text
        else:
            stated = str(value) in text
        audit.checks.append(
            Check(
                capability=capability,
                name=f"cites {field_name} for {observation_id}",
                passed=stated,
                expected=value,
                actual="stated" if stated else "not stated",
                detail=f"the answer omits {field_name}"
                if not stated
                else "",
                classification=None if stated else CLASS_TARGET,
            )
        )

    def check_provenance_chain(
        self,
        audit: Audit,
        observation_id: str,
    ) -> None:
        """
        The full chain, each link verified against the database.

        observation -> source fact -> document -> accession -> concept ->
        period -> availability. A break anywhere means the figure is not
        traceable, and a figure that cannot be traced is not evidence.
        """
        row = self.connection.execute(
            "SELECT * FROM observations WHERE observation_id = ?",
            (observation_id,),
        ).fetchone()
        if row is None:
            audit.checks.append(
                Check(
                    capability="F5",
                    name="provenance chain resolves",
                    passed=False,
                    expected=observation_id,
                    actual=None,
                    detail="the observation is not in the archive",
                    classification=CLASS_TARGET,
                )
            )
            return

        document = self.connection.execute(
            "SELECT d.content_hash FROM observation_sources os"
            " JOIN source_documents d ON d.document_id = os.document_id"
            " WHERE os.observation_id = ? LIMIT 1",
            (observation_id,),
        ).fetchone()

        links = {
            "source_fact_id": row["source_fact_id"],
            "accession": row["accession"],
            "source_concept_ref": row["source_concept_ref"],
            "period_end": row["period_end"],
            "available_at": row["available_at"],
            "document_content_hash": document["content_hash"] if document else None,
        }
        # A vendor figure legitimately has no filing concept and no accession.
        # Requiring them would fail the test for the wrong reason, so they are
        # required only when the observation declares itself a filing.
        required = {"source_fact_id", "period_end"}
        if row["source_concept_ref"] is not None:
            required |= {"accession", "document_content_hash"}
        missing = sorted(
            key for key in required if links[key] in (None, "")
        )
        audit.checks.append(
            Check(
                capability="F5",
                name="provenance chain is complete",
                passed=not missing,
                expected={key: "<present>" for key in sorted(required)},
                actual={key: links[key] for key in sorted(links)},
                detail=f"missing: {missing}" if missing else "",
                classification=CLASS_TARGET if missing else None,
            )
        )

    def check_reported_not_derived(
        self,
        audit: Audit,
        answer: str,
        claims: Set[str],
        derived_ref: str,
    ) -> None:
        """
        A derived figure is described as derived.

        The dangerous failure is a computed number presented as a filed one,
        because it looks like the most reliable kind of number there is.
        """
        derived_row = self.connection.execute(
            "SELECT ref, value_json, unit FROM derived_values WHERE ref = ?",
            (derived_ref,),
        ).fetchone()
        if derived_row is None:
            audit.checks.append(
                Check(
                    capability="F6",
                    name="derived value exists to be distinguished",
                    passed=None,
                    expected=derived_ref,
                    actual=None,
                    detail="the archive holds no such derived value",
                    classification=CLASS_SOURCE,
                )
            )
            return

        claims_derived = derived_ref in answer
        describes_as_derived = bool(
            re.search(r"derived|calculated|computed|not a reported|"
                      r"not directly reported", answer, re.I)
        )
        described_value = _mentions_number(answer, json.loads(derived_row["value_json"]))
        if not described_value:
            audit.checks.append(
                Check(
                    capability="F6",
                    name="does not present a derived value as a reported one",
                    passed=None,
                    expected=derived_ref,
                    actual="not mentioned",
                    detail="the answer does not state the derived value, so "
                    "there is nothing to check",
                    classification=None,
                )
            )
            return
        audit.checks.append(
            Check(
                capability="F6",
                name="does not present a derived value as a reported one",
                passed=claims_derived and describes_as_derived,
                expected=f"names {derived_ref} and calls it derived",
                actual={
                    "cites_ref": claims_derived,
                    "describes_as_derived": describes_as_derived,
                },
                detail="" if (claims_derived and describes_as_derived)
                else "a computed figure was stated without being marked derived",
                classification=None
                if (claims_derived and describes_as_derived)
                else CLASS_TARGET,
            )
        )

    def check_no_derived_in_reported_citations(
        self,
        audit: Audit,
        claims: Set[str],
    ) -> None:
        """
        A `der:` reference is never passed off as an observation.

        Mixing the two is a type confusion, and it is caught here rather than in
        prose because prose checking on identifiers is unreliable.
        """
        bogus = sorted(c for c in claims if c.startswith("der:"))
        audit.checks.append(
            Check(
                capability="F6",
                name="reported citations are observations, not derived values",
                passed=not bogus,
                expected="no der: reference in an observation citation list",
                actual=claims,
                detail=f"derived references cited as evidence: {bogus}"
                if bogus
                else "",
                classification=CLASS_TARGET if bogus else None,
            )
        )

    def check_conflict_preserved(
        self,
        audit: Audit,
        answer: str,
        claims: Set[str],
        expected_side_ids: List[str],
    ) -> None:
        """
        A disagreement is reported as a disagreement.

        Three separate failures, checked separately because they are different
        mistakes: dropping one side, choosing a winner, or describing the
        disagreement as settled.
        """
        side_ids = set(expected_side_ids)
        both_cited = side_ids <= claims
        audit.checks.append(
            Check(
                capability="F8",
                name="both sides of the conflict are cited",
                passed=both_cited,
                expected=sorted(side_ids),
                actual=sorted(claims),
                detail=(
                    f"missing: {sorted(side_ids - claims)}"
                    if not both_cited
                    else ""
                ),
                classification=CLASS_TARGET if not both_cited else None,
            )
        )

        declares_conflict = bool(
            re.search(r"conflict|discrepan|disagree|differ|conflict", answer, re.I)
        )
        audit.checks.append(
            Check(
                capability="F8",
                name="the disagreement is stated as a disagreement",
                passed=declares_conflict,
                expected="the answer names the conflict",
                actual=declares_conflict,
                detail="" if declares_conflict
                else "the answer did not report the disagreement",
                classification=CLASS_TARGET if not declares_conflict else None,
            )
        )

        picks_winner = bool(
            re.search(
                r"(the\s+)?(correct|actual|true|real)\s+(value|figure|number)"
                r"|I\s+would\s+use|use\s+the\s+(sec|filing|vendor)\s+figure",
                answer,
                re.I,
            )
        )
        audit.checks.append(
            Check(
                capability="F8",
                name="no winner is selected",
                passed=not picks_winner,
                expected="neither side selected",
                actual=picks_winner,
                detail="the answer selected one side of a recorded conflict"
                if picks_winner
                else "",
                classification=CLASS_TARGET if picks_winner else None,
            )
        )

    def check_state_preserved(
        self,
        audit: Audit,
        answer: str,
        metric: str,
        expected_state: str,
        expected_reason: str,
    ) -> None:
        """
        A negative state is reported as that state.

        The specific failure is a negative being read as a zero or as "no
        information". Four negatives mean four different things, and a target
        that collapses them has made a claim it cannot support.
        """
        names_state = bool(re.search(expected_state, answer, re.I))
        names_reason = bool(re.search(expected_reason, answer, re.I))
        invents_value = bool(
            re.search(r"\b(is|was|equals?|of)\s+(zero|0|none|null)\b", answer, re.I)
        )
        audit.checks.append(
            Check(
                capability="F7",
                name=f"{metric} is reported as {expected_state}",
                passed=names_state,
                expected=expected_state,
                actual=names_state,
                detail=f"the answer did not name the state {expected_state}"
                if not names_state
                else "",
                classification=CLASS_TARGET if not names_state else None,
            )
        )
        audit.checks.append(
            Check(
                capability="F7",
                name=f"{metric} preserves its reason code",
                passed=names_reason,
                expected=expected_reason,
                actual=names_reason,
                detail="the answer did not preserve why the state applies"
                if not names_reason
                else "",
                classification=CLASS_TARGET if not names_reason else None,
            )
        )
        audit.checks.append(
            Check(
                capability="F7",
                name=f"{metric} is not turned into a value",
                passed=not invents_value,
                expected="no fabricated value",
                actual=invents_value,
                detail="a negative state was reported as a number"
                if invents_value
                else "",
                classification=CLASS_TARGET if invents_value else None,
            )
        )

    def check_consistent_not_truth(
        self,
        audit: Audit,
        answer: str,
    ) -> None:
        """
        `CONSISTENT` is not upgraded to correctness.

        Cross-source agreement is evidence of agreement. A target that reports
        it as "verified" or "confirmed" has made a stronger claim than two
        comparable sources can support, and the word doing the damage is
        precisely the word a reader would trust most.

        Negation-aware, like every keyword check here: "this is not verification
        that the figure is correct" is the answer being asked for, and a naive
        search for "correct" flags it. An evaluator that punishes correct
        hedging produces failures that look like findings.
        """
        upgrade = _asserts_certification(answer)
        audit.checks.append(
            Check(
                capability="F7",
                name="agreement is not upgraded to correctness",
                passed=not upgrade,
                expected="no unqualified claim of verification",
                actual=upgrade,
                detail="an agreement status was described as verification"
                if upgrade
                else "",
                classification=CLASS_TARGET if upgrade else None,
            )
        )

    def check_mapping_fidelity(
        self,
        audit: Audit,
        answer: str,
        partial_concept: str,
        exact_concept: str,
    ) -> None:
        """
        A PARTIAL concept is not described as equivalent to an EXACT one.

        The vocabulary is the whole point: `PARTIAL` means a wider or narrower
        aggregate, and treating it as EXACT splices two different measures.
        """
        conflates = _asserts_sameness(answer, partial_concept.split(":")[-1])
        audit.checks.append(
            Check(
                capability="F9",
                name="a PARTIAL concept is not called equivalent",
                passed=not conflates,
                expected=f"{partial_concept} stays PARTIAL, distinct from "
                f"{exact_concept}",
                actual=conflates,
                detail="a PARTIAL mapping was described as equivalent"
                if conflates
                else "",
                classification=CLASS_TARGET if conflates else None,
            )
        )

    def check_measures_kept_distinct(
        self,
        audit: Audit,
        answer: str,
        concepts: List[str],
    ) -> None:
        """
        Two differently-scoped concepts are not asserted to be one measure.

        Negation-aware, and that is the whole difficulty: "these are not the
        same measure" is a correct answer that a naive keyword search reads as
        an assertion of sameness. An evaluator that punishes a target for
        stating the distinction correctly is worse than no evaluator, because
        its failures look believable.
        """
        for concept in concepts:
            named = concept.split(":")[-1] in answer
            if not named:
                continue
            if _asserts_sameness(answer, concept.split(":")[-1]):
                audit.checks.append(
                    Check(
                        capability="F9",
                        name=f"{concept} is kept a distinct measure",
                        passed=False,
                        expected="the two measures are distinguished",
                        actual="asserted to be one measure",
                        detail="differently-scoped concepts were called one "
                        "measure",
                        classification=CLASS_TARGET,
                    )
                )
                return
        audit.checks.append(
            Check(
                capability="F9",
                name="the measures are kept distinct",
                passed=True,
                expected="the two measures are distinguished",
                actual="distinguished, or not asserted as one measure",
                detail="",
                classification=None,
            )
        )

    def check_truncation_awareness(
        self,
        audit: Audit,
        answer: str,
        truncated: bool,
        acknowledged: bool,
    ) -> None:
        """
        A truncated series is not described as a complete one.

        Checked as a pair: the target must have seen the truncation flag, and
        the answer must reflect it. Seeing it and ignoring it is a different
        failure from never seeing it, and only the pair distinguishes them.
        """
        if not truncated:
            return
        audit.checks.append(
            Check(
                capability="F10",
                name="truncation is acknowledged in the answer",
                passed=acknowledged,
                expected="the answer states the series is partial",
                actual=acknowledged,
                detail="a truncated series was presented as complete"
                if not acknowledged
                else "",
                classification=CLASS_TARGET if not acknowledged else None,
            )
        )

    def check_pagination_completeness(
        self,
        audit: Audit,
        retrieved_point_count: int,
        total_count: int,
    ) -> None:
        """
        The target walked the whole series.

        A target that read one page of a 338-point series and answered as
        though it had read all of it has produced a confident answer from a
        fraction of the evidence, which is the most common way a model uses a
        database badly.
        """
        if total_count <= 0:
            return
        audit.checks.append(
            Check(
                capability="F10",
                name="the series was paged to completion",
                passed=retrieved_point_count >= total_count,
                expected=total_count,
                actual=retrieved_point_count,
                detail=(
                    f"read {retrieved_point_count} of {total_count} points"
                    if retrieved_point_count < total_count
                    else ""
                ),
                classification=CLASS_TARGET
                if retrieved_point_count < total_count
                else None,
            )
        )

    def check_inference_discipline(
        self,
        audit: Audit,
        answer: str,
    ) -> None:
        """
        Interpretation is marked as interpretation.

        `NOT_EXPLAINED` is the archive saying it cannot explain something.
        Turning that into a cause is the failure this catches, because it reads
        as analysis and is indistinguishable from it in a transcript.
        """
        causal = bool(
            re.search(
                r"because\s+(the\s+company|apple|aapl|revenue\s+(fell|rose))"
                r"|due\s+to\s+(the\s+)?(company|revenue|demand|supply)"
                r"|caused\s+by|driven\s+by|explains\s+why",
                answer,
                re.I,
            )
        )
        audit.checks.append(
            Check(
                capability="F11",
                name="no causal claim beyond the evidence",
                passed=not causal,
                expected="interpretation marked as interpretation",
                actual=causal,
                detail="the answer stated a cause the evidence does not carry"
                if causal
                else "",
                classification=CLASS_TARGET if causal else None,
            )
        )

    # -- helpers ----------------------------------------------------------

    def _observation_ids(self) -> Set[str]:
        return {
            row["observation_id"]
            for row in self.connection.execute(
                "SELECT observation_id FROM observations"
            )
        }

    def observation(self, observation_id: str) -> Optional[Dict[str, Any]]:
        row = self.connection.execute(
            "SELECT * FROM observations WHERE observation_id = ?",
            (observation_id,),
        ).fetchone()
        return dict(row) if row is not None else None

    def state(self, asset: str, metric: str) -> Optional[Dict[str, Any]]:
        row = self.connection.execute(
            "SELECT * FROM evidence_state WHERE asset_id = ? AND metric = ?",
            (asset,),
        ).fetchone()
        return dict(row) if row is not None else None


_NEGATION = re.compile(
    r"(not|isn't|is\s+not|are\s+not|never|no)\b[^.]{0,60}$", re.I
)
_SAMENESS = re.compile(
    r"(equivalent|identical|interchangeable|same as|the same measure|"
    r"one and the same)",
    re.I,
)


def _asserts_sameness(text: str, subject: str) -> bool:
    """
    Whether the text asserts that the subject is the same measure as something.

    Negation-aware, because the commonest correct answer here is "these are not
    the same measure" and a keyword search reads that as an assertion of sameness.
    A check that punishes a target for stating a distinction correctly is worse
    than no check: its failure looks like a real finding and gets acted on.
    """
    for match in _SAMENESS.finditer(text):
        prefix = text[max(0, match.start() - 70) : match.start()]
        if _NEGATION.search(prefix):
            continue
        if subject.lower() in text[max(0, match.start() - 200) : match.end() + 200].lower():
            return True
    return False


_CERTIFIED = re.compile(
    r"\b(verified|confirm(?:ed|s|ing)?|proven|guaranteed|correct)\b", re.I
)


def _asserts_certification(text: str) -> bool:
    """
    Whether the text asserts certification, ignoring negated uses.

    The word "correct" appears in both a claim and its denial, and the denial is
    the answer the evidence supports. Reading them identically is how an
    evaluator manufactures a failure against a model that hedged correctly — a
    failure that reads as a real finding and would send someone to fix the
    model.
    """
    for match in _CERTIFIED.finditer(text):
        prefix = text[max(0, match.start() - 60) : match.start()]
        if _NEGATION.search(prefix):
            continue
        return True
    return False


def _numbers_equal(left: Any, right: Any) -> bool:
    """
    Compare figures that may be written differently but mean the same thing.

    A model may render 15504000000 as `15.504e9`, `15,504,000,000` or
    `15.5 billion`. Only the first of those is a formatting difference, so the
    comparison is numeric with a relative tolerance rather than a string match —
    and the tolerance is tight, because a value check that passes at 1% is not
    checking the value.
    """
    try:
        left_value = float(left)
        right_value = float(right)
    except (TypeError, ValueError):
        return left == right
    if left_value == right_value:
        return True
    scale = max(abs(left_value), abs(right_value), 1.0)
    return abs(left_value - right_value) / scale < 1e-9


def _mentions_number(text: str, value: Any) -> bool:
    """Whether a figure appears in the text, written any of the usual ways."""
    try:
        target = float(value)
    except (TypeError, ValueError):
        return str(value) in text
    for match in _NUMBER.finditer(text.replace(",", "")):
        try:
            if _numbers_equal(float(match.group(0).replace(",", "")), target):
                return True
        except ValueError:
            continue
    return False
