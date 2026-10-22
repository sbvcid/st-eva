"""The research issuer configuration.

This module is the only place an issuer's elements, roles, formulas and unit
policy are written down. The capture builder and the research lanes both read
it, so an issuer is described once.

An invalid configuration is an error. Nothing here falls back to a built-in
issuer: a configuration that does not describe a usable issuer says so, and
the caller is told which field is wrong.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from research_lane import (
    BRIDGE_GROUPS,
    BRIDGE_SIGN_DEBT,
    BRIDGE_SIGN_LIQUID_FUNDS,
    BRIDGE_SIGN_NONE,
    CHANGE_RE_TAG,
    CHANGE_SCOPE_CHANGE,
    FORMULA_BRIDGE_COMPONENT,
    FORMULA_DEPRECIATION,
    FORMULA_DENOMINATOR,
    FORMULA_OPERATING_INCOME,
    FORMULA_SHARES,
    ResearchLaneConfig,
    ResearchLaneResult,
    ResearchRole,
    ResearchUnitPolicy,
    assert_research_isolation,
    load_research_lane,
)

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "data" / "research_issuers.json"

SCHEMA_VERSION = 1

FORMULA_ROLES = (
    FORMULA_DENOMINATOR,
    FORMULA_OPERATING_INCOME,
    FORMULA_DEPRECIATION,
    FORMULA_BRIDGE_COMPONENT,
    FORMULA_SHARES,
)
BRIDGE_SIGNS = (BRIDGE_SIGN_DEBT, BRIDGE_SIGN_LIQUID_FUNDS, BRIDGE_SIGN_NONE)
ELEMENT_CHANGE_KINDS = (CHANGE_RE_TAG, CHANGE_SCOPE_CHANGE)
NUMERATOR_KINDS = ("market_cap", "enterprise_value")


class IssuerConfigurationError(ValueError):
    """A configuration that does not describe a usable issuer."""


@dataclass(frozen=True)
class IssuerSettings:
    """One issuer, as the configuration describes it."""

    issuer_id: str
    ticker: str
    entity_name: str
    fiscal_year_end: str
    fye_month: int
    capture: Dict[str, Any]
    unit_policy: ResearchUnitPolicy
    roles: Tuple[ResearchRole, ...]
    lanes: Tuple[ResearchLaneConfig, ...]
    capture_dir: Path

    def lane(self, lane_id: str) -> ResearchLaneConfig:
        for config in self.lanes:
            if config.lane_id == lane_id:
                return config
        raise KeyError(f"{self.ticker} has no lane {lane_id!r}")


def _require(document: Mapping[str, Any], field: str, where: str) -> Any:
    if field not in document or document[field] in (None, "", [], {}):
        raise IssuerConfigurationError(f"{where} names no {field!r}")
    return document[field]


def _fiscal_month(fiscal_year_end: str) -> int:
    """The month a filer's year ends in, from an `MM-DD` or an `MMDD` form."""
    text = str(fiscal_year_end).strip()
    if "-" in text:
        head = text.split("-", 1)[0]
    else:
        head = text[:2]
    if not head.isdigit():
        raise IssuerConfigurationError(
            f"the fiscal year end {fiscal_year_end!r} does not name a month"
        )
    month = int(head)
    if not 1 <= month <= 12:
        raise IssuerConfigurationError(
            f"the fiscal year end {fiscal_year_end!r} names no month"
        )
    return month


def _unit_policy(document: Mapping[str, Any], where: str) -> ResearchUnitPolicy:
    for field in (
        "filing_unit",
        "filing_currency",
        "price_currency",
        "share_unit",
    ):
        _require(document, field, where)
    scale = document.get("scale", 1.0)
    try:
        scale = float(scale)
    except (TypeError, ValueError) as error:
        raise IssuerConfigurationError(
            f"{where} names a scale that is not a number: {scale!r}"
        ) from error
    if scale <= 0:
        raise IssuerConfigurationError(
            f"{where} names a scale that is not positive: {scale}"
        )
    return ResearchUnitPolicy(
        filing_unit=document["filing_unit"],
        filing_currency=document["filing_currency"],
        price_currency=document["price_currency"],
        share_unit=document["share_unit"],
        scale=scale,
        scale_basis=document.get("scale_basis", "") or "",
        fx_rule=document.get("fx_rule"),
    )


def _roles(
    document: Mapping[str, Any],
    capture_elements: Mapping[str, Any],
    where: str,
) -> Tuple[ResearchRole, ...]:
    roles: List[ResearchRole] = []
    seen = set()
    for entry in document:
        name = _require(entry, "name", where)
        if name in seen:
            raise IssuerConfigurationError(f"{where} declares the role {name!r} twice")
        seen.add(name)
        capture_role = entry.get("capture_role", name)
        if capture_role not in capture_elements:
            raise IssuerConfigurationError(
                f"{where} declares the role {name!r}, which reads the capture "
                f"role {capture_role!r}, and the capture holds no such role"
            )
        formula_role = _require(entry, "formula_role", f"the role {name!r}")
        if formula_role not in FORMULA_ROLES:
            raise IssuerConfigurationError(
                f"the role {name!r} has an unknown formula role {formula_role!r}; "
                f"it must be one of {FORMULA_ROLES}"
            )
        bridge_sign = entry.get("bridge_sign", BRIDGE_SIGN_NONE)
        if bridge_sign not in BRIDGE_SIGNS:
            raise IssuerConfigurationError(
                f"the role {name!r} has an unknown bridge sign {bridge_sign!r}"
            )
        bridge_group = entry.get("bridge_group")
        if bridge_group is not None and bridge_group not in BRIDGE_GROUPS:
            raise IssuerConfigurationError(
                f"the role {name!r} has an unknown bridge group {bridge_group!r}; "
                f"it must be one of {BRIDGE_GROUPS}"
            )
        change_kind = entry.get("element_change_kind", CHANGE_RE_TAG)
        if change_kind not in ELEMENT_CHANGE_KINDS:
            raise IssuerConfigurationError(
                f"the role {name!r} has an unknown element change kind "
                f"{change_kind!r}"
            )
        element = capture_elements[capture_role]
        roles.append(
            ResearchRole(
                name=name,
                taxonomy=element["taxonomy"],
                elements=tuple(element["elements"]),
                formula_role=formula_role,
                capture_role=capture_role,
                registry_metric_id=entry.get("registry_metric_id"),
                element_change_kind=change_kind,
                bridge_sign=bridge_sign,
                bridge_group=bridge_group,
                note=entry.get("note", "") or "",
            )
        )
    if not roles:
        raise IssuerConfigurationError(f"{where} declares no role")
    return tuple(roles)


def _lanes(
    document: Mapping[str, Any],
    roles: Tuple[ResearchRole, ...],
    unit_policy: ResearchUnitPolicy,
    issuer: Mapping[str, Any],
    where: str,
    seen_lane_ids: set,
    seen_metric_ids: set,
) -> Tuple[ResearchLaneConfig, ...]:
    by_name = {role.name: role for role in roles}
    shares_roles = [role for role in roles if role.formula_role == FORMULA_SHARES]
    if len(shares_roles) != 1:
        raise IssuerConfigurationError(
            f"{where} must declare exactly one role with the formula role "
            f"{FORMULA_SHARES}, and it declares {len(shares_roles)}"
        )
    lanes: List[ResearchLaneConfig] = []
    for entry in document:
        lane_id = _require(entry, "lane_id", where)
        metric_id = _require(entry, "metric_id", f"the lane {lane_id!r}")
        if lane_id in seen_lane_ids:
            raise IssuerConfigurationError(
                f"the lane id {lane_id!r} is declared twice"
            )
        seen_lane_ids.add(lane_id)
        if metric_id in seen_metric_ids:
            raise IssuerConfigurationError(
                f"the research metric id {metric_id!r} is declared twice"
            )
        seen_metric_ids.add(metric_id)
        numerator_kind = entry.get("numerator_kind", "market_cap")
        if numerator_kind not in NUMERATOR_KINDS:
            raise IssuerConfigurationError(
                f"the lane {lane_id!r} has an unknown numerator kind "
                f"{numerator_kind!r}"
            )
        denominator_roles = tuple(entry.get("denominator_roles") or ())
        bridge_roles = tuple(entry.get("bridge_roles") or ())
        for name in denominator_roles + bridge_roles:
            if name not in by_name:
                raise IssuerConfigurationError(
                    f"the lane {lane_id!r} names the role {name!r}, which the "
                    "issuer does not declare"
                )
        minimum = int(entry.get("min_observations_for_description", 20))
        if minimum < 1:
            raise IssuerConfigurationError(
                f"the lane {lane_id!r} names a descriptive threshold of "
                f"{minimum}, which is not a sample"
            )
        lane_roles = tuple(
            by_name[name]
            for name in denominator_roles + bridge_roles
            if name in by_name
        ) + (shares_roles[0],)
        lanes.append(
            ResearchLaneConfig(
                lane_id=lane_id,
                issuer_id=issuer["issuer_id"],
                instrument_id=issuer["ticker"],
                entity_name=issuer["entity_name"],
                fye_month=_fiscal_month(issuer["fiscal_year_end"]),
                capture_dir=issuer["capture_dir"],
                metric_id=metric_id,
                metric_label=_require(entry, "metric_label", f"the lane {lane_id!r}"),
                research_purpose=entry.get("research_purpose", "") or "",
                formula_expression=_require(
                    entry, "formula_expression", f"the lane {lane_id!r}"
                ),
                formula_numerator=entry.get("formula_numerator", "") or "",
                formula_denominator=entry.get("formula_denominator", "") or "",
                formula_version=entry.get("formula_version", "") or "research-multiples/1.0",
                denominator_roles=denominator_roles,
                roles=lane_roles,
                numerator_kind=numerator_kind,
                candidate_metric=bool(entry.get("candidate_metric", True)),
                min_observations_for_description=minimum,
                unit_policy=unit_policy,
            )
        )
    if not lanes:
        raise IssuerConfigurationError(f"{where} declares no lane")
    return tuple(lanes)


def load_issuer_settings(path: Optional[Path] = None) -> Tuple[IssuerSettings, ...]:
    """
    The configured issuers, validated.

    Every check that can be made on the configuration is made here, and
    every failure says which field is wrong. Nothing is repaired silently.
    """
    config_path = Path(path) if path else CONFIG_PATH
    if not config_path.exists():
        raise IssuerConfigurationError(
            f"the research issuer configuration is missing at {config_path}"
        )
    document = json.loads(config_path.read_text(encoding="utf-8"))
    version = document.get("schema_version")
    if version != SCHEMA_VERSION:
        raise IssuerConfigurationError(
            f"the research issuer configuration declares the schema version "
            f"{version!r}, and this module reads {SCHEMA_VERSION}"
        )
    issuers = document.get("issuers")
    if not issuers:
        raise IssuerConfigurationError(
            "the research issuer configuration declares no issuer"
        )

    settings: List[IssuerSettings] = []
    seen_issuer_ids: set = set()
    seen_tickers: set = set()
    seen_lane_ids: set = set()
    seen_metric_ids: set = set()
    for issuer in issuers:
        ticker = _require(issuer, "ticker", "an issuer")
        where = f"the issuer {ticker!r}"
        issuer_id = _require(issuer, "issuer_id", where)
        if issuer_id in seen_issuer_ids:
            raise IssuerConfigurationError(
                f"the issuer id {issuer_id!r} is declared twice"
            )
        seen_issuer_ids.add(issuer_id)
        if ticker in seen_tickers:
            raise IssuerConfigurationError(
                f"the ticker {ticker!r} is declared twice"
            )
        seen_tickers.add(ticker)

        capture = _require(issuer, "capture", where)
        capture_elements = _require(capture, "elements", f"{where}'s capture")
        for role_name, element in capture_elements.items():
            if not isinstance(element, Mapping):
                raise IssuerConfigurationError(
                    f"{where}'s capture role {role_name!r} is not an element "
                    "table"
                )
            _require(element, "taxonomy", f"{where}'s capture role {role_name!r}")
            tags = _require(element, "elements", f"{where}'s capture role {role_name!r}")
            if not isinstance(tags, list) or not tags:
                raise IssuerConfigurationError(
                    f"{where}'s capture role {role_name!r} names no element"
                )

        unit_policy = _unit_policy(
            _require(issuer, "unit_policy", where), f"{where}'s unit policy"
        )
        roles = _roles(
            _require(issuer, "roles", where), capture_elements, f"{where}'s roles"
        )
        capture_dir = ROOT / capture["directory"]
        issuer_record = {
            "issuer_id": issuer_id,
            "ticker": ticker,
            "entity_name": _require(issuer, "entity_name", where),
            "fiscal_year_end": _require(issuer, "fiscal_year_end", where),
            "capture_dir": capture_dir,
        }
        lanes = _lanes(
            _require(issuer, "lanes", where),
            roles,
            unit_policy,
            issuer_record,
            f"{where}'s lanes",
            seen_lane_ids,
            seen_metric_ids,
        )
        settings.append(
            IssuerSettings(
                issuer_id=issuer_id,
                ticker=ticker,
                entity_name=issuer_record["entity_name"],
                fiscal_year_end=issuer_record["fiscal_year_end"],
                fye_month=_fiscal_month(issuer_record["fiscal_year_end"]),
                capture=capture,
                unit_policy=unit_policy,
                roles=roles,
                lanes=lanes,
                capture_dir=capture_dir,
            )
        )

    # The research metrics may not take a production name.
    try:
        assert_research_isolation(sorted(seen_metric_ids))
    except ValueError as error:
        raise IssuerConfigurationError(str(error)) from error

    return tuple(settings)


def settings_for_ticker(
    ticker: str, path: Optional[Path] = None
) -> IssuerSettings:
    """One configured issuer."""
    for settings in load_issuer_settings(path):
        if settings.ticker == ticker:
            return settings
    raise IssuerConfigurationError(
        f"no research issuer is configured for the ticker {ticker!r}"
    )


def candidate_lane_ids(path: Optional[Path] = None) -> Tuple[str, ...]:
    """
    The lanes a user may choose.

    A diagnostic lane is not a candidate, and a lane whose capture has not
    been built cannot be computed, so it is not offered either.
    """
    ids: List[str] = []
    for settings in load_issuer_settings(path):
        for lane in settings.lanes:
            if lane.candidate_metric and lane.capture_dir.exists():
                ids.append(lane.lane_id)
    return tuple(ids)


def all_lane_ids(path: Optional[Path] = None) -> Tuple[str, ...]:
    """Every configured lane, the diagnostics included."""
    ids: List[str] = []
    for settings in load_issuer_settings(path):
        ids.extend(lane.lane_id for lane in settings.lanes)
    return tuple(ids)


def build_lane_results(
    issuer_ids: Optional[Sequence[str]] = None, path: Optional[Path] = None
) -> Dict[str, ResearchLaneResult]:
    """
    The lanes' results, by lane id.

    A lane whose capture has not been built is not computed, and the reason
    is available from the settings; the caller decides what to do about an
    issuer that has no capture yet.
    """
    results: Dict[str, ResearchLaneResult] = {}
    for settings in load_issuer_settings(path):
        if issuer_ids is not None and settings.ticker not in issuer_ids:
            continue
        for lane in settings.lanes:
            if not lane.capture_dir.exists():
                continue
            results[lane.lane_id] = load_research_lane(lane)
    return results


from typing import Sequence  # noqa: E402  (used in the signature above)


def lane_configs(path: Optional[Path] = None) -> Tuple[ResearchLaneConfig, ...]:
    """Every configured lane, the diagnostics included."""
    configs: List[ResearchLaneConfig] = []
    for settings in load_issuer_settings(path):
        configs.extend(settings.lanes)
    return tuple(configs)


def config_for_lane(
    lane_id: str, path: Optional[Path] = None
) -> ResearchLaneConfig:
    """One configured lane."""
    for config in lane_configs(path):
        if config.lane_id == lane_id:
            return config
    raise IssuerConfigurationError(
        f"no research lane named {lane_id!r} is configured"
    )


def write_research_outputs(
    output_dir: Path, include_lineage: bool = False
) -> Dict[str, Any]:
    """Write the research tree: one summary per lane and an index.

    The output is a research artifact. It is written under the caller's
    directory and nowhere else; no production path is touched.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    results = list(build_lane_results().values())
    settings = load_issuer_settings()
    issuer_of = {
        lane.lane_id: item.ticker
        for item in settings
        for lane in item.lanes
    }
    index: Dict[str, Any] = {
        "dataset": "research lane results",
        "purpose": (
            "Research use only. No figure here is a production reference, and "
            "nothing here is read by the production runner, the Investment "
            "Context or the Archive."
        ),
        "issuers": {
            item.ticker: {
                "issuer_id": item.issuer_id,
                "entity_name": item.entity_name,
                "fiscal_year_end": item.fiscal_year_end,
            }
            for item in settings
        },
        "methodology": "research-multiples/1.0",
        "logic_version": "research-multiples/1.0.0",
        "lanes": {},
        "candidate_lane_ids": list(candidate_lane_ids()),
        "diagnostic_lane_ids": [
            result.lane_id for result in results if not result.candidate_metric
        ],
    }
    for result in results:
        payload = result.to_dict() if include_lineage else _summary_payload(result)
        path = output_dir / f"{result.lane_id}.json"
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        index["lanes"][result.lane_id] = {
            "metric_id": result.metric_id,
            "candidate_metric": result.candidate_metric,
            "status": result.distribution.status,
            "sample_count": result.distribution.sample_count,
            "total_evaluations": result.distribution.total_evaluations,
            "median": result.distribution.percentiles.get("median"),
            "mean": result.distribution.mean,
            "std": result.distribution.std,
            "period_start": result.distribution.period_start,
            "period_end": result.distribution.period_end,
            "rejection_counts": _rejection_counts(result.distribution),
            "prior_period_revisions": len(
                result.distribution.prior_period_revisions
            ),
            "input_set_id": result.input_set_id,
            "content_hash": result.content_hash,
            "file": path.name,
            "issuer": issuer_of.get(result.lane_id),
        }
    (output_dir / "manifest.json").write_text(
        json.dumps(index, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return index




def _summary_payload(result: ResearchLaneResult) -> Dict[str, Any]:
    """The committed summary of one lane.

    Every evaluation date is listed with its value or its refusal, so a
    reader can see the whole sample, and the statistics can be recomputed
    from it. The full observation lineage is not committed: it is large, and
    the lane regenerates it exactly from the capture.
    """
    payload = result.to_dict()
    payload["observations"] = [
        {
            "evaluation_date": observation.evaluation_date,
            "status": observation.status,
            "value": observation.value,
            "reason_code": observation.reason_code,
            "price": observation.price,
            "shares_outstanding": observation.shares_outstanding,
            "market_cap": observation.market_cap,
            "enterprise_value": observation.enterprise_value,
            "denominator": (
                observation.denominator.get("value")
                if observation.denominator
                else None
            ),
            "content_hash": observation.content_hash,
        }
        for observation in result.observations
    ]
    payload["basis_breaks"] = payload["distribution"]["basis_breaks"]
    payload["observation_lineage"] = (
        "The committed summary carries one line per evaluation date. The full "
        "lineage -- every operand, accession, element, period, unit and "
        "usable date -- is regenerated exactly by the lane from the capture, "
        "whose files are hashed in the capture manifest."
    )
    return payload


def _rejection_counts(distribution: Any) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for item in distribution.excluded_observations:
        code = item["reason_code"]
        counts[code] = counts.get(code, 0) + 1
    return dict(sorted(counts.items()))
