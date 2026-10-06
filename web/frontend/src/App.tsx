import React, { useState, useEffect } from 'react'
import {
  JobDetailResponse,
} from './types/api'
import { startAnalysis, getJobStatus } from './services/apiClient'
import { isStandaloneMode } from './services/pwa'
import { I18nProvider, useI18n, Language } from './i18n'
import { ProgressStepper } from './components/ProgressStepper'
import { ResultCards } from './components/ResultCards'
import { EvidenceAccordion } from './components/EvidenceAccordion'
import {
  AlertTriangle,
  ArrowRight,
  Compass,
  Download,
  Languages,
  RotateCcw,
  Search,
  WifiOff,
} from 'lucide-react'

const QUICK_EXAMPLES = ['AAPL', 'MSFT', 'MU', 'TSM']

const MainApp: React.FC = () => {
  const { language, setLanguage, t } = useI18n()
  const [tickerInput, setTickerInput] = useState<string>('')
  const [loading, setLoading] = useState<boolean>(false)
  const [currentJob, setCurrentJob] = useState<JobDetailResponse | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [isOnline, setIsOnline] = useState<boolean>(
    typeof navigator !== 'undefined' ? navigator.onLine : true
  )
  const [installPrompt, setInstallPrompt] = useState<any>(null)
  const [isStandalone, setIsStandalone] = useState<boolean>(false)

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

    return () => {
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
      window.removeEventListener('beforeinstallprompt', handleInstallPrompt)
      window.removeEventListener('appinstalled', handleAppInstalled)
    }
  }, [])

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
      const initResp = await startAnalysis({
        ticker: symbol,
        mode: symbol === '0700.HK' || symbol === 'MSFT' ? 'regression' : 'auto',
      })

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
    setErrorMessage(null)
    setLoading(false)
    setTickerInput('')
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

      {/* Main Content Area */}
      <main className="w-full max-w-2xl px-4 py-6 sm:py-8 flex-1 flex flex-col">
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

          {/* Quick Examples */}
          <div className="flex items-center gap-2 mt-3 pt-3 border-t border-slate-100 text-xs">
            <span className="text-slate-400 text-[11px] font-medium">{t.search.quickExamples}</span>
            <div className="flex flex-wrap gap-1.5">
              {QUICK_EXAMPLES.map((sym) => (
                <button
                  key={sym}
                  type="button"
                  onClick={() => {
                    setTickerInput(sym)
                    handleAnalyze(sym)
                  }}
                  disabled={loading}
                  className="px-2.5 py-1 rounded bg-slate-100 hover:bg-slate-200 text-slate-700 font-mono text-[11px] font-medium transition-colors cursor-pointer disabled:opacity-50 min-h-[32px] sm:min-h-0"
                >
                  {sym}
                </button>
              ))}
            </div>
          </div>

          {/* Coverage Notice */}
          <p className="mt-3 pt-2.5 border-t border-slate-100 text-[11px] text-slate-400 leading-normal">
            {t.search.coverageNotice}
          </p>
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
            <div className="flex items-center justify-between pb-1">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                {t.results.verdictTitle}
              </span>
              <button
                onClick={handleReset}
                className="text-xs text-blue-600 hover:text-blue-700 font-medium flex items-center gap-1 cursor-pointer"
              >
                <RotateCcw className="w-3.5 h-3.5" /> {t.results.analyzeAnother}
              </button>
            </div>

            <ResultCards
              ticker={currentJob.result.ticker}
              companyName={currentJob.result.company_name}
              asOf={currentJob.result.as_of}
              researchId={currentJob.result.research_id}
              valuation={currentJob.result.valuation_summary}
              admission={currentJob.result.admission_summary}
              replay={currentJob.result.replay_summary}
              refusalReasons={currentJob.result.refusal_reasons}
            />

            <EvidenceAccordion
              rawAnalysis={currentJob.result.raw_analysis}
              sourceIdentifiers={currentJob.result.source_identifiers}
            />
          </div>
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
