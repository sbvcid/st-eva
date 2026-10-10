# INDEPENDENT FINANCIAL RESEARCH REPORT: APPLE INC. (AAPL)
**As of Valuation Date:** 2026-10-09  
**Source Dossier:** ST-EVA Frozen Research Dossier (`AAPL_research_dossier_20261009.json` / `report.txt`)  
**Analyst:** Independent Financial Research Analyst  
**Methodological Mandate:** Objective, evidence-based reverse-engineering; strict separation between deterministic calculations and subjective forward hypotheses.

---

## EXECUTIVE SUMMARY

At the observed market price of **336.64 USD** (Market Cap: **$4.919T**), Apple Inc. trades at an observed trailing P/E of **38.61x**, a forward consensus P/E of **35.14x**, a P/FCF of **35.98x**, and an EV/EBITDA of **29.41x**.

1. **Valuation Extremity:** Apple's trailing multiple of 38.61x exceeds the maximum observation (37.46x) in the entire 31-observation point-in-time historical sample spanning 2019 to 2026, and sits +1.66 standard deviations above its historical mean of 28.81x.
2. **Asymmetric Hurdle:** Because current valuation starts at an extreme historical decile, any reversion toward the historical median (28.95x) imposes an immediate **-25.0% multiple compression headwind**. To generate an investor return of 10% annualized over 3 to 5 years under a median multiple, Apple must deliver an EPS CAGR of **+21.1% (3y)** and **+16.5% (5y)**, requiring Net Income to reach **$228.9B** and **$276.9B**, and Revenue to cross the **$1.0 Trillion threshold** (at current peak 27.6% net margins).
3. **Consensus Inadequacy:** Analyst consensus projects 1-year forward EPS of **$9.5804** (+9.9% growth). At this consensus growth rate, if Apple's P/E reverts to its historical median (28.95x), the stock would decline **-17.6%** to $277.35. Positive returns at consensus EPS strictly require the multiple to remain trapped above 35.1x (near the 90th percentile).
4. **Macro / Rate Divergence:** Trailing earnings yield is **2.59%** and forward earnings yield is **2.85%**, compared against a 10-year US Treasury yield of **5.244%** and a 30-year yield of **5.600%**. This creates a deeply **negative equity risk premium (-239 to -265 bps)**, implying the market is pricing either unprecedented, sustained earnings acceleration or an extreme "flight-to-quality duration" premium.

---

## 1. REQUIRED OPERATING CONDITIONS (REVERSE-ENGINEERING MATRIX)

### 1.1 Mathematical Formulation
The reverse-engineering framework determines the terminal fundamentals required by the observed current price ($P_0 = \$336.64$) across an investment horizon $T$, required annualized price return $r$, and exit multiple $(P/E)_{exit}$:
$$\text{Required Exit Price } P_T = P_0 \times (1 + r)^T$$
$$\text{Required Terminal EPS } \text{EPS}_T = \frac{P_T}{(P/E)_{exit}}$$
$$\text{Required EPS CAGR} = \left(\frac{\text{EPS}_T}{\text{EPS}_0}\right)^{1/T} - 1 \quad (\text{where } \text{EPS}_0 = \$8.72)$$

### 1.2 Multi-Horizon Reverse Requirements Matrix
Below are the exact deterministic requirements calculated by ST-EVA across horizons (1y, 3y, 5y), required returns (8%, 10%, 12%, 15%), and exit multiples across the production historical distribution:
- **10th Percentile Exit:** 20.99x (-45.6% vs current 38.61x)
- **Historical Median Exit:** 28.95x (-25.0% vs current 38.61x)
- **90th Percentile Exit:** 36.19x (-6.2% vs current 38.61x)

| Horizon | Req. Return | Exit P/E Multiple | Exit Multiple Basis | Req. Exit Price | Req. Terminal EPS | Req. EPS CAGR | Total EPS Growth | Gap vs. 1y Consensus ($9.58) |
| :--- | :---: | :---: | :--- | :---: | :---: | :---: | :---: | :---: |
| **1 Year** | **8%** | 20.99x | 10th Percentile | $363.57 | **$17.32** | +98.6% | +98.6% | **+80.8%** |
| 1 Year | 8% | 28.95x | Median | $363.57 | **$12.56** | +44.0% | +44.0% | **+31.1%** |
| 1 Year | 8% | 36.19x | 90th Percentile | $363.57 | **$10.05** | +15.2% | +15.2% | **+4.8%** |
| **1 Year** | **10%** | 20.99x | 10th Percentile | $370.30 | **$17.64** | +102.3% | +102.3% | **+84.1%** |
| 1 Year | 10% | 28.95x | Median | $370.30 | **$12.79** | +46.7% | +46.7% | **+33.5%** |
| 1 Year | 10% | 36.19x | 90th Percentile | $370.30 | **$10.23** | +17.3% | +17.3% | **+6.8%** |
| **1 Year** | **12%** | 20.99x | 10th Percentile | $377.04 | **$17.96** | +106.0% | +106.0% | **+87.5%** |
| 1 Year | 12% | 28.95x | Median | $377.04 | **$13.02** | +49.4% | +49.4% | **+35.9%** |
| 1 Year | 12% | 36.19x | 90th Percentile | $377.04 | **$10.42** | +19.5% | +19.5% | **+8.7%** |
| **1 Year** | **15%** | 20.99x | 10th Percentile | $387.14 | **$18.44** | +111.5% | +111.5% | **+92.5%** |
| 1 Year | 15% | 28.95x | Median | $387.14 | **$13.37** | +53.4% | +53.4% | **+39.6%** |
| 1 Year | 15% | 36.19x | 90th Percentile | $387.14 | **$10.70** | +22.7% | +22.7% | **+11.6%** |
| **3 Years** | **8%** | 20.99x | 10th Percentile | $424.07 | **$20.20** | +32.3% | +131.7% | N/A |
| 3 Years | 8% | 28.95x | Median | $424.07 | **$14.65** | +18.9% | +68.0% | N/A |
| 3 Years | 8% | 36.19x | 90th Percentile | $424.07 | **$11.72** | +10.3% | +34.4% | N/A |
| **3 Years** | **10%** | 20.99x | 10th Percentile | $448.07 | **$21.34** | +34.8% | +144.8% | N/A |
| 3 Years | 10% | 28.95x | Median | $448.07 | **$15.48** | +21.1% | +77.5% | N/A |
| 3 Years | 10% | 36.19x | 90th Percentile | $448.07 | **$12.38** | +12.4% | +42.0% | N/A |
| **3 Years** | **12%** | 20.99x | 10th Percentile | $472.95 | **$22.53** | +37.2% | +158.4% | N/A |
| 3 Years | 12% | 28.95x | Median | $472.95 | **$16.34** | +23.3% | +87.4% | N/A |
| 3 Years | 12% | 36.19x | 90th Percentile | $472.95 | **$13.07** | +14.4% | +49.9% | N/A |
| **3 Years** | **15%** | 20.99x | 10th Percentile | $511.99 | **$24.39** | +40.9% | +179.7% | N/A |
| 3 Years | 15% | 28.95x | Median | $511.99 | **$17.69** | +26.6% | +102.8% | N/A |
| 3 Years | 15% | 36.19x | 90th Percentile | $511.99 | **$14.15** | +17.5% | +62.2% | N/A |
| **5 Years** | **8%** | 20.99x | 10th Percentile | $494.63 | **$23.56** | +22.0% | +170.2% | N/A |
| 5 Years | 8% | 28.95x | Median | $494.63 | **$17.09** | +14.4% | +95.9% | N/A |
| 5 Years | 8% | 36.19x | 90th Percentile | $494.63 | **$13.67** | +9.4% | +56.7% | N/A |
| **5 Years** | **10%** | 20.99x | 10th Percentile | $542.16 | **$25.83** | +24.3% | +196.2% | N/A |
| 5 Years | 10% | 28.95x | Median | $542.16 | **$18.73** | +16.5% | +114.8% | N/A |
| 5 Years | 10% | 36.19x | 90th Percentile | $542.16 | **$14.98** | +11.4% | +71.8% | N/A |
| **5 Years** | **12%** | 20.99x | 10th Percentile | $593.27 | **$28.26** | +26.5% | +224.1% | N/A |
| 5 Years | 12% | 28.95x | Median | $593.27 | **$20.49** | +18.6% | +135.0% | N/A |
| 5 Years | 12% | 36.19x | 90th Percentile | $593.27 | **$16.39** | +13.5% | +88.0% | N/A |
| **5 Years** | **15%** | 20.99x | 10th Percentile | $677.10 | **$32.25** | +29.9% | +269.9% | N/A |
| 5 Years | 15% | 28.95x | Median | $677.10 | **$23.39** | +21.8% | +168.2% | N/A |
| 5 Years | 15% | 36.19x | 90th Percentile | $677.10 | **$18.71** | +16.5% | +114.5% | N/A |

### 1.3 Fundamental Translation: Implied Net Income and Revenue Hurdles
To understand the macroeconomic and operational feasibility of these required EPS targets, we translate terminal EPS into aggregate Net Income and Revenue under two scenarios:
1. **Flat Diluted Share Count:** 14.786B shares (derived from TTM Net Income $128.93B / EPS $8.72).
2. **Continued Share Repurchases:** Assuming Apple continues retiring shares at its historical rate of ~2.0% per annum (reducing share count to 13.92B at 3 years and 13.37B at 5 years).
3. **Net Margin Assumptions:** Evaluated at Apple's current peak margin (**27.6%**) vs. normalized FY24 margin (**24.0%**).

#### Implied Operating Conditions under a 10% Required Return:
- **3-Year Horizon @ Historical Median P/E (28.95x):**
  - **Required Terminal EPS:** $15.48 (EPS CAGR: +21.1%)
  - **Required Net Income (Flat Shares):** **$228.9B** (+77.5% over current $128.9B)
  - **Required Net Income (with 2% Buyback p.a.):** **$215.5B** (+67.1% over current $128.9B; Net Income CAGR: +18.7%)
  - **Required Revenue (@ Peak 27.6% Margin):** **$828.6B** (Revenue CAGR: +21.1%)
  - **Required Revenue (@ Normalized 24.0% Margin):** **$954.7B** (Revenue CAGR: +27.0%)
- **5-Year Horizon @ Historical Median P/E (28.95x):**
  - **Required Terminal EPS:** $18.73 (EPS CAGR: +16.5%)
  - **Required Net Income (Flat Shares):** **$276.9B** (+114.8% over current $128.9B)
  - **Required Net Income (with 2% Buyback p.a.):** **$250.4B** (+94.2% over current $128.9B; Net Income CAGR: +14.2%)
  - **Required Revenue (@ Peak 27.6% Margin):** **$1,002.6B ($1.00 Trillion)** (Revenue CAGR: +16.5%)
  - **Required Revenue (@ Normalized 24.0% Margin):** **$1,155.1B ($1.16 Trillion)** (Revenue CAGR: +19.9%)
- **5-Year Horizon @ 10th Percentile P/E (20.99x):**
  - **Required Terminal EPS:** $25.83 (EPS CAGR: +24.3%)
  - **Required Net Income (Flat Shares):** **$381.9B**
  - **Required Revenue (@ 27.6% Margin):** **$1,382.6B ($1.38 Trillion)**
- **5-Year Horizon @ 90th Percentile P/E (36.19x):**
  - **Required Terminal EPS:** $14.98 (EPS CAGR: +11.4%)
  - **Required Net Income (Flat Shares):** **$221.5B**
  - **Required Revenue (@ 27.6% Margin):** **$801.9B** (Revenue CAGR: +11.4%)

**Analytical Takeaway:** Even after giving Apple full credit for continuous share buybacks (-2% p.a.) and sustaining record-high net margins of 27.6%, achieving a standard 10% equity return under a mean-reverting multiple requires Apple to generate more than **$1 Trillion in annual top-line revenue** and **$250B+ in annual net profit** within five years.

---

## 2. COMPARISON AGAINST EVIDENCE BASE

### 2.1 Actual Financial History from SEC Filings
Apple’s actual financial results across the 71 SEC observations in the dossier show:
- **Revenue Growth:**
  - Annual FY24 ($391.04B) to FY25 ($416.16B): **+6.4% YoY**.
  - TTM roll-forward reached **$466.82B** as of 2026-06-27.
  - Quarterly YoY revenue accelerated from +5.1% (Q2 FY25) to +9.6% (Q3 FY25), +15.7% (Q1 FY26), +16.6% (Q2 FY26), and +16.4% (Q3 FY26).
- **Net Income & Diluted EPS Growth:**
  - Annual Net Income rose from $93.74B (FY24) to $112.01B (FY25, **+19.5%**), reaching $128.93B TTM.
  - Annual Diluted EPS grew from $6.08 (FY24) to $7.46 (FY25, **+22.7%**), reaching $8.72 TTM.
  - Quarterly YoY EPS growth accelerated to +18.3% (Q1 FY26), +21.8% (Q2 FY26), and +28.7% (Q3 FY26).
- **Net Margin Trend:**
  - Net margin expanded consistently: 24.0% (FY24) $\rightarrow$ 26.9% (FY25) $\rightarrow$ 27.2% (Q2 FY26 TTM) $\rightarrow$ **27.6%** (Q3 FY26 TTM).
  - Quarterly margins range seasonally between 24.9% (summer quarters) and 29.3% (holiday quarter).
- **Evidence Contrast:**
  While Apple’s recent quarterly earnings growth has accelerated to ~20-28% YoY, this represents a cyclical recovery and product cycle peak. The 1-year reverse requirements under a median multiple (+44% to +53% EPS growth) demand nearly **double** the peak historical delivery. Over 3 to 5 years, the required CAGRs (+16.5% to +21.1%) demand that Apple sustain peak cycle growth continuously without any cyclical pause or margin mean-reversion.

### 2.2 Available Analyst Consensus Estimates
- **Consensus Forward EPS:** **$9.5804** (+9.87% over trailing $8.72).
- **Consensus Forward P/E:** **35.14x**.
- **Hurdle Comparison (1-Year Horizon):**
  - At **8% return**, required EPS is $12.56 at median P/E (+31.1% above consensus) and $17.32 at 10th percentile P/E (+80.8% above consensus).
  - At **10% return**, required EPS is $12.79 at median P/E (+33.5% above consensus) and $17.64 at 10th percentile P/E (+84.1% above consensus).
  - The consensus EPS of $9.5804 can **only** deliver a positive return if the multiple remains near or above the historical 90th percentile:
    - At 90th percentile P/E (36.19x), $9.5804 yields $346.75 (+3.0% price return).
    - To achieve an 8% return at consensus EPS ($9.5804), the exit multiple must be **37.95x**.
    - To achieve a 10% return at consensus EPS, the exit multiple must expand to **38.65x**.
    - If the multiple reverts to the historical median (28.95x), consensus earnings price Apple at **$277.35 (-17.6%)**.
    - If the multiple compresses to the 10th percentile (20.99x), consensus earnings price Apple at **$201.09 (-40.3%)**.

### 2.3 Production Historical P/E Distribution Audit
- **Distribution Scope:** 31 periodic observations (2019-01-31 to 2026-07-31) evaluated on SEC filing/earnings release usable dates.
- **Audited Parameters:**
  - **Mean:** 28.81x | **Std. Dev.:** 5.89x
  - **Range in Dossier:** Min **13.69x** to Max **37.46x** *(Audit note: The prompt text mentioned a range of 15.01 to 41.52; however, deterministic inspection of the frozen dossier confirms the exact production range is 13.69 to 37.46).*
  - **Percentiles:** 10th: 20.99x | 25th: 25.93x | Median: 28.95x | 75th: 33.05x | 90th: 36.19x.
- **Valuation Positioning:**
  Current trailing P/E of **38.61x** is:
  - Higher than the **all-time maximum** of 37.46x across the 7.5-year sample.
  - **+1.66 standard deviations** above the sample mean.
  - **+33.4%** above the sample median.
  - This confirms that holding Apple at current levels requires betting that the stock will permanently trade above its entire 2019–2026 valuation band.

### 2.4 Contemporaneous Interest Rate Evidence
- **Risk-Free Treasury Yields (as of 2026-10-09):**
  - 13-Week T-Bill: **4.057%**
  - 5-Year Treasury Note: **5.021%**
  - 10-Year Treasury Note: **5.244%**
  - 30-Year Treasury Bond: **5.600%**
- **Apple Yield Comparators:**
  - Trailing Earnings Yield ($8.72 / $336.64): **2.59%**
  - Forward Consensus Earnings Yield ($9.58 / $336.64): **2.85%**
  - Trailing Free Cash Flow Yield: **2.78%** ($136.68B / $4.919T)
- **Macro Contrast:**
  - Apple's trailing earnings yield sits **-265 bps below** the 10-year Treasury yield, and its forward earnings yield is **-239 bps below**.
  - Compared to cash (13-week T-Bill at 4.057%), Apple’s earnings yield offers a **-147 bps deficit**.
  - In a normalized capital market, equity commands a positive risk premium of +300 to +500 bps over long-term government bonds. Apple's negative risk premium indicates extreme pricing distortion: investors are accepting an immediate cash return 240+ bps lower than a risk-free bond, relying entirely on aggressive multi-year earnings compounding to break even.

---

## 3. CRITICAL AUDIT OF ASSUMPTIONS, CONTRADICTIONS, AND GAPS

A rigorous audit of the ST-EVA dossier identifies the following structural assumptions, limitations, and missing elements:

### 3.1 Omission of Discounted Cash Flow (DCF) Inputs
- **Status:** Explicitly flagged as `NOT_COMPUTED` with `UNDECLARED` cash flow basis.
- **Gaps:** The acquisition layer did not acquire Capex, Depreciation & Amortization, Cost of Debt, Market Value of Debt, Effective Tax Rate, or Working Capital Changes.
- **Implication:** The dossier appropriately refuses to synthesize or default DCF figures. However, without a clean operating cash flow bridge, intrinsic enterprise-level DCF valuations cannot be validated from this dossier alone.

### 3.2 Cash Flow Definitions & Free Cash Flow Band Deficit
- **FCF Figure:** Observed trailing FCF is reported as **$136.68B** (P/FCF = 35.98x), but ST-EVA notes this is an unverified provider aggregate that is not reconciled to SEC cash flow statements ($CFO - Capex$).
- **Missing Historical Band:** `historical_pfcf_band` is completely absent from the acquisition layer (`UNAVAILABLE`), preventing any percentile-based cash flow reverse requirements.

### 3.3 Dividend Omission in Reverse Requirements
- **Flag:** Explicitly flagged as `REQUIRED_RETURN_EXCLUDES_DIVIDENDS`.
- **Impact:** The required returns (8%, 10%, 12%, 15%) are modeled strictly as **price appreciation**. Apple pays an ongoing quarterly dividend (~0.5%–0.6% dividend yield). Because dividends are omitted, the terminal price and terminal EPS hurdles are slightly overstated by approximately 50 to 60 bps per annum relative to total shareholder return (TSR).

### 3.4 Temporal and Definitional Alignment Gaps
- **Starting EPS Period Undeclared:** Trailing EPS of $8.72 from Yahoo has no stated period start or end (`period_undeclared_by_source: True`), though it was reconciled against SecEdgar’s 2026-06-27 roll-forward figure.
- **Consensus Horizon Mismatch:** Consensus EPS ($9.5804) only covers the +1-year forward window. For 2y, 3y, and 5y horizons, no consensus exists (`CONSENSUS_PERIOD_NOT_COMPARABLE`), preventing empirical consensus comparisons over multi-year horizons.
- **Share Count Discrepancies:**
  - Derived shares (Market Cap / Price): **14.611B**
  - Observed point-in-time cover page shares (dated 2026-07-17): **14.594B**
  - Implied diluted shares for EPS ($128.93B / $8.72): **14.786B**
  - Using cover-page point-in-time shares instead of diluted weighted-average shares creates a ~1.3% variance when calculating aggregate net income.
- **Balance Sheet Methodology Mismatches:**
  - **Cash:** Yahoo reports $62.40B (undated), while SEC filing reports $39.54B (as of 2026-06-27), a **57.8% variance**. Yahoo appears to aggregate Cash and Marketable Securities, while SEC represents pure Cash & Cash Equivalents.
  - **Enterprise Value:** The reconstructed EV of $4.956T is classified as `PARTIAL` because it accounts only for long-term debt and cash, omitting short-term debt, short-term marketable securities, non-controlling interests, and preferred equity.
- **Cost of Equity Incomplete:** CAPM cost of equity is `INCOMPLETE_INPUTS` due to missing Beta and Equity Risk Premium inputs.

---

## 4. INDEPENDENT SCENARIOS & SUBJECTIVE HYPOTHESES

*Disclaimer: The following scenarios, probability weightings, and expected values represent the independent subjective judgment of this research analyst. They are strictly separate from ST-EVA’s deterministic calculations and frozen historical evidence.*

To evaluate Apple's investment risk/reward over a **3-year horizon**, we establish four distinct forward-looking scenarios:

### 4.1 Scenario Definitions & Assumptions

#### Scenario A: Mean Reversion to Historical Median (Weight: 35%)
- **Premise:** High interest rates (>5%) persist, forcing Apple's multiple to compress from 38.6x back to its 7.5-year median of **28.95x**.
- **Operational Performance:** Apple delivers solid operational execution; EPS grows at **+12.0% CAGR** (above current 1y consensus of +9.9%), reaching **$12.25** in Year 3.
- **Year 3 Terminal Price:** $\$12.25 \times 28.95 = \mathbf{\$354.67}$
- **3-Year Total Price Return:** **+5.4%** (Annualized CAGR: **+1.8%**)

#### Scenario B: Elevated Consensus Baseline (Weight: 40%)
- **Premise:** The market continues to treat Apple as an elite consumer monopoly; valuation remains elevated at **34.00x** (near forward P/E).
- **Operational Performance:** Apple grows earnings inline with consensus expectations at **+10.0% CAGR**, reaching **$11.61** in Year 3.
- **Year 3 Terminal Price:** $\$11.61 \times 34.00 = \mathbf{\$394.61}$
- **3-Year Total Price Return:** **+17.2%** (Annualized CAGR: **+5.4%**)

#### Scenario C: AI / Services Supercycle (Weight: 15%)
- **Premise:** Apple Intelligence drives an aggressive iPhone upgrade supercycle and Services margins expand further; the market sustains a top-decile multiple of **36.20x** (90th percentile).
- **Operational Performance:** EPS accelerates to **+18.0% CAGR**, reaching **$14.33** in Year 3.
- **Year 3 Terminal Price:** $\$14.33 \times 36.20 = \mathbf{\$518.65}$
- **3-Year Total Price Return:** **+54.1%** (Annualized CAGR: **+15.5%**)

#### Scenario D: Macro De-Rating / ERP Normalization (Weight: 10%)
- **Premise:** Sticky inflation and higher-for-longer Treasury yields (10Y > 5.5%) force an equity risk premium correction. Apple de-rates toward its 10th percentile historical multiple of **21.00x**.
- **Operational Performance:** Revenue growth slows; EPS grows at **+6.0% CAGR**, reaching **$10.39** in Year 3.
- **Year 3 Terminal Price:** $\$10.39 \times 21.00 = \mathbf{\$218.10}$
- **3-Year Total Price Return:** **-35.2%** (Annualized CAGR: **-13.5%**)

### 4.2 Probability-Weighted Expected Value (3-Year Horizon)

| Scenario | Weight | 3y EPS | Exit P/E | 3y Exit Price | 3y Total Return | Annualized CAGR | Weighted Price Contribution |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **A: Mean Reversion** | 35% | $12.25 | 28.95x | $354.67 | +5.4% | +1.8% | $124.13 |
| **B: Consensus Baseline** | 40% | $11.61 | 34.00x | $394.61 | +17.2% | +5.4% | $157.84 |
| **C: AI Supercycle** | 15% | $14.33 | 36.20x | $518.65 | +54.1% | +15.5% | $77.80 |
| **D: Macro De-Rating** | 10% | $10.39 | 21.00x | $218.10 | -35.2% | -13.5% | $21.81 |
| **Expected Value (Total)** | **100%** | — | — | **$381.59** | **+13.4%** | **+4.26%** | **$381.59** |

### 4.3 Strategic Analyst Conclusion
- **Expected Return vs. Risk-Free Benchmark:**  
  The probability-weighted 3-year expected annualized price return is **+4.26%** (or approximately **+4.8%** including dividends).
- **The Core Asymmetry:**  
  This expected equity return is **lower than the 3-year/5-year risk-free Treasury yield (5.021%)**. In other words, an investor taking equity risk in Apple Inc. at $336.64 is expected to underperform risk-free government bonds unless Apple delivers an exceptional supercycle scenario (Scenario C).
- **Investment Implication:**  
  The current price of $336.64 leaves negligible margin of safety. Strong fundamental execution (~10–12% earnings growth) will largely be consumed by multiple contraction, resulting in bond-like or sub-bond returns for equity-level risk.