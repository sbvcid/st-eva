# Archive 重建完整性核對與最小修復報告

**日期：** 2026-10-16
**基線：** 實際 HEAD `2293a70`（MU 第三標的驗收），與 `origin/master` 同步、工作目錄乾淨。單一 repository `sbvcid/st-eva`。
**性質：** 契約核對 + 最小修復。範圍限於 MU 驗收中確認的差異（archive 未收錄 vendor 共識 observation，重建 context 缺 17 項共識 metric）。

---

## 1. Archive 的正式恢復與重建契約

現有 archive 提供**兩條互相獨立的恢復路徑**，契約對兩者要求不同：

| 路徑 | 入口 | 保證 |
|---|---|---|
| **讀取 context 快照** | `SQLiteArchive.context_by_id(asset, context_id)`（`context_at` 依 as_of 取最早） | 逐欄位還原當時寫入的整份 context 文件（`document_json`），並以 `document_hash` 做竄改偵測 |
| **從 observations 重建 context** | `archive.replay(store, asset, cutoff, build_document, context_id=…)` | 以 cut­off 之前「可重演（replay-eligible）」的 observation 集，跑**同一條 live pipeline**（`build_context_from_observations`）重建文件，再與指定快照比對 |

**契約條文（三處一致，非推測）：**

- `archive.py` 模組 docstring：replay 必須用 ordinary pipeline，且「Replay must not fill in a missing historical world for the sake of completeness. An INSUFFICIENT result is a successful replay.」
- `_build_context_if_requested` docstring：**「All go to the archive: a snapshot that references facts the archive never saw cannot be replayed.」**
- `_archive_run` docstring：**「Every observation the context used is archived… Archiving a subset would leave the snapshot referencing facts the archive has never seen, and it could not be replayed.」**

因此**契約要求 observations 足以重建 context**：凡是 context 註冊（referenced）的 observation，archive 必須持有。這是本輪判定的核心依據，不是把「快照可讀」誤認為「observations 可完整重建」，恰恰相反：程式碼自己的註解明說子集存檔會導致不可重演。

**replay 判定語意：** `matched` 由 **context 身分**（`context_id`＝知識內容的 content hash，已排除 `generated_at`/`retrieved_at`/`checked_at`/`selected_at` 等 when-we-asked 欄位）加上 admission 一致性決定，**不是** raw byte `document_hash`；`document_hash` 僅供竄改偵測。四種結果：`MATCH` / `DIVERGED` / `NO_SNAPSHOT` / `INSUFFICIENT`，其中 `INSUFFICIENT` 是成功答案而非失敗。

---

## 2. 17 項共識 metric 的來源、期間、單位與身分

以真實已保存產物核對（`history/AAPL_context_20261015.json`、`history/MSFT_context_20261015.json`、`history/mu_acceptance_20261016/stored_context_20261015.json`）：

- 三家 context 的 `observed` 各含 **17 項**共識 metric：`analyst_count`、`low`、`high`、`up/down revisions 7d/30d`、`down_revisions_90d`、`trend_current`、`7d/30d/60d/90d_ago`、`change 7d/30d/60d/90d`。
- 每項的 provenance 齊備：**provider**（`YahooFinanceFundamentals`）、**source_type**（`API_LIVE`）、**unit**（`count` 或 `per_share`）、**currency/currency_basis**、**period_end**（樣本與趨勢序列為 `2028-08-31`，即共識所屬財測期間）、**methodology**（原始欄位路徑，如 `Yahoo quoteSummary earningsTrend trend[period].earningsEstimate.low`）、**observation_id**（如 `obs-consensus-eps-low-001`）。
- 來源缺值的例子被如實保留：`consensus_forward_eps_down_revisions_90d` 在欄位中 value 為 `null`、`provenance_kind=UNAVAILABLE`，**未補零**；其觀測身分標為 `obs-consensus_forward_eps_down_revisions_90d` 且無 `period_end`。
- 計數與區間**不帶貨幣**（`currency=null`、`currency_basis=NOT_APPLICABLE`），與「a range is not a dispersion measure」一致。

**為何這些 metric 隨快照保存、卻未進入 observations 記錄（修正前）：**
`_build_context_if_requested` 從 `data.observations` 選出 `consensus_sample`，以 `extra_observations` 交給 context builder（於是進入文件），但**回傳值僅 `sec_observations`**；`_archive_run` 只歸檔 material + metrics + price/volume history + `context_extra_observations`（＝第二來源）＋ `cmp-` comparable，**獨漏 consensus_sample**。因此快照 reference 了 archive 從未見過的 17 項事實。這正是 §1 契約明文禁止的子集存檔。

---

## 3. Archive observations 的實際覆蓋範圍（真實產物）

以「archive 內已保存的 context 快照」對「archive 內的 observations」逐項比對（definitive self-consistency）：

| Ticker | archive observations | 快照 | 快照 obs refs | 缺漏 |
|---|---|---|---|---|
| AAPL | 92 | Oct-08、Oct-09 | 90 / 90 | **0 / 0** |
| MSFT | 114 | Sep-18 ×2、Oct-09 | 85 / 107 / 112 | **0 / 0 / 0** |
| MU | 106 | Oct-09 | 104 | **0** |
| MU | 106 | Oct-15 ×4（本次 MU 驗收 run） | 121 | **17（各）** |

**解讀：**

- **AAPL/MSFT 的已存檔快照缺漏為 0**：它們建立於共識特性導入之前，context 從未 reference 共識 metric，故 archive 自洽。
- **MU 的 4 個 Oct-15 快照各缺 17 項**：這些 run 建立於共識特性導入之後，context reference 了 17 項共識 observation，但 archive 未收錄 → **契約違反**。
- 缺口是**結構性的**：任何在共識特性導入後建立的 context 都會缺同 17 項。

> 這些持久性 SQLite 檔（`data/archives/*.sqlite`，gitignored、使用者資料）本輪**唯讀檢查、未重建、未刪除、未覆寫**。修正只影響之後新跑的 run。

---

## 4. DIVERGED 的根因：預期限制 vs 契約違反

**MU（Oct-15）：契約違反（已修復）。**
以 archive 副本重放 + 文件 diff 證實：重建文件恰好缺 17 項 `obs-consensus-*`，並因多次同日 run 產生多筆 `ev-price-001` 而重選價格。根因是 §2 的存檔子集化。

**AAPL/MSFT（已存檔的舊 context）：預期限制（不修）。**
其快照缺漏為 0，但重放仍 `DIVERGED`。diff 顯示重建**多出**新的 `glossary/consensus_*` 定義與 `der/consensus_price_gap`、`der:consensus_price_ratio` 等衍生項——即**程式在歸檔之後改動了文件結構**，正是 `DIVERGED` reason 字串明示的 "the code changed since archival, which is legitimate" 情形。**不得為消除此 DIVERGED 而修改程式**，此為誠實報告。

**未誤判：** 快照可讀（context_by_id）與 observations 可重建（replay MATCH）在修正後皆成立；修正前 MU 屬後者失敗、前者成功——兩者本輪分別驗證，未混為一談。亦未把 replay 差異當成 live 計算錯誤（MU live 計算經 16/16 情境獨立重算吻合）。

---

## 5. 本次最小修復

**改動僅 `st_eva_runner.py` 一檔（+51 / −25）：**

1. 新增 helper `consensus_sample_observations(observations)`：選出 `metric in CONSENSUS_EXTRA_METRICS` 的 observation，**live 與 replay 兩條路徑共用**，避免漂移。
2. `_build_context_if_requested` 改用它，並回傳 `sec_observations + consensus_sample`；變數 `cross_source_observations` 更名為 `context_extra_observations`（語意已含共識樣本），`_archive_run` 隨之歸檔。
3. `build_context_from_observations`（replay 路徑）在 `extra_observations` 加入 consensus sample，鏡射 live 路徑，使重建能註冊同一組非材料 observation。

**未做（符合範圍限制）：** 不新建資料庫、不擴建 provider 或 archive 架構、不改觀測數門檻、不改 `evidence_ids` 或其順序/數量（共識平均 `ev-consensus-eps-001` 仍為 material evidence，17 項共識樣本**不進入** `evidence_ids`）、不改估值公式、不動 AAPL v1 凍結產物、未觸碰 `methodology/` 或 RUNBOOK、未新增 ticker 驗收。

---

## 6. 修復後的重建完整性驗證

**新測試 `tests/test_consensus_archive_completeness.py`（13 tests / 43 subtests，全綠），使用三家真實已保存產物：**

| 面向 | 測試 |
|---|---|
| 三家真實 context 皆含 17 項共識 | `test_every_real_context_carries_all_seventeen_consensus_metrics` |
| 來源／期間／單位／身分一致 | `test_each_consensus_metric_carries_source_period_unit_and_identity` |
| 計數/區間不帶貨幣 | `test_a_count_and_a_range_are_not_given_a_currency` |
| 來源缺值保留（不補零） | `test_the_source_absent_revision_count_is_preserved_not_zeroed` |
| observations 覆蓋全部 context reference | `test_the_archive_holds_every_observation_the_context_references` |
| 17 項共識確實入 archive | `test_the_seventeen_consensus_observations_are_archived` |
| 快照保存與還原逐欄一致 | `test_the_context_snapshot_reads_back_unchanged` |
| 重建重現 context（MATCH，同 context_id） | `test_the_replay_reproduces_the_consensus_bearing_context` |
| 重建前後 17 項 provenance 一致 | `test_the_rebuilt_consensus_provenance_matches_the_stored_one` |
| 既有 SEC `evidence_ids` 順序/數量不變 | `test_evidence_ids_keep_their_order_and_never_include_consensus` |
| 無共識樣本的 run 不受影響（回歸） | `test_a_context_without_a_consensus_sample_is_unchanged` |
| helper 只選共識 metric | `ConsensusSampleSelection` ×2 |

端到端結果：以**真實 MU 值**驅動 live→archive→replay，修正前缺 17 項，修正後 **MISSING = 0、diff count = 0、outcome = MATCH、context_id 相同**。

**回歸：** 全套件 **2252 passed / 169 skipped / 488 subtests, 0 failed**；replay/archive 子集 101 passed；consensus/reference/矩陣/context/web 子集 371 passed；前端未受影響（僅後端改動）。

---

## 7. 交付回答

1. **恢復與重建契約？** 兩條路徑：快照逐欄還原（`context_by_id`）＋ 由 observations 以同一 pipeline 重建（`replay`）。契約要求 observations 覆蓋 context 所 reference 的每一項（明文三處）。replay 以 knowledge-identity 判定 MATCH/DIVERGED，`INSUFFICIENT` 為合法答案。
2. **DIVERGED 根因？** MU＝契約違反（17 項共識未存檔，已修）；AAPL/MSFT＝歸檔後程式變更（預期限制，不修，誠實報告）。
3. **各能還原多少共識 metric？** 快照：任何含共識的 context 皆 17/17。observations（現有真實 archive）：MU Oct-15 context 缺 17（0/17）、Oct-9 context 無共識 reference（N/A）、AAPL/MSFT 已存檔 context 無共識 reference（N/A）。修正後新 run：17/17 可重建。
4. **最小修復？** 見 §5：一檔、新增共用 helper、live 與 replay 兩路徑一致，並將共識樣本交由既有 observation/SQLite 機制歸檔。
5. **如何驗證？** 見 §6：真實產物測試 + 端到端 MATCH + 全套件回歸。

**不完整重建不會被誤認為完整結果：** 缺漏以 `DIVERGED`/`INSUFFICIENT` 明確報告；共識缺值以 `UNAVAILABLE` 保留（非零）；共識樣本與 material evidence 在 archive 與 `evidence_ids` 中分別呈現，互不混入。

---

## 8. 驗證與最終 Git 狀態

- 適用測試：新檔 13 passed / 43 subtests；相關子集 101 + 371 passed；全套件 2252 passed / 169 skipped / 488 subtests。
- `git diff --check` 通過；改動僅 `st_eva_runner.py` + 新測試檔 + 本報告。
- 持久性 SQLite 檔（`data/archives/{AAPL,MSFT,MU}.sqlite`）唯讀檢查（`PRAGMA integrity_check` 皆 `ok`），未重建/刪除/覆寫。
- 遠端 CI：push 後以 GitHub API 獨立查證（見結案實際結果）。
