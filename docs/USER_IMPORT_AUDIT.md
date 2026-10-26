# 使用者本機歷史價格資料匯入可行性稽核（唯讀，基線 cbaf1bb）

目標：確認從 GitHub clone 後，使用者能否自行取得有權使用的歷史價格資料並匯入本機 SQLite，讓歷史 P/E 管道正常工作。

## 1. 基線與工作目錄狀態

- HEAD: cbaf1bb (master); remote origin/master 同步。
- 工作目錄清潔（僅未追蹤 REVIEW-2ND-PHASE.md）；本機原始資料（包含已排除的 Yahoo 衍生價格檔案）完整保留於原路徑。
- 未修改任何程式碼、資料庫格式、測試、估值公式或 Git 歷史。

## 2. SQLite 歷史價格資料架構（已驗證，非推測）

以 `data/archives/SOFI.sqlite` 為範例（本機副本存在，非 Git 追蹤）：

- 表格數：41 個（`sqlite_master` 查詢）。
- 關鍵價格相關表：`observations`（112 列）、`observation_sources`（118 列）、`assets`（1 列：SOFI）、`sources`（1 列：Yahoo Finance URL）、`context_snapshots`（2 列）、`derived_values`（38 列）。
- `observations.schema` 欄位：`observation_id`, `asset_id`, `metric`, `provider`, `source_type`, `source_url`, `value_json`, `unit`, `currency`, `currency_basis`, `as_of`, `available_at`, `status`, `content_hash`, `raw_json`, 等 51 個欄位。
- 資料來源明確標示：`sources.source_url` = `https://query1.finance.yahoo.com/v8/finance/chart/SOFI?range=3mo&interval=1d`；`provider` = `YahooFinance+YahooFinanceFundamentals`；`API_LIVE`。
- 無簡單「價格序列 + 日期」表；價格觀測是透過多欄位 JSON (`value_json`) 與來源追溯 (`lineage_id` → `observation_lineage`) 儲存，並與 `context_snapshots`、`admissions`、`interpretations` 做關聯。

結論：SQLite 資料庫不是簡單的 CSV 匯入格式；直接複製完整檔案（同一個 `SOFI.sqlite`）才是已驗證的重播機制。若使用者想「匯入」自己的價格資料，必須符合這個架構（或修改程式路徑）。

## 3. 程式碼匯入介面實際檢查（已有證據，非推測）

檢查 `historical_pe_adapter.py`、`sqlite_archive.py`、`st_eva_runner.py`、`tests/test_replay_determinism_sofi.py`：

- `fetch_yahoo_daily_prices()`（主來源）：從 Yahoo Finance v8 API 下載；輸出為標準化 JSON + SQLite 寫入（`save_standardized_prices`）。**沒有參數接受外部檔案路徑或外部 JSON 作為輸入替代。**
- `read_sqlite_price_observations()`（次要來源）：從 `data/archives/SOFI.sqlite` 讀取；路徑固定；無通用「讀取任意 SQLite」介面（雖然 `sqlite_archive.py` 可能支援，但非公開文件化的使用者介面）。
- `sqlite_archive.py`：提供 `SQLiteArchive` 類別，可操作 SQLite，但沒有「匯入外部價格 CSV」的方法；其功能主要是觀察寫入、讀取、驗證。
- `acquire_standardized_prices()`：將 Yahoo 下載結果寫入 `data/historical_pe/<ticker>/daily_prices.json` 與 `data/st-eva.sqlite`（若存在）。**沒有「從使用者提供的檔案讀取」分支。**
- `tests/test_replay_determinism_sofi.py`：直接複製 `data/archives/SOFI.sqlite` 到 `tempfile.mkdtemp()`；證明重播依賴完整 SQLite 檔案，而非單一價格欄位。
- `docs/USAGE.md`：提到 `python st_eva_runner.py AAPL --mode live --context context.json --archive data/st-eva.sqlite`；提到 `Live data, no persistent result snapshot`；**未提及從外部檔案匯入價格序列的命令或選項。**

結論：**目前沒有完整的、已文件化的「使用者自行提供價格資料匯入」介面。** 只有兩種已驗證路徑：
(A) 本機已有完整 `SOFI.sqlite`（或其他已追蹤的歷史價格 JSON）→ 直接複製或讓程式讀取；
(B) 從 Yahoo Finance 即時下載（需獨立授權確認，且不為已追蹤的固定快照）。

## 4. 乾淨 clone 對歷史 P/E 管道的實際影響（已測試）

測試結果（基線 `cbaf1bb`，本機原始副本存在，但 Git 追蹤已排除）：

- 重播測試 (`test_replay_determinism_sofi.py`): 3 skipped（缺檔，正確跳過；非假性通過）。
- 適配器完整測試（`-k 'not live'`，本機檔案存在）: 49 passed。
- 適配器完整測試（清潔模擬，4 個 SOFI 檔案暫時移動）：38 passed / 11 skipped（`TestSofiManifestIntegrity` + `TestSofiHistoricalPePipeline`；跳過原因已標註 `skipUnless`，非假性通過）。
- 隔離測試 (`test_archive_isolation.py`): 6 passed。

功能限制（已由程式路徑確認）：
- `historical_pe_adapter.py` 的 `load_issuer_historical_pe()` 主要從 `data/historical_pe/<ticker>/` 讀取 JSON（已追蹤的 SEC 證據 + 價格資料）。若價格 JSON 缺失，管道會在價格解析階段失敗（已在第 5 階段驗證，非推測）。
- `st_eva_runner.py` 的 `build_context_from_observations()` 在沒有價格觀察時無法建立完整估值上下文。

沒有「自動回退到僅 SEC 證據」的機制：SEC 證據（`filing_acceptance_evidence.json` 等）可驗證財務事實，但不包含市場價格序列，因此不能替代歷史 P/E 的價格輸入。

## 5. 最小可行匯入方案（未實作，僅方案）

若使用者想從 GitHub clone 後重現完整 SOFI（或其他）歷史 P/E，且已獨立取得授權的價格序列，最小路徑為：

1. **提供完整 SQLite archive**（推薦，與重播測試相容）：將本機 `data/archives/SOFI.sqlite`（或其授權副本）複製到 `data/archives/SOFI.sqlite`（已在本機備份）。無需修改程式；重播測試直接通過；適配器次要來源可讀取。
2. **提供 `data/historical_pe/<ticker>/daily_prices.json` + `manifest.json` + `prices_manifest.json`**（若使用者已有與 Yahoo 格式相容的標準化價格序列，且已確認授權）：複製到對應路徑。適配器主路徑（JSON 讀取）可正常運作；但須確保格式與 `historical_pe_adapter.py` 期望的一致（包含 `as_of`, `source_url`, `price_count`, `coverage` 等）。缺乏受支援的通用匯入介面，需手動對應格式。
3. **從 Yahoo Finance 重新下載**（若使用者已有獨立授權確認）：使用 `historical_pe_adapter.py` 的 `fetch_yahoo_daily_prices()` 重新取得；輸出寫入 `data/historical_pe/SOFI/`。但這需要使用者自己管理授權，而非「從 GitHub 取得」解決。

**重要限制（已說明，不被低估）：**
- 沒有 CSV/Excel/DB 匯入功能；沒有 `import_prices.py`；沒有 `--input-file` CLI 選項。
- 沒有「從任意 SQLite 讀取並重新映射到 SOFI 觀察架構」的通用函數；`sqlite_archive.py` 的介面是特定於現有架構的。
- 沽體價格序列的格式（`chart.result` 結構、分割事件、貨幣、新台幣基準）與 Yahoo v8 原始輸出直接相關；若使用者使用不同提供者（例如 Bloomberg、Refinitiv），格式不匹配，需自訂轉換，超出現有支援範圍。

## 6. 相關文件與證據連結

- 程式路徑：`historical_pe_adapter.py`（第 418 行 SQLite 次要來源、第 69/128 行 Yahoo 下載函數作為主來源）。
- 測試路徑：`tests/test_replay_determinism_sofi.py`（第 45 行 `SOFI_ARCHIVE`；第 82 行 `SkipTest`）。
- 測試證據：完整 49/0 通過（SEC 證據路徑）；11 跳過（價格缺失，已標註）；3 重播跳過。
- 文件：`docs/DATA-AVAILABILITY.md`（第 8 篇）；`docs/USAGE.md`（無價格匯入說明）；`docs/THIRD_PARTY_DATA_REGISTRATION.md`（新資料登記規則）。
- 本機備份：`data/archives/SOFI.sqlite`（2,046,304 B）；`data/historical_pe/SOFI/daily_prices.json`（56,786 B）等仍存在。

## 7. 結論

使用者**不能**僅透過 `git clone` + 標準安裝步驟就直接使用完整歷史 P/E 管道（對所有 5 個 issuer）。用於重現測試的完整路徑是：
- 取得獨立授權的完整 SOFI SQLite archive → 複製到 `data/archives/SOFI.sqlite` → 重播測試通過；或
- 取得獨立授權的價格序列 → 手動對應格式放入 `data/historical_pe/<ticker>/` → 適配器主路徑可運作（需驗證格式匹配）；或
- 使用 `fetch_yahoo_daily_prices()` 且自行確認 Yahoo 服務條款允許（C-1 尚未確認，非建議）。

沒有「簡單匯入」選項；沒有合成替代；測試已清楚標示缺乏情境。這是已知功能限制（非缺陷修復對象），已在 `DATA-AVAILABILITY.md` 記錄。
