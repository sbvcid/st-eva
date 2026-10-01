# 2.27 — Cross-Business-Model Evidence Corpus

Two cohorts, measured apart. Population manifest: `reports/2_27_POPULATION_DESIGN.md`,
the only selection authority. Nothing was substituted, added or dropped.

**No registry, applicability policy, semantic rule or Evidence contract was
modified.** The committed tree is unchanged; the suite is 714 run / 640 passed /
74 skipped, and nothing is committed.

---

## The headline, and it is Cohort A

Eighteen filers whose `companyfacts` were already held were given their first
`submissions` document. The result is the cleanest measurement in this project's
history:

```
existing archives (12 strided + 6 cross-framework)   39,525 observations
Cohort A1 (same companyfacts + submissions)          39,525 observations

shared source_fact_id        39,525
only in Cohort A1                   0
only in the existing archives       0

EVIDENCE value / period / identity changes        0
availability changes                        29,283
```

**Thirty-nine thousand five hundred and twenty-five facts, zero of them altered,
and 29,283 of them gained a better availability answer.** That is the invariant
this repository exists to hold, and it is now measured on a population rather than
argued: *changing a semantic interpretation must not change Evidence.* Filling in
context changed no fact, no value, no period and no identity.

### And the availability transition runs in both directions

```
FILED_AS_OF_DATE -> ACCEPTANCE_DATETIME     20,458
ACCEPTANCE_DATETIME -> FILED_AS_OF_DATE      8,825
```

The 20,458 are the twelve filers finally receiving EDGAR's real acceptance
instants instead of a filed date. **The 8,825 are the six cross-framework
filers moving the other way, off the fabricated `T00:00:00+00:00` that 2.14
identified as a pre-fix defect — 8,825 is that exact count.** Rebuilt under the
corrected contract, accessions outside the submissions window correctly fall back
to a declared date rather than a midnight nobody published.

`source_fact_id` is identical across all 29,283 changes, which is the design
property 2.14 was built for: identity does not depend on availability.

### A measurement caveat, reported rather than smoothed

`fetch_source_inventory.py` fetches both streams together, so the Cohort A run
also re-fetched `companyfacts` — 36 requests where 18 were intended. That is why
two Cohort A archives exist: `bulkfacts-227a-orig/` holds the **original**
documents and is what Cohort A1 was built from, isolating context enrichment
exactly. A second build from the freshly fetched documents was not needed: the
identity comparison already came back with **0 only-in-A1**, so EDGAR published
no new filings for these eighteen in the interval. Had it done so, the delta would
have appeared as new `source_fact_id` values with their own accession, and the
per-field comparison on the shared set would have been unaffected either way.

---

## Cohort A — context enrichment

| | |
| --- | --- |
| filers | 18 |
| submissions requests | 18 |
| companyfacts re-fetched unintentionally | 18 |
| filings held | 1,570 |
| distinct accessions in observations | 774 |
| documents | 357 |
| observations | **39,525, unchanged** |
| distinct `source_fact_id` | 39,525, unchanged |
| duplicate identities | 0 |
| missing accession / missing document | 0 / 0 |
| applicability gate | **360/360** — context restored, no ruling invented |

`applicability` moving from *unavailable* to *360/360* is the whole of Cohort A:
before the submissions document these eighteen filers had no SIC and therefore no
business model, and no applicability cell could be derived for any of them.

---

## Cohort B — 22 new filers

| | |
| --- | --- |
| filers resolved | **22 / 22** — every CIK from repository data, six cross-checked against the CIK inside each stored document |
| requests | 44 (22 companyfacts + 22 submissions) |
| runtime / archive | 136.1 s / 179.3 MB |
| filings held | 3,040 |
| distinct accessions in observations | 1,235 |
| documents | 396 |
| observations | **54,103** |
| distinct `source_fact_id` | 54,103 |
| duplicate identities | **0** |
| missing accession | **0** |
| missing document | **0** |
| gates | 7 of 8 at 440/440; `applicability` 320/440 |
| PIT invariant | 0 promoted, 0 eligible before its own instant |

The `applicability` gate at 320/440 is 120 cells across **six filers with no
business model** — four SIC 65 and two with no SIC recorded — which is the gate
reporting a blank honestly rather than a failure.

### The 22, with the forms each issuer actually files

```
ticker  model          obs  metrics  dates%  forms                       collisions
AFL     INSURANCE     3091       13    40.8  10-K,10-Q,10-Q/A                  126
CB      INSURANCE     2585       13    53.0  10-K,10-Q                          104
GNW     INSURANCE     3559       14    34.3  10-K,10-K/A,10-Q                    370
TRV     INSURANCE     2675       14    53.6  10-K,10-Q,10-Q/A                   16
UNH     INSURANCE     3543       16    68.4  10-K,10-Q                           12
CRL     SERVICES      3400       17    32.2  10-K,10-Q                           53
HLT     SERVICES      2737       16     7.6  10-K,10-Q                          167
MAR     SERVICES      3450       16    50.5  10-K,10-K/A,10-Q,10-Q/A              114
MLCO    SERVICES       954       16     0.0  20-F                                 32
FLO     MANUFACTURING  3047       17    18.4  10-K,10-Q                           60
KURA    MANUFACTURING  2036       17     0.0  10-K,10-Q                           12
THRMV   MANUFACTURING  2777       17    18.8  10-K,10-Q,10-Q/A                    112
FCX     MINING        3380       16    19.2  10-K,10-K/A,10-Q                    118
RIO     MINING         595       12     0.0  20-F,20-F/A                          26
TECK    MINING         268       13     0.0  40-F                                 21
WPM     MINING         600       11     0.0  40-F                                  4
AWCA    UNCLASSIFIED   1137       15     0.0  10-K,10-K/A,10-Q                     24
EFC     UNCLASSIFIED   2122       11     0.0  10-K,10-K/A,10-Q,10-Q/A               27
FAST    UNCLASSIFIED   3651       17    15.7  10-K,10-K/A,10-Q                    125
HPP     UNCLASSIFIED   2453       15    19.1  10-K,10-Q                            38
TSCO    UNCLASSIFIED   3261       17    19.4  10-K,10-Q                            53
VAC     UNCLASSIFIED   2782       14    44.5  10-K,10-Q                           277
```

Forms came from each issuer's own submissions document, never from a hand-written
list. The 20-F/40-F group widened from four names in one corpus to seven across
mining and services.

---

## Population matrix — 63 full-scope filers

Denominator fixed before the fetch by the manifest: **20 Core metrics × every
full-scope filer**. `applicable` is not a denominator term, per the manifest.
The 75-issuer population archive holds 8 of 20 metrics, so its cells are scope
gaps rather than silence and it is reported **beside** the matrix, not inside it.

```
BANK 8 · FINANCE_SERVICES 8 · INSURANCE 9 · MANUFACTURING 19 · MINING 8 · SERVICES 5 · UNCLASSIFIED 6
```
— exactly the 63 the manifest projected.

### `business_model × metric × SOURCE_SILENT` (silent / filers)

```
metric                     BANK  FINSERV  INSUR   MANUF   MINING  SERV    UNCLS
gross_profit                 6/8      4/8    9/9    4/19     3/8    3/5     2/6
operating_income             0/8      0/8    0/9    0/19     0/8    0/5     0/6
r_and_d                      8/8      5/8    9/9    3/19     5/8    4/5     6/6
sga                          7/8      1/8    2/9    0/19     3/8    0/5     1/6
capex                        1/8      3/8    6/9    3/19     5/8    0/5     2/6
debt                         8/8      6/8    4/9    5/19     2/8    0/5     4/6
revenue                      0/8      0/8    0/9    0/19     0/8    0/5     0/6
interest_expense             0/8      0/8    0/9    0/19     0/8    0/5     0/6
sbc                          3/8      3/8    4/9    4/19     5/8    0/5     0/6
shares_outstanding           0/8      0/8    0/9    0/19     0/8    0/5     0/6
```

**Q1 — does silence vary with business model? Yes, and the structure is not the
intuitive one in every case.** `sga` is the sharpest: **zero of nineteen
manufacturers silent, seven of eight banks silent.** `r_and_d` runs the other
way — three of nineteen manufacturers silent, **nine of nine insurers**. `debt`
is **eight of eight banks silent**, which is the 2.23 registry gap at population
scale rather than a filer property.

### Q2 — the bimodal PIT precision is model-linked

```
model              median declared-date share      range
INSURANCE                53.6%                8.0 – 70.1   (no insurer at 0%)
SERVICES                 32.2%                0.0 – 66.6
UNCLASSIFIED             19.1%                0.0 – 44.5
BANK                      0.0%                0.0 –  9.2   (7 of 8 at exactly 0)
FINANCE_SERVICES          0.0%                0.0 – 37.2
MANUFACTURING             0.0%                0.0 – 65.8
MINING                    0.0%                0.0 – 58.7
```

**Insurance is the only stratum where declared dates are universal**, and it is
the stratum this session added. The correlation is real in this corpus; the
mechanism is unverified and is most plausibly listing age rather than industry.
That is a measurement, not a rule, and it is the sharpest thing in this corpus
that 2.23's four mining and insurance filers could not show.

### Q3 — dimension ambiguity by model, per metric (collision rows)

```
metric              BANK  FINSERV  INSUR  MANUF  MINING  SERV  UNCLS
equity                 57      50    120      74      35    24     26
eps_diluted            29      42    127     105      36    49     67
gross_profit           11       0      0      90      22    20     11
debt                    0       0      4      11      14     4      2
```

Normalised per issuer, `equity` runs 13.3 rows/issuer in insurance against 3.9 in
manufacturing, and **`gross_profit` ambiguity is exactly zero in both financial
strata** while manufacturing carries 90 rows across 19 filers. The pattern 2.22
could not see — that ambiguity concentrates in some metrics and not others — now
shows a second dimension: it concentrates in some *models* too, and the two are not
the same ordering.

### Q4 — what the coverage surface does with an unclassifiable filer

Six filers, four SIC 65 and two with no SIC recorded. `NOT_APPLICABLE` is **zero**,
`NOT_YET_COLLECTED` is **zero**, conflicts are **zero**, and between 11 and 17 of
their twenty metrics are `COLLECTED`. So: every metric is asked, the source
answers where it has an answer, and nothing is invented. Whether that is *right*
for a REIT is a question this round deliberately did not answer.

### Q5 — the falsification question

Four metrics are **collected by all 63 filers, every model, without exception**:
`operating_income`, `revenue`, `interest_expense`, `shares_outstanding`.

- `operating_income` is collected by **eight banks and nine insurers**. 2.7 wrote a
  rule refusing it for exactly those filers on the reasoning that a financial
  institution's operating result "is not an operating-income concept". 2.25
  refuted it for `FINANCE_SERVICES`. **The corpus now shows the intuition was
  wrong in every stratum, at 63/63.**
- `interest_expense` likewise, in banks and insurers alike — refuting "a financial
  institution does not report interest expense".
- `revenue` and `shares_outstanding`, 63/63, in every model.

The corpus did not merely fail to support the registry's intuitions. It refuted
the remaining two at population scale, and it found the one place the registry is
*not* wrong about a filer's reporting: `debt`, silent for **8 of 8 banks** and
**0 of 8** in the other financial strata, because the registry maps a
current/non-current composition that banks do not use.

### `semantic_conflict` is zero across all 63 filers — by construction

Not a gap in the measurement, and not evidence of a clean corpus. A conflict is a
statement about a *rule*, and 2.26 emptied the refusal surface: `applies_to` is
true for every metric and every model, so there is nothing for a fact to
contradict. **The mechanism is still live and still tested** — the 2.19 contract
tests run against a refusal created deliberately through `support_exclusion`.

---

## Verifications

| check | Cohort A1 | Cohort B |
| --- | --- | --- |
| duplicate `source_fact_id` | 0 | 0 |
| observations without an accession | 0 | 0 |
| observations without a stored document | 0 | 0 |
| declared date promoted to an instant | 0 | 0 |
| eligible before its own acceptance instant | 0 of 28,676 | 0 of 38,709 |
| append-only triggers present | yes | yes |
| full suite | 714 run / 640 passed / 74 skipped | |

**Reconciliation.** Cohort A1 against the two existing archives it supersedes:
39,525 shared identities, 0 one-sided, **0 semantic-field differences**. Cohort B
against the 75-issuer population archive: 14,115 shared, 11,276 matched, 2,839
divergent, all 2,839 accounted for by the reference holding the pre-fix midnight
fabrication — the same single cause as 2.14 and 2.20.

**Zero-observation cells.** Every cell in the matrix carries one of the ledger's
own statuses, and none is unexplained: `SOURCE_SILENT` (asked, nothing returned),
`DELIBERATELY_DECLINED` (a recorded decision about a concept),
`MAPPED_NO_CURRENT_OBSERVATION` (the declared debt composition, whose facts are
held under `debt`). `NOT_YET_COLLECTED` is **zero** in all 63 filers — every cell
was asked.

**No applicability exclusion was created.** `metric_inapplicable_in` is empty
across both cohorts, and the refusal-surface audit is green. Silence produced no
rule, in either direction.

---

## What the two cohorts mean, kept apart

**Companyfacts-only, submissions enrichment, and new full-scope collection are
three different operational numbers and are not combined.** Cohort A added
**0 observations** and **20 filings** of context per filer; Cohort B added **54,103
observations** across **22 filers**. Request counts are 36 and 44. Size, request
count and observation count are scale proxies and are labelled as such; the
coverage statements above are built from statuses with a denominator fixed before
the fetch.

### What would be wrong to conclude

- That the corpus confirms the registry. It refuted two of its four rules at
  population scale and showed the other two are redundant.
- That 63 filers is a distribution. It is a *sample with a stated design*, and
  the strata sizes are 5 to 19.
- That insurance PIT precision is caused by insurance. The correlation is real in
  this corpus; the mechanism is unverified and listing age fits at least as well.

### What is now measurable that was not

Four things the 18+22 made visible and the previous six-per-corpus samples could
not: a metric×model silence structure rather than a per-model anecdote; a
model-linked PIT precision gradient; a second dimension on dimension ambiguity;
and an operating income reporting rate of 63/63 that makes the 2.7 rule
untenable rather than merely untested.

## Not done, deliberately

`OPERATING` and `TECHNOLOGY` remain unreachable — no SIC group covers them, and
the manifest recorded that as a limitation rather than something selection could
solve. `REIT` is still unclassified, and the six filers that would exercise it are
now measured *without* a ruling, which is the answer to Q4 and not a decision
about whether that answer is right.

Nothing committed.