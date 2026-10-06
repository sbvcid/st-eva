import React from 'react'
import {
  AdmissionSummary,
  ReplaySummary,
  ValuationSummary,
} from '../types/api'
import {
  AlertCircle,
  Building2,
  Calendar,
  CheckCircle2,
  Repeat,
  ShieldAlert,
  TrendingUp,
} from 'lucide-react'
import { useI18n } from '../i18n'

interface ResultCardsProps {
  ticker: string
  companyName: string
  asOf?: string | null
  researchId?: string | null
  valuation: ValuationSummary
  admission: AdmissionSummary
  replay: ReplaySummary
  refusalReasons: string[]
}

export const ResultCards: React.FC<ResultCardsProps> = ({
  ticker,
  companyName,
  asOf,
  researchId,
  valuation,
  admission,
  replay,
  refusalReasons,
}) => {
  const { t } = useI18n()
  const isRefused = admission.total_refused > 0 && admission.total_admitted === 0
  const isPartiallyRefused = admission.total_refused > 0 && admission.total_admitted > 0

  return (
    <div className="space-y-4">
      {/* Primary Overview Card */}
      <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs">
        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3 pb-4 border-b border-slate-100">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-2xl font-bold tracking-tight text-slate-900">{ticker}</span>
              <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-slate-100 text-slate-600">
                {valuation.currency || 'USD'}
              </span>
            </div>
            <div className="text-sm text-slate-600 flex items-center gap-1.5 mt-0.5 font-medium">
              <Building2 className="w-4 h-4 text-slate-400 shrink-0" />
              <span>{companyName || 'Unknown Entity'}</span>
            </div>
          </div>

          <div className="flex sm:flex-col items-baseline sm:items-end gap-2 text-xs text-slate-500 font-mono">
            {asOf && (
              <span className="flex items-center gap-1">
                <Calendar className="w-3.5 h-3.5" /> As of {asOf}
              </span>
            )}
            {researchId && <span className="text-[11px] text-slate-400">ID: {researchId}</span>}
          </div>
        </div>

        {/* Key Metrics Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 pt-4">
          <div>
            <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
              {t.results.marketPrice}
            </div>
            <div className="text-lg font-bold text-slate-900 mt-0.5">
              {valuation.current_price !== null && valuation.current_price !== undefined
                ? `${valuation.currency || '$'} ${valuation.current_price.toFixed(2)}`
                : '—'}
            </div>
          </div>

          <div>
            <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
              {t.results.impliedFwdEps}
            </div>
            <div className="text-lg font-bold text-slate-900 mt-0.5">
              {valuation.forward_eps_at_reference_multiple !== null &&
              valuation.forward_eps_at_reference_multiple !== undefined
                ? `${valuation.forward_eps_at_reference_multiple.toFixed(2)}`
                : '—'}
            </div>
          </div>

          <div>
            <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
              {t.results.reqEpsCagr}
            </div>
            <div className="text-lg font-bold text-slate-900 mt-0.5">
              {valuation.required_eps_cagr !== null && valuation.required_eps_cagr !== undefined
                ? `${(valuation.required_eps_cagr * 100).toFixed(1)}%`
                : '—'}
            </div>
          </div>

          <div>
            <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
              {t.results.referencePe}
            </div>
            <div className="text-lg font-bold text-slate-900 mt-0.5">
              {valuation.selected_pe !== null && valuation.selected_pe !== undefined
                ? `${valuation.selected_pe.toFixed(1)}x`
                : '—'}
            </div>
          </div>
        </div>
      </div>

      {/* Admission Status Banner (1st Class Refusal UX) */}
      <div
        className={`rounded-xl border p-4.5 ${
          isRefused
            ? 'bg-amber-50/60 border-amber-200'
            : isPartiallyRefused
            ? 'bg-blue-50/60 border-blue-200'
            : 'bg-emerald-50/60 border-emerald-200'
        }`}
      >
        <div className="flex items-start gap-3">
          <div className="mt-0.5 shrink-0">
            {isRefused ? (
              <ShieldAlert className="w-5 h-5 text-amber-700" />
            ) : isPartiallyRefused ? (
              <AlertCircle className="w-5 h-5 text-blue-700" />
            ) : (
              <CheckCircle2 className="w-5 h-5 text-emerald-700" />
            )}
          </div>
          <div className="flex-1">
            <div className="flex items-center justify-between">
              <span
                className={`text-sm font-semibold tracking-tight ${
                  isRefused
                    ? 'text-amber-900'
                    : isPartiallyRefused
                    ? 'text-blue-900'
                    : 'text-emerald-900'
                }`}
              >
                {t.results.admissionStatus}{' '}
                {isRefused
                  ? t.results.refused
                  : isPartiallyRefused
                  ? t.results.partialAdmission
                  : t.results.admitted}
              </span>
              <span className="text-xs font-mono font-medium text-slate-600">
                {t.results.admittedCounts(admission.total_admitted, admission.total_refused)}
              </span>
            </div>

            {isRefused ? (
              <div className="mt-2 text-xs text-amber-900/90 leading-relaxed">
                <p className="font-medium">
                  {t.results.refusalExplanation}
                </p>
                {refusalReasons.length > 0 && (
                  <ul className="mt-2 list-disc list-inside space-y-1 text-amber-950 font-mono text-[11px] bg-amber-100/50 p-2.5 rounded-lg border border-amber-200/60">
                    {refusalReasons.map((reason, idx) => (
                      <li key={idx}>{reason}</li>
                    ))}
                  </ul>
                )}
              </div>
            ) : (
              <div className="mt-1 text-xs text-slate-600">
                {admission.metrics_admitted.length > 0 ? (
                  <span>
                    {t.results.admittedMetricsPrefix} {admission.metrics_admitted.join(', ')}
                  </span>
                ) : (
                  <span>{t.results.coreFactsAdmitted}</span>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Valuation Multiples Breakdown */}
      <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs">
        <div className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-3 flex items-center gap-1.5">
          <TrendingUp className="w-4 h-4 text-slate-400" />
          <span>{t.results.observedMultiples}</span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
          <div className="bg-slate-50/70 p-3 rounded-lg border border-slate-100">
            <div className="text-xs text-slate-500">{t.results.trailingPe}</div>
            <div className="font-semibold text-slate-900 mt-0.5">
              {valuation.observed_pe !== null && valuation.observed_pe !== undefined
                ? `${valuation.observed_pe.toFixed(1)}x`
                : '—'}
            </div>
          </div>

          <div className="bg-slate-50/70 p-3 rounded-lg border border-slate-100">
            <div className="text-xs text-slate-500">{t.results.ps}</div>
            <div className="font-semibold text-slate-900 mt-0.5">
              {valuation.observed_ps !== null && valuation.observed_ps !== undefined
                ? `${valuation.observed_ps.toFixed(2)}x`
                : '—'}
            </div>
          </div>

          <div className="bg-slate-50/70 p-3 rounded-lg border border-slate-100">
            <div className="text-xs text-slate-500">{t.results.pfcf}</div>
            <div className="font-semibold text-slate-900 mt-0.5">
              {valuation.observed_pfcf !== null && valuation.observed_pfcf !== undefined
                ? `${valuation.observed_pfcf.toFixed(1)}x`
                : '—'}
            </div>
          </div>

          <div className="bg-slate-50/70 p-3 rounded-lg border border-slate-100">
            <div className="text-xs text-slate-500">{t.results.evEbitda}</div>
            <div className="font-semibold text-slate-900 mt-0.5">
              {valuation.observed_ev_ebitda !== null && valuation.observed_ev_ebitda !== undefined
                ? `${valuation.observed_ev_ebitda.toFixed(1)}x`
                : '—'}
            </div>
          </div>
        </div>

        {valuation.limitations && valuation.limitations.length > 0 && (
          <div className="mt-4 pt-3 border-t border-slate-100 text-[11px] text-slate-500 space-y-0.5">
            <span className="font-semibold text-slate-700 block mb-1">
              {t.results.analyticalBoundaries}
            </span>
            {valuation.limitations.map((lim, i) => (
              <p key={i}>• {lim}</p>
            ))}
          </div>
        )}
      </div>

      {/* Replay Verification Banner */}
      <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs">
        <div className="flex items-center justify-between mb-2">
          <div className="text-xs font-semibold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
            <Repeat className="w-4 h-4 text-slate-400" />
            <span>{t.results.replayTitle}</span>
          </div>

          <span
            className={`px-2 py-0.5 rounded text-xs font-semibold font-mono ${
              replay.outcome === 'MATCH'
                ? 'bg-emerald-100 text-emerald-800'
                : replay.outcome === 'INSUFFICIENT'
                ? 'bg-slate-100 text-slate-700'
                : 'bg-amber-100 text-amber-800'
            }`}
          >
            {replay.outcome || t.results.notAttempted}
          </span>
        </div>

        <div className="text-xs text-slate-600 leading-relaxed">
          {replay.outcome === 'MATCH' ? (
            <p className="text-emerald-900 font-medium">
              {t.results.replayMatchText(asOf || '')}
            </p>
          ) : replay.outcome === 'INSUFFICIENT' ? (
            <p className="text-slate-700">
              {replay.reason || t.results.replayInsufficientDefault}
            </p>
          ) : (
            <p className="text-amber-900">
              {replay.reason || t.results.replayDivergedDefault}
            </p>
          )}

          <div className="flex flex-wrap items-center gap-4 mt-2 text-[11px] text-slate-400 font-mono">
            <span>{t.results.obsUsed(replay.observations_used)}</span>
            <span>{t.results.obsConsidered(replay.observations_considered)}</span>
            {replay.replay_fidelity && <span>{t.results.fidelity(replay.replay_fidelity)}</span>}
          </div>
        </div>
      </div>
    </div>
  )
}
