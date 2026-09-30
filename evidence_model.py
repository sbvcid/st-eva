from __future__ import annotations

"""
ST-EVA 2.5 - the state model and the identity rules the Query Surface reads.

Two things live here, and both are read-side concepts rather than storage
concepts.

    The six states a metric can be in. A single "missing" cannot distinguish
    four situations that imply four different next actions: the source omits
    the item, the concept does not exist for this business, our retrieval
    failed, or what we hold has gone stale. The Query Surface returns states
    rather than rows so that distinction survives the read.

    The two identities. `source_fact_id` is one raw fact inside one source
    document, and is the only thing deduplication may use. An observation's
    identity always carries its source, so two sources reporting the same
    number remain two observations and the disagreement between them stays
    findable.

The metric and concept registry is deliberately absent. It is the next stage,
and nothing in a read path needs it to return an observation faithfully.
"""

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from data_contract import ValidationStatus

# --- states -----------------------------------------------------------------

SOURCE_REPORTED = "SOURCE_REPORTED"
SOURCE_DID_NOT_REPORT = "SOURCE_DID_NOT_REPORT"
NOT_APPLICABLE = "NOT_APPLICABLE"
UNAVAILABLE = "UNAVAILABLE"
CONFLICTING = "CONFLICTING"
STALE = "STALE"
# Added in 2.7. "Applicable, and nothing has been collected for it yet" had no
# token, so it could only be reported as `UNAVAILABLE` -- which says the last
# attempt failed. That is the one collapse this project treats as a defect
# rather than a nuance: it tells a reader that a figure is missing when the truth
# is that ST-EVA has not looked for a figure that is expected to exist, and it
# makes an empty archive indistinguishable from a broken one.
#
# The three are now separate states and are derived from three different places:
#
#     NOT_APPLICABLE     the registry: this metric does not exist for this kind
#                        of company. A statement about the business.
#     NO_OBSERVATIONS    the archive: the metric applies and holds nothing yet.
#                        A statement about what has been collected.
#     UNAVAILABLE        retrieval: an attempt was made and did not produce a
#                        figure. A statement about the last attempt.
NO_OBSERVATIONS = "NO_OBSERVATIONS"

EVIDENCE_STATES: Tuple[str, ...] = (
    SOURCE_REPORTED,
    SOURCE_DID_NOT_REPORT,
    NOT_APPLICABLE,
    NO_OBSERVATIONS,
    UNAVAILABLE,
    CONFLICTING,
    STALE,
)

# A state is positive when the answer itself is informative, and negative when
# the answer is the absence of one. The distinction is what a coverage report
# exists to make visible.
NEGATIVE_STATES = frozenset(
    {
        SOURCE_DID_NOT_REPORT, NOT_APPLICABLE, NO_OBSERVATIONS, UNAVAILABLE,
        STALE,
    }
)

# The evidence state maps onto a validation status, because a state is a
# statement about evidence and the 2.3-C contract already has a vocabulary for
# that. NOT_APPLICABLE in particular is new in 2.5 and needed its own member:
# a bank with no operating-income tag is not a retrieval that failed.
STATE_STATUS: Dict[str, ValidationStatus] = {
    SOURCE_REPORTED: ValidationStatus.SINGLE_SOURCE,
    SOURCE_DID_NOT_REPORT: ValidationStatus.UNAVAILABLE,
    NOT_APPLICABLE: ValidationStatus.NOT_APPLICABLE,
    # An empty archive is not a failed retrieval, and the 2.3-C vocabulary has
    # no better member for it than the one an absent concept already uses: both
    # are "there is no figure here", and they differ in *why*, which is what the
    # state and its reason code carry and what the validation status cannot.
    NO_OBSERVATIONS: ValidationStatus.UNAVAILABLE,
    UNAVAILABLE: ValidationStatus.UNAVAILABLE,
    CONFLICTING: ValidationStatus.CONFLICTING,
    STALE: ValidationStatus.STALE,
}

REASON_CODES: Dict[str, str] = {
    SOURCE_REPORTED: "SOURCE_STATED_VALUE",
    SOURCE_DID_NOT_REPORT: "SOURCE_OMITS_CONCEPT",
    NOT_APPLICABLE: "BUSINESS_MODEL_NOT_MEANINGFUL",
    NO_OBSERVATIONS: "NOT_YET_COLLECTED",
    UNAVAILABLE: "RETRIEVAL_FAILED",
    CONFLICTING: "SOURCES_DISAGREE",
    STALE: "NO_RECENT_VALUE",
}


class EvidenceStateError(Exception):
    """A state was asserted that the evidence cannot support."""


@dataclass(frozen=True)
class EvidenceState:
    """The state of one metric for one company, with its reason."""

    asset: str
    metric: str
    state: str
    reason_code: Optional[str] = None
    detail: Optional[str] = None
    as_of: Optional[str] = None

    def __post_init__(self) -> None:
        if self.state not in EVIDENCE_STATES:
            raise EvidenceStateError(
                f"{self.state!r} is not an evidence state; expected one of "
                f"{list(EVIDENCE_STATES)}"
            )
        expected = REASON_CODES.get(self.state)
        if self.state == SOURCE_REPORTED:
            if not self.detail:
                raise EvidenceStateError(
                    "SOURCE_REPORTED needs a locator in `detail`, otherwise "
                    "it is a value with no provenance and is not Evidence"
                )
        elif self.reason_code is not None and self.reason_code != expected:
            raise EvidenceStateError(
                f"state {self.state} expects reason_code {expected!r}, got "
                f"{self.reason_code!r}"
            )
        if self.state in NEGATIVE_STATES and self.detail is not None:
            raise EvidenceStateError(
                f"{self.state} must not carry a locator; there is no value"
            )

    @property
    def is_reported(self) -> bool:
        return self.state == SOURCE_REPORTED

    def contract_dict(self) -> Dict[str, Any]:
        return {
            "asset": self.asset,
            "metric": self.metric,
            "state": self.state,
            "reason_code": self.reason_code or REASON_CODES.get(self.state),
            "detail": self.detail,
            "as_of": self.as_of,
        }


# --- identity ---------------------------------------------------------------


def canonical_json(payload: Any) -> str:
    return json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )


def source_fact_id(
    source_id: str,
    document_ref: str,
    taxonomy: Optional[str],
    concept: Optional[str],
    period_start: Optional[str],
    period_end: Optional[str],
    context: Optional[str] = None,
) -> str:
    """
    The identity of one raw fact inside one source document.

    Deduplication is allowed on this and nothing else. Two runs that parse
    the same filing, or two adapters that read the same filing, produce the
    same `source_fact_id` and the second is recognised as already held.

    Deliberately not included: any cross-source field, and the numeric value.
    Two sources reporting the same number are two facts about the world rather
    than one, and folding them together would delete the only record that two
    independent readings existed, along with the 2.3-B validation model that
    depends on it.
    """
    payload = {
        "source": source_id,
        "document": document_ref,
        "taxonomy": taxonomy or "",
        "concept": concept or "",
        "period_start": period_start or "",
        "period_end": period_end or "",
        "context": context or "",
    }
    return "sfid_" + hashlib.sha256(
        canonical_json(payload).encode("utf-8")
    ).hexdigest()[:32]
