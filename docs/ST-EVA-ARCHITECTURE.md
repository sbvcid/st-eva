# ST-EVA Architecture Constitution & Deep-Dive

**Repository:** `sbvcid/st-eva`  
**Document Status:** CANONICAL ARCHITECTURE CONSTITUTION  
**Authority:** Highest Architectural Authority over `sbvcid/st-eva` Implementation  
**Intended Audience:** All human engineers, system architects, and coding agents before modifying production code, schemas, or contracts.

---

## Executive Warning to Any Modifying Agent

> [!CRITICAL]
> **READ BEFORE TOUCHING ANY CODE OR SCHEMA IN ST-EVA:**
> ST-EVA is **not** a typical loose financial reporting script. It is an append-only, deterministic, point-in-time reverse valuation engine governed by strict mathematical and provenance invariants.
> 
> Boundaries that look redundant or verbose (e.g. separating a Source Fact from an Observation, separating an Observation from an Admission, separating Availability Time from Retrieval Time) were introduced to eliminate specific, historically verified data corruptions.
> 
> **Never collapse layers to make code shorter. Never invent synthetic data to avoid `UNAVAILABLE`. Never change a hash function to suit a downstream consumer.**

---

# A. ST-EVA 是什麼 (What ST-EVA Is)

### 1. 精確定義 (Precise Definition)
**ST-EVA 是一個「反向估值與市場隱含預期引擎」（Reverse Valuation & Market-Implied Expectations Engine）。**  
它接收公開市場的即時報價與明確指定的估值參考倍數（Valuation Reference Multiple），以完全確定性（Deterministic）、可審計（Auditable）且可回溯重現（Replayable）的純粹計算，反向推導出該股價所「隱含」的底層基本面與成長假設。

### 2. 反向估值（Reverse Valuation）的真正研究對象
在傳統財務分析中，分析師研究的對象是「資產（Asset）」——試圖透過預測資產未來的獲利來計算目標價。  
**ST-EVA 的研究對象不是資產，而是「假設（Assumptions）」。**  
核心提問永遠只有一個：  
> **「目前價格反映了什麼假設？」(What assumptions is the current price reflecting?)**

報價本身是市場所有參與者集體投票後生成的「壓縮共識裁決（Compressed Verdict）」。市場在某個價格下，已隱含了對該標的未來獲利、增長率或利潤率的預期。ST-EVA 的任務不是評判價格對不對，而是把這份被壓縮在價格裡的預期**完全解壓縮並顯性化**。

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
5. **LLM 永遠不參與估值算術：** 語言模型（`llm_interpreter.py`）僅作為對已驗證 JSON 結構的文字解讀介面，嚴禁執行任何財務計算。

---

# B. Core Architecture

完整資料流向（Data Flow）嚴格保持單向流動：

```text
Raw Source (SEC EDGAR SGML, Yahoo Finance API, Exchange feeds)
  ↓
Ingest (sec_ingest.py, fundamental_provider.py)
  ↓
Observation (data_contract.py: Observation)
  ↓
Evidence (evidence_model.py, evidence_query.py)
  ↓
Admission (evidence_valuation_boundary.py: admit)
  ↓
Engine (st_eva_runner.py: MarketImpliedAssumptionsEngine)
  ↓
Derived / Valuation Result (ValuationResult, DerivedValue)
  ↓
Snapshot (SnapshotManager, context.json, SQLite context_snapshots)
  ↓
Replay (archive.py: replay, SQLiteArchive)
  ↓
Web / PWA (web/app.py, web/service_adapter.py, React PWA)
```

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
* **擁有資料：** `observation_id`, `metric`, `value`, `unit`, `currency`, `period_start`, `period_end`, `as_of`, `available_at`, `accession`, `provider`, `basis`。
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
* **擁有資料：** `(asset_id, decided_at, metric)`、`admitted` (布林)、`contract_id`、`source_fact_id`、`registry_state_identity`、`resolver_policy_identity`、拒絕標籤（`Refusal`）與被取代的歷史版本。
* **不能擁有：** 原始事實的重新定義；嚴禁直接複製儲存價格或財報數值（避免形成雙重真理來源）。
* **輸入：** Replay-eligible 的 `Observation` 集合、當前資產價格觀測、Core Registry 規則。
* **輸出：** `BoundaryResult`、`ValuationInputs` 欄位注入、寫入 `admissions` 表。
* **可依賴它的下游：** `Engine`（僅接收通過 Admission 的數值）、`Replay`（用於對比決策一致性）。
* **禁止反向污染：** 嚴禁將 Admission 結果寫回 Observation 作為「Role」欄位；嚴禁在 Replay 時把已儲存的 Admission 當成輸入。

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
* **代表意義：** 時空回溯與歷史一致性驗證驅動器。
* **擁有資料：** 回溯比對邏輯、結果狀態（`MATCH`, `DIVERGED`, `NO_SNAPSHOT`, `INSUFFICIENT`）、差異比對分析。
* **不能擁有：** 第二套估值計算邏輯（必須注入生產線相同代碼）。
* **輸入：** 指定的 `asset`、指定歷史時點 `as_of`、歸檔儲存庫 `ArchiveStore`。
* **輸出：** `ReplayResult`。
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
| **Evidence** | 面向讀取的結構化證據包，完整包含事實與其時空有效性解釋 | 原始事實的替代品；決策獲勝者裁決 | Evidence Layer (`evidence_query.py`) |
| **Evidence State** | 指標當前狀態的結構化解釋（缺失原因、爭議、陳舊） | 引擎是否准入（Admission）的裁決 | Evidence Layer (`evidence_model.py`) |
| **Admission** | 引擎在特定時點、註冊表與政策下，對某事實的採納或拒絕判定 | 原始事實本身；事實的內在角色（Role） | Valuation Boundary (`evidence_valuation_boundary.py`) |
| **Interpretation** | ST-EVA 對某一既有源頭事實的後續理解/解析修正（在知識時間軸上） | 原始事實的改寫；申報時間軸（Available At）的變更 | Knowledge Layer (`archive/migrations/0017`, `knowledge_axis.py`) |
| **Derived** | 由確定性算術與明確指認的輸入觀測所計算出的純粹推導值 | 外部觀察到的事實；包含人為判斷的估計 | Valuation Engine (`st_eva_runner.py`) |
| **Snapshot** | 某一執行時點的完整知識狀態與計算結果的不可變封存文件 | 預測；未來的保證；規範性政策 | Archive Subsystem (`archive.py`, `sqlite_archive.py`) |
| **Registry** | 指標語意、來源標籤定義、映射關係與適用性的權威仲裁者 | 經驗觀測事實；資料品質打分者；衝突解決者 | Core Registry (`core_registry.py`, `registry_seed.py`) |
| **Archive** | 實體儲存、版本遷移、完整性校驗與 Point-in-Time 回溯基底 | 財務評估方法論；業務決策制定者 | Persistence Layer (`sqlite_archive.py`, `archive/migrations`) |
| **Research Artifact** | 探索性研究、POC 驗證、離線比對腳本與暫存測試數據 | 規範性生產環境資料；權威觀測依據 | Research Space (`research/`, `experiments/`) |

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
* **Rule:** 所有推導數值必須儲存其運算邏輯與所有輸入觀測 ID（`derived_values.depends_on_json`），並保證能隨時利用純 Python 重算（`data_contract.py:88-93`, `sqlite_archive.py:1260-1280`）。
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
  * **Repository 實例（Migration 0019）：** 在 ST-EVA 3.32 中，曾有人提議在 `Observation` 上增加一個 `role` 欄位（表示它是 ENGINE_INPUT 還是 EVIDENCE_ONLY）。測量結果顯示：這樣做會毀滅 291,134 筆歷史觀測的雜湊唯一性，或者在時點變更時被去重機制靜默丟棄。因此，ST-EVA 堅定建立了獨立的 `admissions` 表。
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
* **Furnished vs Filed 證據 (ADR Decision 10–14):**  
  8-K Item 2.02 的新聞稿附件（EX-99.1）在法律上是「Furnished」（提供）而非「Filed」（申報），不承擔 Section 18 法定虛偽陳述責任。但微軟與蘋果在第四季往往僅在此處提供離散季度 EPS。ST-EVA 既不因為它是 Furnished 而在准入中歧視拒絕，也不抹殺它的法律屬性——將法律免責聲明保留在血統中，並在回溯時嚴格以 16:00 ET 截止規則確定其 Point-in-Time 可用性。

---

# F. Dependency Direction

依據實際 Python AST 語法樹解析，ST-EVA 的生產代碼依賴流向嚴格維持單向階層：

```text
       Provider / Ingest (sec_provider.py, sec_ingest.py)
              ↓
       Data Contract (data_contract.py)  [ZERO ST-EVA IMPORTS]
              ↓
       Evidence / Registry (evidence_model.py, core_registry.py, registry_seed.py)
              ↓
       Admission (evidence_valuation_boundary.py)
              ↓
       Engine (st_eva_runner.py)
              ↓
       Archive / Replay (sqlite_archive.py, archive.py, registry_identity.py)
              ↓
       Web Services / API (web/service_adapter.py, web/app.py)
```

### AST 實證依賴清單 (Verified Import Evidence)
* `data_contract.py`: **`[]`**（絕對純粹，零內部依賴）。
* `evidence_model.py`: `['data_contract']`。
* `core_registry.py`: `['data_contract']`。
* `registry_seed.py`: `['core_registry']`。
* `sec_provider.py`: `['data_contract']`。
* `sec_ingest.py`: `['archive', 'core_registry', 'data_contract', 'evidence_model', 'sec_provider']`。
* `evidence_valuation_boundary.py`: `['archive', 'core_registry', 'data_contract', 'evidence_query']`。
* `st_eva_runner.py`: `['archive', 'data_contract', 'evidence_valuation_boundary', 'registry_identity', 'sec_provider', 'sqlite_archive']`。
* `archive.py`: `['data_contract', 'evidence_valuation_boundary', 'registry_identity']`（動態注入於 Replay 比對）。
* `web/service_adapter.py`: `['archive', 'core_registry', 'registry_seed', 'sqlite_archive', 'st_eva_runner', 'web.schemas']`。
* `web/app.py`: `['web.job_manager', 'web.schemas']`。

### 危險反向依賴禁止守則 (Forbidden Reverse Dependencies)
1. **Core 不得依賴 SQLite 實作細節：** `data_contract` 與 `st_eva_runner` 不得包含 `import sqlite3` 或編寫 SQL 語句。儲存實作可以切換為 PostgreSQL 或 Parquet，核心契約不得產生感知。
2. **Archive 不得包含第二套 Engine：** `archive.py` 在執行 Replay 時，必須透過注入的 `build_document` 呼叫生產環境的統一管線，嚴禁在歸檔層自行實現一套簡化版的估值計算。
3. **Web 不得實作任何估值邏輯：** `web/` 的職責是 DTO 序列化、HTTP 傳輸與非同步協調。所有計算必須委派給 `service_adapter.py`，嚴禁在 FastAPI 路由中出現任何財務公式。
4. **Research 腳本嚴禁成為生產依賴：** `research/` 與 `experiments/` 內的任何模組禁止被根目錄的生產代碼引入。
5. **Registry 語意不得從來源標籤逆向猜測：** 嚴禁在沒有映射表的情況下，直接用正則表達式把 XBRL tag 轉成指標名稱。

---

# G. Identity Model

ST-EVA 建立了一套多層次且互不污染的身分系統（Identity System）：

```text
┌─────────────────────────────────────────────────────────────┐
│ 1. Document / Content Identity (content_hash)              │
│    SHA-256 of raw bytes in source_documents                 │
├─────────────────────────────────────────────────────────────┤
│ 2. Source-Fact Identity (source_fact_id)                   │
│    (source, document, taxonomy, concept, period, context)   │
├─────────────────────────────────────────────────────────────┤
│ 3. Observation Identity (observation_content_hash)         │
│    (observation_id, metric, provider, concept, value,      │
│     unit, currency, periods, as_of, available_at, accn)     │
├─────────────────────────────────────────────────────────────┤
│ 4. Lineage Identity (lineage_id)                           │
│    (asset, metric, concept, period)                         │
├─────────────────────────────────────────────────────────────┤
│ 5. Registry State Identity (rgs:...)                        │
│    Canonical digest of all semantic mapping rows in DB      │
├─────────────────────────────────────────────────────────────┤
│ 6. Resolver Policy Identity (pol:...)                       │
│    Whole-file SHA-256 digest of resolver Python source files│
├─────────────────────────────────────────────────────────────┤
│ 7. Admission Identity (admissions.identity)                 │
│    (asset_id, decided_at, metric, contract_id, rgs, pol...) │
├─────────────────────────────────────────────────────────────┤
│ 8. Snapshot / Document Identity (document_hash)             │
│    Canonical JSON hash of context.json                      │
└─────────────────────────────────────────────────────────────┘
```

### 身分系統規格表

| Identity System | What it Identifies | Inputs Defining It | Why It Exists | What Must NOT Be Included |
| :--- | :--- | :--- | :--- | :--- |
| **Document Identity** | 實體儲存檔案內容 | 原始位元組字節流 | 內容尋址（Content-addressed storage）與重複下載防護 | 檔案名稱、下載時間、URL |
| **Source-Fact Identity** | 單一來源文件內的原始事實 | `source_id`, `document_ref`, `taxonomy`, `concept`, `period_start`, `period_end`, `context` | 標記「同一個來源文件中的同一個宣告點」；去重唯一合法依據 | 數值大小、跨來源比較、評價狀態 |
| **Observation Identity** | 一個完整的觀測事實單元 | 11 個核心屬性（見下方專題） | 確定觀測的不可變唯一性；區分重編事實 | `basis_json`, `raw_json`, `status`, `role` |
| **Lineage Identity** | 時間序列的血統追蹤 | `asset`, `metric`, `concept`, `period` | 串聯跨期間的時間序列演變 | 具體數值、抓取時點 |
| **Registry State Identity** | 註冊表資料狀態 | 資料庫中所有語意映射列的正規化摘要 | 識別「是哪一版註冊表資料做出的判定」 | 實體重複列、無效空白字元 |
| **Resolver Policy Identity** | 解析器程式碼狀態 | 解析器核心原始碼模組的全檔 SHA-256 | 識別「是哪一版 Python 程式碼做出的判定」 | 執行時環境變數、暫存屬性 |
| **Admission Identity** | 某一准入決策 | `(asset, decided_at, metric, contract_id, rgs, pol)` | 確保相同情境下的決策可讀且唯一；支援 supersedes 鏈條 | 價格數值、財報數值（避免資料雙重儲存） |
| **Snapshot Identity** | 某一運行的完整文件 | 完整 Context JSON 的正規化鍵值對 | 防篡改驗證；Replay 對比基準 | 非確定性時間戳（若非生成時點） |

### §J 核心教訓：`observation_content_hash()` 的神聖邊界
在 ST-EVA 歷史進程中，§J 階段發現了一個關鍵架構事實：
`sqlite_archive.py:112-135` 定義的 `observation_content_hash()` 代表的是**來源事實身分（Source-Fact Identity）**。它的散列前像（Preimage）包含且僅包含 11 個欄位：
```python
payload = {
    "observation_id": observation.observation_id,
    "metric": observation.metric,
    "provider": observation.provider,
    "concept": _concept_of(observation),
    "value": observation.value,
    "unit": observation.unit,
    "currency": observation.currency,
    "period_start": observation.period_start,
    "period_end": observation.period_end,
    "as_of": observation.as_of,
    "available_at": observation.available_at,
    "accession": _accession_of(observation),
}
```
**`basis_json` 與 `raw_json` 明確不在雜湊前像中。**  
這意味著：如果將兩個對同一客觀事實但帶有不同 Evidence 分類元數據（例如 `evidence_class="furnished"` 與 `evidence_class="filed"`）的觀測寫入資料庫，`record_observation` 會計算出完全相同的 Hash，並透過 `SELECT observation_id FROM observations WHERE content_hash = ?` 判定為重複資料，進而**靜默丟棄第二個分類**！

> [!WARNING]
> **千萬不要為了迎合下游需求而修改 `observation_content_hash`：**  
> 未來的開發者不可為了讓分類元數據生效，就輕率地把 `evidence_class` 或 `basis_json` 加進 Observation 的 Hash 裡！  
> Observation 記錄的是「來源發布了什麼事實」，而 `evidence_class` 是「證據層如何歸類它」。  
> 正確的邊界處理解決方案應當是讓分類由 Evidence / Admission 或未來的正式模式承載，絕對不能藉由混淆 Observation 身分來解決讀取層問題。

---

# H. Persistence Model

ST-EVA 儲存庫各目錄具有嚴格的語意邊界，絕非單純的工作區分類：

```text
st-eva/
├── archive/        -> 唯讀正向遷移 SQL (0001-0019)；系統 Schema 憲法
├── data/           -> 生產執行期 SQLite 資料庫 (data/archives/*.sqlite)
├── history/        -> 正式評估發布報告與封存之生產快照
├── research/       -> 探索性研究、大量未清洗原始憑證、不可變封存實驗 (Gitignored)
└── experiments/    -> 2.x 時代遺留之凍結實驗基準 (46 legacy tracked files)
```

### 語意區分 (Semantic Distinctions)
1. **Research Artifact $\neq$ Canonical Production Observation:**  
   在 `research/experiments/aapl-historical-pe-poc/` 內包含超過 1 GB 的 SEC 原始 SGML 文件與過渡 JSON。這些是研究材料，是為了證明方法論可行性而存在的。它們**不是**生產環境的正規觀測。只有當正式的 Ingestor 解析並寫入 `data/archives/` 時，它才具備生產效力。
2. **Archive Schema $\neq$ Research Corpus:**  
   研究目錄中可能存在研究員自己建立的臨時 SQLite 資料庫，那些資料庫是探索性的；`archive/migrations/` 定義的 26 張表才是正式資料庫綱要。
3. **嚴禁將研究 SQLite 自動提升為生產狀態：**  
   任何填滿數據的研究 SQLite，都包含特定實驗的簡化假設，絕不能未經驗證便直接複製為生產資料庫。

---

# I. Replay Philosophy

Replay 在 ST-EVA 中是**一等架構公民（First-Class Architectural Property）**，而非附加的輔助工具。

### 1. 回放執行流 (Replay Workflow)
```text
Archive 提供歷史時點 T 之前的觀測集合 (observations_for(asset, as_of))
        ↓
執行完全相同的生產環境管線 (build_document)
        ↓
動態重新計算准入決策 (admit()) 並與存檔之 admissions 記錄對比
        ↓
動態重新計算估值引擎與 Context
        ↓
與原先封存的 Snapshot 進行比對，產出 ReplayResult
```

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

### 12 條強制維護通訊協定 (Mandatory Maintenance Checklist)
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
* ✅ SQLite 歸檔庫與 19 個正向遷移（0001–0019），觸發器強制防護 Append-only。
* ✅ 核心註冊表（`core_registry.py`, `registry_seed.py`），精準映射概念與指標。
* ✅ 准入決策機制（`admissions` 表，`evidence_valuation_boundary.py`）。
* ✅ 時空回放驅動器（`archive.py`），具備 Replay 決策重算與比對。
* ✅ 逆向估值計算引擎（`st_eva_runner.py`）。
* ✅ Web API 與前端展示基礎（FastAPI + React PWA）。
* ✅ Historical P/E 方法論 ADR 與契約（`docs/ADR-HISTORICAL-PE-METHODOLOGY.md`, `docs/methodology/CONTRACT-HISTORICAL-PE.md`）已核准凍結。

### 2. 當前產品工作 (CURRENT PRODUCT WORK)
* 🟡 **Historical P/E Productionization（歷史本益比產品化）：**
  * **角色定位：** Historical P/E 是現有架構的**下一個消費者（Next Consumer）**，絕非重構或推翻既有架構的理由！
  * **當前狀態：** 資料層審計（`docs/ST-EVA-DATA-LAYER-AUDIT.md`）已揭示現有 Schema 缺乏 3 個關鍵欄位；§J 測試已證實 `content_hash` 無法吸收元數據。下階段工作是謹慎設計資料層擴展，絕不修改既有架構邊界。

### 3. 未來擴展 (FUTURE EXTENSIONS - DO NOT PRE-BUILD)
* ⚪ 全新多因子估值模型。
* ⚪ 跨貨幣自動外匯換算。
* ⚪ 即時經紀商交易串接。
* ⚪ 任何非本益比歷史乘數頻寬。

---

# M. Concrete File Map

生產檔案權責分工表（明確劃分「擁有什麼」與「絕不能負責什麼」）：

| File / Directory | What it Owns (擁有什麼權責) | What it Must NOT Become Responsible For (絕不能負責什麼) |
| :--- | :--- | :--- |
| `data_contract.py` | 系統資料契約憲法、`Observation` 資料類別、核心常數與枚舉 | 資料庫連線、SQL 查詢、具體資料來源解析、估值算術 |
| `evidence_model.py` | 證據狀態枚舉（`EVIDENCE_STATES`）、原因代碼、`source_fact_id` 計算 | 註冊表語意仲裁、准入決策、數值儲存 |
| `evidence_query.py` | 唯讀證據查詢介面、動態組裝 Evidence 套件、歧義分類 | 寫入資料庫、解決資料衝突、修改 Observation |
| `core_registry.py` | 指標定義、概念註冊、映射關係、商業模式適用性規則 | 抓取網路資料、判定數值優劣、執行估值計算 |
| `registry_seed.py` | 核心註冊表的正式種子資料初始寫入程式 | 執行時動態決策、覆寫自訂映射 |
| `registry_identity.py` | `registry_state_identity` 與 `resolver_policy_identity` 的純粹散列計算 | 資料庫寫入、資料解析、業務決策 |
| `evidence_valuation_boundary.py`| 估值准入邊界（Rules 1–10）、拒絕原因標籤、`BoundaryResult` | 修改 Observation、執行估值算術、放寬合規標準 |
| `archive.py` | 歸檔抽象介面、Availability 類別、Point-in-Time Replay 驅動器 | 實作第二套估值引擎、直接讀取存檔 Admission 繞過重算 |
| `sqlite_archive.py` | SQLite 實體存取、遷移執行、`record_observation`、去重 | 財務指標業務邏輯、估值倍數計算 |
| `st_eva_runner.py` | 確定性反向估值核心算術、`ValuationInputs` 處理、快照生成 | 外部網路請求、繞過 Admission 直接讀取資料庫 |
| `sec_provider.py` | SEC EDGAR API 抓取、XBRL 標籤解析為 Observation | 估值計算、私自對比 Yahoo 判定勝負 |
| `sec_ingest.py` | 增量申報文件抓取、帳本維護（`held_filings`）、文件去重 | 修改歷史已儲存文件、修改註冊表語意 |
| `archive/migrations/` | 26 張資料庫表的正向唯讀遷移指令碼與觸發器 | 任何向下降級操作、非事務性裸語句 |
| `tests/` | 守護所有架構不變量與回歸一致性的自動化測試套件 | 充當生產依賴、製造臨時生產資料 |
| `web/` | FastAPI REST 路由、非同步任務管理、React PWA 前端介面 | 實作任何財務或估值邏輯、直接操縱底層資料庫 |
| `docs/methodology/` | 正式核准與凍結之方法論契約（如 Historical P/E Contract） | 充當動態 Sprint Checklist、混入暫時性實作筆記 |
| `research/` | 大量原始研究憑證、離線驗證腳本、不可變研究封存資料 | 生產環境依賴、自動寫入正式資料庫 |
| `experiments/` | 2.x 時代保留之 46 個遺留測試基準 | 引入任何新的未經核准研究實驗 |

---

# N. Summary for Future Agents

> **至理名言：**  
> ST-EVA 的複雜度是為了解決真實世界財務申報的混亂性（Restatements, Ambiguities, Form shifts, Legal liabilities）。  
> 每一道邊界都是歷史教訓的結晶。  
> 尊重每一層邊界，守護不可變性，你的修改才能經得起時間的考驗。
