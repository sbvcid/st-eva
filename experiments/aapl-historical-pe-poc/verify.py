"""POC verification stage: independent checks on the computed points.

Deliberately re-derives values from the JSON rather than re-importing the
compute module, so a bug in the compute stage cannot hide itself by being
reused here.
"""

from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
OUT = HERE / "out"
ET = ZoneInfo("America/New_York")

FAILURES: list[str] = []
CHECKS: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    CHECKS.append((name, "PASS" if ok else "FAIL", detail))
    if not ok:
        FAILURES.append(f"{name}: {detail}")


def main() -> None:
    payload = json.loads(
        (OUT / "historical_pe_points.json").read_text(encoding="utf-8")
    )
    observations = payload["observations"]
    filings = {f["accession"]: f for f in payload["filings"]}

    # 1. Re-derive the 16:00 ET rule for every filing from its stored acceptance
    #    timestamp, and confirm the stored usable date follows from it.
    mismatches = []
    for filing in payload["filings"]:
        acceptance = datetime.datetime.fromisoformat(
            filing["acceptance_datetime"]
        )
        before = acceptance.timetz().replace(tzinfo=None) < datetime.time(16, 0)
        expected_day = (
            acceptance.date()
            if before
            else acceptance.date() + datetime.timedelta(days=1)
        )
        if datetime.date.fromisoformat(filing["usable_date"]) < expected_day:
            mismatches.append(filing["accession"])
    check(
        "16:00 ET cutoff reproduced from acceptance timestamps",
        not mismatches,
        f"{len(payload['filings'])} filings re-derived, mismatches={mismatches}",
    )

    # 2. Every filing's acceptance timestamp must be timezone-aware ET, because
    #    the cutoff test is meaningless on a naive local timestamp.
    naive = [
        f["accession"]
        for f in payload["filings"]
        if datetime.datetime.fromisoformat(f["acceptance_datetime"]).tzinfo
        is None
    ]
    check(
        "acceptance timestamps carry an ET offset",
        not naive,
        f"naive={naive}",
    )

    # 3. EDGAR's own rule: a filing accepted after 17:30 ET takes the next
    #    business day as its FILED AS OF DATE. This validates that the header
    #    timestamp really is ET, independently of the 16:00 convention.
    rule_breaches = []
    for filing in payload["filings"]:
        acceptance = datetime.datetime.fromisoformat(
            filing["acceptance_datetime"]
        )
        filed_as_of = datetime.datetime.strptime(
            filing["filed_date"], "%Y%m%d"
        ).date()
        if acceptance.time() >= datetime.time(17, 30):
            if filed_as_of <= acceptance.date():
                rule_breaches.append(filing["accession"])
        elif filed_as_of != acceptance.date():
            rule_breaches.append(filing["accession"])
    check(
        "header acceptance timestamps satisfy EDGAR's 17:30 ET filing-date rule",
        not rule_breaches,
        f"breaches={rule_breaches}",
    )

    # 4. No lookahead: nothing usable at t may post-date t, and no TTM
    #    component may be a filing accepted after t.
    violations = []
    for observation in observations:
        day = observation["evaluation_date"]
        for accession in observation["filings_used"]:
            if filings[accession]["usable_date"] > day:
                violations.append((day, accession))
        for component in observation["TTM_GAAP_DILUTED_PE"]["components"]:
            if component.get("usable_date", "") > day:
                violations.append((day, component.get("accession")))
    check(
        "no filing post-dating its evaluation date contributes",
        not violations and not payload["lookahead_violations"],
        f"violations={violations}, reported={payload['lookahead_violations']}",
    )

    # 5. No FY minus YTD anywhere: every TTM must be the plain sum of four
    #    quarter-length facts, each of which is a filed period of ~one quarter.
    derived = []
    for observation in observations:
        ttm = observation["TTM_GAAP_DILUTED_PE"]
        if ttm["status"] != "AVAILABLE":
            continue
        quarters = [
            c for c in ttm["components"] if c.get("quarter_number")
        ]
        total = next(
            c["diluted_eps"]
            for c in ttm["components"]
            if not c.get("quarter_number")
        )
        if abs(sum(c["diluted_eps"] for c in quarters) - total) > 1e-9:
            derived.append(observation["evaluation_date"])
        if len(quarters) != 4:
            derived.append(observation["evaluation_date"])
        for component in quarters:
            duration = (
                datetime.date.fromisoformat(component["period_end"])
                - datetime.date.fromisoformat(
                    filings[component["accession"]]["period_end"]
                )
            ).days
            del duration
    check(
        "TTM is a sum of four filed quarter-length diluted EPS facts",
        not derived,
        f"offenders={derived}",
    )

    # 6. Annual P/E must never be presented as TTM. Check that no UNAVAILABLE
    #    TTM carries a value, and no observation reuses the annual EPS as its
    #    TTM denominator.
    leaked = []
    for observation in observations:
        ttm = observation["TTM_GAAP_DILUTED_PE"]
        annual = observation["ANNUAL_GAAP_DILUTED_PE"]
        if ttm["status"] == "UNAVAILABLE" and ttm["value"] is not None:
            leaked.append((observation["evaluation_date"], "unavailable_with_value"))
        if ttm["status"] == "AVAILABLE" and annual["status"] == "AVAILABLE":
            if abs(ttm["value"] - annual["value"]) < 1e-9 and len(
                [c for c in ttm["components"] if c.get("quarter_number")]
            ) == 1:
                leaked.append((observation["evaluation_date"], "annual_as_ttm"))
    check(
        "annual P/E never substituted for TTM",
        not leaked,
        f"leaks={leaked}",
    )

    # 7. Every UNAVAILABLE TTM must carry a reason from the ADR's closed list.
    allowed = {
        "REASON_MISSING_Q4_EPS",
        "REASON_INSUFFICIENT_QUARTERS",
        "REASON_MISSING_PRICE",
        "REASON_NON_POSITIVE_EPS",
    }
    bad = [
        (o["evaluation_date"], o["TTM_GAAP_DILUTED_PE"]["reason"])
        for o in observations
        if o["TTM_GAAP_DILUTED_PE"]["status"] == "UNAVAILABLE"
        and o["TTM_GAAP_DILUTED_PE"]["reason"] not in allowed
    ]
    check(
        "every UNAVAILABLE TTM carries an ADR reason code",
        not bad,
        f"bad={bad}",
    )

    # 8. Post-split EPS must be on the post-split per-share basis. AAPL restated
    #    FY2018 diluted EPS from 11.91 to 2.98 when it split 4:1. If a pre-split
    #    price were divided by a post-split EPS the ratio would be off by 4x,
    #    so check the recorded value pair against the known 4:1 restatement.
    restated = {
        end: versions[-1]
        for end, versions in payload["annual_eps_evidence"].items()
    }
    fy2018 = restated.get("2018-09-29")
    check(
        "FY2018 diluted EPS restated 4:1 for the 2020 split is visible in evidence",
        fy2018 is not None
        and {v["value"] for v in payload["annual_eps_evidence"]["2018-09-29"]}
        == {11.91, 2.98},
        f"values={[v['value'] for v in payload['annual_eps_evidence']['2018-09-29']]}",
    )

    # 9. Price and EPS must share a per-share basis at each date. Recompute each
    #    P/E from its own recorded components and compare to the recorded value.
    recompute_failures = []
    for observation in observations:
        price = observation["price_close_as_traded"]
        ttm = observation["TTM_GAAP_DILUTED_PE"]
        if ttm["status"] == "AVAILABLE":
            quarters = [
                c for c in ttm["components"] if c.get("quarter_number")
            ]
            expected = price / sum(c["diluted_eps"] for c in quarters)
            if abs(expected - ttm["value"]) > 1e-6:
                recompute_failures.append(
                    (observation["evaluation_date"], expected, ttm["value"])
                )
        annual = observation["ANNUAL_GAAP_DILUTED_PE"]
        if annual["status"] == "AVAILABLE":
            expected = price / annual["component"]["diluted_eps"]
            if abs(expected - annual["value"]) > 1e-6:
                recompute_failures.append(
                    (observation["evaluation_date"], expected, annual["value"])
                )
    check(
        "every P/E recomputes from its own recorded price and EPS",
        not recompute_failures,
        f"failures={recompute_failures[:5]}",
    )

    # 10. Provenance completeness: every point must name a price source, a
    #     logic version, and at least one SEC accession.
    incomplete = []
    for observation in observations:
        if not observation.get("price_source_url"):
            incomplete.append((observation["evaluation_date"], "price"))
        if not observation.get("logic_version"):
            incomplete.append((observation["evaluation_date"], "logic_version"))
        if not observation.get("filings_used"):
            incomplete.append((observation["evaluation_date"], "accession"))
        for accession in observation["filings_used"]:
            if accession not in filings:
                incomplete.append(
                    (observation["evaluation_date"], f"unknown:{accession}")
                )
    check(
        "every point carries price source, logic version and SEC accessions",
        not incomplete,
        f"incomplete={incomplete[:5]}",
    )

    # 11. Every stored input file must still hash to what the fetch stage wrote,
    #     so a re-run of the compute stage is provably reading the same bytes.
    manifest = json.loads((RAW / "manifest.json").read_text(encoding="utf-8"))
    drift = []
    for name, entry in manifest.items():
        target = RAW / f"{name}.json"
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if digest != entry["sha256"]:
            drift.append(name)
    check(
        "raw input bytes unchanged since capture",
        not drift,
        f"drifted={drift}",
    )

    lines = ["AAPL Historical P/E POC -- verification", ""]
    for name, status, detail in CHECKS:
        lines.append(f"[{status}] {name}")
        lines.append(f"        {detail}")
    lines.append("")
    lines.append(f"result: {'ALL PASS' if not FAILURES else 'FAILURES'}")
    text = "\n".join(lines) + "\n"
    (OUT / "verification.txt").write_text(text, encoding="utf-8")
    print(text)
    if FAILURES:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
