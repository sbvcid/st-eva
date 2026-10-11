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
  ShieldCheck,
  Table as TableIcon,
} from 'lucide-react'
import { useI18n } from '../i18n'

interface ReverseRequirementsMatrixProps {
  report?: ReverseRequirementsReportDTO | null
  currency?: string | null
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
    <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs space-y-4">
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
              {report.unavailable && report.unavailable.length > 0 && (
                <div className="mt-2 space-y-1 bg-amber-100/60 p-2.5 rounded-lg border border-amber-200/60 font-mono text-[11px]">
                  <span className="font-bold text-amber-950 block">Unavailable inputs:</span>
                  {report.unavailable.map((u, i) => (
                    <div key={i}>
                      • <span className="font-semibold">{u.item || 'Item'}:</span>{' '}
                      {u.reason || JSON.stringify(u)}
                    </div>
                  ))}
                </div>
              )}
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
                            {sc.exit_multiple.source === 'user_supplied'
                              ? 'User'
                              : 'Band'}
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
                                            : 'bg-slate-100 text-slate-700'
                                        }`}
                                      >
                                        {sc.evidence.eps_evidence.is_user_assumption
                                          ? t.matrix.userSpecifiedBadge
                                          : t.matrix.sourcedFactBadge}
                                      </span>
                                    </div>
                                    <div className="font-mono text-sm font-bold text-slate-900">
                                      {currency}{sc.evidence.eps_evidence.value.toFixed(2)}
                                      <span className="text-xs text-slate-500 font-normal ml-1">
                                        {sc.evidence.eps_evidence.basis}
                                      </span>
                                    </div>
                                    <div className="text-[11px] text-slate-500 space-y-0.5">
                                      <div>Coverage: {sc.evidence.eps_evidence.months_covered} months</div>
                                      <div>Provider: {sc.evidence.eps_evidence.provider || 'reported'}</div>
                                      {sc.evidence.eps_evidence.observation_id && (
                                        <div className="font-mono text-[10px] text-indigo-700">
                                          {sc.evidence.eps_evidence.observation_id}
                                        </div>
                                      )}
                                      {/* SEC XBRL Fact if attached */}
                                      {sc.evidence.eps_evidence.sec_fact && (
                                        <div className="mt-1 pt-1 border-t border-slate-100 space-y-0.5 text-[10px] font-mono text-slate-600">
                                          <div className="text-emerald-700 font-semibold flex items-center gap-1">
                                            <FileText className="w-3 h-3" />
                                            <span>SEC {sc.evidence.eps_evidence.sec_fact.form || '10-K'}</span>
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
                                      <div>Source: {sc.evidence.multiple_evidence.source}</div>
                                      {sc.evidence.multiple_evidence.sample_size !== null && sc.evidence.multiple_evidence.sample_size !== undefined && (
                                        <div>Sample Size: {sc.evidence.multiple_evidence.sample_size}</div>
                                      )}
                                      {sc.evidence.multiple_evidence.sample_period && (
                                        <div>Period: {sc.evidence.multiple_evidence.sample_period}</div>
                                      )}
                                    </div>
                                  </div>
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
