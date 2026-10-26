# 第三方資料來源登記規則 (Third-Party Data Source Registration)

適用於任何新增到 `data/` 的外部來源資料，不限於 Yahoo Finance、SEC EDGAR 或其他來源。

## 規則（預設保守）

新增外部資料前，必須在檔案旁或 `DATA-DELIVERY.md` 記錄以下（缺一不可；無法確認時預設只留在本機）：

- **路徑**：完整相對路徑（例如 `data/historical_pe/SOFI/daily_prices.json`）。
- **來源**：原始提供者識別（例如 `Yahoo Finance chart API v8`、`SEC EDGAR`、`internal`）。
- **適用條款 / 授權依據**：具體條款版本或 URL（例如 `https://policies.yahoo.com/us/en/yahoo/terms/index.htm`），或 `SEC EDGAR public domain`；若無法確認，記錄「C-1 未確認」。
- **是否允許公開再散布**：只有在條款明確允許或政府公共領域時標記為 `public`；否則標記為 `local_only`。
- **允許保留形式**：例如「固定快照 JSON」、「SQLite 归档」、「原始 API 回應」；不可將未授權原始資料改名後提交。
- **審查日期**：YYYY-MM-DD，與提交日期對應。
- **本機副本確認**：確認本機原始檔案存在，並記錄備份位置（若與 Git 路徑相同，記為 `local_path_preserved`）。

**預設處理：**
- 若授權未確認或來源未記錄 → **不提交到 Git**；只留在本機。
- 若已追蹤資料的授權被發現有疑慮 → 立即移出追蹤（`git rm --cached`），保留本機副本，更新 `DATA-DELIVERY.md` 和 `.gitignore`，不重寫歷史（若需清理歷史，另行提出 `filter-repo` 方案並等待批准）。
- 不得在 `.gitignore` 加入例外後仍提交同一資料；`.gitignore` 只防止未追蹤檔案被加入，不擋已追蹤檔案（已知限制，已在 DATA-DELIVERY.md 記錄）。

## 使用流程

1. 在提交前，先更新本文件（或在 `DATA-DELIVERY.md` 新增條目）。
2. 執行 `python scripts/check_unauthorized_data_precommit.py`（或依賴 `.git/hooks/pre-commit`）。
3. 若腳本阻擋，修正路徑或將資料留在本機；不得改名或轉格式規避。
4. 提交訊息中若涉及第三方資料，須包含來源識別與授權狀態（例如 `data: Yahoo Finance v8 price snapshot; C-1 unverified; local only`）。

## 關聯文件

- `DATA-DELIVERY.md`：分類、授權判定、測試證據、清理歷史。
- `.gitignore`：已知排除路徑列表。
- `scripts/check_unauthorized_data_precommit.py`：防護腳本（只拒絕已知路徑，不禁止 SEC EDGAR 或合法測試 fixture）。
