# ST-EVA — Reverse Valuation & Market-Implied Expectations Engine

ST-EVA takes an observed market price and reverse-engineers the fundamental and valuation assumptions implied by that price, using explicit valuation references and auditable evidence.

It is a deterministic calculation with a traceable result. It is not a forecast, and it does not recommend anything.

## What it asks

A quoted price is a compressed verdict. At a given P/E multiple, the market is implicitly asserting some forward EPS. ST-EVA makes that assertion explicit and computable: given a price and a named reference multiple, what earnings, growth, revenue or margin does that price require?

So the object of study is the assumption, not the asset. The output is a set of market-implied assumptions tied to the reference they were computed against. 「目前價格反映了什麼假設？」 — what assumptions is the current price reflecting?

## Input → output

```
observed price + explicit valuation reference (P/E, P/FCF, EV/EBITDA, P/S)
        ↓
reverse valuation arithmetic
        ↓
market-implied assumptions: forward EPS, required EPS CAGR, EPS gap vs consensus,
implied FCF / EBITDA / revenue, implied net margin
        ↓
auditable JSON — every figure names the observation and the operation behind it
```

The engine is not a DCF calculator and does not project free cash flows forward. It does not generate price targets, scenario ranges, probabilities, or buy/sell calls. It describes what a price already implies, and says which reference it assumed.

## Core calculation

For current price P0 and reference P/E multiple M:

Implied Forward EPS = P0 / M

If current EPS is available:

Required EPS CAGR = (Implied Forward EPS / Current EPS) ^ (1 / T) - 1

If consensus forward EPS is available:

EPS Gap = Implied Forward EPS / Consensus Forward EPS - 1

The word "implied" is conditional. Price alone cannot identify one unique future EPS or growth path.

## What the engine reports

- Current price and provenance.
- Current P/E when current EPS is available.
- Forward P/E when forward EPS is available.
- Consensus forward P/E when consensus EPS is available.
- Historical P/E band.
- Current P/FCF, EV/EBITDA, and P/S when source inputs are available.
- Historical P/S, P/FCF, and EV/EBITDA bands when observed Yahoo valuation time series are available.
- Implied FCF, EBITDA, and revenue under explicit reference multiples.
- Implied net margin when P/E and P/S references can be combined.
- Approximate position inside the historical P/E band.
- Forward EPS implied by the selected valuation multiple.
- EPS gap between implied EPS and consensus EPS.
- EPS CAGR required from current EPS.
- Price implied by consensus EPS at the historical median P/E.
- Price and volume statistics.
- Missing data.
- Evidence IDs.
- An immutable-at-application-level research snapshot.

## What it does not do

ST-EVA does not:

- invent EPS;
- invent consensus estimates;
- invent probability weights;
- invent Bull/Base/Bear target prices;
- use arbitrary price multipliers when fundamentals are unavailable;
- output a buy/sell stance;
- claim that one P/E multiple is objectively what the market assumes;
- ask an LLM to perform valuation arithmetic.

An optional provider-agnostic LLM interpretation adapter is included in `llm_interpreter.py`. It receives the validated JSON and interprets it without performing valuation arithmetic. The calculation core remains deterministic Python.

## Data categories

OBSERVED:
Data supplied by a market-data provider or explicit test fixture.

DERIVED:
Deterministic calculations from observed inputs.

CONDITIONAL_INFERENCE:
Reverse-engineered assumptions that depend on an explicit valuation reference.

UNAVAILABLE:
A required input that has not been sourced. It is never guessed.

## Valuation references

P/E priority:

1. User-supplied P/E reference.
2. Historical P/E median.
3. No reference.

P/FCF, EV/EBITDA, and P/S references can be supplied explicitly. EV/EBITDA and P/S also fall back to their observed historical median when available. P/FCF historical bands are derived only when market-cap and trailing FCF observations can be matched by date.

### Historical band quality gate

A historical band can only act as a valuation reference when it carries enough
observations to support a percentile reading. The threshold is
`MIN_BAND_OBSERVATIONS_FOR_REFERENCE` (20).

A band below that threshold is still reported under `observed_valuation`, but it:

- is not used as a reference multiple;
- does not produce an `approx_historical_*_percentile` reading;
- is reported as `DESCRIPTIVE_ONLY_INSUFFICIENT_OBSERVATIONS` in
  `reference.historical_band_status`.

A numerically precise band built from too few points is not trustworthy, and the
engine will not treat it as though it were. This is the defect behind the NU case
recorded in [docs/ST-EVA-2.3-PLAN.md](docs/ST-EVA-2.3-PLAN.md).

Bands that declare no `observations` count at all are treated as usable, which
preserves static regression fixtures.

## Data quality reporting

Every run emits a `data_quality` block:

```json
"data_quality": {
  "discrepancy_status": "UNVERIFIABLE",
  "acquisition_errors": [],
  "consensus_forward_eps_period": "+1y"
}
```

`discrepancy_status` is an evidence state, not an investment rating. A live
single-provider acquisition is reported as `UNVERIFIABLE` because a single source
cannot cross-validate itself. Provider failures are surfaced in
`acquisition_errors` instead of being silently swallowed.

## Usage

ST-EVA has no third-party dependencies and no API key. Python 3.9+ is sufficient.
Give it a ticker and it prints the result.

```powershell
python st_eva_runner.py 0700.HK --mode live --no-snapshot
```

The default output is a readable report. Use `--json` for the machine-readable
schema, and `--test` to run the built-in regression suite.

```powershell
python st_eva_runner.py --test
python -m unittest discover -s tests
python st_eva_runner.py AAPL --mode live --reference-multiple 30
```

Company names are accepted (`蘋果`, `騰訊`, `台積電`, `apple`). Treat
`--reference-multiple` as a required argument in practice: a historical band is
only adopted automatically when it carries enough observations.

See [docs/USAGE.md](docs/USAGE.md) for the full workflow, output reference,
multi-method reverse valuation, snapshot tracking, and LLM interpretation.

## Fundamental data provider

Live mode now uses a separate `YahooFundamentalProvider` for source financial data. It attempts to acquire trailing EPS, forward EPS, forward-year consensus EPS from Yahoo earnings estimates, and an observed historical trailing P/E distribution from Yahoo fundamentals time series. Missing fields remain unavailable.

The provider does not synthesize consensus from forward EPS and does not invent historical valuation ranges. Historical P/E, P/S, and EV/EBITDA bands are descriptive statistics calculated only from retrieved observations. Current FCF, EBITDA, revenue, enterprise value, and market cap are sourced from Yahoo fundamentals time series when available.

## Repository layout

```
st_eva_runner.py        engine, CLI, validation, snapshots
data_contract.py        provider-agnostic Observation / Evidence / Validation
sec_provider.py         SEC EDGAR adapter (2.3-B second source)
cross_validation.py     cross-source comparability policy (2.3-B)
operation_registry.py   versioned arithmetic vocabulary (2.3-C)
investment_context.py   the agent-consumable context document (2.3-C)
archive.py              archive interface + point-in-time replay driver (2.4)
sqlite_archive.py       SQLite archive implementation (2.4)
archive/migrations/     forward-only schema migrations (2.4 / 2.4.1)
fundamental_provider.py Yahoo fundamental acquisition adapter
llm_interpreter.py      optional non-arithmetic LLM adapter
tests/                  unittest suite
history/                current engine snapshots
history/legacy-v6/      pre-2.2 artifacts, retained but not current output
docs/                   version plans
```

## Architecture

Observed Market Data
        |
        v
Observation            frozen, provider-agnostic, raw payload preserved
        |
        v
Evidence               provenance plus a stable engine identity
        |
        v
Validation             explicit ValidationStatus; labels, never edits
        |
        v
ValuationInputs        provider-agnostic engine input surface
        |
        v
Deterministic Metrics
        |
        v
Reverse Valuation Engine
        |
        +--> Historical P/E reference
        |
        +--> Consensus EPS cross-check
        |
        +--> Required EPS / CAGR
        |
        v
Validator
        |
        v
Machine-readable JSON
        |
        v
Immutable-at-application-level Snapshot
        |
        +--> data_contract block (2.3-A, additive)

The data contract is specified in
[docs/ST-EVA-2.3-A-DATA-CONTRACT.md](docs/ST-EVA-2.3-A-DATA-CONTRACT.md).
The engine reads `ValuationInputs`, which carries no provider field names, so
the calculation core does not depend on Yahoo's structure. A Yahoo field name
such as `trailingEps` survives only as the `methodology` of an observation.

Two rules the data layer enforces:

- A raw observation is never overwritten. Validation attaches a status; it
  cannot write a value, and `Observation` is frozen so it cannot be edited.
- Derived values are recomputable. A valuation band keeps the samples it was
  computed from and the price/volume metrics keep the series they came from, so
  a stored median or ratio can be recomputed rather than trusted.

The CLI, the JSON keys and values, and the readable report are unchanged from
2.2.3. The snapshot gains one additive `data_contract` block; the existing
snapshot keys are untouched.

## Testing

The regression fixtures are static test data. They are not live prices.

The test suite checks:

- reverse-valuation arithmetic;
- evidence integrity;
- zero synthetic financial data;
- missing-data behavior;
- unknown-ticker handling;
- observation provenance: period, currency, availability, and raw preservation;
- validation semantics, including duplicate evidence and duplicate metrics;
- deterministic recomputation of derived values;
- the provider-agnostic engine boundary;
- second-source comparability: the discrete-fact filter, trailing-window
  construction, period alignment, tolerance, and the no-merge guarantee.

Live adapter tests are opt-in, because the SEC's fair-access policy and a
deterministic unit suite do not mix:

```powershell
$env:ST_EVA_LIVE = "1"; python -m unittest tests.test_sec_validation.TestLiveAdapters
```

## Cross-source validation (2.3-B)

The SEC is a second source, used to cross-check seven metrics: revenue,
net income, diluted EPS, total assets, cash, debt, and shares outstanding.

```python
from cross_validation import cross_validate_all
from fundamental_provider import YahooFundamentalProvider
from sec_provider import SECProvider

sec = SECProvider().fetch('AAPL')
yahoo = YahooFundamentalProvider().fetch_acquisition('AAPL', instrument_currency='USD')
results = cross_validate_all(yahoo.observations, sec.observations)

for metric, result in results.items():
    print(metric, result.status.value)
    print('  ', result.validation.explanation)
```

A comparison produces a third object and **replaces neither side**. There is
no merge, no average, and no winner selection anywhere in the comparison path,
and a test asserts the absence of one. A real run of the seven metrics:

```
revenue           CONSISTENT            both trailing, 3 days apart
net_income        CONSISTENT            both trailing, 3 days apart
eps_diluted       CONSISTENT            both trailing, 3 days apart
assets            UNAVAILABLE           the vendor publishes no total assets
cash              METHODOLOGY_MISMATCH  vendor total cash includes short-term
                                        investments; the filing concept does not
debt              METHODOLOGY_MISMATCH  no single total-debt concept exists
shares_outstanding PERIOD_MISMATCH      identical values, but the vendor
                                        states no date
```

Three of seven reach a numeric verdict. The other four are classified rather
than forced, which is the point: a comparison that reports a difference
between two figures that answer different questions is worse than no
comparison, because it teaches a reader to ignore the real findings.

Specified in
[docs/ST-EVA-2.3-B-SEC-VALIDATION.md](docs/ST-EVA-2.3-B-SEC-VALIDATION.md).

## Investment Context (2.3-C)

The opt-in `--context` flag writes a single document that any consumer can read
and check, without knowing how ST-EVA is built.

```powershell
python st_eva_runner.py AAPL --context ctx.json      # add the context
python st_eva_runner.py AAPL --context -            # context to stdout
python st_eva_runner.py AAPL                        # unchanged from 2.2.3
```

Without `--context` the output is byte-identical to 2.2.3.

Every derived figure names an operation from a versioned registry, so a
consumer can re-derive it:

```
der:required_eps_cagr
  op: compound_growth_rate
  operands: [der:implied_forward_eps, obs:ev-current-eps-001, refc:horizon_years]
    der:implied_forward_eps
      op: divide
      operands: [obs:ev-price-001, refc:valuation_reference]
        refc:valuation_reference
          basis: HISTORICAL_MEDIAN
          source_ref: obs:ev-pe-band-001
```

Four hops from a headline number to a raw observation, each a ref lookup and
one registry dispatch, no prose required. The registry is embedded in the
document, so a consumer can read the formulas and check the work itself.

The document states what it is not: no rating, no probability, no score, no
target price, no peer comparison. `data_quality` carries counts and statuses
and never a grade, because a single number standing in for "how good is this
data" is an interpretation.

`unavailable` is a research agenda rather than a filter:

```
trailing_eps   NOT_REPORTED_BY_SOURCE   blocks=[der:current_pe, der:required_eps_cagr]
```

Specified in
[docs/ST-EVA-2.3-C-INVESTMENT-CONTEXT.md](docs/ST-EVA-2.3-C-INVESTMENT-CONTEXT.md).

## Point-in-time archive and replay (2.4)

Opt-in. With no `--archive` flag nothing changes.

```powershell
python st_eva_runner.py AAPL --context ctx.json --archive data/st-eva.sqlite
```

```python
from archive import replay
from sqlite_archive import SQLiteArchive
from st_eva_runner import build_context_from_observations

store = SQLiteArchive("data/st-eva.sqlite")
result = replay(store, "AAPL, as_of, build_context_from_observations")
print(result.outcome)          # MATCH | DIVERGED | NO_SNAPSHOT | INSUFFICIENT
print(result.replay_fidelity)  # SOURCE_DECLARED | OBSERVATIONAL
```

The outcome vocabulary matters more than it looks. `INSUFFICIENT` is a
**successful** replay: it means the archive cannot answer the question, and it
says why. A fully-populated context built from a substituted price would be a
failure, because it would answer a different question while looking exactly
like a real one.

Measured, from a live AAPL run:

| | observations | replay class |
|---|---|---|
| SEC filings | 75 of 75 with `ACCEPTANCE_DATETIME` | `SOURCE_DECLARED` |
| Yahoo fundamentals | 0 of 12 declare when they were published | `ARCHIVE_FIRST_SEEN` |

So SEC history replays, and a vendor replay is labelled observational rather
than passed off as point-in-time truth.

Three properties, enforced rather than documented:

- **Append-only**, by SQLite triggers. A restatement appends a new row in the
  same lineage, so a replay before it still shows the original figure.
- **`retrieved_at` never becomes `available_at`.** Retrieval is always
  populated, and copying it would make every undated value look knowable —
  which is precisely how a backtest ends up worthless.
- **The archive is a consumer of the Data Contract**, behind an interface with
  a `NullArchive` for the normal CLI path. No engine import, no storage engine
  in the Core, so SQLite can be replaced without touching the contract.

Specified in
[docs/ST-EVA-2.4-POINT-IN-TIME-ARCHIVE-REPLAY.md](docs/ST-EVA-2.4-POINT-IN-TIME-ARCHIVE-REPLAY.md).

## Source capture (2.4.1)

An observation resolves to a specific version of a source document, not to a
URL that may serve different bytes tomorrow. SEC data is updated as filings are
disseminated and a filing can be corrected after acceptance, so only the exact
version served can say what a number was read from.

```python
store = SQLiteArchive("data/st-eva.sqlite")
store.documents_summary()          # every captured document, with its type
store.content_for(content_hash)    # the exact bytes, or None for a reference
store.captured_bytes()             # deduplicated total
```

Captured by default: SEC company-concept, SEC submissions, and the SEC ticker
map. Market-data vendor documents are recorded as a hash and a URI without
storing the payload, so a fact from them is still traceable to something
identified and the archive never holds a copy it should not.

Measured on a live AAPL run: **10 documents, 1,166,179 bytes**, content
round-tripping byte-identically. A *second* run against the same archive added
**zero documents and zero bytes**, because a company-concept response is stable
until a new filing lands. Content addressing makes the long-run cost the
cumulative set of distinct filings rather than the cumulative set of runs.

The deterministic core now supports P/E, P/FCF, EV/EBITDA, and P/S reverse valuation. Future work can add additional providers and an optional LLM interpretation layer without moving arithmetic into the LLM.

## Scope

ST-EVA is an analytical primitive. It describes assumptions embedded in a market price; it does not make the investment decision.

"Reverse valuation" here means working backwards from a price under a stated reference to the assumptions that would justify it. It is not a house methodology and makes no claim to be a standard; the assumptions it reports are conditional on the reference and the inputs, and it reports both.
