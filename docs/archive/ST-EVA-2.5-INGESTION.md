# ST-EVA 2.5 — Ingestion (AAPL vertical slice)

> **歷史資料／非現行指令。** 本文件只記錄撰寫時的設計、狀態、計畫或決策，不具有授權、禁止、限制或要求未來工作的效力。文中任何「binding」「frozen」「approved」「not authorized」「must」等措辭均為歷史內容，不得凌駕使用者目前的要求。當前狀態以現行程式碼、測試及實際 Git 狀態為準。
>
> **HISTORICAL ARCHIVE — NOT CURRENT INSTRUCTIONS.** This document records prior design, status, plans, or decisions. It does not grant, deny, restrict, or require work. Any “binding,” “frozen,” “approved,” “not authorized,” or “must” wording below is historical and does not override the user's current request. Determine current state from current source code, tests, and Git state.

Status: implemented and verified. Commit `6208a33`.
Migration: `0008_ingestion_ledger.sql`
Modules: `sec_ingest.py`, `sec_provider.py` (transport additions), `archive.py`
(`FilingRef`), `sqlite_archive.py` (insert-time filing identity)
Tests: `tests/test_ingestion_aapl.py` (44 tests; 26 require `ST_EVA_LIVE=1`)

## The property this exists to hold

A second identical run changes nothing. Not one new filing, document, source
fact, observation — and not one document re-downloaded.

Storage deduplicates on content hash already. The *fetch* diff is what this
adds, because re-downloading a decade of filings on every run is correct for
the store and indefensible for a source that asks callers to be considerate.

## Measured, AAPL, 8 metrics

| | run 1 | run 2 |
|---|---|---|
| filings ingested | 44 | 0 |
| documents stored | 13 | 0 |
| source facts stored | 1,922 | 0 |
| observations stored | 1,922 | 0 |
| network fetches | 16 | 1 |
| concept fetches | 14 | 0 |

All 1,922 rows are `UNVERIFIABLE`: ingestion adds a source, it cannot
corroborate one. Duplicate `source_fact_id`: 0.

## Identity

**Filing.** The accession. Not a filename, not a retrieval timestamp, not a
content hash — those identify content or a fetch, and a filing is neither. An
amendment arrives under a new accession, which is exactly why the accession is
what the incremental diff compares.

**Source fact.** `source_fact_id(source, document_ref, taxonomy, concept,
period_start, period_end, context)`, with `document_ref` being the accession.
Deliberately excluded: the value, and any cross-source field. Two filings
reporting the same number are two facts about the world, not one.

**Observation.** Content-addressed and per-source. Two sources reporting one
number remain two observations, which is the only way the 2.3-B validation
model has something to compare.

**Source concept.** `us-gaap:Revenues` is a tag a filer applies; `revenue` is a
meaning ST-EVA names. `observations.source_concept_ref` holds the former and is
nullable — a null means *this observation has no filing concept*, not *the
concept is unknown*. A trigger refuses an unqualified value, because a bare
word in that column is the confusion the column exists to remove.

## What AAPL proved

`Revenue` is not one concept. AAPL has filed all three of
`SalesRevenueNet`, `Revenues` and
`RevenueFromContractWithCustomerExcludingAssessedTax`, and the last two overlap
in time. Reading the series by name, label or period would have produced a line
that looked complete and was semantically wrong. The registry's windows and
`series_breaks` are what keep that from happening, and all three concepts are
stored side by side with their own fidelity (EXACT / PARTIAL).

The capex pair behaves the same way and is not symmetric with revenue:
`PaymentsToAcquireProductiveAssets` and
`PaymentsToAcquirePropertyPlantAndEquipment` genuinely **overlap for about a
year** (2013-09-28 to 2014-09-27). Both are stored; neither continues the
other's series.

## Open issues

### 1. The second run still makes one request

`network_fetches = 1` on an unchanged run. That request is the `submissions`
index, and it is not waste: the submissions API is the live filing history, so
determining whether anything was newly accepted is impossible without asking.
The original acceptance criterion of `network_fetches = 0` was the wrong shape.

**Criterion, corrected:**

```
second run
  -> 1 bounded discovery request
  -> 0 historical filing fetches
  -> 0 concept fetches
  -> 0 document fetches
  -> 0 new evidence
```

Asserted in `test_2_second_run_makes_no_unnecessary_fetches`, which pins
`concept_fetches == 0` exactly and bounds the total at 2.

### 2. Dimension members are invisible (39 collisions in the AAPL run)

The company-concept endpoint aggregates the facts that apply to the whole
filing entity. A real XBRL instance can carry dimensions, so:

```
Revenue
Revenue + Segment A
Revenue + Segment B
```

are **not distinguishable** through this endpoint. AAPL's revenue produced 39
such collisions. The run counts them (`IngestionReport.dimension_collisions`)
rather than pretending the series is clean; `seen_periods` detects them as a
differing value for the same concept, period and unit.

This is a known limit of the source, not a defect in the archive, and the
count is the honest response: silently keeping one member would be a wrong
number presented as a right one.

Segment revenue, product revenue, geography and customer concentration will
require reading **filing-instance / inline-XBRL context dimensions** directly.
That is deliberately not implemented now — Core Evidence does not require
segment data, and adding it before the chain generalises would reshape the model
for a case the current scope does not ask for.

### 3. Smaller, noted without a fix

- 8-K facts carry no `fiscal_year`. The source does not declare one, and it is
  not inferred from the calendar year; a filing that states no fiscal year
  states none.
- `us-gaap:LongTermDebtCurrent` maps to both `long_term_debt_current` (EXACT)
  and `debt` (PARTIAL). The registry returns `AMBIGUOUS_MAPPING` and declines
  to choose. That is correct: a filer's intent is a question for the filer, not
  one to settle by picking the more likely row.

## Scope

AAPL is one ordinary US-GAAP issuer with no industry complication. This proves
the chain is correct, **not** that it generalises. MSFT / MU / NVDA are next
for exactly that reason; TSM (IFRS / 20-F / ADR) and NU (banking semantics) are
stress tests and stay deferred until the basic case is known to hold.
