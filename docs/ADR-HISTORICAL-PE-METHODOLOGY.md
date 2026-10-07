# ADR: Historical P/E Valuation Reference Methodology

**Status:** APPROVED / FROZEN (Methodology Specification)  
**Date:** 2026-10-07  
**Amended:** 2026-10-07 (Amendment 1 — evidence class separation; see §2.1 and §6.1)  
**Scope:** ST-EVA Valuation Core & Evidence-Valuation Boundary  
**File:** `docs/ADR-HISTORICAL-PE-METHODOLOGY.md`  

> **Amendment 1 is minimal and additive.** It introduces a second primary
> evidence class (§2.1 Decision 10–14), corrects one stated rationale in
> Decision 4 without relaxing it, and disambiguates `REASON_MISSING_Q4_EPS`.
> No existing decision is withdrawn. Decisions 1–9 and 10–14 are equally
> frozen; an engine implementing only the original nine is incomplete for any
> issuer that stops tagging quarter-length EPS in its 10-K.

---

## 1. Context & Problem Statement

ST-EVA 要求逆向工程（Reverse Valuation）之參考倍數（Reference Multiple，如歷史 P/E 50th percentile）必須基於充足、可驗證之歷史觀察值（`MIN_BAND_OBSERVATIONS_FOR_REFERENCE = 20`）。

經診斷，現有外部數據源 `YahooFinanceFundamentals` 的 `fundamentals-timeseries` API 僅保存 3～10 筆零星快照（如 AAPL 8 筆、MSFT 7 筆、MU 3 筆），在物理上無法提供足夠的歷史 P/E 觀察值。

因此，ST-EVA 確立**方案 B**：
不依賴第三方不可審計的歷史倍數黑箱，改由 **ST-EVA 內部 Engine 依據可追溯的原始市場價格、SEC EDGAR 官方申報事實與確定性 Point-in-Time 規則，決定性建立可重演（deterministic & replayable）的歷史估值觀察值（Historical Valuation Observations）**。

---

## 2. Frozen Decisions (已定案架構決策)

以下決策已經過充分論證並正式封存，後續實作 Engine 時**嚴禁變更**：

1. **方案 B 核心架構**：
   - 估值倍數不是外部 Provider 提供的原語，而是由 ST-EVA Engine 由「經過驗證的原始市場價格時間序列」與「SEC EDGAR 點時申報事實」嚴格計算得出。
2. **SEC 資訊可用硬邊界 (`acceptance_datetime`)**：
   - 在 ST-EVA 採 SEC filing 作為法定 GAAP 證據來源的前提下，`acceptance_datetime` 是該 filing 被 EDGAR 接受的可追溯時間邊界，ST-EVA 以此作為資訊可用性的保守硬邊界；它不代表市場首次知悉、首次取得或首次定價的實際時間。
   - **禁止**將 `acceptance_datetime` 表述或解釋為「市場實際首次獲知資訊的時間」（例如忽略盤中新聞稿、提前洩漏或分析師電話會議）。它僅代表資訊在官方申報體系中的可用性下界（Not knowable from SEC filing before this timestamp）。
   - **Amendment 1 延伸**：本決策同樣適用於 `SEC furnished` 之來源（見 §2.1 Decision 10、12）。時間戳為**可得性**事實，**不得**用以推論 `filed` 狀態或 Section 18 法律效力。
3. **收盤截止常規 (`16:00 ET Cutoff Convention`)**：
   - 若申報的 `acceptance_datetime` 落在美東時間 `16:00 ET` 之前，該申報事實於**當日（T）**交易收盤後可用；若落在 `16:00 ET` 或之後（盤後），則該申報事實於**次一交易日（T+1）**收盤後始可與市場價格配對。
   - **聲明**：此規則為 ST-EVA 內部自訂之方法論常規（Methodology Convention），**不是** SEC 法規。
4. **禁止算術相減反推 Q4 Diluted EPS**：
   - **嚴禁**使用 `FY Diluted EPS − (Q1 + Q2 + Q3 Diluted EPS)` 或 `FY Diluted EPS − YTD Q3 Diluted EPS` 反推第四季度（Q4）稀釋每股盈餘。
   - **正確理由（證據資格，非算術）**：FY 與 YTD Diluted EPS 本身是各該期間**已申報**的數字，其分母為各該期間自己的加權平均稀釋股數（Weighted-Average Diluted Shares），並各自套用庫藏股法之反稀釋處理與呈報小數位取整。因此兩者之代數差值**不是發行人申報過的 Q4 稀釋每股盈餘**，而是一個由 ST-EVA 就地製造、發行人從未申報之推導量。它與申報值的差異並非穩定偏移，故不可預期、不可校正、不可回溯。
   - **不得以實測差異幅度作為放寬理由**：即使在特定發行人、特定期間，代數差值恰好等於申報值、或僅差 0.01，禁令**仍然有效**。差異幅度無論大小，都不改變「推導量不等於申報事實」這一點。接受度不得由觀察誤差決定。
   - **唯一合法替代**：Q4 Diluted EPS 必須來自一級來源**直接陳述**該季度之稀釋每股盈餘（見 §2.1 Decision 10 之 Evidence Class 定義）。
5. **Q4 數據缺失時 TTM P/E 之硬性退化**：
   - 若發行人未在**任何合資格之一級來源**（filed 或 furnished，見 §2.1 Decision 10）中直接陳述可追溯之 Q4 稀釋每股盈餘，則該時點之 TTM Diluted EPS **不得合成**，相應之 `TTM_GAAP_DILUTED_PE` 必須標記為 `UNAVAILABLE`。
   - **本決策之對稱要求**：一旦某合資格來源**確實直接陳述**了該 Q4 稀釋每股盈餘，即**不得**僅因該數字未以 XBRL fact 形式存在而仍拒絕它（見 §2.1 Decision 13）。`UNAVAILABLE` 是對**證據資格**的判斷，不是對**機器可讀性**的判斷。
6. **非正每股盈餘之排除**：
   - 凡當期稀釋每股盈餘 $\le 0$（虧損或零盈餘），相應之 P/E 計算結果**嚴禁進入正向 P/E 參考分佈（Reference Distribution）**，避免扭曲中位數與百分位數帶。
7. **嚴格禁止 Lookahead Bias（未來資料污染）**：
   - 任何歷史時點 $t$ 的觀察值建立，僅能且必須使用在該時點 $t$ 之前已接納之申報事實與已發生之市場價格。
   - 嚴禁使用後續發布之重編（Restatement）資料追溯覆蓋當時已知數據。
8. **股票分割（Stock Split）之點時因果調整**：
   - 價格序列與每股盈餘在配對時，必須依據除權息日（Ex-Date）與可追溯的 Corporate Action 證據保持計量口徑一致。在歷史時點 $t$ 評估時，未發生的未來分割不得提前反映於歷史價格或 EPS。
9. **確定性與完全可重演性（Replayability）**：
   - 所有生成的估值觀察值必須具備確定的雜湊值（Content Hash）、完整的資料血統（Lineage）與來源引用（Refs），保證 Replay 重建完全重現。

---

## 2.1 Amendment 1: 一級證據類別分離 (Primary Evidence Class Separation)

新增於 2026-10-07，源自 `experiments/aapl-historical-pe-poc/q4_study/` 對 AAPL
FY2021–FY2025 各 Q4 之一級來源抽查。該研究證實：AAPL 自 FY2021 之 10-K 起不再
標記 quarter-length `EarningsPerShareDiluted` XBRL fact，但**同一季之稀釋每股盈餘
仍以直接陳述形式存在於 Form 8-K Item 2.02 之 EX-99.1 earnings release exhibit**
（period end 欄位明確標為 `Three Months Ended <該季期末>`，且文件內敘述句獨立
佐證同一數值）。五個季度全數取得，acceptance time 皆為 16:30 ET，故 PIT usable
date 皆為次一交易日。

原 Decision 2 之 `acceptance_datetime` 語意在此明確延伸至 furnished 來源；
Decision 5 之「官方申報文件」範圍亦據此擴張。兩者均為**擴張**，非替換。

10. **`SEC filed` 與 `SEC furnished` 語意分離**：
    - **`SEC filed`（既有語意，不變）**：10-K、10-Q、10-K/A 等依《1934 年證券交易法》
      §13(a) 提出之定期報告。其財務報表為 filed statement。
    - **`SEC furnished`（新增之一級證據類別）**：Form 8-K **Item 2.02**
      (`Results of Operations and Financial Condition`) 隨附之 EX-99.1 earnings
      release exhibit。該等 exhibit 明載其資訊「shall not be deemed "filed" for
      purposes of Section 18」。
    - **合資格條件（全部須成立）**：
      1. **issuer-primary**：由發行人本身編製並提交，非第三方彙整或轉載。
      2. **quarter-specific**：文件中存在明確標示為該季度之期間欄位（例
         `Three Months Ended <季末日>`），且該欄位日期與目標季度期末日**逐字相符**。
      3. **直接陳述**：該欄位直接列出 `diluted` 每股盈餘數值，**不得**由任何
         欄位相減、差分或推導得出。
      4. **可確認之公開時間**：存在可追溯之 SEC acceptance / public availability
         timestamp，且據以建立 PIT usable date（Decision 2、3）。
      5. **可回溯與可驗證**：可回指原始文件（accession + form + exhibit
         identifier）並可重新取得、驗證內容雜湊。
    - **強制語意限制**：
      - **嚴禁**將 furnished exhibit 稱為、表述為或等同於 `filed statement`、
        `audited statement`，或暗示其具備 Section 18 效力。
      - **嚴禁**將 furnished exhibit 之數字回填為任何 10-K/10-Q 申報事實。
      - 文件中若同時載有 non-GAAP / adjusted 每股盈餘，**僅** GAAP 欄位可作為
        證據；adjusted 數值必須被解析、記錄，並**明確排除**於計算之外。
11. **Unaudited 本身不構成拒絕理由**：
    - earnings release 之 condensed statements 標示 `(Unaudited)` 屬**常態**，
      **不得**單憑 `unaudited` 即拒絕該來源。
    - 若 Decision 10 之五項合資格條件全部成立，且 quarter period、`diluted` EPS
      row、期間欄位日期三者均可確認，則**須**接納為 Q4 evidence candidate。
    - **Provenance 強制區分**：`audited` 與 `unaudited` 必須作為**不同屬性欄位**
      存在於 lineage 中，不得互相隱含、不得省略。
    - **不得冒充**：`ANNUAL_GAAP_DILUTED_PE` 所需之年度稀釋每股盈餘，其一級證據
      仍為 10-K 之 audited statement。Q4 earnings-release 證據**僅**滿足 TTM 中
      該一個季度之分量需求，**嚴禁**用以支撐、替代或近似任何 audited 年度數字。
12. **`acceptance_datetime` 對 furnished 來源之適用與其界線**：
    - furnished exhibit 之 `acceptance_datetime` 與 filed filing 受**完全相同**之
      PIT 規則約束：作為**保守之資訊可用性下界**（Decision 2），並適用
      `16:00 ET` usable-date convention（Decision 3）。
    - **禁止**將該 timestamp 解釋為或暗示：`filed` 狀態、Section 18 法律效力、
      市場首次獲知時間，或「因未申報故不受問責」之推論。時間戳是**可得性**事實，
      不是**法律地位**事實。
    - **實作教訓（非 SEC 法規）**：EDGAR submissions API 之 `acceptanceDateTime`
      帶 `Z` 後綴但**不等於 UTC**；實測 43 份 filing，其值恆等於 EDGAR SGML header
      `ACCEPTANCE-DATETIME`（**真實 Eastern Time**，無時區標記）加 ET offset
      （EDT +4h / EST +5h）。若誤當 UTC 讀取，16:31 ET 之申報將被讀成 21:31 ET
      而多推遲一個交易日。
      - 判定基準為 **SGML header 值**，並以 EDGAR 自身「17:30 ET 後申報之 filing
        date 為次一營業日」規則獨立交叉驗證。
      - 本條為 ST-EVA **實作層教訓**，屬供應端資料異常之處理紀錄，**不是** SEC
        法規、不是 SEC 對 API 之承諾，亦不得被引用為法規依據。
13. **`XBRL fact unavailable` 與 `primary evidence unavailable` 之強制區分**：
    - 此二狀態**語意完全不同**，在任何 observation、拒絕原因或報告中**必須分開表述**：
      | 狀態 | 意義 |
      | :--- | :--- |
      | `XBRL fact unavailable` | 該季度無對應之 machine-readable XBRL fact。 |
      | `primary evidence unavailable` | 依 Decision 10，**無任何**合資格一級來源直接陳述該季稀釋每股盈餘。 |
    - **禁止**將 `XBRL fact unavailable` 表述為 `primary evidence unavailable`，
      或以此作為 `REASON_MISSING_Q4_EPS` 之唯一依據。
    - 引擎**必須**在使用 `REASON_MISSING_Q4_EPS` 前，窮盡所有合資格之一級來源類別
      （含 furnished），而非僅查詢 XBRL fact API。
    - 對 AAPL FY2021 之後各季：`XBRL fact unavailable` **成立**，
      `primary evidence unavailable` **不成立**（見 §6.1）。
14. **TTM 分量來源混用之允許（Source Mixing）**：
    - 同一 `TTM_GAAP_DILUTED_PE` 之四個 fiscal quarter **得使用不同之一級證據
      來源**。典型且已驗證之組合為：Q1–Q3 取自 10-Q（filed），Q4 取自 Form 8-K
      Item 2.02 EX-99.1（furnished）。
    - **全部須成立**：
      1. 每個分量均為 **GAAP diluted EPS**（非 basic、非 adjusted）。
      2. 每個分量均為 **quarter-specific**，且其 fiscal period 可與目標季度
         **精確對齊**（期間結束日逐字相符）。
      3. 每個分量均具備完整 **PIT provenance**（accession / form 或 exhibit
         identifier / acceptance_datetime / usable_date / content hash）。
      4. 四個分量構成**連續四個 fiscal quarter**，以 fiscal position 錨定，
         不得以「手上恰好有的四個期間」代替。
      5. 無 **lookahead**：每個分量之 usable date ≤ 評估日 $t$。
      6. **無任何** synthetic / derived FY − YTD Q4 分量（Decision 4）。
    - **強制揭露**：observation 之 provenance **必須**記錄四個分量各自的
      evidence class（`filed` / `furnished`）與 `audited` / `unaudited` 屬性，
      不得將混合來源表述為同質來源。
    - **不得**由此推出「furnished 與 filed 等價」之一般命題。本決策僅允許
      furnished 作為 **TTM 單一分量**之一級證據，**不**授權其用於
      `ANNUAL_GAAP_DILUTED_PE` 之建構。

---

## 3. Formal Definitions (正式術語與口徑定義)

### A. `TTM_GAAP_DILUTED_PE`
* **定義**：在評估日 $t$ 的滾動 12 個月 GAAP 稀釋本益比。
* **計算公式**：
  $$\text{TTM\_GAAP\_DILUTED\_PE}_t = \frac{P_t}{\sum_{i=1}^{4} \text{GAAP\_Diluted\_EPS}_{Q_i}}$$
* **先決條件**：
  1. $P_t$ 為評估日 $t$ 之收盤價（或最後有效市場交易價）。
  2. 涵蓋過去連續 4 個會計季度之 GAAP 稀釋每股盈餘，各季度均具備**合資格之一級來源之直接證據**（filed 或 furnished，見 §2.1 Decision 10）。
  3. 四個季度 EPS 總和 $> 0$。
* **約束**：不得以 Annual EPS 代替；不得以算術差額填補 Q4。
* **來源混用（Amendment 1）**：四個季度**得**分屬不同 evidence class（Decision 14）。「直接證據」一詞**不**要求四者同質，亦**不**要求四者皆為 XBRL fact。

### B. `ANNUAL_GAAP_DILUTED_PE`
* **定義**：在評估日 $t$ 所知最新會計年度（Fiscal Year）10-K 申報之 GAAP 稀釋本益比。
* **計算公式**：
  $$\text{ANNUAL\_GAAP\_DILUTED\_PE}_t = \frac{P_t}{\text{GAAP\_Diluted\_EPS}_{FY}}$$
* **證據類別限制（Amendment 1）**：年度稀釋每股盈餘之一級證據**僅限** 10-K 之
  **audited** statement。**嚴禁**以 furnished earnings-release 之季別或年度別
  數字建構本指標（Decision 11）。
* **角色定位**：
  - **合法的描述性替代指標（Descriptive Fallback）**。
  - **嚴禁冒充**：當 TTM 無法建立時，**嚴禁**將 Annual P/E 標記或包裝為 `TTM_GAAP_DILUTED_PE`。
  - **不得作為預設 TTM Reference**：除非使用者顯式聲明以 Annual P/E 為基準，否則不可自動替代 TTM 驅動 Reverse Valuation。

### C. `CURRENT_PE`
* **定義**：在最新分析時點（Run Instant）觀察到的即時或最新有效本益比。
* **屬性**：單一時點的現狀快照（Current Snapshot Observation），**嚴禁**將 `CURRENT_PE` 單一數值直接作為歷史分佈帶（Historical Band）或統計參考值。

### D. `UNAVAILABLE` 核心原因碼體系
當估值指標無法產出時，必須明確標記下列封閉枚舉原因碼：

| 原因碼 | 適用情境 |
| :--- | :--- |
| `REASON_MISSING_PRICE` | 評估日無可驗證之市場收盤價格。 |
| `REASON_MISSING_Q4_EPS` | 依 Decision 13 窮盡**所有**合資格一級來源類別（含 furnished）後，仍無任何來源直接陳述該季 Q4 Diluted EPS。拒絕差額推算。**不得**僅因 XBRL fact 不存在即使用本碼。 |
| `REASON_INSUFFICIENT_QUARTERS` | 申報歷史未達連續 4 季（如新上市或資料斷裂）。 |
| `REASON_NON_POSITIVE_EPS` | TTM 或當期 EPS $\le 0$，無法計算正向本益比。 |
| `REASON_INSUFFICIENT_OBSERVATIONS` | 歷史有效樣本數未達門檻。 |
| `REASON_INSUFFICIENT_TIME_SPAN` | 樣本所跨時間跨度或會計季度覆蓋率未達充足性標準。 |
| `REASON_CORPORATE_ACTION_UNRESOLVED` | 存在無法確切對齊除權基準之分割或重大資本變動。 |

* **原因碼體系之封閉性（Amendment 1）**：本枚舉**維持封閉**，Amendment 1 未新增
  任何原因碼。`XBRL fact unavailable` **不是**原因碼，不得以之作為
  `REASON_MISSING_Q4_EPS` 之正當理由（Decision 13）。若未來確需將
  「XBRL fact 缺失但一級證據存在」暴露為可觀察狀態，須另行決策其歸屬
  （observation 屬性或新原因碼），**目前維持 OPEN**。

---

## 4. Open Questions (尚未定案、保持開放議題)

下列項目目前**尚未完成充分研究，嚴禁提前硬編碼實作**，明確標記為 OPEN：

1. **歷史觀察值充足性標準之多維定義（Reference Sufficiency）**：
   - 現有規則僅要求 `count >= 20`。
   - **OPEN**：Reference sufficiency 不只看 observation count，未來是否應強制加入「時間跨度（Time Span，如至少 3 年或 5 年）」以及「會計季度覆蓋率（Fiscal-Quarter Coverage，如至少涵蓋 12 個季度）」？因門檻數值尚未經充分實證研究，**暫不預設任何新數值 threshold**，保持 OPEN。
2. **Corporate Action Evidence Schema 規格**：
   - 股票分割歷史的來源（SEC 申報 vs 交易所官方公告 vs 價格源調整因子）、除權日（Ex-Date）之時間戳精度與存儲結構尚未真正定義完整，**標記為 OPEN，嚴禁假裝已完成**。
3. **歷史重算之抽樣頻率（Sampling Frequency）**：
   - 歷史估值帶應該按「每日收盤（Daily）」、「每週收盤（Weekly）」、「每月（Monthly）」還是「申報發布事件日（Event-Driven / Filing Date）」進行計算？其對百分位數統計穩定性之影響尚未評估，保持 OPEN。
4. **Annual P/E 的次級降級使用規則（Fallback Policy）**：
   - 若發行人為外國私人發行人（Foreign Private Issuer, FPI / 20-F），僅有半年度或年度報告時，系統是否允許正式宣告降級為 Annual P/E 驅動估值？其交互語意仍待討論。

---

## 5. Out of Scope (本次決策排除範圍)

下列事項明確排除在本次決策與下一階段實作之外：
1. **非 GAAP / 調整後（Adjusted / Non-GAAP）EPS 之歷史倍數計算**。
2. **同行業對標（Peer Comparison）或產業中位數混入**。
3. **利用大語言模型（LLM）推測、估計或填補未披露數據**。
4. **跨貨幣折算（Currency Conversion）之動態估值**。
5. **在缺少審計證據下對複雜資本變動進行推測性復原**。
6. **（Amendment 1）Historical P/E Engine 之實作與 parser 實作**：本 ADR 僅
   凍結方法論口徑。Furnished 來源之擷取、欄位歸屬判定與 evidence class 標記
   之 parser 實作**不在**本 ADR 範圍，亦**不得**由本 ADR 之存在被推定為已完成。
7. **（Amendment 1）Corporate Action schema、Reference Sufficiency threshold、
   Sampling Frequency、20 / 24 observation requirement**：本 Amendment 未觸及，
   維持原狀。

---

## 6. POC 准入就緒評估 (AAPL POC Readiness)

> **本節部分敘述已被 Amendment 1 修正。** 下方標示 ⚠️ 者為原敘述，已被
> `experiments/aapl-historical-pe-poc/q4_study/` 之實證推翻或需澄清；
> 修正後之陳述見 §6.1。標示者保留原文以保留決策軌跡，不得再作為實作依據。

### AAPL 申報事實特徵與邊界約束：
- **Q1–Q3 數據**：AAPL Q1–Q3 可以從相應 10-Q 申報中直接取得官方季度 Diluted EPS。（不變）
- ⚠️ **Q4 數據缺失現實**（原敘述）：2021 年後常態性 AAPL 10-K 不再提供 Q4 Diluted EPS 的季度表。
  - **修正**：此敘述就 **10-K** 而言**成立**，但其**推論範圍過窄**。缺的是 10-K
    內的季度表與 XBRL fact，**非** Q4 一級證據本身。詳見 §6.1。
- ⚠️ **不得假設 Q4 直接可得**（原敘述）：AAPL Historical P/E POC 不得假設 Q4 Diluted EPS 可以直接從 10-K 取得。
  - **修正**：就 **10-K** 而言**仍然成立且必須維持**。但「不可由 10-K 取得」
    **不得**被擴張解讀為「無合資格一級證據」。8-K Item 2.02 EX-99.1 為
    合資格來源（Decision 10）。
- **不得冒充 TTM**：在此期間可以產生 `ANNUAL_GAAP_DILUTED_PE`，但**不得把 Annual P/E 冒充 TTM P/E**。（不變）
- **硬性標記 UNAVAILABLE**：若依 Decision 13 窮盡所有合資格來源後仍無直接陳述之
  Q4 Diluted EPS，必須標記為 `UNAVAILABLE`（`REASON_MISSING_Q4_EPS`）。（不變，
  但觸發條件已由「10-K 無季度表」擴張為「所有一級來源皆無」）

### AAPL POC 現在真正可以開始研究的部分：
1. **Q1–Q3 10-Q 點時申報檢索與時間戳對齊**：驗證 AAPL 各季度 10-Q 之 `acceptance_datetime` 與 `16:00 ET` 收盤對齊邏輯。（已完成）
2. **缺少 Q4 Diluted EPS 期間的狀態機轉換與原因碼標記**：驗證在缺乏合法 Q4 時，系統能確定性觸發 `UNAVAILABLE`，並同時輸出合法的 `ANNUAL_GAAP_DILUTED_PE` 作為 descriptive fallback。（狀態機本身成立；但對 AAPL FY2021+ 之觸發前提已被 §6.1 修正）
3. **歷史價格序列與點時已存在申報之比率計算管線**：在除權已對齊的歷史時點上，驗證無 lookahead 的點時比率合成。（已完成）
4. **（Amendment 1 新增）Furnished 來源之 point-in-time 納入**：驗證 Item 2.02 EX-99.1 之 `acceptance_datetime`、16:00 ET 對齊、evidence class 標記與 TTM 分量混用之 provenance 完整性。

### 仍然不能實作的部分：
1. **嚴禁以 `FY − YTD` 代數相減反推 Q4 Diluted EPS**（Frozen 禁止，理由已於 Decision 4 更正）。
2. **嚴禁將 Annual P/E 自動墊入作為 TTM Reference Multiple**（Frozen 禁止）。
3. **嚴禁將 furnished exhibit 表述為 `filed statement` 或 `audited statement`**（Amendment 1 Decision 10）。
4. **嚴禁以 furnished 季度數字建構 `ANNUAL_GAAP_DILUTED_PE`**（Amendment 1 Decision 11）。
5. **尚未定義完整 Schema 之 Corporate Action 自動調整模組**（Open 待定）。
6. **修改 Core 20 筆門檻或改寫現有 Core Valuation 介面**（Out of Scope）。

---

## 6.1 Amendment 1 實證基礎 (Q4 Evidence Source Study Findings)

來源：`experiments/aapl-historical-pe-poc/q4_study/`（AAPL FY2021–FY2025 各 Q4
之一級來源抽查）。該研究為 POC 級研究輸出，未修改任何 ST-EVA 組件。

### 來源類別實測結果：

| 來源類別 | 優先序 | 產出 Q4 Diluted EPS |
| :--- | :--- | :--- |
| 10-K 本文（filed, audited） | 1 | 0/5 |
| Form 8-K Item 2.02 EX-99.1（furnished, unaudited） | 2 | **5/5** |
| Apple Investor Relations | 3 | 0/5（無 per-quarter publication timestamp） |
| SEC XBRL companyconcept fact | 4 | 0/5 |

### 已驗證取得之 Q4 Diluted EPS：

| Fiscal Q4 | 期間結束 | Q4 Diluted EPS | Accession (8-K) | Acceptance (ET) | PIT usable date |
| :--- | :--- | :--- | :--- | :--- | :--- |
| FY2021 | 2021-09-25 | 1.24 | 0000320193-21-000104 | 2021-10-28 16:30:23 | 2021-10-29 |
| FY2022 | 2022-09-24 | 1.29 | 0000320193-22-000107 | 2022-10-27 16:30:22 | 2022-10-28 |
| FY2023 | 2023-09-30 | 1.46 | 0000320193-23-000104 | 2023-11-02 16:30:32 | 2023-11-03 |
| FY2024 | 2024-09-28 | 0.97 | 0000320193-24-000120 | 2024-10-31 16:30:25 | 2024-11-01 |
| FY2025 | 2025-09-27 | 1.85 | 0000320193-25-000077 | 2025-10-30 16:30:35 | 2025-10-31 |

五季之 acceptance time 均為 16:30 ET（晚於 16:00 ET cutoff），故 usable date 均為
次一交易日；Decision 3 之 cutoff convention 於此為**實際生效**，非僅宣告。

### 對 §6 原敘述之效力判定：

- 對 AAPL FY2021–FY2025 各 Q4：`XBRL fact unavailable` **成立**；
  `primary evidence unavailable` **不成立**。
- 因此**不得**對該期間輸出 `REASON_MISSING_Q4_EPS`。
- 先前 POC 因僅消費 XBRL facts 而得出之 `REASON_MISSING_Q4_EPS`，其成因為
  **證據擷取路徑不完備（ingestion path gap）**，**不是** data availability
  boundary，**不是** implementation failure。

### 尚未決定之事項（Amendment 1 明確不決定）：

1. `XBRL fact unavailable` 之機器可觀察歸屬（observation 屬性 vs 新原因碼）——
   維持 **OPEN**，原因碼枚舉維持封閉。
2. Furnished 證據於 reverse valuation reference 計算中之權重與
   `ANNUAL_GAAP_DILUTED_PE` 之互動語意 —— **OPEN**。
3. 每股盈餘呈報貨幣非 USD 時，furnished 來源之單位處理 —— **OPEN**。
4. Reference Sufficiency、Sampling Frequency、Corporate Action schema、FPI
   fallback policy —— 全部**維持 OPEN**，本 Amendment 未觸及。
5. 20 / 24 observation requirement —— **未修改**。
