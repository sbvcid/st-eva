import React, { useState, useEffect, useMemo } from 'react'
import {
  AnalyzeRequest,
  CoverageResponseDTO,
  IssuerCoverageDTO,
  JobDetailResponse,
} from './types/api'
import { startAnalysis, getJobStatus, getCoverage } from './services/apiClient'
import {
  downloadReverseRequirementsJson,
  downloadReverseRequirementsCsv,
} from './services/exportResult'
import { isStandaloneMode } from './services/pwa'
import { I18nProvider, useI18n, Language } from './i18n'
import { ProgressStepper } from './components/ProgressStepper'
import { ResultCards } from './components/ResultCards'
import { ReverseRequirementsMatrix } from './components/ReverseRequirementsMatrix'
import { ValuationMethods } from './components/ValuationMethods'
import { SecurityIdentityHeader } from './components/SecurityIdentityHeader'
import { EvidenceAccordion } from './components/EvidenceAccordion'
import { ResearchPanel } from './components/ResearchPanel'
import {
  AlertTriangle,
  ArrowRight,
  Compass,
  Download,
  FlaskConical,
  Languages,
  RotateCcw,
  Search,
  SlidersHorizontal,
  WifiOff,
} from 'lucide-react'

// Fallback when the coverage endpoint is unreachable: a single issuer whose
// qualified references are verified, so the first-use path never suggests an
// unsupported ticker. The full list is data-driven from /api/coverage.
const FALLBACK_QUICK_EXAMPLES = ['AAPL']

// The reference families a quick example can carry, in display order, with
// the compact tag each chip shows.
const FAMILY_ORDER: Array<{ key: 'pe' | 'ps' | 'pfcf' | 'ev_ebitda'; tag: string }> = [
  { key: 'pe', tag: 'P/E' },
  { key: 'ps', tag: 'P/S' },
  { key: 'pfcf', tag: 'P/FCF' },
  { key: 'ev_ebitda', tag: 'EV/EBITDA' },
]

const eligibleFamilies = (issuer: IssuerCoverageDTO): string[] =>
  FAMILY_ORDER.filter(({ key }) => issuer[key]?.usable_for_reference).map(({ tag }) => tag)

const QUICK_EXAMPLE_LIMIT = 5

type AppMode = 'valuation' | 'research'

const MainApp: React.FC = () => {
  const { language, setLanguage, t } = useI18n()
  const [tickerInput, setTickerInput] = useState<string>('')
  const [loading, setLoading] = useState<boolean>(false)
  const [currentJob, setCurrentJob] = useState<JobDetailResponse | null>(null)
  // The request that produced the result currently displayed. Captured so an
  // export echoes this exact submission (assumptions + mode); it is never used
  // to recompute figures. Replaced on every new submission, so a second
  // analysis never exports a previous submission's request.
  const [lastSubmittedRequest, setLastSubmittedRequest] =
    useState<AnalyzeRequest | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [isOnline, setIsOnline] = useState<boolean>(
    typeof navigator !== 'undefined' ? navigator.onLine : true
  )
  const [installPrompt, setInstallPrompt] = useState<any>(null)
  const [isStandalone, setIsStandalone] = useState<boolean>(false)
  // The two modes are separate surfaces with separate state. A research
  // calculation never touches the analysis path, and an analysis never
  // touches a research figure.
  const [appMode, setAppMode] = useState<AppMode>('valuation')
  // First-use coverage: which issuers carry which qualified production
  // reference families. Loaded once from the read-only /api/coverage summary;
  // a fetch failure degrades to the verified fallback rather than a hardcoded
  // list that could silently drift from the datasets.
  const [coverage, setCoverage] = useState<CoverageResponseDTO | null>(null)

  // Scenario assumption controls
  // Live-first by default: a normal analysis must observe real market data, not
  // silently resolve to a static regression fixture. `auto` and `regression`
  // remain explicit, user-selectable choices.
  const [mode, setMode] = useState<string>('live')
  // The settings drawer starts expanded so the execution mode and its effect on
  // data sourcing are visible on first use instead of hidden behind a toggle.
  const [showAssumptions, setShowAssumptions] = useState<boolean>(true)
  const [customReferenceMultiple, setCustomReferenceMultiple] = useState<string>('')
  const [customPsMultiple, setCustomPsMultiple] = useState<string>('')
  const [customPfcfMultiple, setCustomPfcfMultiple] = useState<string>('')
  const [customEvEbitdaMultiple, setCustomEvEbitdaMultiple] = useState<string>('')
  const [customHorizons, setCustomHorizons] = useState<string>('')
  const [customReturns, setCustomReturns] = useState<string>('')
  const [epsAnchorBasis, setEpsAnchorBasis] = useState<string>('trailing')
  const [customUserEps, setCustomUserEps] = useState<string>('')

  useEffect(() => {
    setIsStandalone(isStandaloneMode())

    const handleOnline = () => setIsOnline(true)
    const handleOffline = () => setIsOnline(false)

    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)

    const handleInstallPrompt = (e: Event) => {
      e.preventDefault()
      setInstallPrompt(e)
    }

    const handleAppInstalled = () => {
      setInstallPrompt(null)
      setIsStandalone(true)
    }

    window.addEventListener('beforeinstallprompt', handleInstallPrompt)
    window.addEventListener('appinstalled', handleAppInstalled)

    // Coverage is read-only and independent of any analysis; a failure is not
    // an error the user must act on, so the examples simply fall back.
    let cancelled = false
    getCoverage()
      .then((data) => {
        if (!cancelled) setCoverage(data)
      })
      .catch(() => {
        /* covered by the fallback below */
      })

    return () => {
      cancelled = true
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
      window.removeEventListener('beforeinstallprompt', handleInstallPrompt)
      window.removeEventListener('appinstalled', handleAppInstalled)
    }
  }, [])

  // Quick examples are the issuers the coverage summary actually qualifies,
  // richest coverage first, so the homepage reflects coverage differences
  // instead of implying every ticker supports every method. When the summary
  // is unreachable, the verified fallback stands in with no family tags.
  const quickExamples: IssuerCoverageDTO[] = useMemo(() => {
    if (!coverage) {
      return FALLBACK_QUICK_EXAMPLES.map(
        (ticker) =>
          ({
            ticker,
            pe: { status: 'UNAVAILABLE', usable_for_reference: false, sample_count: 0 },
            ps: { status: 'UNAVAILABLE', usable_for_reference: false, sample_count: 0 },
            pfcf: { status: 'UNAVAILABLE', usable_for_reference: false, sample_count: 0 },
            ev_ebitda: { status: 'UNAVAILABLE', usable_for_reference: false, sample_count: 0 },
          }) as IssuerCoverageDTO,
      )
    }
    const eligible = Object.values(coverage.issuers)
      .filter((issuer) => eligibleFamilies(issuer).length > 0)
    if (eligible.length === 0) {
      return Object.values(coverage.issuers)
        .sort((a, b) => a.ticker.localeCompare(b.ticker))
        .slice(0, QUICK_EXAMPLE_LIMIT)
    }
    return eligible
      .sort(
        (a, b) =>
          eligibleFamilies(b).length - eligibleFamilies(a).length ||
          a.ticker.localeCompare(b.ticker),
      )
      .slice(0, QUICK_EXAMPLE_LIMIT)
  }, [coverage])

  const handleInstallClick = async () => {
    if (!installPrompt) return
    try {
      await installPrompt.prompt()
      const choice = await installPrompt.userChoice
      if (choice && choice.outcome === 'accepted') {
        setInstallPrompt(null)
      }
    } catch (e) {
      console.warn('Install prompt error:', e)
    }
  }

  const handleAnalyze = async (symbolToAnalyze?: string) => {
    const symbol = (symbolToAnalyze || tickerInput).trim().toUpperCase()
    if (!symbol) return

    if (!isOnline) {
      setErrorMessage(t.offline.guard)
      return
    }

    setErrorMessage(null)
    setLoading(true)
    setCurrentJob({
      job_id: 'pending',
      ticker: symbol,
      status: 'PENDING',
      stage: 'resolving',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      result: null,
    })

    try {
      const payload: AnalyzeRequest = {
        ticker: symbol,
        mode: mode,
      }

      if (customReferenceMultiple.trim()) {
        const val = parseFloat(customReferenceMultiple.trim())
        if (!isNaN(val) && val > 0) {
          payload.reference_multiple = val
        }
      }

      if (customPsMultiple.trim()) {
        const val = parseFloat(customPsMultiple.trim())
        if (!isNaN(val) && val > 0) {
          payload.ps_multiple = val
        }
      }

      if (customPfcfMultiple.trim()) {
        const val = parseFloat(customPfcfMultiple.trim())
        if (!isNaN(val) && val > 0) {
          payload.pfcf_multiple = val
        }
      }

      if (customEvEbitdaMultiple.trim()) {
        const val = parseFloat(customEvEbitdaMultiple.trim())
        if (!isNaN(val) && val > 0) {
          payload.ev_ebitda_multiple = val
        }
      }

      if (customHorizons.trim()) {
        const hList = customHorizons
          .split(',')
          .map((x) => parseFloat(x.trim()))
          .filter((x) => !isNaN(x) && x > 0)
        if (hList.length > 0) {
          payload.reverse_horizons = hList
        }
      }

      if (customReturns.trim()) {
        const rList = customReturns
          .split(',')
          .map((x) => parseFloat(x.trim()))
          .filter((x) => !isNaN(x))
          .map((x) => (x > 1.0 ? x / 100 : x))
        if (rList.length > 0) {
          payload.required_returns = rList
        }
      }

      if (epsAnchorBasis === 'user' && customUserEps.trim()) {
        const uVal = parseFloat(customUserEps.trim())
        if (!isNaN(uVal)) {
          payload.user_eps = uVal
        }
      } else if (epsAnchorBasis !== 'trailing') {
        payload.prefer_eps_anchor = epsAnchorBasis
      }

      setLastSubmittedRequest(payload)

      const initResp = await startAnalysis(payload)
      pollJob(initResp.job_id)
    } catch (err: any) {
      setLoading(false)
      setErrorMessage(err.message || t.errors.defaultSubmitError)
      setCurrentJob(null)
    }
  }

  const pollJob = (jobId: string) => {
    let interval: any = null

    const check = async () => {
      try {
        const detail = await getJobStatus(jobId)
        setCurrentJob(detail)

        if (detail.status === 'COMPLETED' || detail.status === 'FAILED') {
          if (interval) clearInterval(interval)
          setLoading(false)
          if (detail.status === 'FAILED' && detail.error) {
            setErrorMessage(detail.error)
          }
          return true
        }
      } catch (err: any) {
        if (interval) clearInterval(interval)
        setLoading(false)
        setErrorMessage(err.message || t.errors.defaultCheckError)
        return true
      }
      return false
    }

    // Call check immediately
    void check().then((finished) => {
      if (!finished) {
        interval = setInterval(check, 350)
      }
    })
  }

  const handleReset = () => {
    setCurrentJob(null)
    setLastSubmittedRequest(null)
    setErrorMessage(null)
    setLoading(false)
    setTickerInput('')
  }

  const handleResetAssumptions = () => {
    setMode('live')
    setCustomReferenceMultiple('')
    setCustomPsMultiple('')
    setCustomPfcfMultiple('')
    setCustomEvEbitdaMultiple('')
    setCustomHorizons('')
    setCustomReturns('')
    setEpsAnchorBasis('trailing')
    setCustomUserEps('')
  }

  const handleModeChange = (next: AppMode) => {
    setAppMode(next)
    // The analysis surface is cleared when it is left, so a research figure
    // is never shown beside a valuation result and vice versa.
    if (next === 'research') {
      setCurrentJob(null)
      setLastSubmittedRequest(null)
      setErrorMessage(null)
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col items-center pt-[env(safe-area-inset-top)] pb-[env(safe-area-inset-bottom)]">
      {/* Offline Status Banner */}
      {!isOnline && (
        <div className="w-full bg-amber-600 text-white text-xs font-medium py-2 px-4 text-center flex items-center justify-center gap-2 shadow-xs transition-all">
          <WifiOff className="w-3.5 h-3.5 shrink-0" />
          <span>{t.offline.banner}</span>
        </div>
      )}

      {/* Top Header */}
      <header className="w-full border-b border-slate-200 bg-white py-3 px-4 sm:px-8 sticky top-0 z-10">
        <div className="max-w-2xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-2 cursor-pointer" onClick={handleReset}>
            <div className="w-7 h-7 rounded-lg bg-blue-600 flex items-center justify-center text-white font-black text-sm shadow-2xs">
              ST
            </div>
            <div>
              <span className="font-bold tracking-tight text-slate-900 text-base">ST-EVA</span>
              <span className="text-[11px] text-slate-400 ml-1.5 font-mono">v3.34</span>
            </div>
          </div>
          
          <div className="flex items-center gap-2.5 sm:gap-3">
            {installPrompt && !isStandalone && (
              <button
                type="button"
                onClick={handleInstallClick}
                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md bg-blue-50 hover:bg-blue-100 text-blue-700 text-xs font-semibold cursor-pointer transition-colors border border-blue-200 shadow-2xs"
                title="Install ST-EVA standalone app"
              >
                <Download className="w-3.5 h-3.5 text-blue-600" />
                <span className="hidden sm:inline">{t.header.installApp}</span>
                <span className="sm:hidden">{t.header.install}</span>
              </button>
            )}

            {/* Language Switch: 中文 | EN */}
            <div
              className="flex items-center text-xs font-semibold rounded-lg border border-slate-200 bg-slate-100 p-0.5"
              role="group"
              aria-label="Language selection"
            >
              <button
                type="button"
                onClick={() => setLanguage('zh-TW')}
                className={`px-2.5 py-1 rounded-md text-xs transition-all cursor-pointer min-h-[32px] sm:min-h-0 flex items-center justify-center ${
                  language === 'zh-TW'
                    ? 'bg-white text-blue-600 shadow-2xs font-bold'
                    : 'text-slate-500 hover:text-slate-900'
                }`}
                aria-pressed={language === 'zh-TW'}
              >
                中文
              </button>
              <span className="text-slate-300 text-[10px] select-none">|</span>
              <button
                type="button"
                onClick={() => setLanguage('en')}
                className={`px-2.5 py-1 rounded-md text-xs transition-all cursor-pointer min-h-[32px] sm:min-h-0 flex items-center justify-center ${
                  language === 'en'
                    ? 'bg-white text-blue-600 shadow-2xs font-bold'
                    : 'text-slate-500 hover:text-slate-900'
                }`}
                aria-pressed={language === 'en'}
              >
                EN
              </button>
            </div>

            <div className="hidden sm:flex items-center gap-1.5 text-xs text-slate-500 font-medium pl-1 border-l border-slate-200">
              <Compass className="w-3.5 h-3.5 text-slate-400" />
              <span>{t.header.tagline}</span>
            </div>
          </div>
        </div>
      </header>

      {/* Mode switch: the valuation surface and the research surface are
          separate. It sits in its own bar rather than in the header, so a
          narrow screen does not have to give up the header's controls. */}
      <div className="w-full border-b border-slate-200 bg-white">
        <div
          className="max-w-2xl mx-auto px-4 py-2 flex items-center gap-1.5"
          role="group"
          aria-label={t.mode.label}
        >
          <button
            type="button"
            data-testid="mode-valuation"
            onClick={() => handleModeChange('valuation')}
            className={`px-2.5 py-1 rounded-md text-xs font-semibold transition-all cursor-pointer flex items-center justify-center gap-1.5 ${
              appMode === 'valuation'
                ? 'bg-blue-50 text-blue-700 shadow-2xs'
                : 'text-slate-500 hover:text-slate-900'
            }`}
            aria-pressed={appMode === 'valuation'}
          >
            <Compass className="w-3.5 h-3.5" />
            {t.mode.valuation}
          </button>
          <button
            type="button"
            data-testid="mode-research"
            onClick={() => handleModeChange('research')}
            className={`px-2.5 py-1 rounded-md text-xs font-semibold transition-all cursor-pointer flex items-center justify-center gap-1.5 ${
              appMode === 'research'
                ? 'bg-amber-100 text-amber-800 shadow-2xs'
                : 'text-slate-500 hover:text-slate-900'
            }`}
            aria-pressed={appMode === 'research'}
          >
            <FlaskConical className="w-3.5 h-3.5" />
            {t.mode.research}
          </button>
        </div>
      </div>

      {/* Main Content Area */}
      <main className="w-full max-w-2xl px-4 py-6 sm:py-8 flex-1 flex flex-col">
        {appMode === 'research' ? (
          <ResearchPanel />
        ) : (
          <>
        {/* Hero & Search (Always accessible or prominent when no result) */}
        {!currentJob?.result && (
          <div className="mb-6 text-center sm:text-left">
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900">
              {t.hero.title}
            </h1>
            <p className="text-xs sm:text-sm text-slate-500 mt-1">
              {t.hero.subtitle}
            </p>
          </div>
        )}

        {/* Input Box */}
        <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-xs mb-6">
          <form
            onSubmit={(e) => {
              e.preventDefault()
              handleAnalyze()
            }}
            className="flex flex-col sm:flex-row gap-2.5"
          >
            <div className="relative flex-1">
              <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={tickerInput}
                onChange={(e) => setTickerInput(e.target.value.toUpperCase())}
                placeholder={t.search.placeholder}
                disabled={loading}
                className="w-full pl-9 pr-3 py-2.5 bg-slate-50 border border-slate-200 rounded-lg text-sm font-medium uppercase tracking-wider text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white transition-all disabled:opacity-50"
              />
            </div>

            <button
              type="submit"
              disabled={loading || !tickerInput.trim()}
              className="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 active:bg-blue-800 text-white rounded-lg text-sm font-semibold flex items-center justify-center gap-2 transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed shadow-xs min-h-[44px]"
            >
              <span>{loading ? t.search.analyzing : t.search.analyze}</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </form>

          {/* Assumptions Toggle */}
          <div className="mt-3 pt-2.5 border-t border-slate-100 flex items-center justify-between">
            <button
              type="button"
              onClick={() => setShowAssumptions(!showAssumptions)}
              className="flex items-center gap-1.5 text-xs text-blue-600 hover:text-blue-700 font-semibold cursor-pointer transition-colors"
            >
              <SlidersHorizontal className="w-3.5 h-3.5" />
              <span>{showAssumptions ? t.assumptions.hideAssumptions : t.assumptions.showAssumptions}</span>
            </button>

            {/* Always-visible reminder of where the numbers come from, so the
                selected mode's effect on data sourcing cannot be missed even
                after the drawer is collapsed. */}
            <span
              data-testid="mode-badge"
              className={`px-2 py-0.5 rounded text-[10px] font-mono font-semibold ${
                mode === 'regression'
                  ? 'bg-amber-100 text-amber-800'
                  : mode === 'auto'
                  ? 'bg-slate-100 text-slate-700'
                  : 'bg-emerald-100 text-emerald-800'
              }`}
            >
              {mode === 'regression'
                ? t.assumptions.modeBadgeRegression
                : mode === 'auto'
                ? t.assumptions.modeBadgeAuto
                : t.assumptions.modeBadgeLive}
            </span>
          </div>

          {/* Assumptions Configuration Drawer */}
          {showAssumptions && (
            <div className="mt-3 p-3.5 bg-slate-50/80 rounded-lg border border-slate-200/80 space-y-3 text-xs">
              <div className="flex items-center justify-between pb-1 border-b border-slate-200">
                <span className="font-bold text-slate-800">{t.assumptions.title}</span>
                <button
                  type="button"
                  onClick={handleResetAssumptions}
                  className="text-[11px] text-slate-500 hover:text-slate-700 underline cursor-pointer"
                >
                  {t.assumptions.resetDefaults}
                </button>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {/* Execution Mode */}
                <div>
                  <label className="block text-[11px] font-semibold text-slate-600 mb-1">
                    {t.assumptions.modeLabel}
                  </label>
                  <select
                    value={mode}
                    onChange={(e) => setMode(e.target.value)}
                    disabled={loading}
                    className="w-full px-2.5 py-1.5 bg-white border border-slate-200 rounded text-xs text-slate-800 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  >
                    <option value="auto">{t.assumptions.modeAuto}</option>
                    <option value="live">{t.assumptions.modeLive}</option>
                    <option value="regression">{t.assumptions.modeRegression}</option>
                  </select>
                  <p className="mt-1 text-[11px] text-slate-500 leading-relaxed">
                    {t.assumptions.modeHint}
                  </p>
                </div>

                {/* Reference P/E */}
                <div>
                  <label className="block text-[11px] font-semibold text-slate-600 mb-1">
                    {t.assumptions.refMultipleLabel}
                  </label>
                  <input
                    type="number"
                    step="0.1"
                    min="1"
                    value={customReferenceMultiple}
                    onChange={(e) => setCustomReferenceMultiple(e.target.value)}
                    placeholder="e.g. 20.0"
                    disabled={loading}
                    className="w-full px-2.5 py-1.5 bg-white border border-slate-200 rounded text-xs font-mono text-slate-800 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  />
                </div>

                  {/* Reference P/S */}
                <div>
                  <label className="block text-[11px] font-semibold text-slate-600 mb-1">
                    {t.assumptions.refPsMultipleLabel}
                  </label>
                  <input
                    type="number"
                    step="0.1"
                    min="1"
                    value={customPsMultiple}
                    onChange={(e) => setCustomPsMultiple(e.target.value)}
                    placeholder="e.g. 7.0"
                    disabled={loading}
                    className="w-full px-2.5 py-1.5 bg-white border border-slate-200 rounded text-xs font-mono text-slate-800 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  />
                </div>

                {/* Reference P/FCF */}
                <div>
                  <label className="block text-[11px] font-semibold text-slate-600 mb-1">
                    {t.assumptions.refPfcfMultipleLabel}
                  </label>
                  <input
                    type="number"
                    step="0.1"
                    min="1"
                    value={customPfcfMultiple}
                    onChange={(e) => setCustomPfcfMultiple(e.target.value)}
                    placeholder="e.g. 25.0"
                    disabled={loading}
                    className="w-full px-2.5 py-1.5 bg-white border border-slate-200 rounded text-xs font-mono text-slate-800 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  />
                </div>

                {/* Reference EV/EBITDA */}
                <div>
                  <label className="block text-[11px] font-semibold text-slate-600 mb-1">
                    {t.assumptions.refEvEbitdaMultipleLabel}
                  </label>
                  <input
                    type="number"
                    step="0.1"
                    min="1"
                    value={customEvEbitdaMultiple}
                    onChange={(e) => setCustomEvEbitdaMultiple(e.target.value)}
                    placeholder="e.g. 13.0"
                    disabled={loading}
                    className="w-full px-2.5 py-1.5 bg-white border border-slate-200 rounded text-xs font-mono text-slate-800 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  />
                </div>

              {/* Holding Horizons */}
                <div>
                  <label className="block text-[11px] font-semibold text-slate-600 mb-1">
                    {t.assumptions.horizonsLabel}
                  </label>
                  <input
                    type="text"
                    value={customHorizons}
                    onChange={(e) => setCustomHorizons(e.target.value)}
                    placeholder="e.g. 1.0, 2.0, 3.0, 5.0"
                    disabled={loading}
                    className="w-full px-2.5 py-1.5 bg-white border border-slate-200 rounded text-xs font-mono text-slate-800 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  />
                </div>

                {/* Required Returns */}
                <div>
                  <label className="block text-[11px] font-semibold text-slate-600 mb-1">
                    {t.assumptions.returnsLabel}
                  </label>
                  <input
                    type="text"
                    value={customReturns}
                    onChange={(e) => setCustomReturns(e.target.value)}
                    placeholder="e.g. 8, 10, 12, 15"
                    disabled={loading}
                    className="w-full px-2.5 py-1.5 bg-white border border-slate-200 rounded text-xs font-mono text-slate-800 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  />
                </div>

                {/* EPS Anchor Basis */}
                <div>
                  <label className="block text-[11px] font-semibold text-slate-600 mb-1">
                    {t.assumptions.epsAnchorLabel}
                  </label>
                  <select
                    value={epsAnchorBasis}
                    onChange={(e) => setEpsAnchorBasis(e.target.value)}
                    disabled={loading}
                    className="w-full px-2.5 py-1.5 bg-white border border-slate-200 rounded text-xs text-slate-800 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  >
                    <option value="trailing">{t.assumptions.epsTrailing}</option>
                    <option value="forward">{t.assumptions.epsForward}</option>
                    <option value="consensus">{t.assumptions.epsConsensus}</option>
                    <option value="SEC_ANNUAL_DILUTED_EPS">{t.assumptions.epsSecAnnual}</option>
                    <option value="SEC_TTM_FOUR_QUARTERS">{t.assumptions.epsSecTtm}</option>
                    <option value="user">{t.assumptions.epsUser}</option>
                  </select>
                </div>

                {/* User Supplied EPS (if user selected) */}
                {epsAnchorBasis === 'user' && (
                  <div>
                    <label className="block text-[11px] font-semibold text-slate-600 mb-1">
                      {t.assumptions.userEpsLabel}
                    </label>
                    <input
                      type="number"
                      step="0.01"
                      value={customUserEps}
                      onChange={(e) => setCustomUserEps(e.target.value)}
                      placeholder="e.g. 6.50"
                      disabled={loading}
                      className="w-full px-2.5 py-1.5 bg-white border border-slate-200 rounded text-xs font-mono text-slate-800 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    />
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Quick Examples — only issuers the coverage summary qualifies, each
              labelled with the reference families it actually carries. */}
          <div className="flex items-start gap-2 mt-3 pt-3 border-t border-slate-100 text-xs">
            <span className="text-slate-400 text-[11px] font-medium pt-1.5 shrink-0">
              {t.search.quickExamples}
            </span>
            <div className="flex flex-wrap gap-1.5">
              {quickExamples.map((issuer) => {
                const families = eligibleFamilies(issuer)
                return (
                  <button
                    key={issuer.ticker}
                    type="button"
                    onClick={() => {
                      setTickerInput(issuer.ticker)
                      handleAnalyze(issuer.ticker)
                    }}
                    disabled={loading}
                    title={
                      families.length > 0
                        ? `${issuer.ticker}: ${families.join(' · ')}`
                        : undefined
                    }
                    className="px-2.5 py-1 rounded bg-slate-100 hover:bg-slate-200 text-slate-700 transition-colors cursor-pointer disabled:opacity-50 min-h-[38px] sm:min-h-0"
                  >
                    <span className="font-mono text-[11px] font-medium block leading-tight">
                      {issuer.ticker}
                    </span>
                    {families.length > 0 && (
                      <span className="text-[9px] text-slate-400 block leading-tight">
                        {families.join(' · ')}
                      </span>
                    )}
                  </button>
                )
              })}
            </div>
          </div>

          {/* Coverage Notice */}
          <div className="mt-3 pt-2.5 border-t border-slate-100 text-[11px] text-slate-400 leading-normal space-y-1">
            <p>{t.search.coverageNotice}</p>
            <p>{t.search.coverageNoticeCustom}</p>
          </div>
        </div>

        {/* Global Error Notice */}
        {errorMessage && (
          <div className="mb-6 p-4 bg-rose-50 border border-rose-200 rounded-xl text-rose-900 text-xs flex items-start gap-2.5">
            <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
            <div className="flex-1">
              <span className="font-semibold block mb-0.5">{t.errors.requestErrorTitle}</span>
              <span>{errorMessage}</span>
            </div>
          </div>
        )}

        {/* Progress Stepper when running */}
        {loading && currentJob && (
          <ProgressStepper currentStage={currentJob.stage} />
        )}

        {/* Result Rendering */}
        {currentJob?.result && (
          <div className="space-y-4 animate-in fade-in duration-200">
            <div className="flex flex-wrap items-center justify-between gap-2 pb-1">
              <span data-testid="results-heading" className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                {t.results.verdictTitle}
              </span>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  data-testid="export-json"
                  title={t.export.jsonHint}
                  onClick={() => {
                    if (currentJob?.result) {
                      downloadReverseRequirementsJson(
                        currentJob.result,
                        lastSubmittedRequest,
                      )
                    }
                  }}
                  className="text-xs text-slate-600 hover:text-blue-700 font-medium flex items-center gap-1.5 cursor-pointer border border-slate-200 rounded-md px-2.5 py-1.5 bg-white hover:bg-blue-50 transition-colors shadow-2xs"
                >
                  <Download className="w-3.5 h-3.5" /> {t.export.json}
                </button>
                <button
                  type="button"
                  data-testid="export-csv"
                  title={t.export.csvHint}
                  onClick={() => {
                    if (currentJob?.result) {
                      downloadReverseRequirementsCsv(currentJob.result)
                    }
                  }}
                  className="text-xs text-slate-600 hover:text-blue-700 font-medium flex items-center gap-1.5 cursor-pointer border border-slate-200 rounded-md px-2.5 py-1.5 bg-white hover:bg-blue-50 transition-colors shadow-2xs"
                >
                  <Download className="w-3.5 h-3.5" /> {t.export.csv}
                </button>
                <button
                  onClick={handleReset}
                  className="text-xs text-blue-600 hover:text-blue-700 font-medium flex items-center gap-1 cursor-pointer"
                >
                  <RotateCcw className="w-3.5 h-3.5" /> {t.results.analyzeAnother}
                </button>
              </div>
            </div>

            <SecurityIdentityHeader
              ticker={currentJob.result.ticker}
              companyName={currentJob.result.company_name}
              currentPrice={
                currentJob.result.valuation_summary?.current_price ?? null
              }
              currency={currentJob.result.valuation_summary?.currency || null}
              asOf={currentJob.result.as_of}
              researchId={currentJob.result.research_id}
            />

            <ReverseRequirementsMatrix
              report={currentJob.result.reverse_requirements}
              currency={currentJob.result.valuation_summary?.currency || '$'}
            />

            <ValuationMethods
              report={currentJob.result.reverse_requirements}
              currency={currentJob.result.valuation_summary?.currency || '$'}
            />

            <ResultCards
              asOf={currentJob.result.as_of}
              valuation={currentJob.result.valuation_summary}
              admission={currentJob.result.admission_summary}
              replay={currentJob.result.replay_summary}
              refusalReasons={currentJob.result.refusal_reasons}
              sourceIdentifiers={currentJob.result.source_identifiers}
            />

            <EvidenceAccordion
              rawAnalysis={currentJob.result.raw_analysis}
              sourceIdentifiers={currentJob.result.source_identifiers}
            />
          </div>
        )}
          </>
        )}
      </main>

      {/* Footer */}
      <footer className="w-full border-t border-slate-200 bg-white py-4 px-4 text-center text-xs text-slate-400">
        <p>{t.footer.text}</p>
      </footer>
    </div>
  )
}

export const App: React.FC<{ initialLang?: Language }> = ({ initialLang }) => {
  return (
    <I18nProvider initialLang={initialLang}>
      <MainApp />
    </I18nProvider>
  )
}

export default App
