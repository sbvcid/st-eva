# ST-EVA 2.6 — Cross-Company Ingestion

Status: implemented and verified. Commit `6208a33` (pipeline), this stage adds
`tests/test_ingestion_cross_company.py`.
Issuers: AAPL, MSFT, MU, NVDA. TSM and NU deliberately excluded.
Live run needs `ST_EVA_LIVE=1`.

## The question

AAPL proved the chain. This asks whether it *generalises* — not "does AAPL
work" but "does the same code, the same registry and the same query surface
work unchanged for an issuer nobody designed for".

Four ordinary US-GAAP filers, chosen for what they differ in rather than for
being convenient: AAPL and MSFT have long histories under different revenue
tags, MU is a memory cycle-maker whose capex is equipment-dominated, NVDA files
under a third revenue tag again. Different fiscal calendars, different filing
counts, different concept mixes.

## Result

**The model generalises. One genuine limitation was found, and it is real.**

| | AAPL | MSFT | MU | NVDA |
|---|---|---|---|---|
| filings seen | 44 | 24 | 36 | 24 |
| source facts | 1,922 | 2,126 | 1,683 | 1,655 |
| second pass | 0 new, 1 fetch | 0 new, 1 fetch | 0 new, 1 fetch | 0 new, 1 fetch |
| revenue series | 338 pts | 338 pts | 309 pts | 308 pts |
| ingestion errors | none | none | none | none |

**7,386 observations across four issuers, 13 distinct source concepts, zero
unmapped concepts, zero duplicate `source_fact_id`, zero cross-issuer filing
collisions.** No issuer needed a metric of its own, a special code path, or a
different column.

That the vocabulary is 13 concepts for four filers is the load-bearing result.
If it grew with the company count, the registry would be accumulating
company-specific entries rather than describing a language.

## The finding: concept windows are global, but adoption is per filer

`metric_concept_mapping` carries one `effective_from` / `effective_to` window
per concept. The seed for those windows was derived from AAPL. Filers adopt
concepts on their own schedules, so a single global window is wrong for some of
them:

| concept | registry window | AAPL | MSFT | MU | NVDA |
|---|---|---|---|---|---|
| `Revenues` | 2016-09-24 → 2018-09-29 | 2016-09-24 → 2018-09-29 | **2007-09-30 → 2010-12-31** | 2016-09-01 → 2018-08-30 | **2008-01-27 → 2026-07-26** |
| `SalesRevenueNet` | 2007-09-29 → 2018-06-30 | 2007-09-29 → 2018-06-30 | 2009-06-30 → 2018-03-31 | 2008-12-04 → 2018-05-31 | — |
| `RevenueFromContract…` | 2017-09-30 → open | 2017-09-30 → open | **2016-06-30 → open** | 2017-08-31 → open | 2017-01-29 → 2022-01-30 |
| `PaymentsToAcquirePropertyPlantAndEquipment` | 2013-09-28 → open | 2013-09-28 → open | **2008-06-30 → open** | 2008-12-04 → open | 2010-01-31 → 2020-07-26 |
| `PaymentsToAcquireProductiveAssets` | 2007-09-29 → 2014-09-27 | 2007-09-29 → 2014-09-27 | — | — | **2019-10-27 → 2026-07-26** |

MSFT filed `Revenues` nine years before AAPL's window opens. NVDA still files it
in 2026, eight years after AAPL's window closed. **565 facts across the four
issuers fall outside a registry window**, and at the time of this run they were
reported `resolved: false` with `NOT_EXPLAINED` — true of the table, false about
MSFT.

**Resolved in 2.5.1** by separating a concept's meaning from a filer's use of it:
`issuer_concept_adoption` records `OBSERVED_ADOPTION` per filer, and resolution
consults it. All four filers' revenue series now resolve completely, with
PARTIAL fidelity and the series breaks untouched. See
[ST-EVA-2.5.1-HARDENING.md](ST-EVA-2.5.1-HARDENING.md).

The lesson stands regardless of the fix: a window on a concept is a claim about
an observed filer, and one company's filing history is not a general rule.

## A second, smaller limitation: filings held vs filings known

`held_filings` is populated from the submissions index, which only carries
recent filings. The company-concept endpoint reaches much further back. So:

- AAPL: facts span 2006-09-30 → 2026-07-17; the index starts 2015-10-28
- **4,065 of 7,386 facts (55%) reference an accession the ledger has not seen**

The archive still holds those facts correctly, and nothing is missing. But a
filing that predates the index is not in the incremental ledger, so a *future*
amendment to it would be ingested as if new — which is right — while a
restatement detected only through the index would be missed if the index no
longer lists the original. Not a defect today; a limit on how far back
"incremental" is meaningful, and worth stating before the archive is expected to
be authoritative for a decade of history.

**Made mechanical in 2.5.1:** `Ingestor.coverage(ticker)` reports the evidence
span and the ledger span side by side with `ledger_covers_all_evidence: false`,
rather than leaving the distinction in prose.

## A third observation, in the sealed query surface

`get_metric_history` applied a default limit of 200 and reported
`point_count: 200` for a series that actually holds 338 points. A caller that
did not pass `limit` could not distinguish a truncated series from a complete
one — `point_count` reported the page size, not the series length.

**Fixed in 2.5.1:** `point_count` is the series length, with `returned_count`,
`truncated` and a `truncation_note` alongside, plus a `page()` method for
walking a series with a cursor. It mattered more once the archive held a decade:
an LLM reading `point_count` would have believed it had the whole series when it
had 59% of it.

## What was checked, and where

`tests/test_ingestion_cross_company.py`, 22 tests (17 need `ST_EVA_LIVE=1`):

- every issuer ingests with no error and no special handling
- no issuer needs its own metric; the written metrics are exactly the seeded set
- every concept reaching storage has a registry mapping, for every issuer
- four issuers share ≤ 16 distinct concepts
- one accession is never held under two issuers
- no `source_fact_id` collision anywhere; every identity reproducible from the
  fact's own coordinates
- an amendment is a new filing, not a change to an old one
- fiscal year is whatever the filer declared; units and currency stay separate
  (a ratio is never given a currency)
- a single regulator is never treated as corroboration
- a second pass over all four changes nothing and fetches once per issuer
- re-ingesting one issuer does not disturb the others
- every issuer is queryable and every figure traces to accession, concept,
  fact id, and document hash
- a concept outside its window is reported unresolved, never guessed

Offline (no network): filing identity across issuers and forms; a restatement
by a different filer is a different fact; the registry has no issuer dimension
and is not required to know the company.

## Scope

Four ordinary US-GAAP filers passing is evidence the model is not shaped around
AAPL. It is not evidence of coverage.

Deferred deliberately: **TSM** (IFRS / 20-F / ADR) and **NU** (banking
semantics). Both are good stress tests, and a stress test run before the basic
case generalises tends to reshape the model for the exception. They are next,
after the per-issuer adoption record is decided — because TSM's IFRS concepts
will hit the window limitation head-on, and it is better to have fixed the shape
than to have learned it under pressure.
