# 2.37 — IFRS capex duplicate-context resolution

One question, one concept, one filing. Read-only: no registry entry, no mapping,
no production file changed, no historical observation touched, nothing committed.

**`ifrs-full:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities`
— SUPPORTED**, on evidence from the XBRL instance rather than from the two
renderings that raised the question.

---

## A. The question, and where the answer actually lives

TSM's 20-F presents the concept twice:

```
R5    Consolidated Statements of Cash Flows
      CASH FLOWS FROM INVESTING ACTIVITIES
      Acquisitions of property, plant and equipment          (956,006.5)

R152  Cash Flow Information - Schedule of Detailed Information
      about Non Cash Transaction (Detail)
      Disclosure of detailed information about non-cash transaction [line items]
      Payments for acquisition of property, plant and equipment   956,006.5
```

Same concept, same magnitude, opposite sign. ST-EVA collects **by concept**, so if
one concept carried two accounting objects, a mapping would silently import both.
"Does the cash-flow line is capex" is therefore not sufficient — the question is
whether the *concept* is safe.

**The renderings are the symptom; the instance is the evidence.** Only the XBRL
instance says how many facts exist, what contexts they carry, what dimensions, and
what sign they were tagged with.

```
7 fact instances · 0 carrying sign="-" · 4 distinct values
```

| period | unit | total | by asset class | match |
| --- | --- | --- | --- | --- |
| 2022-01-01..2022-12-31 | TWD | 1,082,672.1 | 1,082,672.1 | yes |
| 2023-01-01..2023-12-31 | TWD | 949,816.8 | 949,816.8 | yes |
| 2024-01-01..2024-12-31 | TWD | 956,006.5 | 956,006.5 | yes |
| 2024-01-01..2024-12-31 | USD | 29,155.4 | — | yes |

Three findings, and none of them is the magnitude matching:

**1. The sign flip is a renderer convention, not a negated fact.** No instance fact
carries `sign="-"`. The parentheses in the cash-flow rendering are how the renderer
presents an investing outflow; the value is tagged positive in both reports.

**2. The second appearance is the same fact, presented as a class breakdown.** The
dimension is `ifrs-full:ClassesOfAssetsAxis` =
`ifrs-full:ClassesOfPropertyPlantAndEquipmentDomain`, and in every unit and every
period the class fact carries **the same value as the total**. For TSM that class is
the whole of it.

**3. There is no second amount.** One value per period per unit. The concept is not
used in this filing for a distinct non-cash transaction.

**A control, not an assertion:** the sibling FVTOCI acquisition line behaves
identically — same magnitude, same sign flip between the same two reports. The
pattern is a property of how this filing is rendered, not a coincidence about one
concept.

**Compared per unit, deliberately.** Comparing whole periods first flagged 2024 as
different, because a period carries the reporting currency *and* its USD
translation, and the translation has no class breakdown. A translation is not a
second transaction, and a period-level comparison would have read it as one.

---

## B. The structural half, answered from the archive

The round asked whether ST-EVA could tell the two presentations apart. It can, and
for a reason worth keeping:

> `observations.observation_id` is **content-derived** — `obsarch_` +
> `sha256(content_hash)[:24]` — and the schema says why:
> *"the row id is a physical key derived from the content hash, because the
> contract id is canonical per metric and a restatement of a band would collide
> on it."*

`contract_id` deliberately **excludes the value**, so two facts sharing a contract
but differing in value would collide on it. The archive re-keys on content for
exactly that hazard.

- **Double-count risk: none here.** Both presentations carry the same value, so one
  row is stored — which is correct, because there is one quantity.
- **A dimensional fact with a different value would not collide**; it would be a
  different row.
- **Residual limitation, recorded rather than fixed:** the **member is not preserved
  as a field**, so two members carrying an *identical* value would collapse into
  one row. That is a loss of member distinction, not a miscount, and it is the
  structural shadow of the dimension ambiguity 2.22 measured from the source side.

---

## C. Two defects of my own, both caught by the guard

**The verdict was hardcoded beside a computation that disagreed with it.** The
first run printed `VERDICT: SUPPORTED` while `is_a_distinct_non_cash_transaction`
read `True`. A conclusion written next to a measurement that says otherwise is worse
than either alone, and the verdict is now **derived** from the evidence.

**A verdict computed from nothing.** The first working run found **zero facts** and
still returned SUPPORTED: `all([])` is true, `not []` is true, and an empty set is
the same length as an empty period map. A verdict that absence can produce is not a
verdict, so the script now refuses to conclude without evidence.

The zero came from a real bug, and the guard is what surfaced it: `index.json`
returns `size` as a **string**, so `max` compared lexicographically — `"9820"`
beats `"8404793"` — and it fetched a 9,820-character *exhibit* instead of the
8.4 MB primary document. A wrong document yields no facts; a verdict from no facts
would have looked like a clean result.

---

## D. What remains unexplained, and why it does not change the answer

**Why TSM's schedule of non-cash information carries the same magnitude as the
cash-flow line is still not explained** by either report or by the instance. It
does not change the verdict — one fact, one value per period — but it is
unexplained, and a mapping should carry an explicit non-cash caveat rather than be
treated as unconditionally clean.

That is also the honest boundary of this round: the *question asked* — one fact
presented twice, or two transactions — is answered. The *reason for the second
presentation* is not, and answering it would need TSM's own cash-flow
reconciliation note rather than a tag.

---

## E. State

| | |
| --- | --- |
| full suite | **744 run, 670 passed, 74 skipped**, unchanged |
| production files changed | **none** |
| registry / mappings / definitions / applicability / historical observations | untouched |
| requests | 2 — one filing index, one primary document |

`ifrs_capex_context_237.py` reads the instance through the repository's own SEC
transport and writes `harness/237-tsm-duplicate-context.json` with every fact,
context, dimension, sign and per-unit comparison behind the verdict.

**Where the three candidates now stand:**

```
A  PaymentsForCapitalImprovements                        UNDECIDED, narrowed
                                                         cash-flow basis settled;
                                                         accounting object is
                                                         filer-dependent
B  PurchaseOfPPEClassifiedAsInvestingActivities           SUPPORTED (this round)
                                                         with a non-cash caveat
C  AdditionsOtherThanThroughBusinessCombinationsPPE       REFUTED
```

**Next.** B is eligible for a mapping proposition, and that proposition should
carry the caveat. A needs one small cross-filer round on CCXIU and HPP — the same
presentation check, two more filers — and should not be mixed with B. C needs
nothing.

No mapping proposed, nothing committed.