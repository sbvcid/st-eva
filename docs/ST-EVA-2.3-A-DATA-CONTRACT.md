# ST-EVA 2.3-A — Data Contract & Architecture Refactor

Status: IN PROGRESS
Target: 2.3-A
Baseline: 2.2.3
Repository: sbvcid/st-eva
Implements phase 1 (and the phase-2 adapter migration) of
[docs/ST-EVA-2.3-PLAN.md](ST-EVA-2.3-PLAN.md)

## 1. Purpose

2.2.3 carries a provider-shaped data model. The Yahoo adapter emits field names
that only make sense for Yahoo (`trailingEps`, `+1y`, `trailingPeRatio`), the
engine reads a flat bag of `UNAVAILABLE` sentinels, and provenance is
synthesized *after* the data has already been consumed.

2.3-A replaces that with an explicit, provider-agnostic data contract:

```
Provider
  -> Observation        (raw, immutable, provider-agnostic)
  -> Evidence           (provenance + identity, references the observation)
  -> Validation         (explicit ValidationStatus, never mutates the value)
  -> Derived            (deterministic function of identified observations)
```

2.3-A is a *structural* refactor. It changes the shape of the data and where it
comes from. It does not change what the engine calculates, and it does not
change what the CLI prints.

## 2. Scope of 2.3-A

In scope:

1. Provider-agnostic `Observation` data contract.
2. `Evidence` / provenance model.
3. Explicit `ValidationStatus`.
4. Raw observation preservation.
5. Deterministic recomputation of derived values from raw observations.
6. Migration of the Yahoo adapter onto the new types.
7. Decoupling of the valuation engine from provider structure.
8. Unit tests for the contract.

Explicitly **out of scope for 2.3-A** (do not implement, do not stub in):

- A second data source. No provider other than Yahoo.
- An external `st-data` repository. The contract lives in this repository.
- A/B comparison, cross-source agreement scoring, or consensus building.
- Ranking, scores, probabilities, buy/sell/hold output.
- Any new valuation model, formula, or reference-selection policy.
- Staleness enforcement in the CLI output (the status exists; 2.3-A computes it
  on observations, and does not change the `data_quality` block).
- Any change to the 2.2.3 CLI flags, JSON keys, JSON values, or report layout.

2.3-B picks up at cross-source validation. 2.3-A must leave a clean seam for it
and must not pre-build it.

## 3. Layer definitions

### 3.1 Provider

A module that acquires data and nothing else. A provider may not calculate
valuation ratios, fill missing fields, or select a reference.

A provider's only permitted outputs are `Observation` objects, acquisition
errors, and a retrieval timestamp.

### 3.2 Observation

The smallest unit of sourced data: one metric, one value, one provenance
record. An observation is immutable. An observation is never edited, normalized
into a different value, or replaced by a validation outcome.

### 3.3 Evidence

The engine-facing identity of a material input. Evidence binds an
`observation_id` to a stable `evidence_id`, carries the validation outcome, and
records the engine-level role of the value. Evidence is what the engine
consumes; the observation is what the provider reported.

### 3.4 Validation

A pure function from an observation to a `ValidationStatus` plus reasons.
Validation never assigns a value, never coerces a type, and never edits the
observation it inspects. When a value fails validation it stays exactly as
reported and is *labelled*, not *repaired*.

### 3.5 Derived

Any value produced by a deterministic function of identified observations.
Every derived value records the `observation_id`s it consumed and the method
used, so it can be recomputed from the raw observations.

## 4. The `Observation` contract

Implemented in `data_contract.py` as a frozen dataclass. Frozen is the
enforcement mechanism for rule 5: a validation pass cannot write to it.

| Field | Type | Required | Meaning |
|---|---|---|---|
| `observation_id` | `str` | yes | Stable identity. Unique within an `ObservationSet`. The canonical material inputs use the 2.2.3 evidence IDs (see §4.2). |
| `metric` | `str` | yes | Canonical metric name, provider-agnostic. Must be one of `CONTRACT_METRICS` (§4.1). |
| `value` | `Any` | yes | The value exactly as the provider reported it. `None` means *not available*; `None` is never replaced by `0`, a median, or a guess. |
| `unit` | `str` | yes | One of `CONTRACT_UNITS` (§4.3). |
| `currency` | `Optional[str]` | yes | ISO-4217 code the value is denominated in, or `None` when the unit is dimensionless. |
| `currency_basis` | `str` | yes | How `currency` was determined. One of `CURRENCY_BASES` (§4.4). |
| `period_start` | `Optional[str]` | yes | Inclusive start of the period the value describes, ISO-8601 date. `None` for point-in-time values. |
| `period_end` | `Optional[str]` | yes | Inclusive end of that period. `None` for point-in-time values. |
| `as_of` | `Optional[str]` | yes | The date the value describes. For a trailing-twelve-month figure this is the period end, not the retrieval date. |
| `available_at` | `Optional[str]` | yes | The earliest instant the value was knowable to the market. `None` when the provider does not disclose it. Never earlier than `as_of` when both are present. |
| `available_at_basis` | `str` | yes | How `available_at` was determined. One of `AVAILABILITY_BASES` (§4.5). |
| `provider` | `str` | yes | The adapter that produced the value, e.g. `YahooFinanceFundamentals`. |
| `source_type` | `str` | yes | One of `CONTRACT_SOURCE_TYPES` (§4.6). |
| `source_url` | `Optional[str]` | yes | The endpoint or document the value came from. `None` when none is available. |
| `definition` | `str` | yes | What the metric means, in provider-agnostic words. Must not name a provider field. |
| `methodology` | `str` | yes | How the value was produced, e.g. the exact upstream field or the distribution method. |
| `retrieved_at` | `str` | yes | UTC ISO-8601 instant of acquisition. |
| `raw` | `Any` | no | The provider payload the value was read from. Preserved verbatim. This is what makes recomputation possible. |
| `observation_count` | `Optional[int]` | yes | Sample size, for distribution metrics only. `None` for scalar metrics. |
| `status` | `ValidationStatus` | yes | Acquisition-time status assigned by the provider (§5.1). |
| `status_reasons` | `Tuple[str, ...]` | yes | Why the acquisition-time status was assigned. |
| `inputs` | `Tuple[str, ...]` | yes | `observation_id`s consumed to produce this value. Empty for directly sourced values. |

### 4.1 Canonical metrics (`CONTRACT_METRICS`)

`price`, `price_history`, `volume_history`, `trailing_eps`, `forward_eps`,
`consensus_forward_eps`, `pe_band`, `pfcf_band`, `ps_band`, `ev_ebitda_band`,
`free_cash_flow`, `ebitda`, `revenue`, `enterprise_value`, `market_cap`,
`price_volume_metrics`.

A provider-specific name such as `trailingPeRatio` is not a metric. It is the
`methodology` of the `pe_band` observation.

### 4.2 Canonical observation IDs (`CONTRACT_OBSERVATION_IDS`)

Material inputs keep their 2.2.3 evidence IDs so the JSON `evidence_ids` array
and the snapshot `evidence` block stay byte-identical:

| Metric | `observation_id` |
|---|---|
| `price` | `ev-price-001` |
| `trailing_eps` | `ev-current-eps-001` |
| `forward_eps` | `ev-forward-eps-001` |
| `consensus_forward_eps` | `ev-consensus-eps-001` |
| `pe_band` | `ev-pe-band-001` |
| `pfcf_band` | `ev-pfcf-band-001` |
| `ps_band` | `ev-ps-band-001` |
| `ev_ebitda_band` | `ev-ev-ebitda-band-001` |
| `free_cash_flow` | `ev-fcf-001` |
| `ebitda` | `ev-ebitda-001` |
| `revenue` | `ev-revenue-001` |
| `enterprise_value` | `ev-enterprise-value-001` |
| `market_cap` | `ev-market-cap-001` |
| `price_volume_metrics` | `ev-metrics-001` |

`price_history` and `volume_history` are not evidence in 2.2.3 and are not
material inputs. They are still observations, because `price_volume_metrics`
must be recomputable from them. They use `obs-price-history-001` and
`obs-volume-history-001`, and they are not listed in `evidence_ids`.

### 4.3 Units (`CONTRACT_UNITS`)

`currency`, `per_share`, `multiple`, `ratio`, `count`.

A valuation band is `multiple`, never `currency`. The 2.2.3 defect of stamping
the instrument currency onto a multiple is not carried forward.

### 4.4 Currency bases (`CURRENCY_BASES`)

| Value | Meaning |
|---|---|
| `REPORTED` | The source stated the currency for this value. |
| `INSTRUMENT_DEFAULT` | The source did not state a currency; the instrument's quote currency is applied, and the basis is recorded so the assumption is visible. |
| `UNDECLARED` | No currency is known for this value. The observation is not usable in a ratio. |
| `NOT_APPLICABLE` | The value is dimensionless. `currency` is `None`. |

`INSTRUMENT_DEFAULT` is used for per-share figures, where Yahoo exposes EPS
without a currency. It is a declared, auditable default, not a silent one.

### 4.5 Availability bases (`AVAILABILITY_BASES`)

| Value | Meaning |
|---|---|
| `REPORTED` | The source stated when the value became available. |
| `OBSERVATION_INSTANT` | The value is a market observation whose `as_of` is the instant it is available (a daily close). |
| `UNDECLARED` | The source does not disclose availability. `available_at` is `None`. |

`UNDECLARED` is the honest state for a trailing EPS or a band sample. It is
recorded rather than back-filled with the retrieval time, because a retrieval
time is not a publication time. This is what makes the point-in-time gap
visible to 2.3-B.

### 4.6 Source types (`CONTRACT_SOURCE_TYPES`)

| `SourceType.API_LIVE`, `SourceType.REGRESSION_FIXTURE`, `SourceType.DETERMINISTIC_CALCULATION`, `SourceType.USER_SUPPLIED` | identity, for 2.2.3 |
| `SourceType.REGULATORY_FILING` | Added in 2.3-B. A value from an official filing rather than a vendor. |
| `AvailabilityBasis.ACCEPTANCE_DATETIME` | Added in 2.3-B. SEC EDGAR acceptance instant. |
| `AvailabilityBasis.FILED_AS_OF_DATE` | Added in 2.3-B. SEC filed date, time of day not published. |

The strings are identical to 2.2.3 so existing output does not change.

## 5. Validation

### 5.1 `ValidationStatus`

| Status | Assigned when |
|---|---|
| `UNAVAILABLE` | The provider was asked for the metric and did not return a value. |
| `UNVERIFIABLE` | A value was acquired from a single live source. One source cannot cross-validate itself, so it is never presented as verified. |
| `SINGLE_SOURCE` | A value was acquired from a single static source that declares itself as a fixture. |
| `INSUFFICIENT_OBSERVATIONS` | A distribution carries fewer than `MIN_BAND_OBSERVATIONS_FOR_REFERENCE` (20) usable samples. |
| `STALE` | `available_at` is older than the configured freshness window. |
| `CURRENCY_MISMATCH` | Numerator and denominator currencies differ, or a required currency is missing. |
| `PERIOD_INVALID` | `period_start` is later than `period_end`, or `available_at` precedes `as_of`. |
| `MISSING_METADATA` | A required contract field is absent. |
| `DUPLICATE_OBSERVATION` | Another observation with the same `observation_id` was offered to the same set. |
| `VALID` | The value passed every check applied to it. |
| `PERIOD_MISMATCH` | Added in 2.3-B. Two sources' period anchors are too far apart to describe the same window. |
| `VERIFIED` | Reserved for 2.3-B cross-source agreement. Not computed. |
| `CONSISTENT` | Added in 2.3-B. Two comparable sources agree within tolerance. |
| `DISCREPANT` | Added in 2.3-B. Two comparable sources disagree beyond tolerance. |
| `METHODOLOGY_MISMATCH` | Added in 2.3-B. The two sources measure different quantities under the same name. |

`VERIFIED`, `CONSISTENT`, `DISCREPANT`, and `METHODOLOGY_MISMATCH` are declared
so the vocabulary is complete and stable, and 2.3-A never produces them:
doing so would require a second source, which is out of scope for 2.3-A.
2.3-B computes `CONSISTENT`, `DISCREPANT`, `METHODOLOGY_MISMATCH`, and
`PERIOD_MISMATCH`, and still does not produce `VERIFIED`; see
[docs/ST-EVA-2.3-B-SEC-VALIDATION.md](ST-EVA-2.3-B-SEC-VALIDATION.md) §2.2 for
why a two-source agreement is not automatically verification.

These are evidence states. They are not ratings, scores, or recommendations.

### 5.2 Validation is a separate object

Validation returns a `ValidationRecord(status, reasons, checked_at)`. It is
attached to `Evidence`, not written back into `Observation`.

`Evidence.status` is the escalation of the two: the more severe of the
acquisition status and the validation status. Escalation only ever adds a
label. The value is untouched.

### 5.3 Deterministic evaluation

`validate_observation(observation, now=...)` takes `now` as an argument. It never
calls the clock, so a validation result is reproducible.

## 6. Raw preservation and recomputation

Rule 5 and rule 6 are implemented as follows.

- `Observation` is a frozen dataclass. Any attempt to assign raises
  `FrozenInstanceError`. There is no code path that edits `value`.
- `Observation.raw` keeps the provider payload, including the full sample list
  behind every band and the full price/volume series behind `ev-metrics-001`.
- Two recomputation functions are provided, and both are pure:
  - `recompute_distribution(observation)` rebuilds a band from
    `raw["samples"]` using the documented percentile method.
  - `recompute_price_volume_metrics(observation)` rebuilds the price/volume
    metrics from `raw["prices"]` and `raw["volumes"]`.
- A test asserts `recompute_distribution(obs) == obs.value` and
  `recompute_price_volume_metrics(obs) == obs.value`. If those hold, no
  derived value in 2.3-A depends on a discarded intermediate.
- `DerivedValue` records `method`, `inputs`, and `deterministic=True`, so any
  other derived figure is traceable to the observations and the formula that
  produced it.

Percentile method for a band, stated so it can be re-implemented exactly:
sort ascending, then linear interpolation at position `(n - 1) * p` between the
floor and ceiling indices. The median is the ordinary sample median. Both are
the 2.2.3 method, unchanged.

## 7. Evidence

`Evidence` binds:

- `evidence_id` — the engine-facing identity, equal to `observation_id` for
  material inputs.
- `observation` — the immutable observation carrying the value and provenance.
- `validation` — the `ValidationRecord` from §5.
- presentation fields kept from 2.2.3 so the snapshot block does not change:
  `source`, `quality`, `traceability`.

`EvidenceStore` rules:

- `add` rejects a duplicate `evidence_id`. A duplicate identity is a defect.
- Duplicate *metric* values are **not** rejected and **not** de-duplicated.
  Two providers reporting the same metric is a real-world fact that 2.3-B
  needs; collapsing it here would destroy the evidence.

## 8. Provider adapter rules

An adapter must:

1. Emit `Observation` objects. It must not emit a provider-shaped struct that
   the engine reads directly.
2. Keep the raw payload in `Observation.raw`.
3. Set `available_at` to `None` with basis `UNDECLARED` rather than inventing a
   publication time.
4. Report `UNAVAILABLE` for a metric it asked for and did not receive. It must
   not substitute a related metric, a median, or a zero.
5. Report its failures. A swallowed provider error is a defect.
6. Compute no valuation ratio and select no reference.
7. Keep currency consistency protection: a ratio whose numerator and
   denominator currencies differ is `UNAVAILABLE` with reason
   `CURRENCY_MISMATCH`, not a computed number.

An adapter must not:

- depend on any other provider's types;
- be imported by the valuation engine;
- be given a second source, a ranking, a score, or a comparison target.

## 9. Engine boundary

The valuation engine consumes `ValuationInputs`, a provider-agnostic frozen
projection of the material observations. `ValuationInputs` names metrics and
values. It contains no provider field names, no provider URLs, and no wire
structures.

`ValuationInputs.from_observations(...)` builds it from an `ObservationSet`.
`ValuationInputs.from_legacy_view(...)` is a compatibility shim over the 2.2.3
`MarketData` attribute surface, used so that existing callers and tests that
construct or mutate `MarketData` keep working. It reads attributes by name and
imports nothing, so the dependency direction stays one-way:
`st_eva_runner` -> `data_contract`, never the reverse.

A test asserts the engine produces identical numbers from a
`ValuationInputs` built purely from observations as from a `MarketData` view.

## 10. Compatibility guarantees for 2.3-A

Guaranteed unchanged:

- every CLI flag, its name, default, and meaning;
- every key in the `--json` result, at the same position, with the same value;
- `evidence_ids` and its order;
- the readable report layout;
- the snapshot filename format;
- every 2.2.3 regression test.

Additive only:

- `history/*.json` snapshots gain a `data_contract` block. The existing
  `evidence` block is untouched. Snapshots are append-only artifacts, not the
  machine-readable contract, and `SnapshotManager.update_outcome` keeps
  working unchanged.

Deliberately not changed, and tracked for 2.3-B:

- `data_quality.discrepancy_status` keeps emitting `SINGLE_SOURCE`,
  `UNVERIFIABLE`, or `DATA_DISCREPANCY`. All three are `ValidationStatus`
  values, so the string is now typed without changing.
- The `as_of` field of a 2.2.3 evidence row is the price date for every row.
  This is a 2.2.3 simplification. The contract's real per-metric `as_of` is
  carried in the `data_contract` block, and the legacy row is left alone so no
  existing snapshot changes meaning.

## 11. Migration map

| 2.2.3 | 2.3-A |
|---|---|
| `FundamentalData.current_eps` | `Observation(metric="trailing_eps").value` |
| `FundamentalData.forward_eps` | `Observation(metric="forward_eps").value` |
| `FundamentalData.consensus_forward_eps` | `Observation(metric="consensus_forward_eps").value` |
| `FundamentalData.consensus_forward_eps_period` | `Observation.raw["period"]`, plus `period_start`/`period_end` where the source gives them |
| `FundamentalData.current_fcf` | `Observation(metric="free_cash_flow").value` |
| `FundamentalData.current_*_currency` | `Observation.currency` + `currency_basis` |
| `FundamentalData.current_*_as_of` | `Observation.as_of` |
| `FundamentalData.historical_pe_band` | `Observation(metric="pe_band").value`, with `raw["samples"]` retained |
| `FundamentalData.source_urls` | per-observation `source_url` |
| `FundamentalData.errors` | unchanged; carried into `data_quality.acquisition_errors` |
| `MarketData` | legacy engine view over an `ObservationSet` |
| `Evidence` built in `build_evidence` | `Evidence` wrapping a provider observation |
| `MarketImpliedAssumptionsEngine.analyze(MarketData)` | `analyze(ValuationInputs or MarketData)` |

`FundamentalData` is retained as a deprecated projection of an `ObservationSet`
so the four 2.2.3 provider tests keep asserting against a familiar shape. It is
no longer the provider's output type.

## 12. Test matrix for 2.3-A

New file `tests/test_data_contract.py`:

1. Observation is frozen; a validation pass cannot change the value.
2. `period_start` / `period_end` round-trip and are validated for ordering.
3. `available_at` is `None` + `UNDECLARED` when the provider hides it, and
   never precedes `as_of` when declared.
4. `currency` is recorded per observation, is `None` for a multiple, and a
   currency mismatch is refused rather than computed.
5. Provenance survives: provider, source type, source URL, definition,
   methodology, and retrieval time reach the serialized contract.
6. Missing data stays `UNAVAILABLE`; the engine output is `null`, not a guess.
7. Duplicate `observation_id` is refused; a duplicate metric from two providers
   is preserved, not overwritten; duplicate `evidence_id` is refused.
8. `recompute_distribution` and `recompute_price_volume_metrics` reproduce the
   stored value.
9. The engine is identical from `ValuationInputs` and from `MarketData`.
10. The Yahoo adapter emits `Observation` objects for every material metric.

## 13. Stop condition

2.3-A is complete when the contract document, the types, the migrated Yahoo
adapter, the new tests, and the compatibility guarantees above are all in place
and the full suite passes.

Work stops there. Cross-source validation, a second provider, and the
OBSERVED/REFERENCE/IMPLIED/COMPARISON/INTERPRETATION output split are 2.3-B.
