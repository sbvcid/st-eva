# ST-EVA 2.5 — Core Registry

> **歷史資料／非現行指令。** 本文件只記錄撰寫時的設計、狀態、計畫或決策，不具有授權、禁止、限制或要求未來工作的效力。文中任何「binding」「frozen」「approved」「not authorized」「must」等措辭均為歷史內容，不得凌駕使用者目前的要求。當前狀態以現行程式碼、測試及實際 Git 狀態為準。
>
> **HISTORICAL ARCHIVE — NOT CURRENT INSTRUCTIONS.** This document records prior design, status, plans, or decisions. It does not grant, deny, restrict, or require work. Any “binding,” “frozen,” “approved,” “not authorized,” or “must” wording below is historical and does not override the user's current request. Determine current state from current source code, tests, and Git state.

Status: implemented. `context_schema_version 2.3-C.2` semantics unchanged.
Migration: `0007_core_registry.sql`
Modules: `core_registry.py`, `registry_seed.py`

## What this is for

The database knows an item's *value* and a source's *name*. Before this, it
did not know what an item **is**. The registry supplies that, and nothing
else.

```
observation -> source concept -> semantic metric
```

A **source concept** is what a source calls something: an XBRL tag, a vendor
field. A **metric** is a meaning ST-EVA names. They are different entities,
related only by an explicit mapping:

```
us-gaap:Revenues     a tag a filer applies
revenue               a meaning ST-EVA names
```

Deciding that they are the same because the names are alike is how a silent
discontinuity gets spliced into one series, which is the defect 2.4.3 exists to
prevent. So the mapping is stated, and its fidelity is part of the statement.

## The three objects

| Table | States |
|---|---|
| `metric_registry` | what a metric *means* |
| `concept_registry` | what a source concept *is*, with the source's own definition |
| `metric_concept_mapping` | how one relates to the other, and how exactly |

Every vocabulary is closed and enforced by a trigger: statement, unit family,
period type, applicability, status, and mapping type. An unknown value would
make "is this series comparable?" unanswerable, because nothing would know
what the value means.

## Mapping types

| Type | Meaning | Series continues across a concept change? |
|---|---|---|
| `EXACT` | the source states this concept and it means the metric | yes |
| `EQUIVALENT` | a different name, an equal meaning | **yes** |
| `PARTIAL` | a component, or a wider aggregate | **no** |
| `NON_COMPARABLE` | related, but a different quantity | **no** |

Only `EXACT` and `EQUIVALENT` continue a series. `PARTIAL` and
`NON_COMPARABLE` must record `effective_from` or `effective_to`, enforced by
trigger, because a mapping that breaks a series has to say when.

That is the 2.4.3 rule applied to a change of *concept* rather than a change of
*period length*: two points may only be joined when they measure the same
thing.

## What the registry does not do

It does not rank sources, resolve conflicts, pick a winner, infer a value, or
decide a metric. Those stay where 2.3-B and 2.4.3 put them:

```
CONFLICTING            NO_WINNER_SELECTED
DISCREPANT              two comparable sources differ
METHODOLOGY_MISMATCH    not comparable
PERIOD_SPAN_MISMATCH    not the same window
RESTATEMENT_OR_REVISION two versions of one period
```

A test asserts the registry exposes no `resolve_conflict`, and that no public
name contains `winner` or `prefer`.

## Applicability

A metric is `APPLICABLE`, `CONDITIONAL`, or `NOT_APPLICABLE`, and may exclude
named business models. Two rules:

- **Absence of retrieval is never evidence of inapplicability.** A metric with
  no archived observation stays applicable. A test walks every metric and fails
  if one is `NOT_APPLICABLE` with no observation to justify it.
- **An unknown business model is not evidence either.** Applicability is
  refused only for a model the registry actually names.

## Resolution

```python
registry.resolve("us-gaap:NetIncomeLoss")     # -> metric net_income
registry.resolve("us-gaap:SomeNovelConcept")  # -> metric None
registry.resolve("revenue")                   # -> metric None
```

An unmapped concept resolves to **nothing**, and says why. It is never attached
to the metric whose name looks nearest. A concept that maps to several metrics
is reported as `AMBIGUOUS_MAPPING` with every candidate listed, because that is
a registry question for a filer to answer, not one to settle here.

The Query Surface exposes this as a `semantic` block on every observation. It
*adds* meaning and replaces no evidence: every provenance field a figure had
before is still there, and a test asserts it.

## The seed

Eighteen metrics, fifteen concepts, seventeen mappings — built from **real AAPL
filings**, not designed in the abstract. A registry designed first and validated
against itself would only prove it against itself.

### Three findings that would have been got wrong from the names

**Revenue has three concepts, not one.** Observed over the SEC endpoint:

| Concept | Facts | Window | Definition |
|---|---|---|---|
| `RevenueFromContractWithCustomerExcludingAssessedTax` | 117 | 2017-09-30 → | the filer's contract-revenue line — `EXACT` |
| `Revenues` | 11 | 2016-09-24 → 2018-09-29 | "other activities that constitute an earning process… includes investment and interest income" — `PARTIAL` |
| `SalesRevenueNet` | 210 | 2007-09-29 → 2018-06-30 | net sales — `PARTIAL` |

`Revenues` and the contract-revenue concept **overlap for two quarters** of
FY2018 and mean different things. A name-based merge would have spliced a
broader measure into a narrower series across exactly the overlap.

**Capital expenditure: two concepts with near-identical names that are not the
same thing.**

- `PaymentsToAcquirePropertyPlantAndEquipment` — "long-lived, physical assets
  … not intended for resale" — `EXACT`
- `PaymentsToAcquireProductiveAssets` — "…**software, and other intangible
  assets**" — `PARTIAL`

The names read alike. The source's own definition says the first excludes
software and intangibles. This is the clearest demonstration in the whole
registry that a name is not a definition.

**Debt's two portions share a name family and are two quantities.**
`LongTermDebtNoncurrent` excludes current maturities; `LongTermDebtCurrent` is
the current portion. They are two metrics, never one series. `debt` is a
**declared composition**, and the registry does not sum it.

### One equivalent, on real evidence

`vendor:trailingTotalRevenue` → `revenue` is `EQUIVALENT` across taxonomies.
That mapping is not a name match: it rests on the 2.3-B cross-source verdict
for this issuer, which found the two agreeing. A vendor that ingested a filing
will agree with it, which is why the mapping and the validation are separate
objects and neither is promoted into the other.

The two remain **two observations**. A shared mapping is not a licence to
merge, and merging would delete the evidence that two independent readings
existed — which is the only reason a conflict is findable at all.

## Queries

The seed is loaded once per archive:

```python
from core_registry import CoreRegistry
from registry_seed import seed
from sqlite_archive import SQLiteArchive

store = SQLiteArchive("data/st-eva.sqlite")
seed(CoreRegistry(store.connection))
```

The Query Surface resolves through the same registry, so a consumer never needs
to know the tables:

```python
row = query.get_observation("cmp-revenue-sec-q-2024-03-30-000032019324000069")
row["semantic"]["metric"]      # "revenue"
row["semantic"]["concept"]     # "us-gaap:RevenueFromContractWithCustomer..."
row["source"]["accession"]     # unchanged
row["source"]["documents"][0]["content_hash"]
```

## Known limitations

1. **`statement` is read from the archive, not from the registry.** An
   observation built from the market-data view carries no filing concept and so
   resolves to nothing. That is correct — it is a vendor aggregate, not a
   filed fact — and the `semantic` block says so.
2. **The archive's `concept` column is overloaded.** For view-derived
   observations it holds a metric name such as `"revenue"` rather than a filing
   concept. The registry declines to resolve those, which is the right
   behaviour, but the column is misleading and a later ingestion stage should
   distinguish "no concept" from "concept unknown".
3. **`accession`, `taxonomy` and `source_fact_id` remain unpopulated** on
   archives written by the current pipeline; those values are in `raw` and the
   Query Surface reads them from there. Populating the indexed columns is
   ingestion work.
4. **No filing-derived applicability yet.** `inapplicable_in` is recorded
   against a metric and takes effect, but nothing yet derives a business model
   from a filing, so in practice only the seeded exclusions apply.
5. **`redistribution_tier` defaults to `B`** for sources created before
   `0004_source_policy`, including the SEC in a plain archive. Ingestion should
   set it.
6. **The seed covers sixteen metrics.** The five absent from real AAPL evidence
   (`gross_profit`, `operating_income`, `r_and_d`, `sga`, `interest_expense`,
   `income_tax`, `operating_cash_flow`) are registered as concepts of the
   meaning with no archived observations, which is the correct state: a metric
   the registry has not seen evidence for is not a metric the archive has
   data for.
