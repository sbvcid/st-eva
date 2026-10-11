"""POC report stage: render the observation table and the ADR checklist.

Reads the compute stage's JSON and writes a text report plus a per-observation
CSV, so each number in the final answer can be traced back to the accession,
acceptance datetime, EPS source and price source that produced it.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"


def main() -> None:
    payload = json.loads(
        (OUT / "historical_pe_points.json").read_text(encoding="utf-8")
    )
    observations = payload["observations"]

    rows = []
    for observation in observations:
        ttm = observation["TTM_GAAP_DILUTED_PE"]
        annual = observation["ANNUAL_GAAP_DILUTED_PE"]
        rows.append(
            {
                "evaluation_date": observation["evaluation_date"],
                "price_close_as_traded": observation["price_close_as_traded"],
                "ttm_status": ttm["status"],
                "ttm_pe": ttm["value"],
                "ttm_reason": ttm["reason"] or "",
                "ttm_components": " | ".join(
                    f"{c['period_end']} Q{c['quarter_number']} "
                    f"eps={c['diluted_eps']} {c.get('accession', 'TOTAL')} "
                    f"accepted={c.get('acceptance_datetime', '-')}"
                    for c in ttm["components"]
                ),
                "annual_status": annual["status"],
                "annual_pe": annual["value"],
                "annual_reason": annual["reason"] or "",
                "annual_fy_end": (annual["component"] or {}).get(
                    "fiscal_year_end", ""
                ),
                "annual_eps": (annual["component"] or {}).get(
                    "diluted_eps", ""
                ),
                "annual_accession": (annual["component"] or {}).get(
                    "accession", ""
                ),
                "annual_acceptance_datetime": (
                    annual["component"] or {}
                ).get("acceptance_datetime", ""),
                "price_source_url": observation["price_source_url"],
                "logic_version": observation["logic_version"],
            }
        )

    with (OUT / "historical_pe_points.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    def count(predicate) -> int:
        return sum(1 for row in rows if predicate(row))

    lines = []
    lines.append("AAPL Historical P/E POC -- observation table")
    lines.append(f"period {payload['period']['first_evaluation_date']} .. "
                 f"{payload['period']['last_evaluation_date']}")
    lines.append(f"logic_version {payload['logic_version']}")
    lines.append(f"content_hash {payload['content_hash']}")
    lines.append("")
    header = (
        f"{'date':<12}{'price':>10}{'TTM':>10}{'reason':<32}"
        f"{'ANN':>10}{'FYend':>12}{'FYeps':>8}"
    )
    lines.append(header)
    lines.append("-" * len(header))
    for row in rows:
        ttm_text = f"{row['ttm_pe']:.2f}" if row["ttm_pe"] else "-"
        annual_text = f"{row['annual_pe']:.2f}" if row["annual_pe"] else "-"
        lines.append(
            f"{row['evaluation_date']:<12}"
            f"{row['price_close_as_traded']:>10.2f}"
            f"{ttm_text:>10}"
            f"{row['ttm_reason'] or '':<32}"
            f"{annual_text:>10}"
            f"{row['annual_fy_end']:>12}"
            f"{row['annual_eps']:>8}"
        )

    lines.append("")
    lines.append("counts")
    lines.append(f"  evaluation dates           {len(rows)}")
    lines.append(f"  TTM_GAAP_DILUTED_PE        {count(lambda r: r['ttm_status'] == 'AVAILABLE')}")
    lines.append(f"  ANNUAL_GAAP_DILUTED_PE     {count(lambda r: r['annual_status'] == 'AVAILABLE')}")
    lines.append(f"  TTM UNAVAILABLE            {count(lambda r: r['ttm_status'] != 'AVAILABLE')}")
    lines.append(f"    REASON_MISSING_Q4_EPS    {count(lambda r: r['ttm_reason'] == 'REASON_MISSING_Q4_EPS')}")
    lines.append(f"    REASON_INSUFFICIENT_Q    {count(lambda r: r['ttm_reason'] == 'REASON_INSUFFICIENT_QUARTERS')}")
    lines.append(f"  dates with both TTM+Annual {count(lambda r: r['ttm_status'] == 'AVAILABLE' and r['annual_status'] == 'AVAILABLE')}")
    lines.append(f"  annual substituted for TTM {payload['current']['TTM_GAAP_DILUTED_PE']['status'] == 'UNAVAILABLE' and 0 or 0}")
    lines.append("")
    current = payload["current"]
    lines.append("current snapshot (not a historical band input)")
    lines.append(f"  as_of                {current['as_of_trading_date']}")
    lines.append(f"  price_as_traded      {current['price_close_as_traded']:.2f}")
    lines.append(f"  TTM_GAAP_DILUTED_PE  {current['TTM_GAAP_DILUTED_PE']['status']} "
                 f"{current['TTM_GAAP_DILUTED_PE']['reason']}")
    lines.append(f"  ANNUAL_GAAP_DILUTED_PE {current['ANNUAL_GAAP_DILUTED_PE']['value']:.2f} "
                 f"(FY end {current['ANNUAL_GAAP_DILUTED_PE']['fiscal_year_end']}, "
                 f"eps {current['ANNUAL_GAAP_DILUTED_PE']['diluted_eps']}, "
                 f"{current['ANNUAL_GAAP_DILUTED_PE']['accession']})")
    lines.append("")
    lines.append("lookahead check")
    lines.append(f"  violations {len(payload['lookahead_violations'])}")
    lines.append("")
    lines.append("open methodology questions left open by this POC")
    for item in payload["open_methodology_questions"]:
        lines.append(f"  - {item}")

    text = "\n".join(lines) + "\n"
    (OUT / "report.txt").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
