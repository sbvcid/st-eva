# MU 第三標的研究流程驗收報告

**驗收日期：** 2026-10-15
**基線核對：** 实际 HEAD `4797f1f`（= AAPL v1 冻结版 `9ca6999` → MSFT 跨标的验证 `37262ae` → web P/FCF 接线 `4797f1f`），与 `origin/master` 同步、working tree 干净。本次只涉及 `sbvcid/st-eva` 一个 repository；`C:\git\research-reports` 为无关的出版项目，未纳入。
**性質：** 第三标的实际研究流程验证。本轮**未修改任何产品代码**，未新增供应商、endpoint 或观测数门槛，未重建数据库，未改动 AAPL v1 冻结产物，未触碰 `methodology/` 或 RUNBOOK。

---

## 0. 结论摘要

MU 的实际执行证实：**现有研究流程可以在一个缺乏合格历史分布、且财务特性与 AAPL/MSFT 显著不同的标的**上正确运行，并把差异诚实地呈现出来。流程本身可直接重用；MU 的局限（生产历史 P/E、P/FCF 双缺、vendor band 仅 3 笔、共识期间与财年错配）全部以显式原因报告，没有以合成数据或替代口径冒充。

**未发现必须修正的共用程式缺陷。** Web 计算、摘要、矩阵、证据四条线在 MU 上一致；独立重算 16/16 情境误差 < 1e-9；摘要隐含 EPS、观测倍数、隐含股数均可独立复算。重演报告 `DIVERGED` 为既有系统性现况（详见 §5），非 MU 新引入问题。

---

## 1. 执行路径（实时采集，非测试数据）

Web UI `http://127.0.0.1:8010`（`py -3.12 -m web.app`，生产前端 `dist/`），模式**仅实时行情（live）**——不会回退到测试 fixture。

四次执行，全部 live 采集（来源标识：`YahooFinance+YahooFinanceFundamentals` / `Yahoo Finance chart API` / `API_LIVE`）：

| 执行 | 参数 | 产出 | 落档 |
|---|---|---|---|
| run1 | 默认（无参考倍数） | 价格 + 显式不可用矩阵 | `run1_default_result.json` |
| run2 | `reference_multiple=15.0` | 16 情境完整矩阵 | `run2_user_pe15_result.json` |
| run3 | PE 15 + horizons/returns 显式 | 同 run2 结构 | `run3_full_params_result.json` |
| run4 | PE 15 + `user_eps=71.28` | 用户 EPS 假设路径 | `run4_user_eps_result.json` |

`run2`/`run3` 的 `matrix_size=16`（4 持有期间 × 4 要求报酬率 × 1 用户倍数），`start_anchor` 来自 `ev-current-eps-001` 的 TTM EPS。`run4` 的 `user_eps` 正确标为 `is_user_assumption` 假设资产，与真实观测严格分离。

**价格日期说明（问题 1）：** 摘要卡标 `As of 2026-10-15`；价格分别为 912.605 / 907.985 / 906.78（四次 live 执行随时间变化，属 Yahoo 即时数据的正常行为）。MU 生产历史 P/E、P/FCF 为 `UNAVAILABLE`，**没有**「重建序列末日」需要与价格日期区分——两个日期单一且明确，不会混淆。

---

## 2. 真实数据记录

### 2.1 市场价格与观测倍数

| 项目 | 值 | 独立重算 |
|---|---|---|
| 市场价格 | 912.605 USD（2026-10-15, NMS, API_LIVE） | — |
| TTM EPS（起始锚） | 71.28 USD（`ev-current-eps-001`，期间未声明） | 912.605 / 71.28 = **12.8031** ✓ |
| Forward EPS 共识 | 204.46593 USD，+1y，period end **2028-08-31** | 912.605 / 204.46593 = **4.4634** ✓ |
| P/S | 13.41x | — |
| P/FCF | 46.25x | market_cap 1,210,573,930,693 / FCF 26,172,000,000 = **46.2545** ✓ |
| EV/EBITDA | 17.44x | — |
| 隐含股数 | 1,326,503,724 | 1,210,573,930,693 / 912.605 = **1,326,503,723.6** ✓ |

FCF 单一观测 `ev-fcf-001` = TTM 26.172B；vendor **未提供** `pfcf_band`，故历史 P/FCF band 为空对象 `{}`、状态 `UNAVAILABLE`。这与 `obs:ev-pfcf-band-001` 被拒原因（"pfcf_band was requested and not provided by YahooFinanceFundamentals"）完全一致。

### 2.2 历史 P/E 与 P/FCF（问题 3 的第一半）

| Reference | 观测数 | 时间范围 | 资格状态 | 系统行为 |
|---|---|---|---|---|
| 生产历史 P/E | 0（数据集未建立） | 无 | `UNAVAILABLE`，`REASON_INSUFFICIENT_OBSERVATIONS`，"Production historical P/E dataset is not yet established for MU." | 明确理由，**无替代倍数** |
| 生产历史 P/FCF | 0（数据集未建立） | 无 | `UNAVAILABLE`，同样 reason_code | 同上 |
| vendor P/E band | 3 | 单一静态快照 | `DESCRIPTIVE_ONLY_INSUFFICIENT_OBSERVATIONS`（< 20） | 中位数 24.209486 仅作描述性统计，**不进入情境倍数** |
| vendor P/S band | 7 | 同上 | `DESCRIPTIVE_ONLY_INSUFFICIENT_OBSERVATIONS` | median 5.530493，仅描述 |
| vendor EV/EBITDA band | 7 | 同上 | `DESCRIPTIVE_ONLY_INSUFFICIENT_OBSERVATIONS` | median 15.924，仅描述 |
| vendor P/FCF band | 0 | — | `UNAVAILABLE` | 空缺即空缺 |

**"不能直接比较"的具体情形（已在 UI 明示）：**
1. **当前 trailing P/E 12.80 落在 vendor band 的 10th 分位（12.87951）附近**——远低于中位数 24.209486。若把两者相比会读出"低估"结论，但 band 只有 3 笔观测且统计口径不明，系统明确拒绝读取百分位（`pe_percentile` 被拒：band 不可用为 reference）。
2. **consensus period end 2028-08-31 vs 情境期末窗口**：矩阵的 comparison_notes 明确写出 "The consensus period ends on 2028-08-31 while the terminal EPS window ends on ..., a difference of 321 days. These are different periods and are not compared here." 并打旗标 `CONSENSUS_PERIOD_NOT_COMPARABLE`。这是 MU 独特的财年口径差异（MU FY 结束于 8 月底，与 AAPL 的 9 月、MSFT 的 6 月不同），系统不强行对齐。

### 2.3 共识资料完整度（问题 4）

MU 的 consensus block 在 `observed` 中有 18 项：`consensus_forward_eps` 本体 + analyst_count + low/high + trend_current + up/down revisions (7d/30d, 90d) + change (7d/30d/60d/90d) + 7d/30d/60d/90d_ago 序列。**实际取得的缺口（来源缺数据，非系统缺陷）：**

- `consensus_forward_eps_down_revisions_90d` → 被拒，"was requested and not provided by YahooFinanceFundamentals"
- 价格日期未声明（`period_start`/`period_end` 为 null，`period_undeclared_by_source=True`），证据抽屉标注 "Starting EPS period coverage was not declared by source"

`data_quality.discrepancy_status = UNVERIFIABLE`：单一 vendor 来源，无第二来源可比对。SEC 侧存在 `cmp-revenue-sec-fy2025-...` 等 filings，但只有 `revenue` 通过 V1 边界准入。

### 2.4 历史 FCF 负值/零值/波动处理（问题 2 的指定检查）

MU **没有历史 FCF 序列**（仅单一 TTM 观测 26.172B，无 vendor band，无生产数据集），所以"负 FCF、零 FCF、波动 FCF"这一组规则在本轮**未被触发**——系统以 `UNAVAILABLE` / 空 `{}` 显式报告，未产生任何倍数。这是正确的缺席保留，而非删除不利观测。

真正体现 MU 财务特性的是 **EPS 的极端周期性**（SEC 证据序列）：FY2025 7.59 → Q FY2026 单季 74.33，TTM 从 21.19 → 44.24 → 74.33。这构成本次验收最重要的周期戒告：任何以单一时点 EPS 为锚的反推结论，对 MU 都可能因周期位置而严重误导。UI 未对 MU 做特殊化，但已通过以下既有机制限制解读：`PERIOD_UNDECLARED_BY_SOURCE`、`NO_REFERENCE_MULTIPLE`、`CONSENSUS_PERIOD_NOT_COMPARABLE` 旗标，以及条件性声明 "Implied fundamentals are conditional on the selected valuation multiple."

---

## 3. 现价隐含假定的独立重算（问题 2 的核心）

以 run2（价格 907.985，用户 P/E 15.0，起始 EPS 71.28 TTM）为基准，对全部 16 个情境独立重算：

- 期末价格 `P_T = P_0 × (1+r)^T`
- 必要期末 EPS `EPS_T = P_T / PE_exit`
- 必要 EPS CAGR `(EPS_T/EPS_0)^(1/t_growth) − 1`

**结果：16/16 全部吻合，误差 < 1e-9。** 例：T=1, r=8% → 907.985×1.08 = 980.6238，/15 = 65.37492，(65.37492/71.28)−1 = −8.284343%。

摘要卡层面：`forward_eps_at_reference_multiple` = 907.985/15 = **60.5323** ✓（UI 显示 60.45，取自 UI 那次的即时价格 906.78，同样自洽）。`eps_gap_vs_consensus` = 60.5323/204.46593 − 1 = **−70.39%** ✓。

`required_eps_cagr`（摘要）−15.08% 与矩阵行的差异是**口径不同**：摘要是"固定倍数对照 TTM EPS、按 1 年折算、不含要求报酬率"，矩阵行含要求报酬率与退出倍数。两者的界限已写在摘要卡说明文字里（"此与下方反推需求矩阵中……屬不同算法，兩者不可互換"）。

---

## 4. Web UI 五个问题的回答能力

1. **价格与估值数据分别来自哪个日期？** 可回答。摘要卡标 `As of 2026-10-15`，source badge 显示 `即時（Yahoo / SEC）`，证据抽屉给出 `API_LIVE` 与三条来源标识。MU 无重建序列，故不存在第二日期。
2. **在明确列出的 reference 下，现价隐含什么？** 可回答。run1 无参考倍数时，摘要卡的三个隐含值均为 `—` 并附说明；run2 用户指定 15.0x 后，摘要卡显示价格隐含 EPS 60.53（API 值；UI 那次即时价格为 60.45）、复合成长差距 −15.2%、参考倍数 15.0x，且倍数明确标注「您自訂的參考本益比」，与生产分布、vendor band、用户假设三者严格分离。相对共识的差距（−70.4%）在 context / API 层给出，摘要卡只呈现其自己口径的那个差距。
3. **历史分布能提供什么参考？不能比较的情况？** 可回答。矩阵区列出全部不可用条目与原因（band 3 < 20、无生产数据集），百分位不出现在情境倍数中；矩阵每行的 `comparison_notes` 与旗标点名共识期间错配。**历史倍數百分位只以显式条件式情境存在，未被自动选为结论，无买卖评级、无预测、无概率。**
4. **共识资料的来源与期间资讯是否足够？** 基本足够。18 个 consensus 观测、7/30/60/90 天序列、变化量、上下调人数、来源 provider 均可从证据抽屉与 context `observed` 取得；`down_90d` 缺口与价格期间未声明被显式标出而非留空。
5. **哪些输出不可用及原因？** 可回答。`unavailable` 列表覆盖 `exit_multiple`、`exit_multiple.band_scenarios`、`valuation_method.{earnings_multiple,cash_flow,enterprise_value,revenue}`、`risk_free_rate`、`dividend_payments`、`sec_declared_dividends`，每条都有 reason 与 reason_kind。

**跨区块一致性检查（摘要卡 / P/E·P-FCF 区 / 反推矩阵 / 证据抽屉）：** 一致。摘要隐含 EPS 与矩阵起始 EPS 同源（`ev-current-eps-001` 71.28）；P/E 15.0x 在摘要、矩阵 exit_multiple、抽屉 multiple_evidence 三处一致且同为 `user_supplied`；P/FCF 区块明确"無可用之現金流參考倍數"，与 `production_historical_pfcf=UNAVAILABLE`、`valuation_method.cash_flow` 被拒三者一致；14 个证据标识符与 `evidence_ids` 数组完全对应。

---

## 5. 缺陷分类与处理

### 5.1 已确认：重演 `DIVERGED` 是既有系统性现况，非 MU 新引入

MU 四次 live 执行的重演均为 `DIVERGED`（obs 106/106，`OBSERVATIONAL`）。根因经数据库副本重放 + 文档 diff 证实：

- 重建文档缺失 17 个 `obs-consensus-*` 观测（7d/30d/60d/90d_ago、analyst_count、low/high、trend、change、revisions）；
- 原因是 **archive 的 `observations` 表从未收录 vendor 共识类观测**。MU archive 的 metric 清单（23 项）中 `consensus` 类只有 `consensus_forward_eps` 一项，其余 consensus analytics 观测（分析師人数、区间、趋势、修正数）完全不进 archive，只存在于执行时的 context 文档中。

**这不是 MU 特有。** 对 AAPL、MSFT 的 archive 做同样重放（数据库副本上验证，原库只读）：

| Ticker | 最新 context | 重演结果 | obs |
|---|---|---|---|
| AAPL | ctx_cb1434b1（2026-10-09） | `DIVERGED` | 92/92 |
| MSFT | ctx_16f2794b（2026-10-09） | `DIVERGED` | 114/114 |
| MU | ctx_3c6a9c00（2026-10-15） | `DIVERGED` | 106/106 |

三家 context 的 `observed` 都有 18 个 consensus 类键，但三家 archive 都只存 1 个 consensus 指标。故这是**所有 ticker 的既有行为**，且 UI 已诚实地把它报告为"stored context 与 rebuilt context 不同，可能是代码变更或重演不忠实，文档如实报告"。

**不作修复的理由（符合任务约束）：**
- 修复需要把 17+ 个 vendor 共识观测纳入 archive 的观测面，等于改变消费者契约并扩大基础设施——任务明令"不增加新的通用基础架构""不得藉此展開另一輪架構重整"。
- 没有证据表明这是"資料正確但系統錯誤"以外的类别；它属于**已知边界：archive 的目标是 SEC + 结构化 evidence 观测，vendor 共識是 acquisition-time-only**。R6/R6.1 的既有结论（通用 `DIVERGED` 解释措辞为 minor usability observation，非 blocker）仍然成立。
- 这是既有记录在案的现况，不是本轮发现的产品缺陷，故不新增回歸測試。

### 5.2 其他分类

| 观察 | 分类 | 处理 |
|---|---|---|
| `down_90d` 無資料 | 來源缺少資料 | 如实保留 UNAVAILABLE |
| `pfcf_band` 空缺 | 來源缺少資料 | 空 `{}`，P/FCF band `UNAVAILABLE` |
| 价格期间未声明 | 財報/來源特性 | `period_undeclared_by_source=True` 标注 |
| MU 无生产历史分布 | 現有公式不支援该情境（数据集未建立） | `UNAVAILABLE` + reason_code，无替代 |
| 多重 live 價格（912.605/907.985/904.44/906.78） | 資料正確 | 各自 context 如实记录，未混用 |
| 需要 P/FCF 参考时无倍数可用 | 現有公式不支援该情境 | `valuation_method.cash_flow` 显式被拒，**不从 earnings 倍数挪用** |

**未發現真正的共用程式缺陷。** 故本轮**没有代码修改**、没有新增测试文件、没有架构重整。

---

## 6. 交付与回答

### 6.1 现成流程哪些部分可直接重用？

全部核心流程可直接重用，无需任何 MU 特例代码：
- acquisition → admission → 摘要卡 → 反推矩阵 → 证据抽屉的端到端串联；
- 反推矩阵引擎（`reverse-requirements/1.1`）的逐行计算追踪、reproducibility 验证、unavailable 结构化报告；
- 生产历史 P/E / P/FCF 的启用与瘦身加载、`ProductionHistoricalPfcfSummaryDTO` 的呈现；
- 用户参考倍数 / 用户 EPS 的假设标记（`USER_SPECIFIED` / `is_user_assumption`）与真实观测分离；
- JSON / CSV 导出；
- 重演与 admission 摘要。

### 6.2 MU 重要的资料限制与周期戒告

1. **无生产历史 P/E、P/FCF**：MU 未建立 point-in-time 观测数据集，两类 reference 均 `UNAVAILABLE`，这是数据集层面的缺席，不是计算失败。
2. **vendor band 薄（P/E 3 笔、P/S 7 笔、EV/EBITDA 7 笔）**：全部低于 20 笔门槛，只能描述不能用。
3. **EPS 极端周期性**（SEC 7.59 → 21.19 → 44.24 → 74.33 TTM）：以单一时点 TTM EPS 为锚的反推对 MU 的周期位置极敏感；当前 trailing P/E 12.86 低于 vendor band 的 10th 分位，若与 3 笔 band 相较会读出一个无依据的估值判断。
4. **财年口径错配**：MU FY 结束于 8 月底，consensus +1y 结束于 2028-08-31，与 AAPL（9 月）/MSFT（6 月）不同；系统不强行对齐，以 flag 与 comparison_notes 显式声明。
5. **单一 vendor 来源**，`discrepancy_status = UNVERIFIABLE`。

### 6.3 Web UI 是否足以呈现这些差异？

是。五个问题全部可答（见 §4），且四个区块一致。特别地：摘要隐含值缺失时显示 `—` 而非 0 或猜测值；P/FCF 缺失时有独立的中文说明行；矩阵的不可用条目逐条给出 reason 与 reason_kind；证据抽屉给出 14 个标识符与 `API_LIVE` 来源。**没有一处把"无数据"呈现为某个数。**

### 6.4 是否存在必须修正的共用缺陷？

**否。** `DIVERGED` 为三家共有且已日志化的既有行为；其余为来源缺席或公式不支援该情境。本轮无代码变更，也因此没有新增或修改的测试。

### 6.5 这次验证是否改变对 ST-EVA 可重複使用性的判断？

**没有改变，反而增强。** 在第三种财务特性（高波动周期性、无合格历史参考、财年不同、单一来源）下，系统仍然：采集真实资料、拒绝以合成数据冒充、把不可用项结构化报告、让用户指定倍数后可完整复算 16 个情境、并清楚分离真实观测/公式计算/条件式情境/不可用数据。这验证了 R1–R7 建立的契约在新的财务条件下依然成立。

---

## 7. 验证与最终 Git 状态

- **本地测试（本轮前已由 CI 覆盖的基线 `4797f1f`）：** 本轮**未修改产品代码**，因此未重跑全量套件；`4797f1f` 的既有 CI 结果保持有效。本轮的验证方式是**实时执行 + 独立重算**（16/16 情境、摘要隐含 EPS、观测倍数、隐含股数，全部误差 < 1e-9）。
- **差异审阅：** 本轮的 repo 改动仅为研究报告与执行产物，`git diff --check` 通过，无未纳入的凭据、私有资料或无谓生成物。
- **随附产物：** `history/mu_acceptance_20261016/`（四次执行的 API 结果、提交参数、2026-10-15 的 stored context 文档）与本报告。
- **AAPL v1 冻结产物与 MSFT 验证快照：** 未改动。
- **遠端 CI：** push 後以 GitHub API 獨立查證最新 commit 的 workflow；若無法查證將明確註記（見結案時的實際結果）。
