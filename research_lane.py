"""The research calculation lane.

A research lane computes a figure from filed evidence that the production
qualification regime does not admit, and it does so without touching that
regime. The two are separate in every respect that matters.

* The names are separate. A research metric id begins with ``RESEARCH_`` and
  is not a production metric id; a research basis is not a production basis.
  :func:`assert_research_isolation` checks the disjointness against the
  production vocabularies at run time rather than trusting a naming
  convention, and refuses to run on a collision.
* The gate is separate. A lane reads the registry's standing on every element
  it uses and records it on every observation, but the standing never decides
  the arithmetic. A registry refusal is a fact about the element, not a veto
  on the research figure.
* The destination is separate. A lane result is written by its caller, and
  the only destination the repository supports is the research tree. A lane
  never writes an Archive, never produces a ``refc:*`` row, never reaches an
  Investment Context, and is never read by the production runner.

What the lane borrows from production is the arithmetic that must not be
re-invented: the discrete-quarter derivation, the trailing-window walk, the
point-in-time usable-date rule and the as-traded close restoration. Those are
imported, not copied, so a research figure and a production figure built from
the same filed facts agree on the window and disagree only where the
production gate says they must.

The methodology (``research-multiples/1.0``) states eight rules:

R-1  The point-in-time rule is the production rule. A fact is knowable only
     from its filing's usable date under the 16:00 ET cutoff, the value in
     force at an evaluation date is the latest knowable version, and a price
     is the as-traded close of the evaluation date.
R-2  The window is the production window: four consecutive fiscal quarters
     containing a Q4, anchored on the greatest fiscal position with knowable
     evidence, refused rather than backfilled.
R-3  The registry's standing on every element is read and recorded on every
     observation, and it never decides the figure. A declined element is still
     usable evidence for a research figure, provided the research metric names
     the element it actually reads.
R-4  A research metric names its own quantity. A research figure is never a
     production metric under another name: the metric id says what the
     denominator is, and the formula is carried on every observation.
R-5  The filed balance-sheet bridge keeps the production rules: every
     component must be knowable at the evaluation date, every component must
     describe one balance-sheet date, and the bridge is never completed by
     omission, substitution or zero-fill.
R-6  An element change is a basis break, not a continuity. Where a filer
     changes the element it uses for a line, the lane reads the successor
     element and records the break on the observation.
R-7  Every observation carries the accessions, elements, spans, periods,
     units, usable dates and the operands the figure was computed from, so
     the figure can be recomputed from the evidence rather than trusted.
R-8  The result is descriptive. A lane states its sample size and its sample
     period, and it never asserts production eligibility.
R-9  A revision of a value already known for a prior period is detected and
     recorded rather than absorbed. The lane compares the version in force
     for the same role and the same fiscal period across adjacent evaluation
     dates. A period that appears for the first time is a first appearance,
     not a revision; a version that is replaced by a different value is a
     prior-period value revision, and it is classified neutrally because the
     lane's evidence shows the value changed, not that the issuer formally
     restated.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from fiscal_calendar import build_fiscal_calendar
from historical_pe import (
    canonical_json_hash,
    compute_distribution_percentiles,
    resolve_usable_date,
    restore_as_traded_close,
)
from historical_pfcf import (
    DurationSpanEvidence,
    concept_spans_from_payload,
    discrete_quarters_for_role,
    in_force_version,
    ttm_window_at,
)
from semantic_qualification import qualify_element

METHODOLOGY = "research-multiples/1.0"
LOGIC_VERSION = "research-multiples/1.0.0"
FORMULA_VERSION = "research-multiples/1.0"

# The lane's own distribution statuses. They are not the production statuses:
# "usable for reference" is a production statement about a production
# distribution, and a research distribution makes no such statement.
STATUS_RESEARCH_DISTRIBUTION = "RESEARCH_DISTRIBUTION"
STATUS_RESEARCH_THIN_SAMPLE = "RESEARCH_THIN_SAMPLE"
STATUS_RESEARCH_UNAVAILABLE = "RESEARCH_UNAVAILABLE"

# The lane's own refusal codes. They are a closed set, separate from the
# production one, because the conditions are different: a research lane has
# its own reasons for refusing an observation, and it must be able to say
# that a figure was refused for a reason the production vocabulary has no
# word for. A production code is never renamed into this set.
REASON_MISSING_PRICE = "RESEARCH_REASON_MISSING_PRICE"
REASON_MISSING_SHARES = "RESEARCH_REASON_MISSING_SHARES"
REASON_NO_DENOMINATOR_WINDOW = "RESEARCH_REASON_NO_DENOMINATOR_WINDOW"
REASON_FISCAL_POSITION_UNRESOLVED = "RESEARCH_REASON_FISCAL_POSITION_UNRESOLVED"
REASON_NON_POSITIVE_DENOMINATOR = "RESEARCH_REASON_NON_POSITIVE_DENOMINATOR"
REASON_INCOMPLETE_EV_BRIDGE = "RESEARCH_REASON_INCOMPLETE_EV_BRIDGE"
REASON_MIXED_BALANCE_SHEET_PERIODS = "RESEARCH_REASON_MIXED_BALANCE_SHEET_PERIODS"
REASON_ELEMENT_UNAVAILABLE = "RESEARCH_REASON_ELEMENT_UNAVAILABLE"
REASON_UNIT_UNKNOWN = "RESEARCH_REASON_UNIT_UNKNOWN"
REASON_UNIT_CONFLICT = "RESEARCH_REASON_UNIT_CONFLICT"
REASON_CURRENCY_MISMATCH = "RESEARCH_REASON_CURRENCY_MISMATCH"

CLOSED_REASON_CODES = frozenset(
    {
        REASON_MISSING_PRICE,
        REASON_MISSING_SHARES,
        REASON_NO_DENOMINATOR_WINDOW,
        REASON_FISCAL_POSITION_UNRESOLVED,
        REASON_NON_POSITIVE_DENOMINATOR,
        REASON_INCOMPLETE_EV_BRIDGE,
        REASON_MIXED_BALANCE_SHEET_PERIODS,
        REASON_ELEMENT_UNAVAILABLE,
        REASON_UNIT_UNKNOWN,
        REASON_UNIT_CONFLICT,
        REASON_CURRENCY_MISMATCH,
    }
)

# How a role enters the formula.
FORMULA_DENOMINATOR = "DENOMINATOR"
FORMULA_OPERATING_INCOME = "OPERATING_INCOME"
FORMULA_DEPRECIATION = "DEPRECIATION"
FORMULA_BRIDGE_COMPONENT = "BRIDGE_COMPONENT"
FORMULA_SHARES = "SHARES"

# How a role enters the enterprise-value bridge.
BRIDGE_SIGN_DEBT = "DEBT"
BRIDGE_SIGN_LIQUID_FUNDS = "LIQUID_FUNDS"
BRIDGE_SIGN_NONE = "NONE"

# What a bridge component is. The comparison service reads the group rather
# than a component's name, so an issuer that names its short-term
# borrowings differently is still compared correctly.
BRIDGE_GROUP_LONG_TERM = "LONG_TERM"
BRIDGE_GROUP_SHORT_TERM = "SHORT_TERM"
BRIDGE_GROUP_LIQUID = "LIQUID"
BRIDGE_GROUPS = (
    BRIDGE_GROUP_LONG_TERM,
    BRIDGE_GROUP_SHORT_TERM,
    BRIDGE_GROUP_LIQUID,
)

# What a change of element means for the series.
CHANGE_RE_TAG = "RE_TAG"
CHANGE_SCOPE_CHANGE = "SCOPE_CHANGE"

# The neutral classification of a prior-period value revision. The lane's
# evidence shows that a value it already knew was replaced by a different
# value; it does not show that the issuer formally restated, so it does not
# say so.
REVISION_PRIOR_PERIOD_VALUE = "PRIOR_PERIOD_VALUE_REVISION"

RESEARCH_USE_LABEL = (
    "RESEARCH USE ONLY. This distribution is computed from filed evidence "
    "that the production qualification regime does not admit. It is not a "
    "valuation reference, it is not a production reference chain input, and "
    "it must not be presented as one."
)


# ---------------------------------------------------------------------------
# The lane's configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResearchRole:
    """One quantity a lane reads, and the elements it may read it from.

    A role names a quantity, never a concept. ``elements`` is the filer's own
    chronology: the element it used first, then the element it moved to. The
    lane reads whichever element is in force at the evaluation date and
    records the change as a basis break (R-6).

    ``registry_metric_id`` is the registry metric the element would be read
    for under a production lane. It is recorded, never enforced (R-3); when
    the registry declares no such metric the standing is NOT_APPLICABLE,
    which is a statement about the registry's coverage and not a refusal.
    """

    name: str
    taxonomy: str
    elements: Tuple[str, ...]
    formula_role: str
    #: The capture role the elements come from. The capture's element table
    #: is the single place an issuer's elements are written down, and this
    #: says which row of it the role reads.
    capture_role: str = ""
    registry_metric_id: Optional[str] = None
    element_change_kind: str = CHANGE_RE_TAG
    bridge_sign: str = BRIDGE_SIGN_NONE
    #: What the role is in the bridge, when it is a bridge component:
    #: LONG_TERM, SHORT_TERM or LIQUID. The comparison service reads the
    #: group rather than a component's name, so a filer that names its
    #: short-term borrowings differently is still compared correctly.
    bridge_group: Optional[str] = None
    note: str = ""

    def __post_init__(self) -> None:
        if not self.elements:
            raise ValueError(f"role {self.name!r} names no element")
        if self.element_change_kind not in (CHANGE_RE_TAG, CHANGE_SCOPE_CHANGE):
            raise ValueError(
                f"role {self.name!r} has an unknown element_change_kind "
                f"{self.element_change_kind!r}"
            )
        if self.bridge_sign not in (
            BRIDGE_SIGN_DEBT,
            BRIDGE_SIGN_LIQUID_FUNDS,
            BRIDGE_SIGN_NONE,
        ):
            raise ValueError(
                f"role {self.name!r} has an unknown bridge_sign {self.bridge_sign!r}"
            )
        if self.bridge_group is not None and self.bridge_group not in BRIDGE_GROUPS:
            raise ValueError(
                f"role {self.name!r} has an unknown bridge_group "
                f"{self.bridge_group!r}"
            )
        if self.bridge_group is not None and self.bridge_sign == BRIDGE_SIGN_NONE:
            raise ValueError(
                f"role {self.name!r} declares a bridge group but takes no part in "
                "the bridge"
            )


@dataclass(frozen=True)
class ResearchUnitPolicy:
    """
    The units and the currency a lane's inputs are in.

    A multiple is a market value over a financial denominator, so the two
    must be in the same currency and the denominator must be stated in a unit
    the policy names. A filer that states its amounts in thousands is not the
    same as a filer that states them in units, and the difference is a factor
    of a thousand rather than a rounding detail.

    ``scale`` is the factor the capture applied to the filed amounts, and
    ``scale_basis`` says why. The lane refuses a capture whose units do not
    match the policy, rather than computing a figure whose magnitude is
    wrong by a factor of a thousand.
    """

    filing_unit: str
    filing_currency: str
    price_currency: str
    share_unit: str
    scale: float = 1.0
    scale_basis: str = ""
    #: The rule that converts the price's currency into the denominator's,
    #: when they differ. Without it a lane whose price and denominator are
    #: in different currencies refuses to compute.
    fx_rule: Optional[str] = None

    def __post_init__(self) -> None:
        for name in (
            "filing_unit",
            "filing_currency",
            "price_currency",
            "share_unit",
        ):
            if not getattr(self, name):
                raise ValueError(f"the unit policy names no {name}")
        if self.scale <= 0:
            raise ValueError(
                f"the unit policy's scale must be positive, got {self.scale}"
            )


@dataclass(frozen=True)
class ResearchLaneConfig:
    """One research lane: its identity, its capture, and its roles."""

    lane_id: str
    issuer_id: str
    instrument_id: str
    entity_name: str
    fye_month: int
    capture_dir: Path
    metric_id: str
    metric_label: str
    research_purpose: str
    formula_expression: str
    formula_numerator: str
    formula_denominator: str
    formula_version: str = FORMULA_VERSION
    #: The roles that build the denominator, in the order the formula reads
    #: them. A two-role denominator is built quarter by quarter: a quarter
    #: that carries only one of the roles is absent, not half a quarter.
    denominator_roles: Tuple[str, ...] = ()
    #: Every role the lane reads, by name.
    roles: Tuple[ResearchRole, ...] = ()
    #: What the lane divides by: the market capitalization, or the filed
    #: enterprise-value bridge. Only the enterprise-value lane is gated by the
    #: bridge's completeness, because the bridge is part of its numerator.
    numerator_kind: str = "market_cap"
    #: Whether the lane may be offered as a research metric. A diagnostic
    #: lane is not a candidate and must not be listed as one.
    candidate_metric: bool = True
    #: The minimum sample the lane reports as a distribution rather than a
    #: descriptive summary. This says how much evidence a description rests
    #: on; it never grants production eligibility.
    min_observations_for_description: int = 20
    #: The units and the currency the lane's inputs are in, and the rule that
    #: ties them together. A lane whose inputs do not match the policy
    #: refuses to compute.
    unit_policy: ResearchUnitPolicy = field(
        default_factory=lambda: ResearchUnitPolicy(
            filing_unit="USD",
            filing_currency="USD",
            price_currency="USD",
            share_unit="shares",
        )
    )

    def __post_init__(self) -> None:
        if self.numerator_kind not in ("market_cap", "enterprise_value"):
            raise ValueError(f"unknown numerator_kind {self.numerator_kind!r}")
        by_name = {role.name: role for role in self.roles}
        for name in self.denominator_roles:
            if name not in by_name:
                raise ValueError(
                    f"lane {self.lane_id!r} names denominator role {name!r} "
                    "which is not among its roles"
                )

    def role(self, name: str) -> ResearchRole:
        for role in self.roles:
            if role.name == name:
                return role
        raise KeyError(f"lane {self.lane_id!r} has no role {name!r}")

    @property
    def bridge_roles(self) -> Tuple[ResearchRole, ...]:
        return tuple(
            role for role in self.roles if role.formula_role == FORMULA_BRIDGE_COMPONENT
        )


# ---------------------------------------------------------------------------
# The lane's results
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResearchObservation:
    """One dated evaluation of one research lane."""

    observation_id: str
    lane_id: str
    issuer_id: str
    instrument_id: str
    evaluation_date: str
    status: str
    metric_id: str
    reason_code: Optional[str] = None
    reason_detail: Optional[str] = None
    value: Optional[float] = None
    price: Optional[float] = None
    price_currency: str = "USD"
    price_accounting_basis: str = "as_traded"
    price_split_restoration: Optional[List[Dict[str, Any]]] = None
    price_source: Dict[str, Any] = field(default_factory=dict)
    shares_outstanding: Optional[float] = None
    shares_source: Dict[str, Any] = field(default_factory=dict)
    shares_as_of_date: Optional[str] = None
    shares_accession: Optional[str] = None
    shares_usable_date: Optional[str] = None
    market_cap: Optional[float] = None
    enterprise_value: Optional[float] = None
    total_debt: Optional[float] = None
    liquid_funds: Optional[float] = None
    denominator: Optional[Dict[str, Any]] = None
    formula: Dict[str, Any] = field(default_factory=dict)
    bridge: Dict[str, Any] = field(default_factory=dict)
    registry_standing: Dict[str, Any] = field(default_factory=dict)
    basis_breaks: List[str] = field(default_factory=list)
    prior_period_revisions: List[Dict[str, Any]] = field(default_factory=list)
    point_in_time: Dict[str, Any] = field(default_factory=dict)
    production_refusal: Dict[str, Any] = field(default_factory=dict)
    methodology: str = METHODOLOGY
    logic_version: str = LOGIC_VERSION
    formula_version: str = FORMULA_VERSION
    input_set_id: str = ""
    content_hash: str = ""

    def __post_init__(self) -> None:
        if self.reason_code is not None and self.reason_code not in CLOSED_REASON_CODES:
            raise ValueError(
                f"reason_code {self.reason_code!r} is not in the research refusal "
                "set; an unknown code is an error, not a refusal"
            )
        if self.status == "UNAVAILABLE" and self.reason_code is None:
            raise ValueError(
                f"observation {self.observation_id!r} refuses without a reason"
            )
        if not self.content_hash:
            object.__setattr__(self, "content_hash", self.compute_content_hash())

    def compute_content_hash(self) -> str:
        data = asdict(self)
        data.pop("content_hash", None)
        return canonical_json_hash(data)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ResearchDistribution:
    """One research lane's distribution.

    ``production_eligible`` is fixed to ``False`` by the type: the field
    cannot be set at construction and the dataclass is frozen, so no code
    path can turn a research distribution into a production reference by
    forgetting a check.
    """

    metric_id: str
    metric_label: str
    research_use_label: str
    lane_id: str
    issuer_id: str
    instrument_id: str
    status: str = STATUS_RESEARCH_UNAVAILABLE
    production_eligible: bool = field(default=False, init=False)
    candidate_metric: bool = True
    sample_count: int = 0
    total_evaluations: int = 0
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    min_observations_for_description: int = 20
    mean: Optional[float] = None
    std: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None
    percentiles: Dict[str, Optional[float]] = field(default_factory=dict)
    reason_code: Optional[str] = None
    reason_detail: Optional[str] = None
    excluded_observations: List[Dict[str, Any]] = field(default_factory=list)
    sampling_cadence: str = "PERIODIC_FILING_USABLE_DATES"
    formula: Dict[str, Any] = field(default_factory=dict)
    registry_standing: Dict[str, Any] = field(default_factory=dict)
    production_refusal: Dict[str, Any] = field(default_factory=dict)
    data_limitations: List[str] = field(default_factory=list)
    prior_period_revisions: List[Dict[str, Any]] = field(default_factory=list)
    basis_breaks: List[Dict[str, Any]] = field(default_factory=dict)
    #: The unit and currency policy the distribution was computed under, and
    #: the units the capture's facts were actually read in. The scaling the
    #: capture applied is recorded with its basis.
    unit_policy: Dict[str, Any] = field(default_factory=dict)
    methodology: str = METHODOLOGY
    logic_version: str = LOGIC_VERSION
    formula_version: str = FORMULA_VERSION
    input_set_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ResearchLaneResult:
    """The package a research lane returns."""

    lane_id: str
    issuer_id: str
    instrument_id: str
    metric_id: str
    candidate_metric: bool
    input_set_id: str
    content_hash: str
    distribution: ResearchDistribution
    observations: List[ResearchObservation] = field(default_factory=list)
    capture_manifest: Dict[str, Any] = field(default_factory=dict)
    methodology: str = METHODOLOGY
    logic_version: str = LOGIC_VERSION
    formula_version: str = FORMULA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lane_id": self.lane_id,
            "issuer_id": self.issuer_id,
            "instrument_id": self.instrument_id,
            "metric_id": self.metric_id,
            "candidate_metric": self.candidate_metric,
            "input_set_id": self.input_set_id,
            "content_hash": self.content_hash,
            "methodology": self.methodology,
            "logic_version": self.logic_version,
            "formula_version": self.formula_version,
            "capture_manifest": dict(self.capture_manifest),
            "distribution": self.distribution.to_dict(),
            "observations": [obs.to_dict() for obs in self.observations],
        }


# ---------------------------------------------------------------------------
# The isolation guard
# ---------------------------------------------------------------------------


def assert_research_isolation(metric_ids: Sequence[str]) -> Dict[str, Any]:
    """Refuse to run when a research name collides with a production name.

    The production vocabularies are read, not restated: the reference bases
    the Archive can reproduce, the bases the Investment Context supports, and
    the production metric ids. A research lane whose name appeared in any of
    them could enter the production chain by accident, so the lane refuses to
    run rather than rely on a convention.

    Returns the evidence of the check so a reader can see it was made.
    """
    from archive import PRODUCTION_REFERENCE_BASES
    from investment_context import REFERENCE_SOURCES

    production_bases = {basis for _name, basis, _source in PRODUCTION_REFERENCE_BASES}
    production_bases |= set(REFERENCE_SOURCES)
    production_metrics = {
        "P_S_RATIO_REFERENCE",
        "EV_EBITDA_RATIO_REFERENCE",
        "TTM_REVENUE",
        "TTM_EBITDA",
    }
    collisions = sorted(set(metric_ids) & (production_bases | production_metrics))
    if collisions:
        raise ValueError(
            "research metric ids collide with production names: "
            f"{collisions}. A research lane may not publish under a production "
            "name."
        )
    return {
        "production_reference_bases": sorted(production_bases),
        "production_metric_ids": sorted(production_metrics),
        "research_metric_ids": sorted(set(metric_ids)),
        "collisions": collisions,
        "checked": (
            "against archive.PRODUCTION_REFERENCE_BASES and "
            "investment_context.REFERENCE_SOURCES as they are in this "
            "repository, at run time"
        ),
    }


# ---------------------------------------------------------------------------
# The capture
# ---------------------------------------------------------------------------


def _sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_capture(config: ResearchLaneConfig) -> Dict[str, Any]:
    """Read the capture's files, their hashes and their roles."""
    directory = config.capture_dir
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files: Dict[str, Dict[str, Any]] = {}
    for name, entry in (manifest.get("files") or {}).items():
        path = directory / name
        if not path.exists():
            raise FileNotFoundError(
                f"the capture declares {name!r} but the file is missing from "
                f"{directory}"
            )
        digest = _sha256_of(path)
        if digest != entry.get("sha256"):
            raise ValueError(
                f"{name!r} does not match its recorded SHA-256; the capture "
                "has changed since it was built"
            )
        files[name] = {**entry, "path": path, "sha256": digest}
    return {"manifest": manifest, "files": files}


def _element_payloads(
    capture: Mapping[str, Any], role: ResearchRole
) -> Dict[str, Dict[str, Any]]:
    """The capture's payloads for the elements a role may be read from.

    A role's own file is read first. An element the capture holds under
    another role's file is still readable, because the capture is a set of
    filed elements and the role names the element it reads.
    """
    payloads: Dict[str, Dict[str, Any]] = {}
    for name, entry in capture["files"].items():
        document = json.loads(entry["path"].read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            continue
        for element in document.get("elements") or []:
            tag = element.get("tag")
            if tag in role.elements and tag not in payloads:
                payloads[tag] = {
                    **element,
                    "_file": name,
                    "_sha256": entry["sha256"],
                    "_source": entry.get("source") or {},
                }
    return payloads


def _unit_of(payloads: Mapping[str, Mapping[str, Any]]) -> str:
    """
    The unit a role's facts are read in, taken from the capture.

    The unit is a property of the filed facts, not an assumption: it is
    whatever unit the capture's rows for that role carry. A role whose
    payloads carry more than one unit is read in the one the capture's
    manifest names for it, and the others are recorded rather than hidden.
    """
    units: set = set()
    for payload in payloads.values():
        units.update((payload.get("units") or {}).keys())
    if len(units) == 1:
        return next(iter(units))
    if "USD" in units:
        return "USD"
    raise ValueError(
        "the capture holds a role in more than one unit and names no unit to "
        f"read it in: {sorted(units)}"
    )


def _source_reference(
    entry: Mapping[str, Any], file_name: str
) -> Dict[str, Any]:
    """
    The source of a capture file, as the evidence view shows it.

    The file, its digest, and where it came from. When the capture's manifest
    does not say where a file came from, the reference says so rather than
    guessing.
    """
    source = entry.get("source") or {}
    url = source.get("url")
    return {
        "source_file": file_name,
        "source_sha256": entry.get("sha256"),
        "source_url": url,
        "source_retrieval": source.get("retrieval"),
        "source_document_sha256": source.get("source_document_sha256"),
        "source_note": source.get("note"),
        "source_known": bool(url or source.get("retrieval")),
    }


def _registry_standing(role: ResearchRole, element: str, ticker: str) -> Dict[str, Any]:
    """The registry's own standing on one element (R-3).

    Recorded, never enforced. A refusal is a fact about the element and is
    carried on the observation so a reader can see exactly why a research
    figure is not a production figure.
    """
    concept = f"{role.taxonomy}:{element}"
    if role.registry_metric_id is None:
        return {
            "role": role.name,
            "element": concept,
            "registry_metric_id": None,
            "registry_decision": "NOT_APPLICABLE",
            "reason_code": "NO_SUCH_REGISTRY_METRIC",
            "qualified": None,
            "mapping_type": None,
            "relation_kind": None,
            "scope": None,
            "effective_from": None,
            "effective_to": None,
            "basis": (
                "The role names no registry metric, so the registry has no "
                "standing to rule on the element. The lane's own specification "
                "governs the role, and the element is read under it."
            ),
        }
    record = qualify_element(
        metric_id=role.registry_metric_id,
        taxonomy=role.taxonomy,
        element=element,
        ticker=ticker,
    ).to_dict()
    qualified = record.get("qualified")
    if qualified:
        decision = "QUALIFIED"
    elif record.get("registry_metric_exists") is False:
        decision = "NOT_APPLICABLE"
    else:
        decision = "NOT_QUALIFIED"
    return {
        "role": role.name,
        "element": concept,
        "registry_metric_id": role.registry_metric_id,
        "registry_decision": decision,
        "reason_code": record.get("reason_code"),
        "qualified": qualified,
        "mapping_type": record.get("mapping_type"),
        "relation_kind": record.get("relation_kind"),
        "scope": record.get("scope"),
        "effective_from": record.get("effective_from"),
        "effective_to": record.get("effective_to"),
        "basis": record.get("reason_detail"),
    }


# ---------------------------------------------------------------------------
# The lane engine
# ---------------------------------------------------------------------------


def _in_force_fact(
    facts: Sequence[Mapping[str, Any]], day: str
) -> Optional[Mapping[str, Any]]:
    """The latest knowable version of a balance-sheet instant (R-1)."""
    in_force = None
    for fact in facts:
        if fact["usable_date"] <= day:
            in_force = fact
        else:
            break
    return in_force


def _select_bridge_fact(
    role: ResearchRole,
    facts_by_element: Mapping[str, Sequence[Mapping[str, Any]]],
    day: str,
) -> Tuple[Optional[Mapping[str, Any]], Optional[str]]:
    """The bridge component in force at an evaluation date, and the break.

    Each element of the role is read at its own latest knowable version. The
    one whose balance-sheet date is the most recent wins, because the issuer's
    successor element describes the same line at a later date and the earlier
    one is then stale. Where two elements describe the same date the
    chronology decides (R-5, R-6).
    """
    candidates: List[Tuple[str, Mapping[str, Any]]] = []
    for element in role.elements:
        fact = _in_force_fact(facts_by_element.get(element, ()), day)
        if fact is not None:
            candidates.append((element, fact))
    if not candidates:
        return None, None
    best_element, best_fact = max(
        candidates,
        key=lambda item: (item[1]["period_end"], role.elements.index(item[0])),
    )
    others = [(element, fact) for element, fact in candidates if element != best_element]
    if not others:
        return best_fact, None
    scope_note = ""
    if role.element_change_kind == CHANGE_SCOPE_CHANGE:
        scope_note = (
            " The role declares this element change to be a scope change: the "
            "successor element measures a different quantity that arrives at "
            "the same line."
        )
    if all(fact["period_end"] == best_fact["period_end"] for _element, fact in others):
        same_value = all(fact["value"] == best_fact["value"] for _element, fact in others)
        if role.element_change_kind == CHANGE_SCOPE_CHANGE:
            detail = (
                "The two elements describe the same balance-sheet date, and "
                "the role declares the change a scope change rather than a "
                "re-tagging."
            )
        elif same_value:
            detail = (
                "The two elements carry the same filed value on that date, so "
                "the change is a re-tagging of the same quantity."
            )
        else:
            detail = (
                "The two elements carry different filed values on that date, "
                "so the change is a re-tagging of a quantity whose filed value "
                "also changed."
            )
        return best_fact, (
            f"The {role.name} line changed element at {best_fact['period_end']}: "
            f"{best_element} supersedes "
            + ", ".join(element for element, _fact in others)
            + f". {detail}"
            + scope_note
        )
    return best_fact, (
        f"The {role.name} line is carried by {best_element} as of "
        f"{best_fact['period_end']}; "
        + ", ".join(f"{element} as of {fact['period_end']}" for element, fact in others)
        + " describes an earlier balance sheet and is not carried forward."
        + scope_note
    )


def _element_source(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Where one element's facts came from, as the capture recorded it.

    The capture names the endpoint each element was read from and, where the
    company concept endpoint served nothing for a filer, the substitution it
    used instead. When the capture records neither, the reference says the
    source was not provided rather than guessing at one.
    """
    source = payload.get("source") or {}
    url = source.get("companyconcept_endpoint") or source.get("facts_endpoint")
    return {
        "source_url": url,
        "source_retrieval": source.get("retrieval"),
        "source_document_sha256": source.get("source_document_sha256"),
        "source_note": source.get("substitution_note") or source.get("note"),
        "source_known": bool(url or source.get("retrieval")),
    }


def _input_spans(
    role: ResearchRole,
    quarter: Mapping[str, Any],
    unit: str,
    payloads: Mapping[str, Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """
    The cumulative spans a discrete quarter was derived from.

    A quarter made from a cumulative difference names the periods it was
    made of, so a reader can see which filings the quarter rests on and
    which of them were later revised. Each span names the unit it was read
    in and the source it was read from.
    """
    spans: List[Dict[str, Any]] = []
    for item in quarter.get("inputs", []) or []:
        tag = item.get("concept_tag")
        payload = payloads.get(tag) or {}
        source = _element_source(payload)
        spans.append(
            {
                "role": role.name,
                "element": f"{role.taxonomy}:{tag}",
                "start": item.get("start"),
                "end": item.get("end"),
                "value": item.get("value"),
                "unit": unit,
                "currency": unit if unit == "USD" else None,
                "accession": item.get("accession"),
                "filed_date": item.get("filed_date"),
                "usable_date": item.get("usable_date"),
                "source_file": payload.get("_file"),
                "source_sha256": payload.get("_sha256"),
                "source_url": source["source_url"],
                "source_note": source["source_note"],
                "source_known": source["source_known"],
            }
        )
    return spans


def _mixed_basis_notes(
    denominator: Optional[Mapping[str, Any]],
    revived_spans: Mapping[Tuple[str, str, str], bool],
) -> List[str]:
    """The quarters whose inputs are not all on the same basis.

    A derived quarter subtracts one cumulative span from another. When one
    of those spans has been revised and the other has not, the quarter is
    made of a pre-revision figure and a post-revision figure, and the
    quarter is therefore on neither basis. The lane records the condition
    rather than absorbing it.
    """
    notes: List[str] = []
    for quarter in (denominator or {}).get("quarters", []) or []:
        spans = quarter.get("input_spans") or []
        if len(spans) < 2:
            continue
        states = {
            revived_spans.get((span["role"], span["start"], span["end"]), False)
            for span in spans
        }
        if len(states) > 1:
            notes.append(
                f"The quarter ending {quarter['period_end']} is derived from "
                "spans that are not all on the same basis: "
                + ", ".join(
                    f"{span['element']} {span['start']}..{span['end']} "
                    f"(accession {span['accession']}, "
                    + (
                        "revised"
                        if revived_spans.get(
                            (span["role"], span["start"], span["end"]), False
                        )
                        else "not revised"
                    )
                    + ")"
                    for span in spans
                )
                + ". The quarter is made of a pre-revision figure and a "
                "post-revision figure and is on neither basis."
            )
    return notes


def _refused_result(
    config: ResearchLaneConfig,
    capture: Mapping[str, Any],
    isolation: Mapping[str, Any],
    input_set_id: Optional[str],
    reason_code: str,
    reason_detail: str,
    unit_record: Mapping[str, Any],
) -> ResearchLaneResult:
    """
    A lane that refuses to compute, with the reason it refuses.

    The refusal is a result, not an exception: a caller can read why the
    lane produced nothing, and the refusal carries the same production
    refusal every other research result carries.
    """
    distribution = ResearchDistribution(
        metric_id=config.metric_id,
        metric_label=config.metric_label,
        research_use_label=RESEARCH_USE_LABEL,
        lane_id=config.lane_id,
        issuer_id=config.issuer_id,
        instrument_id=config.instrument_id,
        status=STATUS_RESEARCH_UNAVAILABLE,
        candidate_metric=config.candidate_metric,
        sample_count=0,
        total_evaluations=0,
        min_observations_for_description=config.min_observations_for_description,
        reason_code=reason_code,
        reason_detail=reason_detail,
        formula={
            "expression": config.formula_expression,
            "formula_version": config.formula_version,
            "numerator": config.formula_numerator,
            "denominator": config.formula_denominator,
        },
        production_refusal={
            "production_eligible": False,
            "statement": (
                "No production reference is created from this result, and none "
                "may be created from it."
            ),
        },
        data_limitations=[
            f"the unit and currency policy: {reason_detail}",
        ],
        unit_policy=dict(unit_record),
        input_set_id=input_set_id or "",
    )
    return ResearchLaneResult(
        lane_id=config.lane_id,
        issuer_id=config.issuer_id,
        instrument_id=config.instrument_id,
        metric_id=config.metric_id,
        candidate_metric=config.candidate_metric,
        input_set_id=input_set_id or "",
        content_hash=canonical_json_hash(
            {
                "reason_code": reason_code,
                "reason_detail": reason_detail,
                "input_set_id": input_set_id or "",
            }
        ),
        distribution=distribution,
        observations=[],
        capture_manifest={
            "capture_dir": str(config.capture_dir),
            "files": {
                name: entry.get("sha256")
                for name, entry in sorted((capture.get("files") or {}).items())
            },
            "unit_policy": dict(unit_record),
            "isolation": isolation,
        },
    )


def _unit_policy_violation(
    config: ResearchLaneConfig,
    role_units: Mapping[str, str],
    share_unit: Optional[str],
    price_currency: Optional[str],
) -> Optional[Tuple[str, str]]:
    """
    Whether the lane's inputs match the unit and currency policy.

    A multiple is a market value over a financial denominator, so the two
    must be in the same currency, and the denominator must be stated in the
    unit the policy names. A capture whose facts are stated in thousands is
    not the same capture as one stated in units, and the difference is a
    factor of a thousand rather than a rounding detail. A lane that cannot
    state the units it reads refuses to compute rather than publishing a
    figure whose magnitude is wrong.
    """
    policy = config.unit_policy
    for role in config.roles:
        if role.formula_role == FORMULA_SHARES:
            continue
        unit = role_units.get(role.name)
        if not unit:
            return (
                REASON_UNIT_UNKNOWN,
                f"The capture names no unit for the {role.name} role, so the "
                "lane cannot state what its figures are in.",
            )
        if unit != policy.filing_unit:
            return (
                REASON_UNIT_CONFLICT,
                f"The {role.name} role is stated in {unit}, but the issuer's "
                f"unit policy states {policy.filing_unit}. The lane refuses to "
                "compute across that difference rather than assume the "
                "amounts are already normalised.",
            )
    if share_unit is None:
        return (
            REASON_UNIT_UNKNOWN,
            "The capture names no unit for the cover-page share count, so the "
            "lane cannot state what it is counting.",
        )
    if share_unit != policy.share_unit:
        return (
            REASON_UNIT_CONFLICT,
            f"The cover-page share count is stated in {share_unit}, but the "
            f"issuer's unit policy states {policy.share_unit}.",
        )
    if not price_currency:
        return (
            REASON_UNIT_UNKNOWN,
            "The price series names no currency, so the lane cannot state what "
            "the market value is in.",
        )
    if price_currency != policy.price_currency:
        return (
            REASON_CURRENCY_MISMATCH,
            f"The price series is in {price_currency}, but the issuer's unit "
            f"policy states {policy.price_currency}.",
        )
    if policy.filing_currency != price_currency and not policy.fx_rule:
        return (
            REASON_CURRENCY_MISMATCH,
            f"The denominator is in {policy.filing_currency} and the price is "
            f"in {price_currency}, and the issuer's unit policy declares no "
            "conversion rule between them, so the lane refuses to divide one "
            "by the other.",
        )
    return None


def _element_availability_violation(
    config: ResearchLaneConfig,
    role_payloads: Mapping[str, Mapping[str, Any]],
) -> Optional[Tuple[str, str]]:
    """
    Whether every element a role declares is one the capture actually holds.

    A role names the elements it reads. If the capture does not hold one of
    them, the lane would read the subset the capture happens to carry, and
    the figure would be a different figure from the one the role names.
    That is a refusal, not a smaller sample.
    """
    for role in config.roles:
        held = role_payloads.get(role.name) or {}
        for element in role.elements:
            if element not in held:
                return (
                    REASON_ELEMENT_UNAVAILABLE,
                    f"The {role.name} role declares {role.taxonomy}:{element}, which "
                    "the capture does not hold, so the lane cannot read the element "
                    "the role names. The lane refuses rather than compute from the "
                    "elements the capture happens to carry.",
                )
    return None


def _capture_normalisation_violation(
    config: ResearchLaneConfig,
    capture: Mapping[str, Any],
) -> Optional[Tuple[str, str]]:
    """
    Whether the capture's own normalisation agrees with the unit policy.

    The capture states the unit it holds its amounts in and the factor it
    applied to the filed amounts. The policy states the unit the issuer's
    figures are in and the factor the capture is to apply. When they
    disagree, the figures the lane would compute are not the figures the
    policy describes, and the lane refuses rather than publish a magnitude
    that is wrong by a factor.
    """
    policy = config.unit_policy
    declared = (
        ((capture.get("manifest") or {}).get("capture_policy") or {}).get(
            "role_normalisation"
        )
        or {}
    )
    for role in config.roles:
        record = declared.get(role.capture_role)
        if not isinstance(record, Mapping):
            continue
        expected_unit = (
            policy.share_unit if role.formula_role == FORMULA_SHARES else policy.filing_unit
        )
        target_unit = record.get("target_unit")
        if target_unit and target_unit != expected_unit:
            return (
                REASON_UNIT_CONFLICT,
                f"The capture holds the {role.name} role in {target_unit}, but the "
                f"issuer's unit policy states {expected_unit}. The lane refuses "
                "to compute across that difference rather than assume the amounts "
                "are already normalised.",
            )
        factor = record.get("factor")
        if (
            factor is not None
            and role.formula_role != FORMULA_SHARES
            and float(factor) != float(policy.scale)
        ):
            return (
                REASON_UNIT_CONFLICT,
                f"The capture applied a scaling factor of {factor} to the {role.name} "
                f"role, but the issuer's unit policy states {policy.scale}. The lane "
                "refuses to reuse a calculation identity that was computed under a "
                "different scaling.",
            )
    return None


def _revision_records(
    previous: Mapping[Tuple[str, str, str], Mapping[str, Any]],
    current: Mapping[Tuple[str, str, str], Mapping[str, Any]],
    day: str,
) -> List[Dict[str, Any]]:
    """The prior-period value revisions visible at this evaluation date (R-9).

    A revision is a period whose version in force changed to a different
    value. A period that appears for the first time is a first appearance and
    is not a revision; a version replaced by the same value is not a value
    revision either.
    """
    revisions: List[Dict[str, Any]] = []
    for key, version in sorted(current.items()):
        before = previous.get(key)
        if before is None:
            # A first appearance: the lane had no version of this period.
            continue
        if before["accession"] == version["accession"]:
            continue
        if before["value"] == version["value"]:
            continue
        role, start, end = key
        difference = version["value"] - before["value"]
        revisions.append(
            {
                "classification": REVISION_PRIOR_PERIOD_VALUE,
                "role": role,
                "period_start": start,
                "period_end": end,
                "detected_at_evaluation_date": day,
                "old_value": before["value"],
                "old_accession": before["accession"],
                "old_usable_date": before["usable_date"],
                "old_element": before["element"],
                "new_value": version["value"],
                "new_accession": version["accession"],
                "new_usable_date": version["usable_date"],
                "new_element": version["element"],
                "difference": difference,
                "difference_ratio": (
                    difference / before["value"] if before["value"] else None
                ),
                "element_changed": before["element"] != version["element"],
                "element_change_kind": (
                    None
                    if before["element"] == version["element"]
                    else "ELEMENT_CHANGED"
                ),
                "note": (
                    "The lane's evidence shows that the value it already knew "
                    "for this period was replaced by a different value. It does "
                    "not show that the issuer formally restated, and it does "
                    "not say so."
                ),
            }
        )
    return revisions


def load_research_lane(config: ResearchLaneConfig) -> ResearchLaneResult:
    """Execute one research lane over its capture.

    Nothing is fetched. The capture is read, never written, and the lane
    never opens an Archive. The caller decides where the result goes; the
    only destination the repository supports is the research tree.
    """
    isolation = assert_research_isolation([config.metric_id])
    capture = _load_capture(config)
    directory = config.capture_dir

    # The capture's files are found by the role the manifest gives them, so
    # the lane does not depend on a file's name.
    files_by_role: Dict[str, Dict[str, Any]] = {}
    for name, entry in capture["files"].items():
        role = entry.get("role")
        if role:
            files_by_role.setdefault(str(role), {"name": name, **entry})
    if "prices" not in files_by_role:
        raise ValueError(
            "the capture names no file with the role 'prices'; the lane "
            "cannot read a price series from it"
        )
    price_entry = files_by_role["prices"]
    price_source = _source_reference(price_entry, price_entry["name"])
    shares_role_name = None
    for role in config.roles:
        if role.formula_role == FORMULA_SHARES:
            shares_role_name = role.name
            break
    shares_entry = files_by_role.get(shares_role_name or "", {})
    shares_source = _source_reference(shares_entry, shares_entry.get("name", ""))

    # -- the acceptance index ------------------------------------------------
    acceptance_entry = files_by_role.get("acceptance index")
    if acceptance_entry is None:
        raise ValueError(
            "the capture names no file with the role 'acceptance index'; the "
            "lane cannot know when a filing became knowable"
        )
    acceptance = json.loads(
        (directory / acceptance_entry["name"]).read_text(encoding="utf-8")
    )
    price_document = json.loads(
        (directory / price_entry["name"]).read_bytes().decode("utf-8")
    )["chart"]["result"][0]
    granularity = price_document.get("meta", {}).get("dataGranularity")
    if granularity != "1d":
        raise ValueError(
            f"price granularity must be '1d', got {granularity!r}; a coarser "
            "series cannot serve a daily evaluation"
        )
    quote = price_document["indicators"]["quote"][0]
    bars = {
        datetime.datetime.fromtimestamp(stamp, datetime.timezone.utc)
        .date()
        .isoformat(): float(quote["close"][index])
        for index, stamp in enumerate(price_document["timestamp"])
        if quote["close"][index] is not None
    }
    trading_days = sorted(bars)
    splits = price_document.get("events", {}).get("splits", {})
    price_currency = (price_document.get("meta") or {}).get("currency")

    filings_index: Dict[str, Dict[str, Any]] = {}
    for row in acceptance:
        acceptance_datetime = datetime.datetime.fromisoformat(
            row["acceptance_datetime_effective_et"]
        )
        usable_date, usable_rule = resolve_usable_date(
            acceptance_datetime, trading_days
        )
        filings_index[row["accession"]] = {
            "form": row["form"],
            "acceptance_datetime": acceptance_datetime.isoformat(),
            "acceptance_basis": row.get("acceptance_basis"),
            "usable_date": usable_date,
            "usable_date_rule": usable_rule,
            "period_end": row["period_end"],
        }


    # -- the role payloads ----------------------------------------------------
    role_payloads: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for role in config.roles:
        role_payloads[role.name] = _element_payloads(capture, role)
        if not role_payloads[role.name]:
            raise ValueError(
                f"the capture holds no element for role {role.name!r}; the "
                "lane cannot be executed"
            )

    # The unit each role's facts are read in. The unit is a property of the
    # filed facts the capture holds, not an assumption the lane makes.
    role_units: Dict[str, str] = {
        role.name: _unit_of(role_payloads[role.name]) for role in config.roles
    }

    # -- the fiscal calendar --------------------------------------------------
    duration_roles = [
        role
        for role in config.roles
        if role.formula_role
        in (FORMULA_DENOMINATOR, FORMULA_OPERATING_INCOME, FORMULA_DEPRECIATION)
    ]
    calendar_payloads = []
    for role in duration_roles:
        for element in role.elements:
            payload = role_payloads[role.name].get(element)
            if payload is not None:
                calendar_payloads.append(payload)
    fiscal_calendar = build_fiscal_calendar(
        calendar_payloads,
        filings_index,
        units=tuple(sorted({role_units[role.name] for role in duration_roles})),
    )

    # -- the duration spans ----------------------------------------------------
    spans: List[DurationSpanEvidence] = []
    for role in duration_roles:
        for element in role.elements:
            payload = role_payloads[role.name].get(element)
            if payload is None:
                continue
            element_source = _element_source(payload)
            spans += concept_spans_from_payload(
                payload=payload,
                unit=role_units[role.name],
                role=role.name,
                concept_tag=element,
                issuer_id=config.issuer_id,
                filings_index=filings_index,
                content_sha256=payload["_sha256"],
                source_url=element_source["source_url"] or "",
            )
    spans_by_key: Dict[Tuple[str, str, str], List[DurationSpanEvidence]] = {}
    for span in spans:
        spans_by_key.setdefault((span.role, span.start, span.end), []).append(span)
    for versions in spans_by_key.values():
        versions.sort(
            key=lambda item: (item.usable_date, item.acceptance_datetime, item.accession)
        )

    # -- the balance-sheet instants -------------------------------------------
    bridge_facts: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    for role in config.bridge_roles:
        facts_by_element: Dict[str, List[Dict[str, Any]]] = {}
        for element in role.elements:
            payload = role_payloads[role.name].get(element)
            if payload is None:
                continue
            facts: List[Dict[str, Any]] = []
            for unit, rows in (payload.get("units") or {}).items():
                for row in rows:
                    if row.get("start"):
                        continue
                    filing = filings_index.get(row.get("accn"))
                    if filing is None:
                        continue
                    facts.append(
                        {
                            "element": f"{role.taxonomy}:{element}",
                            "period_end": str(row.get("end") or ""),
                            "value": float(row["val"]),
                            "currency": unit,
                            "accession": row["accn"],
                            "form": filing["form"],
                            "filed": row.get("filed"),
                            "usable_date": filing["usable_date"],
                            "usable_date_rule": filing["usable_date_rule"],
                            "content_sha256": payload["_sha256"],
                            "source_file": payload["_file"],
                            "source_url": _element_source(payload)["source_url"],
                            "source_note": _element_source(payload)["source_note"],
                        }
                    )
            facts.sort(
                key=lambda fact: (
                    fact["usable_date"],
                    fact["period_end"],
                    fact["accession"],
                )
            )
            facts_by_element[element] = facts
        bridge_facts[role.name] = facts_by_element

    # -- the cover-page share counts ------------------------------------------
    shares_role = next(
        (role for role in config.roles if role.formula_role == FORMULA_SHARES), None
    )
    share_facts: List[Dict[str, Any]] = []
    if shares_role is not None:
        for element in shares_role.elements:
            payload = role_payloads[shares_role.name].get(element)
            if payload is None:
                continue
            for unit, rows in (payload.get("units") or {}).items():
                for row in rows:
                    filing = filings_index.get(row.get("accn"))
                    if filing is None:
                        continue
                    share_facts.append(
                        {
                            "shares": float(row["val"]),
                            "as_of_date": str(row.get("end") or ""),
                            "accession": row["accn"],
                            "form": filing["form"],
                            "filed": row.get("filed"),
                            "usable_date": filing["usable_date"],
                            "usable_date_rule": filing["usable_date_rule"],
                            "unit": unit,
                            "content_sha256": payload["_sha256"],
                            "source_file": payload["_file"],
                            "source_url": _element_source(payload)["source_url"],
                        }
                    )
    share_facts.sort(
        key=lambda fact: (
            fact["usable_date"],
            fact["as_of_date"],
            fact["accession"],
        )
    )
    share_unit = share_facts[0]["unit"] if share_facts else None

    # -- the run identity -------------------------------------------------------
    input_manifest = {
        "lane": {
            "lane_id": config.lane_id,
            "issuer_id": config.issuer_id,
            "metric_id": config.metric_id,
            "formula_version": config.formula_version,
            "denominator_roles": list(config.denominator_roles),
            "numerator_kind": config.numerator_kind,
        },
        "capture_files": {
            name: entry["sha256"] for name, entry in sorted(capture["files"].items())
        },
        "isolation": isolation,
    }
    input_set_id = canonical_json_hash(input_manifest)

    evaluation_dates = sorted(
        {filing["usable_date"] for filing in filings_index.values()}
    )

    # -- the unit and currency policy -----------------------------------------
    # A lane that cannot state the units it reads does not compute. The
    # refusal is a result, not an exception, so the reason travels with it.
    policy = config.unit_policy
    unit_record = {
        "filing_unit": policy.filing_unit,
        "filing_currency": policy.filing_currency,
        "price_currency": policy.price_currency,
        "share_unit": policy.share_unit,
        "scale": policy.scale,
        "scale_basis": policy.scale_basis,
        "fx_rule": policy.fx_rule,
        "role_units": dict(role_units),
        "observed_share_unit": share_unit,
        "observed_price_currency": price_currency,
    }
    violation = _unit_policy_violation(
        config, role_units, share_unit, price_currency
    )
    if violation is None:
        violation = _element_availability_violation(config, role_payloads)
    if violation is None:
        violation = _capture_normalisation_violation(config, capture)
    if violation is not None:
        return _refused_result(
            config,
            capture,
            isolation,
            input_set_id=input_set_id,
            reason_code=violation[0],
            reason_detail=violation[1],
            unit_record=unit_record,
        )

    standing_by_role: Dict[str, Dict[str, Any]] = {}
    for role in config.roles:
        standing_by_role[role.name] = {
            element: _registry_standing(role, element, config.instrument_id)
            for element in role.elements
        }

    observations: List[ResearchObservation] = []
    previous_elements: Dict[str, str] = {}
    previous_span_versions: Dict[Tuple[str, str, str], Mapping[str, Any]] = {}
    revisions: List[Dict[str, Any]] = []
    revisions_by_span: Dict[Tuple[str, str, str], List[str]] = {}

    for day in evaluation_dates:
        spans_in_force = {
            key: in_force_version(versions, day)
            for key, versions in spans_by_key.items()
        }
        spans_in_force = {
            key: version for key, version in spans_in_force.items() if version is not None
        }

        # R-9: the version in force for each role and period, against the
        # version in force at the previous evaluation date.
        span_versions_now = {
            key: {
                "value": version.value,
                "accession": version.accession,
                "usable_date": version.usable_date,
                "element": f"{config.role(key[0]).taxonomy}:{version.concept_tag}",
            }
            for key, version in spans_in_force.items()
        }
        day_revisions = _revision_records(
            previous_span_versions, span_versions_now, day
        )
        previous_span_versions = span_versions_now
        for revision in day_revisions:
            revisions.append(revision)
            revisions_by_span.setdefault(
                (
                    revision["role"],
                    revision["period_start"],
                    revision["period_end"],
                ),
                [],
            ).append(revision["detected_at_evaluation_date"])
        revived_spans = {
            key: bool(revisions_by_span.get(key))
            for key in spans_in_force
        }

        quarters_by_role: Dict[str, Dict[datetime.date, Dict[str, Any]]] = {}
        for role in duration_roles:
            quarters = discrete_quarters_for_role(
                spans_in_force=spans_in_force, role=role.name
            )
            identified: Dict[datetime.date, Dict[str, Any]] = {}
            for end_date, quarter in quarters.items():
                identity = fiscal_calendar.identity_for(end_date.isoformat())
                if identity is None:
                    continue
                identified[end_date] = {
                    **quarter,
                    "period_end": end_date.isoformat(),
                    "fiscal_year": identity.fiscal_year,
                    "fiscal_quarter": identity.fiscal_quarter,
                    "identity_source": identity.identity_source,
                }
            quarters_by_role[role.name] = identified

        # -- the denominator ------------------------------------------------------
        denominator_value: Optional[float] = None
        denominator_window: Optional[Dict[str, Any]] = None
        reason_code: Optional[str] = None
        reason_detail = ""

        windows: List[Tuple[str, Dict[str, Any]]] = []
        for role_name in config.denominator_roles:
            window, _production_reason, detail, refusal = ttm_window_at(
                quarters=quarters_by_role.get(role_name, {}), day=day
            )
            if window is None:
                reason_code = REASON_NO_DENOMINATOR_WINDOW
                reason_detail = (
                    f"The four-quarter {role_name} window is not knowable at "
                    f"{day}: {detail}"
                )
                if refusal and refusal.get("no_quarter_knowable"):
                    reason_detail = (
                        f"No discrete quarter of the {role_name} role is "
                        f"knowable at {day}, so no trailing window exists."
                    )
                break
            windows.append((role_name, window))

        if reason_code is None:
            if len(windows) == 1:
                role_name, window = windows[0]
                role = config.role(role_name)
                denominator_value = sum(
                    quarter["value"] for quarter in window["quarters"]
                )
                unit = role_units[role_name]
                denominator_window = {
                    "value": denominator_value,
                    "unit": unit,
                    "currency": unit if unit == "USD" else None,
                    "anchor": window["anchor"],
                    "positions": window["positions"],
                    "derivation": (
                        "the sum of four consecutive discrete fiscal quarters "
                        f"of the {role_name} role, read from "
                        f"{', '.join(role.elements)}"
                    ),
                    "quarters": [
                        {
                            "period_end": quarter["period_end"],
                            "fiscal_year": quarter["fiscal_year"],
                            "fiscal_quarter": quarter["fiscal_quarter"],
                            "value": quarter["value"],
                            "unit": unit,
                            "currency": unit if unit == "USD" else None,
                            "knowable_from": quarter["knowable_from"],
                            "derivation": quarter["derivation"],
                            "accessions": sorted(
                                {
                                    item["accession"]
                                    for item in quarter.get("inputs", [])
                                }
                            ),
                            "elements": sorted(
                                {
                                    f"{role.taxonomy}:{item.get('concept_tag')}"
                                    for item in quarter.get("inputs", [])
                                }
                            ),
                            "input_spans": _input_spans(
                                role,
                                quarter,
                                unit,
                                role_payloads[role_name],
                            ),
                        }
                        for quarter in window["quarters"]
                    ],
                }
            else:
                anchors = {
                    (
                        window["anchor"]["fiscal_year"],
                        window["anchor"]["fiscal_quarter"],
                    )
                    for _role_name, window in windows
                }
                if len(anchors) != 1:
                    reason_code = REASON_FISCAL_POSITION_UNRESOLVED
                    reason_detail = (
                        "The denominator's roles do not share a fiscal anchor, "
                        "so no single trailing figure is built from them: "
                        + ", ".join(
                            f"{role_name} anchors at FY"
                            f"{window['anchor']['fiscal_year']} Q"
                            f"{window['anchor']['fiscal_quarter']}"
                            for role_name, window in windows
                        )
                    )
                else:
                    role_units_in_window = [
                        role_units[role_name] for role_name, _window in windows
                    ]
                    quarter_unit = (
                        role_units_in_window[0]
                        if len(set(role_units_in_window)) == 1
                        else "MIXED"
                    )
                    per_end: Dict[str, Dict[str, Any]] = {}
                    for role_name, window in windows:
                        role = config.role(role_name)
                        unit = role_units[role_name]
                        for quarter in window["quarters"]:
                            per_end.setdefault(quarter["period_end"], {})[role_name] = {
                                "value": quarter["value"],
                                "element": f"{role.taxonomy}:{role.elements[-1]}",
                                "unit": unit,
                                "currency": unit if unit == "USD" else None,
                                "accessions": sorted(
                                    {
                                        item["accession"]
                                        for item in quarter.get("inputs", [])
                                    }
                                ),
                                "knowable_from": quarter["knowable_from"],
                                "input_spans": _input_spans(
                                    role,
                                    quarter,
                                    unit,
                                    role_payloads[role_name],
                                ),
                            }
                    quarters_out: List[Dict[str, Any]] = []
                    total = 0.0
                    for end in sorted(per_end):
                        parts = per_end[end]
                        if len(parts) != len(windows):
                            reason_code = REASON_NO_DENOMINATOR_WINDOW
                            reason_detail = (
                                f"The fiscal quarter ending {end} is missing one "
                                "of the roles the denominator is built from. The "
                                "quarter is absent, not half a quarter."
                            )
                            break
                        contribution = sum(part["value"] for part in parts.values())
                        total += contribution
                        quarters_out.append(
                            {
                                "period_end": end,
                                "value": contribution,
                                "unit": quarter_unit,
                                "currency": (
                                    quarter_unit if quarter_unit == "USD" else None
                                ),
                                "knowable_from": max(
                                    part["knowable_from"] for part in parts.values()
                                ),
                                "formula": " + ".join(
                                    f"{part['value']} ({name} from {part['element']})"
                                    for name, part in sorted(parts.items())
                                ),
                                "parts": parts,
                                "accessions": sorted(
                                    {
                                        accession
                                        for part in parts.values()
                                        for accession in part["accessions"]
                                    }
                                ),
                                "elements": sorted(
                                    {part["element"] for part in parts.values()}
                                ),
                                "input_spans": [
                                    span
                                    for part in parts.values()
                                    for span in part["input_spans"]
                                ],
                            }
                        )
                    if reason_code is None:
                        denominator_value = total
                        denominator_window = {
                            "value": total,
                            "unit": quarter_unit,
                            "currency": (
                                quarter_unit if quarter_unit == "USD" else None
                            ),
                            "anchor": windows[0][1]["anchor"],
                            "positions": windows[0][1]["positions"],
                            "derivation": (
                                "the sum over four consecutive fiscal quarters, "
                                "each quarter the sum of "
                                + " and ".join(
                                    f"the {name} role"
                                    for name, _window in windows
                                )
                            ),
                            "quarters": quarters_out,
                        }

        # -- the market capitalization ---------------------------------------------
        price = None
        price_provenance: Optional[List[Dict[str, Any]]] = None
        price_evidence: Dict[str, Any] = {
            **price_source,
            "as_of_date": day,
            "period": day,
        }
        close = bars.get(day)
        if close is not None:
            restored, provenance, _note = restore_as_traded_close(close, day, splits)
            price = round(restored, 4)
            price_provenance = [dict(item) for item in provenance]

        share = None
        for candidate in share_facts:
            if candidate["usable_date"] <= day:
                share = candidate
            else:
                break

        market_cap = None
        if price is not None and share is not None:
            market_cap = round(price * share["shares"], 2)

        # -- the enterprise-value bridge ---------------------------------------------
        bridge: Dict[str, Any] = {
            "policy": (
                "Every filed balance-sheet component must be knowable at the "
                "evaluation date and must describe the same balance-sheet "
                "date. The bridge is never completed by omission, "
                "substitution or zero-fill."
            ),
            "components": {},
            "components_absent": [],
            "complete": False,
            "basis_breaks": [],
        }
        selected: Dict[str, Mapping[str, Any]] = {}
        total_debt = None
        liquid_funds = None
        enterprise_value = None
        for role in config.bridge_roles:
            fact, break_note = _select_bridge_fact(
                role, bridge_facts[role.name], day
            )
            if fact is None:
                bridge["components_absent"].append(role.name)
                continue
            selected[role.name] = fact
            bridge["components"][role.name] = dict(fact)
            if break_note:
                bridge["basis_breaks"].append(break_note)
            previous = previous_elements.get(role.name)
            if previous and previous != fact["element"]:
                bridge["basis_breaks"].append(
                    f"The {role.name} line changed element at "
                    f"{fact['period_end']}: {previous} -> {fact['element']}. The "
                    "series continues on the issuer's successor element and the "
                    "change is disclosed on this observation."
                )
            previous_elements[role.name] = fact["element"]

        if selected:
            distinct = sorted({fact["period_end"] for fact in selected.values()})
            bridge["distinct_period_ends"] = distinct
            bridge["balance_sheet_date"] = distinct[0] if len(distinct) == 1 else None
            bridge_reason: Optional[str] = None
            bridge_reason_detail = ""
            if bridge["components_absent"]:
                bridge_reason = REASON_INCOMPLETE_EV_BRIDGE
                bridge_reason_detail = (
                    f"The bridge is incomplete at {day}: missing "
                    f"{', '.join(bridge['components_absent'])}. The bridge is "
                    "never completed by omission or zero-fill."
                )
            elif len(distinct) != 1:
                bridge_reason = REASON_MIXED_BALANCE_SHEET_PERIODS
                bridge_reason_detail = (
                    f"The bridge at {day} spans more than one balance-sheet "
                    "date: "
                    + ", ".join(
                        f"{name} as of {fact['period_end']}"
                        for name, fact in sorted(selected.items())
                    )
                    + ". The stale component is not carried forward."
                )
            else:
                bridge["complete"] = True
                debt_roles = [
                    role.name
                    for role in config.bridge_roles
                    if role.bridge_sign == BRIDGE_SIGN_DEBT
                ]
                funds_roles = [
                    role.name
                    for role in config.bridge_roles
                    if role.bridge_sign == BRIDGE_SIGN_LIQUID_FUNDS
                ]
                total_debt = sum(selected[name]["value"] for name in debt_roles)
                liquid_funds = sum(selected[name]["value"] for name in funds_roles)
                bridge["total_debt"] = total_debt
                bridge["liquid_funds"] = liquid_funds
                if market_cap is not None:
                    enterprise_value = round(market_cap + total_debt - liquid_funds, 2)
                    bridge["enterprise_value"] = enterprise_value
            bridge["reason_code"] = bridge_reason
            bridge["reason_detail"] = bridge_reason_detail
            # The bridge is part of this lane's numerator only when the
            # numerator is the enterprise value. A market-capitalization lane
            # records the bridge's state on the observation and is not gated
            # by it.
            if (
                config.numerator_kind == "enterprise_value"
                and bridge_reason is not None
                and reason_code is None
            ):
                reason_code = bridge_reason
                reason_detail = bridge_reason_detail

        # -- the figure ---------------------------------------------------------------
        value = None
        if reason_code is None:
            if price is None:
                reason_code = REASON_MISSING_PRICE
                reason_detail = f"No price is observed for trading day {day}."
            elif share is None:
                reason_code = REASON_MISSING_SHARES
                reason_detail = (
                    f"No cover-page share count is knowable at {day}."
                )
            elif denominator_value is None or denominator_value <= 0:
                reason_code = REASON_NON_POSITIVE_DENOMINATOR
                reason_detail = (
                    "The trailing denominator is non-positive "
                    f"({denominator_value}); no multiple is produced from it."
                )
            elif config.numerator_kind == "enterprise_value" and enterprise_value is None:
                reason_code = REASON_INCOMPLETE_EV_BRIDGE
                reason_detail = (
                    f"The enterprise-value bridge produced no figure at {day}."
                )
            else:
                numerator_value = (
                    enterprise_value
                    if config.numerator_kind == "enterprise_value"
                    else market_cap
                )
                value = round(numerator_value / denominator_value, 6)

        observation = ResearchObservation(
            observation_id=f"research-{config.lane_id}-{day}",
            lane_id=config.lane_id,
            issuer_id=config.issuer_id,
            instrument_id=config.instrument_id,
            evaluation_date=day,
            status="AVAILABLE" if value is not None else "UNAVAILABLE",
            metric_id=config.metric_id,
            reason_code=reason_code,
            reason_detail=reason_detail,
            value=value,
            price=price,
            price_split_restoration=price_provenance,
            price_source=price_evidence,
            shares_outstanding=share["shares"] if share else None,
            shares_as_of_date=share["as_of_date"] if share else None,
            shares_accession=share["accession"] if share else None,
            shares_usable_date=share["usable_date"] if share else None,
            shares_source=(
                {
                    **shares_source,
                    "source_url": share.get("source_url") or shares_source.get(
                        "source_url"
                    ),
                    "unit": share["unit"] if share else None,
                    "as_of_date": share["as_of_date"] if share else None,
                    "accession": share["accession"] if share else None,
                }
                if share
                else shares_source
            ),
            market_cap=market_cap,
            enterprise_value=enterprise_value,
            total_debt=total_debt,
            liquid_funds=liquid_funds,
            denominator=denominator_window,
            formula={
                "expression": config.formula_expression,
                "formula_version": config.formula_version,
                "numerator": config.formula_numerator,
                "denominator": config.formula_denominator,
                "operands": {
                    "price": price,
                    "shares_outstanding": share["shares"] if share else None,
                    "market_cap": market_cap,
                    "enterprise_value": enterprise_value,
                    "denominator": denominator_value,
                    "numerator_kind": config.numerator_kind,
                    "numerator_used": (
                        enterprise_value
                        if config.numerator_kind == "enterprise_value"
                        else market_cap
                    ),
                },
            },
            bridge=bridge,
            registry_standing=standing_by_role,
            basis_breaks=list(bridge.get("basis_breaks") or [])
            + _mixed_basis_notes(denominator_window, revived_spans),
            prior_period_revisions=day_revisions,
            point_in_time={
                "rule": "The value in force at an evaluation date is the latest "
                "knowable version; knowability is the filing's usable date.",
                "evaluation_date": day,
                "usable_date_rules": sorted(
                    {filing["usable_date_rule"] for filing in filings_index.values()}
                ),
                "facts_used": "every fact's accession, filed date and usable "
                "date are carried on this observation",
            },
            production_refusal={
                "production_eligible": False,
                "reason": (
                    "A research lane is not a production distribution. The "
                    "registry's standing on the elements this lane read is on "
                    "this observation, and it is why a production lane would "
                    "refuse the same figures."
                ),
            },
            input_set_id=input_set_id,
        )
        observations.append(observation)

    # -- the affected observations of each revision ---------------------------------
    for revision in revisions:
        affected = [
            observation.evaluation_date
            for observation in observations
            if observation.denominator
            and any(
                any(
                    span["role"] == revision["role"]
                    and span["start"] == revision["period_start"]
                    and span["end"] == revision["period_end"]
                    for span in (quarter.get("input_spans") or [])
                )
                for quarter in observation.denominator.get("quarters", [])
            )
            and observation.evaluation_date >= revision["detected_at_evaluation_date"]
        ]
        revision["affected_observation_count"] = len(affected)
        revision["affected_observation_dates"] = affected

    # -- the distribution -------------------------------------------------------------
    valid = [
        (observation.evaluation_date, observation.value)
        for observation in observations
        if observation.value is not None and observation.value > 0
    ]
    excluded = [
        {
            "evaluation_date": observation.evaluation_date,
            "reason_code": observation.reason_code,
            "reason_detail": observation.reason_detail,
        }
        for observation in observations
        if observation.value is None
    ]
    series = [value for _day, value in valid]
    percentiles: Dict[str, Optional[float]] = {}
    mean = None
    std = None
    minimum = None
    maximum = None
    if series:
        mean = round(sum(series) / len(series), 6)
        variance = (
            sum((x - mean) ** 2 for x in series) / (len(series) - 1)
            if len(series) > 1
            else 0.0
        )
        std = round(math.sqrt(variance), 6) if len(series) > 1 else 0.0
        minimum = round(min(series), 6)
        maximum = round(max(series), 6)
        percentiles = compute_distribution_percentiles(series)

    if series and len(series) >= config.min_observations_for_description:
        status = STATUS_RESEARCH_DISTRIBUTION
        distribution_reason = None
        distribution_detail = None
    elif series:
        status = STATUS_RESEARCH_THIN_SAMPLE
        distribution_reason = REASON_NO_DENOMINATOR_WINDOW
        distribution_detail = (
            f"The sample holds {len(series)} valid observations, below the "
            f"{config.min_observations_for_description} the lane reports as a "
            "distribution. The figures are descriptive and are not a valuation "
            "reference at any size."
        )
    else:
        status = STATUS_RESEARCH_UNAVAILABLE
        distribution_reason = REASON_NO_DENOMINATOR_WINDOW
        distribution_detail = (
            "No valid observation could be constructed. Every evaluation date "
            "was excluded, and the exclusions are on the excluded_observations "
            "list with their reasons."
        )

    basis_break_summary: Dict[str, List[str]] = {}
    for observation in observations:
        for note in observation.basis_breaks:
            basis_break_summary.setdefault(note, []).append(
                observation.evaluation_date
            )

    distribution = ResearchDistribution(
        metric_id=config.metric_id,
        metric_label=config.metric_label,
        research_use_label=RESEARCH_USE_LABEL,
        lane_id=config.lane_id,
        issuer_id=config.issuer_id,
        instrument_id=config.instrument_id,
        status=status,
        candidate_metric=config.candidate_metric,
        sample_count=len(series),
        total_evaluations=len(observations),
        period_start=valid[0][0] if valid else None,
        period_end=valid[-1][0] if valid else None,
        min_observations_for_description=config.min_observations_for_description,
        mean=mean,
        std=std,
        min=minimum,
        max=maximum,
        percentiles=percentiles,
        reason_code=distribution_reason,
        reason_detail=distribution_detail,
        excluded_observations=excluded,
        formula={
            "expression": config.formula_expression,
            "formula_version": config.formula_version,
            "numerator": config.formula_numerator,
            "denominator": config.formula_denominator,
        },
        registry_standing=standing_by_role,
        production_refusal={
            "production_eligible": False,
            "statement": (
                "No production reference is created from this distribution, and "
                "none may be created from it."
            ),
        },
        data_limitations=[
            role.note for role in config.roles if role.note
        ]
        + [
            "The capture's acceptance index covers the issuer's periodic "
            "filings only, so a fact first published in another form becomes "
            "knowable in this lane at the next periodic filing that carries it. "
            "The lane therefore never uses a value before it was public, and it "
            "may use a value later than it first became public."
        ],
        prior_period_revisions=revisions,
        basis_breaks={
            note: dates for note, dates in sorted(basis_break_summary.items())
        },
        unit_policy=dict(unit_record),
        input_set_id=input_set_id,
    )

    content_hash = canonical_json_hash(
        {
            "input_set_id": input_set_id,
            "observations": [obs.content_hash for obs in observations],
        }
    )
    return ResearchLaneResult(
        lane_id=config.lane_id,
        issuer_id=config.issuer_id,
        instrument_id=config.instrument_id,
        metric_id=config.metric_id,
        candidate_metric=config.candidate_metric,
        input_set_id=input_set_id,
        content_hash=content_hash,
        distribution=distribution,
        observations=observations,
        capture_manifest={
            "capture_dir": str(directory),
            "issuer": (capture["manifest"].get("issuer") or {}),
            "captured_at": capture["manifest"].get("captured_at"),
            "files": {
                name: {
                    "sha256": entry["sha256"],
                    "role": entry.get("role"),
                    "source": entry.get("source"),
                }
                for name, entry in sorted(capture["files"].items())
            },
            "isolation": isolation,
        },
    )
