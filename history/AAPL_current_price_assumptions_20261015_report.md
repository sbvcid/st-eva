# AAPL 現價假設研究快照 — 整合驗收報告

**Research run:** `RES-4DC3AD389D`（2026-10-15 執行，ST-EVA `fd311c5` + earnings-method 來源標籤修正）
**指令：** `python st_eva_runner.py AAPL --mode live --historical-pe --historical-pfcf --context … --dossier … --dossier-report --json`
**性質聲明：** 本報告是反向估值的機械式重述。所有「隱含」數字都是「在明示倍數下，價格對應的基本面」，不是預測、合理價、機率或建議。文中沒有任何 LLM 參與。

---

## 1. 資料日期與口徑（先讀這節）

| 日期 | 意義 | 值 |
|---|---|---|
| 市場價格日 | live quote 的交易日 | **2026-10-14**，收盤 342.96 USD |
| 歷史重建最後評估日 | canonical 價格序列的最後交易日（P/E 與 P/FCF 共用） | **2026-10-06** |
| 歷史 P/E 評估期間 | 36 個申報可知日取樣 | 2018-01-02 → 2026-07-31 |
| 歷史 P/FCF 評估期間 | 36 個申報可知日取樣（35 個有效） | 2018-02-02 → 2026-07-31 |
| 共識預測期間 | Yahoo `+1y`（FY2027），來源宣告 period end | **2027-09-30** |

關鍵區分：**歷史分布的最後評估日（2026-10-06）早於市場價格日（2026-10-14）**。歷史觀測日期從不被當成目前價格日期；當前重建值（P/E 38.26、P/FCF 35.62）標註 2026-10-06，而 vendor 觀測值（現價、現值倍數）標註 2026-10-14。

## 2. 目前股價隱含的已支援假設

引擎在無使用者倍數輸入下的 reference 選擇（既有優先序：使用者 > production 分布 > vendor band）：

| 參考 | 選擇結果 | basis（context 記錄） |
|---|---|---|
| P/E reference | 28.4456 | `PRODUCTION_PE_MEDIAN`（36 obs，USABLE_FOR_REFERENCE） |
| P/FCF reference | 25.3440 | `PRODUCTION_PFCF_MEDIAN`（35 obs，USABLE_FOR_REFERENCE） |
| EV/EBITDA、P/S | 無 | `NONE`（無使用者輸入、無合格 band） |

由此確定性計算（公式見 context derivations，全部可獨立重算）：

| 隱含假設 | 值 | 公式 |
|---|---|---|
| 價格隱含 forward EPS | **12.0567 USD/股** | 342.96 ÷ 28.4456 |
| 相對共識的差距 | **+25.81%** | 12.0567 ÷ 9.58335 − 1 |
| 維持該 EPS 所需年成長（1 年期） | **37.63%/年** | (12.0567 ÷ 8.7608)^1 − 1 |
| 價格隱含 TTM FCF | **194.071B USD** | 4,918.53B ÷ 25.3440 |

解讀（口徑內）：以歷史 P/E 中位數為尺，目前價格隱含的 forward EPS 比分析師共識高 25.8%；以歷史 P/FCF 中位數為尺，目前價格隱含的 FCF 比 vendor 追蹤 FCF（136.68B）高 42%。兩者都是「價格相對歷史倍數較貴」的同一事實的兩種表述，不是市場預期的陳述。

## 3. 歷史 P/E 分布提供什麼

- **36 筆合格觀測 / 36 個評估日**，零拒絕。每筆 = 申報可知日收盤價 ÷ 四個連續財季（含 Q4）的 GAAP 淨利 EPS；Q4 由 8-K 2.02 釋出資料供給。
- 百分位：10th 17.33 / 25th 22.25 / **median 28.45** / 75th 32.44 / 90th 35.81（mean 27.26、σ 6.73）。
- Vendor band（8 obs）僅為 DESCRIPTIVE_ONLY，**未與 production 分布混合**；reverse matrix 的 80 個情境（4 個持有期 × 4 個要求報酬 × 5 個 P/E 百分位 exit）全部來自 production 分布，每個 exit 欄位標註 `production_historical_pe_percentile` + 樣本數 + 期間。
- 反推矩陣（fingerprint `45e67f0a…`）示例（1 年期、8% 要求報酬、10th 百分位 exit 17.33）：所需出場價 370.40，對應所需 terminal EPS 21.37——即較 trailing EPS 8.76 成長 144%。完整 80 情境見 dossier。

## 4. 歷史 P/FCF 分布提供什麼

- **35 筆有效觀測 / 36 個評估日**。唯一被拒：2018-01-02（OCF 概念缺 FY2016 Q1 span，詳見 §7）。
- 每筆 = as-traded 收盤 × 當時可知 cover-page 股數 ÷ TTM FCF（四個連續財季「營業現金流 − 資本支出」之和，全部 point-in-time 可知）。
- 百分位：10th 16.08 / 25th 20.49 / **median 25.34** / 75th 29.79 / 90th 31.96（mean 25.22、σ 6.56）。
- 當前重建值（2026-10-06）：**35.62** = 333.63 × 14,594,180,000 股（cover date 2026-07-17）÷ 136.683B。TTM 視窗 FY2025Q4→FY2026Q3，每季的 OCF/capex 差分、accession 與可知日都記錄在 artifact 中。
- 與 vendor 現值的差異是口徑差異：vendor 現值 P/FCF 35.98 用「即時價 342.96 × vendor 股數」÷ vendor 追蹤 FCF；重建值用「序列收盤 333.63 × 可知 cover-page 股數」。兩者從不互換。

## 5. Forward EPS 共識的樣本與近期變化

同一預測期間（+1y / FY2027，來源宣告 end 2027-09-30，幣別 USD，來源欄位 `trend[].earningsEstimate.*` 與 `trend[].epsTrend.*`）：

- **平均 9.58335**，40 位分析師，區間 [8.69, 10.67]（區間不是標準差）。
- 歷史共識序列（來源相對標籤原樣保留，未推導絕對日期）與同期差分：

| 來源標籤 | 共識值 | 變化量（vs 當前） |
|---|---|---|
| current | 9.58335 | — |
| 7daysAgo | 9.57579 | +0.00756 |
| 30daysAgo | 9.57254 | +0.01081 |
| 60daysAgo | 9.53948 | +0.04387 |
| 90daysAgo | 9.69285 | **−0.10950** |

- 修正人數（來源視窗，計數無幣別）：近 7 天上調 0、下調 2；近 30 天上調 4、下調 3；**90 天下調：來源未提供**（缺口保留為 UNAVAILABLE，未補零）。
- 讀法（口徑內）：90 天視窗共識下修 0.11（−1.1%），主要發生在 60–90 天前；近 30 天小幅上修。上調/下調「人數」不是修正「幅度」，幅度來自序列差分。

## 6. P/FCF 百分位情境（明示的機械式情境）

**定義：** 將歷史倍數百分位套用於目前市值（4,918.53B，2026-10-14 live 價 342.96 的 vendor 口徑）→ 隱含 FCF = 市值 ÷ 倍數。這是**機械式情境**：不是預測、不是合理價、不是機率、不是建議；五個情境對稱列出，**沒有任何一個被程式或本報告選為結論**。

| P/FCF 百分位 | 倍數 | 隱含 TTM FCF |
|---|---|---|
| 10th | 16.0816 | **305.8B** |
| 25th | 20.4935 | **240.0B** |
| 50th（median） | 25.3440 | **194.1B** |
| 75th | 29.7899 | **165.1B** |
| 90th | 31.9636 | **153.9B** |

每個情境在 artifact 中以 `market_cap ÷ multiple` 獨立重算驗證。情境輸入與矩陣完全分離：矩陣的 cash-flow method 維持僅接受使用者明示倍數，本情境在矩陣之外以明示輸入計算。

## 7. 可回答的問題與仍不可用的資料

**可由現有資料回答：** 價格在兩個歷史分布中的位置（P/E 342.96/8.76=39.15 vendor 口徑、重建 38.26，均高於各自分布 90th）；共識樣本與近期變化方向；各倍數下的隱含基本面；歷史百分位下的機械情境。

**仍不可用（缺口與原因）：**

| 缺口 | 原因類型 |
|---|---|
| `down_revisions_90d` | 來源不足（payload 空物件），保留為 UNAVAILABLE |
| Vendor P/FCF band | 來源不足（marketCap 與 FCF 無共同日期）；production 重建是唯一歷史 P/FCF 參考，兩者不混合 |
| `consensus_cross_check.price_at_historical_median_pe` | 方法口徑：該欄位僅讀 vendor band（8 obs，不合格）→ null；production median 未接入此欄位。已記錄，未以 production 數字回填 |
| 矩陣 cash-flow/EV/revenue method | 契約：需使用者明示倍數；情境倍數在矩陣外以明示輸入計算 |
| 無風險利率/CAPM | 本次未請求 |
| SEC 宣告股利 | 未取得該類觀測 |

**資料限制（P/FCF 重建，記錄於 dataset manifest）：** OCF 概念缺 AAPL FY2016 Q1 → 首個評估日被拒；FY2016/17 OCF 經 comparative 才進入概念 → 這些視窗可知時間晚於當時公開可得（保守方向，絕不提早）；FY2018 10-K 的 ASU 2016-18 重述按 R-PIT-SUPERSEDE 於其自身可知日後生效。歷史分布因此**不是**完整的 point-in-time 重建宣稱，是「本資料集可證明的最保守重建」。

## 8. 內部一致性驗證

20 項程式化檢查全部通過（`AAPL_historical_references_20261015.json` 的 `internal_consistency_checks`）：reference block ↔ payload ↔ context 三方一致；context basis 為 PRODUCTION_* 而非 vendor band；earnings-method 來源標籤正確（`production_historical_pe_percentile`，非 user assumption）；TTM 各季可知日 ≤ 評估日、視窗含 Q4、季和 = TTM 總額、當前重建值可重算；18 個共識 metric 單一期間（2027-09-30）；down_90d 缺口未補零；五個情境各自可重算且無自動選擇。

跨來源交叉驗證（--context 併同取得的 SEC filing 觀測，dossier 記錄）：7 個 metric 交叉檢查 — EPS diluted、淨利、營收 **CONSISTENT**（差異 0.0000%）；股數 **PERIOD_MISMATCH**（數值相同但 vendor 端無日期，無法確認同時點）；現金 **METHODOLOGY_MISMATCH**（幣別口徑不同）；assets 與長期債 vendor 端缺。無任何一端被指定為權威值，兩端原樣保留。

## 9. 資料分層聲明

- **真實觀測值：** 價格（2026-10-14）、trailing/consensus EPS、分析師人數與區間、共識歷史序列、修正人數、SEC 現金流事實（accession 可查）、cover-page 股數。
- **公式計算值：** 隱含 EPS/EPS gap/所需成長/隱含 FCF、TTM 差分、兩個歷史分布的每筆倍數、當前重建值。
- **明示情境輸入：** §6 的五個 P/FCF 百分位 → 隱含 FCF；矩陣的 P/E 百分位 exit（標註樣本數）。
- **不可用：** §7 表列各項，全部帶原因碼，未補零。

## 10. 產物清單

| 產物 | 內容 |
|---|---|
| `history/AAPL_RES-4DC3AD389D_market_implied_assumptions.json` | 執行快照（慣例格式） |
| `history/AAPL_context_20261015.json` | Investment Context（自驗證通過，context_id `ctx_6aa52366…`） |
| `history/AAPL_research_dossier_20261015.json` + `_report.txt` | 完整 dossier（含 80 情境矩陣、估值方法、限制） |
| `history/AAPL_historical_references_20261015.json` | 兩個 production 分布 + 五個 P/FCF 情境 + 20 項一致性檢查 |
| 本檔案 | 整合驗收報告 |
