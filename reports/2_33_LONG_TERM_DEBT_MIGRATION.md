# 2.33 — `debt` → `long_term_debt`: a semantic migration, not a rename

**Product decision, taken in 2.32 and implemented here.** Candidate A. Not a
hypothesis, and not reopened.

Suite **737 run, 663 passed, 74 skipped**.

---

## A. The decision

Core `debt` is renamed and redefined to **`long_term_debt`**, whose target is:

> Long-term debt at a balance-sheet date, comprising the current and non-current
> portions of long-term debt — `long_term_debt_current` and
> `long_term_debt_noncurrent`, two views of one quantity.

**Explicitly excluded** unless a source concept says of itself that it is part of
long-term debt, and never on name similarity: short-term borrowings · total
liabilities · lease-inclusive debt obligations · total debt in the general sense.

**`total_debt` is not created.** Not in the Core metric set, no coverage
obligation, no mappings, no empty registry row, no `ShortTermBorrowings` mapping
to stand in for it. It is **unestablished, not refuted** — it has no non-circular
definition, no source representation, and no cross-filer evidence.

---

## B. Why it could not be a rename

**The sealed 2.2.3 archive holds 180 observations recorded under `metric = 'debt'`,**
and `observations.metric` is part of the contract id. Rewriting those rows would
change `observation_id` and manufacture new historical Evidence out of a naming
decision.

So the rename is recorded *alongside* the old name:

```
observation.metric  = 'debt'          unchanged, forever
metric_supersession                   debt -> long_term_debt, with its reason
metric_registry                       'debt' DEPRECATED, 'long_term_debt' ACTIVE
```

What changes is the question *what does this metric denote*, and it is answered by
following the chain — `CoreRegistry.resolve_metric` — rather than by editing rows
that are supposed to be immutable. `metric_supersession` is append-only, enforced
by the same no-update / no-delete triggers every other immutable table here carries,
and it fails loudly on a cycle.

`DEPRECATED` is used rather than a new `SUPERSEDED` status: it is the existing
vocabulary member meaning "retained, no longer the active definition", and adding a
second member with the same meaning would be vocabulary inflation. Every consumer
reading `status = 'ACTIVE'` — the coverage universe, the evidence surface, the
cross-framework verifier — stops treating `debt` as Core while its observations
keep resolving.

### Two things that would have silently broken, and did not

**Historical observations stranded.** The four concepts are now declared against
`long_term_debt`, so a legacy `debt` observation resolves through supersession to
reach them. Without that it would have found no mappings and read as
`UNDETERMINED` — a coverage regression caused entirely by a rename.

**Historical observations dropped from the ledger.** The coverage universe is the
active metrics, so a pre-rename archive holding only `debt` rows would have lost
them from the surface. The ledger now reports the active universe **plus every
metric the archive actually holds**.

---

## C. The two contracts, and the parity that was never tested

`debt` existed in **two** contracts — the Core registry and the cross-source
contract in `data_contract.py` — sharing a metric id with nothing constraining them
to mean the same thing. That is how the drift happened.

Both now state the same target, and `tests/test_metric_supersession.py` asserts it
rather than assuming it: metric id · unit family · period type · the exclusions,
and that neither contract claims total debt any more.

`data_contract.METRIC_DEBT` is **retained as the legacy alias** with a documented
`canonical_metric_id()`, because the sealed archive's rows must keep resolving.
`cross_validation`, `sec_provider` and `fundamental_provider` moved their
comparability specs and vendor-field maps to the decided id; the one branch that
inspects a *stored* metric canonicalises first, so the sealed archive's 180 rows
are still recognised.

---

## D. The ten re-verification items

```
 1  [PASS] Core metric count unchanged at 20       one leaves, one arrives
 2  [PASS] sealed observation rows unchanged       1,925
 3  [PASS] observation identities unchanged        1,925 distinct of 1,925
 4  [PASS] observation_id unmoved                 obsarch_226b7e98515b17f98e4bbb00
 5  [PASS] 180 legacy `debt` rows present, none rewritten
    [PASS] sealed digest unchanged                ce603a5588cef067
 6  [PASS] LongTermDebtCurrent + Noncurrent == LongTermDebt still reproduces
                                                  451 periods across 25 filers
 7  [PASS] us-gaap and ifrs-full both reach long_term_debt
 8  [PASS] total_debt absent from the active Core scope
 9  [PASS] parity test present and passing
10  [PASS] supersession table append-only, enforced by trigger
```

**Item 6 reproduces from the source documents, not from an archive** — because
`us-gaap:LongTermDebt` is unmapped, which is the 2.29 finding and precisely why the
rename did not add it. The identity that justified the decision lives where 2.31
found it.

---

## E. What the migration did not do

- **No observation was updated, deleted or rewritten.** `metric = 'debt'` stands.
- **No `ShortTermBorrowings` mapping.** It is in 11 of 75 filers and participates
  in no debt arithmetic; adding it would have quietly re-imported the quantity the
  rename excluded.
- **No lease-inclusive concept.**
- **No `total_debt`**, in any form.
- **No new applicability rule.**
- **No fetch.**

And one consequence worth stating rather than discovering later: the vendor
projection now reads Yahoo's `financialData.totalDebt` into `long_term_debt`. That
field is a vendor's *total* debt, which the decided definition excludes. The
projection is unchanged and it is **wrong for the new target** — a genuine mismatch
created by a correct decision, and a separate proposition.

---

## F. State

| | |
| --- | --- |
| full suite | **737 run, 663 passed, 74 skipped** (+23) |
| production changes | `registry_seed`, `core_registry`, `coverage_semantics`, `data_contract`, `cross_validation`, `sec_provider`, `fundamental_provider`, migration `0016` |
| tests | `tests/test_metric_supersession.py`, 23 cases |
| archives modified | **none** |
| fetched | **nothing** |
| commits | 2.27 at `7cb5e27`; 2.28 onward uncommitted |

## G. What 2.34 would be

Two open items, neither of which is a mapping change:

1. **`total_debt`**, when it has a non-circular definition and cross-filer
   evidence. Unestablished, not refuted.
2. **The vendor `totalDebt` projection**, which now feeds a metric it does not
   match. Either the projection is retired, or the definition admits what vendors
   actually report — and the second is a reversal of this decision, so it needs the
   same kind of evidence that produced it.