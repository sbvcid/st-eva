# Legacy ST-EVA v6.x Artifacts

This directory contains outputs from the pre-2.2 ST-EVA v6.1 short-term, event-driven framework. It is retained for historical reference only. These files are not current engine results or a specification of the present product.

## Historical output differences

Older records may contain:

| Legacy field or behavior | How to treat it |
|---|---|
| Bull / Base / Bear scenario probabilities | Historical model output, not a current probability estimate |
| Scenario target prices | Historical target-price output, not a current ST-EVA result |
| Stance labels such as 偏多 / 中性 / 觀望 | Historical labels, not current buy/sell signals |
| Model-hypothesis EPS growth assumptions | Historical assumptions, not observed financial data |

The table describes the legacy artifacts; it is not a replacement for a current specification. Older notes may refer to a root-level `SPEC.md` or other documents that have since moved or been retired. Do not treat those old references as current authority.

Fields such as `scenarios`, `market_bet`, `expectation_gap`, and `version_metadata.prompt_version` belong to the legacy output format. Read their meaning only in the context of the archived records.

## Structure

- `*.json` — legacy research snapshots and outcome records.
- `reports/*.md` — legacy narrative reports.

## Current output

Current snapshots are written by `SnapshotManager` under `history/` using the current market-implied-assumptions snapshot format. Do not confuse those snapshots with the legacy `*_snapshot.json` or `*_prediction.json` files retained here.
