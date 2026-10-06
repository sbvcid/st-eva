"""
The 3.18 V1 crossing from archived SEC evidence into reverse valuation.

The whole of this module is one admitted fact moving one step. It reads a
point-in-time eligible observation set out of an `SQLiteArchive`, decides whether
a single metric may become a `ValuationInputs` field, and records why. It adds
nothing to the engine, changes nothing in the contract, and writes nothing to the
archive.

    SQLiteArchive.observations_for(asset, as_of)
        -> replay-eligible contract Observations
    -> V1 admission
        -> ValuationInputs.current_revenue
    -> MarketImpliedAssumptionsEngine.analyze

Two measured facts shape every decision below, both from the MU pilot archive.

**`revenue` is the only metric the two vocabularies share.** The evidence
registry holds twenty ACTIVE filing metrics; `ValuationInputs` holds thirteen
engine metrics; the intersection is `revenue`. V1 admits `revenue` and refuses
the other twelve by name, rather than discovering later that each had a semantic
problem of its own.

**`current_revenue` may not be synthesised.** `METRIC_DEFINITIONS` declares
`revenue` to be *"Observed trailing revenue. Never synthesized."*
(`data_contract.py:552`). `sec_provider` already implements three TTM
constructions -- `SUM_OF_DISCRETE_QUARTERS`, `ANNUAL_FACT_AS_TRAILING_WINDOW`
and a roll-forward -- and every one of them produces a figure this boundary is
forbidden to write. They are licensed for the 2.3-B comparison layer, whose output
is a `CrossValidationResult`, not a `ValuationInputs` field. V1 therefore admits
an *observed filed period* and refuses a cumulative one, which is the whole
difference between a filing and a trailing figure.

What V1 deliberately does not do:

- it does not make the valuation run replayable. `replay_fidelity` stays
  `FIDELITY_OBSERVATIONAL` while any input is `ARCHIVE_FIRST_SEEN`
  (`archive.py:433-437`), and the vendor's twelve fundamentals declare no
  publication time at all.
- it does not produce a cross-source verdict. `cross_validate_all` admits only
  `cmp-` prefixed observations (`cross_validation.py:1119`, an ID-prefix test at
  `data_contract.py:672-680`), and an archived row is `obsarch_<hash>`. An
  archived SEC fact can never enter the cross-validation layer.
- it does not produce a SEC-derived implied figure. `revenue_at_reference_multiple`
  is `market_cap / selected_ps` (`st_eva_runner.py:1330`) and reads no revenue at
  all; `forward_eps_at_reference_multiple` is `price / selected_pe` and needs a
  price the archive does not hold. Injecting SEC revenue adds a conventional
  P/S and nothing else.

Every refusal here leaves the engine field at its existing `UNAVAILABLE` default.
There is no fallback to another metric, no nearest-period search, and no
substitution of a related figure, because a refused input and a wrong input differ
only in whether the reader can tell.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from archive import (
    ARCHIVE_FIRST_SEEN,
    SOURCE_DECLARED,
    ArchiveStore,
    availability_class_for,
)
from core_registry import CoreRegistry
from data_contract import (
    METRIC_PRICE,
    METRIC_REVENUE,
    QUARTER_MAX_DAYS,
    QUARTER_MIN_DAYS,
    YEAR_MAX_DAYS,
    YEAR_MIN_DAYS,
    UNAVAILABLE,
    Observation,
    ObservationSet,
    ValuationInputs,
    currencies_match,
    is_number,
    parse_iso_date,
)
from evidence_query import (
    AMBIGUITY_CROSS_PROVIDER,
    AMBIGUITY_DIMENSION,
    AMBIGUITY_MULTIPLE_CONCEPTS,
    classify_ambiguity,
)

# ---------------------------------------------------------------------------
# V1 scope
# ---------------------------------------------------------------------------

# The one constant that names what may cross. It is the *intersection* of the
# contract's `MATERIAL_METRICS` and the registry's ACTIVE metrics, not a
# hand-written list, and it is a single reference to `data_contract` rather than
# a copy of a string -- so a rename cannot leave a second spelling behind.
#
# It is deliberately one metric. Widening it is not a matter of adding a name
# here: each addition needs its own period, currency and synthesis answer, and
# `free_cash_flow` and `ebitda` have no registry entry at all.
V1_CROSSING_METRICS: Tuple[str, ...] = (METRIC_REVENUE,)

# The registry must agree on all three of these before a metric is a candidate.
# This is the rule that the scope is derived from the registry rather than
# hard-coded: a metric the registry has not heard of, or one it has deprecated,
# or one it holds as a different unit family, is not a valuation input whatever a
# caller's list says.
V1_REQUIRED_UNIT_FAMILY = "currency"
V1_REQUIRED_PERIOD_TYPE = "DURATION"
V1_REQUIRED_REGISTRY_STATUS = "ACTIVE"

# ---------------------------------------------------------------------------
# Refusal labels
# ---------------------------------------------------------------------------

# These are *admission findings*, not validation statuses and not evidence
# reasons. They deliberately live in this module rather than in
# `data_contract.ValidationStatus`, in `evidence_model.REASON_CODES`, or in the
# registry, because a refusal to supply a valuation input is a statement about
# this crossing and about nothing else. A reader must be able to see that a
# refusal came from here and not from a source or a comparison.
METRIC_NOT_IN_V1_SCOPE = "METRIC_NOT_IN_V1_SCOPE"
UNAVAILABLE = "UNAVAILABLE"
UNIT_NOT_MONETARY = "UNIT_NOT_MONETARY"
CURRENCY_MISMATCH = "CURRENCY_MISMATCH"
CURRENCY_UNDECLARED = "CURRENCY_UNDECLARED"
MAPPING_NOT_EXACT = "MAPPING_NOT_EXACT"
CONCEPT_AMBIGUOUS = "CONCEPT_AMBIGUOUS"
PERIOD_NOT_DISCRETE = "PERIOD_NOT_DISCRETE"
AVAILABILITY_UNDECLARED = "AVAILABILITY_UNDECLARED"
NOT_KNOWABLE_AT_AS_OF = "NOT_KNOWABLE_AT_AS_OF"
AMBIGUITY_RAISED = "AMBIGUITY_RAISED"

REFUSAL_LABELS: Tuple[str, ...] = (
    METRIC_NOT_IN_V1_SCOPE,
    UNAVAILABLE,
    UNIT_NOT_MONETARY,
    CURRENCY_MISMATCH,
    CURRENCY_UNDECLARED,
    MAPPING_NOT_EXACT,
    CONCEPT_AMBIGUOUS,
    PERIOD_NOT_DISCRETE,
    AVAILABILITY_UNDECLARED,
    NOT_KNOWABLE_AT_AS_OF,
    AMBIGUITY_RAISED,
)

REFUSALS: Dict[str, str] = {
    METRIC_NOT_IN_V1_SCOPE: (
        "the metric is not one V1 admits; the crossing is declared for "
        f"{', '.join(V1_CROSSING_METRICS)} only, and every other engine input "
        "is a market or estimate quantity that no filing can supply"
    ),
    UNAVAILABLE: (
        "no observation of this metric is replay-eligible at this instant, so "
        "there is no filed figure to consider"
    ),
    UNIT_NOT_MONETARY: (
        "the unit is not a currency, so the value is not combinable with a "
        "price or a market capitalisation under the engine's arithmetic"
    ),
    CURRENCY_MISMATCH: (
        "the observation's currency differs from the valuation-side price's, "
        "and ST-EVA holds no rate at which to convert between them"
    ),
    CURRENCY_UNDECLARED: (
        "the observation declares no currency, so it cannot be shown to be the "
        "same currency as the price; an unstated currency is a refusal here, not "
        "an assumed match"
    ),
    MAPPING_NOT_EXACT: (
        "the registry does not map the observation's own source concept to this "
        "metric exactly, or not at this period; a PARTIAL mapping is a narrower "
        "claim and V1 does not consume its measured scope"
    ),
    CONCEPT_AMBIGUOUS: (
        "more than one source concept reported this metric for this period, so "
        "the evidence does not establish which of them a question about the "
        "metric was asking for; this is not a choice ST-EVA makes"
    ),
    PERIOD_NOT_DISCRETE: (
        "the period is not a discrete quarter or a fiscal year, so it is a "
        "cumulative stub or an instant rather than the trailing figure the "
        "field declares; aggregating it into a trailing figure is a synthesis "
        "the metric definition forbids"
    ),
    AVAILABILITY_UNDECLARED: (
        "the source declared no publication time, so the fact cannot be "
        "asserted to have been knowable at any instant; archive-first-seen is a "
        "weaker kind of knowledge and V1 does not accept it here"
    ),
    NOT_KNOWABLE_AT_AS_OF: (
        "the fact was not public at the requested instant, so admitting it "
        "would answer a question with information the moment did not have"
    ),
    AMBIGUITY_RAISED: (
        "the archive's own ambiguity classification raised a case this "
        "boundary cannot resolve without choosing between figures"
    ),
}


class ValuationAdmissionError(RuntimeError):
    """
    The crossing could not be attempted at all.

    Raised for a missing or unusable valuation-side price. It is deliberately an
    exception rather than a refusal label: a price is not an evidence question,
    and `ValuationInputs.price` is a required float that the engine refuses at
    `st_eva_runner.py:1270-1271`. Substituting `0.0` for an absent price -- which
    is what `ValuationInputs.from_observations` does at
    `data_contract.py:1833-1839` -- would make that refusal arrive as a crash
    carrying a number nobody filed. The existing refusal is left to stand.
    """


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Refusal:
    """One admission finding: a local label and the reason it was reached."""

    label: str
    reason: str

    def contract_dict(self) -> Dict[str, Any]:
        return {"label": self.label, "reason": self.reason}


@dataclass(frozen=True)
class Admission:
    """
    What happened to one metric, and the provenance the reader was shown.

    The record exists because a number that reaches the engine has to be able to
    answer "which fact was this?" without asking anyone. Every field below is
    copied from a stored row or read from the registry; none of it is invented for
    the reader's benefit.

    Bounded by that last phrase. `SQLiteArchive.observations_for` collapses on
    `contract_id` before admission runs, so the candidate set here is what the
    archive returned, not every fact it holds. `superseded_accessions == 0` means
    no other copy was shown, which is not the same claim as no other filing
    reported the period.
    """

    metric: str
    as_of: str
    admitted: bool
    observation_id: Optional[str] = None
    contract_id: Optional[str] = None
    source_fact_id: Optional[str] = None
    accession: Optional[str] = None
    taxonomy: Optional[str] = None
    concept: Optional[str] = None
    source_concept_ref: Optional[str] = None
    mapping_type: Optional[str] = None
    relation_kind: Optional[str] = None
    mapping_fidelity: Optional[str] = None
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    duration_days: Optional[int] = None
    fiscal_year: Optional[int] = None
    fiscal_period: Optional[str] = None
    form: Optional[str] = None
    value: Any = None
    unit: Optional[str] = None
    currency: Optional[str] = None
    currency_basis: Optional[str] = None
    available_at: Optional[str] = None
    available_at_basis: Optional[str] = None
    availability_class: Optional[str] = None
    retrieved_at: Optional[str] = None
    considered_observations: int = 0
    superseded_accessions: int = 0
    superseded_values: Tuple[float, ...] = ()
    competing_concepts: Tuple[str, ...] = ()
    refusals: Tuple[Refusal, ...] = ()
    knowledge_overlay_available: bool = False

    @property
    def refusal_labels(self) -> Tuple[str, ...]:
        return tuple(refusal.label for refusal in self.refusals)

    @property
    def value_diverges_from_superseded(self) -> bool:
        """
        Whether a superseded filing of the same period reported a different value.

        This is disclosure, not a verdict. `latest_knowable` answers "what did a
        reader at this instant most recently see", which is a point-in-time
        question, and it is the right answer. A restatement is a real event in the
        archive and 2.4 class D exists to keep it visible, so a divergent earlier
        copy is reported here rather than resolved into a winner.
        """
        if not is_number(self.value):
            return False
        return any(
            is_number(other) and float(other) != float(self.value)
            for other in self.superseded_values
        )

    def contract_dict(self) -> Dict[str, Any]:
        return {
            "metric": self.metric,
            "as_of": self.as_of,
            "admitted": self.admitted,
            "observation_id": self.observation_id,
            "contract_id": self.contract_id,
            "source_fact_id": self.source_fact_id,
            "accession": self.accession,
            "taxonomy": self.taxonomy,
            "concept": self.concept,
            "source_concept_ref": self.source_concept_ref,
            "mapping_type": self.mapping_type,
            "relation_kind": self.relation_kind,
            "mapping_fidelity": self.mapping_fidelity,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "duration_days": self.duration_days,
            "fiscal_year": self.fiscal_year,
            "fiscal_period": self.fiscal_period,
            "form": self.form,
            "value": self.value,
            "unit": self.unit,
            "currency": self.currency,
            "currency_basis": self.currency_basis,
            "available_at": self.available_at,
            "available_at_basis": self.available_at_basis,
            "availability_class": self.availability_class,
            "retrieved_at": self.retrieved_at,
            "considered_observations": self.considered_observations,
            "superseded_accessions": self.superseded_accessions,
            "superseded_values": list(self.superseded_values),
            "value_diverges_from_superseded": self.value_diverges_from_superseded,
            "competing_concepts": list(self.competing_concepts),
            "refusals": [r.contract_dict() for r in self.refusals],
            "knowledge_overlay_available": self.knowledge_overlay_available,
        }


@dataclass(frozen=True)
class BoundaryResult:
    """The engine input and the record of how it was assembled."""

    valuation_inputs: ValuationInputs
    admissions: Tuple[Admission, ...]
    asset: str
    as_of: str
    valuation_side_currency: str

    @property
    def admitted(self) -> Dict[str, Admission]:
        return {
            admission.metric: admission
            for admission in self.admissions
            if admission.admitted
        }

    @property
    def refused(self) -> Dict[str, Admission]:
        return {
            admission.metric: admission
            for admission in self.admissions
            if not admission.admitted
        }

    def contract_dict(self) -> Dict[str, Any]:
        return {
            "asset": self.asset,
            "as_of": self.as_of,
            "valuation_side_currency": self.valuation_side_currency,
            "crossing_metrics": list(V1_CROSSING_METRICS),
            "admissions": [
                admission.contract_dict() for admission in self.admissions
            ],
        }


# ---------------------------------------------------------------------------
# Reading what the archive stored
# ---------------------------------------------------------------------------

_IDENTITY_COLUMNS = (
    "contract_id",
    "taxonomy",
    "accession",
    "form",
    "fiscal_year",
    "fiscal_period",
    "statement",
    "instant",
    "source_fact_id",
    "source_concept_ref",
)


def _filing_identity(
    connection: Optional[sqlite3.Connection],
    observation: Observation,
) -> Dict[str, Any]:
    """
    The filing identity of one observation, from the archive row or from its raw.

    `Observation.contract_dict()` does not carry `accession`, `form`,
    `fiscal_year`, `fiscal_period`, `source_fact_id` or `source_concept_ref`,
    because the engine surface has no place for them. They are exactly what makes
    a valuation input auditable, so they are read here. The stored row is
    authoritative; the raw payload is the fallback for a row written without a
    `FilingRef`, which is the shape a regression fixture produces.
    """
    identity: Dict[str, Any] = {name: None for name in _IDENTITY_COLUMNS}
    identity["contract_id"] = observation.observation_id
    if connection is not None:
        columns = ", ".join(_IDENTITY_COLUMNS)
        try:
            row = connection.execute(
                f"SELECT {columns} FROM observations WHERE contract_id = ?"
                " LIMIT 1",
                (observation.observation_id,),
            ).fetchone()
        except sqlite3.Error:
            row = None
        if row is not None:
            for name in _IDENTITY_COLUMNS:
                identity[name] = row[name]
    raw = observation.raw if isinstance(observation.raw, dict) else {}
    fact = raw.get("sec_fact") if isinstance(raw.get("sec_fact"), dict) else {}
    for column, key in (
        ("taxonomy", "taxonomy"),
        ("accession", "accession"),
        ("form", "form"),
        ("fiscal_year", "fy"),
        ("fiscal_period", "fp"),
    ):
        if identity.get(column) is None and fact.get(key) is not None:
            identity[column] = fact[key]
    if identity.get("source_concept_ref") is None:
        taxonomy = identity.get("taxonomy")
        tag = fact.get("tag")
        if taxonomy and tag:
            identity["source_concept_ref"] = f"{taxonomy}:{tag}"
    return identity


def _concept_of(observation: Observation, identity: Dict[str, Any]) -> Optional[str]:
    """The qualified source concept, whichever field the row kept it in."""
    reference = identity.get("source_concept_ref")
    if reference:
        return str(reference)
    raw = observation.raw if isinstance(observation.raw, dict) else {}
    fact = raw.get("sec_fact") if isinstance(raw.get("sec_fact"), dict) else {}
    basis = observation.basis if isinstance(observation.basis, dict) else {}
    taxonomy = identity.get("taxonomy") or basis.get("reporting_framework")
    tag = fact.get("tag")
    if taxonomy and tag:
        return f"{taxonomy}:{tag}"
    return None


def _duration_days(observation: Observation) -> Optional[int]:
    """
    Days in the observation's own period, or None when it is not readable.

    `Observation` carries no duration, and `sec_provider` keeps its own
    `duration_days` helper alongside the TTM constructions this boundary must not
    use, so the arithmetic is done here from the contract's own date parser. An
    unreadable boundary is not a period of any length.
    """
    start = parse_iso_date(observation.period_start)
    end = parse_iso_date(observation.period_end)
    if start is None or end is None:
        return None
    return (end - start).days


def _availability_class(
    store: ArchiveStore,
    asset: str,
    observation: Observation,
) -> str:
    """
    The recorded availability class, preferring what the store stored.

    `availability_class_for` is the contract-level derivation and is the right
    answer for a store that records nothing. `SQLiteArchive` does record it, and
    the recorded value is what replay eligibility was computed from, so the store
    is asked first and a disagreement is resolved in the store's favour: the
    stored class is the operative one for a replay.
    """
    reader = getattr(store, "availability_classes", None)
    if callable(reader):
        try:
            recorded = reader(asset)
        except Exception:  # noqa: BLE001 - a store that cannot answer has no opinion
            recorded = None
        if isinstance(recorded, dict):
            value = recorded.get(observation.observation_id)
            if value is not None:
                return str(value)
    return availability_class_for(observation)


def _knowledge_overlay_available(store: ArchiveStore) -> bool:
    """
    Whether the archive holds any interpretation at all.

    Reported, never worked around. `SQLiteArchive.knowledge_state_available()`
    answers a different question -- whether the `interpretations` *table* exists,
    which a freshly migrated archive does and an archive predating 2.61 does not.
    The question the boundary needs is whether any effective reading was ever
    written, so `interpretation_count` is asked first and the table's existence is
    only the fallback for a store that has no count to give.

    Measured: the count is zero in the MU pilot and in all five declared corpora,
    so a unit or currency correction made after archival is currently
    unrepresentable and the stored reading stands for every cutoff. A caller
    reading `False` here knows the admission was decided on the stored reading.
    """
    counter = getattr(store, "interpretation_count", None)
    if callable(counter):
        try:
            return int(counter()) > 0
        except Exception:  # noqa: BLE001 - fall through to the weaker answer
            pass
    reader = getattr(store, "knowledge_state_available", None)
    if callable(reader):
        try:
            return bool(reader())
        except Exception:  # noqa: BLE001
            return False
    return False


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------


def _refusal(label: str, detail: Optional[str] = None) -> Refusal:
    reason = REFUSALS[label]
    if detail:
        reason = f"{reason} ({detail})"
    return Refusal(label=label, reason=reason)


def _registry_scope_refusals(metric: str, registry: CoreRegistry) -> List[Refusal]:
    """
    Rule 1: the metric must be one V1 names and one the registry endorses.

    The scope is asked of the registry rather than asserted, so a deprecated
    metric, an unknown metric, or a metric the registry holds as a different unit
    family all stop here rather than at a currency check three gates later.
    """
    if metric not in V1_CROSSING_METRICS:
        return [
            _refusal(METRIC_NOT_IN_V1_SCOPE, f"requested {metric!r}")
        ]
    try:
        resolved = registry.resolve_metric(metric)
    except Exception as error:  # noqa: BLE001 - a broken chain is a refusal
        return [_refusal(METRIC_NOT_IN_V1_SCOPE, str(error))]
    entry = registry.metric(resolved)
    if entry is None:
        return [
            _refusal(METRIC_NOT_IN_V1_SCOPE, f"the registry holds no {metric!r}")
        ]
    refusals: List[Refusal] = []
    if entry.status != V1_REQUIRED_REGISTRY_STATUS:
        refusals.append(
            _refusal(
                METRIC_NOT_IN_V1_SCOPE,
                f"the registry marks {metric!r} {entry.status}",
            )
        )
    if entry.unit_family != V1_REQUIRED_UNIT_FAMILY:
        refusals.append(
            _refusal(
                UNIT_NOT_MONETARY,
                f"the registry holds {metric!r} as unit family {entry.unit_family}",
            )
        )
    if entry.normal_period_type != V1_REQUIRED_PERIOD_TYPE:
        refusals.append(
            _refusal(
                PERIOD_NOT_DISCRETE,
                f"the registry holds {metric!r} as a {entry.normal_period_type} "
                "metric",
            )
        )
    return refusals


def _unit_refusals(observation: Observation) -> List[Refusal]:
    """Rule 3: the value must be money, in the unit the contract names."""
    if observation.unit != "currency":
        return [
            _refusal(
                UNIT_NOT_MONETARY,
                f"the observation's unit is {observation.unit!r}",
            )
        ]
    return []


def _currency_refusals(
    observation: Observation,
    price: Observation,
) -> List[Refusal]:
    """
    Rule 4: same declared currency, or nothing.

    `currencies_match` is the stricter of the contract's two currency rules; it
    treats an unstated currency as a refusal, where `figure_units_compatible`
    returns True for "unknown, not different". The stricter rule is chosen because
    the engine performs no currency check of its own -- `inputs.currency` is
    carried on the dataclass and never read by `analyze` -- so a mismatch here
    would become a plausible-looking ratio rather than an error. No rate exists in
    this repository and none is introduced.
    """
    if not observation.currency:
        return [
            _refusal(
                CURRENCY_UNDECLARED,
                f"currency_basis is {observation.currency_basis!r}",
            )
        ]
    if not price.currency:
        return [
            _refusal(
                CURRENCY_UNDECLARED,
                "the valuation-side price declares no currency, so there is "
                "nothing to match against",
            )
        ]
    if not currencies_match(observation.currency, price.currency):
        return [
            _refusal(
                CURRENCY_MISMATCH,
                f"{observation.currency} against a {price.currency} price",
            )
        ]
    return []


def _mapping_refusals(
    observation: Observation,
    metric: str,
    concept: Optional[str],
    registry: CoreRegistry,
) -> Tuple[List[Refusal], Optional[str], Optional[str]]:
    """
    Rule 5: the observation's own concept, mapped exactly, at this period.

    The decision belongs to `mappings_for_observation`. That is the registry's
    answer to precisely this question -- one stored metric plus the concept the
    fact actually carries -- and `mappings_for_metric`'s own docstring points at
    it, because a metric-level list is the wrong shape for a single observation:
    under a supersession the successor's concepts would all appear to belong to
    every legacy row, which is the exposure 2.49 measured over 8,193 historical
    rows. Using the resolver also brings its discrimination with it, so a PARTIAL
    that never earned a destination reports the 2.74 basis for its refusal
    rather than merely naming its own type.

    `relation_kind` is read separately, from the metric's own row. The
    `ConceptMapping` that `mappings_for_observation` builds does not carry the
    field, so it would report IDENTITY for every admitted row -- including a
    COMPOSITION one, and `long_term_debt` is a COMPOSITION. The decision does not
    come from that read; only the relation does.

    `basis.mapping_fidelity` is checked too, and independently: it records what
    the ingest applied, which is a different question from what the registry
    declares now. A row the registry calls EXACT and the ingest recorded as
    PARTIAL is a disagreement, and a disagreement is not something to pick a
    side of.
    """
    mapping_type: Optional[str] = None
    relation_kind: Optional[str] = None
    refusals: List[Refusal] = []

    resolved = registry.mappings_for_observation(
        metric,
        source_concept=concept,
        as_of=observation.period_end,
    )
    if not resolved.is_resolved:
        # The resolver's own reason distinguishes no source concept from no
        # applicable mapping from an ambiguous claim, so it is carried through
        # rather than replaced with a message of our own.
        refusals.append(
            _refusal(MAPPING_NOT_EXACT, resolved.reason or resolved.status)
        )
    else:
        mapping_type = resolved.mappings[0].mapping_type
        if mapping_type != "EXACT":
            refusals.append(
                _refusal(
                    MAPPING_NOT_EXACT,
                    f"{concept} is {mapping_type} for {metric!r}",
                )
            )
        relation_kind = _relation_kind_of(
            registry, metric, concept, observation.period_end
        )

    basis = observation.basis if isinstance(observation.basis, dict) else {}
    fidelity = basis.get("mapping_fidelity")
    if (
        fidelity is not None
        and fidelity != "EXACT"
        and not any(refusal.label == MAPPING_NOT_EXACT for refusal in refusals)
    ):
        refusals.append(
            _refusal(MAPPING_NOT_EXACT, f"the row records mapping fidelity {fidelity}")
        )
    if mapping_type is None:
        raw = observation.raw if isinstance(observation.raw, dict) else {}
        recorded = raw.get("mapping_type")
        if isinstance(recorded, str):
            mapping_type = recorded
    return refusals, mapping_type, relation_kind


def _relation_kind_of(
    registry: CoreRegistry,
    metric: str,
    concept: Optional[str],
    period_end: Optional[str],
) -> Optional[str]:
    """
    The relation the metric's own row asserts for this concept, or None.

    A narrow read on purpose: `mappings_for_metric` is the right shape for a
    ledger and the wrong one for an admission decision, and it is used here only
    because the field the decision needs is the one the observation-level
    resolver leaves at its default.
    """
    for mapping in registry.mappings_for_metric(metric, as_of=period_end):
        if mapping.concept_id == concept:
            return mapping.relation_kind
    return None


def _ambiguity_refusals(
    peers: Sequence[Observation],
    concepts: Sequence[Optional[str]],
    identities: Sequence[Dict[str, Any]],
) -> List[Refusal]:
    """
    Rule 6: one period, one concept, or nothing.

    A period with a single row is never ambiguous, so the classifier is not asked
    about one. `classify_ambiguity` returns `DIMENSION_COLLISION` whenever it sees
    exactly one accession, because on `EvidenceQuery` a basis is only ever built
    from gathered rows and one accession among several rows means an aggregate
    over unnamed members. Handed a single row it answers the same way, which is
    true of the classifier and not of the row, so the row count is checked first.

    `MULTIPLE_FILINGS` is deliberately *not* a refusal. Several filings reporting
    one period is the ordinary comparative re-report case -- measured on MU, one
    `net_income` period is published by six accessions over eighteen months -- and
    rule 10 discloses it by naming the chosen accession and counting the rest of
    the copies the archive returned.

    The registry's window view is not asked here. `revenue` carries a
    `vendor:trailingTotalRevenue` EQUIVALENT mapping on every date, and treating
    an unobserved vendor mapping as a competing claim would refuse every period
    forever.
    """
    if len(peers) < 2:
        return []
    distinct = sorted({concept for concept in concepts if concept})
    if len(distinct) > 1:
        return [
            _refusal(
                CONCEPT_AMBIGUOUS,
                f"{', '.join(distinct)} all reported this period",
            )
        ]
    basis = {
        "providers": sorted({peer.provider for peer in peers}),
        "source_concepts": list(distinct),
        "accessions": sorted(
            {
                str(identity.get("accession"))
                for identity in identities
                if identity.get("accession")
            }
        ),
        "unmapped_observations": [
            peer.observation_id
            for peer, concept in zip(peers, concepts)
            if not concept
        ],
        "observation_count": len(peers),
    }
    reason = classify_ambiguity(basis)
    if reason in (
        AMBIGUITY_CROSS_PROVIDER,
        AMBIGUITY_MULTIPLE_CONCEPTS,
        AMBIGUITY_DIMENSION,
    ):
        return [_refusal(AMBIGUITY_RAISED, f"classified {reason}")]
    return []


def _period_refusals(observation: Observation) -> List[Refusal]:
    """
    Rule 7: an observed annual filing, and nothing else.

    `current_revenue` is declared *trailing*, so only an observed annual filing
    (approximately one fiscal year, 330-400 days) may cross. A discrete quarter
    is not trailing, a cumulative stub is not trailing, and an instant is not a
    period at all. Nothing here annualises, rolls forward, or calls into
    `sec_provider`'s TTM constructions.
    """
    if observation.period_start is None or observation.period_end is None:
        return [
            _refusal(
                PERIOD_NOT_DISCRETE,
                "the observation is an instant, not a period",
            )
        ]
    days = _duration_days(observation)
    if days is None:
        return [_refusal(PERIOD_NOT_DISCRETE, "the period has no readable length")]
    if YEAR_MIN_DAYS <= days <= YEAR_MAX_DAYS:
        return []
    if QUARTER_MIN_DAYS <= days <= QUARTER_MAX_DAYS:
        return [
            _refusal(
                PERIOD_NOT_DISCRETE,
                f"the period spans {days} days, which is a discrete quarter, not "
                f"the trailing annual figure `current_revenue` declares",
            )
        ]
    return [
        _refusal(
            PERIOD_NOT_DISCRETE,
            f"the period spans {days} days, which is neither an observed annual "
            f"filing ({YEAR_MIN_DAYS}-{YEAR_MAX_DAYS} days) nor any other "
            f"trailing figure; `current_revenue` is declared trailing and must "
            f"not be synthesised from a partial or cumulative period",
        )
    ]


def _availability_refusals(klass: str, observation: Observation) -> List[Refusal]:
    """
    Rule 8: a source-declared publication time, and nothing weaker.

    `ARCHIVE_FIRST_SEEN` is refused along with `UNDECLARED`. The first records
    when this archive happened to ask, which is knowledge about the archive rather
    than about the world, and an engine input is the last place a retrieval time
    should be allowed to stand in for a publication time.
    """
    if klass == SOURCE_DECLARED and observation.available_at:
        return []
    if klass == ARCHIVE_FIRST_SEEN:
        return [
            _refusal(
                AVAILABILITY_UNDECLARED,
                "the fact is archive-first-seen, which records when ST-EVA asked "
                "rather than when the filer published",
            )
        ]
    return [_refusal(AVAILABILITY_UNDECLARED, f"availability class is {klass}")]


# ---------------------------------------------------------------------------
# The crossing
# ---------------------------------------------------------------------------


def _require_price(price: Any) -> Observation:
    """
    The valuation-side price, or a refusal to proceed.

    A price is not an evidence question, and the engine already refuses a
    non-positive one. Carrying that refusal forward means the adapter must not
    invent a number to be refused with.
    """
    if price is None:
        raise ValuationAdmissionError(
            "the crossing needs a valuation-side price, and none was supplied. "
            "ST-EVA will not fabricate one: the engine's own refusal ('Current "
            "price must be positive.') is the correct outcome and it is left to "
            "stand."
        )
    if not isinstance(price, Observation):
        raise ValuationAdmissionError(
            f"the price must be an Observation, not {type(price).__name__}"
        )
    if price.metric != METRIC_PRICE:
        raise ValuationAdmissionError(
            f"the supplied price observation carries metric {price.metric!r}, "
            f"not {METRIC_PRICE!r}"
        )
    if not is_number(price.value) or float(price.value) <= 0:
        raise ValuationAdmissionError(
            "the valuation-side price is absent or not a positive finite number, "
            "so no valuation input can be constructed from it"
        )
    return price


def _registry_of(store: ArchiveStore) -> Tuple[CoreRegistry, Optional[sqlite3.Connection]]:
    """
    The registry over the store's own connection, or a stated inability.

    The scope is a registry question, so it is asked of the registry rather than
    of a list in this module. A store that exposes no connection cannot answer
    one, and that is reported rather than worked around.
    """
    connection = getattr(store, "connection", None)
    if connection is None:
        raise ValuationAdmissionError(
            "the crossing needs the store's connection to ask the metric registry "
            "what a metric is. A store that exposes none cannot answer, and the "
            "scope is not restated here as a fallback list."
        )
    return CoreRegistry(connection), connection


def _admit_one(
    metric: str,
    store: ArchiveStore,
    asset: str,
    connection: Optional[sqlite3.Connection],
    registry: CoreRegistry,
    observations: Sequence[Observation],
    knowable_ids: Set[str],
    price: Observation,
    as_of: str,
    overlay: bool,
) -> Admission:
    """Rules 1 through 10 for one metric, in that order."""
    base: Dict[str, Any] = dict(
        metric=metric, as_of=as_of, knowledge_overlay_available=overlay
    )

    # Rule 1 -- metric scope, asked of the registry.
    scope = _registry_scope_refusals(metric, registry)
    if scope:
        return Admission(admitted=False, refusals=tuple(scope), **base)

    # Rule 2 -- something to consider.
    candidates = [item for item in observations if item.metric == metric]
    if not candidates:
        return Admission(
            admitted=False,
            refusals=(
                _refusal(
                    UNAVAILABLE,
                    f"no {metric!r} row is replay-eligible at this instant",
                ),
            ),
            **base,
        )

    considered = len(candidates)
    identities: Dict[str, Dict[str, Any]] = {}
    concepts: Dict[str, Optional[str]] = {}
    classes: Dict[str, str] = {}
    # Rule 5's answer is kept per observation so rule 10 reads it back rather than
    # asking the registry a second time about a row already decided. One crossing
    # of a filing with six accessions would otherwise ask twelve times.
    mappings: Dict[str, Tuple[Optional[str], Optional[str]]] = {}
    admissible: List[Observation] = []
    labels: Dict[str, int] = {}
    first_detail: Optional[str] = None

    for observation in candidates:
        identity = _filing_identity(connection, observation)
        identities[observation.observation_id] = identity
        concept = _concept_of(observation, identity)
        concepts[observation.observation_id] = concept
        classes[observation.observation_id] = _availability_class(
            store, asset, observation
        )

        # Rules 3, 4, 5, 7, 8 and 9 are properties of a single row, and are
        # evaluated in that order. Rule 6 needs the whole period, so it runs
        # after every row sharing a period has been gathered.
        refusals: List[Refusal] = []
        refusals.extend(_unit_refusals(observation))
        refusals.extend(_currency_refusals(observation, price))
        mapping_refusals, mapping_type, relation_kind = _mapping_refusals(
            observation, metric, concept, registry
        )
        mappings[observation.observation_id] = (mapping_type, relation_kind)
        refusals.extend(mapping_refusals)
        refusals.extend(_period_refusals(observation))
        refusals.extend(
            _availability_refusals(classes[observation.observation_id], observation)
        )
        if observation.observation_id not in knowable_ids:
            refusals.append(
                _refusal(
                    NOT_KNOWABLE_AT_AS_OF,
                    f"available_at {observation.available_at!r}",
                )
            )
        if not refusals:
            admissible.append(observation)
            continue
        for refusal in refusals:
            labels[refusal.label] = labels.get(refusal.label, 0) + 1
        if first_detail is None:
            first_detail = refusals[0].reason

    if not admissible:
        return Admission(
            admitted=False,
            considered_observations=considered,
            refusals=tuple(
                _refusal(
                    label,
                    f"{labels[label]} of {considered} rows the archive returned"
                    + (f"; first: {first_detail}" if first_detail else ""),
                )
                for label in sorted(labels)
            ),
            **base,
        )

    # Rule 6 -- one period, one concept. Evaluated per period group over every
    # row that reached this point, so a refused claim never dilutes the question
    # and an admitted one can still be shown to have been contested.
    #
    # Ambiguity is scoped to the period, not the metric. A period whose own rows
    # carry competing source concepts is refused on its own; that refusal does
    # not veto other periods that are single-concept and single-accession. The
    # metric-wide veto this replaces was an implementation defect: historical
    # concept overlap (2016-2018 on MU) was blocking a clean 2026Q3 candidate
    # that had nothing to do with the contested years.
    periods: Dict[Tuple[Optional[str], Optional[str]], List[Observation]] = {}
    for observation in admissible:
        periods.setdefault(
            (observation.period_start, observation.period_end), []
        ).append(observation)

    contested_keys: Set[Tuple[Optional[str], Optional[str]]] = set()
    contested: List[Refusal] = []
    contenders: Set[str] = set()
    for key in sorted(periods, key=lambda item: (item[1] or "", item[0] or "")):
        peers = [
            item
            for item in candidates
            if (item.period_start, item.period_end) == key
        ]
        found = _ambiguity_refusals(
            peers,
            [concepts.get(item.observation_id) for item in peers],
            [identities.get(item.observation_id) or {} for item in peers],
        )
        if found:
            contested_keys.add(key)
            contenders.update(
                concept
                for concept in concepts.values()
                if concept
            )
            contested.extend(found)

    if contested_keys:
        # Remove the contested periods from admissible. Rows from other periods
        # survive and may still be selected by rule 10.
        admissible = [
            observation
            for observation in admissible
            if (observation.period_start, observation.period_end)
            not in contested_keys
        ]

    if not admissible:
        # Every surviving period was either empty or contested. The metric is
        # refused, and the record names what contested it.
        return Admission(
            admitted=False,
            considered_observations=considered,
            competing_concepts=tuple(sorted(contenders)) if contenders else (),
            refusals=tuple(contested) if contested else (
                _refusal(
                    UNAVAILABLE,
                    "no admitted row was knowable at this instant",
                ),
            ),
            **base,
        )

    # Rule 10 -- select among the admitted rows with the contract's own selector.
    # It runs over an `ObservationSet` holding only what passed admission, so a
    # refused row that happens to be the newest cannot win. That is not a second
    # selector: `latest_knowable` is the one that runs, over a smaller domain, and
    # it keeps the archive's ordering rather than inventing one.
    selected = ObservationSet(
        ticker=asset, observations=admissible
    ).latest_knowable(as_of, metric)
    if selected is None:
        return Admission(
            admitted=False,
            considered_observations=considered,
            refusals=(
                _refusal(
                    UNAVAILABLE,
                    "no admitted row was knowable at this instant",
                ),
            ),
            **base,
        )

    identity = identities.get(selected.observation_id) or {}
    concept = concepts.get(selected.observation_id)
    selected_accession = identity.get("accession")
    same_period = [
        item
        for item in candidates
        if (item.period_start, item.period_end)
        == (selected.period_start, selected.period_end)
    ]
    superseded = [
        item
        for item in same_period
        if item.observation_id != selected.observation_id
        and concepts.get(item.observation_id) == concept
        and identities.get(item.observation_id, {}).get("accession")
        != selected_accession
    ]
    # Rule 5 already decided this row. Reading its answer back rather than asking
    # again is the point of the per-observation cache.
    mapping_type, relation_kind = mappings.get(selected.observation_id, (None, None))
    basis = selected.basis if isinstance(selected.basis, dict) else {}
    competing = sorted(
        {
            found
            for item in same_period
            for found in (concepts.get(item.observation_id),)
            if found
        }
    )

    return Admission(
        admitted=True,
        observation_id=selected.observation_id,
        contract_id=identity.get("contract_id"),
        source_fact_id=identity.get("source_fact_id"),
        accession=selected_accession,
        taxonomy=identity.get("taxonomy"),
        concept=concept,
        source_concept_ref=identity.get("source_concept_ref") or concept,
        mapping_type=mapping_type,
        relation_kind=relation_kind,
        mapping_fidelity=basis.get("mapping_fidelity"),
        period_start=selected.period_start,
        period_end=selected.period_end,
        duration_days=_duration_days(selected),
        fiscal_year=identity.get("fiscal_year"),
        fiscal_period=identity.get("fiscal_period"),
        form=identity.get("form"),
        value=selected.value,
        unit=selected.unit,
        currency=selected.currency,
        currency_basis=selected.currency_basis,
        available_at=selected.available_at,
        available_at_basis=selected.available_at_basis,
        availability_class=classes.get(selected.observation_id)
        or availability_class_for(selected),
        retrieved_at=selected.retrieved_at,
        considered_observations=considered,
        superseded_accessions=len(superseded),
        superseded_values=tuple(
            float(item.value) for item in superseded if is_number(item.value)
        ),
        competing_concepts=tuple(competing),
        **base,
    )


def admit(
    store: ArchiveStore,
    asset: str,
    as_of: str,
    price: Observation,
    metrics: Sequence[str] = V1_CROSSING_METRICS,
) -> Tuple[ValuationInputs, Tuple[Admission, ...]]:
    """
    Build a `ValuationInputs` and the records explaining how each metric fared.

    The price is valuation-side and passes straight through. Every other field
    keeps the dataclass's own default, which is what "kept valuation-side" means
    in code: `UNAVAILABLE` for a scalar and `{}` for a band, never a zero and
    never a related metric.
    """
    checked_price = _require_price(price)
    registry, connection = _registry_of(store)

    # The store's own point-in-time read. This is rule 9's implementation: it
    # filters on `replay_eligible_from`, overlays the interpretation effective at
    # the cutoff, and never consults `retrieved_at`. Re-deriving eligibility here
    # would be a second selector that could disagree with the one a replay already
    # uses, and two answers to "when was this knowable" is the failure 2.14
    # measured across two delivery routes.
    observations = list(store.observations_for(asset, as_of))
    overlay = _knowledge_overlay_available(store)
    # `eligibility` is passed as None deliberately. That escape hatch exists for
    # archive-first-seen observations, and rule 8 refuses those, so supplying it
    # could only ever weaken this check.
    knowable_ids = {
        item.observation_id
        for item in ObservationSet(
            ticker=asset, observations=observations
        ).knowable_at(as_of, metric=None)
    }

    admissions = tuple(
        _admit_one(
            metric=metric,
            store=store,
            asset=asset,
            connection=connection,
            registry=registry,
            observations=observations,
            knowable_ids=knowable_ids,
            price=checked_price,
            as_of=as_of,
            overlay=overlay,
        )
        for metric in metrics
    )

    revenue = next(
        (
            admission
            for admission in admissions
            if admission.metric == METRIC_REVENUE and admission.admitted
        ),
        None,
    )
    # Only `current_revenue` is ever written. Every other field keeps the
    # dataclass's own default, which is what "kept valuation-side" means in code:
    # `UNAVAILABLE` for a scalar and `{}` for a band, never a zero and never a
    # related metric.
    inputs = ValuationInputs(
        price=float(checked_price.value),
        currency=checked_price.currency,
        current_revenue=(
            revenue.value if revenue is not None else UNAVAILABLE
        ),
    )
    return inputs, admissions


def build_valuation_inputs(
    store: ArchiveStore,
    asset: str,
    as_of: str,
    price: Observation,
    metrics: Sequence[str] = V1_CROSSING_METRICS,
) -> BoundaryResult:
    """
    The V1 crossing, returning the engine input and its provenance together.

    The pair is the deliverable. `ValuationInputs` has no field for an accession,
    a period window or a reason, and it must not grow one, so the record beside it
    is what makes the number auditable.
    """
    inputs, admissions = admit(store, asset, as_of, price, metrics=metrics)
    return BoundaryResult(
        valuation_inputs=inputs,
        admissions=admissions,
        asset=asset,
        as_of=as_of,
        valuation_side_currency=str(price.currency or ""),
    )
