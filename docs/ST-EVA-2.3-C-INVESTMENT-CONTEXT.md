# ST-EVA 2.3-C — Investment Context

Status: SPEC (to be reviewed before implementation)
Target: 2.3-C
Baseline: 2.3-B
Repository: sbvcid/st-eva
Builds on:
[docs/ST-EVA-2.3-A-DATA-CONTRACT.md](ST-EVA-2.3-A-DATA-CONTRACT.md),
[docs/ST-EVA-2.3-B-SEC-VALIDATION.md](ST-EVA-2.3-B-SEC-VALIDATION.md)

## 0. Purpose

> The Investment Context is **the verifiable research material ST-EVA holds
> about one asset at one point in time.**

It is not a report ST-EVA wrote about a stock, and it is not a conclusion. It
is the assembled, provenance-carrying, traversal-ready set of observations,
evidence, validations, derivations, and the market-implied arithmetic that
follows from them, packaged so that any consumer — an agent, an analyst, a
downstream tool — can read it without knowing how ST-EVA is built.

The division of labour it enforces:

```
ST-EVA Core     "these are the data and the arithmetic, and here is how you
                 check every number I produced."
Agent           "I believe these data represent X."
Investor        "so should I allocate?"
```

An intelligence that is not in the Core stays out of the Core. A rating, a
probability, a ranking, a quality score, or a buy/sell label is an
interpretation, and 2.3-C does not contain one.

### 0.1 Non-goals

- No new data source. Yahoo and SEC, as already built.
- No new metric. The 2.3-B seven and the 2.2.3 engine outputs.
- No new valuation model, formula, or reference-selection policy.
- No probability, quality score, AI score, rating, or recommendation.
- No peer, sector, or cross-asset comparison. "Cheaper than NVDA" is not a
  fact about NVDA's price, and this artifact is about one asset.
- No point-in-time replay engine. That is 2.4. 2.3-C makes a context
  *replay-safe* so 2.4 can build one.
- No agent integration, prompt, or model. That is 2.5.
- No change to the 2.2.3 CLI or JSON.

## 1. Purpose, stated as a contract

Three properties, in priority order. When they conflict, the earlier wins.

1. **Every number is traceable.** A consumer can start from any figure and walk
   to the raw observation it came from, through the evidence that admitted it,
   the validation applied, and the formula used, without leaving the document
   and without running ST-EVA.
2. **No figure asserts more than it knows.** A value with an undeclared
   period, an undeclared currency, or an undeclared source is presented as
   undeclared. A value that could not be established is presented as absent.
3. **No figure asserts an opinion.** Data quality is counts and statuses, never
   a grade.

### 1.1 The gap this phase closes

2.3-B proved two sources can be compared. It did not produce anything a third
party can read. Worse, tracing the most important number in the engine is
currently broken at its second link:

```
implied_forward_eps
  -> "price / reference.multiple"      (prose, not evaluable)
  -> inputs: (ev-price-001,)           (the reference multiple is absent)
```

`valuation_reference.multiple` is the value on which **every** implied figure
in the run is conditional, and it has no provenance in the output at all. When
`method` is `historical_pe_median`, nothing points at the band observation the
median came from. A consumer can read `implied_forward_eps: 23.34` and has no
way to learn which multiple produced it, whether that multiple was observed or
assumed, or whether the historical band was even eligible.

2.3-C closes that link, and makes the whole chain machine-traversable.

## 2. Schema

One document, twelve top-level sections. Every numeric figure is a *figure*:
an object with a value, a unit, a ref, and a provenance kind.

```json
{
  "context_schema_version": "2.3-C.1",
  "context_id": "ctx_<content_hash>",
  "supersedes": null,
  "min_reader_version": "2.3-C.0",
  "built_from": {
    "legacy_snapshot_schema_version": "2.2.3",
    "contract_version": "2.3-A",
    "cross_source_version": "2.3-B"
  },

  "asset": {
    "ticker": "MU",
    "company_name": "...",
    "exchange": "...",
    "currency": "USD",
    "identifiers": {"ticker": "MU", "cik": "0000723125", "exchanges": ["Nasdaq"]}
  },

  "as_of": "2026-09-18",
  "generated_at": "2026-09-28T17:04:11+00:00",
  "knowledge_cutoff": "2026-09-26T22:30:24+00:00",

  "scope": { ... },
  "glossary": { ... },
  "observed": { ... },
  "validated_evidence": { ... },
  "derived": { ... },
  "valuation_reference": { ... },
  "market_implied": { ... },
  "data_quality": { ... },
  "unavailable": [ ... ],
  "limitations": [ ... ],
  "provenance": { "refs": { ... }, "derivations": { ... } }
}
```

### 2.1 Section order is reading order

`asset` and the three timestamps, then what was observed, then what survived
validation, then what was computed, then what the price requires, then how
trustworthy the above is, then what is missing, then what it does not support.
A consumer can stop at any section and will not have been misled about the
sections it skipped, because no section asserts a conclusion another section
would have to support.

### 2.2 The figure object

Every numeric value in the document is one of these.

```json
{
  "value": 466823000000.0,
  "unit": "currency",
  "currency": "USD",
  "provenance_kind": "OBSERVED",
  "ref": "obs:ev-revenue-001"
}
```

`provenance_kind` is one of:

| Kind | Meaning |
|---|---|
| `OBSERVED` | read from a source, not computed by ST-EVA |
| `DERIVED` | computed by ST-EVA from named inputs |
| `CONDITIONAL` | computed, but valid only under a stated condition |
| `UNAVAILABLE` | no value; the figure carries no `value` key at all |

`UNAVAILABLE` figures do not carry a number. Not `null` with a sibling status,
not `0`, not a median: the key is absent and the entry appears in
`unavailable` (§9) with a reason. This is the single most important invariant
in the document, and it is directly testable.

## 3. OBSERVED

What the sources reported, with no ST-EVA arithmetic applied.

- One figure per material metric, sourced from the 2.3-A `Observation`.
- Every observation is also registered in `provenance.refs` with its full
  contract record: unit, currency, `currency_basis`, `period_start`,
  `period_end`, `as_of`, `available_at`, `available_at_basis`, `provider`,
  `source_type`, `source_url`, `definition`, `methodology`, `retrieved_at`,
  and `raw_preserved`.
- `observed` carries the figures; `provenance.refs` carries the full records.
  The figure is the index entry, not the archive.

Three rules:

1. **The 2.2.3 legacy evidence row is never used here.** That row stamps the
   instrument currency onto valuation multiples and reports the price date as
   the `as_of` of every input. Both are 2.2.3 presentation projections and both
   are wrong as provenance. The context uses the 2.3-A contract view. Where the
   legacy row is included at all, for operators who read snapshots, it is under
   a key named to say so.
2. **A Yahoo trailing aggregate is presented as a trailing aggregate**, with
   `period_start` and `period_end` `null` and
   `available_at_basis: UNDECLARED`. The context does not invent the window
   Yahoo will not disclose, and does not quietly drop the fact that the window
   is undisclosed.
3. **Multiple providers appear side by side.** `observed.revenue` is a list
   keyed by provider, not a single value. 2.3-B proved two sources may both
   report a metric with different values; the context must not collapse that
   into one field.

```json
"observed": {
  "revenue": [
    {"provider": "YahooFinance", "figure": {...}},
    {"provider": "SecEdgar",    "figure": {...}}
  ],
  "price": [ {"provider": "YahooFinance", "figure": {...}} ]
}
```

## 4. VALIDATED EVIDENCE

The 2.3-B verdicts, published as part of the context for the first time. Until
2.3-C they exist only as a library return value.

```json
"validated_evidence": {
  "revenue": {
    "status": "CONSISTENT",
    "comparable": true,
    "vendor_ref": "obs:cmp-revenue-yahoo-2026-06-30",
    "filing_ref":  "obs:cmp-revenue-sec-ttm-to-2026-06-27-000032019326000020",
    "tolerance": {"kind": "RELATIVE_AND_ABSOLUTE_BOUND",
                  "relative": 0.005, "absolute": 50000000.0},
    "comparison_basis": { ... },
    "explanation": "revenue agrees across the two sources. ...",
    "references": [ ... ]
  }
}
```

Rules:

- A `METHODOLOGY_MISMATCH` or `PERIOD_MISMATCH` entry reports **both values**
  and the specific reason, and never a difference. The arithmetic between two
  figures that answer different questions is not computed.
- `independence` is carried from the 2.3-B `comparison_basis` and is never
  upgraded. `UNVERIFIED_INDEPENDENCE` stays `UNVERIFIED_INDEPENDENCE` no matter
  how many figures come out `CONSISTENT`.
- A metric with no second source is `UNAVAILABLE`, with the reason. It is
  present in the section so the consumer can see the shape of the coverage,
  not absent so the consumer infers success.

## 5. DERIVED

Every value ST-EVA computed, each traceable. This is the section the phase
exists for.

```json
"derived": {
  "required_eps_cagr": {
    "figure": {"value": 0.2241, "unit": "ratio", "currency": null,
               "provenance_kind": "DERIVED", "ref": "der:required_eps_cagr"},
    "derivation_ref": "trc:required_eps_cagr"
  }
}
```

### 5.1 The derivation record

```json
"trc:required_eps_cagr": {
  "depends_on": [
    "obs:ev-current-eps-001",
    "der:implied_forward_eps",
    "refc:horizon_years"
  ],
  "operation": {
    "op": "compound_growth_rate",
    "version": "1",
    "operands": [
      "der:implied_forward_eps",
      "obs:ev-current-eps-001",
      "refc:horizon_years"
    ],
    "parameters": {}
  },
  "expression": "(23.34 / 5.00) ** (1 / 1.0) - 1",
  "deterministic": true,
  "inputs_observed_at": ["2026-09-18", "2026-09-26"],
  "conditional_on": ["refc:valuation_reference"]
}
```

`operands` are plain ref strings. Each ref kind declares which of its fields an
operand reads, so no per-operand field selector is needed:

| Ref kind | Field an operand reads |
|---|---|
| `obs`, `ev`, `der` | `value` |
| `refc` | the field named by the reference's `operand_field` (`multiple`, `years`, …) |
| `val` | not a legal operand; a validation judges, it does not feed arithmetic |

Six requirements:

1. **`operation.op` must be in the registry, and `operation.version` must be
   supported.** An unregistered or unversioned operation is a hard error, not a
   skipped check. See §12.1.
2. **`operation` is fully machine-evaluable.** A consumer re-checks a number by
   resolving the operands, dispatching `op` and `version` through the registry,
   and applying the result. A prose `expression` is carried for a human reader
   and is never the only description.
3. **The graph is complete.** Every ref in `depends_on` and `operands` resolves
   in `provenance.refs`. There are no dangling references, and the graph is
   acyclic.
4. **Transitive input dates are recorded.** `inputs_observed_at` lets a consumer
   see the span of real-world dates a single derived figure rests on, without
   walking the graph.
5. **`conditional_on` is explicit.** A figure that depends on a chosen
   reference multiple says so, and the ref points at that section.
6. **`deterministic: true` is a claim.** It means re-evaluating `operation` on
   the referenced inputs reproduces the stored value within the contract
   tolerance, and a test asserts it for every derived figure in a real run.

### 5.2 The reference multiple is a first-class derivation input

`der:implied_forward_eps` resolves like any other:

```
der:implied_forward_eps
  op: divide
  ├─ obs:ev-price-001            425.50        (OBSERVED)
  └─ refc:valuation_reference   18.22x        (see §6)
```

`valuation_reference` is a *reference node*, not a derived figure: it is
resolved in §6 and appears in the graph by ref. The current gap — a reference
multiple with no provenance — is closed here.

### 5.3 The concrete derivation table

Every figure the 2.2.3 engine computes, and the operation that produces it.
There is no derived figure without a row here, and a row whose stored value the
registry cannot reproduce fails the build (`ParityError`), so the table and the
arithmetic cannot drift apart.

| `der:` ref | op | operands |
|---|---|---|
| `current_pe` | `divide` | `obs:ev-price-001`, `obs:ev-current-eps-001` |
| `forward_pe` | `divide` | price, forward EPS |
| `consensus_forward_pe` | `divide` | price, consensus EPS |
| `current_pfcf` | `divide` | market cap, free cash flow |
| `current_ev_ebitda` | `divide` | enterprise value, EBITDA |
| `current_ps` | `divide` | market cap, revenue |
| `implied_forward_eps` | `divide` | price, `refc:valuation_reference` |
| `consensus_price_at_median` | `multiply` | consensus EPS, `refc:valuation_reference` |
| `consensus_price_ratio` | `ratio` | consensus price, price |
| `consensus_price_gap` | `subtract` | consensus price ratio, `refc:one` |
| `implied_to_consensus` | `divide` | implied EPS, consensus EPS |
| `eps_gap_vs_consensus` | `subtract` | implied/consensus, `refc:one` |
| `required_eps_cagr` | `compound_growth_rate` | implied EPS, current EPS, `refc:horizon_years` |
| `implied_fcf` | `divide` | market cap, `refc:pfcf_reference` |
| `implied_ebitda` | `divide` | enterprise value, `refc:ev_ebitda_reference` |
| `implied_revenue` | `divide` | market cap, `refc:ps_reference` |
| `implied_shares` | `shares_from_market_cap` | market cap, price |
| `implied_revenue_per_share` | `amount_per_share` | implied revenue, implied shares |
| `implied_net_margin` | `divide` | implied EPS, implied revenue per share |
| `pe_percentile` | `percentile_position` | `refc:valuation_reference`, PE band |
| `ps_percentile` | `percentile_position` | current P/S, PS band |
| `ev_ebitda_percentile` | `percentile_position` | current EV/EBITDA, EV band |
| `return_1d` / `5d` / `20d` / `60d` | `price_return` | price history `#-1`, `#-2` / `#-6` / `#-21` / `#-61` |
| `log_returns` | `log_returns` | price history |
| `daily_volatility` | `sample_standard_deviation` | log returns |
| `realized_volatility` | `annualized_volatility` | daily volatility, `refc:trading_periods` |
| `average_volume` | `mean` | volume history |
| `latest_volume_vs_average` | `deviation_from_average` | volume `#-1`, average volume |

Two decompositions are longer than the engine's single expression, and both are
deliberate. The engine writes `implied / consensus - 1`; the graph splits it
into a division and a subtraction of the named constant `refc:one`. Same
arithmetic, two more hops, each one checkable.

Named run constants are `refc:` nodes, not parameters, because each materially
changes a reported number: `refc:horizon_years`, `refc:trading_periods` (the
252-day annualisation convention, which would otherwise be buried in the code),
and `refc:one`.

## 6. REFERENCE

The selected valuation reference, and everything a consumer needs to judge it.

```json
"valuation_reference": {
  "ref": "refc:valuation_reference",
  "metric": "pe",
  "multiple": 18.22,
  "basis": "HISTORICAL_MEDIAN",
  "provenance_kind": "OBSERVED",

  "source_ref": "obs:ev-pe-band-001",
  "source_statistic": "median",
  "source_observation_count": 8,
  "eligible_as_reference": false,
  "eligibility_rule": "a band needs at least 20 usable observations",
  "eligibility_reason": "8 observations is below the 20 required",

  "selected_at": "2026-09-28T17:04:11+00:00",
  "selection_method": "historical_pe_median",
  "user_overridden": false,

  "alternatives_considered": [
    {"basis": "USER_SUPPLIED", "available": false},
    {"basis": "HISTORICAL_MEDIAN", "available": true, "eligible": false},
    {"basis": "NONE", "available": true, "eligible": true}
  ]
}
```

`basis` is one of:

| Basis | Meaning |
|---|---|
| `HISTORICAL_MEDIAN` | the median of a retrieved band observation; `source_ref` names it |
| `USER_SUPPLIED` | supplied on the command line; no observation exists, and `user_overridden` is `true` |
| `NONE` | no reference was available; every dependent figure is `UNAVAILABLE` |

Five requirements:

1. **`basis` is never inferred from the number.** A consumer that sees
   `multiple: 18.22` must be able to tell without guessing whether it was
   observed from a filing or typed by a person.
2. **Ineligibility is reported next to the value.** A band that carries 8
   observations cannot be a reference, and the context says so while still
   showing the median. Whether the engine then falls back to another basis is
   recorded in `alternatives_considered`.
3. **`alternatives_considered` is an audit trail, not a menu.** It records which
   bases were on the table and why the chosen one won.
4. **The multiple has a derivation record too, and it may honestly fail to
   recompute.** When the band's samples are preserved, `trc:valuation_reference`
   declares `{"op": "percentile", "parameters": {"fraction": 0.5}}` and
   recomputes. When the band arrived *without* samples — which is the case for
   every static regression fixture, and for a vendor that publishes only
   summary statistics — the record declares `deterministic: false` with
   `reason: "the band arrived without preserved samples; its statistics are
   themselves sourced, not recomputed here"`.
   This is the only sanctioned `deterministic: false`, and it is the honest
   answer: the median is real, but the arithmetic that produced it happened
   upstream and cannot be re-executed from this document. A consumer that
   requires recomputability checks this flag.
5. **`deterministic: false` requires a reason and is counted.** Acceptance test
   12 recomputes every `deterministic: true` derivation, and separately asserts
   that every `deterministic: false` one carries a non-empty reason. A
   derivation cannot be excused silently.

## 7. CONDITIONAL / IMPLIED

What the current price requires, given the reference.

Every figure here is `provenance_kind: "CONDITIONAL"`. The word is load-bearing:
an implied EPS is not a forecast, it is an arithmetic consequence of a price
and a multiple, and a consumer who reads it as a prediction is misreading it.

```json
"market_implied": {
  "ref": "mic:implied_forward_eps",
  "figure": {"value": 23.34, "unit": "per_share", "currency": "USD",
             "provenance_kind": "CONDITIONAL", "ref": "der:implied_forward_eps"},
  "conditional_statement": "Implied fundamentals are conditional on the selected \
valuation multiple. Price alone does not identify a unique fundamental path.",
  "conditional_on": ["refc:valuation_reference"],
  "derivation_ref": "trc:implied_forward_eps"
}
```

The section-level `conditional_statement` is **required and non-optional**. The
2.2.3 engine already emits this sentence, and 2.3-C promotes it from a field
inside `valuation_reference` to a property of the whole implied block, because
it qualifies every figure in it.

Requirement: **no implied figure may appear without `conditional_on` naming at
least one ref in `valuation_reference`.** A test fails the build otherwise. A
conditional figure whose condition is unstated is a forecast wearing a
disguise, and that is the single failure mode this section exists to prevent.

## 8. DATA QUALITY

Counts and statuses. Never a grade.

```json
"data_quality": {
  "evidence_coverage": {"available": 11, "unavailable": 3, "total": 14},
  "cross_source": {"CONSISTENT": 3, "METHODOLOGY_MISMATCH": 2,
                   "PERIOD_MISMATCH": 1, "DISCREPANT": 0, "UNAVAILABLE": 1},
  "acquisition_errors": [],
  "consensus_forward_eps_period": "+1y",
  "band_eligibility": {"pe": "INSUFFICIENT_OBSERVATIONS",
                       "ps": "INSUFFICIENT_OBSERVATIONS",
                       "pfcf": "UNAVAILABLE", "ev_ebitda": "INSUFFICIENT_OBSERVATIONS"},
  "freshness": {"stale_observations": 0, "oldest_observation_days": 3}
}
```

**No composite number is permitted in this section.** Not a completeness score,
not a confidence, not a 0-to-1 grade, not a letter, not a colour. A single
number standing in for "how good is this data" is an interpretation, it invites
comparison between assets that were not compared, and it hides which specific
weakness is present. A consumer that wants to weigh the evidence reads the
counts and the statuses.

Enforced by a test that scans the serialized `data_quality` object for a
numeric field whose key or whose enclosing key matches a forbidden
vocabulary, and for any 0-to-1 float presented as a grade.

`cross_source` is a tally of the 2.3-B verdicts, not a score. `DISCREPANT: 0`
is good news about a count, not a certificate.

## 9. UNKNOWN / UNAVAILABLE

Every figure that could not be established, with a reason. First-class, not an
afterthought.

```json
"unavailable": [
  {"item": "current_eps", "ref": "obs:ev-current-eps-001",
   "reason": "the source did not report trailing EPS for this instrument",
   "reason_kind": "NOT_REPORTED_BY_SOURCE", "blocks": ["der:required_eps_cagr"]},
  {"item": "historical_pfcf_band", "ref": "obs:ev-pfcf-band-001",
   "reason": "market capitalization and free cash flow were reported in \
different currencies; the ratio was refused rather than computed",
   "reason_kind": "CURRENCY_MISMATCH", "blocks": []},
  {"item": "assets", "ref": null,
   "reason": "the vendor publishes no total-assets counterpart",
   "reason_kind": "NO_COUNTERPART", "blocks": []}
]
```

Three requirements:

1. **`blocks` names the figures that are missing because of this.** An absent
   input is not an isolated fact; it is the reason a dozen other figures are
   null. Making that edge explicit is what lets a consumer answer "why is this
   null?" without reading code.
2. **`reason_kind` is a closed vocabulary**, so reasons can be counted and
   compared across runs.
3. **Absence is never filled.** The same 2.2.3 rule as everywhere else: no
   zero, no median, no carry-forward, no last-known-value substitution.

### 9.1 Unavailability is the research agenda

The 2.3-B verdicts are not only findings; they are a to-do list. Each maps to a
distinct kind of next step, which is what makes this section the most actionable
part of the document.

| Verdict | What it means for the next lookup |
|---|---|
| `DISCREPANT` | two comparable sources disagree: investigate the filings behind both |
| `METHODOLOGY_MISMATCH` | the sources answer different questions: resolve the definitions before comparing anything |
| `PERIOD_MISMATCH` | the values may match but the dates do not: establish which moment each describes |
| `UNAVAILABLE` | the data was never obtained: request it |
| `CURRENCY_MISMATCH` | the concepts cannot be combined: find a same-currency pair |
| `INSUFFICIENT_OBSERVATIONS` | the sample is too thin to support a reference: wait for more periods |

## 10. How provenance is referenced

One flat, addressable table. Every object in the document that a figure depends
on is registered once.

```
provenance.refs["obs:ev-revenue-001"] = { kind: "observation",  ... }
provenance.refs["ev:ev-revenue-001"]  = { kind: "evidence",     ... }
provenance.refs["val:revenue:sec"]    = { kind: "validation",   ... }
provenance.refs["der:implied_forward_eps"] = { kind: "derived", ... }
provenance.refs["refc:valuation_reference"] = { kind: "reference", ... }
```

Ref grammar: `<kind>:<identifier>`, where `<kind>` is one of `obs`, `ev`,
`val`, `der`, `refc`, `mic`. Requirements:

- **Refs are stable across runs for the same inputs**, so a consumer can
  diff two contexts and see which refs changed.
- **A ref appears exactly once.** The full record lives in `refs`; every section
  that mentions it holds only the ref. No duplicated provenance, so no chance
  of two copies disagreeing.
- **No inline provenance objects.** A consumer resolves everything through
  `refs`, which is what makes the graph traversable in one direction.
- **An unknown ref is a hard error**, not a null. A dangling ref means the
  document is corrupt and a consumer must not be left to guess.

## 11. How observations and evidence reference each other

The 2.3-A chain is preserved exactly, and exposed:

```
obs:ev-revenue-001        (SEC XBRL RevenueFromContractWithCustomer... )
  └─ evidence:ev-revenue-001
       └─ validation:val:revenue:sec
            └─ validation:val:revenue:cross_source
```

- An `evidence` ref carries `observation` (its single source) and
  `legacy_row` (the 2.2.3 presentation, explicitly labelled as such).
- A `validation` ref carries `subject` (the observation or pair it judged),
  `status`, `reasons`, and `checked_at`.
- An observation never references its evidence, because evidence is derived
  and an observation is not. The edge is one-way and acyclic by construction.

## 12. How calculations trace their inputs

Covered in §5.1. The summary of the rule:

> Every derived figure declares an operation from a versioned registry, a
> `depends_on` list of refs that all resolve, and a `deterministic` claim that a
> consumer can verify by evaluating the operation.

The user's example, resolved in full:

```
trc:required_eps_cagr
  op: compound_growth_rate
  operands: [der:implied_forward_eps, obs:ev-current-eps-001, refc:horizon_years]
  trc:implied_forward_eps
    op: divide
    operands: [obs:ev-price-001, refc:valuation_reference]
    refc:valuation_reference
      basis: HISTORICAL_MEDIAN
      source: obs:ev-pe-band-001  ->  statistic "median"
```

Four hops from a headline number to a raw observation, each a `ref` lookup and
one registry dispatch, no prose required.

### 12.1 Operation Registry

**The registry is the mechanism that makes "machine-evaluable" true rather than
merely machine-readable.** Without a closed vocabulary, an `operation` field is
a string that promises something; with one, it is a function that can be
dispatched. A derivation whose `op` is not in the registry, or whose `version`
is not supported, is a **hard error** — the document is rejected, not degraded.

An operation is never a name of a Python function, never a URL, never free
text. The registry is implemented in `operation_registry.py` and its
specification is this table.

Each entry declares:

| Field | Meaning |
|---|---|
| `operation_id` | the `op` string |
| `version` | the version of the semantics below |
| `arity` | exact number of operands |
| `accepted_input_units` | units each positional operand may carry |
| `output_unit` | the unit of the result, per the unit table in §12.2 |
| `formula` | the arithmetic, stated so a reimplementation cannot differ |
| `parameters` | named, typed, defaulted arguments carried in the operation record |
| `unit_rules` | how the output unit is determined, and what is rejected |
| `missing_value_rule` | what happens when an operand is unavailable |

**The missing-value rule is uniform and non-negotiable: `PROPAGATE`.** If any
operand is unavailable, the result is unavailable with
`reason_kind = MISSING_INPUT`, and `unavailable.blocks` names the missing ref.
Never zero, never a median, never a carry-forward, never a last-known value.
This is the 2.2.3 `else None` discipline promoted to a declared rule, and
acceptance test 15 asserts the context and the engine agree on every
unavailable figure.

#### Registry v1

| `op` | v | arity | operands | `parameters` | formula | output unit |
|---|---|---|---|---|---|---|
| `divide` | 1 | 2 | numeric, numeric | — | `a / b` | per the unit table |
| `multiply` | 1 | 2 | numeric, numeric | — | `a * b` | per the unit table |
| `add` | 1 | 2 | numeric, numeric | — | `a + b` | the operands' shared unit |
| `subtract` | 1 | 2 | numeric, numeric | — | `a - b` | the operands' shared unit |
| `ratio` | 1 | 2 | numeric, numeric | — | `a / b` | `ratio` |
| `sum_periods` | 1 | 1 | numeric list | — | `sum(x)` | the operand's unit |
| `mean` | 1 | 1 | numeric list | — | `sum(x) / n` | the operand's unit |
| `sample_standard_deviation` | 1 | 1 | numeric list | — | `sqrt(sum((x - mean(x)) ** 2) / (n - 1))` | the operand's unit |
| `median` | 1 | 1 | numeric list | — | the ordinary sample median | the operand's unit |
| `percentile` | 1 | 1 | numeric list | `fraction` (float, 0–1) | linear interpolation at `(n-1)*p` | the operand's unit |
| `percentile_position` | 1 | 2 | numeric, band | — | normalised position of `a` within the band, by linear interpolation between the band keys | the 10–90 position |
| `compound_growth_rate` | 1 | 3 | end, start, years | — | `(end / start) ** (1 / years) - 1` | `ratio` |
| `log_return` | 1 | 2 | from, to | — | `ln(to / from)` | `ratio` |
| `log_returns` | 1 | 1 | price list | — | `[ln(x[i] / x[i-1]) for i in 1..n-1]` | `ratio` (a list) |
| `annualized_volatility` | 1 | 2 | per-period stdev, periods | — | `stdev * sqrt(periods)` | `ratio` |
| `price_return` | 1 | 2 | from, to | — | `to / from - 1` | `ratio` |
| `deviation_from_average` | 1 | 2 | value, average | — | `value / average - 1` | `ratio` |
| `amount_per_share` | 1 | 2 | amount, shares | — | `amount / shares` | `per_share` |
| `shares_from_market_cap` | 1 | 2 | market cap, price | — | `market_cap / price` | `count` |
| `market_cap_from_price_shares` | 1 | 2 | price, shares | — | `price * shares` | `currency` |
| `enterprise_value` | 1 | 2 | market cap, net debt | — | `market_cap + net_debt` | `currency` |

Notes on the harder entries:

- **`percentile` is the forward one** (build a statistic from samples) and
  **`percentile_position` is the inverse** (locate a statistic within a band).
  They are separate operations because conflating them is how a percentile gets
  inverted by accident. `percentile_position` takes the band as its second
  operand, requires the keys `10th`, `25th`, `median`, `75th`, `90th`, and
  returns a position in that same **10–90 space** — the 2.2.3 output field
  means "the 27.5th percentile", not "27.5%". A band that folds back on itself
  is refused, because a percentile read from it is meaningless.
- **List-valued results are legal operands.** `log_returns` returns a list and
  feeds `sample_standard_deviation`, so realised volatility decomposes into
  three checkable steps rather than one opaque summary.
- **`compound_growth_rate` takes years as a ref**, not as a parameter, so the
  horizon is a traced input rather than an ambient assumption. It is the third
  operand. This is deliberate: the horizon materially changes the answer, so it
  belongs in the graph.
- **`amount_per_share` and `shares_from_market_cap` exist because the unit pair
  alone is ambiguous.** A price per share and a valuation multiple per share
  have identical operand units and different meanings, so `divide` refuses that
  pair outright (§12.2) and the caller names the one it means.
- **The last two operations are declared vocabulary, not engine output.**
  `market_cap_from_price_shares` and `enterprise_value` are registered,
  specified, and unit-tested, and each entry carries a `rationale` field so a
  reader can tell a used operation from a declared one. The 2.2.3 engine reads
  enterprise value as observed rather than computing it.

#### Why a registry rather than a function name

If `operation` were `"st_eva.compute_pe"`, then:

- a consumer in another language could not evaluate it;
- renaming a function would silently change the meaning of archived documents;
- a "deterministic recomputation" claim would be unfalsifiable, because the
  thing being checked is the thing being verified.

A versioned, closed vocabulary makes all three failures impossible. When
`percentile` semantics change, that is `percentile` v2, and a v1 document still
evaluates correctly with a v1 evaluator.

### 12.2 Unit table

Unit algebra is a **declared lookup**, not dimensional analysis. Financial units
are conventional rather than physically derived: `multiple` means "a
dimensionless trading multiple" in one role and "currency per count" in another,
and pretending otherwise produces rules nobody can apply. So the table is
explicit, and any pair not in it is a hard error.

For `divide`:

| numerator | denominator | result |
|---|---|---|
| `currency` | `per_share` | `multiple` |
| `currency` | `multiple` | `per_share` |
| `currency` | `currency` | `multiple` |
| `per_share` | `per_share` | `ratio` |
| `multiple` | `multiple` | `ratio` |
| `count` | `count` | `ratio` |

`(currency, count)` is **deliberately absent**. A price per share and a
valuation multiple per share have identical operand units and different
meanings, so the table refuses the pair and the caller must name the one it
means with `amount_per_share` or an explicit multiple operation. A table that
guessed here would be a unit check that only appears to work.

For `multiply`, the result is the numerator's unit for (`currency`, `count`),
`currency` for (`per_share`, `multiple`) and (`multiple`, `per_share`), and
`ratio` for two ratios. For `add` and `subtract`, both operands must share a
unit and the result is that unit.

A pair outside the table is a `UnitRuleError`, which fails the document.

This is the mechanism that catches the mistake of treating a per-share amount
as a multiple. It does **not** catch a TWD amount divided by a USD amount: both
are `currency`, the rule is satisfied, and the fault is in the data rather than
the units. That case is caught by the 2.3-B currency-consistency refusal
instead. Two different mistakes, two different guards, and it is worth being
clear about which catches which.

## 13. Fixing the point-in-time snapshot

Three timestamps, never collapsed, and each answers a different question.

| Field | Question it answers | Source |
|---|---|---|
| `as_of` | what moment is this context about? | the price observation's `as_of` |
| `generated_at` | when was this document built? | the clock at build time |
| `knowledge_cutoff` | what was the latest input knowable? | max `available_at` over all included observations |

`knowledge_cutoff` is the important one. It states the boundary of the
document's knowledge, and it is what makes the context replay-safe: a consumer
can say "this document knows nothing that became public after
2026-09-26T22:30:24Z".

Requirements:

1. **`knowledge_cutoff` is computed, not declared.** It is the maximum
   `available_at` across included observations. A test recomputes it from the
   refs and fails on any mismatch.
2. **No figure may have `as_of` later than the context `as_of`.** A context
   about a moment cannot contain a later-moment fact.
3. **The context is immutable.** Regenerating it produces a new document. It is
   never patched in place.
4. **`content_hash` excludes the when-we-asked fields.** Two builds from the
   same inputs must produce the same `context_id`. Three fields are stripped
   before hashing: `generated_at`, the per-observation `retrieved_at`, and the
   per-validation `checked_at`. All three record *when this process asked*
   rather than *what it learned*, and all three are regenerated on every build.
   Stripping only `generated_at` would leave the identity unstable, which is
   how a "deterministic" guarantee turns out to be untested. If two builds still
   differ, the build is non-deterministic and that is a defect, not a new
   context.

## 14. Revisions and amendments

Handled by the existing 2.3-A/2.3-B machinery; 2.3-C only has to publish it.

1. **A restatement is an additional observation, never an edit.** The same
   `(metric, period)` reported by a later filing produces a new observation
   with a later `available_at`. Both appear in `refs`. A context built at
   cutoff T contains only the observation that was knowable at T.
2. **A later context supersedes an earlier one** through `supersedes`, which
   names the previous `context_id` for the same asset. The chain is a linked
   list, and it is append-only.
3. **A consumer diffing two contexts sees three kinds of change**, and they are
   distinguished because they mean different things:
   - new refs: new data was obtained
   - a ref whose value changed with an unchanged `available_at`: a defect
   - a ref replaced by a later `available_at`: a restatement or a new period
4. **2.3-C does not choose between two restated values.** It publishes both,
   with their availability, and the selection policy belongs to 2.4's replay
   or to the consumer. Consistency with §0.1 of the 2.3-B spec is deliberate.

## 15. Schema versioning

**Two schemas exist, and they are versioned independently. The names say which
is which.**

| Name | Value | Governs |
|---|---|---|
| `legacy_snapshot_schema_version` | `2.2.3` | the frozen 2.2.3 CLI and snapshot JSON. Never changes. |
| `context_schema_version` | `2.3-C.1` | the Investment Context document. |

The legacy 2.2.3 JSON keeps its own `schema_version: "2.2.3"` key, because that
key is part of the frozen byte-compatible output and renaming it would break
every existing consumer. The point of the two explicit names is that **nothing
new may reuse the bare name `schema_version`**, and a reader of any artifact is
never left wondering whether `schema_version: 2.2.3` describes a document that
also contains 2.6-era structures.

Concretely, a snapshot that carries both looks like this, and the naming makes
it unambiguous at a glance:

```json
{
  "schema_version": "2.2.3",
  "data_contract": { "contract_version": "2.3-A" },
  "investment_context": {
    "context_schema_version": "2.3-C.1",
    "built_from": {
      "legacy_snapshot_schema_version": "2.2.3",
      "contract_version": "2.3-A",
      "cross_source_version": "2.3-B"
    }
  }
}
```

| Change to the context | Bump |
|---|---|
| new optional field, new ref kind, new `operation` in the registry, new `reason_kind` | MINOR |
| clarification, new `basis` value, new `parameters` with a default that preserves existing meaning | PATCH |
| removed or renamed field, changed unit of a field, changed `formula` or `missing_value_rule` of an existing operation | MAJOR |

Additional requirements:

- **`min_reader_version` is declared.** A consumer that cannot read a field
  knows from this alone.
- **Unknown fields are ignored, never rejected.** Forward compatibility: a
  consumer written against `2.3-C.0` must read a `2.3-C.3` context without
  failing. A MINOR bump is therefore safe to consume and a MAJOR bump is not.
- **The operation registry is versioned per operation, not per document.** A
  document may legitimately carry `divide` v1 and `percentile` v1 while its own
  version is `2.3-C.4`, and a consumer that supports registry v1 evaluates all
  of it regardless of the document version.
- **`built_from` records the component versions** the context was assembled
  from. A context is only interpretable against the versions that produced it.

## 16. What an agent can see

The context is built so that four questions are answerable from it alone, with
no ST-EVA knowledge required.

| Question | Section |
|---|---|
| "What does the current price require?" | `market_implied` + `valuation_reference`, read together, because every implied figure is conditional on the reference |
| "What supports this?" | `observed` + `validated_evidence` (the `CONSISTENT` verdicts) |
| "What argues against it?" | `validated_evidence` (`DISCREPANT`, `METHODOLOGY_MISMATCH`, `PERIOD_MISMATCH`), and `unavailable.blocks` for the figures that cannot be established |
| "What should I look up next?" | `unavailable` with `reason_kind` and `blocks`, plus `data_quality.acquisition_errors` and `data_quality.band_eligibility` |

The third question is the one that most naive report formats cannot answer.
A report states a conclusion and leaves the reader to guess what was omitted.
The context makes the omissions a queryable list, which is why
`unavailable` is a first-class section rather than a filter.

## 17. What an agent must not be told

An explicit non-claims block, and an enforced vocabulary.

```json
"scope": {
  "provides": [
    "observed values with per-metric provenance",
    "cross-source validation verdicts with their tolerance and basis",
    "deterministic derivations traceable to raw observations",
    "the multiple every implied figure is conditional on",
    "an explicit list of what could not be established, and why"
  ],
  "does_not_provide": [
    "an investment rating, recommendation, or buy/sell/hold view",
    "a price target or any forward price",
    "a probability, likelihood, or confidence for any outcome",
    "a quality score, ranking, or grade of the data or the asset",
    "a comparison against peers, sectors, or other assets",
    "a claim that any value is cheap, expensive, or mispriced",
    "a claim that either data source is authoritative",
    "a forecast; every implied figure is conditional on a stated reference"
  ],
  "authority_note": "Neither source is treated as truth. A CONSISTENT verdict \
means two comparable figures agree within a declared tolerance; it does not \
mean the figure is verified, and independence of the sources is declared \
separately."
}
```

The vocabulary guard: the serialized context is scanned for
`FORBIDDEN_VOCABULARY` (`buy`, `sell`, `hold`, `rating`, `recommend`, `score`,
`probabilit`, `rank`, `target_price`, `bull`, `bear`, `upside`, `downside`,
`overvalued`, `undervalued`, `confidence`) **outside the `does_not_provide`
list**, which is the one place those words are supposed to appear. This
extends the 2.3-A `contract_vocabulary_is_safe()` guard from the vocabulary to
the whole document, which is the only place it actually matters: a token in an
enum is harmless, the same token in a sentence aimed at a model is not.

**Matching is by whole word, not by substring.** This is not a detail. A
substring guard fires on the data's own vocabulary — `shareholders` contains
`hold`, so a perfectly legitimate `trailingNetIncomeCommonStockholders` field
would fail the document — and a guard that cries wolf on real data gets
switched off, which is worse than having no guard at all. Prefixes are used only
for the inflected forms worth catching (`recommend`, `probabilit`).

Note the guard is a backstop, not the mechanism. The mechanism is that the
engine computes nothing that could be a verdict. A vocabulary scan cannot stop a
model from inferring a recommendation from a favourable implied-EPS number;
only the absence of the analysis stops that.

## 18. CLI and JSON backward compatibility

The 2.2.3 contract is frozen. Verified by `Compare-Object` against a captured
pre-2.3 baseline, for MSFT, TENCENT, and NU, plus the rendered report.

Guaranteed unchanged:

- every flag, name, default, and meaning;
- every key in `--json`, at the same position, with the same value;
- `schema_version: "2.2.3"`;
- `evidence_ids` and its order;
- the readable report layout;
- the snapshot filename format.

Additive only:

- a new opt-in flag `--context [PATH]`, plus `--context-sources` choosing which
  acquired sources feed the context. With no `--context`, behaviour and bytes
  are identical to 2.2.3. With `--context -`, the context goes to stdout and
  the normal report is suppressed, so a consumer can pipe it.
- the snapshot gains an `investment_context` key alongside the existing
  `data_contract` block. Both stay additive; `SnapshotManager.update_outcome`
  keeps working.
- a new `context_schema_version` key inside the context, which is *not* a change
  to the frozen `schema_version`.

Forbidden:

- a new required flag;
- any change to a default;
- reordering or renaming an existing key;
- removing `data_contract` from snapshots;
- reusing the bare name `schema_version` for anything new.

## 19. Acceptance tests

Each is objectively checkable. The first eight are the substance of the phase.

1. **Closure.** Every `ref` named anywhere in the document resolves in
   `provenance.refs`. An unresolved ref fails the build.
2. **No dangling or cyclic derivations.** Every `depends_on` target exists, and
   the derivation graph is acyclic. A consumer must be able to walk it
   without looping.
3. **Recomputation.** Evaluating every `operation` against its referenced
   inputs reproduces every stored derived value, within a float tolerance. This
   is the test that makes "every derived number traces back to its inputs" a
   claim rather than a diagram, and it is run against a **real acquisition**,
   not only synthetic observations.
4. **The reference resolves.** `valuation_reference.source_ref` names a real
   observation when `basis` is `HISTORICAL_MEDIAN`, and is `null` when `basis`
   is `USER_SUPPLIED`. A multiple with neither is a failure.
5. **No unavailable figure carries a number.** Every `UNAVAILABLE` figure has no
   `value` key, appears in `unavailable` with a reason, and is counted in
   `evidence_coverage.unavailable`.
6. **No verdict vocabulary outside the non-claims list**, and no numeric grade
   in `data_quality`.
7. **`knowledge_cutoff` is correct.** It equals the maximum `available_at`
   across included observations, and no figure has `as_of` later than the
   context `as_of`.
8. **Every conditional figure is conditioned.** Each figure in `market_implied`
   has a non-empty `conditional_on` naming a ref in `valuation_reference`.
9. **Determinism.** Two builds from the same acquisition produce the same
   `context_id`.
10. **Cross-source verdicts are published.** Every 2.3-B metric appears in
    `validated_evidence` with both observation refs, and `independence` is
    carried through unaltered.
11. **Every operation is in the registry.** Every derivation's `op` exists in the
    registry and its `version` is supported. An unknown operation, or a known
    operation at an unsupported version, fails the document. Additionally, every
    registry entry declares `operation_id`, `version`, arity, accepted input
    units, output unit, formula, parameters, unit rules, and missing-value
    rules, and every entry's arity and unit rules are unit-tested.
12. **Every derivation recomputes, and matches.** Evaluating each `operation`
    through the registry reproduces the stored value within the contract
    tolerance, for synthetic observations and for at least one real
    acquisition.
13. **Engine parity on unavailability.** Every figure the engine computed as
    absent is `UNAVAILABLE` in the context with a `MISSING_INPUT` or
    `NOT_REPORTED_BY_SOURCE` reason, and every figure the engine computed is
    present. The context invents no figure and drops none.
14. **Round-trip.** `context -> dict -> json -> dict -> context` loses
    nothing.
15. **Byte compatibility.** The 2.2.3 `--json` and report are identical with and
    without `--context`.
16. **Regression.** All 136 existing tests still pass, including the 2.2.3
    regression suite and the 2.3-A contract tests.
17. **A real run is published.** A context is generated for at least one live
    acquisition and for all three regression fixtures, and the derived
    recomputation test passes on all of them.

## 20. Stop condition

2.3-C is complete when the document exists, the type is implemented, the
derivations recompute, and the fourteen acceptance tests hold.

Work stops there. No 2.4, no archive, no agent experiments, no new metric, no
new source, no score.

The result of 2.2.3 through 2.3-C is the pipeline the next phases are built on:

```
Data -> Observation -> Evidence -> Validation -> Derived -> Market-Implied
     -> InvestmentContext
```

At that point the same context can be handed to different agents to be asked
the same question, which is the first honest test of the claim that ST-EVA
formalises the world reliably enough that the remaining intelligence can be
delegated. 2.4 makes contexts replayable over time; 2.5 runs that experiment.
Neither is started here.
