# ST-EVA Historical P/E Engine — Contract Design

**Status:** DESIGN ARTIFACT — not implementation, not production.
**Scope:** Interface, semantics, invariants and replay guarantees only.
**Methodology baseline:** `docs/ADR-HISTORICAL-PE-METHODOLOGY.md` (APPROVED / FROZEN, as amended by Amendment 1, Decisions 10–14).
**Evidence base:** `experiments/aapl-historical-pe-poc/` — first POC, Q4 evidence study, Amendment 1 verification (31/31 TTM).
**File:** `docs/methodology/CONTRACT-HISTORICAL-PE.md`

Nothing in this document changes the ADR, ST-EVA Core, the SEC provider, the
admission or replay contracts, the web app, or the POC outputs. It defines what
a Historical P/E engine must consume and must produce, so that an implementation
written later has no freedom to invent semantics.

---

## A. Contract design document

### A.1 What this contract is for

ST-EVA needs a historical reference multiple for reverse valuation. The ADR
freezes *how* the number must be built. This document freezes *what the engine
is handed and what it hands back*, so that two implementations of the same ADR
cannot disagree, and so that a reader can reconstruct any published value from
the recorded inputs alone.

The contract has four obligations:

1. **Consume** quarter EPS evidence from more than one evidence class, without
   letting the class difference leak into the accounting metric.
2. **Resolve** each piece of evidence to a point-in-time usable date, so that a
   historical date can only ever see evidence that existed at that date.
3. **Compose** four consecutive fiscal quarters into a TTM figure, anchored on
   fiscal identity rather than on whatever records happen to be in hand.
4. **Emit** an observation whose every number is traceable to a named document,
   a named instant, a methodology version and a content hash.

### A.2 Design lineage from the POC

Each clause below exists because the AAPL work found something. The three that
changed the design most:

| POC finding | Contract consequence |
| --- | --- |
| Q4 diluted EPS existed as **document text** in a furnished 8-K exhibit while the XBRL fact did not exist | Two evidence classes (§B); `XBRL fact unavailable` is not an eligibility state (§D.4) |
| The first fiscal-window walk-back mislabelled the open fiscal year and published a **455-day** TTM window at three dates | Fiscal identity is derived per quarter from the issuer's own declaration, never from a list of 10-K period ends (§E.1, Invariant F-3) |
| Disabling the furnished path reproduced the prior POC on **31 of 31** dates byte for byte | Negative-path conformance is a contract requirement, not a nice-to-have (§I.3) |

### A.3 Vocabulary layering

This contract does **not** redefine Core's `Observation`, `Evidence`,
`ValidationStatus`, `Refusal`, `Unit`, `SourceType`, `AvailabilityBasis` or
`PRECISION_INSTANT`. Those are read as they exist. Historical P/E adds a thin
layer above them:

```
Core Observation / Evidence      (existing, unchanged)
        |
        v
QuarterEpsEvidence               (B — what the engine consumes)
        |
        v
PIT resolution                   (E — evidence -> usable_date -> eligibility)
        |
        v
FiscalQuarterWindow              (E — four consecutive fiscal quarters)
        |
        v
HistoricalPeObservation          (C — what the engine emits)
```

`QuarterEpsEvidence` is a *view* over a Core `Observation`, not a replacement.
The Core observation remains the record of what the source said; the evidence
view adds the fiscal and classification semantics the P/E builder needs and that
a generic metric record has no place for.

---

## B. Input schema

### B.1 `QuarterEpsEvidence`

One instance per (fiscal quarter, source document) pair. A quarter reported by
three filings is three evidence instances, not one.

```json
{
  "evidence_id": "sha256:<hash of canonical form>",
  "issuer_id": "CIK0000320193",

  "evidence_class": "filed",
  "form": "10-Q",
  "sec_item": null,
  "accession": "0000320193-25-000057",
  "source_document": null,
  "source_url": "https://data.sec.gov/api/xbrl/companyconcept/CIK0000320193/us-gaap/EarningsPerShareDiluted.json",

  "acceptance_datetime": "2025-05-02T06:00:46-04:00",
  "acceptance_source": "EDGAR_SGML_HEADER_ACCEPTANCE_DATETIME",
  "acceptance_precision": "INSTANT",
  "legal_status_note": null,

  "period_declaration": "XBRL_FACT_PERIOD",
  "period_start": "2024-12-29",
  "period_end": "2025-03-29",
  "duration_days": 91,
  "fiscal_year": 2025,
  "fiscal_quarter": 2,
  "fiscal_position_source": "DERIVED_FROM_ISSUER_FY_END",

  "metric": "GAAP_DILUTED_EPS",
  "value": 1.65,
  "unit": "per_share",
  "currency": "USD",

  "audit_status": "unaudited_reviewed",
  "stated_directly": true,
  "derivation": "directly tagged quarter-length XBRL fact",

  "content_sha256": "d58cd0fce2baed8be20b7b6587917b03bb46c08fc0b527d53a4867cab9317acf",
  "retrieved_from": "frozen_raw_input_set",

  "core_observation_ref": "obs-eps-diluted-0001"
}
```

### B.2 Field semantics

#### Evidence class

```
evidence_class ∈ { "filed", "furnished" }
```

| Value | Meaning | Forms |
| --- | --- | --- |
| `filed` | Submitted under §13(a) of the Exchange Act; financial statements are filed statements | 10-K, 10-Q, 10-K/A |
| `furnished` | Submitted under Item 2.02 of Form 8-K and expressly not deemed filed for §18 purposes | 8-K + EX-99.1 earnings release |

Required field `legal_status_note`: when `evidence_class == "furnished"`, this
**must** be populated with the document's own Section 18 language. The AAPL
POC read it from the 8-K body and it is part of the evidence's identity, not a
commentary: an implementation that cannot quote it does not have the evidence.

#### Fiscal position

```
fiscal_year: int          fiscal_quarter: int ∈ {1,2,3,4}
fiscal_position_source ∈ { "ISSUER_STATED", "DERIVED_FROM_ISSUER_FY_END" }
```

`fiscal_position_source` is mandatory and is the answer to the 455-day bug. See
§E.1.

#### Period declaration

```
period_declaration ∈ {
    "XBRL_FACT_PERIOD",            # start and end dates both tagged
    "XBRL_FACT_END_ONLY",          # no start; period class asserted separately
    "STATEMENT_COLUMN_LABEL",      # e.g. "Three Months Ended 2025-09-27"
    "UNSTATED"                     # not admissible for TTM
}
```

This is the load-bearing field for furnished evidence. A furnished exhibit does
not tag XBRL; it presents a **column** whose header names the period. Therefore:

- `period_start` may be `null` for `STATEMENT_COLUMN_LABEL` evidence.
- The period *class* (quarter-length, not cumulative) is asserted by the column
  label itself and must be recorded verbatim in `derivation`.
- `duration_days` may be `null` when the source does not state a start date.
- `period_declaration == "UNSTATED"` evidence is **inadmissible** for
  `TTM_GAAP_DILUTED_PE`. It may be retained for audit but must never contribute.

A column label of `Twelve Months Ended` on a `STATEMENT_COLUMN_LABEL` evidence
instance is an eligibility failure (§G.2), not a quarter.

#### B.2.1 Genericization Note: Furnished Evidence Column Semantics

The MSFT validation (Finding C.1) demonstrated that AAPL's earnings-release
exhibit layout is **not** a universal template. An implementation that
pattern-matches on AAPL's fixed four-column structure with narrative
corroboration will silently lose quarters on other issuers.

The following are **prohibited** as parser requirements for
`STATEMENT_COLUMN_LABEL` evidence:

- A fixed number of statement columns (AAPL shows four; MSFT Q1 shows two).
- The presence of a cumulative column (`Twelve Months Ended`, `Nine Months
  Ended`, etc.) alongside the quarter column.
- A narrative corroboration sentence repeating the quarter EPS figure.
- Any issuer-specific visual layout, PDF/HTML structure, or formatting
  convention.

**What the contract requires instead:**

1. **Column-header semantics are the eligibility signal.** The column header
   must explicitly name the target period (e.g. `Three Months Ended
   2025-09-30`). That text, recorded verbatim in `derivation`, establishes
   quarter-specificity.

2. **`period_start` and `duration_days` may be `null`.** §B.2 already permits
   this for `STATEMENT_COLUMN_LABEL`. Missing start date or duration does not
   make the evidence inadmissible when the column header unambiguously declares
   a quarter-length period and the period end date is stated.

3. **`period_end` must be present and match the target fiscal quarter
   end.** This is the anchor; it is compared against the derived fiscal
   calendar (§E.1).

4. **The diluted EPS value must be directly stated in that column.** Not
   computed, not differenced, not carried from a cumulative column.

5. **Evidence class, legal status, and audit status are determined by the
   document type and item code (Form 8-K Item 2.02), not by layout.** The
   `legal_status_note` (§B.2) must be extracted from the 8-K body text.

AAPL's five Q4 exhibits and MSFT's twenty-three Item 2.02 exhibits are
**examples only**. They illustrate the range of column structures the contract
must accommodate. The parser contract is the semantic criteria above, not either
issuer's layout.

#### Metric classification

```
metric          ∈ { "GAAP_DILUTED_EPS", "GAAP_BASIC_EPS", "NON_GAAP_DILUTED_EPS", "NON_GAAP_BASIC_EPS", ... }
```

`TTM_GAAP_DILUTED_PE` consumes **only** `GAAP_DILUTED_EPS`. Any other metric on
the instance is a refusal (§G.1), not a silent exclusion. This is why the metric
is a closed field on the evidence rather than free text: an implementation
cannot route around it.

An issuer document that quotes both a GAAP and a non-GAAP EPS in the same
statement produces **two** evidence instances. The non-GAAP one is constructed so
that the exclusion is visible in the output rather than inferred from silence.

#### Audit status

```
audit_status ∈ { "audited", "unaudited_reviewed", "unaudited" }
```

Three values, not a boolean. `unaudited` is not a synonym for `audited: false`;
the distinction between "reviewed" and "not reviewed" is exactly the distinction
that made the AAPL mixed-source window auditable.

| Source | audit_status |
| --- | --- |
| 10-K financial statements | `audited` |
| 10-Q interim statements | `unaudited_reviewed` |
| 8-K EX-99.1 earnings release | `unaudited` |

`audit_status == "audited"` is a **necessary** condition for annual evidence
(§E.6) and is **not** a condition for quarterly evidence. Per ADR Decision 11,
unaudited does not by itself justify a refusal.

#### Acceptance and publication time

```
acceptance_datetime: str          # ISO-8601 with explicit offset, or null
acceptance_source: str            # see below
acceptance_precision: "INSTANT" | "DATE"
publication_datetime: str | null  # non-SEC sources only
pit_anchor_datetime: str          # the one field the resolver consumes
```

`acceptance_source` is an enumerated provenance string, never a bare "SEC":

```
"EDGAR_SGML_HEADER_ACCEPTANCE_DATETIME"   # authoritative; Eastern Time
"EDGAR_FILED_AS_OF_DATE"                  # date only, no time of day
"NON_SEC_PUBLICATION_INSTANT"             # issuer IR, press release
"UNDECLARED"                              # precision NONE; inadmissible for PIT
```

Per ADR Decision 12, the submissions API `acceptanceDateTime` is **not** an
acceptable `acceptance_source`: it carries a `Z` suffix that does not denote UTC.
An implementation that records it is non-conformant regardless of the values it
produces.

`pit_anchor_datetime` exists so the resolver has exactly one field to read. When
`acceptance_precision == "DATE"` there is no time of day; the resolver then
applies the conservative same-day reading and the observation records
`usable_date_precision: "DATE"`.

### B.3 `HistoricalPriceEvidence`

Interface only. No provider is chosen, and none may be implied.

```json
{
  "price_evidence_id": "sha256:<hash>",
  "issuer_id": "CIK0000320193",
  "instrument_id": "AAPL",
  "price_date": "2020-07-31",
  "close": 425.04,
  "currency": "USD",
  "unit": "currency",
  "price_source": "Yahoo Finance chart API v8 close",
  "price_source_url": "https://query1.finance.yahoo.com/v8/finance/chart/AAPL?...",
  "vendor_adjustment_note": "vendor series is split-adjusted for all splits in the window",
  "corporate_action_provenance": [
    { "ex_date": "2020-08-31", "split_ratio": "4:1", "source": "vendor_event_stream" }
  ],
  "accounting_basis": "as_traded",
  "content_sha256": "..."
}
```

`accounting_basis` is the field that matters and its vocabulary is deliberately
narrow in this document:

```
accounting_basis ∈ { "as_traded", "split_adjusted" }
```

The POC paired `as_traded` price with `as_filed` EPS and obtained a coherent
ratio without any Corporate Action schema. That is an observation about one
issuer and one split, not a schema decision. The contract therefore requires
only that `accounting_basis` be stated and that price basis and EPS basis agree
(Invariant F-6). **How** to restate a price into a chosen basis remains OPEN
(§K.4); this contract does not define a Corporate Action schema and does not
imply one exists.

---

## C. Output schema

### C.1 `HistoricalPeObservation`

One instance per (issuer, evaluation_date, metric_id).

```json
{
  "observation_id": "histpe-TTM_GAAP_DILUTED_PE-AAPL-2025-10-31",
  "issuer_id": "CIK0000320193",
  "instrument_id": "AAPL",
  "metric_id": "TTM_GAAP_DILUTED_PE",

  "evaluation_date": "2025-10-31",
  "evaluation_date_is_trading_day": true,

  "status": "AVAILABLE",
  "reason_code": null,
  "reason_detail": null,

  "value": 36.19410911876673,
  "unit": "multiple",
  "currency": null,

  "eps_state": {
    "status": "AVAILABLE",
    "window_anchor": { "fiscal_year": 2025, "fiscal_quarter": 4 },
    "quarter_denominator": 7.47,
    "quarters_required": 4,
    "quarters_present": 4,
    "missing_quarters": [],
    "components": [ "... four QuarterEpsEvidence summaries ... " ],
    "component_summary": {
      "evidence_classes_present": ["filed", "furnished"],
      "forms_present": ["10-Q", "8-K"],
      "accessions": [
        "0000320193-25-000008", "0000320193-25-000057",
        "0000320193-25-000073", "0000320193-25-000077"
      ],
      "audit_statuses_present": ["unaudited_reviewed", "unaudited"],
      "mixed_class_window": true,
      "fy_minus_ytd_used": false
    }
  },

  "price_state": {
    "status": "AVAILABLE",
    "price_date": "2025-10-31",
    "close": 270.37,
    "currency": "USD",
    "accounting_basis": "as_traded",
    "price_evidence_id": "sha256:...",
    "basis_alignment": "aligned"
  },

  "pe_state": {
    "status": "AVAILABLE",
    "numerator_source": "price_state",
    "denominator_source": "eps_state.quarter_denominator",
    "formula": "close / quarter_denominator"
  },

  "source_lineage": {
    "evidence_ids": [ "... four evidence ids ..." ],
    "price_evidence_ids": [ "sha256:..." ],
    "refusals": []
  },

  "methodology": "docs/ADR-HISTORICAL-PE-METHODOLOGY.md",
  "methodology_amendment": "Amendment 1 (2026-10-07), Decisions 10-14",
  "logic_version": "historical-pe/<version>",
  "input_set_id": "sha256:<hash of the frozen input set>",
  "content_hash": "sha256:<hash of the canonical form of this record>",

  "replay_identity": {
    "input_set_id": "sha256:...",
    "logic_version": "historical-pe/<version>",
    "deterministic": true
  }
}
```

### C.2 The three metric ids

```
metric_id ∈ {
    "TTM_GAAP_DILUTED_PE",
    "ANNUAL_GAAP_DILUTED_PE",
    "CURRENT_PE"
}
```

**`CURRENT_PE` is not an evaluation-date observation.** It has exactly one
instance per run, at the run instant, and it is structurally incapable of
entering a historical distribution. The contract expresses this by requiring
`CURRENT_PE` observations to carry `role: "current_snapshot"` and by refusing to
aggregate them into any window (§G.5).

**Annual never substitutes for TTM.** `ANNUAL_GAAP_DILUTED_PE` may be present
while `TTM_GAAP_DILUTED_PE` is `UNAVAILABLE` at the same evaluation date. That
combination is expected and normal, not an inconsistency. An implementation that
fills `TTM_GAAP_DILUTED_PE` from annual evidence is in breach of ADR §3.B and
Invariant F-4.

### C.3 `Annual` evidence restriction

`ANNUAL_GAAP_DILUTED_PE` requires an annual EPS evidence instance with:

```
metric                == "GAAP_DILUTED_EPS"
evidence_class        == "filed"
form                  ∈ { "10-K", "10-K/A" }
audit_status          == "audited"
period_declaration    == "XBRL_FACT_PERIOD"
duration_days         ∈ [YEAR_MIN_DAYS, YEAR_MAX_DAYS]
```

A furnished annual or quarterly figure may never satisfy this (§E.6). This is
ADR Decision 11 and it is the one asymmetry between the two metrics.

---

## D. State / status definitions

### D.1 The three states

```
status ∈ { "AVAILABLE", "UNAVAILABLE", "REFUSED" }
```

| State | Meaning | Value | Reason code |
| --- | --- | --- | --- |
| `AVAILABLE` | Produced from admissible evidence | non-null | null |
| `UNAVAILABLE` | Methodology admits it but no qualifying evidence exists at this date | `null` | required |
| `REFUSED` | An input failed admission; the crossing was not attempted | `null` | required, plus a `Refusal` object |

The distinction is not cosmetic. `UNAVAILABLE` is a statement about *the
evidence available at a date*; `REFUSED` is a statement about *an admission
decision on an input*. The AAPL POC's original `REASON_MISSING_Q4_EPS` was an
`UNAVAILABLE` that was simply wrong, because the evidence existed and had not
been looked for in the right place. A wrong `UNAVAILABLE` is worse than a
`REFUSED`, because it asserts a fact about the world.

### D.2 Reason codes

The ADR reason-code enumeration is **closed** and this contract adds nothing to
it. Existing codes are re-used with tightened preconditions:

| Reason code | Precondition this contract imposes |
| --- | --- |
| `REASON_MISSING_PRICE` | No `HistoricalPriceEvidence` at the evaluation date |
| `REASON_MISSING_Q4_EPS` | The required window contains a fiscal Q4 position with **no** admissible evidence, after **all** evidence classes have been enumerated |
| `REASON_INSUFFICIENT_QUARTERS` | The window cannot be filled for a reason other than a missing Q4 |
| `REASON_NON_POSITIVE_EPS` | Quarter denominator $\le 0$ |
| `REASON_CORPORATE_ACTION_UNRESOLVED` | Price and EPS accounting bases cannot be reconciled and no provenance for the difference exists |
| `REASON_INSUFFICIENT_OBSERVATIONS` | Emitted only by the sufficiency gate (§K.1); not by the per-date builder |
| `REASON_INSUFFICIENT_TIME_SPAN` | Emitted only by the sufficiency gate (§K.1) |

`REASON_MISSING_Q4_EPS` carries the ADR's Decision 13 precondition as a hard
requirement of this contract: an implementation **must** enumerate both evidence
classes before emitting it. This is the code whose misuse produced the original
finding, so the contract makes the correct usage the only one available.

### D.3 `REFUSED` and Core refusal labels

`REFUSED` carries a Core `Refusal` (from `evidence_valuation_boundary`), whose
labels are admission findings and not validation statuses. Historical P/E
consumes them; it does not extend the vocabulary. The mapping the engine needs:

| Refusal label | Effect on Historical P/E |
| --- | --- |
| `NOT_KNOWABLE_AT_AS_OF` | Evidence excluded from this evaluation date; may be eligible at a later date |
| `METRIC_NOT_IN_V1_SCOPE` | Metric not admitted; no observation emitted at all |
| `UNIT_NOT_MONETARY` | Applied to EPS evidence that is not `per_share`; component inadmissible |
| `CURRENCY_UNDECLARED` | Component inadmissible; price/EPS currency cannot be shown to match |
| `AMBIGUITY_RAISED` | Component inadmissible; engine raises rather than choose |

The last one matters: where two admissible evidence instances disagree for the
same fiscal quarter, the correct behaviour is to refuse, not to pick. The POC's
AAPL data never hit it, and the contract does not define a tie-break.

### D.4 States that are explicitly *not* eligibility

Two conditions look like states and are not:

**`XBRL_FACT_UNAVAILABLE`** is not a reason code, not a status, and not an
eligibility test. It records that no machine-readable fact exists for a quarter.
Per ADR Decision 13 it must never be reported as `primary evidence unavailable`
and must never, on its own, justify `REASON_MISSING_Q4_EPS`. It may appear in
diagnostic output and nowhere else.

**`audited == false`** is not a refusal condition for quarterly evidence. Per
ADR Decision 11 the correct response to an unaudited-but-otherwise-qualifying
quarter is to admit it.

### D.5 Composition status

The nested `eps_state`, `price_state` and `pe_state` each carry their own
status. An `AVAILABLE` `pe_state` requires both `eps_state` and `price_state`
`AVAILABLE`. A child in `REFUSED` propagates to `REFUSED` at the parent; a child
in `UNAVAILABLE` propagates to `UNAVAILABLE`.

---

## E. Resolver sequence

The order is normative. Reordering these steps is a conformance failure, because
each step's output is an input to the next and several failure modes only
appear in one order.

```
E.0  Load frozen input set; verify input_set_id
E.1  Establish issuer fiscal calendar
E.2  Enumerate admissible quarter EPS evidence (all classes)
E.3  Resolve each evidence instance to a PIT usable date
E.4  Select evaluation dates
E.5  Resolve the point-in-time evidence state at each date
E.6  Build the fiscal quarter window
E.7  Compute the metric or determine its state
E.8  Emit observation, hash, and replay identity
```

### E.1 Establish issuer fiscal calendar (E.1)

Inputs: the issuer's own declaration. In AAPL's case the 10-K SGML header
`FISCAL YEAR END: 0930`. The contract records:

```
fiscal_year_end_month: int         # from the issuer's own declaration
fiscal_year_end_declaration_source: str
fiscal_year_end_drift_observed: bool   # e.g. day drifted 0924 -> 0930
```

**This step must not consult a list of filed 10-K period ends to decide which
fiscal year a quarter belongs to.** That is precisely what produced the 455-day
window. The derivation is:

```
fiscal_year(period_end) = period_end.year + (1 if period_end.month > fiscal_year_end_month else 0)
fiscal_quarter(period_end) = 4 if (period_end.month - fiscal_year_end_month) % 12 == 0
                            else ((period_end.month - fiscal_year_end_month) % 12) // 3
```

Both are functions of the quarter's own period end and the declared fiscal year
end month. Neither needs to know whether a 10-K for that fiscal year exists.
This is what makes the open fiscal year resolve correctly.

**Limitations, stated rather than hidden:**

- Month arithmetic is a *derived fallback*. Where the issuer's own document
  states the fiscal period (`fiscal_position_source == "ISSUER_STATED"`), that
  statement governs and the derived value is a cross-check.
- If the two disagree, the engine **must** refuse the component
  (`AMBIGUITY_RAISED`). It must not silently prefer either.
- Month arithmetic does not model 4-4-5 retail calendars or a fiscal year end
  that drifts across a month boundary. `fiscal_year_end_drift_observed` exists
  so this is visible rather than assumed away.
- `fiscal_year_end_month` is a property of a fiscal year, not of the issuer. An
  issuer whose year end drifts across a boundary needs a per-fiscal-year value.
  This contract does not define that resolution and it is OPEN (§K.4).

### E.2 Enumerate admissible quarter EPS evidence (E.2)

Enumerate **all** evidence classes before any eligibility conclusion. For each
class:

1. Identify candidate documents: filed periodic reports, and furnished Item 2.02
   exhibits.
2. For each document, extract candidate quarterly EPS values **with** their
   period declaration, metric classification and audit status.
3. Reject at enumeration time, recording why:
   - metric is not `GAAP_DILUTED_EPS` → refuse (`UNIT_NOT_MONETARY` or metric
     refusal) but keep the record for audit;
   - `period_declaration == "UNSTATED"` → inadmissible;
   - period is cumulative (`Twelve Months Ended`, `Nine Months Ended`, …) →
     inadmissible;
   - `acceptance_source` is `UNDECLARED` → inadmissible (no PIT anchor);
   - currency undeclared → inadmissible.
4. Emit admissible `QuarterEpsEvidence` instances.

**Hard prohibition.** Enumeration and the TTM builder may never form a quarter
value by subtracting one filed cumulative figure from another. There is no code
path that takes an annual figure and a year-to-date figure and produces a
quarter. `stated_directly` is `true` for every admissible instance and is
asserted, not inferred.

### E.3 Resolve PIT usable date (E.3)

Per ADR Decision 3, the 16:00 ET cutoff is an ST-EVA convention and **not** SEC
filing law. The observation records it as such.

```
pit_anchor = acceptance_datetime (or publication_datetime, non-SEC sources)

usable_date(t):
    anchor_date  = pit_anchor.date()                       # in the anchor's own zone
    before_close = pit_anchor.time() < 16:00 ET
    candidate    = anchor_date if before_close else anchor_date + 1 day
    usable_date  = first trading day on or after candidate
```

`trading_days` comes from the price input set. Recording which set was used, and
its hash, is required: a usable date that lands on a day the calendar did not
consider a trading day is not reproducible.

Provenance obligations at this step:

- The anchor must carry an explicit offset. A naive local timestamp is refused.
- `acceptance_source` must be one of the enumerated values in §B.2. A value
  derived from the submissions API's `Z`-suffixed field is refused.
- `usable_date_rule` records which branch applied:
  `acceptance_before_1600ET_same_day` or
  `acceptance_at_or_after_1600ET_next_trading_day`.
- `usable_date` must never precede the quarter's own `period_end`. A quarter
  cannot be known before it closes.

### E.4 Select evaluation dates (E.4)

The candidate set is the set of dates at which the point-in-time evidence state
can change: the distinct usable dates of enumerated evidence.

**Sampling frequency is OPEN (§K.3) and this contract does not choose one.** The
POC used filing-event dates, which is a sampling choice, not a rule. An
implementation may narrow or widen the candidate set, but the selection **must**
be recorded as `evaluation_date_selection` with a strategy name and a strategy
version, and the strategy **must** be monotone: adding evidence may only add
evaluation dates, never remove them, otherwise a later filing could silently
rewrite history.

### E.5 Resolve point-in-time evidence state (E.5)

At evaluation date $t$, for each fiscal quarter position $q$:

```
known(q, t) = the admissible evidence for q whose usable_date <= t,
              chosen by rule R-PIT-SUPERSEDE
```

**R-PIT-SUPERSEDE**: among admissible instances for the same fiscal quarter with
`usable_date <= t`, select the one with the greatest `usable_date`; break exact
ties by greatest `acceptance_datetime`, then by `accession` ascending. This is
the point-in-time restatement rule: a later restatement is used only once it was
itself public. A restatement filed after $t$ must not reach back into state at
$t$.

The rule is explicit about ordering so two implementations cannot disagree on
which version was known.

### E.6 Build the fiscal quarter window (E.6)

Anchor and step back on **fiscal identity**, never on date ordering and never on
"the last four records I have".

```
anchor       = the greatest fiscal-quarter position with known(q, t)
positions    = [ (FY, Q) ] walking back three fiscal quarters from anchor
window       = positions in ascending fiscal order
```

Crossing a fiscal year boundary increments the fiscal year and resets the
quarter to 4. Nothing about this step consults a 10-K list, and nothing sorts
by `period_end`.

Failure to fill a position produces `missing_quarters`, which the state step
(E.7) turns into a reason code. The engine **must not** shorten the window. A
three-quarter sum is not a TTM and there is no code path that emits one.

### E.7 Compute or determine state (E.7)

```
if any window position is unfilled:
    state     = UNAVAILABLE
    reason    = REASON_MISSING_Q4_EPS if any unfilled position has fiscal_quarter == 4
                else REASON_INSUFFICIENT_QUARTERS
elif price_state is UNAVAILABLE:   state, reason = UNAVAILABLE, REASON_MISSING_PRICE
elif price/EPS basis unaligned:     state, reason = UNAVAILABLE, REASON_CORPORATE_ACTION_UNRESOLVED
elif sum(quarters) <= 0:           state, reason = UNAVAILABLE, REASON_NON_POSITIVE_EPS
else:                              state = AVAILABLE, value = close / sum(quarters)
```

For `ANNUAL_GAAP_DILUTED_PE`, the evidence filter is §C.3 and there is no window.

### E.8 Emit and hash (E.8)

The canonical form is JSON with sorted keys, no insignificant whitespace, and
the **excluded field set** of §I.2 removed.

---

## F. Invariants

These are testable statements. Each names the failure it prevents, because each
one corresponds to something that actually went wrong.

**F-1 — Evidence is never synthesised.**
Every admissible quarter EPS is a directly stated figure from one document.
No code path forms a quarter by subtracting cumulative figures.
*Prevents:* ADR Decision 4 violation; the prohibited `FY − YTD` derivation.

**F-2 — A TTM window is four consecutive fiscal quarters and contains a Q4.**
Exactly four positions, consecutive in fiscal identity, quarter numbers matching
`[(n) mod 4 + 1 for n in 0..3]`, at least one with `fiscal_quarter == 4`,
adjacent `period_end` values within `QUARTER_MAX_DAYS`.
*Prevents:* silent three-quarter truncation.

**F-3 — Fiscal identity never depends on the existence of a 10-K.**
`fiscal_year` and `fiscal_quarter` are functions of `period_end` and the declared
`fiscal_year_end_month`. No list of filed annual period ends participates.
*Prevents:* the open-fiscal-year mislabel and the 455-day window. Conformance
test: a window whose positions include an open fiscal year must have adjacent
`period_end` gaps within `QUARTER_MAX_DAYS`.

**F-4 — Annual never fills TTM.**
`TTM_GAAP_DILUTED_PE` denominators are quarterly evidence only. Where TTM is
`UNAVAILABLE`, no annual value may appear in that observation.
*Prevents:* ADR §3.B masquerade.

**F-5 — Evidence class is never laundered.**
A component's `evidence_class` equals the class of the document it came from.
`furnished` is never `filed`. `audit_status == "audited"` is never asserted for
a furnished or 10-Q source. When `evidence_class == "furnished"`,
`legal_status_note` is non-null and `stated_directly == true`.
*Prevents:* ADR Decisions 10 and 11 violations.

**F-6 — Price and EPS accounting bases agree.**
`accounting_basis` is stated on price evidence, and either it equals the EPS
per-share basis, or the observation is `REASON_CORPORATE_ACTION_UNRESOLVED`.
*Prevents:* a 4× split error. The POC's `as_traded` pairing is one valid
solution, not the only one; the contract requires the bases to be declared and
matched, not a particular schema.

**F-7 — Point-in-time monotonicity.**
For every emitted observation at date $t$ and every contributing component $c$:
`c.usable_date <= t`. Every `usable_date` is reproducible from `c`'s own
`pit_anchor_datetime`, its zone, the 16:00 ET rule, and the named trading-day
calendar.
*Prevents:* lookahead.

**F-8 — Restatements are point-in-time.**
The instance selected at date $t$ is the one with the greatest `usable_date`
among instances with `usable_date <= t`.
*Prevents:* a 2024 restatement contaminating a 2019 state.

**F-9 — GAAP is never mixed with non-GAAP.**
All four components of a TTM carry `metric == "GAAP_DILUTED_EPS"`. No
`NON_GAAP_*` metric participates. Where a document states both, the non-GAAP
instance is constructed and excluded, and its presence is visible in the
evidence set.
*Prevents:* ADR §5.1.

**F-10 — `CURRENT_PE` is excluded from every window.**
`CURRENT_PE` observations carry `role: "current_snapshot"` and are not eligible
as inputs to any aggregation, band, percentile or reference multiple.
*Prevents:* ADR §3.C.

**F-11 — Reason codes are in the closed enumeration.**
Every emitted reason code is a member of the ADR enumeration. No code is
invented, extended or reused outside its defined situation.
*Prevents:* the `XBRL_FACT_UNAVAILABLE` drift the ADR explicitly leaves OPEN.

**F-12 — `XBRL_FACT_UNAVAILABLE` is never an eligibility state.**
Absence of a machine-readable fact does not make a quarter inadmissible when
admissible document text states it.
*Prevents:* the original AAPL finding recurring.

**F-13 — Determinism.**
Same `input_set_id` + same `logic_version` ⟹ same `content_hash`. Fields that
vary between runs of the same computation are in the excluded set (§I.2).
*Prevents:* a hash that cannot be reproduced.

**F-14 — Source identity is complete.**
Every component carries accession, form, source URL and content hash. A
component missing any of these is inadmissible, not partially reported.
*Prevents:* an unreachable number.

**F-15 — Same accounting metric across classes.**
`evidence_class` may differ between the four components of one TTM; `metric`,
`unit` and `currency` may not.
*Prevents:* the class distinction leaking into the arithmetic.

---

## G. Failure / unavailable semantics

### G.1 Component-level failures

| Condition | Result | Carries |
| --- | --- | --- |
| Metric is not `GAAP_DILUTED_EPS` | Component inadmissible | `Refusal` with the metric's existing label |
| `period_declaration == "UNSTATED"` | Component inadmissible | `Refusal` |
| Period is cumulative | Component inadmissible | `Refusal` |
| Currency undeclared | Component inadmissible | `CURRENCY_UNDECLARED` |
| Acceptance timestamp naive | Component inadmissible | `Refusal` |
| `acceptance_source == "UNDECLARED"` | Component inadmissible | `Refusal` |
| Fiscal position derived and issuer-stated disagree | Component inadmissible | `AMBIGUITY_RAISED` |
| Two admissible instances disagree for one quarter | Component inadmissible | `AMBIGUITY_RAISED` |
| `usable_date < period_end` | Component inadmissible | `Refusal` (impossible state) |

An inadmissible component is **retained** in the evidence set with its refusal
attached. Deleting it would make the record say "this was never found" when the
truth is "this was found and judged inadmissible".

### G.2 Window-level failures

An unfilled fiscal position produces an entry in `missing_quarters`:

```json
{ "fiscal_year": 2026, "fiscal_quarter": 4,
  "candidate_evidence_classes_enumerated": ["filed", "furnished"],
  "excluded": [ { "reason": "not_published_at_this_date" } ] }
```

The `candidate_evidence_classes_enumerated` field is what makes
`REASON_MISSING_Q4_EPS` auditable. It asserts that both classes were looked for,
which is the precondition ADR Decision 13 attaches to that code.

A position filled by an inadmissible component counts as unfilled, not as
filled-by-something-else.

### G.3 Metric-level failures

Per §D.1. `UNAVAILABLE` carries a reason code from the closed enumeration;
`REFUSED` carries a reason code plus a `Refusal`.

### G.4 Absent price

No `HistoricalPriceEvidence` at the evaluation date gives
`REASON_MISSING_PRICE`. The EPS state is still emitted as
`AVAILABLE`, because "we have the earnings" and "we have the price" are
independent facts and collapsing them loses the diagnosis. This differs from the
current Core behaviour, which substitutes `0.0` for an absent price; this
contract must not inherit that, and it is one of the reasons a Historical P/E
observation is not a `ValuationInputs` field.

### G.5 `CURRENT_PE` misuse

Any attempt to place a `CURRENT_PE` observation inside a window, band or
reference set is a refusal, not a silent exclusion. This mirrors the existing
boundary's stated position that a refused input and a wrong input differ only in
whether the reader can tell.

### G.6 What must never happen

| Anti-pattern | Why it is not merely a bug |
| --- | --- |
| Derive Q4 as `FY − YTD` | Produces a number the issuer never reported (ADR Decision 4) |
| Fill a TTM gap with an annual figure | Semantic masquerade (ADR §3.B) |
| Emit a TTM from three quarters | Wrong denominator, indistinguishable from a real one |
| Use `XBRL_FACT_UNAVAILABLE` as a reason code | States a false fact about the evidence (ADR Decision 13) |
| Label furnished evidence `filed` or `audited` | Misstates legal status (ADR Decisions 10, 11) |
| Adopt an annual figure for `AUDIT_STATUS == "audited"` on 10-Q evidence | 10-Q interim statements are reviewed, not audited |
| Prefer a later restatement for an earlier date | Lookahead (ADR Decision 7) |
| Sort quarters by `period_end` to pick a window | Ignores fiscal identity; the 455-day failure |

---

## H. Provenance requirements

### H.1 The five questions

A published observation must answer all five without access to anything outside
its own record:

1. **Which day's price?** `price_state.price_date`, `close`, `currency`,
   `accounting_basis`, `price_evidence_id`, and the evidence's own
   `content_sha256`.
2. **Which four documents?** `eps_state.components[*].accession`,
   `form`, `source_document`, `source_url`, `content_sha256`.
3. **When was each obtainable?** Per component:
   `acceptance_datetime` / `publication_datetime`, `acceptance_source`,
   `usable_date`, `usable_date_rule`, `acceptance_precision`.
4. **Why can or cannot this date produce a TTM?** `eps_state.status`,
   `missing_quarters` with `candidate_evidence_classes_enumerated`, and
   `reason_code`.
5. **Can this be recomputed?** `replay_identity.input_set_id`,
   `logic_version`, `content_hash`.

### H.2 Mandatory disclosure of mixing

When the four components do not share one evidence class, the observation must
state it without being asked:

```json
"component_summary": {
  "evidence_classes_present": ["filed", "furnished"],
  "mixed_class_window": true,
  "forms_present": ["10-Q", "8-K"],
  "audit_statuses_present": ["unaudited_reviewed", "unaudited"]
}
```

`mixed_class_window` exists because a reader who sees a single TTM figure has no
way to know it was assembled from two kinds of document. The contract requires
that fact to travel with the number.

### H.3 Structural requirements

- Every component's `content_sha256` must match the bytes of the document it
  names, re-verifiable by refetch. The POC's verification re-extracted every
  furnished value from the exhibit bytes as an independent path; that capability
  is part of the contract, not a test convenience.
- `input_set_id` is a hash over the frozen input set manifest, so an
  observation can be tied to exact bytes.
- Refusals travel with the observation. An observation with a silently dropped
  component is non-conformant.

### H.4 Declared vs derived provenance

Every field in the evidence record is one of:

- **stated** — the document says so (`acceptance_datetime`, `value`,
  `period_declaration`, `legal_status_note`);
- **derived** — computed by a named rule (`fiscal_year`, `fiscal_quarter`,
  `usable_date`);

and the record says which, per field, via `fiscal_position_source` and
`derivation`. A derived value must never be presented as a stated one. This is
the structural version of ADR Decision 4's rule.

---

## I. Replay requirements

### I.1 Guarantee

```
same input_set_id  +  same logic_version  ⟹  identical content_hash
```

The guarantee is over a **frozen input set**. A refetched price series or a new
SEC restatement is a different input set and is expected to change the hash.
That is an input change, not a replay failure, and the observation's
`input_set_id` is what makes the distinction checkable.

### I.2 Excluded field set

Fields that may differ between two runs of the same computation on the same
inputs, and which are therefore excluded from the hash preimage:

```
retrieved_at
wall_clock_timestamp
run_id
host_identifier
```

Everything else is included, including `usable_date_rule`,
`fiscal_position_source`, `derivation`, `legal_status_note` and
`component_summary`. The POC's hash was stable across two process runs only
because it excluded wall-clock values; a hash that excludes anything else would
be hiding a nondeterminism.

### I.3 Conformance suite

An implementation is conformant when it reproduces, from its own output:

1. **Replay.** Two runs over the same input set yield the same `content_hash`.
2. **Independent recomputation.** A third computation path, not sharing the
   builder's code, reproduces every TTM denominator from raw bytes.
3. **Negative path.** Disabling an evidence class returns the metric to its
   prior state for the affected dates, and reproduces the pre-change result
   exactly on the unaffected dates.
4. **Lookahead.** Zero components with `usable_date > evaluation_date`.
5. **Window integrity.** Every available TTM satisfies Invariant F-2, including
   the adjacent-gap condition of F-3.
6. **Provenance completeness.** Every accepted component satisfies F-14.
7. **Class integrity.** Invariants F-5, F-9 and F-15 hold on every emitted
   observation.

Items 3 and 5 are the ones that caught real defects in the POC. A suite without
them would have passed the 455-day window.

### I.4 Replay identity as a first-class field

`replay_identity` is not a debugging aid. It is what lets a later reader
conclude "this was reproducible" or "this was not", and it is required on every
emitted observation.

---

## J. Genericization limits

### J.1 Proven on AAPL

Measured over 31 evaluation dates, 2019-01-31 to 2026-07-31, one issuer:

| Capability | Evidence |
| --- | --- |
| Point-in-time evidence state machine | 31 dates, 0 lookahead violations |
| 16:00 ET usable-date convention actually exercised | 5 of 5 Q4 releases accepted 16:30 ET, all landing on the next trading day |
| `filed ×3 + furnished ×1` TTM window | 20 of 31 dates |
| 31/31 TTM coverage | Prior POC 12/31, furnished path 31/31, negative path reproduces 12/31 exactly |
| Two evidence classes with separation preserved | 0 mislabelled components |
| Non-calendar fiscal year (FYE in September, 52/53-week) | All 31 dates |
| Open fiscal year with no 10-K yet | Correctly resolved after the F-3 fix |
| Split within the window (4:1, ex-date 2020-08-31) | Priced `as_traded` against `as_filed` EPS |
| Deterministic replay | Two runs, identical hash; third path, zero mismatch |
| Provenance completeness | Every component to accession, document and hash |

### J.2 Not proven for any other issuer

Single-issuer evidence. Each of the following is **unverified** and an
implementation must not assume AAPL's answer transfers:

| Area | What AAPL showed | What remains unproven |
| --- | --- | --- |
| 8-K Item 2.02 exhibit | EX-99.1 with `Three Months Ended` / `Twelve Months Ended` columns, corroborated by a narrative sentence | Other issuers' exhibit layouts; whether the narrative corroboration is universal; whether some issuers omit the quarter column entirely |
| Furnished Q4 | Present for all five post-FY2020 quarters | Whether every issuer furnishes Q4; whether the furnished figure ever disagrees with a later filed figure |
| Fiscal calendar | FYE in September, stable month, day drifting within the month | 4-4-5 retail calendars; FYE drifting across a month boundary; multiple fiscal years in one dataset |
| Fiscal year transition | Not exercised | An issuer changing its fiscal year mid-history; a transition quarter; a 53-week quarter |
| Foreign private issuer | Not exercised | 20-F / 6-K cadence; IFRS diluted EPS semantics; no Item 2.02 equivalent |
| ADR / dual-listed | Not exercised | Price in one currency, EPS in another; per-ADS versus per-ordinary-share mismatch |
| Non-USD EPS | Not exercised | Currency declaration quality; whether price and EPS currency can be shown to match without conversion |
| Corporate actions | One 4:1 split, handled by `as_traded` pricing | Rights issues, spinoffs, special dividends, currency redenominations, multiple splits in one window |
| Accounting basis changes | Not exercised | An issuer restating EPS basis, or switching between basic and diluted presentation mid-history |
| Restatement | No conflict observed between competing versions | Which instance wins when two admissible instances for one quarter disagree — the contract refuses rather than decides |

### J.3 What the AAPL result does **not** license

- That TTM P/E is always constructible. It was constructible because AAPL
  furnished Q4 evidence. An issuer that does not will still be
  `UNAVAILABLE`, and that is correct behaviour, not a defect.
- That 31 observations is sufficient. Sufficiency is OPEN (§K.1).
- That filing-event dates are the right sampling. Frequency is OPEN (§K.3).
- That `as_traded` pricing generalises. It worked for one split on one issuer.
- That the fiscal-month arithmetic generalises beyond AAPL's calendar.

---

## K. OPEN decisions

This contract deliberately does **not** settle any of the following. Each is
listed with what it blocks, so the dependency is visible.

**K.1 Reference Sufficiency threshold.**
Whether observation count alone suffices, or whether time span and fiscal-quarter
coverage must also be met, and at what values. Blocks: whether the 31 AAPL
observations form a usable reference set. `REASON_INSUFFICIENT_OBSERVATIONS` and
`REASON_INSUFFICIENT_TIME_SPAN` exist in the ADR enumeration but their triggers
are undetermined. Not decided here.

**K.2 The 20 / 24 observation requirement.**
Unchanged and untouched. Whether it governs a TTM-based reference set, an
annual-based one, or both, is undetermined. Not decided here.

**K.3 Sampling frequency.**
Daily, weekly, monthly or event-driven, and its effect on percentile stability.
§E.4 requires the strategy to be named, versioned and monotone, but does not
choose one. Not decided here.

**K.4 Corporate Action evidence schema.**
Source authority (SEC filing vs exchange notice vs vendor factor), ex-date
timestamp precision, storage structure, and how a price is restated into a chosen
basis. §B.3 defines only the `accounting_basis` field and Invariant F-6. The
question of per-fiscal-year `fiscal_year_end_month` resolution also falls here.
Not decided here.

**K.5 FPI fallback policy.**
Whether an FPI reporting only semi-annually may be declared as an
annual-driven valuation, and the interaction with the TTM/Annual separation.
Not decided here.

**K.6 Weighting of furnished evidence in other valuation contexts.**
Amendment 1 admits furnished evidence as a TTM component. Whether it may also
appear in a standalone `trailing_eps` observation, in a band, or in any
non-historical-P/E crossing is undetermined. This contract covers
`TTM_GAAP_DILUTED_PE` components only. Not decided here.

**K.7 `XBRL_FACT_UNAVAILABLE` observability.**
Whether it becomes an observation attribute or a reason code. The ADR
enumeration is closed and this contract keeps it closed, so today it is
diagnostic only. Not decided here.

**K.8 Ties among competing admissible instances.**
§D.3 refuses rather than tie-breaks. Whether a documented precedence rule is
warranted is undetermined. Not decided here.

**K.9 Non-USD currency handling.**
Whether cross-currency EPS and price may ever be paired, and under what
declaration. ADR §5.4 excludes dynamic FX conversion from valuation, which does
not by itself answer the pairing question. Not decided here.

---

## L. Consistency review

Reviewed against the frozen ADR and the completed POC.

**L.1 Does this contract conform to the ADR?** Yes. It introduces no new reason
code (§D.2, §F-11), changes no frozen decision, and treats Amendment 1
Decisions 10–14 as binding. Where the ADR is silent — sufficiency, frequency,
Corporate Action, FPI, weighting — the contract marks the gap OPEN rather than
filling it (§K). The §2.1 Decision 4 rationale correction is honoured: §F-1 and
§H.4 state the evidence-integrity reason and make no claim about how large the
arithmetic difference is.

**L.2 Can it express the AAPL POC's 31/31 TTM?** Yes, and the POC's own output is
the worked example. `2025-10-31` emits `status: AVAILABLE`, denominator `7.47`
from three `filed` 10-Q components and one `furnished` 8-K component,
`mixed_class_window: true`, `audit_statuses_present:
["unaudited_reviewed", "unaudited"]`. With the furnished class disabled, the
same date returns `UNAVAILABLE` / `REASON_MISSING_Q4_EPS` with
`candidate_evidence_classes_enumerated: ["filed", "furnished"]` — which is
precisely the 12/31 state the prior POC recorded.

**L.3 Is filed/furnished semantic separation preserved?** Yes. F-5 forbids
laundering; §B.2 makes `legal_status_note` mandatory for furnished evidence;
§D.2 makes three-valued `audit_status` mandatory; §C.3 restricts annual evidence
to 10-K `audited`; §H.2 forces a mixed-class window to disclose itself. The POC
verified zero mislabelled components across 31 dates.

**L.4 Is `FY − YTD` fully prohibited?** Yes, structurally. §E.2 step 3 rejects
cumulative periods at enumeration; `stated_directly` is asserted not inferred;
§H.4 requires every field to be marked stated or derived; §G.6 lists the
anti-pattern. There is no arithmetic path from a cumulative figure to a quarter
anywhere in the specified sequence.

**L.5 Is "last four records" excluded?** Yes. §E.6 anchors on the greatest
*fiscal-quarter position with evidence* and steps back on fiscal identity. §E.1
derives that identity from `period_end` plus the declared fiscal year end month.
Invariant F-2 forbids three-quarter truncation. §E.6 contains no date sort.

**L.6 Is the 455-day window failure prevented?** Yes. Invariant F-3 forbids any
10-K-list dependency in fiscal identity, and its conformance test is the
adjacent-gap condition. §E.1 states the prohibition and the derivation
explicitly, and `fiscal_year_end_drift_observed` records the 52/53-week drift the
POC had to handle. The negative-path and window-integrity checks in §I.3 are
what caught it.

**L.7 Does it decide anything the ADR has not decided?** No. All nine items in
§K are left open with their dependencies named. No threshold, no frequency, no
Corporate Action schema, no FPI policy, no new reason code, no weighting rule.
The one place the contract goes beyond restating the ADR is §G.4, which
specifies that an absent price yields `REASON_MISSING_PRICE` with the EPS state
still emitted rather than a zero substituted; this follows from ADR §3.D and
does not introduce a code or a threshold, but it is a behavioural requirement on
a future implementation rather than a restatement, and is flagged as such.

**L.8 Is the boundary with Core respected?** Yes. `Observation`, `Evidence`,
`ValidationStatus`, `Refusal`, `Unit`, `SourceType`, `AvailabilityBasis` and
`PRECISION_INSTANT` are consumed unchanged. `QuarterEpsEvidence` is a view over
a Core observation, not a replacement; the Core observation remains the record of
what the source said. No metric id in `data_contract.py` is redefined; the three
P/E metric ids are namespaced to this contract.

**L.9 Does it stay implementation-free?** Yes. Interfaces, semantics, ordering,
invariants and conformance tests are specified. No algorithm is given beyond the
two short derivations in §E.1 and §E.3 that the POC proved are load-bearing, no
parser is described, no provider is chosen, and no file in
`st_eva_runner.py`, `data_contract.py`, `evidence_valuation_boundary.py`, the SEC
provider, the web app, the ADR or the POC outputs is modified.
