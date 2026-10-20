"""
Production point-in-time historical P/S and EV/EBITDA reference distributions.

Builds the sales and enterprise-value multiples a valuation may use as
historical references, out of the filed trailing revenue and trailing EBITDA
the income-statement dataset already reconstructs, paired with contemporaneous
as-traded prices, cover-page shares outstanding, and filed balance-sheet
components -- without the vendor's bands, whose periods and sample counts the
vendor does not declare.

Methodology (historical-multiples/1.0):

  X-1: The denominators are the income-statement dataset's trailing windows
       (historical-income/1.0), reused by path: TTM revenue for P/S and TTM
       EBITDA for EV/EBITDA. A trailing figure that window refused stays
       refused here; this dataset never recomputes or repairs a denominator.
  X-2: A fact is knowable only from its filing's usable date under the 16:00
       ET cutoff rule, identical to the historical P/E, P/FCF and income
       pipelines. A fact whose filing is not in the acceptance index has no
       knowability evidence in this dataset and is skipped. The value in force
       at an evaluation date is the latest knowable version of each component.
  X-3: Market capitalization is the as-traded close on the evaluation date
       times the latest knowable cover-page shares outstanding, the same
       numerator rule as the historical P/FCF reconstruction; cover-page
       counts are never split-adjusted and pair with the as-traded close.
  X-4: The enterprise value is a filed-component bridge: market capitalization
       plus total debt (long-term debt non-current + long-term debt current +
       commercial paper) minus liquid funds (cash and cash equivalents +
       current marketable securities). Every component must be knowable at the
       evaluation date; a date with any component missing has no EV, and the
       bridge is never completed by omission, substitution or zero-fill. The
       bridge remains a partial statement of enterprise value even when
       complete (it omits leases, non-current investments and off-balance
       sheet claims), and every observation says so.
  X-5: P/S = market capitalization / TTM revenue. EV/EBITDA = enterprise
       value / TTM EBITDA. A non-positive denominator produces no multiple.
       All figures are USD as filed; a mixed-currency figure is refused, never
       converted.
  X-6: The evaluation dates are the income dataset's evaluation dates -- the
       periodic filing usable dates -- the same cadence as the production
       historical P/E, P/FCF and income distributions, not a continuous daily
       trading history.
  X-7: The reference gate is the same >= 20 qualifying observations rule as
       every other production distribution. A thinner sample stays descriptive
       and is never a scenario exit multiple.
  X-8: Every observation carries the accessions, usable dates, price, share
       fact and balance-sheet components it was computed from, so each
       published multiple can be independently recomputed. The dataset's
       input_set_id digests every result-affecting input file, so a rebuild
       that reads the same committed dataset reads the same identity.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from historical_income import (
    ISSUER_CONFIGS as INCOME_ISSUER_CONFIGS,
    HistoricalIncomeConfig,
    load_issuer_historical_income,
)
from historical_pe import (
    MIN_OBSERVATIONS_FOR_REFERENCE,
    STATUS_AVAILABLE,
    STATUS_INSUFFICIENT_OBSERVATIONS,
    STATUS_UNAVAILABLE,
    STATUS_USABLE_FOR_REFERENCE,
    UTC,
    canonical_json_hash,
    compute_distribution_percentiles,
    restore_as_traded_close,
    resolve_usable_date,
)

METHODOLOGY = "historical-multiples/1.0"
LOGIC_VERSION = "historical-multiples/1.0.0"
FORMULA_VERSION = "historical-multiples/1.0"

# The metrics this dataset produces.
METRIC_PS_RATIO = "P_S_RATIO_REFERENCE"
METRIC_EV_EBITDA_RATIO = "EV_EBITDA_RATIO_REFERENCE"

# The EV bridge components a complete filed bridge needs, and the two sums
# they feed. A date missing any one component has no EV (X-4).
EV_BRIDGE_COMPONENTS: Tuple[str, ...] = (
    "cash",
    "marketable_securities_current",
    "commercial_paper",
    "long_term_debt_noncurrent",
    "long_term_debt_current",
)

# Reason codes. The closed set mirrors the shared vocabulary where the
# conditions coincide and names the multiples-specific refusals explicitly.
REASON_MISSING_PRICE = "REASON_MISSING_PRICE"
REASON_MISSING_SHARES = "REASON_MISSING_SHARES"
REASON_MISSING_REVENUE_WINDOW = "REASON_MISSING_REVENUE_WINDOW"
REASON_MISSING_EBITDA_WINDOW = "REASON_MISSING_EBITDA_WINDOW"
REASON_INCOMPLETE_EV_BRIDGE = "REASON_INCOMPLETE_EV_BRIDGE"
REASON_NON_POSITIVE_DENOMINATOR = "REASON_NON_POSITIVE_DENOMINATOR"
REASON_INSUFFICIENT_OBSERVATIONS = "REASON_INSUFFICIENT_OBSERVATIONS"

CLOSED_REASON_CODES = frozenset(
    {
        REASON_MISSING_PRICE,
        REASON_MISSING_SHARES,
        REASON_MISSING_REVENUE_WINDOW,
        REASON_MISSING_EBITDA_WINDOW,
        REASON_INCOMPLETE_EV_BRIDGE,
        REASON_NON_POSITIVE_DENOMINATOR,
        REASON_INSUFFICIENT_OBSERVATIONS,
    }
)


def _sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _concept_source_url(issuer_id: str, concept_tag: str) -> str:
    return (
        "https://data.sec.gov/api/xbrl/companyconcept/"
        f"{issuer_id}/us-gaap/{concept_tag}.json"
    )


@dataclass(frozen=True)
class HistoricalMultiplesConfig:
    """
    Where one issuer's multiples inputs live.

    The price series, acceptance index and cover-page shares are the canonical
    historical P/E and P/FCF datasets' files, read by path so one trading
    calendar and one share series govern every reconstruction. The
    balance-sheet concepts are this dataset's own companyconcept payloads, and
    the denominators are the income dataset's trailing windows, executed from
    its own config.
    """

    ticker: str
    issuer_id: str
    entity_name: str
    fye_month: int
    data_dir: Path
    prices_path: Path
    acceptance_path: Path
    shares_path: Path
    income_config: HistoricalIncomeConfig
    # role -> concept tag, in EV_BRIDGE_COMPONENTS order
    balance_sheet_concepts: Dict[str, str]


ISSUER_CONFIGS: Dict[str, HistoricalMultiplesConfig] = {
    "AAPL": HistoricalMultiplesConfig(
        ticker="AAPL",
        issuer_id="CIK0000320193",
        entity_name="Apple Inc.",
        fye_month=9,
        data_dir=Path(__file__).resolve().parent
        / "data"
        / "historical_multiples"
        / "AAPL",
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
        shares_path=Path(__file__).resolve().parent
        / "data"
        / "historical_pfcf"
        / "AAPL"
        / "shares_outstanding_concept.json",
        income_config=INCOME_ISSUER_CONFIGS["AAPL"],
        balance_sheet_concepts={
            "cash": "CashAndCashEquivalentsAtCarryingValue",
            "marketable_securities_current": "MarketableSecuritiesCurrent",
            "commercial_paper": "CommercialPaper",
            "long_term_debt_noncurrent": "LongTermDebtNoncurrent",
            "long_term_debt_current": "LongTermDebtCurrent",
        },
    ),
}


@dataclass
class BalanceSheetFact:
    """One balance-sheet instant with its knowability evidence."""

    component: str
    concept_tag: str
    period_end: str
    value: float
    currency: str
    accession: str
    form: str
    usable_date: str
    usable_date_rule: str
    source_url: str
    content_sha256: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ShareCountFact:
    """One cover-page share count with its knowability evidence."""

    shares: float
    as_of_date: str
    accession: str
    form: str
    usable_date: str
    usable_date_rule: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class HistoricalMultiplesObservation:
    """One dated evaluation carrying both multiples and their full evidence."""

    observation_id: str
    issuer_id: str
    instrument_id: str
    evaluation_date: str
    status: str
    reason_code: Optional[str] = None
    reason_detail: Optional[str] = None
    ps_status: str = STATUS_UNAVAILABLE
    ps_ratio: Optional[float] = None
    ev_status: str = STATUS_UNAVAILABLE
    ev_ebitda_ratio: Optional[float] = None
    ps_reason_code: Optional[str] = None
    ps_reason_detail: Optional[str] = None
    ev_reason_code: Optional[str] = None
    ev_reason_detail: Optional[str] = None
    price: Optional[float] = None
    price_currency: str = "USD"
    shares_outstanding: Optional[float] = None
    shares_as_of_date: Optional[str] = None
    shares_accession: Optional[str] = None
    market_cap: Optional[float] = None
    enterprise_value: Optional[float] = None
    total_debt: Optional[float] = None
    liquid_funds: Optional[float] = None
    ttm_revenue: Optional[float] = None
    ttm_ebitda: Optional[float] = None
    ev_bridge: Dict[str, Any] = field(default_factory=dict)
    ps_formula: Dict[str, Any] = field(default_factory=dict)
    ev_formula: Dict[str, Any] = field(default_factory=dict)
    source_lineage: Dict[str, Any] = field(default_factory=dict)
    methodology: str = METHODOLOGY
    logic_version: str = LOGIC_VERSION
    input_set_id: str = ""
    content_hash: str = ""

    def __post_init__(self) -> None:
        for code in (self.reason_code, self.ps_reason_code, self.ev_reason_code):
            if code is not None and code not in CLOSED_REASON_CODES:
                raise ValueError(
                    f"reason_code {code!r} is not in the closed set"
                )

    def compute_content_hash(self) -> str:
        data = asdict(self)
        data.pop("content_hash", None)
        return canonical_json_hash(data)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MultiplesDistribution:
    """Distribution statistics and the reference gate for one metric."""

    metric_id: str
    status: str = STATUS_UNAVAILABLE
    usable_for_reference: bool = False
    sample_count: int = 0
    total_evaluations: int = 0
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    min_observations_required: int = MIN_OBSERVATIONS_FOR_REFERENCE
    mean: Optional[float] = None
    std: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None
    percentiles: Dict[str, Optional[float]] = field(default_factory=dict)
    reason_code: Optional[str] = None
    reason_detail: Optional[str] = None
    excluded_observations: List[Dict[str, Any]] = field(default_factory=list)
    observations: List[Dict[str, Any]] = field(default_factory=list)
    sampling_cadence: str = "PERIODIC_FILING_USABLE_DATES"
    evaluation_schedule_description: str = (
        "Evaluated on periodic SEC filing usable dates shared with the "
        "income-statement reconstruction; not a continuous daily trading "
        "history."
    )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class HistoricalMultiplesResult:
    """The package the multiples pipeline returns."""

    issuer_id: str
    instrument_id: str
    input_set_id: str
    distributions: Dict[str, MultiplesDistribution] = field(default_factory=dict)
    observations: List[HistoricalMultiplesObservation] = field(default_factory=list)
    concept_tags: Dict[str, str] = field(default_factory=dict)
    content_hash: str = ""
    summary_notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "issuer_id": self.issuer_id,
            "instrument_id": self.instrument_id,
            "input_set_id": self.input_set_id,
            "content_hash": self.content_hash,
            "methodology": METHODOLOGY,
            "logic_version": LOGIC_VERSION,
            "formula_version": FORMULA_VERSION,
            "concept_tags": dict(self.concept_tags),
            "distributions": {
                metric: dist.to_dict()
                for metric, dist in self.distributions.items()
            },
            "observations": [obs.to_dict() for obs in self.observations],
            "summary_notes": list(self.summary_notes),
        }


def production_multiples_summary(
    payload: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """
    The compact state of a production historical multiples payload.

    The same statement the historical P/E summary makes, for the two
    multiples: each distribution's identity, eligibility, sample counts,
    sample period, percentiles and the reason when it is unavailable or
    under-qualified. It changes nothing about eligibility: the same gate that
    decides the scenarios decides what this summary reports.
    """
    if not payload:
        return None

    distributions = payload.get("distributions") or {}
    summaries: Dict[str, Any] = {}
    for metric, dist in distributions.items():
        percentiles = dist.get("percentiles") or {}
        summaries[metric] = {
            "metric_id": dist.get("metric_id"),
            "status": dist.get("status"),
            "usable_for_reference": bool(dist.get("usable_for_reference")),
            "sample_count": dist.get("sample_count"),
            "total_evaluations": dist.get("total_evaluations"),
            "min_observations_required": dist.get("min_observations_required"),
            "period_start": dist.get("period_start"),
            "period_end": dist.get("period_end"),
            "mean": dist.get("mean"),
            "std": dist.get("std"),
            "min": dist.get("min"),
            "max": dist.get("max"),
            "percentiles": {
                key: value for key, value in percentiles.items() if value is not None
            },
            "excluded_observation_count": len(dist.get("excluded_observations") or []),
            "reason_code": dist.get("reason_code"),
            "reason_detail": dist.get("reason_detail"),
            "sampling_cadence": dist.get("sampling_cadence"),
            "evaluation_schedule_description": dist.get(
                "evaluation_schedule_description"
            ),
        }

    return {
        "issuer_id": payload.get("issuer_id"),
        "instrument_id": payload.get("instrument_id"),
        "input_set_id": payload.get("input_set_id"),
        "content_hash": payload.get("content_hash"),
        "methodology": payload.get("methodology"),
        "logic_version": payload.get("logic_version"),
        "formula_version": payload.get("formula_version"),
        "distributions": summaries,
    }


def compute_multiples_distribution(
    observations: Sequence[HistoricalMultiplesObservation],
    *,
    metric: str,
    values: Sequence[Tuple[str, Optional[float]]],
    min_observations: int = MIN_OBSERVATIONS_FOR_REFERENCE,
) -> MultiplesDistribution:
    """
    One metric's distribution over its qualifying dated values, with the
    shared sufficiency gate.
    """
    valid = [(day, value) for day, value in values if value is not None and value > 0]
    excluded = [
        {
            "evaluation_date": day,
            "value": value,
        }
        for day, value in values
        if value is None or value <= 0
    ]

    sample_count = len(valid)
    if sample_count == 0:
        return MultiplesDistribution(
            metric_id=metric,
            status=STATUS_UNAVAILABLE,
            usable_for_reference=False,
            sample_count=0,
            total_evaluations=len(values),
            min_observations_required=min_observations,
            reason_code=REASON_INSUFFICIENT_OBSERVATIONS,
            reason_detail=(
                "Zero valid point-in-time observations could be constructed."
            ),
            excluded_observations=excluded,
        )

    series = [value for _, value in valid]
    period_start = valid[0][0]
    period_end = valid[-1][0]

    mean_val = round(sum(series) / sample_count, 6)
    variance = (
        sum((x - mean_val) ** 2 for x in series) / (sample_count - 1)
        if sample_count > 1
        else 0.0
    )
    std_val = round(math.sqrt(variance), 6) if sample_count > 1 else 0.0
    percentiles = compute_distribution_percentiles(series)

    if sample_count >= min_observations:
        status = STATUS_USABLE_FOR_REFERENCE
        usable_for_reference = True
        reason_code = None
        reason_detail = None
    else:
        status = STATUS_INSUFFICIENT_OBSERVATIONS
        usable_for_reference = False
        reason_code = REASON_INSUFFICIENT_OBSERVATIONS
        reason_detail = (
            f"The sample holds {sample_count} valid observations, below the "
            f"{min_observations} required to establish an authoritative "
            "reference distribution. Descriptive statistics (median "
            f"{percentiles.get('median')}) are reported for review but are "
            "ineligible as scenario exit multiples."
        )

    return MultiplesDistribution(
        metric_id=metric,
        status=status,
        usable_for_reference=usable_for_reference,
        sample_count=sample_count,
        total_evaluations=len(values),
        period_start=period_start,
        period_end=period_end,
        min_observations_required=min_observations,
        mean=mean_val,
        std=std_val,
        min=round(min(series), 6),
        max=round(max(series), 6),
        percentiles=percentiles,
        reason_code=reason_code,
        reason_detail=reason_detail,
        excluded_observations=excluded,
        observations=[
            {
                "evaluation_date": day,
                "value": round(value, 6),
            }
            for day, value in valid
        ],
    )


def _facts_from_concept_payload(
    *,
    payload: Mapping[str, Any],
    component: str,
    issuer_id: str,
    filings_index: Mapping[str, Dict[str, Any]],
    content_sha256: str,
) -> List[BalanceSheetFact]:
    """Balance-sheet instants from one companyconcept payload (X-2)."""
    facts: List[BalanceSheetFact] = []
    tag = str(payload.get("tag") or "")
    for unit, rows in (payload.get("units") or {}).items():
        for row in rows:
            accession = row.get("accn")
            filing_meta = filings_index.get(accession)
            if filing_meta is None:
                # A fact whose filing is not in the index has no knowability
                # evidence in this dataset and is skipped (X-2).
                continue
            facts.append(
                BalanceSheetFact(
                    component=component,
                    concept_tag=tag,
                    period_end=str(row.get("end") or ""),
                    value=float(row["val"]),
                    currency=unit,
                    accession=str(accession),
                    form=filing_meta["form"],
                    usable_date=filing_meta["usable_date"],
                    usable_date_rule=filing_meta["usable_date_rule"],
                    source_url=_concept_source_url(issuer_id, tag),
                    content_sha256=content_sha256,
                )
            )
    facts.sort(
        key=lambda f: (f.usable_date, f.period_end, f.accession)
    )
    return facts


def _in_force_fact(
    facts: Sequence[BalanceSheetFact], day: str
) -> Optional[BalanceSheetFact]:
    """
    The balance-sheet value in force at an evaluation date: the latest
    knowable version of the component (X-2). Versions are ordered by
    (usable_date, period_end, accession), so the last knowable one wins.
    """
    in_force: Optional[BalanceSheetFact] = None
    for fact in facts:
        if fact.usable_date <= day:
            in_force = fact
        else:
            break
    return in_force


def _in_force_share(
    shares: Sequence[ShareCountFact], day: str
) -> Optional[ShareCountFact]:
    in_force: Optional[ShareCountFact] = None
    for share in shares:
        if share.usable_date <= day:
            in_force = share
        else:
            break
    return in_force


def load_issuer_historical_multiples(
    config: HistoricalMultiplesConfig,
    min_observations: int = MIN_OBSERVATIONS_FOR_REFERENCE,
) -> HistoricalMultiplesResult:
    """
    Load a promoted multiples dataset and execute the pipeline.

    Nothing is fetched and nothing is written. The price series, the
    acceptance index and the cover-page shares are read by path from the
    canonical historical P/E and P/FCF datasets, so one trading calendar and
    one share series serve every reconstruction; the denominators are the
    income dataset's own trailing windows, executed from its own config.
    """
    concept_paths: Dict[str, Path] = {
        component: config.data_dir / f"{component}_concept.json"
        for component in config.balance_sheet_concepts
    }
    required = [config.prices_path, config.acceptance_path, config.shares_path]
    required += list(concept_paths.values())
    for path in required:
        if not path.exists():
            raise FileNotFoundError(f"Missing required file: {path}")

    # -- prices: the canonical chart payload, restored to as-traded closes --
    price_payload = json.loads(config.prices_path.read_bytes().decode("utf-8"))[
        "chart"
    ]["result"][0]
    meta = price_payload.get("meta", {})
    granularity = meta.get("dataGranularity")
    if granularity != "1d":
        raise ValueError(
            f"Price data granularity must be '1d', got '{granularity}'; "
            "quarterly or monthly aggregates cannot serve as daily prices"
        )
    quote = price_payload["indicators"]["quote"][0]
    bars = {
        datetime.datetime.fromtimestamp(stamp, UTC)
        .date()
        .isoformat(): float(quote["close"][idx])
        for idx, stamp in enumerate(price_payload["timestamp"])
        if quote["close"][idx] is not None
    }
    trading_days = sorted(bars.keys())
    splits = price_payload.get("events", {}).get("splits", {})
    prices_map: Dict[str, Dict[str, Any]] = {}
    for day, close in bars.items():
        restored_close, _, _ = restore_as_traded_close(close, day, splits)
        prices_map[day] = {
            "close": round(restored_close, 4),
            "currency": "USD",
            "accounting_basis": "as_traded",
        }

    # -- acceptance index, identical rule to the other production loaders --
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

    # -- shares: cover-page counts from the historical P/FCF dataset --
    shares_payload = json.loads(config.shares_path.read_text(encoding="utf-8"))
    shares_sha = _sha256_of(config.shares_path)
    share_facts: List[ShareCountFact] = []
    for unit, rows in (shares_payload.get("units") or {}).items():
        for row in rows:
            accession = row.get("accn")
            filing_meta = filings_index.get(accession)
            if filing_meta is None:
                continue
            share_facts.append(
                ShareCountFact(
                    shares=float(row["val"]),
                    as_of_date=str(row.get("end") or ""),
                    accession=str(accession),
                    form=filing_meta["form"],
                    usable_date=filing_meta["usable_date"],
                    usable_date_rule=filing_meta["usable_date_rule"],
                )
            )
    share_facts.sort(key=lambda s: (s.usable_date, s.as_of_date, s.accession))

    # -- balance-sheet concepts: this dataset's own companyconcept payloads --
    component_facts: Dict[str, List[BalanceSheetFact]] = {}
    concept_shas: Dict[str, str] = {}
    concept_tags: Dict[str, str] = {}
    for component, tag in config.balance_sheet_concepts.items():
        path = concept_paths[component]
        payload = json.loads(path.read_text(encoding="utf-8"))
        sha = _sha256_of(path)
        concept_shas[component] = sha
        concept_tags[component] = str(payload.get("tag") or tag)
        component_facts[component] = _facts_from_concept_payload(
            payload=payload,
            component=component,
            issuer_id=config.issuer_id,
            filings_index=filings_index,
            content_sha256=sha,
        )

    # -- denominators: the income dataset's own trailing windows (X-1) --
    income_result = load_issuer_historical_income(config.income_config)

    # -- identity: digest every result-affecting input (X-8) --
    input_manifest = {
        "issuer_config": {
            "ticker": config.ticker,
            "issuer_id": config.issuer_id,
            "fye_month": config.fye_month,
        },
        "prices": _sha256_of(config.prices_path),
        "acceptances": _sha256_of(config.acceptance_path),
        "shares_outstanding_concept": shares_sha,
        "balance_sheet_concepts": concept_shas,
        "income_dataset": {
            "input_set_id": income_result.input_set_id,
            "content_hash": income_result.content_hash,
        },
        "min_observations": min_observations,
    }
    input_set_id = canonical_json_hash(input_manifest)

    observations: List[HistoricalMultiplesObservation] = []
    for income_obs in income_result.observations:
        day = income_obs.evaluation_date
        price = prices_map.get(day)
        share = _in_force_share(share_facts, day)
        components_in_force: Dict[str, BalanceSheetFact] = {}
        for component, facts in component_facts.items():
            fact = _in_force_fact(facts, day)
            if fact is not None:
                components_in_force[component] = fact

        market_cap: Optional[float] = None
        ps_ratio: Optional[float] = None
        ev_value: Optional[float] = None
        ev_ebitda_ratio: Optional[float] = None

        ps_reason: Optional[str] = None
        ps_detail: Optional[str] = None
        ev_reason: Optional[str] = None
        ev_detail: Optional[str] = None

        # The trailing windows the income dataset produced (X-1): a window it
        # refused stays refused here.
        revenue_window = income_obs.ttm_revenue
        ebitda_window = income_obs.ttm_ebitda
        ttm_revenue = (
            float(revenue_window["value"]) if revenue_window is not None else None
        )
        ttm_ebitda = (
            float(ebitda_window["value"]) if ebitda_window is not None else None
        )

        if revenue_window is None:
            ps_reason = REASON_MISSING_REVENUE_WINDOW
            ps_detail = (
                "The income-statement dataset carries no TTM revenue window "
                f"at {day} ({income_obs.reason_code or 'refused'}); this "
                "dataset never recomputes or repairs a denominator."
            )
        if ebitda_window is None:
            ev_reason = REASON_MISSING_EBITDA_WINDOW
            ev_detail = (
                "The income-statement dataset carries no TTM EBITDA window "
                f"at {day} ({income_obs.reason_code or 'refused'}); this "
                "dataset never recomputes or repairs a denominator."
            )

        if price is None:
            ps_reason = ps_reason or REASON_MISSING_PRICE
            ps_detail = ps_detail or (
                f"No historical price evidence is observed for trading day {day}."
            )
            ev_reason = ev_reason or REASON_MISSING_PRICE
            ev_detail = ev_detail or (
                f"No historical price evidence is observed for trading day {day}."
            )
        elif share is None:
            ps_reason = ps_reason or REASON_MISSING_SHARES
            ps_detail = ps_detail or (
                f"No cover-page shares outstanding is knowable at {day}."
            )
            ev_reason = ev_reason or REASON_MISSING_SHARES
            ev_detail = ev_detail or (
                f"No cover-page shares outstanding is knowable at {day}."
            )
        else:
            market_cap = round(price["close"] * share.shares, 2)

            if ps_reason is None:
                if ttm_revenue is None or ttm_revenue <= 0:
                    ps_reason = REASON_NON_POSITIVE_DENOMINATOR
                    ps_detail = (
                        f"TTM revenue is non-positive ({ttm_revenue}); a "
                        "negative or zero denominator produces no P/S multiple."
                    )
                else:
                    ps_ratio = round(market_cap / ttm_revenue, 6)

            # ---- EV bridge (X-4): every component knowable, or no EV ----
            present = sorted(components_in_force)
            absent = [c for c in EV_BRIDGE_COMPONENTS if c not in components_in_force]
            bridge_complete = not absent
            total_debt: Optional[float] = None
            liquid_funds: Optional[float] = None
            if bridge_complete:
                total_debt = sum(
                    components_in_force[c].value
                    for c in (
                        "long_term_debt_noncurrent",
                        "long_term_debt_current",
                        "commercial_paper",
                    )
                )
                liquid_funds = sum(
                    components_in_force[c].value
                    for c in ("cash", "marketable_securities_current")
                )
                ev_value = round(market_cap + total_debt - liquid_funds, 2)

            ev_bridge = {
                "components_present": present,
                "components_absent": absent,
                "complete": bridge_complete,
                "components": {
                    component: fact.to_dict()
                    for component, fact in components_in_force.items()
                },
                "total_debt": total_debt,
                "liquid_funds": liquid_funds,
                "definition": (
                    "market capitalization + total debt (long-term debt "
                    "non-current + long-term debt current + commercial paper) "
                    "- liquid funds (cash and cash equivalents + current "
                    "marketable securities)"
                ),
                "completeness_note": (
                    "Every filed component this bridge names is knowable at "
                    "the evaluation date. The bridge remains a partial "
                    "statement of enterprise value: it omits operating leases "
                    "under ASC 842, non-current investments and off-balance "
                    "sheet commitments, and is never presented as the whole "
                    "of enterprise value."
                ),
            }

            if ev_reason is None and not bridge_complete:
                ev_reason = REASON_INCOMPLETE_EV_BRIDGE
                ev_detail = (
                    "The filed EV bridge is incomplete at "
                    f"{day}: missing {', '.join(absent)}. Enterprise value is "
                    "never completed by omission, substitution or zero-fill."
                )
            elif ev_reason is None:
                if ttm_ebitda is None or ttm_ebitda <= 0:
                    ev_reason = REASON_NON_POSITIVE_DENOMINATOR
                    ev_detail = (
                        f"TTM EBITDA is non-positive ({ttm_ebitda}); a "
                        "negative or zero denominator produces no EV/EBITDA "
                        "multiple."
                    )
                else:
                    ev_ebitda_ratio = round(ev_value / ttm_ebitda, 6)

        ps_status = (
            STATUS_AVAILABLE if ps_ratio is not None else STATUS_UNAVAILABLE
        )
        ev_status = (
            STATUS_AVAILABLE if ev_ebitda_ratio is not None else STATUS_UNAVAILABLE
        )
        overall_status = (
            STATUS_AVAILABLE
            if ps_ratio is not None and ev_ebitda_ratio is not None
            else STATUS_UNAVAILABLE
        )

        ps_formula = {
            "expression": "(close x shares outstanding) / TTM revenue",
            "formula_version": FORMULA_VERSION,
            "numerator": (
                "as-traded close on the evaluation date times the latest "
                "knowable cover-page shares outstanding"
            ),
            "denominator": (
                "the income-statement dataset's TTM revenue window, four "
                "consecutive fiscal quarters"
            ),
        }
        ev_formula = {
            "expression": "(market cap + total debt - liquid funds) / TTM EBITDA",
            "formula_version": FORMULA_VERSION,
            "numerator": ev_bridge.get("definition"),
            "denominator": (
                "the income-statement dataset's TTM EBITDA window, four "
                "consecutive fiscal quarters"
            ),
        }

        lineage = {
            "income_observation_id": income_obs.observation_id,
            "income_input_set_id": income_result.input_set_id,
            "revenue_window_accessions": sorted(
                {
                    span["accession"]
                    for quarter in (revenue_window or {}).get("quarters", [])
                    for span in quarter.get("inputs", [])
                }
            ),
            "ebitda_window_accessions": sorted(
                {
                    span["accession"]
                    for quarter in (ebitda_window or {}).get("quarters", [])
                    for span in quarter.get("inputs", [])
                }
            ),
            "balance_sheet_accessions": sorted(
                {fact.accession for fact in components_in_force.values()}
            ),
            "shares_accessions": [share.accession] if share else [],
        }

        observation = HistoricalMultiplesObservation(
            observation_id=f"histmult-{config.ticker}-{day}",
            issuer_id=config.issuer_id,
            instrument_id=config.ticker,
            evaluation_date=day,
            status=overall_status,
            reason_code=ps_reason or ev_reason,
            reason_detail=ps_detail or ev_detail,
            ps_status=ps_status,
            ps_ratio=ps_ratio,
            ev_status=ev_status,
            ev_ebitda_ratio=ev_ebitda_ratio,
            ps_reason_code=ps_reason,
            ps_reason_detail=ps_detail,
            ev_reason_code=ev_reason,
            ev_reason_detail=ev_detail,
            price=price["close"] if price else None,
            price_currency=price["currency"] if price else "USD",
            shares_outstanding=share.shares if share else None,
            shares_as_of_date=share.as_of_date if share else None,
            shares_accession=share.accession if share else None,
            market_cap=market_cap,
            enterprise_value=ev_value,
            total_debt=total_debt,
            liquid_funds=liquid_funds,
            ttm_revenue=ttm_revenue,
            ttm_ebitda=ttm_ebitda,
            ev_bridge=ev_bridge,
            ps_formula=ps_formula,
            ev_formula=ev_formula,
            source_lineage=lineage,
            input_set_id=input_set_id,
        )
        observation.content_hash = observation.compute_content_hash()
        observations.append(observation)

    ps_distribution = compute_multiples_distribution(
        observations,
        metric=METRIC_PS_RATIO,
        values=[(o.evaluation_date, o.ps_ratio) for o in observations],
        min_observations=min_observations,
    )
    ev_distribution = compute_multiples_distribution(
        observations,
        metric=METRIC_EV_EBITDA_RATIO,
        values=[(o.evaluation_date, o.ev_ebitda_ratio) for o in observations],
        min_observations=min_observations,
    )

    result = HistoricalMultiplesResult(
        issuer_id=config.issuer_id,
        instrument_id=config.ticker,
        input_set_id=input_set_id,
        distributions={
            METRIC_PS_RATIO: ps_distribution,
            METRIC_EV_EBITDA_RATIO: ev_distribution,
        },
        observations=observations,
        concept_tags=concept_tags,
    )
    result.content_hash = canonical_json_hash(
        {
            "input_set_id": result.input_set_id,
            "distributions": {
                metric: dist.to_dict()
                for metric, dist in result.distributions.items()
            },
            "observation_hashes": [obs.content_hash for obs in observations],
        }
    )
    return result
