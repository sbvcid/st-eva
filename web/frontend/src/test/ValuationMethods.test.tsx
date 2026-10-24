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
        gap_implied_vs_observed: 159071932.35,
      },
    },
    unavailable: [],
    reading_notes: [],
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
    expect(screen.getByText('+$159,071,932.35')).toBeInTheDocument()
    expect(screen.getByText('13.2x')).toBeInTheDocument()
    expect(screen.getByText('Production point-in-time historical EV/EBITDA')).toBeInTheDocument()
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
