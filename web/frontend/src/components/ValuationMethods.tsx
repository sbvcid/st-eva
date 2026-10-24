import React from 'react'
import { ReverseRequirementsReportDTO } from '../types/api'
import { useI18n } from '../i18n'

interface ValuationMethodsProps {
  report?: ReverseRequirementsReportDTO | null
  currency?: string | null
}

/**
 * The non-earnings valuation methods the engine reports beside the EPS
 * matrix: revenue (P/S), cash flow (P/FCF) and enterprise value
 * (EV/EBITDA).
 *
 * Each is a single-point reference implied by today's price at its own
 * reference multiple -- not a per-scenario matrix row, never ranked
 * against another, and never holding a holding period or required return.
 */
const METHODS: Array<{
  key: 'revenue_multiple' | 'cash_flow_multiple' | 'enterprise_value_multiple'
  labelKey: string
  multipleLabelKey: string
  provenanceKey: 'current_revenue' | 'current_fcf' | 'current_ebitda'
}> = [
  {
    key: 'revenue_multiple',
    labelKey: 'methodRevenue',
    multipleLabelKey: 'ps',
    provenanceKey: 'current_revenue',
  },
  {
    key: 'cash_flow_multiple',
    labelKey: 'methodPfcf',
    multipleLabelKey: 'pfcf',
    provenanceKey: 'current_fcf',
  },
  {
    key: 'enterprise_value_multiple',
    labelKey: 'methodEvEbitda',
    multipleLabelKey: 'evEbitda',
    provenanceKey: 'current_ebitda',
  },
]

const sourceLabel = (t: any, source: string | null | undefined): string => {
  if (!source) return ''
  switch (source) {
    case 'production_historical_ps_median':
      return t.valuationMethods.sourceProductionPs
    case 'production_historical_ev_ebitda_median':
      return t.valuationMethods.sourceProductionEvEbitda
    case 'production_historical_pfcf_median':
      return t.valuationMethods.sourceProductionPfcf
    case 'user_supplied':
      return t.valuationMethods.sourceUserSupplied
    default:
      return String(source)
  }
}

const provenanceSourceLabel = (t: any, source: string | null | undefined): string => {
  if (!source) return ''
  switch (source) {
    case 'SEC_DERIVED':
      return t.valuationMethods.provenanceSecDerived
    case 'VENDOR_REPORTED':
      return t.valuationMethods.provenanceVendorReported
    default:
      return String(source)
  }
}

const eligibilityBadge = (t: any, multiple: any): React.ReactNode => {
  if (!multiple) return null
  if (multiple.is_user_assumption) {
    return (
      <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-blue-100 text-blue-800">
        {t.matrix.eligibilityUserSpecified}
      </span>
    )
  }
  if (multiple.usable_for_reference) {
    return (
      <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-slate-100 text-slate-700">
        {t.matrix.eligibilityProductionDistribution}
      </span>
    )
  }
  return (
    <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-amber-100 text-amber-800">
      {t.matrix.descriptiveOnlyBadge}
    </span>
  )
}

const statusBadge = (t: any, status: string | null | undefined): React.ReactNode => {
  const computed = status === 'COMPUTED'
  return (
    <span
      className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold ${
        computed
          ? 'bg-emerald-100 text-emerald-800'
          : 'bg-amber-100 text-amber-800'
      }`}
    >
      {computed ? t.matrix.statusComputed : t.matrix.statusNotComputed}
    </span>
  )
}

const formatNumber = (value: number): string =>
  Number(value).toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })

// Show the reference multiple with full precision (e.g. 13.221693, 7.257709,
// 22.326, 11.783822) so the reader can re-verify the figure the engine
// actually used instead of a rounded one-decimal rendering.
const formatMultiple = (value: number): string => {
  return Number(value)
    .toFixed(6)
    .replace(/\.?0+$/, '')
}

const money = (currency: string | null | undefined, value: number | null | undefined): string => {
  if (value === null || value === undefined) return '—'
  return `${currency || '$'}${formatNumber(value)}`
}

// gap_implied_vs_observed is a relative ratio (implied / observed - 1),
// e.g. +0.0180 -> +1.80%, -0.0322 -> -3.22%. It is not an absolute currency
// difference, so it is shown as a signed percentage, never as money.
const gapText = (t: any, gap: number | null | undefined): string => {
  if (gap === null || gap === undefined) return '—'
  const sign = gap > 0 ? '+' : gap < 0 ? '-' : ''
  return `${sign}${Number(Math.abs(gap * 100)).toFixed(2)}%`
}

export const ValuationMethods: React.FC<ValuationMethodsProps> = ({
  report,
  currency = '$',
}) => {
  const { t } = useI18n()
  const methods = report?.valuation_methods?.methods ?? {}
  const distributions = report?.production_historical_multiples_summary?.distributions ?? {}
  const provenance = report?.input_provenance ?? {}

  const distributionFor = (key: string): any => {
    const distributions =
      report?.production_historical_multiples_distributions ??
      report?.production_historical_multiples_summary?.distributions ??
      {}
    switch (key) {
      case 'revenue_multiple':
        return distributions.P_S_RATIO_REFERENCE ?? null
      case 'enterprise_value_multiple':
        return distributions.EV_EBITDA_RATIO_REFERENCE ?? null
      case 'cash_flow_multiple':
        return distributions.PFCF_RATIO_REFERENCE ?? null
      default:
        return null
    }
  }

  // The refusal reason, preferring the distribution's own ineligibility
  // (e.g. INSUFFICIENT_OBSERVATIONS with its sample count and required
  // minimum) over the top-level unavailable entry, whose reason names the
  // input a method would invert rather than why the reference is absent.
  const refusalFor = (key: string): string | null => {
    const dist = distributionFor(key)
    if (dist && dist.status && dist.status !== 'USABLE_FOR_REFERENCE') {
      if (dist.reason_detail) return dist.reason_detail
      return `${String(dist.status)} — ${dist.sample_count ?? '—'} of ${
        dist.min_observations_required ?? '—'
      }${t.valuationMethods.requiredObservationsSuffix}`
    }
    const unavailable = report?.unavailable ?? []
    const entry = unavailable.find((u) => u.item === `valuation_method.${key}`)
    return entry ? (entry.reason as string) : null
  }

  if (!report) return null

  return (
    <section
      className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs space-y-4"
    >
      <div className="flex items-center justify-between gap-3 pb-2 border-b border-slate-100">
        <div>
          <h2 className="text-base font-bold text-slate-900 tracking-tight">
            {t.valuationMethods.sectionTitle}
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            {t.valuationMethods.sectionNote}
          </p>
        </div>
        <span
          className={`px-2 py-0.5 rounded text-[11px] font-mono font-semibold ${
            report.formula_version ? 'bg-slate-100 text-slate-700' : ''
          }`}
        >
          {report.formula_version || 'reverse-requirements/1.1'}
        </span>
      </div>

      <p className="text-xs text-slate-500">
        {t.valuationMethods.impliedObservedNote}
      </p>

      <div className="overflow-x-auto border border-slate-200 rounded-lg">
        <table className="w-full text-left text-xs border-collapse">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-200 text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
              <th className="py-2.5 px-3">{t.valuationMethods.columnMethod}</th>
              <th className="py-2.5 px-3">{t.valuationMethods.columnStatus}</th>
              <th className="py-2.5 px-3">{t.valuationMethods.columnReference}</th>
              <th className="py-2.5 px-3">{t.valuationMethods.columnImplied}</th>
              <th className="py-2.5 px-3">{t.valuationMethods.columnObserved}</th>
              <th className="py-2.5 px-3">{t.valuationMethods.columnGap}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 font-mono text-[12px]">
            {METHODS.map(({ key, labelKey, multipleLabelKey, provenanceKey }) => {
              const block = methods[key]
              const multiple = block?.reference_multiple ?? null
              const dist = distributionFor(key)
              const refusal = refusalFor(key)
              const isComputed = block?.status === 'COMPUTED'
              const implied = block?.implied ?? null
              const observed = block?.observed ?? null
              const gap = block?.gap_implied_vs_observed ?? null
              const sampleSize =
                dist?.sample_count ??
                multiple?.sample_size ??
                null
              const minObs = dist?.min_observations_required ?? null
              const samplePeriod =
                dist?.sample_period ?? multiple?.sample_period ?? ''
  const prov = provenance[provenanceKey] ?? null
              const obsPeriod =
                prov?.period_start && prov?.period_end
                  ? `${prov.period_start}${t.valuationMethods.periodRangeSeparator}${prov.period_end}`
                  : ''
              const obsSource = prov?.source
                ? provenanceSourceLabel(t, prov.source)
                : ''

              return (
                <tr key={key}>
                  <td className="py-3 px-3 font-semibold text-slate-900">
                    <span className="font-semibold text-slate-900">
                      {(t.valuationMethods as Record<string, string>)[labelKey]}
                    </span>
                    <span className="text-[10px] text-slate-400 block font-sans mt-0.5">
                      {(t.results as unknown as Record<string, string>)[multipleLabelKey]}
                    </span>
                  </td>
                  <td className="py-3 px-3">{statusBadge(t, block?.status ?? null)}</td>
                  <td className="py-3 px-3">
                    <div className="font-semibold text-slate-900">
                      {multiple ? `${formatMultiple(Number(multiple.value))}x` : '—'}
                    </div>
                    <div className="text-[10px] text-slate-500 mt-0.5">
                      {sourceLabel(t, multiple?.source)}
                    </div>
                    <div className="text-[10px] text-slate-500 mt-0.5">
                      {eligibilityBadge(t, multiple)}
                    </div>
                    <div className="text-[10px] text-slate-500 mt-0.5">
                      {sampleSize != null
                        ? `${t.valuationMethods.sampleSizeLabel}: ${sampleSize}${
                            minObs != null
                              ? ` / ${t.valuationMethods.minObservationsLabel} ${minObs}`
                              : ''
                          }`
                        : ''}
                    </div>
                    {samplePeriod && (
                      <div className="text-[10px] text-slate-500 mt-0.5">
                        {t.valuationMethods.samplePeriodLabel}: {samplePeriod}
                      </div>
                    )}
                    {refusal && (
                      <div className="text-[10px] text-amber-700 mt-0.5">
                        {t.valuationMethods.refusalReasonLabel}: {refusal}
                      </div>
                    )}
                  </td>
                  <td className="py-3 px-3 text-slate-900 font-medium">
                    {money(currency, implied)}
                  </td>
                  <td className="py-3 px-3 text-slate-700">
                    <div className="font-medium">{money(currency, observed)}</div>
                    {obsPeriod && (
                      <div className="text-[10px] text-slate-500 mt-0.5">
                        {t.valuationMethods.observedPeriodLabel}: {obsPeriod}
                      </div>
                    )}
                    {obsSource && (
                      <div className="text-[10px] text-slate-500 mt-0.5">
                        {t.valuationMethods.observedSourceLabel}: {obsSource}
                      </div>
                    )}
                  </td>
                  <td className="py-3 px-3 text-slate-700">
                    {isComputed && (implied != null && observed != null)
                      ? gapText(t, gap)
                      : t.valuationMethods.notComparable}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {Object.values(methods).some((m) => m.status !== 'COMPUTED') && (
        <div className="p-3 bg-amber-50/70 border border-amber-200 rounded-xl text-amber-900 text-xs">
          <p className="font-semibold mb-1">{t.valuationMethods.noticeSomeUnavailable}</p>
          <p className="text-amber-800">
            {t.valuationMethods.noticeSomeUnavailableBody}
          </p>
        </div>
      )}
    </section>
  )
}
