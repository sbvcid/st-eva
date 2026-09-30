# 2.10 — Completing the coverage surface

The two gaps the 2.9 gates found, closed. No collection work, and nothing in
this round changes what is collectible — which was the constraint, and it is
checked below rather than asserted.

---

## 1. A services business model

2.9's gate 6 failed for exactly one issuer, on all twenty of its metrics. The
reason was not a wrong ruling. It was that there were none.

```
MSFT  SIC 7372  Services-Prepackaged Software   major group 73
      the rule covered 10-14 mining, 20-39 manufacturing, 60-67 finance
      an unrecognised classification deliberately makes no ruling
      so every metric stayed applicable, with nothing on the record
```

A services classification is a one-line change and makes twenty failing gates
pass. It is made here deliberately, with the constraint stated:

> **adding `SERVICES` must not make any metric more collectible.**

A business model earns a place in the vocabulary by carrying a ruling — some
metric whose meaning changes for that kind of company. Services currently carries
none, so nothing is excluded for it and every metric stays applicable. The
classification is a statement about the filer, not a licence to drop lines.

And the constraint held. Measured before and after, on the same archive rebuilt
from the same filings:

| | 2.9 | 2.10 |
| --- | --- | --- |
| applicability | 100/120 | **120/120** |
| observations | 97/120 | **97/120** |
| AAPL / MSFT / MU / NVDA collected | 18 | **18** |
| TSM / NU collected | 14 / 10 | **14 / 10** |

**Twenty gates fixed and not one row of data moved.** That is the shape a
metadata change should have, and if the collection numbers had moved it would
have been the first thing to check rather than a result.

---

## 2. What a filer reports that we do not model

2.8 left a question open: *what does a filer report that ST-EVA has no mapping
for?* The ledger could not answer it, and the data said there was something
there — two of the six filers report elements in taxonomies the registry
declares nothing against, and those elements appeared nowhere.

The answer is not two thousand unmapped concepts. `fetch_source_inventory.py`,
one request per issuer:

| | concepts reported |
| --- | --- |
| AAPL | 505 |
| MSFT | 565 |
| MU | 635 |
| NVDA | 644 |
| TSM | 336 |
| NU | 151 |

and across all of them the unmodelled part is **20 concepts in four taxonomies**,
which read like this:

| taxonomy | elements | what they are |
| --- | --- | --- |
| `ffd` | `TtlFeeAmt`, `TtlOfferingAmt`, `TtlOffsetAmt`, `NrrtvMaxAggtOfferingPric` | **filing-fee disclosure** — the mechanics of a securities offering |
| `ecd` | `PeoTotalCompAmt`, `TotalShareholderRtnAmt`, `PeerGroupTotalShareholderRtnAmt` | **executive compensation**, pay-versus-performance |
| `srt` | `StockRepurchaseProgramAuthorizedAmount1`, `…NumberOfSharesAuthorizedToBeRepurchased` | **supplementary narrative tagging** |
| `invest` | `DerivativeNotionalAmount` | **an industry taxonomy** |

**None of them is a financial-statement metric.** No consumer asking about
revenue, assets or equity wanted any of them. So the honest record is a
declaration that these taxonomies are outside the semantic layer, with the reason
— not a decline per concept, and certainly not a coverage gap.

`unmodelled_taxonomies` is a table rather than a name-based rule in the ledger,
for two reasons. A name-based rule has to match a concept to a metric, which is
the "similar label" problem 2.7 spent a phase refusing to solve by name. And a
taxonomy is the unit at which the answer actually exists: these four have nothing
to do with each other and share nothing but being unmodelled. The kind vocabulary
is closed, because "we do not model this" is only useful if a reader can tell
*why not* — a taxonomy of transaction mechanics needs no work, an industry
taxonomy might, and `INDUSTRY_SPECIFIC` says **not yet assessed** rather than out
of scope.

### A filer's XBRL now splits three ways

| | in a modelled taxonomy | in a declared-unmodelled one | **in an unrepresented one** |
| --- | --- | --- | --- |
| AAPL | 505 | 0 | **0** |
| MSFT | 565 | 0 | **0** |
| MU | 631 | 4 | **0** |
| NVDA | 629 | 15 | **0** |
| TSM | 335 | 1 | **0** |
| NU | 151 | 0 | **0** |

**Zero unrepresented, across 2,836 concepts and six issuers.** The third column
is the only one that is work: a concept in a *modelled* taxonomy that no mapping
claims. The second is a decision, and the first is what collection is about.

That is the answer to the question 2.8 could not pose, and it is a better answer
than the question assumed. It is not a coverage hole. It is **20 concepts about
offering mechanics, executive pay and narrative tagging**, and the right response
to every one of them is nothing.

---

## 3. Two tools that did not exist

`fetch_source_inventory.py` — the source inventory, which the archive cannot
derive, with the CIK resolved through `SECProvider` rather than a second copy of
EDGAR's ticker map. The first version fetched the map directly and got a 403,
because the SEC rate-limits unauthenticated callers and the provider already
carries the headers, the retry discipline and a cache for exactly that call. A
tool that resolves issuers should go through the one place that knows how, or it
becomes a second thing to maintain and a second way to fail.

`score_collection_gates.py` — unchanged this round, and it is the reason both
gaps were found. It is the instrument that said "applicability 100/120" and
"something is missing from the coverage story", and both turned out to be real.

---

## 4. Gates, after both gaps

| gate | 2.9 | 2.10 |
| --- | --- | --- |
| definition | 120/120 | 120/120 |
| mapping | 120/120 | 120/120 |
| adoption | 119/120 | 119/120 |
| observations | 97/120 | 97/120 |
| **provenance** | 120/120 | **120/120** |
| **applicability** | 100/120 | **120/120** |
| missingness | 120/120 | 120/120 |
| discoverable | 120/120 | 120/120 |

**Seven of eight gates are now complete, and the eighth — observations — is 97
with every one of the twenty-three failures a metric the archive is *right* not
to have**: a bank reports no capital expenditure element, an IFRS filer has no
diluted share count, and the two debt components hold nothing because the
filers reported 90, 116 and 142 facts which the archive stores under the composed
`debt` metric.

The remaining gate-3 failure is NU's `operating_income`, where the filer reports
no element and the only declared concept is a US-GAAP one. That is a fact about
the filer, and it is the correct answer.

---

## 5. Where the surface stands

```
20 semantic metrics
46 source concepts, 4 taxonomies modelled
47 mappings      19 declines      4 taxonomies declared unmodelled
6 issuers, 5 business models, 2 accounting frameworks
2,836 concepts reported by those filers, 0 of them unrepresented
0 backlog items, anywhere
```

and the two things that are still true and worth saying plainly:

- **The debt components hold nothing because the data was collected**, under the
  composition the mapping declares them a part of. A component of a declared
  composition is not separately stored, and the ledger says so rather than
  leaving two metrics silently empty.
- **NU reports `ifrs-full:GrossProfit` and the metric is still ruled inapplicable
  to it.** A filer tagging an element called GrossProfit does not make "revenue
  less cost of revenue" meaningful for a bank.

---

## 6. The next thing, which is not a gap

The coverage surface is complete for the Core universe. What remains is *scale*,
and the instruments for it already exist: `collection_chain` per run,
`coverage_ledger` per issuer, `score_collection_gates` across a population, and
`fetch_source_inventory` for the one number the archive cannot know.

At ten thousand companies the question those four answer together is:

```
which Core metrics are thin, for which kinds of company, and why
```

and the answer is a sort order for work rather than a percentage. That is a
different kind of work from the last five rounds — there is no ambiguity left to
resolve about what a number means, and the risk is doing a thousand companies
badly rather than getting one right. Which is the better problem, and is where
this stops.
