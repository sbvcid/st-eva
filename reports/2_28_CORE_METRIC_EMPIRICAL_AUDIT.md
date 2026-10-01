# 2.28 — Core Metric Empirical Audit

Metric-centric, offline, repository-only. Twenty Core metrics against the 63
full-scope filers 2.27 assembled.

Nothing was fetched. No registry, mapping, decline, applicability policy or
Evidence contract was changed. Suite 714 run / 640 passed / 74 skipped.

**2.27 asked what filers of different business models report. This asks the other
question: for each of the twenty, what does that metric actually represent in the
Evidence world?**

---

## A correction to 2.27 first

I reported that "four metrics are collected by all 63 filers in every model:
`operating_income`, `revenue`, `interest_expense`, `shares_outstanding`". **That
was wrong, and the three-way matrix 2.27 itself produced shows why.**

```
operating_income   COLLECTED 41   DELIBERATELY_DECLINED 22
revenue            COLLECTED 55   DELIBERATELY_DECLINED  8
interest_expense   COLLECTED 58   DELIBERATELY_DECLINED  5
shares_outstanding COLLECTED 57   DELIBERATELY_DECLINED  6
```

What I measured was a **zero `SOURCE_SILENT` rate**, and I reported it as
"collected". They are different facts: `DELIBERATELY_DECLINED` is a recorded
decision about a concept, and 22 filers never had `operating_income` collected at
all. The accurate claim is that **no filer was asked and had nothing to say**,
which is true of those four metrics across all 63 — and it remains the refutation
of 2.7's `operating_income` rule, since eight banks and nine insurers are in the
41 that *do* collect it. The conclusion survives; the phrasing did not.

---

## The five categories, and why they are not a rating

```
A  broad and consistently observable
B  broad, but how the source represents it varies
C  collection exists and the mapping or decomposition is suspect
D  genuinely model-specific in what gets reported
E  insufficient evidence in this corpus to say
```

A descriptive partition. No ordering, no best-to-worst, and no metric is better
than another — they are different shapes of evidence.

The distinction that carries the most weight is **D against C**. D is a claim about
filers; C is a claim about the registry. A metric whose silence is model-structured
may still be a mapping blind spot, and the two need opposite responses, so the
classifier is required to show which it is claiming.

---

## B — twelve metrics, broad but unevenly represented

```
metric                          collected   collisions   declared-date   concepts
cash                                 63/63           218           23.1%         3
equity                                63/63           386           21.2%         4
assets                                63/63           163           24.8%         2
operating_cash_flow                   63/63           245           22.8%         2
net_income                            62/63           464           26.9%         3
eps_diluted                           62/63           455           33.3%         2
income_tax                            61/63           455           28.2%         2
interest_expense                      58/63           220           25.1%         4
shares_outstanding                    57/63             5           25.2%         2
revenue                                55/63           405           33.1%         4
weighted_average_diluted_shares       53/63           327           29.5%         1
operating_income                      41/63           325           27.9%         1
```

Every one of these is collected by at least 65% of filers in every business
model. They are B rather than A for one reason: **the declared-date share sits
between 21% and 33% for every one of them**, and that is a property of *the
filer*, not the metric. 2.27's Q2 established it at corpus scale; this confirms
it per metric, which is why a metric with a 0% declared-date share would be a
different shape of thing rather than a better one.

`shares_outstanding` is the outlier and the most interesting: **5 collision rows
across the entire corpus, against 218 to 478 for every other metric.** Its
concepts are `dei:EntityCommonStockSharesOutstanding` and
`us-gaap:CommonStockSharesOutstanding`, and dei cover-page share counts are
instants with one value per period — so a metric sourced from a cover page carries
almost no dimension ambiguity by construction. That is a property of *where the
fact sits in the filing*, not of the metric's meaning, and it is worth knowing
before anyone treats a low ambiguity count as evidence of a clean metric.

---

## C — three metrics where the registry, not the filer, may be the limit

```
debt                          collected 34/63   collisions 35   declared 27.8%
long_term_debt_current        collected  0/63   collisions 13   declared    n/a
long_term_debt_noncurrent     collected  0/63   collisions 16   declared    n/a
```

The two components are the declared composition of `debt`, so their facts are held
under the parent and their own status is `MAPPED_NO_CURRENT_OBSERVATION` — absence
by construction, recorded as such. That is the decomposition behaving as declared.

**`debt` is the finding.** 2.23 measured that 0 of 8 banks tag any of the four
concepts the registry maps to it. The natural reading is that banks do not report
debt, and that reading is wrong — so this audit asked the **raw `companyfacts`
documents**, not the archive:

> **29 of the 29 filers that report nothing for `debt` carry adjacent concepts
> the registry does not map.**

Including every bank. `ifrs-full:Borrowings` for BHP, `us-gaap:NotesPayable` and
`us-gaap:NotesPayableCurrent` for AIXC and AWCA, `us-gaap:DebtInstrumentFaceAmount`
for AIXC.

The honesty constraint matters here, and it is why this is a finding and not a
proposal: **most of the adjacent concepts are cash-flow movements rather than
stocks.** `ProceedsFromIssuanceOfLongTermDebtAndCapitalSecuritiesNet`,
`RepaymentsOfLongTermDebtAndCapitalSecurities`, `GainsLossesOnExtinguishmentOfDebt`
— none of those is a debt *balance*, and mapping them to a stock metric would be
wrong. Adjacency is a question to formulate, not a conclusion. What it does
establish is that the silence is **not** evidence that banks report no debt, which
is what the model-specific reading would have said.

---

## D — five metrics whose reporting genuinely varies by filer

```
metric       collected   silent by model                          collisions   concepts
r_and_d           23/63   INSURANCE 9/9 · BANK 8/8 · MINING 5/8      60           2
gross_profit      32/63   INSURANCE 9/9 · BANK 6/8 · SERVICES 3/5   154           2
sbc               44/63   MINING 5/8 · BANK 3/8 · UNCLS 0/6          99           1
capex             43/63   INSURANCE 6/9 · MINING 5/8 · SERVICES 0/5  96          2
sga               49/63   BANK 7/8 · UNCLS 1/6 · MANUFACTURING 0/19 478           3
```

These are the metrics where the corpus answered the falsification question, and
where the answer was *the registry is not wrong about the source*:

- **`gross_profit`: 31 filers report nothing, and 0 of them carry an adjacent
  unmapped concept.** The same probe that convicted `debt` **clears
  `gross_profit`**: those filers genuinely do not report a gross profit concept.
  The variation is a fact about reporting, not a blind spot — which is the
  opposite finding from `debt` on the same evidence.
- **`sga`: 19 of 19 manufacturers report it, 7 of 8 banks do not.**
- **`r_and_d`: 16 of 19 manufacturers, 0 of 9 insurers.**

### One specific mapping candidate, named but not proposed

`capex` is declared from `PaymentsToAcquirePropertyPlantAndEquipment` and
`PaymentsToAcquireProductiveAssets`. Three silent filers carry
**`us-gaap:PaymentsForCapitalImprovements`** — HPP 85 rows, EFC 55, CCXIU 2.

That is one concept, three filers, and a plausible reading of "money spent on a
long-lived asset". It is also exactly the kind of finding that must not become a
mapping without a proposition, because "capital improvements" and "property,
plant and equipment" are near-synonyms that are not synonyms, and the ifrs-full
side of the registry has no corresponding declaration to check against. Recorded,
not proposed.

---

## E — empty, and that is a result

No metric landed in E. With 63 filers every metric has enough evidence to say
*something*, and the classifier is built to fall to E rather than give a metric
the benefit of a guess, so an empty E means the corpus is sufficient rather than
the categories being elastic.

---

## What the audit changes about how Core metrics should be read

**Four metrics have no mapping question at all.** `cash`, `equity` and
`operating_cash_flow` are collected by all 63 filers in every model, and the probe
found nothing adjacent and unmapped because there was no silence to interrogate.
`revenue`, `interest_expense` and `shares_outstanding` are never `SOURCE_SILENT`
either, though a minority are registry declines.

**Two metrics need a proposition before they need a decision.** `debt` is a
vocabulary-alignment question, and the evidence is now unambiguous about what kind
of question: 29/29 silent filers carry adjacent unmapped concepts, most of them
flows rather than stocks. `capex` has one named candidate concept and no
proposition.

**Three components exist only as declarations.** `long_term_debt_current` and
`long_term_debt_noncurrent` hold nothing by design and will keep holding nothing
unless the parent decomposition changes. They are the only two metrics in the
registry that cannot ever be collected, which is worth knowing before anyone
counts them as gaps.

**Declared-date share is a filer property and should not be read per metric.** It
sits between 21% and 33% for every B-category metric and 0% for no metric, because
it tracks how far back a filer's history reaches relative to the submissions
window. A per-metric PIT reading would be noise.

**`shares_outstanding` gets its stability from where it sits, not from what it
means.** Five collision rows corpus-wide, sourced from a cover page. Low ambiguity
is not the same as a clean metric.

---

## State

| | |
| --- | --- |
| full suite | **714 run, 640 passed, 74 skipped**, unchanged |
| production files changed | **none** |
| fetched | **nothing** |
| registry, mappings, declines, applicability | **unchanged** |
| commits | 2.27 at `7cb5e27`; 2.28 not committed |

`metric_audit_228.py` produces `harness/228-metric-audit.json`; the source probe
against raw `companyfacts` is recorded in `harness/228-unmapped-probe.json`. Both
are read-only against existing archives.

The next proposition to formulate is `debt`'s vocabulary alignment. It should be
written as a falsifiable claim, decided in advance what evidence would refute it,
and — following 2.26 — it cannot become a refusal or a mapping without that.