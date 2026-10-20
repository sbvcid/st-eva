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

CLOSED_REASON_CODES = frozenset(
    {
        REASON_INSUFFICIENT_QUARTERS,
        REASON_NO_REVENUE_WINDOW,
        REASON_NO_EBITDA_WINDOW,
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
    depreciation_concept: str


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
    depreciation_path = config.data_dir / "depreciation_concept.json"
    for path in (
        config.prices_path,
        config.acceptance_path,
        revenue_path,
        operating_income_path,
        depreciation_path,
    ):
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
    depreciation_payload = json.loads(depreciation_path.read_text(encoding="utf-8"))

    import hashlib

    revenue_sha = hashlib.sha256(revenue_path.read_bytes()).hexdigest()
    operating_income_sha = hashlib.sha256(operating_income_path.read_bytes()).hexdigest()
    depreciation_sha = hashlib.sha256(depreciation_path.read_bytes()).hexdigest()

    fiscal_calendar = build_fiscal_calendar(
        [revenue_payload, operating_income_payload, depreciation_payload],
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
        + concept_spans_from_payload(
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
    )

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
        "depreciation_concept": depreciation_sha,
    }
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

        revenue_window, revenue_reason, revenue_detail = ttm_window_at(
            quarters=revenue_quarters, day=day
        )
        ebitda_window, ebitda_reason, ebitda_detail = ttm_window_at(
            quarters=ebitda_quarters, day=day
        )

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
        if revenue_window is None:
            status = STATUS_UNAVAILABLE
            reason_code = REASON_NO_REVENUE_WINDOW
            reason_detail = revenue_detail
        elif ebitda_window is None:
            status = STATUS_UNAVAILABLE
            reason_code = REASON_NO_EBITDA_WINDOW
            reason_detail = ebitda_detail

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
