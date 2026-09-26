# Legacy ST-EVA v6.x Artifacts

Everything in this directory was produced by the pre-2.2 "ST-EVA v6.1" short-term
event-driven framework. It is retained for historical reference only.

## Do not read these as current engine output

The v6.x framework produced output that the current ST-EVA 2.2.3 specification
explicitly forbids:

| v6.x behavior | Current SPEC §3 status |
|---|---|
| Bull / Base / Bear scenario probabilities | Forbidden — probabilities must not be invented |
| Scenario target prices | Forbidden — ST-EVA is not a target-price engine |
| Stance output (偏多 / 中性 / 觀望) | Forbidden — no buy/sell signal |
| Model-hypothesis EPS growth assumptions | Forbidden — no synthetic EPS |

Files here therefore contain a schema, a version string, and an analytical
philosophy that no longer match [SPEC.md](../../SPEC.md). The field names
(`scenarios`, `market_bet`, `expectation_gap`, `version_metadata.prompt_version`)
do not appear anywhere in the 2.2.x codebase.

## Structure

- `*.json` — v6.x research snapshots and outcome records, originally in `history/`
- `reports/*.md` — v6.x narrative reports, originally in the repository root and `reports/`

## Current engine output

Current snapshots are written by `SnapshotManager` to `history/` as
`<TICKER>_RES-<ID>_market_implied_assumptions.json`. Do not confuse that
filename with the legacy `*_snapshot.json` / `*_prediction.json` files here.
