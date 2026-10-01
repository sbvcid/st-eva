# 2.25 — Both remaining exclusions refuted, and the registry is nearly empty

2.24 left three seeded exclusions and labelled them honestly: two REFUTED and
removed, one PROPOSED-but-never-tested, one TESTABLE-but-unestablished. This
collected the population for the untested one.

The test set was already in an archive. The 75-issuer population's own
classification table names every SIC 61–62 filer, and 2.16.1's split of SIC 60–67
is what put them there. Seven were fetched; the eighth, **IPB, has no
`companyfacts` document at all** — a 404 from EDGAR, which is a different fact from
reporting nothing and is recorded as such.

```
7 filers  12,489 observations  0 requests  34.9s  42.9 MB
completeness  983 filings · 129 documents · all identities distinct · 0 duplicates
pit safety  0 promoted · 0 of 4,826 eligible too early
```

---

## A. Both rules refuted

Proposition, stated before the run: *refuted if any filer of the class tags a
mapped concept; silence would be testable-with-no-counterexample, not supported.*

```
ticker   gross_profit                        operating_income
AIXC     COLLECTED       4 obs   us-gaap   COLLECTED  134 obs
FMCCH    SOURCE_SILENT   0 obs             DELIBERATELY_DECLINED  0 obs
OMCC     SOURCE_SILENT   0 obs             COLLECTED   18 obs
ORXCF    SOURCE_SILENT   0 obs             COLLECTED  107 obs
PRAA     SOURCE_SILENT   0 obs             COLLECTED  216 obs
SLNHP    COLLECTED      20 obs   us-gaap   COLLECTED  152 obs
SUIG     COLLECTED      15 obs   us-gaap   COLLECTED   39 obs
```

**`gross_profit × FINANCE_SERVICES`: refuted by three of seven.** AIXC, SLNHP and
SUIG tag `us-gaap:GrossProfit`. A savings and loan holding company reporting a
gross profit subtotal is the ordinary case, not an exception — the same finding as
NRIM, from the same SIC major group one division over.

**`operating_income × FINANCIAL`: refuted for `FINANCE_SERVICES` by six of seven,
666 observations.** And this is the one that says the most: `operating_income` for
`BANK` remains **0 of 8**, while for `FINANCE_SERVICES` it is 666. **The same
metric, same metric name, same mapped concept — silence in one class and a complete
series in the other.** The original reasoning said a financial institution's
operating result "is not an operating-income concept". A credit union, a mortgage
banker and a savings and loan holding company all report it. The sentence was
about banks and was written as a statement about finance.

By the lifecycle in 2.24, `REFUTED` forbids use as a refusal rule. So this is
executing that rule rather than making a new decision: both `FINANCE_SERVICES`
exclusions are gone, and `operating_income` was **narrowed to `BANK`** rather than
deleted — because `BANK` was not refuted, and narrowing is what the evidence
supports.

**What is left in the entire registry: one exclusion.**

```
operating_income  NOT_APPLICABLE  for  BANK
```

Eight banks, zero of them tag `us-gaap:OperatingIncomeLoss`. That is consistent
with the rule and does not support it, so it stays at `TESTABLE`.

---

## B. The prediction, verified

Removal was a prediction again, and it holds with no special case:

```
FINANCE_SERVICES  gross_profit      AIXC/SLNHIP/SUIG COLLECTED · four SOURCE_SILENT
                  operating_income  six COLLECTED · FMCCH DELIBERATELY_DECLINED
BANK              operating_income  eight NOT_APPLICABLE, 0 obs
semantic conflicts across both corpora: 0
```

**666 + 39 observations that were collected-then-refused are now simply
collected.** Nothing newly fetched. Nothing discarded. And the registry's refusal
surface went from three exclusions to one without a single line of ingestion code
changing — which is the invariant 2.24 named:

> **Changing a semantic interpretation must not change Evidence.**

The conflicts are gone for the same reason they were gone in 2.24: a conflict is a
statement about a rule, and there is no longer a rule for them to contradict.

---

## C. `SUPPORTED` tightened, as asked

SPEC §0.29 now states three things that were implicit:

**A rule may not enter the lifecycle without a falsifiable proposition attached**,
stating in advance what would support it and what would refute it. Not "banks do
not report gross profit" — unfalsifiable as written, because a bank reporting it
would be *surprising* rather than *contradictory*.

**`SUPPORTED` requires an affirmative evidentiary basis, and "no counterexample
found" is not one.** Stated rather than left implied because the pressure toward
the wrong reading is constant: silence looks like evidence because it produces a
number. To reach `SUPPORTED` a rule needs evidence of the thing it asserts — that
the line does not exist on the filer's statement — not evidence that the archive
has not yet seen it.

**`SUPPORTED` is reached, never assumed into.** A rule that has met no
counterexample and been supported by no evidence either stays `TESTABLE`, which is
where the last remaining rule sits.

---

## D. What this sequence established

Four rules, written in 2.7 from category intuition, tested against filers of their
own class:

| rule | class | filers | outcome |
| --- | --- | --- | --- |
| `gross_profit` NOT_APPLICABLE | BANK | 8 | **REFUTED** — NRIM, 22 obs |
| `r_and_d` NOT_APPLICABLE | MINING | 4 | **REFUTED** — NEM, 236 obs |
| `gross_profit` NOT_APPLICABLE | FINANCE_SERVICES | 7 | **REFUTED** — 3 of 7, 39 obs |
| `operating_income` NOT_APPLICABLE | FINANCIAL | 15 | **REFUTED for FINANCE_SERVICES** — 6 of 7, 666 obs |

**Four refutations, zero supports, and one rule left standing on consistency alone.**
Not one of these was argued; every one was contradicted by a filer within the class
it was written about. The 2.24 framing holds and sharpens:

> `NOT_APPLICABLE` is not a default. It is a refusal proposition that requires
> Evidence to support it. Without sufficient evidence to refuse, the question goes
> to the source and the answer is whatever the source says.

And the mature practice is now the opposite of what a rule-based screener does:

> Not "no counterexample found, therefore add the rule." But: **propose a
> falsifiable rule first, then decide in advance what evidence would support or
> refute it.**

`CONDITIONAL` remains unnecessary — `SOURCE_SILENT` already expresses what a filer
did not report, and it is not work to do. The two propositions it would have
described both resolved the same way: no rule.

---

## E. Two things this round preserved

**IPB has no `companyfacts` document at all.** EDGAR returns 404. That is not a
filer that reports no gross profit — it is a filer with no aggregated fact
document, which is a different fact and is recorded as the absence of the document
rather than as silence about a concept. Six of seven is the honest sample.

**Availability precision stays a first-class distinction.** `FILED_AS_OF_DATE` was
1.4% of the bank corpus, 49.4% of MINING/INSURANCE, and 9.9% here (1,234 of
12,489). The three-corpus spread is the argument: "the source has only a filed
date" is a minority on young filers and a plurality on old ones, so it must not be
converted to a timestamp for convenience, and the further back in history a consumer
looks the more its PIT precision should be visible to it.

The 540 divergent against the 75-issuer reference decompose to a single cause —
`reference holds the pre-fix midnight fabrication` — the same third-time finding.

---

## F. State

| | |
| --- | --- |
| full suite | **643 passed**, 74 skipped, 717 run |
| production change | `registry_seed.py` only |
| registry exclusions remaining | **1** — `operating_income` × `BANK`, state `TESTABLE` |
| corpora re-run | all three; statuses verified against the prediction |
| conflicts remaining | 0 in every corpus, because no rule remains to be contradicted |
| PIT invariant | holds on all three |
| equivalence | 11,174 / 11,174 unchanged |

Eight tests failed after this edit, all asserting the two exclusions that were
removed. That is the correct failure direction again: the rewritten tests now say
`gross_profit` is applicable to every financial class and that `operating_income`
is refused for `BANK` alone — and `operating_income × BANK` has been asserted false
by no filer in seven rounds, so the one rule left standing is also the one whose
justification is weakest.