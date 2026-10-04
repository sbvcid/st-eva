"""
The knowledge-state axis, at domain level.

A source fact is one thing that a source said. An *interpretation* is how
ST-EVA has read that one thing, and that reading can change without the fact
changing at all. This module holds the two apart.

    knowledge_at
        "ST-EVA established this interpretation from this point onward."

It is deliberately **not** any of these, and the distinction is the whole point:

    available_at          when the SOURCE published the fact
    retrieved_at          when ST-EVA asked the source
    period_end / as_of    when the fact is about
    filing date           when a document was lodged

A parser correction moved none of those. The filing was published once, in one
filing, with one availability instant, and it said the same thing every time. What
changed is when ST-EVA understood it. Folding that into `available_at` would date
a correction to a filing that did not contain it -- which is precisely how a
point-in-time contract gets quietly destroyed.

So the archive needs two axes that cannot be substituted for one another:

    source_fact_id   WHICH source fact
    knowledge_at     WHEN ST-EVA held this interpretation of it

## Selection

For a knowledge cutoff C, the effective interpretation is the one with the
greatest `knowledge_at` at or before C. The boundary is **inclusive**, and it is
stated here rather than left to a comparison accident.

## `supersedes`

A link between consecutive interpretations **of the same source fact**. It means
"this reading replaces that reading". It does not mean a new source fact, it is
not `lineage_id`, and it is not a restatement.

## Why this is not an edit mechanism

The series is append-only and its members are constrained. `available_at`,
`replay_eligible_from`, `value`, `period` and `metric` are fixed by the source
fact and every interpretation must agree with them. Only `unit`, `currency` and
`currency_basis` may differ. A model that let any of those move would be a
general "rewrite any historical fact" capability wearing this one's vocabulary,
and the validators below reject it.

Nothing here touches SQLite. Persistence is a later round's decision; this is the
semantics that decision has to satisfy.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from data_contract import parse_iso_date, point_in_time_cutoff


class KnowledgeAxisError(ValueError):
    """A proposed interpretation violates the axis contract."""


def instant(value: Optional[str]) -> Optional[datetime]:
    """A comparable instant, or None if the value is absent or unreadable."""
    if not value or not isinstance(value, str):
        return None
    parsed = parse_iso_date(value)
    return parsed if parsed is not None else None


def _canonical(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      default=str)


# --------------------------------------------------------------------------
# domain objects


@dataclass(frozen=True)
class SourceFact:
    """
    One thing a source said, and the invariants every reading of it shares.

    These fields are the fact. An interpretation may not change any of them; that
    is enforced rather than documented because a relaxed invariant here is how a
    correction becomes a rewrite.
    """

    source_fact_id: str
    available_at: str
    replay_eligible_from: str
    value: float
    period_start: Optional[str]
    period_end: str
    metric: str
    lineage_id: Optional[str] = None

    def invariants(self) -> Dict[str, Any]:
        return {
            "available_at": self.available_at,
            "replay_eligible_from": self.replay_eligible_from,
            "value": self.value,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "metric": self.metric,
        }


@dataclass(frozen=True)
class Interpretation:
    """
    How ST-EVA has read one source fact, as of one knowledge instant.

    Only the reading fields may vary. The identity is derived, so two structurally
    identical interpretations are the same logical interpretation and cannot be
    stored twice under different names.
    """

    source_fact_id: str
    knowledge_at: str
    unit: str
    currency: Optional[str]
    currency_basis: str
    value: float
    period_start: Optional[str]
    period_end: str
    metric: str
    supersedes: Optional[str] = None
    _identity: Optional[str] = field(default=None, compare=False)

    @property
    def identity(self) -> str:
        """
        Deterministic identity: (source_fact_id, knowledge_at, interpretation).

        This is what a later storage layer must enforce as a uniqueness
        constraint. It is content-derived rather than assigned, so re-deriving the
        same interpretation on another machine, or twice in one process, yields
        the same key without a coordination round.
        """
        if self._identity is None:
            payload = {
                "source_fact_id": self.source_fact_id,
                "knowledge_at": self.knowledge_at,
                "unit": self.unit,
                "currency": self.currency,
                "currency_basis": self.currency_basis,
                "value": self.value,
                "period_start": self.period_start,
                "period_end": self.period_end,
            }
            digest = hashlib.sha256(
                _canonical(payload).encode("utf-8")).hexdigest()
            object.__setattr__(self, "_identity", f"interp_{digest[:24]}")
        return self._identity

    @property
    def reading(self) -> Dict[str, Any]:
        """Only the fields an interpretation is allowed to change."""
        return {"unit": self.unit, "currency": self.currency,
                "currency_basis": self.currency_basis}


# --------------------------------------------------------------------------
# the axis


class KnowledgeAxis:
    """
    The ordered interpretations of one source fact, with the invariants enforced
    at the moment a reading is added rather than checked later by a consumer.
    """

    def __init__(self, fact: SourceFact) -> None:
        if not fact.source_fact_id:
            raise KnowledgeAxisError("a source fact must identify itself")
        if instant(fact.available_at) is None:
            raise KnowledgeAxisError(
                f"available_at is absent or unreadable: {fact.available_at!r}")
        if instant(fact.replay_eligible_from) is None:
            raise KnowledgeAxisError(
                "replay_eligible_from is absent or unreadable: "
                f"{fact.replay_eligible_from!r}")
        self.fact = fact
        self._series: List[Interpretation] = []
        self._by_identity: Dict[str, Interpretation] = {}

    # -- reads ------------------------------------------------------------

    def audit(self) -> List[Interpretation]:
        """Every interpretation, in knowledge order. The audit surface."""
        return list(self._series)

    def effective_at(self, cutoff: str) -> Optional[Interpretation]:
        """
        The one interpretation effective at a knowledge cutoff.

        Greatest `knowledge_at` at or before `cutoff`; inclusive at the
        boundary. An unreadable cutoff yields None rather than everything, because
        answering an unreadable question with the whole series is the failure a
        point-in-time contract exists to prevent.
        """
        at = point_in_time_cutoff(cutoff)
        moment = instant(at) if at else None
        if moment is None:
            return None
        eligible = [i for i in self._series
                    if instant(i.knowledge_at) is not None
                    and instant(i.knowledge_at) <= moment]
        if not eligible:
            return None
        # `max` on a strictly increasing series; the ordering is enforced on
        # insert, so there is never a tie to break here.
        return max(eligible, key=lambda i: instant(i.knowledge_at))

    def __len__(self) -> int:
        return len(self._series)

    def __iter__(self):
        return iter(self._series)

    # -- writes -----------------------------------------------------------

    def record(self, knowledge_at: str, unit: str, currency: Optional[str],
               currency_basis: str, supersedes: Optional[str] = None
               ) -> Tuple[Interpretation, bool]:
        """
        Add one interpretation.

        Returns `(interpretation, added)` where `added` is False when the call was
        a no-op because the identical interpretation was already held. That is
        the idempotence property: recording the same reading twice is a read, not
        a second entry.

        Every invariant is checked here. The alternative -- documenting them and
        letting a consumer discover the breach -- is how a correction becomes a
        silent rewrite.
        """
        candidate = Interpretation(
            source_fact_id=self.fact.source_fact_id,
            knowledge_at=knowledge_at,
            unit=unit,
            currency=currency,
            currency_basis=currency_basis,
            value=self.fact.value,
            period_start=self.fact.period_start,
            period_end=self.fact.period_end,
            metric=self.fact.metric,
            supersedes=supersedes,
        )
        # Idempotence is resolved BEFORE validation, and the order matters.
        # An exact repeat is a read, not a second entry -- and if validation ran
        # first it would be refused by the "reads exactly as the previous one
        # did" rule, which is the right rule for a *new* entry and the wrong one
        # for a repeat of an existing one. Validating the repeat would also make
        # re-running a repair non-idempotent, which is the property this whole
        # axis exists to provide.
        existing = self._by_identity.get(candidate.identity)
        if existing is not None:
            return existing, False
        self._validate(candidate)
        self._series.append(candidate)
        self._series.sort(key=lambda i: instant(i.knowledge_at))
        self._by_identity[candidate.identity] = candidate
        return candidate, True

    # -- validation -------------------------------------------------------

    def _validate(self, candidate: Interpretation) -> None:
        fact = self.fact

        # 1. the fact must be the same fact
        if candidate.source_fact_id != fact.source_fact_id:
            raise KnowledgeAxisError(
                f"source_fact_id changed: {candidate.source_fact_id!r} is not "
                f"{fact.source_fact_id!r}. An interpretation is a reading of "
                "one source fact; a different id is a different fact and needs "
                "its own axis.")

        # 2. the knowledge instant must be present and readable
        moment = instant(candidate.knowledge_at)
        if moment is None:
            raise KnowledgeAxisError(
                f"knowledge_at is absent or unreadable: "
                f"{candidate.knowledge_at!r}")

        # 8/9/10/11. The source-fact invariants are carried from the fact and
        # asserted here, so a caller cannot smuggle a change past the axis by
        # constructing an Interpretation directly and handing it in later.
        if (candidate.value != fact.value
                or candidate.period_start != fact.period_start
                or candidate.period_end != fact.period_end
                or candidate.metric != fact.metric):
            raise KnowledgeAxisError(
                "an interpretation may not change the value, the period or the "
                "metric; it is a reading of the fact, not a new fact")

        # 7. one reading per source fact per knowledge instant
        for held in self._series:
            if instant(held.knowledge_at) == moment:
                if held.identity == candidate.identity:
                    # Same fact, same instant, same reading -- so it is the same
                    # logical interpretation and re-recording it is a no-op.
                    # But the identity deliberately excludes `supersedes`, so a
                    # caller may pass a *different* edge for an already-held
                    # reading. Silently keeping the original would make the edge
                    # a function of insertion order rather than of the record,
                    # so a conflicting edge is refused instead.
                    if held.supersedes != candidate.supersedes:
                        raise KnowledgeAxisError(
                            "a different supersedes edge was offered for an "
                            f"interpretation already held at "
                            f"{candidate.knowledge_at!r} "
                            f"(held {held.supersedes!r}, offered "
                            f"{candidate.supersedes!r}). One reading may have "
                            "one predecessor.")
                    return      # idempotent no-op, handled by `record`
                raise KnowledgeAxisError(
                    f"another interpretation of this source fact already exists "
                    f"at {candidate.knowledge_at!r} "
                    f"({held.reading} vs {candidate.reading}). Two readings at "
                    "one instant would need a tie rule, and inventing an "
                    "arbitrary winner is worse than refusing.")

        # 3/6. strictly increasing knowledge time, and no cycles
        previous = self._series[-1] if self._series else None
        if previous is not None:
            if moment < instant(previous.knowledge_at):
                raise KnowledgeAxisError(
                    f"knowledge_at {candidate.knowledge_at!r} precedes the "
                    f"existing {previous.knowledge_at!r}. Interpretations are "
                    "ordered by knowledge, so a later reading cannot know less.")
            if candidate.supersedes is None:
                raise KnowledgeAxisError(
                    "a later interpretation must declare what it supersedes; an "
                    "ordered series with unlinked members is not a chain and "
                    "cannot be audited.")
            target = self._by_identity.get(candidate.supersedes)
            if target is None:
                raise KnowledgeAxisError(
                    f"supersedes {candidate.supersedes!r} is not an "
                    "interpretation held by this axis")
            if target.source_fact_id != candidate.source_fact_id:
                raise KnowledgeAxisError(
                    "supersedes may not cross a source_fact_id")
            if target.identity != previous.identity:
                raise KnowledgeAxisError(
                    f"supersedes must name the immediately preceding "
                    f"interpretation ({previous.identity}); it named "
                    f"{target.identity}")
            if self._reaches(candidate.supersedes, candidate.identity):
                raise KnowledgeAxisError(
                    "supersedes would create a cycle")
        elif candidate.supersedes is not None:
            raise KnowledgeAxisError(
                "the first interpretation cannot supersede anything")

        # 12. the reading fields must actually differ from the previous one,
        # or the entry records nothing
        if previous is not None and previous.reading == candidate.reading:
            raise KnowledgeAxisError(
                "this interpretation reads the fact exactly as the previous one "
                "did; recording it would add a knowledge event that changed "
                "nothing")

    def _reaches(self, start: str, target: str) -> bool:
        """Walk the supersedes chain and report whether `target` is upstream."""
        seen: set = set()
        cursor = start
        while cursor is not None and cursor not in seen:
            if cursor == target:
                return True
            seen.add(cursor)
            node = self._by_identity.get(cursor)
            cursor = node.supersedes if node else None
        return False