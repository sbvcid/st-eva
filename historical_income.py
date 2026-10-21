"""
Production point-in-time quarterly income-statement facts.

Builds the trailing-twelve-month revenue and the trailing-twelve-month EBITDA
a valuation may compute its P/S and EV/EBITDA multiples from, out of filed SEC
income-statement and cash-flow facts -- without the vendor's trailing figures,
whose periods the vendor does not declare.

Methodology (historical-income/1.0):

  I-1: A discrete fiscal quarter is either a directly stated quarter-length
       duration or the difference of two cumulative durations that share one
       fiscal-year start: Q2 = 6M - Q1, Q3 = 9M - 6M, Q4 = FY - 9M. A
       cumulative duration is never summed as if it were a single quarter, and
       a derived quarter says which two durations it came from.
  I-2: A derived quarter is knowable only when both constituent durations are
       knowable, and the value in force at an evaluation date is the latest
       knowable version of each constituent (R-PIT-SUPERSEDE). A filing's
       accounting period end is not its publication date: no fact is used
       before its filing's usable date under the 16:00 ET cutoff rule,
       identical to the historical P/E and P/FCF pipelines.
  I-3: A TTM window is four consecutive fiscal quarters and contains a Q4. It
       anchors on the greatest fiscal-quarter position with knowable evidence
       and never rolls back; an incomplete window is refused, never backfilled,
       and an annual fact never substitutes for a missing quarter.
  I-4: TTM revenue is the sum of the four quarters' revenue. TTM EBITDA is the
       sum of the four quarters' (operating income + depreciation and
       amortization); a quarter that has only one of the two is absent, not
       half a quarter, and a window missing such a quarter is refused.
  I-5: Every quarter carries the accessions, spans, usable dates and the
       formula it was arrived at, so each published figure can be recomputed
       from the evidence rather than taken on trust.

The rules above are the historical P/FCF pipeline's rules (M-2, M-3, M-4) with
the cash-flow statement replaced by the income statement: the difference
between a cumulative duration and a discrete quarter is arithmetic, not a
property of the statement it was filed in.
"""
from __future__ import annotations

import datetime
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from fiscal_calendar import FiscalCalendar, build_fiscal_calendar
from historical_pe import (
    QUARTER_MAX_DAYS,
    QUARTER_MIN_DAYS,
    STATUS_AVAILABLE,
    STATUS_UNAVAILABLE,
    canonical_json_hash,
    resolve_usable_date,
)
from historical_pfcf import (
    DurationSpanEvidence,
    REASON_INSUFFICIENT_QUARTERS,
    concept_spans_from_payload,
    discrete_quarters_for_role,
    in_force_version,
    ttm_window_at,
)

METHODOLOGY = "historical-income/1.0"
LOGIC_VERSION = "historical-income/1.0.0"

# The figures this dataset produces. They are the denominators of two
# multiples, and each is stated on the trailing-twelve-month basis both of
# them need.
METRIC_TTM_REVENUE = "TTM_REVENUE"
METRIC_TTM_EBITDA = "TTM_EBITDA"

# The roles the statements are read under. A role names a quantity, never a
# concept: two concepts of the same quantity are one series only when their
# spans say so.
ROLE_REVENUE = "revenue"
ROLE_OPERATING_INCOME = "operating_income"
ROLE_DEPRECIATION = "depreciation_and_amortization"

# The reason codes the closed set allows.
REASON_INSUFFICIENT_QUARTERS = REASON_INSUFFICIENT_QUARTERS
REASON_NO_REVENUE_WINDOW = "REASON_NO_REVENUE_WINDOW"
REASON_NO_EBITDA_WINDOW = "REASON_NO_EBITDA_WINDOW"
# The issuer has no element that qualifies for the depreciation-and-
# amortization role, so no trailing EBITDA window can exist at any date. It
# is its own condition: neither a missing quarter nor a timing refusal, and
# never filled from an estimate or from the provider.
REASON_NO_QUALIFIED_DA_EVIDENCE = "REASON_NO_QUALIFIED_DA_EVIDENCE"

CLOSED_REASON_CODES = frozenset(
    {
        REASON_INSUFFICIENT_QUARTERS,
        REASON_NO_REVENUE_WINDOW,
        REASON_NO_EBITDA_WINDOW,
        REASON_NO_QUALIFIED_DA_EVIDENCE,
    }
)


def _concept_source_url(issuer_id: str, concept_tag: str) -> str:
    return (
        "https://data.sec.gov/api/xbrl/companyconcept/"
        f"{issuer_id}/us-gaap/{concept_tag}.json"
    )


@dataclass(frozen=True)
class HistoricalIncomeConfig:
    """
    Where one issuer's filed income-statement facts live.

    The concept tags are named here rather than inferred, because a concept is
    a filer's own choice of element: the dataset says which element it read,
    and the registry says whether that element is this metric for this issuer.

    `depreciation_concept` is the element that fills the
    depreciation-and-amortization role, and it is optional because a filer
    may report no element that qualifies for that role. When it is absent the
    role is left empty and no trailing EBITDA is constructed: an element that
    carries depreciation alone is not this metric, and a dataset that filled
    the role with it would publish an EBITDA that is not one.

    `depreciation_evidence_path` and its two companions hold the evidence an
    issuer does report about depreciation when that evidence is not the role:
    the file is kept as source evidence, digested so the dataset's identity
    covers it, and named with what it actually is. It never contributes to
    an EBITDA figure.
    """

    ticker: str
    issuer_id: str
    entity_name: str
    fye_month: int
    data_dir: Path
    prices_path: Path
    acceptance_path: Path
    revenue_concept: str
    operating_income_concept: str
    depreciation_concept: Optional[str]
    depreciation_evidence_path: Optional[Path] = None
    depreciation_evidence_concept: Optional[str] = None
    depreciation_evidence_note: Optional[str] = None


ISSUER_CONFIGS: Dict[str, HistoricalIncomeConfig] = {
    "AAPL": HistoricalIncomeConfig(
        ticker="AAPL",
        issuer_id="CIK0000320193",
        entity_name="Apple Inc.",
        fye_month=9,
        data_dir=Path(__file__).resolve().parent / "data" / "historical_income" / "AAPL",
        prices_path=Path(__file__).resolve().parent
        / "data"
        / "historical_pe"
        / "AAPL"
        / "daily_prices.json",
        acceptance_path=Path(__file__).resolve().parent
        / "data"
        / "historical_pe"
        / "AAPL"
        / "filing_acceptance_evidence.json",
        revenue_concept="RevenueFromContractWithCustomerExcludingAssessedTax",
        operating_income_concept="OperatingIncomeLoss",
        # Apple reports one cash-flow line labelled "Depreciation and
        # amortization" and carries it on this element. The element's own
        # definition also covers depleting assets, so the registry maps it to
        # the metric for Apple alone, and the qualification checks that scope
        # before the figure is used.
        depreciation_concept="DepreciationDepletionAndAmortization",
    ),
    "MSFT": HistoricalIncomeConfig(
        ticker="MSFT",
        issuer_id="CIK0000789019",
        entity_name="Microsoft Corporation",
        fye_month=6,
        data_dir=Path(__file__).resolve().parent / "data" / "historical_income" / "MSFT",
        prices_path=Path(__file__).resolve().parent
        / "data"
        / "historical_pe"
        / "MSFT"
        / "daily_prices.json",
        acceptance_path=Path(__file__).resolve().parent
        / "data"
        / "historical_pe"
        / "MSFT"
        / "filing_acceptance_evidence.json",
        revenue_concept="RevenueFromContractWithCustomerExcludingAssessedTax",
        operating_income_concept="OperatingIncomeLoss",
        # Microsoft's depreciation and amortization.
        #
        # Microsoft has no element that carries depreciation and amortization
        # for this metric. Its cash-flow line "Depreciation, amortization, and
        # other" is carried on the company-specific element
        # msft:DepreciationAmortizationAndOther, which the company-concept
        # API does not serve and which the core registry does not accept --
        # it bundles "other" items and is company-custom. The element the
        # acquisition path can reach, us-gaap:Depreciation, is the property
        # and equipment note's depreciation expense: depreciation alone,
        # without the amortization the metric includes.
        #
        # So the role is left empty. The trailing EBITDA window is not
        # constructed for any date, and no EBITDA figure is published for
        # Microsoft from this dataset. The depreciation evidence is kept as
        # source evidence below, named with what it is, and it contributes to
        # nothing.
        depreciation_concept=None,
        depreciation_evidence_path=Path(__file__).resolve().parent
        / "data"
        / "historical_income"
        / "MSFT"
        / "depreciation_expense_concept.json",
        depreciation_evidence_concept="us-gaap:Depreciation",
        depreciation_evidence_note=(
            "The property and equipment note's depreciation expense, "
            "disclosed as 'depreciation expense was $34.3 billion, $22.0 "
            "billion, and $15.2 billion' for fiscal 2026, 2025 and 2024. It "
            "is depreciation alone: it excludes the amortization of "
            "intangible assets and the other items the cash-flow line "
            "aggregates, so it is not the depreciation-and-amortization "
            "metric and it never contributes to an EBITDA figure. It is "
            "retained as source evidence of what Microsoft reports about "
            "depreciation."
        ),
    ),
    "NKE": HistoricalIncomeConfig(
        ticker="NKE",
        issuer_id="CIK0000320193",
        entity_name="NIKE, Inc.",
        fye_month=5,
        data_dir=Path(__file__).resolve().parent / "data" / "historical_income" / "NKE",
        prices_path=Path(__file__).resolve().parent
        / "data"
        / "historical_pe"
        / "NKE"
        / "daily_prices.json",
        acceptance_path=Path(__file__).resolve().parent
        / "data"
        / "historical_pe"
        / "NKE"
        / "filing_acceptance_evidence.json",
        revenue_concept="RevenueFromContractWithCustomerExcludingAssessedTax",
        operating_income_concept="OperatingIncomeLoss",
        # Nike reports one cash-flow line labelled "Depreciation and
        # amortization" and carries it on this element. The element's own
        # definition also covers depletion, so the registry maps it to the
        # metric for Nike alone and not as a market-wide EXACT mapping --
        # the same treatment Apple's own element receives. Nike reports no
        # depletable assets, so for this issuer the line is depreciation and
        # amortization.
        depreciation_concept="DepreciationDepletionAndAmortization",
    ),
    "AEP": HistoricalIncomeConfig(
        ticker="AEP",
        issuer_id="CIK0000004904",
        entity_name="American Electric Power Company",
        fye_month=12,
        data_dir=Path(__file__).resolve().parent / "data" / "historical_income" / "AEP",
        prices_path=Path(__file__).resolve().parent
        / "data"
        / "historical_pe"
        / "AEP"
        / "daily_prices.json",
        acceptance_path=Path(__file__).resolve().parent
        / "data"
        / "historical_pe"
        / "AEP"
        / "filing_acceptance_evidence.json",
        # AEP's revenue and operating income are on the standard elements, and
        # its revenue element is the one the registry already accepts for the
        # revenue metric.
        revenue_concept="Revenues",
        operating_income_concept="OperatingIncomeLoss",
        # AEP's cash-flow line "Depreciation and Amortization" is carried on
        # us-gaap:UtilitiesOperatingExpenseDepreciationAndAmortization, a
        # utility-sector element: the amortization of nuclear fuel is a
        # separate cash-flow line, so the line itself is depreciation and
        # amortization and nothing else. The element's name says utilities
        # operating expense, so the registry maps it to the metric for AEP
        # alone and not as a market-wide EXACT mapping -- the same treatment
        # Apple's own element receives.
        depreciation_concept="UtilitiesOperatingExpenseDepreciationAndAmortization",
    ),
}


@dataclass
class HistoricalIncomeObservation:
    """One dated evaluation of the issuer's trailing revenue and EBITDA."""

    observation_id: str
    issuer_id: str
    instrument_id: str
    evaluation_date: str
    status: str
    reason_code: Optional[str] = None
    reason_detail: Optional[str] = None
    ttm_revenue: Optional[Dict[str, Any]] = None
    ttm_ebitda: Optional[Dict[str, Any]] = None
    # The structured refusal of a trailing window, per role. The reason code,
    # the fiscal positions the window required, and the ones it could not
    # fill, so a consumer can tell a window that had no knowable quarter from
    # a window that had some and could not complete one -- without parsing
    # the prose.
    window_rejection: Optional[Dict[str, Any]] = None
    currency: str = "USD"
    methodology: str = METHODOLOGY
    logic_version: str = LOGIC_VERSION
    input_set_id: str = ""
    content_hash: str = ""

    def __post_init__(self) -> None:
        if self.reason_code is not None and self.reason_code not in CLOSED_REASON_CODES:
            raise ValueError(
                f"reason_code {self.reason_code!r} is not in the closed set"
            )

    def compute_content_hash(self) -> str:
        data = asdict(self)
        data.pop("content_hash", None)
        return canonical_json_hash(data)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class HistoricalIncomeResult:
    """The package the income-statement pipeline returns."""

    issuer_id: str
    instrument_id: str
    input_set_id: str
    concept_tags: Dict[str, str] = field(default_factory=dict)
    observations: List[HistoricalIncomeObservation] = field(default_factory=list)
    current_snapshot: Optional[HistoricalIncomeObservation] = None
    content_hash: str = ""
    summary_notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "issuer_id": self.issuer_id,
            "instrument_id": self.instrument_id,
            "input_set_id": self.input_set_id,
            "content_hash": self.content_hash,
            "concept_tags": dict(self.concept_tags),
            "observations": [obs.to_dict() for obs in self.observations],
            "current_snapshot": (
                self.current_snapshot.to_dict() if self.current_snapshot else None
            ),
            "summary_notes": list(self.summary_notes),
        }


def _format_positions(positions: Sequence[Mapping[str, Any]]) -> str:
    """The fiscal positions a window could not fill, named as FY and quarter."""
    return ", ".join(
        f"FY{position['fiscal_year']} Q{position['fiscal_quarter']}"
        for position in positions
    )


def _window_rejection(
    refusal: Optional[Mapping[str, Any]],
    *,
    metric_label: str,
    day: str,
) -> Optional[Dict[str, Any]]:
    """
    One refused trailing window, described in this dataset's own words.

    The shared window helper is metric-agnostic and its prose names the
    quantity it was first written for. A consumer of this dataset needs the
    refusal to name the quantity it asked about, and needs the refusal's
    parts in a form it can reason about, so the prose is written here, per
    role, and the parts are carried alongside it.
    """
    if refusal is None:
        return None
    missing = list(refusal.get("positions_missing") or [])
    anchor = refusal.get("anchor")
    stated_detail = refusal.get("detail")
    if stated_detail:
        # A refusal that carries its own statement keeps it: the reason an
        # issuer has no qualifying evidence is not a shortage of quarters, and
        # a description of quarters would misdescribe it.
        detail = stated_detail
    elif refusal.get("no_quarter_knowable"):
        detail = (
            f"No discrete quarterly {metric_label} is knowable at evaluation "
            f"date {day}."
        )
    else:
        detail = (
            f"The four-quarter {metric_label} window ending at "
            f"FY{anchor['fiscal_year']} Q{anchor['fiscal_quarter']} is missing "
            f"positions: {_format_positions(missing)}."
        )
    return {
        "reason_code": refusal.get("reason_code"),
        "metric": metric_label,
        "no_quarter_knowable": bool(refusal.get("no_quarter_knowable")),
        "anchor": anchor,
        "positions_required": list(refusal.get("positions_required") or []),
        "positions_missing": missing,
        "detail": detail,
    }


def _quarter_payload(
    quarter: Mapping[str, Any],
    *,
    value_key: str,
    derivation: str,
    inputs: Sequence[Mapping[str, Any]],
    extra: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """One quarter of a window, with everything needed to recompute it."""
    payload = {
        "period_end": quarter["period_end"],
        "fiscal_year": quarter["fiscal_year"],
        "fiscal_quarter": quarter["fiscal_quarter"],
        "identity_source": quarter.get("identity_source"),
        "value": quarter[value_key],
        "currency": quarter["currency"],
        "formula": derivation,
        "knowable_from": quarter["knowable_from"],
        "inputs": list(inputs),
    }
    if extra:
        payload.update(dict(extra))
    return payload


def _window_payload(
    window: Mapping[str, Any],
    *,
    total: float,
    value_key: str,
    derivation: str,
    currency: str,
    extra: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """The TTM window of one figure, as the payload carries it."""
    payload = {
        "anchor": window["anchor"],
        "positions": window["positions"],
        "value": total,
        "currency": currency,
        "derivation": derivation,
        "window_end": window["anchor"]["period_end"],
        "quarters": [
            {**quarter, "currency": currency} for quarter in window["quarters"]
        ],
    }
    if extra:
        payload.update(dict(extra))
    return payload


def _with_fiscal_identity(
    quarters: Mapping[datetime.date, Dict[str, Any]],
    fiscal_calendar: FiscalCalendar,
    formula: str,
) -> Dict[datetime.date, Dict[str, Any]]:
    """
    The quarters that carry the issuer's own fiscal identity.

    A span end with no issuer declaration identifies no fiscal period, so the
    quarter is left out rather than assigned to a neighbouring one.
    """
    identified: Dict[datetime.date, Dict[str, Any]] = {}
    for end_d, quarter in quarters.items():
        identity = fiscal_calendar.identity_for(end_d.isoformat())
        if identity is None:
            continue
        identified[end_d] = {
            **quarter,
            "period_end": end_d.isoformat(),
            "formula": formula,
            "fiscal_year": identity.fiscal_year,
            "fiscal_quarter": identity.fiscal_quarter,
            "identity_source": identity.identity_source,
        }
    return identified


def _ebitda_quarters(
    operating_income_quarters: Mapping[datetime.date, Dict[str, Any]],
    depreciation_quarters: Mapping[datetime.date, Dict[str, Any]],
    fiscal_calendar: FiscalCalendar,
    currency: str,
) -> Dict[datetime.date, Dict[str, Any]]:
    """
    The quarters an EBITDA can be computed for.

    Operating income and depreciation have to cover the same period and be
    knowable at the same time; a quarter that has only one of the two is
    absent rather than half a quarter.
    """
    combined: Dict[datetime.date, Dict[str, Any]] = {}
    for end_d in sorted(set(operating_income_quarters) | set(depreciation_quarters)):
        operating_income = operating_income_quarters.get(end_d)
        depreciation = depreciation_quarters.get(end_d)
        if operating_income is None or depreciation is None:
            continue
        identity = fiscal_calendar.identity_for(end_d.isoformat())
        if identity is None:
            continue
        combined[end_d] = {
            "fiscal_year": identity.fiscal_year,
            "fiscal_quarter": identity.fiscal_quarter,
            "identity_source": identity.identity_source,
            "period_end": end_d.isoformat(),
            "operating_income": operating_income["value"],
            "depreciation_and_amortization": depreciation["value"],
            "ebitda": operating_income["value"] + depreciation["value"],
            "currency": currency,
            "formula": "operating income + depreciation and amortization",
            "knowable_from": max(
                operating_income["knowable_from"], depreciation["knowable_from"]
            ),
            "operating_income_derivation": operating_income["derivation"],
            "depreciation_derivation": depreciation["derivation"],
            "operating_income_inputs": operating_income["inputs"],
            "depreciation_inputs": depreciation["inputs"],
        }
    return combined


def load_issuer_historical_income(
    config: HistoricalIncomeConfig,
) -> HistoricalIncomeResult:
    """
    Load a promoted income-statement dataset and execute the pipeline.

    The price series and the acceptance index are the canonical historical P/E
    dataset's files, read by path: one trading calendar serves every
    reconstruction, so a fact's usable date is the same here as it is beside
    the earnings and cash-flow figures.
    """
    revenue_path = config.data_dir / "revenue_concept.json"
    operating_income_path = config.data_dir / "operating_income_concept.json"
    # The depreciation-and-amortization role has a file only when the issuer
    # has an element that qualifies for it. An issuer that reports
    # depreciation alone keeps that evidence under
    # `depreciation_evidence_path`, and the role stays empty.
    depreciation_path = config.data_dir / "depreciation_concept.json"
    has_depreciation_role = config.depreciation_concept is not None
    required_paths = [
        config.prices_path,
        config.acceptance_path,
        revenue_path,
        operating_income_path,
    ]
    if has_depreciation_role:
        required_paths.append(depreciation_path)
    if config.depreciation_evidence_path is not None:
        required_paths.append(config.depreciation_evidence_path)
    for path in required_paths:
        if not path.exists():
            raise FileNotFoundError(f"Missing required file: {path}")

    # -- acceptance index, identical rule to the historical P/E loader --
    price_payload = json.loads(config.prices_path.read_bytes().decode("utf-8"))[
        "chart"
    ]["result"][0]
    trading_days = sorted(
        datetime.datetime.fromtimestamp(stamp, datetime.timezone.utc).date().isoformat()
        for stamp in price_payload["timestamp"]
    )
    acceptance_evidence = json.loads(config.acceptance_path.read_text(encoding="utf-8"))
    filings_index: Dict[str, Dict[str, Any]] = {}
    for row in acceptance_evidence:
        acceptance_dt = datetime.datetime.fromisoformat(
            row["acceptance_datetime_header_et"]
        )
        usable_d, usable_r = resolve_usable_date(acceptance_dt, trading_days)
        filings_index[row["accession"]] = {
            "form": row["form"],
            "acceptance_datetime": acceptance_dt.isoformat(),
            "usable_date": usable_d,
            "usable_date_rule": usable_r,
            "period_end": row["period_end"],
        }

    # -- concepts --
    revenue_payload = json.loads(revenue_path.read_text(encoding="utf-8"))
    operating_income_payload = json.loads(operating_income_path.read_text(encoding="utf-8"))

    import hashlib

    revenue_sha = hashlib.sha256(revenue_path.read_bytes()).hexdigest()
    operating_income_sha = hashlib.sha256(operating_income_path.read_bytes()).hexdigest()
    # The evidence an issuer holds about depreciation, when that evidence is
    # not the role. It is read so the fiscal calendar sees the same filed
    # duration facts as before -- the calendar is a property of the issuer's
    # reporting, not of a role -- and it is digested so the dataset's identity
    # covers what the dataset holds. It is not read into any role and
    # contributes to no figure.
    depreciation_evidence_payload: Optional[Dict[str, Any]] = None
    depreciation_evidence_sha: Optional[str] = None
    if config.depreciation_evidence_path is not None:
        depreciation_evidence_payload = json.loads(
            config.depreciation_evidence_path.read_text(encoding="utf-8")
        )
        depreciation_evidence_sha = hashlib.sha256(
            config.depreciation_evidence_path.read_bytes()
        ).hexdigest()

    # The fiscal calendar is derived from the issuer's filed duration facts.
    # Which role each concept fills is a separate question, and a concept that
    # does not fill a role still says when the issuer's periods end.
    calendar_payloads = [revenue_payload, operating_income_payload]
    if has_depreciation_role:
        depreciation_payload = json.loads(depreciation_path.read_text(encoding="utf-8"))
        calendar_payloads.append(depreciation_payload)
    if depreciation_evidence_payload is not None:
        calendar_payloads.append(depreciation_evidence_payload)

    fiscal_calendar = build_fiscal_calendar(
        calendar_payloads,
        filings_index,
        units=("USD",),
    )

    spans: List[DurationSpanEvidence] = (
        concept_spans_from_payload(
            payload=revenue_payload,
            unit="USD",
            role=ROLE_REVENUE,
            concept_tag=config.revenue_concept,
            issuer_id=config.issuer_id,
            filings_index=filings_index,
            content_sha256=revenue_sha,
            source_url=_concept_source_url(config.issuer_id, config.revenue_concept),
        )
        + concept_spans_from_payload(
            payload=operating_income_payload,
            unit="USD",
            role=ROLE_OPERATING_INCOME,
            concept_tag=config.operating_income_concept,
            issuer_id=config.issuer_id,
            filings_index=filings_index,
            content_sha256=operating_income_sha,
            source_url=_concept_source_url(
                config.issuer_id, config.operating_income_concept
            ),
        )
    )
    if has_depreciation_role:
        depreciation_payload = json.loads(depreciation_path.read_text(encoding="utf-8"))
        depreciation_sha = hashlib.sha256(depreciation_path.read_bytes()).hexdigest()
        spans += concept_spans_from_payload(
            payload=depreciation_payload,
            unit="USD",
            role=ROLE_DEPRECIATION,
            concept_tag=config.depreciation_concept,
            issuer_id=config.issuer_id,
            filings_index=filings_index,
            content_sha256=depreciation_sha,
            source_url=_concept_source_url(
                config.issuer_id, config.depreciation_concept
            ),
        )
    else:
        depreciation_sha = None

    spans_by_key: Dict[Tuple[str, str, str], List[DurationSpanEvidence]] = {}
    for span in spans:
        spans_by_key.setdefault((span.role, span.start, span.end), []).append(span)
    for versions in spans_by_key.values():
        versions.sort(
            key=lambda item: (item.usable_date, item.acceptance_datetime, item.accession)
        )

    input_manifest = {
        "issuer_config": {
            "ticker": config.ticker,
            "issuer_id": config.issuer_id,
            "fye_month": config.fye_month,
        },
        "prices": hashlib.sha256(config.prices_path.read_bytes()).hexdigest(),
        "acceptances": hashlib.sha256(config.acceptance_path.read_bytes()).hexdigest(),
        "revenue_concept": revenue_sha,
        "operating_income_concept": operating_income_sha,
    }
    if has_depreciation_role:
        input_manifest["depreciation_concept"] = depreciation_sha
    if depreciation_evidence_sha is not None:
        # The evidence is part of what the dataset holds, so it is part of
        # what the dataset is.
        input_manifest["depreciation_evidence"] = depreciation_evidence_sha
    input_set_id = canonical_json_hash(input_manifest)

    evaluation_dates = sorted({filing["usable_date"] for filing in filings_index.values()})

    observations: List[HistoricalIncomeObservation] = []
    for day in evaluation_dates:
        spans_in_force = {
            key: in_force_version(versions, day)
            for key, versions in spans_by_key.items()
        }
        spans_in_force = {
            key: version for key, version in spans_in_force.items() if version is not None
        }

        revenue_quarters = _with_fiscal_identity(
            discrete_quarters_for_role(
                spans_in_force=spans_in_force, role=ROLE_REVENUE
            ),
            fiscal_calendar,
            "revenue for the fiscal quarter, as the filer stated it",
        )
        operating_income_quarters = discrete_quarters_for_role(
            spans_in_force=spans_in_force, role=ROLE_OPERATING_INCOME
        )
        depreciation_quarters = discrete_quarters_for_role(
            spans_in_force=spans_in_force, role=ROLE_DEPRECIATION
        )
        ebitda_quarters = _ebitda_quarters(
            operating_income_quarters, depreciation_quarters, fiscal_calendar, "USD"
        )

        revenue_window, revenue_reason, revenue_detail, revenue_refusal = ttm_window_at(
            quarters=revenue_quarters, day=day
        )
        ebitda_window, ebitda_reason, ebitda_detail, ebitda_refusal = ttm_window_at(
            quarters=ebitda_quarters, day=day
        )
        if not has_depreciation_role:
            # The role is empty because the issuer has no element that
            # qualifies for it. The refusal says so, and it says it in the
            # issuer's terms: which element it does report, and why that
            # element is not this metric. It is not a shortage of quarters and
            # not a timing refusal, and it is not filled from anywhere else.
            ebitda_reason = REASON_NO_QUALIFIED_DA_EVIDENCE
            ebitda_detail = (
                "This issuer has no element that qualifies for the "
                "depreciation-and-amortization role"
                + (
                    f". What it does report is "
                    f"{config.depreciation_evidence_concept}: "
                    f"{config.depreciation_evidence_note.rstrip('.')}."
                    if config.depreciation_evidence_concept
                    else ""
                )
                + " No trailing EBITDA is constructed from it, from an "
                "estimate, or from any other source, so no trailing EBITDA "
                "window exists at this date."
            )
            ebitda_refusal = {
                "reason_code": REASON_NO_QUALIFIED_DA_EVIDENCE,
                "no_quarter_knowable": True,
                "anchor": None,
                "positions_required": [],
                "positions_missing": [],
                "detail": ebitda_detail,
            }

        revenue_payload_out: Optional[Dict[str, Any]] = None
        if revenue_window is not None:
            revenue_payload_out = _window_payload(
                revenue_window,
                total=sum(quarter["value"] for quarter in revenue_window["quarters"]),
                value_key="value",
                derivation="sum of four discrete quarterly revenue figures",
                currency="USD",
            )

        ebitda_payload_out: Optional[Dict[str, Any]] = None
        if ebitda_window is not None:
            ebitda_payload_out = _window_payload(
                ebitda_window,
                total=sum(quarter["ebitda"] for quarter in ebitda_window["quarters"]),
                value_key="ebitda",
                derivation=(
                    "sum of four discrete quarterly EBITDA figures, each the "
                    "quarter's operating income plus its depreciation and "
                    "amortization"
                ),
                currency="USD",
            )

        status = STATUS_AVAILABLE
        reason_code: Optional[str] = None
        reason_detail: Optional[str] = None
        window_rejection: Optional[Dict[str, Any]] = None
        revenue_rejection = _window_rejection(
            revenue_refusal, metric_label="revenue", day=day
        )
        ebitda_rejection = _window_rejection(
            ebitda_refusal, metric_label="EBITDA", day=day
        )
        if revenue_window is None:
            status = STATUS_UNAVAILABLE
            reason_code = REASON_NO_REVENUE_WINDOW
            reason_detail = (
                revenue_rejection["detail"] if revenue_rejection else revenue_detail
            )
        elif ebitda_window is None:
            status = STATUS_UNAVAILABLE
            reason_code = (
                REASON_NO_QUALIFIED_DA_EVIDENCE
                if not has_depreciation_role
                else REASON_NO_EBITDA_WINDOW
            )
            reason_detail = (
                ebitda_rejection["detail"] if ebitda_rejection else ebitda_detail
            )
        refused = {
            role: rejection
            for role, rejection in (
                ("revenue", revenue_rejection),
                ("ebitda", ebitda_rejection),
            )
            if rejection is not None
        }
        if refused:
            window_rejection = refused

        observation = HistoricalIncomeObservation(
            observation_id=f"income-{config.ticker}-{day}",
            issuer_id=config.issuer_id,
            instrument_id=config.ticker,
            evaluation_date=day,
            status=status,
            reason_code=reason_code,
            reason_detail=reason_detail,
            ttm_revenue=revenue_payload_out,
            ttm_ebitda=ebitda_payload_out,
            window_rejection=window_rejection,
            currency="USD",
            input_set_id=input_set_id,
        )
        observation.content_hash = observation.compute_content_hash()
        observations.append(observation)

    result = HistoricalIncomeResult(
        issuer_id=config.issuer_id,
        instrument_id=config.ticker,
        input_set_id=input_set_id,
        concept_tags={
            "revenue": config.revenue_concept,
            "operating_income": config.operating_income_concept,
            "depreciation_and_amortization": config.depreciation_concept,
        },
        observations=observations,
        current_snapshot=observations[-1] if observations else None,
    )
    result.content_hash = canonical_json_hash(
        {
            "input_set_id": result.input_set_id,
            "observations": [obs.content_hash for obs in observations],
        }
    )
    return result
