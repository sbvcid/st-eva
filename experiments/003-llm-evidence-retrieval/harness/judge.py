"""
The optional semantic judge, and the limit of what it is allowed to do.

Deliberately narrow. A judge model that could overturn a mechanical check would
be able to talk the evaluation into agreeing, and a verdict that depends on a
model's judgement is not a result anyone can act on — it is a second opinion
wearing a number. So the judge is confined to questions about *framing*, where
the failure is an overstatement and there is nothing to compare against.

It is also confined to being advisory. A judge's verdict never changes a
mechanical result, and it is recorded with the model that produced it, because
"the judge approved" is a claim that has to be attributable.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

JUDGE_CONTRACT = """
You are grading one answer about what an evidence database does and does not
establish. You are not grading whether it is true — a mechanical auditor has
already done that. You are grading only whether it overstates its evidence.

You are given:
- the question
- the target's answer
- the ground-truth evidence package
- the rubric

Reply with JSON only:
{"overstates_evidence": true|false, "reason": "one sentence"}

Set overstates_evidence to true when the answer asserts something the evidence
does not establish: a cause, an intent, a reason, or a conclusion the archive
does not carry. Do not grade style, length, or helpfulness. Do not grade factual
accuracy — that is already settled.
""".strip()


class SemanticJudge:
    """
    Advisory grading of framing, with every verdict attributed.

    `client` is anything callable as `client(prompt) -> str`. There is no
    provider SDK here on purpose: the harness must not carry a vendor
    dependency, and a model call is two HTTP requests and a string.
    """

    def __init__(
        self,
        client: Optional[Any] = None,
        identity: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.client = client
        self.identity = identity or {
            "provider": "none",
            "model": "disabled",
            "version": "1",
        }

    @property
    def enabled(self) -> bool:
        return self.client is not None

    def judge(self, test: Any, answer: Any) -> Optional[Dict[str, Any]]:
        """
        Judge one answer, or record that the check was not applicable.

        `None` for a test that needs no judgement is the right answer: a judge
        that comments on everything dilutes the cases where its opinion is the
        only evidence available.
        """
        if not test.needs_judge:
            return None
        if not self.enabled:
            return {
                "judged": False,
                "reason": "no judge configured; this check needs a model and "
                "the mechanical checks below stand on their own",
                "judge": self.identity,
                "advisory": True,
            }
        prompt = "\n\n".join(
            [
                JUDGE_CONTRACT,
                f"QUESTION:\n{test.question}",
                f"ANSWER:\n{answer.answer}",
                f"EVIDENCE:\n{json.dumps(test.expectations, indent=2, default=str)}",
                f"RUBRIC:\n{test.rubric or ''}",
            ]
        )
        try:
            raw = self.client(prompt)
        except Exception as error:  # noqa: BLE001
            # A judge that cannot be reached produces no verdict, never a
            # silent pass. A missing judge must not read as agreement.
            return {
                "judged": False,
                "reason": f"judge call failed: {type(error).__name__}: {error}",
                "judge": self.identity,
                "advisory": True,
            }
        return {
            "judged": True,
            "judge": self.identity,
            "advisory": True,
            "verdict": _parse(raw),
            "raw": raw,
        }


def _parse(raw: str) -> Dict[str, Any]:
    try:
        payload = json.loads(raw)
        return {
            "overstates_evidence": bool(payload.get("overstates_evidence")),
            "reason": str(payload.get("reason", "")),
        }
    except (TypeError, ValueError) as error:
        return {
            "overstates_evidence": None,
            "reason": f"unparseable judge response: {error}",
        }
