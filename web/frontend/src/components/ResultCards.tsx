import React from 'react'
import {
  AdmissionSummary,
  ReplaySummary,
  ValuationSummary,
} from '../types/api'
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  Repeat,
  ShieldAlert,
  TrendingUp,
} from 'lucide-react'
import { useI18n } from '../i18n'
import { MATRIX_SECTION_ID } from './ReverseRequirementsMatrix'

interface ResultCardsProps {
  asOf?: string | null
  valuation: ValuationSummary
  admission: AdmissionSummary
  replay: ReplaySummary
  refusalReasons: string[]
  sourceIdentifiers?: string[]
}

export const ResultCards: React.FC<ResultCardsProps> = ({
  asOf,
  valuation,
  admission,
  replay,
  refusalReasons,
  sourceIdentifiers = [],
}) => {
  const { t } = useI18n()
  const isRefused = admission.total_refused > 0 && admission.total_admitted === 0
  const isPartiallyRefused = admission.total_refused > 0 && admission.total_admitted > 0
  const isRegression = sourceIdentifiers.some(
    (s) => s.toLowerCase().includes('fixture') || s.toLowerCase().includes('regression')
  )

  // The headline metrics are single-point, flat-multiple references implied by
  // today's price; they are NOT reverse-requirements matrix scenarios. State
  // each one's exact calculation/assumption basis so it cannot be mistaken for
  // a return-hurdled matrix row.
  const summaryHorizonYears = valuation.summary_horizon_years ?? 1
  const referencePeBasis =
    valuation.selected_pe_basis === 'user_supplied_multiple'
      ? t.results.referencePeBasisUser
      : valuation.selected_pe_basis === 'production_historical_pe_median'
      ? t.results.referencePeBasisProduction
      : valuation.selected_pe_basis === 'historical_pe_median'
      ? t.results.referencePeBasisBand
      : valuation.selected_pe != null
      ? null
      : t.results.referencePeBasisNone
  const referencePfcfBasis =
    valuation.selected_pfcf_basis === 'user_supplied_multiple'
      ? t.results.referencePfcfBasisUser
      : valuation.selected_pfcf_basis === 'production_historical_pfcf_median'
      ? t.results.referencePfcfBasisProduction
      : valuation.selected_pfcf_basis === 'historical_pfcf_median'
      ? t.results.referencePfcfBasisBand
      : valuation.selected_pfcf != null
      ? null
      : t.results.referencePfcfBasisNone

  return (
    <div className="space-y-4">
      {/* Regression Fixture Warning Banner */}
      {isRegression && (
        <div className="bg-amber-50/90 border border-amber-300 rounded-xl p-4 text-amber-900 shadow-xs">
          <div className="flex items-start gap-2.5">
            <AlertCircle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
            <div>
              <span className="font-bold text-xs uppercase tracking-wider block text-amber-950">
                {t.results.regressionNotice}
              </span>
              <p className="text-xs text-amber-800 mt-0.5 leading-relaxed">
                {t.results.regressionNoticeDesc}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Primary Overview Card */}
      <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs">
        <div className="pt-4">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
            {t.results.headlineMetricsTitle}
          </span>
          <p className="text-[11px] text-slate-500 mt-1 leading-relaxed">
            {t.results.headlineMetricsNote}
          </p>

          {/* Key Metrics Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 pt-3">
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

          {/* Basis legend: the exact calculation/assumption basis of each
              headline metric, kept explicit so it is never read as a matrix row. */}
          <div
            data-testid="summary-basis-legend"
            className="mt-4 pt-3 border-t border-slate-100 space-y-1.5 text-[11px] text-slate-500 leading-relaxed"
          >
            <p>
              <span className="font-semibold text-slate-600">{t.results.impliedFwdEps}:</span>{' '}
              {t.results.impliedFwdEpsBasis}
            </p>
            <p>
              <span className="font-semibold text-slate-600">{t.results.reqEpsCagr}:</span>{' '}
              {t.results.reqEpsCagrBasis(summaryHorizonYears)}
            </p>
            {referencePeBasis && (
              <p>
                <span className="font-semibold text-slate-600">{t.results.referencePe}:</span>{' '}
                {referencePeBasis}
              </p>
            )}
            {(referencePfcfBasis || valuation.implied_fcf_at_reference_multiple != null) && (
              <p>
                <span className="font-semibold text-slate-600">
                  {valuation.implied_fcf_at_reference_multiple != null
                    ? `${t.results.impliedFcfReferenceLabel}: ${(valuation.implied_fcf_at_reference_multiple / 1e9).toFixed(1)}B`
                    : t.results.referencePfcf}
                  :
                </span>{' '}
                {referencePfcfBasis}
              </p>
            )}
            {valuation.selected_pfcf_basis != null && (
              <p className="text-[10px] text-slate-400 italic">
                {t.results.matrixPfcfLimitationNotice}
              </p>
            )}
            <button
              type="button"
              onClick={() => {
                const el = document.getElementById(MATRIX_SECTION_ID)
                if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
              }}
              className="inline-flex items-center gap-1 text-blue-600 hover:text-blue-700 font-medium pt-0.5 cursor-pointer"
            >
              <ArrowRight className="w-3 h-3" />
              <span>{t.results.seeMatrixLink}</span>
            </button>
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
                {t.results.admissionMetricRowCounts(
                  admission.metrics_admitted.length,
                  admission.total_admitted,
                  admission.metrics_refused?.length ?? 0,
                  admission.total_refused,
                )}
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
              <div className="mt-1 text-xs text-slate-600 space-y-0.5">
                {admission.metrics_admitted.length > 0 ? (
                  <div>
                    <span>
                      {t.results.admittedMetricsPrefix} {admission.metrics_admitted.join(', ')}
                    </span>
                  </div>
                ) : (
                  <div>{t.results.coreFactsAdmitted}</div>
                )}
                {/* The refused side of a partial admission, listed by metric so
                    the "refused" count is reconcilable with names a reader can
                    see, not only with the reason feed. */}
                {(admission.metrics_refused?.length ?? 0) > 0 && (
                  <div className="text-slate-500" data-testid="refused-metrics">
                    <span>
                      {t.results.refusedMetricsPrefix}{' '}
                      {(admission.metrics_refused ?? []).join(', ')}
                    </span>
                  </div>
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
          {replay.outcome === 'DIVERGED' && (
            <div className="mt-2 text-[10px] text-slate-500">
              {/* Observation availability classes (informational, not field diffs) */}
              {replay.availability_classes && replay.availability_classes.length > 0 && (
                <div className="mb-2">
                  <p className="font-semibold text-slate-700 mb-1">
                    {t.results.replayObsAvailabilityHeader}
                  </p>
                  <div className="flex flex-wrap gap-2 text-slate-600 font-mono">
                    {replay.availability_classes.map((item, idx) => (
                      <span key={idx} title={`${item.observation_id}: ${item.class}`}>
                        {item.observation_id}:{item.class}
                      </span>
                    ))}
                  </div>
                  <p className="text-slate-500 mt-1">
                    {t.results.replayObsAvailabilityNote}
                  </p>
                </div>
              )}
              {/* Field-level diffs between stored and rebuilt contexts */}
              {replay.field_diffs && replay.field_diffs.length > 0 && (
                <div className="mt-2">
                  <p className="font-semibold text-amber-900 mb-1">
                    {t.results.replayFieldDiffHeader}
                  </p>
                  <div className="text-xs text-amber-800 mb-1">
                    {t.results.replayFieldDiffCount(replay.field_diffs.length)}
                  </div>
                  <details className="border border-amber-200 rounded p-2 bg-amber-50 text-xs">
                    <summary className="font-medium cursor-pointer list-item">
                      {t.results.replayFieldDiffToggle}
                    </summary>
                    <div className="mt-2 space-y-1">
                      {replay.field_diffs.slice(0, 10).map((diff, idx) => (
                        <div key={idx} className="flex flex-col gap-1 text-slate-700">
                          <span className="font-mono">{diff.field}</span>
                          <div className="flex gap-2 pl-2">
                            <span className="text-red-600 text-[10px]">
                              {t.results.replayDiffStoredLabel}:
                            </span>
                            <span className="truncate max-w-[200px]">{JSON.stringify(diff.stored)}</span>
                          </div>
                          <div className="flex gap-2 pl-2">
                            <span className="text-green-600 text-[10px]">
                              {t.results.replayDiffRebuiltLabel}:
                            </span>
                            <span className="truncate max-w-[200px]">{JSON.stringify(diff.rebuilt)}</span>
                          </div>
                        </div>
                      ))}
                      {replay.field_diffs.length > 10 && (
                        <p className="text-slate-500 text-[10px] italic">
                          {t.results.replayFieldDiffMore(replay.field_diffs.length - 10)}
                        </p>
                      )}
                    </div>
                  </details>
                </div>
              )}
              {(!replay.availability_classes || replay.availability_classes.length === 0) &&
               (!replay.field_diffs || replay.field_diffs.length === 0) && (
                <p className="text-slate-500">
                  {t.results.replayDiffNoDetail}
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
