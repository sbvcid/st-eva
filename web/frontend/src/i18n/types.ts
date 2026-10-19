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
    headlineMetricsTitle: string
    headlineMetricsNote: string
    impliedFwdEps: string
    impliedFwdEpsBasis: string
    reqEpsCagr: string
    reqEpsCagrBasis: (years: number) => string
    referencePe: string
    referencePeBasisUser: string
    referencePeBasisProduction: string
    referencePeBasisBand: string
    referencePeBasisNone: string
    impliedFcf: string
    impliedFcfBasis: string
    referencePfcf: string
    referencePfcfBasisUser: string
    referencePfcfBasisProduction: string
    referencePfcfBasisBand: string
    referencePfcfBasisNone: string
    seeMatrixLink: string
    admissionStatus: string
    admitted: string
    refused: string
    partialAdmission: string
    admittedCounts: (admitted: number, refused: number) => string
    refusalExplanation: string
    coreFactsAdmitted: string
    admittedMetricsPrefix: string
    refusedMetricsPrefix: string
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
    regressionNotice: string
    regressionNoticeDesc: string
    // Admission detail: distinct metric count vs observation row count
    admittedMetricsDetail: (distinct: number, rows: number, names: string) => string
    refusedMetricsDetail: (distinct: number, rows: number, names: string) => string
    // P/FCF reference label: inferred, not an actual observation
    impliedFcfReferenceLabel: string
    // Matrix limitation: top-level P/FCF single-point vs per-scenario matrix input
    matrixPfcfLimitationNotice: string
    // Replay divergence structured diff labels
    // Observation availability classes (all observations, informational only)
    replayObsAvailabilityHeader: string
    replayObsAvailabilityNote: string
    // Field-level differences between stored and rebuilt contexts
    replayFieldDiffHeader: string
    replayFieldDiffCount: (count: number) => string
    replayFieldDiffToggle: string
    replayFieldDiffMore: (remaining: number) => string
    replayDiffStoredLabel: string
    replayDiffRebuiltLabel: string
    replayDiffNoDetail: string
  }
  assumptions: {
    title: string
    showAssumptions: string
    hideAssumptions: string
    modeLabel: string
    modeAuto: string
    modeLive: string
    modeRegression: string
    modeHint: string
    modeBadgeLive: string
    modeBadgeAuto: string
    modeBadgeRegression: string
    refMultipleLabel: string
    horizonsLabel: string
    returnsLabel: string
    epsAnchorLabel: string
    epsTrailing: string
    epsForward: string
    epsConsensus: string
    epsUser: string
    epsSecAnnual: string
    epsSecTtm: string
    userEpsLabel: string
    resetDefaults: string
  }
  matrix: {
    title: string
    subtitle: string
    formulaVersion: string
    fingerprint: string
    statusComputed: string
    statusNotComputed: string
    scenariosCount: (count: number) => string
    filterHorizon: string
    filterReturn: string
    all: string
    colHorizon: string
    colReturn: string
    colExitMultiple: string
    colExitPrice: string
    colTerminalEps: string
    colStartAnchor: string
    colGrowthYears: string
    colCagr: string
    colTotalGrowth: string
    notComputable: string
    readingNotes: string
    notesToggle: string
    uncomputableMatrixNotice: string
    unavailableInputsLabel: string
    unavailableItemFallback: string
    computedLimitationsNotice: string
    computedLimitationsSubtitle: string
    auditTitle: string
    calculationSteps: string
    mathematicallyVerified: string
    notComputableReason: string
    operandsLabel: string
    formulaLabel: string
    resultLabel: string
    sourceEvidence: string
    marketPriceFact: string
    startEpsFact: string
    exitMultipleFact: string
    secFilingProvenance: string
    userAssumptionsHeader: string
    verifiedFactsHeader: string
    missingOrUnvalidatedHeader: string
  userSpecifiedBadge: string
  sourcedFactBadge: string
  secLinkedFactBadge: string
  providerSourcedBadge: string
  descriptiveOnlyBadge: string
  sourceLabel: string
  sampleSizeLabel: string
  periodLabel: string
  eligibilityLabel: string
  eligibilityProductionDistribution: string
  eligibilityHistoricalBand: string
  eligibilityUserSpecified: string
  productionDistributionName: string
  productionPfcfDistributionName: string
  vendorPeBandName: string
  productionDistributionHeader: string
  productionPfcfDistributionHeader: string
  productionDistributionEligibleHeader: string
  statusLabel: string
  qualifyingObservationsLabel: string
  observationsLabel: string
  minObservationsLabel: string
  samplePeriodLabel: string
  percentileLabel: string
  currentPeLabel: string
  currentPfcfLabel: string
  asOfRuleLabel: string
  datasetIdentityLabel: string
    eligibleReferenceBadge: string
    observationContractId: string
    accessionLabel: string
    filingFormLabel: string
    conceptLabel: string
    toggleRowAudit: string
    consensusReferenceHeader: string
    consensusEpsLabel: string
    consensusEpsUnavailableLabel: string
    consensusSourcePeriodLabel: string
    consensusPeriodEndLabel: string
    consensusTargetPeriodEndLabel: string
    consensusToleranceLabel: string
    daysUnitLabel: string
    undeclaredValueLabel: string
    consensusGapLabel: string
    consensusGapUnavailableLabel: string
    startEpsPeriodLabel: string
    startEpsPeriodStart: string
    startEpsPeriodEnd: string
    startEpsPeriodUndeclared: string
    startEpsPeriodDeclared: string
    startEpsCoverageAssumed: string
    startEpsCoverageDeclared: string
    startEpsPeriodUnavailable: string
    anchorNatureDirectFiling: string
    anchorNatureDerived: string
    anchorNatureProviderReported: string
    startEpsAvailableAt: string
    startEpsDerivedComponentsHeader: string
    startEpsAnnualComparisonLabel: string
    startEpsAnnualComparisonAgrees: string
    startEpsAnnualDifferenceKept: string
    // Dividend / Total Return
    dividendSectionTitle: string
    dividendNotAvailable: string
    dividendUnavailable: string
    dividendPerShare: string
    dividendSource: string
    dividendPeriodLabel: string
    dividendConventions: string
    conventionCashRetained: string
    conventionReinvested: string
    priceOnlyBasis: string
    comparisonTableTitle: string
    comparisonHorizon: string
    comparisonReturn: string
    comparisonExitMultiple: string
    comparisonPriceOnly: string
    comparisonCashRetained: string
    comparisonReinvested: string
    comparisonExitPrice: string
    comparisonTerminalEps: string
    comparisonEpsCagr: string
    comparisonDeltaExitPrice: string
    comparisonDeltaTerminalEps: string
    comparisonDeltaCagr: string
    baselineLabel: string
    cashRetainedLabel: string
    reinvestedLabel: string
    formulaCashRetained: string
    formulaReinvested: string
  }
  export: {
    sectionTitle: string
    json: string
    csv: string
    jsonHint: string
    csvHint: string
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

