export type Language = 'zh-TW' | 'en'

export interface Translations {
  header: {
    tagline: string
    installApp: string
    install: string
    languageToggle: string
  }
  hero: {
    title: string
    subtitle: string
  }
  search: {
    placeholder: string
    analyze: string
    analyzing: string
    quickExamples: string
    coverageNotice: string
  }
  offline: {
    banner: string
    guard: string
  }
  errors: {
    requestErrorTitle: string
    defaultSubmitError: string
    defaultCheckError: string
  }
  stepper: {
    progressTitle: string
    resolving: string
    fetchingSec: string
    admission: string
    valuation: string
    archiveReplay: string
  }
  results: {
    verdictTitle: string
    analyzeAnother: string
    marketPrice: string
    impliedFwdEps: string
    reqEpsCagr: string
    referencePe: string
    admissionStatus: string
    admitted: string
    refused: string
    partialAdmission: string
    admittedCounts: (admitted: number, refused: number) => string
    refusalExplanation: string
    coreFactsAdmitted: string
    admittedMetricsPrefix: string
    observedMultiples: string
    trailingPe: string
    ps: string
    pfcf: string
    evEbitda: string
    analyticalBoundaries: string
    replayTitle: string
    replayMatchText: (asOf: string) => string
    replayInsufficientDefault: string
    replayDivergedDefault: string
    notAttempted: string
    obsUsed: (count: number) => string
    obsConsidered: (count: number) => string
    fidelity: (fidelity: string) => string
  }
  evidence: {
    title: string
    identifiersCount: (count: number) => string
    hideDetails: string
    showDetails: string
    sourceAttributions: string
    evidenceContractIds: string
    noEvidence: string
    discrepancyStatus: string
  }
  footer: {
    text: string
  }
}

