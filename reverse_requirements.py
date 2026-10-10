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
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from data_contract import currencies_match


# Bumped whenever a formula below changes its meaning. Consumers compare this
# string to decide whether two results are the same calculation or two.
FORMULA_VERSION = "reverse-requirements/1.0"

# The growth window must cover at least this many years for an annualised CAGR
# to mean anything. A shorter window is reported, not extrapolated.
MIN_GROWTH_YEARS = 0.5

# Return labels. A required return without a dividend input is a price return.
RETURN_BASIS_PRICE_ONLY = "PRICE_RETURN_ONLY"
RETURN_BASIS_TOTAL = "TOTAL_RETURN_WITH_SUPPLIED_DIVIDEND"

# EPS anchors. The anchor declares what period its EPS covers; the growth
# arithmetic depends on that declaration, not on the label alone.
ANCHOR_TTM = "TRAILING_TWELVE_MONTHS"
ANCHOR_FORWARD = "FORWARD_TWELVE_MONTHS"
ANCHOR_FISCAL_YEAR = "FISCAL_YEAR"
ANCHOR_USER = "USER_SUPPLIED"

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

    def __post_init__(self) -> None:
        if not math_is_finite(self.value):
            raise ReverseRequirementError(f"EPS anchor value must be a finite number: {self.value!r}")
        if self.months_covered <= 0:
            raise ReverseRequirementError(
                f"EPS anchor must declare a positive coverage window, got {self.months_covered!r}"
            )

    def contract_view(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "basis": self.basis,
            "months_covered": self.months_covered,
            "period_label": self.period_label,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "provider": self.provider,
            "currency": self.currency,
            "period_undeclared_by_source": self.period_undeclared_by_source,
        }


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

    def contract_view(self) -> Dict[str, Any]:
        return {
            "horizon_years": self.horizon_years,
            "required_return": self.required_return,
            "required_return_basis": self.required_return_basis,
            "exit_multiple": self.exit_multiple.contract_view(),
            "required_exit_price": self.required_exit_price,
            "required_exit_price_basis": "PRICE_ONLY_EXCLUDES_DIVIDENDS"
            if self.required_return_basis == RETURN_BASIS_PRICE_ONLY
            else "INCLUDES_SUPPLIED_DIVIDEND",
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
        }


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
    dividend_per_share: Optional[float] = None,
    currency: Optional[str] = None,
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

    return_basis = (
        RETURN_BASIS_TOTAL if _safe_float(dividend_per_share) is not None else RETURN_BASIS_PRICE_ONLY
    )
    if return_basis == RETURN_BASIS_PRICE_ONLY:
        flags.append("REQUIRED_RETURN_EXCLUDES_DIVIDENDS")

    target_price = required_exit_price(price, required_return, horizon_years)
    terminal_eps = implied_eps_at_multiple(target_price, exit_multiple.value)

    window = growth_window_years(start_anchor, horizon_years)
    cagr = required_eps_cagr(start_anchor, terminal_eps, window)

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
    )


def _consensus_is_comparable(
    horizon_years: float,
    consensus_basis: str,
    consensus_months_covered: Optional[float],
) -> Tuple[bool, str]:
    """
    Whether a consensus EPS speaks about the same 12 months as the terminal EPS.

    The terminal EPS covers the year ending at the horizon. A next-twelve-months
    consensus taken at the valuation date covers the first year of the horizon,
    so the two coincide only when the horizon is one year. Any other comparison
    would be a difference between two different years presented as a gap.
    """
    if not consensus_basis:
        return False, (
            "The consensus figure declares no basis, so it cannot be shown to cover "
            "the same period as the terminal EPS."
        )
    if consensus_basis == ANCHOR_FORWARD:
        years = _safe_float(horizon_years) or 0.0
        if abs(years - 1.0) > 1e-9:
            return False, (
                f"The consensus is a next-twelve-months figure taken at the valuation date, "
                f"which covers year 1, while the terminal EPS covers the year ending at "
                f"{years:g} years. These are different periods and are not compared here."
            )
        return True, ""
    if consensus_basis == ANCHOR_TTM:
        years = _safe_float(horizon_years) or 0.0
        if abs(years - 1.0) > 1e-9:
            return False, (
                f"The consensus is a trailing figure covering the year before the valuation "
                f"date, while the terminal EPS covers the year ending at {years:g} years. "
                "These are different periods and are not compared here."
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
    dividend_per_share: Optional[float] = None,
    currency: Optional[str] = None,
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
                        dividend_per_share=dividend_per_share,
                        currency=currency,
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
    band_observations = band.get("observations")

    if band_median is not None and band_median > 0:
        usable = False
        if band_observations is None:
            usable = True
            basis = "historical band median (observation count not declared)"
        else:
            count = int(band_observations)
            usable = count >= min_observations
            basis = f"historical band median from {count} observations"
        if usable:
            multiples.append(
                ReferenceMultiple(
                    value=band_median,
                    source="historical_pe_band_median",
                    sample_size=band_observations,
                    period_label=str(band.get("period_label") or ""),
                )
            )
        else:
            unavailable.append(
                {
                    "item": "exit_multiple.historical",
                    "reason": (
                        f"The historical P/E band holds {band_observations} observations, "
                        f"below the {min_observations} required to read a percentile from it. "
                        f"It is reported as a median of {band_median:g} but is not used as a "
                        "reference multiple."
                    ),
                    "reason_kind": "INSUFFICIENT_OBSERVATIONS",
                    "blocks": ["exit_multiple"],
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
                    )
                ]
            else:
                multiples = [ReferenceMultiple(value=multiple_value, source="user_supplied")]
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

    Only a band with enough observations to read a percentile from is used.
    When the sample is thin the band's own median is still reported as a
    descriptive figure, but it is not turned into a scenario, because calling
    an 8-sample median a historical distribution would present an under-sampled
    statistic as though it were an established fact about the past.

    The returned multiples are labelled with the percentile they came from and
    carry the sample size, so a reader can see how thin the history is.
    """
    multiples: List[ReferenceMultiple] = []
    unavailable: List[Dict[str, Any]] = []
    band = band or {}

    band_median = _safe_float(band.get("median"))
    if band_median is None:
        return multiples, unavailable

    declared = band.get("observations")
    if declared is None:
        # No declared count: treated as usable, matching the existing engine's
        # rule that keeps explicit user input and fixtures working.
        usable = True
        count_text = "not declared"
    else:
        count = int(declared)
        usable = count >= min_observations
        count_text = str(count)

    if not usable:
        unavailable.append(
            {
                "item": "exit_multiple.band_scenarios",
                "reason": (
                    "The historical P/E band holds %s observations, below the %d required "
                    "to read a percentile from it. The band's median of %.4g is reported as "
                    "a descriptive statistic only and is not used as a scenario exit "
                    "multiple." % (count_text, min_observations, band_median)
                ),
                "reason_kind": "INSUFFICIENT_OBSERVATIONS",
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
                    "band percentiles from %s observations" % count_text
                ),
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

    # A combined earnings-and-revenue answer is only meaningful when both
    # multiples and the share count are all present and consistent.
    implied_shares = None
    if cap is not None and usable_price is not None:
        implied_shares = cap / usable_price
    combined = implied_net_margin_at_multiples(
        implied_eps_at_multiple(usable_price, pe_multiple.value)
        if usable_price is not None and pe_multiple is not None
        else None,
        required_revenue_at_multiple(cap, revenue_multiple.value)
        if cap is not None and revenue_multiple is not None
        else None,
        implied_shares,
    )
    methods["implied_net_margin"] = {
        "implied": combined,
        "unit": "ratio",
        "reference_multiple": {
            "pe": pe_multiple.contract_view() if pe_multiple else None,
            "revenue": revenue_multiple.contract_view() if revenue_multiple else None,
        },
        "observed": None,
        "observed_label": None,
        "gap_implied_vs_observed": None,
        "status": "COMPUTED" if combined is not None else "NOT_COMPUTED",
        "notes": [
            "Requires a P/E multiple, a P/S multiple and an implied share count at once.",
            "The share count is derived from market cap divided by price rather than taken "
            "from the filings, so this margin describes the vendor's share basis.",
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
    valuation_multiples: Optional[Dict[str, ReferenceMultiple]] = None,
    shares: Optional[float] = None,
    risk_free_rates: Sequence[RiskFreeRate] = (),
    cost_of_equity_inputs: Optional[Dict[str, Any]] = None,
    investor_required_returns: Optional[Dict[str, Any]] = None,
    dcf_inputs: Optional[Dict[str, Any]] = None,
    unavailable: Optional[Iterable[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Assemble the whole V1 package: the matrix, the cash flow cross-checks, the
    separated rate families, and an explicit statement of what is missing.
    """
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
        dividend_per_share=dividend_per_share,
        currency=currency,
    )

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
        multiples=valuation_multiples or {},
    )
    unavailable: List[Dict[str, Any]] = list(unavailable or [])

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
        "start_anchor": start_anchor.contract_view(),
        "current_pe": current_pe,
        "consensus_eps": consensus_eps,
        "consensus_basis": consensus_basis,
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
        "unavailable": list(unavailable or []),
        "reading_notes": [
            "A required return is a price return unless a dividend was supplied as an input.",
            "A required terminal EPS is the EPS that the chosen exit multiple corresponds to, "
            "not a forecast and not a market expectation.",
            "A CAGR is reported only when the gap between the two EPS anchors is long enough "
            "to annualise; otherwise the raw EPS change is reported without a rate.",
            "Risk-free rates, modelled cost of equity and investor target returns are three "
            "separate kinds of number and are never merged into one figure.",
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
