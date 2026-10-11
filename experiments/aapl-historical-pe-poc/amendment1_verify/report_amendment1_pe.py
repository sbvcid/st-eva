"""Amendment 1 verification, stage 3: prior-vs-current comparison report."""

from __future__ import annotations

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"

REQUIRED_DATES = [
    "2021-10-29",
    "2022-01-28",
    "2022-10-28",
    "2023-11-03",
    "2024-11-01",
    "2025-10-31",
]


def main() -> None:
    current = json.loads(
        (OUT / "amendment1_pe_points.json").read_text(encoding="utf-8")
    )
    negative = json.loads(
        (OUT / "negative_path_no_furnished.json").read_text(encoding="utf-8")
    )
    prior = json.loads(
        (HERE.parent / "out" / "historical_pe_points.json").read_text(
            encoding="utf-8"
        )
    )

    def tally(payload: dict) -> dict:
        observations = payload["observations"]
        ttm_available = sum(
            1
            for o in observations
            if o["TTM_GAAP_DILUTED_PE"]["status"] == "AVAILABLE"
        )
        reasons: dict[str, int] = {}
        for observation in observations:
            reason = observation["TTM_GAAP_DILUTED_PE"]["reason"]
            if reason:
                reasons[reason] = reasons.get(reason, 0) + 1
        return {
            "evaluation_dates": len(observations),
            "ttm_available": ttm_available,
            "ttm_unavailable": len(observations) - ttm_available,
            "reasons": reasons,
            "annual_available": sum(
                1
                for o in observations
                if o["ANNUAL_GAAP_DILUTED_PE"]["status"] == "AVAILABLE"
            ),
            "current_ttm": payload["current"]["TTM_GAAP_DILUTED_PE"]["status"],
            "current_ttm_reason": payload["current"]["TTM_GAAP_DILUTED_PE"][
                "reason"
            ],
            "current_ttm_value": payload["current"]["TTM_GAAP_DILUTED_PE"].get(
                "value"
            ),
            "current_annual": payload["current"]["ANNUAL_GAAP_DILUTED_PE"][
                "status"
            ],
        }

    prior_tally = tally(prior)
    negative_tally = tally(negative)
    current_tally = tally(current)

    lines = []
    lines.append("Amendment 1 verification -- prior vs current")
    lines.append("=" * 92)
    lines.append(
        f"prior POC hash      {prior['content_hash']}"
    )
    lines.append(
        f"negative path hash  {negative['content_hash']}  "
        f"(furnished evidence disabled)"
    )
    lines.append(
        f"current hash        {current['content_hash']}  "
        f"(furnished evidence admitted)"
    )
    lines.append("")
    header = (
        f"{'metric':<34}{'prior POC':>16}{'furnished OFF':>16}"
        f"{'furnished ON':>16}"
    )
    lines.append(header)
    lines.append("-" * len(header))
    rows = [
        ("evaluation dates", "evaluation_dates"),
        ("TTM AVAILABLE", "ttm_available"),
        ("TTM UNAVAILABLE", "ttm_unavailable"),
        ("REASON_MISSING_Q4_EPS", "reasons"),
        ("ANNUAL AVAILABLE", "annual_available"),
        ("CURRENT TTM", "current_ttm"),
    ]
    for label, key in rows:
        left = prior_tally[key]
        mid = negative_tally[key]
        right = current_tally[key]
        if isinstance(left, dict):
            left = left.get("REASON_MISSING_Q4_EPS", 0)
            mid = mid.get("REASON_MISSING_Q4_EPS", 0)
            right = right.get("REASON_MISSING_Q4_EPS", 0)
        lines.append(f"{label:<34}{str(left):>16}{str(mid):>16}{str(right):>16}")
    lines.append(
        f"{'CURRENT ANNUAL':<34}{prior_tally['current_annual']:>16}"
        f"{negative_tally['current_annual']:>16}"
        f"{current_tally['current_annual']:>16}"
    )
    lines.append("")

    lines.append("Per-date comparison")
    lines.append("-" * 92)
    header = (
        f"{'date':<12}{'prior':>10}{'prior reason':>30}"
        f"{'now':>10}{'now reason':>16}{'Q4 src':>10}"
    )
    lines.append(header)
    lines.append("-" * len(header))
    prior_by_date = {o["evaluation_date"]: o for o in prior["observations"]}
    current_by_date = {
        o["evaluation_date"]: o for o in current["observations"]
    }
    for day in current["evaluation_dates"]:
        before = prior_by_date.get(day)
        now = current_by_date[day]
        ttm = now["TTM_GAAP_DILUTED_PE"]
        before_text = "-"
        before_reason = "absent from prior POC"
        if before:
            b = before["TTM_GAAP_DILUTED_PE"]
            before_text = (
                f"{b['value']:.2f}"
                if b["status"] == "AVAILABLE" and b["value"] is not None
                else "UNAVAIL"
            )
            before_reason = b["reason"] or ""
        now_text = (
            f"{ttm['value']:.2f}"
            if ttm["status"] == "AVAILABLE" and ttm["value"] is not None
            else "UNAVAIL"
        )
        furnished = [
            c
            for c in ttm["components"]
            if c.get("evidence_class") == "furnished"
        ]
        q4_source = (
            f"8-K {furnished[0]['accession'][-9:]}" if furnished else "10-Q/10-K"
        )
        lines.append(
            f"{day:<12}{before_text:>10}{before_reason:>30}"
            f"{now_text:>10}{str(ttm['reason'] or ''):>16}{q4_source:>10}"
        )
    lines.append("")

    lines.append("Required dates, verified explicitly")
    lines.append("-" * 92)
    for day in REQUIRED_DATES:
        observation = current_by_date[day]
        ttm = observation["TTM_GAAP_DILUTED_PE"]
        lines.append(f"{day}")
        lines.append(
            f"  TTM {ttm['status']} = {ttm['value']:.4f}"
            if ttm["value"] is not None
            else f"  TTM {ttm['status']} ({ttm['reason']})"
        )
        lines.append(
            f"  price as-traded {observation['price_close_as_traded']:.2f}"
        )
        for component in ttm["components"]:
            if not component.get("period_end"):
                lines.append(
                    f"  = TTM denominator {component['diluted_eps']:.4f}"
                )
                continue
            lines.append(
                f"  {component['period_end']} Q{component['fiscal_quarter']}"
                f"  eps={component['diluted_eps']:<6}"
                f" {component['evidence_class']:<9}"
                f" {component['form']:<5}"
                f" {component['accession']}"
            )
            lines.append(
                f"       accepted={component['acceptance_datetime']}"
                f"  usable={component['usable_date']}"
                f"  {component['audit_status']}"
            )
            lines.append(
                f"       doc={component['source_document']}"
                f"  sha256={component['content_sha256'][:24]}..."
            )
        lines.append("")

    text = "\n".join(lines) + "\n"
    (OUT / "prior_vs_current.txt").write_text(text, encoding="utf-8")
    print(text)

    with (OUT / "prior_vs_current.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "evaluation_date",
                "prior_status",
                "prior_value",
                "prior_reason",
                "current_status",
                "current_value",
                "current_reason",
                "q4_evidence_class",
                "q4_form",
                "q4_accession",
                "q4_acceptance_datetime",
                "q4_usable_date",
                "q4_audit_status",
                "ttm_denominator",
            ]
        )
        for day in current["evaluation_dates"]:
            now = current_by_date[day]
            before = prior_by_date.get(day, {})
            ttm = now["TTM_GAAP_DILUTED_PE"]
            b = before.get("TTM_GAAP_DILUTED_PE", {})
            furnished = [
                c
                for c in ttm["components"]
                if c.get("evidence_class") == "furnished"
            ]
            q4 = furnished[0] if furnished else {}
            denominator = next(
                (
                    c["diluted_eps"]
                    for c in ttm["components"]
                    if not c.get("period_end")
                ),
                None,
            )
            writer.writerow(
                [
                    day,
                    b.get("status", ""),
                    b.get("value"),
                    b.get("reason") or "",
                    ttm["status"],
                    ttm["value"],
                    ttm["reason"] or "",
                    q4.get("evidence_class", ""),
                    q4.get("form", ""),
                    q4.get("accession", ""),
                    q4.get("acceptance_datetime", ""),
                    q4.get("usable_date", ""),
                    q4.get("audit_status", ""),
                    denominator,
                ]
            )


if __name__ == "__main__":
    main()
