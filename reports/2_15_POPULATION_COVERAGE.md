# 2.15 — Full Core scope across twelve issuers, and the shape of coverage

2.14 answered "can the bulk path reproduce twenty Core metrics from evidence the
API path already collected". The answer is yes, exactly, on 17,043 of 17,043
facts. That question is closed.

This asks the one 2.10 left open and nothing since has widened: **when the full
twenty-metric scope moves from six hand-picked filers to a different population,
which metrics get thin, and is that the metric's fault or the filer's.**

Twelve issuers from `harness/bulkfacts/`, the same bulk path, the same twenty
metrics, zero network, and the point-in-time safety check running on the result.

```
bootstrap          12 issuers  22,482 obs  0 requests  71.8s  76.3 MB
completeness       481 filings  233 documents  22,482 observations
                   22,482 distinct identities  0 duplicates
                   0 facts without an accession
                   0 observations without a stored document
reconciliation     9,390 shared identity, all divergent on availability only
                   13,092 only-in-bulk      -> outside the reference's scope
                   45,212 only-in-reference -> issuers this run did not cover
                   0 unexplained rows
pit safety         0 promoted to an instant
                   0 of 8,603 eligible before EDGAR published them
gates              7 of 8 at 240/240; applicability 0/240 (no SIC, as expected)
```

---

## A. What it measured

The unit of report is a cell — metric by issuer — because averaging over metrics
and issuers together is the operation that hides both effects. 20 × 12 = 240
cells, each carrying the ledger's own status, the observation count, and a ratio.

**The first ratio was wrong and said something false.** Scoring each metric
against every instant the archive knows for that issuer put almost everything
between 0.18 and 0.6 and made twelve of twenty metrics look thin. Measured why,
it was an artefact of the denominator. RBC holds 152 distinct instants, but:

```
us-gaap:Assets                          68
us-gaap:CashAndCashEquivalentsAtCarryingValue  77
us-gaap:StockholdersEquity              73
                                         -- union 86
dei:EntityCommonStockSharesOutstanding  65
CashCashEquivalentsRestrictedCash...    19
StockholdersEquityIncludingPortion...   18
                                         -- union 152
```

A metric scored 0.45 against a union that **no single concept spans**. The extra
~66 instants come from a `dei` cover-page concept and two alternate cash/equity
tags, each with its own reporting history. `Assets` is not thin; the denominator
was.

**The obvious explanation was also wrong.** The hypothesis was reporting cadence
— that concepts appear only at annual or only at quarterly dates. It is falsified
in the direction opposite to the prediction: the annual-only instants are the ones
*most* likely to be missing (`assets` covers 10% of RBC's annual-only instants,
against 45% of all instants). Nothing about cadence explains it.

The denominator that answers the operational question is the one that does not
depend on which concepts happen to be in the archive:

```
filing_ratio = periods of this metric that hold it
             / filings in which this filer reported anything we hold
```

### What the matrix actually shows

| metric | collected | median filing ratio | min | statuses |
| --- | --- | --- | --- | --- |
| assets | 12/12 | 1.01 | 0.80 | COLLECTED 12 |
| cash | 12/12 | 1.09 | 0.95 | COLLECTED 12 |
| equity | 12/12 | 1.09 | 0.95 | COLLECTED 12 |
| net_income | 12/12 | 1.04 | 0.20 | COLLECTED 12 |
| sga | 12/12 | 1.05 | 0.51 | COLLECTED 12 |
| gross_profit | 10/12 | 1.05 | 0 | COLLECTED 10, SOURCE_SILENT 2 |
| income_tax | 11/12 | 1.05 | 0 | COLLECTED 11, DECLINED 1 |
| revenue | 11/12 | 1.05 | 0 | COLLECTED 11, DECLINED 1 |
| operating_income | 12/12 | 1.05 | 0.13 | COLLECTED 12 |
| capex | 10/12 | 1.00 | 0 | COLLECTED 10, SOURCE_SILENT 2 |
| eps_diluted | 11/12 | 1.00 | 0 | COLLECTED 11, DECLINED 1 |
| sbc | 9/12 | 1.00 | 0 | COLLECTED 9, SOURCE_SILENT 3 |
| weighted_avg_diluted_shares | 11/12 | 1.00 | 0 | COLLECTED 11, DECLINED 1 |
| r_and_d | 9/12 | 1.05 | 0 | COLLECTED 9, SOURCE_SILENT 3 |
| operating_cash_flow | 12/12 | 1.00 | 0.77 | COLLECTED 12 |
| **shares_outstanding** | 9/12 | **0.97** | 0 | COLLECTED 9, DECLINED 3 |
| **interest_expense** | 9/12 | **0.66** | 0 | COLLECTED 9, DECLINED 3 |
| **debt** | 7/12 | **0.34** | 0 | COLLECTED 7, SOURCE_SILENT 5 |
| long_term_debt_current | 0/12 | 0 | 0 | see below |
| long_term_debt_noncurrent | 0/12 | 0 | 0 | see below |

**The twenty-metric scope is not thin.** Seventeen of the eighteen metrics that
hold anything sit at or above a median filing ratio of 1.0 — every filing a filer
made, the metric is in it, and often more than once because a 10-K reports the
prior year-end as a comparative, which is a real fact at a real date.

Two are genuinely thin and both are **decomposition questions, not collection
failures**:

- **`debt`, 0.34.** Seven of twelve collected, five `SOURCE_SILENT`. `debt` is a
  *composition*: no single standard concept declares total debt, so the registry
  maps `LongTermDebtCurrent` and `LongTermDebtNoncurrent` as `PARTIAL` components.
  Five filers use neither tag, or use a tag the registry does not declare.
- **`interest_expense`, 0.66.** Nine collected, three `DELIBERATELY_DECLINED` —
  filers that tag `InterestIncomeExpenseNet` or `InterestAndDebtExpense` rather
  than `InterestExpense`.

---

## B. The finding the matrix was built to find

**The two debt components hold nothing, and the ledger says the source is silent
when the source answered 423 times.**

`us-gaap:LongTermDebtCurrent` carries **two** mappings:

```
debt                   -> LongTermDebtCurrent  PARTIAL  "a component of total debt,
                                                     never the total on its own"
long_term_debt_current -> LongTermDebtCurrent  EXACT
```

Ingestion stores the fact under **`debt`**: 423 observations of
`LongTermDebtCurrent` and 310 of `LongTermDebtNoncurrent`, across 222 and 171
filings. The component metrics hold zero by construction.

So the ledger reports them as `MAPPED_NO_CURRENT_OBSERVATION` on seven issuers
and `SOURCE_SILENT` on five. `SOURCE_SILENT` is **affirmatively wrong**: it says
the filer was asked and had nothing, and the filer answered with 423 tagged
facts. And the two statuses disagree with each other about the same fact, which
is a granularity defect in the vocabulary independent of the misreading.

This is a semantic decision, not a defect to patch:

- **The composition is the point.** The two `long_term_debt_*` ids exist to
  declare how `debt` is built, and the components are deliberately not separately
  addressable. Then the vocabulary is missing a member meaning *held under a
  parent composition*, and `SOURCE_SILENT` should be reserved for a filer that was
  asked and reported nothing.
- **The components should be addressable.** Then a fact is stored under every
  mapping that accepts it — one source fact, two observations — and `debt` becomes
  a composition of the two. But 2.5's boundary is *derived ≠ reported*, and a
  stored observation is a reported fact, so this is a duplication decision and not
  a small change.

Neither is decided here. What is decided is that the current status is a
**misreading**, not an absence, and that any consumer reading this coverage
surface today is being told the filer withheld data it tagged.

---

## C. The two axes cannot be separated, and that is the finding

**All twelve issuers are `MANUFACTURING`.** SIC 3510, 3530, 3562, 3564, 3569 ×2,
3576, 3577, 3663, 3672, 3674, 3679 — twelve issuers drawn entirely from the
35xx/36xx industrial-machinery-and-electronics range.

So the question "is the thinness the metric's fault or the company type's" is
**not answerable from this sample**, and no amount of analysis of twelve
same-type filers will answer it. The instrument reports the degeneracy rather
than hiding it, because a matrix that silently collapses two axes into one is
worse than no matrix.

What the sample *does* contain is a genuine filer-type mix, which 2.10 did not
test: three foreign private issuers filing 20-F and never 10-K (SSYS, STMEF,
TRSG). The form policy is read from each issuer's own recorded forms rather than
hand-written, precisely so that a coverage difference could not be a form-policy
artefact — a 10-K/10-Q policy would have reported those three as `SOURCE_SILENT`
when the real answer is that nobody asked the right question.

---

## D. Two gaps in the operational machinery, found by running it

**The 75-issuer population archive has never been gated.** `ingest_universe.py`
writes no collection chains, so the gate tool has nothing to iterate for it. The
largest population archive in the repository has never been through the
instrument that found the SIC hole and the unmodelled taxonomies.

**The gate tool crashes instead of skipping.**
`score_collection_gates.py:76` does `connection.execute(...).fetchone()[0]` with
no guard, so a chain file naming a ticker the archive does not hold raises
`TypeError: 'NoneType' object is not subscriptable` and the whole run dies. It
should be a classified skip with a reason — the same failure shape as 2.13's
empty map, where a broken input and an empty input look alike. Recorded, not
fixed.

---

## E. What is now settled, and what is not

Settled: full Core scope over a population runs clean on the bulk path with
complete provenance, no duplicate identity, and the point-in-time invariant
holding; the twenty metrics are **not** thin; two thinness cases are both
decomposition questions; the eight gates hold at 240 metric-issuers.

Not settled, and each is a decision rather than a measurement:

1. **What status does a fact held under a parent composition get?** Currently
   none, and the two nearest words are both wrong.
2. **Is a bulk bootstrap accompanied by `submissions`?** 2.14 measured what
   refusing a question costs: a bank's gross profit reads as collected.
3. **`debt` and `interest_expense` need more declared concepts** — five and three
   filers respectively are `SOURCE_SILENT` or declined for want of a mapping. That
   is registry work, and it is the only metric-level work this round found.
4. **Corpus shape** — 95.8 GB extrapolated from 2.14, now 6.3 MB per issuer at
   20 metrics, unchanged in character.

---

## F. The next step, and the constraint that arrives with it

**The experiment sequence has run out of offline payload.** The repository holds
18 `companyfacts` documents: 6 cross-framework and 12 population. Widening the
population along the business-model axis — which is the axis this sample is
degenerate on — needs documents that are not on disk, and fetching them needs the
network.

So the next input is a **fetch**, and the population should be selected *by
business model* rather than by convenience, because the 75-issuer archive
already records the SIC-derived classification for all 75 and the twelve that
happened to be on disk were all one type. The sample must contain at least one
filer from each model the registry can classify differently — a bank, an
insurer, a REIT, a utility, a services company, a filer using `dei`-only shares
outstanding — or the metric-versus-type question stays unanswerable.

Before that fetch, two cheap repairs, both of which the next run needs and neither
of which is a semantic question: write collection chains for a population
archive, and make the gate tool skip an unknown ticker with a reason instead of
raising.

After the population is wide enough to separate the axes: the real
`companyfacts.zip`, and the mega-cap resample. Not before.

---

## G. State

| | |
| --- | --- |
| full suite | **612 passed**, 74 skipped, 686 run — unchanged |
| production files changed | none in this round |
| instrument | `fullscope_bulk.py`, generalised; six-issuer and twelve-issuer modes |
| committed artefact | `harness/population-215.json` |
| archive | `snapshot-population.sqlite` (76.3 MB, untracked, one command to rebuild) |
| network | none |

The matrix reported a false answer first, and the correction came from measuring
where the extra periods came from rather than from choosing a better denominator
and rerunning. Both denominators are now reported, because a ratio without its
denominator is not a measurement.
