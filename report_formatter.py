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
