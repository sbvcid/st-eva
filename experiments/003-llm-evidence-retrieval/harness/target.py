"""
How a model is put on trial, and the one reference implementation of it.

The target is the thing under test. It gets a toolbox and a question, and it
returns a structured answer. It does not get the expectations, and it does not
get to grade itself.

`ToolCallingTarget` is the adapter shape every provider must implement, so that
two models see byte-identical questions, an identical archive and an identical
tool surface, and the only variable is the model. `ScriptedTarget` implements
that shape without calling anything, which is how the harness is verified: it
can be shown to catch a wrong answer, an unsupported answer and an
overstated answer, without needing a model or a network.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from .tools import Toolbox

# The structured shape every target returns.
#
# This is an evaluation format and deliberately not part of ST-EVA: it exists so
# the auditor can compare claims mechanically, and it must never become a field
# on an observation or a property of the query surface. The archive's contract
# is unchanged by any of it.
ANSWER_CONTRACT = """
Return JSON only, with exactly these keys:

{
  "answer": "the answer in prose, with every claim traceable to evidence",
  "evidence_refs": ["obs_...", "obs_..."],
  "derived_refs": ["der:..."],
  "uncertainties": ["anything the evidence does not settle"]
}

Rules that are not negotiable:
- Every factual claim must be traceable to something a tool returned.
- Do not state a number the tools did not return.
- If the tools do not settle the question, say so in "uncertainties".
- If evidence is incomplete, truncated or conflicting, say that in "answer".
""".strip()

# Fields a probe asks for on top of the four above.
#
# All optional, all defaulting to empty, and all unused by the sealed fifteen --
# `parse` still requires only `answer` and `evidence_refs`, so a sealed test and
# a probe run through identical parsing and a sealed test cannot be affected by
# any of this.
#
# They exist because of what 2.6.3 measured: the sealed tests ask for a claim in
# prose, so the grader has to infer the claim from the wording, and "this seems
# to be saying it is not reported" is a guess with a false-pass rate. A model
# that understood a negative state perfectly and phrased it unconventionally
# scores the same as one that did not understand it at all.
#
# With a field, the grader compares a value. `claim_type` is a code from a closed
# vocabulary stated in the probe, `operation_ref` is the operation id the
# operation registry holds, `stated_value` is the number the archive holds, and
# `evidence_refs` is the citation check the sealed suite already does. Each is
# checkable without reading English.
#
# This remains an evaluation format and is deliberately not part of ST-EVA. None
# of these may become a field on an observation, a property of the query surface,
# or a section of the answer schema the archive publishes. The archive's contract
# is unchanged by any of it.
PROBE_FIELDS = (
    "claim_type",
    "semantic_state",
    "reason_code",
    "operation_ref",
    "stated_value",
)


@dataclass
class TargetAnswer:
    """A target's response, parsed."""

    answer: str = ""
    evidence_refs: List[str] = field(default_factory=list)
    derived_refs: List[str] = field(default_factory=list)
    uncertainties: List[str] = field(default_factory=list)
    parse_error: Optional[str] = None
    raw: Optional[str] = None
    # Probe-only, and documented as such at the top of this module. Held flat
    # rather than nested under a `claims` object so that a probe's expectations
    # and a probe's answer are read the same way.
    claim_type: str = ""
    semantic_state: str = ""
    reason_code: str = ""
    operation_ref: str = ""
    stated_value: Any = None

    @classmethod
    def parse(cls, payload: str) -> "TargetAnswer":
        """
        Parse a target's response.

        A response that cannot be parsed is itself a result, not an exception to
        be papered over: a model that cannot follow the output contract is a
        finding about the model, and a harness that quietly coerced it would
        hide exactly the failure it was built to find.

        The four sealed keys are still the only required ones. A probe field that
        arrives as the wrong type is dropped rather than coerced, because a
        coerced value would be compared as if the model had produced it.
        """
        try:
            data = json.loads(payload)
        except (TypeError, ValueError) as error:
            return cls(
                answer=payload or "",
                parse_error=f"{type(error).__name__}: {error}",
                raw=payload,
            )
        if not isinstance(data, dict):
            return cls(
                answer=payload,
                parse_error="response was JSON but not an object",
                raw=payload,
            )
        missing = [k for k in ("answer", "evidence_refs") if k not in data]
        return cls(
            answer=str(data.get("answer", "")),
            evidence_refs=[str(r) for r in data.get("evidence_refs", []) or []],
            derived_refs=[str(r) for r in data.get("derived_refs", []) or []],
            uncertainties=[
                str(u) for u in data.get("uncertainties", []) or []
            ],
            parse_error=(
                f"missing keys: {missing}" if missing else None
            ),
            raw=payload,
            claim_type=_as_code(data.get("claim_type")),
            semantic_state=_as_code(data.get("semantic_state")),
            reason_code=_as_code(data.get("reason_code")),
            operation_ref=_as_code(data.get("operation_ref")),
            stated_value=_as_number(data.get("stated_value")),
        )

    def probe_claims(self) -> Dict[str, Any]:
        """The probe fields, and nothing else. For a probe's expectations."""
        return {
            "claim_type": self.claim_type,
            "semantic_state": self.semantic_state,
            "reason_code": self.reason_code,
            "operation_ref": self.operation_ref,
            "stated_value": self.stated_value,
        }

    def contract_dict(self) -> Dict[str, Any]:
        payload = {
            "answer": self.answer,
            "evidence_refs": self.evidence_refs,
            "derived_refs": self.derived_refs,
            "uncertainties": self.uncertainties,
            "parse_error": self.parse_error,
        }
        payload.update(self.probe_claims())
        return payload


def _as_code(value: Any) -> str:
    """
    A code field, as a stripped uppercase string, or empty.

    Case-folded because a code is an identifier and an identifier is not
    re-spelled in prose. Anything that is not a scalar string is empty rather
    than stringified: a model that answered `["PARTIAL", "EXACT"]` has not made
    a claim, and turning that into `"['PARTIAL', 'EXACT']"` would produce a
    confident mismatch instead of an honest absence.
    """
    if isinstance(value, str):
        return value.strip().upper()
    return ""


def _as_number(value: Any) -> Any:
    """
    A numeric field, as a float, or None.

    `None` and a wrong number are different answers and stay different here: a
    model that declined to state a figure has not stated a wrong one.
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip().replace(",", ""))
        except ValueError:
            return None
    return None



@runtime_checkable
class Target(Protocol):
    """
    What the harness needs from a model.

    Implemented by one adapter per provider. Keeping the surface this small is
    what makes "the same dataset against another model" a matter of
    configuration rather than of editing the evaluation.
    """

    identity: Dict[str, Any]

    def answer(self, question: str, tools: Toolbox) -> TargetAnswer:
        """Answer one question using only `tools`."""
        ...
