# 2.22 — Dimension collisions at the grain the decision needs

2.21 refused to decide `BANK → gross_profit` because the deciding evidence could
not be trusted: the collision count was filed per issuer, so a question about a
metric had no number to answer it with. This persists the collision at the grain
it is asked at, re-runs the eight banks, and re-characterises.

It also caught the implementation making a claim the data cannot support.

---

## A. Two corrections to 2.21, one of them a logic error

**The general rule is refuted, not undecided.** 2.21 said "for these filers
undecided", which was the wrong frame. One valid counterexample is enough to
refute a universal rule, and NRIM is valid. So:

```
BANK -> gross_profit NOT_APPLICABLE        REFUTED
BANK -> ?  (the replacement)               UNDECIDED
```

Stated separately on purpose. The failure this prevents is specific: "the sample
is too small, so we keep NOT_APPLICABLE" would keep a rule alive that has already
been contradicted.

**BBAR is not subtracted from the counterexample count — it is a third state.**
2.21 framed it as a correction to a count. It is not a count at all:

```
NRIM    valid positive evidence against a BANK-wide NOT_APPLICABLE rule
BBAR    source concept present -> dimension ambiguity -> semantic meaning unresolved
others  no mapped evidence -> SOURCE_SILENT
```

That is the project's existing ambiguity contract, applied rather than a
correction to arithmetic.

---

## B. The table

`archive/migrations/0014_dimension_collisions.sql`. One row per collision, with
the metric, the concept, the filing and the period attached:

```
run_id, asset_id, metric_id, concept_id
accession, period_start, period_end, unit
distinct_values, collision_kind, detected_at
```

Keyed on the collision rather than the run, so a rerun over the same window
replaces its rows and a rerun over a wider window adds them — which is the honest
direction, because more filings means more chances to reach a member the first
window never saw.

Written in the same transaction as the run it belongs to, for the same reason the
scope rows are: a collision is a statement about a metric, and filing it per issuer
put the number somewhere nobody asking the question looks. That was the defect —
404 collisions across eight banks, and no way to say whether any belonged to gross
profit.

### What eight banks now report

```
metric                                filers  keys  extra values per key
operating_cash_flow                       6     67    74
cash                                      5     37    51
eps_diluted                                5     29    34
equity                                     4     57    73
net_income                                 4     56    62
income_tax                                 4     43    48
interest_expense                           4     28    33
assets                                     4     17    18
capex                                      3     20    20
weighted_average_diluted_shares            2     13    13
gross_profit                               2     11    15
sga                                        1     12    17
revenue                                    1      1     1
shares_outstanding                         1      1     1
```

Which is itself a finding: **the collisions are not concentrated in the disputed
metric.** `gross_profit` has 11 affected keys. `operating_cash_flow` has 67, and
`equity` has more extra values per key than `gross_profit`. A reader who assumed
the ambiguity was specific to the metric under argument would be looking in the
wrong place — it is a property of aggregated sources generally, not of this rule.

---

## C. The claim the data would not support

The first implementation classified a collision as `RESTATED_SAME_PERIOD` when
earlier and later filings disagreed and no single filing reported two values for
one period. On the eight banks it reported **392 of 392** as restatements —
including BBAR's GrossProfit, where 2019 moves 88.8bn → 120.9bn → 182.5bn across
three 20-F filings.

**A restatement does not move a number by 36% and then by 51%.**

And the classification could not be rescued: the member axis was dropped by the
aggregated endpoint *before ingestion saw anything*, so "this filer revised the
number" and "these are two members reported in two filings" are the same
observation. No test on this data can separate them.

So the vocabulary now says what was seen and not what it means:

```
SAME_PERIOD_DIFFERENT_VALUE   one filing reported two values for one period.
                              A member was hidden. Provable from this source.
LATER_FILING_DIFFERS          an earlier and a later filing reported different
                              values for one period, each reporting one value.
                              Observable. Whether it is a revision or a hidden
                              member is NOT determinable here.
```

`RESTATED_SAME_PERIOD` was removed rather than left available, and `UNIT_MISMATCH`
went with it: the collision key includes the unit, so a unit mismatch never
collides and nothing could produce it. **A closed vocabulary that names a state no
code can emit is worse than a short one — it advertises a distinction the archive
cannot make.**

`SAME_PERIOD_DIFFERENT_VALUE` did not occur on these eight banks. That is a real
zero, not an untested path: it is covered by a test that feeds one filing two
values for one period.

### The consequence for the decision

BBAR is now correctly labelled **undeterminable** rather than *artefact*, which is
the honest answer and also the weaker one:

```
NRIM   1 key,  2025 Q1,  46,906,000 -> 45,746,000   a 2% revision
BBAR   9 keys, values moving 36% then 51%            not a revision; not provable either way
```

NRIM stands as the valid counterexample and the general rule stays refuted.
BBAR contributes no evidence in either direction — which is the finding, and it is
what a consumer needs to be told rather than left to guess.

---

## D. What this does and does not buy

**Buys:** the three-way split, per metric, per filer, with the concept and the
period attached. A consumer asking "is BBAR's gross profit usable evidence?" now
has an answer that is not "there are 18 observations".

**Does not buy:** the ability to decide the `gross_profit` rule. The obstacle was
never the count; it is that the aggregated endpoint cannot distinguish a revision
from a hidden member, and 11 keys of ambiguity across 2 filers is not the input a
universal rule should be decided on.

**Also does not buy, and this is worth saying plainly:** `LATER_FILING_DIFFERS`
does not make the series unusable. A restated series is a series with a history of
revisions, which is ordinary, and the conflict marker still fires correctly for
NRIM and BBAR. What it prevents is treating either as 18 comparable points.

---

## E. Two bugs I wrote and the grain caught

Both were in the first implementation, and both were invisible at per-issuer grain:

**`distinct_values` was off by one.** Reported before the new value was added, so
a key with two values recorded 1.

**The restatement test compared the wrong container.** It tested whether the set of
accessions was a subset of a dict keyed by *values*, which is never true — so
`RESTATED_SAME_PERIOD` could not execute even in principle. All 392 collisions
came out as the other kind, and nothing complained because there was only one kind
in play.

The second is the more interesting one. A label that cannot fire looks exactly like
a label that correctly never fires, and the difference only becomes visible when a
second kind exists and neither appears. **A vocabulary member with no test is not a
closed vocabulary — it is an untested branch in a comment.**

---

## F. State

| | |
| --- | --- |
| full suite | **639 passed**, 74 skipped, 713 run (+6) |
| production change | `sec_ingest` (persist per event), migration `0014` |
| regressions | six-issuer, twelve-issuer, eight-bank runs re-run |
| equivalence | **11,174 / 11,174 matched, 0 divergent, 0 one-sided** — unchanged |
| sealed snapshot | untouched |

Six new tests cover both kinds, the metric-and-concept naming, the running count
for a third value, and the two removed vocabulary members being rejected by the
database rather than merely absent from the code. The two vocabulary tests build
real parent rows first, because with fakes the foreign key can fire instead of the
CHECK and the test would pass for the wrong reason.

---

## G. What is now decidable, and what is not

**Decided by this round:**

```
BANK -> gross_profit NOT_APPLICABLE     REFUTED
```

by a valid counterexample, which one filer of eight is enough to establish.

**Not decided, and the user's framing is the one to keep:**

```
BANK -> gross_profit ?                  UNDECIDED
```

and the observation that makes it simpler than 2.21 thought — **this may not need a
`CONDITIONAL` state at all.** `SOURCE_SILENT` already says "this filer, in this
source evidence, does not report this metric". `APPLICABLE` / `NOT_APPLICABLE`
answers a different question: do we have sufficient semantic reason to refuse
asking. If there is no such reason, the correct move is not to invent a
conditional but **not to write the `NOT_APPLICABLE` rule** — which keeps the three
layers clean and leaves `semantic_conflict` firing only where layer 1 and layer 2
genuinely disagree.

**And a note that was wrong the first time.** This section said removing the rule
would leave six banks with "a retrieval backlog growing every night". That
conflates two things the system is careful to keep apart. Six banks reporting no
gross profit would read:

```
metric not ruled inapplicable  +  source asked  +  nothing returned
    = SOURCE_SILENT
```

which is **handled, source silent** — a coverage *state*, not a backlog. There is
real recurring cost, because the filing universe moves and the question has to be
asked again whenever the source has something new, but that is an ingestion
scheduling question and not a coverage one. `NOT_YET_COLLECTED` is the only status
that means work to do, and these would not be it.

Which matters more than the wording: the whole system exists to stop "no
observation" being read as "not handled", and the sentence above did exactly that.
A reader who believed it would have thought six filers were carrying undone work,
when in fact they had all been asked and none had anything to say.

**Next:** the `LATER_FILING_DIFFERS` rate is now measurable per metric, so before
the rule is decided, one question deserves an answer — **is 392 collisions across
eight banks normal for an aggregated source, or is this a filer effect?** If it is
normal, then no metric built on `companyfacts` should be read as a flat series
without that caveat attached, which is a much larger statement than any one
applicability rule.