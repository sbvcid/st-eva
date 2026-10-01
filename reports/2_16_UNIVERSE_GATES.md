# 2.16 — The 75-issuer archive, gated for the first time

2.15 left two instrumentation gaps, both of which blocked the next question:

- **the 75-issuer population archive had never been gated** — `ingest_universe.py`
  writes no collection chains, so the largest archive in the repository could not
  be put through the same eight gates as every other one
- **the gate tool crashed instead of skipping** —
  `score_collection_gates.py:76` did `.fetchone()[0]` with no guard, so a chain
  naming a ticker the archive does not hold raised `TypeError` and killed the run

Both fixed, and the gates have now run over 1,500 metric-issuers. What they
produced is a number that looks alarming and is not a quality measure — and
knowing that is the finding.

```
75 issuers  1,500 metric-issuers  0 skipped
   definition     1500/1500
   mapping        1500/1500
   adoption       1500/1500
   provenance     1500/1500
   missingness    1500/1500
   discoverable   1500/1500
   applicability  1280/1500
   observations    491/1500
```

---

## A. The two fixes

### Chains are recoverable; run logs are not

`derive_collection_chains.py` derives one chain per issuer from an archive that
has none, because `coverage_semantics.collection_chain` is a pure function of the
archive and the registry — the ledger, the adoption rows, the declines, the
applicability ruling are all already stored.

What it does **not** reconstruct is transport accounting: request counts, concept
fetches, whether a run returned early for want of new filings. Those are
properties of a run, not of the stored evidence, and the chains this writes say
so in their own output rather than reporting zeros that look measured.

The archive is opened **read-only** (`file:...?mode=ro`). `Ingestor.collection_chain`
calls `record_asset` on its way to the ledger, which would have created an asset
row for any unknown ticker — a measurement that can alter its subject is not a
measurement, so the only reliable way to say otherwise is to make it impossible.

```
75 chains, 1,500 metric-issuers, 491 collected, 488 backlog items
```

### A broken input and an empty input now look different

The crash is now a skip with a reason, reported in the stdout summary and in the
JSON. And the universe line is counted rather than typed in — it read
`6 x 20 = 120 metric-issuers` with both numbers hardcoded, which is a
description of one run rather than a measurement of whatever ran.

The JSON shape changed with it, from `{ticker: entry}` to
`{issuers, measured, skipped}`, because a run's universe and its skips are part of
its result. `fullscope_bulk.py` reads both shapes so the harness can still be
pointed at an artefact from the previous format.

---

## B. `observations` 491/1500 is a scope measure wearing a quality name

The gate asserts `observations > 0`. That is the right assertion and an unreadable
one, and over an 8-metric archive scored against a 20-metric universe it produces
a 33% pass rate that is almost entirely scope and decisions.

So the tool now splits it by the ledger's own status, reading a signal that
already exists rather than adding a new one:

| ledger status | metric-issuers | with observations | without |
| --- | --- | --- | --- |
| `COLLECTED` | 491 | 491 | 0 |
| `DELIBERATELY_DECLINED` | 384 | 0 | 384 |
| `NOT_YET_COLLECTED` | 488 | 0 | 488 |
| `MAPPED_NO_CURRENT_OBSERVATION` | 55 | 0 | 55 |
| `NOT_APPLICABLE` | 48 | 0 | 48 |
| `SOURCE_SILENT` | 34 | 0 | **34** |

**Of 1,009 cells holding no observations, 34 are `SOURCE_SILENT` — a filer that
was asked and reported nothing, which is what this gate exists to catch.** The
other 975 are: 488 never asked (the 2.13 scope rule working exactly as designed),
384 a concept declined on the record, 55 a declared composition whose facts are
held under the parent, and 48 a filer the metric was ruled inapplicable to. Every
one of those is a decision or a scope, and a gate that scores them identically to
a filer withholding data produces a number nobody can act on.

**The gate is not changed.** Whether `observations` should be satisfied by a
recorded answer — the way `adoption` is, which 2.14 already fixed for
`NOT_APPLICABLE` — is a semantic decision about what the gate means, and it is
recorded rather than taken. What is added is the split, so the number can be read.

**This is 2.13 §3's point, one round later.** That section said a coverage report
must distinguish "never requested" from "not reported". The *ledger* does; the
*gate* did not read that distinction.

---

## C. `applicability` 1280/1500, and it is 11 issuers

220 failures, and 11 issuers × 20 metrics = 220 exactly:

```
AILLP  CDZI  CIG-C  EONGY  FAST  FIP  GRWG  NMPWP  TAC  TSCO  UEPEO
```

Eleven of seventy-five have no recorded business model, so no applicability
ruling was derived and the gate correctly reports a blank. That is 15% of the
population where nothing is known about whether any metric applies — not a
collection failure, but a real hole in the corpus, and it is the first number this
project has produced about the 75-issuer archive's classification coverage
because nothing had ever run over it.

---

## D. The type axis exists in the population — it was only the payload that was degenerate

2.15 reported that all twelve issuers on disk are `MANUFACTURING`. That was true
of the twelve and the instrument reported it rather than hiding it, but the
population archive is not degenerate, and the correction matters for what the
next step costs:

```
MANUFACTURING      37
FINANCE_SERVICES   24
SERVICES            3
unclassified       11
```

Three of nine vocabulary members have filers. **The selection for the next fetch
is therefore fully determined by data already in the repository** — no new
classification work is needed, only `companyfacts` documents for a chosen subset.

### But MINING is reachable and five members are not

```
SIC major group -> business model
   10-14   MINING
   20-39   MANUFACTURING
   60-67   FINANCE_SERVICES
   70-89   SERVICES
```

`MINING` has a SIC group and **no issuer in the 75 was classified as it** — the
strided sample contained no SIC 10–14 filer. So including MINING is a matter of
selection, exactly as expected.

The constraint worth stating now, before a fetch is planned around it: the
vocabulary has **nine** members, and **five cannot be reached by SIC at all** —
`BANK`, `INSURANCE`, `OPERATING`, `REIT`, `TECHNOLOGY`. `BUSINESS_MODEL_BASES`
declares them as reachable through `DECLARED_BY_ISSUER`,
`DERIVED_FROM_REPORTED_CONCEPTS` or `MANUAL_CLASSIFICATION`, and the SEC ingestion
path performs none of those. SIC 60–67 is a single `FINANCE_SERVICES` bucket, so a
bank and an insurer are the same class to this pipeline.

So the type axis cannot be fully exercised by widening the population alone. It
would need either a finer SIC mapping — 60/61/62/63/64 are banks, insurers,
finance companies and holding companies respectively, and the SEC publishes the
two-digit code — or an explicit decision to keep one financial bucket. That is a
decision, and it is cheaper to make before the fetch than after.

---

## E. State

| | |
| --- | --- |
| full suite | **612 passed**, 74 skipped, 686 run — unchanged |
| production files changed | none |
| instrumentation changed | `score_collection_gates.py`, `fullscope_bulk.py` |
| new | `derive_collection_chains.py` |
| regenerated | 75 chains for the 75-issuer archive, from a read-only connection |
| first time gated | `snapshot-universe.sqlite`, 1,500 metric-issuers, 0 skipped |
| regressions | six-issuer and twelve-issuer modes both re-run, identical results |
| network | none |

The 75-issuer archive itself was not modified: the connection that produced its
chains is opened read-only, and `git status` shows no archive among the changes.

---

## F. The next step

Everything before the fetch is now done. The remaining sequence is:

```
select across business model, from the 64 classified issuers
    FINANCE_SERVICES   24 available
    MANUFACTURING      37 available
    SERVICES            3 available
    MINING              0 available  -> requires a SIC 10-14 filer in the candidate pool
fetch companyfacts for the selection
full 20-metric bulk bootstrap
reconcile, gate, and run the metric-by-issuer matrix
```

The one decision that should be made first, because it changes what the fetch
targets: **whether to split SIC 60–67 into bank / insurance / finance, or accept
one financial bucket.** Widening the population exercises four of nine vocabulary
members; splitting the financial group exercises two more and makes the
applicability rules testable against the cases 2.7 introduced them for — a bank
that reports no capex and an insurer that reports no inventory are the two rulings
the rules exist to make.
