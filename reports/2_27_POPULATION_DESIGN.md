# 2.27 — Cross-Business-Model Evidence Corpus: population design

Design only. No fetch, no production change, no new applicability rule.

Source of truth: repository at `e45c8df`. Every number below is read from an
archive, a payload directory or a committed artefact already on disk. Nothing was
downloaded, and **no candidate's business model was inferred from its name** —
2.23 measured that this fails: `GOLD` is wholesale jewellery (SIC 50), `AA` is
primary aluminium (33), `NUE` is steel (33), `CIG` is electric services (49).

---

## A. Existing population matrix

89 issuers are known to the repository, from three sources: the 75-issuer
population archive, the five FULL_CORE corpora, and the payloads on disk.

```
model (current SIC mapping)     known   FULL_CORE   both streams   companyfacts only
-----------------------------------------------------------------------------------
MANUFACTURING                      41          16             0                12
BANK                                8           8             8                 0
FINANCE_SERVICES                    9           8             7                 0
MINING                              4           4             4                 0
INSURANCE                           4           4             4                 0
SERVICES                            4           1             0                 0
UNCLASSIFIED                       19           0             0                 0
-----------------------------------------------------------------------------------
TOTAL                              89          41            23                12
```

Three facts in that table do the work.

**1. The largest FULL_CORE stratum has zero issuers usable under the two-stream
contract.** 16 of the 41 FULL_CORE issuers are manufacturing, and not one of them
holds a submissions document — the strided sample and the cross-framework corpus
were fetched `companyfacts`-only. So the biggest stratum has, for every issuer,
no business model and therefore no possible applicability ruling. That is 2.17's
finding generalised: the facts do not stop, the context does, and a stratum built
from one stream has no context at all.

**2. `UNCLASSIFIED` is 19 issuers with zero FULL_CORE evidence**, and it is two
populations, not one:

```
SIC 65, recorded as FINANCE_SERVICES before the 2.16.1 split, now deriving
nothing because no SIC group covers 65:
   EFC 6500 (282 filings)   VAC 6531 (165)   HPP 6500 (152)   MYCB 6500 (77)
   AWCA 6512 (80)   CRESY 6500 (8)   BPYPN 6500 (17)   BNH 6512 (17)

no SIC recorded at all:
   TSCO (167 filings)  FAST (135)  CDZI (118)  GRWG (114)  UEPEO (107)
   AILLP (96)  FIP (63)  NMPWP (15)  TAC (9)  CIG-C (10)  EONGY (0)
```

`REIT` is a member of the vocabulary with no SIC group, so this is not an
oversight to be corrected by a mapping rule — it is a measurement waiting to be
made about what a corpus does with a real filer it cannot classify. And the second
group is a third kind of thing entirely: filers with substantial filing history
and **no classification input whatsoever**.

**3. `SERVICES` has one FULL_CORE issuer out of four known**, and the one is
MSFT. Every other known services filer is uncollected.

### The four FULL_CORE corpora, by what they actually cover

```
corpus                issuers   composition
cross-framework x6        6      AAPL MSFT MU NVDA TSM NU -- 5 of 6 manufacturing
SIC 60 x8                 8      the banks, full submissions
SIC 61-62 x7              7      FINANCE_SERVICES, full submissions
MINING+INSURANCE x8       8      BHP KNF NEM PAAS | HUM PFG PRU SIGI
strided sample x12        12     ALL manufacturing, companyfacts only, no submissions
```

### Axes measured across the 41 FULL_CORE issuers

**Business model** — vocabulary members with *no* SIC group at all, therefore
unreachable by any selection: `OPERATING`, `TECHNOLOGY`, `REIT`. Six are reachable:
`MINING`, `MANUFACTURING`, `BANK`, `FINANCE_SERVICES`, `INSURANCE`, `SERVICES`.

**Filing form** — 9 of 41 hold a 20-F/40-F (`BBAR BHP NU ORXCF PAAS SSYS STMEF
TRSG TSM`), 32 are domestic-only. Four of the nine come from one corpus, so the
foreign-private axis is thinner than the count suggests.

**Historical depth and PIT precision** — declared-date share is bimodal, and the
split is total rather than gradual:

```
0%  (every fact an acceptance instant)   21 issuers
<25%                                     3
25-75%                                    5
100% (every fact a declared date)        12 issuers
```

`CMI` and `KTCC` at 100%, `AAPL`/`MSFT`/`NVDA` at 0%. This is the 2.23 result at
corpus scale: "the source has only a filed date" is a minority on young filers and
a plurality on old ones, so it is an axis with real variance rather than noise.

**Size** — observations per issuer range 145 (`NU`) to 4,344 (`MSFT`). The largest
non-manufacturing filers are `NEM` 3,811 and `HUM` 3,629. Mega-cap *ingestion
shape* remains untested in every non-manufacturing stratum: 2.11 excluded them by
design and nothing since revisited it.

### Axes that genuinely lack discriminative power

| axis | why, from evidence |
| --- | --- |
| `OPERATING`, `TECHNOLOGY` | no SIC group exists; unreachable by selection, so a corpus cannot fill them |
| `REIT` | SIC 65 has no group; 8 filers known, 0 collected |
| foreign/private issuer | 9 of 41, and 4 of those from one corpus |
| historical depth | FULL_CORE filings begin 2009; nothing older is held at full scope |
| mega-cap ingestion shape | absent from every non-manufacturing stratum |
| filer size within a stratum | narrow in the financial strata (`BBAR` 253 vs `NRIM` 2,695) |

---

## B. Manifest — 22 new issuers

Composed against the table above, not by convenience. **No model exceeds 30% of the
post-fetch corpus** (manufacturing goes from 39% to 30%).

### INSURANCE — 5

Every SIC subgroup has exactly one filer. One per subgroup, plus the untested
mega-cap shape.

| ticker | SIC | why |
| --- | --- | --- |
| GNW | 6311 | life insurance; `PRU` alone represents 6311, at the opposite size |
| AFL | 6321 | accident & health; 6321 has one filer (`PFG`) and this is where `operating_income` was reported by `HUM` |
| UNH | 6324 | hospital & medical; `HUM` reported `operating_income` and no other insurer did, so the subgroup earns a second |
| TRV | 6331 | property & casualty mega-cap; **closes the untested mega-cap ingestion shape in a financial stratum** |
| CB | 6331 | second P&C at size; 6331 currently has one small filer (`SIGI`) |

### MINING — 4

SIC 1000 has one filer, 1040 has two, 1400 has one.

| ticker | SIC | why |
| --- | --- | --- |
| RIO | 1000 | **20-F filer and a mega-cap**, in a mining stratum — the only candidate that moves two axes at once |
| FCX | 1000 | second SIC 1000, at size |
| WPM | 1040 | royalty model — a different business inside the same SIC group |
| TECK | 1400 | second SIC 1400, at size |

### Unclassifiable filers — 6

All already known to the repository, none fetched, none selectable by intuition.

| ticker | SIC | why |
| --- | --- | --- |
| EFC | 6500 | 282 held filings, largest of the SIC 65 group |
| VAC | 6531 | 165 held filings |
| HPP | 6500 | 152 held filings |
| AWCA | 6512 | 80 held filings |
| TSCO | *none* | 167 held filings and **no classification input at all** — a third population |
| FAST | *none* | 135 held filings, no classification input |

### SERVICES — 4

One FULL_CORE issuer out of four known. Three of the four are uncollected, and one
is a foreign private issuer, so this stratum moves three axes.

| ticker | SIC | why |
| --- | --- | --- |
| HLT | 7011 | 96 held filings, uncollected |
| MAR | 7011 | 135 held filings, uncollected |
| MLCO | 7011 | **20-F**, the only foreign private issuer available in this stratum |
| CRL | 8731 | from the 2.23 SIC-verified scan; a research services business, not a hotel |

### MANUFACTURING — 3

Deliberately the smallest addition, because this stratum is already the largest.
Chosen for SIC-range coverage, not volume: SIC 20 and SIC 37 have **no filer at
all** in the known set, and SIC 28 is held only at cross-framework scale.

| ticker | SIC | why |
| --- | --- | --- |
| FLO | 2000 | SIC major 20 — no filer anywhere in the repository |
| KURA | 2834 | SIC major 28, communications equipment |
| THRMV | 3714 | SIC major 37, motor vehicles |

### Not new issuers: 18 need the second stream

The 12 strided-sample and 6 cross-framework filers hold `companyfacts` and no
`submissions`. They are not missing evidence, they are missing context, and under
2.26's contract no manifest can substitute for fetching it. **This is a
prerequisite, not an addition**, and it is the single cheapest item in the plan:
18 documents, one request each.

---

## C. What the corpus looks like after the fetch

```
model                now    +new    after    share
MANUFACTURING         16      +3       19       30%
BANK                   8       0        8       13%
FINANCE_SERVICES       8       0        8       13%
MINING                 4      +4        8       13%
INSURANCE              4      +5        9       14%
SERVICES               1      +4        5        8%
UNCLASSIFIED           0      +6        6       10%
                     41     +22       63
```

`FINANCE_SERVICES` gets nothing new: 8 of 9 known filers are already collected at
full scope, which is a measurement in itself — `operating_income` there is 666
observations across six of seven, and adding an eighth would not change what is
knowable about it.

---

## D. Pre-registered measurement definitions

Fixed **before** any document is fetched or read.

### M1 — Denominators, fixed first

- **Universe**: 20 Core metrics × the post-fetch issuer set. Written down before
  the fetch, and not recomputed afterwards.
- **`applicable` is not a denominator term.** 2.26 established that no exclusion
  refuses anything, so every cell is in scope. A denominator that counted only
  "applicable" metrics would have been a way of smuggling a rule back in through
  the arithmetic.
- Per-cell denominators: observations; distinct `period_end` **of the metric's own
  `normal_period_type`** (2.15 showed a single denominator puts every metric near
  0.5 and separates nothing); distinct accessions.

### M2 — Cell vocabulary

The ledger's own, plus the orthogonal markers. Two dimensions, never merged:

```
status              COLLECTED | SOURCE_SILENT | NOT_YET_COLLECTED
                    DELIBERATELY_DECLINED | MAPPED_NO_CURRENT_OBSERVATION
                    NOT_APPLICABLE
orthogonal markers  semantic_conflict      present | absent
                    dimension_ambiguity    count of ingestion_dimension_collisions
                                          rows for this metric x issuer, and the
                                          maximum distinct_values among them
```

`NOT_APPLICABLE` is expected to be **zero everywhere** and that is a result, not a
null: it means the refusal surface stayed empty under a wider population.

### M3–M7 — The axes, each read from the archive

| id | measurement | read from |
| --- | --- | --- |
| M3 | business_model × metric, cells by status | `issuer_business_model`, derived from the SEC's own SIC |
| M4 | filing-form mix | the submissions document's own form list, never a hand-written set |
| M5 | historical depth | `MIN/MAX(filed_at)` and `declared_date_pct` per issuer |
| M6 | size | observations per issuer — **a scale proxy only, explicitly not a coverage-quality measure** |
| M7 | PIT | `available_at_basis` distribution; plus the two invariants |

### M8 — Invariants that must hold before any cell is reported

```
duplicate source_fact_id                          0
observations without an accession                 0
observations without a stored document            0
declared date promoted to an instant              0
eligible before the source said it was public     0
```

### Falsifiable questions, registered in advance

1. **Does any metric's `SOURCE_SILENT` rate vary systematically with business
   model** — beyond what filing-form mix and historical depth already explain?
2. **Is the bimodal declared-date share explained by filing volume, or does it
   track business model?** 21 issuers are all-instant and 12 all-date, and 2.23
   showed the same spread inside one corpus.
3. **Does dimension-ambiguity rate vary by business model**, once measured at
   metric × concept grain? 2.22 found it does *not* concentrate in the disputed
   metric, and that `operating_cash_flow` had six times the affected keys of
   `gross_profit`.
4. **What does the coverage surface do with a filer it cannot classify?** Six
   manifest filers have no model or a SIC no group covers. The expected answer is
   "all twenty applicable, no ruling"; whether that is *right* is a measurement,
   and it must not become a rule.
5. **Is there a metric × model pair where industry intuition predicts silence and
   the evidence shows collection?** This asks the corpus to *refute*, which is the
   only direction 2.21–2.25 ever needed.

### Prohibitions, carried into the run

- **No applicability rule may be created as a result.** Silence is not evidence of
  inapplicability; `SOURCE_SILENT` means the source was asked and had nothing.
- **No registry edit from a business-model intuition.**
- **Observation count is not coverage quality.** Size is M6 and is labelled as a
  proxy.
- **Every denominator fixed before the run** (M1).
- **Dimension ambiguity must be identifiable at metric × concept grain** before
  any matrix is read.

---

## E. Acceptance criteria before the fetch

The fetch may begin only when all of these hold.

1. **Every manifest issuer has a SIC from the SEC's own submissions document**, or
   an explicit `no SIC recorded` entry. Six are expected to be the latter.
2. **No issuer is selected on industry intuition from its name.** 2.23's four
   false positives are the standing evidence for this rule.
3. **The 18 second-stream backfills are scheduled**, because manufacturing is
   otherwise unmeasurable under the two-stream contract.
4. **M1 denominators are written down**, before any document is read.
5. **M8 invariants are instrumented**, so they run on the build rather than being
   checked afterwards.
6. **The refusal surface is confirmed empty**, and the refusal-surface audit is
   green, so nothing in the new corpus can be refused by accident.
7. **This manifest is recorded before the fetch**, so the selection is auditable
   rather than reconstructed afterwards.

### Accepted limitations, stated rather than solved

- **`OPERATING` and `TECHNOLOGY` cannot appear.** No SIC group reaches them, so no
  selection can produce them. Filling them needs a different classification input,
  which is a decision and not this round's.
- **`REIT` will not be classified either**, and the six SIC 65 filers will appear
  as unclassified with full evidence. That is the measurement; classifying them is
  not.
- **Historical depth starts 2009** at full scope. Nothing older is held, so M5's
  depth axis is measured across 2009–2026 only.
- **The manifest is 22, not 30.** The repository's SIC-verified candidate pool
  does not contain enough distinct non-financial names to go further without
  padding manufacturing and violating the no-dominance rule. A SIC discovery pass
  over a wider candidate list would be the way to grow it, and that is a fetch of a
  different kind — not part of this one.

---

## Stopping here

No documents fetched, no production file modified, nothing committed. The next
step is one `companyfacts + submissions + FULL_CORE_METRICS` fetch over this
manifest, after which the M1–M8 definitions run without further adjustment.