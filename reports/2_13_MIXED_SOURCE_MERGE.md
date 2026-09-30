# 2.13 — Mixed-source bootstrap, and the irreversibility test

2.12 proved the two delivery paths produce the same evidence when one of them is
the only source. That is the easy direction: there was nothing to overwrite. The
hard one is a bulk bootstrap arriving into an archive an incremental run has
already built.

Every irreversibility claim holds. One architectural finding, which is worth more
than the claims.

---

## 1. The experiment

One archive, three steps, in order, with the two asymmetries created from real
data:

```
step 1   incremental API, 3 issuers, narrow Core scope (8 metrics)   4,002 obs
step 2   bulk bootstrap, 5 issuers, full Core scope (20 metrics)   +5,998 obs
step 3   incremental API, 5 issuers, full Core scope              +95 obs
```

- **Metric scope differs.** The incremental archive was built with the older,
  narrower metric set; the bulk pass runs the full Core set.
- **Recency differs.** The bulk payload has each issuer's most recent accessions
  **removed from it** — 4,108 fact rows across 12 documents — which is exactly
  what a nightly archive built before those filings landed looks like. The
  trimming is in the *input*; nothing in the archive under test was edited to
  manufacture a difference.
- **Coverage differs.** Two of the five issuers (`NEON`, `RBC`) are in the bulk
  set and not the incremental set, so they are genuinely bulk-only evidence.

The irreversible sequence the brief asked for is the shape of it: **incremental
→ bulk → incremental**, ending with every earlier fact under the same
`source_fact_id` and the same `observation_id`.

---

## 2. Every irreversibility claim, measured

| | |
| --- | --- |
| **bulk-only evidence added** | **yes** — `NEON` and `RBC` ingested entirely from bulk |
| already-shared evidence duplicated | **0 duplicate identities** |
| **incremental-new evidence preserved** | **yes** — nothing removed in any step |
| **any existing observation changed** | **no** — 0 changed, across all three steps |
| **any existing observation removed** | **no** — 0 removed |
| **identity stable** | **4,002 of 4,002 survived three steps, 0 lost** |
| `source_fact_id` stable under both routes | **yes** |
| `UPDATE` on an observation | **refused: observations are append-only** |
| `DELETE` on an observation | **refused: observations are append-only** |

Per step: `added 5,998 / removed 0 / changed 0` and `added 95 / removed 0 /
changed 0`.

**The append-only guarantee was attempted, not assumed.** The archive carries
`observations_no_update` and `observations_no_delete` triggers, and an append-only
guarantee nobody has watched refuse a write is a comment rather than a guarantee,
so the experiment issues a real `UPDATE` and a real `DELETE` against a real
observation and records that the database refused both.

**Duplication is measured on identity, not on row count.** A fingerprint counts
rows, so a second row for the same evidence would look like a successful
addition. The check is therefore a `GROUP BY` on
(ticker, metric, period end, source fact id) `HAVING COUNT(*) > 1` — **zero**,
after every step.

---

## 3. The finding: neither route can widen scope once filings are held

**A bulk bootstrap does not widen an existing archive's metric coverage, and a
later incremental pass does not either.**

```
fresh archive, full Core scope, LTRX alone      18 metrics
step 1, narrow scope, then bulk at full scope     8 metrics
step 3, incremental at full scope                 8 metrics
```

Ten Core metrics exist for this filer, the registry has concepts for them, and
**neither later route fetched them.** The cause is the incrementality guard:
`ingest()` returns as soon as every filing in the index is already held, *before*
the metric loop. A source that is asked about an issuer with nothing new to
learn is asked about nothing at all — which is exactly the property 2.11 measured
as its best result, and here it is also the thing that blocks a legitimate
request.

This inverts the architecture the brief proposed:

> **Initial: SEC bulk** → historical Evidence
> **Ongoing: SEC submissions/API** → new filings

is right, and the reason is sharper than "bulk is cheaper". It must be **bulk
first, on a fresh archive, at the full Core scope.** Run incremental first at a
narrow scope and no later route will ever backfill the difference, because the
guard cannot tell a metric that was never requested from a metric the filer does
not report.

The operational consequence is a rule rather than a bug: **changing the Core
metric set is a re-bootstrap, not an incremental run.** And a coverage report has
to distinguish them, or it will read "18 metrics" and "8 metrics" as the same
kind of absence.

---

## 4. A bug this round nearly reported as a finding

Step 2 first added **nothing at all** and finished in 0.2 seconds. That looked
like "the bulk merge is a no-op, and therefore safe".

It was not safe and not a merge: the trimmed payload directory carried an
**empty** `tickers.json`, so the bulk source resolved **no** issuer and ingested
**no** issuer. An empty map and an empty archive look identical from outside, and
the experiment would have reported a clean pass.

The failure was only visible because a merge that adds nothing after ingesting
5,998 observations in the next step is arithmetically impossible, and the two
steps were printed side by side.

The generalisation is worth keeping: **a merge test that cannot fail is not a
test.** The reason it could not fail was an input that resolved to nothing, and
nothing in the "no errors" output said so.

---

## 5. What is settled, and what is next

**Settled.** Evidence is append-only across ingestion routes. A bulk bootstrap
into a live archive adds what is genuinely new, duplicates nothing, changes
nothing, removes nothing, and leaves every prior fact under the same identity.
The three-step sequence is irreversible-safe, and the two paths can be used in
any order provided bulk comes first on a fresh archive.

**Not settled.** The **per-company cost constant** is still a floor — no mega-cap
in the sample, unchanged since 2.11. And the bulk archive itself has still not
been downloaded: this round again exercised the *interface* one is read through,
because a delivery format is not where the semantic risk was.

And the thing this round actually changed about the plan:

```
        bulk bootstrap          SEC bulk archive
        ↓
     Evidence DB               fresh, full Core scope, all issuers
        ↓
     incremental              submissions endpoint, new filings only
```

with the rule that **scope changes are re-bootstraps**. Getting to a corpus of
thousands now has no untested step in it: the interface, the reconciliation, the
merge, the irreversibility, the append-only guarantee, and the scope rule have all
been measured on real filings. What remains is arithmetic and an operations
decision — how many companies, which Core metrics, how often to run, and where
the boundary of free public data sits.
