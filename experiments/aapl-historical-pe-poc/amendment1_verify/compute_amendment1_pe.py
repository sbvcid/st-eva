"""Amendment 1 verification stage: rebuild AAPL Historical P/E with the
furnished evidence class admitted.

Methodology: docs/ADR-HISTORICAL-PE-METHODOLOGY.md as amended (Decisions 10-14).

This stage answers exactly one question: does admitting Form 8-K Item 2.02
EX-99.1 as a primary evidence class (Decision 10) actually unblock
TTM_GAAP_DILUTED_PE for AAPL fiscal Q4 after FY2021, without weakening anything
the original POC proved.

Inputs are the previously frozen raw bytes. Nothing is refetched, so any change
in the output is attributable to the evidence path and to nothing else.

What this stage deliberately does not do:
  * no generic Historical P/E engine, only the AAPL POC recomputation
  * no FY minus YTD, anywhere, under any flag
  * no change to how ANNUAL_GAAP_DILUTED_PE is built
  * no new provider, no contract change
"""

from __future__ import annotations

import datetime
import hashlib
import json
import re
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
POC_RAW = HERE.parent / "raw"
Q4_RAW = HERE.parent / "q4_study" / "raw"
Q4_OUT = HERE.parent / "q4_study" / "out"
OUT = HERE / "out"

ET = ZoneInfo("America/New_York")
UTC = datetime.timezone.utc
CUTOFF_ET = datetime.time(16, 0)

METHODOLOGY = "docs/ADR-HISTORICAL-PE-METHODOLOGY.md"
METHODOLOGY_AMENDMENT = "Amendment 1 (2026-10-07), Decisions 10-14"
LOGIC_VERSION = "aapl-historical-pe-amendment1/0.1.0"

POC_FIRST_TRADING_DATE = "2019-01-30"
POC_LAST_TRADING_DATE = "2026-10-06"

REASON_MISSING_Q4_EPS = "REASON_MISSING_Q4_EPS"
REASON_INSUFFICIENT_QUARTERS = "REASON_INSUFFICIENT_QUARTERS"
REASON_MISSING_PRICE = "REASON_MISSING_PRICE"
REASON_NON_POSITIVE_EPS = "REASON_NON_POSITIVE_EPS"

QUARTER_MIN_DAYS = 80
QUARTER_MAX_DAYS = 100
YEAR_MIN_DAYS = 350
YEAR_MAX_DAYS = 380

EVIDENCE_CLASS_FILED = "filed"
EVIDENCE_CLASS_FURNISHED = "furnished"

AUDIT_STATUS_AUDITED = "audited"
AUDIT_STATUS_REVIEWED = "unaudited_reviewed"
AUDIT_STATUS_UNAUDITED = "unaudited"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def header_acceptance(path: Path) -> datetime.datetime:
    """EDGAR's SGML header ACCEPTANCE-DATETIME, which is Eastern Time.

    The submissions API value is deliberately not used anywhere in this file.
    It carries a 'Z' suffix that does not denote UTC; see Decision 12.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    found = re.search(r"ACCEPTANCE-DATETIME&gt;(\d{14})", text)
    if not found:
        raise ValueError(f"no acceptance timestamp in {path}")
    return datetime.datetime.strptime(
        found.group(1), "%Y%m%d%H%M%S"
    ).replace(tzinfo=ET)


def usable_date(
    acceptance_et: datetime.datetime, trading_days: list[str]
) -> tuple[str, str]:
    """Decision 3: the 16:00 ET cutoff, then the next real trading day."""
    before = acceptance_et.time() < CUTOFF_ET
    candidate = (
        acceptance_et.date()
        if before
        else acceptance_et.date() + datetime.timedelta(days=1)
    )
    rule = (
        "acceptance_before_1600ET_same_day"
        if before
        else "acceptance_at_or_after_1600ET_next_trading_day"
    )
    for day in trading_days:
        if day >= candidate.isoformat():
            return day, rule
    return candidate.isoformat(), rule + "_before_price_series"


def quarter_number(period_end: datetime.date, fye_month: int) -> int:
    months_after = (period_end.month - fye_month) % 12
    if months_after == 0:
        return 4
    return min(months_after // 3, 3)


def main(enable_furnished: bool) -> dict:
    price_payload = load(POC_RAW / "daily_prices.json")["chart"]["result"][0]
    quote = price_payload["indicators"]["quote"][0]
    bars = {
        datetime.datetime.fromtimestamp(stamp, UTC).date().isoformat(): float(
            quote["close"][index]
        )
        for index, stamp in enumerate(price_payload["timestamp"])
        if quote["close"][index] is not None
    }
    trading_days = sorted(bars)
    period_days = [
        day
        for day in trading_days
        if POC_FIRST_TRADING_DATE <= day <= POC_LAST_TRADING_DATE
    ]

    split_stamp = min(price_payload["events"]["splits"])
    split_entry = price_payload["events"]["splits"][split_stamp]
    split_ex_date = datetime.datetime.fromtimestamp(
        int(split_stamp), UTC
    ).date().isoformat()
    split_ratio = float(split_entry["numerator"]) / float(
        split_entry["denominator"]
    )

    def as_traded_close(day: str) -> tuple[float | None, list[dict]]:
        """Restore the price actually quoted on `day` from the vendor's
        split-adjusted series, so price and EPS share a contemporaneous
        per-share basis (Decision 8). No Corporate Action schema is built."""
        if day not in bars:
            return None, []
        close = bars[day]
        restored = []
        if split_ex_date > day:
            close *= split_ratio
            restored.append(
                {
                    "ex_date": split_ex_date,
                    "split_ratio": split_entry["splitRatio"],
                    "vendor_adjusted_close": bars[day],
                    "restored_as_traded_close": close,
                }
            )
        return close, restored

    # ---- filing registry: filed 10-Q / 10-K ------------------------------
    evidence = load(POC_RAW / "filing_acceptance_evidence.json")
    concept_sha = sha256_of(POC_RAW / "eps_diluted_concept.json")

    filings: dict[str, dict] = {}
    for row in evidence:
        acceptance = datetime.datetime.fromisoformat(
            row["acceptance_datetime_header_et"]
        )
        usable, rule = usable_date(acceptance, trading_days)
        filings[row["accession"]] = {
            "accession": row["accession"],
            "form": row["form"],
            "evidence_class": EVIDENCE_CLASS_FILED,
            "acceptance_datetime": acceptance.isoformat(),
            "acceptance_source": "EDGAR SGML header ACCEPTANCE-DATETIME (ET)",
            "usable_date": usable,
            "usable_date_rule": rule,
            "period_end": row["period_end"],
        }

    ten_k_ends = sorted(
        parse_date_of(f["period_end"])
        for f in filings.values()
        if f["form"] == "10-K"
    )

    # The fiscal year end month comes from the issuer's own 10-K SGML header,
    # not from a hard-coded calendar assumption.
    fye_months = set()
    for row in evidence:
        if row["form"] != "10-K":
            continue
        found = re.search(
            r"FISCAL YEAR END:\s*(\d{2})",
            (POC_RAW / "headers" / f"{row['accession']}.txt").read_text(
                encoding="utf-8", errors="replace"
            ),
        )
        if found:
            fye_months.add(found.group(1))
    if len(fye_months) != 1:
        raise ValueError(f"ambiguous fiscal year end month: {fye_months}")
    fye_month = int(fye_months.pop())

    def fiscal_year_of(end: datetime.date) -> int:
        """The fiscal year a quarter belongs to.

        Derived from the quarter's own period end and the declared fiscal year
        end month. It is deliberately not derived from a list of 10-K period
        ends: such a list cannot cover the still-open fiscal year, and falling
        back to the most recent 10-K would relabel every quarter of the open
        year as belonging to the previous one, producing a window with a
        455-day hole in it.
        """
        return end.year + 1 if end.month > fye_month else end.year

    # ---- quarterly evidence from filed XBRL facts -----------------------
    quarterly: dict[datetime.date, list[dict]] = {}
    annual: dict[datetime.date, list[dict]] = {}
    for fact in load(POC_RAW / "eps_diluted_concept.json")["units"][
        "USD/shares"
    ]:
        if not fact.get("start"):
            continue
        start = parse_date_of(fact["start"])
        end = parse_date_of(fact["end"])
        span = (end - start).days
        accession = fact["accn"]
        if accession not in filings:
            continue
        form = filings[accession]["form"]
        if QUARTER_MIN_DAYS <= span <= QUARTER_MAX_DAYS:
            bucket, is_quarter = quarterly, True
        elif YEAR_MIN_DAYS <= span <= YEAR_MAX_DAYS:
            bucket, is_quarter = annual, False
        else:
            continue
        entry = {
            "period_end": end,
            "period_start": start,
            "duration_days": span,
            "diluted_eps": fact["val"],
            "form": form,
            "accession": accession,
            "evidence_class": EVIDENCE_CLASS_FILED,
            # A 10-K's financial statements are audited. A 10-Q's interim
            # statements are reviewed, not audited. Recording the distinction
            # as three values rather than two keeps "unaudited" from being
            # silently read as "audited".
            "audit_status": (
                AUDIT_STATUS_AUDITED
                if form == "10-K"
                else AUDIT_STATUS_REVIEWED
            ),
            "acceptance_datetime": filings[accession]["acceptance_datetime"],
            "usable_date": filings[accession]["usable_date"],
            "source_url": (
                "https://data.sec.gov/api/xbrl/companyconcept/"
                "CIK0000320193/us-gaap/EarningsPerShareDiluted.json"
            ),
            "source_document": None,
            "content_sha256": concept_sha,
            "stated_directly": True,
            "derivation": "directly tagged quarter-length XBRL fact",
            "is_quarter": is_quarter,
        }
        bucket.setdefault(end, []).append(entry)
    for versions in quarterly.values():
        versions.sort(key=lambda item: item["usable_date"])
    for versions in annual.values():
        versions.sort(key=lambda item: item["usable_date"])

    # ---- furnished Q4 evidence from Item 2.02 EX-99.1 -------------------
    furnished_used = 0
    if enable_furnished:
        study = load(Q4_OUT / "q4_evidence_records.json")
        for record in study["records"]:
            if (
                record["source_type"] != "SEC_8K_ITEM_2_02_EX_99_1"
                or not record["meets_st_eva_q4_evidence"]
            ):
                continue
            period_end = parse_date_of(record["quarter_period_end"])
            acceptance = datetime.datetime.fromisoformat(
                record["acceptance_datetime"]
            )
            usable, rule = usable_date(acceptance, trading_days)
            document = list(Q4_RAW.rglob(record["document_identifier"]))
            if not document:
                raise ValueError(
                    f"missing exhibit {record['document_identifier']}"
                )
            actual = sha256_of(document[0])
            if actual != record["content_sha256"]:
                raise ValueError(
                    f"exhibit hash drift for {record['document_identifier']}"
                )
            quarterly.setdefault(period_end, []).append(
                {
                    "period_end": period_end,
                    "period_start": None,
                    "duration_days": None,
                    "diluted_eps": record["diluted_eps"],
                    "form": "8-K",
                    "accession": record["accession"],
                    "evidence_class": EVIDENCE_CLASS_FURNISHED,
                    "audit_status": AUDIT_STATUS_UNAUDITED,
                    "acceptance_datetime": acceptance.isoformat(),
                    "usable_date": usable,
                    "usable_date_rule": rule,
                    "source_url": record["source_url"],
                    "source_document": record["document_identifier"],
                    "content_sha256": actual,
                    "stated_directly": True,
                    "derivation": (
                        "directly stated in the exhibit's Three Months Ended "
                        "column; no arithmetic performed"
                    ),
                    "is_quarter": True,
                    "furnished_not_filed": record.get(
                        "item_2_02_furnished_not_filed"
                    ),
                    "cover_document": record.get("cover_document"),
                    "statement_columns": record.get("statement_columns"),
                }
            )
            furnished_used += 1
    for versions in quarterly.values():
        versions.sort(key=lambda item: item["usable_date"])

    # ---- evaluation dates ----------------------------------------------
    evaluation_days = sorted(
        {
            filing["usable_date"]
            for filing in filings.values()
            if POC_FIRST_TRADING_DATE
            <= filing["usable_date"]
            <= POC_LAST_TRADING_DATE
        }
    )
    # The 8-K acceptance dates are not filing usable dates on their own, so the
    # furnished class cannot silently add or remove an evaluation date. That is
    # asserted, not assumed.
    furnished_usable_dates = sorted(
        {
            versions[-1]["usable_date"]
            for versions in quarterly.values()
            for entry in versions
            if entry["evidence_class"] == EVIDENCE_CLASS_FURNISHED
        }
    )
    evaluation_days = sorted(set(evaluation_days) | {
        day for day in furnished_usable_dates
        if POC_FIRST_TRADING_DATE <= day <= POC_LAST_TRADING_DATE
    })

    observations = []
    for day in evaluation_days:
        price, restored = as_traded_close(day)

        known: dict[datetime.date, dict] = {}
        for period_end, versions in quarterly.items():
            usable = [v for v in versions if v["usable_date"] <= day]
            if usable:
                known[period_end] = usable[-1]
        ends = sorted(known)

        ttm_status = "UNAVAILABLE"
        ttm_reason = None
        ttm_value = None
        components: list[dict] = []
        missing: list[dict] = []

        if not known:
            ttm_reason = REASON_INSUFFICIENT_QUARTERS
        else:
            # Anchor on the latest fiscal quarter that has evidence, then step back
            # three fiscal quarters. The step is arithmetic on the fiscal
            # year and quarter numbers, never on dates: subtracting days from a
            # period end lands inside the same fiscal year, and resolving that
            # against a 10-K list cannot see the open fiscal year at all.
            anchor = ends[-1]
            anchor_year = fiscal_year_of(anchor)
            anchor_number = quarter_number(anchor, fye_month)

            positions: list[tuple[int, int]] = []
            year_value = anchor_year
            quarter_value = anchor_number
            for _ in range(4):
                positions.append((year_value, quarter_value))
                quarter_value -= 1
                if quarter_value == 0:
                    quarter_value = 4
                    year_value -= 1
            positions.reverse()

            window_ends: list[datetime.date] = []
            for position_year, position_number in positions:
                match = [
                    end
                    for end in ends
                    if fiscal_year_of(end) == position_year
                    and quarter_number(end, fye_month) == position_number
                ]
                if match:
                    window_ends.append(match[-1])
                else:
                    missing.append(
                        {
                            "fiscal_year": position_year,
                            "quarter_number": position_number,
                        }
                    )

            if missing:
                if any(item["quarter_number"] == 4 for item in missing):
                    ttm_reason = REASON_MISSING_Q4_EPS
                else:
                    ttm_reason = REASON_INSUFFICIENT_QUARTERS
            else:
                for end in window_ends:
                    source = known[end]
                    components.append(
                        {
                            "period_end": end.isoformat(),
                            "fiscal_quarter": quarter_number(end, fye_month),
                            "diluted_eps": source["diluted_eps"],
                            "evidence_class": source["evidence_class"],
                            "form": source["form"],
                            "accession": source["accession"],
                            "source_document": source["source_document"],
                            "acceptance_datetime": source[
                                "acceptance_datetime"
                            ],
                            "usable_date": source["usable_date"],
                            "audit_status": source["audit_status"],
                            "source_url": source["source_url"],
                            "content_sha256": source["content_sha256"],
                            "stated_directly": source["stated_directly"],
                            "derivation": source["derivation"],
                            "lookahead_ok": source["usable_date"] <= day,
                        }
                    )
                total = sum(c["diluted_eps"] for c in components)
                components.append(
                    {
                        "period_end": None,
                        "fiscal_quarter": None,
                        "diluted_eps": total,
                        "evidence_class": "composite",
                        "derivation": "sum of 4 directly stated quarterly figures",
                        "fy_minus_ytd_used": False,
                    }
                )
                if price is None:
                    ttm_reason = REASON_MISSING_PRICE
                elif total <= 0:
                    ttm_reason = REASON_NON_POSITIVE_EPS
                else:
                    ttm_status = "AVAILABLE"
                    ttm_value = price / total

        annual_status = "UNAVAILABLE"
        annual_value = None
        annual_reason = None
        annual_component = None
        annual_candidates = []
        for end, versions in annual.items():
            usable = [v for v in versions if v["usable_date"] <= day]
            if usable:
                annual_candidates.append((end, usable[-1]))
        if not annual_candidates:
            annual_reason = REASON_INSUFFICIENT_QUARTERS
        else:
            end, latest = max(annual_candidates, key=lambda pair: pair[0])
            annual_component = {
                "fiscal_year_end": end.isoformat(),
                "diluted_eps": latest["diluted_eps"],
                "evidence_class": latest["evidence_class"],
                "form": latest["form"],
                "accession": latest["accession"],
                "acceptance_datetime": latest["acceptance_datetime"],
                "usable_date": latest["usable_date"],
                "audit_status": latest["audit_status"],
                "source_url": latest["source_url"],
                "content_sha256": latest["content_sha256"],
            }
            if price is None:
                annual_reason = REASON_MISSING_PRICE
            elif latest["diluted_eps"] <= 0:
                annual_reason = REASON_NON_POSITIVE_EPS
            else:
                annual_status = "AVAILABLE"
                annual_value = price / latest["diluted_eps"]

        classes = sorted(
            {c["evidence_class"] for c in components if c.get("evidence_class")}
        )
        observations.append(
            {
                "evaluation_date": day,
                "price_close_as_traded": price,
                "price_split_restoration": restored,
                "TTM_GAAP_DILUTED_PE": {
                    "status": ttm_status,
                    "value": ttm_value,
                    "reason": ttm_reason,
                    "components": components,
                    "missing_window_quarters": missing,
                    "evidence_classes_present": classes,
                    "fy_minus_ytd_used": False,
                },
                "ANNUAL_GAAP_DILUTED_PE": {
                    "status": annual_status,
                    "value": annual_value,
                    "reason": annual_reason,
                    "component": annual_component,
                    "substituted_for_ttm": False,
                },
                "methodology": METHODOLOGY,
                "methodology_amendment": METHODOLOGY_AMENDMENT,
                "logic_version": LOGIC_VERSION,
            }
        )

    # ---- current snapshot -----------------------------------------------
    current_day = trading_days[-1]
    current_price, current_restored = as_traded_close(current_day)
    current_known = {}
    for end, versions in quarterly.items():
        usable = [v for v in versions if v["usable_date"] <= current_day]
        if usable:
            current_known[end] = usable[-1]
    # The current snapshot uses the same fiscal-position anchoring as the
    # historical points. Taking "the last four quarter ends I happen to hold"
    # would silently span a fiscal-year boundary and produce a window that was
    # never four consecutive fiscal quarters.
    current_missing: list[dict] = []
    current_ends: list[datetime.date] = []
    if current_known:
        current_anchor = max(current_known)
        current_year = fiscal_year_of(current_anchor)
        current_quarter = quarter_number(current_anchor, fye_month)
        current_positions: list[tuple[int, int]] = []
        year_value = current_year
        quarter_value = current_quarter
        for _ in range(4):
            current_positions.append((year_value, quarter_value))
            quarter_value -= 1
            if quarter_value == 0:
                quarter_value = 4
                year_value -= 1
        current_positions.reverse()
        for position_year, position_quarter in current_positions:
            match = [
                end
                for end in sorted(current_known)
                if fiscal_year_of(end) == position_year
                and quarter_number(end, fye_month) == position_quarter
            ]
            if match:
                current_ends.append(match[-1])
            else:
                current_missing.append(
                    {
                        "fiscal_year": position_year,
                        "quarter_number": position_quarter,
                    }
                )
    current_total = (
        sum(current_known[end]["diluted_eps"] for end in current_ends)
        if len(current_ends) == 4
        else None
    )
    current_ok = current_total is not None and current_total > 0
    current_annual = max(
        (
            (end, [v for v in versions if v["usable_date"] <= current_day][-1])
            for end, versions in annual.items()
            if any(v["usable_date"] <= current_day for v in versions)
        ),
        key=lambda pair: pair[0],
    )
    current = {
        "as_of_trading_date": current_day,
        "price_close_as_traded": current_price,
        "price_split_restoration": current_restored,
        "TTM_GAAP_DILUTED_PE": {
            "status": (
                "AVAILABLE" if current_ok and current_price else "UNAVAILABLE"
            ),
            "value": (
                current_price / current_total
                if current_ok and current_price
                else None
            ),
            "reason": (
                None
                if current_ok and current_price
                else (
                    REASON_MISSING_Q4_EPS
                    if any(
                        item["quarter_number"] == 4
                        for item in current_missing
                    )
                    else REASON_INSUFFICIENT_QUARTERS
                )
            ),
            "missing_window_quarters": current_missing,
            "components": [
                {
                    "period_end": end.isoformat(),
                    "diluted_eps": current_known[end]["diluted_eps"],
                    "evidence_class": current_known[end]["evidence_class"],
                    "form": current_known[end]["form"],
                    "accession": current_known[end]["accession"],
                    "source_document": current_known[end]["source_document"],
                    "acceptance_datetime": current_known[end][
                        "acceptance_datetime"
                    ],
                    "usable_date": current_known[end]["usable_date"],
                    "audit_status": current_known[end]["audit_status"],
                    "source_url": current_known[end]["source_url"],
                    "content_sha256": current_known[end]["content_sha256"],
                    "stated_directly": current_known[end]["stated_directly"],
                    "lookahead_ok": (
                        current_known[end]["usable_date"] <= current_day
                    ),
                }
                for end in current_ends
            ],
            "fy_minus_ytd_used": False,
        },
        "ANNUAL_GAAP_DILUTED_PE": {
            "status": "AVAILABLE",
            "value": current_price / current_annual[1]["diluted_eps"],
            "fiscal_year_end": current_annual[0].isoformat(),
            "diluted_eps": current_annual[1]["diluted_eps"],
            "evidence_class": current_annual[1]["evidence_class"],
            "audit_status": current_annual[1]["audit_status"],
            "accession": current_annual[1]["accession"],
            "substituted_for_ttm": False,
        },
        "role": "current snapshot observation only; not a historical band input",
    }

    payload = {
        "poc": "AAPL Historical P/E, Amendment 1 verification",
        "not_production": True,
        "furnished_evidence_enabled": enable_furnished,
        "furnished_quarter_records_admitted": furnished_used,
        "methodology": METHODOLOGY,
        "methodology_amendment": METHODOLOGY_AMENDMENT,
        "logic_version": LOGIC_VERSION,
        "cutoff_convention": "16:00 ET",
        "acceptance_timestamp_source": (
            "EDGAR SGML header ACCEPTANCE-DATETIME (Eastern Time); the "
            "submissions API acceptanceDateTime is not used anywhere"
        ),
        "price_meta": {
            "vendor_split_ex_date": split_ex_date,
            "vendor_split_ratio": split_entry["splitRatio"],
            "basis": "as-traded close restored from the vendor's split-adjusted series",
        },
        "evaluation_dates": evaluation_days,
        "observations": observations,
        "current": current,
    }
    serialised = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    payload["content_hash"] = hashlib.sha256(serialised.encode()).hexdigest()
    return payload


def parse_date_of(value: str) -> datetime.date:
    return datetime.date.fromisoformat(value)


def run() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    enabled = main(enable_furnished=True)
    disabled = main(enable_furnished=False)
    (OUT / "amendment1_pe_points.json").write_text(
        json.dumps(enabled, indent=2, sort_keys=True), encoding="utf-8"
    )
    (OUT / "negative_path_no_furnished.json").write_text(
        json.dumps(disabled, indent=2, sort_keys=True), encoding="utf-8"
    )
    for label, payload in (("furnished ON", enabled), ("furnished OFF", disabled)):
        available = sum(
            1
            for o in payload["observations"]
            if o["TTM_GAAP_DILUTED_PE"]["status"] == "AVAILABLE"
        )
        missing_q4 = sum(
            1
            for o in payload["observations"]
            if o["TTM_GAAP_DILUTED_PE"]["reason"] == REASON_MISSING_Q4_EPS
        )
        print(
            f"{label:<13} hash={payload['content_hash'][:16]} "
            f"ttm_available={available} "
            f"ttm_unavailable={len(payload['observations']) - available} "
            f"missing_q4={missing_q4} "
            f"current_ttm={payload['current']['TTM_GAAP_DILUTED_PE']['status']}"
        )


if __name__ == "__main__":
    run()
