import React, { useCallback, useEffect, useState } from 'react'
import {
  ResearchApiError,
  getResearchCatalogue,
  getResearchMetric,
  getResearchObservationEvidence,
  runResearchCalculation,
} from '../services/researchApi'
import {
  ResearchCalculation,
  ResearchCatalogue,
  ResearchMetric,
  ResearchMetricDetail,
  ResearchObservation,
} from '../types/research'
import { useI18n } from '../i18n'
import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  FlaskConical,
  Search,
} from 'lucide-react'

const formatNumber = (value: number | null | undefined, digits = 6): string => {
  if (value === null || value === undefined) return '—'
  return value.toLocaleString('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

const formatCompact = (value: number | null | undefined): string => {
  if (value === null || value === undefined) return '—'
  const absolute = Math.abs(value)
  if (absolute >= 1e12) return `${(value / 1e12).toFixed(3)}T`
  if (absolute >= 1e9) return `${(value / 1e9).toFixed(3)}B`
  if (absolute >= 1e6) return `${(value / 1e6).toFixed(3)}M`
  return value.toLocaleString('en-US', { maximumFractionDigits: 2 })
}

const card = 'bg-white rounded-xl border border-slate-200 p-4 shadow-xs'
const label = 'block text-[11px] font-semibold text-slate-600 mb-1'
const input =
  'w-full px-2.5 py-1.5 bg-white border border-slate-200 rounded text-xs font-mono text-slate-800 focus:outline-none focus:ring-1 focus:ring-blue-500'
const select =
  'w-full px-2.5 py-1.5 bg-white border border-slate-200 rounded text-xs text-slate-800 focus:outline-none focus:ring-1 focus:ring-blue-500'

/**
 * The research panel.
 *
 * A user chooses a research metric, states a multiple and a market value,
 * and reads the figure and the evidence behind it. Nothing here reaches
 * the production analysis path: this panel talks only to the research API,
 * and every figure it shows says that it is a research figure.
 */
const ResearchPanel: React.FC = () => {
  const { t } = useI18n()
  const [catalogue, setCatalogue] = useState<ResearchCatalogue | null>(null)
  const [selectedId, setSelectedId] = useState<string>('')
  const [detail, setDetail] = useState<ResearchMetricDetail | null>(null)
  const [evidence, setEvidence] = useState<Record<string, any> | null>(null)
  const [evidenceDate, setEvidenceDate] = useState<string>('')
  const [multipleSource, setMultipleSource] = useState<string>('HISTORY_MEDIAN')
  const [multipleValue, setMultipleValue] = useState<string>('')
  const [observationDate, setObservationDate] = useState<string>('')
  const [numeratorSource, setNumeratorSource] = useState<string>('OBSERVATION')
  const [numeratorValue, setNumeratorValue] = useState<string>('')
  const [numeratorDate, setNumeratorDate] = useState<string>('')
  const [result, setResult] = useState<ResearchCalculation | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<boolean>(false)

  useEffect(() => {
    let cancelled = false
    getResearchCatalogue()
      .then((payload) => {
        if (!cancelled) setCatalogue(payload)
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const metric: ResearchMetric | null =
    detail?.metric ??
    catalogue?.metrics.find((item) => item.metric_id === selectedId) ??
    null

  const handleSelect = useCallback(
    async (metricId: string) => {
      setSelectedId(metricId)
      setResult(null)
      setEvidence(null)
      setEvidenceDate('')
      setError(null)
      if (!metricId) {
        setDetail(null)
        return
      }
      try {
        const payload = await getResearchMetric(metricId)
        setDetail(payload)
      } catch (err: any) {
        setError(err.message)
      }
    },
    [],
  )

  const handleCalculate = useCallback(async () => {
    if (!selectedId) return
    setBusy(true)
    setError(null)
    try {
      const payload = await runResearchCalculation({
        metric_id: selectedId,
        multiple_source: multipleSource,
        multiple: multipleValue ? Number(multipleValue) : null,
        observation_date: observationDate || null,
        numerator_source: numeratorSource,
        numerator_value: numeratorValue ? Number(numeratorValue) : null,
        numerator_date: numeratorDate || null,
      })
      setResult(payload)
    } catch (err: any) {
      setResult(null)
      const refusal = err instanceof ResearchApiError ? err.refusal : undefined
      setError(refusal ? `${refusal.reason_code}: ${refusal.detail}` : err.message)
    } finally {
      setBusy(false)
    }
  }, [
    selectedId,
    multipleSource,
    multipleValue,
    observationDate,
    numeratorSource,
    numeratorValue,
    numeratorDate,
  ])

  const handleOpenEvidence = useCallback(
    async (date: string) => {
      if (!selectedId) return
      setError(null)
      try {
        const payload = await getResearchObservationEvidence(selectedId, date)
        setEvidence(payload)
        setEvidenceDate(date)
      } catch (err: any) {
        setError(err.message)
      }
    },
    [selectedId],
  )

  const observations: ResearchObservation[] = detail?.observations ?? []
  const validObservations = observations.filter((o) => o.value !== null)
  const refusedObservations = observations.filter((o) => o.value === null)

  return (
    <div className="space-y-4">
      {/* The research-only notice. It is the first thing on the page and it
          is not dismissible: a research figure is never a valuation
          reference, and the interface says so before any figure is shown. */}
      <div
        data-testid="research-notice"
        className="p-4 bg-amber-50 border border-amber-200 rounded-xl text-amber-900 text-xs"
      >
        <div className="flex items-start gap-2.5">
          <FlaskConical className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
          <div>
            <span className="font-semibold block mb-0.5">
              {t.research.bannerTitle}
            </span>
            <span>
              {catalogue?.research_use_notice || t.research.bannerBody}
            </span>
          </div>
        </div>
      </div>

      {error && (
        <div
          data-testid="research-error"
          className="p-4 bg-rose-50 border border-rose-200 rounded-xl text-rose-900 text-xs flex items-start gap-2.5"
        >
          <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
          <div className="flex-1">
            <span className="font-semibold block mb-0.5">
              {t.research.errorTitle}
            </span>
            <span>{error}</span>
          </div>
        </div>
      )}

      {/* The metric selection. There is no default: the user chooses. */}
      <div className={card}>
        <label className={label}>{t.research.metricLabel}</label>
        <select
          data-testid="research-metric-select"
          value={selectedId}
          onChange={(e) => handleSelect(e.target.value)}
          className={select}
        >
          <option value="">{t.research.selectMetricPrompt}</option>
          {(catalogue?.metrics ?? []).map((item) => (
            <option key={item.metric_id} value={item.metric_id}>
              {item.metric_id}
            </option>
          ))}
        </select>
        {metric && (
          <p className="mt-1.5 text-[11px] text-slate-500 leading-relaxed">
            {metric.research_purpose}
          </p>
        )}
      </div>

      {metric && (
        <>
          {/* What the metric is, and what it holds. */}
          <div className={card} data-testid="research-metric-card">
            <h2 className="text-sm font-bold text-slate-900 mb-1">
              {metric.metric_label}
            </h2>
            <div className="font-mono text-[11px] bg-slate-50 border border-slate-200 rounded p-2 mb-3 break-words">
              {metric.formula_expression}
            </div>
            {/* The distribution's state. The three states are told apart: a
                distribution that rests on too little evidence says so, and a
                distribution that could not be built says why. Neither is a
                statement about production eligibility, which the notice
                above already settles. */}
            <div
              data-testid="research-distribution-status"
              data-status={metric.status}
              className={`mb-3 p-2.5 rounded border text-[11px] ${
                metric.status === 'RESEARCH_THIN_SAMPLE'
                  ? 'bg-amber-50 border-amber-200 text-amber-900'
                  : metric.status === 'RESEARCH_UNAVAILABLE'
                    ? 'bg-rose-50 border-rose-200 text-rose-900'
                    : 'bg-emerald-50 border-emerald-200 text-emerald-900'
              }`}
            >
              <span className="font-semibold block mb-0.5">
                {metric.status === 'RESEARCH_THIN_SAMPLE'
                  ? t.research.thinSampleTitle
                  : metric.status === 'RESEARCH_UNAVAILABLE'
                    ? t.research.unavailableTitle
                    : t.research.distributionTitle}
              </span>
              <span>
                {metric.status === 'RESEARCH_THIN_SAMPLE'
                  ? t.research.thinSampleBody
                  : metric.status === 'RESEARCH_UNAVAILABLE'
                    ? metric.reason_detail || t.research.unavailableBody
                    : t.research.distributionBody}
              </span>
              <span className="block mt-1 font-mono">
                {t.research.validObservations} {metric.sample_count} /{' '}
                {t.research.thresholdLabel} {metric.min_observations_for_description}
                {' · '}
                {t.research.refusedObservations} {metric.refused_count}
              </span>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-3">
              <div>
                <span className="text-[10px] text-slate-500 block">
                  {t.research.validObservations}
                </span>
                <span
                  data-testid="research-valid-count"
                  className="text-sm font-bold font-mono text-emerald-700"
                >
                  {metric.sample_count}
                </span>
              </div>
              <div>
                <span className="text-[10px] text-slate-500 block">
                  {t.research.refusedObservations}
                </span>
                <span className="text-sm font-bold font-mono text-slate-700">
                  {metric.refused_count}
                </span>
              </div>
              <div>
                <span className="text-[10px] text-slate-500 block">
                  {t.research.medianLabel}
                </span>
                <span
                  data-testid="research-median"
                  className="text-sm font-bold font-mono text-slate-900"
                >
                  {formatNumber(metric.median)}
                </span>
              </div>
              <div>
                <span className="text-[10px] text-slate-500 block">
                  {t.research.meanLabel}
                </span>
                <span className="text-sm font-bold font-mono text-slate-900">
                  {formatNumber(metric.mean)}
                </span>
              </div>
            </div>
            <div className="text-[11px] text-slate-600 space-y-1">
              <p>
                <span className="text-slate-400">{t.research.samplePeriod}: </span>
                {metric.period_start} … {metric.period_end} ·{' '}
                {t.research.stdLabel} {formatNumber(metric.std)} ·{' '}
                {t.research.minLabel} {formatNumber(metric.minimum)} ·{' '}
                {t.research.maxLabel} {formatNumber(metric.maximum)}
              </p>
              <p>
                <span className="text-slate-400">{t.research.numeratorLabel}: </span>
                {metric.numerator_label}
              </p>
              <p>
                <span className="text-slate-400">{t.research.formulaVersion}: </span>
                <span className="font-mono">{metric.formula_version}</span> ·{' '}
                <span className="font-mono">{metric.input_set_id.slice(0, 16)}</span>
              </p>
            </div>

            {/* Why it is not a production reference. This is not a warning
                line: the metric is structurally ineligible, and the panel
                says what makes it so. */}
            <div
              data-testid="research-production-refusal"
              className="mt-3 p-2.5 bg-slate-50 border border-slate-200 rounded text-[11px] text-slate-700"
            >
              <span className="font-semibold block mb-1">
                {t.research.notProductionTitle}
              </span>
              <ul className="space-y-1">
                {Object.entries(metric.registry_standing).map(([role, standing]) => (
                  <li key={role} className="flex flex-wrap gap-x-2">
                    <span className="font-mono text-slate-500">{role}</span>
                    {Object.values(standing).map((record) => (
                      <span key={record.element} className="text-slate-600">
                        {record.element} → {record.registry_decision}
                        {record.reason_code ? ` (${record.reason_code})` : ''}
                      </span>
                    ))}
                  </li>
                ))}
              </ul>
            </div>

            {metric.data_limitations.length > 0 && (
              <details className="mt-2 text-[11px] text-slate-600">
                <summary className="cursor-pointer font-semibold text-slate-700">
                  {t.research.limitationsTitle}
                </summary>
                <ul className="mt-1 list-disc pl-4 space-y-0.5">
                  {metric.data_limitations.map((limitation) => (
                    <li key={limitation}>{limitation}</li>
                  ))}
                </ul>
              </details>
            )}

            {Object.keys(metric.basis_breaks).length > 0 && (
              <details className="mt-2 text-[11px] text-slate-600">
                <summary className="cursor-pointer font-semibold text-slate-700">
                  {t.research.basisBreaksTitle} ({Object.keys(metric.basis_breaks).length})
                </summary>
                <ul className="mt-1 space-y-0.5">
                  {Object.entries(metric.basis_breaks).map(([note, dates]) => (
                    <li key={note}>
                      {note}
                      <span className="text-slate-400">
                        {' '}
                        ({dates.length} {t.research.datesLabel})
                      </span>
                    </li>
                  ))}
                </ul>
              </details>
            )}

            {metric.prior_period_revisions.length > 0 && (
              <details className="mt-2 text-[11px] text-slate-600">
                <summary className="cursor-pointer font-semibold text-slate-700">
                  {t.research.revisionsTitle} ({metric.prior_period_revisions.length})
                </summary>
                <div className="mt-1 overflow-x-auto">
                  <table className="w-full text-[10px] font-mono">
                    <thead>
                      <tr className="text-slate-400 text-left">
                        <th className="py-0.5 pr-2">{t.research.periodLabel}</th>
                        <th className="py-0.5 pr-2">old</th>
                        <th className="py-0.5 pr-2">new</th>
                        <th className="py-0.5 pr-2">diff</th>
                        <th className="py-0.5">{t.research.detectedLabel}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {metric.prior_period_revisions.map((revision) => (
                        <tr key={`${revision.role}-${revision.period_end}`}>
                          <td className="py-0.5 pr-2">
                            {revision.period_end}
                          </td>
                          <td className="py-0.5 pr-2">
                            {formatCompact(revision.old_value)}
                          </td>
                          <td className="py-0.5 pr-2">
                            {formatCompact(revision.new_value)}
                          </td>
                          <td className="py-0.5 pr-2">
                            {formatCompact(revision.difference)}
                          </td>
                          <td className="py-0.5">
                            {revision.detected_at_evaluation_date}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
            )}
          </div>

          {/* The reverse calculation. */}
          <div className={card} data-testid="research-calculator">
            <h2 className="text-sm font-bold text-slate-900 mb-3">
              {t.research.calculatorTitle}
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className={label}>{t.research.multipleLabel}</label>
                <select
                  data-testid="research-multiple-source"
                  value={multipleSource}
                  onChange={(e) => setMultipleSource(e.target.value)}
                  className={select}
                >
                  <option value="HISTORY_MEDIAN">{t.research.multipleMedian}</option>
                  <option value="OBSERVATION">
                    {t.research.multipleObservation}
                  </option>
                  <option value="USER_SUPPLIED">{t.research.multipleUser}</option>
                </select>
                {multipleSource === 'OBSERVATION' && (
                  <input
                    data-testid="research-observation-date"
                    type="text"
                    value={observationDate}
                    onChange={(e) => setObservationDate(e.target.value)}
                    placeholder="2026-07-29"
                    className={`${input} mt-1.5`}
                  />
                )}
                {multipleSource === 'USER_SUPPLIED' && (
                  <input
                    data-testid="research-multiple-value"
                    type="number"
                    step="0.000001"
                    value={multipleValue}
                    onChange={(e) => setMultipleValue(e.target.value)}
                    placeholder="6.403373"
                    className={`${input} mt-1.5`}
                  />
                )}
              </div>
              <div>
                <label className={label}>{t.research.numeratorLabel}</label>
                <select
                  data-testid="research-numerator-source"
                  value={numeratorSource}
                  onChange={(e) => setNumeratorSource(e.target.value)}
                  className={select}
                >
                  <option value="OBSERVATION">
                    {t.research.numeratorObservation}
                  </option>
                  <option value="USER_SUPPLIED">{t.research.numeratorUser}</option>
                </select>
                {numeratorSource === 'OBSERVATION' ? (
                  <input
                    data-testid="research-numerator-date"
                    type="text"
                    value={numeratorDate}
                    onChange={(e) => setNumeratorDate(e.target.value)}
                    placeholder={t.research.latestValidDate}
                    className={`${input} mt-1.5`}
                  />
                ) : (
                  <input
                    data-testid="research-numerator-value"
                    type="number"
                    step="1"
                    value={numeratorValue}
                    onChange={(e) => setNumeratorValue(e.target.value)}
                    placeholder="250000000000"
                    className={`${input} mt-1.5`}
                  />
                )}
              </div>
            </div>
            <button
              type="button"
              data-testid="research-calculate"
              onClick={handleCalculate}
              disabled={busy || !selectedId}
              className="mt-3 px-4 py-2 bg-amber-600 hover:bg-amber-700 active:bg-amber-800 text-white rounded-lg text-xs font-semibold flex items-center justify-center gap-2 transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed shadow-xs"
            >
              <Search className="w-3.5 h-3.5" />
              <span>{busy ? t.research.calculating : t.research.calculate}</span>
            </button>
          </div>

          {/* The result, and the evidence behind it. */}
          {result && (
            <div className={card} data-testid="research-result">
              <h2 className="text-sm font-bold text-slate-900 mb-2">
                {t.research.resultTitle}
              </h2>
              <div className="p-3 bg-slate-50 border border-slate-200 rounded mb-3">
                <span className="text-[10px] text-slate-500 block">
                  {t.research.impliedDenominator}
                </span>
                <span
                  data-testid="research-implied-denominator"
                  className="text-lg font-bold font-mono text-slate-900 break-all"
                >
                  {formatCompact(result.implied_denominator)}
                </span>
                <span className="block text-[11px] text-slate-600 mt-1">
                  {result.implied_denominator_label}
                </span>
              </div>
              <div className="text-[11px] text-slate-600 space-y-1">
                <p>
                  <span className="text-slate-400">{t.research.multipleUsed}: </span>
                  {formatNumber(result.multiple)} — {result.multiple_label}
                </p>
                <p>
                  <span className="text-slate-400">{t.research.numeratorUsed}: </span>
                  {formatCompact(result.numerator)} — {result.numerator_label}
                </p>
                {result.multiple_source === 'USER_SUPPLIED' && (
                  <p data-testid="research-user-assumption">
                    <span className="px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 font-mono text-[10px] font-semibold">
                      {catalogue?.user_assumption_label}
                    </span>{' '}
                    {t.research.userAssumptionNote}
                  </p>
                )}
                {result.numerator_source === 'USER_SUPPLIED' && (
                  <p data-testid="research-user-assumption">
                    <span className="px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 font-mono text-[10px] font-semibold">
                      {catalogue?.user_assumption_label}
                    </span>{' '}
                    {t.research.userAssumptionNote}
                  </p>
                )}
                <p className="font-mono break-all">
                  <span className="text-slate-400">{t.research.formulaLabel}: </span>
                  {result.formula_expression}
                </p>
                <p className="font-mono break-all">
                  <span className="text-slate-400">{t.research.identityLabel}: </span>
                  {result.calculation_content_hash.slice(0, 32)} ·{' '}
                  {result.lane_input_set_id.slice(0, 16)}
                </p>
                <p>
                  <span className="text-slate-400">{t.research.notProductionTitle}: </span>
                  {result.research_use_label}
                </p>
              </div>

              {result.numerator_evidence &&
                Object.keys(result.numerator_evidence).length > 0 && (
                  <details className="mt-2 text-[11px] text-slate-600">
                    <summary className="cursor-pointer font-semibold text-slate-700">
                      {t.research.evidenceTitle}
                    </summary>
                    <pre className="mt-1 p-2 bg-slate-900 text-slate-100 rounded overflow-x-auto text-[10px] font-mono">
                      {JSON.stringify(result.numerator_evidence, null, 2)}
                    </pre>
                  </details>
                )}
            </div>
          )}

          {/* The evidence explorer: every evaluation date, published and
              refused, and the source chain of any one of them. */}
          <div className={card} data-testid="research-observations">
            <h2 className="text-sm font-bold text-slate-900 mb-1">
              {t.research.observationsTitle}
            </h2>
            <p className="text-[11px] text-slate-500 mb-2">
              {t.research.observationsNote}
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-[11px]">
                <thead>
                  <tr className="text-slate-400 text-left border-b border-slate-200">
                    <th className="py-1 pr-2">{t.research.dateLabel}</th>
                    <th className="py-1 pr-2">{t.research.valueLabel}</th>
                    <th className="py-1 pr-2">{t.research.reasonLabel}</th>
                    <th className="py-1" />
                  </tr>
                </thead>
                <tbody>
                  {observations.map((observation) => (
                    <tr
                      key={observation.evaluation_date}
                      className="border-b border-slate-100"
                    >
                      <td className="py-1 pr-2 font-mono text-slate-700">
                        {observation.evaluation_date}
                      </td>
                      <td className="py-1 pr-2 font-mono text-slate-900">
                        {observation.value !== null
                          ? formatNumber(observation.value)
                          : '—'}
                      </td>
                      <td className="py-1 pr-2 text-slate-500">
                        {observation.reason_code
                          ? `${observation.reason_code}: ${observation.reason_detail}`
                          : ''}
                      </td>
                      <td className="py-1 text-right">
                        <button
                          type="button"
                          data-testid={`research-open-${observation.evaluation_date}`}
                          onClick={() => handleOpenEvidence(observation.evaluation_date)}
                          className="text-amber-700 hover:text-amber-900 font-medium flex items-center gap-1 cursor-pointer"
                        >
                          <ChevronRight className="w-3 h-3" />
                          {t.research.viewEvidence}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-2 text-[10px] text-slate-400">
              {t.research.observationsValid} {validObservations.length} ·{' '}
              {t.research.observationsRefused} {refusedObservations.length}
            </p>
          </div>

          {evidence && evidenceDate && (
            <div className={card} data-testid="research-evidence">
              <div className="flex items-center justify-between mb-2">
                <h2 className="text-sm font-bold text-slate-900">
                  {t.research.evidenceTitle} — {evidenceDate}
                </h2>
                <button
                  type="button"
                  onClick={() => {
                    setEvidence(null)
                    setEvidenceDate('')
                  }}
                  className="text-[11px] text-slate-500 hover:text-slate-700 underline cursor-pointer"
                >
                  {t.research.closeEvidence}
                </button>
              </div>
              <EvidenceTable evidence={evidence} />
              <details className="text-[11px]">
                <summary className="cursor-pointer font-semibold text-slate-700">
                  {t.research.fullEvidence}
                </summary>
                <pre className="mt-1 p-2 bg-slate-900 text-slate-100 rounded overflow-x-auto text-[10px] font-mono max-h-96">
                  {JSON.stringify(evidence, null, 2)}
                </pre>
              </details>
            </div>
          )}
        </>
      )}
    </div>
  )
}

/**
 * The evidence of one evaluation date, as a table.
 *
 * Every input the figure rests on is a row: what it is, what it is worth,
 * the unit it is in, the period it applies to, where it came from and when
 * it became knowable. A reader does not have to read the raw payload to
 * find a source link.
 */
const EvidenceTable: React.FC<{ evidence: Record<string, any> }> = ({
  evidence,
}) => {
  const { t } = useI18n()
  const priceSource = evidence.price_source || {}
  const sharesSource = evidence.shares_source || {}
  const denominator = evidence.denominator || {}
  const bridge = evidence.bridge || {}
  const components = bridge.components || {}

  const rows: Array<{
    label: string
    value: string
    unit: string
    period: string
    source: string
    url: string | null
    known: boolean
    accession: string | null
    knowable: string | null
  }> = []

  rows.push({
    label: t.research.priceRow,
    value: formatNumber(evidence.price, 4),
    unit: evidence.price_currency || '—',
    period: priceSource.as_of_date || evidence.evaluation_date || '—',
    source: priceSource.source_file || t.research.sourceNotProvided,
    url: priceSource.source_url || null,
    known: Boolean(priceSource.source_known),
    accession: null,
    knowable: null,
  })
  rows.push({
    label: t.research.sharesRow,
    value: formatCompact(evidence.shares_outstanding),
    unit: sharesSource.unit || '—',
    period: sharesSource.as_of_date || '—',
    source: sharesSource.source_file || t.research.sourceNotProvided,
    url: sharesSource.source_url || null,
    known: Boolean(sharesSource.source_known),
    accession: evidence.shares_accession || null,
    knowable: evidence.shares_usable_date || null,
  })
  rows.push({
    label: t.research.marketCapRow,
    value: formatCompact(evidence.market_cap),
    unit: evidence.price_currency || '—',
    period: priceSource.as_of_date || evidence.evaluation_date || '—',
    source: t.research.derivedLabel,
    url: null,
    known: true,
    accession: null,
    knowable: null,
  })
  if (evidence.enterprise_value !== null && evidence.enterprise_value !== undefined) {
    rows.push({
      label: t.research.enterpriseValueRow,
      value: formatCompact(evidence.enterprise_value),
      unit: evidence.price_currency || '—',
      period: bridge.balance_sheet_date || '—',
      source: t.research.derivedLabel,
      url: null,
      known: true,
      accession: null,
      knowable: null,
    })
  }
  for (const quarter of denominator.quarters || []) {
    const span = (quarter.input_spans || [])[0] || {}
    rows.push({
      label: `${t.research.quarterRow} ${quarter.period_end}`,
      value: formatCompact(quarter.value),
      unit: quarter.unit || span.unit || '—',
      period: quarter.period_end || '—',
      source: span.source_file || t.research.sourceNotProvided,
      url: span.source_url || null,
      known: Boolean(span.source_known),
      accession: (quarter.accessions || [])[0] || null,
      knowable: quarter.knowable_from || null,
    })
  }
  for (const [name, component] of Object.entries(components)) {
    rows.push({
      label: `${t.research.bridgeRow} ${name}`,
      value: formatCompact((component as any).value),
      unit: (component as any).currency || '—',
      period: (component as any).period_end || '—',
      source: (component as any).source_file || t.research.sourceNotProvided,
      url: (component as any).source_url || null,
      known: Boolean((component as any).source_url),
      accession: (component as any).accession || null,
      knowable: (component as any).usable_date || null,
    })
  }

  return (
    <div className="overflow-x-auto mb-2" data-testid="research-evidence-table">
      <table className="w-full text-[10px]">
        <thead>
          <tr className="text-slate-400 text-left border-b border-slate-200">
            <th className="py-1 pr-2">{t.research.evidenceInputLabel}</th>
            <th className="py-1 pr-2">{t.research.evidenceValue}</th>
            <th className="py-1 pr-2">{t.research.evidenceUnit}</th>
            <th className="py-1 pr-2">{t.research.evidencePeriod}</th>
            <th className="py-1 pr-2">{t.research.evidenceSource}</th>
            <th className="py-1 pr-2">{t.research.evidenceAccession}</th>
            <th className="py-1">{t.research.evidenceKnowable}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={`${row.label}-${index}`} className="border-b border-slate-100 align-top">
              <td className="py-1 pr-2 text-slate-700">{row.label}</td>
              <td className="py-1 pr-2 font-mono text-slate-900">{row.value}</td>
              <td className="py-1 pr-2 font-mono text-slate-600">{row.unit}</td>
              <td className="py-1 pr-2 font-mono text-slate-600">{row.period}</td>
              <td className="py-1 pr-2 text-slate-600">
                {row.url ? (
                  <a
                    href={row.url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-blue-700 hover:text-blue-900 underline break-all"
                  >
                    {row.source}
                  </a>
                ) : (
                  row.source
                )}
                {!row.known && row.source === t.research.sourceNotProvided && (
                  <span className="block text-slate-400">
                    {t.research.sourceUnknown}
                  </span>
                )}
              </td>
              <td className="py-1 pr-2 font-mono text-slate-500">
                {row.accession || '—'}
              </td>
              <td className="py-1 font-mono text-slate-500">{row.knowable || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export { ResearchPanel }
export default ResearchPanel
