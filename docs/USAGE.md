# ST-EVA Usage Guide

> **歷史資料／非現行指令。** 本文件只記錄撰寫時的設計、狀態、計畫或決策，不具有授權、禁止、限制或要求未來工作的效力。文中任何「binding」「frozen」「approved」「not authorized」「must」等措辭均為歷史內容，不得凌駕使用者目前的要求。當前狀態以現行程式碼、測試及實際 Git 狀態為準。
>
> **HISTORICAL ARCHIVE — NOT CURRENT INSTRUCTIONS.** This document records prior design, status, plans, or decisions. It does not grant, deny, restrict, or require work. Any “binding,” “frozen,” “approved,” “not authorized,” or “must” wording below is historical and does not override the user's current request. Determine current state from current source code, tests, and Git state.

ST-EVA answers one question: 「目前價格反映了什麼假設？」

It reverse-engineers the earnings assumptions required to justify an observed
price under an explicitly selected valuation reference. It does not forecast,
does not produce target prices, and does not issue buy/sell signals.

## Requirements

Python 3.9 or newer. No third-party packages. No API keys.

## The one-liner

Ticker in, report out:

```powershell
python st_eva_runner.py AAPL
```

Add `--no-snapshot` while exploring, and `--reference-multiple <n>` when you want
the reverse-engineered section populated. Add `--json` if you are piping the
result somewhere.

## Quick start

There is no configuration. Give it a ticker, it prints the result.

```powershell
python st_eva_runner.py 0700.HK --mode live --no-snapshot --reference-multiple 20
```

```
==========================================================================
ST-EVA 2.2.3  |  0700.HK
0700.HK (Live Acquired)  (HKG)
價格: HKD 436.60    資料日期: 2026-09-25
==========================================================================

[資料品質] UNVERIFIABLE — 無法驗證（單一來源）
           來源: YahooFinance+YahooFinanceFundamentals  (API_LIVE)
           取得錯誤: 無
           共識 EPS 期間: +1y

--------------------------------------------------------------------------
已觀察估值 (OBSERVED)
--------------------------------------------------------------------------
  指標          數值
  ------------  -----
  目前 P/E      14.69
  前瞻 P/E      12.11
  共識前瞻 P/E  14.15
  P/FCF         N/A
  EV/EBITDA     N/A
  P/S           N/A

歷史估值區間 (來源觀測值)
  倍數       中位數  觀測數  目前分位  可否作參考
  ---------  ------  ------  --------  ----------
  P/E        24.00   7       -         觀測不足
  P/S        5.44    8       -         觀測不足
  P/FCF      無資料  -       -         -
  EV/EBITDA  15.69   8       -         觀測不足

--------------------------------------------------------------------------
參考倍數 (REFERENCE)
--------------------------------------------------------------------------
選用方式: user_supplied_multiple — 使用者指定倍數
選用倍數: 20.00x
採用門檻: 歷史區間需 >= 20 個觀測值方可作為參考

注意: 以下歷史區間因觀測數不足未被採用為參考
      - pe
      - ps
      - ev_ebitda
      若需隱含數值，請以 --reference-multiple 明確指定。

--------------------------------------------------------------------------
市場隱含假設 (CONDITIONAL INFERENCE)
--------------------------------------------------------------------------
  項目                數值     說明
  ------------------  -------  ------------------
  隱含前瞻 EPS        21.8300  價格 / 20.00x
  EPS 缺口 (vs 共識)  -29.2%   正值 = 高於共識
  所需 EPS CAGR       -26.6%   自目前 EPS 起算
```

Note how the 觀測數 column reads 7, 8, 8. Yahoo returns a small number of
annual observations, so the historical bands are reported but never used. The
`--reference-multiple 20` above is what makes the implied section possible.

The report always ends with the missing-data list and the limitations. It never
prints a target price, a probability, or a stance.

## Company names work too

```powershell
python st_eva_runner.py 蘋果 --mode live --no-snapshot
python st_eva_runner.py 騰訊 --mode live --no-snapshot
python st_eva_runner.py 台積電 --mode live --no-snapshot
python st_eva_runner.py apple --mode live --no-snapshot
python st_eva_runner.py nvidia --mode live --no-snapshot
```

Unrecognised input passes through unchanged so it fails loudly rather than
silently resolving to a different company.

## Output modes

| Command | Output |
|---|---|
| `python st_eva_runner.py AAPL` | Readable report (default) |
| `python st_eva_runner.py AAPL --json` | Machine-readable JSON |
| `python st_eva_runner.py AAPL --no-snapshot` | Suppress snapshot writing |

`--json` preserves the exact schema used before the readable report existed, so
existing pipelines are unaffected. The 2.3-A data contract is additive: it
changes no key and no value in this output, and it appears only in the snapshot
artifact as a separate `data_contract` block.

## Where the data came from

Every number the engine uses is backed by an observation that records its
metric, unit, currency, period, provenance, and the raw payload the provider
returned. To inspect it:

```python
from st_eva_runner import material_observations, YahooFinanceProvider

data = YahooFinanceProvider().fetch('AAPL')
for metric, observation in material_observations(data).items():
    print(metric, observation.value, observation.unit, observation.currency)
    print('   period', observation.period_start, observation.period_end)
    print('   as_of', observation.as_of, 'available_at', observation.available_at)
    print('   source', observation.provider, observation.source_url)
    print('   method', observation.methodology)
    print('   status', observation.status.value, observation.status_reasons)
```

A live band reports the window it covers, which is what a bare median could
never tell you:

```
pe_band   median 35.6  period 2024-06-10..2026-09-17  observations 8
          provider YahooFinanceFundamentals
          status INSUFFICIENT_OBSERVATIONS
```

`available_at` is `None` with basis `UNDECLARED` when the provider does not
disclose when a figure became public. That gap is recorded rather than filled
with the retrieval time, because a retrieval time is not a publication time.

## Cross-checking against the SEC

The SEC is a second source for seven metrics. It never replaces Yahoo and never
feeds the engine; it produces a verdict on the pair.

```python
from cross_validation import cross_validate_all
from fundamental_provider import YahooFundamentalProvider
from sec_provider import SECProvider

sec = SECProvider().fetch('AAPL')
yahoo = YahooFundamentalProvider().fetch_acquisition('AAPL', instrument_currency='USD')
for metric, result in cross_validate_all(yahoo.observations, sec.observations).items():
    print(f"{metric:<20} {result.status.value}")
    print(f"   {result.validation.explanation}")
    print(f"   references: {list(result.validation.references)}")
```

Three notes on reading the output:

- `CONSOLIDENCY`-style agreement carries an `independence` field in
  `comparison_basis`. When it reads `UNVERIFIED_INDEPENDENCE`, the agreement is
  real but the vendor's ingestion path is not disclosed, so it is not proof.
- A `PERIOD_MISMATCH` on an identical pair means the values match but one side
  published no date, so contemporaneity cannot be established. The record says
  so rather than claiming agreement.
- Both observations survive the comparison unchanged. Read either side directly
  if you want the raw figure rather than the verdict.

The SEC requires a declared, contactable `User-Agent` and allows at most 10
requests per second. `SECProvider` sets one and self-limits to 4 per second.

## The central idea

Most tools ask "what will this stock be worth". ST-EVA asks the inverse:

> Given this price, what must be true for the price to make sense?

The whole engine is one division:

$$\text{Implied forward EPS} = \frac{P_0}{M}$$

where $P_0$ is the observed price and $M$ is the valuation multiple you have
explicitly chosen.

Everything else — EPS gap, required CAGR, implied FCF/EBITDA/revenue, implied
net margin — is built on top of that single reference.

## Modes

| Mode | Command | Behaviour |
|---|---|---|
| `live` | `python st_eva_runner.py AAPL --mode live` | Acquire from Yahoo Finance |
| `regression` | `python st_eva_runner.py MSFT --mode regression` | Use a static fixture, no network |
| `auto` (default) | `python st_eva_runner.py AAPL` | Fixture when one exists, otherwise live |

`regression` only recognises these keys: `TENCENT`, `0700.HK`, `騰訊`, `MSFT`,
`MICROSOFT`, `NU`, `NU HOLDINGS`. Anything else falls through to live.

## Workflow

### Step 1 — check whether a historical reference is usable

```powershell
python st_eva_runner.py 0700.HK --mode live --no-snapshot
```

Read the 可否作參考 column:

- 可用 — enough observations, the historical median is adopted automatically.
- 觀測不足 — the band exists but is too thin. Implied figures show `N/A`.
- 無資料 — no band at all.

A real live run for AAPL currently reports only 8 P/E observations, so the
historical median is refused. This is deliberate: eight points cannot support a
10/25/50/75/90 percentile reading, and a median that looks precise is not the
same as evidence.

### Step 2 — supply your own reference multiple

```powershell
python st_eva_runner.py 0700.HK --mode live --reference-multiple 20 --no-snapshot
```

An explicit multiple always wins over a historical band, thin or not.

### Step 3 — verify, then save

Only write a snapshot once the numbers look defensible:

```powershell
python st_eva_runner.py 0700.HK --mode live --reference-multiple 20
```

## Reading the report

Example using the TENCENT regression fixture:

```powershell
python st_eva_runner.py TENCENT --mode regression --no-snapshot
```

```
--------------------------------------------------------------------------
已觀察估值 (OBSERVED)
--------------------------------------------------------------------------
  指標          數值
  ------------  -----
  目前 P/E      N/A
  前瞻 P/E      13.72
  共識前瞻 P/E  13.72

歷史估值區間 (來源觀測值)
  倍數       中位數  觀測數  目前分位  可否作參考
  ---------  ------  ------  --------  ----------
  P/E        18.50   未宣告  約 50 分位  可用

--------------------------------------------------------------------------
參考倍數 (REFERENCE)
--------------------------------------------------------------------------
選用方式: historical_pe_median — 歷史 P/E 中位數
選用倍數: 18.50x

--------------------------------------------------------------------------
市場隱含假設 (CONDITIONAL INFERENCE)
--------------------------------------------------------------------------
  項目                數值     說明
  ------------------  -------  ------------------
  隱含前瞻 EPS        23.3622  價格 / 18.50x
  EPS 缺口 (vs 共識)  -25.8%   正值 = 高於共識
```

Interpretation:

1. The stock trades at 13.72x forward earnings.
2. The historical median is 18.5x, so the current multiple sits at the 50th
   percentile — neither expensive nor cheap.
3. At 18.5x, the price implies forward EPS of 23.36.
4. Consensus forward EPS is 31.50, so the price-implied figure sits 25.8% below
   consensus.

Note the 觀測數 reads 未宣告 for this fixture. A band that does not declare its
observation count is treated as usable, which is what keeps static regression
fixtures working. Live bands always declare a count and are subject to the
threshold.

The conditional statement that matters: **23.36 is what the price requires if
the market is paying 18.5x.** It is not a forecast, and it is not "the market
expects 23.36".

## Key output fields (`--json`)

```jsonc
{
  "market_snapshot":        { "price": 341.07, "currency": "USD", ... },
  "data_quality":           { "discrepancy_status": "UNVERIFIABLE", ... },
  "observed_valuation":     { "current_pe": 39.07, "historical_pe_band": {...}, ... },
  "market_implied_assumptions": {
    "forward_eps_at_reference_multiple": 11.37,
    "eps_gap_vs_consensus": 0.187,
    "required_eps_cagr_from_current_eps": null,
    "reference_multiples": { "pe": 30.0, "pfcf": 25.0, ... }
  },
  "consensus_cross_check":  { "consensus_forward_eps": 30.15, ... },
  "reference":              { "method": "user_supplied_multiple", "multiple": 30.0, ... },
  "missing_data":           [ "current_fcf" ],
  "evidence_ids":           [ "ev-price-001", ... ]
}
```

`missing_data` is a first-class output. A long list there means the run is thin,
not that the engine failed.

## Multi-method reverse valuation

```powershell
python st_eva_runner.py AAPL --mode live `
  --reference-multiple 30 `
  --pfcf-multiple 25 `
  --ev-ebitda-multiple 20 `
  --ps-multiple 8
```

```
  項目                數值     說明
  ------------------  -------  ------------------
  隱含前瞻 EPS        11.3690  價格 / 30.00x
  EPS 缺口 (vs 共識)  +18.7%   正值 = 高於共識
  隱含 FCF            196.74B  P/FCF = 25.00x
  隱含 EBITDA         247.02B  EV/EBITDA = 20.00x
  隱含營收            614.82B  P/S = 8.00x
  隱含淨利率          26.7%    P/S + P/E 聯合推得
```

Each method expresses the same price in a different unit. Comparing them is how
you detect a price that is only defensible under one lens.

The implied net margin is worth attention: it combines the P/S-implied revenue
with the P/E-implied EPS to answer "what profitability must this company earn
for the current price to hold?" For AAPL at 30x, that is 26.7%.

P/FCF, EV/EBITDA and P/S implied figures are absolute currency amounts. The
report abbreviates large values as B/M, but the magnitude itself is not the
signal — compare them across methods or against history instead.

## Other options

```powershell
# Years over which required EPS growth is compounded
python st_eva_runner.py AAPL --reference-multiple 30 --horizon-years 3

# Record an event date (metadata only, does not affect calculation)
python st_eva_runner.py AAPL --event "Q3 earnings"

# Suppress snapshot writing
python st_eva_runner.py AAPL --no-snapshot
```

## Snapshots and outcome tracking

Without `--no-snapshot`, a run writes:

```
history/<TICKER>_RES-<ID>_market_implied_assumptions.json
```

The snapshot is append-only. Outcomes are recorded in separate files and never
modify the original analysis.

```python
from st_eva_runner import SnapshotManager

SnapshotManager('history').update_outcome(
    'RES-5F74EBF112',
    {'t_plus_1_return': 0.0079, 'event_result': None},
)
```

This creates `history/AAPL_RES-5F74EBF112_outcome_<timestamp>.json` alongside
the untouched snapshot.

## Using it as a library

`run_st_eva()` is the same entry point the CLI uses:

```python
from st_eva_runner import run_st_eva
from report_formatter import render_report, resolve_console_encoding

resolve_console_encoding()

result = run_st_eva(
    'AAPL',
    mode='live',
    reference_multiple=30.0,
    save_snapshot=False,
)

print(render_report(result))
print(result['market_implied_assumptions']['forward_eps_at_reference_multiple'])
```

`render_report()` performs no arithmetic. It only reformats a result the engine
has already validated.

## LLM interpretation

The adapter in `llm_interpreter.py` converts a validated snapshot into a strict
interpretation prompt. Its system prompt forbids the model from calculating,
modifying, or inventing any financial figure, and from issuing a verdict.

```python
from llm_interpreter import (
    build_interpretation_prompt,
    build_interpretation_request,
)

prompt = build_interpretation_prompt(result)
request = build_interpretation_request(result)
```

Send `prompt` to whichever model client you already use. The calculation core
stays deterministic Python; only the prose is delegated.

## Tests

```powershell
python st_eva_runner.py --test              # 6 built-in regression checks
python -m unittest discover -s tests        # 271 unit tests
```

The data contract itself is covered separately in
`tests/test_data_contract.py`, which asserts the provenance fields, the
validation semantics, the raw-preservation rule, the deterministic
recomputation guarantee, and the provider-agnostic engine boundary.

Second-source validation is covered in `tests/test_sec_validation.py`, which
asserts the comparability policy, the discrete-fact filter, the trailing-window
constructions, period alignment, tolerance, and the no-merge guarantee.

The Investment Context is covered in `tests/test_investment_context.py`, which
asserts that every ref resolves, every operation is registered, every
derivation recomputes, unavailable figures carry no value, the content hash is
stable, and the 2.2.3 JSON is byte-identical with and without `--context`.

The tests that call the real SEC and Yahoo are opt-in, because a fair-access
rate limit and a deterministic suite do not mix:

```powershell
$env:ST_EVA_LIVE = "1"
python -m unittest tests.test_investment_context.TestLiveContexts
python -m unittest tests.test_sec_validation.TestLiveAdapters
python -m unittest tests.test_archive_replay.TestLiveArchive
```

## Archive and replay

Opt-in persistence. Without `--archive` the output is byte-identical to 2.2.3.

```powershell
python st_eva_runner.py AAPL --context ctx.json --archive data/st-eva.sqlite
```

```python
from archive import replay
from sqlite_archive import SQLiteArchive
from st_eva_runner import build_context_from_observations

store = SQLiteArchive("data/st-eva.sqlite")
result = replay(store, "AAPL", "2026-06-30", build_context_from_observations)
print(result.outcome, result.reason)
```

| Outcome | Meaning |
|---|---|
| `MATCH` | the rebuild reproduces the archived document |
| `DIVERGED` | the same inputs produced a different document; the diff is informative |
| `NO_SNAPSHOT` | no context was archived for that instant |
| `INSUFFICIENT` | not enough was archived at that instant; **nothing was substituted** |

`INSUFFICIENT` is a successful replay. It means the archive cannot answer the
question asked, and it reports why rather than approximating.

`replay_fidelity` is `SOURCE_DECLARED` only when every observation used carries a
source-declared availability. Anything archive-dated downgrades the whole replay
to `OBSERVATIONAL`, because a document cannot be more trustworthy than its
weakest input.

`retrieved_at` is never copied into `available_at`. The SEC requires a declared,
contactable `User-Agent` and allows at most 10 requests per second;
`SECProvider` sets one and self-limits to 4 per second.

### Source capture

```python
from sqlite_archive import SQLiteArchive

store = SQLiteArchive("data/st-eva.sqlite", capture_content=True)
for document in store.documents_summary():
    print(document["document_type"], document["byte_size"],
          document["content_encoding"])     # gzip = payload kept, None = reference
```

Pass `capture_content=False` to record only the hash and the URI, for a source
whose payload should not be stored. A captured document that a stored
observation references is never deleted; the table has no delete path at all.

## Windows console encoding

The CLI reconfigures stdout and stderr to UTF-8 on startup, so the readable
report renders correctly on a default Windows console without any environment
setup. If you import `run_st_eva()` from your own script, call
`resolve_console_encoding()` first when the target stream may be using a legacy
code page.

## What this tool will not do

- invent EPS, consensus estimates, or probabilities;
- produce Bull/Base/Bear target prices;
- issue a buy/sell recommendation;
- pick a valuation reference without reporting which one it used;
- fabricate fundamentals when data is missing;
- ask an LLM to perform valuation arithmetic.

If a required input is missing, the answer is `UNAVAILABLE` or `null`. It stays
that way rather than becoming a guess.
