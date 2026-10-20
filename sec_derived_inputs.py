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

from data_contract import (
    AvailabilityBasis,
    CurrencyBasis,
    Observation,
    SourceType,
    Unit,
    ValidationStatus,
)

# The basis a figure is on. A multiple's arithmetic is only meaningful against
# a figure on the same basis.
BASIS_TTM = "TTM"
BASIS_ANNUAL = "ANNUAL"
BASIS_QUARTERLY = "QUARTERLY"

# The trailing figures' source windows. A trailing figure the valuation used is
# the sum of the quarters its window holds, so the window travels with the
# context and the document recomputes the sum from it.
TTM_WINDOW_METRICS: Tuple[str, ...] = (
    "ttm_eps_window",
    "ttm_fcf_window",
    "ttm_revenue_window",
    "ttm_ebitda_window",
)

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
                    "period_start": c.get("period_start"),
                    "period_end": c.get("period_end"),
                    "usable_date": c.get("usable_date"),
                    "acceptance_datetime": c.get("acceptance_datetime"),
                    "source_url": c.get("source_url"),
                    "content_sha256": c.get("content_sha256"),
                    "evidence_class": c.get("evidence_class"),
                    "metric": c.get("metric"),
                    "currency": c.get("currency"),
                    "stated_directly": c.get("stated_directly"),
                    "legal_status_note": c.get("legal_status_note"),
                    "sec_item": c.get("sec_item"),
                    "evidence_id": c.get("evidence_id"),
                }
                for c in components
            ],
        }
    return None


# ---------------------------------------------------------------------------
# The income-statement trailing figures
# ---------------------------------------------------------------------------

# The metric each income-statement concept has to be this metric for. The
# registry decides that, and it decides it per issuer: an element that is
# this metric for one filer is not this metric for the market.
_INCOME_CONCEPT_METRICS = {
    "revenue": "revenue",
    "operating_income": "operating_income",
    "depreciation_and_amortization": "depreciation_and_amortization",
}


def _concept_is_exact_for(metric_id: str, concept_tag: str, ticker: str) -> bool:
    """
    Whether the registry maps this concept to this metric for this issuer.

    An EXACT mapping with no scope applies to every filer; a scoped one
    applies to the issuer it names and to no other. A concept that is not
    mapped to the metric at all, or that is mapped to it only partially, is
    not this metric's input, and a figure built on it is not a filed figure
    of that metric.
    """
    from core_registry import MAPPING_EXACT, concept_id_for
    from registry_seed import MAPPINGS, US_GAAP

    wanted = concept_id_for(US_GAAP, concept_tag)
    for mapping in MAPPINGS:
        if mapping.metric_id != metric_id or mapping.concept_id != wanted:
            continue
        if mapping.mapping_type != MAPPING_EXACT:
            continue
        scope = mapping.scope or {}
        scoped_to = scope.get("ticker")
        if scoped_to is not None and scoped_to != ticker:
            continue
        return True
    return False


def _window_quarters(
    record: Dict[str, Any],
    window_key: str,
    as_of: str,
    source_keys: Tuple[str, ...] = ("inputs",),
) -> Optional[List[Dict[str, Any]]]:
    """
    The four quarters of a window, when they all qualify.

    Qualified means: four quarters, no quarter missing, every quarter
    knowable at the cut, one currency across the window, and each quarter
    carrying the sources it was arrived at. A window that fails any of these
    is not used, and the caller keeps whatever it had.
    """
    window = record.get(window_key) or {}
    quarters = [q for q in (window.get("quarters") or []) if isinstance(q, dict)]
    if len(quarters) != 4:
        return None
    knowable = [str(q.get("knowable_from") or "") for q in quarters]
    if not all(knowable) or max(knowable) > str(as_of):
        return None
    currencies = {q.get("currency") for q in quarters}
    if len(currencies) != 1 or not currencies or None in currencies:
        return None
    if not all(q.get("formula") for q in quarters):
        return None
    if not all(all(q.get(key) for key in source_keys) for q in quarters):
        return None
    # The four quarters have to be four consecutive fiscal positions: a window
    # with a hole in it is not a trailing twelve months.
    positions = [
        (int(q["fiscal_year"]), int(q["fiscal_quarter"])) for q in quarters
    ]
    for index in range(1, len(positions)):
        year, number = positions[index - 1]
        expected = (year, number + 1) if number < 4 else (year + 1, 1)
        if positions[index] != expected:
            return None
    return quarters


def qualified_ttm_revenue(
    production_income: Optional[Dict[str, Any]],
    as_of: str,
    ticker: str = "",
) -> Optional[Dict[str, Any]]:
    """
    The trailing-twelve-month revenue, if a qualified one is knowable.

    Qualified means: the reconstruction found four consecutive quarters of
    revenue, every quarter knowable at the cut, one currency across the
    window, and a revenue concept the registry maps to the revenue metric for
    this issuer. A quarter that was arrived at by differencing a fiscal year
    against the nine months states both of its sources and the formula, and
    is marked derived rather than directly stated.

    Returns None when none qualifies. The caller then keeps the vendor's
    trailing figure and says so.
    """
    if not ticker:
        return None
    for record in _records_at_or_before(production_income, as_of):
        if record.get("status") != "AVAILABLE":
            continue
        tags = (production_income or {}).get("concept_tags") or {}
        concept = tags.get("revenue")
        if not concept or not _concept_is_exact_for("revenue", concept, ticker):
            continue
        quarters = _window_quarters(record, "ttm_revenue", as_of)
        if quarters is None:
            continue
        window = record.get("ttm_revenue") or {}
        value = window.get("value")
        if value is None:
            continue
        return {
            "value": float(value),
            "basis": BASIS_TTM,
            "source": SOURCE_SEC_DERIVED,
            "currency": window.get("currency"),
            "concept": concept,
            "window_anchor": window.get("anchor"),
            "usable_from": max(str(q["knowable_from"]) for q in quarters),
            "derivation": window.get("derivation"),
            "quarter_count": len(quarters),
            "components": [_income_component(q) for q in quarters],
        }
    return None


def qualified_ttm_ebitda(
    production_income: Optional[Dict[str, Any]],
    as_of: str,
    ticker: str = "",
) -> Optional[Dict[str, Any]]:
    """
    The trailing-twelve-month EBITDA, if a qualified one is knowable.

    Qualified means: four consecutive quarters, each with a qualified
    operating income and a qualified depreciation and amortization over the
    same period and in the same currency, every quarter knowable at the cut,
    and both concepts mapped to their metrics for this issuer. A quarter that
    has only one of the two is absent, so a window that misses one is not a
    trailing twelve months of EBITDA.

    A fiscal year's EBITDA is not this figure and never stands in for it.
    """
    if not ticker:
        return None
    for record in _records_at_or_before(production_income, as_of):
        if record.get("status") != "AVAILABLE":
            continue
        tags = (production_income or {}).get("concept_tags") or {}
        operating_income_concept = tags.get("operating_income")
        depreciation_concept = tags.get("depreciation_and_amortization")
        if not operating_income_concept or not depreciation_concept:
            continue
        if not _concept_is_exact_for(
            "operating_income", operating_income_concept, ticker
        ):
            continue
        if not _concept_is_exact_for(
            "depreciation_and_amortization", depreciation_concept, ticker
        ):
            continue
        quarters = _window_quarters(
            record,
            "ttm_ebitda",
            as_of,
            source_keys=("operating_income_inputs", "depreciation_inputs"),
        )
        if quarters is None:
            continue
        window = record.get("ttm_ebitda") or {}
        value = window.get("value")
        if value is None:
            continue
        components: List[Dict[str, Any]] = []
        for quarter in quarters:
            component = _income_component(quarter)
            # The quarter's own figure is its EBITDA; the two it was built
            # from travel beside it.
            component["value"] = quarter.get("ebitda")
            component["operating_income"] = quarter.get("operating_income")
            component["depreciation_and_amortization"] = quarter.get(
                "depreciation_and_amortization"
            )
            component["ebitda"] = quarter.get("ebitda")
            component["operating_income_derivation"] = quarter.get(
                "operating_income_derivation"
            )
            component["depreciation_derivation"] = quarter.get(
                "depreciation_derivation"
            )
            component["operating_income_accessions"] = [
                item.get("accession") for item in quarter.get("operating_income_inputs") or []
            ]
            component["depreciation_accessions"] = [
                item.get("accession") for item in quarter.get("depreciation_inputs") or []
            ]
            # The quarter's sources are both of its own: the operating income
            # filings and the depreciation filings that produced it.
            sources = list(quarter.get("operating_income_inputs") or []) + list(
                quarter.get("depreciation_inputs") or []
            )
            seen_accessions: List[str] = []
            for item in sources:
                accession = item.get("accession")
                if accession and accession not in seen_accessions:
                    seen_accessions.append(accession)
            component["accessions"] = seen_accessions
            component["forms"] = [item.get("form") for item in sources]
            component["accession"] = component["accessions"][0] if sources else None
            component["form"] = component["forms"][0] if sources else None
            component["period_start"] = (
                sources[0].get("start") if sources else None
            )
            component["source_urls"] = [item.get("source_url") for item in sources]
            component["acceptance_datetimes"] = [
                item.get("acceptance_datetime") for item in sources
            ]
            component["periods"] = [
                {"start": item.get("start"), "end": item.get("end")} for item in sources
            ]
            component["stated_directly"] = all(
                len(item.get("inputs") or []) == 1 for item in sources
            )
            component["derived_not_issuer_declared"] = any(
                len(item.get("inputs") or []) > 1 for item in sources
            )
            components.append(component)
        return {
            "value": float(value),
            "basis": BASIS_TTM,
            "source": SOURCE_SEC_DERIVED,
            "currency": window.get("currency"),
            "concept": operating_income_concept,
            "depreciation_concept": depreciation_concept,
            "window_anchor": window.get("anchor"),
            "usable_from": max(str(q["knowable_from"]) for q in quarters),
            "derivation": window.get("derivation"),
            "quarter_count": len(quarters),
            "components": components,
        }
    return None


def _income_component(quarter: Dict[str, Any]) -> Dict[str, Any]:
    """One quarter of an income-statement window, with its own sources."""
    inputs = [item for item in (quarter.get("inputs") or []) if isinstance(item, dict)]
    first = inputs[0] if inputs else {}
    return {
        "value": quarter.get("value"),
        "metric": quarter.get("metric") or "GAAP_INCOME_STATEMENT_QUARTER",
        "period_end": quarter.get("period_end"),
        "period_start": first.get("start"),
        "fiscal_year": quarter.get("fiscal_year"),
        "fiscal_quarter": quarter.get("fiscal_quarter"),
        "identity_source": quarter.get("identity_source"),
        "currency": quarter.get("currency"),
        "formula": quarter.get("formula"),
        "knowable_from": quarter.get("knowable_from"),
        "usable_date": quarter.get("knowable_from"),
        "derivation": quarter.get("derivation"),
        "accession": first.get("accession"),
        "form": first.get("form"),
        "accessions": [item.get("accession") for item in inputs],
        "forms": [item.get("form") for item in inputs],
        "source_urls": [item.get("source_url") for item in inputs],
        "acceptance_datetimes": [
            item.get("acceptance_datetime") for item in inputs
        ],
        "periods": [
            {"start": item.get("start"), "end": item.get("end")} for item in inputs
        ],
        "stated_directly": len(inputs) == 1,
        "derived_not_issuer_declared": len(inputs) > 1,
    }


def ttm_value_from_window(
    observation: Optional[Observation],
) -> Optional[float]:
    """
    The trailing figure a window carries, when the window qualifies.

    The window is the authority: it names the four quarters, and the trailing
    figure is their sum. A window that does not qualify -- too few quarters,
    or no furnished fourth quarter -- yields nothing, and the caller keeps the
    figure it had.

    Both the live path and a rebuild read the trailing figure this way, from
    the same window, so they cannot disagree about it.
    """
    if observation is None:
        return None
    value = observation.value
    if not isinstance(value, dict):
        return None
    if not value.get("window_end"):
        return None
    quarters = value.get("quarters") or []
    if len(quarters) != 4:
        return None
    if value.get("requires_furnished_quarter", True) and not any(
        quarter.get("evidence_class") == "furnished" for quarter in quarters
    ):
        return None
    samples = value.get("samples")
    if not isinstance(samples, (list, tuple)) or len(samples) != 4:
        return None
    declared = value.get("declared_value")
    if declared is not None:
        try:
            return float(declared)
        except (TypeError, ValueError):
            pass
    try:
        return sum(float(sample) for sample in samples)
    except (TypeError, ValueError):
        return None


def window_observation(
    ttm_eps: Optional[Dict[str, Any]],
    metric: str = "ttm_eps_window",
    requires_furnished_quarter: bool = True,
    unit: str = Unit.PER_SHARE.value,
) -> Optional[Observation]:
    """
    The trailing figure's window, as one list-valued observation.

    A trailing figure is the sum of the quarters the window holds, so the
    window is carried as a list the registry can sum, with the quarters named
    beside it. The list is what the registry recomputes from; the quarter
    entries are what a reader takes the figure apart with.

    The observation id names the window, so the selection is recoverable from
    the observations alone -- the same way for a run and for a replay of it.
    """
    if not ttm_eps:
        return None
    components = [
        component
        for component in (ttm_eps.get("components") or [])
        if (
            component.get("value") is not None
            or component.get("free_cash_flow") is not None
        )
        and component.get("period_end")
    ]
    if len(components) != 4:
        return None
    window = ttm_eps.get("window_anchor") or {}
    window_end = components[-1]["period_end"]

    def _quarter_value(component: Dict[str, Any]) -> Optional[float]:
        raw = component.get("value")
        if raw is None:
            raw = component.get("free_cash_flow")
        try:
            return None if raw is None else float(raw)
        except (TypeError, ValueError):
            return None

    return Observation(
        metric=metric,
        observation_id=f"{metric}-{window_end}",
        # The figure is a series, not a scalar: the trailing figure is its
        # sum, and the registry sums the list the operand selects.
        value={
            "samples": [_quarter_value(component) for component in components],
            "window_end": window_end,
            # The declared trailing figure, as the source states it. The
            # samples are the quarters it is the sum of, and their sum in
            # floating point is the same number to fifteen places but not the
            # same number. The declared figure is what the valuation uses; the
            # sum is what the document recomputes, and the two are compared
            # with a tolerance.
            "declared_value": ttm_eps.get("value"),
            # Whether this window needs a furnished fourth quarter. An earnings
            # window does -- the fourth quarter is the one a fiscal year does
            # not report on its own -- and a cash-flow window does not, because
            # every quarter of it is a filed cash-flow statement.
            "requires_furnished_quarter": requires_furnished_quarter,
            "fiscal_year": window.get("fiscal_year"),
            "fiscal_quarter": window.get("fiscal_quarter"),
            "derivation": ttm_eps.get("derivation"),
            "derived_not_issuer_declared": bool(
                ttm_eps.get("derived_not_issuer_declared")
            ),
            "quarters": [
                {
                    "position": position,
                    "value": component.get("value"),
                    "form": component.get("form"),
                    "accession": component.get("accession"),
                    "period_start": component.get("period_start"),
                    "period_end": component.get("period_end"),
                    "acceptance_datetime": component.get("acceptance_datetime"),
                    "usable_date": component.get("usable_date"),
                    "evidence_class": component.get("evidence_class"),
                    "stated_directly": component.get("stated_directly"),
                    "content_sha256": component.get("content_sha256"),
                    "source_url": component.get("source_url"),
                }
                for position, component in enumerate(components, start=1)
            ],
        },
        unit=unit,
        provider="SecEdgar",
        source_type=SourceType.REGULATORY_FILING.value,
        definition=(
            "The four directly stated quarterly figures a trailing figure is "
            "the sum of."
        ),
        methodology=(
            "the four directly stated quarterly diluted figures the window "
            "covers, each as the filer reported it"
        ),
        retrieved_at=components[-1].get("usable_date") or "1970-01-01",
        currency=components[0].get("currency") or "USD",
        currency_basis=CurrencyBasis.REPORTED.value,
        period_start=components[0].get("period_start"),
        period_end=window_end,
        as_of=window_end,
        available_at=max(
            str(
                component.get("usable_date")
                or component.get("knowable_from")
                or ""
            )
            for component in components
        ),
        available_at_basis=AvailabilityBasis.ACCEPTANCE_DATETIME.value,
        source_url=components[-1].get("source_url"),
        raw={
            "ttm_window": {
                "role": "EARNINGS_ANCHOR",
                "window_end": window_end,
                "fiscal_year": window.get("fiscal_year"),
                "fiscal_quarter": window.get("fiscal_quarter"),
                "derivation": ttm_eps.get("derivation"),
                "derived_not_issuer_declared": bool(
                    ttm_eps.get("derived_not_issuer_declared")
                ),
                "quarters": [
                    {
                        "position": position,
                        "value": component.get("value"),
                        "form": component.get("form"),
                        "accession": component.get("accession"),
                        "period_start": component.get("period_start"),
                        "period_end": component.get("period_end"),
                        "acceptance_datetime": component.get("acceptance_datetime"),
                        "usable_date": component.get("usable_date"),
                        "evidence_class": component.get("evidence_class"),
                        "stated_directly": component.get("stated_directly"),
                        "content_sha256": component.get("content_sha256"),
                        "source_url": component.get("source_url"),
                    }
                    for position, component in enumerate(components, start=1)
                ],
            },
            "samples": [_quarter_value(component) for component in components],
        },
        observation_count=len(components),
        status=ValidationStatus.UNVERIFIABLE,
        status_reasons=("a single official source cannot cross-validate itself",),
        inputs=(),
        basis={
            "measurement_basis": "DIRECTLY_STATED_QUARTERS",
            "reporting_currency": components[0].get("currency") or "USD",
            "derivation": "SUM_OF_DIRECTLY_STATED_QUARTERLY_FIGURES",
            "source_declared": True,
        },
    )


def income_window_observation(
    qualified: Optional[Dict[str, Any]],
    metric: str = "ttm_revenue_window",
    unit: str = Unit.CURRENCY.value,
) -> Optional[Observation]:
    """
    The trailing revenue or EBITDA window, as one list-valued observation.

    A trailing figure is the sum of the quarters the window holds, so the
    window is carried as a list the registry can sum, with the quarters named
    beside it. Each quarter carries the accessions it was arrived at, the
    formula, and whether it was stated by the filer or arrived at by
    differencing two of its durations, so the sum can be taken apart rather
    than taken on trust.
    """
    if not qualified:
        return None
    components = [
        component
        for component in (qualified.get("components") or [])
        if component.get("value") is not None and component.get("period_end")
    ]
    if len(components) != 4:
        return None
    window = qualified.get("window_anchor") or {}
    window_end = components[-1]["period_end"]

    def _quarter(component: Dict[str, Any]) -> Dict[str, Any]:
        quarter = {
            "position": None,
            "value": component.get("value"),
            "period_end": component.get("period_end"),
            "fiscal_year": component.get("fiscal_year"),
            "fiscal_quarter": component.get("fiscal_quarter"),
            "currency": component.get("currency"),
            "formula": component.get("formula"),
            "derivation": component.get("derivation"),
            "accessions": component.get("accessions"),
            "forms": component.get("forms"),
            "source_urls": component.get("source_urls"),
            "acceptance_datetimes": component.get("acceptance_datetimes"),
            "periods": component.get("periods"),
            "stated_directly": bool(component.get("stated_directly")),
            "derived_not_issuer_declared": bool(
                component.get("derived_not_issuer_declared")
            ),
            "knowable_from": component.get("knowable_from"),
        }
        if component.get("operating_income") is not None:
            quarter["operating_income"] = component.get("operating_income")
            quarter["depreciation_and_amortization"] = component.get(
                "depreciation_and_amortization"
            )
            quarter["ebitda"] = component.get("ebitda")
            quarter["operating_income_derivation"] = component.get(
                "operating_income_derivation"
            )
            quarter["depreciation_derivation"] = component.get(
                "depreciation_derivation"
            )
            quarter["operating_income_accessions"] = component.get(
                "operating_income_accessions"
            )
            quarter["depreciation_accessions"] = component.get(
                "depreciation_accessions"
            )
        return quarter

    quarters = []
    for position, component in enumerate(components, start=1):
        quarter = _quarter(component)
        quarter["position"] = position
        quarters.append(quarter)

    return Observation(
        metric=metric,
        observation_id=f"{metric}-{window_end}",
        value={
            "samples": [float(component["value"]) for component in components],
            "window_end": window_end,
            "declared_value": qualified.get("value"),
            # Neither an income-statement window nor a cash-flow window needs a
            # furnished fourth quarter: every quarter of them comes from a
            # filed statement, and the fourth is the fiscal year less the nine
            # months it states.
            "requires_furnished_quarter": False,
            "fiscal_year": window.get("fiscal_year"),
            "fiscal_quarter": window.get("fiscal_quarter"),
            "derivation": qualified.get("derivation"),
            "currency": qualified.get("currency"),
            "quarters": quarters,
        },
        unit=unit,
        provider="SecEdgar",
        source_type=SourceType.REGULATORY_FILING.value,
        definition=(
            "The four quarterly figures a trailing income-statement figure is "
            "the sum of."
        ),
        methodology=(
            "the four fiscal quarters the window covers, each as the filer "
            "stated it or as the difference of two of its filed durations"
        ),
        retrieved_at=qualified.get("usable_from") or "1970-01-01",
        currency=qualified.get("currency") or "USD",
        currency_basis=CurrencyBasis.REPORTED.value,
        period_start=components[0].get("period_end"),
        period_end=window_end,
        as_of=window_end,
        available_at=qualified.get("usable_from"),
        available_at_basis=AvailabilityBasis.ACCEPTANCE_DATETIME.value,
        source_url=(components[-1].get("source_urls") or [None])[0],
        raw={
            "ttm_window": {
                "role": "INCOME_STATEMENT_WINDOW",
                "window_end": window_end,
                "fiscal_year": window.get("fiscal_year"),
                "fiscal_quarter": window.get("fiscal_quarter"),
                "derivation": qualified.get("derivation"),
                "currency": qualified.get("currency"),
                "quarters": quarters,
            },
            "samples": [float(component["value"]) for component in components],
        },
        observation_count=len(components),
        status=ValidationStatus.UNVERIFIABLE,
        status_reasons=("a single official source cannot cross-validate itself",),
        inputs=(),
        basis={
            "measurement_basis": "DIRECTLY_STATED_QUARTERS",
            "reporting_currency": qualified.get("currency") or "USD",
            "derivation": "SUM_OF_DISCRETE_QUARTERLY_FIGURES",
            "source_declared": True,
        },
    )


def component_observations(
    ttm_eps: Optional[Dict[str, Any]],
) -> List[Observation]:
    """
    The quarterly figures a trailing earnings figure is built from, as
    observations.

    Each carries the filing that reported it, the acceptance instant, the
    period it covers and the currency it is in, so the trailing figure can be
    taken apart rather than taken on trust. The observation id names the
    window and the quarter's place in it, so the selection is recoverable from
    the observations alone -- the same way for a run and for a replay of it.
    """
    if not ttm_eps:
        return []
    window = ttm_eps.get("window_anchor") or {}
    window_end = window.get("period_end")
    if window_end is None:
        # The anchor's period end is the window's end; the dataset's anchor
        # states the fiscal year and quarter, and the last component's period
        # end is the window's end.
        components = ttm_eps.get("components") or []
        window_end = components[-1]["period_end"] if components else None
    if window_end is None:
        return []

    observations: List[Observation] = []
    for position, component in enumerate(ttm_eps.get("components") or []):
        period_end = component.get("period_end")
        if not period_end:
            continue
        observations.append(
            Observation(
                metric="ttm_eps_component",
                observation_id=(
                    f"ttm-eps-{window_end}-q{position + 1}-{period_end}"
                ),
                value=component.get("value"),
                unit=Unit.PER_SHARE.value,
                provider="SecEdgar",
                source_type=SourceType.REGULATORY_FILING.value,
                definition=(
                    "A directly stated quarterly diluted earnings figure, as "
                    "the filer reported it."
                ),
                methodology=(
                    "us-gaap:EarningsPerShareDiluted as reported in "
                    f"{component.get('form')} accession {component.get('accession')}"
                ),
                retrieved_at=component.get("usable_date") or "1970-01-01",
                currency=component.get("currency") or "USD",
                currency_basis=CurrencyBasis.REPORTED.value,
                period_start=component.get("period_start"),
                period_end=period_end,
                as_of=period_end,
                available_at=component.get("usable_date"),
                available_at_basis=AvailabilityBasis.ACCEPTANCE_DATETIME.value,
                source_url=component.get("source_url"),
                raw={
                    "ttm_window": {
                        "role": "EARNINGS_ANCHOR",
                        "window_end": window_end,
                        "position": position + 1,
                        "quarter_count": ttm_eps.get("quarter_count"),
                    },
                    "accession": component.get("accession"),
                    "form": component.get("form"),
                    "acceptance_datetime": component.get("acceptance_datetime"),
                    "evidence_class": component.get("evidence_class"),
                    "stated_directly": component.get("stated_directly"),
                    "content_sha256": component.get("content_sha256"),
                    "legal_status_note": component.get("legal_status_note"),
                    "sec_item": component.get("sec_item"),
                },
                observation_count=1,
                status=ValidationStatus.UNVERIFIABLE,
                status_reasons=(
                    "a single official source cannot cross-validate itself",
                ),
                inputs=(),
                basis={
                    "measurement_basis": "DIRECTLY_STATED_QUARTER",
                    "reporting_currency": component.get("currency") or "USD",
                    "derivation": "DIRECTLY_STATED_BY_FILER",
                    "source_declared": True,
                },
            )
        )
    return observations


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
