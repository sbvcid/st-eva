# Local Historical Price Data — Usage & Limitations

Baseline: `cbaf1bb` / `37b6291` (master). Verified against current code (`historical_pe_adapter.py`, `sqlite_archive.py`, `st_eva_runner.py`) and test suite. Not a feature claim; documents actual behavior.

## 1. What works (verified by existing code & tests)

### A. Replay determinism (SOFI SQLite archive)
- **Path**: `data/archives/SOFI.sqlite`
- **How**: `tests/test_replay_determinism_sofi.py` copies the file to a temporary directory (`tempfile.mkdtemp`) and rebuilds the document via `SQLiteArchive` / `replay()`.
- **Verification**: with local file present — `pytest tests/test_replay_determinism_sofi.py` passes (3/3). Without it — 3 skipped (`SkipTest`), not false pass.
- **Required format**: SQLite database with `schema_migrations`, `assets`, `sources`, `observations`, `context_snapshots`, `derived_values`, etc. (41 tables, ~2 MB for SOFI). Direct copy of the existing archive works; manual construction from scratch requires matching every table, index, and identity set.
- **Source authorization**: User must independently confirm Yahoo Finance / SEC EDGAR authorization for their own copy; this document describes mechanics only, not grants permission.

### B. Adapter production pipeline (historical P/E reference)
- **Primary path**: `historical_pe_adapter.py` reads `data/historical_pe/<ticker>/daily_prices.json` + `manifest.json` (JSON format with `source` / `price_source` metadata, `daily_prices.json` containing standardized price bars, `prices_manifest.json` where present).
- **Secondary path**: `historical_pe_adapter.py` reads `data/archives/SOFI.sqlite` (`read_sqlite_price_observations()` at line 367) only when SQLite archive is present.
- **No generic import**: There is no `import_prices.py`, no `--import-file`, no CSV adapter, no external DB connector. The adapter either (a) fetches from Yahoo Finance (`fetch_yahoo_daily_prices()` at line 69), or (b) reads an existing SQLite archive / standardized JSON at the exact expected path.
- **Verification with local data**: copy existing `SOFI.sqlite` or `daily_prices.json` (with matching `manifest.json`) to the expected path; adapter passes 49/49 (`-k 'not live'`). Removing the price JSON causes 11 adapter tests to skip (`skipUnless` at `tests/test_historical_pe_adapter.py`); removing the SQLite archive causes replay to skip.
- **Data format match required**: `daily_prices.json` must contain the fields the adapter expects (`as_of`, `price` / close series, `currency`, `source_url`, `content_sha256` when manifest references it). The adapter does not validate arbitrary formats; it parses based on the saved manifest contract.

## 2. Placement (exact paths; no renaming permitted for adapter compatibility)

For replay (archive):
- `data/archives/SOFI.sqlite`

For adapter (history P/E per issuer):
- `data/historical_pe/SOFI/daily_prices.json`
- `data/historical_pe/SOFI/prices_manifest.json` (optional for SOFI; required by manifest digest tests)
- `data/historical_pe/SOFI/manifest.json` (mixed source; if replaced, must include both price source evidence and SEC evidence or adapter integrity tests skip)
- `data/historical_pe/AAPL/daily_prices.json` + `manifest.json`
- `data/historical_pe/AEP/daily_prices.json` + `manifest.json`
- `data/historical_pe/MSFT/daily_prices.json` + `manifest.json`
- `data/historical_pe/MU/daily_prices.json` + `daily_prices_metadata.json`

Note: `manifest.json` for each issuer references price source (e.g., AAPL: `"YahooFinance as-traded"`). If user supplies only price data without a matching manifest, adapter manifest-integrity tests (if run) will report digest mismatch; this is expected and correct behavior.

## 3. What is NOT supported (explicit, not implied)

- No CSV / Excel / Parquet / external DB import interface exists.
- No "convert from Bloomberg / Refinitiv / other provider" tool exists.
- No automatic format normalization if the source schema differs from Yahoo v8 `chart.result` structure.
- No synthetic / simulated price generation is provided or authorized by this project; users must supply their own authorized price series.
- No guarantee that placing a file at the path automatically makes all adapter tests pass, because some tests verify manifest digest against specific file content (requires exact byte match if that file is tracked and expected).

## 4. Validation steps (what the user can do independently)

After placing local file(s):

```bash
# Verify replay (requires archive)
python -m pytest tests/test_replay_determinism_sofi.py -v --tb=line

# Verify adapter (requires price JSON + manifest where applicable; SEC files already tracked)
python -m pytest tests/test_historical_pe_adapter.py -k "not live" -q --tb=line

# Check that no unauthorized file was accidentally tracked
python scripts/check_unauthorized_data_preflight.py  # if available
```

Expected:
- Replay: 3 passed (if archive present); 3 skipped (if missing — correct, not hidden).
- Adapter: 49 passed (with local price + archive); 11 skipped (when price JSON / manifest missing — correct for SOFI-specific classes).

## 5. Authorization reminder (C-1 unconfirmed)

If a user obtains historical price data from Yahoo Finance or any other provider, they must independently confirm redistribution rights under that provider's terms. This document describes mechanics only. The project does not grant redistribution rights for third-party price sequences.

## 6. Source evidence (for reference)

- Adapter primary fetch: `historical_pe_adapter.py` lines 69–128 (`fetch_yahoo_daily_prices`, `parse_yahoo_price_bars`).
- Secondary SQLite read: `historical_pe_adapter.py` line 367 (`read_sqlite_price_observations`).
- Replay dependence: `tests/test_replay_determinism_sofi.py` lines 45 (`SOFI_ARCHIVE`), 82 (`SkipTest` if missing).
- Data-availability notes: `DATA-AVAILABILITY.md` (root), section 9 (phase 5 audit), section 8 (phase 4 verification).
- Prevention hook: `.git/hooks/pre-commit`; `scripts/check_unauthorized_data_precommit.py`.
EOF