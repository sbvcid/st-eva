from __future__ import annotations

"""
ST-EVA 2.3-C - Investment Context.

The verifiable research material ST-EVA holds about one asset at one point in
time, packaged so that any consumer can read it and check every number in it
without knowing how ST-EVA is built.

    "these are the data and the arithmetic, and here is how you check every
     number I produced."

It is not a report ST-EVA wrote about a stock, and it is not a conclusion.

Three properties, in priority order, and the earlier one wins any conflict:

    Every number is traceable. Start from any figure and walk to the raw
    observation, through the evidence, the validation, and the formula,
    without leaving the document.

    No figure asserts more than it knows. An undeclared period, currency, or
    source is presented as undeclared. A value that could not be established
    is presented as absent.

    No figure asserts an opinion. Data quality is counts and statuses, never a
    grade.

Dependency direction: this module imports `data_contract` and
`operation_registry`. It does not import `st_eva_runner` or `sec_provider`, so
the document and the engine are one-way and a document can never be able to
influence a number the engine produced.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import operation_registry
from data_contract import (
    AvailabilityBasis,
    FORBIDDEN_VOCABULARY,
    METRIC_UNITS,
    MIN_BAND_OBSERVATIONS_FOR_REFERENCE,
    Observation,
    Unit,
    ValidationStatus,
    duration_days,
    is_comparable_observation,
    is_number,
    parse_iso_date,
    safe_float,
    utc_now,
)
from operation_registry import (
    CurrencyMismatchError,
    MissingOperandError,
    RegistryError,
    evaluate,
    registry_contract,
    result_unit,
)

CONTEXT_SCHEMA_VERSION = "2.3-C.2"
MIN_READER_VERSION = "2.3-C.0"
LEGACY_SNAPSHOT_SCHEMA_VERSION = "2.2.3"
CONTRACT_VERSION = "2.3-A"
CROSS_SOURCE_VERSION = "2.3-B"

# Tolerance for the parity check between the engine's figure and the registry's
# recomputation of it. Relative, so a 466 billion revenue figure and a 2.85
# per-share EPS are both checked at a meaningful resolution.
PARITY_RELATIVE_TOLERANCE = 1e-9
PARITY_ABSOLUTE_TOLERANCE = 1e-9

# The annualisation convention the 2.2.3 engine applies to realised volatility.
# It is named here rather than buried in the code, because it materially changes
# the number and a consumer is entitled to see it.
TRADING_PERIODS_PER_YEAR = 252

# Ref kinds. `operands` may name any kind except `val`: a validation judges, it
# does not feed arithmetic.
KIND_OBSERVATION = "obs"
KIND_EVIDENCE = "ev"
KIND_VALIDATION = "val"
KIND_DERIVED = "der"
KIND_REFERENCE = "refc"

REF_KINDS = (
    KIND_OBSERVATION,
    KIND_EVIDENCE,
    KIND_VALIDATION,
    KIND_DERIVED,
    KIND_REFERENCE,
)

# The field an operand of each ref kind reads. Declared once, here, so a
# consumer never has to guess which field a bare ref string means.
OPERAND_FIELD_BY_KIND = {
    KIND_OBSERVATION: "value",
    KIND_EVIDENCE: "value",
    KIND_DERIVED: "value",
    KIND_REFERENCE: "operand_field",
}

PROVENANCE_OBSERVED = "OBSERVED"
PROVENANCE_DERIVED = "DERIVED"
PROVENANCE_CONDITIONAL = "CONDITIONAL"
PROVENANCE_UNAVAILABLE = "UNAVAILABLE"

# reason_kind vocabulary for the unavailable section. Closed, so reasons can be
# counted and compared across runs.
REASON_NOT_REPORTED = "NOT_REPORTED_BY_SOURCE"
REASON_MISSING_INPUT = "MISSING_INPUT"
REASON_NO_REFERENCE = "NO_REFERENCE_AVAILABLE"
REASON_INSUFFICIENT_OBSERVATIONS = "INSUFFICIENT_OBSERVATIONS"
REASON_CURRENCY_MISMATCH = "CURRENCY_MISMATCH"
REASON_NOT_AVAILABLE = "NOT_AVAILABLE"


class ContextError(Exception):
    """A context could not be built, or a built context is not self-consistent."""


class UnresolvedRefError(ContextError):
    """A ref names something the document does not contain."""


class ParityError(ContextError):
    """
    The registry's recomputation disagrees with the engine's figure.

    This is a defect, not a tolerance question. The context is built from the
    engine's output, so a disagreement means one of the two is wrong and the
    document must not be published.
    """


@dataclass(frozen=True)
class Figure:
    """
    One number in the document, or the absence of one.

    An unavailable figure carries no `value` at all. Not `null` with a sibling
    status, not zero, not a median. The key is absent, and the figure appears
    in `unavailable` with a reason.
    """

    ref: str
    unit: Optional[str]
    currency: Optional[str] = None
    provenance_kind: str = PROVENANCE_OBSERVED
    value: Any = None
    available: bool = True
    note: Optional[str] = None

    def contract_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "ref": self.ref,
            "unit": self.unit,
            "currency": self.currency,
            "provenance_kind": self.provenance_kind,
        }
        if self.available:
            payload["value"] = self.value
        if self.note:
            payload["note"] = self.note
        return payload


@dataclass(frozen=True)
class Derivation:
    """The record that makes one derived figure checkable."""

    ref: str
    operation: Dict[str, Any]
    expression: str
    deterministic: bool = True
    non_deterministic_reason: Optional[str] = None
    inputs_observed_at: Tuple[str, ...] = ()
    conditional_on: Tuple[str, ...] = ()
    depends_on: Tuple[str, ...] = ()

    def contract_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "ref": self.ref,
            "depends_on": list(self.depends_on),
            "operation": self.operation,
            "expression": self.expression,
            "deterministic": self.deterministic,
            "inputs_observed_at": list(self.inputs_observed_at),
            "conditional_on": list(self.conditional_on),
        }
        if self.non_deterministic_reason:
            payload["non_deterministic_reason"] = (
                self.non_deterministic_reason
            )
        return payload


@dataclass
class RefEntry:
    """One row of the flat provenance table."""

    ref: str
    kind: str
    payload: Dict[str, Any]
    operand_field: Optional[str] = None
    operand_unit: Optional[str] = None

    def contract_dict(self) -> Dict[str, Any]:
        payload = dict(self.payload)
        payload["ref"] = self.ref
        payload["kind"] = self.kind
        if self.operand_field:
            payload["operand_field"] = self.operand_field
        return payload


def split_ref(ref: str) -> Tuple[str, str, Optional[str]]:
    """
    Parse a ref into (kind, identifier, selector).

    `obs:ev-pe-band-001#median` -> ("obs", "ev-pe-band-001", "median")
    `obs:obs-price-history-001#-1` -> ("obs", "obs-price-history-001", "-1")
    """
    base, _, selector = ref.partition("#")
    kind, separator, identifier = base.partition(":")
    if not separator or not identifier:
        raise ContextError(
            f"{ref!r} is not a valid ref; expected '<kind>:<identifier>' with "
            f"kind in {list(REF_KINDS)}"
        )
    if kind not in REF_KINDS:
        raise ContextError(
            f"{ref!r} names unknown ref kind {kind!r}; expected one of "
            f"{list(REF_KINDS)}"
        )
    return kind, identifier, selector or None


def observation_ref(observation_id: str) -> str:
    return f"{KIND_OBSERVATION}:{observation_id}"


def evidence_ref(evidence_id: str) -> str:
    return f"{KIND_EVIDENCE}:{evidence_id}"


def derived_ref(name: str) -> str:
    return f"{KIND_DERIVED}:{name}"


def validation_ref(name: str) -> str:
    return f"{KIND_VALIDATION}:{name}"


def reference_ref(name: str) -> str:
    return f"{KIND_REFERENCE}:{name}"


class ContextBuilder:
    """
    Assembles one Investment Context from an engine run.

    The engine's output is the authority for every value. The registry is the
    mechanism for checking it: each derived figure is recomputed here and a
    disagreement raises `ParityError` rather than producing a document. So a
    number can never reach the document that the engine did not produce, and
    every number in the document is independently checkable from it.
    """

    def __init__(
        self,
        data: Any,
        analysis: Dict[str, Any],
        evidence: Any,
        metrics: Dict[str, Any],
        material_observations: Sequence[Observation] = (),
        extra_observations: Sequence[Observation] = (),
        horizon_years: float = 1.0,
        reference_multiple: Optional[float] = None,
        pfcf_multiple: Optional[float] = None,
        ev_ebitda_multiple: Optional[float] = None,
        ps_multiple: Optional[float] = None,
        cross_validation: Optional[Dict[str, Any]] = None,
        cik: Optional[str] = None,
        sec_entity_name: Optional[str] = None,
        generated_at: Optional[str] = None,
        supersedes: Optional[str] = None,
        trading_periods: int = TRADING_PERIODS_PER_YEAR,
    ) -> None:
        self.data = data
        self.analysis = analysis
        self.evidence = evidence
        self.metrics = metrics
        # Supplied by the caller rather than imported, so this module keeps its
        # one-way dependency on the contract and can never reach back into the
        # engine to change a number.
        self.material_observations = list(material_observations)
        # Observations a second source produced, which the cross-source
        # verdicts reference. They are registered so those references resolve.
        self.extra_observations = list(extra_observations)
        self.horizon_years = horizon_years
        self.user_references = {
            "valuation_reference": reference_multiple,
            "pfcf_reference": pfcf_multiple,
            "ev_ebitda_reference": ev_ebitda_multiple,
            "ps_reference": ps_multiple,
        }
        self.cross_validation = cross_validation or {}
        self.cik = cik
        self.sec_entity_name = sec_entity_name
        self.generated_at = generated_at or utc_now()
        self.supersedes = supersedes
        self.trading_periods = trading_periods

        self.refs: Dict[str, RefEntry] = {}
        self.figures: Dict[str, Figure] = {}
        self.derivations: Dict[str, Derivation] = {}
        self.unavailable: List[Dict[str, Any]] = []
        # Observations published before the freshness window, and the metrics whose
        # newest observation is older than it. An aged observation is still
        # evidence; a metric with no recent value has nothing current to offer.
        self._aged_ids: set = set()
        self._stale_metrics: set = set()
        self._stale_days: Dict[str, int] = {}
        self._freshness_by_metric: Dict[str, Any] = {}
        self._series: Dict[str, Dict[str, Any]] = {}
        self._identity_conflicts: List[Dict[str, Any]] = []
        self._cross_source_subjects: Dict[str, Tuple[str, ...]] = {}

    # -- ref table --------------------------------------------------------

    def _register(
        self,
        ref: str,
        kind: str,
        payload: Dict[str, Any],
        operand_field: Optional[str] = None,
        operand_unit: Optional[str] = None,
    ) -> None:
        if ref in self.refs:
            raise ContextError(
                f"ref {ref!r} is already registered. Provenance must be "
                "singular: two entries for one ref would let them disagree."
            )
        self.refs[ref] = RefEntry(
            ref=ref,
            kind=kind,
            payload=payload,
            operand_field=operand_field,
            operand_unit=operand_unit,
        )

    def figure(self, ref: str) -> Figure:
        figure = self.figures.get(ref)
        if figure is None:
            raise UnresolvedRefError(
                f"{ref!r} has no figure in this context. Every figure named "
                "by a section must be registered."
            )
        return figure

    def _register_figure(self, figure: Figure) -> Figure:
        if figure.ref in self.figures:
            raise ContextError(f"figure {figure.ref!r} is already registered")
        self.figures[figure.ref] = figure
        return figure

    def _mark_unavailable(
           self,
           ref: str,
           reason: str,
           reason_kind: str,
           item: str,
           blocks: Sequence[str] = (),
           reason_code: Optional[str] = None,
       ) -> None:
           """
           Record an absent item.

           `reason_code` comes from the closed `REASON_CODES` vocabulary. It is
           not optional in practice: a refusal a consumer has to read as prose
           to act on is a guess waiting to happen, and every caller in this
           module passes a code.
           """
           self.unavailable.append(
               {
                   "item": item,
                   "ref": ref,
                   "reason": reason,
                   "reason_kind": reason_kind,
                   "reason_code": reason_code,
                   "blocks": list(blocks),
               }
           )

    # -- observations -----------------------------------------------------

    def _observation_payload(self, observation: Observation) -> Dict[str, Any]:
        payload = observation.contract_dict()
        payload["status"] = observation.status.value
        return payload

    def register_observations(self, observations: Iterable[Observation]) -> None:
        """
        Register observations that the document refers to.

        The inclusion rule is deliberate: an observation enters the table if it
        is a figure, a derivation operand, or a validation subject. Everything
        else stays reachable through the raw payload of something that is, which
        keeps the document bounded without losing anything.
        """
        for observation in observations:
            ref = observation_ref(observation.observation_id)
            if ref in self.refs:
                continue
            available = observation.is_available
            self._register(
                ref,
                KIND_OBSERVATION,
                self._observation_payload(observation),
                operand_field="value",
                operand_unit=observation.unit,
            )
            if not available:
                self._register_figure(
                    Figure(
                        ref=ref,
                        unit=observation.unit,
                        currency=observation.currency,
                        provenance_kind=PROVENANCE_UNAVAILABLE,
                        available=False,
                    )
                )
                self._mark_unavailable(
                    ref=ref,
                    reason=(
                        f"{observation.metric} was requested and not provided "
                        f"by {observation.provider}"
                    ),
                    reason_kind=REASON_NOT_REPORTED,
                    reason_code="SOURCE_DID_NOT_REPORT",
                    item=observation.metric,
                )
            else:
                self._register_figure(
                    Figure(
                        ref=ref,
                        unit=observation.unit,
                        currency=observation.currency,
                        provenance_kind=PROVENANCE_OBSERVED,
                        value=observation.value,
                    )
                )

    def register_evidence(self) -> None:
        for evidence_id in self.evidence.ids():
            evidence = self.evidence.get(evidence_id)
            if evidence is None:
                continue
            ref = evidence_ref(evidence_id)
            self._register(
                ref,
                KIND_EVIDENCE,
                {
                    "observation": observation_ref(
                        evidence.observation.observation_id
                    ),
                    "legacy_row": evidence.as_dict(),
                    "legacy_row_note": (
                        "the 2.2.3 presentation projection, retained because "
                        "it stamps the instrument currency onto valuation "
                        "multiples; the observation is the provenance"
                    ),
                },
                operand_field="value",
                operand_unit=evidence.unit,
            )
            self._register_figure(
                Figure(
                    ref=ref,
                    unit=evidence.unit,
                    currency=evidence.currency,
                    provenance_kind=PROVENANCE_OBSERVED,
                    value=(
                        evidence.value
                        if evidence.is_available
                        else None
                    ),
                    available=evidence.is_available,
                )
            )

    def register_single_source_validations(self) -> None:
        """
        Validate every observation the document registers, not only the
        material evidence set.

        Validating only the fourteen engine inputs meant a second source's
        observations were never aged. A filing-sourced balance-sheet series
        that stopped in 2013 read as current because nothing ever asked how old
        it was.
        """
        for ref, entry in sorted(self.refs.items()):
            if entry.kind != KIND_OBSERVATION:
                continue
            identifier = str(entry.payload.get("observation_id") or ref)
            if identifier not in self._aged_ids:
                continue
            self._register(
                validation_ref(f"{identifier}:single_source"),
                KIND_VALIDATION,
                {
                    "subject": ref,
                    "status": "STALE",
                    "reasons": [
                        "the source published this observation "
                        f"{self._stale_days.get(identifier)} days before the "
                        "context's as-of date, past the "
                        f"{self._window_for(entry)}-day freshness window for its cadence"
                    ],
                    "checked_at": entry.payload.get("retrieved_at"),
                    "value_snapshot": None,
                    "as_of": entry.payload.get("as_of"),
                    "period_start": entry.payload.get("period_start"),
                    "period_end": entry.payload.get("period_end"),
                },
            )

    def _window_for(self, entry: RefEntry) -> int:
        """
        The freshness window that applies to one observation.

        A daily market quote goes stale in a week. A periodic filing does not:
        it is inherently up to a quarter and a filing lag old between reports,
        and holding it to a daily window would mark every periodic source
        permanently stale, which is the same as not flagging anything.
        """
        if entry.payload.get("available_at_basis") in (
            DAILY_OBSERVATION_BASES
        ):
            return FRESHNESS_WINDOW_DAYS["DAILY"]
        return FRESHNESS_WINDOW_DAYS["PERIODIC_FILING"]

    def compute_freshness(self) -> None:
        """
        Two different questions, answered separately.

        *How old is this observation?* Every filing-sourced fact is years older
        than the context it sits in, because a 2024 annual report reports on
        2024. Calling that stale would flag almost the whole document and
        teach a reader to ignore the flag.

        *Is there a recent value for this metric?* That is the question a
        consumer acts on. A balance-sheet series whose newest entry is from
        2013 has no current value, and presenting its last figure as though it
        were one is the failure worth preventing.

        The per-metric recency state is the one that gates use. The per-
        observation age is reported for information.
        """
        as_of = self._as_of()
        as_of_date = parse_iso_date(as_of) if as_of else None
        if as_of_date is None:
            return

        by_metric: Dict[str, Dict[str, Any]] = {}
        ages: Dict[str, int] = {}
        checked = 0
        for ref, entry in self.refs.items():
            if entry.kind != KIND_OBSERVATION:
                continue
            identifier = str(entry.payload.get("observation_id") or ref)
            metric = str(entry.payload.get("metric") or "unknown")
            available_at = entry.payload.get("available_at")
            available_date = (
                parse_iso_date(available_at) if available_at else None
            )
            bucket = by_metric.setdefault(
                metric,
                {
                    "checked": 0,
                    "aged_observations": 0,
                    "undated_availability": 0,
                    "latest_as_of": None,
                    "latest_availability": None,
                    "aged_observation_refs": [],
                },
            )
            bucket["checked"] += 1
            checked += 1
            observed_as_of = entry.payload.get("as_of")
            if observed_as_of and (
                bucket["latest_as_of"] is None
                or str(observed_as_of) > bucket["latest_as_of"]
            ):
                bucket["latest_as_of"] = str(observed_as_of)
            if available_date is None:
                bucket["undated_availability"] += 1
                continue
            window = self._window_for(entry)
            age = (as_of_date - available_date).days
            ages[identifier] = age
            if available_at and (
                bucket["latest_availability"] is None
                or str(available_at) > bucket["latest_availability"]
            ):
                bucket["latest_availability"] = str(available_at)
            if age > window:
                self._aged_ids.add(identifier)
                self._stale_days[identifier] = age
                bucket["aged_observations"] += 1
                bucket["aged_observation_refs"].append(ref)

        for metric, bucket in by_metric.items():
            latest = bucket["latest_availability"]
            if latest is None:
                bucket["current_value_age_days"] = None
                bucket["recency"] = "UNDATED_AVAILABILITY"
            else:
                age = (as_of_date - parse_iso_date(latest)).days
                bucket["current_value_age_days"] = age
                window = FRESHNESS_WINDOW_DAYS["PERIODIC_FILING"]
                bucket["window_days"] = window
                bucket["recency"] = (
                    "CURRENT"
                    if age <= window
                    else "NO_RECENT_VALUE"
                )
            bucket["aged_observation_refs"] = sorted(
                bucket["aged_observation_refs"]
            )
            if bucket["recency"] == "NO_RECENT_VALUE":
                self._stale_metrics.add(metric)
            bucket.pop("aged_observations", None)

        self._freshness_by_metric = {
            "as_of": as_of,
            "window_days_by_cadence": FRESHNESS_WINDOW_DAYS,
            "checked": checked,
            "aged_observations": len(self._aged_ids),
            "stale_metrics": sorted(self._stale_metrics),
            "no_recent_value_for": sorted(self._stale_metrics),
            "note": (
                "An individual observation is 'aged' when the source published "
                "it before the freshness window; that is normal for a filing "
                "about an earlier period and is not by itself a defect. A "
                "metric is listed in 'stale_metrics' when its newest "
                "observation is older than the window, which means it has no "
                "current value. Both are retained; neither is substituted."
            ),
            "by_metric": {
                metric: bucket for metric, bucket in sorted(by_metric.items())
            },
        }

    def index_cross_source_subjects(self) -> None:
        """
        Map each cross-source validation to the observations it judged.

        A validation constrains only the exact observations it compared.
        Indexing them by ref is what lets a derived figure discover whether the
        numbers it actually used are among them.
        """
        self._cross_source_subjects = {}
        for metric, result in self.cross_validation.items():
            if not hasattr(result, "status"):
                continue
            name = validation_ref(f"{metric}:cross_source")
            subjects = tuple(
                ref
                for ref in (
                    f"{KIND_OBSERVATION}:{result.left_observation_id}"
                    if result.left_observation_id else None,
                    f"{KIND_OBSERVATION}:{result.right_observation_id}"
                    if result.right_observation_id else None,
                )
                if ref
            )
            self._cross_source_subjects[name] = subjects

    def _validation_state_for(
        self,
        operands: Sequence[str],
    ) -> Tuple[str, Tuple[str, ...]]:
        """
        Whether a figure's inputs were actually cross-validated.

        A validation covers an operand only when it judged that exact
        observation. Judging one trailing window and then computing on another
        leaves the computation unvalidated, and publishing a neighbouring clean
        verdict without saying so makes the unvalidated figure look
        corroborated.

        A stale input is not validated either, however clean the other side
        was: agreement about a thirteen-year-old figure says nothing about the
        figure a consumer would use today.
        """
        covered: List[str] = []
        stale_inputs: List[str] = []
        for operand in operands:
            base = _operand_base(operand)
            entry = self.refs.get(base)
            identifier = (
                str(entry.payload.get("observation_id") or base)
                if entry is not None
                else base
            )
            if identifier in self._aged_ids and (
                entry is not None
                and str(entry.payload.get("metric") or "")
                in self._stale_metrics
            ):
                stale_inputs.append(base)
                continue
            for name, subjects in self._cross_source_subjects.items():
                if base in subjects:
                    covered.append(name)
        if stale_inputs:
            return VALIDATION_CONFLICTING, tuple(sorted(set(covered)))
        if not operands:
            return VALIDATION_UNVALIDATED, ()
        if len(set(covered)) == len(operands):
            return VALIDATION_VALIDATED, tuple(sorted(set(covered)))
        if covered:
            return VALIDATION_PARTIAL, tuple(sorted(set(covered)))
        return VALIDATION_UNVALIDATED, ()

    def check_identity_cross_checks(self) -> None:
        """
        Compare a derived figure against the reported figure it should
        reconcile with, and record any breach as a conflict.

        Nothing is reconciled and nothing is corrected. The identity is a
        general property of price, share count and market capitalisation rather
        than a statement about any issuer, and a breach is reported as two
        numbers that cannot both be right on one basis.
        """
        for check in IDENTITY_CHECKS:
            derived = self.figures.get(check.derived_ref)
            if derived is None or not derived.available:
                continue
            worst: Optional[Dict[str, Any]] = None
            for ref, entry in sorted(self.refs.items()):
                if entry.kind != KIND_OBSERVATION:
                    continue
                if entry.payload.get("metric") != check.reported_metric:
                    continue
                reported = entry.payload.get("value")
                if not is_number(reported) or float(reported) == 0:
                    continue
                derived_value = float(derived.value)
                difference = abs(derived_value - float(reported))
                allowed = max(
                    check.absolute_tolerance,
                    check.relative_tolerance
                    * max(abs(derived_value), abs(float(reported))),
                )
                if difference <= allowed:
                    continue
                relative = difference / max(
                    abs(derived_value), abs(float(reported))
                )
                if worst is not None and relative <= worst["relative_difference"]:
                    continue
                derivation = self.derivations.get(check.derived_ref)
                worst = {
                    "check": check.name,
                    "statement": check.statement,
                    "status": ValidationStatus.CONFLICTING.value,
                    "derived_ref": check.derived_ref,
                    "derived_value": derived_value,
                    "derived_expression": (
                        derivation.expression if derivation else None
                    ),
                    "reported_ref": ref,
                    "reported_value": float(reported),
                    "reported_observation_id": entry.payload.get(
                        "observation_id"
                    ),
                    "reported_provider": entry.payload.get("provider"),
                    "reported_as_of": entry.payload.get("as_of"),
                    "reported_available_at": entry.payload.get("available_at"),
                    "relative_difference": relative,
                    "tolerance": {
                        "relative": check.relative_tolerance,
                        "absolute": check.absolute_tolerance,
                    },
                    "resolution": "NO_WINNER_SELECTED",
                    "explanation": (
                        "Both figures are retained unchanged. ST-EVA does "
                        "not determine which basis is correct, and choosing "
                        "one would be the failure this record exists to "
                        "prevent."
                    ),
                }
            if worst is not None:
                self._identity_conflicts.append(worst)

    def compute_series_metadata(self) -> None:
        """Per-metric series shape, and where a series jumps."""
        observations = [
            Observation(
                **{
                    field: entry.payload.get(field)
                    for field in (
                        "observation_id", "metric", "unit", "currency",
                        "currency_basis", "period_start", "period_end", "as_of",
                    )
                },
                value=entry.payload.get("value"),
                available_at=entry.payload.get("available_at"),
                available_at_basis=entry.payload.get("available_at_basis"),
                provider=entry.payload.get("provider"),
                source_type=entry.payload.get("source_type"),
                source_url=None,
                definition="",
                methodology="",
                retrieved_at=entry.payload.get("retrieved_at") or "",
                raw=None,
            )
            for entry in self.refs.values()
            if entry.kind == KIND_OBSERVATION
        ]
        self._series = series_metadata(observations)

    def register_cross_source_validations(self) -> None:
        for metric, result in self.cross_validation.items():
            if not hasattr(result, "status"):
                continue
            name = f"{metric}:cross_source"
            ref = validation_ref(name)
            payload = result.contract_dict()
            payload["independence"] = (
                (result.validation.comparison_basis or {}).get(
                    "independence"
                )
            )
            self._register(ref, KIND_VALIDATION, payload)

    # -- references -------------------------------------------------------

    def _band_status(self, band: Any) -> str:
        if not band or not safe_float((band or {}).get("median")):
            return "UNAVAILABLE"
        declared = safe_float((band or {}).get("observations"))
        if declared is None:
            return "USABLE_FOR_REFERENCE"
        if declared >= MIN_BAND_OBSERVATIONS_FOR_REFERENCE:
            return "USABLE_FOR_REFERENCE"
        return "DESCRIPTIVE_ONLY_INSUFFICIENT_OBSERVATIONS"

    def _register_reference(
        self,
        name: str,
        multiple: Optional[float],
        source_metric: Optional[str],
        source_ref: Optional[str],
        basis: str,
    ) -> str:
        """
        Register a valuation reference, and say plainly where it came from.

        This is the link 2.3-B found missing: the multiple every implied figure
        is conditional on had no provenance at all. `basis` is never inferred
        from the number, and the band the statistic came from is named even when
        that band was too thin to be a reference.
        """
        ref = reference_ref(name)
        band = getattr(self.data, f"historical_{source_metric}_band", None) if source_metric else None
        status = self._band_status(band) if source_metric else None
        declared = safe_float((band or {}).get("observations")) if band else None
        eligible = status == "USABLE_FOR_REFERENCE"

        self._register(
            ref,
            KIND_REFERENCE,
            {
                "metric": source_metric or "pe",
                "multiple": multiple,
                "basis": basis,
                "operand_field": "multiple",
                "provenance_kind": (
                    PROVENANCE_OBSERVED
                    if basis == "HISTORICAL_MEDIAN"
                    else PROVENANCE_UNAVAILABLE
                    if multiple is None
                    else PROVENANCE_CONDITIONAL
                ),
                "source_ref": source_ref,
                "source_statistic": "median" if source_metric else None,
                "source_observation_count": (
                    int(declared) if declared is not None else None
                ),
                "eligible_as_reference": eligible,
                "eligibility_rule": (
                    "a band needs at least "
                    f"{MIN_BAND_OBSERVATIONS_FOR_REFERENCE} usable observations"
                ),
                "eligibility_reason": (
                    None
                    if status is None
                    else (
                        "the band declares no observation count and is treated "
                        "as usable"
                        if declared is None
                        else f"{int(declared)} observations"
                        + (
                            " is below the required count"
                            if not eligible
                            else " meets the requirement"
                        )
                    )
                ),
                "selected_at": self.generated_at,
                "selection_method": (
                    "user_supplied_multiple"
                    if basis == "USER_SUPPLIED"
                    else "historical_pe_median"
                    if basis == "HISTORICAL_MEDIAN"
                    else "none"
                ),
                "user_overridden": basis == "USER_SUPPLIED",
            },
            operand_field="multiple",
            operand_unit=Unit.MULTIPLE.value,
        )
        self._register_figure(
            Figure(
                ref=ref,
                unit=Unit.MULTIPLE.value,
                provenance_kind=(
                    PROVENANCE_OBSERVED
                    if basis == "HISTORICAL_MEDIAN"
                    else PROVENANCE_UNAVAILABLE
                    if multiple is None
                    else PROVENANCE_CONDITIONAL
                ),
                value=multiple,
                available=multiple is not None,
            )
        )
        if multiple is None:
            self._mark_unavailable(
                ref=ref,
                reason=(
                    "no valuation reference was available: the historical band "
                    "is absent or too thin to be a reference, and none was "
                    "supplied"
                ),
                reason_kind=REASON_NO_REFERENCE,
                reason_code="REFERENCE_NOT_AVAILABLE",
                item=f"{name}_multiple",
            )
        return ref

    def register_references(self) -> Dict[str, str]:
        """
        Register the reference multiples and the named run constants.

        `horizon_years` and `trading_periods` are operands, not parameters,
        because both materially change a reported number. Burying the 252-day
        annualisation convention inside the code would be exactly the kind of
        silent financial assumption this document exists to make visible.
        """
        analysis_reference = self.analysis.get("reference") or {}
        selected_pe = safe_float(analysis_reference.get("multiple"))
        band_pe = getattr(self.data, "historical_pe_band", None)
        # A historical median must always name the band it came from, whether
        # or not the band's samples were preserved. Naming the source and
        # declaring the statistics non-recomputable are two different facts.
        source_ref = self._band_ref("pe_band") if band_pe else None

        basis = "NONE"
        if self.user_references["valuation_reference"] is not None:
            basis = "USER_SUPPLIED"
        elif selected_pe is not None:
            basis = "HISTORICAL_MEDIAN"

        # Only a historical median is sourced from the band. A user-supplied
        # multiple came from a person, and pointing at the band would be a false
        # claim about where the number came from.
        if basis != "HISTORICAL_MEDIAN":
            source_ref = None

        refs = {
            "valuation_reference": self._register_reference(
                name="valuation_reference",
                multiple=selected_pe,
                source_metric="pe",
                source_ref=source_ref,
                basis=basis,
            )
        }

        secondary = {
            "pfcf_reference": (
                "pfcf",
                self.user_references["pfcf_reference"],
                safe_float(
                    (analysis_reference.get("reference_multiples") or {}).get(
                        "pfcf"
                    )
                ),
            ),
            "ev_ebitda_reference": (
                "ev_ebitda",
                self.user_references["ev_ebitda_reference"],
                safe_float(
                    (analysis_reference.get("reference_multiples") or {}).get(
                        "ev_ebitda"
                    )
                ),
            ),
            "ps_reference": (
                "ps",
                self.user_references["ps_reference"],
                safe_float(
                    (analysis_reference.get("reference_multiples") or {}).get(
                        "ps"
                    )
                ),
            ),
        }
        for name, (metric, user_value, engine_value) in secondary.items():
            multiple = user_value if user_value is not None else engine_value
            secondary_basis = "NONE"
            if user_value is not None:
                secondary_basis = "USER_SUPPLIED"
            elif engine_value is not None:
                secondary_basis = "HISTORICAL_MEDIAN"
            refs[name] = self._register_reference(
                name=name,
                multiple=multiple,
                source_metric=metric,
                source_ref=None,
                basis=secondary_basis,
            )

        self._register_constant(
            "horizon_years",
            self.horizon_years,
            Unit.RATIO.value,
            "the horizon used for the required EPS CAGR, in years",
        )
        self._register_constant(
            "trading_periods",
            float(self.trading_periods),
            Unit.COUNT.value,
            (
                "trading days per year, the annualisation convention applied "
                "to realised volatility"
            ),
        )
        self._register_constant(
            "one",
            1.0,
            Unit.RATIO.value,
            (
                "the additive identity, used where the 2.2.3 engine writes "
                "'x / y - 1' as a ratio and a subtraction"
            ),
        )
        return refs

    def _register_constant(
        self,
        name: str,
        value: float,
        unit: str,
        meaning: str,
    ) -> None:
        ref = reference_ref(name)
        self._register(
            ref,
            KIND_REFERENCE,
            {
                "multiple": value,
                "operand_field": "multiple",
                "meaning": meaning,
                "provenance_kind": PROVENANCE_OBSERVED,
                "selected_at": self.generated_at,
            },
            operand_field="multiple",
            operand_unit=unit,
        )
        self._register_figure(
            Figure(
                ref=ref,
                unit=unit,
                provenance_kind=PROVENANCE_OBSERVED,
                value=value,
            )
        )

    # -- operand resolution ----------------------------------------------

    def _resolve_operand(self, operand_ref: str) -> Tuple[Any, Optional[str]]:
        """
        Resolve one operand to its value and unit.

        An unresolvable or unavailable operand yields `(None, None)`, and the
        caller propagates that into an unavailable figure. It never substitutes
        a number.
        """
        kind, identifier, selector = split_ref(operand_ref)
        base_ref = f"{kind}:{identifier}"
        entry = self.refs.get(base_ref)
        if entry is None:
            raise UnresolvedRefError(
                f"operand {operand_ref!r} does not resolve; the document has "
                f"no ref {base_ref!r}. Every operand must resolve."
            )
        figure = self.figures.get(base_ref)
        if figure is None or not figure.available:
            return None, None

        value: Any = figure.value
        unit = entry.operand_unit or figure.unit

        if kind == KIND_REFERENCE:
            field_name = entry.operand_field or "multiple"
            value = entry.payload.get(field_name)

        if selector is not None:
            value = self._select(value, selector, operand_ref)

        return value, unit

    def _select(self, value: Any, selector: str, operand_ref: str) -> Any:
        if isinstance(value, dict):
            if selector in value:
                return value[selector]
            raise UnresolvedRefError(
                f"operand {operand_ref!r} selects {selector!r}, which the "
                f"figure does not carry; it has {sorted(value)}"
            )
        if isinstance(value, (list, tuple)):
            if not selector.lstrip("-").isdigit():
                raise UnresolvedRefError(
                    f"operand {operand_ref!r} needs a numeric element index, "
                    f"got {selector!r}"
                )
            index = int(selector)
            resolved = index if index >= 0 else len(value) + index
            if not 0 <= resolved < len(value):
                raise UnresolvedRefError(
                    f"operand {operand_ref!r} index {selector} is outside the "
                    f"{len(value)}-element series"
                )
            return value[resolved]
        raise UnresolvedRefError(
            f"operand {operand_ref!r} cannot select from a "
            f"{type(value).__name__} value"
        )

    # -- derivations ------------------------------------------------------

    def _add_derivation(
        self,
        name: str,
        op: str,
        operands: Sequence[str],
        engine_value: Any,
        unit: str,
        expression: str,
        conditional_on: Sequence[str] = (),
        currency: Optional[str] = None,
        provenance_kind: str = PROVENANCE_DERIVED,
        extra_operation: Optional[Dict[str, Any]] = None,
        non_deterministic_reason: Optional[str] = None,
    ) -> str:
        """
        Register one derived figure, its operation, and its parity check.

        The engine's value is the authority. The registry recomputes it, and a
        disagreement raises `ParityError`, so a number can never enter the
        document that the engine did not produce and that the published formula
        does not reproduce.
        """
        ref = derived_ref(name)
        if ref in self.figures:
            return ref

        resolved: List[Any] = []
        operand_units: List[Optional[str]] = []
        operand_currencies: List[Optional[str]] = []
        missing: List[str] = []
        for operand in operands:
            value, operand_unit = self._resolve_operand(operand)
            resolved.append(value)
            operand_units.append(operand_unit)
            operand_currencies.append(self._operand_currency(operand))
            if value is None:
                missing.append(operand)

        spec = operation_registry.lookup(op)

        computed: Any = None
        refusal: Optional[str] = None
        if not missing and engine_value is not None:
            try:
                computed = evaluate(
                    op,
                    resolved,
                    operand_units,
                    (extra_operation or {}).get("parameters"),
                    operand_currencies=operand_currencies,
                )
            except CurrencyMismatchError as error:
                # The operands are denominated in different currencies, so the
                # figure is withheld rather than published. The engine's value
                # is discarded here, deliberately: it cannot be reproduced by
                # any valid arithmetic, and publishing it would assert a ratio
                # that does not exist.
                refusal = str(error)
        available = (
            engine_value is not None and not missing and refusal is None
        )
        if available:
            derived_unit = result_unit(spec, operand_units) or unit
        else:
            derived_unit = unit

        self._register_figure(
            Figure(
                ref=ref,
                unit=derived_unit,
                currency=currency,
                provenance_kind=(
                    provenance_kind if available
                    else PROVENANCE_UNAVAILABLE
                ),
                value=engine_value if available else None,
                available=available,
            )
        )
        # The derived figure appears in the address book as an identity, not as
        # a second copy of its value. The value lives in exactly one place, so
        # the two copies cannot disagree.
        self._register(
            ref,
            KIND_DERIVED,
            {
                "derivation": ref,
                "unit": derived_unit,
                "currency": currency,
                "provenance_kind": (
                    provenance_kind if available
                    else PROVENANCE_UNAVAILABLE
                ),
            },
            operand_field="value",
            operand_unit=derived_unit,
        )
        self.derivations[ref] = Derivation(
            ref=ref,
            operation={
                "op": op,
                "version": spec.version,
                "operands": list(operands),
                **({"parameters": extra_operation["parameters"]}
                   if (extra_operation or {}).get("parameters")
                   else {}),
            },
            expression=expression,
            deterministic=not non_deterministic_reason,
            non_deterministic_reason=non_deterministic_reason,
            inputs_observed_at=self._input_dates(operands),
            conditional_on=tuple(conditional_on),
            depends_on=tuple(operands),
        )
        if not available:
            operand_states = [
                ("available" if value is not None else "unavailable", value)
                for value in resolved
            ]
            classified = reason_code_for(
                operation=op,
                operand_states=operand_states,
                engine_value=engine_value if not missing else None,
                operand_refs=[_operand_base(item) for item in operands],
            ) or {}
            if refusal is not None:
                # A cross-currency refusal names the currencies itself, and
                # that is more specific than any input condition, so it keeps
                # its own reason and only borrows the machine-readable shape.
                reason = refusal
                classified = {
                    "reason_kind": "INCOMPATIBLE_CURRENCY",
                    "reason_code": "OPERAND_CURRENCIES_DIFFER",
                    "explanation": refusal,
                }
            elif missing:
                reason = classified.get("explanation", "not computable")
            else:
                reason = classified.get("explanation", "not computable")

            entry = {
                "item": name,
                "ref": ref,
                "reason": reason,
                "reason_kind": classified.get(
                    "reason_kind",
                    REASON_MISSING_INPUT if missing else REASON_NOT_AVAILABLE,
                ),
                "reason_code": classified.get("reason_code"),
                "blocks": missing,
            }
            for field_name in (
                "operand_position",
                "input_ref",
                "input_value",
                "condition",
            ):
                if classified.get(field_name) is not None:
                    entry[field_name] = classified[field_name]
            self.unavailable.append(entry)
        elif computed is not None:
            self._assert_parity(ref, computed, engine_value)
        return ref

    def _operand_currency(self, operand: str) -> Optional[str]:
        """
        The currency an operand is denominated in, read from its figure.

        Unit and currency are different axes. The unit says what kind of
        quantity a figure is; the currency says which money. A derivation that
        combines two monetary figures needs both, and the currency is the axis
        that catches a figure reported in a different currency from its peers.
        """
        base = _operand_base(operand)
        figure = self.figures.get(base)
        return figure.currency if figure is not None else None

    def _assert_parity(
        self,
        ref: str,
        computed: Any,
        engine_value: Any,
    ) -> None:
        if not is_number(computed) or not is_number(engine_value):
            raise ParityError(
                f"{ref}: the registry produced {computed!r} where the engine "
                f"produced {engine_value!r}"
            )
        difference = abs(float(computed) - float(engine_value))
        allowed = max(
            PARITY_ABSOLUTE_TOLERANCE,
            PARITY_RELATIVE_TOLERANCE
            * max(abs(float(computed)), abs(float(engine_value))),
        )
        if difference > allowed:
            raise ParityError(
                f"{ref}: the registry recomputed {computed!r} but the engine "
                f"produced {engine_value!r}; difference {difference:.6g} "
                f"exceeds {allowed:.6g}. The published formula does not "
                "reproduce the published number."
            )

    def _input_dates(self, operands: Sequence[str]) -> Tuple[str, ...]:
        dates: List[str] = []
        for operand in operands:
            kind, identifier, _ = split_ref(operand)
            entry = self.refs.get(f"{kind}:{identifier}")
            if entry is None:
                continue
            for key in ("as_of", "period_end"):
                value = entry.payload.get(key)
                if value:
                    dates.append(str(value))
                    break
        return tuple(sorted(set(dates)))

    # -- the derivation table --------------------------------------------

    def _observations_for_metric(self, metric: str) -> List[Observation]:
        """
        Every observation the document knows for a metric.

        The material observations are projected from the view on demand and are
        not stored in the view's own observation set, so both collections are
        searched, with the material set first.
        """
        found = [
            observation
            for observation in self.material_observations
            if observation.metric == metric
        ]
        found.extend(self.data.observations.for_metric(metric))
        return found

    def _obs_ref(self, metric: str) -> Optional[str]:
        """
        The ref of a material observation by metric.

        Prefers the 2.2.3 material-evidence observation, because that is the one
        the engine read. A cross-source observation shares the metric name and
        must not be substituted for it here.
        """
        for observation in self._observations_for_metric(metric):
            if not is_comparable_observation(observation):
                return observation_ref(observation.observation_id)
        for observation in self._observations_for_metric(metric):
            return observation_ref(observation.observation_id)
        return None

    def _band_ref(self, metric: str) -> Optional[str]:
        for observation in self._observations_for_metric(metric):
            return observation_ref(observation.observation_id)
        return None

    def register_derivations(self, reference_refs: Dict[str, str]) -> None:
        """
        Register every figure the engine computed, with its operation.

        The table is the whole point of the phase: a derived figure without an
        operation here would be exactly the "22.4% in a vacuum" the phase
        exists to eliminate.
        """
        observed = self.analysis.get("observed_valuation") or {}
        implied = self.analysis.get("implied_assumptions") or {}
        cross_check = self.analysis.get("consensus_cross_check") or {}

        price = self._obs_ref("price")
        current_eps = self._obs_ref("trailing_eps")
        forward_eps = self._obs_ref("forward_eps")
        consensus_eps = self._obs_ref("consensus_forward_eps")
        fcf = self._obs_ref("free_cash_flow")
        ebitda = self._obs_ref("ebitda")
        revenue = self._obs_ref("revenue")
        enterprise_value = self._obs_ref("enterprise_value")
        market_cap = self._obs_ref("market_cap")
        pe_band = self._band_ref("pe_band")
        ps_band = self._band_ref("ps_band")
        ev_band = self._band_ref("ev_ebitda_band")

        valuation_ref = reference_refs["valuation_reference"]
        pfcf_ref = reference_refs["pfcf_reference"]
        ev_ebitda_ref = reference_refs["ev_ebitda_reference"]
        ps_ref = reference_refs["ps_reference"]
        one = reference_ref("one")
        horizon = reference_ref("horizon_years")

        # Observed multiples: price over a per-share or currency input.
        for name, value, numerator, denominator, unit in (
            ("current_pe", observed.get("current_pe"), price, current_eps, Unit.MULTIPLE.value),
            ("forward_pe", observed.get("forward_pe"), price, forward_eps, Unit.MULTIPLE.value),
            (
                "consensus_forward_pe",
                observed.get("consensus_forward_pe"),
                price,
                consensus_eps,
                Unit.MULTIPLE.value,
            ),
            ("current_pfcf", observed.get("current_pfcf"), market_cap, fcf, Unit.MULTIPLE.value),
            (
                "current_ev_ebitda",
                observed.get("current_ev_ebitda"),
                enterprise_value,
                ebitda,
                Unit.MULTIPLE.value,
            ),
            ("current_ps", observed.get("current_ps"), market_cap, revenue, Unit.MULTIPLE.value),
        ):
            if numerator and denominator:
                self._add_derivation(
                    name=name,
                    op="divide",
                    operands=[numerator, denominator],
                    engine_value=value,
                    unit=unit,
                    expression=f"{numerator} / {denominator}",
                )

        # Market-implied figures. Every one is conditional on a reference, and
        # every one says so.
        conditional = (valuation_ref,)
        if price:
            self._add_derivation(
                name="implied_forward_eps",
                op="divide",
                operands=[price, valuation_ref],
                engine_value=implied.get("forward_eps_at_reference_multiple"),
                unit=Unit.PER_SHARE.value,
                expression=f"{price} / {valuation_ref}",
                conditional_on=conditional,
                currency=self.data.currency or None,
                provenance_kind=PROVENANCE_CONDITIONAL,
            )
        if price and market_cap and valuation_ref:
            self._add_derivation(
                name="consensus_price_at_median",
                op="multiply",
                operands=[consensus_eps, valuation_ref],
                engine_value=cross_check.get("price_at_historical_median_pe"),
                unit=Unit.CURRENCY.value,
                expression=f"{consensus_eps} * {valuation_ref}",
                conditional_on=conditional,
                currency=self.data.currency or None,
                provenance_kind=PROVENANCE_CONDITIONAL,
            )
            if cross_check.get("price_at_historical_median_pe") is not None:
                self._add_derivation(
                    name="consensus_price_ratio",
                    op="ratio",
                    operands=[derived_ref("consensus_price_at_median"), price],
                    engine_value=(
                        cross_check.get(
                            "price_at_historical_median_pe"
                        )
                        / self.data.price
                    ),
                    unit=Unit.RATIO.value,
                    expression=(
                        f"{derived_ref('consensus_price_at_median')} / {price}"
                    ),
                    conditional_on=conditional,
                    provenance_kind=PROVENANCE_CONDITIONAL,
                )
                self._add_derivation(
                    name="consensus_price_gap",
                    op="subtract",
                    operands=[derived_ref("consensus_price_ratio"), one],
                    engine_value=cross_check.get(
                        "price_gap_vs_historical_median_on_consensus_eps"
                    ),
                    unit=Unit.RATIO.value,
                    expression=(
                        f"{derived_ref('consensus_price_ratio')} - {one}"
                    ),
                    conditional_on=conditional,
                    provenance_kind=PROVENANCE_CONDITIONAL,
                )

        implied_eps_ref = derived_ref("implied_forward_eps")
        if implied_eps_ref in self.figures and current_eps:
            # The engine's expression is implied / consensus - 1, so the
            # intermediate is implied / consensus and the subtraction follows.
            implied_eps = safe_float(
                implied.get("forward_eps_at_reference_multiple")
            )
            consensus_value = safe_float(
                (self.analysis.get("source_inputs") or {}).get(
                    "consensus_forward_eps"
                )
            )
            if (
                implied_eps is not None
                and consensus_value is not None
                and consensus_value > 0
            ):
                self._add_derivation(
                    name="implied_to_consensus",
                    op="divide",
                    operands=[
                        derived_ref("implied_forward_eps"),
                        consensus_eps,
                    ],
                    engine_value=implied_eps / consensus_value,
                    unit=Unit.RATIO.value,
                    expression=(
                        f"{derived_ref('implied_forward_eps')} / {consensus_eps}"
                    ),
                    conditional_on=conditional,
                    provenance_kind=PROVENANCE_CONDITIONAL,
                )
                self._add_derivation(
                    name="eps_gap_vs_consensus",
                    op="subtract",
                    operands=[derived_ref("implied_to_consensus"), one],
                    engine_value=implied.get("eps_gap_vs_consensus"),
                    unit=Unit.RATIO.value,
                    expression=(
                        f"{derived_ref('implied_to_consensus')} - {one}"
                    ),
                    conditional_on=conditional,
                    provenance_kind=PROVENANCE_CONDITIONAL,
                )

            self._add_derivation(
                name="required_eps_cagr",
                op="compound_growth_rate",
                operands=[
                    derived_ref("implied_forward_eps"),
                    current_eps,
                    horizon,
                ],
                engine_value=implied.get(
                    "required_eps_cagr_from_current_eps"
                ),
                unit=Unit.RATIO.value,
                expression=(
                    f"({derived_ref('implied_forward_eps')} / {current_eps})"
                    f" ** (1 / {horizon}) - 1"
                ),
                conditional_on=conditional,
                provenance_kind=PROVENANCE_CONDITIONAL,
            )

        for name, value, numerator, reference, unit in (
            (
                "implied_fcf",
                implied.get("fcf_at_reference_multiple"),
                market_cap,
                pfcf_ref,
                Unit.CURRENCY.value,
            ),
            (
                "implied_ebitda",
                implied.get("ebitda_at_reference_multiple"),
                enterprise_value,
                ev_ebitda_ref,
                Unit.CURRENCY.value,
            ),
            (
                "implied_revenue",
                implied.get("revenue_at_reference_multiple"),
                market_cap,
                ps_ref,
                Unit.CURRENCY.value,
            ),
        ):
            if numerator and reference:
                self._add_derivation(
                    name=name,
                    op="divide",
                    operands=[numerator, reference],
                    engine_value=value,
                    unit=unit,
                    expression=f"{numerator} / {reference}",
                    conditional_on=(reference,),
                    currency=self.data.currency or None,
                    provenance_kind=PROVENANCE_CONDITIONAL,
                )

        # implied_net_margin decomposes into three divisions, which is one more
        # hop than the engine needs but keeps every operand checkable.
        implied_eps_ref = derived_ref("implied_forward_eps")
        implied_revenue_ref = derived_ref("implied_revenue")
        if price and market_cap and implied_eps_ref in self.figures:
            self._add_derivation(
                name="implied_shares",
                op="shares_from_market_cap",
                operands=[market_cap, price],
                engine_value=(
                    safe_float(
                        (self.analysis.get("fundamental_snapshot") or {}).get(
                            "current_market_cap"
                        )
                    )
                    / self.data.price
                )
                if safe_float(
                    (self.analysis.get("fundamental_snapshot") or {}).get(
                        "current_market_cap"
                    )
                )
                and self.data.price
                else None,
                unit=Unit.COUNT.value,
                expression=f"{market_cap} / {price}",
            )
        if implied_revenue_ref in self.figures and derived_ref(
            "implied_shares"
        ) in self.figures:
            implied_revenue_value = safe_float(implied.get("revenue_at_reference_multiple"))
            implied_shares_value = safe_float(
                (self.analysis.get("fundamental_snapshot") or {}).get(
                    "current_market_cap"
                )
            ) / self.data.price if (
                safe_float(
                    (self.analysis.get("fundamental_snapshot") or {}).get(
                        "current_market_cap"
                    )
                )
                and self.data.price
            ) else None
            if (
                implied_revenue_value is not None
                and implied_shares_value
            ):
                self._add_derivation(
                    name="implied_revenue_per_share",
                    op="amount_per_share",
                    operands=[implied_revenue_ref, derived_ref("implied_shares")],
                    engine_value=implied_revenue_value / implied_shares_value,
                    unit=Unit.CURRENCY.value,
                    expression=(
                        f"{implied_revenue_ref} / {derived_ref('implied_shares')}"
                    ),
                )
            implied_eps_value = safe_float(
                implied.get("forward_eps_at_reference_multiple")
            )
            per_share_value = (
                implied_revenue_value / implied_shares_value
                if (implied_revenue_value is not None and implied_shares_value)
                else None
            )
            if implied_eps_value is not None and per_share_value:
                self._add_derivation(
                    name="implied_net_margin",
                    op="divide",
                    operands=[implied_eps_ref, derived_ref("implied_revenue_per_share")],
                    engine_value=implied.get("implied_net_margin"),
                    unit=Unit.RATIO.value,
                    expression=(
                        f"{implied_eps_ref} / "
                        f"{derived_ref('implied_revenue_per_share')}"
                    ),
                )

        # Percentile positions. These need a usable band, which is a policy
        # decision rather than arithmetic, so the check happens here and the
        # figure is marked unavailable with an explicit reason.
        for name, value, numerator_ref, band_ref in (
            (
                "pe_percentile",
                observed.get("approx_historical_pe_percentile"),
                valuation_ref,
                pe_band,
            ),
            (
                "ps_percentile",
                observed.get("approx_historical_ps_percentile"),
                derived_ref("current_ps"),
                ps_band,
            ),
            (
                "ev_ebitda_percentile",
                observed.get("approx_historical_ev_ebitda_percentile"),
                derived_ref("current_ev_ebitda"),
                ev_band,
            ),
        ):
            if not (numerator_ref and band_ref):
                continue
            # The P/E percentile locates the *chosen reference* within the
            # band, so it inherits that reference's conditionality. The other
            # two locate an observed multiple and are not conditional.
            percentile_conditional = (
                conditional if name == "pe_percentile" else ()
            )
            percentile_kind = (
                PROVENANCE_CONDITIONAL
                if name == "pe_percentile"
                else PROVENANCE_DERIVED
            )
            status = self._band_status(
                getattr(
                    self.data,
                    {
                        "pe_percentile": "historical_pe_band",
                        "ps_percentile": "historical_ps_band",
                        "ev_ebitda_percentile": "historical_ev_ebitda_band",
                    }[name],
                    None,
                )
            )
            if status != "USABLE_FOR_REFERENCE" or value is None:
                if value is None and status != "USABLE_FOR_REFERENCE":
                    self._add_derivation(
                        name=name,
                        op="percentile_position",
                        operands=[numerator_ref, band_ref],
                        engine_value=None,
                        unit=Unit.RATIO.value,
                        expression=(
                            f"percentile_position({numerator_ref}, {band_ref})"
                        ),
                        conditional_on=percentile_conditional,
                        provenance_kind=percentile_kind,
                    )
                    entry = next(
                        item
                        for item in self.unavailable
                        if item["ref"] == derived_ref(name)
                    )
                    entry["reason"] = (
                        f"the band is not usable as a reference ({status}), so "
                        "no percentile position is read from it"
                    )
                    entry["reason_kind"] = REASON_INSUFFICIENT_OBSERVATIONS
                    # The code moves with the kind. The input observation is
                    # present and usable; the *series* behind it is too thin,
                    # and leaving INPUT_OBSERVATION_UNAVAILABLE here would say
                    # the opposite.
                    entry["reason_code"] = "SERIES_TOO_THIN"
                continue
            self._add_derivation(
                name=name,
                op="percentile_position",
                operands=[numerator_ref, band_ref],
                engine_value=value,
                unit=Unit.RATIO.value,
                expression=f"percentile_position({numerator_ref}, {band_ref})",
                conditional_on=percentile_conditional,
                provenance_kind=percentile_kind,
            )

        self._register_price_and_volume_metrics()

    def _register_price_and_volume_metrics(self) -> None:
        """
        Register the price and volume statistics.

        Each one is decomposed into registry operations over the preserved
        series, so a consumer can recompute a return from two elements of the
        price history rather than trusting a stored percentage.
        """
        metrics = self.metrics or {}
        price_history_ref = observation_ref("obs-price-history-001")
        volume_history_ref = observation_ref("obs-volume-history-001")
        trading_periods = reference_ref("trading_periods")

        if price_history_ref not in self.refs:
            return

        for name, offset in (
            ("return_1d", 2),
            ("return_5d", 6),
            ("return_20d", 21),
            ("return_60d", 61),
        ):
            self._add_derivation(
                name=name,
                op="price_return",
                operands=[
                    f"{price_history_ref}#-1",
                    f"{price_history_ref}#-{offset}",
                ],
                engine_value=metrics.get(name),
                unit=Unit.RATIO.value,
                expression=(
                    f"{price_history_ref}#-1 / "
                    f"{price_history_ref}#-{offset} - 1"
                ),
            )

        log_returns_ref = derived_ref("log_returns")
        self._add_derivation(
            name="log_returns",
            op="log_returns",
            operands=[price_history_ref],
            engine_value=None,
            unit=Unit.RATIO.value,
            expression=(
                "the per-period log returns of the observed price series, kept "
                "as an intermediate so the volatility below is checkable"
            ),
        )
        # The intermediate is a list, not a headline figure: it is registered
        # as a figure so it can be an operand, but the stored value comes from
        # the registry so it cannot drift from the formula.
        if log_returns_ref in self.figures:
            computed = evaluate(
                "log_returns", [self.data.price_history], [Unit.CURRENCY.value]
            )
            self.figures[log_returns_ref] = Figure(
                ref=log_returns_ref,
                unit=Unit.RATIO.value,
                provenance_kind=PROVENANCE_DERIVED,
                value=computed,
                available=True,
            )

        volatility_ref = derived_ref("realized_volatility")
        self._add_derivation(
            name="daily_volatility",
            op="sample_standard_deviation",
            operands=[log_returns_ref],
            engine_value=None,
            unit=Unit.RATIO.value,
            expression=f"the sample standard deviation of {log_returns_ref}",
        )
        if derived_ref("daily_volatility") in self.figures:
            computed = evaluate(
                "sample_standard_deviation",
                [self.figures[log_returns_ref].value],
                [Unit.RATIO.value],
            )
            self.figures[derived_ref("daily_volatility")] = Figure(
                ref=derived_ref("daily_volatility"),
                unit=Unit.RATIO.value,
                provenance_kind=PROVENANCE_DERIVED,
                value=computed,
                available=True,
            )

        self._add_derivation(
            name="realized_volatility",
            op="annualized_volatility",
            operands=[derived_ref("daily_volatility"), trading_periods],
            engine_value=metrics.get("realized_volatility_annualized"),
            unit=Unit.RATIO.value,
            expression=(
                f"{derived_ref('daily_volatility')} * sqrt({trading_periods})"
            ),
        )

        if volume_history_ref in self.refs:
            self._add_derivation(
                name="average_volume",
                op="mean",
                operands=[volume_history_ref],
                engine_value=metrics.get("average_volume"),
                unit=Unit.COUNT.value,
                expression=f"mean({volume_history_ref})",
            )
            if derived_ref("average_volume") in self.figures:
                self._add_derivation(
                    name="latest_volume_vs_average",
                    op="deviation_from_average",
                    operands=[
                        f"{volume_history_ref}#-1",
                        derived_ref("average_volume"),
                    ],
                    engine_value=metrics.get("latest_volume_vs_average"),
                    unit=Unit.RATIO.value,
                    expression=(
                        f"{volume_history_ref}#-1 / "
                        f"{derived_ref('average_volume')} - 1"
                    ),
                )

    def register_reference_derivations(self) -> None:
        """
        Give the valuation reference a derivation record of its own.

        It is recomputable when the band's samples are preserved. It is not when
        they are not, and the record says so rather than claiming a check that
        cannot be run.
        """
        ref = reference_ref("valuation_reference")
        entry = self.refs.get(ref)
        if entry is None or entry.payload.get("basis") != "HISTORICAL_MEDIAN":
            return
        band_ref = entry.payload.get("source_ref")
        if band_ref is None:
            return
        band_entry = self.refs.get(band_ref)
        raw = (band_entry.payload or {}).get("raw") if band_entry else None
        samples = (raw or {}).get("samples") if isinstance(raw, dict) else None
        if not samples:
            self.derivations[ref] = Derivation(
                ref=ref,
                operation={
                    "op": "percentile",
                    "version": operation_registry.REGISTRY_VERSION,
                    "operands": [f"{band_ref}#samples"],
                    "parameters": {"fraction": 0.5},
                },
                expression=f"median of the {band_ref} samples",
                deterministic=False,
                non_deterministic_reason=(
                    "the band arrived without preserved samples; its statistics "
                    "are themselves sourced, not recomputed here"
                ),
                depends_on=(band_ref,),
            )
            return
        self.derivations[ref] = Derivation(
            ref=ref,
            operation={
                "op": "percentile",
                "version": operation_registry.REGISTRY_VERSION,
                "operands": [f"{band_ref}#samples"],
                "parameters": {"fraction": 0.5},
            },
            expression=f"median of the {band_ref} samples",
            deterministic=True,
            depends_on=(band_ref,),
        )

    # -- document assembly ------------------------------------------------

    def _link_blocks(self) -> None:
        """
        Record which figures each missing input blocks.

        Without this a consumer can see that something is missing but not what
        it cost, and the answer to "why is this null?" requires reading code.
        """
        dependents: Dict[str, List[str]] = {}
        for derivation in self.derivations.values():
            for operand in derivation.depends_on:
                kind, identifier, _ = split_ref(operand)
                base = f"{kind}:{identifier}"
                dependents.setdefault(base, [])
                if derivation.ref not in dependents[base]:
                    dependents[base].append(derivation.ref)
        for entry in self.unavailable:
            if not entry.get("ref"):
                continue
            for dependent in dependents.get(entry["ref"], ()):
                if dependent not in entry["blocks"]:
                    entry["blocks"].append(dependent)

    def _as_of(self) -> Optional[str]:
        return getattr(self.data, "price_date", None)

    def _knowledge_cutoff(self) -> Optional[str]:
        """
        The latest moment any included observation became knowable.

        Computed, not declared. This is the boundary of the document's
        knowledge, and it is what makes the context replay-safe: a consumer can
        say this document knows nothing that became public after this instant.
        """
        latest: Optional[str] = None
        for entry in self.refs.values():
            if entry.kind != KIND_OBSERVATION:
                continue
            available_at = entry.payload.get("available_at")
            if available_at and (latest is None or str(available_at) > latest):
                latest = str(available_at)
        return latest

    def _data_quality(self) -> Dict[str, Any]:
        """
        Counts and statuses. Never a grade.

        A single number standing in for "how good is this data" is an
        interpretation, it invites comparison between assets that were never
        compared, and it hides which specific weakness is present.
        """
        available = 0
        unavailable = 0
        for ref, figure in self.figures.items():
            if split_ref(ref)[0] == KIND_EVIDENCE:
                if figure.available:
                    available += 1
                else:
                    unavailable += 1

        cross_source: Dict[str, int] = {}
        for result in self.cross_validation.values():
            if not hasattr(result, "status"):
                continue
            key = result.status.value
            cross_source[key] = cross_source.get(key, 0) + 1

        band_eligibility = {}
        for metric in ("pe_band", "ps_band", "pfcf_band", "ev_ebitda_band"):
            band_eligibility[metric.replace("_band", "")] = self._band_status(
                getattr(self.data, f"historical_{metric}", None)
            )

        return {
            "evidence_coverage": {
                "available": available,
                "unavailable": unavailable,
                "total": available + unavailable,
            },
            "cross_source": cross_source,
            "acquisition_errors": list(
                getattr(self.data, "errors", []) or []
            ),
            "consensus_forward_eps_period": getattr(
                self.data, "consensus_forward_eps_period", None
            ),
            "band_eligibility": band_eligibility,
            "freshness": self._freshness_by_metric,
            "identity_conflicts": list(self._identity_conflicts),
            "series": self._series,
        }

    def _glossary(self) -> Dict[str, Any]:
        """
        Metric definitions and units, so a consumer that has never seen ST-EVA
        can read a number and know what it is a number of.
        """
        from data_contract import METRIC_DEFINITIONS

        return {
            metric: {
                "definition": METRIC_DEFINITIONS.get(metric),
                "unit": METRIC_UNITS.get(metric),
            }
            for metric in sorted(set(METRIC_UNITS) & set(METRIC_DEFINITIONS))
        }

    SCOPE = {
        "provides": [
            "observed values with per-metric provenance",
            "cross-source validation verdicts with their tolerance and basis",
            "deterministic derivations traceable to raw observations",
            "the multiple every implied figure is conditional on",
            "an explicit list of what could not be established, and why",
        ],
        "does_not_provide": [
            "an investment rating, recommendation, or buy/sell/hold view",
            "a price target or any forward price",
            "a probability, likelihood, or confidence for any outcome",
            "a quality score, ranking, or grade of the data or the asset",
            "a comparison against peers, sectors, or other assets",
            "a claim that any value is cheap, expensive, or mispriced",
            "a claim that either data source is authoritative",
            "a forecast; every implied figure is conditional on a stated "
            "reference",
        ],
        "authority_note": (
            "Neither source is treated as truth. A CONSISTENT verdict means two "
            "comparable figures agree within a declared tolerance; it does not "
            "mean the figure is verified, and independence of the sources is "
            "declared separately."
        ),
    }

    def _limitations(self) -> List[str]:
        """
        The 2.2.3 standing limitations, plus the conditions that actually
        applied in this run.

        A static list of caveats is weak: it says the same thing whether the
        reference was observed from a filing or typed by a person. The
        run-specific conditions are the ones a consumer actually needs.
        """
        limitations = [
            "This is reverse valuation, not a price target.",
            "Implied earnings/growth are conditional on the selected multiple.",
            "Missing financial data is not estimated.",
        ]
        for name in (
            "valuation_reference",
            "pfcf_reference",
            "ev_ebitda_reference",
            "ps_reference",
        ):
            entry = self.refs.get(reference_ref(name))
            if entry is None:
                continue
            basis = entry.payload.get("basis")
            if basis == "USER_SUPPLIED":
                limitations.append(
                    f"{name} was supplied on the command line, not observed "
                    "from a source; every figure conditional on it inherits "
                    "that assumption."
                )
            elif basis == "HISTORICAL_MEDIAN" and not entry.payload.get(
                "eligible_as_reference"
            ):
                limitations.append(
                    f"{name} came from a band with "
                    f"{entry.payload.get('source_observation_count')} "
                    "observations, below the required count; it is "
                    "descriptive only."
                )
            elif basis == "NONE":
                limitations.append(
                    f"{name} was unavailable, so every figure conditional on "
                    "it is absent rather than estimated."
                )
        non_recomputable = [
            derivation.ref
            for derivation in self.derivations.values()
            if not derivation.deterministic
        ]
        if non_recomputable:
            limitations.append(
                "the following figures carry a derivation that cannot be "
                "recomputed from this document: "
                + ", ".join(sorted(non_recomputable))
            )
        return limitations

    def build(self) -> Dict[str, Any]:
        """Assemble the document."""
        self.register_observations(self.material_observations)
        self.register_observations(self.extra_observations)
        self.register_observations(
            observation
            for observation in (
                self.data.observations.get(identifier)
                for identifier in self.data.observations.ids()
            )
            if observation is not None and is_comparable_observation(observation)
        )
        self.register_evidence()
        self.compute_freshness()
        self.register_single_source_validations()
        self.register_cross_source_validations()
        self.index_cross_source_subjects()
        reference_refs = self.register_references()
        self.register_derivations(reference_refs)
        self.register_reference_derivations()
        self.compute_series_metadata()
        self.check_identity_cross_checks()
        self._link_blocks()

        document: Dict[str, Any] = {
            "context_schema_version": CONTEXT_SCHEMA_VERSION,
            "min_reader_version": MIN_READER_VERSION,
            "built_from": {
                "legacy_snapshot_schema_version": LEGACY_SNAPSHOT_SCHEMA_VERSION,
                "contract_version": CONTRACT_VERSION,
                "cross_source_version": CROSS_SOURCE_VERSION,
            },
            "context_id": "",
            "supersedes": self.supersedes,
            "asset": self._asset(),
            "as_of": self._as_of(),
            "generated_at": self.generated_at,
            "knowledge_cutoff": self._knowledge_cutoff(),
            "scope": self.SCOPE,
            "glossary": self._glossary(),
            "observed": self._observed_section(),
            "validated_evidence": self._validated_section(),
            "derived": self._derived_section(),
            "valuation_reference": self.refs[
                reference_refs["valuation_reference"]
            ].contract_dict(),
            "market_implied": self._implied_section(),
            "data_quality": self._data_quality(),
            "unavailable": self.unavailable,
            "limitations": self._limitations(),
            "provenance": {
                "refs": {
                    ref: entry.contract_dict()
                    for ref, entry in sorted(self.refs.items())
                },
                "derivations": {
                    ref: derivation.contract_dict()
                    for ref, derivation in sorted(self.derivations.items())
                },
                "operation_registry": registry_contract(),
            },
        }
        document["context_id"] = compute_content_hash(document)
        return document

    def _asset(self) -> Dict[str, Any]:
        identifiers: Dict[str, Any] = {
            "ticker": getattr(self.data, "ticker", None),
        }
        if self.cik:
            identifiers["cik"] = self.cik
        company = getattr(self.data, "company_name", None)
        if self.sec_entity_name:
            identifiers["sec_entity_name"] = self.sec_entity_name
        return {
            "ticker": getattr(self.data, "ticker", None),
            "company_name": company,
            "exchange": getattr(self.data, "exchange", None),
            "currency": getattr(self.data, "currency", None),
            "identifiers": identifiers,
        }

    def _observed_section(self) -> Dict[str, Any]:
        """
        What the sources reported, keyed by metric and then by provider.

        A list per metric, never a single value: 2.3-B proved two sources may
        report the same metric with different values, and collapsing that into
        one field would destroy the finding.
        """
        by_metric: Dict[str, List[Dict[str, Any]]] = {}
        for ref, entry in self.refs.items():
            if entry.kind != KIND_OBSERVATION:
                continue
            figure = self.figures.get(ref)
            if figure is None:
                continue
            provider = entry.payload.get("provider")
            by_metric.setdefault(
                entry.payload.get("metric") or "unknown", []
            ).append(
                {
                    "provider": provider,
                    "source_type": entry.payload.get("source_type"),
                    # The security, share, price and reporting basis a source
                    # stated, so a consumer cannot divide a price by a count
                    # of a different security.
                    "basis": entry.payload.get("basis"),
                    "figure": figure.contract_dict(),
                }
            )
        return {
            metric: sorted(
                entries,
                key=lambda item: (
                    str(item.get("provider")),
                    str((item.get("figure") or {}).get("ref")),
                ),
            )
            for metric, entries in sorted(by_metric.items())
        }

    def _validated_section(self) -> Dict[str, Any]:
        section: Dict[str, Any] = {}
        for metric, result in self.cross_validation.items():
            if not hasattr(result, "status"):
                continue
            basis = result.validation.comparison_basis or {}
            section[metric] = {
                "status": result.status.value,
                "comparable": result.comparable,
                "vendor_ref": (
                    f"{KIND_OBSERVATION}:{result.left_observation_id}"
                    if result.left_observation_id
                    else None
                ),
                "filing_ref": (
                    f"{KIND_OBSERVATION}:{result.right_observation_id}"
                    if result.right_observation_id
                    else None
                ),
                "independence": basis.get("independence"),
                "tolerance": result.validation.tolerance,
                "comparison_basis": basis,
                "explanation": result.validation.explanation,
                "references": list(result.validation.references),
            }
        return section

    def _state_flags_for(
        self,
        operands: Sequence[str],
        stale_metrics: Sequence[str],
    ) -> List[Dict[str, Any]]:
        """
        What a reader must know about a figure's inputs, stated on the figure.

        The freshness and validation sections already hold this. Repeating all
        of it on every figure would bloat the document and create two places
        for the same fact to disagree. What goes here are pointers to the
        specific ref that is affected, so a reader who has the figure can reach
        the reason without a second lookup — and a reader who only has the
        figure is not misled into treating it as current.
        """
        flags: List[Dict[str, Any]] = []
        for operand in operands:
            base = _operand_base(operand)
            entry = self.refs.get(base)
            if entry is None:
                continue
            metric = str(entry.payload.get("metric") or "")
            if metric and metric in stale_metrics:
                flags.append(
                    {
                        "kind": "STALE_INPUT",
                        "ref": base,
                        "metric": metric,
                        "detail": (
                            "this input's metric has no observation inside its "
                            "source cadence's freshness window"
                        ),
                        "see": "data_quality.freshness.by_metric",
                    }
                )
            if entry.kind == KIND_OBSERVATION and not entry.payload.get(
                "available_at"
            ):
                flags.append(
                    {
                        "kind": "UNDATED_INPUT",
                        "ref": base,
                        "detail": (
                            "this input's source declared no publication time, "
                            "so its recency cannot be established"
                        ),
                        "see": "data_quality.freshness.by_metric",
                    }
                )
        if not operands:
            return flags
        covered, _refs = self._validation_state_for(operands)
        if covered == VALIDATION_UNVALIDATED and any(
            _operand_base(operand).startswith(f"{KIND_OBSERVATION}:")
            for operand in operands
        ):
            flags.append(
                {
                    "kind": "UNVALIDATED_INPUTS",
                    "count": len(operands),
                    "detail": (
                        "no cross-source check judged these inputs; a clean "
                        "verdict on a different observation of the same metric "
                        "is not a validation of these"
                    ),
                    "see": "provenance.refs and validated_evidence",
                }
            )
        return flags

    def _derived_section(self) -> Dict[str, Any]:
        section: Dict[str, Any] = {}
        stale_metrics = set(self._stale_metrics)
        for ref, figure in sorted(self.figures.items()):
            if split_ref(ref)[0] != KIND_DERIVED:
                continue
            entry: Dict[str, Any] = {"figure": figure.contract_dict()}
            derivation = self.derivations.get(ref)
            if derivation is not None:
                entry["derivation_ref"] = ref
            # Whether this figure's inputs were actually cross-validated. A
            # clean verdict on a neighbouring window is not a validation of
            # this figure, and the state says which of the two applies.
            state, refs = self._validation_state_for(
                derivation.depends_on if derivation is not None else ()
            )
            entry["validation_state"] = state
            entry["validation_refs"] = list(refs)
            flags = self._state_flags_for(
                derivation.depends_on if derivation is not None else (),
                sorted(stale_metrics),
            )
            if flags:
                entry["state_flags"] = flags
            if not figure.available:
                entry["provenance_kind"] = PROVENANCE_UNAVAILABLE
            section[split_ref(ref)[1]] = entry
        return section

    def _implied_section(self) -> Dict[str, Any]:
        """
        What the price requires, with the condition stated on every figure.

        `conditional_statement` is required and non-optional: the 2.2.3 engine
        already emits this sentence, and 2.3-C promotes it from a field inside
        `valuation_reference` to a property of the whole implied block, because
        it qualifies every figure in it.
        """
        reference = self.analysis.get("reference") or {}
        implied_names = (
            "implied_forward_eps",
            "eps_gap_vs_consensus",
            "required_eps_cagr",
            "implied_fcf",
            "implied_ebitda",
            "implied_revenue",
            "implied_net_margin",
        )
        figures: Dict[str, Any] = {}
        for name in implied_names:
            ref = derived_ref(name)
            figure = self.figures.get(ref)
            if figure is None:
                continue
            derivation = self.derivations.get(ref)
            figures[name] = {
                "ref": ref,
                "figure": figure.contract_dict(),
                "conditional_on": list(
                    derivation.conditional_on if derivation else ()
                ),
                "derivation_ref": ref if derivation else None,
                "validation_state": self._validation_state_for(
                    derivation.depends_on if derivation is not None else ()
                )[0],
            }
        return {
            "figures": figures,
            "conditional_statement": reference.get(
                "conditional_statement",
                "Implied fundamentals are conditional on the selected "
                "valuation multiple. Price alone does not identify a unique "
                "fundamental path.",
            ),
            "min_observations_for_reference": reference.get(
                "min_observations_for_reference",
                MIN_BAND_OBSERVATIONS_FOR_REFERENCE,
            ),
        }

    # -- self-validation -------------------------------------------------

    def validate(self, document: Dict[str, Any]) -> None:
        """
        Check the document against its own rules.

        Every failure here is a defect in the document, not in the consumer, so
        the build raises rather than emitting something a consumer has to
        discover later.
        """
        check_references_resolve(document)
        check_graph_acyclic(document)
        check_no_unavailable_value(document)
        check_conditional_figures_are_conditioned(document)
        check_data_quality_has_no_grade(document)
        check_no_verdict_vocabulary(document)
        check_knowledge_cutoff(document)
        check_derivations_declare_reasons(document)
        check_operations_are_registered(document)


# Fields that record *when this process asked* rather than what it learned.
# They are excluded from the content hash, because a context's identity is a
# function of its knowledge, not of when the file was written.
#
# The list grew when 2.4 replayed a context built at a different moment and
# found it would not compare. Stripping only `generated_at` would leave the
# identity unstable, which is how a "deterministic" guarantee turns out to be
# untested. `selected_at` is the same class: when the reference was selected.
VOLATILE_FIELDS = (
    "generated_at",
    "retrieved_at",
    "checked_at",
    "selected_at",
)


def _strip_volatile(node: Any) -> Any:
    """Deep-copy the payload without the when-we-asked fields."""
    if isinstance(node, dict):
        return {
            key: _strip_volatile(value)
            for key, value in node.items()
            if key not in VOLATILE_FIELDS
        }
    if isinstance(node, list):
        return [_strip_volatile(item) for item in node]
    return node


def compute_content_hash(document: Dict[str, Any]) -> str:
    """
    A stable identity for the document's knowledge.

    If two builds from the same inputs produce different ids, the build is
    non-deterministic, and that is a defect rather than a new context.
    """
    payload = {
        key: value
        for key, value in document.items()
        if key not in ("context_id",) + VOLATILE_FIELDS
    }
    encoded = json.dumps(
        _strip_volatile(payload),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return "ctx_" + hashlib.sha256(encoded).hexdigest()[:32]


# ---------------------------------------------------------------------------
# Validation linkage, identity cross-checks, and series metadata
# ---------------------------------------------------------------------------

VALIDATION_VALIDATED = "VALIDATED"
VALIDATION_UNVALIDATED = "UNVALIDATED"
VALIDATION_PARTIAL = "PARTIALLY_VALIDATED"
VALIDATION_CONFLICTING = "CONFLICTING"

# Freshness is per source cadence, not one global window. A daily market quote
# is stale in a week; a quarterly filing is inherently up to a quarter and a
# filing lag old between reports, and applying a 7-day window to one would mark
# every periodic source permanently stale and teach a reader to ignore the flag.
FRESHNESS_WINDOW_DAYS: Dict[str, int] = {
    "DAILY": 7,
    "PERIODIC_FILING": 120,
}

DAILY_OBSERVATION_BASES = (
    AvailabilityBasis.OBSERVATION_INSTANT.value,
)

# A period-over-period move larger than this relative to the prior value is a
# discontinuity worth surfacing. It says nothing about *why*, which ST-EVA
# cannot establish from the sources it holds.
DISCONTINUITY_RELATIVE_THRESHOLD = 0.5

NOT_EXPLAINED = "NOT_EXPLAINED_BY_ST_EVA"

# A series is comparable only when every point in it shares a series key. Where
# a metric's points fall into more than one key they are not a single line, and
# the Context says so instead of differencing across the gap.
SERIES_COMPARABLE = "COMPARABLE"
NOT_COMPARABLE = "NOT_COMPARABLE"

QUARTER_MIN_DAYS = 60
QUARTER_MAX_DAYS = 130
YEAR_MIN_DAYS = 330
YEAR_MAX_DAYS = 400

NEGATIVE_INPUT = "NEGATIVE_INPUT"
NON_POSITIVE_DENOMINATOR = "NON_POSITIVE_DENOMINATOR"
NON_POSITIVE_NUMERATOR = "NON_POSITIVE_NUMERATOR"

# Refusal vocabulary. Every refusal carries a code from these closed sets, so
# a consumer can branch on it rather than reading prose. The prose is kept
# alongside for a human, and is never the only description.
REASON_KINDS: Tuple[str, ...] = (
    REASON_NOT_REPORTED,
    REASON_MISSING_INPUT,
    REASON_NO_REFERENCE,
    REASON_INSUFFICIENT_OBSERVATIONS,
    "INCOMPATIBLE_CURRENCY",
    NEGATIVE_INPUT,
    REASON_NOT_AVAILABLE,
)

REASON_CODES: Tuple[str, ...] = (
    "SOURCE_DID_NOT_REPORT",
    "INPUT_OBSERVATION_UNAVAILABLE",
    "REFERENCE_NOT_AVAILABLE",
    "SERIES_TOO_THIN",
    "OPERAND_CURRENCIES_DIFFER",
    NON_POSITIVE_DENOMINATOR,
    NON_POSITIVE_NUMERATOR,
    "ENGINE_PRODUCED_NO_VALUE",
)

# Operations whose second operand is a scale-like quantity that must be
# strictly positive for the ratio to mean anything. A ratio over a negative
# figure is not a multiple; it is a sign with no interpretation.
_POSITIVE_DENOMINATOR_OPERATIONS = frozenset(
    {"divide", "ratio", "amount_per_share", "shares_from_market_cap",
     "price_return", "deviation_from_average"}
)


def reason_code_for(
    operation: str,
    operand_states: Sequence[Tuple[str, Optional[float]]],
    engine_value: Any = None,
    operand_refs: Sequence[str] = (),
) -> Optional[Dict[str, Any]]:
    """
    Classify why a derived figure is absent, as machine-readable fields.

    Returns None when the engine produced a value, because there is then nothing
    to explain. Otherwise names the condition, the operand responsible, and the
    value that caused it.

    The order matters: a missing input is reported as missing even when
    another operand is also non-positive, because a missing input is the
    earlier and more actionable fact.
    """
    if engine_value is not None:
        return None

    states = list(operand_states)
    refs = list(operand_refs)

    def describe(index: int) -> str:
        ref = refs[index] if index < len(refs) else f"operand {index}"
        return f"operand {index} ({ref})"

    for index, (state, _value) in enumerate(states):
        if state != "available":
            return {
                "reason_kind": REASON_MISSING_INPUT,
                "reason_code": "INPUT_OBSERVATION_UNAVAILABLE",
                "operand_position": index,
                "input_ref": refs[index] if index < len(refs) else None,
                "explanation": (
                    f"not computable: {describe(index)} is unavailable, and no "
                    "substitute is permitted."
                ),
            }

    if operation in _POSITIVE_DENOMINATOR_OPERATIONS and len(states) > 1:
        value = states[1][1]
        if is_number(value) and float(value) <= 0:
            return {
                "reason_kind": NEGATIVE_INPUT,
                "reason_code": NON_POSITIVE_DENOMINATOR,
                "operand_position": 1,
                "input_ref": refs[1] if len(refs) > 1 else None,
                "input_value": safe_float(value),
                "condition": "DIVISOR_MUST_BE_POSITIVE",
                "explanation": (
                    f"not computable: {describe(1)} is "
                    f"{value}, and a ratio over a non-positive figure has no "
                    "interpretation. The observation itself is present and is "
                    "not treated as missing."
                ),
            }

    for index, (_state, value) in enumerate(states):
        if is_number(value) and float(value) <= 0:
            return {
                "reason_kind": NEGATIVE_INPUT,
                "reason_code": NON_POSITIVE_NUMERATOR,
                "operand_position": index,
                "input_ref": refs[index] if index < len(refs) else None,
                "input_value": safe_float(value),
                "condition": "OPERAND_MUST_BE_POSITIVE",
                "explanation": (
                    f"not computable: {describe(index)} is {value}, and a "
                    "figure computed from a non-positive operand is not "
                    "interpretable."
                ),
            }

    return {
        "reason_kind": REASON_NOT_AVAILABLE,
        "reason_code": "ENGINE_PRODUCED_NO_VALUE",
        "explanation": (
            "not computable: every input is present and usable, and the engine "
            "produced no value. No substitute is permitted."
        ),
    }


@dataclass(frozen=True)
class IdentityCheck:
    """
    An accounting identity that two independently reported figures should meet.

    These are general properties of how a quoted price relates to a share count
    and a market capitalisation, not statements about any particular issuer. A
    breach means the document's own numbers cannot all be true on one basis; it
    does not say which is wrong, and no side is selected.

    The derived figure is the one ST-EVA computed; the reported figure is one a
    source stated. Publishing the derived figure alone would present a number
    ST-EVA derived from two others as if it were a fact about the company.
    """

    name: str
    derived_ref: str
    reported_metric: str
    reported_provider: str
    relative_tolerance: float
    absolute_tolerance: float
    statement: str


IDENTITY_CHECKS: Tuple[IdentityCheck, ...] = (
    IdentityCheck(
        name="price_times_count_equals_market_cap",
        derived_ref=derived_ref("implied_shares"),
        reported_metric="shares_outstanding",
        reported_provider="",
        relative_tolerance=0.05,
        absolute_tolerance=1.0,
        statement=(
            "price x share count should reconcile with the reported market "
            "capitalisation, so the share count implied by that "
            "capitalisation should reconcile with the reported share count"
        ),
    ),
)


def _point_basis_key(observation: Observation) -> str:
    """
    What kind of series a point belongs to, when the construction differs.

    A discrete reported period and a constructed trailing window are the same
    metric but not the same measure: one covers three months and the other
    twelve. Differencing them produces a discontinuity that means nothing.
    """
    raw = observation.raw if isinstance(observation.raw, dict) else {}
    derivation = raw.get("derivation")
    if derivation:
        return f"CONSTRUCTED:{derivation}"
    return "REPORTED"


def period_span_bucket(
    period_start: Optional[str],
    period_end: Optional[str],
) -> str:
    """
    The length class a period falls into.

    A quarterly observation and an annual one are not two points on a line.
    Without this bucket, differencing them yields a change that measures the
    filing calendar rather than the business.
    """
    if not period_start:
        return "INSTANT"
    days = duration_days(period_start, period_end)
    if days is None:
        return "UNDECLARED"
    if QUARTER_MIN_DAYS <= days <= QUARTER_MAX_DAYS:
        return "QUARTERLY"
    if YEAR_MIN_DAYS <= days <= YEAR_MAX_DAYS:
        return "ANNUAL"
    return "CUMULATIVE"


def observation_type_of(observation: Observation) -> str:
    """
    Whether a point was reported by a source or constructed by ST-EVA, and
    whether it carries a period at all.
    """
    raw = observation.raw if isinstance(observation.raw, dict) else {}
    if raw.get("derivation"):
        return "DERIVED_WINDOW"
    if observation.period_start is None and observation.period_end:
        return "INSTANT_REPORTED"
    if observation.available_at is None:
        return "REPORTED_UNDATED"
    return "REPORTED_PERIOD"


def series_key(observation: Observation) -> Dict[str, str]:
    """
    What a point must match to be differenced against another point.

    Three axes, all of them necessary. Two points are only comparable on period
    length, on how the figure was produced, and on whether either carries a
    period at all.
    """
    return {
        "period_span": period_span_bucket(
            observation.period_start, observation.period_end
        ),
        "observation_type": observation_type_of(observation),
        "basis": _point_basis_key(observation),
    }


def series_metadata(
    observations: Sequence[Observation],
    relative_threshold: float = DISCONTINUITY_RELATIVE_THRESHOLD,
) -> Dict[str, Dict[str, Any]]:
    """
    Per-metric series shape, and where a series jumps.

    A discontinuity is only computed between two points that share a series key.
    Where a metric's points fall into more than one key, the series is reported
    as not comparable and the reason is stated, rather than being differenced
    across spans and presented as a change in the business.

    Two points that share a period end are not a step on a line. They are two
    versions of one period, and they are reported separately.

    What a discontinuity *means* is never stated. A large move may be a genuine
    change, a reclassification, a change in the concepts a filer tags, or a
    change in how a vendor composes a total, and only the filer can say which.
    """
    grouped: Dict[Tuple[str, str, str, str], List[Tuple[str, str, Observation]]] = {}
    for observation in observations:
        if not observation.is_available or not is_number(observation.value):
            continue
        if not (observation.period_end or observation.as_of):
            continue
        key = series_key(observation)
        group = (
            observation.metric,
            key["period_span"],
            key["observation_type"],
            key["basis"],
        )
        # The identifier is part of the sort key so the order is total: two
        # points can share a period end, and a stable order is what lets a
        # replay reproduce the archived document.
        grouped.setdefault(group, []).append(
            (
                str(observation.period_end or observation.as_of),
                str(observation.observation_id),
                observation,
            )
        )

    per_metric: Dict[str, Dict[str, Any]] = {}
    for (metric, span, kind, basis), entries in grouped.items():
        entries.sort(key=lambda item: (item[0], item[1]))
        periods = [period for period, _, _ in entries]
        values = [float(observation.value) for _, _, observation in entries]
        label = f"{span}|{kind}|{basis}"
        bucket = per_metric.setdefault(
            metric,
            {
                "observations": 0,
                "providers": [],
                "first_period": None,
                "last_period": None,
                "latest_value": None,
                "comparability": "NO_SERIES",
                "discontinuities": [],
                "same_period_pairs": [],
                "trend_is_explained": False,
                "series_status": SERIES_COMPARABLE,
                "series_status_reason": None,
                "bases": {},
                "note": (
                    "Points are grouped by period span, observation type, and "
                    "basis. Two points may be differenced only when all three "
                    "match. A group with fewer than two points has no trend."
                ),
            },
        )
        bucket["observations"] += len(values)
        bucket["providers"] = sorted(
            set(bucket["providers"]) | {o.provider for _, _, o in entries}
        )
        if bucket["first_period"] is None or periods[0] < bucket["first_period"]:
            bucket["first_period"] = periods[0]
        if bucket["last_period"] is None or periods[-1] > bucket["last_period"]:
            bucket["last_period"] = periods[-1]
        bucket["latest_value"] = values[-1]

        group_discontinuities: List[Dict[str, Any]] = []
        group_pairs: List[Dict[str, Any]] = []
        for position in range(1, len(values)):
            previous, current = values[position - 1], values[position]
            if periods[position] == periods[position - 1]:
                # Two versions of the same period. Not a step on a line.
                group_pairs.append(
                    {
                        "period_end": periods[position],
                        "from_value": previous,
                        "to_value": current,
                        "relative_difference": (
                            abs(current - previous) / abs(previous)
                            if previous
                            else None
                        ),
                        "relationship": "RESTATEMENT_OR_REVISION",
                        "from_ref": entries[position - 1][2].observation_id,
                        "to_ref": entries[position][2].observation_id,
                        "explanation": NOT_EXPLAINED,
                        "selection": "NO_WINNER_SELECTED",
                    }
                )
                continue
            if previous == 0:
                continue
            relative = abs(current - previous) / abs(previous)
            if relative > relative_threshold:
                group_discontinuities.append(
                    {
                        "from_period": periods[position - 1],
                        "to_period": periods[position],
                        "from_value": previous,
                        "to_value": current,
                        "absolute_change": current - previous,
                        "relative_change": relative,
                        "series_group": label,
                        "explanation": NOT_EXPLAINED,
                        "cause": "UNDETERMINED_FROM_AVAILABLE_SOURCES",
                    }
                )

        if len(values) < 2:
            group_comparability = "SINGLE_OBSERVATION_NO_TREND"
        elif len(values) < 4:
            group_comparability = "THIN_SERIES"
        else:
            group_comparability = "SERIES_AVAILABLE"

        bucket["bases"][label] = {
            "period_span": span,
            "observation_type": kind,
            "basis": basis,
            "observations": len(values),
            "first_period": periods[0],
            "last_period": periods[-1],
            "comparability": group_comparability,
            "discontinuities": group_discontinuities,
            "same_period_pairs": group_pairs,
        }
        bucket["discontinuities"].extend(group_discontinuities)
        bucket["same_period_pairs"].extend(group_pairs)

    for bucket in per_metric.values():
        if bucket["observations"] < 2:
            bucket["comparability"] = "SINGLE_OBSERVATION_NO_TREND"
        elif bucket["observations"] < 4:
            bucket["comparability"] = "THIN_SERIES"
        else:
            bucket["comparability"] = "SERIES_AVAILABLE"

        # More than one group means the points are not a single line, and the
        # reader is told so rather than being handed a list that looks like one.
        if len(bucket["bases"]) > 1:
            bucket["series_status"] = NOT_COMPARABLE
            bucket["series_status_reason"] = "PERIOD_SPAN_MISMATCH"
            bucket["series_status_detail"] = {
                "groups": sorted(bucket["bases"]),
                "note": (
                    "These observations are on different period spans, "
                    "observation types, or constructions. They are not "
                    "differenced against each other, and the list of "
                    "discontinuities below spans only the groups named."
                ),
            }
        else:
            bucket["series_status"] = SERIES_COMPARABLE
            bucket["series_status_reason"] = None
        bucket["discontinuities"].sort(
            key=lambda item: (item["from_period"], item["to_period"])
        )
        bucket["same_period_pairs"].sort(key=lambda item: item["period_end"])
    return per_metric


# ---------------------------------------------------------------------------
# Self-validation
#
# Every check here is a rule the document claims to obey. A failure is a defect
# in the document, and the build raises rather than emitting something a
# consumer has to discover later.
# ---------------------------------------------------------------------------


def _walk(node: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


def _operand_base(operand: str) -> str:
    kind, identifier, _ = split_ref(operand)
    return f"{kind}:{identifier}"


def check_references_resolve(document: Dict[str, Any]) -> None:
    """
    Every ref named anywhere resolves.

    A dangling ref means the document is corrupt, and a consumer must not be
    left to guess what it points at.
    """
    refs = document["provenance"]["refs"]
    base_refs = {_operand_base(ref) for ref in refs}

    for node in _walk(document):
        for key in ("ref", "derivation_ref"):
            value = node.get(key)
            if isinstance(value, str) and ":" in value:
                if _operand_base(value) not in base_refs:
                    raise UnresolvedRefError(
                        f"{value!r} is named as a {key} but is not in the "
                        "provenance table"
                    )
        for key in (
            "vendor_ref",
            "filing_ref",
            "source_ref",
            "observation",
            "subject",
        ):
            value = node.get(key)
            if isinstance(value, str) and value:
                if _operand_base(value) not in base_refs:
                    raise UnresolvedRefError(
                        f"{value!r} is named as a {key} but is not in the "
                        "provenance table"
                    )

    for derivation in document["provenance"]["derivations"].values():
        for operand in derivation["operation"]["operands"]:
            if _operand_base(operand) not in base_refs:
                raise UnresolvedRefError(
                    f"operand {operand!r} does not resolve in the provenance "
                    "table"
                )


def check_graph_acyclic(document: Dict[str, Any]) -> None:
    """
    The derivation graph is acyclic.

    A consumer must be able to walk it without looping, and a cycle would make
    "start from any figure and reach a raw observation" undecidable.
    """
    derivations = document["provenance"]["derivations"]
    graph: Dict[str, List[str]] = {}
    for ref, derivation in derivations.items():
        graph.setdefault(ref, [])
        for operand in derivation["operation"]["operands"]:
            base = _operand_base(operand)
            if base in derivations:
                graph[ref].append(base)

    state: Dict[str, int] = {}

    def visit(node: str, trail: Tuple[str, ...]) -> None:
        if state.get(node) == 2:
            return
        if state.get(node) == 1:
            raise ContextError(
                "the derivation graph contains a cycle: "
                + " -> ".join(trail + (node,))
            )
        state[node] = 1
        for neighbour in graph.get(node, ()):
            visit(neighbour, trail + (node,))
        state[node] = 2

    for node in graph:
        visit(node, ())


def check_no_unavailable_value(document: Dict[str, Any]) -> None:
    """
    An unavailable figure carries no value.

    Not `null` with a sibling status, not zero, not a median. This is the single
    most important invariant in the document.
    """
    for name, entry in document["derived"].items():
        figure = entry["figure"]
        if figure.get("provenance_kind") == PROVENANCE_UNAVAILABLE:
            if "value" in figure:
                raise ContextError(
                    f"{name} is marked UNAVAILABLE but carries a value; an "
                    "absent figure must carry no number at all"
                )
    for metric, entries in document["observed"].items():
        for item in entries:
            figure = item["figure"]
            if (
                figure.get("provenance_kind") == PROVENANCE_UNAVAILABLE
                and "value" in figure
            ):
                raise ContextError(
                    f"observed {metric} is UNAVAILABLE but carries a value"
                )
    for item in document["unavailable"]:
        ref = item.get("ref")
        if not ref:
            continue
        base = _operand_base(ref)
        refs = document["provenance"]["refs"].get(base)
        if refs and "value" in refs and refs.get("provenance_kind") == (
            PROVENANCE_OBSERVED
        ):
            raise ContextError(
                f"{item['ref']} is listed as unavailable but is registered as "
                "an observed value"
            )


def check_conditional_figures_are_conditioned(document: Dict[str, Any]) -> None:
    """
    Every implied figure names the reference it is conditional on.

    A conditional figure whose condition is unstated is a forecast wearing a
    disguise, and that is the failure mode the implied section exists to
    prevent.
    """
    valuation_ref = reference_ref("valuation_reference")
    for name, entry in document["market_implied"]["figures"].items():
        if not entry.get("conditional_on"):
            raise ContextError(
                f"implied figure {name!r} declares no conditional_on; a "
                "conditional figure must name the reference it is "
                "conditional on"
            )
        for condition in entry["conditional_on"]:
            if _operand_base(condition) not in document["provenance"]["refs"]:
                raise UnresolvedRefError(
                    f"implied figure {name!r} is conditional on {condition!r}, "
                    "which does not resolve"
                )
    if not document["market_implied"].get("conditional_statement"):
        raise ContextError(
            "the implied section must carry a conditional_statement; it "
            "qualifies every figure in it"
        )
    if valuation_ref not in document["provenance"]["refs"]:
        raise UnresolvedRefError(
            f"{valuation_ref!r} must be present; every implied figure is "
            "conditional on it"
        )


def check_data_quality_has_no_grade(document: Dict[str, Any]) -> None:
    """
    No composite number in data_quality.

    A single figure standing in for "how good is this data" is an
    interpretation, it invites comparison between assets that were never
    compared, and it hides which specific weakness is present.
    """
    grade_words = (
        "score",
        "grade",
        "quality",
        "completeness",
        "confidence",
        "rating",
        "reliability",
    )
    for key in document["data_quality"]:
        for word in grade_words:
            if word in key.lower():
                raise ContextError(
                    f"data_quality carries a {key!r} field; this section is "
                    "counts and statuses, never a grade"
                )


def check_no_verdict_vocabulary(document: Dict[str, Any]) -> None:
    """
    No verdict vocabulary outside the non-claims list.

    `scope.does_not_provide` is the one place these words are supposed to
    appear, because it is where the document says what it is not. The scan runs
    over a copy with that block removed, so the exemption is exact rather than a
    heuristic about where the string sits.

    Matching is by whole word, not by substring. Substring matching produces
    false positives on the data's own vocabulary — `shareholders` contains
    `hold`, `trailingNetIncomeCommonStockholders` would fail a document for no
    reason — and a guard that cries wolf gets switched off, which is worse than
    having no guard. Prefixes are used for the inflected forms we want to catch
    (`recommend`, `probabilit`).
    """
    scanned = {
        key: value
        for key, value in document.items()
        if key != "scope"
    }
    scanned["scope"] = {
        key: value
        for key, value in document["scope"].items()
        if key != "does_not_provide"
    }

    def walk(node: Any) -> Iterable[Dict[str, Any]]:
        if isinstance(node, dict):
            yield node
            for value in node.values():
                yield from walk(value)
        elif isinstance(node, list):
            for item in node:
                yield from walk(item)

    patterns = {
        token: re.compile(
            rf"\b{token}\w*" if token.endswith(("recommend", "probabilit"))
            else rf"\b{token}\b"
        )
        for token in FORBIDDEN_VOCABULARY
    }

    for node in walk(scanned):
        for key, value in node.items():
            if not isinstance(value, str):
                continue
            lowered = value.lower()
            for token, pattern in patterns.items():
                if pattern.search(lowered):
                    raise ContextError(
                        f"key {key!r} contains verdict vocabulary "
                        f"{token!r}: {value!r}. The context must not state "
                        "or imply an investment verdict."
                    )


def check_knowledge_cutoff(document: Dict[str, Any]) -> None:
    """
    `knowledge_cutoff` is the latest availability, and nothing is from the
    future.
    """
    latest: Optional[str] = None
    for entry in document["provenance"]["refs"].values():
        if entry.get("kind") != KIND_OBSERVATION:
            continue
        available_at = entry.get("available_at")
        if available_at and (latest is None or str(available_at) > latest):
            latest = str(available_at)
    declared = document.get("knowledge_cutoff")
    if latest and declared and str(latest) > str(declared):
        raise ContextError(
            f"knowledge_cutoff {declared!r} precedes the latest available "
            f"observation {latest!r}; the declared boundary understates what "
            "the document knows"
        )
    as_of = document.get("as_of")
    if as_of:
        for node in _walk(document.get("provenance", {}).get("refs", {})):
            observed_as_of = node.get("as_of")
            if observed_as_of and str(observed_as_of) > str(as_of):
                raise ContextError(
                    f"{node.get('ref')} has as_of {observed_as_of!r}, later "
                    f"than the context as_of {as_of!r}; a context about a "
                    "moment cannot contain a later-moment fact"
                )


def check_derivations_declare_reasons(document: Dict[str, Any]) -> None:
    """
    A derivation may honestly fail to recompute, but it must say so.

    `deterministic: false` without a reason is a quiet excuse; a reason is the
    difference between an audit trail and a shrug.
    """
    for ref, derivation in document["provenance"]["derivations"].items():
        if derivation.get("deterministic"):
            if derivation.get("non_deterministic_reason"):
                raise ContextError(
                    f"{ref} is deterministic but also declares a "
                    "non-deterministic reason"
                )
            continue
        if not derivation.get("non_deterministic_reason"):
            raise ContextError(
                f"{ref} is marked non-deterministic without a reason; a "
                "derivation cannot be excused silently"
            )


def check_operations_are_registered(document: Dict[str, Any]) -> None:
    """
    Every operation in the document exists in the registry at the version it
    declares.

    A derivation naming an operation the evaluator cannot run is a derivation
    whose provenance cannot be checked, which is exactly the state this
    document exists to rule out.
    """
    for ref, derivation in document["provenance"]["derivations"].items():
        operation = derivation["operation"]
        try:
            operation_registry.lookup(
                operation["op"], operation.get("version", "1")
            )
        except RegistryError as error:
            raise ContextError(
                f"{ref} names an operation the registry cannot run: {error}"
            ) from error


def recompute_derivation(
    document: Dict[str, Any],
    ref: str,
) -> Optional[float]:
    """
    Re-evaluate one derivation from the document alone.

    This is what a consumer does to check a number, and what acceptance test 12
    does to every derived figure in a real run.
    """
    derivation = document["provenance"]["derivations"].get(ref)
    if derivation is None or not derivation.get("deterministic"):
        return None
    refs = document["provenance"]["refs"]
    figure_value = _document_figure_value(document, ref)

    values: List[Any] = []
    units: List[Optional[str]] = []
    for operand in derivation["operation"]["operands"]:
        base = _operand_base(operand)
        _, _, selector = split_ref(operand)
        entry = refs.get(base)
        if entry is None:
            raise UnresolvedRefError(
                f"operand {operand!r} does not resolve"
            )
        value = _document_figure_value(document, base)
        if value is None:
            raise MissingOperandError(
                f"operand {operand!r} is unavailable, so {ref} cannot be "
                "recomputed"
            )
        if entry.get("operand_field") == "multiple" and entry.get("kind") == (
            KIND_REFERENCE
        ):
            value = entry.get("multiple")
        if selector is not None:
            value = _select_operand_value(value, selector, operand)
        values.append(value)
        units.append(
            document["derived"].get(split_ref(base)[1], {})
            .get("figure", {})
            .get("unit")
            if split_ref(base)[0] == KIND_DERIVED
            else entry.get("unit") or entry.get("operand_unit")
        )

    return evaluate(
        derivation["operation"]["op"],
        values,
        units,
        derivation["operation"].get("parameters"),
        derivation["operation"].get("version", "1"),
    ) if figure_value is not None else None


def _document_figure_value(
    document: Dict[str, Any],
    ref: str,
) -> Any:
    kind, identifier, _ = split_ref(ref)
    if kind == KIND_DERIVED:
        entry = document["derived"].get(identifier)
        if entry is None:
            return None
        figure = entry["figure"]
        return figure.get("value") if "value" in figure else None
    if kind == KIND_OBSERVATION:
        for entries in document["observed"].values():
            for item in entries:
                if item["figure"].get("ref") == ref:
                    figure = item["figure"]
                    return figure.get("value") if "value" in figure else None
        return None
    if kind == KIND_EVIDENCE:
        entry = document["provenance"]["refs"].get(ref)
        if entry is None:
            return None
        legacy = entry.get("legacy_row") or {}
        value = legacy.get("value")
        return None if value == UNAVAILABLE_SENTINEL else value
    if kind == KIND_REFERENCE:
        entry = document["provenance"]["refs"].get(ref)
        return None if entry is None else entry.get("multiple")
    return None


def _select_operand_value(value: Any, selector: str, operand: str) -> Any:
    if isinstance(value, dict):
        if selector in value:
            return value[selector]
        raise UnresolvedRefError(
            f"operand {operand!r} selects {selector!r}, which is absent"
        )
    if isinstance(value, (list, tuple)):
        if not selector.lstrip("-").isdigit():
            raise UnresolvedRefError(
                f"operand {operand!r} needs a numeric index, got {selector!r}"
            )
        index = int(selector)
        resolved = index if index >= 0 else len(value) + index
        if not 0 <= resolved < len(value):
            raise UnresolvedRefError(
                f"operand {operand!r} index {selector} is out of range"
            )
        return value[resolved]
    raise UnresolvedRefError(
        f"operand {operand!r} cannot select from {type(value).__name__}"
    )


UNAVAILABLE_SENTINEL = "UNAVAILABLE"


def verify_document(document: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run every self-check, and recompute every deterministic derivation.

    Returns a report so a caller can log what was verified. Raises on the first
    failure, because a document that fails a check must not be published.
    """
    ContextBuilder.validate  # the checks are module functions; see below
    for check in (
        check_references_resolve,
        check_graph_acyclic,
        check_no_unavailable_value,
        check_conditional_figures_are_conditioned,
        check_data_quality_has_no_grade,
        check_no_verdict_vocabulary,
        check_knowledge_cutoff,
        check_derivations_declare_reasons,
        check_operations_are_registered,
    ):
        check(document)

    recomputed = 0
    skipped: List[str] = []
    for ref, derivation in document["provenance"]["derivations"].items():
        if not derivation.get("deterministic"):
            skipped.append(ref)
            continue
        figure = _document_figure_value(document, ref)
        if figure is None:
            # The figure is unavailable because an input was. That is a
            # recorded state, not a check that can be run, and the reason is
            # already in the unavailable section.
            skipped.append(ref)
            continue
        value = recompute_derivation(document, ref)
        if value is None:
            skipped.append(ref)
            continue
        recomputed += 1

    return {
        "recomputed": recomputed,
        "not_recomputable": sorted(skipped),
        "context_id": document["context_id"],
    }


def build_investment_context(
    data: Any,
    analysis: Dict[str, Any],
    evidence: Any,
    metrics: Dict[str, Any],
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Build and self-validate one Investment Context.

    The document is validated before it is returned, so an inconsistent context
    never reaches a caller.
    """
    builder = ContextBuilder(
        data=data,
        analysis=analysis,
        evidence=evidence,
        metrics=metrics,
        **kwargs,
    )
    document = builder.build()
    builder.validate(document)
    return document
