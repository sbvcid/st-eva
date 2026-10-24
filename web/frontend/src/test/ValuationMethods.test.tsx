import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ValuationMethods } from '../components/ValuationMethods'
import { ReverseRequirementsReportDTO } from '../types/api'
import { I18nProvider } from '../i18n'

const mockReport: ReverseRequirementsReportDTO = {
  formula_version: 'reverse-requirements/1.1',
  fingerprint: 'mock-fp-1234567890',
  status: 'NOT_COMPUTED',
  status_reason: 'No eligible P/E production reference for this issuer.',
  matrix_size: 0,
  reverse_requirements_matrix: [],
  reading_notes: [],
  unavailable: [],
  production_historical_multiples_summary: {
    distributions: {
      P_S_RATIO_REFERENCE: {
        status: 'INSUFFICIENT_OBSERVATIONS',
        usable_for_reference: false,
        sample_count: 4,
        min_observations_required: 20,
        sample_period: '2020-06-30 .. 2026-06-30',
      },
      EV_EBITDA_RATIO_REFERENCE: {
        status: 'USABLE_FOR_REFERENCE',
        usable_for_reference: true,
        sample_count: 24,
        min_observations_required: 20,
        sample_period: '2020-06-30 .. 2026-06-30',
      },
    },
  },
  valuation_methods: {
    methods: {
      revenue_multiple: {
        status: 'NOT_COMPUTED',
        reference_multiple: null,
        implied: null,
        observed: 22207500000,
        unit: 'currency',
        notes: [],
      },
      cash_flow_multiple: {
        status: 'NOT_COMPUTED',
        reference_multiple: null,
        implied: null,
        observed: -2437000000,
        unit: 'currency',
      },
      enterprise_value_multiple: {
        status: 'COMPUTED',
        reference_multiple: {
          value: 13.221693,
          source: 'production_historical_ev_ebitda_median',
          eligibility_state: 'ELIGIBLE_PRODUCTION_DISTRIBUTION',
          is_user_assumption: false,
          usable_for_reference: true,
        },
        implied: 9008271932.35,
        observed: 8849200000,
        unit: 'currency',
        gap_implied_vs_observed: 0.018,
      },
    },
    unavailable: [],
    reading_notes: [],
  },
  input_provenance: {
    current_ebitda: {
      value: 8849200000,
      source: 'SEC_DERIVED',
      basis: 'TTM',
      currency: 'USD',
      derivation:
        'sum of four discrete quarterly EBITDA figures, each the quarter\'s operating income plus its depreciation and amortization',
      usable_from: '2026-07-30',
      period_start: '2025-06-30',
      period_end: '2026-03-31',
      used_by_engine: true,
      provider_figure: {
        value: 9308000000,
        source: 'VENDOR_REPORTED',
        basis: 'UNDECLARED',
      },
    },
    current_revenue: {
      value: 22207500000,
      source: 'SEC_DERIVED',
      basis: 'TTM',
      currency: 'USD',
      derivation: 'sum of four discrete quarterly revenue figures',
      usable_from: '2026-07-30',
      period_start: '2025-06-30',
      period_end: '2026-03-31',
      used_by_engine: true,
    },
  },
}

describe('ValuationMethods Component', () => {
  it('renders the valuation-methods section and all three non-earnings methods', () => {
    render(
      <I18nProvider initialLang="en">
        <ValuationMethods report={mockReport} />
      </I18nProvider>
    )

    expect(screen.getByText('Valuation Methods')).toBeInTheDocument()
    expect(screen.getByText('Revenue (P/S)')).toBeInTheDocument()
    expect(screen.getByText('Free Cash Flow (P/FCF)')).toBeInTheDocument()
    expect(screen.getByText('Enterprise Value (EV/EBITDA)')).toBeInTheDocument()
  })

  it('shows COMPUTED with implied/observed/gap for EV/EBITDA', () => {
    render(
      <I18nProvider initialLang="en">
        <ValuationMethods report={mockReport} />
      </I18nProvider>
    )

    expect(screen.getByText('COMPUTED')).toBeInTheDocument()
    expect(screen.getByText('$9,008,271,932.35')).toBeInTheDocument()
    expect(screen.getByText('$8,849,200,000.00')).toBeInTheDocument()
    expect(screen.getByText('+1.80%')).toBeInTheDocument()
    expect(screen.getByText('13.221693x')).toBeInTheDocument()
    expect(screen.getByText('Production point-in-time historical EV/EBITDA')).toBeInTheDocument()
  })

  it('shows a negative signed gap when implied is below observed', () => {
    const negative = {
      ...mockReport,
      valuation_methods: {
        ...mockReport.valuation_methods,
        methods: {
          ...mockReport.valuation_methods.methods,
          enterprise_value_multiple: {
            ...mockReport.valuation_methods.methods.enterprise_value_multiple,
            implied: 8500000000,
            observed: 8849200000,
            gap_implied_vs_observed: -0.0395,
          },
        },
      },
    }
    render(
      <I18nProvider initialLang="en">
        <ValuationMethods report={negative} />
      </I18nProvider>
    )

    expect(screen.getByText('-3.95%')).toBeInTheDocument()
  })

  it('shows a zero gap without a sign when implied equals observed', () => {
    const zero = {
      ...mockReport,
      valuation_methods: {
        ...mockReport.valuation_methods,
        methods: {
          ...mockReport.valuation_methods.methods,
          enterprise_value_multiple: {
            ...mockReport.valuation_methods.methods.enterprise_value_multiple,
            implied: 8849200000,
            observed: 8849200000,
            gap_implied_vs_observed: 0,
          },
        },
      },
    }
    render(
      <I18nProvider initialLang="en">
        <ValuationMethods report={zero} />
      </I18nProvider>
    )

    expect(screen.getByText('0.00%')).toBeInTheDocument()
  })

  it('shows the observed financial period and source beside the observed figure', () => {
    render(
      <I18nProvider initialLang="en">
        <ValuationMethods report={mockReport} />
      </I18nProvider>
    )

    // Observed EBITDA carries its SEC-derived TTM period and source.
    expect(screen.getAllByText('Observed period: 2025-06-30 to 2026-03-31')).toHaveLength(2)
    expect(screen.getAllByText('Observed source: SEC-derived TTM')).toHaveLength(2)
    // The reference sampling period is shown separately from the observed period.
    expect(screen.getAllByText('Sample period: 2020-06-30 .. 2026-06-30')).toHaveLength(2)
  })

  it('shows NOT COMPUTED for methods without a usable reference', () => {
    render(
      <I18nProvider initialLang="en">
        <ValuationMethods report={mockReport} />
      </I18nProvider>
    )

    // Two NOT COMPUTED rows: revenue and cash flow.
    expect(screen.getAllByText('NOT COMPUTED').length).toBe(2)
    expect(screen.getByText('$22,207,500,000.00')).toBeInTheDocument()
  })

  it('renders in zh-TW without hard-coded English labels', () => {
    render(
      <I18nProvider initialLang="zh-TW">
        <ValuationMethods report={mockReport} />
      </I18nProvider>
    )

    expect(screen.getByText('估值方法')).toBeInTheDocument()
    expect(screen.getByText('企業價值 (EV/EBITDA)')).toBeInTheDocument()
    expect(screen.queryByText('COMPUTED')).not.toBeInTheDocument()
  })
})
