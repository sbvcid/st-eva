# 2.26 — Only `SUPPORTED` may refuse, and nothing is

The question 2.24 left open was whether a `TESTABLE` rule could keep refusing
collection. It could, which meant an unsupported hypothesis held production
authority over Evidence — the same defect as a screening heuristic wearing a
rule's clothes, except that this one also edited the archive's coverage surface.

This answers it, and then checks the consequence against every archive.

```
                    PROPOSED / TESTABLE / UNDECIDED   ->  may not refuse
                    SUPPORTED                          ->  may refuse
                    REFUTED                            ->  must not refuse
```

---

## A. The change

`metric_inapplicable_in` and `metric_exclusion` were the same table doing two
jobs. Now:

```
metric_exclusion        a proposition, its state, its falsifiable claim, and who
                       refuted it. Recorded whatever the state.
metric_inapplicable_in  the refusal surface. Only SUPPORTED reaches it.
```

Migration `0015` carries any existing row over as `TESTABLE` — a rule written in
2.7 with no evidence claim recorded is exactly what "testable, never tested"
means — and then empties the refusal surface. Nothing is deleted; the
hypotheses are queryable.

A refusal can now only come into existence by an explicit act,
`registry.support_exclusion(metric, model)`, which is deliberately not a data
edit: refusing Evidence collection is a decision, so it is made like one.

**What survives in the registry:**

```
metric_exclusion       {"operating_income": {"BANK": "TESTABLE"}}
metric_inapplicable_in  0 rows
```

One open question, recorded with its claim, refusing nothing.

---

## B. The four checks, on all three archives

```
corpus                          NOT_APPLICABLE   observations   held+visible
BANK x8                                    0          11,174        11,174
FINANCE_SERVICES x7                        0          12,489        12,489
MINING + INSURANCE x8                      0          16,351        16,351
```

**Evidence unchanged** — every observation count identical to before the change,
and **every observation held *and* visible**, meaning no metric lost its
collected count to a refusal.

**Coverage re-reflected** — `NOT_APPLICABLE` is now **zero cells in every
archive**, because no rule has the standing to produce one. `applicability`
reads 160/160 on both remaining corpora, `adoption` 140/140 on the
FINANCE_SERVICES one, and the `observations` gate is unchanged at 95/160, 106/140
and 110/160 — the same figures, reached without a refusal anywhere.

**The 705 collected-then-refused observations all survive**, plus the 258 from
2.24 and the 39 from 2.25: nothing was ever discarded, and every round of
refuting a rule turned collected-then-hidden into simply collected.

---

## C. What this makes of `NOT_APPLICABLE`

It is now a much harder thing to be, and the vocabulary does not need to change
to say so:

```
no rule                            -> the metric is asked
the source reports it               -> COLLECTED
the source has nothing              -> SOURCE_SILENT
the source has nothing and the line
  provably does not exist           -> NOT_APPLICABLE
a filer contradicts a refusal        -> CONFLICT
```

`NOT_APPLICABLE` no longer means *"an analyst would not expect this company to
have this number."* It means **ST-EVA has affirmative evidence that this metric is
not part of the issuer's core evidence**, which is a much higher bar and matches
what an Evidence layer should claim.

`TESTABLE` does not appear in the runtime coverage vocabulary at all. It is a
**rule lifecycle state**, not an Evidence state, and keeping it out of the ledger
is what stops an open question from reading as a settled answer.

---

## D. What this says about the first generation of rules

**ST-EVA has no applicability rule with sufficient evidence to refuse anything.**
Four were written in 2.7 from category intuition; three were refuted by filers of
their own class; the fourth is unsupported and now refuses nothing.

That is not a failure of the rules. It is the first honest result the rules could
have produced, and the alternative to reaching it — promoting the surviving
hypothesis on the strength of eight silent banks — is the exact move the
`SUPPORTED` bar now forbids.

```
gross_profit  x BANK             REFUTED  NRIM, 22 obs
r_and_d       x MINING           REFUTED  NEM, 236 obs
gross_profit  x FINANCE_SERVICES REFUTED  3 of 7, 39 obs
operating_income x FINANCE_SERVICES REFUTED  6 of 7, 666 obs
operating_income x BANK           TESTABLE  8 banks silent, no support
```

---

## E. Cost, stated rather than assumed

Three classes now answer `SOURCE_SILENT` each time their filing universe moves,
where a refusal would have stopped asking. That is real recurring work and it is
**not** a coverage debt: `NOT_YET_COLLECTED` is the only status that means work to
do, and these cells are handled — the source was asked and had nothing.

The reduction in cost that matters is the one nobody will miss: the coverage
surface stopped asserting things it could not support. A `NOT_APPLICABLE` cell is
an answer, and an answer nobody can defend is worse than a question that is
recorded and visible.

---

## F. State

| | |
| --- | --- |
| full suite | **637 passed**, 74 skipped, 711 run (−8 net) |
| production changes | `core_registry` (hypothesis layer, `support_exclusion`, `exclusion_states`), `registry_seed`, migration `0015` |
| refusal surface | **0 rows**, across every archive |
| open propositions | 1 — `operating_income × BANK`, `TESTABLE`, with its falsifiable claim |
| `NOT_APPLICABLE` cells | **0** in all three corpora, from 8 before |
| evidence | unchanged in all three; every observation held and visible |
| equivalence | 11,174 / 11,174, 0 divergent, 0 one-sided |
| PIT invariant | holds on all three |

Thirteen tests failed when this landed, all exercising a refusal that the seed no
longer provides — the correct failure direction. Every one of them now creates
its refusal explicitly through `support_exclusion`, which means the semantics of
`NOT_APPLICABLE` are tested against a refusal somebody made rather than one
nobody remembers making.

One test migration bug worth recording: the first version of `0015` read and
deleted `metric_inapplicable_in` before creating it, because that table was
created lazily by the registry rather than by a migration. It broke 286 tests,
which is a good ratio. Making the refusal surface part of the versioned schema
rather than an artefact of a write is the right fix regardless.