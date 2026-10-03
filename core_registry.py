from __future__ import annotations

"""
ST-EVA 2.5 - the Core Registry.

    metric_registry          what a metric means
    concept_registry         what a source concept is
    metric_concept_mapping   how one relates to the other

The registry exists so the database can answer *what an item is* rather than
only *what it is called*. A filer may change the tag it uses for a fact without
changing the fact, and may use a different tag for a genuinely different
quantity. Only an explicit mapping tells those apart.

Three rules the module holds, each because the alternative was measured to be
wrong against real AAPL filings:

    A concept is not a metric. `us-gaap:Revenues` is a tag a filer applies;
    `revenue` is a meaning ST-EVA names. Equating them by name is how a silent
    discontinuity gets spliced into one series.

    A missing retrieval is never evidence of inapplicability. A metric is
    NOT_APPLICABLE because of what the concept means for that business, or
    because the registry says so, and never because a fetch returned nothing.

    The registry resolves nothing. It does not rank sources, pick a winner in a
    conflict, or infer a value. It states what things mean and how they relate,
    and the 2.4.3 states stay where they were decided.
"""

import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from data_contract import utc_now

# Business models a metric can be excluded for. A model is a property of the
# issuer, not of the metric, and it is recorded only when a concept genuinely
# does not exist for that kind of business.
BANK = "BANK"
INSURANCE = "INSURANCE"
REIT = "REIT"
MINING = "MINING"
INSURANCE = "INSURANCE"
REIT = "REIT"
MINING = "MINING"
# A filer classified by the SEC under SIC major group 61 or 62: banks, insurers
# and finance companies. Added in 2.7 because a filer that publishes that
# classification was previously unrepresentable, and a financial institution
# that could not be recorded was a financial institution whose inapplicable
# metrics fell through to `UNAVAILABLE` and reported a retrieval failure for a
# line that does not exist.
#
# `BANK` stays in the vocabulary. It was declared against a metric before any
# issuer could be classified at all, and deleting it would silently make
# operating income applicable to every issuer this round did not touch.
FINANCE_SERVICES = "FINANCE_SERVICES"
# `OPERATING` is what a filer is when nothing more specific is warranted, and it
# is deliberately a member rather than the absence of one: an issuer recorded as
# `None` has had no ruling made, and an issuer recorded as `OPERATING` has been
# looked at and found to be an ordinary business. The two read the same in a
# coverage report and mean different things, and the difference is the whole
# point of the record.
OPERATING = "OPERATING"
MANUFACTURING = "MANUFACTURING"
TECHNOLOGY = "TECHNOLOGY"
# SIC major group 70-89: services. Added in 2.10 because the 2.9 collection gates
# failed for one issuer on all twenty of its metrics, and the reason was not a
# wrong ruling -- it was that there were none, because a services classification
# fell outside the rule and an unrecognised classification deliberately makes
# none.
#
# It carries no exclusion of its own, and that is the point. A business model
# earns a place in this vocabulary by carrying a ruling, and this one currently
# does not, so adding it closes a metadata gap and deliberately moves no
# coverage. Had the collection numbers moved, that would have been the first
# thing to check rather than a result.
SERVICES = "SERVICES"
BUSINESS_MODELS = (
    OPERATING,
    MANUFACTURING,
    TECHNOLOGY,
    SERVICES,
    FINANCE_SERVICES,
    BANK,
    INSURANCE,
    REIT,
    MINING,
)

# Why a taxonomy carries no semantic metric. The distinctions are not decoration:
# a taxonomy of transaction mechanics needs no work, an industry taxonomy might,
# and a reader who cannot tell those apart gets a number with no remedy attached.
UNMODELLED_TRANSACTION_DISCLOSURE = "TRANSACTION_DISCLOSURE"
UNMODELLED_EXECUTIVE_COMPENSATION = "EXECUTIVE_COMPENSATION"
UNMODELLED_NARRATIVE_TEXT = "NARRATIVE_TEXT"
UNMODELLED_INDUSTRY_SPECIFIC = "INDUSTRY_SPECIFIC"
UNMODELLED_OUT_OF_SCOPE = "OUT_OF_SCOPE"
UNMODELLED_KINDS = (
    UNMODELLED_TRANSACTION_DISCLOSURE,
    UNMODELLED_EXECUTIVE_COMPENSATION,
    UNMODELLED_NARRATIVE_TEXT,
    UNMODELLED_INDUSTRY_SPECIFIC,
    UNMODELLED_OUT_OF_SCOPE,
)

# Metric vocabularies, mirroring the migration's triggers.
STATEMENTS = (
    "INCOME",
    "BALANCE_SHEET",
    "CASH_FLOW",
    "CAPITAL_RETURN",
    "MARKET",
)
UNIT_FAMILIES = ("currency", "per_share", "count", "ratio", "multiple")
PERIOD_TYPES = ("DURATION", "INSTANT")
APPLICABILITIES = ("APPLICABLE", "CONDITIONAL", "NOT_APPLICABLE")
METRIC_STATUSES = ("ACTIVE", "DEPRECASED", "PROPOSED")

# How an issuer came to be classified, mirroring the migration's trigger. A
# reader has to be able to tell "the filer publishes this" from "somebody decided
# this" without opening a comment, because the two support very different
# confidence in an inapplicability ruling.
BUSINESS_MODEL_BASES = (
    "DECLARED_BY_ISSUER",
    "DERIVED_FROM_REPORTED_CONCEPTS",
    "MANUAL_CLASSIFICATION",
)

# The mapping vocabulary, and the one rule that matters: only EXACT and
# EQUIVALENT let a series continue across a change of concept.
MAPPING_EXACT = "EXACT"
MAPPING_EQUIVALENT = "EQUIVALENT"
MAPPING_PARTIAL = "PARTIAL"
MAPPING_NON_COMPARABLE = "NON_COMPARABLE"

MAPPING_TYPES = (
    MAPPING_EXACT,
    MAPPING_EQUIVALENT,
    MAPPING_PARTIAL,
    MAPPING_NON_COMPARABLE,
)

# Why a source concept was considered for a metric and not mapped to it.
#
# Closed, because the distinction that matters is *which kind* of near-miss it
# is, and a free-text reason cannot be branched on. A component of the metric, a
# wider aggregate of it, a measure of something else, a count of a different
# population and a figure that is not a measurement at all all read as "not
# mapped" in a flat list, and they call for completely different responses:
# the first two are the metric's own definition, the third is a different
# question, the fourth is a near miss worth revisiting, and the fifth is out of
# scope entirely.
REASON_COMPONENT_OF = "COMPONENT_OF"
REASON_WIDER_AGGREGATE = "WIDER_AGGREGATE"
REASON_NARROWER_AGGREGATE = "NARROWER_AGGREGATE"
REASON_DIFFERENT_QUANTITY = "DIFFERENT_QUANTITY"
REASON_IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
REASON_NOT_A_METRIC = "NOT_A_METRIC"
DECLINE_REASONS = (
    REASON_COMPONENT_OF,
    REASON_WIDER_AGGREGATE,
    REASON_NARROWER_AGGREGATE,
    REASON_DIFFERENT_QUANTITY,
    REASON_IDENTITY_MISMATCH,
    REASON_NOT_A_METRIC,
)

# A series continues only through these. A PARTIAL mapping is a wider or
# narrower aggregate, and NON_COMPARABLE is a different quantity, so splicing
# across either would splice two different numbers into one line.
CONTINUING_MAPPINGS = frozenset({MAPPING_EXACT, MAPPING_EQUIVALENT})

#: Which of two different relations a mapping row asserts. Added in 2.73.
#:
#: IDENTITY      this source concept expresses this metric
#: COMPOSITION   this metric is composed from this source concept
#:
#: Deliberately orthogonal to `mapping_type`. An IDENTITY mapping may be EXACT or
#: PARTIAL; a COMPOSITION row is a declaration about an aggregate and is never a
#: destination claim. Before this existed both relations shared one row shape,
#: and 2.72 measured the result: promoting the component mapping left one concept
#: ambiguous between the aggregate naming it and the component it belongs to.
#:
#: Declared above ConceptMapping because that dataclass uses it as a field
#: default; placing it lower raises NameError at import.
MAPPING_IDENTITY = "IDENTITY"
MAPPING_COMPOSITION = "COMPOSITION"
MAPPING_RELATION_KINDS = (MAPPING_IDENTITY, MAPPING_COMPOSITION)

# The adoption basis, closed for the same reason every other vocabulary here is
# closed. `OBSERVED_ADOPTION` is the only honest claim available from a filing:
# "this filer's own filings reported this concept in these periods". It is not
# the taxonomy's validity period and not a statement that the filer intends to
# stop, and a value that let a stronger claim in would make "how much do we
# actually know here?" unanswerable.
OBSERVED_ADOPTION = "OBSERVED_ADOPTION"
ADOPTION_BASES = (OBSERVED_ADOPTION,)


class RegistryError(Exception):
    """The registry was asked for something it does not hold."""


@dataclass(frozen=True)
class Metric:
    """What a metric means, independently of who reports it."""

    metric_id: str
    display_name: str
    statement: str
    semantic_definition: str
    unit_family: str
    normal_period_type: str
    applicability: str = "APPLICABLE"
    comparability_group: Optional[str] = None
    status: str = "ACTIVE"
    # **The refusal surface.** Business models this metric is actually ruled out
    # for, which means: the evidence is not collected and the coverage surface
    # reports `NOT_APPLICABLE`. A row here is a *refusal*, and a refusal requires
    # an affirmative evidentiary basis.
    #
    # 2.25 split this from `exclusions` below because the two were the same field
    # and four refusals written in 2.7 from category intuition sat here with no
    # recorded basis. All four were refuted by filers of their own class. Only a
    # `SUPPORTED` exclusion belongs here, and as of 2.25 **there is none** -- which
    # is a finding, not a loss.
    inapplicable_in: Tuple[str, ...] = ()

    # Declared propositions about business models where the metric might not
    # exist, as `(business_model, state, proposition)`. Recorded whatever their
    # state, because a hypothesis nobody can see is a hypothesis that gets
    # re-derived from scratch and re-authored from the same intuition.
    #
    # `state` is one of PROPOSED / TESTABLE / SUPPORTED / REFUTED / UNDECIDED, and
    # **none of them except SUPPORTED has any authority over Evidence
    # collection.** A `TESTABLE` exclusion is a question the archive is asking,
    # not an answer it is acting on -- and that is the whole difference between a
    # hypothesis layer and a screener.
    exclusions: Tuple[Tuple[str, str, Optional[str]], ...] = ()

    def applies_to(self, business_model: Optional[str]) -> bool:
        """
        Whether the metric is applicable to a business.

        Consults the refusal surface only, never `exclusions`. A business model we
        do not know about is not evidence of inapplicability, so an unknown model
        applies rather than being refused; and a model we have a *hypothesis*
        about is not evidence either, so a `TESTABLE` or `UNDECIDED` exclusion
        does not refuse anything.

        The refused consequence is that a metric with an open proposition is asked
        and answered by the source: `COLLECTED` if the filer reports it,
        `SOURCE_SILENT` if not, and `NOT_YET_COLLECTED` only if we have not asked.
        All three are honest, and `SOURCE_SILENT` is not work to do -- which is
        why the safe direction is also the cheap one.
        """
        if self.applicability == "NOT_APPLICABLE":
            return False
        if not business_model or not self.inapplicable_in:
            return True
        return business_model not in self.inapplicable_in

    def contract_dict(self) -> Dict[str, Any]:
        return {
            "metric_id": self.metric_id,
            "display_name": self.display_name,
            "statement": self.statement,
            "semantic_definition": self.semantic_definition,
            "unit_family": self.unit_family,
            "normal_period_type": self.normal_period_type,
            "applicability": self.applicability,
            "comparability_group": self.comparability_group,
            "status": self.status,
            "inapplicable_in": list(self.inapplicable_in),
        }


@dataclass(frozen=True)
class Concept:
    """A source concept, with the source's own definition of it."""

    concept_id: str
    taxonomy: str
    concept: str
    label: Optional[str] = None
    source_definition: Optional[str] = None

    @property
    def qualified(self) -> str:
        return f"{self.taxonomy}:{self.concept}"

    def contract_dict(self) -> Dict[str, Any]:
        return {
            "concept_id": self.concept_id,
            "taxonomy": self.taxonomy,
            "concept": self.concept,
            "qualified": self.qualified,
            "label": self.label,
            "source_definition": self.source_definition,
        }


@dataclass(frozen=True)
class ConceptMapping:
    """How one source concept expresses one metric, and how exactly."""

    metric_id: str
    concept_id: str
    mapping_type: str
    effective_from: Optional[str] = None
    effective_to: Optional[str] = None
    notes: Optional[str] = None
    # Which relation this row asserts; see MAPPING_IDENTITY.
    relation_kind: str = MAPPING_IDENTITY
    # Structured breadth qualification, and the reason a PARTIAL identity mapping
    # is PARTIAL. It lives here rather than in a report so a resolver or query
    # consumer can tell why without parsing prose. None means no scope variation
    # has been measured -- NOT a claim that scope does not vary.
    scope: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        if self.mapping_type not in MAPPING_TYPES:
            raise RegistryError(
                f"mapping_type {self.mapping_type!r} is not in {list(MAPPING_TYPES)}"
            )
        if self.relation_kind not in MAPPING_RELATION_KINDS:
            raise RegistryError(
                f"relation_kind {self.relation_kind!r} is not in"
                f" {list(MAPPING_RELATION_KINDS)}"
            )
        if self.mapping_type not in CONTINUING_MAPPINGS and not (
            self.effective_from or self.effective_to
        ):
            raise RegistryError(
                f"{self.mapping_type} mapping must record effective dates, "
                "because the series does not continue across it"
            )

    @property
    def series_continues(self) -> bool:
        return self.mapping_type in CONTINUING_MAPPINGS

    def applies_on(self, when: Optional[str]) -> bool:
        """
        Whether the mapping held on a date.

        No date means no time filter, so every mapping applies. Narrowing to the
        unbounded ones would silently hide a concept that stopped being reported,
        which is the one thing this table exists to make visible.
        """
        if not when:
            return True
        if self.effective_from and when < self.effective_from:
            return False
        if self.effective_to and when > self.effective_to:
            return False
        return True

    def contract_dict(self) -> Dict[str, Any]:
        return {
            "metric_id": self.metric_id,
            "concept_id": self.concept_id,
            "mapping_type": self.mapping_type,
            "relation_kind": self.relation_kind,
            "scope": self.scope,
            "series_continues": self.series_continues,
            "effective_from": self.effective_from,
            "effective_to": self.effective_to,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class DeclinedConcept:
    """
    A source concept that was weighed against a metric and rejected.

    The counterpart to `ConceptMapping`, and the more informative of the two for
    a coverage question. A mapping says "this concept means this metric". This
    says "this concept was considered, and here is why it is not" -- which is
    what separates a metric ST-EVA has no opinion about from one it has decided
    about, and those are different things to read in a coverage report.
    """

    concept_id: str
    considered_for_metric: str
    reason_code: str
    reason: str
    # Which framework reading produced it, so a decline about an IFRS element is
    # not read as a claim about the US-GAAP one. None where the judgement does
    # not depend on the framework.
    framework_basis: Optional[str] = None

    def __post_init__(self) -> None:
        if self.reason_code not in DECLINE_REASONS:
            raise RegistryError(
                f"decline reason_code {self.reason_code!r} is not in "
                f"{list(DECLINE_REASONS)}"
            )
        if not self.reason or not self.reason.strip():
            # A decline with no stated reason is an omission wearing a
            # decision's clothes, and the code alone does not say which of the
            # six it is.
            raise RegistryError(
                "a decline must state why, not only which category"
            )
        if ":" not in (self.concept_id or ""):
            raise RegistryError(
                "a decline concept_id must be qualified as taxonomy:concept"
            )

    def contract_dict(self) -> Dict[str, Any]:
        return {
            "concept_id": self.concept_id,
            "considered_for_metric": self.considered_for_metric,
            "reason_code": self.reason_code,
            "reason": self.reason,
            "framework_basis": self.framework_basis,
        }


@dataclass(frozen=True)
class ConceptAdoption:
    """
    One filer's observed use of one concept, over a period.

    The counterpart to `ConceptMapping`, and the reason that class cannot answer
    every question. A mapping says what a concept means; this says when one
    company was seen using it. They differ, and conflating them is what produced
    a global window that was really AAPL's filing history.

    `basis` is `OBSERVED_ADOPTION` and nothing else. These are the periods that
    filer's filings reported, which is a weaker claim than a statement of intent:
    a filer that stopped reporting in 2018 has not necessarily retired the
    concept, and this record must never be read as saying that it has.
    """

    asset_id: str
    concept_id: str
    first_used: Optional[str]
    last_used: Optional[str]
    fact_count: int
    filing_count: int
    basis: str = OBSERVED_ADOPTION

    def covers(self, when: Optional[str]) -> bool:
        """
        Whether this filer was observed using the concept on a date.

        No date means no time filter, matching `ConceptMapping.applies_on`. An
        unobserved date is not evidence of non-use, so a caller asking about a
        date with no adoption record must not read this as a refusal.
        """
        if not when:
            return True
        if self.first_used and when < self.first_used:
            return False
        if self.last_used and when > self.last_used:
            return False
        return True

    def contract_dict(self) -> Dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "concept_id": self.concept_id,
            "first_used": self.first_used,
            "last_used": self.last_used,
            "fact_count": self.fact_count,
            "filing_count": self.filing_count,
            "basis": self.basis,
        }


@dataclass(frozen=True)
class ResolvedEvidence:
    """
    An observation resolved through the registry.

    `metric` is None when the registry does not hold the concept. That is the
    answer, and it is deliberately not filled with a name-based guess: an
    unmapped concept must be visible as unmapped rather than quietly attached
    to the nearest metric.
    """

    observation_id: str
    concept_id: Optional[str]
    metric: Optional[Metric]
    mappings: Tuple[ConceptMapping, ...] = ()
    series_breaks: Tuple[Dict[str, Any], ...] = ()
    # What the filing evidence says this filer did with the concept, when it has
    # been ingested. None means "not observed", which is a gap in what we hold
    # and never a claim that the filer did not use the concept.
    adoption: Optional[ConceptAdoption] = None
    # True when adoption supplied a period the mapping window did not cover. It
    # is surfaced rather than silently absorbed, because a figure that resolves
    # outside its concept's stated window is worth a reader knowing about.
    adopted_outside_mapping_window: bool = False

    @property
    def is_resolved(self) -> bool:
        return self.metric is not None

    def contract_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "observation_id": self.observation_id,
            "resolved": self.is_resolved,
            "concept": self.concept_id,
            "metric": self.metric.metric_id if self.metric else None,
            "metric_definition": (
                self.metric.semantic_definition if self.metric else None
            ),
            "mappings": [mapping.contract_dict() for mapping in self.mappings],
            "series_breaks": [dict(break_) for break_ in self.series_breaks],
            "issuer_adoption": (
                self.adoption.contract_dict() if self.adoption else None
            ),
            "adopted_outside_mapping_window": (
                self.adopted_outside_mapping_window
            ),
        }
        if not self.is_resolved:
            payload["reason"] = (
                self.series_breaks[0]["explanation"]
                if self.series_breaks
                else (
                    "NOT_EXPLAINED. No registry mapping relates this concept to "
                    "a metric. It is left unresolved rather than attached to "
                    "the metric whose name looks nearest."
                )
            )
        return payload


@dataclass(frozen=True)
class ObservationMapping:
    """
    What a single historical observation resolves to, given the fact it came from.

    `mappings_for_metric` answers *what a metric declares*. That is a
    metric-level question and it is the right question for a ledger, a gate or an
    ingestion plan. It is the wrong question for one observation, because every
    observation carries a source concept and the concept, not the metric name,
    is what says what the figure means.

    Under a supersession the two diverge sharply. `mappings_for_metric('debt')`
    follows `debt -> long_term_debt` and returns every concept the successor
    declares, so a single legacy row looks as though it carried all of them --
    and a concept with no established destination for the successor inherits an
    interpretation simply by sharing a predecessor name with four others. 2.49
    measured that over 8,193 historical rows and found the exposure invisible in
    every coverage count, because the concept set does not change.

    So this type carries the three things that record:

      * the **stored** metric, which is never rewritten here,
      * the **resolved** metric, which is what lineage says the name now means,
      * the mappings applicable to **this observation's own concept**, and
        nothing else.

    The status is explicit rather than derived from emptiness. `UNRESOLVED` with
    a reason is an answer; an empty list that a caller is invited to read as
    "nothing special" is not.
    """

    # The concept has a declared mapping on the resolved metric, and that
    # mapping is the one that applies.
    RESOLVED = "RESOLVED"
    # The observation carries no source concept, so nothing can be said about
    # what it means. Never inferred away, and never treated as "unmapped
    # because the registry is silent".
    UNRESOLVED_NO_SOURCE_CONCEPT = "UNRESOLVED_NO_SOURCE_CONCEPT"
    # The resolved metric declares no mapping for this concept. The observation
    # keeps its historical identity and gains no successor interpretation.
    UNRESOLVED_NO_APPLICABLE_MAPPING = "UNRESOLVED_NO_APPLICABLE_MAPPING"

    stored_metric_id: str
    resolved_metric_id: str
    source_concept: Optional[str]
    mappings: Tuple[ConceptMapping, ...] = ()
    status: str = RESOLVED
    reason: str = ""
    supersession: Optional[Dict[str, Any]] = None

    @property
    def is_superseded(self) -> bool:
        """
        Whether the stored metric was actually superseded.

        Read from the recorded supersession rather than inferred from the
        destination differing. 2.67 introduced a case where the two legitimately
        differ with no supersession involved: a concept declared directly by a
        component metric resolves to that component while the row is still
        stored under an unrelated active metric. Inferring supersession from the
        difference would report that as a rename, which it is not.
        """
        return self.supersession is not None

    @property
    def is_resolved(self) -> bool:
        # Both conditions, deliberately. A status alone could be positive while
        # the mapping tuple was empty, and an empty tuple is not a resolution.
        return self.status == self.RESOLVED and bool(self.mappings)

    @property
    def mapping_types(self) -> Tuple[str, ...]:
        return tuple(mapping.mapping_type for mapping in self.mappings)

    def contract_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "stored_metric": self.stored_metric_id,
            "resolved_metric": self.resolved_metric_id,
            "superseded": self.is_superseded,
            "source_concept": self.source_concept,
            "status": self.status,
            "resolved": self.is_resolved,
            "mappings": [mapping.contract_dict() for mapping in self.mappings],
            "mapping_types": list(self.mapping_types),
        }
        if self.supersession:
            payload["supersession"] = dict(self.supersession)
        if not self.is_resolved:
            payload["reason"] = self.reason
        return payload


def concept_id_for(taxonomy: str, concept: str) -> str:
    return f"{taxonomy}:{concept}"


@dataclass(frozen=True)
class ConceptResolution:
    """
    Where one source concept points, and how that conclusion was reached.

    The distinction this type exists to carry is **origin**. A metric can claim a
    concept because it declared that mapping itself, or because the metric was
    superseded and the mapping only became visible through the chain. 2.66 measured
    a concept carrying three claimants at once -- its own component metric, the
    superseded `debt`, and the successor `long_term_debt` -- and `resolve`
    answered "ambiguous" for all 3,378 legacy rows, so the current/noncurrent
    split was never selected and everything collapsed onto the total.

    Origin is not a ranking of metrics by name, value, period or insertion order.
    It is the difference between "this metric declares this concept" and "this
    mapping is visible only because that metric was renamed".

    An inherited mapping is an affirmative destination only when it is EXACT. A
    PARTIAL proposition that has not been promoted is a characterisation, not a
    decision, and 2.47 and 2.51 both left the IFRS concepts unauthorised.
    """

    RESOLVED = "RESOLVED"
    AMBIGUOUS_MAPPING = "AMBIGUOUS_MAPPING"
    UNRESOLVED_NO_SOURCE_CONCEPT = "UNRESOLVED_NO_SOURCE_CONCEPT"
    UNRESOLVED_NO_APPLICABLE_MAPPING = "UNRESOLVED_NO_APPLICABLE_MAPPING"

    DIRECT = "DIRECT"
    INHERITED = "INHERITED"

    source_concept: Optional[str]
    status: str
    destination_metric: Optional[str] = None
    mapping_origin: Optional[str] = None
    mapping_type: Optional[str] = None
    effective_from: Optional[str] = None
    effective_to: Optional[str] = None
    notes: Optional[str] = None
    # Structured scope carried from the winning mapping, so a caller can see why
    # a PARTIAL destination is partial without reading notes.
    scope: Optional[Dict[str, Any]] = None
    candidates: Tuple[str, ...] = ()
    detail: str = ""

    @property
    def is_exact(self) -> bool:
        """
        Whether the destination is an identity claim rather than a component.

        Separate from `is_resolved` so a consumer can ask "does this concept
        express that metric" and "may I treat it as the whole metric" without
        re-deriving the second from `mapping_type` each time.
        """
        return self.is_resolved and self.mapping_type == "EXACT"

    @property
    def is_component(self) -> bool:
        """A resolved destination that contributes without expressing all of it."""
        return self.is_resolved and self.mapping_type == "PARTIAL"

    @property
    def is_resolved(self) -> bool:
        """
        RESOLVED *and* a destination.

        A status alone can be read as resolved while naming nowhere, so both are
        required. This is the same shape as `ObservationMapping.is_resolved`, and
        for the same reason.
        """
        return self.status == self.RESOLVED and bool(self.destination_metric)

    def contract_dict(self) -> Dict[str, Any]:
        return {
            "source_concept": self.source_concept,
            "status": self.status,
            "resolved": self.is_resolved,
            "destination_metric": self.destination_metric,
            "mapping_origin": self.mapping_origin,
            "mapping_type": self.mapping_type,
            "exact": self.is_exact,
            "component": self.is_component,
            "effective_from": self.effective_from,
            "effective_to": self.effective_to,
            "scope": self.scope,
            "notes": self.notes,
            "candidates": list(self.candidates),
            "detail": self.detail,
        }


def _optional_column(row, column: str):
    """
    Read a column a pre-2.73 archive does not have.

    `sqlite3.Row` raises IndexError for an unknown column name and a plain dict
    would raise KeyError. An archive opened read-only never applies migrations, so
    an absent column is expected rather than exceptional, and it means absent
    metadata -- it must not raise and must not become a value.
    """
    try:
        return row[column]
    except (IndexError, KeyError):
        return None


def _read_scope(row) -> Optional[Dict[str, Any]]:
    """
    Read a mapping's structured scope, tolerating a pre-2.73 archive.

    A missing column, an empty value and malformed JSON all yield None: scope is a
    qualification, and losing it must not make a mapping unreadable.
    """
    raw = _optional_column(row, "scope_json")
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _scope_is_measured(scope: Optional[Dict[str, Any]]) -> bool:
    """
    Whether a PARTIAL mapping's narrower scope was actually measured.

    This is the whole of F1's correction, and it is deliberately one predicate
    over the evidence that already exists. `_read_scope` has already turned a
    missing column, an empty value, malformed JSON and a non-object payload into
    `None`, so what remains to ask is whether there is any scope at all -- an
    absence of evidence, not a question about JSON syntax.

    No per-mapping flag is added and nothing about an analyst's conclusion is
    stored: `scope` is the measurement, and this asks only whether it is present.
    A PARTIAL with no scope has not been characterised, so it is unknown, and
    unknown stays unknown.
    """
    return isinstance(scope, dict) and bool(scope)


class CoreRegistry:
    """A read/write view over the three registry tables."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    # -- writes ----------------------------------------------------------

    def add_metric(
        self,
        metric: Metric,
    ) -> str:
        self.connection.execute(
            "INSERT OR REPLACE INTO metric_registry (metric_id, display_name,"
            " statement, semantic_definition, unit_family, normal_period_type,"
            " applicability, comparability_group, status)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                metric.metric_id,
                metric.display_name,
                metric.statement,
                metric.semantic_definition,
                metric.unit_family,
                metric.normal_period_type,
                metric.applicability,
                metric.comparability_group,
                metric.status,
            ),
        )
        # `inapplicable_in` is deliberately not a parameter here.
        #
        # It was, until 2.26's audit, and that was a bypass: `seed()` passed
        # `metric.inapplicable_in` straight through, so any metric dataclass
        # declaring an exclusion repopulated the refusal surface with no
        # proposition and no lifecycle state -- which is precisely what the
        # SUPPORTED-only contract exists to prevent. It happened to be inert
        # because every seeded exclusion is empty, but a contract is only as
        # strong as the narrowest path to the surface, and the narrowest path is
        # the one nobody remembers closing.
        #
        # The only writer is now `support_exclusion`, and
        # `tests/test_semantic_conflict.py::TestTheRefusalSurfaceHasOneEntryPoint`
        # is what keeps it that way.
        self._record_exclusions(metric)
        self.connection.commit()
        return metric.metric_id

    def _record_exclusions(self, metric: Metric) -> None:
        """
        The hypothesis layer, written beside the metric.

        Separate from `metric_inapplicable_in` because those two tables answer
        different questions and were the same table until 2.25:

            metric_exclusion       what we are claiming, and on what evidence
            metric_inapplicable_in what we are refusing, which is SUPPORTED only

        The proposition text is stored because a claim that cannot say what would
        refute it cannot be refuted, and one that never says what would support it
        cannot be supported.
        """
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS metric_exclusion ("
            " metric_id TEXT NOT NULL REFERENCES metric_registry(metric_id),"
            " business_model TEXT NOT NULL,"
            " state TEXT NOT NULL CHECK (state IN ('PROPOSED','TESTABLE',"
            "   'SUPPORTED','REFUTED','UNDECIDED')),"
            " proposition TEXT,"
            " refuted_by_ticker TEXT, refuted_by_concept TEXT,"
            " refuted_by_observations INTEGER,"
            " support_basis TEXT, recorded_at TEXT NOT NULL,"
            " PRIMARY KEY (metric_id, business_model))"
        )
        for model, state, proposition in metric.exclusions:
            self.connection.execute(
                "INSERT OR IGNORE INTO metric_exclusion"
                " (metric_id, business_model, state, proposition, recorded_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    metric.metric_id, model, state, proposition, utc_now(),
                ),
            )

    def exclusion_states(self) -> Dict[str, Dict[str, str]]:
        """
        Every declared proposition and its state, keyed metric then class.

        The question 2.25 exists to make answerable: *what is the registry
        claiming, and on what evidence?* Before the split, the only way to ask it
        was to read the coverage report and see which metrics had no rows.
        """
        if not self._has_table("metric_exclusion"):
            return {}
        out: Dict[str, Dict[str, str]] = defaultdict(dict)
        for row in self.connection.execute(
            "SELECT metric_id, business_model, state FROM metric_exclusion"
        ):
            out[str(row["metric_id"])][str(row["business_model"])] = str(
                row["state"]
            )
        return dict(out)

    def support_exclusion(self, metric_id: str, business_model: str) -> None:
        """
        Promote a proposition to a refusal. The deliberate act.

        Refusing Evidence collection is not a data edit, so it is not one here
        either: a proposition becomes a refusal by being marked `SUPPORTED` on a
        named basis and by then entering the refusal surface. There is no path
        that does this implicitly, because the failure mode this whole round
        exists to undo is a refusal that appeared without anyone deciding to
        make one.
        """
        row = self.connection.execute(
            "SELECT state FROM metric_exclusion WHERE metric_id = ?"
            " AND business_model = ?",
            (metric_id, business_model),
        ).fetchone()
        if row is None:
            raise RegistryError(
                f"no such exclusion: {metric_id} x {business_model}"
            )
        self.connection.execute(
            "UPDATE metric_exclusion SET state = 'SUPPORTED'"
            " WHERE metric_id = ? AND business_model = ?",
            (metric_id, business_model),
        )
        self._set_inapplicable(metric_id, [business_model])
        self.connection.commit()

    def _has_table(self, name: str) -> bool:
        return self.connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (name,),
        ).fetchone() is not None

    def _set_inapplicable(self, metric_id: str, models: Sequence[str]) -> None:
        """
        Applicability per business model.

        Held beside the metric rather than inside it, because a model is a
        property of the issuer and not of the metric. It is recorded only when
        a business model is actually excluded; an empty list stays empty, and
        never stands in for a retrieval that found nothing.

        The table is created once and never rebuilt. Dropping it per call would
        silently discard the previous metric's exclusions, which is how an
        operating income would quietly become applicable to a bank.
        """
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS metric_inapplicable_in ("
            " metric_id TEXT NOT NULL REFERENCES metric_registry(metric_id),"
            " business_model TEXT NOT NULL,"
            " PRIMARY KEY (metric_id, business_model))"
        )
        for model in models:
            self.connection.execute(
                "INSERT OR IGNORE INTO metric_inapplicable_in"
                " (metric_id, business_model) VALUES (?, ?)",
                (metric_id, model),
            )

    def set_issuer_business_model(
        self,
        asset_id: str,
        business_model: str,
        basis: str = "MANUAL_CLASSIFICATION",
        source: Optional[str] = None,
    ) -> None:
        """
        Record which business an issuer is in, and how that was established.

        Issuer metadata, not a metric property and not a company code path. The
        reason this exists is that `metric_inapplicable_in` had a column no row
        could fill, so a metric correctly declared inapplicable for a financial
        institution could never be resolved for one -- and the surface fell
        through to `UNAVAILABLE`, reporting a retrieval failure for a line that
        does not exist.
        """
        if business_model not in BUSINESS_MODELS:
            raise RegistryError(
                f"business_model {business_model!r} is not in "
                f"{list(BUSINESS_MODELS)}"
            )
        if not self._has_business_models():
            raise RegistryError(
                "this archive predates migration 0010 and has no "
                "issuer_business_model table. Writing a classification into an "
                "archive that cannot be migrated would record a fact with "
                "nothing enforcing its vocabulary."
            )
        if basis not in BUSINESS_MODEL_BASES:
            raise RegistryError(
                f"business model basis {basis!r} is not in "
                f"{list(BUSINESS_MODEL_BASES)}"
            )
        if basis != "MANUAL_CLASSIFICATION" and not source:
            raise RegistryError(
                "a declared or derived business model must name the source it "
                "came from; an inapplicability ruling rests on it"
            )
        self.connection.execute(
            "INSERT OR REPLACE INTO issuer_business_model (asset_id,"
            " business_model, basis, source, recorded_at) VALUES (?, ?, ?, ?, ?)",
            (asset_id, business_model, basis, source, utc_now()),
        )
        self.connection.commit()

    def mark_taxonomy_unmodelled(
        self,
        taxonomy: str,
        kind: str,
        reason: str,
    ) -> None:
        """
        Declare that a source taxonomy carries no semantic metric, and say why.

        2.8 could not answer "what does a filer report that we have no mapping
        for?", and the answer turned out to be worth having: across six issuers
        the unmodelled part of a filer's XBRL is nineteen concepts in four
        taxonomies, and reading them shows they are the mechanics of securities
        offerings, executive compensation, narrative tagging and one industry
        namespace. None is a financial-statement metric.

        So the record is a *declaration about a taxonomy*, not a decline per
        concept and certainly not a coverage gap. A table rather than a name
        rule in the ledger, because a taxonomy is the unit at which the answer
        exists and because a name-based rule would have to match a concept to a
        metric -- the "similar label" problem 2.7 spent a phase refusing to
        solve by name.
        """
        if kind not in UNMODELLED_KINDS:
            raise RegistryError(
                f"unmodelled taxonomy kind {kind!r} is not in "
                f"{list(UNMODELLED_KINDS)}"
            )
        if not (reason or "").strip():
            raise RegistryError(
                "a taxonomy declared unmodelled must say why; a reader cannot "
                "tell whether it needs work without it"
            )
        self.connection.execute(
            "INSERT OR REPLACE INTO unmodelled_taxonomies (taxonomy, kind,"
            " reason, recorded_at) VALUES (?, ?, ?, ?)",
            (taxonomy, kind, reason, utc_now()),
        )
        self.connection.commit()

    def unmodelled_taxonomies(self) -> Dict[str, Dict[str, Any]]:
        """
        Every taxonomy the semantic layer declares nothing against, with its
        reason. Empty on an archive predating migration 0013, which is correct:
        such an archive has made no such declaration.
        """
        if self.connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table'"
            " AND name = 'unmodelled_taxonomies'"
        ).fetchone() is None:
            return {}
        return {
            row["taxonomy"]: {
                "kind": row["kind"],
                "reason": row["reason"],
            }
            for row in self.connection.execute(
                "SELECT taxonomy, kind, reason FROM unmodelled_taxonomies"
                " ORDER BY taxonomy"
            )
        }

    def modelled_taxonomies(self) -> List[str]:
        """
        The taxonomies the semantic layer does model.

        Read from the concepts themselves rather than from a configured list, so
        it cannot fall behind a mapping that was added. A taxonomy is modelled
        when something in it has been given a definition.
        """
        return [
            row["taxonomy"]
            for row in self.connection.execute(
                "SELECT DISTINCT taxonomy FROM concept_registry"
                " ORDER BY taxonomy"
            )
        ]

    def decline_concept_mapping(
        self,
        concept_id: str,
        considered_for_metric: str,
        reason_code: str,
        reason: str,
        framework_basis: Optional[str] = None,
    ) -> None:
        """
        Record a source concept that was weighed against a metric and rejected.

        The counterpart to `add_mapping`, and the more informative of the two.
        A mapping says "this concept means this metric"; a decline says "this
        concept was considered for this metric and here is why it is not", which
        is the information a coverage figure needs and cannot get from a count.

        Without it, 2.7's nine IFRS decisions lived in seed-file prose, and an
        archive holding 3.0% of a filer's concepts could report what it held and
        not what it had deliberately left out. Those are different claims and a
        reader is entitled to the difference.

        Validated by building a `DeclinedConcept` and writing that, rather than
        by writing the fields directly. Two validation paths is how a blank
        reason ends up in a table whose trigger refuses one: the dataclass
        checked it on the seed path and the method did not check it here.
        """
        record = DeclinedConcept(
            concept_id=concept_id,
            considered_for_metric=considered_for_metric,
            reason_code=reason_code,
            reason=reason,
            framework_basis=framework_basis,
        )
        self.connection.execute(
            "INSERT OR REPLACE INTO declined_concept_mappings (concept_id,"
            " considered_for_metric, reason_code, reason, framework_basis,"
            " recorded_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                record.concept_id,
                record.considered_for_metric,
                record.reason_code,
                record.reason,
                record.framework_basis,
                utc_now(),
            ),
        )
        self.connection.commit()

    def declines_for_metric(
        self,
        metric_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Every concept that was considered for one metric and declined.

        Sorted by concept so a coverage report is stable between runs, which
        matters more here than it sounds: this list is read by a language model
        through the query surface, and a reordering would look like a change in
        what ST-EVA holds.

        Empty on an archive predating migration 0012, for the same reason
        `business_model_of` is: an archive that cannot have recorded a decision
        has recorded none, and the read path may not demand a migration it cannot
        ask for.
        """
        if not self._has_decline_records():
            return []
        return [
            dict(row)
            for row in self.connection.execute(
                "SELECT concept_id, considered_for_metric, reason_code, reason,"
                " framework_basis FROM declined_concept_mappings"
                " WHERE considered_for_metric = ? ORDER BY concept_id",
                (metric_id,),
            )
        ]

    def _has_decline_records(self) -> bool:
        return self.connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table'"
            " AND name = 'declined_concept_mappings'"
        ).fetchone() is not None

    def all_declines(self) -> List[Dict[str, Any]]:
        if not self._has_decline_records():
            return []
        return [
            dict(row)
            for row in self.connection.execute(
                "SELECT concept_id, considered_for_metric, reason_code, reason,"
                " framework_basis FROM declined_concept_mappings"
                " ORDER BY considered_for_metric, concept_id"
            )
        ]

    def business_model_of(self, asset_id: str) -> Optional[Dict[str, Any]]:
        """
        The issuer's business model, with its basis and source.

        `None` for an issuer nobody has classified, and that is a meaningful
        answer rather than a missing one: an unclassified issuer gets no
        inapplicability ruling, so every declared metric stays applicable. A
        business model we do not know about is not evidence that a metric does
        not apply, and `Metric.applies_to` is written the same way.

        `None` also for an archive built before migration 0010, which has no such
        table. That is the same answer and for the same reason, and it is
        deliberate: the read path must not require a migration it cannot demand.
        An evaluation archive is a frozen record of what a build produced, and
        every 2.1 through 2.6 result was read out of one that predates this
        migration. Applying it would change the bytes and the contents of the
        ground truth those results were graded against, so the older archive has
        to keep answering -- with no classifications in it, and therefore no
        inapplicability rulings, which is exactly what it knew before.
        """
        if not self._has_business_models():
            return None
        row = self.connection.execute(
            "SELECT asset_id, business_model, basis, source, recorded_at"
            " FROM issuer_business_model WHERE asset_id = ?",
            (asset_id,),
        ).fetchone()
        return dict(row) if row is not None else None

    def _has_business_models(self) -> bool:
        return self.connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table'"
            " AND name = 'issuer_business_model'"
        ).fetchone() is not None

    def inapplicable_metrics(self, business_model: str) -> List[str]:
        """Every metric declared inapplicable to one business, in metric order."""
        return [
            row["metric_id"]
            for row in self.connection.execute(
                "SELECT metric_id FROM metric_inapplicable_in"
                " WHERE business_model = ? ORDER BY metric_id",
                (business_model,),
            )
        ]

    def add_concept(self, concept: Concept) -> str:
        self.connection.execute(
            "INSERT OR REPLACE INTO concept_registry (concept_id, taxonomy,"
            " concept, label, source_definition) VALUES (?, ?, ?, ?, ?)",
            (
                concept.concept_id,
                concept.taxonomy,
                concept.concept,
                concept.label,
                concept.source_definition,
            ),
        )
        self.connection.commit()
        return concept.concept_id

    def add_mapping(self, mapping: ConceptMapping) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO metric_concept_mapping (metric_id,"
            " concept_id, mapping_type, effective_from, effective_to, notes,"
            " relation_kind, scope_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                mapping.metric_id,
                mapping.concept_id,
                mapping.mapping_type,
                mapping.effective_from,
                mapping.effective_to,
                mapping.notes,
                mapping.relation_kind,
                None if mapping.scope is None else json.dumps(
                    mapping.scope, sort_keys=True, separators=(",", ":")),
            ),
        )
        self.connection.commit()

    def record_adoption(
        self,
        asset_id: str,
        concept_id: str,
        first_used: Optional[str],
        last_used: Optional[str],
        fact_count: int = 0,
        filing_count: int = 0,
        observed_at: Optional[str] = None,
    ) -> None:
        """
        Record that one filer was observed using one concept.

        Evidence, not a claim about intent. `first_used` and `last_used` are the
        periods that filer's own filings reported; they say nothing about
        whether the filer intends to continue, and a filer that stopped in 2018
        is recorded as having stopped in 2018 rather than as having retired the
        concept. The basis column is `OBSERVED_ADOPTION` and only that, enforced
        by trigger.

        Idempotent and monotone: re-observing a period extends the window rather
        than replacing it, so a later ingestion covering more history widens what
        is known instead of silently narrowing it.
        """
        stamp = observed_at or utc_now()
        self.connection.execute(
            "INSERT INTO issuer_concept_adoption (asset_id, concept_id,"
            " first_used, last_used, fact_count, filing_count, basis,"
            " first_seen_at, last_seen_at) VALUES (?, ?, ?, ?, ?, ?,"
            " 'OBSERVED_ADOPTION', ?, ?)"
            " ON CONFLICT(asset_id, concept_id) DO UPDATE SET"
            "   first_used = CASE"
            "     WHEN issuer_concept_adoption.first_used IS NULL THEN excluded.first_used"
            "     WHEN excluded.first_used IS NULL THEN issuer_concept_adoption.first_used"
            "     WHEN excluded.first_used < issuer_concept_adoption.first_used"
            "       THEN excluded.first_used"
            "     ELSE issuer_concept_adoption.first_used END,"
            "   last_used = CASE"
            "     WHEN excluded.last_used IS NULL THEN issuer_concept_adoption.last_used"
            "     WHEN issuer_concept_adoption.last_used IS NULL THEN excluded.last_used"
            "     WHEN excluded.last_used > issuer_concept_adoption.last_used"
            "       THEN excluded.last_used"
            "     ELSE issuer_concept_adoption.last_used END,"
            "   fact_count = issuer_concept_adoption.fact_count + excluded.fact_count,"
            "   filing_count = issuer_concept_adoption.filing_count + excluded.filing_count,"
            "   last_seen_at = excluded.last_seen_at",
            (
                asset_id,
                concept_id,
                first_used,
                last_used,
                fact_count,
                filing_count,
                stamp,
                stamp,
            ),
        )
        self.connection.commit()

    def adoption_for(
        self,
        asset_id: str,
        concept_id: str,
    ) -> Optional[ConceptAdoption]:
        """
        What one filer was observed doing with one concept.

        None means *not observed*, which is not the same as *not used*: a filer
        whose evidence has not been ingested has no adoption record, and that is
        a gap in what we hold rather than a fact about the filer. Callers must
        treat None as unknown and must not read it as "never used".
        """
        row = self.connection.execute(
            "SELECT * FROM issuer_concept_adoption"
            " WHERE asset_id = ? AND concept_id = ?",
            (asset_id, concept_id),
        ).fetchone()
        if row is None:
            return None
        return ConceptAdoption(
            asset_id=row["asset_id"],
            concept_id=row["concept_id"],
            first_used=row["first_used"],
            last_used=row["last_used"],
            fact_count=row["fact_count"],
            filing_count=row["filing_count"],
            basis=row["basis"],
        )

    def adoptions_for_asset(
        self,
        asset_id: str,
    ) -> List[ConceptAdoption]:
        rows = self.connection.execute(
            "SELECT * FROM issuer_concept_adoption WHERE asset_id = ?"
            " ORDER BY concept_id",
            (asset_id,),
        ).fetchall()
        return [
            ConceptAdoption(
                asset_id=row["asset_id"],
                concept_id=row["concept_id"],
                first_used=row["first_used"],
                last_used=row["last_used"],
                fact_count=row["fact_count"],
                filing_count=row["filing_count"],
                basis=row["basis"],
            )
            for row in rows
        ]

    # -- reads -----------------------------------------------------------

    def metric(self, metric_id: str) -> Optional[Metric]:
        row = self.connection.execute(
            "SELECT * FROM metric_registry WHERE metric_id = ?",
            (metric_id,),
        ).fetchone()
        if row is None:
            return None
        models = [
            r["business_model"]
            for r in self.connection.execute(
                "SELECT business_model FROM metric_inapplicable_in"
                " WHERE metric_id = ?",
                (metric_id,),
            )
        ]
        return Metric(
            metric_id=row["metric_id"],
            display_name=row["display_name"],
            statement=row["statement"],
            semantic_definition=row["semantic_definition"],
            unit_family=row["unit_family"],
            normal_period_type=row["normal_period_type"],
            applicability=row["applicability"],
            comparability_group=row["comparability_group"],
            status=row["status"],
            inapplicable_in=tuple(sorted(models)),
        )

    def concept(self, concept_id: str) -> Optional[Concept]:
        row = self.connection.execute(
            "SELECT * FROM concept_registry WHERE concept_id = ?"
            " OR (taxonomy || ':' || concept) = ? LIMIT 1",
            (concept_id, concept_id),
        ).fetchone()
        if row is None:
            return None
        return Concept(
            concept_id=row["concept_id"],
            taxonomy=row["taxonomy"],
            concept=row["concept"],
            label=row["label"],
            source_definition=row["source_definition"],
        )

    def metrics(self, statement: Optional[str] = None) -> List[Metric]:
        if statement:
            rows = self.connection.execute(
                "SELECT metric_id FROM metric_registry WHERE statement = ?"
                " ORDER BY metric_id",
                (statement,),
            ).fetchall()
        else:
            rows = self.connection.execute(
                "SELECT metric_id FROM metric_registry ORDER BY metric_id"
            ).fetchall()
        return [
            metric
            for metric in (self.metric(row["metric_id"]) for row in rows)
            if metric is not None
        ]

    def resolve_metric(self, metric_id: str) -> Optional[str]:
        """
        Follow a supersession chain to the metric that now carries the meaning.

        A metric that has been renamed keeps its row and keeps every observation
        recorded against it, because `observations.metric` is part of the contract
        id and rewriting it would change `observation_id` and manufacture new
        historical Evidence out of a naming decision. What changes is the question
        *what does this metric denote*, and it is answered here rather than by
        editing rows that are supposed to be immutable.

        Resolution follows the chain to its end and **fails loudly on a cycle**,
        because a supersession table that can loop would make every meaning in the
        archive ambiguous, and that is worse than an unresolved name.

        Returns the id unchanged when nothing supersedes it, so callers need not
        special-case the common case.
        """
        seen = [metric_id]
        current = metric_id
        if not self._has_table("metric_supersession"):
            # An archive opened without the migration -- a read-only consumer, or a
            # fixture that builds its schema directly. Nothing has superseded
            # anything in a store that has never heard of supersession, so the id
            # stands. Failing here would make an older archive unreadable rather
            # than merely un-renamed.
            return current
        for _ in range(8):
            row = self.connection.execute(
                "SELECT successor_id FROM metric_supersession"
                " WHERE predecessor_id = ?", (current,)
            ).fetchone()
            if row is None:
                return current
            current = str(row["successor_id"])
            if current in seen:
                raise RegistryError(
                    "metric supersession cycle: "
                    + " -> ".join(seen + [current])
                )
            seen.append(current)
        raise RegistryError(
            "metric supersession chain longer than expected: "
            + " -> ".join(seen)
        )

    def supersession_of(self, metric_id: str) -> Optional[Dict[str, Any]]:
        """
        The recorded decision, if this metric has been superseded.

        Returns None when the archive has no supersession table, for the same
        reason `resolve_metric` does: a store that has never heard of
        supersession has not superseded anything, and reporting the absence of a
        table as an error would make an older archive unreadable rather than
        merely un-renamed.
        """
        if not self._has_table("metric_supersession"):
            return None
        row = self.connection.execute(
            "SELECT * FROM metric_supersession WHERE predecessor_id = ?",
            (metric_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "predecessor_id": row["predecessor_id"],
            "successor_id": row["successor_id"],
            "decided_at": row["decided_at"],
            "reason": row["reason"],
            "evidence": row["evidence"],
        }

    def record_supersession(
        self,
        predecessor_id: str,
        successor_id: str,
        reason: str,
        evidence: Optional[str] = None,
        decided_at: Optional[str] = None,
    ) -> None:
        """
        Record a rename. Append-only, and it does not touch the predecessor.

        The predecessor's row, its mappings and every observation filed under it
        are left exactly as they are. What this adds is the decision, so that a
        reader asking what a historical `metric = 'debt'` observation denotes gets
        an answer rather than a stale name.
        """
        self.connection.execute(
            "INSERT OR IGNORE INTO metric_supersession"
            " (predecessor_id, successor_id, decided_at, reason, evidence,"
            "  recorded_at) VALUES (?, ?, ?, ?, ?, ?)",
            (predecessor_id, successor_id, decided_at or utc_now(), reason,
             evidence, utc_now()),
        )
        self.connection.commit()

    def mappings_for_metric(
        self,
        metric_id: str,
        as_of: Optional[str] = None,
    ) -> List[ConceptMapping]:
        """
        Every concept the named metric declares, following the supersession chain.

        **This is a metric-level query. It does not answer what applies to a
        single observation, and it must not be read as if it did.**

        A metric declares concepts; an observation carries one. Following the
        chain means a renamed metric reports its successor's declarations, which
        is what stops a legacy row from being stranded by a rename -- but it also
        means every legacy row looks as though it carried every one of the
        successor's concepts. Under `debt -> long_term_debt` that is four
        concepts, two of which had no established destination for the successor
        when 2.49 measured it.

        The concept set is unchanged by the follow, so this is invisible in
        coverage counts and has to be asked about directly. For one observation,
        use `mappings_for_observation`, which conditions on the observation's own
        concept and reports an explicit unresolved state instead of returning a
        set the observation does not carry.
        """
        target = self.resolve_metric(metric_id)
        rows = self.connection.execute(
            "SELECT * FROM metric_concept_mapping WHERE metric_id = ?"
            " ORDER BY mapping_type, effective_from, concept_id",
            (target,),
        ).fetchall()
        return [
            mapping
            for mapping in (self._mapping(row) for row in rows)
            if mapping is not None and mapping.applies_on(as_of)
        ]

    def mappings_for_observation(
        self,
        metric_id: str,
        source_concept: Optional[str] = None,
        as_of: Optional[str] = None,
    ) -> ObservationMapping:
        """
        Resolve one observation: stored metric + its own source concept.

        The supersession still resolves -- `debt` still means `long_term_debt`,
        and the stored metric is never rewritten -- but a mapping reaches this
        observation only when the successor declares it **for the concept this
        observation actually carries**. A concept with no such declaration gets
        an explicit unresolved result, never the successor's full mapping set.

        No source concept means insufficient context, and it is reported as
        such. Falling back to every mapping the successor declares would make a
        missing fact look like a resolved one, which is the specific failure 2.49
        measured: the blanket path was invisible precisely because it always
        produced an answer.

        The registry needs no new metadata for this. A mapping row already names
        its concept, and that name *is* the applicability key -- "declared for X"
        and "applies to an observation of X" are the same relation. What was
        missing was a resolution entry point that could ask the question, which
        is why this is a function rather than a schema change.
        """
        resolved_id = self.resolve_metric(metric_id)
        if resolved_id is None:
            return ObservationMapping(
                stored_metric_id=metric_id,
                resolved_metric_id=metric_id,
                source_concept=source_concept,
                status=ObservationMapping.UNRESOLVED_NO_APPLICABLE_MAPPING,
                reason=(
                    "the stored metric does not resolve, so there is no "
                    "successor to inherit a mapping from"
                ),
            )
        supersession = self.supersession_of(metric_id)
        resolution = self.resolve_source_concept(
            source_concept, as_of=as_of, asset_id=None)
        if resolution.status == ConceptResolution.AMBIGUOUS_MAPPING:
            return ObservationMapping(
                stored_metric_id=metric_id,
                resolved_metric_id=resolved_id,
                source_concept=source_concept,
                status=ObservationMapping.UNRESOLVED_NO_APPLICABLE_MAPPING,
                reason=(
                    "NOT_EXPLAINED. More than one metric claims this concept, "
                    f"so the registry does not choose: {list(resolution.candidates)}."
                ),
                supersession=supersession,
            )
        if not resolution.is_resolved:
            return ObservationMapping(
                stored_metric_id=metric_id,
                resolved_metric_id=resolved_id,
                source_concept=source_concept,
                status=(
                    ObservationMapping.UNRESOLVED_NO_SOURCE_CONCEPT
                    if resolution.status
                    == ConceptResolution.UNRESOLVED_NO_SOURCE_CONCEPT
                    else ObservationMapping.UNRESOLVED_NO_APPLICABLE_MAPPING),
                reason=resolution.detail,
                supersession=supersession,
            )
        return ObservationMapping(
            stored_metric_id=metric_id,
            resolved_metric_id=resolution.destination_metric or resolved_id,
            source_concept=source_concept,
            mappings=(ConceptMapping(
                metric_id=resolution.destination_metric or resolved_id,
                concept_id=source_concept or "",
                mapping_type=resolution.mapping_type or "EXACT",
                effective_from=resolution.effective_from,
                effective_to=resolution.effective_to,
                notes=resolution.notes,
            ),),
            status=ObservationMapping.RESOLVED,
            reason=(
                ""
                if resolution.destination_metric == metric_id
                else resolution.detail),
            supersession=supersession,
        )

    def metrics_for_concept(
        self,
        concept_id: str,
        as_of: Optional[str] = None,
    ) -> List[Tuple[ConceptMapping, Optional[Metric]]]:
        """
        Every metric a concept can express.

        More than one is a legitimate answer rather than a defect to resolve: a
        vendor's "total cash" may be an aggregate, and returning only the
        closest-looking metric would be the name-based guess this registry
        exists to avoid.
        """
        rows = self.connection.execute(
            "SELECT * FROM metric_concept_mapping WHERE concept_id = ?"
            " ORDER BY mapping_type, metric_id",
            (concept_id,),
        ).fetchall()
        results: List[Tuple[ConceptMapping, Optional[Metric]]] = []
        for row in rows:
            mapping = self._mapping(row)
            if mapping is None or not mapping.applies_on(as_of):
                continue
            results.append((mapping, self.metric(mapping.metric_id)))
        return results

    def _mapping(self, row: sqlite3.Row) -> Optional[ConceptMapping]:
        try:
            return ConceptMapping(
                metric_id=row["metric_id"],
                concept_id=row["concept_id"],
                mapping_type=row["mapping_type"],
                effective_from=row["effective_from"],
                effective_to=row["effective_to"],
                notes=row["notes"],
                relation_kind=(_optional_column(row, "relation_kind")
                               or MAPPING_IDENTITY),
                scope=_read_scope(row),
            )
        except RegistryError:
            return None

    def resolve_source_concept(
        self,
        concept_id: Optional[str],
        as_of: Optional[str] = None,
        asset_id: Optional[str] = None,
    ) -> ConceptResolution:
        """
        Where a source concept points, preferring a direct declaration.

        The order of consideration is fixed and is not a ranking:

            1. gather every mapping applicable to the concept at `as_of`
            2. partition into DIRECT (declared by a metric that is not
               superseded) and INHERITED (visible only through a chain)
            3. exactly one DIRECT wins outright
            4. more than one DIRECT stays AMBIGUOUS and nothing is guessed
            5. with no DIRECT, an INHERITED mapping qualifies only when it is
               EXACT; a PARTIAL proposition that was never promoted is a
               characterisation, not a destination

        Step 5 is what keeps the IFRS concepts unresolved. They have no direct
        mapping anywhere, and the only thing offering them a destination is a
        PARTIAL mapping inherited through `debt -> long_term_debt`, which 2.47
        and 2.51 explicitly did not authorise.
        """
        if not concept_id:
            return ConceptResolution(
                source_concept=concept_id,
                status=ConceptResolution.UNRESOLVED_NO_SOURCE_CONCEPT,
                detail=("NOT_APPLICABLE. Without a source concept there is "
                        "nothing to resolve; the stored metric stands."),
            )

        pairs = self.metrics_for_concept(concept_id, as_of=as_of)
        adoption = self.adoption_for(asset_id, concept_id) if asset_id else None
        if adoption is not None and as_of is not None:
            # Adoption widens the window a concept applies in; it never changes
            # the fidelity of how it applied.
            pairs = [
                (mapping, metric) for mapping, metric in pairs
                if mapping.applies_on(as_of) or adoption.covers(as_of)
            ]

        # Only IDENTITY rows are destination claims.
        #
        # A COMPOSITION row says the metric is built from the concept, which is
        # the same relation read from the other end and is never a statement about
        # which metric the concept expresses. Letting one compete is exactly what
        # 2.72 measured as AMBIGUOUS_MAPPING between `long_term_debt` and
        # `long_term_debt_noncurrent` for a single concept. The fix is neither to
        # weaken a row nor to date one out, but to stop treating a declaration as
        # a claim.
        identity_rows = [mapping for mapping, _metric in pairs
                         if mapping.relation_kind == MAPPING_IDENTITY]
        direct: List[ConceptMapping] = []
        inherited: List[ConceptMapping] = []
        for mapping in identity_rows:
            if self.resolve_metric(mapping.metric_id) == mapping.metric_id:
                direct.append(mapping)
            else:
                inherited.append(mapping)

        # Ordered by declared identity so the outcome cannot depend on row order.
        direct.sort(key=lambda m: (m.metric_id, m.concept_id))
        inherited.sort(key=lambda m: (m.metric_id, m.concept_id))

        # An identity claim is an EXACT mapping declared by a metric that is
        # itself active.
        #
        # "Declared by an active metric" is NOT sufficient on its own, and
        # measuring that is what corrected this: the successor `long_term_debt`
        # re-declares its PARTIAL components in its own name, so those rows are
        # structurally indistinguishable from a direct declaration while being
        # a statement that the concept is *part of* the total rather than what
        # the total is. Mapping type carries that distinction, and the registry
        # already uses it everywhere else.
        identity_claims = [
            mapping for mapping in direct if mapping.mapping_type == "EXACT"
        ]

        if len(identity_claims) == 1:
            mapping = identity_claims[0]
            return ConceptResolution(
                source_concept=concept_id,
                status=ConceptResolution.RESOLVED,
                destination_metric=mapping.metric_id,
                mapping_origin=ConceptResolution.DIRECT,
                mapping_type=mapping.mapping_type,
                effective_from=mapping.effective_from,
                effective_to=mapping.effective_to,
                notes=mapping.notes,
                detail=(f"declared directly by `{mapping.metric_id}`; an "
                        "inherited mapping and a PARTIAL component statement do "
                        "not compete with a metric that declares the concept "
                        "itself"),
            )
        if len(identity_claims) > 1:
            return ConceptResolution(
                source_concept=concept_id,
                status=ConceptResolution.AMBIGUOUS_MAPPING,
                candidates=tuple(m.metric_id for m in identity_claims),
                detail=("NOT_EXPLAINED. More than one metric claims this "
                        "concept exactly, so the registry does not choose."),
            )

        # A measured direct PARTIAL identity claim is an affirmative destination
        # of lesser strength than an exact one, and it is never upgraded.
        #
        # 2.72 established that PARTIAL may not stand in for missing evidence:
        # that would convert unknown into a known narrower scope. 2.70 defines
        # PARTIAL as a semantic outcome -- the accounting object matches and the
        # scope demonstrably differs -- and not as a state for "not yet
        # researched". So a PARTIAL earns a destination only once the narrower
        # scope has been MEASURED, and the measurement rides on the mapping as
        # structured scope so this check can be made here rather than taking the
        # word for it.
        #
        # Filtering before the count is deliberate: an unmeasured PARTIAL does
        # not compete at all, so it can neither win nor create an ambiguity.
        component_claims = [
            mapping for mapping in direct
            if mapping.mapping_type == "PARTIAL"
            and _scope_is_measured(mapping.scope)
        ]
        if not identity_claims and len(component_claims) == 1:
            mapping = component_claims[0]
            return ConceptResolution(
                source_concept=concept_id,
                status=ConceptResolution.RESOLVED,
                destination_metric=mapping.metric_id,
                mapping_origin=ConceptResolution.DIRECT,
                mapping_type=mapping.mapping_type,
                effective_from=mapping.effective_from,
                effective_to=mapping.effective_to,
                notes=mapping.notes,
                scope=mapping.scope,
                detail=(
                    f"declared directly by `{mapping.metric_id}` as a "
                    "component of that metric rather than as its whole. The scope "
                    "was measured and is recorded on the mapping, so a consumer "
                    "can see that this concept contributes without expressing "
                    "all of it."),
            )

        if not identity_claims and len(component_claims) > 1:
            return ConceptResolution(
                source_concept=concept_id,
                status=ConceptResolution.AMBIGUOUS_MAPPING,
                candidates=tuple(m.metric_id for m in component_claims),
                detail=("NOT_EXPLAINED. More than one metric claims this "
                        "concept as a component, so the registry does not "
                        "choose."),
            )

        # No direct identity claim. An inherited mapping authorises only when it
        # is EXACT; a PARTIAL proposition that was never promoted is a
        # characterisation, not a decision.
        authorised = [m for m in inherited if m.mapping_type == "EXACT"]
        if len(authorised) == 1:
            mapping = authorised[0]
            successor = self.resolve_metric(mapping.metric_id)
            return ConceptResolution(
                source_concept=concept_id,
                status=ConceptResolution.RESOLVED,
                destination_metric=successor,
                mapping_origin=ConceptResolution.INHERITED,
                mapping_type=mapping.mapping_type,
                effective_from=mapping.effective_from,
                effective_to=mapping.effective_to,
                notes=mapping.notes,
                detail=(f"no direct claim; an EXACT mapping declared by "
                        f"`{mapping.metric_id}` was inherited through "
                        f"`{mapping.metric_id}` -> `{successor}`"),
            )
        if len(authorised) > 1:
            return ConceptResolution(
                source_concept=concept_id,
                status=ConceptResolution.AMBIGUOUS_MAPPING,
                candidates=tuple(self.resolve_metric(m.metric_id)
                                 for m in authorised),
                detail=("NOT_EXPLAINED. More than one authorised inherited "
                        "mapping claims this concept."),
            )
        return ConceptResolution(
            source_concept=concept_id,
            status=ConceptResolution.UNRESOLVED_NO_APPLICABLE_MAPPING,
            detail=(
                "NOT_APPLICABLE. No metric claims this concept exactly."
                + (f" The only mappings offered are "
                   f"{[(m.metric_id, m.mapping_type) for m in direct + inherited]}, "
                   "which record component relationships or unauthorised "
                   "propositions rather than an identity."
                   if (direct or inherited) else
                   " No metric declares it at all.")
                + " This is unresolved, not refuted: a destination may still be "
                  "decided."),
        )

    def effective_metric_sources(self, metric_id: str) -> List[Dict[str, Any]]:
        """
        Source concepts that resolve uniquely to `metric_id`, with their windows.

        This is the retrieval half of the same rule: a metric query needs to know
        which legacy concepts belong to the requested metric and over which
        dates, and that must come from one place rather than a second algorithm
        restated per reader.

        Only DIRECT resolutions are listed, because only those are decided by a
        declaration on an active metric. Adoption-widened applicability is not
        represented here, so a concept that applies to one filer only under
        adoption will not be reached by this predicate; that is a known
        narrowing rather than a claim of completeness.
        """
        rows = self.connection.execute(
            "SELECT DISTINCT concept_id, mapping_type, effective_from,"
            " effective_to FROM metric_concept_mapping"
            " WHERE metric_id = ? ORDER BY concept_id", (metric_id,)
        ).fetchall()
        out: List[Dict[str, Any]] = []
        for row in rows:
            if self.resolve_metric(metric_id) != metric_id:
                # Only an active metric declares destinations of its own.
                continue
            resolution = self.resolve_source_concept(row["concept_id"])
            if (resolution.is_resolved
                    and resolution.destination_metric == metric_id
                    and resolution.mapping_origin == ConceptResolution.DIRECT):
                out.append({
                    "concept": row["concept_id"],
                    "mapping_type": row["mapping_type"],
                    "effective_from": row["effective_from"],
                    "effective_to": row["effective_to"],
                })
        return out

    def superseded_metric_ids(self) -> List[str]:
        """Metric ids that have been replaced, so their rows are legacy."""
        if not self._has_table("metric_supersession"):
            return []
        return [row["predecessor_id"] for row in self.connection.execute(
            "SELECT predecessor_id FROM metric_supersession ORDER BY"
            " predecessor_id")]

    def resolve(
        self,
        concept_id: str,
        as_of: Optional[str] = None,
        asset_id: Optional[str] = None,
    ) -> ResolvedEvidence:
        """
        Resolve a concept to the metric it means.

        An unmapped concept resolves to nothing. It is not attached to the
        metric whose name looks nearest, because that is precisely the inference
        this registry exists to make explicit and to refuse to make silently.

        `asset_id` separates the two questions that were previously one. The
        mapping window answers *what the concept means*; a filer's observed
        adoption answers *when this filer used it*. When both are available the
        adoption window widens the mapping rather than replacing it, so a filer
        that used a concept outside the seeded window is no longer reported as
        unmapped — which was a fact about the seed, not about the filer.
        """
        mappings = [
            mapping
            for mapping, _ in self.metrics_for_concept(concept_id, as_of=None)
        ]
        adoption = (
            self.adoption_for(asset_id, concept_id) if asset_id else None
        )

        # Adoption governs when it covers the period, and the mapping governs
        # everything else. It replaces the window rather than deferring to it,
        # because the window was seeded from one filer's filings and is that
        # filer's timeline: NVDA reported `Revenues` through 2026, long after
        # the 2018 close that AAPL's last period produced. A real filing from
        # the filer being asked about is better evidence than another filer's
        # inferred boundary. The mapping's *fidelity* is untouched — a PARTIAL
        # concept is still PARTIAL and still breaks the series — so adoption
        # widens when a concept applied and never how faithfully it applied.
        effective = [
            mapping
            for mapping in mappings
            if mapping.applies_on(as_of)
            or (adoption is not None and adoption.covers(as_of))
        ]
        candidates = [
            (mapping, self.metric(mapping.metric_id)) for mapping in effective
        ]
        if not candidates:
            return ResolvedEvidence(
                observation_id="",
                concept_id=concept_id if self.concept(concept_id) else None,
                metric=None,
                adoption=adoption,
            )

        # A concept that maps to more than one metric is a registry question,
        # not something to settle here. It is reported as unresolved with every
        # candidate attached, so the ambiguity is visible instead of resolved.
        if len(candidates) > 1:
            return ResolvedEvidence(
                observation_id="",
                concept_id=concept_id,
                metric=None,
                mappings=tuple(mapping for mapping, _ in candidates),
                series_breaks=(
                    {
                        "kind": "AMBIGUOUS_MAPPING",
                        "metric_ids": [
                            mapping.metric_id for mapping, _ in candidates
                        ],
                        "explanation": (
                            "NOT_EXPLAINED. One concept maps to several "
                            "metrics, so the registry does not choose. This "
                            "is a registry question for a filer to answer, not "
                            "one to settle by name."
                        ),
                    },
                ),
            )

        mapping, metric = candidates[0]
        return ResolvedEvidence(
            observation_id="",
            concept_id=concept_id,
            metric=metric,
            mappings=(mapping,),
            adoption=adoption,
            adopted_outside_mapping_window=bool(
                adoption is not None
                and not mapping.applies_on(as_of)
                and as_of
            ),
        )

    def series_breaks(
        self,
        metric_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Where a metric's series must break.

        A PARTIAL or NON_COMPARABLE mapping is a change in what was measured,
        so joining the periods on either side of it would splice two different
        numbers into one line. This is the 2.4.3 rule applied to a change of
        concept rather than a change of period length.
        """
        breaks: List[Dict[str, Any]] = []
        for mapping in self.mappings_for_metric(metric_id):
            if mapping.series_continues:
                continue
            breaks.append(
                {
                    "kind": "CONCEPT_MAPPING_BREAK",
                    "metric_id": metric_id,
                    "concept_id": mapping.concept_id,
                    "mapping_type": mapping.mapping_type,
                    "effective_from": mapping.effective_from,
                    "effective_to": mapping.effective_to,
                    "explanation": "NOT_EXPLAINED_BY_ST_EVA",
                }
            )
        return breaks
