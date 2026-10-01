# 2.23 — MINING and INSURANCE: the first rules with filers of their own

2.22 left the semantic question standing and refused to widen the bank sample.
This went and got the population that has been missing since 2.16.1:
`INSURANCE` (SIC 63–64) and `MINING` (SIC 10–14) had **no filer in any archive in
this repository**, so `r_and_d`'s MINING exclusion had never fired and no INSURANCE
rule could even be evaluated.

Eight filers, four of each, full Core scope, zero network:

```
8 issuers  16,351 observations  0 requests  52.1s  54.9 MB
completeness  996 filings · 132 documents · all 16,351 identities distinct
              0 duplicates · 0 without an accession · 0 without a document
pit safety  0 promoted to an instant · basis: ACCEPTANCE_DATETIME 8,279
                                          FILED_AS_OF_DATE   8,072
gates  7 of 8 at 160/160 · applicability 160/160 · observations 110/160
```

**`r_and_d → NOT_APPLICABLE for MINING` fired for the first time in this project's
history, and it is contradicted.**

---

## A. The finding

```
ticker   model      r_and_d status      obs    conflict
BHP      MINING     NOT_APPLICABLE        0
KNF      MINING     NOT_APPLICABLE        0
NEM      MINING     NOT_APPLICABLE      236     EVIDENCE_HELD_FOR_INAPPLICABLE_METRIC
PAAS     MINING     NOT_APPLICABLE        0
HUM      INSURANCE  SOURCE_SILENT         0
PFG      INSURANCE  SOURCE_SILENT         0
PRU      INSURANCE  SOURCE_SILENT         0
SIGI     INSURANCE  SOURCE_SILENT         0
```

**NEM (Newmont, SIC 1040 Gold and Silver Ores) tags
`us-gaap:ResearchAndDevelopmentExpense` in 236 observations.** A gold miner
reporting research and development is not a contradiction of the word "mining" —
it is what the word "mining" has meant since gold and silver exploration became
capitalised decades ago. The rule is right for three of four miners and wrong for
the fourth, and the fourth is the one that makes the class interesting.

The conflict marker fired on its own, naming the concept. Nothing about this needed
a special case: the rule fired, the source contradicted it, and both facts are in
one ledger row.

### Two for two

Every applicability rule this project has been able to test against real filers in
its own target class has been contradicted by at least one of them:

| rule | target class | filers | contradicted by |
| --- | --- | --- | --- |
| `gross_profit` NOT_APPLICABLE | BANK | 8 | NRIM, 22 obs, `us-gaap:GrossProfit` |
| `r_and_d` NOT_APPLICABLE | MINING | 4 | NEM, 236 obs, `us-gaap:ResearchAndDevelopmentExpense` |

Two rules, two independent model classes, two contradictions. That is a small
sample and it does not prove a general law — but it is enough to say that **a rule
authored from a category intuition and never checked against a filer in the class
should be assumed wrong until the filers say otherwise.** `r_and_d`'s exclusion
was written in 2.7 and survived untouched through every round since, because no
miner had ever been in an archive to contradict it.

---

## B. The INSURANCE baseline, which did not exist before

No rule names `INSURANCE` — that is the gap the 2.16.1 marker test guards. What
was missing was the evidence needed to write one, and four filers spanning four
SIC subgroups now supply it:

```
              BHP   KNF   NEM   PAAS  │  HUM   PFG   PRU   SIGI     (observations held)
revenue        33    48   141    18  │  391   309   329   255
eps_diluted    33    45   331    18  │  321   309   273   303
operating_cash_flow
               33    31   164    18  │  160    77   155    92
interest_expense
               39    15    54    31  │  207     0    43   215
gross_profit    0    45    98    18  │    0     0     0     0     <-- 0 of 4
r_and_d         0     0   236     0  │    0     0     0     0     <-- 0 of 4
operating_income
                0    45     0     0  │  233     0     0     0
sga             0    45   236    18  │  233     0   155     0
capex           0    31   208     0  │  165     0     0    73
debt            0    72   276    26  │  144     0   138     0
```

Four filers is a thin basis for a rule and this does not write one. What it gives:

- **`gross_profit` is 0 of 4 insurers** — the same silence as 0 of 6 banks, for a
  different reason: an insurer's income statement is built from premiums and
  benefits, and there is no cost-of-goods subtotal to take a margin from. Two
  independent industries reaching the same silence for different reasons is a
  better argument than either alone.
- **`r_and_d` is 0 of 4 insurers**, which is *evidence* for an INSURANCE exclusion
  rather than the absence of evidence that `INSURANCE` currently is.
- **`operating_income` is reported by HUM and no other insurer** — a hospital and
  medical service plan does have an operating income line; a life insurer does
  not. This is the clearest example yet of why an industry bucket is too coarse:
  HUM and PRU are both `INSURANCE` and they differ on this metric.
- **PFG reports almost nothing**: revenue, EPS and operating cash flow only, and
  zero on interest expense, operating income, SG&A, capex and debt. One filer
  saying less than its peers is a coverage finding about the registry, not about
  the filer.

---

## C. A point-in-time finding that only longer histories show

```
bank corpus (8 filers)      ACCEPTANCE_DATETIME 11,022   FILED_AS_OF_DATE   152    1.4%
this corpus   (8 filers)    ACCEPTANCE_DATETIME  8,279   FILED_AS_OF_DATE 8,072   49.4%
```

**Half of this corpus falls back to a declared date.** BHP and KNF are decades-old
filers whose early filings sit outside the submissions window entirely, and the
submissions endpoint only carries roughly the most recent thousand filings per
issuer.

So the one-day allowance `DECLARED_DATE_LAG_DAYS = 1` is not an edge case that
applies to a rounding error of the corpus — **on older filers it governs half the
evidence**, and on a corpus that reaches back decades it would govern more. That is
a reason to keep the allowance conservative, and a reason not to describe it as a
detail.

It also means the two corpora are not directly comparable on time coverage, and a
coverage figure drawn across them without saying so would be misleading.

---

## D. Two corrections this round made

**My own error, corrected in 2.22.** That report said removing the `gross_profit`
rule would leave six banks with "a retrieval backlog growing every night". Wrong,
and wrong in the direction this whole system exists to prevent: those banks would
read

```
not ruled inapplicable  +  source asked  +  nothing returned  =  SOURCE_SILENT
```

which is **handled, source silent** — a coverage state, not undone work.
`NOT_YET_COLLECTED` is the only status that means work to do, and these would not
be it. There is real recurring cost, but it belongs to ingestion scheduling, not to
coverage.

**The ticker map could not come from the reference archive.** These eight filers
exist in no archive here beforehand, and `fullscope_bulk.py` correctly refused to
proceed rather than guess a CIK. The map now comes from the payload's own
`tickers.json`, which `fetch_source_inventory.py` writes from the SEC's company
ticker map through the same provider ingestion resolves through. Nothing is
inferred from a company name.

Also added, because eight filers in no archive needed it: **`--forms submissions`**,
reading each filer's form set from the submissions document the run already holds.
A hand-written periodic list would have been a form-policy assumption in a result
whose whole value is that nothing was assumed.

And a discovery note worth keeping: the candidate pool was chosen for *industry*
coverage and the SIC was read from the SEC's own submissions — which is the only
reason the SIC is trustworthy here. Four guesses that looked like miners were not:
`GOLD` is wholesale jewellery (SIC 50), `AA` is primary aluminium (33), `NUE` is
steel (33), `CIG` is electric services (49).

---

## E. The reframing that made this possible

2.22's collisions were a **source representation property**, not a metric
exception, and this round made that structural. `sources` had **no row at all** in
any evidence archive — documents carried a `provider` string and nothing described
what that provider *is*. So a question about the shape of the source's facts had
nowhere to be answered except as a per-metric exception.

It is now declared once, where it belongs:

```
sources.retains_dimensions = 'AGGREGATE'
sources.aggregation_note   = 'Facts are aggregated across dimension members...'
```

with the chain it belongs to:

```
source fact
    ↓
does the endpoint retain the dimensional axis?     AGGREGATE — it does not
    ↓
ambiguity may attach, and is recorded per event
```

That is what makes `ingestion_dimension_collisions` readable as **evidence** for a
declared property rather than as a list of metrics that are odd — which matters
here, because `operating_cash_flow` has six times more affected keys than the
`gross_profit` the argument was about.

---

## F. State

| | |
| --- | --- |
| full suite | **639 passed**, 74 skipped, 713 run — unchanged |
| production change | `sec_ingest` (source registration), `sqlite_archive` (declaration columns), migration `0014` |
| new population | 4 MINING + 4 INSURANCE, none of which existed in any archive |
| archives | `snapshot-ins-min.sqlite` built; bank archive rebuilt and equivalence re-verified **11,174 / 11,174** |
| sealed snapshot | untouched; all five pre-existing archives open under the edited migration |
| network | 8 companyfacts + 8 submissions + a candidate SIC scan through the provider |

---

## G. Where this leaves the semantic work

```
BANK -> gross_profit NOT_APPLICABLE        REFUTED   (NRIM)
MINING -> r_and_d NOT_APPLICABLE           REFUTED   (NEM, 236 observations)
INSURANCE -> ?                             no rule; baseline now exists
```

Two rules, two classes, two contradictions — which is the answer to the question
2.17 posed. It is no longer open whether a semantic rule can survive real source
evidence; the answer is that neither of the two tested could.

**And the direction of the fix is now empirically supported rather than argued.**
2.21 offered three options for `gross_profit` and leaned toward "no universal rule,
possibly conditional". The evidence now says something stronger: **conditionality
is probably unnecessary, because the correct response to a refuted rule is to have
no rule.** `SOURCE_SILENT` already says what a filer did not report, and it is not
work to do. A filer that genuinely reports gross profit gets it collected; one
that does not is asked again when the source has something new. That is the
system's existing behaviour and it needs no new state.

**Next, and it is a decision rather than a measurement:** apply that to both
refuted rules. Removing them is the smallest change that makes the archive agree
with the evidence, and it is now supported by two independent counterexamples
rather than one. The counter-argument — six banks and three insurers that would
be asked again each cycle — is a scheduling cost, not a coverage debt, and the
`--forms submissions` work above is the shape of how that cost would be managed.

What should *not* happen is a third rule being written from the same intuition and
waiting for a filer to contradict it. If a narrower rule is wanted, it needs
evidence for the narrower claim.