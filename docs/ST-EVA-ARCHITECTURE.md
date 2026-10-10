# ST-EVA Architecture & Implementation Reference

> **歷史資料／非現行指令。** 本文件只記錄撰寫時的設計、狀態、計畫或決策，不具有授權、禁止、限制或要求未來工作的效力。文中任何「binding」「frozen」「approved」「not authorized」「must」等措辭均為歷史內容，不得凌駕使用者目前的要求。當前狀態以現行程式碼、測試及實際 Git 狀態為準。
>
> **HISTORICAL ARCHIVE — NOT CURRENT INSTRUCTIONS.** This document records prior design, status, plans, or decisions. It does not grant, deny, restrict, or require work. Any “binding,” “frozen,” “approved,” “not authorized,” or “must” wording below is historical and does not override the user's current request. Determine current state from current source code, tests, and Git state.

**Repository:** `sbvcid/st-eva`  
**Historical status:** Architecture and implementation notes recorded at the time; not a current instruction source or authority.  
**Role:** Help maintainers and agents understand the current implementation and why particular safeguards exist. The project owner may revise a prior design or change direction. When this record conflicts with the owner's current instruction, explain the impact and update the relevant record rather than treating old wording as immutable.  
**Intended Audience:** Maintainers and coding agents working on production code, schemas, data and tests.

---

## Historical contributor notes (retired)

The original version of this document asked modifying agents to read relevant sections before changing code and treated some boundaries as fixed. Those statements record the workflow proposed at the time; they are not current instructions, permissions, or restrictions. The technical sections below preserve earlier reasoning and may be outdated or superseded. For current work, follow the user's current request and verify actual behavior against current source code, tests, and repository state.

---

# A. ST-EVA 是什麼 (What ST-EVA Is)

### 1. 精確定義 (Precise Definition)
**ST-EVA 是一套面向金融研究與 LLM 消費者的證據資料及市場隱含假設紀錄系統。**  
它保存可追查的市場與財務觀測、來源及驗證結果，對明確指定的估值條件執行確定性反向計算，並將資料、公式、條件與指定時點的快照交給外部 LLM 或研究者分析。ST-EVA 本身不預測公司的合理價值，也不把條件式反推結果宣稱為市場唯一且可直接觀測的預期。

### 2. 反向估值（Reverse Valuation）的真正研究對象
傳統估值常從未來基本面假設推導價值；ST-EVA 採相反方向，研究「在明確估值條件下，當前價格要求哪些財務結果」。

> **「目前價格在什麼條件下說得通？這些條件隨時間如何改變？」**

價格本身不能唯一揭示市場所有參與者真正相信的成長路徑。ST-EVA 記錄觀測到的價格、當時可得的證據，以及在各組明確參考條件下計算出的隱含數值；LLM 再利用這些材料提出並比較可能的解釋。條件式計算是可重現的研究輸入，不是對市場心理的直接觀測。

### 3. Price → Assumptions 的基本思路
在給定價格 $P_0$ 與明確指定的參考倍數 $M$（例如本益比 P/E、市銷率 P/S、市現率 P/FCF、企業價值倍數 EV/EBITDA）下：
1. **隱含未來獲利 (Implied Forward Metric):**
   $$\text{Implied Forward EPS} = \frac{P_0}{M_{\text{selected\_PE}}}$$
   $$\text{Implied Revenue} = \frac{\text{Market Cap}}{M_{\text{selected\_PS}}}$$
2. **所需複合年增長率 (Required EPS CAGR):**  
   若當前每股盈餘 $\text{Current EPS}$ 可取得且大於零，在預測跨度 $T$ 年下：
   $$\text{Required EPS CAGR} = \left(\frac{\text{Implied Forward EPS}}{\text{Current EPS}}\right)^{\frac{1}{T}} - 1$$
3. **共識差距 (Consensus Gap):**  
   若市場分析師共識每股盈餘 $\text{Consensus Forward EPS}$ 可取得：
   $$\text{EPS Gap vs Consensus} = \frac{\text{Implied Forward EPS}}{\text{Consensus Forward EPS}} - 1$$

「隱含」一詞永遠是**條件式（Conditional）**的：價格本身無法唯一鎖定單一未來成長路徑，它必須依賴明確宣告的參考倍數（例如歷史中位數或使用者給定倍數）。

### 4. Deterministic / Auditable / Replayable 的絕對意義
* **Deterministic（確定性）：** 估值核心計算為純 Python 算術（`st_eva_runner.py`）。不引入隨機模擬、不使用蒙地卡羅黑箱、不依賴任何外部非確定性模型。相同的輸入必然產出逐字節相同的結果。
* **Auditable（可審計性）：** 輸出的每一個數字都擁有完整血統（Provenance）。每個推導數值必須指明它依賴哪些 `Observation ID`，使用哪種 `Operation`，並能從留存的原始觀測完全重新計算。
* **Replayable（可回溯性）：** 系統具備嚴格的時空回溯能力。在時間點 $T$，系統只能使用在時間點 $T$ 或之前「市場已公開且可獲知」的數據重算當時的決策與輸出，杜絕任何未來資訊偏差（Lookahead Bias）。

### 5. 為什麼 ST-EVA 刻意不是 Forecasting / DCF / Rating / Buy-Sell System
ST-EVA 明確拒絕成為下列系統：
1. **不是 Forecasting System（不預測）：** 不發布分析師預測、不預估 EPS、不設定股價目標（Target Price）。
2. **不是 DCF（現金流折現）：** 不預測未來數十年的自由現金流，不隨意給定加權平均資金成本（WACC）或永續成長率。DCF 容易因為微小的貼現率假設變動產生巨大的估值幻覺；ST-EVA 僅反解市場現狀。
3. **不是 Rating / Buy-Sell System（不做買賣評級）：** 不輸出 Bull/Base/Bear 劇本機率、不產出 Buy/Hold/Sell 建議。
4. **堅持零合成財務資料（Zero Synthetic Financial Data）：** 若底層財務數據（如 EPS 或營收）缺失，系統嚴格標記為 `UNAVAILABLE` 或拒絕計算，**絕不**使用同業平均、平滑曲線、黑箱插值或隨意乘數來填補空白數值。
5. **LLM 是外部分析者，不是權威資料來源：** ST-EVA 的確定性核心負責產生可重現的基礎指標與明確條件下的反向計算。LLM 可以利用相同資料包自行分析、提出候選假設或進行額外計算，但必須把其假設、公式與解釋和 ST-EVA 的來源觀測及已保存計算結果分開；不能把模型推論回寫成原始事實。目前 `llm_interpreter.py` 主要建構解讀提示詞，尚未整合即時模型呼叫。

---

# B. Core Architecture

## B.0 Conceptual Execution Flow

以下描述的是**概念執行流程（Conceptual Execution Flow）**：一個事實從外部來源走到結論所必須依序經過的**語意階段**。

> [!IMPORTANT]
> 這**不是** Python import dependency diagram。
> ST-EVA 的實際 import graph **並非**嚴格 DAG，詳見 §F.2。
> 這兩件事必須分開讀：flow 決定「語意上誰消費誰的產物」，import graph 決定「模組在載入時實際依賴誰」。兩者在本專案**並不一致**。

```text
Raw Source (SEC EDGAR SGML, Yahoo Finance API, Exchange feeds)
  ↓
Ingest (sec_ingest.py, sec_provider.py, fundamental_provider.py)
  ↓
Observation (data_contract.py: Observation)
  ↓
Evidence (evidence_model.py, evidence_query.py)
  ↓
Admission (evidence_valuation_boundary.py: admit)
  ↓
Analytical Engine (st_eva_runner.py: MarketImpliedAssumptionsEngine)
  ↓
Derived / Valuation Result (MarketImpliedAssumptions, DerivedValue)
  ↓
Snapshot (SnapshotManager, context.json, SQLite context_snapshots)
  ↓
Publication / Presentation (history/, reports/, web/app.py, web/service_adapter.py)
```

## B.0.1 Archive / Replay 不是流程的下一層，而是包覆核心管線的子系統

`Archive / Replay` **不是**上面這條流程的末端步驟。它是一個跨越整條核心管線的 **persistence + verification subsystem**：

```text
        ┌───────────────────────────────────────────────┐
        │  Archive / Replay subsystem                   │
        │  (archive.py, sqlite_archive.py)              │
        │                                               │
        │   • 持久化核心管線的每一層產物                 │
        │     observation / evidence / admission /      │
        │     derived / context snapshot                │
        │   • Replay 時【重新進入】核心管線：           │
        │     1. 從 archive 取出 as_of 之前可知的觀測    │
        │     2. 重新執行 admit()（不讀 stored admission）│
        │     3. 呼叫注入的 build_document 重建估值與      │
        │        context                                 │
        │     4. 與已儲存 admissions / snapshot 逐欄比對   │
        │   • 因此它「向下」消費核心管線，也「向上」       │
        │     驅動核心管線重跑                             │
        └───────────────────────────────────────────────┘
                     ↑                    ↓
              Observation          Admission recomputation
```

**後果（維護者必須知道）：** Replay 是整個架構中少數會**反向呼叫核心邏輯**的子系統。因此：

* `archive.py` 依賴 `evidence_valuation_boundary` 是**刻意的**，不是分層洩漏。
* 把 Archive 當成「Engine 之下的一層」來理解，會導致錯誤的修改方向（例如以為可以在 archive 內改寫估值邏輯）。
* 完整說明見 §F.2 與 §I。

### 資料流層級深剖 (Layer-by-Layer Breakdown)

#### 1. Raw Source
* **代表意義：** 外部世界的原始公開事實載體（SEC SGML submissions, SEC EDGAR XBRL JSON, 8-K Exhibits, Vendor API responses）。
* **擁有資料：** 原始 HTTP 封包、未解析的 JSON/HTML/XML 字節流、文件雜湊。
* **不能擁有：** ST-EVA 內部的語意指標名稱、清洗後的數值、任何估值邏輯。
* **輸入：** 網路連線與資料提供商端點。
* **輸出：** 原始字節與 HTTP 狀態元數據。
* **可依賴它的下游：** 僅限 `Ingest` 層。
* **禁止反向污染：** 任何核心引擎、契約、註冊表不得直接發起對原始資料源的呼叫。

#### 2. Ingest
* **代表意義：** 從原始文件提取結構化宣告事實的無損轉換層。
* **擁有資料：** 解析邏輯、過濾規則（如篩選離散季度與年度）、原始 Accession 編號、申報日期與接受時間。
* **不能擁有：** 跨資料源對比評級、估值多倍數選擇、指標計算。
* **輸入：** `Raw Source`。
* **輸出：** 具備完整血統的 `Observation` 物件、寫入 `source_documents` 與 `held_filings`。
* **可依賴它的下游：** `Observation`、`Archive` 儲存程序。
* **禁止反向污染：** 嚴禁將下游引擎的「需求缺口」反向滲透進 Ingest（例如為了湊齊 TTM 營收而把累計季度強行切碎合成）。

#### 3. Observation
* **代表意義：** 一個不可變的最小事實單元（One metric, one value, one provenance record）。
* **擁有資料：** `Observation` 是 `data_contract.py:735-776` 定義的 frozen dataclass，其欄位為：
  * **身分與量值：** `observation_id`, `metric`, `value`, `unit`, `currency`, `currency_basis`
  * **期間與時點：** `period_start`, `period_end`, `as_of`, `available_at`, `available_at_basis`
  * **來源血統：** `provider`, `source_type`, `source_url`, `definition`, `methodology`
  * **抓取時間：** `retrieved_at`
  * **評價與推導輸入：** `status`, `status_reasons`, `inputs`, `observation_count`
  * **保留容器：** `basis`（結構化 basis dict）、`raw`（供應商原始 payload）
* **不屬於 `Observation` dataclass 的東西（重要）：**
  * `accession` **不是** dataclass 欄位。它必須由 `sqlite_archive.py:106-109` 的 `_accession_of()` 從 `raw["sec_fact"]["accession"]`（或 `raw["accession"]`）推導，缺失時為 `None`。
  * `concept` **不是** dataclass 欄位。它由 `sqlite_archive.py:87-103` 的 `_concept_of()` 從 `raw["sec_fact"]` 的 `taxonomy:tag` 推導，無 SEC 來源時退回 `metric`。
  * `taxonomy`, `form`, `fiscal_year`, `fiscal_period`, `statement`, `instant`, `source_fact_id`, `source_concept_ref` 是**archive 層級的 filing identity 欄位**（見 §H.2），由 `record_observation()` 在 `filing is not None` 時另外寫入，**不在** dataclass 上。注意 §H.2 的 writer boundary：此寫入只在該 `content_hash` **首次** INSERT 時發生，命中既有列時會提前 return，不 backfill。
* **不能擁有：** 決策狀態（是否被引擎採納）、跨資料源獲勝標籤、清洗覆寫後的值。
* **輸入：** `Ingest` 層所解析的單一事實。
* **輸出：** 凍結的 `Observation` 資料結構，寫入 SQLite `observations` 表（Append-only）。
* **可依賴它的下游：** `Evidence`、`EvidenceQuery`、`Admission`、`Archive`。
* **禁止反向污染：** Validation、Admission 或 Engine 嚴禁修改 Observation 的任何屬性（`dataclass(frozen=True)`）。

#### 4. Evidence
* **代表意義：** 面向查詢與分析的證據結構化套件。解釋「該指標在該時點處於何種證據狀態」。
* **擁有資料：** 關聯的 Observation 參考、證據狀態（`SOURCE_REPORTED`, `NOT_APPLICABLE`, `NO_OBSERVATIONS`, `UNAVAILABLE`, `CONFLICTING`, `STALE`）、原因代碼（`REASON_CODES`）、資料歧義分類（`AMBIGUITY_*`）。
* **不能擁有：** 引擎的採納裁定（Admission）、數值的覆寫。
* **輸入：** 儲存的 `Observation`、註冊表語意定義、驗證記錄。
* **輸出：** 唯讀的 `Evidence` 套件與 `EvidenceState`。
* **可依賴它的下游：** `Admission`、`EvidenceQuery`、`InvestmentContext`、LLM 解讀器。
* **禁止反向污染：** 不得將 Evidence 的分類元數據（如 `evidence_class`）倒灌合併為 Observation 的固有身分。

#### 5. Admission
* **代表意義：** 估值邊界裁決（Valuation Boundary Decision）。在給定的資產、時點與政策下，判定「某個證據是否被允許進入估值引擎計算」。
* **擁有資料：** `admissions` 表（`0019_admissions.sql:49-99`）欄位：裁決身分 `(asset_id, decided_at, metric)`、`admitted` (布林)、`contract_id`、`source_fact_id`、`registry_state_identity`、`resolver_policy_identity`、`price_contract_id`、`price_source_fact_id`、`identity` (UNIQUE)、`supersedes`、以及審計欄位 `refusals_json`、`considered_observations`、`superseded_accessions`、`superseded_values`、`competing_concepts`、`mapping_type`、`relation_kind`、`availability_class`。
  * **價格以身分記錄、絕不複製數值：** `price_contract_id` / `price_source_fact_id` 存在的理由是價格「決定了 rule 4」（`0019_admissions.sql:27-34`），所以「是哪一個價格參與裁決」屬於裁決的一部分；但價格的數值屬於 observation，複製過來會製造第二份可能互相矛盾的真理來源。
* **不能擁有：** 原始事實的重新定義；嚴禁直接複製儲存價格或財報數值（避免形成雙重真理來源）。
* **輸入：** Replay-eligible 的 `Observation` 集合、當前資產價格觀測、Core Registry 規則。
* **輸出：** `BoundaryResult`、`ValuationInputs` 欄位注入、寫入 `admissions` 表。
* **可依賴它的下游：** `Engine`（僅接收通過 Admission 的數值）、`Replay`（用於對比決策一致性）。
* **禁止反向污染：** 嚴禁將 Admission 結果寫回 Observation 作為「Role」欄位；嚴禁在 Replay 時把已儲存的 Admission 當成輸入。

##### 5.1 Admission V1 Scope：目前只有 `revenue`（**必讀**）

> [!WARNING]
> **`admissions` 表的 schema 能力（可以記錄任何 metric 的裁決）與目前 admission evaluator 的實際 scope 是兩件事。**
> 不要因為 migration 支援泛用 admission，就假設所有 valuation inputs 都已經有完整的 admission boundary。

**目前 V1 crossing scope 只有一個 metric：**

```python
V1_CROSSING_METRICS: Tuple[str, ...] = (METRIC_REVENUE,)
# evidence_valuation_boundary.py:103
```

`admit()`（`evidence_valuation_boundary.py:1185-1256`）實際產生的行為：

1. 價格（price）通過 `_require_price` 後**直接穿透**（"valuation-side"），不經過 metric admission。
2. 對 `metrics` 中的每個 metric（V1 即 `revenue`）執行 `_admit_one`，即 Rule 1–10。
3. `ValuationInputs` **只會**被寫入三個欄位：`price`、`currency`、`current_revenue`（`evidence_valuation_boundary.py:1249-1255`）。
4. **其餘所有 `ValuationInputs` 欄位一律維持 dataclass 自己的 `UNAVAILABLE` 預設值**——不是零，也不是任何相關指標。

這個限制在程式碼裡是**顯式的一等概念**，不是意外：

* 拒絕標籤 `METRIC_NOT_IN_V1_SCOPE`（`evidence_valuation_boundary.py:124`）存在的唯一目的就是表達「這個 metric 不在目前的 V1 範圍內」。
* `REFUSAL_LABELS` 共 11 個（`evidence_valuation_boundary.py:136-148`），與 `docs/ST-EVA-DATA-ADMISSION-RECONCILIATION.md:136-147` 的 Rule 1–10 對照表一致。

**維護後果：** 若你要新增一個可進入引擎的 valuation input 指標，**必須**同時擴充 `V1_CROSSING_METRICS` 與對應的 `ValuationInputs` 寫入邏輯。只擴 schema（新增 `metric` 值、新增 `admissions` 列）不會讓指標通過 admission——它會被 `METRIC_NOT_IN_V1_SCOPE` 拒絕，而這是一筆**合法的、有完整拒絕標籤的裁決紀錄**，不是缺失。

#### 6. Engine
* **代表意義：** 純粹確定性的反向估值算術核心。
* **擁有資料：** 反向估值數學模型、隱含 EPS / CAGR / Margin / Gap 計算公式。
* **不能擁有：** 資料庫連線、HTTP 呼叫、資料提供商專屬欄位名稱、LLM Prompt。
* **輸入：** 完全與提供商無關的 `ValuationInputs`。
* **輸出：** `MarketImpliedAssumptions` 字典結構。
* **可依賴它的下游：** `Snapshot`、`Derived`、`Web`。
* **禁止反向污染：** Engine 不得反向指揮 Admission 應該放寬何種標準。

#### 7. Derived / Valuation Result
* **代表意義：** 確定性計算的產出物及其依賴關係。
* **擁有資料：** 計算數值、`depends_on`（所依賴的觀測 ID 列表）、運算名稱與版本標籤。
* **不能擁有：** 偽裝為「原始觀測事實」的身分。
* **輸入：** Engine 計算結果。
* **輸出：** `DerivedValue` 物件，寫入 `derived_values` 表。
* **可依賴它的下游：** `Snapshot`、報表格式化器、Web API。
* **禁止反向污染：** 不得反向覆寫其底層依賴的輸入事實。

#### 8. Snapshot
* **代表意義：** 某一特定運行時點的完整知識與計算結果的不可變歸檔文件。
* **擁有資料：** 完整的 JSON 文件（如 `AAPL.context.json`）、`document_hash`、執行時元數據、資產元數據。
* **不能擁有：** 對未來未發生的事實的引用。
* **輸入：** 觀測集、估值結果、證據套件。
* **輸出：** 磁碟上的 `.context.json` 與資料庫 `context_snapshots` 表。
* **可依賴它的下游：** `Replay`、歷史審計、離線研究。
* **禁止反向污染：** Snapshot 只是已發生事實的快照，嚴禁作為規範性（Normative）政策來約束引擎邏輯。

#### 9. Replay
* **代表意義：** 時空回溯與歷史一致性驗證驅動器。**它跨越整條核心管線，不是管線末端的一層**（見 §B.0.1）。
* **擁有資料：** 回溯比對邏輯、結果狀態（`MATCH`, `DIVERGED`, `NO_SNAPSHOT`, `INSUFFICIENT`）、差異比對分析（`archive.py:61-64`）。
* **不能擁有：** 第二套估值計算邏輯（必須呼叫與生產線相同的 `build_document`）。
* **輸入：** 指定的 `asset`、指定歷史時點 `as_of`、歸檔儲存庫 `ArchiveStore`、以及**由呼叫端注入的** `build_document`。
* **輸出：** `ReplayResult`。
* **反向呼叫核心管線：** Replay 會在執行中 `import evidence_valuation_boundary` 並重新執行 `admit()`（`archive.py:462`, `:471-473`）。這是刻意的設計，也是 §F.2 所述 import cycle 的 cycle-break 位置。
* **可依賴它的下游：** 測試套件、Web 審計面板、CI/CD 迴歸防護。
* **禁止反向污染：** Replay 不得在缺少歷史資料時自動捏造或填補替代價格。

#### 10. Web / PWA
* **代表意義：** 終端展示與非同步任務調度層。
* **擁有資料：** REST API 路由、PWA 靜態前端、非同步 Job 佇列狀態、國際化（i18n）字串。
* **不能擁有：** 任何獨立的財務估值邏輯、資料驗證硬編碼、底層資料庫直接操作。
* **輸入：** HTTP 請求、呼叫 `service_adapter.py`。
* **輸出：** JSON DTO 響應、靜態 HTML/JS/CSS。
* **可依賴它的下游：** 終端使用者瀏覽器。
* **禁止反向污染：** Web 層的任何 UI 需求（如想要展示一個平滑的圖表）嚴禁倒逼 Core 抹平 `UNAVAILABLE` 或放寬數據檢驗。

---

# C. Core Object Boundary

系統核心物件邊界定義嚴格規範如下，嚴禁為追求對稱而發明新物件：

| Object | Means (代表意義) | Does not mean (絕不代表) | Owner (語意權限擁有者) |
| :--- | :--- | :--- | :--- |
| **Observation** | 來自單一來源、具有明確時空血統的原始宣告事實 | 引擎的採納決策；不可變事實的覆寫；推導計算 | Data Contract (`data_contract.py`) |
| **Source Document** | 一次外部取得、位元級固定的原始文件本體（SEC SGML / XBRL JSON / vendor response） | 從中解析出的事實；跨文件的合併 | Archive (`source_documents`, `sqlite_archive.py`) |
| **Source Fact Identity** (`source_fact_id`) | **單一來源文件內某一個宣告點**的身分。7-key、**value-independent**。唯一合法對象是 DB 的 partial UNIQUE index | 觀測的身分；跨來源比較結果；任何數值 | Evidence Model (`evidence_model.py:168-201`, `0006`) |
| **Observation Content Identity** (`observation_content_hash`) | `record_observation()` 寫入前計算的 **observation content hash**，作為該 writer 路徑的 persistence dedup key。12-key、**value-dependent** | Source Fact Identity（見 §G.1，兩者是不同的機制） | Archive (`sqlite_archive.py:112-135`) |
| **Evidence** | 面向讀取的結構化證據包，完整包含事實與其時空有效性解釋 | 原始事實的替代品；決策獲勝者裁決 | Evidence Layer (`evidence_query.py`) |
| **Evidence State** | 指標當前狀態的結構化解釋（缺失原因、爭議、陳舊） | 引擎是否准入（Admission）的裁決 | Evidence Layer (`evidence_model.py`) |
| **Admission** | 引擎在特定時點、註冊表與政策下，對某事實的採納或拒絕判定 | 原始事實本身；事實的內在角色（Role） | Valuation Boundary (`evidence_valuation_boundary.py`) |
| **Interpretation** | ST-EVA 對某一既有源頭事實的後續理解/解析修正（在知識時間軸上） | 原始事實的改寫；申報時間軸（Available At）的變更 | Knowledge Layer (`archive/migrations/0017`, `knowledge_axis.py`) |
| **Derived** | 由確定性算術與明確指認的輸入觀測所計算出的純粹推導值 | 外部觀察到的事實；包含人為判斷的估計 | Valuation Engine (`st_eva_runner.py`) |
| **Snapshot** | 某一執行時點的完整知識狀態與計算結果的不可變封存文件 | 預測；未來的保證；規範性政策 | Archive Subsystem (`archive.py`, `sqlite_archive.py`) |
| **Replay** | 以今天的代碼與註冊表重新推演歷史決策，並與存檔結果比對的驗證驅動器 | 估值計算的第二套實作；stored admission 的消費途徑 | Archive Subsystem (`archive.py:392-612`) |
| **Registry** | 指標語意、來源標籤定義、映射關係與適用性的權威仲裁者 | 經驗觀測事實；資料品質打分者；衝突解決者 | Core Registry (`core_registry.py`, `registry_seed.py`) |
| **Lineage** | 同一 `(asset, metric, concept, period)` 在不同申報之間的版本串聯 | 具體數值；內容雜湊 | Archive (`observation_lineage`, `sqlite_archive.py:138-149`) |
| **Archive** | 實體儲存、版本遷移、完整性校驗與 Point-in-Time 回溯基底 | 財務評估方法論；業務決策制定者 | Persistence Layer (`sqlite_archive.py`, `archive/migrations`) |
| **Research Artifact** | 探索性研究、POC 驗證、離線比對腳本與暫存測試數據 | 規範性生產環境資料；權威觀測依據 | Research Space (`research/`, `experiments/`) |

> [!NOTE]
> **四個物件最容易被混淆，必須分清：**
> **Observation**（來源說了什麼）≠ **Evidence**（這份證據現在是什麼狀態）≠ **Admission**（引擎當時決定要不要用）≠ **Replay**（今天重跑能不能得到同一個決定）。
> 其中 **Observation** 與 **Source Fact Identity** 也是不同物件：前者是「一個可被引擎評價的觀測值」，後者是「某份文件裡的某個宣告點」。前者進了 `content_hash`，後者進了 partial UNIQUE index。

---

# D. The Most Important Invariants

以下不變量（Invariants）均提取自實際生產代碼、測試與資料庫遷移觸發器，是 ST-EVA 系統的鋼鐵法則：

### 1. Observation is append-only
* **Rule:** `observations` 資料庫表及 Python `Observation` 類別完全為 Append-only。資料庫藉由觸發器 `observations_no_update` 與 `observations_no_delete` 強制禁止 `UPDATE` 與 `DELETE`（`0001_initial.sql:127-137`）。
* **Why:** 任何已記錄的事實都是歷史的一部分。修改歷史就摧毀了可審計性與科學重現性。
* **What breaks if violated:** 回溯回放（Replay）將產生非確定性分歧；審計軌跡中斷；先前的快照驗證全面失效。

### 2. Validation never mutates an Observation
* **Rule:** 驗證程序是純函數，僅產出 `ValidationStatus` 與原因，絕不修改 `Observation` 物件上的任何數值（`data_contract.py:735-744`）。
* **Why:** 驗證是對數值的評價，不是對數值的重寫。「修復」一個錯誤值等於製造了一個誰也沒宣告過的偽造事實。
* **What breaks if violated:** 無法溯源真實申報數據，下游將誤把系統修改過的值當作來源申報值。

### 3. Restatement creates a new observation rather than rewriting history
* **Rule:** 當公司發布財報重編（Restatement）時，系統會為新的申報建立獨立的 `Observation`（不同的 Accession 與時間戳），保留舊觀測（`sec_provider.py:27-29`, `0019_admissions.sql`）。
* **Why:** 在重編公告前，市場參與者只能看見舊數字並依據舊數字定價。若覆寫舊數據，歷史回溯時將產生致命的 Lookahead Bias。
* **What breaks if violated:** 回溯過去某個交易日時，系統會使用當時根本還沒發生的重編數字，導致歷史回測完全虛假。

### 4. Evidence is not merged into Observation
* **Rule:** `Evidence` 包含的狀態分類與上下文解釋，是在讀取時動態組裝的封包（`evidence_query.py`），絕不能合併寫入 `Observation` 的物理儲存。
* **Why:** 一個事實是客觀存在的，但對它的解讀與上下文（例如它是否與另一來源衝突、是否陳舊）會隨時空與其他資料的加入而演變。
* **What breaks if violated:** 事實與解讀耦合，導致資料庫去重機制失效或解讀被凍結在錯誤的初始時點。

### 5. Admission is not stored as an Observation role
* **Rule:** 准入決策（Admission）獨立儲存於 `admissions` 表（`0019_admissions.sql`），絕不在 `Observation` 上增加 `role` 欄位。
* **Why:** 一個事實在時點 $T_1$ 可能是證據備選，在時點 $T_2$ 可能是引擎輸入。若作為屬性寫在觀測上，將導致 29 萬筆歷史資料需要重新編號，且抹殺了決策的「時點關聯性」。
  > **量測時點說明：** 「291,134 筆」是 Migration 0019 撰寫時（ST-EVA 3.32）對當時 corpus 的量測值，該 corpus 並未保留在本 repository 中（見 §H.1）。它是**設計階段的歷史量測**，不是本 repo 目前可觀察的狀態。
* **What breaks if violated:** 破壞 `observations` 表的唯一散列去重，使得同一個客觀事實因為在不同情境下被使用而出現重複插入。

### 6. Stored Admission is not Replay input
* **Rule:** Replay 執行時，嚴禁直接讀取資料庫已存的 `admissions` 表作為引擎輸入；Replay 必須重新執行准入邏輯（`archive.py:471-473`）。
* **Why:** 回溯的真諦是「重新推演」。如果直接拿已儲存的決策餵給引擎，那只是重複讀取快照，根本無法驗證「當前的代碼與註冊表是否依然能得出相同的決策」。
* **What breaks if violated:** 掩蓋了註冊表映射變更或程式碼邏輯漂移（Code Drift）對歷史決策的潛在破壞。

### 7. Replay recomputes the decision
* **Rule:** Replay 會即時調用 `admit()` 重新計算決策，並將重算出的結果與已儲存的 `admissions` 記錄進行逐欄位比對（`archive.py:507-544`）。
* **Why:** 確保從事實到決策的整條邏輯鏈條在軟體生命週期中保持完全一致。
* **What breaks if violated:** 系統失去了發現「無意間修改了歷史准入規則」的能力。

### 8. `available_at` is not `retrieved_at`
* **Rule:** `available_at` 是資料源自身宣告對外公開的時點（如 SEC 接收時間戳）；`retrieved_at` 是 ST-EVA 發起網路請求抓取該資料的時點（`data_contract.py:754-761`, `0001_initial.sql:93-99`）。
* **Why:** 抓取時間取決於爬蟲何時運行，與該事實何時為市場可知毫無關係。
* **What breaks if violated:** 將抓取時間當作公開時間會導致資料被延後認定為可用；將公開時間假定為抓取時間則會引發超前引用。

### 9. `available_at`, `knowledge_at`, `decided_at`, and `retrieved_at` are different time axes
* **Rule:** 四個時間軸嚴格分離：
  * `available_at`: 來源申報公開時間。
  * `knowledge_at`: ST-EVA 理解/解析該事實的知識時點（`0017_knowledge_state_interpretations.sql:32-36`）。
  * `decided_at`: 准入決策發生的時點（`0019_admissions.sql:53`）。
  * `retrieved_at`: 實體抓取時間。
* **Why:** 把解析修正混入 `available_at`，等於宣稱那份原始申報早在發布當天就包含了未來的解析邏輯，毀滅了 Point-in-Time 契約。
* **What breaks if violated:** 徹底摧毀時空一致性，導致歷史回放產生不可理解的邏輯混亂。

### 10. Registry semantic identity is not inferred from filenames or labels
* **Rule:** 指標語意只能透過 `metric_concept_mapping` 的明確記錄（`0007_core_registry.sql`）來解析，嚴禁從標籤文字或檔案名稱進行字串猜測。
* **Why:** 申報人經常在不改變事實本質的情況下變更 XBRL tag，或使用看似相同但定義不同的標籤。
* **What breaks if violated:** 靜默引入時間序列斷層，或把不同性質的數據（如普通股與優先股）混為一談。

### 11. Unknown / unavailable / inapplicable / refused are not interchangeable
* **Rule:** 四者語意絕對獨立：
  * `UNKNOWN`: 尚未定義或無法識別。
  * `UNAVAILABLE`: 該指標在業務上適用，且系統嘗試抓取但未能取得（`evidence_model.py:53-54`）。
  * `NOT_APPLICABLE`: 根據公司業務模型（如銀行沒有營業利益），該指標在理論上不存在（`evidence_model.py:49-50`）。
  * `REFUSED`: 資料已取得，但未通過准入規則審查（如貨幣不匹配、非離散季度）（`evidence_valuation_boundary.py:118-148`）。
* **Why:** 混淆這四者會讓使用者將「業務上合理的缺失」誤判為「系統抓取失敗」，或將「品質不合規被剔除」誤判為「資料不存在」。
* **What breaks if violated:** 覆蓋率報告（Coverage Report）與資料品質警報徹底失真。

### 12. Research artifacts do not automatically become canonical data
* **Rule:** 在 `research/` 或 `experiments/` 產生的任何數據、CSV、JSON、POC 成果，絕不自動成為生產環境資料庫的權威資料（`docs/ST-EVA-PROJECT-STRUCTURE.md:§2.10`）。
* **Why:** 研究是探索性的、包含一次性假設的；生產資料必須通過正式 Ingestion 管道與約束校驗。
* **What breaks if violated:** 未經審核的研究垃圾數據污染生產資料庫，破壞可審計性。

### 13. Derived values must remain recomputable
* **Rule:** 所有推導數值必須儲存其運算邏輯與所有輸入觀測 ID，並保證能隨時利用純 Python 重算。
  * `DerivedValue`（`data_contract.py:1256-1270`）以 `method` 命名公式、以 `inputs`（`Tuple[str, ...]`）指認被消耗的觀測、以 `deterministic` 標示是否為確定性。
  * `record_context()`（`sqlite_archive.py:1329-1352`）把 context document 的 `provenance.derivations[ref]` 寫入 `derived_values`：`operation_json`、`expression`、`value_json`、`unit`、`deterministic`，以及 `depends_on_json` ← `derivation["depends_on"]`。
* **Why:** 不依賴未經證實的儲存快照，保證推導結果的純粹可解釋性。
* **What breaks if violated:** 系統退化為無法驗證真實性的黑箱結果集合。

### 14. No unavailable input may be silently substituted
* **Rule:** 當所需輸入不可用時，輸出必須為 `UNAVAILABLE`，嚴禁使用預設值、鄰近期間數值或同業均值靜默填補（`data_contract.py:17`, `st_eva_runner.py:23`）。
* **Why:** 一個錯誤的數值與一個被拒絕的數值，差別僅在於讀者能否察覺（`evidence_valuation_boundary.py:52-53`）。
* **What breaks if violated:** 產生看似合理但實質虛假的估值結果，嚴重誤導決策。

### 15. A refusal is a meaningful result, not merely absence
* **Rule:** 准入拒絕在資料庫中必須作為一條具備完整拒絕標籤的實體記錄儲存（`admissions` 表，`admitted=0`），而不是直接省略寫入（`0019_admissions.sql:57-60`）。
* **Why:** 「因為不合規而被拒絕」與「從未考慮過」是完全不同的系統狀態。
* **What breaks if violated:** 無法審計系統為何沒有採納某一筆已存在的財報數據。

### 16. Evidence comparison does not silently select a winner
* **Rule:** 當多個來源（如 SEC 與 Yahoo）回報不同數值時，系統標記為 `CONFLICTING` 並保留全部數據，嚴禁代碼內部私自挑選獲勝者（`core_registry.py:26-28`, `evidence_query.py:16-20`）。
* **Why:** 決定信任哪個來源屬於使用者或方法論的權限，底層架構不能代替人類做出未經說明的偏好選擇。
* **What breaks if violated:** 抹殺了資料來源之間的真實分歧，掩蓋潛在的資料錯誤。

### 17. Migration is forward-only and checksum verified
* **Rule:** 所有資料庫結構變更必須以正向遷移檔案存在（`archive/migrations/00xx_*.sql`），並經過 SHA-256 Checksum 嚴格驗證，禁止任何向下還原或手動變更（`0001_initial.sql:8-13`）。
* **Why:** 保證所有部署節點與本地資料庫具備百分之百完全相同的結構保證。
* **What breaks if violated:** Schema 漂移導致不可重現的資料庫運行崩潰。

### 18. Archive replay must never silently substitute a newer price
* **Rule:** 在 Replay 過程中，若指定時點 $T$ 缺乏價格觀測，Replay 必須直接傳回 `INSUFFICIENT`，嚴禁抓取 $T$ 之後的最新價格來替代（`archive.py:446-450`）。
* **Why:** 價格是估值分母的核心基準。替換價格將徹底破壞歷史時間點的真實性。
* **What breaks if violated:** 產生歷史穿透偏差，重現出完全虛假的市場估值。

### 19. EDGAR-generated renderings are not distinguishable from filed documents with current evidence

**VERIFIED ARCHITECTURAL FINDING — current evidence boundary, not an implementation detail.**

* **Rule:** 目前歸檔的 provenance 證據，**不足以**可靠區分 EDGAR 自行產生的 rendering 與 filer 自行提交的 document。任何下游階段（3B / 3C）**嚴禁**自行發明一個 filer-authored / EDGAR-generated 分類器，也**嚴禁**僅因某文件「看起來像 EDGAR 產物」就將其排除。
* **Evidence basis（已於 SEC 實際回應驗證，非推測）:**
    * EDGAR directory manifest (`index.json`) 提供 `filename` / MIME `type` / `size` / `last-modified`。
    * Full submission SGML 提供 `<DOCUMENT>` 序列與 `<TYPE>`。
    * 在已驗證的 AAPL 樣本中，EDGAR 生成的 rendering 與 filer 相關資源**共用泛用 `<TYPE>` 值**（例如 `XML`）。`aapl-20260730_htm.xml`（filer 的 inline XBRL，3C 需要）與 `report.css`（純 EDGAR 產物）同為 `<TYPE>XML</TYPE>`，且同時出現在兩份 manifest 中。
    * 因此**檔案副檔名與 `<TYPE>` 皆不足以**構成可靠分類的證據。
* **Architectural consequence:**
    * 保留此證據邊界本身。`filing_documents` 只宣告「該 filename 是此 filing 的一份文件」；它不承載 provenance role 的判定。
    * 目前生效且唯一有實證支撐的 eligibility 規則是**雙 manifest 互證**（directory ∧ submission）。此規則確實、且僅僅排除了 EDGAR 的三個 transmission products（`-index.html`、`-index-headers.html`、`.txt`）——它們只出現在 directory manifest。
    * 未來若要取得可靠區分，**必須先取得新的、經過驗證的證據，並另做一次架構決策**；不得在本階段默默補上。
* **This finding does NOT imply** 所有此類檔案都是 substantive filing documents。它只表示：其 provenance role 目前無法可靠判定到足以支持推斷式分類的程度。與 invariant 11（unknown / unavailable / inapplicable / refused 不可互換）、invariant 14（不得靜默替代不可用輸入）同一性質。
* **Why:** 3C 若為尋找 XBRL instance 而假設「`<TYPE>XML</TYPE>` 必定是 filer-authored」，將同時造成兩種破壞——對真正的 EDGAR 產物誤判為證據，以及把一個未經驗證的假設固化成架構事實。
* **Where it is pinned:** `tests/test_sec_document_bytes.py`（14 of 17 eligible；3 個 transmission products 被排除；7 個 EDGAR-generated rendering **被納入且未經排除**）。

### 20. `observation_filing_documents` 只承載「精確來源文件斷言」一種語意

**FROZEN ARCHITECTURAL DECISION — Phase 3C-A close-out.**

* **Rule:** `observation_filing_documents`（`0020:558-568`）唯一且全部的語意是 `EXACT_SOURCE_DOCUMENT_ASSERTION`：「這個 observation 是從這一份 filing document 讀出來的，且不主張任何其他讀法」。它**不是** candidate document、**不是** supporting document、**不是** duplicate occurrence、也**不是**「含有等價事實的文件」。第二種語意必須另建 relation 並另做架構決策，嚴禁在這一張表上複用。
* **Why:** 一個 accession 底下有多份法律地位不同的文件，且 accession 本身無法解析（`0020:552-557`：某份 8-K 的 diluted-EPS 事實來自 `EX-101.INS`，其 `EX-99.1` 完全沒有 inline XBRL）。若這張表可以同時容納「斷言」與「猜測」，讀者便無從分辨哪一列是證明、哪一列是推測——而這正是 provenance 層存在的唯一理由。
* **What breaks if violated:** provenance 從「可稽核的宣告」退化成「看起來合理的推測」；invariant 19 的證據邊界會被一個無法驗證的斷言繞過。

### 21. 精確來源文件斷言要求 cardinality 恰好為 1；2 份以上即不斷言

**FROZEN ARCHITECTURAL DECISION — Phase 3C-A close-out.**

* **Rule:** 0 列 = `UNAVAILABLE` / unresolved；1 列 = 精確斷言；**2 列以上 = 不作任何斷言**。嚴禁 confidence score、嚴禁 candidate 列、嚴禁排序式 tiebreak（例如「取檔名較小者」「取 manifest ordinal 較小者」「優先 primary document」）。此 cardinality 檢查是**生產端前置條件**，資料庫看不到候選集合，因此無法由 schema 保證，必須同時由 producer 執行**並由測試釘住**。
* **Verified case:** AAPL 8-K `0000320193-26-000018` 同一個 inline XBRL 事實同時出現在 filed primary document `aapl-20260730.htm`（SGML ordinal 1）與 EDGAR 產生的 `aapl-20260730_htm.xml`（SGML ordinal 7）。**兩者皆不得被斷言為精確來源。** Option 2（primary document by virtue of being primary）被否決：它在**形式上**用的是 declared role 而非檔名啟發式，但在**實質上**執行的正是「這個是 filed 的、那個是 EDGAR 產的」這個 invariant 19 記載為不可判定的區分。Option 3（兩者皆為 occurrence）需要 per-occurrence role，同樣依賴那個被禁止的 classifier。
* **讀端要求:** 「0 列」必須讀作「精確來源文件未解」，且必須與「從未嘗試過文件層讀取」可區分——否則計數器會把兩件相反的事讀成同一句話（這正是 2.7 產生 `NO_OBSERVATIONS` 的那個缺陷）。此區分**不得**靠在本關係表上加一列來實作。
* **What breaks if violated:** 一個無法證明的單一文件會被寫成血統，之後每一個引用它的推導都會繼承這個偽造。

### 22. 目前生產路徑未讀取任何 filing document，因此該關係對既有 observation 必須維持空

**VERIFIED ARCHITECTURAL FINDING — 由程式碼路徑與 writer call site 證實。**

* **Rule:** SEC observation 由 `companyconcept` 聚合端點寫入（`sec_ingest.py:985-1005`），`record_observation` 連結的是那份 concept document（`document_hashes=[document_hash]`，`:2283`）。**沒有任何寫入 observation 的程式路徑開啟過 filing document。** `record_observation_filing_document`（`sqlite_archive.py:1145-1185`）目前沒有任何 production call site。因此在本階段，`observation_filing_documents` 對所有既有 observation 必須維持 **0 列**。
* **Why:** 斷言「這個 observation 是從某份文件讀出來的」的前提是它真的被讀過。在沒有讀取路徑的情況下寫入這一列，等於主張一個 ST-EVA 從未開啟過的位元序列。
* **What breaks if violated:** 全量歷史 observation 會在第一次 provenance backfill 時被貼上從未發生過的文件血統，且因為 append-only 無法收回。

### 23. XBRL `contextRef` 目前不可得；`source_fact_id` 的 `context=accession` 是凍結的相容性要求

**FROZEN ARCHITECTURAL DECISION — 已量測的限制，不是待修的缺陷。**

* **Rule:** `contextRef` **不是被 ST-EVA 遺失，而是端點從未交付**：`companyconcept` 的 unit entries 不含它，`SecFact`（`sec_provider.py:825-848`）也沒有對應欄位。其生產後果是 `context=accession` 與 `document_ref=accession` 重複（`sec_ingest.py:2247,2252`），context 槽位不帶任何 dimension 資訊；同一 `(accession, taxonomy, concept, period_start, period_end)` 的所有 dimension member 收斂為同一個 `source_fact_id`，第 2 個以後由 `_fact_held` 跳過。此收斂**是已記錄的**：一個 accession 回報多個不同值時會寫入 `dimension_collision`（kind `SAME_PERIOD_DIFFERENT_VALUE`，`:2191-2236`），讀回時為 `DIMENSION_COLLISION`（`evidence_query.py:94,349`）。
* **凍結後果:** provenance 階段**嚴禁**變更 `source_fact_id` 的 preimage 或其 production wiring。那會為每一筆既有 SEC 事實換一個新身分、令 stored-identity 可重現性測試失敗（`tests/test_ingestion_aapl.py:735-757`、`tests/test_ingestion_cross_company.py:333-352`）、把整段 SEC 歷史以新 `source_fact_id` 重新附加，並要求重建無法重建的歷史 provenance。未來的文件讀取路徑**可以**讀 `contextRef`，但**只能**用於「定位」（證明唯一性、分離 dimension member），**不得**用於鑄造新的事實身分。
* **相關事實:** `tests/test_ingestion_aapl.py:95-109` 與上述兩組測試並不矛盾——前者釘住 **preimage**（context 是一個鍵，所以真實 contextRef 會分離 member），後者釘住 **stored value**（相容性要求）。
* **位元掃描的界限:** `concept + period`（加不加 value 都一樣）**不能**建立精確來源 provenance——單一 concept 在 TSM 20-F 即有七個 fact instance，且 dimensioned 與 undimensioned context **值相同**（`ifrs_capex_context_237.py:21-25`），因此 value 比對也無法 tiebreak。掃描只能作為候選產生器，永遠不得作為斷言。
* **Where it is pinned:** `docs/ADR-XBRL-SOURCE-DOCUMENT-PROVENANCE.md` Decisions 4–5（ADR §2 / §7 為規範來源）。
* **Amendment 1:** `docs/ADR-XBRL-SOURCE-DOCUMENT-PROVENANCE.md` Amendment 1 §1–§12 記錄文件讀取路徑的身分設計（invariant 24–27）。

### 24. 文件讀取路徑必須沿用 `source_fact_id`，且不得企圖用它分辨文件或 dimension

**FROZEN ARCHITECTURAL DECISION — Amendment 1。**

* **Rule:** 未來讀取 filing document bytes 的路徑，其 observation 身分**必須**以 production 現有方式計算 `source_fact_id`（`document_ref=accession`、`context=accession`），**不得**改動 preimage。文件與 `contextRef` 資訊**不得**進入 observation 身分。
* **結構理由（已驗證）:** `observation_id` = `ingest|{metric}|{concept}|{accession}|{period_start\|instant}|{period_end}|{unit}`（`sec_ingest.py:2391-2394`）不含 route；`content_hash` 12-key 亦不含 `source_fact_id`。`record_observation` 在 content_hash 命中既有列時提前 return 且**不回填** `source_fact_id`（`sqlite_archive.py:1284-1296`）。所以第二條路徑**在結構上無法**為同一事實建立第二筆 observation——用新命名空間當 observation 身分只會製造 duplicate reading，正是 §E.1 要拒絕的失敗。
* **既有承諾:** `evidence_model.py:180-182` 明確承諾「two adapters that read the same filing produce the same `source_fact_id`」。`companyconcept` 路徑與文件路徑就是讀同一份 filing 的兩個 adapter，因此**必須**產生相同 id；這是 Option A 成立、Option B 與 Option C 成立的唯一理由。
* **硬上限:** `observation_id` 沒有 dimension 槽位，所以同一 concept/period/unit 的兩個 dimension member 會在 **primary key** 上相撞，與 `source_fact_id` 及任何未來命名空間無關。文件路徑**不得**嘗試存放第二個 member；其歧義由既有 `dimension_collision` 機制記錄。
* **What breaks if violated:** 同一個經濟事實被同一份 filing 的兩條路徑存成兩筆 observation，archive 的去重基礎失效。

### 25. 文件層事實節點使用新的獨立命名空間 `document_fact_id`（前綴 `dfid_`）

**FROZEN ARCHITECTURAL DECISION — Amendment 1。**

* **Rule:** 文件層的事實節點（occurrence）擁有自己 8-key、value-independent、locator-independent 的 preimage：`{provider, asset_id, accession, document_id, taxonomy, tag, context_ref, unit_ref}`。`dfid_` 前綴目前未被占用（已用：`sfid_`、`doc_`、`decl_`、`fid_`、`fit_`、`fdd_`、`fac_`、`ifc_`、`fds_`）。
* **必須包含:** `document_id`——它是**唯一**能精確區分 filed primary HTML / EDGAR 產生的 `_htm.xml` / legacy `EX-101.INS` 的身分，而且它**不含任何分類**，因此在結構上滿足 invariant 19；`accession`——`document_id` 是 content-addressed，跨 filing 可能共用相同位元組（EDGAR 產物），而兩個 filing 的相同位元組是兩次不同的申報。
* **明確排除:** value（重述是不同事實，見 `evidence_model.py:184-188`）、byte locator（由身分化出，屬證據）、`period_start`/`period_end`（在 XBRL 內位於 context 內，由 `contextRef` 決定）、`filename`（事實存在於**位元組**中）、`captured_at`/`capture_kind`、任何 classifier 欄位。
* **與 `source_fact_id` 的關係:** 兩者是**不同物件的身分**，preimage 不同、前綴不同，**永不比較、永不等價**。`dfid_` **嚴禁**寫入 `observations.source_fact_id`。
* **前置條件:** `(document_id, taxonomy, tag, context_ref, unit_ref)` 在單一文件內必須唯一；違反時記為**歧義**，絕不產生第二個身分。
* **What breaks if violated:** 兩套命名空間互相冒充，任何跨層 join 都會把「讀到的理解」與「文件實際宣告的節點」混為一談。

### 26. `contextRef` 與 `unitRef` 是 occurrence 身分的必要成分；byte locator 屬證據不屬身分

**FROZEN ARCHITECTURAL DECISION — Amendment 1。**

* **Rule:** `contextRef` 是 instance 對**整個申報脈絡**的自身識別：entity identifier + scheme、期間（instant / start-end / forever）、以及 segment/scenario 軸上的每一個 `explicitMember`/`typedMember`。它**不可**由 period 或 value 取代。
* **Why:** 已量測的反例——`ifrs_capex_context_237.py:21-25`：同一 concept、同一期間集，dimensional 與 undimensioned context **值完全相同**。在「concept + period（加不加 value）」之下這兩個事實不可分辨；在 `contextRef` 之下可分辨。
* **Byte locator 屬 evidence:** 給定 `(document_id, contextRef, tag, unitRef)` 即可算出 locator；把它放進 key 會讓 parser 的 locator 策略改變時全部事實換 id，並把同一節點的兩個位元位置變成兩個事實。此處**刻意背離** `filing_document_statements` 把 locator 放進 key 的做法（`0020:370-372`）：statement 是沒有語意鍵的純文字節點，只有 locator 可用；XBRL fact 有 `contextRef`。
* **唯一 insert 前置條件:** `(document_id, taxonomy, tag, context_ref, unit_ref)` 在文件內唯一。
* **What breaks if violated:** dimension member 會被誤判為同一事實——正是 amendment 已記錄的「值相同但 context 不同」那一類。

### 27. 文件路徑的寫入邊界：不得讓 filing document 進入 `document_hashes`，且其 observation 的 `source_fact_id` 為 NULL

**FROZEN ARCHITECTURAL DECISION — Amendment 1。**

* **Rule（寫入陷阱）:** 去重路徑上 `record_observation` 會呼叫 `_link_documents(existing_id, document_hashes, ...)`（`sqlite_archive.py:1290-1294`）。**嚴禁**把 filing document 的 hash 當作 `document_hashes` 傳入——那會寫出一條 `observation_sources`，主張該 observation 是從該文件讀出的，完全繞過 `observation_filing_documents` 的 0/1 精確斷言規則，而且**不發出任何錯誤**。
* **Rule（後果）:** 文件路徑建立的 observation，其 `observations.source_fact_id` 為 **NULL**；`dfid_` 不得寫入該欄。因此這些 observation **對 `interpretations` 不可見**（`0017:91-92` 為 `NOT NULL REFERENCES observations(source_fact_id)`），`admissions.source_fact_id` 亦為 NULL，`fullscope_bulk.py:325-346`、`merge_sources.py:124-133`、`crossframework_verify.py:331` 這些以 `source_fact_id` join／select 的路徑會略過或讀到 NULL。
* **Why:** 這些後果是**已知且被接受的**，不是缺陷；但在 `interpretations`／`admissions` 的處置被決策之前，**嚴禁**任何文件路徑的 observation 進入 valuation boundary。
* **What breaks if violated:** 一條未被 0/1 規則保護的 `observation_sources` 斷言會靜默存在，而「修正機制無法指向文件路徑事實」會在需要重解讀時才被發現。
* **Phase 3C-B 狀態:** **未授權。** Amendment 1 §11 列出五項新的架構／schema 前置條件，屬**第二次 design freeze**，不是 3C-B 實作。

### 28. CORRECTION：文件路徑的 observation 帶 accession-scoped `sfid_`，`source_fact_id` 為 NULL 的條款已撤回

**FROZEN ARCHITECTURAL CORRECTION — Amendment 2。此條款取代 invariant 27 的「Rule（後果）」前半段；invariant 27 保留於原處以記錄當時凍結了什麼。**

* **Rule:** 文件路徑建立的 observation，其 `observations.source_fact_id` **必須**是 production 現有方式算出的 accession-scoped `sfid_`（與 invariant 24 同一要求），且**嚴禁**寫入 `dfid_`。**它不是 NULL。**
* **撤回理由:** 舊條款與 invariant 24 直接矛盾——一個算不出來也不落地的 `source_fact_id` 既不提供 adapter-independence，也不提供任何去重，只是一個被丟棄的值。而且該條款會讓文件路徑事實**完全無法被更正**：`knowledge_axis.py:182-183` 對空值拋 `KnowledgeAxisError`，`0017:89-92` 的 `interpretations.source_fact_id` 為 `NOT NULL REFERENCES`，而 `interpretations` 的存在理由正是 2.53 這類「讀錯了要能改」的情況。
* **已驗證不受阻:** `observations_source_fact_full`（`0017:54-55`）是**完整** UNIQUE index，SQLite 視 NULL 為相異，所以它從未阻擋過非 NULL 值。
* **後果（與舊條款列出的相反）:** `interpretations`、`admissions`、`knowledge_axis` **全部照常運作**；`fullscope_bulk.py:325-346`、`merge_sources.py:124-133`、`crossframework_verify.py:331` **不需任何加寬、排除或修改**。
* **What breaks if violated:** 一個有權威卻不可更正的證據層——比缺資料更糟，因為它讀起來像已解決。

### 29. `filing_document_fact_occurrences` 是「邏輯事實」身分，不是「實體位元組位置」身分

**FROZEN ARCHITECTURAL DECISION — Amendment 2。**

* **Rule:** 該 relation 記錄的是**一份文件對一個邏輯 XBRL 事實的斷言**，身分為 `dfid_`；byte locator 僅為證據 payload。**同一邏輯事實在同一文件中的多個實體外觀必須收斂成一列**，所有 byte span 收進 `locators_json`（canonical、確定性排序的陣列）。不需要另外的 evidence-occurrence relation。
* **Why:** XBRL 中 `(concept, context, unit)` 由 instance 保證**至多出現一次**，這是文件自己宣告的語意身分；實體位置則是序列化器的產物——inline XBRL 的 `ix:continuation` 讓**一個事實合法地跨越多個 byte range**。把 locator 放進身分會把單一事實分裂成數個，等於製造事實。
* **與 0020 的差別（不可直接援引）:** statement 是沒有語意鍵的純文字節點，locator 是它僅有的識別物，故放進 key（`0020:370-372`）；XBRL fact 有 `contextRef`，故 locator 是**衍生證據**。
* **偵測機制:** `(document_id, taxonomy, tag, context_ref, unit_ref)` 的五欄 UNIQUE index 讓「同一三元組出現兩個節點」（Case D）成為**資料庫保證的歧義偵測**，而不是 writer 的承諾。
* **What breaks if violated:** `ix:continuation` 型式的單一事實會被存成數筆 observation 級事實。

### 30. 候選文件 cardinality 以 `filing_documents` 身分計算；`observation_sources` 永不指向 filing document

**FROZEN ARCHITECTURAL DECISION — Amendment 2。**

* **Rule（計算粒度）:** 候選文件數 = 所有已鑄 occurrence 之中**相異 `(asset_id, accession, filename)`** 的數量。**嚴禁**以 `document_id` 或 capture 列數計算——同一 filename 的兩次不同位元組 capture（Case B）否則會把可解的 1 誤判成 2。0 → UNAVAILABLE；1 → 寫入斷言；≥2 → 不作斷言。
* **Rule（寫入邊界）:** `observation_sources` 的語意是「這個讀取值是從哪一份**取得回應**抽出來的」。filing document 是**關於申報的證據**，不是取得回應，兩者語意不同。新增 `BEFORE INSERT` trigger：`NEW.document_id` 一旦出現在 `filing_document_captures` 即 `RAISE(ABORT)`。精確來源文件只允許由 `observation_filing_documents` 宣告。
* **已驗證的漏洞:** `_link_documents` 在**去重提前 return 與 insert 兩條路徑上都會執行**（`sqlite_archive.py:1290,1373`），而 `document_id_for`（`:1213-1226`）以 `content_hash` 查找，filing document 的位元組**確實存在於 `source_documents`**（`sec_ingest.py:1964-1976`），唯一防線只拒絕「從未 capture 過」的 hash。`observation_sources` 亦**完全沒有 append-only trigger**（僅有 index，`0001:167-175`）。
* **Why:** 這是**潛在的架構違反**，不是單純的證據路徑。凍結的 0/1 語意只與最弱的寫入路徑一樣強。
* **What breaks if violated:** 一條未受 0/1 規則保護、卻會被 `documents_for()` 當成「這份 observation 來自哪個文件」回答的列會靜默存在。
* **Phase 3C-B 狀態:** **仍未授權。** 設計問題已關閉（Amendment 2 §1–§11），剩下的閘門是實作 migration `0021` 與十項驗收標準，屬另一個任務。

---

# E. Architecture Philosophy

ST-EVA 架構的核心哲學只有一句話：  
**「拒絕在不具備完全同一性的概念之間進行過早的折疊（Refusal to prematurely collapse distinct concepts）。」**

在許多軟體系統中，工程師為了簡化代碼，傾向於把相近的概念合併。但在財務估值與審計系統中，每一次簡化折疊，都是向未來的資料災難埋下一顆定時炸彈。

### 1. 概念層的絕對分離 (The Separation of Concerns)
```text
Fact (事實)
  ≠ Evidence (證據)
    ≠ Decision (決策)
      ≠ Interpretation (解讀)
        ≠ Derivation (推導)
```
* **Fact vs Evidence:**  
  * *Fact (Observation)* 是客觀世界中由來源申報的一組位元與數字（例如：微軟在 2013 年 8-K 中宣告 Q1 EPS 為 0.68）。它一旦被申報，就永遠不可抹除。
  * *Evidence* 是我們對該事實的組織方式。同一個事實，在不同的問題脈絡下，其證據狀態可能是 `SOURCE_REPORTED`，也可能是與另一來源對比下的 `CONFLICTING`。
* **Evidence vs Decision (Admission):**  
  * 證據表明「有這個數據存在」。
  * 決策表明「估值引擎現在是否允許使用它」。  
  * **Repository 實例（Migration 0019）：** 在 ST-EVA 3.32 中，曾有人提議在 `Observation` 上增加一個 `role` 欄位（表示它是 ENGINE_INPUT 還是 EVIDENCE_ONLY）。測量結果顯示：這樣做會毀滅 291,134 筆歷史觀測的雜湊唯一性，或者在時點變更時被去重機制靜默丟棄（此為設計階段量測，見 §D.5 的時點說明）。因此，ST-EVA 堅定建立了獨立的 `admissions` 表。
* **Fact vs Interpretation:**  
  * *Interpretation* 是 ST-EVA 對事實的理解演進。
  * **Repository 實例（Migration 0017）：** 在 ST-EVA 2.53 中發現一個解析錯誤：非美元貨幣的事實被解析為無貨幣比率。修復此問題後，我們**不能**直接修改原始 `Observation`（觸發器會直接 `ABORT`，且 `source_fact_id` 唯一索引會拒絕）。這不是一個新事實，而是 ST-EVA 在後續時點對舊事實的新「解讀」。因此建立 `interpretations` 表，透過 `knowledge_at` 記錄理解發生的時間，徹底守住了不可變性。
* **Decision vs Derivation:**  
  * 准入決策挑選合規輸入；推導算術基於輸入進行確定性計算。兩者擁有完全不同的生命週期。

### 2. 四大時間軸的絕對分離 (The Four Time Axes)
```text
Source Time (available_at)
  ≠ Knowledge Time (knowledge_at)
    ≠ Decision Time (decided_at)
      ≠ Retrieval Time (retrieved_at)
```
* **Source Time (`available_at`):** 來源自身宣告該事實進入公共領域的法定時間（如 SEC SGML Header 的 `ACCEPTANCE-DATETIME`）。
* **Knowledge Time (`knowledge_at`):** ST-EVA 程式碼具備正確理解該事實的時點。
* **Decision Time (`decided_at`):** 准入決策執行的當下時點。
* **Retrieval Time (`retrieved_at`):** 我們的爬蟲發送 HTTP 請求取得回應的系統時點。

**為什麼不能折疊？**  
若把解析錯誤的修正合併至 `available_at`，等於在歷史檔案中宣稱：這份 2011 年的財報在 2011 年發布時就已經包含了解析器在 2026 年才修正的貨幣邏輯！這將使得任何基於 2011 年時點的回溯都帶有未來特異功能。

### 3. 典型儲存庫案例 (Concrete Repository Cases)
* **SEC vs Yahoo 跨來源對比 (2.3-B):**  
  SEC 是監管申報，Yahoo 是市場聚合商。兩者對同一季營收有差異時，`cross_validation.py` 輸出 `CONFLICTING` 並給予 `cmp-` 前綴，絕對不私自設定「以 SEC 為準」而把 Yahoo 刪除。
* **Registry Concept vs Metric (Migration 0007):**  
  `us-gaap:Revenues` 是申報人打上的標籤；`revenue` 是 ST-EVA 定義的語意概念。蘋果公司某一年可能把標籤換成 `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax`。若直接將標籤等同於指標，時間序列將產生斷崖。Core Registry 透過顯式映射將兩者解耦。
* **Furnished vs Filed 證據 — 【方法論政策，非現行實作】 (ADR Decision 10–14):**  
  8-K Item 2.02 的新聞稿附件（EX-99.1）在法律上是「Furnished」（提供）而非「Filed」（申報），不承擔 Section 18 法定虛偽陳述責任。ADR 規定 ST-EVA **不得**因此歧視拒絕，也不得抹殺其法律屬性——法律免責聲明須保留在血統中；回溯時以 `16:00 ET` usable-date convention 決定 Point-in-Time 可用性。

  > [!WARNING]
  > **以上是已凍結的方法論 / 契約政策，不是現行 production 實作。**
  > 目前 production code 中**完全沒有** `furnished` / `filed` 證據類別欄位、沒有 `legal_status_note`、沒有 `audit_status`，也沒有 `16:00 ET` cutoff 的實作常數（`evidence_class`、`legal_status_note`、`audit_status`、`accounting_basis`、`fiscal_year_end_month` 在任何 `.py` / `.sql` 中出現次數皆為零——見 `docs/ST-EVA-DATA-ADMISSION-RECONCILIATION.md:373-377`）。
  > ADR Decision 10 的五項合資格條件（issuer-primary / quarter-specific / 直接陳述 / 可確認公開時間 / 可回溯）目前**沒有**對應的 production validator。8-K Item 2.02 EX-99.1 現況是「已決策但未實作」，不可當成已生效的准入規則引用。
  > §G「§J 專題」中 `evidence_class` 的說明同屬此類：**舉例說明用的假想欄位**，不是現存欄位。

---

# F. Dependency Direction

## F.1 Conceptual Layering（語意分層）

以下是**語意分層**：每一層在概念上只能消費它下方層的產物。這是設計意圖，也是修改程式碼時應遵守的方向。

```text
        Provider / Ingest (sec_provider.py, sec_ingest.py, fundamental_provider.py)
               ↓
        Data Contract (data_contract.py)  [ZERO ST-EVA IMPORTS]
               ↓
        Evidence / Registry (evidence_model.py, evidence_query.py, core_registry.py,
                             registry_seed.py, registry_identity.py, coverage_semantics.py)
               ↓
        Admission (evidence_valuation_boundary.py)
               ↓
        Engine (st_eva_runner.py)
               ↓
        Persistence & Replay (sqlite_archive.py, archive.py)   ← 見 §F.2.3，這一層會反向驅動上面的管線
               ↓
        Web Services / API (web/service_adapter.py, web/job_manager.py, web/app.py)
```

## F.2 實際 Python Import Graph（**並非嚴格 DAG**）

> [!WARNING]
> **誠實記錄：ST-EVA 目前的 Python import graph 不是嚴格 DAG。**
> 把它描述成「嚴格單向階層」是錯的。本節列出實際情況，包括一個刻意存在的 import cycle。

### F.2.1 實際內部 import 清單（由原始碼 import 陳述式核對）

* `data_contract.py`: **`[]`** — 絕對純粹，零內部依賴。**這一條成立且必須保持。**
* `evidence_model.py`: `['data_contract']`
* `core_registry.py`: `['data_contract']`
* `registry_seed.py`: `['core_registry']`
* `cross_validation.py`: `['data_contract']`
* `fundamental_provider.py`: `['data_contract']`
* `knowledge_axis.py`: `['data_contract']`
* `coverage_semantics.py`: `['data_contract']`
* `sec_provider.py`: `['data_contract']`
* `registry_identity.py`: `['core_registry', 'data_contract', 'evidence_query', 'registry_seed']`（以 `import X  # noqa: F401` 釘住模組身分）
* `evidence_query.py`: `['core_registry', 'coverage_semantics', 'data_contract', 'evidence_model', 'sqlite_archive']`
* `evidence_valuation_boundary.py`: `['archive', 'core_registry', 'data_contract', 'evidence_query']`
* `sqlite_archive.py`: `['archive', 'data_contract', 'knowledge_axis']`
* `archive.py`: `['data_contract']` + **function-local** `['evidence_valuation_boundary', 'registry_identity']`（見 F.2.2）
* `sec_ingest.py`: `['archive', 'core_registry', 'coverage_semantics', 'data_contract', 'evidence_model', 'sec_provider']`
* `investment_context.py`: `['operation_registry']` + 資料契約層依賴
* `st_eva_runner.py`: `['archive', 'cross_validation', 'data_contract', 'evidence_valuation_boundary', 'fundamental_provider', 'investment_context', 'registry_identity', 'report_formatter', 'sec_provider', 'sqlite_archive']`（其中 `archive` 與 `sqlite_archive` 是 **function/branch-local** import，不是 module-level；見 §F.2.3。其餘多數亦為 function-local。）
* `web/job_manager.py`: `['web.schemas', 'web.service_adapter']`
* `web/service_adapter.py`: `['archive', 'core_registry', 'registry_seed', 'sqlite_archive', 'st_eva_runner', 'web.schemas']`
* `web/app.py`: `['web.job_manager', 'web.schemas']`

### F.2.2 已存在的 import cycle 與其 cycle-break 機制

實際存在的環：

```text
archive.py ──(function-local import, archive.py:462)──▶ evidence_valuation_boundary.py
evidence_valuation_boundary.py:84 ──▶ evidence_query.py
evidence_query.py:48 ──▶ sqlite_archive.py
sqlite_archive.py:29 ──▶ archive.py
```

`archive.py` 的 replay 路徑在**函式內部**才 `from evidence_valuation_boundary import admit, V1_CROSSING_METRICS`（`archive.py:462`，並在 `try:` 內、且以 `connection is not None` 為前提）。

* **這是 cycle-break mechanism，不是依賴注入（dependency injection）。** 若將它重新提升為模組層級 import，會直接造成循環匯入錯誤。
* Replay 的**估值重建**部分確實是注入的：`build_document` 是由呼叫端（`st_eva_runner` 端）以參數傳入 replay 的可呼叫物件（`archive.py:398`, `archive.py:561`）。這才是真正的依賴注入；**不要**把兩者混為一談。

### F.2.3 分層假設被打破的三處（維護者必須知道）

1. **Engine 依賴 Archive，不是反過來。** `st_eva_runner.py` 對 `Archive` / `SQLiteArchive` 存在**實際 dependency edge**，但 import **不是 module-level**：`archive` 是 `_archive_run()` 內的 **function-local** import（`st_eva_runner.py:1985`），`sqlite_archive` 是 CLI branch 內的 function-local import（`st_eva_runner.py:2514`）。**dependency edge 與 import placement 是兩件事**，不要混為一談——runner 確實在 CLI 路徑直接 `SQLiteArchive(args.archive_path)`，但那是 branch 內取得型別，不是模組載入期建立。§F.1 把它們畫在 Engine 之下是**語意**分層，不是 import 方向。
2. **Admission 傳遞依賴 SQLite 實作。** `evidence_valuation_boundary → evidence_query → sqlite_archive`。因此「准入層不知道儲存實作」並不成立（見規則 1 的限定說明）。
3. **Archive 向上驅動核心管線。** replay 會重新執行 `admit()`（`archive.py:471-473`）。這是刻意的（§B.0.1），但它使 import graph 與語意分層不再是同一張圖。

### 危險反向依賴禁止守則 (Forbidden Reverse Dependencies)
1. **Core 不得直接撰寫 SQL：** `data_contract` 與 `st_eva_runner` **不得**包含 `import sqlite3` 或任何 SQL 語句。
   * *現況（已核對）：兩者皆無 `sqlite3` import、無 SQL 字串。此規則成立。*
   * *但「核心對儲存實作無感知」**尚未**完全成立*：`st_eva_runner` 直接 import `sqlite_archive.SQLiteArchive`。因此切換儲存後端需要改動 Engine 端點，該端點是可接受的、可見的替換點，不是抽象邊界。要擴張此規則到「零依賴」，需要先在 Engine 與 Archive 之間引入真正的介面注入——那是尚未進行的設計工作。
2. **Archive 不得包含第二套 Engine：** `archive.py` 在執行 Replay 時，必須透過注入的 `build_document` 呼叫生產環境的統一管線，嚴禁在歸檔層自行實現一套簡化版的估值計算。**此規則成立且必須保持。**
3. **Web 不得實作任何估值邏輯：** `web/` 的職責是 DTO 序列化、HTTP 傳輸與非異步協調。所有計算必須委派給 `service_adapter.py`，嚴禁在 FastAPI 路由中出現任何財務公式。**此規則成立**（`web/app.py` 僅 import `web.job_manager` 與 `web.schemas`，不直接觸及 core）。
4. **Research 腳本嚴禁成為生產依賴：** `research/` 與 `experiments/` 內的任何模組禁止被根目錄的生產代碼引入。
5. **Registry 語意不得從來源標籤逆向猜測：** 嚴禁在沒有映射表的情況下，直接用正則表達式把 XBRL tag 轉成指標名稱。
6. **不得為了「看起來更分層」而移除 §F.2.2 的 cycle-break import。** 那會讓 replay 的決策重算能力直接消失，或造成循環匯入。

---

# G. Identity Model

ST-EVA 存在**多套彼此獨立的識別機制**。它們**不是同一套 identity 的細分**，也**不可互換**。

> [!CRITICAL]
> **本節最重要的區分：`source_fact_id` 與 `observation_content_hash` 是兩個不同的機制，不是同一個東西的兩種說法。**
> 前者是「某份來源文件中的某個宣告點」，後者是「`record_observation()` 寫入前對整筆 observation 內容計算的雜湊」。
> 兩者的 preimage、是否含數值、使用位置、強制方式**全部不同**。混淆這兩者會導致維護者修改錯誤的 hash。

## G.1 Identity Map

| Identity | What it identifies | Defined by | Used for | Must not be confused with |
| :--- | :--- | :--- | :--- | :--- |
| **Document Identity** (`content_hash`) | 一份已存取的外部來源文件的原始位元組 | 原始 bytes 的 SHA-256（`source_documents`） | 內容尋址儲存、重複下載防護、observation↔document 連結 | Observation 的 hash；Source Fact Identity |
| **Source-Fact Identity** (`source_fact_id`) | **單一來源文件內的某一個宣告點** | `evidence_model.source_fact_id()` 的 7-key preimage：`source_id`, `document_ref`, `taxonomy`, `concept`, `period_start`, `period_end`, `context`（`evidence_model.py:168-201`） | 「同一個來源文件中的同一個宣告點」；DB partial UNIQUE index（`0006:50-52`）；`admissions.source_fact_id` 的參照目標 | **`observation_content_hash`**（值相依、12-key、作為 writer dedup key）；Observation 本身 |
| **Observation Content Identity** (`observation_content_hash`) | `record_observation()` 為一筆即將寫入的 observation 計算的**內容雜湊** | `observation_content_hash()` 的 12-key preimage（見 §G.2） | 該 writer 路徑的 **persistence dedup key**；`row_id` 衍生；`observations.content_hash` 欄位 | **Source-Fact Identity**（值獨立、7-key、DB index）；Document Identity |
| **Lineage Identity** (`lineage_id`) | 同一 `(asset, metric, concept, period)` 的跨申報版本串聯 | `sqlite_archive._lineage_id()` 的 preimage：`asset`, `metric`, `concept`, `period_start`, `period_end`（`sqlite_archive.py:138-149`） | 串聯重編前後的觀測；跨期時間序列追蹤 | 內容雜湊；具體數值 |
| **Registry State Identity** (`registry_state_identity`) | 「是哪一版**註冊表資料**」 | DB 中所有語意映射列的正規化摘要 | 讓 admission 裁決記錄自己依據的 registry 版本 | Resolver Policy Identity（那是**程式碼**版本，非資料版本） |
| **Resolver Policy Identity** (`resolver_policy_identity`) | 「是哪一版**解析器 Python 原始碼**」 | 解析器模組的全檔 SHA-256 | 讓 admission 裁決記錄自己依據的程式碼版本 | Registry State Identity；runtime 環境變數 |
| **Admission Identity** (`admissions.identity`) | 某一個**准入裁決**本身 | 該裁決欄位的內容衍生 key（`0019:74-78`），含裁決維度與兩份 policy identity | 保證相同情境下的裁決唯一；`supersedes` 鏈條 | 價格數值；財報數值；Observation hash |
| **Snapshot / Document Identity** (`document_hash`) | 某一執行時點封存的**完整 context 文件** | context JSON 的正規化 JSON hash | 防竄改驗證；Replay 對比基準 | Document Identity（那是外部來源文件的 bytes） |

### G.2 `observation_content_hash` 的 12-key preimage

`sqlite_archive.py:112-135`：

```python
payload = {
    "observation_id": observation.observation_id,   # 1
    "metric":         observation.metric,           # 2
    "provider":       observation.provider,         # 3
    "concept":        _concept_of(observation),     # 4
    "value":          observation.value,            # 5
    "unit":           observation.unit,             # 6
    "currency":       observation.currency,         # 7
    "period_start":   observation.period_start,     # 8
    "period_end":     observation.period_end,       # 9
    "as_of":          observation.as_of,            # 10
    "available_at":   observation.available_at,     # 11
    "accession":      _accession_of(observation),   # 12
}
```

**共 12 個 logical keys。這是 value-dependent 的**——`value` 在 preimage 內，所以同一 (concept, period) 由不同申報報出不同數值時，是**不同的** hash（`sqlite_archive.py:116-117` 註明了這正是設計意圖）。

### §J 專題（歷史階段名稱）：`observation_content_hash()` 的神聖邊界

> [!NOTE]
> **名稱說明：** 此處的「§J」是 ST-EVA 歷史進程中對「observation identity conformance」這個階段的稱呼（對應 `tests/test_observation_identity_conformance.py`）。
> **它與本文件的第 J 章「How to Modify ST-EVA Safely」是不同事物**，不要混淆。

**`observation_content_hash` 定義的是 observation 的內容／持久化去重身分（Observation Content Identity），它不等於、也沒有取代 `source_fact_id`（Source-Fact Identity）。** 兩者並存，服務不同目的（見 §G.1）。

它的散列前像**包含且僅包含**上列 12 個 logical keys。

**`basis_json` 與 `raw_json` 明確不在雜湊前像中**（`sqlite_archive.py:119-132` 的 payload 中沒有 `basis` 或 `raw`）。

這意味著：**不能**把 Evidence classification metadata 塞進 `Observation` 的 JSON 容器後，就期待 archive 自動保留同一筆 observation 的多重分類。實際行為是：

`record_observation()` 計算 hash 後先做一次 lookup：

```python
content_hash = observation_content_hash(observation)
existing = self.connection.execute(
    "SELECT observation_id FROM observations WHERE content_hash = ?",
    (content_hash,),
).fetchone()
if existing is not None:
    self._link_documents(...)   # 連結文件
    return existing["observation_id"]   # ← 直接返回，第二筆被丟棄
```
（`sqlite_archive.py:756-768`）

因此，若兩個對同一客觀事實、但 Evidence 分類元數據不同的 observation 被寫入（例如假想的 `evidence_class="furnished"` 與 `evidence_class="filed"`），它們會算出**完全相同的 hash**，第二筆會被判為重複資料並**靜默丟棄第二個分類**——不報錯、不合併。

> [!NOTE]
> `evidence_class` 目前**不是**現存欄位（production code 中出現次數為零）。上述是說明該機制如何運作的反例，非現存程式碼路徑。

> [!WARNING]
> **千萬不要為了迎合下游需求而修改 `observation_content_hash`：**
> 未來的開發者不可為了讓分類元數據生效，就輕率地把 `evidence_class` 或 `basis_json` 加進 Observation 的 Hash 裡！
> Observation 的 hash 表達的是「這個 observation 的內容是什麼」，而 `evidence_class` 是「證據層如何歸類它」。
> 把分類塞進 hash 會讓 observation 的身分**隨讀取層判斷而改變**——同一客觀事實在 EVIDENCE_ONLY 與 ENGINE_INPUT 情境下會得到兩個不同身分，等於把 §D.4 / §D.5 辛苦守住的分離重新折疊掉，還會使既有 hash 與快照全面失效。
> **正確的邊界處理解決方案**是讓分類由 Evidence 讀取層 / Admission 裁決 / 未來的正式 schema 承載，絕對不能藉由混淆 Observation 身分來解決讀取層問題。

---

# H. Persistence Model

## H.1 儲存庫目錄的語意邊界

```text
st-eva/
├── archive/        -> 唯讀正向遷移 SQL (0001-0019)；系統 Schema 憲法
├── data/           -> 【runtime archive 位置】目前為空
├── history/        -> 已封存的正式評估發布報告與 context 快照
├── reports/        -> 已核准的設計／決策報告（tracked，被 registry_seed 引用）
├── research/       -> 探索性研究與原始憑證（見 H.4 的 Git 說明）
├── experiments/    -> 2.x 時代遺留之凍結實驗基準 (46 legacy tracked files)
├── docs/           -> 架構、ADR、方法論契約與治理文件
├── tests/          -> 不變量的自動化守護
└── web/            -> FastAPI / React PWA
```

### H.1.1 本 repository 目前沒有已填充的 production corpus（**重要**）

> [!WARNING]
> **本 repo 目前不存在任何已填充的 SQLite 資料庫。**
> 已核對：整個 working tree 內 `.sqlite` / `.db` / `.sqlite3` / `.duckdb` 檔案數為 **0**。`data/archives/` 目錄存在但**為空**。

因此：

* `data/archives/` 是 **runtime location**（Web per-ticker archive 的寫入目標）與 **expected archive location**（CLI 預設為 `data/st-eva.sqlite`），**不是**「已經存放著生產資料的目錄」。
* **交付物是 schema，不是資料。** Migration 註解與早期文件中出現的觀測筆數／issuer 數是**設計階段對先前 corpus 的量測值**，該 corpus 並未保留在本 repo（見 `docs/ST-EVA-DATA-LAYER-AUDIT.md:16-46`）。§D.5 的 291,134 即屬此類。
* 這不影響架構邊界的正確性：schema 仍由 `tests/`（48 個測試檔）建立臨時 archive 而被實際結構性exercise。**Schema 被測試，不等於 Schema 被填充。**

### 語意區分 (Semantic Distinctions)
1. **Research Artifact $\neq$ Canonical Production Observation:**  
   在 `research/experiments/aapl-historical-pe-poc/` 內包含超過 1 GB 的 SEC 原始 SGML 文件與過渡 JSON（829 個檔案）。這些是研究材料，是為了證明方法論可行性而存在的。它們**不是**生產環境的正規觀測。只有當正式的 Ingestor 解析並寫入 `data/archives/` 時，它才具備生產效力。
2. **Archive Schema $\neq$ Research Corpus:**  
   研究目錄中可能存在研究員自己建立的臨時 SQLite 資料庫，那些資料庫是探索性的；`archive/migrations/` 定義的 26 張領域表（另加 1 張 `schema_migrations` 帳本表）才是正式資料庫綱要。
3. **嚴禁將研究 SQLite 自動提升為生產狀態：**  
   任何填滿數據的研究 SQLite，都包含特定實驗的簡化假設，絕不能未經驗證便直接複製為生產資料庫。
4. **`reports/` 是正式、被引用的設計紀錄，不是研究垃圾。**  
   這 35 個 tracked 檔案記載已核准的語意決策，且 `registry_seed.py`（生產 seed 資料）會**以檔名引用**它們作為映射依據。因此刪除或改寫 `reports/` 會使 registry 的可追溯性斷裂。它與 `research/` 的處置原則**不同**。

## H.2 Schema Capability ≠ Writer Behavior（**必讀**）

> [!WARNING]
> **`archive/migrations/0006_source_fact_identity.sql` 建立了 filing identity 欄位，但 `record_observation()` 並非在每一條寫入路徑上都會填寫它們。**
> **Schema 能夠儲存這些欄位，不代表 production writer 已全面維護它們。**

**Schema 已建立的欄位**（`0006:18-28`）：`taxonomy`, `accession`, `form`, `fiscal_year`, `fiscal_period`, `statement`, `instant`, `source_fact_id`（另加後續 migration 的 `source_concept_ref`）。

**Writer 的實際條件**（`sqlite_archive.py:756-845`）：

* `record_observation()` 先計算 `content_hash = observation_content_hash(observation)`（`:756`），再以該 hash 查詢既有列（`:757-760`）。
* **若已存在相同 `content_hash` 的列，writer 只 link documents 便 `return existing["observation_id"]`（`:761-768`）——它在 filing branch 之前就結束了。** 因此即使呼叫端傳入 `FilingRef`，只要同 hash 的列已由**不帶 `filing`** 的 writer 建立，`taxonomy/accession/form/fiscal_year/...` 就**不會**被 backfill：本路徑沒有任何 backfill（no-backfill 原則見 `0019_admissions.sql:36-39` 與 §J）。
* 只有在**沒有**既有列時才繼續：預設 INSERT 欄位清單（`:776-785`）**不包含**任何 filing identity 欄位。
* 只有在 **`if filing is not None:`** 分支內（`:819-838`）才會額外附加這 9 個欄位與對應的值。
* `sqlite_archive.py:841` 是**全 repo 唯一的 `INSERT INTO observations`**，因此上述條件是唯一的寫入閘門。

**目前各呼叫路徑的行為（已核對）：**

| 呼叫路徑 | 是否傳入 `filing` | filing identity 欄位 |
| :--- | :--- | :--- |
| `sec_ingest.py:1334`（SEC XBRL 增量 ingest） | **是**（`sec_ingest.py:1344` 呼叫 `_filing()`，`sec_ingest.py:1513-1542`） | 僅在該 `content_hash` **首次** INSERT 時填寫；命中既有 hash 時提前 return，不 backfill |
| `st_eva_runner.py:2023`, `:2025`, `:2033`, `:2036`, `:2045`（price / metrics / cross-source 封存） | **否** | **全部為 NULL** |
| `fullscope_bulk.py` | 不適用 | **不寫入**——它是雙 archive 的讀取與比對 harness（`SEMANTIC_FIELDS`, `fullscope_bulk.py:127-154`；全部為 `SELECT`），不是 writer |

> [!NOTE]
> **Current production writer paths are not uniform.**
> 同一個 repo 內的 `docs/ST-EVA-DATA-ADMISSION-RECONCILIATION.md:356-371` 也記錄了這個落差，但其描述機制不夠精確——該文件稱「the SEC API path leaves them NULL」，實際上真正的判準有兩層：**(1)** `filing is not None` 與否（SEC XBRL ingest 路徑 `sec_ingest.py` **確實**傳入 `FilingRef`，而 `st_eva_runner.py` 的封存路徑**沒有**）；**(2)** 該 `content_hash` 是否為首次寫入——**傳入 `FilingRef` 是必要條件，不是充分條件**。若同 hash 的列已由不帶 `filing` 的 writer 建立，`record_observation()` 會在 `:761-768` 提前 return，filing 欄位不會 backfill。
> 該文件的結論本身正確且仍然有效：`observations.form` **不能**作為「哪一份申報說了這句話」的可靠 index——在非 `sec_ingest` 建立的 archive 上，該查詢會靜默回傳空結果，而證據套件本身仍帶有 form。

**維護後果：**
* 若你依賴 `observations.taxonomy` / `.form` / `.source_fact_id` 等欄位做查詢或判斷，**必須先確認該列是由哪條路徑寫入的**。
* **傳入 `FilingRef` 是必要條件，不是充分條件：** 它只在該 `content_hash` **首次** INSERT 時生效；命中既有列時 writer 在 filing branch **之前** return（`:761-768`），**不會** backfill filing identity。不要假設「有傳 `FilingRef`」就一定有 filing 欄位。
* 新增 ingestion 路徑時，若需要 filing identity，**必須顯式傳入 `FilingRef`**，否則欄位會靜默留空。
* 讀取端已有雙來源容錯：`evidence_query.py` 與 `evidence_valuation_boundary.py` 都是**先讀欄位、再退回 `raw.sec_fact`**。

## H.3 Research 目錄的 Git 處置

> [!IMPORTANT]
> `research/` **不是**單純的「Gitignored 目錄」。
> `.gitignore` 以 `/research/` 規則忽略**新產生的研究產物**；但 `research/README.md` 與 `research/RESEARCH-ARCHIVE-MANIFEST.json` 等**控制／manifest 檔案仍為 tracked**。
> 這是刻意的：封存清單需要版本控制，原始憑證（約 1.15 GB）不需要。

---

# I. Replay Philosophy

Replay 在 ST-EVA 中是**一等架構公民（First-Class Architectural Property）**，而非附加的輔助工具。

### 1. 回放執行流 (Replay Workflow)

以下是 `archive.replay()` 的**實際執行順序**（`archive.py:392-612`）：

```text
1. 取出 as_of 之前 replay-eligible 的觀測集合
       observations_for(asset, as_of)                    archive.py:~430
        ↓
2. 解析 as_of 當下可知的價格觀測
       latest_knowable(..., metric=price)                archive.py:438
        ↓
3. 價格不存在 → 立即回傳 INSUFFICIENT（絕不替代）         archive.py:441-448
        ↓
4. 【重新執行】准入裁決 admit(store, asset, as_of, price) archive.py:471-473
       → 產出 admissions_recomputed
        ↓
5. 逐欄位比對 recomputed vs STORED admissions             archive.py:511-543
       （contract_id, source_fact_id, rgs, pol,
         price_contract_id, refusals, ...）
        ↓
6. 以【注入的】build_document 重建估值與 context          archive.py:561
        ↓
7. 與存檔 snapshot 比對 → MATCH / DIVERGED / NO_SNAPSHOT   archive.py:579-612
```

> [!CRITICAL]
> **Stored Admission is a comparison target, never a replay input.**
> 步驟 4 產生的是「今天重算的裁決」，步驟 5 才把它拿去跟資料庫裡**已儲存**的裁決比對。
> 已儲存的 `admissions` 記錄**從未被**餵進引擎。這兩者的角色不可互換（見 §D.6 / §D.7）。

### 2. 為什麼 Replay 絕不直接使用已儲存的 Admission
如果 Replay 直接讀取已儲存的 Admission，那麼：
1. 程式碼邏輯若被改壞，Replay 將完全無法發現；
2. Core Registry 映射若被篡改，Replay 也無法察覺。  
Replay 的目的就是檢驗：**「以今天的代碼和註冊表，重新審視昨天的歷史，能否得出與昨天一模一樣的決策與數值？」**

### 3. 四大回放結果 (The Four Outcomes)
* **`MATCH`:** 完全重現。重算結果與封存 Snapshot 雜湊完全一致，准入決策無分歧。
* **`DIVERGED`:** 分歧。相同的歷史輸入，今天卻算出了不同的結果或做出了不同的准入裁決（觸發警報，需審計是代碼 Bug 還是故意的方法論升級）。
* **`NO_SNAPSHOT`:** 該歷史時點未曾封存過 Snapshot，無法對比。
* **`INSUFFICIENT`:** 歷史資料不足。在歷史時點 $T$，歸檔庫中沒有足夠的合規數據來支撐計算。

### 4. 為什麼 `INSUFFICIENT` 是一個成功的誠實結果，而非失敗
在金融分析中，最危險的行為就是「在數據不足時假裝知道答案」。  
若時點 $T$ 缺乏合規價格或財報，系統優雅且明確地回報 `INSUFFICIENT`，代表系統忠實地捍衛了 Point-in-Time 邊界，拒絕捏造未來或替代歷史。**這是一個 100% 成功的系統行為。**

---

# J. How to Modify ST-EVA Safely

任何開發者或 AI Agent 在修改 ST-EVA 生產代碼前，**必須依序回答以下 12 道自我審查清單：**

### Historical maintenance checklist (not an active gate)
1. **Which layer am I changing?** （我正在改動哪一層？Raw, Ingest, Observation, Evidence, Admission, Engine, Snapshot, Replay, Web?）
2. **What semantic object owns this information?** （這項資訊的語意擁有者是誰？嚴禁把屬於 Admission 的概念塞給 Observation。）
3. **Is this a fact, evidence, interpretation, decision, derivation, or presentation concern?** （這是一個客觀事實、讀取證據、解讀、准入決策、推導計算，還是純展示需求？）
4. **Am I changing an identity / hash?** （我是否在變更任何 Hash 或 ID 前像？若是，是否考慮到這會毀掉去重或使得既有快照失效？）
5. **Am I changing a time axis?** （我是否動到了時間軸？我有沒有把 `knowledge_at` 或 `retrieved_at` 誤寫進 `available_at`？）
6. **Could this affect point-in-time replay?** （這是否會破壞歷史回溯？是否引入了在過去時點無法得知的未來資訊？）
7. **Could this affect Registry resolution?** （這是否會改變既有概念的解析結果？會不會讓原本明確的映射變成 AMBIGUOUS？）
8. **Could this affect Admission?** （這是否會改變指標進入引擎的條件？是否會靜默放寬檢驗標準？）
9. **Does this alter methodology rather than implementation?** （這是在改善實作，還是在偷偷變更經過核准的方法論？若是方法論變更，必須先修改 ADR/Contract！）
10. **Which invariant / tests protect the boundary?** （有哪些不變量與既有測試在守護這個邊界？我是否跑過迴歸測試？）
11. **Is a migration actually necessary?** （是否真的需要資料庫遷移？若僅是讀取端的需求，是否能由現有結構承載？）
12. **Am I accidentally creating a second source of truth?** （我是否在另一個表裡複製了數值，製造了潛在的雙重真理來源？）

### 顯式終止條件 (Explicit STOP Conditions)
遇到下列情況，**必須立即停止修改並向架構師/使用者回報**：
* ❌ **STOP:** 試圖在生產代碼中擅自解決尚未定案的方法論問題（例如 ADR-4.1 中的抽樣頻率或門檻）。
* ❌ **STOP:** 為了讓某個函式傳參方便，試圖把資料跨層搬移或折疊。
* ❌ **STOP:** 在沒有定義清晰語意擁有者的情況下，隨意在表或資料類別上加欄位。
* ❌ **STOP:** 因為下游需要額外元數據，就試圖去修改 `observation_content_hash`。
* ❌ **STOP:** 因為 ADR / Contract 寫了某條規則，就假設該規則已有 production 實作（見 §L.2.1 的清單）。
* ❌ **STOP:** 因為某個儲存的快照已經存在，就直接把它當作權威輸入而跳過驗證。
* ❌ **STOP:** 覺得某個架構層次「看起來很多餘」就想把它刪掉，卻未曾查明它背後守護的歷史 Bug 與不變量。

---

# K. Historical Decisions Explaining Today's Complexity

ST-EVA 今天的架構並非憑空設計，而是經歷了多輪慘痛的現實數據檢驗所沉澱的結果：

### 1. 2.0 時代：反向估值基礎 (Reverse Valuation Foundation)
* **問題：** 傳統財務分析工具充斥著黑箱目標價與隨意的樂觀/悲觀預測。
* **架構規則：** 確立純確定性反向工程。股價是輸入，假設是輸出；核心計算純 Python 化。
* **保留至今的原因：** 構成了專案不可動搖的科學哲學底座。

### 2. 2.3 時代：資料契約與跨來源驗證 (Data Contract & Multi-Source)
* **問題：** 早期代碼深度綁定 Yahoo Finance 專屬欄位名稱，當引入 SEC EDGAR 時代碼全面崩潰。
* **架構規則：** 建立嚴格無關來源的 `data_contract.py`，定義不可變 `Observation`；建立 2.3-B 跨來源比對（Yahoo vs SEC），不設私自偏好。
* **保留至今的原因：** 徹底解耦了資料提供商與估值計算，使多來源接入成為可能。

### 3. 2.4 時代：Point-in-Time 歸檔與回放 (PIT Archive & Replay)
* **問題：** 發現真實資料中，SEC 具備 100% 的精確發布時戳，而 Yahoo 歷史數據完全缺乏發布時間；若混為一談，歷史回測將充滿超前偏差。
* **架構規則：** 建立 `available_at_basis` 與 `replay_eligible_from`；定義嚴格的四種 Replay 結果；確立「`INSUFFICIENT` 是誠實的成功」原則。
* **保留至今的原因：** 讓系統具備機構級的歷史回溯合規能力。

### 4. 2.5 時代：核心證據與註冊表 (Core Evidence & Registry)
* **問題：** 蘋果公司在歷年財報中頻繁更換營收與負債的 XBRL tag，字串比對導致歷史序列斷裂；且抓取失敗被誤判為公司無此業務。
* **架構規則：** 導入 `core_registry.py`，將 Concept 與 Metric 徹底分開；導入封閉的狀態與原因代碼庫，區分 `UNAVAILABLE` 與 `NOT_APPLICABLE`。
* **保留至今的原因：** 解決了跨年度財報標籤漂移的本質問題。

### 5. 2.6–2.27 時代：跨體系泛化與覆蓋率 (Cross-Framework & Coverage)
* **問題：** 遇到非美國公司（IFRS 制）或金融業（銀行、保險業），因缺乏營業利益而導致大量警報誤報。
* **架構規則：** 引入商業模式（`BUSINESS_MODELS`）排除機制與 `NO_OBSERVATIONS` 狀態；支援 IFRS 映射；實施負債語意重命名（`0016_metric_supersession.sql`，歷史觀測保持 `debt`，透過超取代碼指向 `long_term_debt`）。
* **保留至今的原因：** 證明了在不重寫歷史資料的前提下，系統具備語意演進的能力。

### 6. 後期 2.x / 3.x 時代：解讀、身分與准入完整性 (Interpretations, Identity, Admissions)
* **問題：** 修正解析器 Bug 時無法寫入已存在的不可變事實；Replay 時無法確認讀取端使用的是哪版註冊表與程式碼。
* **架構規則：** 引入 `interpretations` 表（知識時間軸）；引入 `registry_state_identity` 與 `resolver_policy_identity`；引入 `admissions` 表（Migration 0019）。
* **保留至今的原因：** 實現了完整的決策可溯源性與決策可重算性。

---

# L. Current Architecture vs Future Work

為防止專案範圍蔓延，必須對現狀與未來劃清界線：

### 1. 已完成之堅固基石 (DONE FOUNDATION)
* ✅ 完整的 `data_contract.py`，零外部依賴。
* ✅ SQLite 歸檔**架構**與 19 個正向遷移（0001–0019），觸發器強制防護 Append-only。**注意：架構已完成，但 repo 內沒有已填充的 corpus（§H.1.1）。**
* ✅ 核心註冊表（`core_registry.py`, `registry_seed.py`），精準映射概念與指標。
* ✅ 准入決策機制（`admissions` 表，`evidence_valuation_boundary.py`）—— **機制已完成；V1 crossing scope 目前只有 `revenue`（§B.5.1）。**
* ✅ 時空回放驅動器（`archive.py`），具備 Replay 決策重算與比對。
* ✅ 逆向估值計算引擎（`st_eva_runner.py`）。
* ✅ Web API 與前端展示基礎（FastAPI + React PWA）。
* ✅ Historical P/E **方法論文件**（`docs/ADR-HISTORICAL-PE-METHODOLOGY.md`, `docs/methodology/CONTRACT-HISTORICAL-PE.md`）已核准凍結。**這是文件成果，不是軟體成果——詳見 §L.2.1。**

### 2. 當前產品工作 (CURRENT PRODUCT WORK)
* 🟡 **Historical P/E Productionization（歷史本益比產品化）：**
  * **角色定位：** Historical P/E 是現有架構的**下一個消費者（Next Consumer）**，絕非重構或推翻既有架構的理由！
  * **當前狀態：** 資料層審計（`docs/ST-EVA-DATA-LAYER-AUDIT.md:181-247`）已揭示現有 Schema 的實際缺口；`docs/ST-EVA-DATA-ADMISSION-RECONCILIATION.md:596-627` 另列出 4 項 genuine schema gaps（evidence class 判別欄位、三值 audit status 與 legal-status note、issuer fiscal calendar、acceptance instant 來源判別欄位）。下一階段工作是謹慎設計資料層擴展，**絕不修改既有架構邊界**。

### 2.1 Historical P/E 目前【尚未】production 化（**必讀**）

> [!CRITICAL]
> **本 repo 目前沒有任何「Historical P/E Contract 所定義的」production pipeline。**
> 不要因為 ADR 與 Contract 寫得完整，就假設它們已被實作。
>
> **但這不等於 repo 完全沒有任何 historical P/E 相關的 production capability。** 既有的 legacy provider-fed `historical_pe_band` 是**另一件事**，兩者不可混為一談：

**既有的 legacy capability（與 Contract 無關，不得與上述 pipeline 混淆）：**

| 項目 | 路徑 | 性質 |
| :--- | :--- | :--- |
| `ValuationInputs.historical_pe_band` | `data_contract.py:1805` | provider-fed 的 historical P/E reference band（dataclass 欄位，預設空 dict） |
| `STEVAEEngine.analyze()` 讀取該 band | `st_eva_runner.py:1378`（`pe_band = inputs.historical_pe_band or {}`） | 既有 reverse valuation 引擎以 band median 作為 reference multiple 之一 |

> 這是 provider 餵入的粗粒度 reference band，**不是** Contract 所定義、由季度來源／證據重建出來的 engine。前者存在，後者尚未實作。

**已經存在的（規格與證據）：**

| 項目 | 路徑 | 性質 |
| :--- | :--- | :--- |
| 方法論 ADR（已核准凍結） | `docs/ADR-HISTORICAL-PE-METHODOLOGY.md` | 規格 |
| 方法論契約 | `docs/methodology/CONTRACT-HISTORICAL-PE.md` | 規格（**其自身第 3 行載明：`Status: DESIGN ARTIFACT — not implementation, not production`**） |
| AAPL / MSFT 驗證證據 | `research/experiments/aapl-historical-pe-poc/` | 研究／驗證產物，非生產資料（§H） |
| 資料層缺口盤點 | `docs/ST-EVA-DATA-LAYER-AUDIT.md`, `docs/ST-EVA-DATA-ADMISSION-RECONCILIATION.md` | 分析 |

**尚未存在（明確清單）：**

* ❌ **production Historical P/E engine**（無 Contract-defined 的獨立計算模組）
* ❌ **`HistoricalPeObservation`**（Contract §C.1 定義的輸出物件；無 production 型別）
* ❌ **quarter-level source / evidence reconstruction**（無季度證據重建）
* ❌ **production runner integration of the new model**（`st_eva_runner.py` 中無 Contract-defined Historical P/E 路徑；既有 `historical_pe_band` 讀取**不算**，見上）
* ❌ **production archive integration**（current evaluator crossing scope 不含本益比類指標。**這不是 migration `0019` 的限制**：`0019_admissions.sql` 建立的是 generic `admissions` persistence schema，可記錄任何 metric 的裁決；限制來自 evaluator 的常數 `V1_CROSSING_METRICS = (METRIC_REVENUE,)`（`evidence_valuation_boundary.py:103`）。見 §B.5.1）
* ❌ **production web surface**（`web/` 中無 Historical P/E endpoint）

**方法論政策 vs. 目前實作——不要混為一談：**

以下規則**已由 ADR 決策凍結，但目前沒有 production code 實作它們**：

| 規則 | ADR 來源 | Production 實作狀態 |
| :--- | :--- | :--- |
| `furnished` vs `filed` 證據類別分離 | D10 | **無**（無欄位、無 validator） |
| `unaudited` 本身不構成拒絕理由 | D11 | **無**（無 `audit_status` 欄位） |
| `16:00 ET` usable-date convention | D3, D12 | **無**（無實作常數） |
| TTM 分量來源混用（Q1–Q3 filed + Q4 furnished） | D14 | **無** |
| Reference Sufficiency threshold / 20-24 requirement / Sampling Frequency / Corporate Action schema / FPI fallback | Contract | **OPEN**（見 Contract 內標示） |

**維護後果：** 若你要實作 Historical P/E，必須**同時**遵守 §L.2.1 的「尚未存在」清單與第 J 章的 STOP 條件——不得為了讓 ADR 的某條規則「生效」而修改 observation hash、放寬 admission、或新增 migration。

### 3. 未來擴展 (FUTURE EXTENSIONS - DO NOT PRE-BUILD)
* ⚪ 全新多因子估值模型。
* ⚪ 跨貨幣自動外匯換算。
* ⚪ 即時經紀商交易串接。
* ⚪ 任何非本益比歷史乘數頻寬。

---

# M. Core File Map

生產檔案權責分工表（明確劃分「擁有什麼」與「絕不能負責什麼」）：

| File / Directory | What it Owns (擁有什麼權責) | What it Must NOT Become Responsible For (絕不能負責什麼) |
| :--- | :--- | :--- |
| `data_contract.py` | 系統資料契約憲法、`Observation` 資料類別、核心常數與枚舉 | 資料庫連線、SQL 查詢、具體資料來源解析、估值算術 |
| `evidence_model.py` | 證據狀態枚舉（`EVIDENCE_STATES`）、原因代碼、`source_fact_id` 計算 | 註冊表語意仲裁、准入決策、數值儲存 |
| `evidence_query.py` | 唯讀證據查詢介面、動態組裝 Evidence 套件、歧義分類 | 寫入資料庫、解決資料衝突、修改 Observation |
| `core_registry.py` | 指標定義、概念註冊、映射關係、商業模式適用性規則 | 抓取網路資料、判定數值優劣、執行估值計算 |
| `registry_seed.py` | 核心註冊表的正式種子資料初始寫入程式 | 執行時動態決策、覆寫自訂映射 |
| `registry_identity.py` | `registry_state_identity` 與 `resolver_policy_identity` 的純粹散列計算 | 資料庫寫入、資料解析、業務決策 |
| `evidence_valuation_boundary.py`| 估值准入邊界（Rules 1–10）、拒絕原因標籤、`BoundaryResult`。**V1 crossing scope 僅 `revenue`**（§B.5.1） | 修改 Observation、執行估值算術、放寬合規標準 |
| `archive.py` | 歸檔抽象介面、Availability 類別、Point-in-Time Replay 驅動器（§B.0.1） | 實作第二套估值引擎、直接讀取存檔 Admission 繞過重算 |
| `sqlite_archive.py` | SQLite 實體存取、遷移執行、`record_observation`、`observation_content_hash` 去重（§H.2） | 財務指標業務邏輯、估值倍數計算 |
| `st_eva_runner.py` | 確定性反向估值核心算術、`ValuationInputs` 處理、快照生成 | 外部網路請求、繞過 Admission 直接讀取資料庫、撰寫 SQL |
| `sec_provider.py` | SEC EDGAR API 抓取、XBRL 標籤解析為 Observation | 估值計算、私自對比 Yahoo 判定勝負 |
| `sec_ingest.py` | 增量申報文件抓取、帳本維護（`held_filings`）、文件去重、**唯一傳入 `FilingRef` 的生產寫入路徑**（§H.2） | 修改歷史已儲存文件、修改註冊表語意 |
| `coverage_semantics.py` | Coverage ledger 語意（collection chain、`scoped_ledger`），被 `evidence_query` 與 `sec_ingest` 共用 | 估值算術、准入裁決 |
| `cross_validation.py` | 跨來源比對（SEC vs Yahoo），產生 `CONFLICTING` 與 `cmp-` 前綴觀測 | 私自挑選獲勝來源、刪除任一方觀測 |
| `fundamental_provider.py` | Yahoo / vendor 端點擷取，產出 provider 專屬適配 Observation | 估值計算、決定來源勝負 |
| `investment_context.py` | 投資脈絡組裝；經 `operation_registry` 命名運算與版本 | 繞過 admission、逕行改寫觀測 |
| `operation_registry.py` | 運算（Operation）名稱與版本的權威登錄，供 derivation 記錄使用 | 執行估值算術、儲存資料 |
| `report_formatter.py` | 評估結果的報表格式化輸出 | 重新計算任何數值、決定採納與否 |
| `knowledge_axis.py` | `knowledge_at` 時間軸的解析（`SourceFact`、`Interpretation`、`KnowledgeAxis`） | 修改原始 Observation、把解讀寫回 `available_at` |
| `archive/migrations/` | 26 張領域資料庫表（+ `schema_migrations`）的正向唯讀遷移指令碼與觸發器 | 任何向下降級操作、非事務性裸語句 |
| `tests/` | 守護架構不變量與回歸一致性的自動化測試套件 | 充當生產依賴、製造臨時生產資料 |
| `web/` | FastAPI REST 路由、非同步任務管理（`job_manager.py`）、序列化（`service_adapter.py`）、React PWA | 實作任何財務或估值邏輯、直接操縱底層資料庫 |
| `data/` | Runtime archive 位置（**目前為空**，§H.1.1） | 存放研究資料或未經驗證的 corpus |
| `history/` | 已封存的正式評估發布報告與 context 快照 | 當作權威輸入跳過 replay 驗證 |
| `reports/` | 已核准的設計／決策報告（35 tracked，**被 `registry_seed.py` 引用**） | 當作可自由改寫的草稿 |
| `docs/` | 架構、ADR、方法論契約與治理文件 | 混入未核准的實作筆記 |
| `docs/methodology/` | 正式核准與凍結之方法論契約（如 Historical P/E Contract，**自身標明為 design artifact**） | 充當動態 Sprint Checklist、混入暫時性實作筆記 |
| `research/` | 大量原始研究憑證、離線驗證腳本、不可變研究封存資料（`/research/` gitignored，控制檔仍 tracked，§H.3） | 生產環境依賴、自動寫入正式資料庫 |
| `experiments/` | 2.x 時代保留之 46 個遺留測試基準 | 引入任何新的未經核准研究實驗 |

### M.1 本表未涵蓋的內容（誠實聲明）

> [!NOTE]
> **這是 core subset，不是 complete inventory。**
> 根目錄另有數十個 `*.py` 模組屬於**單次分析／量測／決策記錄腳本**（例如 `measure_227.py`、`capex_characterisation_234.py`、`debt_definition_232.py`、`selector_tie_break_ambiguity_332.py` 等），它們記錄特定時期的一次性判斷，但**不在生產 import graph 中**。
>
> 判斷某個根目錄 `.py` 是否屬於 core 的準則：**它是否出現在 §F.2.1 的 import 清單中，或是否被 `registry_seed.py` / `archive/migrations/` 引用。**

---

# N. Summary for Future Agents

> **至理名言：**  
> ST-EVA 的複雜度是為了解決真實世界財務申報的混亂性（Restatements, Ambiguities, Form shifts, Legal liabilities）。  
> 每一道邊界都是歷史教訓的結晶。  
> 尊重每一層邊界，守護不可變性，你的修改才能經得起時間的考驗。

