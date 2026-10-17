"""
Reverse Requirements Report V1.

This module answers one question with arithmetic instead of opinion:

    At the observed price, what would the company have to deliver?

Concretely, for a chosen holding period, a chosen required return and a chosen
exit multiple, it computes the exit price the required return demands, the exit
EPS that multiple implies, and the earnings growth rate that bridges an
explicitly named starting EPS to that exit EPS.

Three properties are load-bearing and are enforced by the tests:

1. Every reverse figure names the reference multiple and period it is
   conditional on. ``price / 20`` is the EPS that a 20x multiple corresponds
   to. It is not evidence that the market expects that EPS.

2. Every rate distinguishes a price return from a total return. Unless a
   dividend is supplied as an input, a required return is a *price* return and
   is labelled ``PRICE_RETURN_ONLY``. It is never called a total return.

3. Every earnings figure names the period its EPS actually covers. A
   next-twelve-months EPS cannot be used as though it were a trailing EPS at
   today's date; doing so silently shortens the growth window by a year. The
   growth period is computed from the anchor's declared coverage and a scenario
   whose growth window closes to zero is reported as not computable rather than
   divided by a near-zero exponent.

The module is pure and deterministic. It performs no I/O, imports nothing from
the runner, and holds no state, so the same inputs and the same formula version
always produce the same outputs. The fingerprint helper exists so a consumer can
tell a recomputation apart from a re-derivation after an input or a formula
changes.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from data_contract import SourceType, currencies_match, parse_iso_date


# Bumped whenever a formula below changes its meaning. Consumers compare this
# string to decide whether two results are the same calculation or two.
FORMULA_VERSION = "reverse-requirements/1.1"

# The growth window must cover at least this many years for an annualised CAGR
# to mean anything. A shorter window is reported, not extrapolated.
MIN_GROWTH_YEARS = 0.5

# Return labels. A required return without a dividend input is a price return.
RETURN_BASIS_PRICE_ONLY = "PRICE_RETURN_ONLY"
RETURN_BASIS_TOTAL = "TOTAL_RETURN_WITH_SUPPLIED_DIVIDEND"

# Dividend conventions for total return reverse hurdles.
DIVIDEND_CONVENTION_PRICE_ONLY = "PRICE_RETURN_ONLY"
DIVIDEND_CONVENTION_CASH_RETAINED = "CASH_DIVIDENDS_RETAINED"
DIVIDEND_CONVENTION_REINVESTED = "DIVIDENDS_REINVESTED_AT_TARGET_RETURN"

# EPS anchors. The anchor declares what period its EPS covers; the growth
# arithmetic depends on that declaration, not on the label alone.
ANCHOR_TTM = "TRAILING_TWELVE_MONTHS"
ANCHOR_FORWARD = "FORWARD_TWELVE_MONTHS"
ANCHOR_FISCAL_YEAR = "FISCAL_YEAR"
ANCHOR_USER = "USER_SUPPLIED"

# The consensus EPS the matrix's gap column is differenced against.

# The consensus a vendor reports is a next-fiscal-year estimate, so its own
# declared period end can fall a long way from the end of the year the matrix
# prices. Two windows that are not the same year are not differenced, so the
# rule below is the tolerance within which they are treated as the same
# exposure. One quarter is chosen because a fiscal year is only ever offset
# from the valuation date by up to three reporting quarters plus a reporting
# lag; beyond that the two figures describe different periods.
CONSENSUS_PERIOD_TOLERANCE_DAYS = 92

# The only horizon whose terminal EPS window can line up with a forward
# consensus. A longer horizon prices a year the estimate never covered, so
# the date comparison is never reached there and the gap stays unreported.
CONSENSUS_COMPARABLE_HORIZON_YEARS = 1.0

_MONTHS_PER_YEAR = 12.0


class ReverseRequirementError(ValueError):
    """An input that makes a requested figure undefined rather than merely large."""


def _safe_float(value: Any) -> Optional[float]:
    """A float, or None. Never a zero standing in for a missing number."""
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result != result or result in (float("inf"), float("-inf")):
        return None
    return result


def _declared_sample_count(value: Any) -> Optional[int]:
    """Return a valid non-negative integer sample count, or None if unverifiable."""
    numeric = _safe_float(value)
    if numeric is None or numeric < 0 or not numeric.is_integer():
        return None
    return int(numeric)


def band_reference_eligibility(
    band: Optional[Dict[str, Any]],
    *,
    min_observations: int,
) -> Tuple[bool, Optional[int]]:
    """
    The single historical-band eligibility rule every P/E reference path shares.

    A band may serve as a reference only when it declares a valid non-negative
    integer sample count of at least `min_observations` and a positive median.
    Returns ``(usable, declared_count)``. A band whose count is missing or
    unverifiable is never usable, whatever statistics it carries: an uncounted
    sample cannot be checked against the threshold, so its figures stay
    descriptive no matter which path reads them.
    """
    median = _safe_float((band or {}).get("median"))
    declared = _declared_sample_count((band or {}).get("observations"))
    usable = (
        median is not None
        and median > 0
        and declared is not None
        and declared >= min_observations
    )
    return usable, declared


@dataclass(frozen=True)
class EpsAnchor:
    """
    One EPS figure together with the period it actually covers.

    ``basis`` says where the number came from. ``months_covered`` says how long
    that number speaks for. The two are independent: a forward EPS from a
    vendor is a next-twelve-months figure even when the vendor labels it with a
    fiscal year, and treating it as a trailing figure is what silently turns a
    one-year gap into a multi-year growth rate.
    """

    value: float
    basis: str
    months_covered: float
    period_label: str = ""
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    provider: str = ""
    currency: Optional[str] = None
    # True when the source did not state which period the EPS covers and the
    # window was supplied from outside. The figure is still usable, but every
    # growth rate derived from it rests on an assumption rather than on
    # something the source reported, so the flag travels with it.
    period_undeclared_by_source: bool = False
    source_type: str = ""
    observation_id: Optional[str] = None
    is_user_assumption: bool = False
    sec_fact: Optional[Dict[str, Any]] = None
    sec_related_evidence: Optional[Dict[str, Any]] = None
    # For a vendor-sourced value, the provider field and endpoint that recorded
    # it (e.g. "defaultKeyStatistics.trailingEps" and the quoteSummary URL), and
    # the provider that produced the value's own observation. The observation
    # provider is distinct from the market-data provider on the anchor (which
    # composes the price and fundamentals providers); an EPS figure's direct
    # source is the former. Internal provenance only: deliberately kept out of
    # contract_view so the report's start_eps block and fingerprint are
    # unchanged. It feeds the human-readable sourced_facts entry, which is where
    # the evidence model records a source description.
    source_field: Optional[str] = None
    source_url: Optional[str] = None
    source_provider: Optional[str] = None
    # The source type the value's own observation recorded (e.g. API_LIVE for a
    # vendor sample). Distinct from the run's source_type, which says how this
    # execution obtained its data (a live run, or a regression fixture replay).
    source_observation_type: Optional[str] = None
    # When the value's own observation was retrieved. A vendor TTM figure with
    # no declared effective date can be retrieved on a different day than the
    # market price it is paired with, which the evidence keeps visible rather
    # than silently treating the two as one point-in-time snapshot.
    source_retrieved_at: Optional[str] = None
    # The EPS anchor catalogue entry this anchor was adopted from, with the
    # identity that entry carries: what the figure is (provider-reported, a
    # directly stated filing fact, or a derived sum), the accounting basis the
    # source declared, when it became public, and the directly stated quarterly
    # components a derived sum was built from. Empty for the legacy vendor
    # anchors, whose provenance is the fields above alone.
    anchor_id: Optional[str] = None
    anchor_nature: str = ""
    anchor_gaap_basis: str = ""
    anchor_available_at: Optional[str] = None
    anchor_available_at_basis: str = ""
    sec_components: Optional[Tuple[Dict[str, Any], ...]] = None
    anchor_derivation: str = ""
    annual_comparison: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        if not math_is_finite(self.value):
            raise ReverseRequirementError(f"EPS anchor value must be a finite number: {self.value!r}")
        if self.months_covered <= 0:
            raise ReverseRequirementError(
                f"EPS anchor must declare a positive coverage window, got {self.months_covered!r}"
            )

    def contract_view(self) -> Dict[str, Any]:
        view = {
            "value": self.value,
            "basis": self.basis,
            "months_covered": self.months_covered,
            "period_label": self.period_label,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "provider": self.provider,
            "currency": self.currency,
            "period_undeclared_by_source": self.period_undeclared_by_source,
            "source_type": self.source_type,
            "observation_id": self.observation_id,
            "is_user_assumption": self.is_user_assumption,
            "sec_fact": self.sec_fact,
            "sec_related_evidence": self.sec_related_evidence,
        }
        # A catalogue-adopted anchor extends its contract view with the identity
        # that makes it traceable: which entry it is, what kind of figure it is,
        # when it became public, and the directly stated quarterly components a
        # derived sum was built from. A legacy anchor's view is unchanged, so
        # every fingerprint computed before this field existed still matches.
        if self.anchor_id is not None:
            view["anchor_id"] = self.anchor_id
            view["anchor_nature"] = self.anchor_nature
            view["anchor_gaap_basis"] = self.anchor_gaap_basis
            view["anchor_available_at"] = self.anchor_available_at
            view["anchor_available_at_basis"] = self.anchor_available_at_basis
            view["anchor_derivation"] = self.anchor_derivation
            view["annual_comparison"] = self.annual_comparison
            if self.sec_components:
                view["sec_components"] = [dict(item) for item in self.sec_components]
        return view


def math_is_finite(value: Any) -> bool:
    return _safe_float(value) is not None


@dataclass(frozen=True)
class ReferenceMultiple:
    """
    A valuation multiple used to invert a price into a fundamental.

    ``source`` records where the multiple came from. A multiple derived from a
    usable historical distribution is a different kind of claim from one the
    user typed in, and the two must not read identically downstream.
    """

    value: float
    source: str
    period_label: str = ""
    sample_size: Optional[int] = None
    sample_period: str = ""
    is_user_assumption: bool = False
    eligibility_state: str = "USABLE_FOR_REFERENCE"
    usable_for_reference: bool = True

    def __post_init__(self) -> None:
        value = _safe_float(self.value)
        if value is None:
            raise ReverseRequirementError(f"Reference multiple must be a finite number: {self.value!r}")
        if value <= 0:
            raise ReverseRequirementError(
                f"A reference multiple must be positive; got {value!r}. "
                "A zero or negative multiple inverts to a non-meaningful EPS."
            )

    def contract_view(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "source": self.source,
            "period_label": self.period_label,
            "sample_size": self.sample_size,
            "sample_period": self.sample_period,
            "conditionality": (
                "The implied figure is the fundamental this multiple corresponds to. "
                "It is not a statement of what the market expects."
            ),
            "is_user_assumption": self.is_user_assumption,
            "eligibility_state": self.eligibility_state,
            "usable_for_reference": self.usable_for_reference,
        }


@dataclass(frozen=True)
class RiskFreeRate:
    """
    One observed risk-free rate.

    Kept as a distinct kind of number from a cost of equity and from an
    investor's target return. Each carries its own observation date, tenor,
    source and unit, because a rate substituted from the wrong date silently
    rewrites a historical valuation.
    """

    rate: float
    tenor_label: str
    as_of: str
    provider: str
    source_url: str = ""
    unit: str = "percent_per_annum"
    currency: str = "USD"
    instrument: str = ""

    def contract_view(self) -> Dict[str, Any]:
        return {
            "rate": self.rate,
            "rate_decimal": self.rate / 100.0 if self.unit == "percent_per_annum" else self.rate,
            "tenor_label": self.tenor_label,
            "as_of": self.as_of,
            "provider": self.provider,
            "source_url": self.source_url,
            "unit": self.unit,
            "currency": self.currency,
            "instrument": self.instrument,
        }


@dataclass(frozen=True)
class EpsScenario:
    """One row of the reverse requirements matrix."""

    horizon_years: float
    required_return: float
    required_return_basis: str
    exit_multiple: ReferenceMultiple
    required_exit_price: Optional[float]
    required_terminal_eps: Optional[float]
    start_anchor: EpsAnchor
    growth_years: Optional[float]
    required_eps_cagr: Optional[float]
    total_terminal_eps_growth: Optional[float]
    terminal_eps_vs_start_pct: Optional[float]
    terminal_pe_change_vs_current_pe: Optional[float]
    gap_vs_consensus_terminal_eps: Optional[float]
    comparison_notes: Tuple[str, ...]
    flags: Tuple[str, ...] = ()
    price: Optional[float] = None
    as_of: Optional[str] = None
    dividend_per_share: Optional[float] = None
    dividend_convention: Optional[str] = None
    dividend_relief_exit_price: Optional[float] = None
    dividend_relief_terminal_eps: Optional[float] = None
    dividend_relief_cagr: Optional[float] = None
    calculation_steps: Tuple[Dict[str, Any], ...] = ()
    evidence: Optional[Dict[str, Any]] = None

    def contract_view(self) -> Dict[str, Any]:
        view = {
            "price": self.price,
            "as_of": self.as_of,
            "horizon_years": self.horizon_years,
            "required_return": self.required_return,
            "required_return_basis": self.required_return_basis,
            "exit_multiple": self.exit_multiple.contract_view(),
            "required_exit_price": self.required_exit_price,
            "required_exit_price_basis": "PRICE_ONLY_EXCLUDES_DIVIDENDS"
            if self.required_return_basis == RETURN_BASIS_PRICE_ONLY
            else (self.dividend_convention or "INCLUDES_SUPPLIED_DIVIDEND"),
            "required_terminal_eps": self.required_terminal_eps,
            "start_eps": self.start_anchor.contract_view(),
            "growth_years": self.growth_years,
            "required_eps_cagr": self.required_eps_cagr,
            "total_terminal_eps_growth": self.total_terminal_eps_growth,
            "terminal_eps_vs_start_pct": self.terminal_eps_vs_start_pct,
            "terminal_pe_change_vs_current_pe": self.terminal_pe_change_vs_current_pe,
            "gap_vs_consensus_terminal_eps": self.gap_vs_consensus_terminal_eps,
            "comparison_notes": list(self.comparison_notes),
            "flags": list(self.flags),
            "formula_version": FORMULA_VERSION,
            "calculation_steps": [dict(s) for s in self.calculation_steps] if self.calculation_steps else [],
            "evidence": dict(self.evidence) if self.evidence is not None else None,
        }
        if self.dividend_per_share is not None:
            view["dividend_per_share"] = self.dividend_per_share
            view["dividend_convention"] = self.dividend_convention
            view["dividend_relief_exit_price"] = self.dividend_relief_exit_price
            view["dividend_relief_terminal_eps"] = self.dividend_relief_terminal_eps
            view["dividend_relief_cagr"] = self.dividend_relief_cagr
        return view


def required_exit_price(
    price: float,
    required_return: float,
    horizon_years: float,
) -> float:
    """
    The exit price a required price return demands: ``price * (1 + r) ** t``.

    Excludes dividends by construction. The caller states whether a dividend
    was supplied; this function never assumes one.
    """
    price_value = _safe_float(price)
    if price_value is None or price_value <= 0:
        raise ReverseRequirementError(f"Price must be a positive finite number, got {price!r}")
    rate = _safe_float(required_return)
    if rate is None:
        raise ReverseRequirementError(f"Required return must be a finite number, got {required_return!r}")
    if rate <= -1.0:
        raise ReverseRequirementError(
            f"A required return at or below -100% has no finite compounding solution; got {rate!r}"
        )
    years = _safe_float(horizon_years)
    if years is None or years <= 0:
        raise ReverseRequirementError(f"Horizon must be positive, got {horizon_years!r}")
    return price_value * ((1.0 + rate) ** years)


def required_total_return_exit_price(
    price: float,
    required_return: float,
    horizon_years: float,
    dividend_per_share: Optional[float] = None,
    convention: str = DIVIDEND_CONVENTION_CASH_RETAINED,
) -> float:
    """
    The terminal share price hurdle required when dividend income is included.

    Conventions:
    - PRICE_RETURN_ONLY: P_T = P_0 * (1 + r)^T
    - CASH_DIVIDENDS_RETAINED: P_T = P_0 * (1 + r)^T - T * D
      Cumulative cash dividends are retained without reinvestment and deducted
      from the required terminal share price hurdle.
    - DIVIDENDS_REINVESTED_AT_TARGET_RETURN: P_T = P_0 * (1 + r)^T - D * ((1 + r)^T - 1) / r
      Annual dividends are reinvested at the target rate of return r; the future value
      of the dividend annuity is deducted from the required terminal share price hurdle.
    """
    base_exit = required_exit_price(price, required_return, horizon_years)
    div = _safe_float(dividend_per_share)
    if div is None or div <= 0 or convention == DIVIDEND_CONVENTION_PRICE_ONLY:
        return base_exit

    years = float(horizon_years)
    rate = float(required_return)

    if convention == DIVIDEND_CONVENTION_CASH_RETAINED:
        cumulative_cash = div * years
        return max(0.0, base_exit - cumulative_cash)
    elif convention == DIVIDEND_CONVENTION_REINVESTED:
        if abs(rate) < 1e-12:
            fv_annuity = div * years
        else:
            fv_annuity = div * (((1.0 + rate) ** years - 1.0) / rate)
        return max(0.0, base_exit - fv_annuity)
    else:
        raise ReverseRequirementError(f"Unknown dividend convention: {convention!r}")


def implied_eps_at_multiple(price: float, multiple: float) -> float:
    """``price / multiple``: the EPS that this multiple corresponds to."""
    price_value = _safe_float(price)
    if price_value is None or price_value <= 0:
        raise ReverseRequirementError(f"Price must be a positive finite number, got {price!r}")
    multiple_value = _safe_float(multiple)
    if multiple_value is None or multiple_value <= 0:
        raise ReverseRequirementError(f"Multiple must be positive, got {multiple!r}")
    return price_value / multiple_value


def growth_window_years(start_anchor: EpsAnchor, horizon_years: float) -> float:
    """
    The span between the two EPS anchors, in years.

    A trailing anchor already covers the year that ended at the valuation
    date, so it sits ``months_covered / 12`` years before the horizon ends. A
    forward anchor reaches forward from the valuation date, so it sits that far
    *after* the horizon begins. Subtracting the forward anchor's coverage is
    what keeps a next-twelve-months EPS from being treated as a trailing one.
    """
    years = _safe_float(horizon_years)
    if years is None or years <= 0:
        raise ReverseRequirementError(f"Horizon must be positive, got {horizon_years!r}")
    if start_anchor.basis == ANCHOR_FORWARD:
        return years - (start_anchor.months_covered / _MONTHS_PER_YEAR)
    return years


def required_eps_cagr(
    start_anchor: EpsAnchor,
    terminal_eps: float,
    growth_years: float,
) -> Optional[float]:
    """
    The compound annual rate that bridges the start anchor to the terminal EPS.

    Returns None when the bridge is undefined rather than guessing: a
    non-positive start EPS, a non-positive terminal EPS, or a growth window too
    short to annualise.
    """
    terminal = _safe_float(terminal_eps)
    if terminal is None or terminal <= 0:
        return None
    if start_anchor.value <= 0:
        return None
    years = _safe_float(growth_years)
    if years is None or years < MIN_GROWTH_YEARS:
        return None
    return (terminal / start_anchor.value) ** (1.0 / years) - 1.0


def capm_cost_of_equity(
    risk_free_rate_decimal: float,
    beta: float,
    equity_risk_premium_decimal: float,
) -> float:
    """
    ``Rf + beta * ERP``.

    A model estimate, not an observation. Beta and the equity risk premium are
    themselves estimates, so the caller must carry their provenance; this
    function only does the arithmetic.
    """
    rf = _safe_float(risk_free_rate_decimal)
    if rf is None:
        raise ReverseRequirementError(f"Risk-free rate must be a finite number, got {risk_free_rate_decimal!r}")
    beta_value = _safe_float(beta)
    if beta_value is None:
        raise ReverseRequirementError(f"Beta must be a finite number, got {beta!r}")
    erp = _safe_float(equity_risk_premium_decimal)
    if erp is None:
        raise ReverseRequirementError(
            f"Equity risk premium must be a finite number, got {equity_risk_premium_decimal!r}"
        )
    return rf + beta_value * erp


def fcf_yield(free_cash_flow: float, market_cap: float) -> Optional[float]:
    """``FCF / market cap``. None when FCF is missing or the denominator is not positive."""
    fcf = _safe_float(free_cash_flow)
    cap = _safe_float(market_cap)
    if fcf is None or cap is None or cap <= 0:
        return None
    return fcf / cap


def required_fcf_at_multiple(market_cap: float, multiple: float) -> Optional[float]:
    """``market cap / P/FCF``: the FCF that this multiple corresponds to."""
    cap = _safe_float(market_cap)
    multiple_value = _safe_float(multiple)
    if cap is None or cap <= 0 or multiple_value is None or multiple_value <= 0:
        return None
    return cap / multiple_value


def required_revenue_at_multiple(market_cap: float, multiple: float) -> Optional[float]:
    """``market cap / P/S``: the revenue that this multiple corresponds to."""
    cap = _safe_float(market_cap)
    multiple_value = _safe_float(multiple)
    if cap is None or cap <= 0 or multiple_value is None or multiple_value <= 0:
        return None
    return cap / multiple_value


def required_ebitda_at_multiple(enterprise_value: float, multiple: float) -> Optional[float]:
    """``enterprise value / EV/EBITDA``: the EBITDA that this multiple corresponds to."""
    ev = _safe_float(enterprise_value)
    multiple_value = _safe_float(multiple)
    if ev is None or ev <= 0 or multiple_value is None or multiple_value <= 0:
        return None
    return ev / multiple_value


def implied_net_margin_at_multiples(
    implied_eps: float,
    implied_revenue: float,
    implied_shares: float,
) -> Optional[float]:
    """
    The net margin consistent with an implied EPS and an implied revenue.

    Only meaningful when the implied share count and the implied EPS describe
    the same share basis. Returns None otherwise instead of dividing across
    two different definitions of a share.
    """
    eps = _safe_float(implied_eps)
    revenue = _safe_float(implied_revenue)
    shares = _safe_float(implied_shares)
    if eps is None or revenue is None or shares is None:
        return None
    if revenue <= 0 or shares <= 0:
        return None
    return eps / (revenue / shares)


def build_scenario_calculation_steps(
    *,
    price: float,
    required_return: float,
    horizon_years: float,
    required_exit_price: Optional[float],
    exit_multiple_value: float,
    required_terminal_eps: Optional[float],
    start_eps_value: float,
    growth_years: Optional[float],
    required_eps_cagr: Optional[float],
    total_terminal_eps_growth: Optional[float],
    dividend_per_share: Optional[float] = None,
    dividend_convention: Optional[str] = None,
    currency: str = "USD",
) -> List[Dict[str, Any]]:
    steps: List[Dict[str, Any]] = []

    # Step 1: Required Exit Price
    operands_1: Dict[str, Any] = {
        "price": price,
        "required_return": required_return,
        "horizon_years": horizon_years,
    }
    formula_1 = "P_T = P_0 * (1 + r)^T"
    if dividend_per_share is not None and dividend_per_share > 0:
        operands_1["dividend_per_share"] = dividend_per_share
        operands_1["dividend_convention"] = dividend_convention or "CASH_RETAINED"
        formula_1 = "P_T = P_0 * (1 + r)^T - total_dividends"

    reproducible_1 = True
    if required_exit_price is not None:
        try:
            expected_price = price * ((1.0 + required_return) ** horizon_years)
            if dividend_per_share is not None and dividend_per_share > 0:
                expected_price = required_total_return_exit_price(
                    price, required_return, horizon_years, dividend_per_share, convention=dividend_convention or "CASH_RETAINED"
                )
            reproducible_1 = abs(expected_price - required_exit_price) < 1e-4
        except Exception:
            reproducible_1 = False

    steps.append({
        "step_number": 1,
        "step_id": "required_exit_price",
        "name": "Required Exit Price",
        "formula_expression": formula_1,
        "operands": operands_1,
        "output_value": required_exit_price,
        "output_unit": currency,
        "reproducible": reproducible_1,
        "status": "COMPUTED" if required_exit_price is not None else "NOT_COMPUTED",
        "status_reason": None if required_exit_price is not None else "Price or return is invalid.",
    })

    # Step 2: Required Terminal EPS
    reproducible_2 = True
    if required_terminal_eps is not None and required_exit_price is not None and exit_multiple_value > 0:
        expected_eps = required_exit_price / exit_multiple_value
        reproducible_2 = abs(expected_eps - required_terminal_eps) < 1e-4

    steps.append({
        "step_number": 2,
        "step_id": "required_terminal_eps",
        "name": "Required Terminal EPS",
        "formula_expression": "EPS_T = P_T / Exit_PE",
        "operands": {
            "required_exit_price": required_exit_price,
            "exit_multiple": exit_multiple_value,
        },
        "output_value": required_terminal_eps,
        "output_unit": f"{currency}/share",
        "reproducible": reproducible_2,
        "status": "COMPUTED" if required_terminal_eps is not None else "NOT_COMPUTED",
        "status_reason": None if required_terminal_eps is not None else "Exit multiple is not positive.",
    })

    # Step 3: Total Terminal EPS Growth
    reproducible_3 = False
    status_3 = "NOT_COMPUTED"
    reason_3 = None
    if start_eps_value > 0 and required_terminal_eps is not None:
        expected_growth = (required_terminal_eps - start_eps_value) / start_eps_value
        if total_terminal_eps_growth is not None:
            reproducible_3 = abs(expected_growth - total_terminal_eps_growth) < 1e-4
            status_3 = "COMPUTED"
    else:
        reason_3 = f"Starting EPS ({start_eps_value}) is non-positive; total growth cannot be computed."

    steps.append({
        "step_number": 3,
        "step_id": "total_terminal_eps_growth",
        "name": "Total Terminal EPS Growth",
        "formula_expression": "Delta_EPS = (EPS_T - EPS_0) / EPS_0",
        "operands": {
            "required_terminal_eps": required_terminal_eps,
            "start_eps": start_eps_value,
        },
        "output_value": total_terminal_eps_growth,
        "output_unit": "ratio",
        "reproducible": reproducible_3,
        "status": status_3,
        "status_reason": reason_3,
    })

    # Step 4: Required EPS CAGR
    reproducible_4 = False
    status_4 = "NOT_COMPUTED"
    reason_4 = None
    if growth_years is not None and growth_years < MIN_GROWTH_YEARS:
        reason_4 = f"Growth window ({growth_years:g} years) is too short to annualise (minimum {MIN_GROWTH_YEARS:g} years)."
    elif start_eps_value <= 0:
        reason_4 = f"Starting EPS ({start_eps_value}) is non-positive; compound annual growth rate cannot be computed."
    elif required_terminal_eps is not None and required_terminal_eps <= 0:
        reason_4 = f"Required terminal EPS ({required_terminal_eps}) is non-positive; CAGR cannot be computed."
    elif required_eps_cagr is not None and growth_years is not None and growth_years > 0:
        try:
            expected_cagr = (required_terminal_eps / start_eps_value) ** (1.0 / growth_years) - 1.0
            reproducible_4 = abs(expected_cagr - required_eps_cagr) < 1e-4
            status_4 = "COMPUTED"
        except Exception:
            reproducible_4 = False

    steps.append({
        "step_number": 4,
        "step_id": "required_eps_cagr",
        "name": "Required EPS CAGR",
        "formula_expression": "CAGR = (EPS_T / EPS_0)^(1 / t_growth) - 1",
        "operands": {
            "required_terminal_eps": required_terminal_eps,
            "start_eps": start_eps_value,
            "growth_years": growth_years,
        },
        "output_value": required_eps_cagr,
        "output_unit": "percent_per_annum",
        "reproducible": reproducible_4,
        "status": status_4,
        "status_reason": reason_4,
    })

    return steps


def build_scenario_evidence(
    *,
    price: float,
    currency: Optional[str],
    as_of: Optional[str],
    price_evidence: Optional[Dict[str, Any]],
    start_anchor: EpsAnchor,
    exit_multiple: ReferenceMultiple,
    horizon_years: float,
    required_return: float,
    required_return_basis: str,
) -> Dict[str, Any]:
    pe_info = price_evidence or {}
    price_ev = {
        "value": price,
        "currency": currency,
        "as_of": as_of or pe_info.get("as_of"),
        "provider": pe_info.get("provider", "market"),
        "source_type": pe_info.get("source_type", "OBSERVED"),
        "observation_id": pe_info.get("observation_id", "ev-price-001"),
        "is_user_assumption": bool(pe_info.get("is_user_assumption", False)),
    }

    # The synthetic vendor observation id is a legacy-path default only. An
    # anchor adopted from the EPS anchor catalogue carries its own identity --
    # the accession that states a filing figure, or the run observation id the
    # catalogue recorded for a supplier figure -- and is never labelled with
    # another figure's observation id.
    eps_observation_id = getattr(start_anchor, "observation_id", None)
    if (
        eps_observation_id is None
        and getattr(start_anchor, "anchor_id", None) is None
        and not getattr(start_anchor, "is_user_assumption", False)
    ):
        eps_observation_id = "ev-current-eps-001"
    sec_components = getattr(start_anchor, "sec_components", None) or ()

    eps_ev = {
        "value": start_anchor.value,
        "basis": start_anchor.basis,
        "months_covered": start_anchor.months_covered,
        "period_label": start_anchor.period_label,
        "period_start": start_anchor.period_start,
        "period_end": start_anchor.period_end,
        "provider": start_anchor.provider,
        "currency": start_anchor.currency or currency,
        "period_undeclared_by_source": start_anchor.period_undeclared_by_source,
        "source_type": getattr(start_anchor, "source_type", "") or ("USER_SUPPLIED" if getattr(start_anchor, "is_user_assumption", False) else "OBSERVED"),
        "observation_id": eps_observation_id,
        "is_user_assumption": getattr(start_anchor, "is_user_assumption", False),
        "sec_fact": getattr(start_anchor, "sec_fact", None),
        "sec_related_evidence": getattr(start_anchor, "sec_related_evidence", None),
    }
    # Catalogue-adopted anchors extend the evidence contract with the identity
    # that makes them traceable; legacy vendor anchors keep the original 14-field
    # contract so existing provenance assertions stay valid.
    if getattr(start_anchor, "anchor_id", None) is not None:
        eps_ev["anchor_id"] = getattr(start_anchor, "anchor_id", None)
        eps_ev["anchor_nature"] = getattr(start_anchor, "anchor_nature", "")
        eps_ev["anchor_gaap_basis"] = getattr(start_anchor, "anchor_gaap_basis", "")
        eps_ev["available_at"] = getattr(start_anchor, "anchor_available_at", None)
        eps_ev["available_at_basis"] = getattr(start_anchor, "anchor_available_at_basis", "")
        eps_ev["sec_components"] = [dict(item) for item in sec_components] if sec_components else None
        eps_ev["annual_comparison"] = getattr(start_anchor, "annual_comparison", None)

    mult_ev = {
        "value": exit_multiple.value,
        "source": exit_multiple.source,
        "period_label": exit_multiple.period_label,
        "sample_size": exit_multiple.sample_size,
        "sample_period": exit_multiple.sample_period,
        "conditionality": (
            "The implied figure is the fundamental this multiple corresponds to. "
            "It is not a statement of what the market expects."
        ),
        "is_user_assumption": getattr(exit_multiple, "is_user_assumption", exit_multiple.source == "user_supplied"),
        "eligibility_state": getattr(exit_multiple, "eligibility_state", "USER_SPECIFIED" if exit_multiple.source == "user_supplied" else "USABLE_FOR_REFERENCE"),
        "usable_for_reference": getattr(exit_multiple, "usable_for_reference", True),
    }

    user_assumptions: List[str] = [
        f"Holding Horizon: {horizon_years:g} years",
        f"Required Return Hurdle: {required_return * 100:g}% ({required_return_basis})",
    ]
    if mult_ev["is_user_assumption"]:
        user_assumptions.append(f"Exit Multiple: {exit_multiple.value:g}x (user-supplied)")
    if eps_ev["is_user_assumption"]:
        user_assumptions.append(f"Starting EPS: {start_anchor.value:g} (user-supplied)")

    sourced_facts: List[str] = [
        f"Market Price: {price:g} {currency or 'USD'} (as-of {as_of or 'latest'}, provider: {price_ev['provider']})"
    ]
    # The EPS figure's direct source provider is the provider of its own
    # observation, not the anchor's market-data provider (which composes the
    # price and fundamentals providers). When the observation recorded one it is
    # named as such; otherwise the anchor's provider stands, unchanged.
    eps_source_provider = getattr(start_anchor, "source_provider", None)
    eps_provider = eps_source_provider or start_anchor.provider
    eps_provider_label = "EPS provider" if eps_source_provider else "provider"
    if not eps_ev["is_user_assumption"]:
        sec_note = ""
        if eps_ev["sec_fact"] and eps_ev["sec_fact"].get("accession"):
            # Direct provenance is claimed only when the data structures establish it.
            sec_note = f"; SEC {eps_ev['sec_fact'].get('form', '10-K')} accession {eps_ev['sec_fact']['accession']}"
        sourced_facts.append(
            f"Starting EPS: {start_anchor.value:g} {start_anchor.currency or currency or 'USD'} ({start_anchor.basis}, {eps_provider_label}: {eps_provider}{sec_note})"
        )
    if not mult_ev["is_user_assumption"]:
        sample_note = f", sample size: {exit_multiple.sample_size}" if exit_multiple.sample_size else ""
        sourced_facts.append(
            f"Reference Exit Multiple: {exit_multiple.value:g}x ({exit_multiple.source}{sample_note})"
        )

    # A derived twelve-month anchor keeps its four directly stated quarterly
    # components visible, so a reader can check the sum against the filings it
    # was built from. The sum is this engine's arithmetic; no issuer stated it.
    if sec_components and not eps_ev["is_user_assumption"]:
        component_summary = "; ".join(
            f"{item.get('period_start') or 'undeclared start'}..{item.get('period_end')}"
            f" = {item.get('value')} ({item.get('form')} accession {item.get('accession')})"
            for item in sec_components
        )
        sourced_facts.append(
            f"Starting EPS derivation: four directly stated quarterly filing facts summed "
            f"over {start_anchor.period_start} to {start_anchor.period_end} ({component_summary})"
        )

    # A provider-sourced starting EPS reports the provider field and endpoint
    # that recorded the value, so the number is traceable to its actual raw
    # material. This is stated only when a direct SEC fact is absent (a linked
    # filing names itself in the entry above) and only from what the acquisition
    # observation actually recorded; nothing here is inferred from a value or a
    # related filing, and a source that declared no period date says so.
    if not eps_ev["is_user_assumption"] and not (
        eps_ev.get("sec_fact") and eps_ev["sec_fact"].get("accession")
    ):
        source_field = getattr(start_anchor, "source_field", None)
        source_url = getattr(start_anchor, "source_url", None)
        if source_field or source_url:
            eps_source_type = getattr(start_anchor, "source_observation_type", None) or eps_ev["source_type"]
            entry = f"Starting EPS source: {source_field or 'provider-reported value'}"
            entry += f" (EPS provider: {eps_provider or 'unknown'}; source_type: {eps_source_type})"
            if source_url:
                entry += f"; source: {source_url}"
            if start_anchor.period_end:
                entry += f"; source-declared period end: {start_anchor.period_end}"
            else:
                entry += "; source declared no period date"
            sourced_facts.append(entry)

    missing_or_unvalidated: List[str] = []
    # A regression fixture pairs inputs recorded on different days by
    # construction (a captured EPS with no declared effective date beside a
    # fixed market price dated earlier), so the pair is stated to be a
    # cross-date input rather than a point-in-time snapshot. A live run reads
    # its price and EPS from one acquisition, so this caveat is not raised for
    # it. The effective date is never back-dated from the value itself, and a
    # source that declared a period (a linked filing) is not flagged.
    if (
        str(getattr(start_anchor, "source_type", "")) == SourceType.REGRESSION_FIXTURE.value
        and not eps_ev["is_user_assumption"]
        and not (eps_ev.get("sec_fact") and eps_ev["sec_fact"].get("accession"))
    ):
        retrieved_at = getattr(start_anchor, "source_retrieved_at", None)
        retrieved_date = str(retrieved_at)[:10] if retrieved_at else None
        if retrieved_date and as_of and retrieved_date != str(as_of)[:10]:
            missing_or_unvalidated.append(
                f"Starting EPS observation was retrieved on {retrieved_date}, which differs from "
                f"the market price date {as_of}; the EPS effective date is undeclared, so the "
                "inputs span more than one date and this is not a verified point-in-time snapshot"
            )
    if mult_ev["eligibility_state"] in ("DESCRIPTIVE_ONLY_UNVERIFIED_SAMPLE_COUNT", "INSUFFICIENT_OBSERVATIONS_DESCRIPTIVE_ONLY"):
        missing_or_unvalidated.append(f"Exit multiple qualification: {mult_ev['eligibility_state']}")
    if start_anchor.period_undeclared_by_source:
        missing_or_unvalidated.append("Starting EPS period coverage was not declared by source")
    # Explicit provenance limitation: direct SEC link must be proven, never inferred from existence.
    # Every sourced (non-user) anchor either names the filing that supplied it
    # or states what its figure actually is. A derived twelve-month anchor is
    # not an unestablished link: its components are directly stated filings,
    # and the thing that is not an issuer statement is the sum itself.
    related = eps_ev.get("sec_related_evidence") or None
    if not eps_ev["is_user_assumption"] and not (eps_ev.get("sec_fact") and eps_ev["sec_fact"].get("accession")):
        if sec_components:
            limitation = (
                "Starting EPS is a derived twelve-month sum of four directly stated "
                "quarterly filing facts; the sum itself is this engine's arithmetic "
                "and was not stated by the issuer"
            )
        else:
            limitation = "Direct SEC source of selected EPS not established"
        if related and related.get("accession"):
            limitation += "; related filing shown for cross-check only"
        missing_or_unvalidated.append(limitation)

    return {
        "price_evidence": price_ev,
        "eps_evidence": eps_ev,
        "multiple_evidence": mult_ev,
        "user_assumptions": user_assumptions,
        "sourced_facts": sourced_facts,
        "missing_or_unvalidated": missing_or_unvalidated,
        "related_sec_evidence": related,
    }


def build_scenario(
    price: float,
    horizon_years: float,
    required_return: float,
    exit_multiple: ReferenceMultiple,
    start_anchor: EpsAnchor,
    current_pe: Optional[float] = None,
    consensus_eps: Optional[float] = None,
    consensus_basis: str = "",
    consensus_months_covered: Optional[float] = None,
    consensus_period_end: Optional[str] = None,
    dividend_per_share: Optional[float] = None,
    currency: Optional[str] = None,
    as_of: Optional[str] = None,
    dividend_convention: str = DIVIDEND_CONVENTION_PRICE_ONLY,
    price_evidence: Optional[Dict[str, Any]] = None,
) -> EpsScenario:
    """
    One row of the matrix: what this horizon, return and exit multiple demand.

    Nothing here is filled in when an input is missing. A missing consensus
    leaves the comparison out rather than substituting the trailing EPS, and a
    consensus whose period does not line up with the terminal EPS is reported
    as not comparable rather than compared anyway.
    """
    notes: List[str] = []
    flags: List[str] = []

    div_val = _safe_float(dividend_per_share)
    if div_val is not None and div_val > 0:
        return_basis = RETURN_BASIS_TOTAL
        conv = (
            dividend_convention
            if dividend_convention != DIVIDEND_CONVENTION_PRICE_ONLY
            else DIVIDEND_CONVENTION_CASH_RETAINED
        )
        target_price = required_total_return_exit_price(
            price, required_return, horizon_years, div_val, convention=conv
        )
        price_only_target = required_exit_price(price, required_return, horizon_years)
        relief_exit_price = target_price - price_only_target

        terminal_eps = implied_eps_at_multiple(target_price, exit_multiple.value)
        price_only_eps = implied_eps_at_multiple(price_only_target, exit_multiple.value)
        relief_terminal_eps = terminal_eps - price_only_eps

        window = growth_window_years(start_anchor, horizon_years)
        cagr = required_eps_cagr(start_anchor, terminal_eps, window)
        price_only_cagr = required_eps_cagr(start_anchor, price_only_eps, window)
        relief_cagr = (
            cagr - price_only_cagr
            if (cagr is not None and price_only_cagr is not None)
            else None
        )
    else:
        div_val = None
        conv = None
        return_basis = RETURN_BASIS_PRICE_ONLY
        flags.append("REQUIRED_RETURN_EXCLUDES_DIVIDENDS")
        target_price = required_exit_price(price, required_return, horizon_years)
        terminal_eps = implied_eps_at_multiple(target_price, exit_multiple.value)
        window = growth_window_years(start_anchor, horizon_years)
        cagr = required_eps_cagr(start_anchor, terminal_eps, window)
        relief_exit_price = None
        relief_terminal_eps = None
        relief_cagr = None

    if window < MIN_GROWTH_YEARS:
        flags.append("GROWTH_WINDOW_TOO_SHORT_FOR_CAGR")
        notes.append(
            f"The starting anchor is a {start_anchor.basis} figure covering "
            f"{start_anchor.months_covered:g} months, which leaves "
            f"{window:g} years to the horizon. That window is too short to "
            "annualise, so no CAGR is reported. Comparing the two EPS figures "
            "directly would misstate a one-period step as a growth rate."
        )

    total_growth: Optional[float] = None
    pct_change: Optional[float] = None
    if start_anchor.value > 0:
        total_growth = terminal_eps / start_anchor.value - 1.0
        pct_change = (terminal_eps - start_anchor.value) / start_anchor.value

    pe_change: Optional[float] = None
    current_pe_value = _safe_float(current_pe)
    if current_pe_value is not None and current_pe_value > 0:
        pe_change = exit_multiple.value / current_pe_value - 1.0
        if abs(pe_change) < 1e-12:
            notes.append("Exit multiple equals the current observed P/E, so no multiple change is implied.")
        elif pe_change < 0:
            notes.append(
                f"The exit multiple is {abs(pe_change) * 100:.1f}% below the current P/E; "
                "the required terminal EPS is therefore higher than a flat-multiple case."
            )
        else:
            notes.append(
                f"The exit multiple is {pe_change * 100:.1f}% above the current P/E; "
                "the required terminal EPS is therefore lower than a flat-multiple case."
            )

    gap_vs_consensus: Optional[float] = None
    consensus_value = _safe_float(consensus_eps)
    if consensus_value is None:
        flags.append("NO_CONSENSUS_FOR_COMPARISON")
    elif consensus_value <= 0:
        flags.append("CONSENSUS_NOT_USABLE_FOR_COMPARISON")
        notes.append("The available consensus EPS is not positive, so no gap is reported.")
    else:
        comparable, why = _consensus_is_comparable(
            horizon_years=horizon_years,
            consensus_basis=consensus_basis,
            consensus_months_covered=consensus_months_covered,
            consensus_period_end=consensus_period_end,
            as_of=as_of,
        )
        if comparable:
            gap_vs_consensus = terminal_eps / consensus_value - 1.0
        else:
            flags.append("CONSENSUS_PERIOD_NOT_COMPARABLE")
            notes.append(why)

    if start_anchor.currency and currency and not currencies_match(start_anchor.currency, currency):
        flags.append("CURRENCY_MISMATCH")
        notes.append(
            f"The starting EPS is denominated in {start_anchor.currency} while the "
            f"price is denominated in {currency}; this row is not comparable."
        )

    calc_steps = build_scenario_calculation_steps(
        price=price,
        required_return=required_return,
        horizon_years=horizon_years,
        required_exit_price=target_price,
        exit_multiple_value=exit_multiple.value,
        required_terminal_eps=terminal_eps,
        start_eps_value=start_anchor.value,
        growth_years=window,
        required_eps_cagr=cagr,
        total_terminal_eps_growth=total_growth,
        dividend_per_share=div_val,
        dividend_convention=conv,
        currency=currency or start_anchor.currency or "USD",
    )
    evidence_block = build_scenario_evidence(
        price=price,
        currency=currency or start_anchor.currency or "USD",
        as_of=as_of,
        price_evidence=price_evidence,
        start_anchor=start_anchor,
        exit_multiple=exit_multiple,
        horizon_years=horizon_years,
        required_return=required_return,
        required_return_basis=return_basis,
    )

    return EpsScenario(
        horizon_years=float(horizon_years),
        required_return=float(required_return),
        required_return_basis=return_basis,
        exit_multiple=exit_multiple,
        required_exit_price=target_price,
        required_terminal_eps=terminal_eps,
        start_anchor=start_anchor,
        growth_years=window,
        required_eps_cagr=cagr,
        total_terminal_eps_growth=total_growth,
        terminal_eps_vs_start_pct=pct_change,
        terminal_pe_change_vs_current_pe=pe_change,
        gap_vs_consensus_terminal_eps=gap_vs_consensus,
        comparison_notes=tuple(notes),
        flags=tuple(flags),
        price=float(price) if price is not None else None,
        as_of=as_of,
        dividend_per_share=div_val,
        dividend_convention=conv,
        dividend_relief_exit_price=relief_exit_price,
        dividend_relief_terminal_eps=relief_terminal_eps,
        dividend_relief_cagr=relief_cagr,
        calculation_steps=tuple(calc_steps),
        evidence=evidence_block,
    )


def terminal_period_end(
    as_of: Optional[str],
    horizon_years: float,
) -> Optional[str]:
    """
    The calendar date the terminal EPS window ends on.

    `as_of` is the valuation date the price was observed at, and the terminal
    EPS covers the `horizon_years` that follow it. One calendar year is added
    by date, not by a fixed day count, so a leap day does not move the window.

    None when either input cannot be read, because a window that cannot be
    dated is not a window to compare anything against.
    """
    start = parse_iso_date(as_of)
    years = _safe_float(horizon_years)
    if start is None or years is None or years <= 0:
        return None
    whole = int(years)
    try:
        added = start.replace(year=start.year + whole)
    except ValueError:
        # 29 February: the only date a whole-year addition can land on
        # nothing, and the convention is the last day of February.
        added = start.replace(
            year=start.year + whole, month=2, day=28
        )
    if whole < years:
        added = added + timedelta(days=round((years - whole) * 365))
    return added.isoformat()


def _consensus_is_comparable(
    horizon_years: float,
    consensus_basis: str,
    consensus_months_covered: Optional[float],
    consensus_period_end: Optional[str] = None,
    as_of: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Whether a consensus EPS speaks about the same period as the terminal EPS.

    The terminal EPS covers the year ending at the horizon, so a
    next-twelve-months consensus taken at the valuation date covers the first
    year of the horizon and the two coincide only when the horizon is one
    year. Any other comparison would be a difference between two different
    years presented as a gap.

    When the horizon is a year, the decision is made on the period the source
    declared rather than on its label. A vendor's ``+1y`` row is a
    next-fiscal-year estimate whose end date the source states; that declared
    end is compared against the end of the terminal window, and only a
    difference within `CONSENSUS_PERIOD_TOLERANCE_DAYS` counts as the same
    period. A missing or unreadable declared end is not a date to be inferred
    from the label, so it leaves the comparison unavailable.
    """
    if not consensus_basis:
        return False, (
            "The consensus figure declares no basis, so it cannot be shown to cover "
            "the same period as the terminal EPS."
        )
    if consensus_basis in (ANCHOR_FORWARD, ANCHOR_TTM):
        years = _safe_float(horizon_years) or 0.0
        if abs(years - CONSENSUS_COMPARABLE_HORIZON_YEARS) > 1e-9:
            subject = (
                "next-twelve-months figure taken at the valuation date"
                if consensus_basis == ANCHOR_FORWARD
                else "trailing figure covering the year before the valuation date"
            )
            return False, (
                f"The consensus is a {subject}, which covers year 1, "
                f"while the terminal EPS covers the year ending at "
                f"{years:g} years. These are different periods and are not compared here."
            )
        declared = parse_iso_date(consensus_period_end)
        if declared is None:
            return False, (
                "The consensus EPS declares no readable period end, so no calendar year "
                "can be identified to line it up against the terminal EPS."
            )
        target = parse_iso_date(terminal_period_end(as_of, years))
        if target is None:
            return False, (
                "The terminal EPS window end cannot be dated from this run's price date, "
                "so the consensus period cannot be lined up against it."
            )
        offset = (declared - target).days
        if abs(offset) > CONSENSUS_PERIOD_TOLERANCE_DAYS:
            return False, (
                f"The consensus period ends on {declared.isoformat()} while the terminal "
                f"EPS window ends on {target.isoformat()}, a difference of "
                f"{abs(offset)} days. These are different periods and are not compared here."
            )
        return True, ""
    return False, (
        f"The consensus basis {consensus_basis!r} is not a period this module can line up "
        "against a terminal EPS, so no gap is reported."
    )


def build_matrix(
    price: float,
    horizons_years: Sequence[float],
    required_returns: Sequence[float],
    exit_multiples: Sequence[ReferenceMultiple],
    start_anchor: EpsAnchor,
    current_pe: Optional[float] = None,
    consensus_eps: Optional[float] = None,
    consensus_basis: str = "",
    consensus_months_covered: Optional[float] = None,
    consensus_period_end: Optional[str] = None,
    dividend_per_share: Optional[float] = None,
    currency: Optional[str] = None,
    as_of: Optional[str] = None,
    dividend_convention: str = DIVIDEND_CONVENTION_PRICE_ONLY,
    price_evidence: Optional[Dict[str, Any]] = None,
) -> List[EpsScenario]:
    """The full cross product of horizons, required returns and exit multiples."""
    scenarios: List[EpsScenario] = []
    for years in horizons_years:
        for rate in required_returns:
            for multiple in exit_multiples:
                scenarios.append(
                    build_scenario(
                        price=price,
                        horizon_years=years,
                        required_return=rate,
                        exit_multiple=multiple,
                        start_anchor=start_anchor,
                        current_pe=current_pe,
                        consensus_eps=consensus_eps,
                        consensus_basis=consensus_basis,
                        consensus_months_covered=consensus_months_covered,
                        consensus_period_end=consensus_period_end,
                        dividend_per_share=dividend_per_share,
                        currency=currency,
                        as_of=as_of,
                        dividend_convention=dividend_convention,
                        price_evidence=price_evidence,
                    )
                )
    return scenarios


def discount_present_value(
    cash_flows: Sequence[float],
    discount_rate: float,
) -> float:
    """Sum of ``cf[t] / (1 + r) ** (t + 1)``. The first flow is one year out."""
    rate = _safe_float(discount_rate)
    if rate is None or rate <= -1.0:
        raise ReverseRequirementError(f"Discount rate must be greater than -1, got {discount_rate!r}")
    total = 0.0
    for index, flow in enumerate(cash_flows):
        value = _safe_float(flow)
        if value is None:
            raise ReverseRequirementError(f"Cash flow at position {index} is not a finite number: {flow!r}")
        total += value / ((1.0 + rate) ** (index + 1))
    return total


def terminal_value(cash_flow: float, discount_rate: float, growth_rate: float) -> float:
    """
    Gordon growth terminal value at the end of the explicit period.

    Requires the discount rate to exceed the growth rate. Without that check
    the denominator is zero or negative and the result is either undefined or a
    large negative number that looks like a valuation.
    """
    rate = _safe_float(discount_rate)
    growth = _safe_float(growth_rate)
    flow = _safe_float(cash_flow)
    if rate is None or growth is None or flow is None:
        raise ReverseRequirementError("Terminal value requires finite cash flow, discount rate and growth rate.")
    if rate <= growth:
        raise ReverseRequirementError(
            f"A terminal growth rate of {growth!r} is not below the discount rate {rate!r}; "
            "the Gordon terminal value is undefined in that case."
        )
    return flow * (1.0 + growth) / (rate - growth)


def solve_implied_growth_rate(
    present_value: float,
    base_cash_flow: float,
    discount_rate: float,
    explicit_years: int,
    terminal_growth: float,
    growth_bounds: Tuple[float, float] = (-0.95, 3.0),
    tolerance: float = 1e-9,
    max_iterations: int = 300,
) -> Optional[float]:
    """
    The constant explicit-period FCF growth rate that makes the modelled value
    equal the observed one.

    This is the reverse direction a discounted cash flow model normally does not
    run: instead of asking whether a forecast is worth the price, it asks what
    forecast the price already implies, at a stated discount rate and terminal
    growth rate. It is a solver over a single constant growth rate, not a full
    cash flow forecast, and it says nothing about the path within the explicit
    period.

    Returns None when the observed value lies outside the bracket the growth
    bounds can reach, which means no constant growth rate in that range
    explains the price under these assumptions.
    """
    value = _safe_float(present_value)
    base = _safe_float(base_cash_flow)
    rate = _safe_float(discount_rate)
    growth = _safe_float(terminal_growth)
    if value is None or base is None or rate is None or growth is None:
        return None
    if value <= 0 or base <= 0:
        return None
    if rate <= growth:
        return None
    if rate <= -1.0:
        return None
    if explicit_years < 1:
        return None

    low, high = growth_bounds

    def total_value(candidate_growth: float) -> float:
        flows = [base * ((1.0 + candidate_growth) ** (index + 1)) for index in range(explicit_years)]
        explicit = discount_present_value(flows, rate)
        terminal_flow = flows[-1] * (1.0 + growth)
        terminal_pv = terminal_flow / (rate - growth)
        return explicit + terminal_pv / ((1.0 + rate) ** explicit_years)

    # The model is strictly increasing in the growth rate, so a bisection on
    # the bracket is sufficient and terminates.
    low_value = total_value(low)
    high_value = total_value(high)
    if value < low_value or value > high_value:
        return None

    for _ in range(max_iterations):
        middle = (low + high) / 2.0
        middle_value = total_value(middle)
        if abs(middle_value - value) < tolerance * max(1.0, value):
            return middle
        if middle_value < value:
            low = middle
        else:
            high = middle
        if high - low < tolerance:
            return (low + high) / 2.0
    return (low + high) / 2.0


def dcf_feasibility(
    *,
    has_free_cash_flow: bool,
    has_depreciation_amortisation: bool,
    has_capex: bool,
    has_working_capital_change: bool,
    has_cost_of_debt: bool,
    has_market_value_of_debt: bool,
    has_tax_rate: bool,
    cash_flow_basis: str = "",
) -> Dict[str, Any]:
    """
    Whether a discounted cash flow model is supported, and what is missing.

    A missing input is named rather than filled. Producing a number anyway would
    be the more harmful outcome, because a precise-looking figure with an
    invented tax rate or a guessed working capital change reads as evidence.
    """
    checks = {
        "free_cash_flow": has_free_cash_flow,
        "depreciation_amortisation": has_depreciation_amortisation,
        "capex": has_capex,
        "working_capital_change": has_working_capital_change,
        "cost_of_debt": has_cost_of_debt,
        "market_value_of_debt": has_market_value_of_debt,
        "tax_rate": has_tax_rate,
    }
    missing = sorted(name for name, present in checks.items() if not present)

    # FCFF needs the unlevered bridge complete. FCFE needs the levered inputs
    # and an equity discount rate, and must not be mixed with a WACC.
    if not cash_flow_basis:
        basis_status = "UNDECLARED"
        blocking = ["cash_flow_basis"]
    elif cash_flow_basis not in ("FCFF", "FCFE"):
        basis_status = f"UNSUPPORTED:{cash_flow_basis}"
        blocking = ["cash_flow_basis"]
    else:
        basis_status = cash_flow_basis
        blocking = []

    hard_blockers = list(missing) + blocking
    return {
        "supported": not hard_blockers,
        "cash_flow_basis": cash_flow_basis or None,
        "cash_flow_basis_status": basis_status,
        "missing_inputs": missing,
        "blocking_reasons": hard_blockers,
        "explanation": (
            "A discounted cash flow model needs an explicit unlevered or levered cash flow "
            "definition and the inputs to bridge from reported earnings to it. Inputs that "
            "are not observed are named here instead of being estimated, so no figure is "
            "produced that would look precise and rest on an assumption that was never stated."
        ),
        "discount_rate_note": (
            "A discount rate must match the cash flow definition: a WACC prices unlevered "
            "cash flow (FCFF) and an equity discount rate prices levered cash flow (FCFE). "
            "Using one with the other changes the answer without any visible sign."
        ),
    }


def build_start_anchor(
    *,
    trailing_eps: Optional[float],
    forward_eps: Optional[float],
    consensus_eps: Optional[float],
    currency: Optional[str],
    trailing_period_label: str = "",
    forward_period_label: str = "",
    provider: str = "",
    prefer: str = "trailing",
    forward_months_covered: float = 12.0,
) -> Tuple[Optional[EpsAnchor], List[Dict[str, Any]]]:
    """
    Choose the EPS the growth bridge starts from.

    Preference order is trailing, then forward, then consensus. The trailing
    anchor is preferred because a next-twelve-months EPS reaches forward from
    the valuation date, so using it as the starting point shortens the growth
    window; where it is used, that shortening is carried in the anchor rather
    than absorbed silently.

    Returns the anchor plus an explicit list of what was missing, so a caller
    can report the gap instead of running a matrix with no starting point.
    """
    unavailable: List[Dict[str, Any]] = []

    candidates = (("trailing", trailing_eps), ("forward", forward_eps), ("consensus", consensus_eps))
    order = {
        "trailing": ("trailing", "forward", "consensus"),
        "forward": ("forward", "trailing", "consensus"),
        "consensus": ("consensus", "forward", "trailing"),
    }.get(prefer, ("trailing", "forward", "consensus"))

    values = dict(candidates)
    labels = {"trailing": trailing_period_label, "forward": forward_period_label, "consensus": ""}

    for name, value in candidates:
        numeric = _safe_float(value)
        if numeric is None:
            unavailable.append(
                {
                    "item": f"start_eps_candidate.{name}",
                    "reason": f"No usable {name} EPS was observed, so it could not start the growth bridge.",
                    "reason_kind": "MISSING",
                    "blocks": ["start_anchor"],
                }
            )
        elif numeric <= 0:
            unavailable.append(
                {
                    "item": f"start_eps_candidate.{name}",
                    "reason": (
                        f"The observed {name} EPS is {numeric}, which is not positive. "
                        "A growth rate from it would have no meaning."
                    ),
                    "reason_kind": "NOT_POSITIVE",
                    "blocks": ["start_anchor"],
                }
            )

    for name in order:
        numeric = _safe_float(values.get(name))
        if numeric is None or numeric <= 0:
            continue
        if name == "trailing":
            return (
                EpsAnchor(
                    value=numeric,
                    basis=ANCHOR_TTM,
                    months_covered=12.0,
                    period_label=trailing_period_label or "trailing twelve months (assumed; source stated no period)",
                    provider=provider,
                    currency=currency,
                    period_undeclared_by_source=not trailing_period_label,
                ),
                unavailable,
            )
        if name == "forward":
            return (
                EpsAnchor(
                    value=numeric,
                    basis=ANCHOR_FORWARD,
                    months_covered=forward_months_covered,
                    period_label=forward_period_label
                    or f"forward {forward_months_covered:g} months (assumed; source stated no period)",
                    provider=provider,
                    currency=currency,
                    period_undeclared_by_source=not forward_period_label,
                ),
                unavailable,
            )
        return (
            EpsAnchor(
                value=numeric,
                basis=ANCHOR_FORWARD,
                months_covered=forward_months_covered,
                period_label="consensus forward EPS (source stated no period)",
                provider=provider,
                currency=currency,
                period_undeclared_by_source=True,
            ),
            unavailable,
        )

    unavailable.append(
        {
            "item": "start_anchor",
            "reason": (
                "No positive EPS was observed, so no starting point exists for a growth "
                "bridge. The matrix cannot be computed without one."
            ),
            "reason_kind": "MISSING",
            "blocks": ["reverse_requirements_matrix"],
        }
    )
    return None, unavailable


def build_exit_multiples(
    *,
    historical_pe_band: Optional[Dict[str, Any]],
    user_pe_multiple: Optional[float],
    min_observations: int,
) -> Tuple[List[ReferenceMultiple], List[Dict[str, Any]]]:
    """
    The exit multiples the matrix is computed over.

    A historical band with too few observations is reported as descriptive
    rather than silently promoted into a reference. When the band cannot serve
    and the user supplied no multiple, the matrix is left empty and the reason
    is recorded, because inventing a plausible-looking multiple would put a
    fabricated number at the centre of every downstream conclusion.
    """
    multiples: List[ReferenceMultiple] = []
    unavailable: List[Dict[str, Any]] = []

    band = historical_pe_band or {}
    band_median = _safe_float(band.get("median"))
    usable, declared_count = band_reference_eligibility(band, min_observations=min_observations)
    supplied_multiple_value = _safe_float(user_pe_multiple)
    supplied_multiple_usable = (
        supplied_multiple_value is not None and supplied_multiple_value > 0
    )

    if band_median is not None and band_median > 0:
        if usable:
            multiples.append(
                ReferenceMultiple(
                    value=band_median,
                    source="historical_pe_band_median",
                    sample_size=declared_count,
                    period_label=str(band.get("period_label") or ""),
                    is_user_assumption=False,
                    eligibility_state="ELIGIBLE_HISTORICAL_BAND",
                    usable_for_reference=True,
                )
            )
        else:
            if declared_count is None:
                reason = (
                    "The historical P/E band does not declare a valid non-negative integer "
                    f"observation count, so it cannot be verified against the {min_observations} "
                    f"observation minimum. Its median ({band_median:g}) is descriptive only "
                    "and is not used as a reference multiple."
                )
                reason_kind = "OBSERVATION_COUNT_UNVERIFIED"
            else:
                reason = (
                    f"The historical P/E band holds {declared_count} observations, below the "
                    f"{min_observations} required to use it as a reference. Its median "
                    f"({band_median:g}) is descriptive only and is not used as a reference multiple."
                )
                reason_kind = "INSUFFICIENT_OBSERVATIONS"
            unavailable.append(
                {
                    "item": "exit_multiple.historical",
                    "reason": reason,
                    "reason_kind": reason_kind,
                    "blocks": [] if supplied_multiple_usable else ["exit_multiple"],
                }
            )

    if user_pe_multiple is not None:
        multiple_value = _safe_float(user_pe_multiple)
        if multiple_value is not None and multiple_value > 0:
            # An explicitly supplied multiple overrides the band, matching the
            # existing reverse-valuation engine: the user has stated which
            # reference they mean, so adding the band median as a second
            # scenario would answer a question they did not ask. The band
            # median is still reported below as a descriptive cross-check.
            if multiples and multiples[0].source == "historical_pe_band_median":
                multiples = [
                    ReferenceMultiple(
                        value=multiple_value,
                        source="user_supplied",
                        sample_size=multiples[0].sample_size,
                        period_label=multiples[0].period_label,
                        is_user_assumption=True,
                        eligibility_state="USER_SPECIFIED",
                        usable_for_reference=True,
                    )
                ]
            else:
                multiples = [
                    ReferenceMultiple(
                        value=multiple_value,
                        source="user_supplied",
                        is_user_assumption=True,
                        eligibility_state="USER_SPECIFIED",
                        usable_for_reference=True,
                    )
                ]
        else:
            unavailable.append(
                {
                    "item": "exit_multiple.user_supplied",
                    "reason": (
                        f"The supplied exit multiple {user_pe_multiple!r} is not positive, "
                        "so it cannot invert a price into an EPS."
                    ),
                    "reason_kind": "NOT_POSITIVE",
                    "blocks": ["exit_multiple"],
                }
            )

    if not multiples:
        unavailable.append(
            {
                "item": "exit_multiple",
                "reason": (
                    "No exit multiple is available. The historical band did not carry enough "
                    "observations to serve as a reference and no multiple was supplied, so the "
                    "reverse requirements matrix cannot be built."
                ),
                "reason_kind": "MISSING",
                "blocks": ["reverse_requirements_matrix"],
            }
        )

    return multiples, unavailable


def exit_multiples_from_band(
    band: Optional[Dict[str, Any]],
    *,
    min_observations: int,
    percentiles: Sequence[float] = (10.0, 25.0, 50.0, 75.0, 90.0),
) -> Tuple[List[ReferenceMultiple], List[Dict[str, Any]]]:
    """
    Exit multiple scenarios taken from a historical distribution.

    Only a band that passes the shared eligibility rule
    (`band_reference_eligibility`: a declared sample count of at least
    `min_observations` beside a positive median) contributes scenarios. A thin
    band's median, and a band that declares no sample count at all, are
    reported as descriptive figures but are not turned into scenarios, because
    calling an uncounted or under-sampled median a historical distribution
    would present a descriptive statistic as though it were an established
    fact about the past.

    The returned multiples are labelled with the percentile they came from and
    carry the sample size, so a reader can see how thin the history is.
    """
    multiples: List[ReferenceMultiple] = []
    unavailable: List[Dict[str, Any]] = []
    band = band or {}

    band_median = _safe_float(band.get("median"))
    if band_median is None:
        return multiples, unavailable

    usable, declared = band_reference_eligibility(band, min_observations=min_observations)
    if not usable:
        if declared is None:
            reason_kind = "OBSERVATION_COUNT_UNVERIFIED"
            reason = (
                "The historical P/E band does not declare a valid non-negative integer "
                "observation count, so it cannot be verified against the %d required "
                "to read a percentile from it. The band's median of %.4g is reported as "
                "a descriptive statistic only and is not used as a scenario exit "
                "multiple." % (min_observations, band_median)
            )
        else:
            reason_kind = "INSUFFICIENT_OBSERVATIONS"
            reason = (
                "The historical P/E band holds %d observations, below the %d required "
                "to read a percentile from it. The band's median of %.4g is reported as "
                "a descriptive statistic only and is not used as a scenario exit "
                "multiple." % (declared, min_observations, band_median)
            )
        unavailable.append(
            {
                "item": "exit_multiple.band_scenarios",
                "reason": reason,
                "reason_kind": reason_kind,
                "blocks": ["exit_multiple.band_scenarios"],
            }
        )
        return multiples, unavailable

    for percentile in percentiles:
        key = {10.0: "10th", 25.0: "25th", 50.0: "median", 75.0: "75th", 90.0: "90th"}.get(
            float(percentile)
        )
        if key is None:
            continue
        value = _safe_float(band.get(key))
        if value is None or value <= 0:
            continue
        multiples.append(
            ReferenceMultiple(
                value=value,
                source="historical_pe_band_percentile",
                period_label=str(band.get("period_label") or ""),
                sample_size=declared,
                sample_period=(
                    "band percentiles from %d observations" % declared
                ),
                is_user_assumption=False,
                eligibility_state="ELIGIBLE_HISTORICAL_BAND",
                usable_for_reference=True,
            )
        )
    return multiples, unavailable


def exit_multiples_from_production_distribution(
    distribution: Optional[Dict[str, Any]],
    *,
    min_observations: int = 20,
    percentiles: Sequence[float] = (10.0, 25.0, 50.0, 75.0, 90.0),
) -> Tuple[List[ReferenceMultiple], List[Dict[str, Any]]]:
    """
    Exit multiple scenarios taken from a production point-in-time historical P/E distribution.

    Strictly enforces ADR Decision 9 & CONTRACT §K.2: only a distribution that
    its own gate marks eligible (`usable_for_reference` true, or the status that
    states it) qualifies for reference distribution status. A distribution that
    declares too few observations, or one that carries enough observations but
    declares itself ineligible, is reported with its reason and produces no
    scenario multiples: the declared eligibility status is what decides, so a
    merely large count cannot promote a distribution the gate refused.
    """
    multiples: List[ReferenceMultiple] = []
    unavailable: List[Dict[str, Any]] = []
    if not distribution:
        return multiples, unavailable

    sample_count = distribution.get("sample_count")
    status = distribution.get("status")
    period_start = distribution.get("period_start")
    period_end = distribution.get("period_end")
    percentiles_dict = distribution.get("percentiles") or {}
    median = _safe_float(percentiles_dict.get("median"))

    if median is None:
        return multiples, unavailable

    declared_count = _declared_sample_count(sample_count)
    if declared_count is None:
        # A distribution that declares no verifiable sample count cannot be
        # checked against the threshold; state that instead of returning
        # silently.
        unavailable.append(
            {
                "item": "exit_multiple.production_historical_pe_scenarios",
                "reason": (
                    "The production historical P/E distribution does not declare a valid "
                    "non-negative integer sample count, so it cannot be verified against "
                    "the %d required to establish an authoritative reference distribution. "
                    "The median of %.4g is reported as a descriptive statistic only and is "
                    "not used as a scenario exit multiple." % (min_observations, median)
                ),
                "reason_kind": "OBSERVATION_COUNT_UNVERIFIED",
                "blocks": ["exit_multiple.production_historical_pe_scenarios"],
            }
        )
        return multiples, unavailable

    usable = (
        distribution.get("usable_for_reference") is True
        or status == "USABLE_FOR_REFERENCE"
    )

    if not usable:
        if declared_count >= min_observations:
            reason_kind = "INELIGIBLE_STATUS"
            reason = (
                "The production historical P/E distribution holds %d observations but "
                "declares the eligibility status %s, so it is not an authoritative "
                "reference distribution. The median of %.4g is reported as a descriptive "
                "statistic only and is not used as a scenario exit multiple."
                % (declared_count, status, median)
            )
        else:
            reason_kind = "INSUFFICIENT_OBSERVATIONS"
            reason = (
                "The production historical P/E distribution holds %d observations, below the %d "
                "required to establish an authoritative reference distribution. The median of %.4g "
                "is reported as a descriptive statistic only and is not used as a scenario exit "
                "multiple." % (declared_count, min_observations, median)
            )
        unavailable.append(
            {
                "item": "exit_multiple.production_historical_pe_scenarios",
                "reason": reason,
                "reason_kind": reason_kind,
                "blocks": ["exit_multiple.production_historical_pe_scenarios"],
            }
        )
        return multiples, unavailable

    period_label = f"{period_start} to {period_end}" if period_start and period_end else ""
    for percentile in percentiles:
        key = {10.0: "10th", 25.0: "25th", 50.0: "median", 75.0: "75th", 90.0: "90th"}.get(
            float(percentile)
        )
        if key is None:
            continue
        val = _safe_float(percentiles_dict.get(key))
        if val is None or val <= 0:
            continue
        multiples.append(
            ReferenceMultiple(
                value=val,
                source="production_historical_pe_percentile",
                period_label=f"{key} ({period_label})" if period_label else key,
                sample_size=declared_count,
                sample_period=(
                    "production historical P/E %s from %d observations (%s)"
                    % (key, declared_count, period_label)
                ),
                is_user_assumption=False,
                eligibility_state="ELIGIBLE_PRODUCTION_DISTRIBUTION",
                usable_for_reference=True,
            )
        )
    return multiples, unavailable


def valuation_method_scenarios(
    *,
    price: float,
    shares: Optional[float],
    market_cap: Optional[float],
    enterprise_value: Optional[float],
    free_cash_flow: Optional[float],
    ebitda: Optional[float],
    revenue: Optional[float],
    trailing_eps: Optional[float],
    observed_net_margin: Optional[float] = None,
    observed_net_margin_period: Optional[str] = None,
    observed_shares_outstanding: Optional[float] = None,
    observed_shares_date: Optional[str] = None,
    multiples: Dict[str, ReferenceMultiple],
) -> Dict[str, Any]:
    """
    Conditional results per valuation method, kept as separate answers.

    The earnings method, the revenue method, the cash flow method and the
    enterprise-value method are four different questions. When they disagree
    they are reported as disagreeing. This function does not rank them, pick a
    winner, or average them into a single number, because doing so would
    manufacture a consensus the underlying evidence does not contain.
    """
    unavailable: List[Dict[str, Any]] = []
    methods: Dict[str, Any] = {}

    cap = _safe_float(market_cap)
    ev = _safe_float(enterprise_value)
    share_count = _safe_float(shares)

    def record(
        name: str,
        *,
        implied: Optional[float],
        observed: Optional[float],
        multiple: Optional[ReferenceMultiple],
        unit: str,
        missing_reason: str,
        observed_label: str,
        notes: Sequence[str] = (),
    ) -> None:
        if multiple is None:
            unavailable.append(
                {
                    "item": "valuation_method.%s" % name,
                    "reason": missing_reason,
                    "reason_kind": "NO_REFERENCE_MULTIPLE",
                    "blocks": ["valuation_method.%s" % name],
                }
            )
        elif implied is None:
            unavailable.append(
                {
                    "item": "valuation_method.%s" % name,
                    "reason": (
                        "The %s reference multiple is available but the input it inverts "
                        "(%s) was not observed, so no implied figure is produced."
                        % (name, missing_reason)
                    ),
                    "reason_kind": "MISSING_INPUT",
                    "blocks": ["valuation_method.%s" % name],
                }
            )
        methods[name] = {
            "implied": implied,
            "unit": unit,
            "reference_multiple": multiple.contract_view() if multiple else None,
            "observed": observed,
            "observed_label": observed_label,
            "gap_implied_vs_observed": _gap(implied, observed),
            "notes": list(notes),
            "status": "COMPUTED" if implied is not None else "NOT_COMPUTED",
        }

    price_value = _safe_float(price)
    # A non-positive price is a degenerate input, not a reason to abort a whole
    # report. The public helpers refuse it loudly because they are also called
    # directly; here the affected figures simply stay absent.
    usable_price = price_value if price_value is not None and price_value > 0 else None
    pe_multiple = multiples.get("pe")
    eps = _safe_float(trailing_eps)
    record(
        "earnings_multiple",
        implied=(
            implied_eps_at_multiple(usable_price, pe_multiple.value)
            if usable_price is not None and pe_multiple is not None
            else None
        ),
        observed=eps,
        multiple=pe_multiple,
        unit="per_share",
        missing_reason="the current share price",
        observed_label="observed trailing EPS",
        notes=(
            "This is the EPS the chosen P/E corresponds to at the current price. It is not "
            "a forecast and not a statement about what the market expects.",
        ),
    )

    revenue_multiple = multiples.get("revenue")
    record(
        "revenue_multiple",
        implied=(
            required_revenue_at_multiple(cap, revenue_multiple.value)
            if cap is not None and revenue_multiple is not None
            else None
        ),
        observed=_safe_float(revenue),
        multiple=revenue_multiple,
        unit="currency",
        missing_reason="market capitalization",
        observed_label="the observed trailing revenue",
        notes=(
            "Market capitalization divided by the chosen P/S. It prices the company's "
            "current equity value, so it says nothing about enterprise value.",
        ),
    )

    fcf_multiple = multiples.get("cash_flow")
    record(
        "cash_flow_multiple",
        implied=(
            required_fcf_at_multiple(cap, fcf_multiple.value)
            if cap is not None and fcf_multiple is not None
            else None
        ),
        observed=_safe_float(free_cash_flow),
        multiple=fcf_multiple,
        unit="currency",
        missing_reason="market capitalization",
        observed_label="the observed trailing free cash flow",
        notes=(
            "The free cash flow definition behind the observed figure is the provider's. "
            "It is not reconciled to an operating cash flow minus capital expenditure "
            "bridge, so the implied and observed figures share whatever definition the "
            "provider applied.",
        ),
    )

    ev_ebitda_multiple = multiples.get("enterprise_value")
    record(
        "enterprise_value_multiple",
        implied=(
            required_ebitda_at_multiple(ev, ev_ebitda_multiple.value)
            if ev is not None and ev_ebitda_multiple is not None
            else None
        ),
        observed=_safe_float(ebitda),
        multiple=ev_ebitda_multiple,
        unit="currency",
        missing_reason="enterprise value",
        observed_label="the observed trailing EBITDA",
        notes=(
            "Enterprise value divided by the chosen EV/EBITDA. Enterprise value is taken "
            "as observed rather than rebuilt from market cap plus net debt, because the "
            "provider's debt and cash definitions are not reconciled to the market cap's.",
        ),
    )

    # The implied margin is computed twice, on two different share bases.
    #
    # The original derivation divides market capitalization by price to recover
    # a share count, which keeps the answer consistent with the vendor's own
    # market capitalization. The alternative uses a dated shares-outstanding
    # observation, which is independent of the vendor figure but refers to a
    # cover-page instant rather than the weighted-average diluted count EPS
    # uses. Neither is right in general, so both are reported and labelled.
    derived_shares = None
    if cap is not None and usable_price is not None:
        derived_shares = cap / usable_price

    observed_shares_count = _safe_float(observed_shares_outstanding)
    variants = []
    if derived_shares is not None:
        variants.append(
            {
                "label": "derived share count (market capitalization / price)",
                "implied": implied_net_margin_at_multiples(
                    implied_eps_at_multiple(usable_price, pe_multiple.value)
                    if usable_price is not None and pe_multiple is not None
                    else None,
                    required_revenue_at_multiple(cap, revenue_multiple.value)
                    if cap is not None and revenue_multiple is not None
                    else None,
                    derived_shares,
                ),
                "shares": derived_shares,
                "shares_source": "derived",
                "shares_date": None,
                "is_original_formula": True,
            }
        )
    if observed_shares_count is not None and observed_shares_count > 0:
        variants.append(
            {
                "label": "observed shares outstanding (point-in-time)",
                "implied": implied_net_margin_at_multiples(
                    implied_eps_at_multiple(usable_price, pe_multiple.value)
                    if usable_price is not None and pe_multiple is not None
                    else None,
                    required_revenue_at_multiple(cap, revenue_multiple.value)
                    if cap is not None and revenue_multiple is not None
                    else None,
                    observed_shares_count,
                ),
                "shares": observed_shares_count,
                "shares_source": "observed",
                "shares_date": observed_shares_date,
                "is_original_formula": False,
                "note": (
                    "A cover-page shares-outstanding count is not the weighted-average "
                    "diluted count EPS uses. Using it changes the implied net income, so "
                    "the result is labelled rather than presented as the same measure."
                ),
            }
        )

    combined = None
    for variant in variants:
        if variant["implied"] is not None:
            combined = variant["implied"]
            break
    observed_margin: Optional[float] = None
    observed_margin_period: Optional[str] = None
    margin_gap: Optional[float] = None
    if combined is not None and observed_net_margin is not None:
        observed_margin = observed_net_margin
        margin_gap = combined - observed_margin
        if observed_net_margin_period:
            observed_margin_period = observed_net_margin_period

    methods["implied_net_margin"] = {
        "implied": combined,
        "unit": "ratio",
        "share_basis": "derived" if variants and variants[0]["shares_source"] == "derived" else None,
        "share_basis_variants": variants,
        "reference_multiple": {
            "pe": pe_multiple.contract_view() if pe_multiple else None,
            "revenue": revenue_multiple.contract_view() if revenue_multiple else None,
        },
        "observed": observed_margin,
        "observed_label": (
            "observed net margin for %s" % observed_margin_period if observed_margin_period else None
        ),
        "observed_margin_period": observed_margin_period,
        "gap_implied_vs_observed": margin_gap,
        "status": "COMPUTED" if combined is not None else "NOT_COMPUTED",
        "notes": [
            "Requires a P/E multiple, a P/S multiple and a share count at once.",
            (
                "Two share bases are reported. The derived one is the original formula and "
                "is kept as the headline; the observed one is offered alongside because it "
                "does not inherit the vendor's market capitalization."
                if len(variants) > 1
                else "The share count is derived from market capitalization divided by price."
            ),
            (
                "The observed net margin is the margin the filings report for the stated "
                "period. It is compared here rather than left as a separate series, because "
                "the implied margin is a statement about exactly that quantity."
            )
            if margin_gap is not None
            else "No observed net margin was available for the same measure, so no gap is "
            "reported.",
        ],
    }

    computed = [name for name, block in methods.items() if block["status"] == "COMPUTED"]
    spread = None
    if len(computed) >= 2:
        spread = {
            "methods_computed": sorted(computed),
            "note": (
                "These methods answer different questions and can disagree. They are "
                "reported side by side and no winner is selected: averaging them would "
                "produce a single number that none of the inputs supports."
            ),
        }

    return {
        "methods": methods,
        "disagreement": spread,
        "unavailable": unavailable,
        "reading_notes": [
            "Each method is conditional on its own reference multiple and carries that "
            "multiple's provenance.",
            "No method is ranked against another and no composite valuation is produced.",
        ],
    }


def compute_fingerprint(payload: Dict[str, Any]) -> str:
    """
    A stable digest of the inputs and the formula version.

    Two runs that produce the same fingerprint were the same calculation. A
    changed fingerprint means an input or the formula moved, so a consumer
    should treat the outputs as a different result rather than a confirmation.
    """
    material = {
        "formula_version": FORMULA_VERSION,
        "payload": payload,
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_consensus_reference(
    *,
    consensus_eps: Optional[float],
    consensus_basis: str = "",
    consensus_months_covered: Optional[float] = None,
    consensus_provider: str = "",
    consensus_period_label: Optional[str] = None,
    consensus_period_end: Optional[str] = None,
    consensus_target_period_end: Optional[str] = None,
) -> Dict[str, Any]:
    """
    The consensus EPS the matrix's gap column is differenced against.

    This block states the source's facts and the rule that consumes them. It
    deliberately does not state a verdict: whether a *particular* row's terminal
    EPS covers the same period depends on that row's horizon, so the verdict
    travels on each scenario as a flag and a reason. Restating one here would
    be a second, possibly different, answer.

    `consensus_period_label` is the vendor's own label, kept verbatim.
    `consensus_period_end` is the calendar date the same source declared for
    that estimate, or None when it declared none. Nothing in this block derives
    one from the other.
    """
    declared = parse_iso_date(consensus_period_end)
    return {
        "eps": _safe_float(consensus_eps),
        "provider": consensus_provider,
        "basis": consensus_basis,
        "months_covered": _safe_float(consensus_months_covered),
        "source_period_label": consensus_period_label,
        "period_end": declared.isoformat() if declared is not None else None,
        "period_end_declared_by_source": declared is not None,
        # The end of the window the one-year terminal EPS covers, so a reader
        # can compare the two dates without recomputing either.
        "target_period_end": consensus_target_period_end,
        "comparison_tolerance_days": CONSENSUS_PERIOD_TOLERANCE_DAYS,
        "comparable_horizon_years": CONSENSUS_COMPARABLE_HORIZON_YEARS,
    }


def build_reverse_requirements_report(
    *,
    price: float,
    ticker: str,
    currency: Optional[str],
    as_of: str,
    price_source: str,
    horizons_years: Sequence[float],
    required_returns: Sequence[float],
    exit_multiples: Sequence[ReferenceMultiple],
    start_anchor: EpsAnchor,
    current_pe: Optional[float] = None,
    current_trailing_pe: Optional[float] = None,
    consensus_eps: Optional[float] = None,
    consensus_basis: str = "",
    consensus_months_covered: Optional[float] = None,
    consensus_period_label: Optional[str] = None,
    consensus_period_end: Optional[str] = None,
    consensus_target_period_end: Optional[str] = None,
    consensus_provider: str = "",
    dividend_per_share: Optional[float] = None,
    dividend_source: str = "",
    market_cap: Optional[float] = None,
    enterprise_value: Optional[float] = None,
    free_cash_flow: Optional[float] = None,
    ebitda: Optional[float] = None,
    revenue: Optional[float] = None,
    pfcf_multiple: Optional[float] = None,
    ev_ebitda_multiple: Optional[float] = None,
    ps_multiple: Optional[float] = None,
    observed_net_margin: Optional[float] = None,
    observed_net_margin_period: Optional[str] = None,
    observed_shares_outstanding: Optional[float] = None,
    observed_shares_date: Optional[str] = None,
    valuation_multiples: Optional[Dict[str, ReferenceMultiple]] = None,
    shares: Optional[float] = None,
    risk_free_rates: Sequence[RiskFreeRate] = (),
    cost_of_equity_inputs: Optional[Dict[str, Any]] = None,
    investor_required_returns: Optional[Dict[str, Any]] = None,
    dcf_inputs: Optional[Dict[str, Any]] = None,
    unavailable: Optional[Iterable[Dict[str, Any]]] = None,
    production_historical_pe: Optional[Dict[str, Any]] = None,
    price_evidence: Optional[Dict[str, Any]] = None,
    eps_anchor_catalogue: Optional[Dict[str, Any]] = None,
    eps_anchor_selection: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Assemble the whole V1 package: the matrix, the cash flow cross-checks, the
    separated rate families, and an explicit statement of what is missing.

    The EPS anchor catalogue and its selection record travel with the report
    when the run asked for a named catalogue anchor: every entry the issuer has
    evidence for, what each one is, and which one the matrix actually started
    from (or the specific reason the named one was refused). A run that made no
    explicit request reports neither block and is byte-identical to before.
    """
    from historical_pe import production_distribution_summary

    if price_evidence is None:
        price_evidence = {
            "value": price,
            "currency": currency,
            "as_of": as_of,
            "provider": price_source,
            "source_type": "OBSERVED",
            "observation_id": "ev-price-001",
            "is_user_assumption": False,
        }

    # Baseline price-return matrix is strictly preserved as price return only.
    scenarios = build_matrix(
        price=price,
        horizons_years=horizons_years,
        required_returns=required_returns,
        exit_multiples=exit_multiples,
        start_anchor=start_anchor,
        current_pe=current_pe,
        consensus_eps=consensus_eps,
        consensus_basis=consensus_basis,
        consensus_months_covered=consensus_months_covered,
        consensus_period_end=consensus_period_end,
        dividend_per_share=None,
        currency=currency,
        as_of=as_of,
        dividend_convention=DIVIDEND_CONVENTION_PRICE_ONLY,
        price_evidence=price_evidence,
    )

    unavailable: List[Dict[str, Any]] = list(unavailable or [])

    consensus_reference = build_consensus_reference(
        consensus_eps=consensus_eps,
        consensus_basis=consensus_basis,
        consensus_months_covered=consensus_months_covered,
        consensus_provider=consensus_provider,
        consensus_period_label=consensus_period_label,
        consensus_period_end=consensus_period_end,
        consensus_target_period_end=consensus_target_period_end,
    )

    div_val = _safe_float(dividend_per_share)
    total_return_scenarios = None
    comparison_rows = []
    dividend_basis_block = None

    if div_val is not None and div_val > 0:
        cash_scenarios = build_matrix(
            price=price,
            horizons_years=horizons_years,
            required_returns=required_returns,
            exit_multiples=exit_multiples,
            start_anchor=start_anchor,
            current_pe=current_pe,
            consensus_eps=consensus_eps,
            consensus_basis=consensus_basis,
            consensus_months_covered=consensus_months_covered,
            consensus_period_end=consensus_period_end,
            dividend_per_share=div_val,
            currency=currency,
            as_of=as_of,
            dividend_convention=DIVIDEND_CONVENTION_CASH_RETAINED,
            price_evidence=price_evidence,
        )
        reinvested_scenarios = build_matrix(
            price=price,
            horizons_years=horizons_years,
            required_returns=required_returns,
            exit_multiples=exit_multiples,
            start_anchor=start_anchor,
            current_pe=current_pe,
            consensus_eps=consensus_eps,
            consensus_basis=consensus_basis,
            consensus_months_covered=consensus_months_covered,
            dividend_per_share=div_val,
            currency=currency,
            as_of=as_of,
            dividend_convention=DIVIDEND_CONVENTION_REINVESTED,
            price_evidence=price_evidence,
        )

        for p_scen, c_scen, r_scen in zip(scenarios, cash_scenarios, reinvested_scenarios):
            comparison_rows.append({
                "horizon_years": p_scen.horizon_years,
                "required_return": p_scen.required_return,
                "exit_multiple": p_scen.exit_multiple.value,
                "exit_multiple_source": p_scen.exit_multiple.source,
                "price_only": {
                    "required_exit_price": p_scen.required_exit_price,
                    "required_terminal_eps": p_scen.required_terminal_eps,
                    "required_eps_cagr": p_scen.required_eps_cagr,
                },
                "cash_dividends_retained": {
                    "required_exit_price": c_scen.required_exit_price,
                    "required_terminal_eps": c_scen.required_terminal_eps,
                    "required_eps_cagr": c_scen.required_eps_cagr,
                    "delta_exit_price": c_scen.dividend_relief_exit_price,
                    "delta_terminal_eps": c_scen.dividend_relief_terminal_eps,
                    "delta_eps_cagr": c_scen.dividend_relief_cagr,
                },
                "dividends_reinvested_at_target_return": {
                    "required_exit_price": r_scen.required_exit_price,
                    "required_terminal_eps": r_scen.required_terminal_eps,
                    "required_eps_cagr": r_scen.required_eps_cagr,
                    "delta_exit_price": r_scen.dividend_relief_exit_price,
                    "delta_terminal_eps": r_scen.dividend_relief_terminal_eps,
                    "delta_eps_cagr": r_scen.dividend_relief_cagr,
                },
            })

        total_return_scenarios = {
            "cash_dividends_retained": [s.contract_view() for s in cash_scenarios],
            "dividends_reinvested_at_target_return": [s.contract_view() for s in reinvested_scenarios],
        }
        dividend_basis_block = {
            "dividend_per_share": div_val,
            "dividend_source": dividend_source or "Observed market chart events / SEC filings",
            "dividend_currency": currency,
            "dividend_period": "TTM",
            "conventions": [
                {
                    "convention": DIVIDEND_CONVENTION_CASH_RETAINED,
                    "formula": "P_T = P_0 * (1 + r)^T - T * D",
                    "description": "Cash dividends retained as uninvested cash; cumulative cash is subtracted from required exit share price.",
                },
                {
                    "convention": DIVIDEND_CONVENTION_REINVESTED,
                    "formula": "P_T = P_0 * (1 + r)^T - D * ((1 + r)^T - 1) / r",
                    "description": "Dividends reinvested annually at the target required return rate r; future value of dividend annuity is subtracted from required exit share price.",
                },
            ],
        }

    cash_flow_cross_checks = _cash_flow_cross_checks(
        market_cap=market_cap,
        enterprise_value=enterprise_value,
        free_cash_flow=free_cash_flow,
        ebitda=ebitda,
        revenue=revenue,
        pfcf_multiple=pfcf_multiple,
        ev_ebitda_multiple=ev_ebitda_multiple,
        ps_multiple=ps_multiple,
        price=price,
    )

    rate_families = _rate_families(
        risk_free_rates=risk_free_rates,
        cost_of_equity_inputs=cost_of_equity_inputs,
        investor_required_returns=investor_required_returns,
        required_returns=required_returns,
    )

    dcf_block = _dcf_block(dcf_inputs)

    methods_block = valuation_method_scenarios(
        price=price,
        shares=shares,
        market_cap=market_cap,
        enterprise_value=enterprise_value,
        free_cash_flow=free_cash_flow,
        ebitda=ebitda,
        revenue=revenue,
        trailing_eps=(start_anchor.value if start_anchor is not None else None),
        observed_net_margin=observed_net_margin,
        observed_net_margin_period=observed_net_margin_period,
        observed_shares_outstanding=observed_shares_outstanding,
        observed_shares_date=observed_shares_date,
        multiples=valuation_multiples or {},
    )

    fingerprint_payload = {
        "ticker": ticker,
        "as_of": as_of,
        "price": price,
        "currency": currency,
        "horizons_years": list(horizons_years),
        "required_returns": list(required_returns),
        "exit_multiples": [m.contract_view() for m in exit_multiples],
        "valuation_multiples": {
            key: value.contract_view() for key, value in (valuation_multiples or {}).items()
        },
        "shares": shares,
        "observed_shares_outstanding": observed_shares_outstanding,
        "observed_shares_date": observed_shares_date,
        "start_anchor": start_anchor.contract_view(),
        "current_pe": current_pe,
        "consensus_eps": consensus_eps,
        "consensus_basis": consensus_basis,
        # The declared period end is in the payload because it decides whether
        # a consensus gap is reported at all. Two runs whose consensus values
        # match but whose declared periods differ produce different gap columns
        # and therefore are not the same calculation.
        "consensus_period_end": consensus_reference["period_end"],
        "consensus_period_label": consensus_period_label,
        "dividend_per_share": dividend_per_share,
        "market_cap": market_cap,
        "enterprise_value": enterprise_value,
        "free_cash_flow": free_cash_flow,
        "ebitda": ebitda,
        "revenue": revenue,
        "pfcf_multiple": pfcf_multiple,
        "ev_ebitda_multiple": ev_ebitda_multiple,
        "ps_multiple": ps_multiple,
        "risk_free_rates": [r.contract_view() for r in risk_free_rates],
    }

    return {
        "report": "reverse_requirements_v1",
        "formula_version": FORMULA_VERSION,
        "fingerprint": compute_fingerprint(fingerprint_payload),
        "asset": {"ticker": ticker, "currency": currency},
        "as_of": as_of,
        "market_price": {"value": price, "currency": currency, "source": price_source},
        "reverse_requirements_matrix": [s.contract_view() for s in scenarios],
        "matrix_size": len(scenarios),
        "cash_flow_cross_checks": cash_flow_cross_checks,
        "valuation_methods": methods_block,
        "rate_families": rate_families,
        "dcf": dcf_block,
        "production_historical_pe": production_historical_pe,
        # The compact statement of the production distribution's identity and
        # eligibility. Readers that only need to judge the reference use this;
        # the full payload stays available above for the underlying evidence.
        "production_historical_pe_summary": production_distribution_summary(
            production_historical_pe
        ),
        # The consensus the gap column is differenced against, with the period
        # the source declared for it, so an eligible gap can be checked and a
        # missing one explained rather than read as a zero.
        "consensus_reference": consensus_reference,
        "total_return_scenarios": total_return_scenarios,
        "price_vs_total_return_comparison": comparison_rows,
        "dividend_basis": dividend_basis_block,
        "unavailable": list(unavailable or []),
        **(
            {
                "eps_anchor_catalogue": eps_anchor_catalogue,
                "eps_anchor_selection": eps_anchor_selection,
            }
            if eps_anchor_catalogue is not None or eps_anchor_selection is not None
            else {}
        ),
        "reading_notes": [
            "The baseline reverse-requirements matrix is strictly price-return-only; required returns exclude dividends.",
            "When a dividend per share is supplied, two additional scenario sets are computed: cash dividends retained and dividends reinvested at the target return.",
            "A required terminal EPS is the EPS that the chosen exit multiple corresponds to, "
            "not a forecast and not a market expectation.",
            "A CAGR is reported only when the gap between the two EPS anchors is long enough "
            "to annualise; otherwise the raw EPS change is reported without a rate.",
            "Risk-free rates, modelled cost of equity and investor target returns are three "
            "separate kinds of number and are never merged into one figure.",
            "A consensus gap is differenced only when the period the source declared for the "
            "consensus lines up with the terminal EPS window. Otherwise the gap is left "
            "unreported and the reason names both period ends; a missing gap is not a zero.",
        ],
    }


def _cash_flow_cross_checks(
    *,
    market_cap: Optional[float],
    enterprise_value: Optional[float],
    free_cash_flow: Optional[float],
    ebitda: Optional[float],
    revenue: Optional[float],
    pfcf_multiple: Optional[float],
    ev_ebitda_multiple: Optional[float],
    ps_multiple: Optional[float],
    price: float,
) -> Dict[str, Any]:
    """
    Cash flow and operating cross-checks against explicit reference multiples.

    Each entry names the multiple it is conditional on, or records that the
    multiple was not supplied. Observed yields are reported separately from
    reverse-solved amounts so the two are never confused.
    """
    cap = _safe_float(market_cap)
    ev = _safe_float(enterprise_value)
    fcf = _safe_float(free_cash_flow)
    ebitda_value = _safe_float(ebitda)
    revenue_value = _safe_float(revenue)
    price_value = _safe_float(price)

    observed_pfcf = cap / fcf if cap and fcf and fcf > 0 else None
    observed_ev_ebitda = ev / ebitda_value if ev and ebitda_value and ebitda_value > 0 else None
    observed_ps = cap / revenue_value if cap and revenue_value and revenue_value > 0 else None

    entries: Dict[str, Any] = {
        "observed": {
            "p_fcf": observed_pfcf,
            "ev_ebitda": observed_ev_ebitda,
            "p_s": observed_ps,
            "fcf_yield": fcf_yield(fcf, cap) if fcf is not None else None,
            "ebitda_yield_on_ev": (ebitda_value / ev) if ev and ev > 0 and ebitda_value else None,
            "revenue_yield_on_market_cap": (revenue_value / cap) if cap and cap > 0 and revenue_value else None,
        },
        "required_at_reference_multiple": {
            "fcf": {
                "multiple": pfcf_multiple,
                "required_fcf": required_fcf_at_multiple(cap, pfcf_multiple) if pfcf_multiple else None,
                "gap_vs_observed_fcf": _gap(
                    required_fcf_at_multiple(cap, pfcf_multiple) if pfcf_multiple else None, fcf
                ),
                "conditional_on": "the supplied P/FCF multiple",
            },
            "ebitda": {
                "multiple": ev_ebitda_multiple,
                "required_ebitda": required_ebitda_at_multiple(ev, ev_ebitda_multiple)
                if ev_ebitda_multiple
                else None,
                "gap_vs_observed_ebitda": _gap(
                    required_ebitda_at_multiple(ev, ev_ebitda_multiple) if ev_ebitda_multiple else None,
                    ebitda_value,
                ),
                "conditional_on": "the supplied EV/EBITDA multiple",
            },
            "revenue": {
                "multiple": ps_multiple,
                "required_revenue": required_revenue_at_multiple(cap, ps_multiple) if ps_multiple else None,
                "gap_vs_observed_revenue": _gap(
                    required_revenue_at_multiple(cap, ps_multiple) if ps_multiple else None,
                    revenue_value,
                ),
                "conditional_on": "the supplied P/S multiple",
            },
        },
        "notes": [
            "An observed P/FCF is the multiple the market is applying to the reported FCF. "
            "A required FCF is the FCF a chosen multiple would correspond to. They are "
            "different questions and are reported separately.",
        ],
    }
    if price_value is None:
        entries["notes"].append("No price was supplied, so per-share figures are omitted.")
    return entries


def _gap(required: Optional[float], observed: Optional[float]) -> Optional[float]:
    if required is None or observed is None or observed <= 0:
        return None
    return required / observed - 1.0


def _rate_families(
    *,
    risk_free_rates: Sequence[RiskFreeRate],
    cost_of_equity_inputs: Optional[Dict[str, Any]],
    investor_required_returns: Optional[Dict[str, Any]],
    required_returns: Sequence[float],
) -> Dict[str, Any]:
    """
    Three separated rate families.

    Keeping them apart is the point. A risk-free rate is an observation. A cost
    of equity is a model output that depends on a beta and an equity risk
    premium, both of which are estimates. An investor target is a scenario
    input that is allowed to disagree with the model.
    """
    observations = [rate.contract_view() for rate in risk_free_rates]

    cost_of_equity: Dict[str, Any] = {
        "status": "NOT_COMPUTED",
        "method": "CAPM: Rf + beta * ERP",
        "value": None,
        "explanation": (
            "A cost of equity is a model estimate. It is not reported unless a risk-free "
            "rate, a beta and an equity risk premium are each supplied with their own "
            "source and estimation window, because the result inherits every assumption "
            "behind those three inputs."
        ),
    }
    if cost_of_equity_inputs:
        rf = _safe_float(cost_of_equity_inputs.get("risk_free_rate_decimal"))
        beta = _safe_float(cost_of_equity_inputs.get("beta"))
        erp = _safe_float(cost_of_equity_inputs.get("equity_risk_premium_decimal"))
        missing = [
            name
            for name, value in (
                ("risk_free_rate_decimal", rf),
                ("beta", beta),
                ("equity_risk_premium_decimal", erp),
            )
            if value is None
        ]
        if missing:
            cost_of_equity["status"] = "INCOMPLETE_INPUTS"
            cost_of_equity["missing_inputs"] = missing
        else:
            cost_of_equity["status"] = "COMPUTED"
            cost_of_equity["value"] = capm_cost_of_equity(rf, beta, erp)
            cost_of_equity["inputs"] = {
                "risk_free_rate_decimal": rf,
                "risk_free_rate_source": cost_of_equity_inputs.get("risk_free_rate_source", ""),
                "risk_free_rate_as_of": cost_of_equity_inputs.get("risk_free_rate_as_of", ""),
                "beta": beta,
                "beta_source": cost_of_equity_inputs.get("beta_source", ""),
                "beta_estimation_window": cost_of_equity_inputs.get("beta_estimation_window", ""),
                "equity_risk_premium_decimal": erp,
                "equity_risk_premium_source": cost_of_equity_inputs.get("equity_risk_premium_source", ""),
                "equity_risk_premium_estimation_window": cost_of_equity_inputs.get(
                    "equity_risk_premium_estimation_window", ""
                ),
            }
            cost_of_equity["is_estimate"] = True

    investor_block: Dict[str, Any] = {
        "status": "NOT_SUPPLIED",
        "values": None,
        "explanation": (
            "An investor target return is a scenario input. It is reported separately from "
            "the modelled cost of equity and is not required to agree with it."
        ),
    }
    if investor_required_returns:
        investor_block = {
            "status": "SUPPLIED",
            "values": dict(investor_required_returns),
            "is_estimate": False,
            "explanation": (
                "These are the required returns the matrix is computed over. They are the "
                "investor's own hurdle, not an output of any model."
            ),
        }

    return {
        "risk_free_rate": {
            "kind": "OBSERVATION",
            "unit": "percent_per_annum",
            "observations": observations,
            "count": len(observations),
            "explanation": (
                "Each row is one observed rate with its observation date and tenor. A "
                "historical valuation must use the rate available at that date rather than "
                "a rate observed later and substituted backwards."
            ),
        },
        "cost_of_equity": cost_of_equity,
        "investor_required_return": investor_block,
        "matrix_required_returns": list(required_returns),
        "separation_note": (
            "These three are never averaged together. Substituting a single rate for all "
            "three would present an observation, a model estimate and a chosen hurdle as if "
            "they were the same kind of number."
        ),
    }


def _dcf_block(dcf_inputs: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    The discounted cash flow section.

    When the required inputs are present it solves for the constant explicit
    period growth rate that reconciles the modelled value with the observed one.
    When they are not, it names them.
    """
    if not dcf_inputs:
        return {
            "status": "NOT_ATTEMPTED",
            "feasibility": dcf_feasibility(
                has_free_cash_flow=False,
                has_depreciation_amortisation=False,
                has_capex=False,
                has_working_capital_change=False,
                has_cost_of_debt=False,
                has_market_value_of_debt=False,
                has_tax_rate=False,
            ),
            "implied_explicit_growth_rate": None,
            "explanation": (
                "No discounted cash flow inputs were supplied for this run, so none were used."
            ),
        }

    feasibility = dcf_feasibility(
        has_free_cash_flow=bool(dcf_inputs.get("free_cash_flow")),
        has_depreciation_amortisation=bool(dcf_inputs.get("depreciation_amortisation")),
        has_capex=bool(dcf_inputs.get("capex")),
        has_working_capital_change=bool(dcf_inputs.get("working_capital_change")),
        has_cost_of_debt=bool(dcf_inputs.get("cost_of_debt")),
        has_market_value_of_debt=bool(dcf_inputs.get("market_value_of_debt")),
        has_tax_rate=bool(dcf_inputs.get("tax_rate")),
        cash_flow_basis=str(dcf_inputs.get("cash_flow_basis") or ""),
    )

    discount_rate = _safe_float(dcf_inputs.get("discount_rate_decimal"))
    base_cash_flow = _safe_float(dcf_inputs.get("base_cash_flow"))
    explicit_years = dcf_inputs.get("explicit_years")
    terminal_growth = _safe_float(dcf_inputs.get("terminal_growth_decimal"))
    present_value = _safe_float(dcf_inputs.get("present_value"))

    block: Dict[str, Any] = {
        "status": "NOT_COMPUTED",
        "feasibility": feasibility,
        "implied_explicit_growth_rate": None,
        "assumptions": {
            "cash_flow_basis": dcf_inputs.get("cash_flow_basis"),
            "discount_rate_decimal": discount_rate,
            "discount_rate_source": dcf_inputs.get("discount_rate_source", ""),
            "explicit_years": explicit_years,
            "terminal_growth_decimal": terminal_growth,
            "terminal_growth_source": dcf_inputs.get("terminal_growth_source", ""),
            "present_value": present_value,
            "present_value_source": dcf_inputs.get("present_value_source", ""),
            "base_cash_flow": base_cash_flow,
        },
    }

    if not feasibility["supported"]:
        block["explanation"] = (
            "The inputs required for a discounted cash flow model were not all observed, so "
            "no implied growth rate is reported. The missing inputs are named so a later run "
            "can close the gap rather than guess at it."
        )
        return block

    if discount_rate is None or base_cash_flow is None or terminal_growth is None or present_value is None:
        block["status"] = "INCOMPLETE_INPUTS"
        block["explanation"] = (
            "The cash flow bridge is complete, but the discount rate, base cash flow, "
            "terminal growth rate or present value is missing, so nothing was solved."
        )
        return block

    if not isinstance(explicit_years, int) or explicit_years < 1:
        block["status"] = "INVALID_EXPLICIT_PERIOD"
        block["explanation"] = (
            f"The explicit forecast period must be a whole number of years of at least 1, got {explicit_years!r}."
        )
        return block

    if discount_rate <= terminal_growth:
        block["status"] = "INVALID_DISCOUNT_PARAMETERS"
        block["explanation"] = (
            f"The terminal growth rate {terminal_growth!r} is not below the discount rate "
            f"{discount_rate!r}, so the terminal value is undefined."
        )
        return block

    solved = solve_implied_growth_rate(
        present_value=present_value,
        base_cash_flow=base_cash_flow,
        discount_rate=discount_rate,
        explicit_years=explicit_years,
        terminal_growth=terminal_growth,
        growth_bounds=tuple(dcf_inputs.get("growth_bounds", (-0.95, 3.0))),  # type: ignore[arg-type]
    )
    if solved is None:
        block["status"] = "NO_SOLUTION_IN_BOUNDS"
        block["explanation"] = (
            "No constant explicit-period growth rate inside the searched range reconciles "
            "the modelled value with the observed one under these assumptions."
        )
        return block

    block["status"] = "COMPUTED"
    block["implied_explicit_growth_rate"] = solved
    block["explanation"] = (
        "The constant explicit-period growth rate that makes the modelled value equal the "
        "observed one, at the stated discount rate and terminal growth rate. It says nothing "
        "about the path within the explicit period, and it holds only for the discount rate "
        "and terminal growth rate given above."
    )
    return block
