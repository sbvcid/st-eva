# 2.6.3 — Ambiguity classified from evidence, and a model that is repeatable

Two production defects fixed, one harness capability added, and the first run
series in the project. The order is the point: the surface was wrong before any
model was measured, so it was fixed first, and only then was the same model run
three times against the corrected surface.

---

## 1. What was fixed, and what it was actually costing

### 1.1 The ambiguity block told a story it had no evidence for

`EvidenceQuery._ambiguity_for` returned one sentence for every case, whatever the
cause:

> "Several observations share this metric, period **and source concept** but
> report different values. ST-EVA does not know which one is meant and has not
> chosen: **the source endpoint aggregates dimension members without returning
> the member**, so the aggregate is not identifiable from the evidence held."

Measured against the AAPL snapshot, that sentence is wrong in **107 of 107**
ambiguity groups. Not wrong sometimes: wrong every time, including on the exact
example the method's own docstring used as its worked demonstration.

| shape, measured from the rows | groups | the old sentence said |
| --- | --- | --- |
| `MULTIPLE_SOURCE_CONCEPTS` — different concepts | **68** | same concept, aggregated |
| `MULTIPLE_FILINGS` — one concept, several accessions | **38** | same concept, aggregated |
| `CROSS_PROVIDER_DISCREPANCY` — different providers | **1** | same concept, aggregated |
| `DIMENSION_COLLISION` — one filing, one concept, two values | **0** | — this is the only shape it fits |

The docstring's own example, AAPL's FY2007 revenue, is `MULTIPLE_FILINGS`: a 10-K
(`0001193125-09-214859`) against a 10-K/A (`0001193125-10-012091`). Two filings,
not two dimension members. And the largest class is worse than a mis-attribution.
`debt` at 2014-09-27 is reported as `LongTermDebtCurrent` **and**
`LongTermDebtNoncurrent`; `cash` at 2019-03-30 as
`CashAndCashEquivalentsAtCarryingValue` and
`CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents`. Those are
different measures. There is no choice between them, and a reader told they are
two readings of one aggregate will pick one and report it as a fact about the
metric.

### 1.2 It cost real answers, and the evidence is in the 2.6.2 traces

| | answers asserting the dimension-aggregation mechanism | answers |
| --- | --- | --- |
| before the fix (2.6.2 runs) | **5** | 10 |
| after the fix (2.6.3 runs) | **0** | 38 |

And 8 of the 38 answers now quote the classification itself, e.g.
`MULTIPLE_FILINGS` for the revenue case. The models were not making this mistake.
They were reporting what the surface told them, which is what an evidence
database exists to prevent.

### 1.3 The fix

`reason` is now a code drawn from a closed vocabulary, decided by a pure function
of the gathered evidence:

| reason | decided by | `same_measure_established` |
| --- | --- | --- |
| `CROSS_PROVIDER_DISCREPANCY` | rows carry different providers | false (one side is unmapped) |
| `MULTIPLE_SOURCE_CONCEPTS` | rows carry different `source_concept_ref` | **false** |
| `DIMENSION_COLLISION` | one concept, one filing, two values | true |
| `MULTIPLE_FILINGS` | one concept, several accessions | true |
| `MULTIPLE_OBSERVATIONS` | nothing identifiable — the honest fallback | depends |

The order of the branches is part of the contract and is documented as such:
providers subsume everything, concepts come before filing identity, and only
exactly one known accession licenses the aggregation story. `resolution` stays
`NO_WINNER_SELECTED` in every case — the 2.6.2 evidence was that weakening that
is how a model ends up asserting a winner.

Three things came with it:

- **`basis`** — the evidence the classification was read from: distinct concepts,
  providers, source types, accessions, row and value counts. A consumer can
  check the code against the rows instead of taking either on trust.
- **`same_measure_established`** — stated outright rather than inferred from the
  reason, because the inference is the failure. For `MULTIPLE_SOURCE_CONCEPTS` it
  is False, and a reader who wanted one number is being told neither of these may
  be it.
- **`recorded_cross_check`** — for the cross-provider case, the archive's own
  `DISCREPANT` validation record, quoted rather than re-derived, and
  `determination` becomes `FROM_RECORDED_EVIDENCE`. Where the archive knows why,
  the archive says so.

The explanation text is generated from the class (`_ambiguity_explanation`), so
it cannot claim a mechanism the classification did not establish. A
`CROSS_PROVIDER` explanation that mentioned dimension aggregation is now
unreachable by construction rather than by review.

`source_concept_ref` is the column the classification reads, and deliberately not
`concept`. The vendor observation in this archive stores the *metric id*
`shares_outstanding` in `concept`, because a vendor API reports no XBRL tag.
Reading `concept` would have put a metric id beside
`dei:EntityCommonStockSharesOutstanding` and invented a second measure that does
not exist. Reading the registry-resolved column and treating NULL as unmapped is
the archive's own convention, and it makes `same_measure_established` False for
that pair — which is correct: a filing and a vendor quote of share count are a
cross-source discrepancy, not two readings of one source.

**The classification is `classify_ambiguity(basis)`, a pure function with no
database in it.** That is the structural change. A classification that can only
be exercised through SQLite is one nobody will exercise, and this one decides
whether a consumer is offered a choice at all.

### 1.4 Tests

The ambiguity block had **no production test of any kind** before this — the only
`NO_WINNER_SELECTED` assertion in the suite was on a validation record, not on
this block. That is how one sentence sat in the codebase being wrong 107 times
without anything noticing. There are now 9 tests in
`tests/test_evidence_query.py::TestAmbiguityIsClassified` pinning each class, the
order of the branches, the closure of the vocabulary, the empty-basis case, and
specifically that no explanation may contain a cause the classification did not
establish. Plus 2 for the derived value. 496 offline tests pass, up from 482.

### 1.5 `get_lineage` returns the stored derived value at the top level

`der:current_ps` returned 31.42 only inside `chain[0]`, one level down, in a
payload whose entire purpose is to answer "what is this derived figure and how
was it made". A consumer now gets `value`, `unit` and `expression` at the top
level next to the operands, and `recomputation` states
`recomputed_by_query: false` and `value_source: STORED_DERIVED_VALUE` in the same
payload. The value is read back from the archive; the query layer is still not a
second calculation engine, and the tests assert both halves of that.

**This fix did not change the behaviour it was aimed at.** See section 4.2.

---

## 2. The one thing that also had to change, in the grader

`harness/dataset.py::_ambiguity_side_sets` re-derives the acceptable "sides of a
conflict" for T8 so that the grader accepts any archive-presented disagreement
rather than one arbitrarily selected record. Its 2.6.2 version accepted any two
figures for one metric and period with different values — all 107 groups,
including the 68 that are two different measures.

Offering those to a model as a disagreement to preserve is asking it to choose
between a question it was not asked and an answer that may not fit it. The
grader now applies the same same-measure restriction, re-derived independently
so it does not depend on the surface it is grading.

`verify_harness.py` is unchanged and still shows the reference target at 0/15
with each deliberately broken target failing exactly the one test it was built
to fail. T8 is still caught for `picks-winner`, T1 still for `hides-ambiguity`.

---

## 3. Request budget, refusal classification, and a provider outage

The 2.6.2 report noted that a `429` had to be distinguished from a model failure
by a human reading a log. That is exactly the thing a harness should not leave to
a reader. `harness/budget.py` now owns it:

| | |
| --- | --- |
| `declared_limit` / `requests_sent` / `remaining_budget` | counted **on the way out**, so a refused request spends the allowance — the case that actually bites |
| `rate_limit_headers` | recorded from the response, not inferred afterwards |
| `refusals_by_kind` | `rate_limited`, `provider_error`, `model_unavailable`, `malformed_response`, `network` |
| `model_finding_refusals` | always 0. The field exists so the check is made rather than assumed |
| `stopped_because` | a budget stop, a refusal run, or a withdrawn model, each naming itself |

`rate_limited` and `provider_error` are retryable; `model_unavailable` is not,
because retrying a model that no longer exists is how a run loses its whole
allowance. Three refusals of one kind with no answer in between end the phase.

### It mattered within an hour of being written

Run 3's first attempt hit three consecutive `503 provider_overloaded` from the
upstream Nvidia provider. The budget stopped the phase after **3 of 120
requests**, and the remaining twelve tests were recorded as `budget_exhausted` /
E — not as twelve model failures. The run directory reports **0/15**, and that
number is an artefact of a provider having a bad minute. The attempt is preserved
at `full/run3-attempt1-aborted-by-provider/` and is **excluded from the run
series by rule**, not by hand, with the exclusion printed and recorded in
`variance-*.json`.

Without this the variance table would have been garbage: averaging a 0/15 outage
in as a fourth run turns every stable result into "unstable".

---

## 4. Nemotron × 3

`nvidia/nemotron-3-ultra-550b-a55b:free`, temperature 0, seed 7, 8 exchanges.
Snapshot `ce603a5588cef067`, dataset `4af104d3508e110f`, tool schema
`5a2784a6dc7d7a9b`, evaluator and prompt unchanged from 2.6.2. Every run is its
own directory; the 2.6.2 run is untouched.

**run 1: 10 pass / 5 fail · 64 requests · 0 refusals**
**run 2: 8 pass / 4 fail / 3 E · 58 requests · 3 provider errors**
**run 3: 9 pass / 5 fail / 1 E · 56 requests · 1 provider error**

### 4.1 Per test, and what a pass count hides

| test | r1 | r2 | r3 | | capability | failed because |
| --- | :-: | :-: | :-: | --- | --- | --- |
| T1 exact value | P | P | P | **stable** | retrieval | |
| T2 series | P | P | P | **stable** | retrieval | |
| T3 pagination | P | P | P | **stable** | pagination | |
| T14 truncation | P | P | P | **stable** | pagination | |
| T4 point-in-time | P | P | P | **stable** | temporal | |
| T5 source attribution | P | P | P | **stable** | provenance | |
| T11 partial mapping | P | P | P | **stable** | concepts | |
| T12 non-comparable | P | E | P | unstable | concepts | missed a concept |
| T10 concept evolution | P | F | F | unstable | concepts | missed a concept |
| T13 provenance chain | F | E | P | unstable | provenance | cited an unretrieved document id |
| T8 conflict | F | P | F | unstable | conflict | one side uncited |
| T15 inference boundary | P | E | E | 1 decided | interpretation | |
| T6 reported vs derived | F | F | F | **stable fail** | interpretation | `get_lineage` never called |
| T7 validation | F | F | F | **stable fail** | provenance | 8 exchanges, no answer |
| T9 unavailable | F | F | F | **stable fail** | negative states | collapsed three negative states |

**Seven tests are stable across three runs. Four are stable failures. Four are
unstable, and three of those four flip between PASS and FAIL on the same
configuration.**

### 4.2 The `get_lineage` fix, and an honest negative result

T6 is the test the derived-value fix was aimed at, and it failed 3/3 after the
fix. The trace says why: in all three runs the model called
`query_observations` and nothing else. It never called `get_lineage`. It searched
for a *metric* named `ps`, was told the metric does not exist, and answered
about metrics.

So the limitation was real and is now fixed, and this model is not the one to
show it working. The failure is upstream of the fix: the model does not reach
for the operation.

The question text is also a factor and is not being fixed here: it renders the
reference as "Was **current ps** for AAPL reported by a source, or calculated?"
— the words "current ps" with no signal that they name a *derived value* rather
than a metric. A model that took the question at face value would do exactly what
this one did. That is a **D candidate for the next round**, recorded with the
evidence rather than quietly fixed, because changing the question changes the
dataset and the 2.6.2 baseline with it.

### 4.3 Grounding

| | |
| --- | --- |
| identifiers cited across the three runs | **79** |
| valid observation ids | **78** |
| identifiers that do not exist | **0** |
| source-fact or derived references cited in `evidence_refs` | 0 |
| wrong-namespace identifiers | **1** (`doc_24e18832…` in `evidence_refs`, T13, run 1) |
| off-surface tool calls | **0** |

**Zero fabricated identifiers in 45 test-attempts.** One model, three runs, 79
citations, none invented. For an evidence database this is the number that
matters most, and it is the one the 2.6.2 run got wrong once.

---

## 5. Capability gate — by what the model is for, not by its score

The pass count is the wrong summary. 9/15 says less than "it paged correctly in
three runs out of three and invented an identifier in none", and the second is
what a consumer is buying.

| consumer capability | passes | fails | interrupted | reading |
| --- | :-: | :-: | :-: | --- |
| **evidence retrieval** | 6 | 0 | 0 | **strong and stable** |
| **pagination** | 6 | 0 | 0 | **strong and stable** — including the truncation trap |
| **temporal discipline** | 3 | 0 | 0 | **strong and stable** — honours a historical cutoff |
| **concept semantics** | 6 | 2 | 1 | good, with an unstable recall edge |
| **provenance** | 4 | 4 | 1 | **split**: attribution stable, full chain unstable, validation metadata absent |
| conflict handling | 1 | 2 | 0 | **not reliable** — flips between runs |
| **reported vs derived** | 1 | 3 | 2 | **does not hold** |
| **negative states** | 0 | 3 | 0 | **does not hold** |

`nvidia/nemotron-3-ultra-550b-a55b:free` is **ACCEPTED as a grounded retrieval and
verification consumer, and NOT ACCEPTED as an unsupervised interpreter.**

The dividing line is not difficulty, it is layer. Everything that requires the
model to *find and cite* evidence is stable across three runs at 100%. Everything
that requires it to *classify* what the evidence means — a derived value versus
a reported one, `SOURCE_DID_NOT_REPORT` versus `UNAVAILABLE` versus `STALE`, a
conflict versus two different measures — is where it fails, and three of those
failures are stable enough to be structural rather than bad luck.

T9 is the sharpest case. Asked to distinguish three negative states the surface
reports precisely, it answered correctly about the one metric in the question and
collapsed the other three. It did not invent a value and did not assert an
absence. It simply did not carry a distinction the archive had made for it.

Against the six gate criteria from 2.6.2, unchanged: tool use yes, valid evidence
yes, no escape yes, one provenance task handled correctly yes, no invented
identifiers yes, and **criterion 5 — not treating empty results as evidence
absence — remains the open one**, on T6 rather than on T8 this time.

No ranking is given and none is implied. One model, three runs, and the run-to-run
movement in section 4.1 is the reason: T8 and T13 flip on an identical
configuration.

---

## 6. What the 2.6.2 report said about these two models still holds

Unchanged, because nothing this round touched them:

```
Nemotron 3 Ultra:
- tool use: strong
- retrieval: generally capable          -> now: strong and stable, 3/3
- provenance: mostly grounded           -> now: split; 0 fabricated in 79 citations
- semantic discipline: generally good   -> now: NOT supported; 0/3 on negative states
- run variance: present                 -> now: measured; 3 of 15 tests flip
- 1 ST-EVA Query semantic defect exposed -> fixed, 5 false claims -> 0
- not yet a stable benchmark            -> now three runs; a real series, one model
```

```
Space Bunny Alpha:
- tool use: strong
- no off-surface behavior
- screening gate not passed
- provenance / conflict handling needs more evidence
- not enough data to classify as incapable
```

Not re-screened this round, and that is a deliberate omission rather than an
oversight: the round's purpose was to fix the surface before comparing models,
and Space Bunny's 2.6.2 failure was partly *caused* by the surface. Re-running it
now would be a measurement of the fix on the model that exposed it, which is worth
doing — but it is a new comparison, not a variance series, and it belongs after
this one is sealed.

---

## 7. Failures classified

| | count | what |
| --- | --- | --- |
| **A** | **1, systemic, fixed** | the ambiguity block's fabricated cause, wrong in 107/107 groups |
| **B** | 13 checks across 15 test-attempts | target model errors — concept recall, one uncited conflict side, negative states collapsed, the wrong-namespace citation |
| **C** | 2, fixed in 2.6.2 | the keyword and currency checks that failed a correct answer |
| **D** | 1, fixed in 2.6.2 | T8 grading one arbitrary conflict out of two dispute mechanisms |
| **E** | 5 | upstream `502`/`503` provider errors, plus one aborted attempt |
| **D candidate** | 1, not fixed | T6's question renders a derived reference as prose with nothing to signal that |

No new A beyond the one that was fixed. The derived-value limitation is fixed
too, but it was recorded as a limitation and not a defect, and this round's
evidence says the model is not reaching it — so it is a capability finding, not a
production finding.

---

## 8. Reproducing any of this

```
python openrouter_screening.py reaudit  --model <m> --reaudit-phase full
python openrouter_screening.py variance --model <m> --reaudit-phase full
```

`reaudit` re-grades stored answers with the current evaluator and sends nothing.
The 2.6.2 runs re-audit to **exactly** their 2.6.2 verdicts under the corrected
surface and grader — the production fix changed the explanation models read, not
the grading of answers already given.

`variance` reads a run series and sends nothing. It prints the per-test matrix,
the per-capability rollup, the grounding count, and the attempts it excluded and
why.

Each run directory holds `audit/`, `runs/`, `reports/`, `run_metadata.json`,
`usage_ledger.json` and `budget.json`. No credential is in any of them; a
repository-wide scan returns zero matches.

**request accounting:** 64 + 58 + 56 = 178 across the three runs, plus 3 for the
aborted attempt. The account reports `is_free_tier: false` with no daily limit
attached and OpenRouter's own rate limiting was never reached; the refusals here
were all upstream, at the provider behind the model. The documented ~50/day free
allowance was again not enforced against this key, and that is recorded rather
than assumed.
