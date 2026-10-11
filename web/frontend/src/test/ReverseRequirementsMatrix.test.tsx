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
