import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ReverseRequirementsMatrix } from '../components/ReverseRequirementsMatrix'
import { ReverseRequirementsReportDTO } from '../types/api'
import { I18nProvider } from '../i18n'

const mockReport: ReverseRequirementsReportDTO = {
  formula_version: 'reverse-requirements/1.1',
  fingerprint: 'mock-fp-1234567890',
  status: 'COMPUTED',
  status_reason: null,
  matrix_size: 2,
  reverse_requirements_matrix: [
    {
      horizon_years: 1.0,
      required_return: 0.10,
      required_return_basis: 'PRICE_RETURN_ONLY',
      exit_multiple: {
        value: 20.0,
        source: 'user_supplied',
      },
      required_exit_price: 110.0,
      required_terminal_eps: 5.5,
      start_eps: {
        value: 5.0,
        basis: 'FORWARD_TWELVE_MONTHS',
        months_covered: 12.0,
      },
      growth_years: 0.0,
      required_eps_cagr: null, // Uncomputable!
      total_terminal_eps_growth: 0.10,
      comparison_notes: ['Growth window too short to annualise (0.0 years).'],
      flags: ['GROWTH_WINDOW_TOO_SHORT_FOR_CAGR'],
      formula_version: 'reverse-requirements/1.1',
    },
    {
      horizon_years: 3.0,
      required_return: 0.10,
      required_return_basis: 'PRICE_RETURN_ONLY',
      exit_multiple: {
        value: 25.0,
        source: 'historical_pe_band_percentile',
      },
      required_exit_price: 133.1,
      required_terminal_eps: 5.324,
      start_eps: {
        value: 4.0,
        basis: 'TRAILING_TWELVE_MONTHS',
        months_covered: 12.0,
      },
      growth_years: 3.0,
      required_eps_cagr: 0.125, // Computable: 12.5%
      total_terminal_eps_growth: 0.331,
      comparison_notes: [],
      flags: [],
      formula_version: 'reverse-requirements/1.1',
      calculation_steps: [
        {
          step_number: 1,
          step_id: 'required_exit_price',
          name: 'Required Exit Price',
          formula_expression: 'P_T = P_0 * (1 + r)^T',
          operands: { price: 100.0, required_return: 0.10, horizon_years: 3.0 },
          output_value: 133.1,
          output_unit: 'USD',
          reproducible: true,
          status: 'COMPUTED',
          status_reason: null,
        },
        {
          step_number: 2,
          step_id: 'required_terminal_eps',
          name: 'Required Terminal EPS',
          formula_expression: 'EPS_T = P_T / Exit_PE',
          operands: { required_exit_price: 133.1, exit_multiple: 25.0 },
          output_value: 5.324,
          output_unit: 'USD/share',
          reproducible: true,
          status: 'COMPUTED',
          status_reason: null,
        },
        {
          step_number: 3,
          step_id: 'total_terminal_eps_growth',
          name: 'Total Terminal EPS Growth',
          formula_expression: 'Delta_EPS = (EPS_T - EPS_0) / EPS_0',
          operands: { required_terminal_eps: 5.324, start_eps: 4.0 },
          output_value: 0.331,
          output_unit: 'ratio',
          reproducible: true,
          status: 'COMPUTED',
          status_reason: null,
        },
        {
          step_number: 4,
          step_id: 'required_eps_cagr',
          name: 'Required EPS CAGR',
          formula_expression: 'CAGR = (EPS_T / EPS_0)^(1 / t_growth) - 1',
          operands: { required_terminal_eps: 5.324, start_eps: 4.0, growth_years: 3.0 },
          output_value: 0.125,
          output_unit: 'percent_per_annum',
          reproducible: true,
          status: 'COMPUTED',
          status_reason: null,
        },
      ],
      evidence: {
        price_evidence: {
          value: 100.0,
          currency: 'USD',
          as_of: '2026-09-18',
          provider: 'RegressionFixture',
          source_type: 'REGRESSION_FIXTURE',
          observation_id: 'ev-price-001',
          is_user_assumption: false,
        },
        eps_evidence: {
          value: 4.0,
          basis: 'TRAILING_TWELVE_MONTHS',
          months_covered: 12.0,
          period_label: 'FY2026',
          provider: 'sec',
          currency: 'USD',
          period_undeclared_by_source: false,
          source_type: 'REGULATORY_FILING',
          observation_id: 'ev-current-eps-001',
          is_user_assumption: false,
          sec_fact: {
            accession: '0001193125-26-323660',
            concept: 'us-gaap:EarningsPerShareDiluted',
            unit: 'USD/shares',
            period_end: '2026-06-30',
            form: '10-K',
            filed_date: '2026-07-30',
          },
        },
        multiple_evidence: {
          value: 25.0,
          source: 'historical_pe_band_percentile',
          sample_size: 40,
          period_label: 'median',
          sample_period: 'band percentiles from 40 observations',
          is_user_assumption: false,
          eligibility_state: 'ELIGIBLE_HISTORICAL_BAND',
          usable_for_reference: true,
        },
        user_assumptions: [
          'Holding Horizon: 3 years',
          'Required Return Hurdle: 10% (PRICE_RETURN_ONLY)',
        ],
        sourced_facts: [
          'Market Price: 100 USD (as-of 2026-09-18, provider: RegressionFixture)',
          'Starting EPS: 4 USD (TRAILING_TWELVE_MONTHS via sec; SEC 10-K accession 0001193125-26-323660)',
          'Reference Exit Multiple: 25x (historical_pe_band_percentile, sample size: 40)',
        ],
        missing_or_unvalidated: [],
      },
    },
  ],
  reading_notes: [
    'A required return is a price return unless a dividend was supplied as an input.',
  ],
}

describe('ReverseRequirementsMatrix Component', () => {
  it('renders matrix header with formula version and COMPUTED status', () => {
    render(
      <I18nProvider initialLang="en">
        <ReverseRequirementsMatrix report={mockReport} />
      </I18nProvider>
    )

    expect(screen.getByText('Reverse Requirements Matrix')).toBeInTheDocument()
    expect(screen.getByText('reverse-requirements/1.1')).toBeInTheDocument()
    expect(screen.getByText('COMPUTED')).toBeInTheDocument()
    expect(screen.getByText('2 scenarios')).toBeInTheDocument()
  })

  it('renders scenarios table with both computable and uncomputable rows', () => {
    render(
      <I18nProvider initialLang="en">
        <ReverseRequirementsMatrix report={mockReport} />
      </I18nProvider>
    )

    // Check table headers
    expect(screen.getByText('Horizon')).toBeInTheDocument()
    expect(screen.getByText('Exit Multiple')).toBeInTheDocument()
    expect(screen.getByText('Req. EPS CAGR')).toBeInTheDocument()

    // Row 1: uncomputable CAGR shows "Not Computable" badge
    expect(screen.getByText('Not Computable')).toBeInTheDocument()
    expect(screen.getByText('1.0y')).toBeInTheDocument()
    expect(screen.getByText('20.0x')).toBeInTheDocument()
    expect(screen.getByText('$110.00')).toBeInTheDocument()

    // Row 2: computable CAGR shows +12.5%
    expect(screen.getByText('+12.5%')).toBeInTheDocument()
    expect(screen.getByText('3.0y')).toBeInTheDocument()
    expect(screen.getByText('25.0x')).toBeInTheDocument()
  })

  it('filters scenarios by horizon button click', () => {
    render(
      <I18nProvider initialLang="en">
        <ReverseRequirementsMatrix report={mockReport} />
      </I18nProvider>
    )

    const btn3y = screen.getByRole('button', { name: '3y' })
    fireEvent.click(btn3y)

    // Now only 3.0y row is rendered
    expect(screen.getByText('3.0y')).toBeInTheDocument()
    expect(screen.queryByText('1.0y')).not.toBeInTheDocument()
  })

  it('expands row details drawer to show uncomputable flags and comparison notes', () => {
    render(
      <I18nProvider initialLang="en">
        <ReverseRequirementsMatrix report={mockReport} />
      </I18nProvider>
    )

    const toggleBtns = screen.getAllByTitle('Toggle details')
    expect(toggleBtns.length).toBeGreaterThan(0)
    fireEvent.click(toggleBtns[0])

    expect(screen.getByText('GROWTH_WINDOW_TOO_SHORT_FOR_CAGR')).toBeInTheDocument()
    expect(screen.getByText('Growth window too short to annualise (0.0 years).')).toBeInTheDocument()
  })

  it('expands row details drawer to show calculation steps and SEC fact provenance', () => {
    render(
      <I18nProvider initialLang="en">
        <ReverseRequirementsMatrix report={mockReport} />
      </I18nProvider>
    )

    const toggleBtns = screen.getAllByTitle('Toggle details')
    // Click toggle on row 2 (3.0y row)
    fireEvent.click(toggleBtns[1])

    expect(screen.getByText('Deterministic Calculation Steps')).toBeInTheDocument()
    expect(screen.getByText('P_T = P_0 * (1 + r)^T')).toBeInTheDocument()
    expect(screen.getByText('EPS_T = P_T / Exit_PE')).toBeInTheDocument()
    expect(screen.getByText('CAGR = (EPS_T / EPS_0)^(1 / t_growth) - 1')).toBeInTheDocument()
    expect(screen.getByText(/accn: 0001193125-26-323660/)).toBeInTheDocument()
    expect(screen.getByText('us-gaap:EarningsPerShareDiluted')).toBeInTheDocument()
    expect(screen.getByText('ev-price-001')).toBeInTheDocument()
  })

  it('renders uncomputable matrix state when status is NOT_COMPUTED', () => {
    const uncomputableReport: ReverseRequirementsReportDTO = {
      formula_version: 'reverse-requirements/1.1',
      status: 'NOT_COMPUTED',
      status_reason: 'Missing positive starting EPS anchor.',
      matrix_size: 0,
      reverse_requirements_matrix: [],
      unavailable: [
        { item: 'start_anchor', reason: 'No positive EPS was observed.' },
      ],
    }

    render(
      <I18nProvider initialLang="en">
        <ReverseRequirementsMatrix report={uncomputableReport} />
      </I18nProvider>
    )

    expect(screen.getByText('NOT COMPUTED')).toBeInTheDocument()
    expect(screen.getByText(/Missing positive starting EPS anchor/i)).toBeInTheDocument()
    expect(screen.getByText(/No positive EPS was observed/i)).toBeInTheDocument()
  })
})
