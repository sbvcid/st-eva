# Amendment 1 Verification — AAPL TTM Q4 Unblocking

**Status:** Verification only. Not production. Nothing here is imported by ST-EVA.

**Methodology:** `docs/ADR-HISTORICAL-PE-METHODOLOGY.md`, Amendment 1
(Decisions 10–14). The ADR was not modified by this verification.

**Question:** with the furnished evidence class admitted, does AAPL
`TTM_GAAP_DILUTED_PE` become available for every evaluation date, and does
everything the original POC proved still hold?

## Headline

| Metric | Prior POC | Furnished OFF | Furnished ON |
| --- | --- | --- | --- |
| Evaluation dates | 31 | 31 | 31 |
| TTM AVAILABLE | 12 | 12 | **31** |
| TTM UNAVAILABLE | 19 | 19 | **0** |
| `REASON_MISSING_Q4_EPS` | 19 | 19 | **0** |
| ANNUAL AVAILABLE | 31 | 31 | 31 |
| CURRENT TTM | UNAVAILABLE | UNAVAILABLE | **AVAILABLE** |
| CURRENT ANNUAL | AVAILABLE | AVAILABLE | AVAILABLE |

The `furnished OFF` column is the negative path: the same code with the
furnished evidence class switched off. It reproduces the prior POC on all 31
dates, byte for byte on status, reason and value. So the entire change is
attributable to admitting the evidence path, and to nothing else.

## Two behaviours worth reading carefully

**2021-10-29 changes value, not just status.** In the prior POC this date was
`AVAILABLE` at 29.32, using the window ending FY2021 Q3
(0.73 + 1.68 + 1.40 + 1.30). With the furnished Q4 admitted, the latest known
quarter becomes FY2021 Q4, so the window shifts forward to FY2021 Q1–Q4
(1.68 + 1.40 + 1.30 + 1.24 = 5.62) and the P/E becomes 26.65. Both are correct;
they are TTM values at different anchor points. This is the window-anchoring
rule working as specified, not a regression.

**`CURRENT_PE` TTM becomes AVAILABLE.** The run-instant window
(FY2025 Q4 furnished + FY2026 Q1–Q3 filed) is now complete. Previously it
reported `REASON_MISSING_Q4_EPS`.

## Evidence mixing, as observed

20 of 31 dates use exactly `filed ×3 + furnished ×1`, for example 2025-10-31:

| Quarter | EPS | Class | Form | Accession | Acceptance (ET) | Usable | Audit |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2024-12-28 Q1 | 2.40 | filed | 10-Q | 0000320193-25-000008 | 2025-01-31 06:01:27 | 2025-01-31 | unaudited_reviewed |
| 2025-03-29 Q2 | 1.65 | filed | 10-Q | 0000320193-25-000057 | 2025-05-02 06:00:46 | 2025-05-02 | unaudited_reviewed |
| 2025-06-28 Q3 | 1.57 | filed | 10-Q | 0000320193-25-000073 | 2025-08-01 06:00:42 | 2025-08-01 | unaudited_reviewed |
| 2025-09-27 Q4 | 1.85 | **furnished** | **8-K** | 0000320193-25-000077 | 2025-10-30 16:30:35 | 2025-10-31 | **unaudited** |

Denominator 7.47, price as-traded 270.37, TTM P/E 36.1941.

Note the three filed quarters all use `unaudited_reviewed`, not `audited`: 10-Q
interim statements are reviewed. Only 10-K annual figures carry `audited`, and
`ANNUAL_GAAP_DILUTED_PE` is verified to draw on 10-K audited evidence only.

## A defect found and fixed during this verification

The fiscal-window walk-back originally stepped across a fiscal year boundary by
subtracting ~370 days from a period end and re-resolving it against the list of
10-K period ends. For the open fiscal year that list has no entry, so the
resolution fell through to the most recent 10-K and relabelled every quarter of
the open year as belonging to the previous one. The symptom was a TTM window
containing a 455-day hole, published at 2026-01-30, 2026-05-01 and 2026-07-31.

Fiscal position is now derived from each quarter's own period end and the
fiscal year end month the issuer declares in its own 10-K SGML header. The
verification asserts four consecutive fiscal quarters containing a Q4 with no
gap over 120 days, which is what caught this. The same defect is worth checking
for in any future implementation.

## Pipeline

| Stage | Script | Purpose |
| --- | --- | --- |
| 1 | `compute_amendment1_pe.py` | Recompute with furnished admitted, and again with it disabled |
| 2 | `verify_amendment1_pe.py` | 19 conformance checks including the negative path and a third computation path |
| 3 | `report_amendment1_pe.py` | Prior-vs-current table, required-date detail, CSV |

No network access. Inputs are the previously frozen raw bytes, hash-checked
before use, so the comparison is against the same inputs both times.

## Checks that matter most

- **Lookahead** — every component, in every point and in the current snapshot,
  has `usable_date <= evaluation_date`, and every usable date is re-derived from
  its own acceptance timestamp under the 16:00 ET rule.
- **No API timezone leakage** — no acceptance timestamp in the output ends in
  `Z`. Everything comes from the SGML header.
- **Semantic separation** — no furnished component is labelled `filed`, `10-K`,
  `10-Q` or `audited`; no 8-K is labelled `filed`; annual evidence is 10-K
  `audited` only; annual is never substituted for TTM.
- **No FY − YTD** in either path.
- **No window truncation** — no TTM published from fewer than four quarters.
- **Negative path** — matches the prior POC on all 31 dates.
- **Third path** — re-extracts furnished figures from the exhibit HTML and
  re-resolves filed figures by accession, then recomputes every denominator.
- **Replay** — two process runs, identical content hash.

## Not decided here

- Whether `XBRL fact unavailable` becomes an observable attribute or a reason
  code. Still OPEN per §6.1.
- Reference Sufficiency, Sampling Frequency, Corporate Action schema, FPI
  fallback. All still OPEN; the 20 / 24 observation requirement is untouched.
- Whether 31 observations across 7.5 years is sufficient. This verification says
  nothing about sufficiency; it only says the values are now constructible.

## Outputs

- `out/amendment1_pe_points.json` — the run with furnished evidence admitted.
- `out/negative_path_no_furnished.json` — the same code with furnished disabled.
- `out/verification.txt` — 19 conformance checks.
- `out/prior_vs_current.txt` / `.csv` — comparison table and required-date detail.
