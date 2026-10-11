"""POC replay stage: prove that re-running the compute stage is deterministic.

Runs the compute stage twice in separate processes from the same frozen raw
bytes, compares the content hashes, and additionally re-derives every P/E from
the stored raw inputs in a third, independent pass. Determinism here means
"same inputs, same bytes in, same bytes out", not "stable across future SEC
restatements", which is a different claim and is not made.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
OUT = HERE / "out"
ET = ZoneInfo("America/New_York")


def compute_hash() -> str:
    subprocess.run(
        [sys.executable, "compute_historical_pe.py"],
        cwd=HERE,
        check=True,
        capture_output=True,
    )
    payload = json.loads(
        (OUT / "historical_pe_points.json").read_text(encoding="utf-8")
    )
    return payload["content_hash"]


def independent_pass() -> list[tuple[str, float | None]]:
    """Recompute TTM P/E from raw files with no shared code path."""
    concept = json.loads(
        (RAW / "eps_diluted_concept.json").read_text(encoding="utf-8")
    )["units"]["USD/shares"]
    submissions = json.loads(
        (RAW / "submissions.json").read_text(encoding="utf-8")
    )["filings"]["recent"]
    evidence = json.loads(
        (RAW / "filing_acceptance_evidence.json").read_text(encoding="utf-8")
    )
    prices = json.loads(
        (RAW / "daily_prices.json").read_text(encoding="utf-8")
    )
    result = prices["chart"]["result"][0]
    bars = {
        datetime.datetime.fromtimestamp(stamp, datetime.timezone.utc).date().isoformat(): (
            result["indicators"]["quote"][0]["close"][index]
        )
        for index, stamp in enumerate(result["timestamp"])
        if result["indicators"]["quote"][0]["close"][index] is not None
    }
    split_ts = min(result["events"]["splits"])
    split_ex = datetime.datetime.fromtimestamp(
        int(split_ts), datetime.timezone.utc
    ).date()

    acceptance = {}
    for row in evidence:
        accepted = datetime.datetime.fromisoformat(
            row["acceptance_datetime_header_et"]
        )
        before = accepted.time() < datetime.time(16, 0)
        day = accepted.date() if before else accepted.date() + datetime.timedelta(days=1)
        while day.isoformat() not in bars:
            day += datetime.timedelta(days=1)
        acceptance[row["accession"]] = (day.isoformat(), row["form"], row["period_end"])

    del submissions

    quarterly: dict[str, list[tuple[str, float]]] = {}
    for fact in concept:
        if not fact.get("start"):
            continue
        span = (
            datetime.date.fromisoformat(fact["end"])
            - datetime.date.fromisoformat(fact["start"])
        ).days
        if not 80 <= span <= 100:
            continue
        if fact["accn"] not in acceptance:
            continue
        usable = acceptance[fact["accn"]][0]
        quarterly.setdefault(fact["end"], []).append((usable, fact["val"]))

    first = json.loads(
        (OUT / "historical_pe_points.json").read_text(encoding="utf-8")
    )["observations"][0]["evaluation_date"]
    last = json.loads(
        (OUT / "historical_pe_points.json").read_text(encoding="utf-8")
    )["observations"][-1]["evaluation_date"]

    rows = []
    for observation in json.loads(
        (OUT / "historical_pe_points.json").read_text(encoding="utf-8")
    )["observations"]:
        day = observation["evaluation_date"]
        if not first <= day <= last:
            continue
        close = bars[day]
        if datetime.date.fromisoformat(day) < split_ex:
            close *= 4.0
        # Point-in-time: among the versions filed at or before t, take the one
        # with the latest usable date, which is the most recent restatement the
        # market could have known at t.
        quarters = []
        for end, versions in quarterly.items():
            known = [(usable, value) for usable, value in versions if usable <= day]
            if not known:
                continue
            latest = max(known, key=lambda item: item[0])
            quarters.append((end, latest[1]))
        quarters.sort()
        window = quarters[-4:]
        value = None
        if len(window) == 4:
            ends = [datetime.date.fromisoformat(end) for end, _ in window]
            consecutive = all(
                (ends[i] - ends[i - 1]).days < 120 for i in range(1, len(ends))
            )
            has_q4 = any(end.month == 9 for end in ends)
            if consecutive and has_q4:
                value = close / sum(v for _, v in window)
        rows.append((day, value))
    return rows


def main() -> None:
    first_hash = compute_hash()
    second_hash = compute_hash()
    payload = json.loads(
        (OUT / "historical_pe_points.json").read_text(encoding="utf-8")
    )

    independent = dict(independent_pass())
    mismatches = []
    for observation in payload["observations"]:
        day = observation["evaluation_date"]
        recorded = observation["TTM_GAAP_DILUTED_PE"]["value"]
        recomputed = independent.get(day)
        if recorded is None and recomputed is None:
            continue
        if recorded is None or recomputed is None:
            mismatches.append((day, recorded, recomputed))
            continue
        if abs(recorded - recomputed) > 1e-6:
            mismatches.append((day, recorded, recomputed))

    lines = [
        "AAPL Historical P/E POC -- replay / determinism",
        "",
        f"run 1 content_hash {first_hash}",
        f"run 2 content_hash {second_hash}",
        f"identical         {first_hash == second_hash}",
        f"raw input sha256  {json.loads((RAW / 'manifest.json').read_text(encoding='utf-8'))['daily_prices']['sha256'][:32]}... (daily_prices)",
        "",
        f"independent recomputation of TTM P/E: {len(independent)} dates",
        f"mismatches: {mismatches if mismatches else 'none'}",
        "",
        "note: determinism is over frozen raw bytes. A future SEC restatement or a",
        "refetched price series is a different input set and is expected to change",
        "the hash; that is an input change, not a replay failure.",
    ]
    text = "\n".join(lines) + "\n"
    (OUT / "determinism.txt").write_text(text, encoding="utf-8")
    print(text)
    if first_hash != second_hash or mismatches:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
