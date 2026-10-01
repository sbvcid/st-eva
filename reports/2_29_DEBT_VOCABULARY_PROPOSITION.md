# 2.29 — Debt Vocabulary Proposition: SUPPORTED

Not a mapping fix. A proposition test, decided in advance, with the evidence
named.

**No mapping, coverage status, registry entry or applicability rule was changed.**
No data was fetched. Suite 714 run / 640 passed / 74 skipped. Nothing committed.

---

## A. The proposition and its verdict

> The current Core `debt` vocabulary is insufficient to express entity-level debt
> stock for some filers; these filers' `SOURCE_SILENT` partly stems from registry
> vocabulary coverage, not only source absence.

### SUPPORTED — on the half that needed no name matching

> **None of the 29 filers that report nothing for `debt` tags any of the four
> concepts already mapped to it.**

That is the whole first half, and it is a subtraction rather than a judgement:
for every one of the 29, take their raw `companyfacts` document and ask whether
the concepts the registry has declared for `debt` appear at all. None does — not
one filer, not one concept, not one row. `us-gaap:LongTermDebtCurrent`,
`us-gaap:LongTermDebtNoncurrent`, `ifrs-full:LongtermBorrowings`,
`ifrs-full:CurrentPortionOfLongtermBorrowings`: zero coverage across 29 filers.

So the declared vocabulary describes nothing these filers report, and `debt`'s
silence is at least partly a coverage question rather than only source absence.
This is the half the proposition turns on, and it required no string matching.

### The second half is not claimed

> 278 candidate concepts have every fact as an **instant** rather than a
> duration, and 171 of those recur across two or more filers.

Objective, and **necessary but not sufficient.** An instant can be a debt stock, a
debt *security*, a borrowing *capacity*, accrued *interest*, a *ratio* of
indebtedness, or a foreclosed asset. Two concepts that both survive a period-shape
test and mean different things:

```
us-gaap:ShortTermBorrowings
  "Reflects the total carrying amount as of the balance sheet date of debt
   having initial terms less than one year or the normal operating cycle, if longer."

us-gaap:LineOfCreditFacilityCurrentBorrowingCapacity
  "Amount of current borrowing capacity under the credit facility ... but
   without considering any amounts currently outstanding under the facility."
```

Both are instants. One is a liability balance and the other is headroom on a
facility, and only the description tells them apart.

---

## B. What I got wrong first, and why it is worth the round

My first implementation collected candidates by substring and admitted any
instant that passed a description check. It returned **SUPPORTED with 18
"obligation" concepts**, including:

```
us-gaap:DebtSecuritiesAvailableForSaleAmortizedCostAfterAllowanceForCreditLoss
us-gaap:LineOfCreditFacilityCurrentBorrowingCapacity
us-gaap:FederalHomeLoanBankAdvancesGeneralDebtObligationsDisclosuresMaximumAmountAvailable
```

The needle matched debt **securities** because they contain the word "Debt" — a
debt security is an **investment asset**, not a liability. That is precisely the
failure the instruction warned about: *不能靠名稱匹配*.

Four attempts, each leaking a different category:

| pass | what it wrongly admitted |
| --- | --- |
| 1 | debt **securities** — an asset, matched on the word "Debt" |
| 2 | a borrowing **capacity** — not a balance at all |
| 3 | a **ratio** of indebtedness, and a foreclosed asset |
| 4 | accrued **interest**, and a debt **extinguishment payment** |

Every pass produced a confident verdict and a shortlist that was wrong in a
different way each time. **A shortlist this shape cannot be trusted, and the
correct response is to stop producing one.** The instrument now records period
shape, coverage, and the SEC's own label and description for every candidate, and
**judges none of them**.

The name-free half survives all four passes, because it is a subtraction and not
a classifier. That is why the verdict rests on it.

---

## C. The research buckets, as delivered

```
1  candidate stock concepts                    171 instant concepts recurring
                                                 across 2+ filers, with taxonomy,
                                                 filer and accession counts,
                                                 period type, units, SEC label and
                                                 description, dimension-ambiguity
                                                 flag and a representative raw
                                                 fact — UNJUDGED
2  movement concepts                          concepts whose every fact is a
                                                 duration; not a balance by
                                                 construction
3  dimension / aggregation ambiguity          candidates where more than one value
                                                 appears for one period key, so the
                                                 members are not separable from
                                                 this source
4  semantics the payload supplies             the SEC description, recorded
5  semantics NOT established                  278 instant candidates carry no
                                                 description at all — the whole
                                                 `ifrs-full` side supplies neither
                                                 label nor description in
                                                 `companyfacts` — plus the
                                                 duration and mixed-shape counts
```

Bucket 5 is the finding, not a failure to fill bucket 1: **`companyfacts` cannot
settle semantics for the IFRS half of this vocabulary at all**, and for the
us-gaap half it settles them only by supplying the SEC's prose, which a human or a
stated proposition has to interpret.

---

## D. What is established and what is not

**Established.** The vocabulary gap is real — zero coverage of the declared
concepts across 29 filers. It is not an artefact of one filer. It is wider than
one concept, with 171 instant candidates recurring across filers.

**Not established, and not to be inferred from this round:** that any named concept
is a debt stock, that any of them belongs to the current or the non-current side
of the composition, or that mapping any of them would be correct.

**The next proposition** is narrower and must state its own basis: *for a given
filer set, does `us-gaap:ShortTermBorrowings` carry the same quantity as the
`debt` decomposition's current side?* That is a comparability question about
carrying amounts, and its evidence would be value relationships against concepts
the registry already maps — not a substring and not an instant.

---

## E. Why this does not touch the registry

Three reasons, in the order they bind:

1. **The proposition does not decide the mapping.** SUPPORTED establishes that the
   vocabulary is insufficient. It says nothing about which concept fills the gap,
   and 2.26 is explicit that a refusal or a mapping requires its own decision with
   a named basis.
2. **The candidates are not yet vetted.** 171 recurring instant concepts is a
   *search space*, not a shortlist. Naming a mapping from it now would be the
   name-matching failure with one more step of distance from the data.
3. **`debt` is a declared composition.** `long_term_debt_current` and
   `long_term_debt_noncurrent` exist so the parent can be assembled from a
   filer's own current/non-current split. A concept like `ShortTermBorrowings` is
   plausibly the *current* side, and possibly the whole of it for filers that
   report no long-term debt at all. Either answer changes what the components
   mean, so it belongs with the composition, not beside it.

## F. State

| | |
| --- | --- |
| full suite | **714 run, 640 passed, 74 skipped**, unchanged |
| production files changed | **none** |
| fetched | **nothing** |
| registry / mappings / declines / coverage / applicability | **unchanged** |
| refusal surface | empty; audit green |
| commits | 2.27 at `7cb5e27`; 2.28 and 2.29 not committed |

`debt_vocabulary_229.py` is read-only against the existing archives and writes
`harness/229-debt-vocabulary.json`.