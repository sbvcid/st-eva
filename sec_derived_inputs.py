"""
The SEC-derived figures the engine may use, and the ones it may not.

The engine's arithmetic needs a figure on a stated basis: a trailing-twelve-month
earnings figure for a P/E, a trailing-twelve-month cash flow for a P/FCF. A
figure that is a fiscal year's, or a single quarter's, is a different quantity
and cannot be put in its place -- a P/FCF computed from one quarter's free cash
flow is not a P/FCF.

So this module answers one question per figure: is there a *qualified* figure
on the basis the multiple needs, knowable at the analysis cut, and if so what
is it and where did it come from? A figure that does not qualify is not
returned at all, and the engine keeps whatever it had.

The two sources are the committed production datasets, not the archive, so the
answer does not depend on whether a run was archived.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# The basis a figure is on. A multiple's arithmetic is only meaningful against
# a figure on the same basis.
BASIS_TTM = "TTM"
BASIS_ANNUAL = "ANNUAL"
BASIS_QUARTERLY = "QUARTERLY"

# Where a figure came from.
SOURCE_SEC_DERIVED = "SEC_DERIVED"
SOURCE_VENDOR = "VENDOR_REPORTED"
SOURCE_UNAVAILABLE = "UNAVAILABLE"


def _records_at_or_before(
    payload: Optional[Dict[str, Any]],
    as_of: str,
) -> List[Dict[str, Any]]:
    """The payload's observation records, newest first, that the cut can see."""
    if not isinstance(payload, dict):
        return []
    records = [
        record
        for record in (payload.get("observations") or [])
        if isinstance(record, dict)
        and record.get("evaluation_date")
        and str(record["evaluation_date"]) <= str(as_of)
    ]
    records.sort(key=lambda record: str(record["evaluation_date"]), reverse=True)
    return records


def qualified_ttm_eps(
    production_pe: Optional[Dict[str, Any]],
    as_of: str,
) -> Optional[Dict[str, Any]]:
    """
    The trailing-twelve-month diluted EPS, if a qualified one is knowable.

    Qualified means: the reconstruction found a window of four directly stated
    quarterly figures, with no quarter missing, every constituent knowable at
    the cut, and the window itself knowable at the cut. The fourth quarter --
    the one a fiscal year does not report on its own -- has to come from the
    furnished earnings release, and the constituent list says which.

    Returns None when none qualifies. The caller then keeps the vendor's
    trailing figure and says so.
    """
    for record in _records_at_or_before(production_pe, as_of):
        if record.get("metric_id") != "TTM_GAAP_DILUTED_PE":
            continue
        if record.get("status") != "AVAILABLE":
            continue
        state = record.get("eps_state") or {}
        components = [c for c in (state.get("components") or []) if isinstance(c, dict)]
        if len(components) != 4:
            continue
        if state.get("missing_quarters"):
            continue
        usable_dates = [str(c.get("usable_date") or "") for c in components]
        if not all(usable_dates) or max(usable_dates) > str(as_of):
            continue
        denominator = state.get("quarter_denominator")
        if denominator is None:
            continue
        derivation = state.get("quarter_denominator_derivation") or {}
        # Only a sum of directly stated quarterly figures qualifies. A trailing
        # figure rolled forward from a fiscal year and two cumulative periods
        # is a subtraction, and for a per-share amount the subtrahend's
        # denominator moves, so the result is an approximation rather than a
        # filed figure. The SEC provider's own trailing earnings view says so
        # on its face -- it records the window as not additive -- and such a
        # figure is not a filed fact and is not labelled as one.
        method = str(derivation.get("method") or "")
        if "SUM" not in method.upper():
            continue
        furnished = [
            c for c in components if c.get("evidence_class") == "furnished"
        ]
        # The fourth quarter is the one a fiscal year does not report on its
        # own. It has to come from a furnished earnings release, or the window
        # is not four directly stated quarterly figures.
        if not furnished:
            continue
        return {
            "value": float(denominator),
            "basis": BASIS_TTM,
            "source": SOURCE_SEC_DERIVED,
            "currency": components[0].get("currency"),
            "window_anchor": state.get("window_anchor"),
            "usable_from": max(usable_dates),
            "derivation": derivation.get("method"),
            "derived_not_issuer_declared": bool(
                derivation.get("derived_not_issuer_declared")
            ),
            "quarter_count": len(components),
            "q4_evidence": [
                {
                    "accession": c.get("accession"),
                    "form": c.get("form"),
                    "period_end": c.get("period_end"),
                    "value": c.get("value"),
                    "acceptance_datetime": c.get("acceptance_datetime"),
                    "usable_date": c.get("usable_date"),
                    "source_url": c.get("source_url"),
                    "stated_directly": c.get("stated_directly"),
                }
                for c in furnished
            ],
            "components": [
                {
                    "value": c.get("value"),
                    "form": c.get("form"),
                    "accession": c.get("accession"),
                    "period_end": c.get("period_end"),
                    "usable_date": c.get("usable_date"),
                    "evidence_class": c.get("evidence_class"),
                    "metric": c.get("metric"),
                }
                for c in components
            ],
        }
    return None


def qualified_ttm_fcf(
    production_pfcf: Optional[Dict[str, Any]],
    as_of: str,
) -> Optional[Dict[str, Any]]:
    """
    The trailing-twelve-month free cash flow, if a qualified one is knowable.

    Qualified means: the reconstruction found four consecutive quarters, every
    quarter knowable at the cut, and the window knowable at the cut. The four
    quarters and their own derivations are reported, so the figure can be
    taken apart rather than taken on trust.
    """
    for record in _records_at_or_before(production_pfcf, as_of):
        if record.get("status") != "AVAILABLE":
            continue
        value = record.get("ttm_free_cash_flow")
        if value is None:
            continue
        window = record.get("ttm_window") or {}
        quarters = [q for q in (window.get("quarters") or []) if isinstance(q, dict)]
        if len(quarters) != 4:
            continue
        # Each quarter has to say how it was arrived at. A quarter that is the
        # difference of two cumulative filings is a legitimate quarter, but it
        # is a derived one and has to declare itself as such.
        if not all(q.get("formula") for q in quarters):
            continue
        knowable = [str(q.get("knowable_from") or "") for q in quarters]
        if not all(knowable) or max(knowable) > str(as_of):
            continue
        return {
            "value": float(value),
            "basis": BASIS_TTM,
            "source": SOURCE_SEC_DERIVED,
            "currency": record.get("ttm_free_cash_flow_currency"),
            "window_anchor": window.get("anchor"),
            "usable_from": max(knowable),
            "derivation": quarters[0].get("formula"),
            "quarter_count": len(quarters),
            "components": [
                {
                    "value": q.get("free_cash_flow"),
                    "metric": "GAAP_FREE_CASH_FLOW",
                    "period_end": q.get("period_end"),
                    "fiscal_year": q.get("fiscal_year"),
                    "fiscal_quarter": q.get("fiscal_quarter"),
                    "operating_cash_flow": q.get("operating_cash_flow"),
                    "capital_expenditure": q.get("capital_expenditure"),
                    "free_cash_flow": q.get("free_cash_flow"),
                    "currency": q.get("currency"),
                    "formula": q.get("formula"),
                    "knowable_from": q.get("knowable_from"),
                    "identity_source": q.get("identity_source"),
                }
                for q in quarters
            ],
        }
    return None
