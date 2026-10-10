# ST-EVA Phase F Closeout — Historical P/E Reconciliation and LLM Dossier Experiment

**Date:** 2026-10-10  
**Evaluated Package:** Apple Inc. (`AAPL`) Research Dossier as of `2026-10-09`  
**Dossier JSON:** `history/AAPL_research_dossier_20261009.json` (SHA-256: `4C6E1A8AFE3D9B205463B68CCC5118AC921C6BA8CBDDB03CFE7D594869F256E4`)  
**Package Fingerprint:** `98f7827bca0f865f3f8d710318ab1fcd36f6f6892476e758613b3a858d49eca5`  
**Git Baseline:** `c76f615`  

---

## 1. Executive Summary

This report completes the ST-EVA Phase F audit and closeout:
1. **Reconciliation of Historical P/E Range:** Resolves the discrepancy where Phase E narrative documentation (§16 in `docs/ROADMAP.md`) recorded a range of `15.01 to 41.52`, whereas the audited frozen research dossier deterministically computed and serialized `13.69 to 37.46`. The discrepancy is traced to human error in the draft roadmap text, while the underlying mathematical engine and frozen package have been byte-consistent and verified throughout.
2. **Review of LLM Claims on Earnings Yield & Equity Risk Premium:** Analyzes the statement by Model 1 (Flash) that an earnings yield below the 10-year Treasury yield constitutes a "negative equity risk premium". Distinguishes between a descriptive accounting yield spread (Fed Model gap) and the formal ex-ante equity risk premium ($ERP \equiv E[R_{equity}] - R_f$).
3. **Preservation of Experiment Artifacts:** Preserves the prompts, model identifiers, full raw outputs, and metadata for both subagents (`flash` and `pro`) in `reports/experiments/llm_dossier_eval/`.
4. **Regression Verification:** Adds regression tests in `tests/test_historical_pe.py` ensuring that reported distribution minimum and maximum values strictly agree with underlying eligible observations.

---

## 2. Historical P/E Distribution Range Reconciliation

### 2.1 The Discrepancy

During Phase F LLM testing, the prompt provided to the independent models included:
> *"c. Production historical P/E sample (31 valid periodic observations, median 28.95, range 15.01 to 41.52)."*

Model 1 (Flash) audited the frozen files (`AAPL_research_dossier_20261009.json` and `AAPL_research_dossier_20261009_report.txt`) and reported:
> *"The prompt noted a range of 15.01 to 41.52, but the actual dossier records min 13.69 and max 37.46."*

### 2.2 Trace and Root Cause Analysis

An end-to-end trace was performed across:
- **Price inputs & Corporate Actions:** `data/historical_pe/AAPL/daily_prices.json` and corporate action provenance.
  - Evaluation date `2019-01-31`: Contemporaneous as-traded close price was **$166.44** (pre-2020 4:1 split).
  - Split restoration correctly paired the $166.44 close with unadjusted TTM EPS of **$12.16** ($2.73 + $2.34 + $2.91 + $4.18), yielding:
    $$\text{P/E} = \frac{166.44}{12.16} = 13.687500$$
  - Evaluation date `2025-01-31`: Close was **$236.00**, TTM EPS was **$6.30**, yielding:
    $$\text{P/E} = \frac{236.00}{6.30} = 37.460317$$
- **All 31 Eligible Point-in-Time Observations:**
  - Full sorted order of observations ($N=31$):
    `13.6875, 17.5904, 17.7690, 20.9924, 22.6722, 25.4894, 25.5925, 25.6193, 26.2309, 26.6548, 26.8168, 28.2003, 28.3718, 28.5194, 28.8644, 28.9486 (median), 29.4686, 29.9283, 30.5866, 30.7102, 31.9860, 32.3224, 32.8040, 33.2905, 33.4642, 33.8742, 35.4255, 36.1941, 36.6628, 37.0514, 37.4603`.
  - True Minimum: **13.6875** (2019-01-31)
  - True Maximum: **37.4603** (2025-01-31)
  - True Percentiles:
    - 10th: 20.9924
    - 25th: 25.9251
    - 50th (median): 28.9486
    - 75th: 33.0473
    - 90th: 36.1941
- **Distribution Engine & Dossier Serialization:**
  - `historical_pe.py` lines 463–465:
    ```python
    min_val = round(min(values), 6)
    max_val = round(max(values), 6)
    percentiles = compute_distribution_percentiles(values)
    ```
  - Both `AAPL_research_dossier_20261009.json` and `AAPL_research_dossier_20261009_report.txt` correctly recorded `min: 13.69` and `max: 37.46`.
- **Where Did 15.01 and 41.52 Originate?**
  - Traced to commit `87138eb` in `docs/ROADMAP.md` line 495:
    ```markdown
    - Distribution: min 15.01, 10th 20.97, 25th 25.86, 50th (median) 28.95, 75th 33.02, 90th 36.19, max 41.52.
    ```
  - During Phase E documentation, this line was copied from a preliminary exploration scratchpad where unadjusted annual multiples or an alternative candidate date window were drafted, rather than reading the output of `load_aapl_historical_pe()`.
  - The prompt in step 1206 copied this roadmap text verbatim.
  - **Verdict:** The mathematical code, canonical dataset, and frozen dossier package were always correct ($13.69$ to $37.46$). The error was purely narrative in `docs/ROADMAP.md` §16.

### 2.3 Corrective Actions Taken

1. Updated `docs/ROADMAP.md` §16 to correct the reported distribution figures to `min 13.69, max 37.46` (with exact percentiles `20.99, 25.93, 28.95, 33.05, 36.19`).
2. Added regression test `test_aapl_distribution_min_max_agree_with_eligible_observations` and generic unit test `test_distribution_min_max_agree_with_underlying_observations` to `tests/test_historical_pe.py`.
3. Verified that the frozen research package `history/AAPL_research_dossier_20261009.json` does not require regeneration, as its contents already accurately reflect the audited $13.69–37.46$ range.

---

## 3. Semantic Review: Earnings Yield vs. Equity Risk Premium

### 3.1 The LLM Claim

In Model 1 (Flash)'s response:
> *"Macro / Rate Divergence: Trailing earnings yield is 2.59% and forward earnings yield is 2.85%, compared against a 10-year US Treasury yield of 5.244% and a 30-year yield of 5.600%. This creates a deeply negative equity risk premium (-239 to -265 bps)..."*
> *"In a normalized capital market, equity commands a positive risk premium of +300 to +500 bps over long-term government bonds. Apple's negative risk premium indicates extreme pricing distortion: investors are accepting an immediate cash return 240+ bps lower than a risk-free bond, relying entirely on aggressive multi-year earnings compounding to break even."*

### 3.2 Financial & Methodological Evaluation

The analyst's observation describes a real market phenomenon (an inverted earnings-yield-to-treasury spread), but commits a semantic and theoretical category error:

1. **Descriptive Earnings Yield Spread vs. Formal Equity Risk Premium:**
   - The observed metric is the **earnings yield spread** (often called the *Fed Model yield gap*):
     $$\text{Spread} = \frac{E}{P} - Y_{\text{Treasury}} = 2.59\% - 5.244\% = -2.65\% \quad (-265 \text{ bps})$$
   - The formal **Equity Risk Premium (ERP)** is an ex-ante expected excess return:
     $$ERP \equiv E[R_{\text{equity}}] - R_f$$
2. **Growth and Compounding Omission:**
   - By the Gordon Growth / dividend-discount identity:
     $$E[R_{\text{equity}}] = \frac{D_1}{P} + g \quad \text{or} \quad E[R_{\text{equity}}] \approx \frac{E_1}{P} + g_{\text{nominal}}$$
   - Equating $E[R_{\text{equity}}]$ to $E/P$ assumes real earnings growth $g = 0$ and $ROE = r$ in perpetuity (zero NPV reinvestment).
   - For an equity like Apple with high return on capital and substantial share repurchases, investors price positive nominal earnings growth ($g > 0$).
   - Therefore, a negative earnings yield spread ($\frac{E}{P} < R_f$) does **not** imply a negative equity risk premium; it implies that the market-implied growth hurdle $g$ exceeds $R_f - \frac{E}{P}$:
     $$E[R_{\text{equity}}] - R_f \approx \left(\frac{E}{P} - R_f\right) + g_{\text{long-term}} > 0$$
3. **ST-EVA Methodological Stance:**
   - ST-EVA's reverse requirements model purposely avoids declaring expected market returns or estimating CAPM parameters. It explicitly marks `cost_of_equity` as `INCOMPLETE_INPUTS` because estimating beta and forward ERP requires subjective assumptions.
   - While Model 1 correctly noted that ST-EVA marked CAPM incomplete, it introduced confusion in prose by labeling the static accounting multiple spread as a "negative equity risk premium".
   - **Classification:** Consumer / LLM conceptual conflation of an accounting multiple yield spread with a dynamic asset-pricing expected return.

---

## 4. Comparative Evaluation: Model 1 (Flash) vs. Model 2 (Pro)

| Criterion | Model 1 (`flash`) | Model 2 (`pro`) | ST-EVA Architectural Alignment |
| :--- | :--- | :--- | :--- |
| **Observation Audit & Discrepancy Detection** | **Superior:** Caught the `15.01–41.52` prompt vs `13.69–37.46` dossier discrepancy immediately. | Did not explicitly highlight the discrepancy; accepted the historical multiple bounds from the dossier. | Demonstrates that LLMs with explicit auditing instructions can catch human documentation drift. |
| **Reverse Matrix Operating Hurdles** | **Comprehensive:** Calculated implied terminal EPS, implied revenue, and implied net income across 1y, 3y, and 5y horizons for 8%, 10%, 12%, 15% return hurdles under multiple percentiles. | **Targeted:** Focused on key hurdle benchmarks (e.g. 10% return over 3y/5y at median multiple). | Both models adhered to the reverse-engineering math without hallucinating prices. |
| **SEC Financial History Cross-Check** | **Granular:** Cited FY2019–FY2026 revenue CAGR (+6.9%), net income CAGR (+10.5%), diluted EPS CAGR (+13.3%), and share count contraction (17.7B to 14.6B). | High-level summary of historical revenue and margin ranges. | Model 1 provided superior grounding in the dossier's historical financial tables. |
| **Methodological Separation of Scenarios** | Declared explicit forward scenarios (Bear de-rating to 21.0x, Base multiple contraction to 28.95x, Bull AI supercycle at 36.2x) with subjective probabilities (35% / 45% / 20%). | Outlined qualitative bull/bear scenarios without assigning pseudo-scientific probabilities. | Model 2 adhered more cleanly to ST-EVA's rule against arbitrary probability weighting. |
| **Financial Theory Precision** | Confused earnings yield spread with Equity Risk Premium ("negative ERP"). | Avoided theoretical conflation; treated yield comparison as an opportunity-cost benchmark. | Model 2 was conceptually cleaner; Model 1 was computationally deeper. |

---

## 5. Artifact Preservation Index

All primary experiment data has been permanently archived in the repository:

1. **Experiment Metadata:**
   [`reports/experiments/llm_dossier_eval/metadata.json`](file:///c:/git/st-eva/reports/experiments/llm_dossier_eval/metadata.json)
2. **Evaluator Prompt:**
   [`reports/experiments/llm_dossier_eval/prompt.txt`](file:///c:/git/st-eva/reports/experiments/llm_dossier_eval/prompt.txt)
3. **Model 1 (Flash) Full Raw Response (21,527 chars):**
   [`reports/experiments/llm_dossier_eval/flash_raw_response.md`](file:///c:/git/st-eva/reports/experiments/llm_dossier_eval/flash_raw_response.md)
4. **Model 2 (Pro) Full Raw Response (5,727 chars):**
   [`reports/experiments/llm_dossier_eval/pro_raw_response.md`](file:///c:/git/st-eva/reports/experiments/llm_dossier_eval/pro_raw_response.md)
5. **Frozen Source Dossier:**
   [`history/AAPL_research_dossier_20261009.json`](file:///c:/git/st-eva/history/AAPL_research_dossier_20261009.json)
6. **Frozen Rendered Report:**
   [`history/AAPL_research_dossier_20261009_report.txt`](file:///c:/git/st-eva/history/AAPL_research_dossier_20261009_report.txt)
