import React, { useCallback, useEffect, useState } from 'react'
import {
  ResearchApiError,
  compareResearchBridges,
  compareResearchHistory,
  getResearchComparability,
  getResearchDefinitions,
  runResearchSensitivity,
} from '../services/researchApi'
import {
  ResearchComparability,
  ResearchComparison,
  ResearchMetricDefinition,
  ResearchSensitivity,
} from '../types/research'
import { useI18n } from '../i18n'
import { AlertTriangle, ArrowRight, GitCompareArrows, FlaskConical } from 'lucide-react'

const card = 'bg-white rounded-xl border border-slate-200 p-4 shadow-xs'
const label = 'block text-[11px] font-semibold text-slate-600 mb-1'
const input =
  'w-full px-2.5 py-1.5 bg-white border border-slate-200 rounded text-xs font-mono text-slate-800 focus:outline-none focus:ring-1 focus:ring-blue-500'
const select =
  'w-full px-2.5 py-1.5 bg-white border border-slate-200 rounded text-xs text-slate-800 focus:outline-none focus:ring-1 focus:ring-blue-500'

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

type CompareMode = 'history' | 'pair' | 'sensitivity'

/**
 * The comparison surface.
 *
 * Three comparisons, and the user chooses which one: one metric at two
 * dates, two metrics on the dates where both published, or one named
 * assumption applied to one published figure. Nothing is chosen for the
 * user, and a comparison that cannot be made says why.
 */
const ResearchCompare: React.FC = () => {
  const { t } = useI18n()
  const [mode, setMode] = useState<CompareMode>('history')
  const [definitions, setDefinitions] = useState<ResearchMetricDefinition[]>([])
  const [assumptions, setAssumptions] = useState<Record<string, any>>({})
  const [metricId, setMetricId] = useState<string>('')
  const [leftId, setLeftId] = useState<string>('')
  const [rightId, setRightId] = useState<string>('')
  const [earlierDate, setEarlierDate] = useState<string>('')
  const [laterDate, setLaterDate] = useState<string>('')
  const [sensitivityDate, setSensitivityDate] = useState<string>('')
  const [assumption, setAssumption] = useState<string>('NUMERATOR_MULTIPLIER')
  const [assumptionValue, setAssumptionValue] = useState<string>('1.1')
  const [compatibility, setCompatibility] = useState<ResearchComparability | null>(
    null,
  )
  const [comparison, setComparison] = useState<ResearchComparison | null>(null)
  const [sensitivity, setSensitivity] = useState<ResearchSensitivity | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<boolean>(false)

  useEffect(() => {
    let cancelled = false
    getResearchDefinitions()
      .then((payload) => {
        if (cancelled) return
        setDefinitions(payload.definitions)
        setAssumptions(payload.sensitivity_assumptions)
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const report = useCallback((err: unknown) => {
    const refusal = err instanceof ResearchApiError ? err.refusal : undefined
    setError(
      refusal
        ? `${refusal.reason_code}: ${refusal.detail}`
        : err instanceof Error
          ? err.message
          : String(err),
    )
  }, [])

  const runHistory = useCallback(async () => {
    setBusy(true)
    setError(null)
    setComparison(null)
    try {
      setComparison(
        await compareResearchHistory(metricId, earlierDate, laterDate),
      )
    } catch (err) {
      report(err)
    } finally {
      setBusy(false)
    }
  }, [metricId, earlierDate, laterDate, report])

  const runPair = useCallback(async () => {
    setBusy(true)
    setError(null)
    setComparison(null)
    try {
      setCompatibility(await getResearchComparability(leftId, rightId))
      setComparison(await compareResearchBridges(leftId, rightId))
    } catch (err) {
      report(err)
    } finally {
      setBusy(false)
    }
  }, [leftId, rightId, report])

  const runSensitivity = useCallback(async () => {
    setBusy(true)
    setError(null)
    setSensitivity(null)
    try {
      setSensitivity(
        await runResearchSensitivity({
          metric_id: metricId,
          evaluation_date: sensitivityDate,
          assumption,
          value: Number(assumptionValue),
        }),
      )
    } catch (err) {
      report(err)
    } finally {
      setBusy(false)
    }
  }, [metricId, sensitivityDate, assumption, assumptionValue, report])

  const metricOptions = definitions.map((definition) => (
    <option key={definition.metric_id} value={definition.metric_id}>
      {definition.metric_id}
    </option>
  ))

  return (
    <div className="space-y-4" data-testid="research-compare">
      <div className={card}>
        <h2 className="text-sm font-bold text-slate-900 mb-1 flex items-center gap-2">
          <GitCompareArrows className="w-4 h-4 text-amber-600" />
          {t.compare.title}
        </h2>
        <p className="text-[11px] text-slate-500 mb-3">{t.compare.intro}</p>
        <div className="flex flex-wrap gap-1.5 mb-3">
          {(
            [
              ['history', t.compare.modeHistory],
              ['pair', t.compare.modePair],
              ['sensitivity', t.compare.modeSensitivity],
            ] as Array<[CompareMode, string]>
          ).map(([value, text]) => (
            <button
              key={value}
              type="button"
              data-testid={`compare-mode-${value}`}
              onClick={() => {
                setMode(value)
                setError(null)
                setComparison(null)
                setSensitivity(null)
                setCompatibility(null)
              }}
              className={`px-2.5 py-1 rounded-md text-[11px] font-semibold cursor-pointer ${
                mode === value
                  ? 'bg-amber-100 text-amber-800'
                  : 'bg-slate-100 text-slate-500 hover:text-slate-800'
              }`}
            >
              {text}
            </button>
          ))}
        </div>

        {mode === 'history' && (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <label className={label}>{t.compare.metricLabel}</label>
              <select
                data-testid="compare-history-metric"
                value={metricId}
                onChange={(e) => setMetricId(e.target.value)}
                className={select}
              >
                <option value="">{t.research.selectMetricPrompt}</option>
                {metricOptions}
              </select>
            </div>
            <div>
              <label className={label}>{t.compare.earlierDateLabel}</label>
              <input
                data-testid="compare-history-earlier"
                value={earlierDate}
                onChange={(e) => setEarlierDate(e.target.value)}
                placeholder="2026-04-30"
                className={input}
              />
            </div>
            <div>
              <label className={label}>{t.compare.laterDateLabel}</label>
              <input
                data-testid="compare-history-later"
                value={laterDate}
                onChange={(e) => setLaterDate(e.target.value)}
                placeholder="2026-07-29"
                className={input}
              />
            </div>
          </div>
        )}

        {mode === 'pair' && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className={label}>{t.compare.leftLabel}</label>
              <select
                data-testid="compare-left-metric"
                value={leftId}
                onChange={(e) => setLeftId(e.target.value)}
                className={select}
              >
                <option value="">{t.research.selectMetricPrompt}</option>
                {metricOptions}
              </select>
            </div>
            <div>
              <label className={label}>{t.compare.rightLabel}</label>
              <select
                data-testid="compare-right-metric"
                value={rightId}
                onChange={(e) => setRightId(e.target.value)}
                className={select}
              >
                <option value="">{t.research.selectMetricPrompt}</option>
                {metricOptions}
              </select>
            </div>
          </div>
        )}

        {mode === 'sensitivity' && (
          <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
            <div>
              <label className={label}>{t.compare.metricLabel}</label>
              <select
                data-testid="compare-sensitivity-metric"
                value={metricId}
                onChange={(e) => setMetricId(e.target.value)}
                className={select}
              >
                <option value="">{t.research.selectMetricPrompt}</option>
                {metricOptions}
              </select>
            </div>
            <div>
              <label className={label}>{t.compare.evaluationDateLabel}</label>
              <input
                data-testid="compare-sensitivity-date"
                value={sensitivityDate}
                onChange={(e) => setSensitivityDate(e.target.value)}
                placeholder="2026-07-29"
                className={input}
              />
            </div>
            <div>
              <label className={label}>{t.compare.assumptionLabel}</label>
              <select
                data-testid="compare-sensitivity-assumption"
                value={assumption}
                onChange={(e) => setAssumption(e.target.value)}
                className={select}
              >
                {Object.keys(assumptions).map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className={label}>{t.compare.assumptionValueLabel}</label>
              <input
                data-testid="compare-sensitivity-value"
                type="number"
                step="0.01"
                value={assumptionValue}
                onChange={(e) => setAssumptionValue(e.target.value)}
                className={input}
              />
            </div>
          </div>
        )}

        <button
          type="button"
          data-testid="compare-run"
          onClick={() => {
            if (mode === 'history') void runHistory()
            else if (mode === 'pair') void runPair()
            else void runSensitivity()
          }}
          disabled={
            busy ||
            (mode === 'history' &&
              (!metricId || !earlierDate || !laterDate)) ||
            (mode === 'pair' && (!leftId || !rightId)) ||
            (mode === 'sensitivity' &&
              (!metricId || !sensitivityDate || !assumptionValue))
          }
          className="mt-3 px-4 py-2 bg-amber-600 hover:bg-amber-700 active:bg-amber-800 text-white rounded-lg text-xs font-semibold flex items-center justify-center gap-2 transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed shadow-xs"
        >
          <GitCompareArrows className="w-3.5 h-3.5" />
          <span>{busy ? t.compare.running : t.compare.run}</span>
        </button>
      </div>

      {error && (
        <div
          data-testid="compare-error"
          className="p-4 bg-rose-50 border border-rose-200 rounded-xl text-rose-900 text-xs flex items-start gap-2.5"
        >
          <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {compatibility && (
        <div className={card} data-testid="compare-compatibility">
          <h3 className="text-xs font-bold text-slate-900 mb-1">
            {t.compare.compatibilityTitle}
          </h3>
          <p
            className={`text-[11px] px-2 py-1.5 rounded border mb-2 ${
              compatibility.comparable
                ? 'bg-emerald-50 border-emerald-200 text-emerald-900'
                : 'bg-amber-50 border-amber-200 text-amber-900'
            }`}
            data-testid="compare-compatibility-statement"
          >
            {compatibility.reasons.join(' ')}
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[10px]">
            <div>
              <div className="font-semibold text-slate-700">
                {compatibility.left.metric_id}
              </div>
              <div className="font-mono text-slate-500 break-words">
                {compatibility.left.formula_expression}
              </div>
              <div className="text-slate-500">
                {t.compare.numeratorLabel}: {compatibility.left.numerator_kind} ·{' '}
                {t.compare.denominatorLabel}:{' '}
                {(compatibility.left.denominator_elements ?? []).join(', ') ||
                  '—'}
              </div>
            </div>
            <div>
              <div className="font-semibold text-slate-700">
                {compatibility.right.metric_id}
              </div>
              <div className="font-mono text-slate-500 break-words">
                {compatibility.right.formula_expression}
              </div>
              <div className="text-slate-500">
                {t.compare.numeratorLabel}:{' '}
                {compatibility.right.numerator_kind} ·{' '}
                {t.compare.denominatorLabel}:{' '}
                {(compatibility.right.denominator_elements ?? []).join(', ') ||
                  '—'}
              </div>
            </div>
          </div>
          {compatibility.differences.length > 0 && (
            <ul className="mt-2 text-[10px] text-slate-600 list-disc pl-4">
              {compatibility.differences.map((difference) => (
                <li key={difference.attribute}>
                  {difference.attribute}: {String(difference.left)} →{' '}
                  {String(difference.right)}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {comparison && comparison.comparison_kind === 'SAME_LANE_HISTORY' && (
        <div className={card} data-testid="compare-history-result">
          <h3 className="text-xs font-bold text-slate-900 mb-2">
            {t.compare.historyTitle}
          </h3>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-2">
            <div>
              <span className="text-[10px] text-slate-500 block">
                {t.compare.earlierMultipleLabel}
              </span>
              <span
                data-testid="compare-earlier-multiple"
                className="text-sm font-bold font-mono text-slate-900"
              >
                {formatNumber(comparison.comparison?.earlier_multiple)}
              </span>
            </div>
            <div>
              <span className="text-[10px] text-slate-500 block">
                {t.compare.laterMultipleLabel}
              </span>
              <span
                data-testid="compare-later-multiple"
                className="text-sm font-bold font-mono text-slate-900"
              >
                {formatNumber(comparison.comparison?.later_multiple)}
              </span>
            </div>
            <div>
              <span className="text-[10px] text-slate-500 block">
                {t.compare.absoluteChangeLabel}
              </span>
              <span
                data-testid="compare-absolute-change"
                className="text-sm font-bold font-mono text-slate-900"
              >
                {formatNumber(comparison.comparison?.absolute_change)}
              </span>
            </div>
            <div>
              <span className="text-[10px] text-slate-500 block">
                {t.compare.percentageChangeLabel}
              </span>
              <span className="text-sm font-bold font-mono text-slate-900">
                {formatNumber(
                  comparison.comparison?.percentage_change
                    ? comparison.comparison.percentage_change * 100
                    : null,
                  2,
                )}
                %
              </span>
            </div>
          </div>
          <div className="text-[10px] text-slate-600 space-y-1">
            <p>
              {t.compare.numeratorLabel}:{' '}
              {formatCompact(comparison.comparison?.earlier_numerator)} →{' '}
              {formatCompact(comparison.comparison?.later_numerator)} ·{' '}
              {t.compare.denominatorLabel}:{' '}
              {formatCompact(comparison.comparison?.earlier_denominator)} →{' '}
              {formatCompact(comparison.comparison?.later_denominator)}
            </p>
            <p className="font-mono break-all">
              {t.compare.observationHashLabel}:{' '}
              {String(comparison.earlier?.content_hash).slice(0, 16)} →{' '}
              {String(comparison.later?.content_hash).slice(0, 16)}
            </p>
            <p className="font-mono break-all">
              {t.compare.comparisonHashLabel}:{' '}
              {comparison.comparison_hash.slice(0, 24)}
            </p>
          </div>
          {(comparison.refused_between_count ?? 0) > 0 && (
            <div
              className="mt-2 p-2 bg-amber-50 border border-amber-200 rounded text-[10px] text-amber-900"
              data-testid="compare-refused-between"
            >
              <span className="font-semibold block">
                {t.compare.refusedBetweenLabel} (
                {comparison.refused_between_count})
              </span>
              <ul className="mt-1 space-y-0.5">
                {(comparison.refused_between ?? []).map((item: any) => (
                  <li key={item.evaluation_date} className="font-mono">
                    {item.evaluation_date} — {item.reason_code}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div className="mt-2 text-[10px] text-slate-500">
            {t.compare.evidenceChangesLabel}:{' '}
            {Object.entries(comparison.evidence_changes ?? {})
              .map(([key, value]) => `${key}=${String(value)}`)
              .join(' · ')}
          </div>
        </div>
      )}

      {comparison && comparison.comparison_kind === 'PAIRED_BRIDGE' && (
        <div className={card} data-testid="compare-pairs-result">
          <h3 className="text-xs font-bold text-slate-900 mb-2">
            {t.compare.pairsTitle}
          </h3>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-2">
            <div>
              <span className="text-[10px] text-slate-500 block">
                {t.compare.pairedSampleLabel}
              </span>
              <span
                data-testid="compare-paired-count"
                className="text-sm font-bold font-mono text-slate-900"
              >
                {comparison.paired_sample_count}
              </span>
            </div>
            <div>
              <span className="text-[10px] text-slate-500 block">
                {t.compare.attributableLabel}
              </span>
              <span
                data-testid="compare-attributable-count"
                className="text-sm font-bold font-mono text-slate-900"
              >
                {comparison.attributable_sample_count}
              </span>
            </div>
            <div>
              <span className="text-[10px] text-slate-500 block">
                {t.compare.unpairedLeftLabel}
              </span>
              <span className="text-sm font-bold font-mono text-slate-900">
                {(comparison.unpaired_left ?? []).length}
              </span>
            </div>
            <div>
              <span className="text-[10px] text-slate-500 block">
                {t.compare.unpairedRightLabel}
              </span>
              <span className="text-sm font-bold font-mono text-slate-900">
                {(comparison.unpaired_right ?? []).length}
              </span>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-[10px]">
              <thead>
                <tr className="text-slate-400 text-left border-b border-slate-200">
                  <th className="py-1 pr-2">{t.research.dateLabel}</th>
                  <th className="py-1 pr-2">{t.compare.evDifferenceLabel}</th>
                  <th className="py-1 pr-2">{t.compare.shortTermDifferenceLabel}</th>
                  <th className="py-1 pr-2">{t.compare.multipleDifferenceLabel}</th>
                  <th className="py-1">{t.compare.attributableColumnLabel}</th>
                </tr>
              </thead>
              <tbody>
                {(comparison.pairs ?? []).map((pair: any) => (
                  <tr key={pair.evaluation_date} className="border-b border-slate-100">
                    <td className="py-1 pr-2 font-mono text-slate-700">
                      {pair.evaluation_date}
                    </td>
                    <td className="py-1 pr-2 font-mono text-slate-900">
                      {formatCompact(pair.differences.enterprise_value)}
                    </td>
                    <td className="py-1 pr-2 font-mono text-slate-600">
                      {formatCompact(pair.differences.short_term_value_difference)}
                    </td>
                    <td className="py-1 pr-2 font-mono text-slate-900">
                      {formatNumber(pair.differences.multiple)}
                    </td>
                    <td className="py-1 text-slate-600">
                      {pair.attributable
                        ? t.compare.attributableYes
                        : pair.other_factors.join('; ')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {((comparison.unpaired_left ?? []).length > 0 ||
            (comparison.unpaired_right ?? []).length > 0) && (
            <div
              className="mt-2 p-2 bg-amber-50 border border-amber-200 rounded text-[10px] text-amber-900"
              data-testid="compare-unpaired"
            >
              <span className="font-semibold block">
                {t.compare.unpairedLabel}
              </span>
              <ul className="mt-1 space-y-0.5 font-mono">
                {[...(comparison.unpaired_left ?? []), ...(comparison.unpaired_right ?? [])].map(
                  (item: any) => (
                    <li key={`${item.side}-${item.evaluation_date}`}>
                      {item.evaluation_date} — {item.side} — {item.reason_code}
                    </li>
                  ),
                )}
              </ul>
            </div>
          )}
        </div>
      )}

      {sensitivity && (
        <div className={card} data-testid="compare-sensitivity-result">
          <h3 className="text-xs font-bold text-slate-900 mb-2 flex items-center gap-2">
            <FlaskConical className="w-3.5 h-3.5 text-amber-600" />
            {t.compare.sensitivityTitle}
          </h3>
          <div className="p-2 bg-amber-50 border border-amber-200 rounded text-[10px] text-amber-900 mb-2">
            <span className="font-mono font-semibold">
              {sensitivity.assumption.origin}
            </span>{' '}
            — {sensitivity.assumption.name} = {sensitivity.assumption.value}{' '}
            {sensitivity.assumption.unit}
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-2">
            <div>
              <span className="text-[10px] text-slate-500 block">
                {t.compare.baselineLabel}
              </span>
              <span
                data-testid="compare-baseline"
                className="text-sm font-bold font-mono text-slate-900"
              >
                {formatNumber(sensitivity.baseline.multiple)}
              </span>
            </div>
            <div>
              <span className="text-[10px] text-slate-500 block">
                {t.compare.adjustedLabel}
              </span>
              <span
                data-testid="compare-adjusted"
                className="text-sm font-bold font-mono text-slate-900"
              >
                {formatNumber(sensitivity.adjusted.multiple)}
              </span>
            </div>
            <div>
              <span className="text-[10px] text-slate-500 block">
                {t.compare.absoluteChangeLabel}
              </span>
              <span
                data-testid="compare-sensitivity-change"
                className="text-sm font-bold font-mono text-slate-900"
              >
                {formatNumber(sensitivity.change.absolute)}
              </span>
            </div>
            <div>
              <span className="text-[10px] text-slate-500 block">
                {t.compare.assumptionHashLabel}
              </span>
              <span className="text-[10px] font-mono text-slate-600 break-all">
                {sensitivity.assumption_hash.slice(0, 20)}
              </span>
            </div>
          </div>
          <p className="text-[10px] text-slate-600">{sensitivity.formula}</p>
          <p className="text-[10px] text-slate-500 mt-1">
            {sensitivity.notice}
          </p>
          <p className="text-[10px] font-mono text-slate-500 mt-1 break-all">
            {t.compare.observationHashLabel}:{' '}
            {String(sensitivity.observation.content_hash).slice(0, 16)} ·{' '}
            {t.compare.comparisonHashLabel}: {sensitivity.comparison_hash.slice(0, 16)}
          </p>
        </div>
      )}
    </div>
  )
}

export { ResearchCompare }
export default ResearchCompare
