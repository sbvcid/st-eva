# 多公司個股研究流程第一版驗收報告

**驗收日期：** 2026-10-15
**基線核對：** 實際 HEAD `37262ae`（= AAPL v1 凍結版 `9ca6999` 之後的 MSFT 跨標的驗證 commit），與 origin/master 同步、working tree 乾淨。未假定各 repository commit 相同。
**性質：** 整合驗收。除非發現實際使用障礙，不改程式；唯一發現的障礙以最小修改處理（見 §3）。

---

## 1. 使用路徑盤點（§一）

使用者從股票代號進入研究流程的實際路徑有三條：

| 路徑 | 入口 | 產出 | 狀態 |
|---|---|---|---|
| **CLI** | `python st_eva_runner.py <TICKER> --mode live --historical-pe --historical-pfcf [--context …] [--dossier …]` | 執行快照、context、dossier、可讀報告、`--json` | 完整（AAPL/MSFT live 已驗收並凍結） |
| **Web API** | `POST /api/analyze {"ticker": …}` → job → result DTO | `ValuationSummary`、`ReverseRequirementsReportDTO`、production summaries | **發現障礙並已修補**（見 §3） |
| **Web UI** | 前端輸入代號 → ProgressStepper → ResultCards + ReverseRequirementsMatrix + EvidenceAccordion | 主要畫面 + 明細層 | 隨 API 修補而完整 |

手動步驟：CLI 需要使用者自行附加旗標（`--historical-pe --historical-pfcf`，已寫入 USAGE.md）；web 路徑無需旗標。除此之外無手動斷點。

## 2. 兩家公司的流程驗收（§二）

同一套流程分別在 AAPL 與 MSFT 上執行（live 執行快照已凍結於 repo；web 路徑以 regression-mode 端到端測試驗收，同機連續執行兩家公司）：

| 驗收項 | AAPL | MSFT |
|---|---|---|
| 市場價格 + 日期 | 342.96 USD，2026-10-14 | 539.055 USD，2026-10-15 |
| 歷史 P/E | 36/36 觀測，USABLE，2018-01-02→2026-07-31，median 28.4456 | 24/27 觀測，USABLE，2021-07-28→2026-07-30，median 33.1959 |
| 歷史 P/FCF | 35/36 觀測，USABLE，2018-02-02→2026-07-31，median 25.3440 | 23/27 觀測，USABLE，2021-07-30→2026-07-30，median 41.5783 |
| 共識期間（來源宣告） | +1y，end 2027-09-30 | +1y，end 2028-06-30 |
| 共識樣本 | 40 位分析師，[8.69, 10.67]，趨勢/變化量/修正人數齊備 | 33 位分析師，[22.08, 26.00]，同構欄位 |
| 來源缺口 | down_90d UNAVAILABLE、cross-check null | down_90d UNAVAILABLE、cross-check null |
| 被拒評估日 | 1（OCF 缺 FY2016 Q1） | 4（首個 TTM 視窗未滿前） |

**隔離驗證**（同機序貫執行 AAPL→MSFT 的 adapter 測試 `test_references_are_isolated_per_ticker`）：兩家各自取得自己的 reference（median 25.3440 vs 41.578319；期間起點 2018-02-02 vs 2021-07-30；P/E 28.4456 vs 33.1959），無殘留、無混合。共識期間的公司日曆差異在 live 產物中如實呈現（2027-09-30 vs 2028-06-30），regression fixtures 不含該 metadata，故以 live 產物為準。

**身分區分**（23+20 項程式化檢查 + web 測試）：production 分布（`PRODUCTION_PE_MEDIAN`/`PRODUCTION_PFCF_MEDIAN`，帶 sample count 與 eligibility）、vendor band（P/E descriptive 7-8 obs、P/FCF UNAVAILABLE）、使用者自訂倍數（`user_supplied`/`is_user_assumption=true`）三者在 API、UI、context、dossier 四層各自標記，從不互換。

## 3. 發現的障礙與最小修補（本次唯一程式變更）

**障礙：** web 路徑（API + UI）啟用了歷史 P/E reference，但未啟用 `include_historical_pfcf`——使用者從代號進入 web 流程時，現價反推缺少 FCF 假設（問題 2 只能答一半），且 UI 無從分辨「P/FCF 不適用此公司」與「流程不支援」。

**最小修補（不改動任何計算邏輯）：**
- `web/service_adapter.py`：`include_historical_pfcf=True`；`_visible_result` 對 `production_historical_pfcf` 做與 P/E 相同的瘦身；映射 `selected_pfcf`/`selected_pfcf_basis`/`implied_fcf_at_reference_multiple`；以 run 自己的 payload 建構 compact P/FCF summary。
- `web/schemas.py`：`ProductionHistoricalPfcfSummaryDTO`（含 `current_pfcf`/`current_pfcf_as_of`）+ `ValuationSummary` 三欄位 + `ReverseRequirementsReportDTO` 與 `AnalysisResultDTO` 的 summary 欄位。
- 前端：`ReverseRequirementsMatrix` 新增 P/FCF summary 區塊（`data-testid="production-historical-pfcf"`，鏡像已驗證的 P/E 區塊）；`ResultCards` 基礎說明列新增隱含 FCF 與參考 P/FCF；i18n（en/zhTW）+ 類型定義。
- 測試：web 路徑兩個新測試（上述）；全套件 2,227 passed / 169 skipped / 0 failed；前端 `npm run build` 通過。

## 4. 四個問題的回答能力（§三）

以 MSFT 為例（AAPL 同構，數值不同）：

1. **目前市場價格與日期**：主要畫面標頭 539.055 USD（2026-10-15）；歷史重建值另標 2026-10-06（canonical 序列末日）——兩個日期從不混淆。
2. **現價隱含假設**：隱含 EPS 16.2386（÷33.1959）、相對共識 −31.5%、所需成長 −7.89%/年、隱含 TTM FCF 89.4B（÷41.5783）——每個都有 basis 標籤（production median / user supplied / band），基礎說明列逐項寫明公式與「非矩陣情境」的界限。
3. **共識與修正**：主要畫面顯示共識值與觀察倍數；明細層（context `observed` + dossier）給出 7/30/60/90 天前序列、變化量、上/下調人數與來源標籤。
4. **不可用項**：`unavailable` 列表帶原因（band 不足 20 筆、cash-flow method 需明示倍數、無風險利率未請求等）；`down_90d`、cross-check 缺口保留 UNAVAILABLE/null，不補零。

歷史倍數情境（矩陣 exit 欄位、P/FCF 百分位情境）全部標註來源與樣本數，且 UI 與報告都聲明其為條件式計算；無任何中位數或倍數被自動選為結論（測試釘死：使用者倍數永遠標為 user assumption，production median 永遠標為其自身來源）。

## 5. 可追溯性（§五）

主要顯示值 → context → 原始來源的鏈路已驗證：摘要卡的每個數字對應 `ValuationSummary` 欄位 → run 的 `reference`/`market_implied_assumptions`/`observed_valuation` → context `provenance.refs`（含 basis、observation count、eligibility）→ 觀測的原始欄位路徑（module/field、accession、usable date、content hash、input_set_id）。歷史分布另附 `input_set_id`（對全部輸入檔案的雜湊），資料集 manifest 記錄取得方式與限制。

## 6. 交付清單與狀態

- 本次 commit：web 路徑 P/FCF 接線（後端 3 檔 + 前端 6 檔）+ 2 個 web 驗收測試 + PROJECT-STATUS 狀態更新。
- 已凍結產物不變：AAPL v1（`fe7d7c7`/`9ca6999`）與 MSFT 驗證（`37262ae`）的全部研究快照。
- 仍未支援（記錄於 PROJECT-STATUS）：cross-check 欄位的 vendor-band-only 口徑、`down_90d` 來源缺口、矩陣非 P/E 方法的自動參考（契約要求明示輸入）。
- 遠端同步與 CI：見 commit 記錄；每個 commit 的 CI 均獨立查證。
