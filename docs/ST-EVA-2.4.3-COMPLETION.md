# ST-EVA 2.4.3 — completion note

> **歷史資料／非現行指令。** 本文件只記錄撰寫時的設計、狀態、計畫或決策，不具有授權、禁止、限制或要求未來工作的效力。文中任何「binding」「frozen」「approved」「not authorized」「must」等措辭均為歷史內容，不得凌駕使用者目前的要求。當前狀態以現行程式碼、測試及實際 Git 狀態為準。
>
> **HISTORICAL ARCHIVE — NOT CURRENT INSTRUCTIONS.** This document records prior design, status, plans, or decisions. It does not grant, deny, restrict, or require work. Any “binding,” “frozen,” “approved,” “not authorized,” or “must” wording below is historical and does not override the user's current request. Determine current state from current source code, tests, and Git state.

Prepared as a sealing pass: verify only, plus the one S2 wiring gap the pass
found. No functional change was made beyond that gap.

## Commit

| | |
|---|---|
| HEAD | see the final report; this note is committed with the S2 fix |
| Parent | `95373eb` "2.4.3 Fix what the consumption experiment found" |
| Base commit | `46e05d3` |

Five untracked `history/*.json` files predate this work: they are dated
2026-09-26, three days before the 2.3-A commit, and are engine snapshot output
from runs made before this effort began. 17 `history/*.json` are tracked. Left
untouched.

## Schema version

`context_schema_version = 2.3-C.2` (MINOR bump from `2.3-C.1`).

## Tests

`python -m unittest discover -s tests` → **318 tests, OK, 8 skipped, 0 failures.**

| Phase | Module | Result |
|---|---|---|
| built-in regression | `st_eva_runner.py --test` | 6/6 `[PASS]`, `ALL TESTS PASSED` |
| 2.3-A data contract | `tests/test_data_contract.py` | 50 tests, 1 skipped |
| 2.3-B cross-source | `tests/test_sec_validation.py` | 59 tests, 3 skipped |
| 2.3-C context | `tests/test_investment_context.py` | 70 tests, OK |
| 2.4 archive / replay | `tests/test_archive_replay.py` | 64 tests, 4 skipped |
| 2.4.2 findings | `tests/test_material_findings.py` | 26 tests, OK |
| 2.4.3 findings | `tests/test_2_4_3_traceability.py` | 21 tests, OK |

318 is 313 plus the 5 new S2 coverage tests. The 8 skips are the three
opt-in live classes, gated on `ST_EVA_LIVE=1`: `TestLiveAdapters` (3),
`TestLiveArchive` (4), `TestLiveContexts` (1). Skipped by design, not failure.

The line `[ST-EVA] Yahoo acquisition failed for THIS_TIC
KER_SHOULD_NOT_EXIST_XYZ: HTTP Error 404: Not Found` on stderr during the suite
is `test_unknown_ticker` exercising the failure path deliberately.

## Regression results

2.2.3 contract, compared against baselines captured from the 2.2.3 build
before any of 2.3-A:

| Artifact | Result | Size |
|---|---|---|
| `MSFT --json` | **byte-identical** | 8,864 bytes |
| `TENCENT --json` | **byte-identical** | 8,914 bytes |
| `NU --json` | **byte-identical** | 8,842 bytes |
| `MSFT --reference-multiple 30` report | **byte-identical** | 7,316 bytes |

## Smoke test

Three live contexts through the ordinary pipeline
(`--mode live --no-snapshot --context`), no traceback, no undefined name, no
serialisation error:

| Context | Bytes | refs | derivations | validation states | discontinuities | restatement pairs |
|---|---|---|---|---|---|---|
| AAPL | 396,985 | 196 | 16 | all `UNVALIDATED` | 5 | 3 |
| NU | 150,695 | 64 | 16 | all `UNVALIDATED` | 0 | 0 |
| NVDA | 406,693 | 200 | 16 | all `UNVALIDATED` | 9 | 4 |

## The three 2.4.3 fixes

**28 of 28 verification checks pass.**

**S1 — series comparability. PASS.**

- Points are differenced only within a group sharing period span, observation
  type, and construction. Spans observed: `ANNUAL`, `QUARTERLY`, `INSTANT`.
- Mixed-span metrics are `NOT_COMPARABLE` with
  `series_status_reason: PERIOD_SPAN_MISMATCH`: NVDA `revenue`, `net_income`,
  `eps_diluted`.
- Every discontinuity names the `series_group` it was computed inside, and none
  has `from_period == to_period`. Two versions of one period are reported
  separately as restatement pairs.
- **NVDA's 2.94x debt move is preserved**: `series_status COMPARABLE`,
  `relative_change 2.939`, still `NOT_EXPLAINED_BY_ST_EVA`.

**S2 — machine-readable refusal reasons. PASS, after the sealing pass.**

Three call sites were wired to codes that already existed in the vocabulary. No
`reason_kind` and no `reason_code` was added, and `REASON_KINDS` (7) and
`REASON_CODES` (8) are unchanged, which a test now asserts by size and by
membership.

| Site | `reason_kind` | `reason_code` |
|---|---|---|
| observation not reported | `NOT_REPORTED_BY_SOURCE` | `SOURCE_DID_NOT_REPORT` |
| no eligible reference | `NO_REFERENCE_AVAILABLE` | `REFERENCE_NOT_AVAILABLE` |
| percentile, band too thin | `INSUFFICIENT_OBSERVATIONS` | `SERIES_TOO_THIN` |
| derived, input unavailable | `MISSING_INPUT` | `INPUT_OBSERVATION_UNAVAILABLE` |
| derived, non-positive divisor | `NEGATIVE_INPUT` | `NON_POSITIVE_DENOMINATOR` |
| derived, unexplained absence | `NOT_AVAILABLE` | `ENGINE_PRODUCED_NO_VALUE` |

The third row is a **pre-existing mismatch the new coverage tests found, not a
regression**: percentile refusals carried
`reason_kind: INSUFFICIENT_OBSERVATIONS` with
`reason_code: INPUT_OBSERVATION_UNAVAILABLE`, which says the opposite of the
kind. The input observation is present and usable; the series behind it is too
thin. `SERIES_TOO_THIN` existed in the vocabulary and was unused. Fixing it was
required to satisfy "C: derived-figure refusal keeps its existing
reason_kind + reason_code", not as an addition.

Every `reason_kind` in the three smoke contexts now maps to exactly one code,
with none missing. NU's `current_pfcf` reads:

```json
{"item": "current_pfcf",
 "ref": "der:current_pfcf",
 "reason_kind": "NEGATIVE_INPUT",
 "reason_code": "NON_POSITIVE_DENOMINATOR",
 "operand_position": 1,
 "input_ref": "obs:ev-fcf-001",
 "input_value": -1669966000.0,
 "condition": "DIVISOR_MUST_BE_POSITIVE",
 "blocks": [],
 "reason": "not computable: operand 1 (obs:ev-fcf-001) is -1669966000.0, and
            a ratio over a non-positive figure has no interpretation. The
            observation itself is present and is not treated as missing."}
```

**S3 — figure-level traceability. PASS.**

- `current_pe` carries `UNDATED_INPUT` and `UNVALIDATED_INPUTS`.
- Flags are pointers, not copies: 443 bytes, with no freshness or validation
  block duplicated into them.
- `state_flags` is present only when non-empty, across 32 figures. No empty
  arrays are emitted.

## Known limitations

1. **`MU` had 22 reported discontinuities before 2.4.3 and 21 after.** Only one
   was spurious. The rest are within a single comparable series and are genuine
   reported movements, correctly left unexplained. A reader who treats a high
   count as evidence of a defect will be wrong about MU.
2. **The vendor's forward EPS and consensus forward EPS share a value in every
   context tested**, so `forward_pe` and `consensus_forward_pe` are equal. They
   are reported as two figures with two operand pairs, not collapsed.
3. **`UNDATED_INPUT` appears on most figures** because the market-data source
   declares no publication time for its fundamentals. Accurate, and the same
   limitation 2.3-B documented, not a new one.
4. **An archive written by `2.3-C.1` and replayed by `2.3-C.2` will report
   `DIVERGED`**, because the document shape changed. Correct for a changed
   document. Experiment 001's pinned inputs remain `2.3-C.1`; Experiment 002
   must choose deliberately which version it feeds an agent.
5. **8 live tests are skipped** unless `ST_EVA_LIVE=1`.
6. **All 16 derived figures in all three smoke contexts are `UNVALIDATED`**, and
   that is the 2.4.2 behaviour working: validations judge comparable
   observations, derivations consume material ones. Recorded in experiment 001
   as a presentation gap and **not** fixed by 2.4.3, which was scoped to three
   items. Every derived figure now carries `UNVALIDATED_INPUTS` saying so.

## Status

**2.4.3 is SEALED.** All three scoped items verified, S2 completed, the
2.2.3 contract byte-identical, 318 tests passing. The next stage is
Experiment 002, to be run in a new workspace against a `2.3-C.2` baseline.

