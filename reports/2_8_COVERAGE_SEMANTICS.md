# 2.8 — Coverage Semantics

ST-EVA can now answer *"coverage is low — where exactly?"* rather than only
*"how much?"*

2.7 ended with a number that was true and almost useless: **3.0% of TSM's
concepts**. It was measured against a denominator that is not a target, and it
could not be decomposed — so "3.0%" read as *ST-EVA only manages 3%* when the
truth was that nine concepts had been deliberately declined with reasons, ten
were declared, and the rest were never asked for. Three completely different
situations, one number, no way to tell them apart.

That is the whole of this phase.

---

## 1. The universe, and the refusal to change it

```
SCOPED_CORE_UNIVERSE
    every ACTIVE semantic metric
  × the source concepts declared to express it
```

**Coverage is measured against ST-EVA's own Core Metric Universe, and not
against a filer's full concept count.** That is a refusal, not an oversight, and
the reasoning is worth stating because this project has now walked into the
opposite mistake twice:

```
XBRL reports 334 concepts for a filer
  -> collecting them all is not the goal and never was
  -> a figure against that number says "3.0%", which invites someone to raise it
  -> the cheapest way to raise it is to collect concepts nobody asked for
  -> which is the exact opposite of providing necessary, trustworthy data
```

The source figure is still **reported** — 505 concepts for AAPL, 336 for TSM,
151 for NU — because losing it would lose a real number. It is just not the
denominator, and `universe_note` in every ledger says so in the payload rather
than in a comment.

The filer's full concept list is also **not derivable from the archive**, and
2.7 established why: ingestion only fetches concepts the registry maps, so the
archive is blind to a concept it never asked for. It is therefore an *input*
(`source_inventory`), and where it is absent the ledger says
`source_inventory_known: false` rather than concluding the filer reports nothing.

---

## 2. Eight statuses, all derived from records

| status | derived from | call for |
| --- | --- | --- |
| `COLLECTED` | observations held for this issuer and metric | nothing |
| `MAPPED_NO_CURRENT_OBSERVATION` | the issuer has an adoption record for a declared concept, and no rows are held | the mapping window, or deduplication |
| `SOURCE_SILENT` | a run reached the source and it returned nothing | the filer, not us |
| `NOT_YET_COLLECTED` | applicable, nothing held, **no run has ever asked** | **the only backlog item** |
| `DELIBERATELY_DECLINED` | a recorded decline, with a reason code | a decision already made |
| `UNMAPPED` | a source concept we can see and no declaration claims it | the registry |
| `SOURCE_UNAVAILABLE` | the inventory says the filer reports no such concept | the filer |
| `NOT_APPLICABLE` | the registry rules the metric out for this business model | nothing; it is a statement about the company |
| `UNDETERMINED` | the archive predates the scope record | an older build, not a gap |

The ordering inside `_status` is the argument, and it is deliberate: the
**decisions are evaluated above the fetches**, so a deliberate refusal can never
be reported as a gap to be filled. `COLLECTED` comes first because it is the
only positive fact, but it does not outrank `NOT_APPLICABLE` — a decision about
the company beats a fact about collection.

`NOT_YET_COLLECTED` is the only status flagged `is_backlog_item`. A to-do list
built from the other four would be a list of work somebody already did, or
already decided against.

---

## 3. Two records that did not exist

### 3.1 `ingestion_scope` — what was asked

`ingestion_runs` recorded what a run *did* (filings seen, documents stored,
facts kept) and nothing about what it was *for*. So "this metric has no
observations" was a sentence with three meanings that all read the same:

```
we never asked                        the registry maps nothing we queried
we asked and the filer was silent     the concept endpoint returned nothing
we asked, and the rows are not here   deduplicated away, or the window closed
```

`ingestion_scope` is one row per metric per run, with a closed status
(`INGESTED`, `SOURCE_SILENT`, `NO_MAPPING`, `NOT_ATTEMPTED`, `ERROR`).

Two details that are easy to get wrong and are pinned by tests:

- **A run that returned early because nothing was new has asked nothing**, and
  records `NOT_ATTEMPTED`. Written on every run, including the ones that ask
  nothing, because an unattempted metric is the single most useful thing a
  coverage figure can report.
- The scope is buffered and written **in the same transaction as the run row**,
  so a run can never exist without its scope or the reverse.

The ledger unions scope across runs rather than reading the last one, so a later
`NOT_ATTEMPTED` cannot silence the evidence that an earlier run reached the
source.

### 3.2 `declined_concept_mappings` — what was rejected

2.7's nine IFRS decisions were prose in a seed file. An archive holding 3.0% of
a filer's concepts could report what it held and not what it had considered and
rejected — which is most of what a coverage claim has to be honest about.

Nine declines are now records, each with a **closed reason code**:

| concept | metric | code |
| --- | --- | --- |
| `RevenueFromContractsWithCustomers` | revenue | `COMPONENT_OF` |
| `RevenueFromInterest` | revenue | `COMPONENT_OF` |
| `RevenueFromGovernmentGrants` | revenue | `COMPONENT_OF` |
| `RevenueFromDividends` | revenue | `COMPONENT_OF` |
| `DilutedEarningsLossPerShareFromContinuingOperations` | eps_diluted | `DIFFERENT_QUANTITY` |
| `NumberOfSharesAuthorised` | shares_outstanding | `IDENTITY_MISMATCH` |
| `IssuedCapital` | shares_outstanding | `NOT_A_METRIC` |
| `LoansAndAdvancesToCustomers` | revenue | `NOT_A_METRIC` |
| `InterestRevenueExpense` | revenue | `DIFFERENT_QUANTITY` |

Keyed on **(concept, metric considered)** rather than the concept alone,
because the interesting declines are *near misses* — a concept that expresses
almost the right thing is the one worth recording, and keying on the concept
would lose the metric it was nearly good enough for.

It is a concept-and-metric record and **not a per-issuer one**. "This element
measures continuing operations" is a fact about the element and does not become
true or false per company; a per-issuer decline would multiply one decision by
the number of filers and invite a reader to think a framework judgement had been
made separately for each.

---

## 4. What the 3.0% actually means

The same three issuers, the same archive, one question.

| | AAPL | TSM | NU |
| --- | --- | --- | --- |
| business model | MANUFACTURING | MANUFACTURING | FINANCE_SERVICES |
| **Core metrics applicable** | **18** | **18** | **16** (2 not applicable) |
| **collected** | **7 — 38.9%** | **7 — 38.9%** | **5 — 31.3%** |
| mapped, none held now | 2 | 0 | 0 |
| asked, source silent | 0 | 0 | 1 (`debt`) |
| **not yet collected (backlog)** | **9** | **11** | **9** |
| deliberately declined | 0 | 0 | 1 (`shares_outstanding`) |
| not applicable | 0 | 0 | 2 (`gross_profit`, `operating_income`) |
| concepts the filer reports | 505 | 336 | 151 |
| concepts declared or declined | 35 | 35 | 35 |

**So the answer to "3.0%" is:**

```
TSM, measured against what ST-EVA promised:
    18 applicable Core metrics
     7 collected
    11 never asked for          <- an 11-item backlog, and it is knowable

TSM, measured against what TSM reports:
    336 concepts
    10 declared
     9 declined, with reasons
   317 not considered
```

The first is the product question and it has an answer. The second is the
2.7 number, and it is not a score — it is the size of a space ST-EVA has not
promised to fill, reported so nobody has to guess at it.

**Every issuer has the same 35 declared-or-declined concepts**, which is the
point: the semantic layer is issuer-independent, and the differences between
these three companies are entirely in what has been collected and what applies
to them.

### Two statuses worth stopping on

**`shares_outstanding` for NU is `DELIBERATELY_DECLINED`.** Both IFRS candidates
are declined — authorised shares count a different population, and
`IssuedCapital` is a currency amount — and NU reports no share count. A metric
whose only candidate concepts were rejected is not a backlog item and not a
silent gap; it is a decided thing, and the ledger says which.

**`debt` for NU is `SOURCE_SILENT`.** Asked, and the source had nothing under
the declared IFRS borrowings elements. A fact about the filer, and a completely
different piece of work from the eleven `NOT_YET_COLLECTED` metrics beside it.

### Also surfaced, correctly

`long_term_debt_current` and `long_term_debt_noncurrent` are Core metrics that
map to the same concepts as `debt`, and hold nothing — because the archive stores
the **composed** metric. The ledger reports that rather than hiding it: a
component of a declared composition is not separately collected, and a reader who
asks about one deserves to be told.

---

## 5. Reachable the way a consumer can reach it

```
query.coverage_ledger("TSM", source_inventory=...)
```

The same eight statuses, the same derivation, plus `source_inventory_known` and
`scope_known` so a caller can tell a thin answer from an undeterminable one. The
`variance` and `crossframework_verify` instruments read through the same path.

---

## 6. Two of my own errors, and what they showed

**A decline was made to compete with a collection.** The first version treated
`DELIBERATELY_DECLINED` as a status, so a metric collected through one concept
hid every decline against another. But a decline is a fact about a *concept*:
AAPL's revenue is collected through US-GAAP concepts while four IFRS revenue
elements are declined, and those are framework judgements rather than per-issuer
ones. Declines are now a **row attribute** that coexists with any status, and
become the *status* only when nothing is held — where they are the only
explanation available.

**`decline_concept_mapping` skipped its own validation.** `DeclinedConcept`
validated the reason and the qualification; the method that wrote it did not. Two
validation paths is how a blank reason reaches a table whose trigger refuses one
— the dataclass checked on the seed path and the method did not. There is now one
path, and it constructs the validated record.

A third was caught by a test rather than by reading: an archive predating
migration 0012 would have reported every uncollected metric as `NOT_YET_COLLECTED`
— *nobody has ever looked* — about metrics it plainly holds observations for. It
now answers `UNDETERMINED`, which is the only honest thing an archive without a
scope record can say.

---

## 7. What is still missing

**The ledger does not do concept-level `UNMAPPED` matching.** `UNMAPPED` fires
when a metric has no declared concept and the run that asked found none; it does
not fire when the inventory reports a concept that nothing claims. NU is the live
example: it reports `ifrs-full:Borrowings` (1,730,357,000), no mapping claims
it, and the ledger does not say so. Doing it properly means matching an
inventory concept to a metric without a mapping, which is the "similar label"
problem 2.7 spent a phase refusing to solve by name — and an `UNMAPPED` status
built on a name match would be worse than none.

**Declines are per framework, not per filer.** Correct for the nine recorded, and
it means a decline is visible to every issuer whether or not that framework
applies to them. The `framework_basis` column makes the scope explicit, but
nothing filters on it yet.

**Collection is still the bottleneck, and it is now measurable.** The eleven
TSM backlog items and the nine for AAPL are the same list of Core metrics, which
is the useful consequence: widening collection is one decision, not three
per-issuer negotiations. Whether to make it is 2.9's question, and the ledger is
what makes it answerable.

---

## 8. State

| | |
| --- | --- |
| full suite | **578 passed**, 74 skipped (was 554) |
| `verify_harness` | unchanged — reference 0/15, each broken target failing only its own test |
| sealed AAPL snapshot | `ce603a5588cef067` — byte-identical |
| new tests | `tests/test_coverage_semantics_2_8.py`, 24 tests |
| migrations | 0012 `ingestion_scope`, `declined_concept_mappings` |
| issuer-specific anything | 0 |

```
Source universe  ->  Core scope  ->  Collected  ->  Discoverable
   (inventory)         (ledger)      (ledger)     (2.6.6)
  ->  Correctly interpreted  ->  Correctly encoded  ->  LLM research
        (2.6.5)                    (2.6.6)
```

The chain is complete end to end, and each arrow is a separate measurement with
its own vocabulary. That is what 2.6.6 built the three axes for, and what this
phase adds upstream of them.
