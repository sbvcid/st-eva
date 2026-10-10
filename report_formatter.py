from __future__ import annotations

"""
ST-EVA human-readable report renderer.

This module performs no valuation arithmetic. It only reformats an already
validated ST-EVA result so a person can read it without parsing JSON.

The rendered report preserves the engine's rules:

    - no price target;
    - no buy/sell stance;
    - every implied figure is labelled with the multiple it is conditional on;
    - missing data is stated explicitly, never smoothed over.
"""

import json
import sys
import unicodedata
from typing import Any, Dict, List, Sequence

UNAVAILABLE = "UNAVAILABLE"

BOX_WIDTH = 74

BAND_STATUS_LABELS = {
    "USABLE_FOR_REFERENCE": "可用",
    "DESCRIPTIVE_ONLY_INSUFFICIENT_OBSERVATIONS": "觀測不足",
    "UNAVAILABLE": "無資料",
}

METHOD_LABELS = {
    "user_supplied_multiple": "使用者指定倍數",
    "historical_pe_median": "歷史 P/E 中位數",
    "none": "無參考倍數",
}

DISCREPANCY_LABELS = {
    "UNVERIFIABLE": "無法驗證（單一來源）",
    "SINGLE_SOURCE": "單一來源",
    "VERIFIED": "已交叉驗證",
    "CONSISTENT": "來源一致",
    "DISCREPANT": "來源不一致",
    "DATA_DISCREPANCY": "資料不一致",
}


def _is_missing(value: Any) -> bool:
    return value is None or value == UNAVAILABLE or value == {}


def _rule(char: str = "=") -> str:
    return char * BOX_WIDTH


def _display_width(text: str) -> int:
    """
    Terminal column count for a string.

    CJK glyphs occupy two columns, so len() misaligns any table that mixes
    Chinese labels with ASCII values.
    """
    width = 0
    for char in text:
        if unicodedata.combining(char):
            continue
        width += 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
    return width


def _pad(text: str, width: int) -> str:
    return text + " " * max(0, width - _display_width(text))


def _number(value: Any, digits: int = 2) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return "N/A"
    if abs(value) >= 1e12:
        return f"{value:,.0f}"
    if abs(value) >= 1e6:
        return f"{value / 1e9:,.2f}B"
    if abs(value) >= 1e4:
        return f"{value / 1e6:,.2f}M"
    return f"{value:,.{digits}f}"


def _percent(value: Any, digits: int = 1) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return "N/A"
    return f"{value * 100:+.{digits}f}%"


def _signed_percent(value: Any, digits: int = 1) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return "N/A"
    return f"{value * 100:.{digits}f}%"


def _basis_label(name: str, multiple: Any) -> str:
    if multiple is None or multiple == UNAVAILABLE:
        return f"{name} 無參考"
    return f"{name} = {_number(multiple)}x"


def _table(rows: Sequence[Sequence[str]], headers: Sequence[str]) -> List[str]:
    widths = [_display_width(h) for h in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], _display_width(cell))
    lines = [
        "  " + "  ".join(_pad(h, widths[i]) for i, h in enumerate(headers)),
        "  " + "  ".join("-" * widths[i] for i in range(len(headers))),
    ]
    for row in rows:
        lines.append(
            "  " + "  ".join(_pad(cell, widths[i]) for i, cell in enumerate(row))
        )
    return lines


def _render_reverse_requirements(reverse: Any) -> List[str]:
    """
    The reverse requirements matrix and its supporting blocks.

    Pure formatting. Every number is quoted from the package, and where the
    package reports a figure as not computable, that is printed as such rather
    than being replaced by a blank or a zero.
    """
    if not reverse:
        return []

    lines: List[str] = []
    lines.append(_rule("-"))
    lines.append("反向要求矩陣 (REVERSE REQUIREMENTS)")
    lines.append(_rule("-"))

    status = reverse.get("status")
    if status != "COMPUTED":
        lines.append("未計算。")
        reason = reverse.get("status_reason")
        if reason:
            lines.append(f"原因: {reason}")
        lines.append("")
        return lines

    anchor_block = None
    for row in reverse.get("reverse_requirements_matrix") or []:
        anchor_block = row.get("start_eps") or anchor_block
    if anchor_block:
        lines.append(
            f"起算 EPS: {_number(anchor_block.get('value'), 4)} "
            f"({anchor_block.get('basis')}, 涵蓋 {anchor_block.get('months_covered')} 個月)"
        )
        if anchor_block.get("period_undeclared_by_source"):
            lines.append("  注意: 來源未宣告 EPS 涵蓋期間，期間為假設值。")
        lines.append(f"目前價格: {_number(reverse.get('market_price', {}).get('value'))}"
                     f"  {reverse.get('market_price', {}).get('currency') or ''}")
        lines.append("")

    rows: List[List[str]] = []
    for row in reverse.get("reverse_requirements_matrix") or []:
        multiple = row.get("exit_multiple") or {}
        rows.append([
            f"{_number(row.get('horizon_years'), 1)}年",
            _percent(row.get("required_return"), 0),
            _number(multiple.get("value"), 1),
            _number(row.get("required_exit_price")),
            _number(row.get("required_terminal_eps"), 4),
            _percent(row.get("required_eps_cagr")),
        ])
    lines.extend(_table(rows, ["期間", "要求報酬", "期末P/E", "期末需求價", "所需EPS", "所需CAGR"]))
    lines.append("")
    lines.append("  要求報酬為價格報酬，不含股息。CAGR 僅在兩端 EPS 期間可比較時計算。")
    lines.append("")

    flags = sorted({
        flag
        for row in reverse.get("reverse_requirements_matrix") or []
        for flag in row.get("flags") or []
    })
    if flags:
        lines.append("  情境標記: " + ", ".join(flags))
        lines.append("")

    _render_rate_families(lines, reverse.get("rate_families") or {})
    _render_cash_flow_cross_checks(lines, reverse.get("cash_flow_cross_checks") or {})
    _render_dcf(lines, reverse.get("dcf") or {})

    unavailable = reverse.get("unavailable") or []
    if unavailable:
        lines.append(_rule("-"))
        lines.append(f"缺漏與不可計算 ({len(unavailable)})")
        lines.append(_rule("-"))
        for item in unavailable:
            reason = str(item.get("reason", "")).replace("\n", " ")
            lines.append(f"  - {item.get('item', '?')}: {reason}")
        lines.append("")

    return lines


def _render_rate_families(lines: List[str], families: Dict[str, Any]) -> None:
    """The three rate families, printed separately and never merged."""
    risk_free = families.get("risk_free_rate") or {}
    observations = risk_free.get("observations") or []
    cost_of_equity = families.get("cost_of_equity") or {}
    investor = families.get("investor_required_return") or {}

    lines.append(_rule("-"))
    lines.append("利率家族 (RATE FAMILIES)")
    lines.append(_rule("-"))

    if observations:
        lines.append("無風險利率 (觀測值):")
        rows = [
            [str(item.get("tenor_label")), _number(item.get("rate"), 3),
             str(item.get("as_of", "")), str(item.get("provider", ""))]
            for item in observations
        ]
        lines.extend(_table(rows, ["期限", "殖利率%", "觀測日", "來源"]))
    else:
        lines.append("無風險利率 (觀測值): 未取得 (需 --risk-free-rates)")
    lines.append("")

    status = cost_of_equity.get("status")
    if status == "COMPUTED":
        inputs = cost_of_equity.get("inputs") or {}
        lines.append(
            f"CAPM 股權要求報酬 (估計): {_signed_percent(cost_of_equity.get('value'))}"
        )
        lines.append(
            f"  Rf {_signed_percent(inputs.get('risk_free_rate_decimal'))}"
            f" ({inputs.get('risk_free_rate_as_of') or '?'})"
            f" + beta {_number(inputs.get('beta'), 2)}"
            f" × ERP {_signed_percent(inputs.get('equity_risk_premium_decimal'))}"
        )
    else:
        lines.append(f"CAPM 股權要求報酬: {status}")
        if cost_of_equity.get("missing_inputs"):
            lines.append("  缺: " + ", ".join(cost_of_equity["missing_inputs"]))
    lines.append("")

    values = investor.get("values")
    if values:
        rendered = ", ".join(f"{key} {_signed_percent(item)}" for key, item in sorted(values.items()))
        lines.append(f"投資人設定報酬率 (情境輸入): {rendered}")
    else:
        lines.append("投資人設定報酬率 (情境輸入): 未另行設定")
    lines.append("")


def _render_cash_flow_cross_checks(lines: List[str], block: Dict[str, Any]) -> None:
    """Cash flow cross-checks, with observed and reverse-solved kept apart."""
    observed = block.get("observed") or {}
    required = block.get("required_at_reference_multiple") or {}

    lines.append(_rule("-"))
    lines.append("現金流交叉驗證 (CASH FLOW CROSS-CHECKS)")
    lines.append(_rule("-"))

    lines.append("已觀察:")
    lines.extend(_table([
        ["P/FCF", _number(observed.get("p_fcf"))],
        ["FCF 殖利率", _signed_percent(observed.get("fcf_yield"))],
        ["EV/EBITDA", _number(observed.get("ev_ebitda"))],
        ["EBITDA / EV", _signed_percent(observed.get("ebitda_yield_on_ev"))],
        ["P/S", _number(observed.get("p_s"))],
        ["營收 / 市值", _signed_percent(observed.get("revenue_yield_on_market_cap"))],
    ], ["指標", "數值"]))
    lines.append("")

    rows: List[List[str]] = []
    for key, label in (("fcf", "隱含 FCF"), ("ebitda", "隱含 EBITDA"), ("revenue", "隱含營收")):
        entry = required.get(key) or {}
        rows.append([
            label,
            _number(entry.get("multiple"), 1),
            _number(entry.get("required_fcf") or entry.get("required_ebitda") or entry.get("required_revenue")),
            _percent(entry.get("gap_vs_observed_fcf") or entry.get("gap_vs_observed_ebitda")
                     or entry.get("gap_vs_observed_revenue")),
        ])
    lines.append("在指定參考倍數下反推:")
    lines.extend(_table(rows, ["項目", "參考倍數", "所需金額", "vs 實際"]))
    lines.append("")


def _render_dcf(lines: List[str], block: Dict[str, Any]) -> None:
    """The discounted cash flow block, including what it could not do."""
    feasibility = block.get("feasibility") or {}
    status = block.get("status", "NOT_ATTEMPTED")

    lines.append(_rule("-"))
    lines.append("折現現金流 (DCF)")
    lines.append(_rule("-"))
    lines.append(f"狀態: {status}")
    lines.append(f"現金流定義: {feasibility.get('cash_flow_basis_status', 'UNDECLARED')}")

    implied = block.get("implied_explicit_growth_rate")
    if implied is not None:
        lines.append(f"隱含顯性期 FCF 成長率: {_signed_percent(implied)}")
    missing = feasibility.get("missing_inputs") or []
    if missing:
        lines.append("缺少欄位: " + ", ".join(missing))
    lines.append("")


def render_report(
    result: Dict[str, Any],
    show_json: bool = False,
) -> str:
    """
    Render an ST-EVA result as a human-readable report.

    No arithmetic is performed here. Every number is quoted from the result.
    """
    lines: List[str] = []

    snapshot = result.get("market_snapshot", {})
    quality = result.get("data_quality", {})
    reference = result.get("reference", {})
    observed = result.get("observed_valuation", {})
    implied = result.get("market_implied_assumptions", {})
    cross = result.get("consensus_cross_check", {})
    metrics = result.get("market_metrics", {})

    ticker = result.get("ticker", "UNKNOWN")
    price = snapshot.get("price")
    currency = snapshot.get("currency", "")

    # ---- header ----
    lines.append(_rule("="))
    lines.append(f"ST-EVA {result.get('version_metadata', {}).get('version', '?')}  |  {ticker}")
    lines.append(f"{result.get('company_name', '')}  ({snapshot.get('exchange', '?')})")
    lines.append(f"價格: {currency} {_number(price)}    資料日期: {result.get('as_of', '?')}")
    lines.append(_rule("="))
    lines.append("")

    # ---- data quality ----
    status = quality.get("discrepancy_status", "UNKNOWN")
    status_label = DISCREPANCY_LABELS.get(status, status)
    lines.append(f"[資料品質] {status} — {status_label}")
    lines.append(f"           來源: {snapshot.get('provider', '?')}  ({snapshot.get('source_type', '?')})")

    errors = quality.get("acquisition_errors") or []
    if errors:
        lines.append(f"           取得錯誤 {len(errors)} 筆:")
        for error in errors:
            lines.append(f"             - {error}")
    else:
        lines.append("           取得錯誤: 無")

    period = quality.get("consensus_forward_eps_period")
    if period:
        lines.append(f"           共識 EPS 期間: {period}")
    lines.append("")

    # ---- reverse requirements matrix ----
    # Placed first because it is the answer the run exists to produce: what
    # the current price demands, given a stated return, horizon and exit
    # multiple.
    lines.extend(_render_reverse_requirements(result.get("reverse_requirements")))

    # ---- observed valuation ----
    lines.append(_rule("-"))
    lines.append("已觀察估值 (OBSERVED)")
    lines.append(_rule("-"))

    observed_rows = [
        ["目前 P/E", _number(observed.get("current_pe"))],
        ["前瞻 P/E", _number(observed.get("forward_pe"))],
        ["共識前瞻 P/E", _number(observed.get("consensus_forward_pe"))],
        ["P/FCF", _number(observed.get("current_pfcf"))],
        ["EV/EBITDA", _number(observed.get("current_ev_ebitda"))],
        ["P/S", _number(observed.get("current_ps"))],
    ]
    lines.extend(_table(observed_rows, ["指標", "數值"]))
    lines.append("")

    # ---- historical bands ----
    lines.append("歷史估值區間 (來源觀測值)")
    band_specs = [
        ("P/E", observed.get("historical_pe_band"), observed.get("approx_historical_pe_percentile")),
        ("P/S", observed.get("historical_ps_band"), observed.get("approx_historical_ps_percentile")),
        ("P/FCF", observed.get("historical_pfcf_band"), None),
        ("EV/EBITDA", observed.get("historical_ev_ebitda_band"), observed.get("approx_historical_ev_ebitda_percentile")),
    ]
    band_rows = []
    for name, band, percentile in band_specs:
        if _is_missing(band) or not band:
            band_rows.append([name, "無資料", "-", "-", "-"])
            continue
        band_state = (reference.get("historical_band_status") or {}).get(
            {"P/E": "pe", "P/S": "ps", "P/FCF": "pfcf", "EV/EBITDA": "ev_ebitda"}[name],
            "UNAVAILABLE",
        )
        band_state_label = BAND_STATUS_LABELS.get(band_state, band_state)
        observations = band.get("observations")
        observations_text = str(observations) if isinstance(observations, (int, float)) else "未宣告"
        percentile_text = (
            f"約 {percentile:.0f} 分位" if isinstance(percentile, (int, float)) else "-"
        )
        band_rows.append([
            name,
            _number(band.get("median")),
            observations_text,
            percentile_text,
            band_state_label,
        ])
    lines.extend(_table(band_rows, ["倍數", "中位數", "觀測數", "目前分位", "可否作參考"]))
    lines.append("")

    prod_pe = result.get("production_historical_pe") or (result.get("reverse_requirements") or {}).get("production_historical_pe")
    if isinstance(prod_pe, dict):
        dist = prod_pe.get("distribution") if isinstance(prod_pe.get("distribution"), dict) else prod_pe
        status = dist.get("status")
        sample_count = dist.get("sample_count", 0)
        p_start = dist.get("period_start")
        p_end = dist.get("period_end")
        min_req = dist.get("min_observations_required", 20)
        percentiles = dist.get("percentiles") or {}
        excluded = dist.get("excluded_observations") or []

        lines.append("生產級點時歷史 P/E 分布 (PRODUCTION PIT HISTORICAL P/E)")
        lines.append(f"狀態: {status} (門檻 >= {min_req} 筆有效觀測值)")
        if sample_count > 0:
            lines.append(f"有效樣本數: {sample_count}   涵蓋期間: {p_start} 至 {p_end}")
            p_rows = []
            for p_key, p_lbl in (
                ("10th", "10th 分位"),
                ("25th", "25th 分位"),
                ("median", "50th 分位 (中位數)"),
                ("75th", "75th 分位"),
                ("90th", "90th 分位"),
            ):
                p_rows.append([p_lbl, _number(percentiles.get(p_key))])
            lines.extend(_table(p_rows, ["分位數", "P/E 倍數"]))
            lines.append(f"排除樣本: {len(excluded)} 筆")
        else:
            lines.append(f"無有效樣本: {dist.get('reason_detail') or dist.get('reason_code') or '無資料'}")
        lines.append("")

    # ---- reference ----
    lines.append(_rule("-"))
    lines.append("參考倍數 (REFERENCE)")
    lines.append(_rule("-"))

    method = reference.get("method", "none")
    multiple = reference.get("multiple")
    lines.append(f"選用方式: {method} — {METHOD_LABELS.get(method, method)}")
    if _is_missing(multiple):
        lines.append("選用倍數: N/A")
    else:
        lines.append(f"選用倍數: {_number(multiple)}x")
    minimum = reference.get("min_observations_for_reference")
    if minimum is not None:
        lines.append(
            f"採用門檻: 歷史區間需 >= {int(minimum)} 個觀測值方可作為參考"
        )

    insufficient = [
        name for name, state in (reference.get("historical_band_status") or {}).items()
        if state == "DESCRIPTIVE_ONLY_INSUFFICIENT_OBSERVATIONS"
    ]
    if insufficient:
        lines.append("")
        lines.append("注意: 以下歷史區間因觀測數不足未被採用為參考")
        for name in insufficient:
            lines.append(f"      - {name}")
        lines.append("      若需隱含數值，請以 --reference-multiple 明確指定。")
    lines.append("")

    # ---- implied assumptions ----
    lines.append(_rule("-"))
    lines.append("市場隱含假設 (CONDITIONAL INFERENCE)")
    lines.append(_rule("-"))

    if _is_missing(multiple):
        lines.append("無參考倍數，故不產生隱含數值。")
        lines.append("指定 --reference-multiple 後即可計算。")
    else:
        multiples = implied.get("reference_multiples") or {}
        implied_rows = [
            ["隱含前瞻 EPS", _number(implied.get("forward_eps_at_reference_multiple"), 4),
             f"價格 / {_number(multiple)}x"],
            ["EPS 缺口 (vs 共識)", _percent(implied.get("eps_gap_vs_consensus")),
             "正值 = 高於共識"],
            ["所需 EPS CAGR", _percent(implied.get("required_eps_cagr_from_current_eps")),
             "自目前 EPS 起算"],
            ["隱含 FCF", _number(implied.get("fcf_at_reference_multiple")),
             _basis_label("P/FCF", multiples.get("pfcf"))],
            ["隱含 EBITDA", _number(implied.get("ebitda_at_reference_multiple")),
             _basis_label("EV/EBITDA", multiples.get("ev_ebitda"))],
            ["隱含營收", _number(implied.get("revenue_at_reference_multiple")),
             _basis_label("P/S", multiples.get("ps"))],
            ["隱含淨利率", _signed_percent(implied.get("implied_net_margin")),
             "P/S + P/E 聯合推得"],
        ]
        lines.extend(_table(implied_rows, ["項目", "數值", "說明"]))
    lines.append("")

    # ---- consensus cross check ----
    lines.append(_rule("-"))
    lines.append("共識交叉檢核 (CROSS-CHECK)")
    lines.append(_rule("-"))

    cross_rows = [
        ["共識前瞻 EPS", _number(cross.get("consensus_forward_eps"), 4)],
        ["以中位數倍數計之價格", _number(cross.get("price_at_historical_median_pe"))],
        ["該價格 vs 現價", _percent(cross.get("price_gap_vs_historical_median_on_consensus_eps"))],
    ]
    lines.extend(_table(cross_rows, ["項目", "數值"]))
    lines.append("")

    # ---- market metrics ----
    lines.append(_rule("-"))
    lines.append("價格動能 (DERIVED)")
    lines.append(_rule("-"))

    metric_rows = [
        ["1 日報酬", _percent(metrics.get("return_1d"), 2)],
        ["5 日報酬", _percent(metrics.get("return_5d"), 2)],
        ["20 日報酬", _percent(metrics.get("return_20d"), 2)],
        ["60 日報酬", _percent(metrics.get("return_60d"), 2)],
        ["年化實現波動", _signed_percent(metrics.get("realized_volatility_annualized"))],
        ["平均成交量", _number(metrics.get("average_volume"))],
        ["最新量 vs 均量", _percent(metrics.get("latest_volume_vs_average"), 1)],
    ]
    lines.extend(_table(metric_rows, ["指標", "數值"]))
    lines.append("")

    # ---- evidence ----
    evidence_ids = result.get("evidence_ids") or []
    lines.append(f"證據 IDs ({len(evidence_ids)}): {', '.join(evidence_ids[:6])}")
    if len(evidence_ids) > 6:
        lines.append(f"  ... 另有 {len(evidence_ids) - 6} 筆 (見 --json)")
    lines.append("")

    # ---- missing data ----
    missing = result.get("missing_data") or []
    lines.append(_rule("-"))
    lines.append("缺漏資料 (UNAVAILABLE)")
    lines.append(_rule("-"))
    if missing:
        for name in missing:
            lines.append(f"  - {name}")
    else:
        lines.append("  無")
    lines.append("")

    # ---- limitations ----
    lines.append(_rule("-"))
    lines.append("限制說明")
    lines.append(_rule("-"))
    for limitation in result.get("limitations", []):
        lines.append(f"  - {limitation}")
    lines.append("")
    lines.append(
        "以上為描述性估值分析，非投資建議。所有隱含數值皆為條件式推論。"
    )
    lines.append(_rule("="))

    if show_json:
        lines.append("")
        lines.append(json.dumps(result, ensure_ascii=False, indent=2))

    return "\n".join(lines)


def print_report(
    result: Dict[str, Any],
    stream: Any = None,
    show_json: bool = False,
) -> None:
    """
    Write a human-readable ST-EVA report to a stream.

    Falls back to UTF-8 on terminals that cannot encode the report directly,
    which is common on Windows consoles using a legacy code page.
    """
    text = render_report(result, show_json=show_json)
    target = stream if stream is not None else sys.stdout
    try:
        target.write(text + "\n")
    except UnicodeEncodeError:
        buffer = getattr(target, "buffer", None)
        if buffer is not None:
            buffer.write(text.encode("utf-8", errors="replace") + b"\n")
            buffer.flush()
            return
        raise
    try:
        target.flush()
    except Exception:
        pass


def resolve_console_encoding() -> None:
    """
    Make stdout tolerant of CJK output on legacy Windows code pages.
    """
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def normalize_ticker(query: str) -> str:
    """
    Resolve a loose company reference to a ticker Yahoo understands.

    Only unambiguous well-known mappings are handled. Everything else is
    returned upper-cased so unknown input fails loudly rather than being
    silently mapped to a different company.
    """
    key = query.strip().upper()
    return ALIASES.get(key, key)


ALIASES: Dict[str, str] = {
    "AAPL": "AAPL",
    "APPLE": "AAPL",
    "MSFT": "MSFT",
    "MICROSOFT": "MSFT",
    "GOOG": "GOOG",
    "GOOGLE": "GOOG",
    "AMZN": "AMZN",
    "AMAZON": "AMZN",
    "META": "META",
    "FACEBOOK": "META",
    "NVDA": "NVDA",
    "NVIDIA": "NVDA",
    "TSLA": "TSLA",
    "TESLA": "TSLA",
    "TSM": "TSM",
    "NU": "NU",
    "TENCENT": "0700.HK",
    "騰訊": "0700.HK",
    "腾讯": "0700.HK",
    "TENCENT HOLDINGS": "0700.HK",
    "0700.HK": "0700.HK",
    "TAT-QA": "TAT-QA",
    "2308": "2308.TW",
    "聯電": "2308.TW",
    "联电": "2308.TW",
    "台積電": "2330.TW",
    "台积电": "2330.TW",
    "TSMC": "2330.TW",
    "SMIC": "0981.HK",
    "WTC": "WTC.AX",
}
