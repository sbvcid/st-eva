import { Translations } from './types'

export const zhTW: Translations = {
  header: {
    tagline: '市場隱含反推估值',
    installApp: '安裝應用',
    install: '安裝',
    languageToggle: 'EN',
  },
  hero: {
    title: '反推市場定價預期',
    subtitle: '萃取隱含基本面假設，並以時點重演驗證歷史可接納性。',
  },
  search: {
    placeholder: '輸入股票代號（例如 AAPL, MSFT, TSM, MU）...',
    analyze: '開始分析',
    analyzing: '分析中...',
    quickExamples: '快速範例：',
    coverageNotice:
      '目前針對美國 SEC 申報企業最佳化。外國發行人與非美股標的之覆蓋程度可能有所不同。',
  },
  offline: {
    banner:
      '離線模式 — 已載入快取介面。即時金融反推估值需要網路與後端連線。',
    guard:
      '離線狀態：即時 SEC 擷取與金融準入審查需要網路連線。',
  },
  errors: {
    requestErrorTitle: '分析請求錯誤',
    defaultSubmitError: '無法提交分析任務。',
    defaultCheckError: '查詢任務狀態失敗。',
  },
  stepper: {
    progressTitle: '分析進度',
    resolving: '解析公司主體',
    fetchingSec: '擷取 SEC 申報',
    admission: '指標準入審查',
    valuation: '隱含估值計算',
    archiveReplay: '存檔與時點重演',
  },
  results: {
    verdictTitle: '分析結果裁決',
    analyzeAnother: '分析其他標的',
    marketPrice: '市場價格',
    impliedFwdEps: '隱含遠期 EPS',
    reqEpsCagr: '所需 EPS 複合成長率',
    referencePe: '參考本益比',
    admissionStatus: '準入審查狀態：',
    admitted: '已準入',
    refused: '拒絕準入',
    partialAdmission: '部分準入',
    admittedCounts: (admitted: number, refused: number) =>
      `${admitted} 項已準入 / ${refused} 項遭拒`,
    refusalExplanation:
      '依據數據契約與可比性規則（例如跨幣別或未映射會計基礎），此發行人已被合法拒絕準入。此為正式契約審查結果，非系統異常。',
    coreFactsAdmitted: '核心財務事實已成功準入估值計算邊界。',
    admittedMetricsPrefix: '已準入指標：',
    observedMultiples: '觀測估值倍數',
    trailingPe: '歷史本益比 (Trailing P/E)',
    ps: '股價營收比 (P/S)',
    pfcf: '股價自由現金流比 (P/FCF)',
    evEbitda: '企業價值倍數 (EV/EBITDA)',
    analyticalBoundaries: '分析邊界限制：',
    replayTitle: '歷史切點重演驗證',
    replayMatchText: (asOf: string) =>
      `重演確定性已驗證：截至 ${asOf} 之歷史存檔輸入完美重現此估值情境。`,
    replayInsufficientDefault:
      '在此切點時刻所存檔之歷史事實不足。已如實回報可信度不足。',
    replayDivergedDefault:
      '重演計算結果與已存檔之快照產生歧異。',
    notAttempted: '未執行',
    obsUsed: (count: number) => `使用觀測值：${count}`,
    obsConsidered: (count: number) => `考量觀測值：${count}`,
    fidelity: (fidelity: string) => `精確度：${fidelity}`,
  },
  evidence: {
    title: '事實證據與監管溯源',
    identifiersCount: (count: number) => `(${count} 個識別碼)`,
    hideDetails: '收合明細',
    showDetails: '展開明細',
    sourceAttributions: '資料來源標註',
    evidenceContractIds: '證據契約編號清單',
    noEvidence: '無關聯之特定證據項目。',
    discrepancyStatus: '跨資料來源差異比對狀態：',
  },
  footer: {
    text: 'ST-EVA 敘事型反向估值與數據準入框架 • 生產基準 3.34',
  },
}

