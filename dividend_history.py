"""
Dividend evidence and total-return calculations.

This module provides source-backed dividend observations, trailing and indicated
yield metrics, and dividend-inclusive return calculations.

Key principles enforced:
1. Determinism and Evidence Basis:
   - Dividends are observed facts with explicit ex-dates, pay dates, amounts,
     and split adjustments.
   - Future dividends and future dividend growth are NEVER assumed or predicted.
   - Indicated annual dividend is strictly an annualized run-rate of the latest
     declared regular dividend, explicitly distinguished from historical TTM dividends
     and never presented as a guaranteed future distribution.
2. Price-Return vs. Total-Return Separation:
   - Price return measures capital appreciation alone: (P_end / P_start)^(1/t) - 1.
   - Total return incorporates cash distributions under explicit, named conventions:
     * Cash Retained (Simple Cash Retention): dividends are held in cash without reinvestment.
     * Reinvested (DRIP): dividends are reinvested into additional shares on ex-dividend dates.
   - A dividend yield is never silently added to a price-return hurdle.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from data_contract import (
    currencies_match,
    is_number,
    safe_float,
    utc_now,
    Observation,
    METRIC_DIVIDENDS_PER_SHARE,
)

DIVIDEND_FORMULA_VERSION = "dividend-analysis/1.0"


@dataclass(frozen=True)
class DividendPaymentRecord:
    """One declared or paid dividend."""

    ex_date: str
    amount: float
    unadjusted_amount: Optional[float] = None
    currency: str = "USD"
    source: str = ""
    period: Optional[str] = None

    def contract_view(self) -> Dict[str, Any]:
        return {
            "ex_date": self.ex_date,
            "amount": self.amount,
            "unadjusted_amount": self.unadjusted_amount,
            "currency": self.currency,
            "source": self.source,
            "period": self.period,
        }


def extract_dividends_from_chart_events(
    chart_payload: Dict[str, Any],
    currency: str = "USD",
    source_label: str = "Market chart events",
) -> List[DividendPaymentRecord]:
    """
    Extract dividend payment records from Yahoo chart result payload.

    Preserves split-adjusted amounts and as-traded unadjusted amounts.
    """
    if not isinstance(chart_payload, dict):
        return []
    if "chart" in chart_payload:
        result = (chart_payload.get("chart", {}).get("result") or [{}])[0]
        events = result.get("events") or {}
    elif "events" in chart_payload:
        events = chart_payload.get("events") or {}
    else:
        events = chart_payload

    divs_dict = events.get("dividends") or {}
    splits_dict = events.get("splits") or {}

    # Identify any splits
    splits: List[Tuple[str, float]] = []
    for split_key, split_entry in splits_dict.items():
        try:
            ts = int(split_entry.get("date") or split_key)
            ex_date = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).date().isoformat()
            num = float(split_entry.get("numerator") or 1.0)
            den = float(split_entry.get("denominator") or 1.0)
            ratio = num / den
            splits.append((ex_date, ratio))
        except (ValueError, TypeError):
            continue
    splits.sort(key=lambda s: s[0])

    records: List[DividendPaymentRecord] = []
    for date_key, div_entry in divs_dict.items():
        raw_amt = safe_float(div_entry.get("amount"))
        if raw_amt is None or raw_amt <= 0:
            continue
        try:
            ts = int(div_entry.get("date") or date_key)
            ex_date = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).date().isoformat()
        except (ValueError, TypeError):
            continue

        # Vendor chart events report split-adjusted dividend amounts.
        # If a split occurred AFTER the dividend ex-date, reconstruct as-traded pre-split amount.
        unadjusted_amt = raw_amt
        for split_date, ratio in splits:
            if split_date > ex_date and ratio > 0:
                unadjusted_amt = unadjusted_amt * ratio

        records.append(
            DividendPaymentRecord(
                ex_date=ex_date,
                amount=round(raw_amt, 4),
                unadjusted_amount=round(unadjusted_amt, 4) if unadjusted_amt != raw_amt else raw_amt,
                currency=currency,
                source=source_label,
            )
        )

    records.sort(key=lambda r: r.ex_date)
    return records


def extract_dividends_from_sec_observations(
    observations: Sequence[Any],
) -> List[Dict[str, Any]]:
    """Extract discrete and TTM dividend observations acquired from SEC filings."""
    sec_divs: List[Dict[str, Any]] = []
    for obs in observations:
        metric = getattr(obs, "metric", None)
        if metric == METRIC_DIVIDENDS_PER_SHARE or metric == "dividends_per_share":
            raw = getattr(obs, "raw", {}) or {}
            sec_divs.append({
                "observation_id": getattr(obs, "observation_id", ""),
                "value": getattr(obs, "value", None),
                "unit": getattr(obs, "unit", ""),
                "currency": getattr(obs, "currency", "USD"),
                "period_start": getattr(obs, "period_start", None),
                "period_end": getattr(obs, "period_end", None),
                "as_of": getattr(obs, "as_of", None),
                "available_at": getattr(obs, "available_at", None),
                "form": raw.get("form") or getattr(obs, "form", ""),
                "accession": raw.get("accession") or raw.get("accession_number") or getattr(obs, "accession", ""),
                "accession_number": raw.get("accession_number") or raw.get("accession") or getattr(obs, "accession", ""),
                "fiscal_year": raw.get("fy"),
                "fiscal_period": raw.get("fp"),
                "derivation": getattr(obs, "derivation", ""),
            })
    sec_divs.sort(key=lambda d: (d.get("period_end") or "", d.get("observation_id") or ""))
    return sec_divs


def _parse_iso_date(d_val: Any) -> datetime.date:
    if isinstance(d_val, datetime.date):
        return d_val
    if isinstance(d_val, (int, float)):
        return datetime.datetime.fromtimestamp(int(d_val), datetime.timezone.utc).date()
    s = str(d_val).strip()
    if s.isdigit():
        return datetime.datetime.fromtimestamp(int(s), datetime.timezone.utc).date()
    return datetime.date.fromisoformat(s[:10])


def calculate_dividend_summary(
    payments: Sequence[DividendPaymentRecord],
    as_of: str,
    price: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Compute verified TTM, indicated, and YoY dividend metrics as of an evaluation date.
    """
    as_of_date = _parse_iso_date(as_of)
    one_year_prior = as_of_date - datetime.timedelta(days=365)
    two_years_prior = as_of_date - datetime.timedelta(days=730)

    # Filter to dividends knowable on or before as_of
    eligible = [p for p in payments if _parse_iso_date(p.ex_date) <= as_of_date]

    # Trailing 12 months payments: (one_year_prior, as_of_date]
    ttm_payments = [
        p for p in eligible
        if one_year_prior < _parse_iso_date(p.ex_date) <= as_of_date
    ]
    ttm_dividend = sum(p.amount for p in ttm_payments) if ttm_payments else 0.0

    # Prior 12 months payments: (two_years_prior, one_year_prior]
    prior_ttm_payments = [
        p for p in eligible
        if two_years_prior < _parse_iso_date(p.ex_date) <= one_year_prior
    ]
    prior_ttm_dividend = sum(p.amount for p in prior_ttm_payments) if prior_ttm_payments else 0.0

    # YoY growth between the two 12-month periods
    yoy_growth: Optional[float] = None
    if prior_ttm_dividend > 0 and ttm_dividend > 0:
        yoy_growth = (ttm_dividend - prior_ttm_dividend) / prior_ttm_dividend

    # Latest payment and Indicated Annual Dividend
    latest_payment = eligible[-1] if eligible else None
    indicated_rate: Optional[float] = None
    latest_yoy_growth: Optional[float] = None
    if latest_payment is not None:
        # Standard convention: quarterly regular dividend annualized x 4
        indicated_rate = latest_payment.amount * 4.0

        # Find payment ~1 year earlier for latest payment YoY comparison
        target_prior_date = _parse_iso_date(latest_payment.ex_date) - datetime.timedelta(days=365)
        closest_prior = None
        min_diff = 45  # within 45 days
        for p in eligible:
            diff = abs((_parse_iso_date(p.ex_date) - target_prior_date).days)
            if diff < min_diff:
                min_diff = diff
                closest_prior = p
        if closest_prior is not None and closest_prior.amount > 0:
            latest_yoy_growth = (latest_payment.amount - closest_prior.amount) / closest_prior.amount

    # Yields
    ttm_yield: Optional[float] = None
    indicated_yield: Optional[float] = None
    if price is not None and price > 0:
        if ttm_dividend > 0:
            ttm_yield = ttm_dividend / price
        if indicated_rate is not None and indicated_rate > 0:
            indicated_yield = indicated_rate / price

    return {
        "as_of": as_of,
        "eligible_payment_count": len(eligible),
        "ttm_payments_count": len(ttm_payments),
        "ttm_payments": [p.contract_view() for p in ttm_payments],
        "trailing_twelve_month_dividends": round(ttm_dividend, 4) if ttm_payments else None,
        "trailing_dividend_yield": ttm_yield,
        "trailing_twelve_month_yield": ttm_yield,
        "prior_trailing_twelve_month_dividends": round(prior_ttm_dividend, 4) if prior_ttm_payments else None,
        "yoy_ttm_dividend_growth": yoy_growth,
        "dividend_growth_yoy": yoy_growth,
        "latest_payment": latest_payment.contract_view() if latest_payment else None,
        "latest_payment_amount": latest_payment.amount if latest_payment else None,
        "latest_payment_date": latest_payment.ex_date if latest_payment else None,
        "indicated_annual_dividend": round(indicated_rate, 4) if indicated_rate is not None else None,
        "indicated_annual_dividend_rate": round(indicated_rate, 4) if indicated_rate is not None else None,
        "indicated_dividend_yield": indicated_yield,
        "indicated_annual_dividend_yield": indicated_yield,
        "latest_dividend_growth_yoy": latest_yoy_growth,
        "trailing_dividends_source": (
            latest_payment.source if latest_payment else "Market chart events / SEC filings"
        ),
        "currency": latest_payment.currency if latest_payment else "USD",
    }


def calculate_historical_returns(
    price_series: Sequence[Tuple[str, float]],
    payments: Sequence[DividendPaymentRecord],
    as_of: str,
    windows_years: Sequence[float] = (1.0, 3.0, 5.0),
) -> List[Dict[str, Any]]:
    """
    Calculate historical price return vs total return over specified horizons ending at as_of.

    Conventions:
    1. Price Return: (P_end / P_start)^(1/years) - 1
    2. Total Return (Cash Retained): ((P_end + sum(D)) / P_start)^(1/years) - 1
    3. Total Return (Reinvested DRIP): compound growth factor using ex-date prices
    """
    if not price_series:
        return []

    # Map dates to prices
    prices_by_date = {_parse_iso_date(d).isoformat(): p for d, p in price_series}
    sorted_dates = sorted(prices_by_date.keys())
    if not sorted_dates:
        return []

    as_of_date_str = as_of[:10]
    # Ending price: latest price on or before as_of
    end_dates = [d for d in sorted_dates if d <= as_of_date_str]
    if not end_dates:
        return []
    end_date = end_dates[-1]
    p_end = prices_by_date[end_date]

    results: List[Dict[str, Any]] = []

    for years in windows_years:
        target_days = int(years * 365.25)
        target_start = (_parse_iso_date(end_date) - datetime.timedelta(days=target_days)).isoformat()

        # Find closest price on or after target_start (within 10 days)
        eligible_starts = [d for d in sorted_dates if d >= target_start and d < end_date]
        if not eligible_starts:
            continue
        start_date = eligible_starts[0]
        actual_days = (_parse_iso_date(end_date) - _parse_iso_date(start_date)).days
        actual_years = actual_days / 365.25
        if actual_years < 0.5:
            continue

        p_start = prices_by_date[start_date]
        if p_start <= 0 or p_end <= 0:
            continue

        # 1. Price Return
        price_cagr = (p_end / p_start) ** (1.0 / actual_years) - 1.0

        # Dividends in window: start_date < ex_date <= end_date
        window_divs = [
            p for p in payments
            if start_date < p.ex_date <= end_date
        ]
        sum_divs = sum(p.amount for p in window_divs)

        # 2. Total Return with Cash Retention
        wealth_cash = p_end + sum_divs
        tr_cash_cagr = (wealth_cash / p_start) ** (1.0 / actual_years) - 1.0

        # 3. Total Return with Dividend Reinvestment (DRIP)
        shares = 1.0
        for div in window_divs:
            # Price on ex-date or closest prior trading date
            ex_date_candidates = [d for d in sorted_dates if d <= div.ex_date]
            if ex_date_candidates:
                p_ex = prices_by_date[ex_date_candidates[-1]]
                if p_ex > 0:
                    shares *= (1.0 + div.amount / p_ex)

        wealth_reinvest = shares * p_end
        tr_reinvest_cagr = (wealth_reinvest / p_start) ** (1.0 / actual_years) - 1.0

        results.append({
            "horizon_label": f"{int(years)}y" if years.is_integer() else f"{years:g}y",
            "horizon_years": years,
            "actual_years": round(actual_years, 2),
            "start_date": start_date,
            "end_date": end_date,
            "start_price": round(p_start, 4),
            "end_price": round(p_end, 4),
            "dividends_received_count": len(window_divs),
            "total_cash_dividends": round(sum_divs, 4),
            "price_return_cagr": price_cagr,
            "total_return_cash_cagr": tr_cash_cagr,
            "total_return_reinvested_cagr": tr_reinvest_cagr,
            "dividend_contribution_cash_cagr": tr_cash_cagr - price_cagr,
            "dividend_contribution_reinvested_cagr": tr_reinvest_cagr - price_cagr,
        })

    return results


def build_dividend_package(
    ticker: str,
    *,
    price: Optional[float] = None,
    price_date: Optional[str] = None,
    currency: Optional[str] = None,
    chart_payload: Optional[Dict[str, Any]] = None,
    chart_events: Optional[Dict[str, Any]] = None,
    price_series: Optional[Sequence[Tuple[str, float]]] = None,
    sec_observations: Optional[Sequence[Any]] = None,
    as_of: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build the complete dividend package for the research dossier.
    """
    effective_as_of = as_of or price_date or utc_now()[:10]
    effective_currency = currency or "USD"

    payload = chart_payload if chart_payload is not None else chart_events
    if not payload:
        daily_json = Path(f"data/historical_pe/{ticker}/daily_prices.json")
        if daily_json.exists():
            try:
                with open(daily_json, "r", encoding="utf-8") as f:
                    payload = json.load(f)
            except Exception:
                payload = None

    payments: List[DividendPaymentRecord] = []
    if payload:
        payments = extract_dividends_from_chart_events(
            payload,
            currency=effective_currency,
        )

    # Auto-extract price series if not supplied directly
    if not price_series:
        chart_obj = payload if (payload and isinstance(payload, dict) and "chart" in payload) else None
        if not chart_obj:
            daily_json = Path(f"data/historical_pe/{ticker}/daily_prices.json")
            if daily_json.exists():
                try:
                    with open(daily_json, "r", encoding="utf-8") as f:
                        chart_obj = json.load(f)
                except Exception:
                    chart_obj = None
        if chart_obj and isinstance(chart_obj, dict) and "chart" in chart_obj:
            try:
                res = (chart_obj.get("chart", {}).get("result") or [{}])[0]
                timestamps = res.get("timestamp") or []
                closes = (res.get("indicators", {}).get("quote") or [{}])[0].get("close") or []
                series = []
                for ts, close in zip(timestamps, closes):
                    if ts and close is not None:
                        d = datetime.datetime.fromtimestamp(int(ts), datetime.timezone.utc).date().isoformat()
                        series.append((d, float(close)))
                if series:
                    price_series = series
            except Exception:
                pass

    sec_filing_evidence = []
    if sec_observations:
        sec_filing_evidence = extract_dividends_from_sec_observations(sec_observations)

    summary = calculate_dividend_summary(
        payments,
        as_of=effective_as_of,
        price=price,
    )

    historical_returns = []
    if price_series and payments:
        historical_returns = calculate_historical_returns(
            price_series,
            payments,
            as_of=effective_as_of,
        )

    has_dividends = len(payments) > 0 or len(sec_filing_evidence) > 0
    status = "COMPUTED" if has_dividends else "NO_DIVIDENDS_ACQUIRED"

    unavailable: List[Dict[str, Any]] = []
    if not payments:
        unavailable.append({
            "item": "dividend_payments",
            "reason": f"No market dividend event history was acquired for {ticker}.",
            "reason_kind": "MISSING_DIVIDEND_DATA",
            "blocks": ["dividends"],
        })
    if not sec_filing_evidence:
        unavailable.append({
            "item": "sec_declared_dividends",
            "reason": f"No SEC regulatory filing observations of declared dividends were acquired for {ticker}.",
            "reason_kind": "MISSING_SEC_DIVIDEND_DATA",
            "blocks": ["sec_filing_evidence"],
        })

    notes = [
        "Dividends are reported as verifiable point-in-time facts based on declared ex-dividend dates.",
        "Indicated annual dividend is strictly an annualized run-rate (latest quarterly payment x 4), "
        "distinguished from historical trailing twelve-month dividends and never guaranteed.",
        "Total returns are computed under two explicit conventions: (1) simple cash retention without reinvestment, "
        "and (2) full dividend reinvestment (DRIP) on ex-dates.",
    ]

    return {
        "formula_version": DIVIDEND_FORMULA_VERSION,
        "status": status,
        "as_of": effective_as_of,
        "ticker": ticker,
        "currency": effective_currency,
        "price": price,
        "price_date": price_date,
        "summary": summary,
        "recent_payments": [p.contract_view() for p in payments[-12:]],
        "sec_filing_evidence": sec_filing_evidence,
        "historical_returns": historical_returns,
        "unavailable": unavailable,
        "notes": notes,
    }
