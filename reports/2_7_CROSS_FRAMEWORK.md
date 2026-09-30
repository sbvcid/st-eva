# 2.7 — Cross-Framework and Applicability Generalization

Two issuers, one of them reporting under a different accounting framework and the
other classified as a financial institution, against the same registry and the
same query surface. The question is not "can it run" — AAPL, MSFT, MU and NVDA
answered that. It is **whether the semantic model generalises**, and where it
does not, which concept turns out not to have been generic enough.

Every number here is read out of a real SEC archive by
`crossframework_verify.py`, which takes the issuers and the metrics as arguments
so that it cannot name its own subject.

The cross-framework archive is a build artefact and is not committed, for the same
reason the sealed one is not. Rebuild and re-verify with:

```python
from harness.snapshot import build_snapshot
build_snapshot(
    "experiments/003-llm-evidence-retrieval/harness/snapshot-crossframework.sqlite",
    live=True, include_fixture=False,
    metrics=("revenue", "net_income", "eps_diluted", "assets", "cash",
             "debt", "shares_outstanding"),
)  # then ingest each issuer with its own forms: AAPL 10-K/10-Q, TSM and NU 20-F

python crossframework_verify.py --snapshot <that path> \
    --issuer TSM --issuer NU --issuer AAPL \
    --probe-metric revenue --probe-metric net_income
```

---

## 1. Environment

| | |
| --- | --- |
| archive | `harness/snapshot-crossframework.sqlite`, migration version 11 |
| sealed archive | `harness/snapshot.sqlite` at `ce603a5588cef067` — **byte-identical before and after this round** |
| registry | 24 concepts, 26 mappings, 18 metrics across four taxonomies |
| full suite | **554 passed**, 74 skipped (was 532 before this round) |
| `verify_harness` | unchanged — reference 0/15, every broken target still fails only its own test |
| company-specific columns | **0** |
| company tokens in the semantic modules | **0** |

The sealed snapshot was not migrated. Every 2.1 through 2.6 result was read out of
it, and applying migrations 0010/0011 to it would have changed the ground truth
those results were graded against. The new read path therefore works on an
archive that has no `issuer_business_model` table and answers "no
classifications recorded" — which is exactly what that archive knew before.

---

## 2. TSM — filing and taxonomy inventory

`data.sec.gov/api/xbrl/companyfacts`, CIK 0001046179, one request.

| | |
| --- | --- |
| taxonomies present | `ifrs-full` **334 concepts** · `dei` 1 · `srt` 1 |
| **us-gaap concepts** | **0** |
| forms | 20-F (5,480 facts) · 6-K (501) |
| concepts queried by ST-EVA | 10 |
| **coverage of what the filer reports** | **10 of 334 = 3.0%** |

TSM files IFRS and nothing else. The framework boundary is not a special case to
be worked around — it is the ordinary case for a foreign private issuer, and the
archive holds no US-GAAP row for TSM at all.

Ingested: 10 filings, 214 observations, 26 source facts skipped as duplicates,
**0 concepts unresolved**, 16 dimension collisions.

### The three-axis instrument earning its place

`coverage_report` for TSM, from the 2.6.6 axes:

```
evidence_coverage         214 observations, 10 concepts, ifrs-full + dei
query_discoverability     every one of the 10 reachable from a metric query
semantic_interpretability not measured -- no model was run this round
```

The number the round did **not** have to guess: **3.0% of what TSM actually
reports is in the archive.** The framework generalised *reachability* for the
concepts that were declared, and it did not come close to generalising *coverage*.
Those are different claims and the 2.6.6 axes are what made the difference
visible rather than letting "TSM revenue works" stand in for "TSM is covered".

---

## 3. TSM — mappings

Four EXACT, five PARTIAL, from one registry with no framework column and no
issuer branch.

| metric | concept | type | why |
| --- | --- | --- | --- |
| assets | `ifrs-full:Assets` | **EXACT** | "total assets at the balance sheet date" in both; neither framework admits a narrower reading |
| cash | `ifrs-full:CashAndCashEquivalents` | **EXACT** | the metric definition already excludes short-term investments; the IFRS element draws the same line |
| eps_diluted | `ifrs-full:DilutedEarningsLossPerShare` | **EXACT** | weighted-average diluted count over the period in both |
| net_income | `ifrs-full:ProfitLossAttributableToOwnersOfParent` | **EXACT** | parent-only, the same claim `us-gaap:NetIncomeLoss` makes |
| revenue | `ifrs-full:Revenue` | PARTIAL | **the trap this phase exists to catch** — see below |
| net_income | `ifrs-full:ProfitLoss` | PARTIAL | total profit including non-controlling interests; TSM's differs from attributable-to-parent by exactly −856,300,000 |
| shares_outstanding | `ifrs-full:NumberOfSharesIssuedAndFullyPaid` | PARTIAL | *issued* is not *outstanding*; equal only absent treasury shares, and the archive holds no evidence either way |
| debt | `ifrs-full:CurrentPortionOfLongtermBorrowings` | PARTIAL | one declared component of a composition |
| debt | `ifrs-full:LongtermBorrowings` | PARTIAL | the other, structurally identical to the US-GAAP current/non-current pair |

### Revenue: the one that is not EXACT

`ifrs-full:Revenue` and `us-gaap:Revenues` read alike. They are not the same
claim. The IFRS element is an aggregate of ordinary-activity income that may
carry interest, dividend, royalty and grant income; the concept the metric calls
exact is contracts-with-customers only, which is a **component** of it.

TSM reports `Revenue` = 2,894,307,700,000 and `RevenueFromContractsWithCustomers`
= 2,894,307,700,000 — the same number — while reporting interest revenue
(87.2bn), government grants (75.2bn) and dividends (0.567bn) as *separate*
concepts. So for TSM the two figures coincide today. **That is a fact about TSM
and not a definition**, and a mapping that said EXACT would be asserting a
generalisation from one filer's presentation. It is PARTIAL, the series break is
recorded, and the note says why.

A test asserts the weaker type, so a future edit that promotes it on the strength
of the spelling fails.

### Windows are evidence-derived

A PARTIAL mapping must record dates, because a series does not continue across
one. Both available answers were wrong:

* dating the mapping from the day it was written would resolve no IFRS concept
  for any historical period — the same silent loss as an undiscoverable fact;
* using one filer's reporting history is AAPL's history by another name, the
  defect 2.5.1 removed.

So the window is a **taxonomy** fact: the earliest period each element is
reported for by any filer using it, with no end date. `Revenue` 2015-12-31,
`Assets` 2016-12-31, `LongtermBorrowings` 2020-12-31.

---

## 4. TSM — concepts deliberately left unresolved

Reported by the filer, queried by ST-EVA, and **not** mapped:

| concept | TSM's value | why not |
| --- | --- | --- |
| `RevenueFromContractsWithCustomers` | 2,894,307,700,000 | a **component** of `ifrs-full:Revenue`; mapping both would put two IFRS figures into one metric for one period with no way to tell which the filer presented |
| `RevenueFromInterest` | 87,213,400,000 | a component of ordinary-activity income, not the revenue line |
| `RevenueFromGovernmentGrants` | 75,164,300,000 | as above |
| `RevenueFromDividends` | 566,900,000 | as above |
| `DilutedEarningsLossPerShareFromContinuingOperations` | 302,850,900,000 (2015) | continuing operations only; the metric has no such qualifier, and it is a different quantity |
| `NumberOfSharesAuthorised` | 28,050,000,000 | authorised is neither issued nor outstanding |
| `IssuedCapital` | 259,327,300,000 TWD | a **currency amount**, not a share count |
| `LoansAndAdvancesToCustomers` (NU) | 5,321,885,000 | a bank's earning assets; no Core metric declares them |
| `InterestRevenueExpense` (NU) | 2,834,859,000 | a bank's revenue line; `revenue` is mapped to the IFRS `Revenue` element, not to a bank-specific one |

`RevenueFromContractsWithCustomers` is the sharpest: same value, same period,
one tag. Forcing it in would have raised the mapping count and lowered the
meaning.

**A caveat about how the unresolved set is knowable.** The archive reports zero
unmapped concepts for all three issuers, because ingestion only fetches concepts
the registry maps. The set above came from the companyfacts inventory — which is
exactly the 2.6.6 `query_discoverability` axis applied to a new issuer, and the
reason to run that inventory *before* touching the registry.

---

## 5. NU — applicability

`data.sec.gov/api/xbrl/submissions`, CIK 0001691493:

```
sic            6199  Finance Services
ownerOrg       02 Finance
entityType     other          (a foreign private issuer)
```

**NU is not a US-GAAP financial-services filer. It is an IFRS one.** That
reframes the phase: NU cannot isolate the applicability question from the
framework question on its own, because there is no US-GAAP bank in the set to
separate them with. Stated rather than worked around.

### What the registry rules, and what the archive holds

`FINANCE_SERVICES` comes from the filer's own SIC code, `basis =
DECLARED_BY_ISSUER`, source recorded. `gross_profit` and `operating_income` are
declared inapplicable to it.

| metric | state | applicability | reason | held |
| --- | --- | --- | --- | --- |
| **gross_profit** | **NOT_APPLICABLE** | NOT_APPLICABLE | `BUSINESS_MODEL_NOT_MEANINGFUL` | 0 |
| **operating_income** | **NOT_APPLICABLE** | NOT_APPLICABLE | `BUSINESS_MODEL_NOT_MEANINGFUL` | 0 |
| capex | NO_OBSERVATIONS | APPLICABLE | `NOT_YET_COLLECTED` | 0 |
| r_and_d | NO_OBSERVATIONS | APPLICABLE | `NOT_YET_COLLECTED` | 0 |
| sga | NO_OBSERVATIONS | APPLICABLE | `NOT_YET_COLLECTED` | 0 |
| revenue | SOURCE_REPORTED | APPLICABLE | `SOURCE_STATED_VALUE` | 12 |
| net_income | SOURCE_REPORTED | APPLICABLE | `SOURCE_STATED_VALUE` | 24 |
| assets | SOURCE_REPORTED | APPLICABLE | `SOURCE_STATED_VALUE` | 8 |
| cash | SOURCE_REPORTED | APPLICABLE | `SOURCE_STATED_VALUE` | 16 |
| eps_diluted | SOURCE_REPORTED | APPLICABLE | `SOURCE_STATED_VALUE` | 9 |

**NU's own taxonomy settles the applicability question before any policy is
written: it reports `operating_income` in zero concepts.** A bank's income
statement has interest income and interest expense and no cost of sales, so
"revenue less cost of revenue" and "operating income" are not constructs for it.
ST-EVA refuses, and the refusal is derived from a registry declaration plus a
filed classification — not from an empty observation count.

### The distinction held

```
NOT_APPLICABLE     the metric does not exist for this kind of company
NO_OBSERVATIONS    it applies and nothing has been collected yet
UNAVAILABLE        an attempt was made and produced nothing
```

Eleven NU metrics are `NO_OBSERVATIONS / NOT_YET_COLLECTED`; two are
`NOT_APPLICABLE / BUSINESS_MODEL_NOT_MEANINGFUL`. **Zero `UNAVAILABLE`.** They
did not collapse, and AAPL and TSM show the same `NO_OBSERVATIONS` behaviour, so
the fix is generic rather than fitted to a bank.

### What the brief asked for that does not exist

`EBITDA`, `enterprise_value` and `PFCF` are **not Core metrics**, and none was
added. Under the rule that a metric is not created because a test asked for it,
the answer is that the Core registry does not define them, so the applicability
question for them is out of scope by construction. `equity` is likewise not
registered. `gross_profit` and `operating_income` were the two registered
metrics that genuinely do not apply, and both are now ruled on.

---

## 6. Registry changes

| | |
| --- | --- |
| concepts added | 9, all `ifrs-full` |
| mappings added | 9 — 4 EXACT, 5 PARTIAL |
| applicability added | `gross_profit` → `BANK`, `FINANCE_SERVICES` |
| business-model vocabulary | `FINANCE_SERVICES`, `OPERATING`, `MANUFACTURING`, `TECHNOLOGY` added |
| migrations | 0010 `issuer_business_model`, 0011 `NO_OBSERVATIONS` |
| **metric definitions naming an issuer** | **0** |

```
taxonomy      EXACT  EQUIVALENT  PARTIAL
ifrs-full     4      0           5
us-gaap       5      0           5
dei           1      0           0
vendor        0      1           0
```

### What required a generic schema change

Two, both found by the evidence rather than anticipated:

**1. There was nowhere to record an issuer's business model.** `metric_inapplicable_in`
was keyed by business model and its own column comment said the right thing —
*"never stands in for a retrieval that found nothing"* — but no row could ever
fill that column. The rule was enforceable and completely unreachable, so a
metric correctly declared inapplicable to a financial institution fell through to
`UNAVAILABLE / RETRIEVAL_FAILED`: **a retrieval failure reported for a line of
business that does not have one.** Migration 0010 is a link, not a new vocabulary
of companies, and the basis is closed by trigger so "the filer publishes this"
and "somebody decided this" never read the same in a row.

**2. "Applicable and not yet collected" had no state.** It was reported as
`UNAVAILABLE`, which says the last attempt failed. Migration 0011 adds
`NO_OBSERVATIONS` with reason `NOT_YET_COLLECTED`, and the trigger that closes the
vocabulary is dropped and recreated rather than edited, because migrations are
forward-only and an archive that ran the earlier build must keep running the
earlier rules.

---

## 7. Query surface — no change, and one real fix

The surface was **not** redesigned. Both axes come out of it already, and the
provenance chain resolves end to end for a cross-framework metric:

```
semantic metric   revenue
  -> observation  obsarch_fec7c02f0f0a236cdc803b02      (NU)
  -> source_fact  sfid_14bec8755c17a9aedf27b66b447d313e
  -> document     doc_48f69fbad3fb9b21445a9d14
  -> accession    0001292814-22-001705
  -> form         20-F
  -> taxonomy     ifrs-full
  -> concept      ifrs-full:Revenue
  -> mapping      PARTIAL, series_continues false
  -> period       2019-12-31
  -> available_at 2022-04-21T01:16:03.000Z
  -> adoption     TSM 2015-12-31..2024-12-31, 26 facts, 9 filings
```

**Six of six chains complete** for AAPL, TSM and NU across revenue and net
income. No raw SQL, and nothing a consumer has to know about the taxonomy beyond
what the payload states.

### The one fix, and it was pre-existing

`held_filings` is written from the SEC submissions index, which is bounded —
roughly the most recent thousand filings per filer. Company facts reach much
further back. So facts were stored for accessions the index never mentioned, and
**no filing row was written for them**, and the chain stopped one link short:

| | before | after |
| --- | --- | --- |
| accessions with observations | 86 | 86 |
| accessions in `held_filings` | 59 | 88 |
| **observations with no filing row** | **29** | **0** |

Not new with this round — the **sealed 2.6 archive has the same gap for 30 of
its 74 accessions** — and not specific to a framework or an issuer. It was a gap
in writing down an identity that was in the fact all along, and Phase 5 is the
first thing that looked for it.

---

## 8. Cross-company regression

| | |
| --- | --- |
| full suite | **554 passed**, 74 skipped, 26 subtests (was 532 / 74 / 26) |
| `verify_harness` | unchanged: reference 0/15, each broken target failing only its own test |
| sealed AAPL snapshot | `ce603a5588cef067` before and after — **byte-identical** |
| AAPL live evidence in the new archive | 1,758 observations, 11 concepts, unchanged |
| AAPL business model | MANUFACTURING (SIC 3571) → no inapplicability ruling, as before |
| issuer-named columns | **0** |
| issuer tokens in `core_registry` / `registry_seed` / `evidence_model` / `data_contract` / `evidence_query` | **0** |

The specificity count is read from the schema and from the module text rather
than from a flag, and it skips comments deliberately: this project documents
which issuer prompted which decision, and a count that included the documentation
would forbid the record of why.

---

## 9. Semantic ambiguities found

Five, and they are the substance of the round rather than a defect list.

1. **`ifrs-full:Revenue` is an aggregate; `us-gaap`'s exact concept is a
   component of it.** Resolved as PARTIAL with a series break. The two tags agree
   in TSM's filings and still are not the same claim.
2. **`ProfitLoss` includes non-controlling interests; `NetIncomeLoss` does
   not.** TSM's two differ by exactly −856,300,000, which is the test for
   whether a series may continue across them. Both mapped, the parent-only one
   EXACT.
3. **IFRS has no `outstanding` share count that maps to a metric defined as
   `outstanding`.** `NumberOfSharesIssuedAndFullyPaid` is *issued*. Equal only
   absent treasury shares, for which the archive holds no evidence. PARTIAL, and
   the reason recorded.
4. **`debt` has no single standard concept in either framework.** The metric
   already says so, and both frameworks are handled by a declared composition of
   two components — structurally identical, which is the generalisation the
   phase was asked to demonstrate.
5. **A filer may report the same figure under an aggregate and a component.**
   TSM's `Revenue` and `RevenueFromContractsWithCustomers` are the same number
   for the same period. Mapping both would have put two rows into one metric
   with nothing to distinguish them.

### No new A-class defect

The two schema changes were gaps in wiring that the evidence exposed, and both
are now closed with the reasoning recorded in the migrations. The provenance gap
was pre-existing and is fixed. **Nothing found this round requires a metric
definition to change.**

---

## 10. Did the Core Evidence model generalise?

**Yes, for the framework. Partially, and not at all for coverage.**

What holds:

- One registry serves two taxonomies and two business models with **zero**
  issuer-named columns, definitions or code paths.
- A semantic metric is reached through whichever concept the filer used, and the
  *lesser* type is recorded wherever the definitions do not agree.
- Applicability is **derived** from a filed classification plus a registry
  declaration, and it is reported as its own axis beside evidence state.
- A financial institution's inapplicable metrics are refused with an explicit
  reason, and applicable-but-empty is a different state with a different reason.
- Provenance resolves from a semantic metric to a filing, across frameworks, for
  every issuer.
- The sealed archive is untouched and the sealed harness is unchanged.

What does not:

- **Coverage is 3.0% of what TSM reports and 4.0% of what NU reports.** The
  framework generalised reachability for declared concepts, not collection. A
  metric is a mapping someone declared; a filer reports hundreds of concepts, and
  nothing in this round moved that number.
- **NU cannot separate the framework question from the applicability question**,
  because it is itself an IFRS filer and there is no US-GAAP bank in the set.
- `NumberOfSharesAuthorised`, `IssuedCapital` and the IFRS revenue components
  stay unmapped on purpose, and there is no mechanism yet to say *why* a concept
  was declined in a machine-readable way — the reasoning lives in seed notes.

That last point is the one this phase hands to the next. The unresolved set is
currently a property of the seed file rather than of the archive, which means the
archive can report what it holds and not what it considered and declined. Given
that 3.0% is the coverage figure and not 100%, a reader has no way to tell how
much of the remainder is *deliberate* — and the difference between those two
numbers is exactly what a coverage claim has to be honest about.
