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


@dataclass
class TargetAnswer:
    """A target's response, parsed."""

    answer: str = ""
    evidence_refs: List[str] = field(default_factory=list)
    derived_refs: List[str] = field(default_factory=list)
    uncertainties: List[str] = field(default_factory=list)
    parse_error: Optional[str] = None
    raw: Optional[str] = None

    @classmethod
    def parse(cls, payload: str) -> "TargetAnswer":
        """
        Parse a target's response.

        A response that cannot be parsed is itself a result, not an exception to
        be papered over: a model that cannot follow the output contract is a
        finding about the model, and a harness that quietly coerced it would
        hide exactly the failure it was built to find.
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
        )

    def contract_dict(self) -> Dict[str, Any]:
        return {
            "answer": self.answer,
            "evidence_refs": self.evidence_refs,
            "derived_refs": self.derived_refs,
            "uncertainties": self.uncertainties,
            "parse_error": self.parse_error,
        }


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
