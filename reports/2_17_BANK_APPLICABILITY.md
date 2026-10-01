# 2.17 — Eight bank filers, and what the source says about the rules

2.16.1 left `BANK` reachable, populated with eight filers, with two applicability
rules already written against it. This runs the full Core scope over them and asks
the question 2.16.1 could not: **does the ruling materialise, and does the source
agree with it?**

2.16.1's obstacle was that absence is ambiguous — the 75-issuer archive holds eight
metrics and the ruling speaks about two that are not among them. That is solvable
without guessing: read the **raw `companyfacts` documents** for the concepts the
registry maps to the refused metrics, independently of the semantic layer. If a
bank tags a concept ST-EVA refuses, the refusal is contradicted by the source and
no archive is needed to see it.

Eight SIC 60 filers fetched, one request each, `fullscope_bulk.py` unchanged.

```
8 issuers  11,174 observations  0 requests  34.3s  37.6 MB
completeness  389 filings · 105 documents · 11,174 observations, all distinct
              0 duplicates · 0 without an accession · 0 without a document
pit safety  0 promoted to an instant, 0 of 5,447 eligible too early
gates  7 of 8 at 160/160; applicability 0/160
```

---

## A. The answer to the question: no, it cannot materialise on the bulk path

**`applicability` reads 0/160, and the reason is structural.** `companyfacts`
carries no SIC, so no business model is recorded, so no applicability rule fires.
The rule is not wrong here — it is **unreachable**.

That is why `gross_profit` comes out `COLLECTED` for two of the eight banks rather
than `NOT_APPLICABLE`. The refusal is available on the submissions/API path and
absent on the bulk path, which is the only path that scales.

```
gross_profit     COLLECTED 2   SOURCE_SILENT 6
operating_income DELIBERATELY_DECLINED 8
```

2.15 established that a missing `submissions` payload removes a refusal rather
than adding data. This is the same fact again, now against a rule that exists,
is populated, and would otherwise fire — so **applicability is currently
untestable at scale**, and no amount of collecting banks will change that.

---

## B. What the source says, read before the archive

The registry maps `gross_profit` to `ifrs-full:GrossProfit` and
`us-gaap:GrossProfit`, and `operating_income` to `us-gaap:OperatingIncomeLoss`.
Read straight out of the eight documents:

| metric | banks tagging a mapped concept | verdict |
| --- | --- | --- |
| `operating_income` | **0 of 8** | the refusal is **supported** |
| `gross_profit` | **2 of 8** | the refusal is **contradicted** |

Both cases are real reported lines, not artefacts:

- **NRIM** (`us-gaap:GrossProfit`, 22 rows) files a clean quarterly and annual
  series in USD alongside its 10-K and 10-Q — 2024 Q1 through 2026 Q2, restated
  comparatives included.
- **BBAR** (`ifrs-full:GrossProfit`, 18 rows) files it in **ARS** units on a 20-F,
  with the same period carrying different values across filing years — a
  restatement or a flattened dimension member, and worth knowing which.

So `gross_profit → NOT_APPLICABLE for BANK` asserts that a bank never reports a
gross profit subtotal, and **two of eight do**. The rule is too broad.

Whether to narrow it, keep it and accept the exclusion, or make applicability a
prior rather than a refusal is a **semantic decision**, and it is not taken here.
What is decided is which way the evidence points, which is what a corpus is for.

---

## C. Two rules the evidence would justify, and one that is a registry gap

The same read produced the opposite result twice, and a gap:

**`r_and_d` — `SOURCE_SILENT` for 8 of 8.** No bank reports research and
development. Compare `INSURANCE`, where no filer exists to say anything: here the
evidence is unanimous and an applicability rule is warranted by it.

**`sga` — `SOURCE_SILENT` for 7 of 8.** Banks do not report a selling, general
and administrative line. Same shape, and it is the metric a reader would most
expect a bank not to have.

**`revenue` — `COLLECTED` for only 3 of 8, `DELIBERATELY_DECLINED` for 5.** Banks
report net interest income rather than a revenue subtotal. A third candidate, and
the one where the registry has already declined a concept, so it needs the decline
revisited before it needs a new rule.

**`debt` — `SOURCE_SILENT` for 8 of 8, and it is not the filers.** The registry
maps four concepts:

```
us-gaap:LongTermDebtCurrent   us-gaap:LongTermDebtNoncurrent
ifrs-full:CurrentPortionOfLongtermBorrowings   ifrs-full:LongtermBorrowings
```

**0 of 8 banks tag any of them.** What they tag instead:

```
us-gaap:LongTermDebt                                            6 of 8
us-gaap:ShortTermBorrowings                                     4 of 8
us-gaap:OtherBorrowings                                         3 of 8
us-gaap:SubordinatedDebt                                        2 of 8
us-gaap:LongTermDebtAndCapitalLeaseObligations                  1 of 8
us-gaap:DebtLongtermAndShorttermCombinedAmount                  1 of 8
```

`debt` is declared as a composition of current and non-current, and the registry
already records why: no single standard concept declares total debt. **A bank that
reports one unsplit `LongTermDebt` is reporting a total, not the composition**, so
mapping it to `debt` would be a different claim rather than a missing one.

That also explains 2.15's `debt` at a median filing ratio of 0.34: manufacturers
that tag only one side of the split get partial coverage, and filers that report a
combined total get none. One cause, two populations.

---

## D. The positive control

The pipeline is not refusing everything financial, which is what would make the
rest of this unremarkable. `interest_expense` is `COLLECTED` for **8 of 8** at a
median filing ratio of 0.93, and `assets`, `equity`, `cash`, `income_tax`,
`operating_cash_flow` and `eps_diluted` are 8 of 8 as well. A bank archive that
collected only what suits a bank would show `SOURCE_SILENT` across the board; this
one collected 11,174 observations.

---

## E. Where this leaves the two rules 2.7 wrote

`FINANCIAL = (BANK, FINANCE_SERVICES)` and the exclusions hanging off it were
written in 2.7 from a filer that could not be recorded. They now have evidence:

```
gross_profit     refused for BANK and FINANCE_SERVICES
                 2 of 8 banks report it            -> too broad
operating_income refused for BANK and FINANCE_SERVICES
                 0 of 8 report it                  -> supported
```

And the two candidates the evidence raises, which have no rule and no filer class
that can apply one:

```
r_and_d   8 of 8 banks silent   -> evidence exists, rule does not
sga       7 of 8 banks silent   -> evidence exists, rule does not
```

`r_and_d`'s MINING exclusion exists and has never fired, because no SIC 10–14
filer exists in any archive. **Three states now, all measured:** a rule with
evidence against it, a rule with evidence for it, and a rule with no filer to
test it on.

---

## F. State

| | |
| --- | --- |
| full suite | **620 passed**, 74 skipped, 694 run — unchanged |
| production files changed | none |
| fetch | 8 companyfacts documents, one request each, plus the ticker map |
| instrument | `fullscope_bulk.py`, unchanged, third issuer set |
| archives | `snapshot-banks.sqlite` (37.6 MB), none modified in place |
| committed artefact | `harness/banks-217.json` |

Nothing here changed code, because nothing here was a defect. Four of the five
findings are semantic decisions about what a bank is, and the fifth is a
consequence of the bulk path not carrying SIC — which is the same missing
`submissions` payload recorded in 2.15 and still the largest structural gap in the
project.

The cheapest next measurement is not more rules. It is the one measurement that
would make applicability testable at all: **does `submissions` ship with the bulk
bootstrap?** A single `company_tickers`-free fetch of eight submissions documents
would answer it, and every applicability rule in the registry depends on the
answer.
