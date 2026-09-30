# 2.12 — Bulk bootstrap and reconciliation

The one untested link in the chain. 2.11 measured the incremental path at 23.4
requests per company with a second pass at zero, said that at 234,000 requests for
ten thousand issuers the SEC's own guidance is that bulk archives are the right
mechanism, and said the reconciliation between the two was **documented but never
exercised**. This is that exercise.

**Result: the two paths produce the same evidence. 7,956 observations, 7,956
matched, zero divergent values, zero one-sided.**

---

## 1. The abstraction held, and that is the finding

A bulk source needs **no second ingestion path**. Verified before writing the
code: a `companyconcept` payload is *exactly* a `companyfacts` slice plus four
envelope fields — `cik`, `entityName`, `taxonomy`, `tag` — with **byte-identical
fact rows**.

```
companyconcept  {'cik','description','entityName','label','tag','taxonomy','units'}
companyfacts[]  {'description','label','units'}
rows            IDENTICAL   (117 = 117, byte for byte)
```

So `sec_bulk.py` is thin by construction: it reads one local document per issuer
and reconstructs the envelope. The whole provider interface `Ingestor` uses is six
members, and a source that reads a nightly archive and a source that makes
twenty-three requests are **interchangeable to the archive**.

That is the property that makes the two paths reconcilable at all. Had the bulk
path needed its own ingestor, the two archives would have been two different
things that happened to share a name, and reconciling them would have proved
nothing.

---

## 2. The reconciliation

| | |
| --- | --- |
| API-path observations in the archive | 54,602 |
| bulk-path observations built | **7,956** |
| **MATCHED** | **7,956** |
| divergent *values* | **0** |
| only in API | **0** |
| only in bulk | **0** |
| issuers compared | 9 |
| **provenance-only differences** | **7,956** |

**Seven thousand nine hundred and fifty-six observations, byte-identical values,
from two entirely different delivery mechanisms.** The same `Ingestor`, the same
registry, the same semantics, the same archive — which is the question 2.7 asked
about frameworks and 2.11 asked about scale, now answered for delivery.

### The one difference, and why it is not a disagreement

**All 7,956 differ in `document_id`, and none in anything else.**

The API path reads a fact from that issuer's `companyconcept` document. The bulk
path reads the same fact from the `companyfacts` document. Both are honest: the
fact *was* read from those bytes. They are not the same bytes, so the two archives
attribute identical evidence to different provenance.

This is exactly why the reconciler classifies provenance separately rather than
letting it land in `DIVERGENT`. **An archive rebuilt from a different source would
otherwise look like it disagreed with itself**, and a diff that reported 7,956
differences would train a reader to ignore diffs.

---

## 3. The economics, which is why the SEC says to use bulk

| per company | API path | bulk path |
| --- | --- | --- |
| **network requests** | **23.4** | **0** |
| documents read | ~23 | **1** |
| seconds | 10.8 | 1.6 |
| observations | 728 | 663 |
| archive | 2.33 MB | 2.06 MB |

Twelve issuers: **19.2 seconds, 0 requests, 23 MB read from disk.** The
observation counts differ slightly because these twelve are a subset and three had
nothing new to ingest.

**23.4 requests per company becomes one document per company.** That is the whole
argument for bulk at population scale, and it is now measured rather than
asserted: the 234,000-request bootstrap of 2.11 becomes **10,000 documents**.

---

## 4. Two things `companyfacts` does not carry

Both surfaced by building the source rather than by reading about it, and both
handled rather than papered over.

**The SIC classification.** `companyfacts` has no submissions payload, so an
issuer classified from bulk alone is unclassified and every declared metric stays
applicable — the safe default, and the same position 2.10 measured for a filer
whose SIC major group the rule does not recognise. The source therefore takes an
optional `submissions` directory, and reports `submissions_available: false` when
it has none, so a caller can tell **why** no ruling was made instead of inferring
it from a metric that happened to come back empty.

**The filing index.** `companyfacts` has no submissions index either, so this
source derives one from the facts: every accession that contributed a fact becomes
an accepted filing, with its form and filing date. That is a *narrower* index than
the API path's — a filing that contributed no fact we can see is invisible — and a
**better** one for bootstrap, because every entry is a filing that actually carries
evidence.

---

## 5. A bug this round refused to commit

My first bulk source resolved a ticker by matching the company name:

```python
if name.upper().startswith(ticker.upper()):   # resolved 2 of 12
```

That is **exactly the guess the API provider explicitly refuses to make** —
`resolve_company` documents that guessing a CIK would attach another issuer's
filings to a ticker and make every comparison after it false. It resolved 2 of 12
issuers, and both were accidental.

A bulk archive is keyed by CIK and says nothing about tickers, so the mapping has
to come from the file that has it. `fetch_inventory` now writes a `tickers.json`
beside the documents and `BulkFactsSource` reads it; an unmapped ticker returns
`None`, which upstream is the already-classified `ISSUER_UNRESOLVED` rather than a
guess.

The first version of this round would have shipped a source that quietly attached
filings to the wrong company — and the reconciliation, had it passed, would have
been comparing two wrong things consistently.

---

## 6. What is now settled

The bootstrap path is **exercised**, not documented. A ten-thousand-issuer
corpus has two working routes to it and they agree:

```
bootstrap    bulk archive   -> 1 document per issuer, 0 requests
incremental  submissions    -> 0 requests when nothing is new, and the
                               2.11 second pass was exactly that
```

Both write through the same ingestor, the same registry and the same semantics, and
the reconciliation between them is zero-unexplained over 7,956 observations.

## 7. What is still not settled

**The per-company constant remains a floor**, for the reason 2.11 gave and this
round did not change: the sample has no mega-cap, and the twenty-year archives
live in files the submissions payload only names. A mega-cap-weighted resample is
still the measurement that would revise it.

**The bulk archive itself has not been downloaded.** This exercises the *interface*
a bulk archive is read through — one document per issuer, keyed by CIK — using the
per-issuer documents fetched individually, because a delivery format is not where
the semantic risk was. What is untested is a zip of several gigabytes and the
reconciliation of a **bulk bootstrap into an archive that an incremental run has
already touched**, which is the harder direction: the incremental run may have
observations the bulk payload predates, and whether those survive a bulk bootstrap
is a question about append-only evidence that this round did not reach.

That is the next piece of work, and it is now a small one rather than an unknown.