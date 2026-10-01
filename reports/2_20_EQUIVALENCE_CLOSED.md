# 2.20 — The bulk/API equivalence chain, closed

2.18 left an argument rather than a measurement: **5,447 semantic-equivalent, 88
known-stale-reference differences, 0 unexplained.** The 88 were fully explained —
accessions outside the submissions window, where the older API-built archive still
recorded the filed date as a fabricated midnight labelled `ACCEPTANCE_DATETIME`,
the defect 2.14 fixed — but "fully explained" is not the same as "measured".

This rebuilds the reference under the corrected contract and reconciles again.

```
11,174 shared source_fact_id
11,174 matched
     0 divergent
     0 only-in-bulk
     0 only-in-reference
     0 unexplained

all eight gates identical on both routes
sealed snapshot ce603a5588cef067, unchanged
```

**The chain is closed.**

---

## A. What closed, and how

Eight `companyfacts` + `submissions` documents read from disk, against eight SEC
API walks of the same filers, same twenty metrics, same forms policy read from
one archive so the comparison could not be a form-policy artefact.

| | bulk (2 files per filer) | API (per-concept requests) |
| --- | --- | --- |
| network requests | **0** | **392** (49 per filer) |
| elapsed | 34.9 s | — |
| observations | 11,174 | 11,174 |
| distinct identities | 11,174 | 11,174 |
| filings held | 858 | 858 |
| archive | 37.7 MB | — |

So the bulk route reads the same SEC source, through two files per filer instead
of 49 requests, and lands on an archive that is **identical on every one of 26
semantic fields for every row** — value, unit, currency, period, as-of,
availability and its basis, taxonomy, concept, accession, form, fiscal period,
contract id, identity, source concept ref, basis block, definition, methodology,
status, instant.

### Cross-checked without the project's code

The reconciliation tool reported the match; then it was recomputed in plain SQL
against both files, with no project module involved, because a test that can only
be satisfied by the code under test is not a second opinion:

```
INDEPENDENT SQL CROSS-CHECK
  bulk rows                       11,174
  api rows                        11,174
  shared source_fact_id           11,174
  differing on any of 26 fields        0
  only in bulk / only in api            0 / 0
```

Same answer from two unrelated implementations of the same comparison.

### Gates identical, both routes

```
                     bulk     API
definition        160/160  160/160
mapping           160/160  160/160
applicability     160/160  160/160
adoption          160/160  160/160
observations       95/160   95/160
provenance        160/160  160/160
missingness       160/160  160/160
discoverable      160/160  160/160
```

Including the nine failing `observations` cells, which are the same nine on both
sides — `debt` at 8 of 8, the two debt components, `r_and_d`, `sga`, `capex`,
`shares_outstanding`, `weighted_average_diluted_shares`. Those are real coverage
findings about banks, not route differences.

### The sealed snapshot is untouched

`ce603a5588cef067` before and after, `UNCHANGED: True`. Every 2.1–2.6 result is
still reading the same ground truth.

---

## B. The conflict survives both routes

```
                bulk            API
gross_profit    BBAR:18 NRIM:22    BBAR:18 NRIM:22
business models recorded    8/8        8/8
```

Both archives hold the forty observations and both refuse to count them, and both
name the conflict. That is the 2.19 contract working identically on both delivery
paths — which is the point of having measured equivalence. A contract that only
behaved on one route would not be a contract.

---

## C. What the equivalence does and does not license

**It licenses:** treating the bulk route as a *substitute*, not a variant. Reading
from files rather than from endpoints produces the same evidence, the same
identity, the same point-in-time boundary and the same coverage surface. The 2.13
premise — that a bootstrap and an incremental run can be reconciled because they
produce the same thing — is now demonstrated at the full Core scope rather than
asserted, and the archive can be rebuilt from a nightly bulk download without any
semantic consequence.

**It does not license:** assuming the next filer behaves the same way. This is
eight SIC 60 banks, 47 concept fetches each, no mega-cap, and no filer outside one
industry group. The cost constant that matters is still a floor, and 2.11's
mega-cap caveat is untouched by anything in this round.

**And it makes the operational number concrete at full scope:** 392 requests for
eight filers, or 49 per filer, against **zero** for the same eight from files. At
ten thousand filers the API route's cost extrapolates to roughly half a million
requests; the bulk route's does not move.

---

## D. State

| | |
| --- | --- |
| full suite | **631 passed**, 74 skipped, 705 run — unchanged |
| production change | none |
| script change | `build_crossframework_snapshot.py` gained `--issuer` / `--reference` |
| network | 392 requests, one API walk per filer |
| archives | `snapshot-banks-api.sqlite`, `snapshot-banks2.sqlite`, neither modified in place |
| committed artefacts | `harness/banks-api-220.json`, `harness/banks2-220.json` |

The reference's issuer set and form policy are read from an archive rather than
hand-written, because 2.13's empty-map incident was a run that reported no errors
and collected nothing.

---

## E. What remains, in the order it should be taken

**1. `BANK → gross_profit`.** The conflict is named identically on both routes,
with the concept attached, and the decision is a semantic one rather than an
ingestion one:

```
BBAR    ifrs-full:GrossProfit   18 rows   20-F, ARS units, same period carrying
                                            different values across filing years
NRIM    us-gaap:GrossProfit     22 rows   10-K and 10-Q, clean quarterly series
```

Narrow the rule, keep it, or accept that two filers' reported gross profit is
collected and then not counted. What is *not* available as an option is deleting
the evidence, for the reason 2.19 recorded.

**2. `r_and_d` and `sga` for banks.** `SOURCE_SILENT` at 8 of 8 and 7 of 8 with
unanimous evidence — the strongest applicability candidate in the project, and the
mirror image of `INSURANCE`, where there is no filer to say anything.

**3. A cross-business-model population.** The bank sample is homogeneous by
construction. `INSURANCE` (SIC 63–64) and `MINING` (SIC 10–14) still have no
filer anywhere, so the type axis cannot be exercised, and `r_and_d`'s MINING
exclusion has never fired.

**4. Whether a semantic conflict should score as a gate failure.** Open, reported
rather than decided, and now measurable on any archive that holds one.