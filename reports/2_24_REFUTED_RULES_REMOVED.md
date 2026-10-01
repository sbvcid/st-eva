# 2.24 — Two rules removed, and a lifecycle so they stay removed

2.23 left two applicability rules refuted by filers of their own target class.
This removes them, and writes down what a rule's state means — because the failure
mode this has to prevent is not a rule being wrong, it is a refuted rule coming
back on the grounds that the sample was small.

---

## A. What was removed, and what was not

One production file changed: `registry_seed.py`. Two exclusions gone.

```
BANK   -> gross_profit    REMOVED     refuted by NRIM, 22 obs, us-gaap:GrossProfit
MINING -> r_and_d         REMOVED     refuted by NEM, 236 obs,
                                      us-gaap:ResearchAndDevelopmentExpense
```

**But there were three seeded exclusions, not two, and the third is not a survivor
of the same argument:**

| rule | class | state | why |
| --- | --- | --- | --- |
| `gross_profit` NOT_APPLICABLE | BANK | **REFUTED** | NRIM |
| `r_and_d` NOT_APPLICABLE | MINING | **REFUTED** | NEM |
| `gross_profit` NOT_APPLICABLE | FINANCE_SERVICES | **PROPOSED, never tested** | SIC 61–62 was split out in 2.16.1 and the eight filers it produced were all SIC 60. No filer of this class has been through a full Core-scope collection anywhere in this repository |
| `operating_income` NOT_APPLICABLE | BANK, FINANCE_SERVICES | **TESTABLE** | 8 banks, 0 tag the concept — consistent with the rule, does not establish it |

So removing the two refuted rules did not make the remaining ones supported. **It
made their lack of support visible**, which is the more useful outcome.

---

## B. The lifecycle, and the two definitions that carry the weight

```
PROPOSED   ↓  a filer of that class exists and has been through a full
            Core-scope collection
TESTABLE   ↓
    ├── SUPPORTED    no counterexample found
    ├── REFUTED      a filer of that class contradicts it
    └── UNDECIDED    the replacement proposition has not been established
```

Both of these are about what a state **forbids**:

**`REFUTED` — the rule must not serve as a refusal rule.** Removal is required, not
optional. Re-adding it means editing the test that records which filer contradicted
it, which names the filer and the concept:

```
BANK   -> gross_profit    NRIM,  22 obs, us-gaap:GrossProfit
MINING -> r_and_d         NEM,  236 obs, us-gaap:ResearchAndDevelopmentExpense
```

`tests/test_semantic_conflict.py::TestRefutedRulesAreAbsent` is that test.

**`UNDECIDED` — the replacement has not been established. It does not mean the old
rule may continue to exist.** Different sentences, and conflating them is exactly
how a refuted rule returns: *"the sample was only four filers"* is an argument about
a **replacement**, and was never an argument that the refuted rule was right.

And `SUPPORTED` is not `TESTABLE` promoted by silence. A metric with no
observations is a different fact from a metric with no meaning — the distinction
`SOURCE_SILENT` against `NOT_APPLICABLE` exists for — and it is also what stops
"0 of 8 banks report this" being read as "a bank cannot".

**Three of the four states above are not `SUPPORTED`.** That is the honest position:
one rule is contradicted twice over, one has never been tested, and one has met no
counterexample and been supported by no evidence either.

---

## C. What removal produced, verified rather than asserted

The removal was a prediction, so it was tested. No special case anywhere:

```
snapshot-banks2      gross_profit
   NRIM                                  COLLECTED      22 obs
   BBAR                                  COLLECTED      18 obs
   AUBN CCFN CZWI FCNCP FHB PFBX          SOURCE_SILENT

snapshot-ins-min     r_and_d
   NEM                                   COLLECTED     236 obs
   BHP KNF PAAS                          SOURCE_SILENT
   HUM PFG PRU SIGI       (INSURANCE)     SOURCE_SILENT
```

**258 observations that were previously collected-then-refused are now simply
collected.** Nothing new was fetched, nothing discarded, and the three filers that
report these metrics keep their evidence. Exactly the outcome the decision was taken
for.

### And the conflict markers are gone — correctly

Zero `semantic_conflict` on either metric now. That is not a regression and worth
saying plainly rather than discovering later: **a conflict is a statement about a
rule**, and with no rule there is nothing to contradict. The machinery is still
live and still tested — against the rule that *survived*,
`operating_income` × a `FINANCE_SERVICES` filer — because a contract that only ever
applied to rules that have since been deleted would be evidence of nothing.

The durable record of the contradiction is the code comment on each exclusion and
the refutation test. The marker was a live signal about a live rule, and there is no
live rule.

---

## D. The four cases, which is what this adds up to

```
a rule exists and rules the metric out   -> NOT_APPLICABLE
no rule                                  -> no refusal; the metric is asked
the source reports it                     -> COLLECTED
the source has nothing                    -> SOURCE_SILENT
```

**`NOT_APPLICABLE` is not a default. It is a refusal proposition that requires
Evidence to support it. Without sufficient evidence to refuse, the question goes to
the source and the answer is whatever the source says.**

`CONDITIONAL` was considered and rejected on evidence rather than taste. It was
never needed. The two propositions it would have described — "a bank may report
gross profit", "a miner may report research and development" — both resolved the
same way: there is no rule, because `SOURCE_SILENT` already expresses what a filer
did not report, and it is not work to do. `applies_to` stays binary, and a gap
marker fails if anyone adds conditionality — because the first thing they would have
to decide is whether a conditional ruling satisfies or overrides the conflict marker.

---

## E. What removal does not fix, and the exact remedy in each case

**`operating_income × FINANCIAL`** still refuses on nothing beyond consistency with
eight banks. **A bank that reports it, or an explicit decision that the silence is
enough** — the second being a change of evidentiary standard rather than of rule.

**`gross_profit × FINANCE_SERVICES`** still refuses having never been tested. **The
eight SIC 61–62 filers the 75-issuer archive already names**, collected at full
Core scope.

Neither remedy is a code change. Both are a population, and the candidate names are
already in an archive.

---

## F. Two points from 2.23 preserved, because they are not about rules

**The availability semantics stay genuinely distinct.** `FILED_AS_OF_DATE` is 1.4%
of the bank corpus and **49.4%** of the MINING/INSURANCE one — BHP and KNF are
decades-old and their early filings sit outside the ~1,000-filing submissions
window. "The source has only a filed date" is not a tail on a corpus; it is a
substantial part of any historical one and it grows with age. So a filed date must
not become a timestamp for convenience later, and the further back in history a
consumer looks, the more its PIT precision should be visible to it.

**`INSURANCE` is too coarse to carry a universal rule.** Four filers, four SIC
subgroups, and `operating_income` reported by exactly one: a hospital and medical
service plan has that line, a life insurer does not. `gross_profit` 0 of 4 and
`r_and_d` 0 of 4 are four source-silent observations each — not evidence for an
exclusion. Before any insurance rule is written the question is *which kind of
insurance*, which is the same lesson as `BANK` and `gross_profit`: **a coarse
business-model label makes a false universal rule easy to write.**

---

## G. State

| | |
| --- | --- |
| full suite | **643 passed**, 74 skipped, 717 run (+4) |
| production change | `registry_seed.py` only |
| tests | 8 rewritten, 4 added; 8 failures were expected and are the refutation guard |
| both corpora | re-run; statuses verified against the prediction |
| equivalence | **11,174 / 11,174**, 0 divergent, 0 one-sided — unchanged |
| PIT invariant | holds on both corpora |
| sealed snapshot | untouched |

The eight tests that failed after the edit were all asserting the refuted rules.
That is the correct failure direction: removing a rule should break the tests that
say it exists, and the rewritten ones now say it *must not*.