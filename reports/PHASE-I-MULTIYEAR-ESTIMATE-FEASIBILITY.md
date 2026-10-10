# Phase I — Multi-Year Analyst Estimate Coverage Feasibility Audit

**Status:** DOCUMENT-ONLY AUDIT — NO CODE CHANGES TO PRODUCTION DATA, NO COMMIT, NO MODIFY TO FROZEN DOSSIERS OR SQLITE.
**Audit date:** 2026-10-10 (verification timestamp from repository state at commit `10d298f` / frozen package `2026-10-09` / Phase H `2026-10-10`)
**Author / session:** Kilo session `ses_...` — audit performed by direct read of `C:\git\st-eva` working tree.
**Scope per objective:** Source-feasibility and data-contract audit only; not an implementation authorization. No scenario probabilities, no price targets, no new valuation method, no DCF expansion.

---

## 1. Current implementation baseline (exact, from code, not inferred)

### 1.1 How +1y consensus is sourced
- **Metric definition:** `METRIC_CONSENSUS_FORWARD_EPS = "consensus_forward_eps"` (`data_contract.py:405`). Unit `UNIT_PER_SHARE` (`data_contract.py:586`). Definition: `"Consensus forward EPS. Never synthesized."` (`data_contract.py:564`).
- **Provider / acquisition:** `FundamentalProvider` (`fundamental_provider.py:110`) via `fetch_acquisition()`.
- **Endpoint inspected in source:** Yahoo Finance `quoteSummary` / `earningsTrend`. The response is parsed at `fundamental_provider.py:466` (`trend = item.get("earningsTrend") or {}`) and `_extract_consensus_forward_eps()` (`fundamental_provider.py:386`).
- **Exact endpoint fields used for consensus:** `earningsTrend.trend[].period` (vendor label, e.g. `"+1y"`, `"0y"`, `"+1q"`, `"0q"`) and `earningsTrend.trend[].earningsEstimate.avg` (average estimate value). No other fields from `earningsTrend` are read for this metric.
- **Selection logic:** Priority map `{"+1y":0,"0y":1,"+1q":2,"0q":3}`; lowest-priority (first) wins (`fundamental_provider.py:400-408`). Historical actuals are excluded by lack of matching period labels.
- **Storage format:** `Observation` frozen dataclass (`data_contract.py:819`) with exact fields: `observation_id`, `metric`, `value`, `unit`, `currency`, `currency_basis`, `period_start`, `period_end`, `as_of`, `available_at`, `available_at_basis`, `provider`, `source_type`, `source_url`, `definition`, `methodology`, `retrieved_at`, `raw`, `observation_count`, `status`, `status_reasons`, `inputs`, `basis`.
- **Observation construction:** `provider=self.name` (`fundamental_provider.py:797`); `retrieved_at = utc_now()` (`fundamental_provider.py:425`); `source_url` from `quoteSummary` URL; `definition` / `methodology` declared in adapter; `raw` preserved; `observation_count` set to `None` for this metric because endpoint provides no contributor count.

### 1.2 Exact figure at dossier valuation date (2026-10-09)
- Frozen Phase F package (`history/AAPL_research_dossier_20261009.json`) — `as_of = "2026-10-09"` (`dossier section market_and_company`); fingerprint referenced in `ST-EVA-PROJECT-STATUS.md` (not re-computed; file unread-modified per `git status`).
- Value in `sections.validation_metrics.consensus.consensus_forward_eps`: `9.58043`.
- Period label preserved in dossier: `data.consensus_forward_eps_period` set from `consensus.raw.get("period")` (`st_eva_runner.py:1093`), typically `"+1y"`. Runner interprets present period as `consensus_basis = "FORWARD_TWELVE_MONTHS"`, `consensus_months = 12.0` (`st_eva_runner.py:2328-2329`). If period absent, comparison against terminal EPS is declared `UNAVAILABLE` (`st_eva_runner.py:2321-2341`).
- Currency: USD (`data_contract.py` applies `INSTRUMENT_DEFAULT` basis; Yahoo does not declare EPS currency explicitly; this is a declared application, not silent).
- EPS basis: **undeclared by source** — `earningsEstimate.avg` does not state GAAP / adjusted / non-GAAP. The adapter does not set `basis["eps_basis"]` for this observation. This is a gap.
- Source timestamp / retrieval: `retrieved_at` = fetch-time (`utc_now()`). No separate `as_of` is taken from `earningsTrend` specifically; `as_of` for EPS observations is derived from `stats.get("trailingEps").get("asOfDate")` / `forwardEps.asOfDate` (`fundamental_provider.py:476-479`), which may not correspond to the `earningsTrend` timestamp.
- Source attribution in dossier: only `consensus_forward_eps` value and `consensus_forward_eps_period`; no `provider`, `source_url`, `retrieved_at`, `observation_count`, or `raw` preserved at dossier-output level (observer-level fields exist in `ObservationSet` but are not all exported to the frozen JSON package).

### 1.3 Existing schemas / contracts that could accommodate FY+2 / FY+3 / LT growth
- `Observation` (`data_contract.py:819`) can represent any metric string; no schema change required to add new metric names such as `consensus_forward_eps_fy2`, `consensus_forward_eps_fy3`, `consensus_long_term_growth`.
- `ObservationSet` (`data_contract.py:1122`) supports multiple observations for the same metric via distinct `observation_id`.
- `ValuationInputs` (`data_contract.py:1878`) currently has only `consensus_forward_eps`; no fields for FY+2/3 or growth. Extending `ValuationInputs` would be needed only if the engine must consume them — not required for a contract-only audit.
- `fundamental_provider.py` `FundamentalAcquisition` (`fundamental_provider.py:163`) has `consensus_forward_eps_period`; could extend to `consensus_forward_eps_fy2_period`, etc.
- `data_contract.py` `BAND_METRICS`, `METRIC_*` registry (`data_contract.py:403-498`) is extensible.
- Existing `sqlite_archive.py` / `evidence_model.py` layers do not store analyst estimates; the sqlite DB (`observations` table at `data/st-eva.sqlite`) has zero rows for `consensus_forward_eps`-class metrics (verified by direct query: 0 matching rows). All analyst-estimate data in this repo is runtime-generated from Yahoo, not archived persistently.

### 1.4 Existing partially implemented support
- The `Observation` contract, `ObservationSet`, `fundamental_provider.py`, and `st_eva_runner.py` already have the infrastructure: observation IDs, metric registry, cross-source comparison framework (`ValidationRecord` at `data_contract.py:908`), `knowable_at()` point-in-time selector (`data_contract.py:1191`), and `contract_dict()` serialization (`data_contract.py:880`).
- The gap is **not structural** — it is a **source-data gap**. The engine can consume multi-year observations if they are provided; the current provider (`Yahoo Finance`) does not produce them.

---

## 2. Candidate source comparison (verified against endpoint documentation / direct inspection / source code; unverified claims marked *unknown*)

Sources are evaluated independently for **A. Current point-in-time** (estimates as known on 2026-10-09) and **B. Historical point-in-time** (reconstruction without look-ahead).

| Source / Endpoint | FY+1 | FY+2 | FY+3 | LT Growth | Consensus or Individual | Fiscal Year Explicit | Adjusted / GAAP Distinguishable | Contributor Count | Historical Vintages | As-Of / Availability Timestamp Trustworthy | API Access | Cost / Licensing | Redistribution Restrictions | Verified By |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Yahoo Finance** (`quoteSummary` / `earningsTrend`) — *current* | Yes (`+1y`) | **No** (only `+1y`, `0y`, quarterly) | **No** | **No** | Consensus (`avg`) | Partial — vendor label `+1y`; not mapped to fiscal year end | **Unknown / undeclared** (`earningsEstimate.avg` unlabeled) | **No** (not in endpoint) | **No** (only latest `trend`) | Partial — `asOfDate` from `stats` for EPS only, not `earningsTrend` specifically; `retrieved_at` = fetch time | Open / unauthenticated | Free | Not restricted (public endpoint) | **Direct code inspection** (`fundamental_provider.py:386-408`, `st_eva_runner.py:1093`) + `git` file state |
| **Financial Modeling Prep** (`/api/v3/analyst-estimates/<ticker>`, `/stable/financial-estimates`) | Yes (documented) | **Documented** (period parameter `annual`) | **Documented** (period parameter) | **Unknown** (growth endpoints documented separately: `income-statement-growth`, `financial-growth`) | Consensus + individual analyst recommendations documented | **Documented** (period = annual / quarter; year labels in response per docs) | **Unknown** (not verified by direct call — endpoint requires API key; 401 observed) | **Documented / unknown** (docs mention "consensus" but contributor counts not explicitly confirmed in exemplar) | **Unknown** (docs mention historical earnings calendar / surprises; not confirmed for estimate vintages) | **Unknown** (docs do not explicitly declare historical as-of for each estimate row) | HTTP REST; API key required (401 without) | Paid tiers; free tier rate-limited | **Unknown / likely restricted by Terms** (no redistribution clause reviewed in this session) | **Web documentation** (`site.financialmodelingprep.com/developer/docs/stable/financial-estimates`, endpoint samples); **direct fetch returned 401** (not verified by response content) |
| **Bloomberg API / Terminal** (`EST_EPS`, `LTG`, `EST_REV`) | Yes | Yes (documented) | Yes (documented) | Yes (`LTG` — long-term growth, definition vendor-specific, usually 3-5yr) | Both (consensus + individual estimates available) | **Yes** (fiscal year labels in response; e.g., FY2026) | **Yes** (GAAP / adjusted / normalized variations available; must check specific `EST_EPS` field) | **Yes** (analyst count per estimate available in terminal/API) | **Yes** (historical estimate vintages available via `EST_EPS` history / `BDS`) | **Yes** (publication dates / as-of dates tracked per vintage) | Bloomberg API / BPIPE; terminal only; enterprise contract | **High** (enterprise / institutional subscription required) | **Strict** (redistribution restricted; data may not be stored / redistributed without agreement) | **Industry documentation** (Bloomberg API reference docs; not directly called — requires authentication) |
| **Refinitiv I/B/E/S** (Workspace / Data Platform / API) | Yes | Yes | Yes | Yes (`LTG` field in `EPS_EST` / `EPS_ACT`) | Both (consensus `EPS_EST` + individual analyst records) | **Yes** (fiscal year end explicitly labeled; e.g., `FISCAL_YR` = 2026) | **Yes** (basis fields: GAAP / adjusted; distinction preserved in dataset) | **Yes** (analyst identifier + count per consensus) | **Yes** (full historical vintages by `REVID` / `DATE` per analyst) | **Yes** (as-of = estimate publication date per `DATE`) | Enterprise subscription / API license | **Very high** (institutional / corporate data license) | **Strict** (I/B/E/S conditions: no redistribution; use restricted to licensed entity; storage rules apply) | **Industry documentation** (Refinitiv I/B/E/S data manual; not directly called — requires subscription authentication) |
| **FactSet** (Estimates / API) | Yes | Yes | Yes | Yes (`LT_GROWTH` / long-term growth estimates documented) | Both (consensus + analyst-level) | **Yes** (fiscal year labels) | **Yes** (adjusted / actuals / normalized distinctions) | **Yes** (analyst count) | **Yes** (historical estimate series available) | **Yes** (historical as-of tracked) | Enterprise API / desktop | **Enterprise** (institutional subscription) | **Restricted** (terms of service limit redistribution; storage conditions apply) | **Industry documentation** (FactSet Estimates product docs; not directly called) |
| **S&P Capital IQ Pro / API** | Yes | Yes | Yes | Yes (long-term growth estimates in estimates dataset) | Consensus (individual analyst estimates available in some plans) | **Yes** (fiscal year) | **Yes** (adjusted / GAAP distinctions available) | **Yes** (contributor counts in API response for some endpoints) | **Yes** (historical estimates available) | **Yes** (historical dates available) | Subscription / API | Paid (institutional / corporate) | **Restricted** (license terms apply) | **Industry documentation** (Capital IQ API docs; not directly called) |
| **SEC EDGAR (`sec_provider.py`)** | **No** (only filed actual EPS, not estimates) | **No** | **No** | **No** | Actual only | Yes (fiscal calendar declared) | Yes (as-reported / restated distinctions via filing declarations) | **N/A** | Historical actuals only (no estimates) | Yes (filing acceptance dates) | Public (EDGAR) / `sec_provider.py` adapter | Free / no subscription | Unrestricted for filed data (but source-specific terms for bulk access apply) | **Direct code inspection** (`sec_provider.py`; `observations` table 0 rows for estimates) |

### 2.1 Key verification notes (what was directly verified vs. what is documented-only)
- **Yahoo Finance:** Direct code inspection of endpoint fields and selection logic confirms exactly what is available (`+1y`/`0y`/quarterly). No other fields are read. **Direct fetch of Yahoo endpoint was not performed in this session** (the adapter relies on existing `quoteSummary` bootstrap; endpoint structure is inferred from parsed code, not a live snapshot of current Yahoo response). The frozen dossier value `9.58043` confirms the adapter produces a number, but does not confirm the endpoint's current response for 2026-10-09.
- **FMP:** Direct `GET` to `https://financialmodelingprep.com/api/v3/analyst-estimates/AAPL` returned HTTP 401 (API key required). Endpoint documentation is from FMP site docs (websearch result `site.financialmodelingprep.com/developer/docs/stable/financial-estimates`). Multi-year fields (`period=annual`) and growth endpoints (`income-statement-growth`, `financial-growth`) are documented but the response schema for multi-year EPS estimates and long-term growth was **not verified by live response**.
- **Bloomberg / I/B/E/S / FactSet / Capital IQ:** No endpoint calls attempted (no credentials, no terminal access). Features listed are from standard industry documentation. **Historical coverage and contributor counts are documented standards for these sources, but not independently verified in this session.** They must be treated as *documented, not directly observed*.
- **No source in this repo currently supplies FY+2, FY+3, or LT growth estimates.** The repository's only active analyst-estimate pipeline (`fundamental_provider.py`) is hard-limited to Yahoo `earningsTrend`.

---

## 3. Separate verdicts (A = current point-in-time; B = historical point-in-time)

### 3.1 A. Current point-in-time coverage (as of 2026-10-09 valuation date)
- **Yahoo Finance (existing):** Partial — provides only FY+1 (`+1y`) consensus EPS; no FY+2, FY+3, no LT growth. **Not sufficient for full multi-year requirement.**
- **FMP (with API key / paid access):** Conditional — endpoint documentation supports FY+1–FY+3 and growth endpoints, but exact response fields for multi-year estimates and long-term growth must be verified by live call after account access is obtained. **Conditional GO only after endpoint verification and licensing review.** Without access: **NO-GO**.
- **Bloomberg / I/B/E/S / FactSet / Capital IQ:** Conditional GO for current point-in-time — documented to have all required fields, but access requires enterprise subscription. **Implementation not justified without committed account and endpoint verification.**
- **SEC EDGAR:** **NO-GO** — only actuals; no estimates.
- **Overall current verdict:** **Not practical with existing open source. Requires subscription access first.** Even with FMP, endpoint verification is a prerequisite because the endpoint returned 401 and multi-year fields are not confirmed by live observation.

### 3.2 B. Historical point-in-time coverage (reconstruction without look-ahead)
- **Yahoo Finance (existing):** **NO-GO.** Endpoint provides only latest `earningsTrend`; no historical vintages of estimates. The sqlite archive (`data/st-eva.sqlite`, `observations` table) contains zero rows for estimate metrics. Reconstruction of historical multi-year estimates is impossible from current sources.
- **FMP:** **Unknown / conditional** — documentation references historical earnings calendar / surprises; it is not confirmed whether `analyst-estimates` endpoint preserves historical estimate vintages with trustworthy `as_of` per observation. **Requires endpoint verification with API key and explicit check for historical fields.**
- **Bloomberg / I/B/E/S / FactSet / Capital IQ:** **Conditional GO for historical** — these sources are the industry standard for historical estimate vintages (I/B/E/S `DATE` / `REVID`; Bloomberg `EST_EPS` history; FactSet historical series). **Mandatory prerequisites:** (1) subscription access; (2) verification that the specific endpoint / dataset preserves historical estimates with reliable `as_of` per observation (not just latest consensus); (3) licensing permits storage / replay for research use.
- **Overall historical verdict:** **Not possible with current open source. Requires subscription source with confirmed historical-vintage capability and verified timestamp reliability.** Do not use today's consensus as a substitute for historical consensus (constraint from objective §3).

---

## 4. Recommended minimum data contract extension

Extend the existing `Observation` (`data_contract.py:819`) without breaking frozen contracts. The smallest justified schema extension for multi-year analyst estimates is:

### 4.1 Metric naming convention (proposed, not implemented)
- `consensus_forward_eps` = FY+1 (existing; keep)
- `consensus_forward_eps_fy2` = FY+2 (new metric name, or keep `consensus_forward_eps` with `period_end` explicitly set to FY+2 fiscal year end)
- `consensus_forward_eps_fy3` = FY+3 (new or explicit period)
- `consensus_long_term_growth` = long-term growth estimate (new metric; unit `UNIT_RATIO` or `UNIT_PERCENT`; definition must declare forecast horizon, e.g., "3-year to 5-year annualized expected EPS growth" per vendor definition)

**Recommendation:** Prefer explicit `period_start` / `period_end` over new metric names where possible, because `Observation` already supports period fields. However, because `ValuationInputs` (`data_contract.py:1878`) reads by metric name, new metric names are required if the engine must consume FY+2/3 directly. A contract-only extension can use either approach, but the recommendation is: **keep metric names fixed and require `period_end` to declare fiscal year** — this avoids multiplying metric registry entries.

### 4.2 Required fields per observation (do not silently omit)
| Field | Required for current dossier? | Required for historical backtest? | Source capability (Yahoo) | Source capability (subscription) | Action if unavailable |
|---|---|---|---|---|---|
| `observation_id` | Yes | Yes | Yes | Yes | Mandatory |
| `metric` | Yes | Yes | Yes | Yes | Mandatory |
| `value` | Yes | Yes | Yes | Yes | Mandatory; must not synthesize |
| `unit` | Yes (`UNIT_PER_SHARE` / `UNIT_RATIO`) | Yes | Yes | Yes | Mandatory |
| `currency` | Yes | Yes | Partial (applied, not stated) | Yes | Declare `INSTRUMENT_DEFAULT` explicitly; not silent |
| `currency_basis` | Yes | Yes | Partial | Yes | Declare |
| `period_start` / `period_end` | **Yes** (must declare fiscal year end, not vendor label only) | **Yes** (fiscal year must align to historical date) | Partial (`+1y` only, no fiscal year end) | Yes | Set to `UNAVAILABLE` if source does not declare fiscal year; do not infer |
| `as_of` | Recommended | **Mandatory** (source publication / availability date per historical observation) | Partial (`stats.asOfDate` for EPS; not for `earningsTrend`) | Yes | `UNAVAILABLE` if source does not declare; do not substitute retrieval date |
| `available_at` / `available_at_basis` | Recommended | Recommended | No (not set for this metric) | Yes | Declare `UNAVAILABLE`; no inference |
| `provider` | Yes (must include endpoint reference, not just vendor name) | Yes | Partial (`self.name`; endpoint not preserved in observation) | Yes | Must include endpoint path (e.g., `"I/B_E_S-Refinitiv"` + endpoint) |
| `source_type` | Yes | Yes | Partial | Yes | Declare |
| `source_url` | Yes (traceable endpoint / record reference) | Yes (must allow reproduction of historical query) | Partial (quoteSummary URL; earningsTrend sub-path not preserved separately) | Yes | Preserve query URL including parameters |
| `retrieved_at` | Yes | Yes | Yes (`utc_now()`) | Yes | Mandatory (retrieval is not source publication) |
| `observation_count` (analyst/contributor count) | Recommended | Recommended | **No** | Yes (subscription sources) | `UNAVAILABLE`; do not invent |
| `basis` (dict with `eps_basis`: GAAP / adjusted / non-GAAP / consensus-adjusted) | **Mandatory** for comparability | **Mandatory** | **Unknown / undeclared** (gap) | Yes | Must declare `UNAVAILABLE` if source does not state; do not assume adjusted |
| `definition` | Yes | Yes | Yes (declared) | Yes | Declare vendor definition exactly |
| `methodology` | Yes | Yes | Partial | Yes | Declare consensus calculation method |
| `raw` | Recommended | **Mandatory** (preserve full vendor response for audit) | Yes (trend preserved?) | Yes | Preserve |
| `status` / `status_reasons` | Yes | Yes | Yes (`UNVERIFIABLE` by default) | Yes | Must not be silently set to `VERIFIED` without cross-source check |

### 4.3 Explicitly required new states (do not invent comparability)
- `MISSING` / `UNAVAILABLE`: when source does not provide the field for that fiscal year (e.g., FY+3 not covered).
- `CONFLICTING`: when multiple sources disagree on the same period / metric (cross-source validation framework at `data_contract.py:908` already supports this).
- `STALE`: when `available_at` is older than defined freshness threshold (to be defined per source, not inferred).
- `NON_COMPARABLE`: when `eps_basis` or `currency_basis` differs from other observations of the same metric for the same issuer — must not be silently converted to comparable observation.

---

## 5. Acceptance criteria (separate mandatory / conditional)

### 5.1 Mandatory for current-dossier use (point-in-time at valuation date)
1. **Fiscal-period alignment:** The estimate must be linked to an explicit fiscal period (`period_end` or `period_start`) that can be matched to the valuation date's fiscal calendar. Vendor label `"+1y"` is not sufficient without mapping to fiscal year end. **Mandatory.**
2. **Estimate basis and unit comparability:** `basis["eps_basis"]` must be declared (GAAP / adjusted / consensus-adjusted / unknown). Unit must be `UNIT_PER_SHARE`. If unknown, observation is `UNVERIFIABLE` for comparison, not silently comparable. **Mandatory.**
3. **Timestamp and point-in-time reliability:** `retrieved_at` must be declared. `as_of` must represent the source's publication/availability time for the estimate, not retrieval time. If `as_of` is missing, the observation can be used for single-source current dossier but must be labeled `UNVERIFIABLE` for cross-source or historical comparison. **Mandatory for accurate attribution; conditional for raw current use.**
4. **Source traceability and reproducibility:** `provider`, `source_url`, `source_type` must allow reproduction of the query. If endpoint requires authentication and query cannot be reproduced, source traceability is partial but must be declared. **Mandatory.**
5. **Multi-year coverage completeness:** For the intended use (FY+1, FY+2, FY+3, LT growth), all required periods must be present for the same issuer on the same valuation date, or gaps must be explicitly declared (`UNAVAILABLE`). Partial coverage is not sufficient for full multi-year growth calculations. **Mandatory for intended scope.**
6. **Data freshness:** Observation `available_at` / `retrieved_at` must be within a declared freshness window relative to dossier `as_of`. Not defined here; to be set per source contract. **Conditional / to be defined in next phase.**
7. **Licensing and operational feasibility:** Source must be accessible for the project's intended use (no assumed credentials). If access requires enterprise subscription that is not secured, source is **NO-GO** regardless of endpoint capability. **Mandatory before any implementation.**

### 5.2 Mandatory for historical backtesting / reconstruction
- All criteria from §5.1 apply, plus:
- **Point-in-time reliability per historical date:** Each historical observation must have its own `as_of` (not derived from current `retrieved_at`). `knowable_at()` (`data_contract.py:1191`) must be able to select observations public at or before the historical cutoff.
- **No look-ahead bias:** Historical estimates must not include information available only after the historical cutoff (e.g., actuals revised later must not retroactively change historical estimates; if vendor revises historical estimate series, the original vintage must be preserved, not overwritten).
- **Historical estimate vintage preservation:** Source must provide historical estimates, not just current consensus. If only latest consensus is available (Yahoo), historical reconstruction is impossible.
- **Cross-source validation:** For historical use, at least two independent sources or documented single-source audit trail should be available to confirm the historical observation. The existing `ValidationRecord` (`data_contract.py:908`) framework supports this.

---

## 6. Constraints preserved (verified against project rules)

- **No probabilities / rankings / expected values:** Report does not include likelihood rankings, scenario weights, or authoritative expected EPS values.
- **No price targets / recommendations:** No price targets, ratings, or buy/sell recommendations added.
- **No DCF / new valuation method:** No discount-cash-flow or new valuation methodology introduced.
- **Frozen dossiers untouched:** `history/AAPL_research_dossier_20261009.json` (Phase F) and `history/AAPL_research_dossier_20261010_phase_h.json` (Phase H) not edited; `git status` shows only prior untracked files plus cleaned temp scripts.
- **Production DB untouched:** `data/st-eva.sqlite` not written; direct query only (read-only). No schema changes, no migrations.
- **Isolated temporary stores:** All experiments performed via temporary Python scripts in working directory (all removed via `rm tmp_*.py`); no writes to `data/`, `archive/`, or `history/`. No temporary SQLite files created.
- **No commits:** No `git commit` executed.
- **Documentation-only change:** Only new file created is this report (`reports/PHASE-I-MULTIYEAR-ESTIMATE-FEASIBILITY.md`); no modifications to `data_contract.py`, `fundamental_provider.py`, `research_dossier.py`, `sec_provider.py`, or any frozen output.

---

## 7. Deliverables — prioritized decisions and remaining work

### 7.1 Prioritized GO / CONDITIONAL GO / NO-GO (from verification above)

| Source / Approach | Current Point-in-Time | Historical Point-in-Time | Overall | Rationale (short) |
|---|---|---|---|---|
| **Yahoo Finance (existing adapter)** | PARTIAL (FY+1 only) | NO-GO | **NO-GO** for intended multi-year scope | Endpoint hard-limited to `+1y`/`0y`/quarterly; no FY+2/3; no LT growth; no vintages; `basis` undeclared |
| **Financial Modeling Prep (premium / API key)** | CONDITIONAL GO (after endpoint verification) | CONDITIONAL GO (after verification of historical fields) | **CONDITIONAL GO — access + verification required first** | Endpoint requires 401 auth; multi-year / growth fields documented but not confirmed by live response; licensing / redistribution terms not reviewed |
| **Bloomberg Terminal / API** | CONDITIONAL GO (after subscription + endpoint verification) | CONDITIONAL GO | **CONDITIONAL GO — requires enterprise subscription** | Standard source for all required fields; access restricted; redistribution strict |
| **Refinitiv I/B/E/S** | CONDITIONAL GO | CONDITIONAL GO | **CONDITIONAL GO — requires institutional license** | Best source for contributor counts + historical vintages + fiscal alignment; licensing strict |
| **FactSet / Capital IQ** | CONDITIONAL GO | CONDITIONAL GO | **CONDITIONAL GO — enterprise subscription** | Documented multi-year + LT growth + historical series; access required |
| **SEC EDGAR (`sec_provider`)** | NO-GO | NO-GO | **NO-GO** | Only filed actuals; no estimates |

### 7.2 Smallest justified implementation scope if a source passes
If and only if a subscription source is secured and endpoint verification confirms all required fields with trustworthy `as_of` and `observation_count`, the smallest scope is:
- **Data layer:** Add new metric names or explicit `period_end` usage in `Observation`; extend `FundamentalAcquisition` to read multi-year fields (not new adapter, just new parsing rules); preserve `raw` response for audit.
- **Schema extension:** Extend `Observation.basis` with `"eps_basis"`; extend `ObservationSet` / `ValidationRecord` usage for cross-source comparison if second source available (recommended for historical).
- **Engine layer:** Extend `ValuationInputs` only if multi-year estimates must feed the deterministic engine; otherwise keep contract-only extension and let dossier/reporting layer consume observations directly (as `research_dossier.py` already does for `consensus_forward_eps`).
- **Testing:** Before implementation, required tests: (1) endpoint response parsing for FY+2/3/LT growth with real credentials; (2) `as_of` extraction verification per historical row; (3) `knowing_at()` selection with historical cutoff; (4) `basis` declaration and non-comparable-state handling; (5) license / redistribution compliance check.
- **No database migration needed:** Existing `data_contract.py` and `Observation` are sufficient; sqlite archive can remain read-only.

### 7.3 Remaining uncertainty, access requirements, cost/licensing, tests required
- **Access:** No subscription credentials exist in this environment. FMP endpoint returned 401; Bloomberg / I/B/E/S / FactSet require institutional accounts not available.
- **Endpoint verification:** For FMP, direct `GET /api/v3/analyst-estimates/AAPL` failed; full response schema for multi-year estimates and growth endpoints unverified. For Bloomberg/I-B/E-S/FactSet, no endpoint calls performed.
- **Historical vintages:** For all subscription sources, the presence of historical estimate series and the reliability of `as_of` per historical observation is documented but not independently verified in this session.
- **Cost / licensing:** FMP has paid tiers (free tier rate-limited); Bloomberg / I/B/E/S / FactSet / Capital IQ are enterprise-cost; redistribution restrictions apply to all except Yahoo and SEC filed data. The project must confirm that its intended use (research dossier + potential storage / replay) complies with source license terms before storage.
- **Tests required before any implementation:** See §7.2. At minimum: live endpoint verification with credentials; `as_of` extraction verification; historical-vintage selection test with `knowable_at()`; `basis` handling test; licensing review.

---

## 8. Final statement — evidence and recommendation

**Evidence summary:**
- The existing +1y consensus (`consensus_forward_eps = 9.58043`, `as_of = 2026-10-09`) is verifiable from frozen Phase F dossier (`history/AAPL_research_dossier_20261009.json`) and source code (`fundamental_provider.py:386-408`, `st_eva_runner.py:1093`, `data_contract.py:405`). It comes from Yahoo Finance `earningsTrend` (`+1y` vendor label only, fiscal year end undeclared, `basis` undeclared, contributor count absent, historical vintages absent).
- The repository's data contract (`Observation`, `ObservationSet`, `ValidationRecord`) can already represent multi-year estimates and growth figures; the engine is structurally ready.
- No open source accessible to this project (Yahoo, SEC EDGAR, or any uncredentialed endpoint) supplies FY+2, FY+3, or long-term growth estimates with explicit fiscal-year alignment, trustworthy historical `as_of`, and contributor counts.
- FMP endpoint documentation suggests capability but the endpoint requires authentication (401 observed) and multi-year / growth response schemas were not verified by direct observation.
- Bloomberg / I/B/E/S / FactSet / Capital IQ are documented to supply all required fields, but they require enterprise subscriptions that this project does not currently hold, and redistribution / storage conditions must be reviewed.

**Conclusion:**
The evidence **does not justify implementation now**. It **requires access to a provider / account first**, followed by endpoint verification and licensing confirmation, before any data-contract extension or adapter change is approved. If a suitable subscription source is secured and verified, the smallest scope (§7.2) is justified; without that access, the intended multi-year analyst estimate coverage is **not currently practical** using only the repository's existing open-source pipeline.

No code changes made to production systems. Only documentation created (`reports/PHASE-I-MULTIYEAR-ESTIMATE-FEASIBILITY.md`). All temporary scripts removed; `data/st-eva.sqlite`, frozen dossier JSONs, and `archive/` files verified unread-modified (`git status` after cleanup shows only pre-existing untracked experiment/report files, no modifications to tracked production files or frozen outputs).
