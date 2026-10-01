# 2.19 — Evidence, applicability and coverage are three facts

2.18 produced a contradiction and left it sitting in an archive:

```
                ledger status        observations in the archive
gross_profit    NOT_APPLICABLE       40   (BBAR 18, NRIM 22)
operating_income NOT_APPLICABLE        0
```

Eight banks, all classified `BANK` from their own SIC, `gross_profit` ruled out
for banks — and forty reported gross profit facts held and addressable. This
settles what that means and makes the archive say so in words rather than leaving
a reader to notice two columns disagreeing.

---

## A. The decision

**A coverage interpretation is not a deletion filter on evidence.**

The tempting alternative was to refuse to store observations for a metric the
ledger calls inapplicable, so the archive and the coverage layer would agree. That
would have been a mistake, and this round is the evidence for why:

> Those forty observations are the *entire* finding. They are how
> `BANK → gross_profit NOT_APPLICABLE` was caught as too broad. Had ingestion
> refused them on the grounds that the metric was ruled inapplicable, the ledger
> would have read zero, the rule would have looked **confirmed**, and the error
> would have been locked in by the very mechanism meant to catch it.

A rule that cannot be contradicted by evidence is not a rule. It is an assumption
with a column.

So nothing is deleted, the disagreement is named, and what a consumer does about it
stays its own decision.

---

## B. Three facts, three places — and why the obvious shortcut was rejected

```
Evidence existence   did the source report this metric?
Applicability        should it mean anything for this filer?
Coverage             have we handled it?
```

In the bank archive these three disagree for the first time:

```
Evidence      = yes   (40 observations, two concepts, one filer each)
Applicability = no    (the registry rules gross_profit out for BANK)
Coverage      = handled   (collected, ruled on, contradicted)
```

The tempting encoding is a `SEMANTIC_CONFLICT` *status*. It was rejected, for a
reason that is mechanical rather than philosophical: **a status is a partition of
the Core universe.** `scoped_ledger` guarantees that the status counts sum to
`metrics_total` — 20 for every filer — and every reader that reconciles a tally
against the registry depends on that. Moving a conflicted cell into a status of its
own breaks the sum, and it does so silently.

So the conflict is a **derived marker beside the status**, not a fourth value of
it:

```json
"status": "NOT_APPLICABLE",
"observations_held": 22,
"semantic_conflict": {
  "kind": "EVIDENCE_HELD_FOR_INAPPLICABLE_METRIC",
  "applicability": "NOT_APPLICABLE",
  "observations_held": 22,
  "concepts_reported": ["us-gaap:GrossProfit"],
  "ledger_status": "NOT_APPLICABLE",
  "note": "..."
}
```

Reported on every ledger row, counted in `ledger["semantic_conflicts"]`, carried
through `collection_chain`, and printed by the gate tool.

**Over the eight banks, exactly two cells conflict:**

```
BBAR    gross_profit    18 obs    ifrs-full:GrossProfit
NRIM    gross_profit    22 obs    us-gaap:GrossProfit
```

and the statuses still sum to 20 on every filer.

### Three things deliberately *not* done

- **The conflict is not a backlog item.** `NOT_YET_COLLECTED` means work to do:
  the metric has not been handled. This metric *has* been handled — collected,
  ruled on, and contradicted — which is a different state and is flagged
  separately rather than being folded into the one that means "get to this".
- **The conflict is not scored.** The gate tool reports it and says plainly that
  it is not scoring it, because whether a conflict should fail a gate is an open
  decision and the tool does not take it quietly. It currently passes
  `observations` (22 > 0) *and* counts under `NOT_APPLICABLE` at the same time,
  which is the honest reading of three independent facts.
- **A decline is not a conflict.** Declining a concept is a recorded decision
  about that concept, and a metric the registry has already routed around is not
  evidence contradicting a ruling.

---

## C. The regression guard

`tests/test_semantic_conflict.py`, 11 cases, and the fixture is deliberately the
hardest version of the situation: a filer that classifies as `BANK`, reports
`us-gaap:GrossProfit`, and is asked for a metric the registry refuses it. Nothing
about the run is exceptional — the conflict arises from the registry, not from
anything the pipeline did.

What it pins:

```
the observation is stored                              1 row, addressable
the ledger still reports NOT_APPLICABLE
both facts are in the same row                          no join required
the conflict is named, with its concept
the conflict is counted at the ledger level
the status counts still partition the Core universe    sum == metrics_total
a conflicted cell is not a backlog item
a silent inapplicable metric raises no conflict
a quiet cell stays quiet                                only one fires
```

That last group matters as much as the first. A marker that fires constantly
teaches a reader to ignore it, so it has to stay silent everywhere the three facts
agree — and there are 158 of those cells in this archive against 2 that fire.

One fixture bug was caught by writing it: the fake source answered for *both*
declared `gross_profit` concepts, so two observations appeared where there should
have been one. A test for "the evidence survives the rule" has to be about one
real fact, or it measures the fixture.

---

## D. The three dimensions, measured and now enforced

The last of 2.18's structural findings, and the clearest statement of why it
matters:

| dimension | NRIM in this archive |
| --- | --- |
| **filing universe** | 128 filings held, from the filer's own submissions |
| **evidence universe** | 2,695 observations across 14 metrics |
| **coverage state** | 13 collected, 5 silent, 2 not-applicable, 0 backlog |

**All three are different numbers and none of them substitutes for another.** A
reader who takes `filings held` as evidence coverage is wrong by two orders of
magnitude. 2.18 measured the same thing from the other end — `filings_held` 389 →
858 while `distinct_accessions_in_observations` stayed at 389 — and BBAR's ledger
was sixteen times narrower than the filer's own account of itself while its facts
were untouched.

These three, plus the applicability ruling, are now four separately reported
things. They are no longer allowed to be read as one.

---

## E. State

| | |
| --- | --- |
| full suite | **631 passed**, 74 skipped, 705 run (+11) |
| production change | `coverage_semantics` (conflict marker), `score_collection_gates` (reports it) |
| the 5,447 / 88 / 0 | **5,447 semantic-equivalent, 88 known-stale-reference differences, 0 unexplained** |
| regressions | six-issuer, twelve-issuer and eight-bank runs re-run, all reproduce exactly |
| archives | `snapshot-banks2.sqlite`, not modified in place |

The three prior measurements reproduce unchanged, including the six-issuer
reconciliation that 2.14 recorded to the row.

---

## F. What is next, and one cheap confirmation

**The semantic contract is settled. What remains is closing, then widening.**

1. **A corrected API reference.** Not because there is serious doubt — the 88 are
   fully explained as the pre-fix fabrication in the older archive — but because
   "5,447 equivalent, 88 known-stale, 0 unexplained" is an argument and
   "5,535 / 5,535" is a measurement. Rebuilding the reference under the
   corrected availability contract and reconciling would close it.

2. **`BANK → gross_profit`.** The conflict is now named, so the decision has a
   stable input to reason from. Narrow the rule, keep it, or accept that two
   filers' reported gross profit is collected and not counted.

3. **A real cross-business-model population.** The bank sample is homogeneous by
   construction — eight SIC 60 filers. INSURANCE and MINING still have no filer
   anywhere, and the type axis cannot be exercised until they do.

No further bulk machinery. `companyfacts + submissions` covers the context the
current layer needs, and the remaining work is semantic.