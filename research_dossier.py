"""
The research dossier: one company, one valuation date, everything ST-EVA has.

This module assembles the deliverable a person or an LLM actually reads. It
orders the material the way a research reader wants it and keeps the provenance
attached to every figure, rather than presenting a short list of headline
numbers whose inputs are somewhere else.

The section order is fixed and each section states what it does and does not
contain:

  1. Market and company data      -- what was observed, from where, as of when
  2. Financial history            -- how the numbers moved, with growth and margin
  3. Valuation metrics            -- the multiples the current price implies
  4. Reverse requirements         -- what the current price demands
  5. Valuation under scenarios    -- the same question at several assumptions
  6. Comparison to history and estimates -- the reverse result beside what is observed
  7. Rates and return conditions  -- the three rate families, kept apart
  8. Data limitations             -- what is missing, incomparable or unresolved

Two rules hold throughout:

* Nothing is averaged, ranked or blended into a single valuation. When two
  methods disagree the dossier shows the disagreement, because a single number
  would conceal which assumption produced it.
* A scenario is not a forecast. The dossier says so, and never attaches a
  probability, a ranking or a recommendation to any of them.

The module is pure formatting and assembly over an existing run result. It
performs no arithmetic of its own and no I/O.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence


DOSSIER_VERSION = "research-dossier/1.0"

SECTION_ORDER: Sequence[str] = (
    "market_and_company",
    "financial_history",
    "balance_sheet_and_capital_structure",
    "valuation_metrics",
    "reverse_requirements",
    "valuation_scenarios",
    "comparison_to_observations",
    "rates_and_conditions",
    "data_limitations",
)

SECTION_TITLES: Dict[str, str] = {
    "market_and_company": "市場與公司資料 / Market and company data",
    "financial_history": "歷史財務變化 / Financial history",
    "balance_sheet_and_capital_structure": (
        "資產負債表與資本結構 / Balance sheet and capital structure"
    ),
    "valuation_metrics": "估值指標 / Valuation metrics",
    "reverse_requirements": "目前價格的反推要求 / Reverse requirements at the current price",
    "valuation_scenarios": "多組假設下的估值結果 / Valuation under multiple assumptions",
    "comparison_to_observations": "與歷史及市場預估比較 / Comparison to history and estimates",
    "rates_and_conditions": "利率與報酬條件 / Rates and return conditions",
    "data_limitations": "資料限制 / Data limitations",
}


def _number(value: Any, digits: int = 2) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return "N/A"
    if abs(value) >= 1e12:
        return "{:,.0f}".format(value)
    if abs(value) >= 1e6:
        return "{:,.2f}B".format(value / 1e9)
    if abs(value) >= 1e4:
        return "{:,.2f}M".format(value / 1e6)
    return "{:,.{d}f}".format(value, d=digits)


def _percent(value: Any, digits: int = 1, signed: bool = False) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return "N/A"
    return "{:+.{d}f}%".format(value * 100, d=digits) if signed else "{:.{d}f}%".format(value * 100, d=digits)


def build_dossier(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Assemble the dossier from a run result.

    Every section is always present, including when it is empty. A section that
    says "not acquired" is more useful to a reader than a missing key, because
    the two are otherwise indistinguishable from a bug.
    """
    reverse = result.get("reverse_requirements") or {}
    observed = result.get("observed_valuation") or {}
    snapshot = result.get("market_snapshot") or {}
    quality = result.get("data_quality") or {}
    fundamentals = result.get("fundamental_snapshot") or {}
    cross = result.get("consensus_cross_check") or {}

    sections: Dict[str, Any] = {}

    # ---- 1. market and company ----
    cross_source = reverse.get("cross_source_validation") or {}
    sections["market_and_company"] = {
        "title": SECTION_TITLES["market_and_company"],
        "asset": {
            "ticker": result.get("ticker"),
            "company_name": result.get("company_name"),
            "exchange": snapshot.get("exchange"),
            "currency": snapshot.get("currency"),
        },
        "as_of": result.get("as_of"),
        "price": {
            "value": snapshot.get("price"),
            "currency": snapshot.get("currency"),
            "provider": snapshot.get("provider"),
            "source": snapshot.get("source"),
            "source_type": snapshot.get("source_type"),
        },
        "size": {
            "market_cap": fundamentals.get("current_market_cap"),
            "enterprise_value": fundamentals.get("current_enterprise_value"),
        },
        "data_quality": {
            "discrepancy_status": quality.get("discrepancy_status"),
            "acquisition_errors": quality.get("acquisition_errors") or [],
            "consensus_forward_eps_period": quality.get("consensus_forward_eps_period"),
        },
        "cross_source_validation": cross_source,
        "notes": [
            "Market capitalization and enterprise value are taken as observed from the "
            "provider. They are not rebuilt from price times shares plus net debt, because "
            "the provider's debt and cash definitions are not reconciled to its share count.",
        ],
    }

    # ---- 2. financial history ----
    history = reverse.get("financial_history") or {}
    sections["financial_history"] = {
        "title": SECTION_TITLES["financial_history"],
        "acquired": bool(history.get("observation_count")),
        "observation_count": history.get("observation_count"),
        "source_provider": history.get("source_provider"),
        "series": history.get("series") or {},
        "growth": history.get("growth") or {},
        "margins": history.get("margins") or {},
        "unavailable": history.get("unavailable") or [],
        "notes": history.get("reading_notes") or [],
    }

    # ---- 3. balance sheet and capital structure ----
    capital = reverse.get("capital_structure") or {}
    sections["balance_sheet_and_capital_structure"] = {
        "title": SECTION_TITLES["balance_sheet_and_capital_structure"],
        "status": capital.get("status", "NOT_ACQUIRED"),
        "observations": capital.get("observations") or {},
        "observed": capital.get("observed") or {},
        "reconstructed_market_cap": capital.get("reconstructed_market_cap") or {},
        "reconstructed_enterprise_value": capital.get("reconstructed_enterprise_value") or {},
        "observed_vs_reconstructed": capital.get("observed_vs_reconstructed") or [],
        "share_count_note": capital.get("share_count_note"),
        "unavailable": capital.get("unavailable") or [],
        "notes": capital.get("notes") or [],
    }

    # ---- 4. valuation metrics ----
    sections["valuation_metrics"] = {
        "title": SECTION_TITLES["valuation_metrics"],
        "observed_multiples": {
            "current_pe": observed.get("current_pe"),
            "forward_pe": observed.get("forward_pe"),
            "consensus_forward_pe": observed.get("consensus_forward_pe"),
            "current_ps": observed.get("current_ps"),
            "current_pfcf": observed.get("current_pfcf"),
            "current_ev_ebitda": observed.get("current_ev_ebitda"),
        },
        "observed_yields": {
            "fcf_yield": ((reverse.get("cash_flow_cross_checks") or {}).get("observed") or {}).get("fcf_yield"),
            "ebitda_yield_on_ev": ((reverse.get("cash_flow_cross_checks") or {}).get("observed") or {}).get(
                "ebitda_yield_on_ev"
            ),
            "revenue_yield_on_market_cap": (
                (reverse.get("cash_flow_cross_checks") or {}).get("observed") or {}
            ).get("revenue_yield_on_market_cap"),
        },
        "historical_bands": {
            "pe": observed.get("historical_pe_band"),
            "ps": observed.get("historical_ps_band"),
            "pfcf": observed.get("historical_pfcf_band"),
            "ev_ebitda": observed.get("historical_ev_ebitda_band"),
        },
        "band_eligibility": (result.get("reference") or {}).get("historical_band_status") or {},
        "min_observations_for_reference": (result.get("reference") or {}).get(
            "min_observations_for_reference"
        ),
        "consensus": {
            "consensus_forward_eps": cross.get("consensus_forward_eps"),
            "price_at_historical_median_pe": cross.get("price_at_historical_median_pe"),
            "price_gap_vs_historical_median": cross.get(
                "price_gap_vs_historical_median_on_consensus_eps"
            ),
        },
        "notes": [
            "An observed multiple is the multiple the market is applying to a reported "
            "figure today. It is not a reference and it does not imply what the market "
            "expects.",
            "A historical band whose observation count is below the stated threshold is "
            "reported but is not used as a reference multiple.",
        ],
    }

    # ---- 4. reverse requirements ----
    matrix = reverse.get("reverse_requirements_matrix") or []
    sections["reverse_requirements"] = {
        "title": SECTION_TITLES["reverse_requirements"],
        "status": reverse.get("status"),
        "status_reason": reverse.get("status_reason"),
        "market_price": reverse.get("market_price"),
        "starting_eps": matrix[0].get("start_eps") if matrix else None,
        "matrix": matrix,
        "matrix_size": reverse.get("matrix_size"),
        "fingerprint": reverse.get("fingerprint"),
        "formula_version": reverse.get("formula_version"),
        "notes": (reverse.get("reading_notes") or [])
        + [
            "This matrix is a set of conditional results under stated assumptions. It "
            "carries no probabilities, no weighting and no ranking, and it does not state "
            "which scenario is more likely.",
        ],
    }

    # ---- 5. valuation under scenarios ----
    methods = reverse.get("valuation_methods") or {}
    sections["valuation_scenarios"] = {
        "title": SECTION_TITLES["valuation_scenarios"],
        "methods": methods.get("methods") or {},
        "disagreement": methods.get("disagreement"),
        "unavailable": methods.get("unavailable") or [],
        "exit_multiple_scenarios": sorted(
            {
                (row.get("exit_multiple") or {}).get("source")
                for row in matrix
                if row.get("exit_multiple")
            },
            key=lambda value: str(value),
        ),
        "notes": (methods.get("reading_notes") or [])
        + [
            "Each method is conditional on its own reference multiple and carries that "
            "multiple's provenance and sample size.",
        ],
    }

    # ---- 6. comparison to observations ----
    required = (reverse.get("cash_flow_cross_checks") or {}).get(
        "required_at_reference_multiple"
    ) or {}
    comparisons = []
    for method_name, label in (
        ("earnings_multiple", "EPS"),
        ("revenue_multiple", "Revenue"),
        ("cash_flow_multiple", "FCF"),
        ("enterprise_value_multiple", "EBITDA"),
    ):
        block = (methods.get("methods") or {}).get(method_name) or {}
        comparisons.append(
            {
                "method": method_name,
                "label": label,
                "implied": block.get("implied"),
                "unit": block.get("unit"),
                "observed": block.get("observed"),
                "observed_label": block.get("observed_label"),
                "gap": block.get("gap_implied_vs_observed"),
                "reference_multiple": block.get("reference_multiple"),
                "status": block.get("status"),
            }
        )
    margin_block = (methods.get("methods") or {}).get("implied_net_margin") or {}
    sections["comparison_to_observations"] = {
        "title": SECTION_TITLES["comparison_to_observations"],
        "per_method": comparisons,
        "required_at_reference_multiple": required,
        "implied_net_margin": margin_block,
        "net_margin_context": _net_margin_context(history, margin_block),
        "notes": [
            "The gap is the implied figure against the observed figure for the same "
            "method. It is not a forecast error and has no sign meaning.",
            "A positive gap means the reference multiple would require more than the "
            "company currently reports; it does not mean the company will deliver it.",
        ],
    }

    # ---- 7. rates and conditions ----
    families = reverse.get("rate_families") or {}
    sections["rates_and_conditions"] = {
        "title": SECTION_TITLES["rates_and_conditions"],
        "risk_free_rate": families.get("risk_free_rate") or {},
        "cost_of_equity": families.get("cost_of_equity") or {},
        "investor_required_return": families.get("investor_required_return") or {},
        "matrix_required_returns": families.get("matrix_required_returns") or [],
        "separation_note": families.get("separation_note"),
    }

    # ---- 8. data limitations ----
    reverse_unavailable = reverse.get("unavailable") or []
    sections["data_limitations"] = {
        "title": SECTION_TITLES["data_limitations"],
        "missing_data": result.get("missing_data") or [],
        "unavailable": reverse_unavailable,
        "financial_history_unavailable": history.get("unavailable") or [],
        "run_limitations": result.get("limitations") or [],
        "dcf": reverse.get("dcf") or {},
        "counts": {
            "unavailable_total": len(reverse_unavailable),
            "by_reason_kind": _count_by_kind(reverse_unavailable),
        },
        "notes": [
            "An item listed here was requested and not produced, or was produced under "
            "conditions that limit it. Nothing listed here has been filled with a "
            "default, an interpolation or a borrowed value from a related metric.",
        ],
    }

    return {
        "dossier_version": DOSSIER_VERSION,
        "ticker": result.get("ticker"),
        "as_of": result.get("as_of"),
        "currency": snapshot.get("currency"),
        "formula_versions": {
            "reverse_requirements": reverse.get("formula_version"),
            "financial_history": history.get("formula_version"),
            "dossier": DOSSIER_VERSION,
        },
        "fingerprint": reverse.get("fingerprint"),
        "section_order": list(SECTION_ORDER),
        "sections": sections,
        "scope_statement": (
            "This dossier records sourced evidence and deterministic calculations made "
            "under explicitly stated assumptions. It does not assign probabilities to "
            "scenarios, rank them, or combine them into a single expected value. A "
            "conditional figure is the fundamental a chosen multiple corresponds to, not "
            "a claim about what the market expects."
        ),
    }


def _net_margin_context(history: Dict[str, Any], margin_block: Dict[str, Any]) -> Dict[str, Any]:
    """
    The implied net margin beside the margin the filings actually report.

    The implied figure is derived from a chosen P/E and P/S. The only thing it
    can be checked against is the margin the company earns today, so that
    series is carried next to it rather than being left in another section.
    """
    rows = ((history.get("margins") or {}).get("net_margin.annual")) or []
    comparable = [row for row in rows if row.get("comparable") and row.get("margin") is not None]
    series = [
        {"period_end": row.get("period_end"), "margin": row.get("margin")} for row in comparable
    ]
    return {
        "implied": margin_block.get("implied"),
        "implied_reference": margin_block.get("reference_multiple"),
        "observed_latest": series[-1] if series else None,
        "observed_series": series,
        "gap": margin_block.get("gap_implied_vs_observed"),
        "gap_basis": margin_block.get("observed_label"),
        "status": (
            "COMPARED"
            if margin_block.get("implied") is not None and series
            else "NOT_COMPARED"
        ),
        "note": (
            "The implied margin depends on both reference multiples. It is the margin "
            "those two multiples jointly require, not a margin the market has stated."
        ),
    }


def _count_by_kind(entries: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for entry in entries:
        kind = str(entry.get("reason_kind") or "UNSPECIFIED")
        counts[kind] = counts.get(kind, 0) + 1
    return counts


def render_dossier(dossier: Dict[str, Any]) -> str:
    """
    The human-readable dossier.

    Ordered, complete and free of new arithmetic. Where a figure is not
    computable the section says so instead of omitting the row, so a reader can
    tell a missing number from an unimportant one.
    """
    lines: List[str] = []
    bar = "=" * 78
    rule = "-" * 78

    lines.append(bar)
    lines.append(
        "ST-EVA 研究資料冊  |  %s  |  %s"
        % (dossier.get("ticker"), dossier.get("as_of"))
    )
    lines.append("dossier %s" % dossier.get("dossier_version"))
    lines.append(bar)
    lines.append("")
    lines.append(dossier.get("scope_statement", ""))
    lines.append("")

    sections = dossier.get("sections") or {}
    for key in dossier.get("section_order") or []:
        section = sections.get(key)
        if not section:
            continue
        lines.append(rule)
        lines.append(section.get("title", key))
        lines.append(rule)
        lines.extend(_render_section(key, section))
        lines.append("")

    return "\n".join(lines)


def _render_section(key: str, section: Dict[str, Any]) -> List[str]:
    renderer = _SECTION_RENDERERS.get(key)
    if renderer is None:
        return []
    return renderer(section)


def _render_market(section: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    asset = section.get("asset") or {}
    price = section.get("price") or {}
    size = section.get("size") or {}
    quality = section.get("data_quality") or {}

    lines.append(
        "公司: %s (%s)  交易所: %s  幣別: %s"
        % (asset.get("company_name"), asset.get("ticker"), asset.get("exchange"), asset.get("currency"))
    )
    lines.append(
        "估值時點: %s" % section.get("as_of")
    )
    lines.append("")
    lines.append("市場資料:")
    lines.append(
        "  股價 %s %s   來源 %s (%s)   來源欄位 %s"
        % (
            _number(price.get("value")),
            price.get("currency") or "",
            price.get("provider"),
            price.get("source_type"),
            price.get("source"),
        )
    )
    lines.append("  市值 %s   企業價值 %s" % (_number(size.get("market_cap")), _number(size.get("enterprise_value"))))
    lines.append("")
    lines.append("資料品質:")
    lines.append("  狀態: %s" % quality.get("discrepancy_status"))
    errors = quality.get("acquisition_errors") or []
    lines.append("  取得錯誤: %s" % (", ".join(errors) if errors else "無"))
    if quality.get("consensus_forward_eps_period"):
        lines.append("  共識 EPS 期間: %s" % quality["consensus_forward_eps_period"])
    lines.append("")
    lines.append("跨來源比對 (CROSS-SOURCE VERIFICATION):")
    cross = section.get("cross_source_validation") or {}
    if cross.get("performed"):
        lines.append("  %s" % cross.get("summary"))
        lines.append("  %-22s %-22s %-12s %s" % ("指標", "狀態", "差異", "說明"))
        for metric, verdict in sorted((cross.get("verdicts") or {}).items()):
            lines.append(
                "  %-22s %-22s %-12s %s"
                % (
                    metric,
                    verdict.get("status"),
                    _format_difference(verdict),
                    (verdict.get("explanation") or "")[:0],
                )
            )
            explanation = (verdict.get("explanation") or "").replace("\n", " ")
            if explanation:
                lines.append("      %s" % explanation)
        lines.append("")
        lines.append("  未採用任何一方為權威值；每個數值皆保留原值。")
    else:
        lines.append("  未執行: %s" % cross.get("reason"))
    lines.append("")
    for note in section.get("notes") or []:
        lines.append("  * %s" % note)
    return lines


def _format_difference(verdict: Dict[str, Any]) -> str:
    """A short difference cell: percentage when both sides exist, else a dash."""
    vendor = verdict.get("vendor_value")
    filing = verdict.get("filing_value")
    if not isinstance(vendor, (int, float)) or not isinstance(filing, (int, float)):
        return "-"
    if not filing:
        return "-"
    return "%.4f%%" % (abs(vendor - filing) / abs(filing) * 100.0)


def _render_history(section: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    if not section.get("acquired"):
        lines.append("本次執行未取得財報資料。")
        for entry in section.get("unavailable") or []:
            lines.append("  - %s: %s" % (entry.get("item"), entry.get("reason")))
        return lines

    lines.append(
        "來源: %s   觀測筆數: %s" % (section.get("source_provider"), section.get("observation_count"))
    )
    lines.append("")

    for name, series in (section.get("series") or {}).items():
        points = series.get("points") or []
        if not points:
            continue
        metric = (points[0].get("metric") if points else name) or name
        unit = points[0].get("unit") or ""
        lines.append("[%s / %s]  %d 筆" % (metric, series.get("window"), len(points)))
        for point in points:
            deriv = point.get("derivation") or ""
            lines.append(
                "   期間末 %-12s  值 %-20s 單位 %-10s 可用日 %-12s 來源 %s %s"
                % (
                    point.get("period_end"),
                    _number(point.get("value")),
                    unit,
                    str(point.get("available_at") or "")[:10],
                    point.get("provider"),
                    deriv,
                )
            )
        lines.append("")

    growth = section.get("growth") or {}
    if growth:
        lines.append("成長率 (年增率):")
        for name, rows in growth.items():
            if not rows:
                continue
            lines.append("  [%s]" % name)
            for row in rows:
                lines.append(
                    "   %-12s 值 %-20s 成長 %-10s 可比較 %s"
                    % (
                        row.get("period_end"),
                        _number(row.get("value")),
                        _percent(row.get("growth"), signed=True) if row.get("comparable") else "N/A",
                        "是" if row.get("comparable") else "否",
                    )
                )
                if not row.get("comparable") and row.get("reason"):
                    lines.append("       原因: %s" % row["reason"])
        lines.append("")

    margins = section.get("margins") or {}
    if margins:
        lines.append("利潤率:")
        for name, rows in margins.items():
            if not rows:
                continue
            lines.append("  [%s]" % name)
            for row in rows:
                lines.append(
                    "   %-12s 分子 %-18s 分母 %-18s 利潤率 %s"
                    % (
                        row.get("period_end"),
                        _number(row.get("numerator")),
                        _number(row.get("denominator")),
                        _percent(row.get("margin")) if row.get("comparable") else "N/A",
                    )
                )
                if not row.get("comparable") and row.get("reason"):
                    lines.append("       原因: %s" % row["reason"])
                if row.get("currency_match"):
                    lines.append("       注意: %s" % row["currency_match"])
        lines.append("")

    for note in section.get("notes") or []:
        lines.append("  * %s" % note)
    return lines


def _render_capital_structure(section: Dict[str, Any]) -> List[str]:
    """
    The balance sheet and the two capitalizations, side by side.

    Observed and reconstructed figures are printed as separate blocks with
    their own definitions and dates, because collapsing them would hide which
    one a reader is looking at.
    """
    lines: List[str] = []
    if section.get("status") == "NOT_ACQUIRED":
        lines.append("本次執行未取得財報資料，因此沒有資產負債表資料。")
        for entry in section.get("unavailable") or []:
            lines.append("  - %s: %s" % (entry.get("item"), entry.get("reason")))
        return lines

    lines.append("[時點觀測值 (INSTANT)]  有效日期為觀測當日，非期間金額")
    lines.append("  %-18s %-18s %-12s %-12s %-12s %-22s %s" % ("欄位", "值", "單位/幣別", "有效日", "可用日", "可用基準", "來源"))
    for metric, block in sorted((section.get("observations") or {}).items()):
        latest = block.get("latest") or {}
        if not latest.get("present"):
            lines.append("  %-18s %s" % (metric, "未取得"))
            continue
        unit_currency = "%s%s" % (
            latest.get("unit") or "",
            "/" + latest["currency"] if latest.get("currency") else "",
        )
        provider_status = (
            "%s [%s]" % (latest.get("provider"), latest.get("validation_status"))
            if latest.get("validation_status")
            else latest.get("provider")
        )
        lines.append(
            "  %-18s %-18s %-12s %-12s %-12s %-22s %s"
            % (
                metric,
                _number(latest.get("value")),
                unit_currency,
                latest.get("effective_date"),
                str(latest.get("available_at") or "")[:10],
                latest.get("available_at_basis") or "-",
                provider_status,
            )
        )
        if latest.get("comparability_caveat"):
            lines.append("    * 比較限制: %s" % latest["comparability_caveat"])
        for caveat in latest.get("caveats") or []:
            lines.append("    * 注意: %s" % caveat)
    lines.append("")

    observed = section.get("observed") or {}
    reconstructed_cap = section.get("reconstructed_market_cap") or {}
    reconstructed_ev = section.get("reconstructed_enterprise_value") or {}

    lines.append("[觀察值 vs 重建值]")
    lines.append("  %-18s %-22s %-22s %-14s" % ("項目", "觀察值(來源)", "重建值", "差異"))
    for row in section.get("observed_vs_reconstructed") or []:
        label = "市值" if row["metric"] == "market_cap" else "企業價值"
        observed_value = row.get("observed")
        reconstructed_value = row.get("reconstructed")
        difference = row.get("difference")
        lines.append(
            "  %-18s %-22s %-22s %-14s"
            % (
                label,
                _number(observed_value) if observed_value is not None else "-",
                _number(reconstructed_value) if reconstructed_value is not None
                else "不可計算(%s)" % row.get("reconstructed_status"),
                ("%+.4f%%" % (row["relative_difference"] * 100.0))
                if row.get("relative_difference") is not None
                else "-",
            )
        )
    lines.append("")

    if reconstructed_cap.get("status") == "COMPUTED":
        lines.append("  重建市值定義: %s" % reconstructed_cap.get("definition"))
        lines.append(
            "  輸入: 價格 %s @%s  ×  股數 %s @%s"
            % (
                reconstructed_cap["inputs"].get("price"),
                reconstructed_cap["inputs"].get("price_date"),
                _number(reconstructed_cap["inputs"].get("shares_outstanding")),
                reconstructed_cap["inputs"].get("shares_date"),
            )
        )
        if reconstructed_cap.get("date_alignment"):
            lines.append("  日期對齊: %s" % reconstructed_cap["date_alignment"])
        for note in reconstructed_cap.get("notes") or []:
            lines.append("    - %s" % note)
        lines.append("")

    lines.append("  重建企業價值: %s" % reconstructed_ev.get("status"))
    if reconstructed_ev.get("value") is not None:
        lines.append("    定義: %s" % reconstructed_ev.get("definition"))
        lines.append("    值: %s" % _number(reconstructed_ev.get("value")))
        lines.append(
            "    已具備組成: %s" % ", ".join(reconstructed_ev.get("components_present") or [])
        )
        lines.append(
            "    缺少組成: %s" % ", ".join(reconstructed_ev.get("components_absent") or [])
        )
    for note in reconstructed_ev.get("notes") or []:
        lines.append("    - %s" % note)
    lines.append("")

    if section.get("share_count_note"):
        lines.append("  股數口徑: %s" % section["share_count_note"])
        lines.append("")

    for entry in section.get("unavailable") or []:
        lines.append("  - %s [%s]: %s" % (entry.get("item"), entry.get("reason_kind"), entry.get("reason")))
    if section.get("unavailable"):
        lines.append("")
    for note in section.get("notes") or []:
        lines.append("  * %s" % note)
    return lines


def _render_metrics(section: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    multiples = section.get("observed_multiples") or {}
    yields = section.get("observed_yields") or {}

    lines.append("目前倍數 (以現價與已報告數字計算):")
    for key, label in (
        ("current_pe", "P/E (TTM)"),
        ("forward_pe", "前瞻 P/E"),
        ("consensus_forward_pe", "共識前瞻 P/E"),
        ("current_ps", "P/S"),
        ("current_pfcf", "P/FCF"),
        ("current_ev_ebitda", "EV/EBITDA"),
    ):
        lines.append("  %-16s %s" % (label, _number(multiples.get(key))))
    lines.append("")
    lines.append("殖利率:")
    for key, label in (
        ("fcf_yield", "FCF 殖利率"),
        ("ebitda_yield_on_ev", "EBITDA / EV"),
        ("revenue_yield_on_market_cap", "營收 / 市值"),
    ):
        lines.append("  %-16s %s" % (label, _percent(yields.get(key))))
    lines.append("")

    bands = section.get("historical_bands") or {}
    eligibility = section.get("band_eligibility") or {}
    minimum = section.get("min_observations_for_reference")
    lines.append("歷史估值區間:")
    for key, label in (("pe", "P/E"), ("ps", "P/S"), ("pfcf", "P/FCF"), ("ev_ebitda", "EV/EBITDA")):
        band = bands.get(key) or {}
        median = band.get("median") if isinstance(band, dict) else None
        count = band.get("observations") if isinstance(band, dict) else None
        status = eligibility.get(key)
        lines.append(
            "  %-10s 中位數 %-10s 觀測數 %-8s 可否作參考: %s"
            % (label, _number(median, 2), count if count is not None else "未宣告", status or "-")
        )
    if minimum:
        lines.append("  (採用門檻: 歷史區間需 >= %s 個觀測值方可作為參考)" % minimum)
    lines.append("")

    consensus = section.get("consensus") or {}
    if consensus.get("consensus_forward_eps") is not None:
        lines.append("共識交叉檢核:")
        lines.append("  共識前瞻 EPS          %s" % _number(consensus.get("consensus_forward_eps"), 4))
        lines.append("  以歷史中位數倍數計之價格 %s" % _number(consensus.get("price_at_historical_median_pe")))
        lines.append(
            "  該價格 vs 現價        %s"
            % _percent(consensus.get("price_gap_vs_historical_median"), signed=True)
        )
        lines.append("")

    for note in section.get("notes") or []:
        lines.append("  * %s" % note)
    return lines


def _render_reverse(section: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    if section.get("status") != "COMPUTED":
        lines.append("未計算: %s" % section.get("status_reason"))
        return lines

    price = section.get("market_price") or {}
    anchor = section.get("starting_eps") or {}
    lines.append(
        "現價 %s %s (%s)"
        % (_number(price.get("value")), price.get("currency") or "", price.get("source"))
    )
    lines.append(
        "起始 EPS %s  基礎 %s  涵蓋 %s 個月  期間 %s"
        % (
            _number(anchor.get("value"), 4),
            anchor.get("basis"),
            anchor.get("months_covered"),
            anchor.get("period_label") or "-",
        )
    )
    if anchor.get("period_undeclared_by_source"):
        lines.append("  注意: 來源未宣告 EPS 涵蓋期間，上列期間為假設值。")
    lines.append("")
    lines.append("  期間   要求報酬  期末P/E  期末需求價  所需EPS  所需CAGR  vs共識")
    lines.append("  -----  --------  -------  ----------  -------  --------  -------")
    for row in section.get("matrix") or []:
        multiple = row.get("exit_multiple") or {}
        source = str(multiple.get("source") or "")
        label = "%s%s" % (
            _number(multiple.get("value"), 1),
            "*" if source.startswith("historical") else "",
        )
        lines.append(
            "  %-6s %-9s %-8s %-11s %-8s %-9s %s"
            % (
                "%s年" % _number(row.get("horizon_years"), 1),
                _percent(row.get("required_return"), 0, signed=True),
                label,
                _number(row.get("required_exit_price")),
                _number(row.get("required_terminal_eps"), 4),
                _percent(row.get("required_eps_cagr"), signed=True),
                _percent(row.get("gap_vs_consensus_terminal_eps"), signed=True)
                if row.get("gap_vs_consensus_terminal_eps") is not None
                else "-",
            )
        )
    lines.append("")
    lines.append("  * 期末 P/E 取自歷史區間分位數; 未標示者為使用者指定情境。")
    lines.append("  要求報酬為價格報酬，不含股息。CAGR 僅在兩端 EPS 期間可比較時計算。")
    lines.append("")
    flags = sorted(
        {flag for row in section.get("matrix") or [] for flag in row.get("flags") or []}
    )
    if flags:
        lines.append("  情境標記: %s" % ", ".join(flags))
        lines.append("")
    for note in section.get("notes") or []:
        lines.append("  * %s" % note)
    return lines


def _render_scenarios(section: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    methods = section.get("methods") or {}
    if not methods:
        lines.append("本次執行未產生任何估值方法結果。")
        for entry in section.get("unavailable") or []:
            lines.append("  - %s: %s" % (entry.get("item"), entry.get("reason")))
        return lines

    labels = {
        "earnings_multiple": "盈利倍數法 (P/E)",
        "revenue_multiple": "營收倍數法 (P/S)",
        "cash_flow_multiple": "現金流倍數法 (P/FCF)",
        "enterprise_value_multiple": "企業價值法 (EV/EBITDA)",
        "implied_net_margin": "隱含淨利率 (P/S + P/E 聯合)",
    }
    lines.append("  方法                     隱含值        實際值        差異       參考倍數")
    for name, label in labels.items():
        block = methods.get(name) or {}
        multiple = block.get("reference_multiple") or {}
        if isinstance(multiple, dict) and multiple.get("value") is not None:
            reference = "%s x (%s)" % (_number(multiple.get("value"), 2), multiple.get("source"))
        elif isinstance(multiple, dict) and multiple.get("pe") is not None:
            reference = "P/E %s + P/S %s" % (
                _number((multiple.get("pe") or {}).get("value"), 2),
                _number((multiple.get("revenue") or {}).get("value"), 2),
            )
        else:
            reference = "-"
        lines.append(
            "  %-22s %-13s %-13s %-10s %s"
            % (
                label,
                _number(block.get("implied"), 4) if block.get("status") == "COMPUTED" else "不可計算",
                _number(block.get("observed")) if block.get("observed") is not None else "-",
                _percent(block.get("gap_implied_vs_observed"), signed=True)
                if block.get("gap_implied_vs_observed") is not None
                else "-",
                reference,
            )
        )
    lines.append("")

    inm = methods.get("implied_net_margin") or {}
    variants = inm.get("share_basis_variants") or []
    if len(variants) > 1:
        lines.append("  隱含淨利率股數基準拆解:")
        for v in variants:
            shares_str = _number(v.get("shares"))
            date_str = f" @{v['shares_date']}" if v.get("shares_date") else ""
            lines.append(
                "    * %s: 隱含淨利率 %s (股數 %s%s)"
                % (
                    v.get("label"),
                    _percent(v.get("implied")),
                    shares_str,
                    date_str,
                )
            )
            if v.get("note"):
                lines.append("      - %s" % v["note"])
        lines.append("")

    sources = section.get("exit_multiple_scenarios") or []
    if sources:
        lines.append("  期末倍數情境來源: %s" % ", ".join(str(source) for source in sources))
        lines.append("")

    disagreement = section.get("disagreement")
    if disagreement:
        lines.append("  已計算方法: %s" % ", ".join(disagreement.get("methods_computed") or []))
        lines.append("  %s" % disagreement.get("note"))
        lines.append("")

    for entry in section.get("unavailable") or []:
        lines.append("  - %s: %s" % (entry.get("item"), entry.get("reason")))
    if section.get("unavailable"):
        lines.append("")
    for note in section.get("notes") or []:
        lines.append("  * %s" % note)
    return lines


def _render_comparison(section: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    lines.append("  方法                 隱含值          實際值          差異      實際值定義")
    for row in section.get("per_method") or []:
        multiple = row.get("reference_multiple") or {}
        lines.append(
            "  %-18s %-15s %-15s %-10s %s"
            % (
                row.get("label"),
                _number(row.get("implied"), 4) if row.get("implied") is not None else "不可計算",
                _number(row.get("observed")) if row.get("observed") is not None else "-",
                _percent(row.get("gap"), signed=True) if row.get("gap") is not None else "-",
                row.get("observed_label") or "-",
            )
        )
        if multiple.get("sample_size") is not None:
            lines.append(
                "      參考倍數 %s (%s, 樣本 %s)"
                % (_number(multiple.get("value"), 2), multiple.get("source"), multiple.get("sample_size"))
            )
    lines.append("")
    context = section.get("net_margin_context") or {}
    if context.get("status") == "COMPARED":
        lines.append("隱含淨利率 vs 實際淨利率:")
        lines.append(
            "  隱含淨利率 (由 P/E + P/S 聯合反推): %.2f%%"
            % (context["implied"] * 100.0)
        )
        observed = context.get("observed_latest") or {}
        lines.append(
            "  實際淨利率 @%s: %s"
            % (observed.get("period_end"), "%.2f%%" % (observed["margin"] * 100.0))
        )
        lines.append(
            "  差異: %+.3f 個百分點" % (context["gap"] * 100.0)
        )
        lines.append("  歷史序列:")
        for row in context.get("observed_series") or []:
            lines.append("    %-12s %.2f%%" % (row["period_end"], row["margin"] * 100.0))
        lines.append("  %s" % context.get("note"))
        lines.append("")
    else:
        lines.append("隱含淨利率: 無法與實際淨利率比較 (缺少可比較的實際序列)")
        lines.append("")

    for note in section.get("notes") or []:
        lines.append("  * %s" % note)
    return lines


def _render_rates(section: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    lines: List[str] = []
    risk_free = section.get("risk_free_rate") or {}
    observations = risk_free.get("observations") or []
    cost_of_equity = section.get("cost_of_equity") or {}
    investor = section.get("investor_required_return") or {}

    lines.append("[1] 無風險利率 (觀測值):")
    if observations:
        lines.append("    期限        殖利率%    觀測日        單位                 來源")
        for item in observations:
            lines.append(
                "    %-11s %-10s %-14s %-20s %s"
                % (
                    item.get("tenor_label"),
                    _number(item.get("rate"), 3),
                    item.get("as_of"),
                    item.get("unit"),
                    item.get("provider"),
                )
            )
    else:
        lines.append("    未取得 (需 --risk-free-rates)")
    lines.append("")

    lines.append("[2] CAPM 股權要求報酬 (模型估計):")
    if cost_of_equity.get("status") == "COMPUTED":
        inputs = cost_of_equity.get("inputs") or {}
        lines.append("    值: %s" % _percent(cost_of_equity.get("value")))
        lines.append(
            "    Rf %s (%s, %s)"
            % (
                _percent(inputs.get("risk_free_rate_decimal")),
                inputs.get("risk_free_rate_as_of") or "-",
                inputs.get("risk_free_rate_source") or "-",
            )
        )
        lines.append(
            "    Beta %s (%s, 估計期間 %s)"
            % (
                _number(inputs.get("beta"), 2),
                inputs.get("beta_source") or "-",
                inputs.get("beta_estimation_window") or "-",
            )
        )
        lines.append(
            "    ERP %s (%s, 估計期間 %s)"
            % (
                _percent(inputs.get("equity_risk_premium_decimal")),
                inputs.get("equity_risk_premium_source") or "-",
                inputs.get("equity_risk_premium_estimation_window") or "-",
            )
        )
    else:
        lines.append("    狀態: %s" % cost_of_equity.get("status"))
        if cost_of_equity.get("missing_inputs"):
            lines.append("    缺少: %s" % ", ".join(cost_of_equity["missing_inputs"]))
    lines.append("")

    lines.append("[3] 投資人設定報酬率 (情境輸入):")
    values = investor.get("values")
    if values:
        for key in sorted(values):
            lines.append("    %-14s %s" % (key, _percent(values[key])))
    else:
        lines.append("    未另行設定")
    lines.append("")
    if section.get("separation_note"):
        lines.append("  * %s" % section["separation_note"])
    return lines


def _render_limitations(section: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    dcf = section.get("dcf") or {}
    feasibility = dcf.get("feasibility") or {}

    lines.append("[缺少資料 (本次執行的 acquisition 層)]")
    missing = section.get("missing_data") or []
    if missing:
        for item in missing:
            lines.append("  - %s" % item)
    else:
        lines.append("  無")
    lines.append("")

    lines.append("[不可計算 / 不適用 (含原因)]")
    entries = section.get("unavailable") or []
    if entries:
        for entry in entries:
            lines.append(
                "  - %s [%s]: %s"
                % (entry.get("item"), entry.get("reason_kind"), entry.get("reason"))
            )
    else:
        lines.append("  無")
    lines.append("")

    history_entries = section.get("financial_history_unavailable") or []
    if history_entries:
        lines.append("[財務歷史限制]")
        for entry in history_entries:
            lines.append("  - %s [%s]: %s" % (entry.get("item"), entry.get("reason_kind"), entry.get("reason")))
        lines.append("")

    lines.append("[折現現金流 (DCF)]")
    lines.append("  狀態: %s" % dcf.get("status"))
    lines.append("  現金流定義: %s" % feasibility.get("cash_flow_basis_status"))
    missing_inputs = feasibility.get("missing_inputs") or []
    if missing_inputs:
        lines.append("  缺少欄位: %s" % ", ".join(missing_inputs))
    if dcf.get("explanation"):
        lines.append("  %s" % dcf["explanation"])
    lines.append("")

    counts = section.get("counts") or {}
    if counts:
        lines.append("[不可計算項目統計] 共 %s 筆" % counts.get("unavailable_total"))
        for kind, count in sorted((counts.get("by_reason_kind") or {}).items()):
            lines.append("  %-28s %s" % (kind, count))
        lines.append("")

    lines.append("[執行層限制說明]")
    for item in section.get("run_limitations") or []:
        lines.append("  - %s" % item)
    lines.append("")
    for note in section.get("notes") or []:
        lines.append("  * %s" % note)
    return lines


_SECTION_RENDERERS = {
    "market_and_company": _render_market,
    "financial_history": _render_history,
    "balance_sheet_and_capital_structure": _render_capital_structure,
    "valuation_metrics": _render_metrics,
    "reverse_requirements": _render_reverse,
    "valuation_scenarios": _render_scenarios,
    "comparison_to_observations": _render_comparison,
    "rates_and_conditions": _render_rates,
    "data_limitations": _render_limitations,
}
