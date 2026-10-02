# 2.38 — IFRS PPE acquisition → `capex`: mapping proposition

A proposition only. Nothing promoted, nothing edited, nothing fetched, nothing
committed.

```
ifrs-full:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities
    -> capex   EXACT
```

## VERDICT: **SUPPORTED_EXACT**, with no promotion blocker on measured evidence

---

## A. Semantics — established affirmatively, not inferred

| | |
| --- | --- |
| accounting object | acquisition of property, plant and equipment |
| measurement basis | cash outflow, classified as an investing activity |
| asset scope | **the same scope as the declared `us-gaap:PaymentsToAcquirePropertyPlantAndEquipment` EXACT mapping** — PP&E excluding intangibles, which is exactly the difference Core `capex` records between EXACT and PARTIAL |
| sign convention | the source fact is **positive**; the cash-flow renderer displays an investing outflow in parentheses. 2.37 found no `sign="-"` on any instance fact |
| period semantics | duration — a flow over the reporting period |
| unit / currency | preserved per observation; observed in TWD with a USD translation in the same context |
| second appearance | the **same fact** presented as an asset-class breakdown, established from the instance |

None of that comes from a number agreeing. The accounting object and the
measurement basis come from the presentation, and the second appearance was settled
by the instance's contexts and dimensions.

---

## B. Cross-filer adversarial check — four filers, no adverse finding

```
       facts   keys   ambiguous   instants   negatives   declared comparator
BHP      33     33           0         0           0   none
PAAS     18     18           0         0           0   none
TECK     18     18           0         0           0   none
TSM      35     35           0         0           0   none
```

**0 of 104 period/unit/accession keys carry more than one value.** No fact is an
instant, so the concept is purely a period flow. No value is negative, so it never
carries an outflow sign the source did not assert. No value sits outside investing
cash flow, because no other presentation exists for it in these four filings.

**One check could not be run.** No filer holding the candidate also reports a
declared capex concept, so no cross-framework value reconciliation is possible from
what is held — 2.35's condition 7 again.

**That is a limitation on the check, not an adverse finding**, and the difference
matters. The semantics were settled affirmatively from primary evidence; value
reconciliation would have been *supporting* evidence under this project's own rule,
not a requirement. Recording a missing measurement as a blocker would let the
absence of a check masquerade as evidence against the proposition — which is the
error 2.37 made in the opposite direction, when a hardcoded verdict sat beside a
computation that disagreed with it.

---

## C. A prediction of mine that was wrong, and the correction

I expected to find dimensional duplication creating a double-count risk, and I
built the promotion blocker around it. **It does not exist in these documents.**

2.36 counted 15 "ambiguous" periods for this concept, keyed on `period_end` across
all accessions. Keyed **per accession** — which is how the archive keys facts —
there are **none**. A period reported in a 20-F and again in a 6-K with a revised
figure is a **revision**, not a dimension member, and it is not a duplication.

| keyed on | count | what it means |
| --- | --- | --- |
| `period_end` across accessions | 15 | the same period revised between filings |
| `period_end` + `accn` | **0** | no fact duplicated within a filing |

My structural worry was real in principle and had **zero measured incidence** here.

---

## D. The structural limitation, recorded with its incidence

**The dimension member is not preserved as a field.** Two facts sharing concept,
period, unit and accession but differing only in a member would get the same
`contract_id` and different `observation_id`, both would be stored, and nothing on
either row would record that they are one fact seen two ways. Observation identity
is content-derived for a good reason — the schema says the contract id "is
canonical per metric and a restatement of a band would collide on it" — and this is
its other side.

**Measured incidence for this concept across these four filers: 0 of 104 keys.**

So it is recorded as a **latent limitation to re-measure when the population
widens**, not as a promotion blocker. Calling it one would overstate what is
known — and the honest position is that the risk is structural and real while its
occurrence here is nil.

---

## E. The caveat, preserved verbatim and not weakened by the verdict

> **TSM's non-cash transaction schedule presents the same XBRL fact and value
> under a non-cash heading. The instance shows one fact and one value rather than
> a distinct second transaction, but the filing does not explain why this cash-flow
> magnitude is repeated there.**

It does not change the verdict — one fact, one value per period per unit — and it
is not removed because it does not change the verdict. Any promotion should carry
it.

---

## F. What a promotion round would inherit

```
SUPPORTED_EXACT on semantics
  no promotion blocker on measured evidence
  one check not performable: cross-framework value reconciliation
  one latent structural limitation: member not preserved, incidence 0 here
  one caveat to carry into the mapping notes
```

The proposition is ready to be argued rather than promoted. If it is taken forward,
the promotion should re-measure the exposure across whatever population exists by
then — because the limitation is structural and its incidence is a property of the
filers, not of the concept.

---

## G. State

| | |
| --- | --- |
| full suite | **744 run, 670 passed, 74 skipped**, unchanged |
| production files changed | **none** |
| registry / mappings / definitions / applicability / historical observations | untouched |
| fetches | **none** |
| commits | `1a37225` (2.33) · 2.34–2.38 uncommitted |

`ifrs_capex_proposition_238.py` writes `harness/238-ifrs-capex-proposition.json` with
the proposition, the semantic evidence, every filer's adversarial findings, the
structural limitation with its measured incidence, the checks that could not be run,
and the verdict.

**Where the three stand:**

```
A  PaymentsForCapitalImprovements                  UNDECIDED, narrowed
                                                     cash-flow basis settled;
                                                     accounting object filer-dependent
B  PurchaseOfPPEClassifiedAsInvestingActivities    SUPPORTED_EXACT (2.38), no blocker
C  AdditionsOtherThanThroughBusinessCombinationsPPE REFUTED (2.36)
```

**Next.** If B is taken forward: a small promotion round with regression tests.
Separately, A's cross-filer confirmation on CCXIU and HPP — same presentation
check, two more filers, not mixed with B.

Nothing promoted, nothing committed.