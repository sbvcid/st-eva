# 2.11 — Scale / Universe Ingestion

The question is not what ST-EVA should be. That is answered. It is:

> **can it accumulate ten or twenty years of traceable evidence for a thousand
> companies, cheaply and incrementally, without changing what evidence means?**

Seventy-five issuers, twelve SIC strata, two accounting frameworks, every filing
form the population actually uses. And the answer turns out to rest almost
entirely on one number.

---

## 1. What a company costs

| per issuer | |
| --- | --- |
| **requests** | **23.4** |
| **seconds** | **10.8** |
| wire bytes | 36,580 |
| observations | 728 |
| **archive size** | **2.33 MB** |
| seconds per filing | 0.13 |

Totals: **6,160 filings, 54,602 observations, 708 source documents, 174 MB**, in
**13.5 minutes** for 75 companies.

The cost is strikingly flat — 23.4 requests per company, whether it is a
semiconductor firm with two decades of 10-Qs or a REIT with three filings. That
flatness is the structural result, and it comes from the design: the request
count is a function of *how many filings were accepted*, and the per-filing cost
is 0.13 seconds. A company is expensive because it has a long history, not
because it is large.

### Extrapolated to 10,000 issuers, on this sample's profile

| | |
| --- | --- |
| requests, first bootstrap | **234,000** |
| — at our 4 req/s self-limit | 16.2 hours |
| — at the SEC's 10 req/s ceiling | 6.5 hours |
| wall clock at current throttle | 29.9 hours |
| observations | 7.3 million |
| archive | **23.3 GB** |
| requests, every subsequent pass | **0** |

**234,000 requests, once.** That is the whole of the bootstrap, and the SEC's own
guidance is that bulk archives are the right mechanism at that volume rather than
234,000 individual API calls. The per-company cost here is the API path's cost;
the archive path exists precisely because it is smaller.

**The honest caveat, which decides how much weight the extrapolation carries.**
This sample is deliberately the *cheapest* defensible one: the deepest readable
history found within a strided sample of 700 candidates from EDGAR's own map. It
contains no mega-cap — the largest filer here is a small REIT or a mid-cap
insurer — because a mega-cap's recent submission window is mostly Form 4 and
Form 8-K, so ranking by raw form count *selects against* them. The
twenty-year 10-K archives live in files the submissions payload only *names*,
and reading them would cost a request each, which is why the ranking uses the
depth visible in the recent window instead.

So **23.4 requests and 2.33 MB per company is a floor, not a central estimate.** A
mega-cap with twelve years of 10-Ks, 10-Qs and 8-Ks carries the same number of
concepts across far more filings. The linear shape of the cost is what
extrapolates; the constant is what a 10,000-issuer sample would revise.

---

## 2. The incremental claim, measured

This is the number the round turns on, because it separates "ST-EVA can ingest
EDGAR" from "ST-EVA can be *maintained* against EDGAR".

```
first pass    1755 requests   2,743,506 bytes   807 seconds   54,602 observations
second pass       0 requests          0 bytes     0.3 seconds        0 observations
                                        ratio: 0.0
```

**Zero. Not "few" — zero.** A second pass over the same population issued no
request at all, because the submissions index is re-read to discover new filings,
nothing was accepted since, and the run therefore asked about no concept. The
ingestion ledger, held filings and source-fact identity that 2.5 built are what
make it zero rather than merely small.

Extrapolated: **the first pass costs 234,000 requests and every pass after it
costs nothing.** A nightly incremental run over 10,000 issuers is 10,000 index
reads and however many filings arrived since — which is the shape an accumulating
corpus actually has.

---

## 3. Every failure is classified

The acceptance criterion for this round is explicitly **not** a success rate. A run
that says "93% collected" is worth less than one that says what the other seven
percent was.

**By issuer — 75 issuers, and nothing unclassified:**

| outcome | n |
| --- | --- |
| `COLLECTED` | **70** |
| `SOURCE_SILENT` | 3 |
| `NOT_ATTEMPTED` | 2 |
| `PARSER_FAILURE` · `FILING_UNSUPPORTED` · `ISSUER_UNRESOLVED` | **0** |

**By metric slot — 1,500 slots:**

| | n |
| --- | --- |
| classified failures, all `SOURCE_SILENT` or `NOT_ATTEMPTED` | **109** |
| unclassified | **0** |

Two of the nine kinds earned their place immediately. `NOT_ATTEMPTED` fires for
issuers whose index reported no new accepted filing, and `SOURCE_SILENT` for the
93 metric slots where the concept endpoint had nothing — which is a fact about the
filer, and would have read as "the registry has no mapping" in a count.

`PARSER_FAILURE` and `FILING_UNSUPPORTED` are both zero, and that is a result
rather than an absence: the distinction exists because **a filing whose form the
pipeline does not handle and a filing whose document will not parse look
identical in a count** — both produce nothing — and they call for opposite
responses, one being scope and the other a bug. Neither occurred, and the
vocabulary that would tell them apart is now in place for a population that
produces them.

### One behaviour changed, and it was wrong before

An unresolvable ticker used to raise. At population scale **a raise ends the
run** — one bad name on issuer three leaves ninety-seven unclassified and the
report names only the issuer that stopped it. It now returns
`ISSUER_UNRESOLVED` and the run continues. The claim the sealed test was making
(*an unresolvable ticker ingests nothing*) is unchanged and still asserted; only
the shape of the report changed, and the test was rewritten to pin the
classification as well as the absence.

---

## 4. A ticker is not an issuer

Found by running, at issuer thirty of seventy-six: a preferred share and its
common mapped to one CIK, and `record_asset` refused the second with a UNIQUE
violation.

The constraint is right — two rows for one filer would put the same filing under
two names and make every later comparison ambiguous — so the fix belongs in the
caller and the lookup, not in the constraint:

- the stratified sample deduplicates by **CIK**, not by ticker;
- `SQLiteArchive.asset_id_for_cik()` resolves an issuer we already hold under a
  different ticker, so a second arrival is a lookup rather than a violation.

It matters for the cost model: EDGAR lists **10,431 tickers** for far fewer
companies, so a population drawn from tickers over-counts, and *requests and
megabytes per company* would be understated by however many share classes a
company trades. The EDGAR map discovered 700 candidates down to 75 issuers.

---

## 5. The population

Drawn from EDGAR's own company map, **strided rather than prefixed** — the first
version took the first 700 alphabetically and produced 73 issuers all beginning
with A, mostly warrants and Form 4 filers, and not one company anybody would
name. A contiguous slice of a ticker map is a sample of its first page.

Within each SIC stratum, the issuers with the **deepest readable history** are
taken, because that is the hard case: a thinly-filed company would report a
per-company cost a real population would not pay.

```
bank 8    chemicals 8    industrial_technology 8    insurance 8
manufacturing 5    reit 8    retail 3    semiconductor 8
services 3    software 8    utilities 1    utilities_transport 7
```

**Both filing regimes are represented** — 20-F and 40-F filers sit beside 10-K
ones, which is what the cross-framework work of 2.7 has to survive at scale. And
**forms are derived from each issuer's own submission history, not assumed**:
asking 10-K/10-Q across a population reports every foreign private issuer as
`SOURCE_SILENT`, which is a fact about our request dressed as a fact about the
filer.

---

## 6. A number I removed because it was wrong

The first version of `transport_stats()` reported a `deduplication_ratio` of
**0.157**, computed as wire bytes divided by retained document bytes. Those are
different units — one is gzipped off the wire, the other the decompressed
payload we keep — so the ratio was a category error producing a confident
nonsense number. It is gone rather than corrected, because a real deduplication
figure needs *served* bytes on both sides and the provider does not have them.

What is reported instead is **requests per unique document: 2.48** — how many
times a document had to be asked for before it was kept once. That is meaningful,
it is the same order as the flat 23.4-requests-per-company figure, and it is the
number that says deduplication is already doing most of its work.

---

## 7. What this settles, and what it does not

**Settled.** The per-company cost is small, flat and linear in filings. The
incremental pass is free. Every failure carries one of nine kinds, and the two
that would have needed a decision — a parser fault and an unsupported form — did
not occur. The archive holds 75 issuers across two frameworks, twelve industries
and five business models with **one semantic layer and no change to what
evidence means**.

**Not settled.** The per-company constant is a floor, for the sampling reason in
§1. The archive path is *documented* here, not exercised: at 234,000 requests the
SEC's own guidance is that bulk archives are the right mechanism, and ST-EVA's
2.5 identity model is what would make a bulk bootstrap reconcile with an
incremental one — but the reconciliation itself is untested, and it is the
single thing standing between this sample and a ten-thousand-issuer corpus.

**What I would do next, in order:** build the archive reconciliation, because it
is the only untested step in the chain; then re-run this population with a
deliberately mega-cap-weighted sample, because that is what would revise the
constant; and only then consider 1,000. The risk at scale is no longer semantic —
there is no ambiguity left in what a number means — it is doing a thousand
companies badly in a way a 75-company sample cannot show.
