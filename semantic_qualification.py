"""
Registry-backed semantic qualification of a source element for a metric.

The historical valuation datasets reconstruct trailing revenue and trailing
EBITDA out of filed SEC facts. A reconstruction can be arithmetically perfect,
point-in-time correct, contiguous and long enough, and still be built on an
element the registry does not accept as this metric for this filer. Decision
2.99 retired `us-gaap:Revenues` as a source of `revenue` because it is
broader than the target metric. Nothing in the reconstruction pipeline would
have noticed: the retired element's filed values are complete, knowable and
contiguous, so they would have produced a perfectly computable price-to-sales
distribution and, with enough of them, a production reference.

This module is the gate that notices. It asks the registry -- the same
registry, the same rows and the same resolver the rest of the engine uses --
one question: is this element this metric for this filer?

  S-1: A concept qualifies for a metric only when the registry resolves it to
       that metric: an EXACT, IDENTITY mapping, in force at the date asked
       about, whose scope covers the filer. A concept the registry maps only
       PARTIALLY, maps to another metric, scopes to another filer, or does
       not map at all does not qualify, whatever values it carries.
  S-2: The registry's own decision state is read, never re-decided. A concept
       the registry recorded as declined for the metric, or that it retired by
       removing its mapping, is not qualified, and the reason says which of
       those it is.
  S-3: Keeping the filed element as traceable evidence is not the same as
       admitting it to a figure. A rejected element may still be held as
       evidence; it contributes to no revenue, no EBITDA and no multiple.
  S-4: The qualification is a condition of its own, separate from every
       technical one -- sample size, point-in-time knowability, window
       contiguity, bridge completeness. It is reported in its own right, so a
       distribution that is long and correct but semantically unqualified says
       so, and never passes for a thin one or a mistimed one.

The gate reads the registry through `CoreRegistry.resolve_source_concept`, the
resolver the evidence-admission boundary uses, so the repository holds one
answer to "is this concept this metric" rather than two that may disagree. The
registry is materialised in memory from `registry_seed`, the seed being the
authoritative statement of the registry's decisions, and it is built once per
process.
"""
from __future__ import annotations

import threading
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional, Tuple

from core_registry import (
    MAPPING_EXACT,
    MAPPING_IDENTITY,
    ConceptResolution,
    CoreRegistry,
    concept_id_for,
)
from registry_seed import seed

# The decision the gate reaches.
DECISION_QUALIFIED = "QUALIFIED"
DECISION_NOT_QUALIFIED = "NOT_QUALIFIED"
# The registry declares no such metric, so it has no standing to rule on the
# element. It is not a decision against the element: the role is governed by
# the calculation specification that names it.
DECISION_NOT_APPLICABLE = "NOT_APPLICABLE"

# The closed set of reasons a qualification can carry. A qualified element and
# an unqualified one are told apart by the reason, not by the absence of one.
REASON_QUALIFIED = "QUALIFIED_EXACT_IDENTITY_MAPPING"
REASON_NO_MAPPING = "NO_MAPPING_FOR_METRIC"
REASON_MAPPING_TYPE = "MAPPING_TYPE_NOT_ACCEPTED"
REASON_RELATION = "RELATION_NOT_IDENTITY"
REASON_SCOPE = "SCOPE_NOT_APPLICABLE"
REASON_OTHER_METRIC = "RESOLVES_TO_ANOTHER_METRIC"
REASON_AMBIGUOUS = "AMBIGUOUS_REGISTRY_CLAIM"
REASON_DECLINED = "DECLINED_FOR_METRIC"
REASON_NOT_IN_FORCE = "MAPPING_NOT_IN_FORCE"
REASON_NO_SUCH_METRIC = "NO_SUCH_REGISTRY_METRIC"
REASON_NO_ELEMENT = "NO_ELEMENT_FOR_ROLE"

CLOSED_REASON_CODES = frozenset(
    {
        REASON_QUALIFIED,
        REASON_NO_MAPPING,
        REASON_MAPPING_TYPE,
        REASON_RELATION,
        REASON_SCOPE,
        REASON_OTHER_METRIC,
        REASON_AMBIGUOUS,
        REASON_DECLINED,
        REASON_NOT_IN_FORCE,
        REASON_NO_SUCH_METRIC,
        REASON_NO_ELEMENT,
    }
)

# The policy the gate applies, stated once and carried by every qualification
# record, so a reader of a dataset can see the rule its elements were read
# under without reading this module.
QUALIFICATION_POLICY = (
    "A source element is qualified for a metric only when the core registry "
    "resolves it to that metric for that filer: an EXACT IDENTITY mapping, in "
    "force at the date read, whose scope covers the filer. An element the "
    "registry declines, retires, maps only partially, maps to another metric "
    "or scopes to another filer is not qualified, and its filed values "
    "produce no figure and no production reference. Holding a filed element as "
    "traceable evidence is not the same as admitting it to a valuation."
)

# The mapping types and relations the gate accepts. They are the registry's own
# continuing-claim vocabulary, read rather than redefined: a COMPOSITION row
# says the metric is built from the concept, which is not a statement that the
# concept expresses the metric.
ACCEPTED_MAPPING_TYPES = (MAPPING_EXACT,)
ACCEPTED_RELATION_KINDS = (MAPPING_IDENTITY,)

_REGISTRY_LOCAL = threading.local()


def registry() -> CoreRegistry:
    """
    The registry, materialised in memory from the seed.

    The seed is the authoritative statement of the registry's decisions, and
    the resolver needs the rows and the schema the archive's migrations
    define. The store is in memory: this gate reads the registry, it never
    writes an archive and never touches the operator's own database.

    The registry is built once per thread, because a SQLite connection
    belongs to the thread that opened it and this gate is called from worker
    threads as well as from the main one. Each thread pays for the build
    once and then reads the same rows.
    """
    built = getattr(_REGISTRY_LOCAL, "registry", None)
    if built is None:
        from sqlite_archive import SQLiteArchive

        store = SQLiteArchive(":memory:")
        registry_built = CoreRegistry(store.connection)
        seed(registry_built)
        store.connection.commit()
        _REGISTRY_LOCAL.store = store
        _REGISTRY_LOCAL.registry = registry_built
        built = registry_built
    return built


@dataclass(frozen=True)
class SemanticQualification:
    """
    One element's standing as a source of one metric for one filer.

    The record carries the decision, the reason and the registry's own terms
    of the decision, so a dataset can state why it used an element without a
    reader having to re-derive it.
    """

    metric_id: str
    concept_id: str
    taxonomy: str
    element: str
    ticker: str
    qualified: bool
    reason_code: str
    reason_detail: str
    mapping_type: Optional[str] = None
    relation_kind: Optional[str] = None
    scope: Optional[Dict[str, Any]] = None
    effective_from: Optional[str] = None
    effective_to: Optional[str] = None
    resolved_metric_id: Optional[str] = None
    registry_metric_exists: bool = True

    def __post_init__(self) -> None:
        if self.reason_code not in CLOSED_REASON_CODES:
            raise ValueError(
                f"reason_code {self.reason_code!r} is not in the closed set"
            )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _scope_applies(scope: Optional[Dict[str, Any]], ticker: str) -> bool:
    """
    Whether a mapping's scope covers this filer.

    The registry's own rule, mirrored: no scope means universal, a scope that
    names a ticker covers that filer and no other, and a scope that only
    records how a metric was measured -- variation, measured holders -- says
    nothing about where the claim applies. An accession-scoped mapping names a
    filing rather than a filer, and this gate reads a filer, so it does not
    apply here.
    """
    if not scope:
        return True
    if "ticker" in scope and scope["ticker"] != ticker:
        return False
    if "accession" in scope:
        return False
    return True


def _scope_restricts(scope: Optional[Dict[str, Any]]) -> bool:
    """
    Whether a scope restricts where a mapping applies.

    A scope that names a ticker or a filing restricts the mapping to it. A
    scope that only records a measurement does not, and treating it as a
    restriction would let a measured weaker claim suppress a global exact one.
    """
    if not scope:
        return False
    return "ticker" in scope or "accession" in scope


def registry_has_metric(metric_id: str) -> bool:
    """
    Whether the registry declares this metric at all.

    A metric the registry does not declare cannot be qualified by the
    registry, and saying so is different from saying the element failed. A
    source role the registry does not model is governed by the calculation
    specification that names it, and the dataset says which of the two it is.
    """
    return registry().metric(metric_id) is not None


def _decline_for(
    reg: CoreRegistry, concept_id: str, metric_id: str
) -> Optional[Dict[str, Any]]:
    """The registry's own decline record for this concept and metric, if any."""
    for decline in reg.declines_for_metric(metric_id):
        if decline.get("concept_id") == concept_id:
            return decline
    return None


def _accepted_mapping(
    reg: CoreRegistry,
    concept_id: str,
    metric_id: str,
    ticker: str,
    as_of: Optional[str],
) -> Optional[Any]:
    """
    The mapping that qualifies this concept for this metric, if there is one.

    The search mirrors the registry's resolver: the scope filter first, then
    the restricted-scope preference, then the relation kind, then the mapping
    type. It is the same order the resolver uses, so the two cannot disagree
    about which mapping carries the claim.
    """
    pairs = reg.metrics_for_concept(concept_id, as_of=as_of)
    pairs = [
        (mapping, metric)
        for mapping, metric in pairs
        if _scope_applies(mapping.scope, ticker)
    ]
    restricted = [
        (mapping, metric)
        for mapping, metric in pairs
        if _scope_restricts(mapping.scope)
    ]
    if restricted:
        pairs = restricted
    for mapping, _metric in pairs:
        if mapping.metric_id != metric_id:
            continue
        if mapping.relation_kind != MAPPING_IDENTITY:
            continue
        if mapping.mapping_type != MAPPING_EXACT:
            continue
        return mapping
    return None


def qualify_element(
    *,
    metric_id: str,
    taxonomy: str,
    element: str,
    ticker: str,
    as_of: Optional[str] = None,
) -> SemanticQualification:
    """
    Whether this element is this metric for this filer, and why.

    `as_of` asks the question at a date: a mapping that was not in force then
    does not qualify then, and the reason says so rather than reporting the
    element as never mapped. With no date, the question is whether the
    registry recognises the element at all.

    The registry's resolver decides the outcome; this function names the
    reason the resolver's own rows imply.
    """
    reg = registry()
    concept_id = concept_id_for(taxonomy, element)

    if not registry_has_metric(metric_id):
        return SemanticQualification(
            metric_id=metric_id,
            concept_id=concept_id,
            taxonomy=taxonomy,
            element=element,
            ticker=ticker,
            qualified=False,
            reason_code=REASON_NO_SUCH_METRIC,
            reason_detail=(
                f"The core registry declares no metric {metric_id!r}, so it "
                f"cannot recognise {concept_id} as a source of it. The role "
                "is governed by the calculation specification that names it."
            ),
            registry_metric_exists=False,
        )

    resolution = reg.resolve_source_concept(
        concept_id, as_of=as_of, asset_id=ticker
    )
    accepted = _accepted_mapping(
        reg, concept_id, metric_id, ticker, as_of=as_of
    )

    if (
        resolution.status == ConceptResolution.RESOLVED
        and resolution.destination_metric == metric_id
        and resolution.mapping_type == MAPPING_EXACT
        and accepted is not None
    ):
        scope = dict(accepted.scope) if accepted.scope else None
        detail = (
            f"The core registry maps {concept_id} to {metric_id!r} for "
            f"{ticker} as an EXACT IDENTITY mapping"
            + (
                f", scoped to {ticker}"
                if scope and scope.get("ticker")
                else ", without a filer restriction"
            )
            + (
                f", in force from {accepted.effective_from}"
                if accepted.effective_from
                else ""
            )
            + (
                f" until {accepted.effective_to}"
                if accepted.effective_to
                else ""
            )
            + ". The element is this metric for this filer, and its filed "
            "values may produce a figure."
        )
        return SemanticQualification(
            metric_id=metric_id,
            concept_id=concept_id,
            taxonomy=taxonomy,
            element=element,
            ticker=ticker,
            qualified=True,
            reason_code=REASON_QUALIFIED,
            reason_detail=detail,
            mapping_type=accepted.mapping_type,
            relation_kind=accepted.relation_kind,
            scope=scope,
            effective_from=accepted.effective_from,
            effective_to=accepted.effective_to,
            resolved_metric_id=metric_id,
        )

    reason_code, reason_detail, mapping = _rejection(
        reg=reg,
        metric_id=metric_id,
        concept_id=concept_id,
        element=element,
        taxonomy=taxonomy,
        ticker=ticker,
        as_of=as_of,
        resolution=resolution,
    )
    return SemanticQualification(
        metric_id=metric_id,
        concept_id=concept_id,
        taxonomy=taxonomy,
        element=element,
        ticker=ticker,
        qualified=False,
        reason_code=reason_code,
        reason_detail=reason_detail,
        mapping_type=mapping.mapping_type if mapping is not None else None,
        relation_kind=mapping.relation_kind if mapping is not None else None,
        scope=dict(mapping.scope) if mapping is not None and mapping.scope else None,
        effective_from=mapping.effective_from if mapping is not None else None,
        effective_to=mapping.effective_to if mapping is not None else None,
        resolved_metric_id=(
            resolution.destination_metric
            if resolution.status == ConceptResolution.RESOLVED
            else None
        ),
    )


def _rejection(
    *,
    reg: CoreRegistry,
    metric_id: str,
    concept_id: str,
    element: str,
    taxonomy: str,
    ticker: str,
    as_of: Optional[str],
    resolution: Any,
) -> Tuple[str, str, Optional[Any]]:
    """
    Why the element does not qualify, named from the registry's own rows.

    The order is the order of the ways the registry can withhold the claim:
    the element was considered and declined; it carries no mapping at all;
    the mappings it carries are restricted to another filer; the mappings it
    carries are of a type the registry does not accept as an identity claim;
    the mapping it carries was not in force at the date asked about; the
    element resolves to another metric; or the registry holds more than one
    claim and chooses none.
    """
    decline = _decline_for(reg, concept_id, metric_id)
    all_pairs = reg.metrics_for_concept(concept_id, as_of=None)
    scope_pairs = [
        (mapping, metric)
        for mapping, metric in all_pairs
        if _scope_applies(mapping.scope, ticker)
    ]
    for_mapping = [
        (mapping, metric)
        for mapping, metric in scope_pairs
        if mapping.metric_id == metric_id
    ]

    if decline is not None:
        return (
            REASON_DECLINED,
            f"The core registry declined {concept_id} for {metric_id!r} "
            f"({decline.get('reason_code')}): "
            f"{decline.get('reason')}. A declined element is not this "
            "metric's input, whatever values it carries.",
            for_mapping[0][0] if for_mapping else None,
        )

    if not all_pairs:
        return (
            REASON_NO_MAPPING,
            f"The core registry holds no mapping for {concept_id} at all, so "
            f"it does not recognise the element as {metric_id!r} for any "
            "filer. The element may still be filed and traceable; it is not "
            "this metric's source, and its values produce no figure.",
            None,
        )

    if not scope_pairs:
        other = sorted(
            {
                str((mapping.scope or {}).get("ticker"))
                for mapping, _metric in all_pairs
            }
        )
        return (
            REASON_SCOPE,
            f"The core registry maps {concept_id} only with a scope that "
            f"names another filer ({', '.join(other)}), so the element is "
            f"not {metric_id!r} for {ticker}. An element the registry "
            "recognises for another filer is not this filer's metric.",
            None,
        )

    if not for_mapping:
        others = sorted({mapping.metric_id for mapping, _metric in scope_pairs})
        return (
            REASON_OTHER_METRIC,
            f"The core registry maps {concept_id} to "
            f"{', '.join(others)} and not to {metric_id!r}, so the element "
            f"is not this metric for {ticker}.",
            None,
        )

    mapping = for_mapping[0][0]
    if mapping.relation_kind != MAPPING_IDENTITY:
        return (
            REASON_RELATION,
            f"The core registry records {concept_id} for {metric_id!r} as a "
            f"{mapping.relation_kind} relation, which says the metric is "
            "built from the element rather than that the element expresses "
            "the metric. A composition claim is not an identity claim.",
            mapping,
        )
    if mapping.mapping_type != MAPPING_EXACT:
        return (
            REASON_MAPPING_TYPE,
            f"The core registry maps {concept_id} to {metric_id!r} as "
            f"{mapping.mapping_type}, which is a characterisation of how the "
            "element relates to the metric rather than a claim that the "
            "element is the metric. Only an EXACT mapping is this metric's "
            "input.",
            mapping,
        )
    if not mapping.applies_on(as_of):
        return (
            REASON_NOT_IN_FORCE,
            f"The core registry's EXACT mapping for {concept_id} and "
            f"{metric_id!r} was in force from {mapping.effective_from} until "
            f"{mapping.effective_to}, and it was not in force on the date "
            "read. The element is not this metric's source on that date.",
            mapping,
        )
    if resolution.status == ConceptResolution.AMBIGUOUS_MAPPING:
        return (
            REASON_AMBIGUOUS,
            f"The core registry holds more than one exact claim for "
            f"{concept_id} and chooses none, so the element cannot be "
            f"resolved to {metric_id!r} for {ticker}.",
            mapping,
        )
    return (
        REASON_OTHER_METRIC,
        f"The core registry does not resolve {concept_id} to {metric_id!r} "
        f"for {ticker}, so the element is not this metric's source.",
        mapping,
    )


def qualify_roles(
    roles: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """
    The qualification record of a set of source roles.

    `roles` maps a role name to that role's own qualification record. The
    record names the policy, the accepted vocabulary and each role's
    decision, so a dataset can state the elements it read, the metrics they
    were read for and the registry's basis for accepting them.
    """
    return {
        "policy": QUALIFICATION_POLICY,
        "accepted_mapping_types": list(ACCEPTED_MAPPING_TYPES),
        "accepted_relation_kinds": list(ACCEPTED_RELATION_KINDS),
        "roles": {name: dict(record) for name, record in roles.items()},
    }


def no_element_for_role(
    *,
    metric_id: str,
    taxonomy: str,
    ticker: str,
    detail: str = "",
) -> SemanticQualification:
    """
    A role no element fills.

    The role is empty, which is a different condition from a role whose
    element the registry declined or scoped away: there is nothing to judge,
    so the record says the role has no element and the metric has no source
    for this filer.
    """
    return SemanticQualification(
        metric_id=metric_id,
        concept_id="",
        taxonomy=taxonomy,
        element="",
        ticker=ticker,
        qualified=False,
        reason_code=REASON_NO_ELEMENT,
        reason_detail=detail
        or (
            f"No element fills the role for {metric_id!r} at {ticker}. The "
            "role is empty, so the metric has no source for this filer and "
            "no figure is constructed from it."
        ),
    )


def manifest_section(
    roles: Dict[str, Dict[str, Any]],
    *,
    subject: str,
) -> Dict[str, Any]:
    """
    A manifest's statement of the elements, their roles and the basis.

    A manifest says what a dataset holds and where it came from. This part
    says which elements the dataset read, the metric each was read for, and
    the registry's decision on it -- so the recognition basis travels with
    the data rather than living only in the code that produced it.
    """
    return {
        "policy": QUALIFICATION_POLICY,
        "read_by": "the core registry, as seeded from registry_seed",
        "subject": subject,
        "roles": {
            name: {
                "metric_id": record.get("metric_id"),
                "element": record.get("element"),
                "concept_id": record.get("concept_id"),
                "registry_decision": (
                    DECISION_QUALIFIED
                    if record.get("qualified")
                    else (
                        DECISION_NOT_APPLICABLE
                        if record.get("registry_metric_exists") is False
                        else DECISION_NOT_QUALIFIED
                    )
                ),
                "reason_code": record.get("reason_code"),
                "basis": record.get("reason_detail"),
            }
            for name, record in roles.items()
        },
    }
