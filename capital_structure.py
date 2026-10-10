"""
Capital structure: what the filings state, and what can be rebuilt from them.

Two numbers describe a company's size: what the market data vendor reports for
market capitalization and enterprise value, and what those quantities work out
to from a dated share count and dated balance-sheet components. They are
different claims and this module keeps them apart rather than preferring one.

Why they can differ, and why the difference is worth showing:

- The vendor's share count and its market capitalization may not describe the
  same date. Multiplying a price on one day by a share count from another is a
  reconstruction with a stated mismatch, not a correction.
- The provider's cash may include short-term investments while a filing's cash
  concept may not. The two are different quantities, and a bridge built on one
  of them is a different bridge.
- Long-term debt alone is not the whole of debt. A bridge that subtracts cash
  and adds only long-term debt omits short-term borrowings and other claims, so
  this module never presents the result as *the* enterprise value.

Every reconstructed figure therefore carries the definition it was built on and
a completeness statement. A partial bridge is reported as partial and is never
labelled as an enterprise value without the qualifier.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from data_contract import currencies_match

from financial_history import (
    HISTORY_FORMULA_VERSION,
    HistoryPoint,
    build_series,
)


CAPITAL_FORMULA_VERSION = "capital-structure/2.0"

# The components a complete enterprise-value bridge would need. Naming them
# lets the module say which are present and which are missing rather than
# presenting a partial sum as if it were the whole.
EV_BRIDGE_COMPONENTS = (
    "total_debt",
    "long_term_debt",
    "commercial_paper",
    "short_term_borrowings",
    "cash",
    "marketable_securities_current",
    "non_controlling_interests",
    "preferred_equity",
)


def _latest(series_points: Sequence[HistoryPoint]) -> Optional[HistoryPoint]:
    if not series_points:
        return None
    return series_points[-1]


def _format_amount(val: Optional[float]) -> str:
    if val is None:
        return "N/A"
    return f"{val:,.2f}"


def _point_view(
    point: Optional[HistoryPoint],
    cross_verdict: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if point is None:
        return {"present": False}
    verdict = cross_verdict or {}
    status = verdict.get("status") or getattr(point, "status", "VALID")
    caveats = list(verdict.get("reasons") or getattr(point, "status_reasons", ()) or [])
    note = verdict.get("explanation") or ""
    return {
        "present": True,
        "value": point.value,
        "unit": point.unit,
        "currency": point.currency,
        "period_type": "INSTANT",
        "effective_date": point.period_end,
        "provider": point.provider,
        "source_type": point.source_type,
        "available_at": point.available_at,
        "available_at_basis": point.available_at_basis,
        "definition": point.definition,
        "derivation": point.derivation,
        "form": point.form,
        "accession": point.accession,
        "fiscal_year": getattr(point, "fiscal_year", None),
        "fiscal_period": getattr(point, "fiscal_period", None),
        "validation_status": status,
        "caveats": caveats,
        "comparability_caveat": note,
    }


def build_capital_structure(
    observations: Sequence[Any],
    *,
    price: Optional[float] = None,
    price_date: Optional[str] = None,
    currency: Optional[str] = None,
    observed_market_cap: Optional[float] = None,
    observed_enterprise_value: Optional[float] = None,
    observed_ebitda: Optional[float] = None,
    cross_source: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Present the acquired balance-sheet evidence alongside what can be rebuilt.

    Nothing here overwrites a provider observation. The observed and the
    reconstructed values sit in separate blocks, each with its own definition
    and date, and the difference between them is reported with the dates that
    explain it.
    """
    from financial_history import _WINDOW_INSTANT

    series = {
        metric: build_series(observations, metric, _WINDOW_INSTANT)
        for metric in (
            "assets",
            "cash",
            "marketable_securities_current",
            "commercial_paper",
            "long_term_debt",
            "shares_outstanding",
        )
    }
    unavailable: List[Dict[str, Any]] = []

    latest = {metric: _latest(value.points) for metric, value in series.items()}

    for metric, value in sorted(latest.items()):
        if value is None:
            unavailable.append(
                {
                    "item": "capital_structure.%s" % metric,
                    "reason": (
                        "No point-in-time observation of %s was acquired for this run, so "
                        "the field is absent rather than approximated." % metric
                    ),
                    "reason_kind": "MISSING",
                    "blocks": ["capital_structure"],
                }
            )

    shares = latest.get("shares_outstanding")
    cash = latest.get("cash")
    debt = latest.get("long_term_debt")
    cp = latest.get("commercial_paper")
    msc = latest.get("marketable_securities_current")

    currency_issues: List[str] = []
    for name, point in (
        ("cash", cash),
        ("long_term_debt", debt),
        ("commercial_paper", cp),
        ("marketable_securities_current", msc),
    ):
        if point is not None and point.currency and currency and not currencies_match(point.currency, currency):
            currency_issues.append(
                "%s is denominated in %s while the price is %s; no reconstruction combining "
                "them is produced." % (name, point.currency, currency)
            )
    for issue in currency_issues:
        unavailable.append(
            {
                "item": "capital_structure.reconstruction",
                "reason": issue,
                "reason_kind": "CURRENCY_MISMATCH",
                "blocks": ["reconstructed_market_cap", "reconstructed_enterprise_value"],
            }
        )

    # ---- reconstructed market capitalization -------------------------------
    reconstructed_market_cap: Dict[str, Any] = {
        "value": None,
        "status": "NOT_COMPUTED",
        "definition": "price x point-in-time shares outstanding",
        "inputs": {
            "price": price,
            "price_date": price_date,
            "shares_outstanding": shares.value if shares else None,
            "shares_date": shares.period_end if shares else None,
        },
        "date_alignment": "",
        "notes": [],
    }
    if price is not None and shares is not None and not currency_issues:
        reconstructed_market_cap["value"] = price * shares.value
        reconstructed_market_cap["status"] = "COMPUTED"
        reconstructed_market_cap["date_alignment"] = _date_alignment(
            price_date, shares.period_end
        )
        if reconstructed_market_cap["date_alignment"]:
            reconstructed_market_cap["notes"].append(
                "The share count and the price are not from the same date. The product is "
                "a reconstruction under that mismatch, not a corrected market capitalization."
            )
        reconstructed_market_cap["notes"].append(
            "This is a cover-page shares-outstanding count. It is not the weighted-average "
            "diluted share count used in EPS, and the two differ; neither is substituted "
            "for the other."
        )

    # ---- reconstructed enterprise value ------------------------------------
    reconstructed_ev: Dict[str, Any] = {
        "value": None,
        "status": "NOT_COMPUTED",
        "definition": (
            "market capitalization + long-term debt - cash and cash equivalents"
        ),
        "definition_is_complete": False,
        "components_present": [],
        "components_absent": [],
        "inputs": {},
        "notes": [],
    }

    present_components: List[str] = []
    if debt is not None:
        present_components.append("long_term_debt")
    if cp is not None:
        present_components.append("commercial_paper")
    if debt is not None and cp is not None:
        present_components.append("total_debt")
    if cash is not None:
        present_components.append("cash")
    if msc is not None:
        present_components.append("marketable_securities_current")

    absent = [name for name in EV_BRIDGE_COMPONENTS if name not in present_components]
    reconstructed_ev["components_present"] = present_components
    reconstructed_ev["components_absent"] = absent

    total_debt_val: Optional[float] = None
    if debt is not None or cp is not None:
        total_debt_val = (debt.value if debt else 0.0) + (cp.value if cp else 0.0)

    liquid_funds_val: Optional[float] = None
    if cash is not None or msc is not None:
        liquid_funds_val = (cash.value if cash else 0.0) + (msc.value if msc else 0.0)

    net_debt_val: Optional[float] = None
    if total_debt_val is not None and liquid_funds_val is not None:
        net_debt_val = total_debt_val - liquid_funds_val

    reconstructed_ev["inputs"] = {
        "market_cap": reconstructed_market_cap.get("value"),
        "long_term_debt": debt.value if debt else None,
        "long_term_debt_date": debt.period_end if debt else None,
        "commercial_paper": cp.value if cp else None,
        "commercial_paper_date": cp.period_end if cp else None,
        "total_debt": total_debt_val,
        "cash": cash.value if cash else None,
        "cash_date": cash.period_end if cash else None,
        "marketable_securities_current": msc.value if msc else None,
        "marketable_securities_current_date": msc.period_end if msc else None,
        "liquid_funds": liquid_funds_val,
        "net_debt": net_debt_val,
        "observed_ebitda": observed_ebitda,
    }

    if reconstructed_market_cap["value"] is not None and net_debt_val is not None:
        reconstructed_ev["value"] = (
            reconstructed_market_cap["value"] + net_debt_val
        )
        reconstructed_ev["status"] = "PARTIAL"

        if cp is not None and msc is not None:
            reconstructed_ev["definition"] = (
                "market capitalization + total debt (long-term debt + commercial paper) - "
                "liquid funds (cash + current marketable securities)"
            )
        else:
            reconstructed_ev["definition"] = (
                "market capitalization + long-term debt - cash and cash equivalents"
            )

        reconstructed_ev["notes"].append(
            "This is not a complete enterprise value. It omits %s."
            % (", ".join(absent) if absent else "none")
        )
        if cp is not None:
            reconstructed_ev["notes"].append(
                "Commercial paper (%s) is included in total debt (%s) alongside long-term debt (%s); "
                "short-term borrowings are not double-counted."
                % (
                    _format_amount(cp.value),
                    _format_amount(total_debt_val),
                    _format_amount(debt.value if debt else 0.0),
                )
            )
        if msc is not None:
            reconstructed_ev["notes"].append(
                "Current marketable securities (%s) are included in liquid funds (%s) alongside cash (%s)."
                % (
                    _format_amount(msc.value),
                    _format_amount(liquid_funds_val),
                    _format_amount(cash.value if cash else 0.0),
                )
            )
        reconstructed_ev["notes"].append(
            "It also combines a share-count date (%s), a price date (%s) and a balance-sheet date (%s) "
            "that need not coincide."
            % (
                shares.period_end if shares else "-",
                price_date or "-",
                debt.period_end if debt else (cash.period_end if cash else "-"),
            )
        )
        reconstructed_ev["notes"].append(
            "Status remains PARTIAL because reconstructed EV omits non-current marketable securities, "
            "operating leases under ASC 842, and off-balance sheet commitments. An arithmetic match with "
            "provider net debt does not constitute exhaustive accounting coverage."
        )

        if observed_ebitda is not None and observed_ebitda > 0:
            reconstructed_ev["ev_to_ebitda"] = (
                reconstructed_ev["value"] / observed_ebitda
            )
            if observed_enterprise_value is not None:
                reconstructed_ev["observed_ev_to_ebitda"] = (
                    observed_enterprise_value / observed_ebitda
                )
    else:
        missing = [
            name
            for name, present in (
                ("a reconstructed market capitalization", reconstructed_market_cap["value"] is not None),
                ("debt components", total_debt_val is not None),
                ("cash or liquid investment components", liquid_funds_val is not None),
            )
            if not present
        ]
        reconstructed_ev["status"] = "NOT_COMPUTED"
        reconstructed_ev["notes"].append(
            "No enterprise value is reconstructed because %s is missing." % ", ".join(missing)
        )
        unavailable.append(
            {
                "item": "reconstructed_enterprise_value",
                "reason": (
                    "Reconstructing an enterprise value requires a market capitalization, "
                    "a debt figure and a cash figure. Missing: %s." % ", ".join(missing)
                ),
                "reason_kind": "MISSING_INPUT",
                "blocks": ["reconstructed_enterprise_value"],
            }
        )

    comparisons = []
    for label, observed, reconstructed in (
        ("market_cap", observed_market_cap, reconstructed_market_cap),
        ("enterprise_value", observed_enterprise_value, reconstructed_ev),
    ):
        if label == "market_cap":
            obs_def = "provider-published market capitalization"
            recon_dates = {
                "price_date": price_date,
                "shares_date": shares.period_end if shares else None,
            }
            def_diff = (
                "Observed is provider market capitalization; reconstructed is price (%s) x "
                "point-in-time shares outstanding (%s)."
                % (price_date or "-", shares.period_end if shares else "-")
            )
        else:
            obs_def = "provider-published enterprise value"
            recon_dates = {
                "market_cap_date": price_date,
                "long_term_debt_date": debt.period_end if debt else None,
                "commercial_paper_date": cp.period_end if cp else None,
                "cash_date": cash.period_end if cash else None,
                "marketable_securities_current_date": msc.period_end if msc else None,
            }
            if cp and msc:
                bridge_desc = "(market cap + long-term debt + commercial paper - cash - current marketable securities)"
            else:
                bridge_desc = "(market cap + long-term debt - cash)"
            def_diff = (
                "Observed is provider enterprise value; reconstructed is a partial bridge "
                "%s omitting: %s."
                % (bridge_desc, ", ".join(absent) if absent else "none")
            )

        comparisons.append(
            {
                "metric": label,
                "observed": observed,
                "observed_date": price_date,
                "observed_definition": obs_def,
                "reconstructed": reconstructed.get("value"),
                "reconstructed_status": reconstructed.get("status"),
                "reconstructed_dates": recon_dates,
                "definition": reconstructed.get("definition"),
                "definition_difference": def_diff,
                "difference": (
                    reconstructed["value"] - observed
                    if reconstructed.get("value") is not None and observed is not None
                    else None
                ),
                "relative_difference": (
                    (reconstructed["value"] - observed) / observed
                    if reconstructed.get("value") is not None and observed not in (None, 0)
                    else None
                ),
            }
        )

    if observed_ebitda is not None and observed_ebitda > 0:
        obs_ev_ebitda = (
            observed_enterprise_value / observed_ebitda
            if observed_enterprise_value is not None
            else None
        )
        recon_ev_ebitda = (
            reconstructed_ev["value"] / observed_ebitda
            if reconstructed_ev.get("value") is not None
            else None
        )
        diff_ev_ebitda = (
            recon_ev_ebitda - obs_ev_ebitda
            if recon_ev_ebitda is not None and obs_ev_ebitda is not None
            else None
        )
        rel_diff_ev_ebitda = (
            diff_ev_ebitda / obs_ev_ebitda
            if diff_ev_ebitda is not None and obs_ev_ebitda not in (None, 0)
            else None
        )
        comparisons.append(
            {
                "metric": "ev_ebitda",
                "observed": obs_ev_ebitda,
                "observed_date": price_date,
                "observed_definition": "provider enterprise value / observed trailing EBITDA",
                "reconstructed": recon_ev_ebitda,
                "reconstructed_status": reconstructed_ev.get("status"),
                "reconstructed_dates": {
                    "market_cap_date": price_date,
                    "balance_sheet_date": debt.period_end if debt else None,
                    "ebitda_basis": "trailing_twelve_months",
                },
                "definition": "reconstructed enterprise value / observed trailing EBITDA",
                "definition_difference": (
                    "Observed is provider EV / trailing EBITDA; reconstructed is partial reconstructed EV / "
                    "trailing EBITDA. The delta reflects the share count timing mismatch."
                ),
                "difference": diff_ev_ebitda,
                "relative_difference": rel_diff_ev_ebitda,
            }
        )

    has_any = any(len(value.points) > 0 for value in series.values())
    status = "COMPUTED" if has_any else "NOT_ACQUIRED"
    verdicts = (cross_source or {}).get("verdicts") or {}

    return {
        "formula_version": CAPITAL_FORMULA_VERSION,
        "history_formula_version": HISTORY_FORMULA_VERSION,
        "status": status,
        "as_of": price_date,
        "currency": currency,
        "observations": {
            metric: {
                "series": [
                    point.contract_view() for point in value.points
                ],
                "count": len(value.points),
                "latest": _point_view(latest[metric], verdicts.get(metric)),
            }
            for metric, value in sorted(series.items())
        },
        "observed": {
            "market_cap": observed_market_cap,
            "enterprise_value": observed_enterprise_value,
            "ebitda": observed_ebitda,
            "basis": "as published by the market data provider",
        },
        "reconstructed_market_cap": reconstructed_market_cap,
        "reconstructed_enterprise_value": reconstructed_ev,
        "observed_vs_reconstructed": comparisons,
        "share_count_note": (
            "Shares outstanding here is a point-in-time cover-page count. EPS uses a "
            "weighted-average diluted count over a window. The two answer different "
            "questions and neither is substituted for the other."
        ),
        "cross_source_validation": cross_source or {},
        "unavailable": unavailable,
        "notes": [
            "Provider observations and reconstructed values are reported side by side. "
            "Neither overwrites the other and neither is declared correct.",
            "A reconstructed enterprise value built from balance-sheet components is "
            "partial by construction and is labelled as such.",
        ],
    }


def _date_alignment(price_date: Optional[str], share_date: Optional[str]) -> str:
    """A plain statement of how far apart two dates are."""
    if not price_date or not share_date:
        return ""
    if price_date == share_date:
        return "The price and the share count share the date %s." % price_date
    return (
        "The price is dated %s and the share count %s. They are not from the same date."
        % (price_date, share_date)
    )
