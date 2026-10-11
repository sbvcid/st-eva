# Historical P/E POC — version-controlled archive

This directory is the tracked, version-controlled home of the AAPL Historical P/E
proof of concept and its Amendment 1 verification run.

## Why this exists

`research/` is git-ignored by design, so material preserved only there cannot be
reviewed, reproduced from a clean checkout, or verified by CI. The scripts and
deterministic outputs that establish how the Historical P/E methodology was
implemented and checked are research evidence, not scratch data, so they are
mirrored here at their canonical tracked location.

## Provenance

Every file here was copied byte-for-byte from the git-ignored research tree on
2026-10-11 and verified by SHA-256 after copying:

| Tracked path | Source under `research/` |
| --- | --- |
| `*.py`, `README.md` | `research/experiments/aapl-historical-pe-poc/` |
| `out/` | `research/experiments/aapl-historical-pe-poc/out/` |
| `amendment1_verify/` | `research/experiments/aapl-historical-pe-poc/amendment1_verify/` |

The originals remain in place under `research/`; nothing was moved or deleted.

`out/historical_pe_points.json` is the AAPL proof-of-concept oracle. It is the
independent expectation behind the MSFT regression fixture committed at
`tests/fixtures/msft_historical_pe_expected.json`.

## What is deliberately not here

The frozen **raw inputs** are not mirrored. They are large vendor and SEC
payloads, regenerable by `fetch_raw.py` and `fetch_filing_headers.py`, and they
carry no independent conclusions:

- `research/experiments/aapl-historical-pe-poc/raw/` — frozen submissions index,
  `EarningsPerShareDiluted` concept and daily prices.
- `research/experiments/aapl-historical-pe-poc/contract/` and `q4_study/` —
  cached SEC filing documents and exhibits, roughly 1.1 GB in total.

The production inputs derived from them *are* version-controlled, under
`data/historical_pe/AAPL/` and `data/historical_pe/MSFT/`, each with a manifest
recording source URLs and content hashes.