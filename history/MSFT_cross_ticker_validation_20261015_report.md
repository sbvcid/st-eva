# MSFT 跨標的驗證報告 — AAPL v1 pipeline 的第二家公司重用

**Research run:** `RES-B35CA79AA4`（2026-10-15 執行）
**程式基線核對：** 實際 HEAD 為 `9ca6999`（= 預期程式基線 `fe7d7c7` + 已提交的 AAPL v1 市值文件修正 `docs` commit），與 origin/master 同步、working tree 乾淨。未假設與 AAPL 快照 repo 同 commit。
**指令：** `python st_eva_runner.py MSFT --mode live --historical-pe --historical-pfcf --context … --dossier … --dossier-report --json`
**性質聲明：** 反向估值的機械式重述；無 LLM、無評級、無預測、無自動倍數選擇。門檻未放寬（≥20 維持）、取樣方法未變。

---

## 1. 結論摘要

**AAPL 的整條 pipeline——歷史 P/E、歷史 P/FCF、共識擷取、現價反推、reference provenance——在 MSFT 上以零 pipeline 程式修改直接重用成功。** 唯一的「新增程式」是 `historical_pfcf.py` 的 issuer 設定項（路徑 + 會計年度月份，這是設計好的延伸點）與三個 SEC concept 檔 + manifest。發現的差異全部屬於**公司/來源資料差異**（類別 2），**沒有發現一般性程式缺陷**（類別 3），因此本次除了設定與資料外沒有修改任何程式邏輯。

## 2. 真正成功重用的現有功能

| 能力 | MSFT 實際結果 | 重用方式 |
|---|---|---|
| Live acquisition + 契約觀測 | 價格 539.055 USD（2026-10-15）、14 個 material evidence、資料契約自驗證通過 | 不變 |
| Production 歷史 P/E | **24/27 觀測，USABLE_FOR_REFERENCE**，2021-07-28→2026-07-30，median 33.20（10th 25.60 / 90th 36.09）；3 個早期評估日因 Q4 EPS 尚不可知被拒（`REASON_MISSING_Q4_EPS`） | 不變 |
| **Production 歷史 P/FCF** | **23/27 觀測，USABLE_FOR_REFERENCE**，2021-07-30→2026-07-30，median 41.58（10th 31.69 / 90th 49.12）；4 個早期評估日因 TTM 視窗未滿被拒 | **僅新增 issuer 設定（fye_month=6）+ 資料集；pipeline 程式零修改** |
| Forward EPS 共識 | 17 項 metric 全部取得（見 §4）；`down_revisions_90d` 來源未提供 → UNAVAILABLE | 不變 |
| Reference provenance | context 記錄 `PRODUCTION_PE_MEDIAN`（24）/`PRODUCTION_PFCF_MEDIAN`（23），從不誤記為 vendor band；earnings-method 來源標籤修正（`production_historical_pe_percentile`、非 user assumption）在 MSFT 路徑同樣成立 | 不變 |
| 現價反推 + 機械情境 | 隱含假設與五個 P/FCF 百分位情境全部可獨立重算（見 §5） | 不變 |
| Vendor cap 戳記驗證 | AAPL 的核對邏輯直接重用：3,717,153,817,339 ÷ 2026-09-23 收盤 500.59 = 7,425,545,545 股，與 cover-page 股數一致（差 54 股）——**與 AAPL 相同的季度戳記機制，非 live 價乘積** | 不變 |

## 3. MSFT 新增取得的真實資料

- **歷史 P/FCF 資料集**（`data/historical_pfcf/MSFT/`，與 AAPL 同一取得機制）：OCF 170 facts、capex 230 facts（皆 USD 正數量值，與 AAPL 同符號慣例）、dei 股數 24 facts 落於 acceptance index（as-of 2020-10-22→2026-07-23）。OCF/capex 的累計期間（Q/6M/9M/FY）自索引內申報完整覆蓋 FY2021–FY2026。
- **公司差異被正確處理**：會計年度 6 月底（`fye_month=6`，Q1 止 9 月、Q4 止 6 月）；共識 `+1y` 宣告 end = **2028-06-30**（AAPL 為 2027-09-30）——同一欄位、不同公司日曆，來源宣告原樣保留。
- **MSFT 口徑註記**（記錄於 manifest）：Microsoft 的 finance-lease 本金支付在 capex 標籤之外，重建按標籤定義排除之——這是標籤邊界的如實記錄，不是缺陷。

## 4. 共識樣本與近期變化（同一預測期間 +1y / 2028-06-30）

平均 **23.71027**、33 位分析師、區間 [22.08, 26.00]；7/30/60/90 天前 23.67732/23.59268/23.57328/22.60632，變化量 +0.033/+0.118/+0.137/**+1.104**（90 天淨上修）；修正人數 7d 上3下1、30d 上3下2；90 天下調來源未提供（缺口保留）。與 AAPL 方向相反——MSFT 近 90 天共識上修 4.7%，AAPL 下修 1.1%——同一擷取路徑正確反映兩家公司的不同事實。

## 5. 現價反推（price 539.055，2026-10-15）

| 隱含假設 | 值 | 公式 |
|---|---|---|
| 價格隱含 forward EPS | **16.2386** | 539.055 ÷ 33.1959 |
| 相對共識差距 | **−31.51%** | 16.2386 ÷ 23.71027 − 1 |
| 所需 EPS 年成長 | **−7.89%/年** | (16.2386 ÷ 17.633)^1 − 1 |
| 價格隱含 TTM FCF | **89.40B** | 3,717.15B ÷ 41.5783 |

跨標的對照（同一公式、不同公司事實）：AAPL 以歷史中位數 P/E 反推隱含 EPS **高於**共識 25.8%；MSFT **低於**共識 31.5%——兩家的價格/共識關係相反，pipeline 正確呈現而未強加任何方向。P/FCF 情境（明示機械式，無一被選為結論）：10th→117.3B、25th→99.4B、median→89.4B、75th→84.9B、90th→75.7B。重建當前值 58.67（2026-10-06）較歷史 median 高 41%；AAPL 為 +40%。

## 6. 未能重用/受限的部分與根本原因

| 項目 | 類別 | 根本原因 |
|---|---|---|
| P/FCF 27 個評估日中 4 個被拒（2020-10-28~2021-07-28） | 來源資料差異 | acceptance index 自 2020-09-30 期別起，首個完整 FY 視窗（FY2021 Q4）在 FY2021 10-K 可知日前不成立——與 AAPL 前 4 個評估日被拒同理，是 same-rule 的誠實拒絕 |
| `down_revisions_90d` UNAVAILABLE | 來源資料差異 | Yahoo 在 MSFT 的 payload 同樣不提供該區塊數值 |
| Vendor P/FCF band UNAVAILABLE | 來源資料差異 | 與 AAPL 相同：vendor marketCap 與 FCF 序列無共同日期 |
| `consensus_cross_check` 欄位 null | 方法口徑 | 該欄位僅讀 vendor band（7 obs），production median 未接入——與 AAPL 同一已記錄缺口，本次不擴大修改 |
| P/E 3 個早期評估日被拒 | 來源資料差異 | Q4 EPS 可知日（8-K/10-K）晚於前三次評估 |

**類別 3（一般性程式缺陷）：本輪未發現新缺陷。** 上一輪修復的 earnings-method 來源標籤在 MSFT 路徑驗證成立（23 項程式化檢查含此項）。

## 7. 對下一階段的實際影響

1. **可重用性已由第二家公司證實**：跨標的擴充的成本 = 一個 issuer 設定 + 一份同構資料集（3 個 concept 檔 + manifest），前提是標的已有 canonical 歷史 P/E 資料集（價格 + acceptance index）。
2. **資料前提清單**（下一家公司適用）：SEC 三 concept 可得、正數量值標籤、索引內累計期間覆蓋 ≥ 一個完整財年、cover-page 股數在索引內。
3. **兩個既有記錄缺口不阻擋下一家**：consensus cross-check 的 vendor-band-only 口徑與 `down_revisions_90d` 來源缺口，如實保留即可。
4. **不建議的方向**：不需要 MSFT 專用引擎、不需要為湊滿 20 筆放寬規則——23 筆合格觀測由既有規則自然產生。

## 8. 驗證證據

23 項程式化檢查全部通過（`MSFT_cross_ticker_validation_20261015.json`）：reference 三方一致、context basis 正確、earnings-method 標籤正確、vendor cap 戳記與 cover-page 股數核對、TTM 四季可知日 ≤ 評估日、觀測值重算、隱含假設重算、共識單一期間（2028-06-30）、down_90d 缺口保留、五情境可重算且無自動選擇。資料隔離：未觸碰 `st-eva.sqlite`、AAPL 產物與 `methodology/`；全套件回歸見 commit 記錄。

## 9. 產物清單

| 產物 | 內容 |
|---|---|
| `history/MSFT_RES-B35CA79AA4_market_implied_assumptions.json` | 執行快照 |
| `history/MSFT_context_20261015.json` | Investment Context（自驗證通過） |
| `history/MSFT_research_dossier_20261015.json` + `_report.txt` | 完整 dossier（80 情境矩陣） |
| `history/MSFT_cross_ticker_validation_20261015.json` | 23 項驗證檢查 + 分布 + 情境 + 市值戳記核對 |
| `data/historical_pfcf/MSFT/` | MSFT P/FCF 資料集（3 concept 檔 + manifest） |
| 本檔案 | 跨標的驗證報告 |
