import { Translations } from './types'

export const en: Translations = {
  header: {
    tagline: 'Market-Implied Valuation',
    installApp: 'Install App',
    install: 'Install',
    languageToggle: '中文',
  },
  hero: {
    title: 'Reverse-engineer market expectations',
    subtitle: 'Extract implied fundamentals and verify historical admissibility with point-in-time replay.',
  },
  search: {
    placeholder: 'Enter ticker (e.g. AAPL, MSFT, TSM, MU)...',
    analyze: 'Analyze',
    analyzing: 'Analyzing...',
    quickExamples: 'Quick examples:',
    coverageNotice:
      'Currently optimized for U.S. SEC-reporting companies. Coverage may vary for foreign issuers and non-U.S. securities.',
  },
  offline: {
    banner:
      'Offline Mode — App shell cached. Live financial valuation requires an active network connection.',
    guard:
      'Offline: Live SEC ingestion and financial admission require network connectivity.',
  },
  errors: {
    requestErrorTitle: 'Analysis Request Error',
    defaultSubmitError: 'Failed to submit analysis job.',
    defaultCheckError: 'Error checking job status.',
  },
  stepper: {
    progressTitle: 'Analysis Progress',
    resolving: 'Resolving company',
    fetchingSec: 'Fetching SEC',
    admission: 'Admission',
    valuation: 'Valuation',
    archiveReplay: 'Archive / Replay',
  },
  results: {
    verdictTitle: 'Analysis Verdict',
    analyzeAnother: 'Analyze another',
    marketPrice: 'Market Price',
    impliedFwdEps: 'Implied Fwd EPS',
    reqEpsCagr: 'Req. EPS CAGR',
    referencePe: 'Reference P/E',
    admissionStatus: 'Admission Status:',
    admitted: 'ADMITTED',
    refused: 'REFUSED',
    partialAdmission: 'PARTIAL ADMISSION',
    admittedCounts: (admitted: number, refused: number) =>
      `${admitted} admitted / ${refused} refused`,
    refusalExplanation:
      'This issuer was legitimately withheld per data contract and comparability rules (e.g. cross-currency or unmapped basis). This is a formal contract result, not a system defect.',
    coreFactsAdmitted: 'Core facts admitted into valuation input boundary.',
    admittedMetricsPrefix: 'Admitted metrics:',
    observedMultiples: 'Observed Valuation Multiples',
    trailingPe: 'Trailing P/E',
    ps: 'P/S (Revenue)',
    pfcf: 'P/FCF',
    evEbitda: 'EV / EBITDA',
    analyticalBoundaries: 'Analytical Boundaries:',
    replayTitle: 'Point-in-Time Replay Verification',
    replayMatchText: (asOf: string) =>
      `Replay determinism verified: historical archive inputs at ${asOf} perfectly reproduce this valuation context.`,
    replayInsufficientDefault:
      'Not enough historical facts were archived at this cutoff instant. Honest insufficiency reported.',
    replayDivergedDefault:
      'Replay produced a diverged document from the stored snapshot.',
    notAttempted: 'NOT ATTEMPTED',
    obsUsed: (count: number) => `Obs used: ${count}`,
    obsConsidered: (count: number) => `Obs considered: ${count}`,
    fidelity: (fidelity: string) => `Fidelity: ${fidelity}`,
  },
  evidence: {
    title: 'Evidence & Regulatory Provenance',
    identifiersCount: (count: number) => `(${count} identifiers)`,
    hideDetails: 'Hide details',
    showDetails: 'Show details',
    sourceAttributions: 'Source Attributions',
    evidenceContractIds: 'Evidence Contract IDs',
    noEvidence: 'No explicit evidence items attached.',
    discrepancyStatus: 'Cross-source discrepancy status:',
  },
  footer: {
    text: 'ST-EVA Descriptive Reverse Valuation & Admissibility Framework • Production Baseline 3.34',
  },
}

