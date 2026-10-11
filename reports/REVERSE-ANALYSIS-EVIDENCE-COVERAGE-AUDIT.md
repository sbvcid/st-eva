# ST-EVA — Reverse-Analysis Evidence Coverage Audit Report

**Status:** COMPLETED / READ-ONLY AUDIT  
**Date:** 2026-10-10  
**Scope:** Repository Core, SQLite Archives (`data/archives/AAPL.sqlite`, `MSFT.sqlite`, `TSM.sqlite`), Central Data Store (`data/st-eva.sqlite`), Data Ingestion Pipelines, Deterministic Valuation Engine (`st_eva_runner.py`), Evidence Packaging (`investment_context.py`), and LLM Interface Boundary (`llm_interpreter.py`).  
**Mode:** Strict Read-Only Audit (Zero schema changes, zero database mutations, zero synthetic data interpolation, zero mock/live LLM API invocations).

---

## 摘要與核心結論 (Executive Summary)

本稽核旨在回答核心問題：**「ST-EVA 目前的資料庫、資料管線、時間序列、確定性計算及證據封裝，是否足以向外部 LLM 提供進行多種金融反向分析（Reverse Valuation Analysis）所需的資料？」**

經對原始程式碼、Schema、現存中央資料庫與實際封存資料庫（AAPL/MSFT/TSM）進行深入且可重現的唯讀檢查，核心結論如下：

1. **現存實際資料的斷層**：
   - **中央資料庫 (`data/st-eva.sqlite`) 為空結構**（41 張資料表全部為 0 筆資料）。
   - **單一公司封存庫 (`data/archives/AAPL.sqlite`, 92 筆 observations)** 包含兩類截然不同的資料源：
     - **YahooFinance / Fundamentals API**：提供最新單一時點快照（`price`, `trailing_eps`, `forward_eps`, `ebitda`, `free_cash_flow` 等各 1 筆），且其歷史估值倍數分佈（`pe_band` 8 筆、`ps_band` 9 筆、`ev_ebitda_band` 8 筆、`pfcf_band` null）均低於系統規定的最低門檻 20 筆（`MIN_BAND_OBSERVATIONS_FOR_REFERENCE = 20`），全面標記為 `INSUFFICIENT_OBSERVATIONS`。
     - **SEC EDGAR Regulatory Filing**：僅針對 `revenue`（13 筆）、`eps_diluted`（14 筆）、`net_income`（14 筆）、`cash`（9 筆）、`assets`（8 筆）、`long_term_debt`（8 筆）、`shares_outstanding`（9 筆）有季報/年報點時觀測，覆蓋約 2024–2026 年（約 2 年跨度）。
2. **反向分析路徑能力分佈**：
   - **P/E → Implied Forward EPS 及所需 EPS CAGR**：現有程式具有完整確定性實作（`MarketImpliedAssumptionsEngine.analyze`），但在預設依賴歷史中位數時，因 `pe_band` 僅 8 筆，歷史參考被拒絕；若由使用者顯式指定 `reference_multiple`，計算可執行，但消耗的是 API 的即時單筆快照，而非點時可審計的 GAAP 歷史序列。
   - **P/S → Implied Revenue 及所需 Revenue CAGR**：程式可反解 `implied_revenue`（`market_cap / selected_ps`），但**尚未實作所需的 Revenue CAGR 衍生運算**；且 `ps_band` 僅 9 筆，歷史參考被拒絕。
   - **EV/EBITDA → Implied EBITDA 及 Margin 條件**：程式可反解 `implied_ebitda`（`enterprise_value / selected_ev_ebitda`），但**尚未實作 EBITDA margin 反推條件與營收約束公式**；且 `ev_ebitda_band` 僅 8 筆，歷史參考被拒絕。
   - **P/FCF → Free Cash Flow 及營運條件**：程式可反解 `implied_fcf`，但現有資料庫中 `pfcf_band` 完全為 `null`，無顯式倍數時徹底無法計算，亦無營運資本或 FCF 條件模型。
   - **會計恆等與推導（EPS、淨利、營收、利潤率、股數）**：引擎僅實作了單一 `implied_net_margin` 粗略推導，但因為 SEC 事實進入 ValuationInputs 的準入邊界（`evidence_valuation_boundary.py`）目前在 V1 **被硬編碼僅允許 `revenue` 單一指標 crossing**，其餘 SEC 事實（`eps_diluted`, `net_income`）無法進入引擎，且引擎禁止就地差分計算 Q4 EPS 或未經申報之合成財務比率。
3. **證據封裝與 LLM 介面狀態**：
   - `investment_context.py` 能產出嚴格可溯源的 JSON 證據包（帶有 `depends_on`, `operation`, `expression`, `parity_check`）。
   - 然而目前的證據包主要提供「最新單一決策時點之截面圖」，**缺乏提供歷史點時序列供 LLM 對比與檢驗假設成立與否之能力**。
   - `llm_interpreter.py` 僅產生純文字提示詞模板，嚴格禁止模型推論回寫，但尚未具備向 LLM 揭露「反例歷史數據」、「不同期間估值倍數變遷分佈」的結構化支撐。

---

## 一、現有實作與資料分類檢查

依據規格與現有程式碼，將目前 ST-EVA 各項能力分類如下：

| 能力項目 | 分類判定 | 實作依據 / 模組 | 實際資料現況 (以 AAPL.sqlite / st-eva.sqlite 為例) |
|---|---|---|---|
| **市場即時價格與價量指標** | **已有可用實作及實際資料** | `st_eva_runner.py`, `data_contract.py` | `price` 1 筆 (2026-10-08), `price_history` / `volume_history` (63 個交易日), `price_volume_metrics` (計算出 realized vol, Parkinson vol 等) |
| **條件式 P/E 反向計算 (隱含 EPS、所需 CAGR、共識差距)** | **已有實作，但現有資料不足** | `st_eva_runner.py:1401-1409` | 算術完全確定性，但預設之 `pe_band` 僅 8 筆（門檻需 20 筆），被判定 `INSUFFICIENT_OBSERVATIONS`。需使用者顯式傳入 `reference_multiple` 始可計算 |
| **條件式 P/S 反向計算 (隱含 Revenue)** | **已有實作，但現有資料不足** | `st_eva_runner.py:1424` | 程式可計算 `implied_revenue`，但 `ps_band` 僅 9 筆（不足 20 筆）；且未包含 Revenue CAGR 與營收條件推導 |
| **條件式 EV/EBITDA 反向計算** | **已有實作，但現有資料不足** | `st_eva_runner.py:1418-1420` | 可計算 `implied_ebitda`，但 `ev_ebitda_band` 僅 8 筆（不足 20 筆），且缺 EBITDA margin 限制條件 |
| **條件式 P/FCF 反向計算** | **已有實作，但現有資料不足** | `st_eva_runner.py:1412-1413` | 可計算 `implied_fcf`，但 `pfcf_band` 在 AAPL.sqlite 為 `null`，無任何樣本，完全依賴外部輸入 |
| **SEC GAAP 基礎觀測保存 (營收、淨利、稀釋 EPS、資產、現金、長債、股數)** | **已有可用實作及實際資料** | `archive/`, `sqlite_archive.py`, `sec_provider.py` | AAPL.sqlite 中存在 2024Q2～2026Q3 期間之 10-Q/10-K 正式申報 facts (各 8～15 筆)，具備 SEC accession 與 acceptance_datetime |
| **SEC 事實跨越至估值輸入 (Valuation Boundary Admission)** | **已有原始資料，尚未完成必要的衍生計算或證據封裝** | `evidence_valuation_boundary.py` | 目前 V1 crossing scope 硬編碼僅允許 `V1_CROSSING_METRICS = (METRIC_REVENUE,)`，`eps_diluted`, `net_income`, `ebitda`, `fcf` 均被擋在門外，無法進入 ValuationInputs |
| **歷史 TTM P/E 點時重組 (Historical P/E Engine - 方案 B)** | **已有原始資料，尚未完成必要的衍生計算或證據封裝** | `research/experiments/aapl-historical-pe-poc/` (研究已驗證，Production 未實作) | 規格已於 `ADR-HISTORICAL-PE-METHODOLOGY.md` 定案 (FROZEN)，POC 已在 AAPL 達成 31/31 點時 TTM 計算，但 Production 尚無 Python 模組、無測試、無資料表整合 |
| **跨期基本面恆等關係驗證 (淨利、利潤率、營收、股數)** | **已有實作，但現有資料不足** | `st_eva_runner.py:1425-1429`, `cross_validation.py` | 僅實作 `implied_net_margin` 單一比率；`cross_validation.py` 僅用於 vendor vs sec 比對，不提供反向分析所需的約束聯立方程 |
| **時間序列與多時點點時回溯 (Point-in-Time Historical Replay)** | **已有實作，但現有資料不足** | `archive.py`, `historical_state_reconstruction_331.py` | Replay 架構能回溯特定 `as_of` 切片，但因資料庫僅有 2 年 SEC 資料且無歷史價格時序庫，無法生成連續歷史估值倍數變遷鏈 |
| **外部 LLM 結構化證據封裝** | **已有可用實作及實際資料** | `investment_context.py` | 能產生具備 refs, depends_on, validation, parity check 的 JSON，但僅限於最新單點快照，無法提供歷史時間序列供 LLM 反向推論 |
| **外部 LLM 雙向互動與假設檢驗** | **尚無實作** | `llm_interpreter.py` (現為單向 Prompt Generator) | 無 LLM API 呼叫、無即時假設評估介面、無法將 LLM 假設帶回引擎重新執行條件運算 |

---

## 二、反向分析覆蓋矩陣 (Reverse-Analysis Coverage Matrix)

| 反向分析路徑 | 計算所需輸入 | 目前實際存在之資料與觀測數 (AAPL) | 可追溯性 (來源與期間) | 單位與時間欄位 | 現有程式能否計算 | 缺失輸入與無法計算原因 | 最小必要補充工作 |
|---|---|---|---|---|---|---|---|
| **1. P/E → Implied EPS 及所需 EPS CAGR** | (1) 當前價格 $P_0$<br>(2) 參考本益比 $M_{pe}$<br>(3) Current EPS<br>(4) 預測期 $T$<br>(5) 共識 EPS | • Price: 1 筆 ($258.98)<br>• Current EPS: 1 筆 ($8.72, Yahoo)<br>• Forward EPS: 1 筆 ($9.59)<br>• Consensus EPS: 1 筆 ($9.58)<br>• pe_band: 8 筆 samples | • Price: API_LIVE (2026-10-08)<br>• EPS: API_LIVE (as_of None, 期間未聲明)<br>• pe_band: 8 個歷史時點 (2024-06-10 ~ 2026-09-17) | • Price: USD, date<br>• EPS: USD/share, 無 period_start/end<br>• pe_band: multiple, samples 無期間聲明 | **條件式可計算**<br>(若給定倍數)；<br>**不可自動計算**<br>(若依賴歷史分佈) | • 歷史 `pe_band` 僅 8 筆 (< 20 筆)，觸發 `INSUFFICIENT_OBSERVATIONS`，拒絕提供 median。<br>• 缺少 GAAP 申報之可審計點時 TTM EPS。 | 1. 允許使用者輸入顯式倍數（目前已支援）。<br>2. 落地 ADR-HISTORICAL-PE-METHODOLOGY 產出可審計的 20+ 筆點時 TTM P/E。 |
| **2. P/S → Implied Revenue 及所需 Revenue CAGR** | (1) 市值 Market Cap<br>(2) 參考市銷率 $M_{ps}$<br>(3) Current Revenue<br>(4) 預測期 $T$ | • Market Cap: 1 筆 ($3.89T)<br>• Current Revenue: 1 筆 ($391.0B, Yahoo)<br>• SEC Revenue: 15 筆<br>• ps_band: 9 筆 samples | • Market Cap: API_LIVE (2026-09-23)<br>• Yahoo Rev: API_LIVE (2026-06-30)<br>• SEC Rev: REGULATORY_FILING (2024Q2 ~ 2026Q3)<br>• ps_band: 9 個時點 (2024-06-10 ~ 2026-09-17) | • Market Cap: USD<br>• Revenue: USD, 季/年報 period_start/end<br>• ps_band: multiple | **部分可計算**<br>(可算 Implied Revenue；**無法算 Required Revenue CAGR**) | • `ps_band` 僅 9 筆 (< 20)，拒絕自動中位數。<br>• 引擎中**未實作 Revenue CAGR 運算邏輯**（僅有 EPS CAGR）。 | 1. 於 `st_eva_runner.py` 與 `operation_registry.py` 增加 `required_revenue_cagr` 算術運算與註冊。<br>2. 補充足夠 P/S 歷史樣本。 |
| **3. EV/EBITDA → Implied EBITDA 及 Margin 條件** | (1) 企業價值 EV<br>(2) 參考倍數 $M_{ev}$<br>(3) Current EBITDA<br>(4) Revenue 預估值 (算 margin) | • EV: 1 筆 ($3.95T)<br>• EBITDA: 1 筆 ($134.7B, Yahoo)<br>• ev_ebitda_band: 8 筆 samples | • EV: API_LIVE (2026-09-23)<br>• EBITDA: API_LIVE (2026-06-30)<br>• ev_band: 8 個時點 (2024-06-10 ~ 2026-09-17) | • EV: USD<br>• EBITDA: USD<br>• ev_ebitda_band: multiple | **部分可計算**<br>(可算 Implied EBITDA；**無法算 Margin 約束**) | • `ev_ebitda_band` 僅 8 筆 (< 20)，拒絕自動參考。<br>• 引擎**未定義 EBITDA Margin 推導運算**與條件關係。 | 1. 於引擎增加 EBITDA Margin 及隱含營收/利潤率聯立推導公式。<br>2. 補充 EV 與 EBITDA 點時歷史時序。 |
| **4. P/FCF → Free Cash Flow 及營運條件** | (1) 市值 Market Cap<br>(2) 參考市現率 $M_{pfcf}$<br>(3) Current FCF<br>(4) 營運現金流與 CapEx 拆解 | • Market Cap: 1 筆<br>• Current FCF: 1 筆 ($104.7B, Yahoo)<br>• pfcf_band: **0 筆 (null)** | • Market Cap: API_LIVE<br>• FCF: API_LIVE (2026-06-30)<br>• pfcf_band: 無資料 | • Market Cap: USD<br>• FCF: USD<br>• pfcf_band: multiple | **完全依賴手動輸入**<br>(若未手動給倍數則為 null) | • `pfcf_band` 完全缺失（Yahoo fundamentals 未回傳或未解析）。<br>• 缺少 CapEx 與 OCF 拆解能力。 | 1. 解析 SEC 現金流量表（Operating Cash Flow − CapEx）建立點時 FCF。<br>2. 建立 P/FCF 歷史時間序列。 |
| **5. 基本面恆等推導 (EPS、淨利、營收、利潤率、股數)** | (1) Diluted EPS<br>(2) Net Income<br>(3) Revenue<br>(4) Diluted Shares<br>(5) Net Margin | • SEC 申報有齊全的 Revenue (15), Net Income (14), EPS Diluted (14), Shares (9)<br>• Yahoo 快照有最新單筆 | • SEC 事實具完整 10-Q/10-K 追溯期與 accession<br>• Yahoo 資料無期間分解 | • EPS: USD/share<br>• NI/Rev: USD<br>• Shares: count<br>• Margin: ratio | **受限於架構隔離而無法在引擎中聯立計算** | • `evidence_valuation_boundary.py` 之 V1 scope 僅開放 `revenue`，其餘指標無法進入 `ValuationInputs`。<br>• 引擎目前僅實作單向 `implied_net_margin = implied_eps / (implied_rev / shares)`。 | 1. 擴充 admission boundary crossing scope，允許 SEC 驗證過的 Net Income 與 Diluted Shares 進入。<br>2. 在 `investment_context` 註冊恆等式驗證運算。 |
| **6. 多時間點價格、倍數與基本面變動** | 多個歷史時點 $t_k$ 的截面數據集 $(P_{t_k}, M_{t_k}, F_{t_k})$ | 目前 AAPL.sqlite 僅有最新 1 筆價格，歷史價格僅存於 `price_history` 陣列（無對應歷史倍數截面） | 歷史價格為最近 63 交易日，但無歷史截面關聯 | 日期、收盤價、無歷史截面 ID | **尚無實作** | • 系統架構雖支援 Replay，但目前資料庫無歷史價格與財務資料的跨期配對快照庫。 | 1. 依據 ADR-HISTORICAL-PE-METHODOLOGY 建立多時點配對資料表。<br>2. 實作多時點截面導出器。 |
| **7. 歷史估值分佈作為明確標示參考** | 足額的歷史倍數樣本分佈（$N \ge 20$），包含百分位數與樣本血統 | • PE: 8 筆<br>• PS: 9 筆<br>• EV/EBITDA: 8 筆<br>• PFCF: 0 筆 | 外部 API 靜態陣列，無每日配對算術血統 | multiple, 樣本僅帶日期無 period | **已有實作，但現有資料不足** | 樣本數低於 20 筆，被 `band_is_usable_for_reference()` 嚴格拒絕。 | 1. 不降低 20 筆之安全防線。<br>2. 透過內部歷史配對管線生成足額樣本。 |

---

## 三、時間序列與證據鏈稽核 (Time-Series & Provenance Audit)

### 3.1 原始資料來源識別與指紋保存
- **SEC EDGAR 資料**：
  - **優良**：每一筆 SEC 觀測皆在 `observations` 表保留了 `accession`（如 `0000320193-24-000106`）、`taxonomy`（`us-gaap`）、`form`（`10-Q` / `10-K`）、`fiscal_year`、`fiscal_period` 及 `content_hash`。
  - 在 `source_documents` 表中支援原始 SGML/XML 檔案之 gzip BLOB 保存與 SHA-256 驗證。
- **Yahoo Finance API 資料**：
  - **薄弱**：僅記錄 `provider = 'YahooFinanceFundamentals'`，`source_type = 'API_LIVE'`，其 `raw_json` 僅為該 API 回傳的鍵值，無原始 HTTP payload 指紋，且 `trailing_eps`、`forward_eps` 的 `as_of` 全數為 `null`，亦無對應財報期間。

### 3.2 時間語意傳遞 (`as_of`, `available_at`, `period_start`, `period_end`)
- **語意嚴格分離**：
  - `period_start` / `period_end`：精確標示財務事實所屬的會計期間（例如 `2024-03-31` 至 `2024-06-29` 標示為 90 天之 discrete quarter）。
  - `as_of`：標示事實的基準時點。
  - `available_at`：標示市場可獲知時間（SEC acceptance timestamp，例如 `2024-08-02T02:03:34.000Z`）。
  - `retrieved_at`：標示 ST-EVA 系統抓取該資料的時間。
- **已知問題與時間斷層**：
  - SEC Fact 具有上述完整時間欄位；但 Yahoo API 提供的即時數據（如 `price`、`market_cap`、`trailing_eps`）其 `available_at` 被直接填入 `OBSERVATION_INSTANT` 或 `null`，喪失了「該 EPS 究竟是哪一天發布」的點時追溯能力。

### 3.3 歷史估值倍數之時間對齊與 Lookahead Bias 防範
- **防範規範已完全定案**：
  - `ADR-HISTORICAL-PE-METHODOLOGY.md` 明確規定：
    1. 採用 `acceptance_datetime` 作為可用性硬邊界。
    2. 採用「16:00 ET 截止常規」：16:00 前申報於當日收盤配對，16:00 盤後申報延至次一交易日（T+1）配對。
    3. 嚴禁算術差分推導 Q4 EPS（防止製造合成數據）。
    4. 嚴禁 Lookahead Bias：不得以未來重編資料回溯覆蓋。
- **實際執行現狀**：
  - 現存資料庫中之 `pe_band` 來自外部 Yahoo API，其 8 筆樣本（如 `2024-06-10: 30.03`, `2024-07-12: 35.86`）完全為第三方黑箱計算，無法驗證其分子價格與分母 EPS 是否符合上述防 Lookahead Bias 規範。

### 3.4 衍生結果追溯性與可信度標籤
- **審計鏈架構健全**：
  - `investment_context.py` 的每一個衍生數值均攜帶 `depends_on` 參照清單、`operation` 註冊項、`expression` 字串與 `parity_check` 誤差驗證。
  - 系統嚴格遵循 **「不使用單一綜合可信度分數」** 的原則，而是以具體的列舉狀態呈現：`VALID`、`UNVERIFIABLE`、`SINGLE_SOURCE`、`INSUFFICIENT_OBSERVATIONS`、`CONFLICTING`、`UNAVAILABLE`。

---

## 四、歷史估值參考資料評估 (Historical Valuation Reference Audit)

針對 P/E、P/S、EV/EBITDA、P/FCF 四大倍數之歷史參考資料，檢查結果如下：

| 倍數類型 | 實際觀測數量 (AAPL) | 判定狀態 | 現狀與代表性限制 |
|---|---|---|---|
| **P/E Band** | 8 筆 | **有部分歷史資料，但不足以支持目前規定的參考方法** | 樣本僅 8 筆，遠低於門檻 20 筆。數值介於 30.03 至 39.01。計算樣本跨度僅 2 年，無法代表完整景氣循環，且分母口徑不可考。 |
| **P/S Band** | 9 筆 | **有部分歷史資料，但不足以支持目前規定的參考方法** | 樣本僅 9 筆，低於門檻 20 筆。數值介於 7.74 至 10.66。同樣受限於樣本不足與採樣定義黑箱。 |
| **EV/EBITDA Band** | 8 筆 | **有部分歷史資料，但不足以支持目前規定的參考方法** | 樣本僅 8 筆，低於門檻 20 筆。數值介於 22.29 至 29.41。分子 EV 與分母 EBITDA 之口徑未經 SEC 點時校驗。 |
| **P/FCF Band** | 0 筆 (null) | **沒有歷史資料** | 資料庫中完全無任何樣本，系統直接判定為 `UNAVAILABLE`。 |

> **稽核結論**：
> 目前 ST-EVA 依賴的外部歷史倍數資料**在全部四個維度上均無法作為合法的估值參考依據**。這證明了先前 ADR-HISTORICAL-PE-METHODOLOGY 決定啟動「方案 B（內部構建點時估值序列）」的必要性與正確性。

---

## 五、證據資料包向外部 LLM 傳遞能力評估

評估 `investment_context.py` 與 `llm_interpreter.py` 生成的資料包是否足以支援外部 LLM 進行嚴謹金融反向分析：

| 評估維度 | 目前支援程度 | 具體評估細節與落差說明 |
|---|---|---|
| **1. 數值來源與定義之理解** | **充分支援** | 每個數值均有明確的 `ref`（如 `obs:ev-price-001`）、`unit`、`currency`、`provenance_kind`（OBSERVED/DERIVED/CONDITIONAL），LLM 可精確分辨數值意義。 |
| **2. 讀取適當歷史序列** | **嚴重不足** | 目前資料包僅包含截面數字（單一價格、單期 EPS、靜態 Band 百分位數）與 63 天價量序列。**完全缺乏歷史財務指標時間序列（例如過去 5 年各季營收、淨利、EPS 的變動時序）**，LLM 僅能看到最新一期數字，無法進行歷史軌跡對比。 |
| **3. 區分觀測、計算、假設與推論** | **充分支援** | 資料結構強制區分 `OBSERVED`（外部觀測）、`DERIVED`（確定性計算）與 `CONDITIONAL`（條件反推）。提示詞模板嚴格禁止模型將推論偽造為原始事實。 |
| **4. 使用不同明確假設檢驗條件式反向計算** | **部分支援** | 若使用者/外部呼叫者主動帶入不同的倍數參數（`reference_multiple`），引擎能計算並封裝；但**資料包本身是靜態的**，未包含多劇本敏感度矩陣（Sensitivity Matrix），LLM 必須自行在外部做乘除法。 |
| **5. 尋找限制假設成立之歷史證據或反例** | **完全不足** | 資料包中**未包含公司歷史最高/最低成長率、產業下行期獲利波動、歷史利潤率區間等基準事實**。當 LLM 反推出「股價隱含需要 25% EPS CAGR」時，LLM 在資料包內找不到「該公司過去 5 年最高 CAGR 僅 12%」的反例證據，導致無法進行壓力測試。 |
| **6. 揭示計算可用性與缺失原因** | **充分支援** | `unavailable` 區塊明確列出無法計算的指標，並帶有受控詞彙原因代碼（如 `INSUFFICIENT_OBSERVATIONS`, `MISSING_INPUT`, `NO_REFERENCE_AVAILABLE`）。 |
| **7. 重要結論之可審計證據鏈** | **充分支援** | 凡是系統計算出的數值，皆可透過 `der:` 引用追溯至 `inputs_observed_at` 與運算子表達式，parity error 檢查可保證數字重算一致性。 |

---

## 六、各反向分析路徑阻塞點與證據缺口分析

### 6.1 核心阻塞點（依重要性排序）

```
[阻塞點 1: 缺少點時歷史估值倍數時間序列]
       │
       ├── 現況: 外部 API 僅給 8~9 筆黑箱快照，觸發 INSUFFICIENT_OBSERVATIONS 拒絕
       └── 影響: 所有 4 條反向路徑（P/E, P/S, EV/EBITDA, P/FCF）在自動模式下全線停擺

[阻塞點 2: 準入邊界 (Admission Boundary) 僅開放 Revenue]
       │
       ├── 現況: evidence_valuation_boundary.py 規定 V1_CROSSING_METRICS = (revenue,)
       └── 影響: SEC 庫中已驗證的 14 筆 eps_diluted 與 net_income 無法進入估值引擎

[阻塞點 3: 引擎反向運算模型覆蓋不全]
       │
       ├── 現況: 僅實作 Implied Forward EPS 及 EPS CAGR；缺 Revenue CAGR、EBITDA Margin
       └── 影響: P/S 與 EV/EBITDA 反推停留在絕對金額，無法進一步產出研究者所需的條件約束

[阻塞點 4: 證據包缺乏歷史基準序列 (Historical Baseline Series)]
       │
       ├── 現況: 僅封裝最新截面數字，無歷史營收成長率、利潤率區間與景氣反例
       └── 影響: 外部 LLM 空有反解結果，卻無法對比歷史極限來評估假設的合理性
```

### 6.2 缺口性質歸類：資料缺失 vs 研究方法限制

1. **純粹可透過資料處理或取得解決的缺口（Engineering & Data Gap）**：
   - **落地 Historical P/E 點時管線**：依據已核准的 ADR-HISTORICAL-PE-METHODOLOGY，利用 SEC 官方事實與已發生價格，計算出 20+ 筆可審計的歷史 P/E 分佈。
   - **擴充 Admission Boundary 涵蓋範圍**：將驗證過的 SEC `eps_diluted` 與 `net_income` 加入 crossing scope。
   - **完善算術公式**：在 `st_eva_runner.py` 與 `operation_registry.py` 中補充 Revenue CAGR、EBITDA Margin 等確定性算術。
2. **屬於研究方法與本質限制的缺口（Methodological Boundaries）**：
   - **Q4 Diluted EPS 不能由減法推導**：依據 ADR 規定，發行人未直接申報的數字絕對不能由算術相減製造，若無 8-K EX-99.1 等一級直接陳述證據，TTM 必須降級為 `UNAVAILABLE`。這是方法論的「真實性約束」，而非資料處理缺陷。
   - **價格不等於單一真實預期**：反向推導出的「隱含獲利」永遠是條件式的，取決於選擇的倍數，不能將其包裝為「市場唯一共識」。
   - **零合成財務資料（Zero Synthetic Data）**：當缺乏資料時，堅持 `UNAVAILABLE`，絕不進行線性插值或同業平均填補。

---

## 七、架構保留與擴充決策建議

### 7.1 應嚴格保留的現有架構 (Preserve)
- **資料分層體系**：`Provider -> Observation -> Evidence -> Admission -> Engine -> Derived -> Snapshot`。此分層成功隔絕了外部髒資料與未驗證推論。
- **不可變雜湊與血統追溯**：`observation_content_hash()` 與 `investment_context.py` 的平坦化引用表（refs table）。
- **點時可用性硬邊界**：以 SEC `acceptance_datetime` 與 16:00 ET 收盤常規杜絕 Lookahead Bias。
- **確定性運算與可重演性**：核心算術維持純 Python 確定性執行，禁止隨機黑箱。
- **嚴格門檻**：維持 `MIN_BAND_OBSERVATIONS_FOR_REFERENCE = 20`，寧可標記不可用，也不接受 8 筆資料造成的虛假百分位數。

### 7.2 目前缺乏足夠理由的過度擴充 (Do Not Expand Yet)
- **切勿引入複雜的 DCF 或 WACC 貼現模型**：違背 ST-EVA 反向工程之核心哲學，引入過多主觀未驗證參數。
- **切勿引入即時雙向 LLM 決策迴圈**：在基礎數據與歷史序列尚未健全前，讓 LLM 直接介入運算或回寫資料庫只會擴大不確定性與不可審計風險。
- **切勿草率放寬門檻以迎合 Yahoo 8 筆樣本**：降低門檻至 5 筆或 8 筆會嚴重破壞統計代表性，掩蓋真實的證據缺陷。

---

## 八、最小且合理的後續工作順序 (Minimal Sequential Next Steps)

依據本次稽核之客觀證據，建議下一階段的工作順序如下：

1. **Step 1: 實作 ADR-HISTORICAL-PE-METHODOLOGY 之 Production 模組 (HPE-1)**
   - 將已在 `research/experiments/aapl-historical-pe-poc/` 驗證過的 31/31 TTM 計算邏輯正式工程化為 Production 模組。
   - 納入 8-K EX-99.1 一級直接陳述證據解析，解決 AAPL 等發行人 Q4 Diluted EPS 缺失問題。
   - 在 AAPL.sqlite 生成超過 20 筆符合點時規範的 `pe_band` 觀察值，解除 P/E 反向路徑的 `INSUFFICIENT_OBSERVATIONS` 封鎖。
2. **Step 2: 擴充 Admission Crossing Scope 與 Engine 輸入 (V1.1 Boundary)**
   - 在 `evidence_valuation_boundary.py` 中，將 crossing scope 由 `(METRIC_REVENUE,)` 擴展至包含經過點時驗證的 `METRIC_EPS_DILUTED` 與 `METRIC_NET_INCOME`。
   - 讓引擎的 `current_eps` 能直接消費來自 SEC 的點時 TTM 數據，取代目前不可追溯的 Yahoo 單點快照。
3. **Step 3: 補齊 P/S 與 EV/EBITDA 的確定性反向算術公式**
   - 於 `st_eva_runner.py` 與 `operation_registry.py` 中新增 `required_revenue_cagr` 及 `implied_ebitda_margin`。
   - 同步更新 `investment_context.py` 的運算子註冊與 parity check。
4. **Step 4: 擴充 Context 證據資料包之歷史基準序列 (Historical Context Package)**
   - 在 `investment_context.py` 中新增 `historical_series` 區塊，提供過去 3～5 年的年度/季度成長率區間、利潤率分佈與估值倍數變遷軌跡。
   - 使外部 LLM 在讀取資料包時，能對比當前價格隱含的假設與歷史極限，產生具有壓力測試實質意義的客觀反向分析報告。

