# 2.21 — What the 40 observations actually are

2.20 closed the equivalence chain and left the semantic question standing:
`BANK → gross_profit NOT_APPLICABLE`, against 2 of 8 banks that report a mapped
gross profit concept. The standing order was not to overturn the rule on 2 of 8
but to turn it into an explicit, testable proposition.

That means characterising the evidence before stating anything. Which is what
produced the finding — and it narrows the counterexample count from two to one.

---

## A. Two banks reported it. One of them is not a counterexample.

```
NRIM    22 obs   us-gaap:GrossProfit   unit currency   10-K x6, 10-Q x16
        17 distinct periods, 5 carrying more than one value
        4 of those 5 are IDENTICAL values   -> a restated comparative filed twice
        1 is genuinely different: 2025 Q1  46,906,000 -> 45,746,000
        range 34.1M .. 208.9M

BBAR    18 obs   ifrs-full:GrossProfit  unit RATIO      20-F x18
        8 distinct periods, 6 carrying more than one value, and they diverge:
          2019   88.8B / 120.9B / 182.5B
          2022   368.3B / 1,146.8B / 2,497.3B
```

**BBAR is not evidence for or against anything.** A restatement moves a number;
it does not move it sevenfold. Six of BBAR's eight periods carry two or three
distinct values, spread by factors of three to seven, all tagged
`ifrs-full:GrossProfit` in a `ratio` unit on a 20-F. That is the signature
2.14's `dimension_collisions` counter was written to catch: **the aggregated
endpoint hides dimension members, so several different facts arrive looking like
one.** BBAR's 18 observations are not 18 comparable gross-profit values.

And the archive already knew. `dimension_collisions` for these eight filers:

```
AUBN 11    BBAR 133   CCFN 2    CZWI 65
FCNCP 86   FHB  (0)   NRIM 48   PFBX 59          404 total
```

133 for BBAR, the filer whose gross profit is flattened.

**NRIM is a clean counterexample.** A US savings institution filing
`us-gaap:GrossProfit` as a quarterly line beside its 10-Q, with ordinary
restatement behaviour — the same period revised once, in the following year's
filing, which is what restatement *is*.

So the honest count is not "2 of 8 banks report gross profit". It is:

| filer | reports a mapped gross profit concept | the state it puts the question in |
| --- | --- | --- |
| NRIM | yes, 22 rows, quarterly, currency | **valid positive evidence** against a BANK-wide rule |
| BBAR | yes, 18 rows, annual, ratio units | **dimension ambiguity, meaning unresolved** |
| other 6 | no | `SOURCE_SILENT` |

BBAR is **not subtracted from a count** — it is the project's existing ambiguity
contract, arrived at by a different route: source concept present, dimension
ambiguity, semantic meaning unresolved. 2.22 persisted the collisions per metric,
which is what made it a state rather than an inference.

**One genuine counterexample, one artefact.** And the difference between them is
only visible because the collisions were counted — see section C.

---

## B. The proposition, stated

> **Does `BANK` imply that `gross_profit` is `NOT_APPLICABLE`?**

> **Corrected in 2.22.** The two paragraphs below conflated a refutation with an
> open decision, and the distinction matters. One valid counterexample refutes a
> universal rule; it does not leave it "not yet decidable for this sample".

As a general proposition about banks: **refuted.** One filer of eight reports an
entity-level gross profit subtotal under a mapped concept, quarterly, in its own
10-Q, and it is a real reported line rather than a dimensional artefact. **One is
enough; eight is not needed.** The specific failure this prevents is "the sample
is too small, so we keep `NOT_APPLICABLE`", which would keep a rule alive that has
already been contradicted.

What remains open is the **replacement**, not the refutation:

```
BANK -> gross_profit NOT_APPLICABLE     REFUTED
BANK -> ?  (the replacement)            UNDECIDED
```

and the six filers that report nothing are evidence about the replacement rather
than about the rule.

And the vocabulary has no way to say any of that:

```python
def applies_to(self, business_model):
    if self.applicability == "NOT_APPLICABLE":     return False
    if not business_model or not self.inapplicable_in: return True
    return business_model not in self.inapplicable_in
```

**Binary.** There is no conditional. So "a bank *may* report gross profit, and
this filer *does*" is not expressible — which is precisely the situation the
evidence describes.

### The three options, with what each costs

**Narrow the rule** — remove `BANK` from `gross_profit.inapplicable_in`. Then six
banks that report no gross profit get `SOURCE_SILENT` forever, which is honest but
noisy, and the six would have been better served by the rule. Cost: trades a
known-wrong refusal for six recurring retrieval backlogs.

**Keep it** — accept that one filer's reported gross profit is collected and then
not counted. Cost: the archive holds 22 observations no consumer of the coverage
surface will ever see, and the conflict marker becomes permanent furniture for
NRIM.

**Make it conditional** — `BANK` stops being a rule and becomes a prior, resolved
per filer by whether that filer actually reports the concept. Cost: it is the
largest change of the three, because it moves applicability from a *statement about
the company* to a *statement about the filer's reporting*, which is what
`SOURCE_SILENT` is already for. It also means the 2.19 conflict stops being
expressible for this pair — the two mechanisms would be solving the same problem.

**No option is taken here.** The evidence says the first proposition is false and
the second is undecided; deciding between the three needs the population to widen,
and section C says what has to be fixed before that evidence can be trusted.

---

## C. The gap that blocks deciding on a bigger sample

`dimension_collisions` is counted per run, per issuer, and printed in the
ingestion report. It is **not persisted per metric**, so it cannot be joined to
the semantic conflict.

The consequence is concrete: BBAR's `gross_profit` conflict looks exactly like
NRIM's.

```
BBAR   gross_profit  NOT_APPLICABLE  18 obs  ['ifrs-full:GrossProfit']
NRIM   gross_profit  NOT_APPLICABLE  22 obs  ['us-gaap:GrossProfit']
```

One is a refutation and one is an artefact of reading from a single aggregated
document, and a consumer reading the coverage surface has no way to tell them
apart. **The measurement exists; it is filed at the wrong grain.**

So before a larger bank sample is used to decide anything, the collision count has
to travel with the metric. That is engineering — `ingestion_scope` is already keyed
by `(run_id, asset_id, metric_id)`, and the counter is already computed inside
`_store_facts`, where the metric is in hand. Not done this round, because the
instruction was to state a proposition rather than build instrumentation, and
because doing it half-way would make the conflict marker look more authoritative
than it is.

Until then, any count of "how many banks report gross profit" taken from this
archive is wrong, and the direction of the error is toward over-counting.

---

## D. The same question for `r_and_d` and `sga`

Both are `SOURCE_SILENT` at 8 of 8 and 7 of 8, and both are **not** contradicted by
anything — no bank tags the concepts, so there is no conflict, only silence.

They are therefore the opposite case from `gross_profit`, and the cheap test is
different: they need more filers, not better characterisation of existing ones.
`INSURANCE` and `MINING` have no filer anywhere, which is the only remaining
sufficient reason to fetch new data.

Note the asymmetry worth carrying forward: **a rule that fires and is contradicted
is more informative than a rule that fires and is silent.** `gross_profit` has
already taught us something about banks that eight `SOURCE_SILENT` results could
not.

---

## E. State

| | |
| --- | --- |
| full suite | **633 passed**, 74 skipped, 707 run (+2) |
| production change | none |
| tests | 2 added to `tests/test_semantic_conflict.py` |
| archives | read only; nothing modified in place |

The two new tests pin the pair that makes the argument hold: the rule under
dispute is a **live seeded rule** — `gross_profit.inapplicable_in` contains `BANK`
and `applies_to("BANK")` is False — and the vocabulary **cannot currently express
conditionality**. The second is a gap marker, written to fail if anyone adds
`CONDITIONAL`, because the first thing they will have to decide is whether a
conditional ruling satisfies or overrides the conflict marker, and it is not
obvious.

## F. Where this leaves the roadmap

```
2.20  bulk/API equivalence closed                    done
2.21  gross_profit evidence characterised            done
      next, in order:
  1. per-metric dimension collisions, so a conflict
     marker can tell a refutation from an artefact
     -> DONE in 2.22, and it corrected this report's
        framing as well as the measurement
  2. INSURANCE and MINING filers -- the only remaining
     sufficient reason to fetch
  3. decide BANK -> gross_profit with evidence that
     can be trusted at that size
  4. r_and_d and sga, which need population rather
     than characterisation
```