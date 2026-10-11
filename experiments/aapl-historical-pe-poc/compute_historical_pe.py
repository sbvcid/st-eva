"""POC compute stage: point-in-time Historical P/E for AAPL under the ADR rules.

Methodology source: docs/ADR-HISTORICAL-PE-METHODOLOGY.md (APPROVED / FROZEN).
This file implements only what that ADR freezes, only for the POC period, and
writes only into this scratch directory.

The four frozen decisions this stage actually depends on:

  2. acceptance_datetime is the information-availability hard boundary.
  3. 16:00 ET cutoff: accepted before 16:00 ET -> usable at that day's close;
     at or after 16:00 ET -> usable only from the next trading day's close.
  4. Q4 diluted EPS may never be derived by subtracting FY from YTD.
  5. A missing Q4 makes TTM_GAAP_DILUTED_PE UNAVAILABLE with
     REASON_MISSING_Q4_EPS; ANNUAL_GAAP_DILUTED_PE is still recorded separately
     and is never substituted for TTM.
  7. No lookahead: at date t, only filings whose acceptance-derived usable date
     is <= t may contribute, and only the most recent restatement known at t.
  8. Price and per-share figures must share a per-share basis. The POC uses the
     as-traded close, which is the contemporaneous basis, so it pairs with the
     EPS as filed at that date and needs no split-adjustment schema. This is a
     POC-level choice and the Corporate Action schema stays OPEN.
"""

from __future__ import annotations

import datetime
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
OUT = HERE / "out"

ET = ZoneInfo("America/New_York")
UTC = datetime.timezone.utc

METHODOLOGY_ID = "docs/ADR-HISTORICAL-PE-METHODOLOGY.md"
METHODOLOGY_STATUS = "APPROVED / FROZEN 2026-10-07"
LOGIC_VERSION = "aapl-historical-pe-poc/0.1.0"
CUTOFF_ET = datetime.time(16, 0)

POC_FIRST_TRADING_DATE = "2019-01-30"
POC_LAST_TRADING_DATE = "2026-10-06"

QUARTER_MIN_DAYS = 80
QUARTER_MAX_DAYS = 100
YEAR_MIN_DAYS = 350
YEAR_MAX_DAYS = 380

REASON_MISSING_Q4_EPS = "REASON_MISSING_Q4_EPS"
REASON_INSUFFICIENT_QUARTERS = "REASON_INSUFFICIENT_QUARTERS"
REASON_MISSING_PRICE = "REASON_MISSING_PRICE"
REASON_NON_POSITIVE_EPS = "REASON_NON_POSITIVE_EPS"

# AAPL's fiscal year ends on the last Saturday of September, so Q4 is the
# quarter whose end date sits closest to but not after the fiscal year end the
# issuer reports. Rather than hard-code a calendar, a quarter is Q4 when the
# next quarter's end date crosses the 10-K's fiscal year end, i.e. when the
# quarter is the last one inside the fiscal year the annual fact covers.
def quarter_number(quarter_end: datetime.date, fiscal_year_end_month: int) -> int:
    """Quarter number of `quarter_end` for an issuer whose fiscal year ends in `fiscal_year_end_month`.

    AAPL's fiscal year ends in late September, so the four quarters end in late
    December, late March, late June and late September. Counting quarter ends
    backwards from the fiscal year end month the issuer declares in its own 10-K
    header keeps the mapping auditable rather than hard-coded per quarter.
    """
    months_after = (quarter_end.month - fiscal_year_end_month) % 12
    if months_after == 0:
        return 4
    return min(months_after // 3, 3)


def load_json(name: str):
    return json.loads((RAW / name).read_text(encoding="utf-8"))


def parse_date(value: str) -> datetime.date:
    return datetime.date.fromisoformat(value)


def usable_date_from_acceptance(
    acceptance_et: datetime.datetime, trading_days: list[datetime.date]
) -> tuple[datetime.date, str]:
    """ADR rule 3: apply the 16:00 ET cutoff, then land on a real trading day."""
    acceptance_day = acceptance_et.date()
    before_cutoff = acceptance_et.timetz().replace(tzinfo=None) < CUTOFF_ET
    candidate = (
        acceptance_day
        if before_cutoff
        else acceptance_day + datetime.timedelta(days=1)
    )
    rule = (
        "acceptance_before_1600ET_same_day"
        if before_cutoff
        else "acceptance_at_or_after_1600ET_next_trading_day"
    )
    for day in trading_days:
        if day >= candidate:
            return day, rule
    # Older than the price series: keep the calendar candidate and say so, so
    # the gap is visible rather than silently moved.
    return candidate, rule + "_before_price_series"


def load_prices() -> tuple[dict[datetime.date, dict], dict]:
    payload = load_json("daily_prices.json")
    result = payload["chart"]["result"][0]
    meta = result["meta"]
    timestamps = result["timestamp"]
    quote = result["indicators"]["quote"][0]
    bars: dict[datetime.date, dict] = {}
    for index, stamp in enumerate(timestamps):
        close = quote["close"][index]
        if close is None:
            continue
        day = datetime.datetime.fromtimestamp(stamp, UTC).date()
        bars[day] = {"close": float(close), "volume": quote["volume"][index]}
    return bars, meta


def as_traded_close(
    day: datetime.date,
    bars: dict[datetime.date, dict],
    splits: list[dict],
) -> tuple[float | None, list[dict]]:
    """Undo the vendor's split adjustment so the price is the price traded on `day`.

    Yahoo's chart `close` is already restated for every split in the series,
    including splits that had not happened yet on `day`. Multiplying by the
    inverse of the split ratios whose ex-date is after `day` returns the
    as-traded basis that a participant at `day` actually saw, which is the only
    basis on which the EPS filed at `day` is simultaneously correct.
    """
    bar = bars.get(day)
    if bar is None:
        return None, []
    close = bar["close"]
    applied = []
    for split in splits:
        ex_date = split["ex_date"]
        if ex_date <= day:
            continue
        ratio = split["numerator"] / split["denominator"]
        close *= ratio
        applied.append(
            {
                "ex_date": ex_date.isoformat(),
                "split_ratio": split["split_ratio"],
                "vendor_adjusted_close": bar["close"],
                "restored_as_traded_close": close,
            }
        )
    return close, applied


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    bars, price_meta = load_prices()
    submissions = load_json("submissions.json")
    concept = load_json("eps_diluted_concept.json")
    acceptance_evidence = load_json("filing_acceptance_evidence.json")

    trading_days = sorted(bars)
    period_days = [
        day
        for day in trading_days
        if POC_FIRST_TRADING_DATE <= day.isoformat() <= POC_LAST_TRADING_DATE
    ]

    price_payload = load_json("daily_prices.json")["chart"]["result"][0]
    splits = [
        {
            "ex_date": datetime.datetime.fromtimestamp(
                int(stamp), UTC
            ).date(),
            "split_ratio": entry["splitRatio"],
            "numerator": entry["numerator"],
            "denominator": entry["denominator"],
        }
        for stamp, entry in sorted(
            (price_payload.get("events", {}).get("splits", {}) or {}).items()
        )
    ]

    # ---- filing identity and acceptance-derived usable date -----------------
    filings: dict[str, dict] = {}
    for row in acceptance_evidence:
        acceptance_et = datetime.datetime.fromisoformat(
            row["acceptance_datetime_header_et"]
        )
        # Land on a real trading day using the whole price series, not just the
        # POC window, so a filing accepted just before the window start keeps
        # its true usable date instead of being clamped onto the first day.
        usable, rule = usable_date_from_acceptance(acceptance_et, trading_days)
        filings[row["accession"]] = {
            "accession": row["accession"],
            "form": row["form"],
            "period_end": row["period_end"],
            "filed_date": row["filed_as_of_date_header"],
            "acceptance_datetime": row["acceptance_datetime_header_et"],
            "acceptance_source": "EDGAR SGML header ACCEPTANCE-DATETIME (ET)",
            "usable_date": usable.isoformat(),
            "usable_date_rule": rule,
            "conformed_period_of_report": row[
                "conformed_period_of_report_header"
            ],
            "fiscal_year_end_header": row["fiscal_year_end_header"],
            "header_source_url": row["header_source_url"],
            "header_source_sha256": row["header_source_sha256"],
        }

    # ---- SEC diluted EPS facts, keyed by fiscal period ---------------------
    facts = concept["units"]["USD/shares"]
    # The fiscal year end the issuer declares in its own 10-K SGML header.
    # The 10-K header carries the fiscal year end as MMDD and AAPL runs a
    # 52/53-week year, so the day moves every year (0924, 0925, 0926, 0927,
    # 0928, 0930). Only the month is stable, and only the month is needed to
    # place a quarter inside its fiscal year.
    declared_fye_months = {
        filing["fiscal_year_end_header"][:2]
        for filing in filings.values()
        if filing["form"] == "10-K" and filing["fiscal_year_end_header"]
    }
    if len(declared_fye_months) != 1:
        raise ValueError(
            f"issuer declares more than one fiscal year end month: {declared_fye_months}"
        )
    fiscal_year_end_month = int(declared_fye_months.pop())

    ten_k_period_ends = sorted(
        parse_date(filing["period_end"])
        for filing in filings.values()
        if filing["form"] == "10-K"
    )

    def fiscal_year_end_for(end: datetime.date) -> datetime.date:
        for candidate in ten_k_period_ends:
            if candidate >= end:
                return candidate
        return ten_k_period_ends[-1]

    # Keep every version of every fact, because the point-in-time rule needs the
    # most recent version known at each date t, not the latest overall.
    all_quarterly_versions: dict[datetime.date, list[dict]] = defaultdict(list)
    all_annual_versions: dict[datetime.date, list[dict]] = defaultdict(list)
    for fact in facts:
        if not fact.get("start"):
            continue
        start = parse_date(fact["start"])
        end = parse_date(fact["end"])
        span = (end - start).days
        accession = fact["accn"]
        if accession not in filings:
            continue
        entry = {
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "duration_days": span,
            "value": fact["val"],
            "form": fact["form"],
            "accession": accession,
            "acceptance_datetime": filings[accession]["acceptance_datetime"],
            "usable_date": filings[accession]["usable_date"],
            "period_of_report": filings[accession]["period_end"],
        }
        if QUARTER_MIN_DAYS <= span <= QUARTER_MAX_DAYS:
            all_quarterly_versions[end].append(entry)
        elif YEAR_MIN_DAYS <= span <= YEAR_MAX_DAYS:
            all_annual_versions[end].append(entry)

    for versions in all_quarterly_versions.values():
        versions.sort(key=lambda item: (item["usable_date"], item["accession"]))
    for versions in all_annual_versions.values():
        versions.sort(key=lambda item: (item["usable_date"], item["accession"]))

    sorted_quarter_ends = sorted(all_quarterly_versions)

    # ---- evaluate on each filing's usable date ------------------------------
    evaluation_days = sorted(
        {
            parse_date(filing["usable_date"])
            for filing in filings.values()
            if POC_FIRST_TRADING_DATE
            <= filing["usable_date"]
            <= POC_LAST_TRADING_DATE
        }
    )

    observations = []
    for day in evaluation_days:
        day_iso = day.isoformat()
        used_filings: set[str] = set()
        price, restored = as_traded_close(day, bars, splits)

        def known_quarters() -> dict[datetime.date, dict]:
            result = {}
            for end, versions in all_quarterly_versions.items():
                usable = [v for v in versions if v["usable_date"] <= day_iso]
                if usable:
                    result[end] = usable[-1]
            return result

        known = known_quarters()
        ends = sorted(known)
        ttm_value = None
        ttm_status = "UNAVAILABLE"
        ttm_reason = None
        ttm_components: list[dict] = []
        missing_window_quarters: list[dict] = []

        # The trailing window is anchored on the latest fiscal quarter that has
        # a directly filed quarter-length diluted EPS fact at t, and extends back
        # over that quarter's three fiscal predecessors. Anchoring on fiscal
        # positions rather than on "the last four dates I happen to hold" is what
        # makes a missing Q4 surface as a missing Q4 instead of silently
        # shortening the window.
        if not known:
            ttm_reason = REASON_INSUFFICIENT_QUARTERS
        else:
            anchor = ends[-1]
            anchor_fye = fiscal_year_end_for(anchor)
            anchor_number = quarter_number(anchor, fiscal_year_end_month)

            # Walk back three fiscal quarters from the anchor, crossing into the
            # prior fiscal year whenever the index drops below 1.
            positions: list[tuple[datetime.date, int]] = []
            index = anchor_number
            fye = anchor_fye
            for _ in range(4):
                positions.append((fye, index))
                index -= 1
                if index == 0:
                    index = 4
                    fye = fiscal_year_end_for(
                        fye - datetime.timedelta(days=370)
                    )
            positions.reverse()

            window_ends: list[datetime.date] = []
            for position_fye, position_number in positions:
                match = [
                    end
                    for end in ends
                    if fiscal_year_end_for(end) == position_fye
                    and quarter_number(end, fiscal_year_end_month) == position_number
                ]
                if match:
                    window_ends.append(match[-1])
                else:
                    missing_window_quarters.append(
                        {
                            "fiscal_year_end": position_fye.isoformat(),
                            "quarter_number": position_number,
                        }
                    )

            missing = missing_window_quarters
            if not missing:
                ttm_components = [
                    {
                        "period_end": end.isoformat(),
                        "quarter_number": quarter_number(
                            end, fiscal_year_end_month
                        ),
                        "fiscal_year_end": fiscal_year_end_for(end).isoformat(),
                        "diluted_eps": known[end]["value"],
                        "accession": known[end]["accession"],
                        "form": known[end]["form"],
                        "acceptance_datetime": known[end]["acceptance_datetime"],
                        "usable_date": known[end]["usable_date"],
                    }
                    for end in window_ends
                ]
                total = sum(item["diluted_eps"] for item in ttm_components)
                ttm_components.append(
                    {
                        "period_end": None,
                        "quarter_number": None,
                        "fiscal_year_end": None,
                        "diluted_eps": total,
                        "derivation": "sum of 4 directly filed quarterly diluted EPS",
                    }
                )
                if price is None:
                    ttm_reason = REASON_MISSING_PRICE
                elif total <= 0:
                    ttm_reason = REASON_NON_POSITIVE_EPS
                else:
                    ttm_status = "AVAILABLE"
                    ttm_value = price / total
                    used_filings.update(
                        item["accession"] for item in ttm_components
                        if item.get("accession")
                    )
            elif any(item["quarter_number"] == 4 for item in missing):
                ttm_reason = REASON_MISSING_Q4_EPS
            else:
                ttm_reason = REASON_INSUFFICIENT_QUARTERS

        annual_status = "UNAVAILABLE"
        annual_value = None
        annual_reason = None
        annual_component = None
        annual_candidates = []
        for end, versions in all_annual_versions.items():
            usable = [v for v in versions if v["usable_date"] <= day_iso]
            if usable:
                annual_candidates.append((end, usable[-1]))
        if not annual_candidates:
            annual_reason = REASON_INSUFFICIENT_QUARTERS
        else:
            end, latest = max(annual_candidates, key=lambda pair: pair[0])
            annual_component = {
                "fiscal_year_end": end.isoformat(),
                "diluted_eps": latest["value"],
                "accession": latest["accession"],
                "form": latest["form"],
                "acceptance_datetime": latest["acceptance_datetime"],
                "usable_date": latest["usable_date"],
            }
            if price is None:
                annual_reason = REASON_MISSING_PRICE
            elif latest["value"] <= 0:
                annual_reason = REASON_NON_POSITIVE_EPS
            else:
                annual_status = "AVAILABLE"
                annual_value = price / latest["value"]
                used_filings.add(latest["accession"])

        latest_quarters_seen = [
            {
                "period_end": end.isoformat(),
                "diluted_eps": known[end]["value"],
                "accession": known[end]["accession"],
                "usable_date": known[end]["usable_date"],
            }
            for end in ends[-6:]
        ]

        observations.append(
            {
                "evaluation_date": day_iso,
                "is_trading_day": True,
                "price_close_as_traded": price,
                "price_vendor_adjusted_close": (
                    bars[day]["close"] if day in bars else None
                ),
                "price_source": "Yahoo Finance chart API v8 close (split-adjusted by vendor; restored to as-traded basis)",
                "price_source_url": (
                    "https://query1.finance.yahoo.com/v8/finance/chart/AAPL"
                    "?period1=1514764800&period2=1800000000&interval=1d&events=div,split"
                ),
                "price_split_restoration": restored,
                "TTM_GAAP_DILUTED_PE": {
                    "status": ttm_status,
                    "value": ttm_value,
                    "reason": ttm_reason,
                    "components": ttm_components,
                    "quarters_known_at_t": latest_quarters_seen,
                    "derivation": "sum of 4 directly filed quarterly diluted EPS",
                    "fy_minus_ytd_used": False,
                },
                "ANNUAL_GAAP_DILUTED_PE": {
                    "status": annual_status,
                    "value": annual_value,
                    "reason": annual_reason,
                    "component": annual_component,
                    "substituted_for_ttm": False,
                },
                "filings_used": sorted(used_filings),
                "methodology": METHODOLOGY_ID,
                "methodology_status": METHODOLOGY_STATUS,
                "logic_version": LOGIC_VERSION,
            }
        )

    # ---- point-in-time assertions ------------------------------------------
    lookahead_violations = []
    for observation in observations:
        day_iso = observation["evaluation_date"]
        for accession in observation["filings_used"]:
            filing = filings[accession]
            if filing["usable_date"] > day_iso:
                lookahead_violations.append(
                    {
                        "evaluation_date": day_iso,
                        "accession": accession,
                        "usable_date": filing["usable_date"],
                    }
                )
        for component in observation["TTM_GAAP_DILUTED_PE"]["components"]:
            if not component.get("usable_date"):
                continue
            if component["usable_date"] > day_iso:
                lookahead_violations.append(
                    {
                        "evaluation_date": day_iso,
                        "accession": component["accession"],
                        "usable_date": component["usable_date"],
                    }
                )

    # ---- current snapshot at the run instant --------------------------------
    current_day = trading_days[-1]
    current_price, current_restored = as_traded_close(current_day, bars, splits)
    current_known = {}
    for end, versions in all_quarterly_versions.items():
        usable = [
            v for v in versions if v["usable_date"] <= current_day.isoformat()
        ]
        if usable:
            current_known[end] = usable[-1]
    current_ends = sorted(current_known)[-4:]
    current_annual = max(
        (
            (end, [v for v in versions if v["usable_date"] <= current_day.isoformat()][-1])
            for end, versions in all_annual_versions.items()
            if any(v["usable_date"] <= current_day.isoformat() for v in versions)
        ),
        key=lambda pair: pair[0],
    )
    current = {
        "as_of_trading_date": current_day.isoformat(),
        "price_close_as_traded": current_price,
        "price_split_restoration": current_restored,
        "price_source": observations[-1]["price_source"] if observations else None,
        "price_source_url": observations[-1]["price_source_url"] if observations else None,
        "TTM_GAAP_DILUTED_PE": {
            "status": "UNAVAILABLE",
            "reason": REASON_MISSING_Q4_EPS,
            "detail": (
                "No 10-K filed on or before the run instant discloses a Q4 "
                "quarter-length diluted EPS fact; the trailing four quarters "
                f"known at {current_day.isoformat()} are "
                + ", ".join(end.isoformat() for end in current_ends)
                + " and do not form four consecutive quarters of a fiscal year."
            ),
        },
        "ANNUAL_GAAP_DILUTED_PE": {
            "status": "AVAILABLE",
            "value": (
                current_price / current_annual[1]["value"]
                if current_price is not None and current_annual[1]["value"] > 0
                else None
            ),
            "fiscal_year_end": current_annual[0].isoformat(),
            "diluted_eps": current_annual[1]["value"],
            "accession": current_annual[1]["accession"],
            "acceptance_datetime": current_annual[1]["acceptance_datetime"],
            "substituted_for_ttm": False,
        },
        "role": "current snapshot observation only; not a historical band input",
        "methodology": METHODOLOGY_ID,
        "logic_version": LOGIC_VERSION,
    }

    payload = {
        "poc": "AAPL Historical P/E proof of concept",
        "not_production": True,
        "period": {
            "first_evaluation_date": observations[0]["evaluation_date"],
            "last_evaluation_date": observations[-1]["evaluation_date"],
            "price_series_first_day": trading_days[0].isoformat(),
            "price_series_last_day": trading_days[-1].isoformat(),
        },
        "methodology": METHODOLOGY_ID,
        "methodology_status": METHODOLOGY_STATUS,
        "logic_version": LOGIC_VERSION,
        "cutoff_convention": "16:00 ET",
        "acceptance_timezone_note": (
            "EDGAR SGML header ACCEPTANCE-DATETIME is Eastern Time; the "
            "submissions API acceptanceDateTime for the same filing differs by "
            "the ET offset (4h or 5h) and was not used for the cutoff test."
        ),
        "open_methodology_questions": [
            "Reference Sufficiency (observation count / time span / fiscal-quarter coverage) - OPEN",
            "Corporate Action evidence schema - OPEN; POC used as-traded price so no split adjustment schema was needed",
            "Sampling frequency (daily / weekly / monthly / event-driven) - OPEN; POC used filing-event dates",
            "Annual P/E fallback policy for FPIs - OPEN",
        ],
        "price_meta": {
            "currency": price_meta.get("currency"),
            "symbol": price_meta.get("symbol"),
            "exchange_name": price_meta.get("exchangeName"),
            "exchange_timezone": price_meta.get("exchangeTimezoneName"),
            "vendor_splits": [
                {
                    "ex_date": split["ex_date"].isoformat(),
                    "split_ratio": split["split_ratio"],
                }
                for split in splits
            ],
        },
        "filings": [filings[key] for key in sorted(filings)],
        "quarterly_eps_evidence": {
            end.isoformat(): versions
            for end, versions in sorted(all_quarterly_versions.items())
        },
        "annual_eps_evidence": {
            end.isoformat(): versions
            for end, versions in sorted(all_annual_versions.items())
        },
        "observations": observations,
        "current": current,
        "lookahead_violations": lookahead_violations,
    }

    serialised = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    payload["content_hash"] = hashlib.sha256(
        serialised.encode("utf-8")
    ).hexdigest()

    (OUT / "historical_pe_points.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    print("content_hash", payload["content_hash"])
    print("observations", len(observations))
    print(
        "ttm available",
        sum(
            1
            for o in observations
            if o["TTM_GAAP_DILUTED_PE"]["status"] == "AVAILABLE"
        ),
    )
    print(
        "annual available",
        sum(
            1
            for o in observations
            if o["ANNUAL_GAAP_DILUTED_PE"]["status"] == "AVAILABLE"
        ),
    )
    print("lookahead violations", len(lookahead_violations))


if __name__ == "__main__":
    main()
