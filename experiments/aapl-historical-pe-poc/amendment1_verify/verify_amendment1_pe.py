"""Amendment 1 verification, stage 2: independent conformance and audit.

Checks that admitting the furnished evidence class did what Amendment 1 says
it does, and nothing else. Every check re-derives from the emitted JSON or the
frozen raw bytes rather than reusing the compute stage's own conclusions.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
POC_RAW = HERE.parent / "raw"
Q4_RAW = HERE.parent / "q4_study" / "raw"
OUT = HERE / "out"
ET = ZoneInfo("America/New_York")
CUTOFF_ET = datetime.time(16, 0)

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    CHECKS.append((name, ok, detail))


def main() -> None:
    enabled = json.loads(
        (OUT / "amendment1_pe_points.json").read_text(encoding="utf-8")
    )
    disabled = json.loads(
        (OUT / "negative_path_no_furnished.json").read_text(encoding="utf-8")
    )
    prior = json.loads(
        (HERE.parent / "out" / "historical_pe_points.json").read_text(
            encoding="utf-8"
        )
    )
    observations = enabled["observations"]

    # 1. Lookahead. Every component, in every point and in the current
    #    snapshot, must have a usable date at or before its evaluation date,
    #    and that usable date must follow from its own acceptance timestamp
    #    under the 16:00 ET rule.
    lookahead = []
    for observation in observations:
        day = observation["evaluation_date"]
        for component in observation["TTM_GAAP_DILUTED_PE"]["components"]:
            if not component.get("usable_date"):
                continue
            if component["usable_date"] > day:
                lookahead.append(
                    (day, component["accession"], "usable_after_t")
                )
            accepted = datetime.datetime.fromisoformat(
                component["acceptance_datetime"]
            )
            if accepted.tzinfo is None:
                lookahead.append((day, component["accession"], "naive_timestamp"))
                continue
            earliest = (
                accepted.date()
                if accepted.time() < CUTOFF_ET
                else accepted.date() + datetime.timedelta(days=1)
            )
            if datetime.date.fromisoformat(component["usable_date"]) < earliest:
                lookahead.append((day, component["accession"], "early_usable"))
        annual = observation["ANNUAL_GAAP_DILUTED_PE"]["component"]
        if annual and annual["usable_date"] > day:
            lookahead.append((day, annual["accession"], "annual_after_t"))
    for component in enabled["current"]["TTM_GAAP_DILUTED_PE"]["components"]:
        if component["usable_date"] > enabled["current"]["as_of_trading_date"]:
            lookahead.append(("current", component["accession"], "after_run"))
    check(
        "no component post-dates its evaluation date, and every usable date "
        "follows from its own acceptance timestamp",
        not lookahead,
        f"violations={lookahead[:5]}",
    )

    # 2. Every TTM component carries the full provenance Amendment 1 requires,
    #    including the evidence class and audit status distinctions.
    required = (
        "period_end",
        "fiscal_quarter",
        "diluted_eps",
        "evidence_class",
        "form",
        "accession",
        "acceptance_datetime",
        "usable_date",
        "audit_status",
        "source_url",
        "content_sha256",
        "stated_directly",
        "lookahead_ok",
    )
    incomplete = []
    for observation in observations:
        for component in observation["TTM_GAAP_DILUTED_PE"]["components"]:
            if component.get("period_end") is None:
                continue
            for field in required:
                if component.get(field) in (None, ""):
                    incomplete.append(
                        (observation["evaluation_date"], component["accession"], field)
                    )
    check(
        "every TTM component carries evidence_class, form, accession, "
        "acceptance_datetime, usable_date, audit status, URL and content hash",
        not incomplete,
        f"missing={incomplete[:5]}",
    )

    # 3. Semantic separation. A furnished component must never be labelled
    #    filed, and an unaudited one must never be labelled audited.
    mislabelled = []
    for observation in observations:
        for component in observation["TTM_GAAP_DILUTED_PE"]["components"]:
            if component.get("period_end") is None:
                continue
            if component["evidence_class"] == "furnished":
                if component["form"] == "10-K" or component["form"] == "10-Q":
                    mislabelled.append(
                        (observation["evaluation_date"], "furnished_as_periodic")
                    )
                if component["audit_status"] == "audited":
                    mislabelled.append(
                        (observation["evaluation_date"], "furnished_as_audited")
                    )
                if component.get("stated_directly") is not True:
                    mislabelled.append(
                        (observation["evaluation_date"], "furnished_not_direct")
                    )
            if component["evidence_class"] == "filed" and component["form"] == "8-K":
                mislabelled.append(
                    (observation["evaluation_date"], "8k_labelled_filed")
                )
    check(
        "furnished components are never labelled filed, 10-K, 10-Q or audited",
        not mislabelled,
        f"violations={mislabelled[:5]}",
    )

    # 4. Audit status must be the three-valued field, not a boolean.
    statuses = {
        component["audit_status"]
        for observation in observations
        for component in observation["TTM_GAAP_DILUTED_PE"]["components"]
        if component.get("period_end")
    }
    check(
        "audit status is three-valued (audited / unaudited_reviewed / unaudited)",
        statuses == {"audited", "unaudited_reviewed", "unaudited"},
        f"observed={sorted(statuses)}",
    )

    # 5. Evidence mixing actually occurred: at least one point must combine
    #    three filed quarters with one furnished quarter.
    mixed = [
        observation["evaluation_date"]
        for observation in observations
        if _mix(observation) == "filed_x3_furnished_x1"
    ]
    check(
        "the filed x3 + furnished x1 combination occurs and is disclosed",
        len(mixed) >= 5,
        f"n={len(mixed)} dates e.g. {mixed[:6]}",
    )

    # 6. Window integrity. Every available TTM must be four consecutive fiscal
    #    quarters, numbered 1-4 in order, with a Q4 present.
    window_bad = []
    for observation in observations:
        ttm = observation["TTM_GAAP_DILUTED_PE"]
        if ttm["status"] != "AVAILABLE":
            continue
        quarters = [
            c for c in ttm["components"] if c.get("period_end")
        ]
        numbers = [c["fiscal_quarter"] for c in quarters]
        if len(quarters) != 4:
            window_bad.append((observation["evaluation_date"], "not_four"))
        if 4 not in numbers:
            window_bad.append((observation["evaluation_date"], "no_q4"))
        if numbers != [(numbers[0] + i - 1) % 4 + 1 for i in range(4)]:
            window_bad.append((observation["evaluation_date"], "not_consecutive"))
        ends = [datetime.date.fromisoformat(c["period_end"]) for c in quarters]
        if any(
            (ends[i] - ends[i - 1]).days > 120 for i in range(1, len(ends))
        ):
            window_bad.append((observation["evaluation_date"], "gap"))
    check(
        "every available TTM is four consecutive fiscal quarters containing a Q4",
        not window_bad,
        f"violations={window_bad[:5]}",
    )

    # 7. No three-quarter truncation. A TTM must never be published from fewer
    #    than four quarters, which is the failure mode the missing Q4 would
    #    otherwise invite.
    truncated = [
        observation["evaluation_date"]
        for observation in observations
        if observation["TTM_GAAP_DILUTED_PE"]["status"] == "AVAILABLE"
        and len(
            [
                c
                for c in observation["TTM_GAAP_DILUTED_PE"]["components"]
                if c.get("period_end")
            ]
        )
        != 4
    ]
    check(
        "no TTM was published from fewer than four quarters",
        not truncated,
        f"violations={truncated}",
    )

    # 8. No FY minus YTD anywhere in either path.
    arithmetic = []
    for label, payload in (("on", enabled), ("off", disabled)):
        for observation in payload["observations"]:
            if observation["TTM_GAAP_DILUTED_PE"].get("fy_minus_ytd_used"):
                arithmetic.append((label, observation["evaluation_date"]))
        for component in observation["TTM_GAAP_DILUTED_PE"]["components"]:
            if component.get("fy_minus_ytd_used"):
                arithmetic.append((label, component.get("period_end")))
        if payload["current"]["TTM_GAAP_DILUTED_PE"].get("fy_minus_ytd_used"):
            arithmetic.append((label, "current"))
    check(
        "neither path performs FY minus YTD",
        not arithmetic,
        f"violations={arithmetic[:5]}",
    )

    # 9. No accepted quarterly figure equals the annual figure in the same
    #    fiscal year, which would mean the annual number had been smuggled in
    #    as a quarter.
    annual_spoof = []
    for observation in observations:
        annual = observation["ANNUAL_GAAP_DILUTED_PE"]["component"]
        if not annual:
            continue
        fye = datetime.date.fromisoformat(annual["fiscal_year_end"])
        for component in observation["TTM_GAAP_DILUTED_PE"]["components"]:
            if not component.get("period_end"):
                continue
            end = datetime.date.fromisoformat(component["period_end"])
            if end.year == fye.year and component["diluted_eps"] == annual[
                "diluted_eps"
            ]:
                annual_spoof.append(
                    (observation["evaluation_date"], component["period_end"])
                )
    check(
        "no quarterly component equals its fiscal-year diluted EPS",
        not annual_spoof,
        f"violations={annual_spoof[:5]}",
    )

    # 10. Annual semantics unchanged: annual is never presented as TTM, and
    #     every annual figure comes from a 10-K audited statement only.
    annual_leak = []
    for observation in observations:
        ttm = observation["TTM_GAAP_DILUTED_PE"]
        annual = observation["ANNUAL_GAAP_DILUTED_PE"]
        if annual.get("substituted_for_ttm"):
            annual_leak.append((observation["evaluation_date"], "substituted"))
        component = annual.get("component")
        if component:
            if component["evidence_class"] != "filed":
                annual_leak.append(
                    (observation["evaluation_date"], "annual_not_filed")
                )
            if component["form"] != "10-K":
                annual_leak.append(
                    (observation["evaluation_date"], "annual_not_10k")
                )
            if component["audit_status"] != "audited":
                annual_leak.append(
                    (observation["evaluation_date"], "annual_not_audited")
                )
        if ttm["status"] == "UNAVAILABLE" and ttm["value"] is not None:
            annual_leak.append(
                (observation["evaluation_date"], "unavailable_with_value")
            )
    check(
        "ANNUAL semantics unchanged: 10-K audited only, never substituted for TTM",
        not annual_leak,
        f"violations={annual_leak[:5]}",
    )

    # 11. Reason codes stay inside the ADR's closed enumeration.
    allowed = {
        "REASON_MISSING_PRICE",
        "REASON_MISSING_Q4_EPS",
        "REASON_INSUFFICIENT_QUARTERS",
        "REASON_NON_POSITIVE_EPS",
        "REASON_INSUFFICIENT_OBSERVATIONS",
        "REASON_INSUFFICIENT_TIME_SPAN",
        "REASON_CORPORATE_ACTION_UNRESOLVED",
    }
    bad_codes = []
    for label, payload in (("on", enabled), ("off", disabled)):
        for observation in payload["observations"]:
            for block in ("TTM_GAAP_DILUTED_PE", "ANNUAL_GAAP_DILUTED_PE"):
                reason = observation[block]["reason"]
                if reason is not None and reason not in allowed:
                    bad_codes.append(
                        (label, observation["evaluation_date"], reason)
                    )
    check(
        "all reason codes are inside the closed enumeration",
        not bad_codes,
        f"violations={bad_codes[:5]}",
    )

    # 12. The six dates the study must confirm explicitly.
    required_dates = [
        "2021-10-29",
        "2022-01-28",
        "2022-10-28",
        "2023-11-03",
        "2024-11-01",
        "2025-10-31",
    ]
    by_date = {o["evaluation_date"]: o for o in observations}
    date_report = {}
    date_failures = []
    for day in required_dates:
        observation = by_date.get(day)
        if observation is None:
            date_failures.append((day, "not_an_evaluation_date"))
            continue
        ttm = observation["TTM_GAAP_DILUTED_PE"]
        furnished = [
            c
            for c in ttm["components"]
            if c.get("evidence_class") == "furnished"
        ]
        date_report[day] = {
            "status": ttm["status"],
            "value": ttm["value"],
            "reason": ttm["reason"],
            "furnished_components": len(furnished),
            "furnished_unaudited": all(
                c["audit_status"] == "unaudited" for c in furnished
            ),
        }
        if ttm["status"] != "AVAILABLE":
            date_failures.append((day, ttm["reason"]))
        if not furnished:
            date_failures.append((day, "no_furnished_q4_used"))
    check(
        "the six required dates each build a legal TTM from a furnished Q4",
        not date_failures,
        f"failures={date_failures}; detail={date_report}",
    )

    # 13. Decision 13: AAPL FY2021-2025 Q4 must not report MISSING_Q4_EPS.
    banned = [
        observation["evaluation_date"]
        for observation in observations
        if observation["TTM_GAAP_DILUTED_PE"]["reason"]
        == "REASON_MISSING_Q4_EPS"
    ]
    check(
        "no AAPL FY2021-2025 date reports REASON_MISSING_Q4_EPS",
        not banned,
        f"hits={banned}",
    )

    # 14. Negative path reproduces the prior POC exactly, per date. This is
    #     what shows the change came from the evidence path alone.
    prior_by_date = {o["evaluation_date"]: o for o in prior["observations"]}
    drift = []
    for observation in disabled["observations"]:
        day = observation["evaluation_date"]
        before = prior_by_date.get(day)
        if before is None:
            drift.append((day, "absent_in_prior"))
            continue
        a = before["TTM_GAAP_DILUTED_PE"]
        b = observation["TTM_GAAP_DILUTED_PE"]
        if a["status"] != b["status"] or a["reason"] != b["reason"]:
            drift.append((day, a["status"], b["status"], a["reason"], b["reason"]))
            continue
        av, bv = a["value"], b["value"]
        if (av is None) != (bv is None):
            drift.append((day, "value_presence"))
        elif av is not None and abs(av - bv) > 1e-9:
            drift.append((day, av, bv))
    check(
        "with furnished evidence disabled, every point matches the prior POC "
        "exactly, so the unblocking comes from the evidence path alone",
        not drift and len(drift) == 0,
        f"drift={drift[:5]} over {len(disabled['observations'])} dates",
    )

    # 15. Negative path really does regress, and specifically on Q4.
    off_missing_q4 = sum(
        1
        for observation in disabled["observations"]
        if observation["TTM_GAAP_DILUTED_PE"]["reason"]
        == "REASON_MISSING_Q4_EPS"
    )
    off_available = sum(
        1
        for observation in disabled["observations"]
        if observation["TTM_GAAP_DILUTED_PE"]["status"] == "AVAILABLE"
    )
    on_available = sum(
        1
        for observation in observations
        if observation["TTM_GAAP_DILUTED_PE"]["status"] == "AVAILABLE"
    )
    check(
        "disabling furnished evidence restores the pre-Amendment-1 shortfall",
        off_missing_q4 == 19 and off_available == 12 and on_available == 31,
        f"off: available={off_available} missing_q4={off_missing_q4}; "
        f"on: available={on_available}",
    )

    # 16. Independent third computation of the TTM denominators, re-extracting
    #     the furnished figures straight from the exhibit bytes.
    independent = _third_path(enabled)
    mismatches = []
    for observation in observations:
        ttm = observation["TTM_GAAP_DILUTED_PE"]
        if ttm["status"] != "AVAILABLE":
            continue
        recorded = next(
            c["diluted_eps"]
            for c in ttm["components"]
            if c.get("period_end") is None
        )
        recomputed = independent.get(observation["evaluation_date"])
        if recomputed is None:
            mismatches.append(
                (observation["evaluation_date"], "no_independent_value")
            )
        elif abs(recomputed - recorded) > 1e-9:
            mismatches.append(
                (observation["evaluation_date"], recomputed, recorded)
            )
    check(
        "a third independent path reproduces every TTM denominator from raw bytes",
        not mismatches,
        f"mismatches={mismatches[:5]}",
    )

    # 17. Replay determinism across two process runs.
    hashes = []
    for _ in range(2):
        subprocess.run(
            [sys.executable, "compute_amendment1_pe.py"],
            cwd=HERE,
            check=True,
            capture_output=True,
        )
        hashes.append(
            json.loads(
                (OUT / "amendment1_pe_points.json").read_text(encoding="utf-8")
            )["content_hash"]
        )
    check(
        "two runs over the same frozen inputs produce an identical content hash",
        hashes[0] == hashes[1] == enabled["content_hash"],
        f"run1={hashes[0][:16]} run2={hashes[1][:16]} recorded={enabled['content_hash'][:16]}",
    )

    # 18. Raw inputs still hash to what the earlier studies recorded, so the
    #     comparison is against the same bytes, not a refetch.
    drift = []
    manifest = json.loads(
        (POC_RAW / "manifest.json").read_text(encoding="utf-8")
    )
    for name, entry in manifest.items():
        digest = hashlib.sha256(
            (POC_RAW / f"{name}.json").read_bytes()
        ).hexdigest()
        if digest != entry["sha256"]:
            drift.append(name)
    study = json.loads(
        (Q4_RAW / "source_manifest.json").read_text(encoding="utf-8")
    )
    for key, entry in study.items():
        if "sha256" not in entry:
            continue
        path = HERE.parent / "q4_study" / entry["local_path"]
        if not path.exists():
            drift.append(f"missing:{key}")
            continue
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            drift.append(f"q4:{key}")
    check(
        "every frozen raw input still matches its recorded hash",
        not drift,
        f"drift={drift[:5]}",
    )

    # 19. The submissions API timestamp must not appear anywhere in the
    #     emitted evidence, because Decision 12 forbids relying on it.
    api_leak = [
        observation["evaluation_date"]
        for observation in observations
        for component in observation["TTM_GAAP_DILUTED_PE"]["components"]
        if component.get("acceptance_datetime", "").endswith("Z")
    ]
    check(
        "no acceptance timestamp in the output came from the submissions API",
        not api_leak,
        f"leaks={api_leak[:5]}",
    )

    lines = ["Amendment 1 verification -- conformance audit", ""]
    for name, ok, detail in CHECKS:
        lines.append(f"[{'PASS' if ok else 'FAIL'}] {name}")
        lines.append(f"        {detail}")
    failures = [name for name, ok, _ in CHECKS if not ok]
    lines.append("")
    lines.append(
        f"result: {'ALL PASS' if not failures else 'FAILED: ' + '; '.join(failures)}"
    )
    text = "\n".join(lines) + "\n"
    (OUT / "verification.txt").write_text(text, encoding="utf-8")
    print(text)
    if failures:
        raise SystemExit(1)


def _mix(observation: dict) -> str | None:
    components = [
        c
        for c in observation["TTM_GAAP_DILUTED_PE"]["components"]
        if c.get("period_end")
    ]
    filed = sum(1 for c in components if c["evidence_class"] == "filed")
    furnished = sum(
        1 for c in components if c["evidence_class"] == "furnished"
    )
    if filed == 3 and furnished == 1:
        return "filed_x3_furnished_x1"
    if furnished:
        return f"filed_x{filed}_furnished_x{furnished}"
    return None


def _third_path(enabled: dict) -> dict[str, float]:
    """Recompute every TTM denominator without the compute stage's code.

    Filed quarters come from the XBRL concept JSON. Furnished quarters are
    re-extracted from the exhibit HTML with an independent expression, then the
    four quarters of each window are summed using the component identities the
    compute stage emitted, so the sum itself is checked rather than trusted.
    """
    concept_sha = hashlib.sha256(
        (POC_RAW / "eps_diluted_concept.json").read_bytes()
    ).hexdigest()
    facts = json.loads(
        (POC_RAW / "eps_diluted_concept.json").read_text(encoding="utf-8")
    )["units"]["USD/shares"]
    filed_by_end: dict[str, list[float]] = {}
    by_accession: dict[str, dict[str, float]] = {}
    for fact in facts:
        if not fact.get("start"):
            continue
        span = (
            datetime.date.fromisoformat(fact["end"])
            - datetime.date.fromisoformat(fact["start"])
        ).days
        if 80 <= span <= 100:
            filed_by_end.setdefault(fact["end"], []).append(fact["val"])
            by_accession.setdefault(fact["accn"], {})[fact["end"]] = fact[
                "val"
            ]

    furnished_by_end: dict[str, float] = {}
    for observation in enabled["observations"]:
        for component in observation["TTM_GAAP_DILUTED_PE"]["components"]:
            if component.get("evidence_class") != "furnished":
                continue
            document = list(Q4_RAW.rglob(component["source_document"]))[0]
            text = document.read_text(encoding="utf-8", errors="replace")
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text)
            numbers = re.findall(
                r"Diluted\s*\$?\s*(-?[\d,]+\.\d{2})", text
            )
            assert numbers, f"no diluted row in {component['source_document']}"
            value = float(numbers[0].replace(",", ""))
            furnished_by_end[component["period_end"]] = value

    result: dict[str, float] = {}
    for observation in enabled["observations"]:
        ttm = observation["TTM_GAAP_DILUTED_PE"]
        if ttm["status"] != "AVAILABLE":
            continue
        total = 0.0
        for component in ttm["components"]:
            if not component.get("period_end"):
                continue
            end = component["period_end"]
            if component["evidence_class"] == "furnished":
                total += furnished_by_end[end]
            else:
                total += _resolve_filed(
                    end,
                    component["accession"],
                    component["diluted_eps"],
                    filed_by_end,
                    by_accession,
                    concept_sha,
                )
        result[observation["evaluation_date"]] = round(total, 6)
    return result


def _resolve_filed(
    period_end: str,
    accession: str,
    value: float,
    filed_by_end: dict[str, list[float]],
    by_accession: dict[str, dict[str, float]],
    concept_sha: str,
) -> float:
    """Pick the filed figure independently, keyed on the accession.

    A given quarter is tagged by several filings over time, and the later ones
    may restate it. The point-in-time rule is that the value used is the one
    from the accession the observation actually cites, which is a different
    question from "the last value in the file".
    """
    by_accn = by_accession[accession]
    if period_end in by_accn:
        return by_accn[period_end]
    raise AssertionError(
        f"accession {accession} has no quarter fact ending {period_end}"
    )


if __name__ == "__main__":
    main()
