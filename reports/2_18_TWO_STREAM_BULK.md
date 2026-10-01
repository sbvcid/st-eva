# 2.18 — `companyfacts + submissions`: what the second stream is worth

2.17 concluded that business-model applicability is not a coverage problem but a
reachability one: `companyfacts` carries no SIC, so no business model is recorded,
so no applicability rule fires, and `applicability` reads 0/160 on a population of
eight filers that were already classified in another archive.

The question is therefore **not** "must bulk ingestion have submissions" but the
sharper one: **which semantic capabilities become unreachable without it?**

```
companyfacts   what a filer ever tagged        -> facts, and only facts
submissions    the filer's own filing history,
               and the filer's own SIC          -> issuer and filing context
```

Eight `companyfacts` documents and eight `submissions` documents, one request each,
the same eight issuers, the same twenty metrics, the same instrument.

```
                       companyfacts only      + submissions
observations                    11,174             11,174        unchanged
distinct identities             11,174             11,174        unchanged
duplicate identities                 0                  0          unchanged
metrics yielding                      15                 15        unchanged
facts without an accession            0                  0        unchanged
observations without a document       0                  0        unchanged
filings held                        389                858        2.2x
availability basis     FILED_AS_OF_DATE 1174    ACCEPTANCE_DATETIME 11022
                                                  FILED_AS_OF_DATE   152
applicability gate                 0/160            160/160        restored
reconciliation vs the API archive    0 matched      5447 matched    of 5535
                                   5535 divergent     88 divergent
```

**Facts did not move. Context did.** Every number in the first block is identical,
and that is the finding: the second stream changes nothing about the evidence and
everything about what can be said about it.

---

## A. The capability split, measured rather than asserted

| capability | companyfacts only | + submissions |
| --- | --- | --- |
| fact identity | 11,174 distinct, 0 duplicates | **unchanged** |
| metric mapping | 15 metrics yield | **unchanged** |
| provenance chain | complete, 389 filings | complete, **858 filings** |
| point-in-time | 100% declared date, one-day-late bound | **98.6% acceptance instants**, 0 eligible too early |
| reconciliation against the API path | 0 matched of 5,535 | **5,447 matched**, 88 divergent |
| applicability / business model | **0/160** | **160/160** |

So the answer to "which capabilities become unreachable" is narrow and precise:
**only the classification-dependent ones.** Identity, mapping, provenance and the
value of every observation are untouched, because none of them reads a SIC.

What is genuinely restored is three things, and they are worth separating:

1. **Applicability.** All eight banks are now classified from their own SIC —
   6022 and 6029 and 6035, five state commercial banks, one commercial bank NEC and
   two federally chartered savings institutions — and every metric's ruling
   derives. `gross_profit` and `operating_income` read `NOT_APPLICABLE` for all
   eight. This is the first time an applicability rule has fired in a bulk-built
   archive at all.

2. **Point-in-time precision.** 11,022 of 11,174 facts now carry EDGAR's acceptance
   instant instead of a filed date. The remaining 152 fall back to a declared date
   because their accession sits outside the submissions window, which is the
   correct answer rather than a gap. `declared value promoted to an instant: 0`,
   `eligible before the source said it was public: 0` — the invariant holds with
   the sharper data, which is the point of having it checked.

3. **Equivalence with the API path.** 5,447 of 5,535 shared facts now match on
   *every* semantic field including `available_at`. The bulk path stopped being a
   different kind of source and became the same kind, read from a file.

The 88 that still differ are all one thing: **the reference archive holding the
pre-fix midnight fabrication.** Those accessions sit outside the submissions window,
so the API-built archive recorded `T00:00:00+00:00` labelled
`ACCEPTANCE_DATETIME` — the defect 2.14 fixed — while this archive correctly records
the bare date as `FILED_AS_OF_DATE`. Zero unexplained rows, for the third time.

---

## B. The filing ledger widened without the evidence moving

`filings_held` went 389 → 858 while `distinct_accessions_in_observations` stayed at
389. That is the distinction `Ingestor.coverage` was written to state and that 2.15
found the gates could not read:

- **evidence coverage** — 389 filings actually contributed tagged facts
- **filing-ledger coverage** — 858 filings the filer declared

The derived index can only prove the first. The submitted index carries the second,
which is what makes incremental ingestion answer "what is new since the last run"
for filings that tagged nothing we ask for.

Per issuer the gap is uneven and instructive:

```
BBAR        8 filings held    253 obs     11 metrics
NRIM      128 filings held   2695 obs     14 metrics
FHB       121 filings held   1496 obs     13 metrics
```

BBAR held 8 filings against 253 observations and 11 metrics — because BBAR's facts
arrive with 20-F filings whose accessions the derived index resolved to a handful.
Its facts were fine; its ledger was 16 times narrower than the filer's own account
of itself.

---

## C. What the restored ruling exposes, now materialised

With the classification finally live, the contradiction 2.17 identified from the
raw source is visible inside a single archive:

```
                ledger status        observations in the archive
gross_profit    NOT_APPLICABLE       40   (BBAR 18, NRIM 22)
operating_income NOT_APPLICABLE        0
```

**The archive holds 40 observations for a metric it reports as inapplicable.** NRIM
tagged `us-gaap:GrossProfit` in twenty-two rows and BBAR tagged
`ifrs-full:GrossProfit` in eighteen, and both facts were stored, and the ledger says
the metric does not apply to a bank.

That is not a data-integrity problem — it is the semantic contradiction now visible
rather than inferred, and it is exactly the state in which the decision is worth
making. Three options, none taken here:

- **narrow the rule** so `gross_profit` is not refused for `BANK`
- **keep it**, and accept that two filers' reported gross profit is collected and
  then not counted
- **refuse to store** observations for a metric the ledger calls inapplicable, so
  the archive and the ledger agree — which is a *third* decision, distinct from
  whether the rule is right, because it is about whether evidence and a coverage
  ruling are allowed to disagree inside one archive.

The third is the one this round makes unavoidable by existing at all, and it is the
only place where the two-stream archive behaves differently from what the coverage
semantics were written to assume.

---

## D. Two engineering defects, both mine, both caught

**Recursion between `filing_index` and `submissions`.** Teaching `filing_index` to
prefer the submitted index made it call `submissions`, whose companyfacts-only
fallback payload calls `filing_index` to report a count. Every companyfacts-only
mode recursed until the stack ran out. The offline suite caught it on the first
run, in `test_the_bulk_source_declares_a_date` — which is the derived-index test
and therefore the exact case every prior measurement depends on.

Fixed by splitting `_submissions_document` out of `submissions`, so the document
lookup and the reporting payload are separate. Worth noting that the test which
caught it is one added two rounds ago for an unrelated reason: the availability
contract and the bulk index shape happened to be guarded by the same assertion.

**`is_xbrl` became a string in the submitted index.** The API path stores
`isXBRL` verbatim; the derived path stored the integer `1`. `Ingestor` tests
`str(entry.get("is_xbrl") or "") == "1"`, so both work — but the two index shapes now
differ in type where they used to agree, and a future change to that test would
break one path silently. Recorded, not changed.

---

## E. State

| | |
| --- | --- |
| full suite | **620 passed**, 74 skipped, 694 run |
| production change | `sec_bulk.filing_index` prefers the submitted index, derived index kept as fallback |
| regressions | six-issuer and eight-bank companyfacts-only modes re-run, **byte-identical results** |
| archives | `snapshot-banks2.sqlite`, none modified in place |
| committed artefact | `harness/banks2-218.json` |

The derived path is untouched and remains the fallback, so every companyfacts-only
measurement taken before this round still reproduces — verified by re-running two of
them rather than by reasoning that it should.

## F. What this settles, and what it opens

**Settled:** the two-stream shape is the right one and it costs one extra request
per issuer. The SEC bulk distribution ships both, so nothing has to be synthesised:
`companyfacts` for facts, `submissions` for context, and no heuristic
classification anywhere.

**Opened, in priority order:**

1. **`gross_profit` for BANK** — the contradiction in section C, now live.
2. **Should ingestion store evidence for a metric the ledger calls inapplicable?**
   The question only exists because the ruling is now reachable.
3. **`r_and_d` and `sga` for banks** — `SOURCE_SILENT` at 8/8 and 7/8 with the
   evidence unanimous, which is the strongest applicability candidate this project
   has.
4. **`debt`** — `SOURCE_SILENT` at 8/8 and it is a registry gap, not a filer one:
   0 of 8 tag the four mapped concepts while 6 of 8 tag `us-gaap:LongTermDebt`.