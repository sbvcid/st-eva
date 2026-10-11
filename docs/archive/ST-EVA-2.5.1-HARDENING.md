# ST-EVA 2.5.1 — Semantic Adoption and Query Completeness

> **歷史資料／非現行指令。** 本文件只記錄撰寫時的設計、狀態、計畫或決策，不具有授權、禁止、限制或要求未來工作的效力。文中任何「binding」「frozen」「approved」「not authorized」「must」等措辭均為歷史內容，不得凌駕使用者目前的要求。當前狀態以現行程式碼、測試及實際 Git 狀態為準。
>
> **HISTORICAL ARCHIVE — NOT CURRENT INSTRUCTIONS.** This document records prior design, status, plans, or decisions. It does not grant, deny, restrict, or require work. Any “binding,” “frozen,” “approved,” “not authorized,” or “must” wording below is historical and does not override the user's current request. Determine current state from current source code, tests, and Git state.

Status: implemented and verified.
Migration: `0009_issuer_concept_adoption.sql`
Modules: `core_registry.py`, `evidence_query.py`, `sec_ingest.py`
Tests: `tests/test_hardening_2_5_1.py` (26, all offline), plus updated
`tests/test_ingestion_cross_company.py`

## Why this stage exists

The cross-company run passed on identity, storage, concept resolution and
idempotence. Two defects survived it, and both are the kind that only appear
once more than one company is in the archive.

Neither is a new feature. Both are a promise the query surface was making and
not keeping.

## 1. A concept's meaning and a filer's use of it were one row

### What was wrong

`metric_concept_mapping` carried one `effective_from` / `effective_to` window
per concept, seeded from AAPL, and resolution filtered on it. But a window on a
*concept* is a claim about the filer who was observed, not about the concept:

| concept | seeded window | AAPL | MSFT | MU | NVDA |
|---|---|---|---|---|---|
| `Revenues` | 2016-09-24 → 2018-09-29 | matches | **2007-09-30 → 2010-12-31** | 2016-09-01 → 2018-08-30 | **2008-01-27 → 2026-07-26** |
| `PaymentsToAcquirePropertyPlantAndEquipment` | 2013-09-28 → open | matches | **2008-06-30 → open** | 2008-12-04 → open | 2010-01-31 → 2020-07-26 |
| `PaymentsToAcquireProductiveAssets` | 2007-09-29 → 2014-09-27 | matches | — | — | **2019-10-27 → 2026-07-26** |

**565 facts across the four filers were reported unmapped.** The reason given
was `NOT_EXPLAINED. No registry mapping relates this concept to a metric` —
which was true of the table and false about MSFT. One company's filing history
was wearing a general rule's clothes.

Widening the window would have "fixed" the symptom by deleting the distinction
and made a single company's observation look like a semantic fact.

### The separation

```
metric_concept_mapping     what a concept means, and how faithfully
issuer_concept_adoption    what one filer was observed doing with it
```

`issuer_concept_adoption` is derived by ingestion from the periods a filer's own
filings actually reported, and is labelled `OBSERVED_ADOPTION` — closed by
trigger, because the evidence supports exactly that claim and no stronger one.
A filer that stopped reporting in 2018 is recorded as having stopped reporting
in 2018, **not** as having retired the concept. Absence of a fact is not a
decision to stop.

The record carries `fact_count` and `filing_count` so a window derived from two
facts is visibly different from one derived from two hundred, and no adoption
record at all means *not observed* — a gap in what we hold, never a claim that
the filer did not use the concept.

Re-observation widens and sums; it never narrows, so a later run covering more
history extends what is known rather than silently retracting the first.

### How resolution uses it

`resolve(concept, as_of, asset_id)` consults adoption when it covers the period.
The filer is passed in from the query surface, which is the **only** place in
the read path that knows the issuer — the semantic layer stays filer-agnostic.

Three properties, each tested:

- **Adoption governs *when*; the mapping governs *how faithfully*.** A PARTIAL
  concept is still PARTIAL after adoption widens its window, and still breaks
  the series. Adoption can never promote a wider aggregate into the same series
  as a narrower one.
- **Adoption is bounded by what was observed.** A period outside the recorded
  window does not resolve. Extending to an unobserved period would be inference
  dressed as evidence.
- **A closed window is not a contradiction.** This was the subtle one. A window
  that closes records *that filer's last period*, not a statement that the
  concept stopped existing. An earlier draft of this treated `effective_to` as a
  hard boundary and left NVDA's 90 post-2018 facts unresolved — reintroducing
  the original defect in a stricter shape. A real filing from the filer being
  asked about is better evidence than another filer's inferred boundary.

Every figure that resolves outside its concept's window says so:
`adopted_outside_mapping_window: true`, with the adoption evidence attached.

### Result

| | before | after |
|---|---|---|
| revenue rows unresolved, AAPL | 0 | 0 |
| revenue rows unresolved, MSFT | 38 | **0** |
| revenue rows unresolved, MU | 2 | **0** |
| revenue rows unresolved, NVDA | 90 | **0** |

Fidelity unchanged: MSFT 204 PARTIAL / 134 EXACT, NVDA 280 PARTIAL / 28 EXACT,
all four series still report their two PARTIAL breaks. The figures are now
readable *and* still marked as what they are.

## 2. A truncated series reported the page size as the series length

### What was wrong

`get_metric_history` applies a default limit of 200 and reported
`point_count: 200` for AAPL's 338-point revenue series. A reader — human or LLM
— has no way to tell that from a complete answer. It is the worst kind of wrong
in an evidence database: a JSON document that looks finished and is not.

### The fix

`point_count` is now the size of the series, not of the response:

```json
{
  "point_count": 338,
  "returned_count": 200,
  "truncated": true,
  "truncation_note": "This series holds 338 points and this response carries 200. The series is not complete; ask again with a higher limit or page through `page()` to reach the rest."
}
```

`truncated` is false and `truncation_note` is null when nothing was dropped. A
flag that is always on teaches a reader to ignore it, which is the opposite of
what it is for.

`page()` returns `total_count`, `returned_count`, `truncated` and an opaque
`next_cursor`, and pages through a series until every point has arrived exactly
once. Cursors are validated rather than trusted: a forged or empty cursor is a
malformed query, not an empty page. Silently accepting `""` would let a caller
that lost its cursor believe it had read the whole series while holding the
first page of it.

`query_observations` keeps its list return and its silent limit, because
changing it would break every caller that already depends on it. `page()` is the
honest form.

## 3. Evidence coverage is not filing-ledger coverage

Not a defect; a distinction the surface now makes mechanically.

The company-concept endpoint reaches back to 2006. The submissions index that
populates `held_filings` carries roughly the last year to 1,000 filings. So most
of the facts held for a filer have an accession the ledger has never seen:

| | evidence span | ledger span | outside the ledger |
|---|---|---|---|
| AAPL | 2006-09-30 → 2026-07-17 (1,922) | 2015-10-28 → 2026-07-31 (44) | 706 |
| MSFT | 2007-06-30 → 2026-07-23 (2,126) | 2020-10-27 → 2026-07-29 (24) | 1,478 |

Nothing is missing from the archive — every one of those facts carries the
accession the filer filed it under, and `test_every_ingested_fact_still_traces_
to_a_real_accession` asserts it. What is missing is the *incremental* view:
`"what changed since the last run"` is answerable only inside the index window.

`Ingestor.coverage(ticker)` reports the two spans side by side with
`ledger_covers_all_evidence: false` rather than a single number, because a lone
"coverage" figure reads as a promise about the whole history.

Closing this needs SEC's historical submission files or the EDGAR full-index.
It is not a wider company-concept call, and it is not done here.

## What was verified

- **Offline** (443 passing): adoption widens monotonically and never narrows;
  unobserved is not unused; the basis vocabulary is closed by trigger; an
  unqualified concept and an inverted window are both refused; resolution
  consults adoption only for the filer asked about; adoption never changes
  fidelity; an unmapped concept stays unmapped; `point_count` is the series and
  not the page; a complete series is not flagged; paging reaches every point
  exactly once and terminates; forged and empty cursors are refused; the
  surface still exposes no raw SQL escape hatch.
- **Live** (514 passing): all four filers' revenue series resolve completely;
  adoption is recorded per filer with `OBSERVED_ADOPTION` and the right counts;
  MSFT's pre-2016 `Revenues` resolves with `adopted_outside_mapping_window` set;
  every PARTIAL mapping still breaks its series; truncated series state their
  true length; the ledger gap is reported rather than hidden.
- Sealed 2.4.3, 2.2.3 and Query Surface semantics unchanged.

## Remaining, in the order it will bite

1. **TSM (IFRS / 20-F / ADR).** IFRS concepts are not in the registry at all, so
   every TSM figure will arrive unmapped until they are added. Adoption does not
   help: it widens *when* a concept applied, and there is no mapping to widen.
2. **NU (banking semantics).** Needs the same per-issuer adoption work plus
   metric definitions that name banking concepts rather than operating-company
   ones.
3. **Historical ledger.** Before claiming incremental ingestion over a decade,
   the ledger needs the historical submission files.
4. **Dimension members.** Unchanged and still open — segment revenue requires
   filing-instance contexts, not a wider company-concept call.
