import React, { useState, useMemo } from 'react'
import {
  EpsScenarioDTO,
  ReverseRequirementsReportDTO,
} from '../types/api'
import {
  AlertCircle,
  AlertTriangle,
  Calculator,
  CheckCircle,
  ChevronDown,
  ChevronRight,
  Database,
  ExternalLink,
  FileText,
  Filter,
  Info,
  Layers,
  Percent,
  ShieldCheck,
  Table as TableIcon,
} from 'lucide-react'
import { useI18n } from '../i18n'

interface ReverseRequirementsMatrixProps {
  report?: ReverseRequirementsReportDTO | null
  currency?: string | null
}

/** Stable anchor id so the summary cards can deep-link to the matrix. */
export const MATRIX_SECTION_ID = 'reverse-requirements-matrix'

/**
 * The supporting inputs this run could not use.
 *
 * Rendered from `report.unavailable` and nowhere else, so the API, the export
 * and the UI can never disagree about what was missing. Each entry is shown
 * with the item the report names and the reason the report gave, so an
 * unavailable reference stays a named absence rather than becoming an implied
 * zero.
 */
const UnavailableList: React.FC<{
  entries: Array<Record<string, any>>
  tone: 'computed' | 'notComputed'
}> = ({ entries, tone }) => {
  const { t } = useI18n()
  return (
    <div
      data-testid="unavailable-list"
      className={`mt-2 space-y-1 p-2.5 rounded-lg border font-mono text-[11px] ${
        tone === 'notComputed'
          ? 'bg-amber-100/60 border-amber-200/60'
          : 'bg-slate-50 border-slate-200'
      }`}
    >
      <span
        className={`font-bold block ${
          tone === 'notComputed' ? 'text-amber-950' : 'text-slate-700'
        }`}
      >
        {t.matrix.unavailableInputsLabel}
      </span>
      {entries.map((u, i) => (
        <div key={i} className={tone === 'notComputed' ? '' : 'text-slate-700'}>
          • <span className="font-semibold">{u.item || t.matrix.unavailableItemFallback}:</span>{' '}
          {u.reason || JSON.stringify(u)}
        </div>
      ))}
    </div>
  )
}

/**
 * The source of an exit multiple, stated as what it is.
 *
 * A production historical P/E percentile is an observed reference drawn from a
 * point-in-time distribution; a band percentile is the vendor's P/E band; a
 * user value is the operator's own assumption. Raw source identifiers are not
 * shown to a reader as if they were labels.
 *
 * `compact` returns the same source name without the leading "Source:" prefix
 * or the period suffix, for the narrow matrix column. Both variants read the
 * one source mapping, so a row and its audit drawer cannot disagree about
 * where a multiple came from.
 */
const multipleSourceLabel = (t: any, multiple: any, compact = false): string => {
  if (!multiple) return ''
  if (compact) {
    switch (multiple.source) {
      case 'production_historical_pe_percentile':
        return t.matrix.productionDistributionName
      case 'historical_pe_band_percentile':
        return t.matrix.vendorPeBandName
      case 'user_supplied':
        return t.matrix.userSpecifiedBadge
      default:
        // An unrecognised or absent source keeps its raw identifier rather
        // than being relabelled as a band, which would misrepresent it.
        return String(multiple.source ?? '')
    }
  }
  switch (multiple.source) {
    case 'production_historical_pe_percentile':
      return `${t.matrix.sourceLabel}: ${t.matrix.productionDistributionName} (${multiple.period_label || t.matrix.percentileLabel})`
    case 'historical_pe_band_percentile':
      return `${t.matrix.sourceLabel}: ${t.matrix.vendorPeBandName} (${multiple.period_label || t.matrix.percentileLabel})`
    case 'user_supplied':
      return `${t.matrix.sourceLabel}: ${t.matrix.userSpecifiedBadge}`
    default:
      return `${t.matrix.sourceLabel}: ${multiple.source}`
  }
}

/**
 * The eligibility state of an exit multiple, in the report's own terms.
 */
const eligibilityLabel = (t: any, state?: string | null): string => {
  switch (state) {
    case 'ELIGIBLE_PRODUCTION_DISTRIBUTION':
      return t.matrix.eligibilityProductionDistribution
    case 'ELIGIBLE_HISTORICAL_BAND':
      return t.matrix.eligibilityHistoricalBand
    case 'USER_SPECIFIED':
      return t.matrix.eligibilityUserSpecified
    case 'DESCRIPTIVE_ONLY_UNVERIFIED_SAMPLE_COUNT':
    case 'DESCRIPTIVE_ONLY_INSUFFICIENT_OBSERVATIONS':
      return `${t.matrix.descriptiveOnlyBadge} (${state})`
    default:
      return state || ''
  }
}

export const ReverseRequirementsMatrix: React.FC<ReverseRequirementsMatrixProps> = ({
  report,
  currency = '$',
}) => {
  const { t } = useI18n()
  const [selectedHorizon, setSelectedHorizon] = useState<string>('ALL')
  const [selectedReturn, setSelectedReturn] = useState<string>('ALL')
  const [expandedRows, setExpandedRows] = useState<Record<number, boolean>>({})
  const [showNotes, setShowNotes] = useState<boolean>(false)

  const scenarios = report?.reverse_requirements_matrix || []
  const isNotComputed = report?.status === 'NOT_COMPUTED' || scenarios.length === 0
  // Supporting inputs the run could not use. `report.unavailable` is the only
  // source, so this is the same list the API and the CSV carry. An empty or
  // absent list must not leave an empty section behind, hence the length test
  // rather than a truthiness test on the array itself.
  const unavailable = report?.unavailable || []
  const hasUnavailable = unavailable.length > 0

  // Distinct horizons and returns for filter buttons
  const availableHorizons = useMemo(() => {
    const s = new Set<number>()
    scenarios.forEach((sc) => s.add(sc.horizon_years))
    return Array.from(s).sort((a, b) => a - b)
  }, [scenarios])

  const availableReturns = useMemo(() => {
    const s = new Set<number>()
    scenarios.forEach((sc) => s.add(sc.required_return))
    return Array.from(s).sort((a, b) => a - b)
  }, [scenarios])

  const filteredScenarios = useMemo(() => {
    return scenarios.filter((sc) => {
      if (selectedHorizon !== 'ALL' && sc.horizon_years !== parseFloat(selectedHorizon)) {
        return false
      }
      if (selectedReturn !== 'ALL' && Math.abs(sc.required_return - parseFloat(selectedReturn)) > 1e-6) {
        return false
      }
      return true
    })
  }, [scenarios, selectedHorizon, selectedReturn])

  const toggleRow = (idx: number) => {
    setExpandedRows((prev) => ({ ...prev, [idx]: !prev[idx] }))
  }

  if (!report) {
    return null
  }

  return (
    <div
      id={MATRIX_SECTION_ID}
      className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs space-y-4"
    >
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-100">
        <div>
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-lg bg-blue-50 text-blue-600">
              <TableIcon className="w-4 h-4" />
            </div>
            <h2 className="text-base font-bold text-slate-900 tracking-tight">
              {t.matrix.title}
            </h2>
            <span
              className={`px-2 py-0.5 rounded text-[11px] font-mono font-semibold ${
                report.status === 'COMPUTED'
                  ? 'bg-emerald-100 text-emerald-800'
                  : 'bg-amber-100 text-amber-800'
              }`}
            >
              {report.status === 'COMPUTED' ? t.matrix.statusComputed : t.matrix.statusNotComputed}
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">{t.matrix.subtitle}</p>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="px-2 py-0.5 bg-slate-100 rounded text-slate-600 font-mono text-[11px]">
            {report.formula_version || 'reverse-requirements/1.1'}
          </span>
          <span className="text-slate-400 font-mono text-[11px]">
            {t.matrix.scenariosCount(report.matrix_size || scenarios.length)}
          </span>
        </div>
      </div>

      {/* Uncomputable Matrix Banner */}
      {isNotComputed && (
        <div className="p-4 bg-amber-50/70 border border-amber-200 rounded-xl text-amber-900 text-xs">
          <div className="flex items-start gap-2.5">
            <AlertTriangle className="w-4 h-4 text-amber-700 shrink-0 mt-0.5" />
            <div>
              <span className="font-semibold block mb-1">
                {t.matrix.uncomputableMatrixNotice}
              </span>
              <p className="text-amber-800">
                {report.status_reason ||
                  'The calculation engine cannot construct the matrix due to missing positive EPS anchor or exit multiples.'}
              </p>
            </div>
          </div>
          {/* Rendered once, here: the matrix itself did not compute. */}
          {hasUnavailable && (
            <UnavailableList entries={unavailable} tone="notComputed" />
          )}
        </div>
      )}

      {/* Supporting-data limitations, for a matrix that did compute */}
      {!isNotComputed && hasUnavailable && (
        <div
          data-testid="limitations-section"
          className="p-4 bg-slate-50/70 border border-slate-200 rounded-xl text-slate-700 text-xs"
        >
          <div className="flex items-start gap-2.5">
            <AlertCircle className="w-4 h-4 text-slate-500 shrink-0 mt-0.5" />
            <div className="min-w-0">
              <span className="font-semibold block mb-1">
                {t.matrix.computedLimitationsNotice}
              </span>
              <p className="text-slate-600">
                {t.matrix.computedLimitationsSubtitle}
              </p>
              <UnavailableList entries={unavailable} tone="computed" />
            </div>
          </div>
        </div>
      )}

      {/* Filter Toolbar */}
      {!isNotComputed && (
        <div className="space-y-2.5 pt-1">
          <div className="flex flex-wrap items-center gap-3 text-xs">
            {/* Horizon Filter */}
            <div className="flex items-center gap-1.5">
              <span className="text-slate-500 font-medium flex items-center gap-1">
                <Filter className="w-3.5 h-3.5 text-slate-400" />
                {t.matrix.filterHorizon}:
              </span>
              <div className="flex flex-wrap gap-1">
                <button
                  type="button"
                  onClick={() => setSelectedHorizon('ALL')}
                  className={`px-2 py-0.5 rounded text-[11px] font-mono transition-colors cursor-pointer ${
                    selectedHorizon === 'ALL'
                      ? 'bg-blue-600 text-white font-semibold'
                      : 'bg-slate-100 hover:bg-slate-200 text-slate-700'
                  }`}
                >
                  {t.matrix.all}
                </button>
                {availableHorizons.map((h) => (
                  <button
                    key={h}
                    type="button"
                    onClick={() => setSelectedHorizon(h.toString())}
                    className={`px-2 py-0.5 rounded text-[11px] font-mono transition-colors cursor-pointer ${
                      selectedHorizon === h.toString()
                        ? 'bg-blue-600 text-white font-semibold'
                        : 'bg-slate-100 hover:bg-slate-200 text-slate-700'
                    }`}
                  >
                    {h}y
                  </button>
                ))}
              </div>
            </div>

            {/* Return Filter */}
            <div className="flex items-center gap-1.5 ml-0 sm:ml-2">
              <span className="text-slate-500 font-medium">{t.matrix.filterReturn}:</span>
              <div className="flex flex-wrap gap-1">
                <button
                  type="button"
                  onClick={() => setSelectedReturn('ALL')}
                  className={`px-2 py-0.5 rounded text-[11px] font-mono transition-colors cursor-pointer ${
                    selectedReturn === 'ALL'
                      ? 'bg-blue-600 text-white font-semibold'
                      : 'bg-slate-100 hover:bg-slate-200 text-slate-700'
                  }`}
                >
                  {t.matrix.all}
                </button>
                {availableReturns.map((r) => (
                  <button
                    key={r}
                    type="button"
                    onClick={() => setSelectedReturn(r.toString())}
                    className={`px-2 py-0.5 rounded text-[11px] font-mono transition-colors cursor-pointer ${
                      selectedReturn === r.toString()
                        ? 'bg-blue-600 text-white font-semibold'
                        : 'bg-slate-100 hover:bg-slate-200 text-slate-700'
                    }`}
                  >
                    {(r * 100).toFixed(0)}%
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Matrix Table */}
          <div className="border border-slate-200 rounded-lg overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200 text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
                  <th className="py-2.5 px-3">{t.matrix.colHorizon}</th>
                  <th className="py-2.5 px-3">{t.matrix.colReturn}</th>
                  <th className="py-2.5 px-3">{t.matrix.colExitMultiple}</th>
                  <th className="py-2.5 px-3">{t.matrix.colExitPrice}</th>
                  <th className="py-2.5 px-3">{t.matrix.colTerminalEps}</th>
                  <th className="py-2.5 px-3">{t.matrix.colStartAnchor}</th>
                  <th className="py-2.5 px-3">{t.matrix.colCagr}</th>
                  <th className="py-2.5 px-3">{t.matrix.colTotalGrowth}</th>
                  <th className="py-2.5 px-3 text-right"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-mono text-[12px]">
                {filteredScenarios.map((sc: EpsScenarioDTO, idx: number) => {
                  const isExpanded = !!expandedRows[idx]
                  const isCagrComputable =
                    sc.required_eps_cagr !== null && sc.required_eps_cagr !== undefined
                  const hasNotes =
                    (sc.comparison_notes && sc.comparison_notes.length > 0) ||
                    (sc.flags && sc.flags.length > 0)
                  // The consensus gap is reported only when the period the
                  // source declared lines up with this row's terminal window.
                  // When it does not, the reason that names both period ends
                  // is shown; a missing gap is never rendered as a zero.
                  const consensusGap =
                    sc.gap_vs_consensus_terminal_eps !== null &&
                    sc.gap_vs_consensus_terminal_eps !== undefined
                      ? sc.gap_vs_consensus_terminal_eps
                      : null
                  const consensusGapReason =
                    consensusGap === null && report?.consensus_reference
                      ? (sc.comparison_notes || []).find((note) =>
                          /consensus period ends|declares no readable period end|consensus is a/i.test(
                            note,
                          ),
                        ) ?? null
                      : null

                  return (
                    <React.Fragment key={idx}>
                      <tr
                        className={`hover:bg-slate-50/80 transition-colors ${
                          !isCagrComputable ? 'bg-amber-50/20' : ''
                        }`}
                      >
                        {/* Horizon */}
                        <td className="py-2 px-3 font-semibold text-slate-900">
                          {sc.horizon_years.toFixed(1)}y
                        </td>

                        {/* Req Return */}
                        <td className="py-2 px-3 text-slate-700">
                          {(sc.required_return * 100).toFixed(1)}%
                        </td>

                        {/* Exit Multiple */}
                        <td className="py-2 px-3">
                          <span className="font-semibold text-slate-900">
                            {sc.exit_multiple.value.toFixed(1)}x
                          </span>
                          <span className="text-[10px] text-slate-400 block font-sans">
                            {multipleSourceLabel(t, sc.exit_multiple, true)}
                          </span>
                        </td>

                        {/* Terminal Price */}
                        <td className="py-2 px-3 text-slate-900 font-medium">
                          {sc.required_exit_price !== null && sc.required_exit_price !== undefined
                            ? `${currency}${sc.required_exit_price.toFixed(2)}`
                            : '—'}
                        </td>

                        {/* Required EPS */}
                        <td className="py-2 px-3 text-slate-900 font-medium">
                          {sc.required_terminal_eps !== null &&
                          sc.required_terminal_eps !== undefined
                            ? `${currency}${sc.required_terminal_eps.toFixed(2)}`
                            : '—'}
                        </td>

                        {/* Start EPS Anchor */}
                        <td className="py-2 px-3 text-slate-600 text-[11px]">
                          {sc.start_eps?.value !== undefined
                            ? `${currency}${sc.start_eps.value.toFixed(2)}`
                            : '—'}
                          <span className="text-[10px] text-slate-400 block font-sans">
                            {sc.start_eps?.basis || ''}
                          </span>
                        </td>

                        {/* Req EPS CAGR */}
                        <td className="py-2 px-3">
                          {isCagrComputable ? (
                            <span
                              className={`font-semibold ${
                                (sc.required_eps_cagr || 0) >= 0
                                  ? 'text-blue-700'
                                  : 'text-rose-700'
                              }`}
                            >
                              {(sc.required_eps_cagr! >= 0 ? '+' : '') +
                                (sc.required_eps_cagr! * 100).toFixed(1)}
                              %
                            </span>
                          ) : (
                            <span
                              className="px-1.5 py-0.5 rounded text-[10px] font-sans font-medium bg-amber-100 text-amber-800"
                              title={sc.comparison_notes?.join(' ') || 'Not Computable'}
                            >
                              {t.matrix.notComputable}
                            </span>
                          )}
                        </td>

                        {/* Total EPS Growth */}
                        <td className="py-2 px-3 text-slate-700">
                          {sc.total_terminal_eps_growth !== null &&
                          sc.total_terminal_eps_growth !== undefined ? (
                            <span>
                              {(sc.total_terminal_eps_growth >= 0 ? '+' : '') +
                                (sc.total_terminal_eps_growth * 100).toFixed(1)}
                              %
                            </span>
                          ) : (
                            '—'
                          )}
                        </td>

                        {/* Expand Row Button */}
                        <td className="py-2 px-3 text-right">
                          <button
                            type="button"
                            onClick={() => toggleRow(idx)}
                            className="text-slate-400 hover:text-slate-600 p-1 cursor-pointer transition-colors"
                            title="Toggle details"
                          >
                            {isExpanded ? (
                              <ChevronDown className="w-3.5 h-3.5" />
                            ) : (
                              <ChevronRight className="w-3.5 h-3.5" />
                            )}
                          </button>
                        </td>
                      </tr>

                      {/* Expandable Scenario Detail Drawer */}
                      {isExpanded && (
                        <tr className="bg-slate-50/70 border-b border-slate-100">
                          <td colSpan={9} className="py-4 px-5 text-xs font-sans space-y-4">
                            {/* Drawer Header */}
                            <div className="flex flex-wrap items-center justify-between gap-2 pb-2.5 border-b border-slate-200">
                              <div className="flex items-center gap-2">
                                <ShieldCheck className="w-4 h-4 text-emerald-600" />
                                <span className="font-semibold text-slate-900 text-xs">
                                  {t.matrix.auditTitle}
                                </span>
                              </div>
                              <div className="flex items-center gap-2 text-[11px] font-mono">
                                <span className="px-2 py-0.5 rounded bg-emerald-100 text-emerald-800 font-semibold flex items-center gap-1">
                                  <CheckCircle className="w-3 h-3 text-emerald-600" />
                                  {t.matrix.mathematicallyVerified}
                                </span>
                                <span className="text-slate-400">
                                  {sc.formula_version || 'reverse-requirements/1.1'}
                                </span>
                              </div>
                            </div>

                            {/* Deterministic Calculation Steps */}
                            {sc.calculation_steps && sc.calculation_steps.length > 0 && (
                              <div className="space-y-2">
                                <div className="flex items-center gap-1.5 text-[11px] font-semibold text-slate-700">
                                  <Calculator className="w-3.5 h-3.5 text-blue-600" />
                                  <span>{t.matrix.calculationSteps}</span>
                                </div>
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[11px]">
                                  {sc.calculation_steps.map((step) => (
                                    <div
                                      key={step.step_number}
                                      className="p-2.5 bg-white rounded-lg border border-slate-200 shadow-2xs space-y-1.5"
                                    >
                                      <div className="flex items-center justify-between">
                                        <span className="font-bold text-slate-800 font-sans text-xs">
                                          {step.step_number}. {step.name}
                                        </span>
                                        <span
                                          className={`px-1.5 py-0.2 rounded text-[10px] ${
                                            step.status === 'COMPUTED'
                                              ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                                              : 'bg-amber-50 text-amber-700 border border-amber-200'
                                          }`}
                                        >
                                          {step.status === 'COMPUTED' ? t.matrix.mathematicallyVerified : t.matrix.notComputableReason}
                                        </span>
                                      </div>
                                      <div className="text-blue-900 bg-blue-50/50 px-2 py-1 rounded text-[10px] break-all border border-blue-100">
                                        {step.formula_expression}
                                      </div>
                                      <div className="text-[10px] text-slate-600 flex flex-wrap gap-x-2 gap-y-0.5">
                                        <span className="text-slate-400 font-sans">{t.matrix.operandsLabel}:</span>
                                        {Object.entries(step.operands || {}).map(([opKey, opVal]) => (
                                          <span key={opKey}>
                                            {opKey}={typeof opVal === 'number' ? opVal.toFixed(opVal < 1 ? 4 : 2) : String(opVal)}
                                          </span>
                                        ))}
                                      </div>
                                      <div className="pt-1 border-t border-slate-100 flex items-center justify-between text-[11px]">
                                        <span className="text-slate-500 font-sans">{t.matrix.resultLabel}:</span>
                                        <span className="font-bold text-slate-900">
                                          {step.output_value !== null && step.output_value !== undefined
                                            ? (step.output_unit === 'percent_per_annum' || step.output_unit === 'ratio'
                                                ? `${(step.output_value * 100).toFixed(2)}%`
                                                : `${currency}${step.output_value.toFixed(2)}`)
                                            : '—'}
                                        </span>
                                      </div>
                                      {step.status_reason && (
                                        <div className="text-[10px] text-amber-700 font-sans italic">
                                          {step.status_reason}
                                        </div>
                                      )}
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}

                            {/* Source Evidence & Sourced Facts */}
                            {sc.evidence && (
                              <div className="space-y-2 pt-1">
                                <div className="flex items-center gap-1.5 text-[11px] font-semibold text-slate-700">
                                  <Database className="w-3.5 h-3.5 text-indigo-600" />
                                  <span>{t.matrix.sourceEvidence}</span>
                                </div>
                                <div className="grid grid-cols-1 md:grid-cols-3 gap-2.5 font-sans text-xs">
                                  {/* Market Price Evidence */}
                                  <div className="p-3 bg-white rounded-lg border border-slate-200 shadow-2xs space-y-1.5">
                                    <div className="flex items-center justify-between">
                                      <span className="font-semibold text-slate-800 text-[11px]">
                                        {t.matrix.marketPriceFact}
                                      </span>
                                      <span className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-700 text-[10px] font-mono">
                                        {t.matrix.sourcedFactBadge}
                                      </span>
                                    </div>
                                    <div className="font-mono text-sm font-bold text-slate-900">
                                      {currency}{sc.evidence.price_evidence.value.toFixed(2)}
                                      <span className="text-xs text-slate-500 font-normal ml-1">
                                        {sc.evidence.price_evidence.currency || 'USD'}
                                      </span>
                                    </div>
                                    <div className="text-[11px] text-slate-500 space-y-0.5">
                                      <div>Provider: {sc.evidence.price_evidence.provider || 'market'}</div>
                                      <div>As-of: {sc.evidence.price_evidence.as_of || sc.as_of || 'N/A'}</div>
                                      {sc.evidence.price_evidence.observation_id && (
                                        <div className="font-mono text-[10px] text-indigo-700">
                                          {sc.evidence.price_evidence.observation_id}
                                        </div>
                                      )}
                                    </div>
                                  </div>

                                  {/* Start EPS Anchor Evidence */}
                                  <div className="p-3 bg-white rounded-lg border border-slate-200 shadow-2xs space-y-1.5">
                                    <div className="flex items-center justify-between">
                                      <span className="font-semibold text-slate-800 text-[11px]">
                                        {t.matrix.startEpsFact}
                                      </span>
                                      <span
                                        className={`px-1.5 py-0.5 rounded text-[10px] font-mono ${
                                          sc.evidence.eps_evidence.is_user_assumption
                                            ? 'bg-blue-100 text-blue-800'
                                            : sc.evidence.eps_evidence.anchor_nature === 'DIRECT_FILING'
                                            ? 'bg-emerald-100 text-emerald-800'
                                            : sc.evidence.eps_evidence.anchor_nature === 'DERIVED_FROM_DIRECT_FILINGS'
                                            ? 'bg-teal-100 text-teal-800'
                                            : sc.evidence.eps_evidence.sec_fact
                                            ? 'bg-emerald-100 text-emerald-800'
                                            : 'bg-amber-100 text-amber-800'
                                        }`}
                                      >
                                        {sc.evidence.eps_evidence.is_user_assumption
                                          ? t.matrix.userSpecifiedBadge
                                          : sc.evidence.eps_evidence.anchor_nature === 'DIRECT_FILING'
                                          ? t.matrix.anchorNatureDirectFiling
                                          : sc.evidence.eps_evidence.anchor_nature === 'DERIVED_FROM_DIRECT_FILINGS'
                                          ? t.matrix.anchorNatureDerived
                                          : sc.evidence.eps_evidence.sec_fact
                                          ? t.matrix.secLinkedFactBadge
                                          : t.matrix.providerSourcedBadge}
                                      </span>
                                    </div>
                                    <div className="font-mono text-sm font-bold text-slate-900">
                                      {currency}{sc.evidence.eps_evidence.value.toFixed(2)}
                                      <span className="text-xs text-slate-500 font-normal ml-1">
                                        {sc.evidence.eps_evidence.basis}
                                      </span>
                                    </div>
                                    <div className="text-[11px] text-slate-500 space-y-0.5">
                                      {sc.evidence.eps_evidence.period_label && (
                                        <div>
                                          {t.matrix.startEpsPeriodLabel}: {sc.evidence.eps_evidence.period_label}
                                        </div>
                                      )}
                                      <div>
                                        {sc.evidence.eps_evidence.period_undeclared_by_source
                                          ? t.matrix.startEpsCoverageAssumed
                                          : t.matrix.startEpsCoverageDeclared}
                                        : {sc.evidence.eps_evidence.months_covered} months
                                      </div>
                                      {sc.evidence.eps_evidence.period_start && (
                                        <div>
                                          {t.matrix.startEpsPeriodStart}: {sc.evidence.eps_evidence.period_start}
                                        </div>
                                      )}
                                      {sc.evidence.eps_evidence.period_end && (
                                        <div>
                                          {t.matrix.startEpsPeriodEnd}: {sc.evidence.eps_evidence.period_end}
                                        </div>
                                      )}
                                      {!sc.evidence.eps_evidence.period_start && (
                                        <div>
                                          {t.matrix.startEpsPeriodStart}: {t.matrix.startEpsPeriodUnavailable}
                                        </div>
                                      )}
                                      {!sc.evidence.eps_evidence.period_end && (
                                        <div>
                                          {t.matrix.startEpsPeriodEnd}: {t.matrix.startEpsPeriodUnavailable}
                                        </div>
                                      )}
                                      {sc.evidence.eps_evidence.period_undeclared_by_source && (
                                        <div className="text-amber-700 font-semibold">
                                          {t.matrix.startEpsPeriodUndeclared}
                                        </div>
                                      )}
                                      <div>Provider: {sc.evidence.eps_evidence.provider || 'reported'}</div>
                                      {sc.evidence.eps_evidence.available_at && (
                                        <div>
                                          {t.matrix.startEpsAvailableAt}: {sc.evidence.eps_evidence.available_at}
                                          {sc.evidence.eps_evidence.available_at_basis ? ` (${sc.evidence.eps_evidence.available_at_basis})` : ''}
                                        </div>
                                      )}
                                      {sc.evidence.eps_evidence.observation_id && (
                                        <div className="font-mono text-[10px] text-indigo-700">
                                          {sc.evidence.eps_evidence.observation_id}
                                        </div>
                                      )}
                                      {/* Derived twelve-month anchor: the four directly stated quarterly
                                          filings it sums, so the engine's arithmetic is checkable. */}
                                      {(sc.evidence.eps_evidence.sec_components?.length || 0) > 0 && (
                                        <div className="mt-1 pt-1 border-t border-teal-200 space-y-0.5 text-[10px] font-mono text-teal-800">
                                          <div className="font-semibold">{t.matrix.startEpsDerivedComponentsHeader}</div>
                                          {(sc.evidence.eps_evidence.sec_components || []).map((comp, ci) => (
                                            <div key={ci}>
                                              {comp.period_start || '?'} .. {comp.period_end} = {comp.value} ({comp.form} accn {comp.accession}{comp.evidence_class === 'furnished' ? ', furnished' : ''})
                                            </div>
                                          ))}
                                          {sc.evidence.eps_evidence.annual_comparison?.comparable && (
                                            <div className="text-[9px] text-teal-700 italic">
                                              {t.matrix.startEpsAnnualComparisonLabel}: {sc.evidence.eps_evidence.annual_comparison.annual_value} —{' '}
                                              {sc.evidence.eps_evidence.annual_comparison.agrees
                                                ? t.matrix.startEpsAnnualComparisonAgrees
                                                : t.matrix.startEpsAnnualDifferenceKept}
                                            </div>
                                          )}
                                        </div>
                                      )}
                                      {/* Direct SEC source — rendered only when the input-to-fact linkage is proven */}
                                      {sc.evidence.eps_evidence.sec_fact && (
                                        <div className="mt-1 pt-1 border-t border-slate-100 space-y-0.5 text-[10px] font-mono text-slate-600">
                                          <div className="text-emerald-700 font-semibold flex items-center gap-1">
                                            <FileText className="w-3 h-3" />
                                            <span>Source: SEC {sc.evidence.eps_evidence.sec_fact.form || '10-K'}</span>
                                          </div>
                                          {sc.evidence.eps_evidence.sec_fact.accession && (
                                            <div>accn: {sc.evidence.eps_evidence.sec_fact.accession}</div>
                                          )}
                                          {sc.evidence.eps_evidence.sec_fact.filed_date && (
                                            <div>filed: {sc.evidence.eps_evidence.sec_fact.filed_date}</div>
                                          )}
                                          <div>{sc.evidence.eps_evidence.sec_fact.concept}</div>
                                        </div>
                                      )}
                                      {/* Direct SEC source not established: state it, keep the value.
                                          A derived anchor's components are directly stated filings, so the
                                          derivation block above is its provenance and this caveat is not raised. */}
                                      {!sc.evidence.eps_evidence.sec_fact && (sc.evidence.eps_evidence.sec_components?.length || 0) === 0 && !sc.evidence.eps_evidence.is_user_assumption && (
                                        <div className="mt-1 pt-1 border-t border-amber-200 text-[10px] font-mono text-amber-800">
                                          <div className="font-semibold">Direct SEC source: not established</div>
                                          <div className="text-[9px] text-amber-700 italic">
                                            Value retained from its declared provider; no filing fact is claimed as its source.
                                          </div>
                                        </div>
                                      )}
                                      {/* Related / cross-check SEC evidence — never claimed as direct source */}
                                      {sc.evidence.related_sec_evidence && sc.evidence.related_sec_evidence.accession && (
                                        <div className="mt-1 pt-1 border-t border-amber-200 space-y-0.5 text-[10px] font-mono text-amber-800">
                                          <div className="font-semibold flex items-center gap-1">
                                            <FileText className="w-3 h-3 text-amber-600" />
                                            <span>Related SEC {sc.evidence.related_sec_evidence.form || '10-K'} (cross-check)</span>
                                          </div>
                                          <div>accn: {sc.evidence.related_sec_evidence.accession}</div>
                                          {sc.evidence.related_sec_evidence.filed_date && (
                                            <div>filed: {sc.evidence.related_sec_evidence.filed_date}</div>
                                          )}
                                          <div className="text-[9px] text-amber-700 italic">{sc.evidence.related_sec_evidence.note || "Not verified as direct source of selected EPS value"}</div>
                                        </div>
                                      )}
                                    </div>
                                  </div>

                                  {/* Exit Multiple Evidence */}
                                  <div className="p-3 bg-white rounded-lg border border-slate-200 shadow-2xs space-y-1.5">
                                    <div className="flex items-center justify-between">
                                      <span className="font-semibold text-slate-800 text-[11px]">
                                        {t.matrix.exitMultipleFact}
                                      </span>
                                      <span
                                        className={`px-1.5 py-0.5 rounded text-[10px] font-mono ${
                                          sc.evidence.multiple_evidence.is_user_assumption
                                            ? 'bg-blue-100 text-blue-800'
                                            : sc.evidence.multiple_evidence.usable_for_reference
                                            ? 'bg-slate-100 text-slate-700'
                                            : 'bg-amber-100 text-amber-800'
                                        }`}
                                      >
                                        {sc.evidence.multiple_evidence.is_user_assumption
                                          ? t.matrix.userSpecifiedBadge
                                          : sc.evidence.multiple_evidence.usable_for_reference
                                          ? t.matrix.eligibleReferenceBadge
                                          : t.matrix.descriptiveOnlyBadge}
                                      </span>
                                    </div>
                                    <div className="font-mono text-sm font-bold text-slate-900">
                                      {sc.evidence.multiple_evidence.value.toFixed(1)}x
                                    </div>
                                    <div className="text-[11px] text-slate-500 space-y-0.5">
                                      <div>{multipleSourceLabel(t, sc.evidence.multiple_evidence)}</div>
                                      {sc.evidence.multiple_evidence.eligibility_state && (
                                        <div>
                                          {t.matrix.eligibilityLabel}: {eligibilityLabel(t, sc.evidence.multiple_evidence.eligibility_state)}
                                        </div>
                                      )}
                                      {sc.evidence.multiple_evidence.sample_size !== null && sc.evidence.multiple_evidence.sample_size !== undefined && (
                                        <div>{t.matrix.sampleSizeLabel}: {sc.evidence.multiple_evidence.sample_size}</div>
                                      )}
                                      {sc.evidence.multiple_evidence.sample_period && (
                                        <div>{t.matrix.periodLabel}: {sc.evidence.multiple_evidence.sample_period}</div>
                                      )}
                                    </div>
                                  </div>

                                  {/* Production historical P/E reference distribution.
                                      Reported for what it is: the observed, point-in-time
                                      distribution this matrix draws its reference rows
                                      from, kept distinct from the vendor P/E band and
                                      from user-supplied multiples. An ineligible or
                                      unavailable distribution is stated, never filled
                                      from the band. */}
                                  {report.production_historical_pe_summary && (
                                    <div
                                      data-testid="production-historical-pe"
                                      className={`p-3 rounded-lg border shadow-2xs space-y-1 text-[11px] ${
                                        report.production_historical_pe_summary.usable_for_reference
                                          ? 'bg-emerald-50 border-emerald-200'
                                          : 'bg-amber-50 border-amber-200'
                                      }`}
                                    >
                                      <div className="font-semibold text-slate-800 flex items-center gap-1">
                                        <Layers className="w-3 h-3" />
                                        <span>
                                          {report.production_historical_pe_summary.usable_for_reference
                                            ? `${t.matrix.productionDistributionEligibleHeader}: ${t.matrix.productionDistributionName}`
                                            : `${t.matrix.productionDistributionHeader}: ${t.matrix.productionDistributionName}`}
                                        </span>
                                      </div>
                                      <div className="font-mono text-[10px] text-slate-600 space-y-0.5">
                                        <div>
                                          {t.matrix.statusLabel}: {report.production_historical_pe_summary.status || 'UNAVAILABLE'}
                                        </div>
                                        {report.production_historical_pe_summary.usable_for_reference ? (
                                          <>
                                            <div>
                                              {t.matrix.qualifyingObservationsLabel}:{' '}
                                              {report.production_historical_pe_summary.sample_count}
                                              {report.production_historical_pe_summary.total_evaluations !==
                                                null &&
                                                report.production_historical_pe_summary.total_evaluations !== undefined &&
                                                ` / ${report.production_historical_pe_summary.total_evaluations}`}
                                            </div>
                                            <div>
                                              {t.matrix.minObservationsLabel}:{' '}
                                              {report.production_historical_pe_summary.min_observations_required}
                                            </div>
                                            <div>
                                              {t.matrix.samplePeriodLabel}:{' '}
                                              {report.production_historical_pe_summary.period_start} to{' '}
                                              {report.production_historical_pe_summary.period_end}
                                            </div>
                                            {report.production_historical_pe_summary.percentiles && (
                                              <div>
                                                {t.matrix.percentileLabel}:{' '}
                                                {Object.entries(report.production_historical_pe_summary.percentiles)
                                                  .map(([key, value]) => `${key} ${Number(value).toFixed(2)}x`)
                                                  .join(' · ')}
                                              </div>
                                            )}
                                            {report.production_historical_pe_summary.current_pe !== null &&
                                              report.production_historical_pe_summary.current_pe !== undefined && (
                                                <div>
                                                  {t.matrix.currentPeLabel}:{' '}
                                                  {Number(report.production_historical_pe_summary.current_pe).toFixed(2)}x (
                                                  {report.production_historical_pe_summary.current_pe_as_of})
                                                </div>
                                              )}
                                            <div>
                                              {t.matrix.asOfRuleLabel}:{' '}
                                              {report.production_historical_pe_summary.evaluation_schedule_description}
                                            </div>
                                          </>
                                        ) : (
                                          <>
                                            {report.production_historical_pe_summary.sample_count !== null &&
                                              report.production_historical_pe_summary.sample_count !== undefined && (
                                                <div>
                                                  {t.matrix.observationsLabel}:{' '}
                                                  {report.production_historical_pe_summary.sample_count} (
                                                  {t.matrix.minObservationsLabel}:{' '}
                                                  {report.production_historical_pe_summary.min_observations_required})
                                                </div>
                                              )}
                                            {report.production_historical_pe_summary.reason_detail && (
                                              <div className="text-amber-800 italic">
                                                {report.production_historical_pe_summary.reason_detail}
                                              </div>
                                            )}
                                          </>
                                        )}
                                        {report.production_historical_pe_summary.input_set_id && (
                                          <div className="text-[9px] text-slate-500">
                                            {t.matrix.datasetIdentityLabel}:{' '}
                                            {report.production_historical_pe_summary.input_set_id.slice(0, 16)}
                                          </div>
                                        )}
                                        </div>
                                      </div>
                                    )}

                                   {/* Production historical P/FCF reference distribution.
                                       The cash-flow counterpart of the block above, with the
                                       same discipline: reported for what it is and never
                                       filled from a band; an unavailable or unsupported
                                       reconstruction is stated as such. */}
                                   {report.production_historical_pfcf_summary && (
                                     <div
                                       data-testid="production-historical-pfcf"
                                       className={`p-3 rounded-lg border shadow-2xs space-y-1 text-[11px] ${
                                         report.production_historical_pfcf_summary.usable_for_reference
                                           ? 'bg-emerald-50 border-emerald-200'
                                           : 'bg-amber-50 border-amber-200'
                                       }`}
                                     >
                                       <div className="font-semibold text-slate-800 flex items-center gap-1">
                                         <Layers className="w-3 h-3" />
                                         <span>
                                           {report.production_historical_pfcf_summary.usable_for_reference
                                             ? `${t.matrix.productionDistributionEligibleHeader}: ${t.matrix.productionPfcfDistributionName}`
                                             : `${t.matrix.productionPfcfDistributionHeader}: ${t.matrix.productionPfcfDistributionName}`}
                                         </span>
                                       </div>
                                       <div className="font-mono text-[10px] text-slate-600 space-y-0.5">
                                         <div>
                                           {t.matrix.statusLabel}: {report.production_historical_pfcf_summary.status || 'UNAVAILABLE'}
                                         </div>
                                         {report.production_historical_pfcf_summary.usable_for_reference ? (
                                           <>
                                             <div>
                                               {t.matrix.qualifyingObservationsLabel}:{' '}
                                               {report.production_historical_pfcf_summary.sample_count}
                                               {report.production_historical_pfcf_summary.total_evaluations !==
                                                 null &&
                                                 report.production_historical_pfcf_summary.total_evaluations !== undefined &&
                                                 ` / ${report.production_historical_pfcf_summary.total_evaluations}`}
                                             </div>
                                             <div>
                                               {t.matrix.minObservationsLabel}:{' '}
                                               {report.production_historical_pfcf_summary.min_observations_required}
                                             </div>
                                             <div>
                                               {t.matrix.samplePeriodLabel}:{' '}
                                               {report.production_historical_pfcf_summary.period_start} to{' '}
                                               {report.production_historical_pfcf_summary.period_end}
                                             </div>
                                             {report.production_historical_pfcf_summary.percentiles && (
                                               <div>
                                                 {t.matrix.percentileLabel}:{' '}
                                                 {Object.entries(report.production_historical_pfcf_summary.percentiles)
                                                   .map(([key, value]) => `${key} ${Number(value).toFixed(2)}x`)
                                                   .join(' · ')}
                                               </div>
                                             )}
                                             {report.production_historical_pfcf_summary.current_pfcf !== null &&
                                               report.production_historical_pfcf_summary.current_pfcf !== undefined && (
                                                 <div>
                                                   {t.matrix.currentPfcfLabel}:{' '}
                                                   {Number(report.production_historical_pfcf_summary.current_pfcf).toFixed(2)}x (
                                                   {report.production_historical_pfcf_summary.current_pfcf_as_of})
                                                 </div>
                                               )}
                                             <div>
                                               {t.matrix.asOfRuleLabel}:{' '}
                                               {report.production_historical_pfcf_summary.evaluation_schedule_description}
                                             </div>
                                           </>
                                         ) : (
                                           <>
                                             {report.production_historical_pfcf_summary.reason_detail && (
                                               <div className="text-amber-800 italic">
                                                 {report.production_historical_pfcf_summary.reason_detail}
                                               </div>
                                             )}
                                           </>
                                         )}
                                         {report.production_historical_pfcf_summary.input_set_id && (
                                           <div className="text-[9px] text-slate-500">
                                             {t.matrix.datasetIdentityLabel}:{' '}
                                             {report.production_historical_pfcf_summary.input_set_id.slice(0, 16)}
                                           </div>
                                         )}
                                       </div>
                                     </div>
                                   )}

                                  {/* Consensus reference. The period facts
                                      the gap column is differenced against, so
                                      an eligible gap can be checked and a
                                      missing one explained. */}
                                  {report.consensus_reference && (
                                    <div
                                      data-testid="consensus-reference"
                                      className="p-3 rounded-lg border bg-slate-50 border-slate-200 shadow-2xs space-y-1 text-[11px]"
                                    >
                                      <div className="font-semibold text-slate-800 flex items-center gap-1">
                                        <Percent className="w-3 h-3" />
                                        <span>{t.matrix.consensusReferenceHeader}</span>
                                      </div>
                                      <div className="font-mono text-[10px] text-slate-600 space-y-0.5">
                                        {report.consensus_reference.eps !== null &&
                                        report.consensus_reference.eps !== undefined ? (
                                          <div>
                                            {t.matrix.consensusEpsLabel}:{' '}
                                            {Number(report.consensus_reference.eps).toFixed(4)}
                                            {report.consensus_reference.provider
                                              ? ` (${report.consensus_reference.provider})`
                                              : ''}
                                          </div>
                                        ) : (
                                          <div>{t.matrix.consensusEpsUnavailableLabel}</div>
                                        )}
                                        <div>
                                          {t.matrix.consensusSourcePeriodLabel}:{' '}
                                          {report.consensus_reference.source_period_label ||
                                            t.matrix.undeclaredValueLabel}
                                        </div>
                                        <div>
                                          {t.matrix.consensusPeriodEndLabel}:{' '}
                                          <span
                                            className={
                                              report.consensus_reference
                                                .period_end_declared_by_source
                                                ? ''
                                                : 'text-amber-700'
                                            }
                                          >
                                            {report.consensus_reference.period_end ||
                                              t.matrix.undeclaredValueLabel}
                                          </span>
                                        </div>
                                        {report.consensus_reference.target_period_end && (
                                          <div>
                                            {t.matrix.consensusTargetPeriodEndLabel}:{' '}
                                            {report.consensus_reference.target_period_end}
                                          </div>
                                        )}
                                        {report.consensus_reference
                                          .comparison_tolerance_days !== null &&
                                          report.consensus_reference
                                            .comparison_tolerance_days !== undefined && (
                                            <div>
                                              {t.matrix.consensusToleranceLabel}:{' '}
                                              {report.consensus_reference.comparison_tolerance_days}{' '}
                                              {t.matrix.daysUnitLabel}
                                            </div>
                                          )}
                                        <div className="pt-0.5">
                                          {consensusGap !== null ? (
                                            <span className="text-emerald-800">
                                              {t.matrix.consensusGapLabel}:{' '}
                                              {(consensusGap * 100).toFixed(2)}%
                                            </span>
                                          ) : (
                                            <span className="text-amber-800">
                                              {consensusGapReason ||
                                                t.matrix.consensusGapUnavailableLabel}
                                            </span>
                                          )}
                                        </div>
                                      </div>
                                    </div>
                                  )}
                                </div>

                                {/* Assumptions vs Facts vs Limitations tags */}
                                <div className="space-y-1.5 pt-1 text-[11px]">
                                  {sc.evidence.user_assumptions && sc.evidence.user_assumptions.length > 0 && (
                                    <div className="flex flex-wrap gap-1.5 items-center">
                                      <span className="font-semibold text-blue-900">
                                        {t.matrix.userAssumptionsHeader}:
                                      </span>
                                      {sc.evidence.user_assumptions.map((uItem, uIdx) => (
                                        <span
                                          key={uIdx}
                                          className="px-2 py-0.5 rounded bg-blue-50 text-blue-800 border border-blue-200/60 font-mono text-[10px]"
                                        >
                                          {uItem}
                                        </span>
                                      ))}
                                    </div>
                                  )}
                                  {sc.evidence.sourced_facts && sc.evidence.sourced_facts.length > 0 && (
                                    <div className="flex flex-wrap gap-1.5 items-center">
                                      <span className="font-semibold text-slate-700">
                                        {t.matrix.verifiedFactsHeader}:
                                      </span>
                                      {sc.evidence.sourced_facts.map((sItem, sIdx) => (
                                        <span
                                          key={sIdx}
                                          className="px-2 py-0.5 rounded bg-slate-100 text-slate-700 border border-slate-200 font-mono text-[10px]"
                                        >
                                          {sItem}
                                        </span>
                                      ))}
                                    </div>
                                  )}
                                  {sc.evidence.missing_or_unvalidated && sc.evidence.missing_or_unvalidated.length > 0 && (
                                    <div className="flex flex-wrap gap-1.5 items-center">
                                      <span className="font-semibold text-amber-800">
                                        {t.matrix.missingOrUnvalidatedHeader}:
                                      </span>
                                      {sc.evidence.missing_or_unvalidated.map((mItem, mIdx) => (
                                        <span
                                          key={mIdx}
                                          className="px-2 py-0.5 rounded bg-amber-50 text-amber-800 border border-amber-200 font-mono text-[10px]"
                                        >
                                          {mItem}
                                        </span>
                                      ))}
                                    </div>
                                  )}
                                </div>
                              </div>
                            )}

                            {/* Flags */}
                            {sc.flags && sc.flags.length > 0 && (
                              <div className="flex flex-wrap gap-1.5 items-center pt-1">
                                <span className="text-[11px] font-semibold text-slate-500">
                                  Flags:
                                </span>
                                {sc.flags.map((fl, fIdx) => (
                                  <span
                                    key={fIdx}
                                    className="px-2 py-0.5 rounded bg-amber-100/70 text-amber-900 font-mono text-[10px]"
                                  >
                                    {fl}
                                  </span>
                                ))}
                              </div>
                            )}

                            {/* Comparison Notes */}
                            {sc.comparison_notes && sc.comparison_notes.length > 0 && (
                              <div className="space-y-1">
                                <span className="text-[11px] font-semibold text-slate-500">
                                  Notes:
                                </span>
                                <ul className="list-disc list-inside space-y-0.5 text-slate-600 text-[11px]">
                                  {sc.comparison_notes.map((note, nIdx) => (
                                    <li key={nIdx}>{note}</li>
                                  ))}
                                </ul>
                              </div>
                            )}

                            {/* Lineage Info */}
                            <div className="pt-1.5 border-t border-slate-200/60 flex flex-wrap gap-4 text-[11px] text-slate-500 font-mono">
                              <span>Growth window: {sc.growth_years !== null ? `${sc.growth_years} yrs` : 'N/A'}</span>
                              <span>Return basis: {sc.required_return_basis}</span>
                              {sc.start_eps?.provider && (
                                <span>EPS provider: {sc.start_eps.provider}</span>
                              )}
                              <span>Formula: {sc.formula_version}</span>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Dividend & Total-Return Comparison Section */}
      {!isNotComputed && report.dividend_basis && (
        <div className="mt-4 pt-4 border-t border-slate-200">
          <div className="flex items-center gap-2 text-xs font-semibold text-slate-700 mb-3">
            <Layers className="w-3.5 h-3.5 text-indigo-600" />
            <span>{t.matrix.dividendSectionTitle}</span>
          </div>
          <div className="space-y-3">
            {/* Dividend Basis Info */}
            <div className="p-3 bg-white rounded-lg border border-slate-200 shadow-2xs space-y-2">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-slate-800 text-[11px]">
                  {t.matrix.dividendPerShare}:
                </span>
                <span className="font-mono text-sm font-bold text-slate-900">
                  {report.dividend_basis.dividend_per_share !== undefined && report.dividend_basis.dividend_per_share !== null
                    ? `${report.dividend_basis.dividend_currency || currency}${Number(report.dividend_basis.dividend_per_share).toFixed(2)}`
                    : t.matrix.dividendUnavailable}
                </span>
              </div>
              {report.dividend_basis.dividend_period && (
                <div className="text-[11px] text-slate-500">
                  {t.matrix.dividendPeriodLabel}: {report.dividend_basis.dividend_period}
                </div>
              )}
              {report.dividend_basis.dividend_source && (
                <div className="text-[11px] text-slate-500">
                  {t.matrix.dividendSource}: {report.dividend_basis.dividend_source}
                </div>
              )}
              {report.dividend_basis.conventions && report.dividend_basis.conventions.length > 0 && (
                <div className="space-y-1">
                  <div className="font-semibold text-slate-700 text-[11px]">{t.matrix.dividendConventions}</div>
                  {report.dividend_basis.conventions.map((conv: any, idx: number) => (
                    <div key={idx} className="p-2 bg-slate-50 rounded text-[10px] font-sans text-slate-700 space-y-0.5">
                      <div className="font-semibold text-indigo-800">
                        {conv.convention === 'CASH_DIVIDENDS_RETAINED'
                          ? t.matrix.conventionCashRetained
                          : conv.convention === 'DIVIDENDS_REINVESTED_AT_TARGET_RETURN'
                          ? t.matrix.conventionReinvested
                          : conv.convention}
                      </div>
                      <div className="font-mono text-[10px] text-blue-900 bg-blue-50 px-1.5 py-0.5 rounded">
                        {conv.formula}
                      </div>
                      <div className="text-[9px] text-slate-500">{conv.description}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Comparison Table */}
            {report.price_vs_total_return_comparison &&
              report.price_vs_total_return_comparison.length > 0 && (
              <div className="space-y-2">
                <div className="font-semibold text-slate-700 text-[11px]">
                  {t.matrix.comparisonTableTitle}
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead>
                      <tr className="bg-slate-50 border-b border-slate-200 text-[10px] font-semibold text-slate-500 uppercase tracking-wider">
                        <th className="py-1.5 px-2">{t.matrix.comparisonHorizon}</th>
                        <th className="py-1.5 px-2">{t.matrix.comparisonReturn}</th>
                        <th className="py-1.5 px-2">{t.matrix.comparisonExitMultiple}</th>
                        <th className="py-1.5 px-2" colSpan={3}>{t.matrix.comparisonPriceOnly}</th>
                        <th className="py-1.5 px-2" colSpan={4}>{t.matrix.comparisonCashRetained}</th>
                        <th className="py-1.5 px-2" colSpan={4}>{t.matrix.comparisonReinvested}</th>
                      </tr>
                      <tr className="bg-slate-50 border-b border-slate-200 text-[10px] font-semibold text-slate-500 uppercase tracking-wider">
                        <th className="py-1.5 px-2"></th>
                        <th className="py-1.5 px-2"></th>
                        <th className="py-1.5 px-2"></th>
                        <th className="py-1.5 px-2">{t.matrix.comparisonExitPrice}</th>
                        <th className="py-1.5 px-2">{t.matrix.comparisonTerminalEps}</th>
                        <th className="py-1.5 px-2">{t.matrix.comparisonEpsCagr}</th>
                        <th className="py-1.5 px-2">{t.matrix.comparisonExitPrice}</th>
                        <th className="py-1.5 px-2">{t.matrix.comparisonTerminalEps}</th>
                        <th className="py-1.5 px-2">{t.matrix.comparisonEpsCagr}</th>
                        <th className="py-1.5 px-2">{t.matrix.comparisonDeltaExitPrice}</th>
                        <th className="py-1.5 px-2">{t.matrix.comparisonDeltaTerminalEps}</th>
                        <th className="py-1.5 px-2">{t.matrix.comparisonDeltaCagr}</th>
                        <th className="py-1.5 px-2">{t.matrix.comparisonExitPrice}</th>
                        <th className="py-1.5 px-2">{t.matrix.comparisonTerminalEps}</th>
                        <th className="py-1.5 px-2">{t.matrix.comparisonEpsCagr}</th>
                        <th className="py-1.5 px-2">{t.matrix.comparisonDeltaExitPrice}</th>
                        <th className="py-1.5 px-2">{t.matrix.comparisonDeltaTerminalEps}</th>
                        <th className="py-1.5 px-2">{t.matrix.comparisonDeltaCagr}</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 font-mono text-[11px]">
                      {report.price_vs_total_return_comparison.map((row: any, idx: number) => (
                        <tr key={idx} className="hover:bg-slate-50/50">
                          <td className="py-1.5 px-2 font-semibold text-slate-900">
                            {row.horizon_years?.toFixed(1)}y
                          </td>
                          <td className="py-1.5 px-2 text-slate-700">
                            {(row.required_return * 100).toFixed(1)}%
                          </td>
                          <td className="py-1.5 px-2 text-slate-700">
                            {row.exit_multiple?.toFixed(1)}x
                          </td>
                          {/* Price Only */}
                          <td className="py-1.5 px-2 text-slate-900">
                            {row.price_only?.required_exit_price !== null && row.price_only?.required_exit_price !== undefined
                              ? `${currency}${Number(row.price_only.required_exit_price).toFixed(2)}`
                              : '—'}
                          </td>
                          <td className="py-1.5 px-2 text-slate-900">
                            {row.price_only?.required_terminal_eps !== null && row.price_only?.required_terminal_eps !== undefined
                              ? `${currency}${Number(row.price_only.required_terminal_eps).toFixed(2)}`
                              : '—'}
                          </td>
                          <td className="py-1.5 px-2 text-slate-700">
                            {row.price_only?.required_eps_cagr !== null && row.price_only?.required_eps_cagr !== undefined
                              ? `${(row.price_only.required_eps_cagr * 100).toFixed(1)}%`
                              : '—'}
                          </td>
                          {/* Cash Retained */}
                          <td className="py-1.5 px-2 text-slate-900">
                            {row.cash_dividends_retained?.required_exit_price !== null && row.cash_dividends_retained?.required_exit_price !== undefined
                              ? `${currency}${Number(row.cash_dividends_retained.required_exit_price).toFixed(2)}`
                              : '—'}
                          </td>
                          <td className="py-1.5 px-2 text-slate-900">
                            {row.cash_dividends_retained?.required_terminal_eps !== null && row.cash_dividends_retained?.required_terminal_eps !== undefined
                              ? `${currency}${Number(row.cash_dividends_retained.required_terminal_eps).toFixed(2)}`
                              : '—'}
                          </td>
                          <td className="py-1.5 px-2 text-slate-700">
                            {row.cash_dividends_retained?.required_eps_cagr !== null && row.cash_dividends_retained?.required_eps_cagr !== undefined
                              ? `${(row.cash_dividends_retained.required_eps_cagr * 100).toFixed(1)}%`
                              : '—'}
                          </td>
                          <td className="py-1.5 px-2 text-blue-700">
                            {row.cash_dividends_retained?.delta_exit_price !== null && row.cash_dividends_retained?.delta_exit_price !== undefined
                              ? `${currency}${Number(row.cash_dividends_retained.delta_exit_price).toFixed(2)}`
                              : '—'}
                          </td>
                          <td className="py-1.5 px-2 text-blue-700">
                            {row.cash_dividends_retained?.delta_terminal_eps !== null && row.cash_dividends_retained?.delta_terminal_eps !== undefined
                              ? `${currency}${Number(row.cash_dividends_retained.delta_terminal_eps).toFixed(2)}`
                              : '—'}
                          </td>
                          <td className="py-1.5 px-2 text-blue-700">
                            {row.cash_dividends_retained?.delta_eps_cagr !== null && row.cash_dividends_retained?.delta_eps_cagr !== undefined
                              ? `${(row.cash_dividends_retained.delta_eps_cagr * 100).toFixed(1)}%`
                              : '—'}
                          </td>
                          {/* Reinvested */}
                          <td className="py-1.5 px-2 text-slate-900">
                            {row.dividends_reinvested_at_target_return?.required_exit_price !== null && row.dividends_reinvested_at_target_return?.required_exit_price !== undefined
                              ? `${currency}${Number(row.dividends_reinvested_at_target_return.required_exit_price).toFixed(2)}`
                              : '—'}
                          </td>
                          <td className="py-1.5 px-2 text-slate-900">
                            {row.dividends_reinvested_at_target_return?.required_terminal_eps !== null && row.dividends_reinvested_at_target_return?.required_terminal_eps !== undefined
                              ? `${currency}${Number(row.dividends_reinvested_at_target_return.required_terminal_eps).toFixed(2)}`
                              : '—'}
                          </td>
                          <td className="py-1.5 px-2 text-slate-700">
                            {row.dividends_reinvested_at_target_return?.required_eps_cagr !== null && row.dividends_reinvested_at_target_return?.required_eps_cagr !== undefined
                              ? `${(row.dividends_reinvested_at_target_return.required_eps_cagr * 100).toFixed(1)}%`
                              : '—'}
                          </td>
                          <td className="py-1.5 px-2 text-emerald-700">
                            {row.dividends_reinvested_at_target_return?.delta_exit_price !== null && row.dividends_reinvested_at_target_return?.delta_exit_price !== undefined
                              ? `${currency}${Number(row.dividends_reinvested_at_target_return.delta_exit_price).toFixed(2)}`
                              : '—'}
                          </td>
                          <td className="py-1.5 px-2 text-emerald-700">
                            {row.dividends_reinvested_at_target_return?.delta_terminal_eps !== null && row.dividends_reinvested_at_target_return?.delta_terminal_eps !== undefined
                              ? `${currency}${Number(row.dividends_reinvested_at_target_return.delta_terminal_eps).toFixed(2)}`
                              : '—'}
                          </td>
                          <td className="py-1.5 px-2 text-emerald-700">
                            {row.dividends_reinvested_at_target_return?.delta_eps_cagr !== null && row.dividends_reinvested_at_target_return?.delta_eps_cagr !== undefined
                              ? `${(row.dividends_reinvested_at_target_return.delta_eps_cagr * 100).toFixed(1)}%`
                              : '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Dividend not available message */}
      {!isNotComputed && !report.dividend_basis && (
        <div className="mt-4 pt-4 border-t border-slate-200">
          <div className="p-3 bg-slate-50 rounded-lg border border-slate-200">
            <div className="flex items-center gap-2 text-xs font-semibold text-slate-700 mb-2">
              <Layers className="w-3.5 h-3.5 text-indigo-600" />
              <span>{t.matrix.dividendSectionTitle}</span>
            </div>
            <p className="text-slate-600 text-sm">{t.matrix.dividendNotAvailable}</p>
            <p className="text-slate-500 text-xs mt-1">
              {t.matrix.priceOnlyBasis}
            </p>
          </div>
        </div>
      )}

      {/* Reading / Methodology Notes (Collapsible) */}
      {report.reading_notes && report.reading_notes.length > 0 && (
        <div className="pt-2 border-t border-slate-100">
          <button
            type="button"
            onClick={() => setShowNotes(!showNotes)}
            className="flex items-center gap-1.5 text-xs font-medium text-slate-500 hover:text-slate-800 cursor-pointer transition-colors"
          >
            <Info className="w-3.5 h-3.5 text-slate-400" />
            <span>{t.matrix.notesToggle}</span>
            {showNotes ? (
              <ChevronDown className="w-3.5 h-3.5" />
            ) : (
              <ChevronRight className="w-3.5 h-3.5" />
            )}
          </button>

          {showNotes && (
            <ul className="mt-2.5 space-y-1 text-slate-600 text-xs list-disc list-inside bg-slate-50 p-3 rounded-lg border border-slate-100 leading-relaxed">
              {report.reading_notes.map((note: string, idx: number) => (
                <li key={idx}>{note}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
