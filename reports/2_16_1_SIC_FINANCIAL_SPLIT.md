# 2.16.1 — Splitting SIC 60–67, only as far as the rules need

2.16 left one decision: whether to split SIC 60–67 into bank / insurance /
finance, or accept one financial bucket. Taken, and taken narrowly — four models
were in play and the question is *classification resolution sufficient to explain
missing evidence*, not taxonomy coverage.

```
SIC major group -> business model
   10-14   MINING
   20-39   MANUFACTURING
   70-89   SERVICES
   60-60   BANK               new
   61-62   FINANCE_SERVICES   unchanged
   63-64   INSURANCE          new
```

`REIT`, `BANK`→`INSURANCE` finer splits, and any rule for `OPERATING` /
`TECHNOLOGY` are all deliberately absent. `BUSINESS_MODEL_BASES` already declares
those reachable only through `DECLARED_BY_ISSUER`, `DERIVED_FROM_REPORTED_CONCEPTS`
or `MANUAL_CLASSIFICATION`, and the SEC ingestion path performs none of those.
They stay unreachable rather than being given a SIC code they do not own: a rule
added to raise taxonomy coverage cannot answer a question about missing evidence.

---

## A. What the split actually does to the population

Re-derived read-only from the 75-issuer archive. **The archive was not modified**,
so these are what a fresh run would classify, not what the archive says.

```
recorded under the old map:   MANUFACTURING 37   FINANCE_SERVICES 24   SERVICES 3
under the new map:            MANUFACTURING 37   BANK 8   FINANCE_SERVICES 8
                              SERVICES 3         unclassified 8
```

16 issuers change. 8 gain a more specific label and **8 lose a classification
entirely**:

```
SIC 60 -> BANK                FHB  CCFN  BBAR  PFBX  NRIM  CZWI  AUBN  FCNCP
                              (6022 national commercial banks, 6029/6035 savings)
SIC 61 -> FINANCE_SERVICES    unchanged, 8 issuers
SIC 65 -> unclassified        AWCA  EFC  MYCB  BPYPN  CRESY  HPP  VAC  BNH
                              (6500 real estate, 6512 REITs, 6531 real estate)
```

The eight that lose a classification are real estate investment trusts. They were
`FINANCE_SERVICES`, which was wrong for them, and they are now `None`, which is
the safe direction: an unclassified filer is asked about a metric that turns out
not to exist and is told so by the evidence layer, rather than silently having a
metric removed from its coverage. The cost is that they can no longer express
that gross profit does not apply to them — and mapping SIC 65 to `REIT` would
restore that at the same cost as `INSURANCE`: a label, and no ruling, because no
seeded rule names `REIT` either. **Left undecided rather than taken quietly.**

SIC 67 also left the range, so a finance company now makes no ruling where it
previously made a financial one. Same safe direction, same kind of loss.

---

## B. `BANK` is populated; `INSURANCE` and `MINING` are not

This is the part that constrains the next fetch:

```
SIC 63-64 (INSURANCE) filers in the 75-issuer population: none
SIC 10-14 (MINING)   filers in the 75-issuer population: none
```

**The population contains no insurance filer and no mining filer at all.** So:

- **`BANK` is reachable and populated** — 8 filers, and it is the one label whose
  classification changes an applicability ruling. `gross_profit` and
  `operating_income` are refused for `BANK`, and `BANK` was unreachable from any
  SIC code before this split, so **those two rules had never fired for the reason
  they were written**. They now can.
- **`INSURANCE` is reachable in principle and empty in practice.** The split adds
  a label and no ruling, because **no seeded applicability rule names
  `INSURANCE`**:

  ```
  refused for BANK:        gross_profit, operating_income
  refused for INSURANCE:   (nothing)
  refused for MINING:      r_and_d
  refused for REITs:       (nothing)
  ```

  Claiming the split "tests insurance applicability" would be a null result
  dressed as a success. Writing those rules is a semantic decision, not a mapping
  fix, and it is not taken here.
- **`r_and_d`'s MINING rule still has never fired**, and still cannot, from this
  population.

The 8 BANK filers are named in section A, so the selection for the next fetch is
determinable without any new classification work. Insurance and mining filers are
**not** in the archive and have to be sourced deliberately — which is a fact about
the candidate pool, not about the pipeline.

---

## C. The obvious validation is inconclusive, and saying otherwise would repeat the mistake

The first thing to try was: do the 8 newly-BANK filers actually hold zero
`gross_profit` and `operating_income`, as the ruling claims? They do — 0 and 0,
across all 8.

**That is not a validation.** The 75-issuer archive holds eight metrics:

```
cash  net_income  eps_diluted  revenue  assets  capex  debt  shares_outstanding
```

`gross_profit`, `operating_income` and `r_and_d` are **not in it at all**. So their
absence is scope, not evidence of inapplicability, and the check cannot
distinguish "the rule correctly refused this" from "nobody was ever asked".

This is the same lesson as 2.13 §3 and 2.16's `observations` split, arriving a
third time and in a new place: **an absent metric is not a negative result.** The
ruling-vs-evidence check only becomes real once the full scope has been collected
at population scale, which is exactly what the next round is for.

So the correct status of the split is: **implemented, measured against the
population, and confirmed to contradict nothing in the archive — with the archive
unable to confirm it yet.**

---

## D. A schema observation

The numeric SIC is **not stored**. `issuer_business_model` holds
`(asset_id, business_model, basis, source, recorded_at)`, and the code appears only
inside the provenance string — `"SIC 6199 Finance Services"`.

So re-classifying an existing archive means parsing a human-readable provenance
string. That was necessary to measure section A, and it is the reason the
measurement could be done offline at all rather than requiring a re-fetch of
submissions for 75 issuers. A filer's SIC is a property of the filer and not of
any metric, so it belongs in its own column; recorded here rather than changed,
because a schema migration on a gitignored archive is not this round's work.

---

## E. State

| | |
| --- | --- |
| full suite | **620 passed**, 74 skipped, 694 run (+8) |
| production change | `sec_ingest.SIC_GROUPS` only |
| tests | 8 added to `tests/test_cross_framework_2_7.py`, including a gap marker |
| regressions | six-issuer and twelve-issuer modes re-run, identical results |
| archives | none modified; measured read-only |
| network | none |

The gap marker is worth naming: `test_insurance_is_reachable_and_has_no_rule`
asserts that no rule refuses `INSURANCE`. It is written so that it **fails** if
someone adds an insurance rule — which they should, and should then update this
test and SPEC §0.20 with it. That is the mechanism that stops a future round from
discovering the gap as a surprise.
