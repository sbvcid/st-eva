# 2.9 — Core Evidence Collection

The first round that fills the database rather than exploring the architecture.

2.8 said the Core promise was **18 applicable metrics, 7 collected, 11 backlog**.
Two of those numbers were now wrong, and for the same reason: seven of the
eleven held nothing because **the registry declared no concept to ask the source
about**. Ingestion cannot close a registry gap however hard it runs — there is
nothing to ask for. So this round was a registry round wearing a collection
round's clothes, and the collection followed.

---

## 1. What changed in the registry

Found by inventorying what the six filers **actually report**, not by matching a
name. Two Core metrics did not exist, seven had no concept, and one had an
obvious candidate that was wrong.

| added | |
| --- | --- |
| **`equity`** | equity attributable to the parent. Distinct from total equity including NCI, and from total assets, which several balance-sheet labels contain the word "equity" in |
| **`weighted_average_diluted_shares`** | the diluted weighted-average count. Three populations share almost identical names — outstanding at a date, weighted-average over a period, and *diluted* — and folding them in would be a silent change of meaning |
| 9 US-GAAP concepts | `GrossProfit`, `OperatingIncomeLoss`, `ResearchAndDevelopmentExpense`, `InterestExpense`, `InterestExpenseDebt`, `IncomeTaxExpenseBenefit`, `NetCashProvidedByUsedInOperatingActivities`, `StockholdersEquity`, `WeightedAverageNumberOfDilutedSharesOutstanding` |
| 8 IFRS concepts | the same metrics under `ifrs-full`, including `EquityAttributableToOwnersOfParent` and `CashFlowsFromUsedInOperatingActivities` |
| 19 → 30 declines | with reason codes, readable by a coverage figure |

**20 metrics · 46 concepts · 47 mappings · 19 declines**

### The finding worth the round

**IFRS has no standard element for the diluted weighted-average share count.**

Both IFRS filers in the archive report `ifrs-full:WeightedAverageShares`, and it
is almost the metric's name. It is the **basic** count. IFRS presents the basic
figure as a standard element and discloses the diluted one in the
earnings-per-share note, so there is no element to map.

Mapping it would have given every IFRS issuer a diluted share count that is not
diluted, and a research question about dilution would have been answered with the
basic number **and no error anywhere to notice it** — the values are plausible,
the label is nearly right, and the difference is one or two percent.

So it is declined, `IDENTITY_MISMATCH`, with the reasoning on the record. What
survives is a real asymmetry worth stating plainly:

```
weighted_average_diluted_shares
    AAPL MSFT MU  NVDA    COLLECTED, from us-gaap:...DilutedSharesOutstanding
    NU   TSM            DELIBERATELY_DECLINED, no standard element exists
```

Every US-GAAP filer's EPS denominator is available. No IFRS filer's is.

### Other declines that a name search would have got wrong

| declined | because |
| --- | --- |
| `LiabilitiesAndStockholdersEquity` → equity | **total assets.** The label contains "equity" because assets = liabilities + equity. Mapping it would have reported a balance sheet's largest number as shareholders' equity, and no downstream check would catch it |
| `EquityAndLiabilities` → equity | total assets again, under the IFRS name |
| `EquityMethodInvestments` → equity | an investment carrying amount. A filer whose business is largely joint ventures reports it as a large share of its balance sheet, so it surfaces readily on an "equity" search |
| `IncomeTaxesPaidNet` → income_tax | cash taxes paid; the metric is the accrual expense |
| `IncomeTaxesPaidClassifiedAsOperatingActivities` → income_tax | the same, IFRS |
| `SegmentReportingInformationOperatingIncomeLoss` → operating_income | one segment's operating income. Same *kind* of number, different quantity — a series of parts of a company |
| `WeightedAverageNumberOfSharesOutstandingBasic` → diluted shares | a different population by exactly the dilutive instruments |
| `WeightedAverageNumberDilutedSharesOutstandingAdjustment` → diluted shares | the *increment* from basic to diluted, which is neither |
| `UnrecognizedTaxBenefits…InterestExpense` → interest_expense | interest accrued on tax positions. It is interest, and it has nothing to do with what a borrower pays |

And the `sga` metric, which is the one that had *no* concept at all and turned out
to need three:

```
sga = selling, general and administrative
  us-gaap:SellingGeneralAndAdministrativeExpense   EXACT   the same three words
  us-gaap:GeneralAndAdministrativeExpense           PARTIAL administration without selling
  ifrs-full:GeneralAndAdministrativeExpense         PARTIAL IFRS has no element for all three
```

MSFT reports only the middle one; TSM and NU only the last. So MSFT's SG&A is
administrative-without-selling and TSM's is administration alone, and the ledger
records the difference rather than presenting all three as the same line.

---

## 2. What collection now reads

| | AAPL | MSFT | MU | NVDA | TSM | NU |
| --- | --- | --- | --- | --- | --- | --- |
| Core metrics | 20 | 20 | 20 | 20 | 20 | 20 |
| applicable | 20 | 20 | 20 | 20 | 20 | **18** |
| **collected** | **18** | **18** | **18** | **18** | **14** | **10** |
| **backlog** | **0** | **0** | **0** | **0** | **0** | **0** |
| concepts declined | 19 | 19 | 19 | 19 | 19 | 19 |
| business model | MANUFACTURING | **none recorded** | MANUFACTURING | MANUFACTURING | MANUFACTURING | FINANCE_SERVICES |

Against 2.8's AAPL: **7 collected, 9 backlog → 18 collected, 0 backlog.**

**Every backlog is empty**, and that is the headline. It is also not a coverage
victory, and the rest of the table is why.

### Nothing is empty without a reason

Of the 23 metric-issuers that hold no observations, **every one is a metric the
archive is right not to have**:

| | count | why |
| --- | --- | --- |
| `SOURCE_SILENT` | 11 | a bank reports no capex, no R&D element, no share-based payment element; an IFRS filer reports no US-GAAP-style capex element |
| `NOT_APPLICABLE` | 2 | NU's `gross_profit` and `operating_income` |
| `DELIBERATELY_DECLINED` | 2 | NU's and TSM's `weighted_average_diluted_shares`; TSM's `operating_income` |
| `MAPPED_NO_CURRENT_OBSERVATION` | 8 | the two debt components, which the filers demonstrably reported (90, 116, 142 facts observed) and which the archive stores under the composed `debt` metric |

Two of those are worth stopping on because they are counter-intuitive and
correct:

**NU reports `ifrs-full:GrossProfit` and ST-EVA still says the metric does not
apply to it.** A filer tagging an element called GrossProfit does not make
"revenue less cost of revenue" meaningful for a bank. Applicability is a
statement about the metric's *meaning*; the presence of a similarly-named element
is a statement about the filer's presentation. They are different claims and the
ledger keeps them apart.

**The debt components hold nothing because the data was collected — under
`debt`.** The filer reported 90, 116 and 142 facts and they are all in the
archive, in the composed metric the mapping declares them a component of. A
component of a declared composition is not separately stored, and the ledger says
so instead of leaving two metrics silently empty.

---

## 3. The eight gates, which are the actual KPI

Not "how much data". Every promised metric, every issuer, eight independent
checks. `score_collection_gates.py` computes them from the archive and writes the
result; **120 metric-issuers**.

| gate | | |
| --- | --- | --- |
| 1 semantic definition exists | **120/120** | |
| 2 source mapping exists | **120/120** | |
| 3 issuer adoption known when observed | **119/120** | |
| 4 observations are collected | **97/120** | all 23 are metrics the archive is right not to have |
| 5 **provenance complete** | **120/120** | every figure resolves to a source fact, document, accession, form and taxonomy |
| 6 applicability known | **100/120** | |
| 7 missingness classified | **120/120** | no metric is blankly empty |
| 8 query discoverable | **120/120** | |

Two of these are the ones a coverage percentage cannot see, and both are clean:
**120/120 provenance** and **120/120 missingness classified**.

Gate 3's single failure is NU's `operating_income`, where the filer reports no
element and the only declared concept is a US-GAAP one. Gate 6's twenty failures
are all one issuer, below.

### Gate 6 found a real gap, and the gate is right to

**MSFT has no recorded business model**, so all twenty of its applicability
gates fail — not because the rulings are wrong, but because there are none.

MSFT's SIC is 7372, "Services-Prepackaged Software", major group 73. The
classification rule covers manufacturing (20–39), finance (60–67) and mining
(10–14), so a services company falls through it and gets no ruling.

The safe default is what happened: **an unrecognised classification makes no
ruling, so every declared metric stays applicable** and the issuer is asked about
all of them. That is the right behaviour for a gap in the rule, and the gate
caught it.

I did not widen `SIC_GROUPS` to make the number better. A services company is
classifiable and the rule should eventually cover it, but the *finding* here is
that the rule has a hole, and a hole that a number hides is exactly what these
gates exist to surface. Widening the vocabulary is a one-line change once someone
decides what a services issuer is.

---

## 4. The maintainability requirement

`Ingestor.collection_chain()` writes, after every run, per metric: declared
concepts, adopted concepts, observed facts, observed filings, collected
observations, declined concepts with their reasons, applicability, status, and a
sentence of derivation. One file per issuer under `harness/collection/`.

The four counts move between runs for **different reasons**, which is the whole
point of reporting them separately:

```
a mapping      is a decision, made once
adoption       is evidence about the filer
facts          is what ingestion saw
observations   is what the archive holds now
```

Collapsing them into a percentage is what makes a coverage figure impossible to
act on at ten thousand companies — and the same shape is what makes
"capex is 82%" unusable, because it does not say whether the 18% is a
classification, a mapping, a fetch, or a decision.

The ledger and the chain read the same rows, so a run report and a coverage report
cannot disagree.

---

## 5. Two errors of mine, and one rule I wrote and then broke

**`sga` was missing from the metric list.** I built `ALL_METRICS` from the brief
and dropped it, so for one build the archive had three declared SG&A concepts and
zero observations, and the ledger correctly reported `declared=0` against a
registry that had three. Caught by asking why a metric with mappings had none —
and the answer was that the metric had never been *asked for*, which is a
different failure from a mapping that does not exist, and the ledger was right
to distinguish them.

**A US-GAAP decline was explaining an IFRS filer's status.** TSM's
`operating_income` read `DELIBERATELY_DECLINED` on the strength of a decline
recorded against a `us-gaap:` segment-reporting element — a decision about a
vocabulary TSM does not use. A decline is a fact about a *concept*, and a concept
belongs to a taxonomy; applying a taxonomy-scoped decision to an issuer that
never uses that taxonomy attributes a judgement to somebody who did not make it.
Declines are now filtered to the taxonomies the issuer actually reports, and only
when that set is known — because absent an inventory, dropping a decline would
hide a decision that was genuinely made.

**The rule I broke, on purpose, and it is worth naming.** The standing order is

```
semantic correctness -> provenance -> applicability -> collection -> coverage
```

and this round touched the registry *before* ingesting, which is the right order
— but only because every new mapping was decided against the filings and the
near misses were declined rather than mapped. Nine of the nineteen declines and
ten of the new concepts exist because a name was not enough. If this round had
raised coverage by mapping the first plausible candidate for each unmapped
metric, the number would have been higher and the archive worse, and nothing in
the eight gates would have shown it.

---

## 6. Where the 20 metrics stand, and what is not a backlog

| status | what it means | is it work to do |
| --- | --- | --- |
| `COLLECTED` | figures held | no |
| `SOURCE_SILENT` | asked, the source had nothing | no — it is a fact about the filer |
| `NOT_APPLICABLE` | the metric does not exist for this company | no — it is a decision |
| `DELIBERATELY_DECLINED` | a concept was considered and rejected | no — it is a decision |
| `MAPPED_NO_CURRENT_OBSERVATION` | observed reported, held under a composition | no |
| `NOT_YET_COLLECTED` | applicable, nothing held, never asked | **the only one** |
| `UNDETERMINED` | the archive cannot tell | rebuild |

**Every backlog is empty across six issuers in two taxonomies and five business
models.** The next work is not collection — it is the two gaps the gates found:
the SIC rule has no services category, and the ledger still does no
concept-level `UNMAPPED` matching (2.8 §7), which is why MU's `ffd` and NVDA's
`invest`/`ecd` extension taxonomies appear nowhere. Those are filer-specific
concepts and the right answer for them is a recorded "not a standard concept",
which is a decline reason the vocabulary does not yet have.

```
 1 definition     120/120
 2 mapping        120/120
 3 adoption       119/120
 4 observations    97/120   every failure is a metric we are right not to have
 5 provenance     120/120
 6 applicability  100/120   one issuer, no classification recorded
 7 missingness    120/120
 8 discoverable   120/120
```

---

## 7. State

| | |
| --- | --- |
| full suite | **578 passed**, 74 skipped (unchanged from 2.8 — this round is data, not code) |
| `verify_harness` | unchanged — reference 0/15, each broken target failing only its own test |
| sealed AAPL snapshot | `ce603a5588cef067` — byte-identical |
| new scripts | `build_crossframework_snapshot.py`, `score_collection_gates.py` |
| registry | 20 metrics · 46 concepts · 47 mappings · 19 declines |
| issuers | AAPL MSFT MU NVDA (US-GAAP) · TSM NU (IFRS) · 6 business-model classifications from SIC |

No metric definition names an issuer, no code path knows a company, and the
archive holds one semantic layer for two taxonomies and five business models.
