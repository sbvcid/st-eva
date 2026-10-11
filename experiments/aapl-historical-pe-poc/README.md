# AAPL Historical P/E — Proof of Concept

**Status:** POC only. Not production. Nothing here is imported by ST-EVA Core.

**Methodology baseline:** `docs/ADR-HISTORICAL-PE-METHODOLOGY.md` (APPROVED / FROZEN).
The ADR was not modified by this POC.

## Scope boundaries honoured

- No generic Historical P/E engine was implemented.
- No change to ST-EVA Core, the web app, valuation/admission/replay contracts.
- No new provider was added; the only price source is the Yahoo chart API that
  `st_eva_runner.py` already calls, and the only filing source is SEC EDGAR.
- No Corporate Action schema was decided.
- All output lives in this directory and in `out/`.

## Pipeline

| Stage | Script | Purpose |
| --- | --- | --- |
| 1 | `fetch_raw.py` | Freeze submissions index, `EarningsPerShareDiluted` concept, daily prices |
| 2 | `fetch_filing_headers.py` | Per-filing EDGAR SGML header: `ACCEPTANCE-DATETIME` (ET), `FILED AS OF DATE`, period of report, fiscal year end |
| 3 | `compute_historical_pe.py` | Point-in-time EPS state, usable dates, TTM / Annual / Current P/E, provenance, content hash |
| 4 | `report.py` | Observation table, CSV, counts |
| 5 | `verify.py` | 11 independent ADR conformance checks |
| 6 | `replay_determinism.py` | Double-run hash equality plus a third independent recomputation |

Run order: `fetch_raw.py` → `fetch_filing_headers.py` → `compute_historical_pe.py`
→ `report.py` → `verify.py` → `replay_determinism.py`.

## Findings that shaped the implementation

### The submissions API timestamp is not the timestamp the ADR names

`data.sec.gov` submissions returns `acceptanceDateTime` with a `Z` suffix.
EDGAR's own SGML header `ACCEPTANCE-DATETIME` carries the same filing's
acceptance instant with **no** suffix, and it is **Eastern Time**. Measured
across 43 filings, the API value sits exactly 4h (EDT) or 5h (EST) later than
the header value.

The header value is independently validated by EDGAR's own filing-date rule: a
filing accepted after 17:30 ET takes the next business day as
`FILED AS OF DATE`. All 43 filings satisfy this reading and none satisfy the
alternative, so the header timestamp is the one used for the 16:00 ET cutoff.

Had the API value been taken as UTC, filings accepted at 16:31 ET would have
been read as 21:31 ET and pushed one trading day too late. This is a real
methodology hazard, not a cosmetic one.

### Sampling is event-driven, and that is a POC choice, not a decision

Evaluation dates are the usable dates of 10-Q/10-K filings. Daily / weekly /
monthly sampling remains OPEN under ADR §4.3; the POC only needed enough real
dates to exercise the state machine.

### TTM anchoring is on fiscal position, not on "the last four dates held"

The trailing window is anchored on the latest fiscal quarter with a directly
filed quarter-length diluted EPS fact, then extended back over that quarter's
three fiscal predecessors. Anchoring on fiscal positions is what makes a
missing Q4 surface as `REASON_MISSING_Q4_EPS` instead of silently shortening
the window to three known quarters and reporting a wrong TTM.

### AAPL's Q4 evidence stops exactly where the ADR predicted

AAPL's 10-Ks carried a quarterly diluted EPS table through the FY2020 10-K.
From the FY2021 10-K onward there is no quarter-length fact for the September
quarter, and no 8-K supplies one either. So the last TTM that can be built
without subtraction is the one ending FY2020 Q4, usable from 2020-10-30, and
every TTM from 2022-01-28 onward is `REASON_MISSING_Q4_EPS`.

### Stock split handling without a Corporate Action schema

AAPL split 4:1 with ex-date 2020-08-31. The Yahoo `close` field is already
restated across that split, and so are the later-filed EPS figures (FY2018
diluted EPS appears as both 11.91 and 2.98 in the evidence).

The POC pairs **as-traded close** with **EPS as filed at that date**. For any
date before the ex-date, the vendor's split-adjusted close is multiplied back
by 4, restoring the price that was actually quoted on that day, and the EPS in
use at that date is the pre-split figure the issuer reported then. Both sides of
the ratio are on the contemporaneous basis, so no Corporate Action schema is
needed and the split itself never becomes an unexplained adjustment factor.

This is POC-level, explicit and per-point traceable (`price_split_restoration`
on each observation). It does **not** specify a Corporate Action evidence
schema, which stays OPEN under ADR §4.2.

## What is deliberately not decided here

- Reference Sufficiency thresholds (count / time span / fiscal-quarter coverage) — OPEN.
- Corporate Action evidence schema — OPEN.
- Sampling frequency — OPEN.
- Annual P/E fallback policy for FPIs — OPEN.
- The 20-observation Core threshold was not touched.

## Outputs

- `out/historical_pe_points.json` — every point with full provenance and a content hash.
- `out/historical_pe_points.csv` — flat per-date table.
- `out/report.txt` — observation table and counts.
- `out/verification.txt` — 11 conformance checks.
- `out/determinism.txt` — double-run hash equality and independent recomputation.
- `raw/` — frozen inputs with sha256 manifest, plus per-filing EDGAR headers.
