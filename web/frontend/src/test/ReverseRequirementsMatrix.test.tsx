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

  describe('exit-multiple source label in the matrix table', () => {
    // One row carrying the chosen exit multiple, so the label under the value
    // can be asserted without the other fixture rows contributing their own.
    // The same reference is placed in the row's audit evidence, because the
    // runner fills both from one ReferenceMultiple.
    const withMultiple = (
      exit_multiple: Record<string, any>,
    ): ReverseRequirementsReportDTO => ({
      ...mockReport,
      matrix_size: 1,
      reverse_requirements_matrix: [
        {
          ...mockReport.reverse_requirements_matrix[1],
          exit_multiple,
          evidence: {
            ...mockReport.reverse_requirements_matrix[1].evidence,
            multiple_evidence: exit_multiple,
          },
        },
      ],
    })

    const tableLabel = (report: ReverseRequirementsReportDTO): string => {
      const { container } = render(
        <I18nProvider initialLang="en">
          <ReverseRequirementsMatrix report={report} />
        </I18nProvider>
      )
      // The value is followed by its source sub-label in the same cell.
      const cell = Array.from(container.querySelectorAll('td')).find((node) =>
        node.textContent?.includes('x')
      )
      return cell?.querySelector('span.text-\\[10px\\]')?.textContent ?? ''
    }

    it('names the production historical P/E distribution, not "Band"', () => {
      const report = withMultiple({
        value: 33.2,
        source: 'production_historical_pe_percentile',
        period_label: '10th (2021-07-28 to 2026-07-30)',
        sample_size: 24,
        is_user_assumption: false,
        eligibility_state: 'ELIGIBLE_PRODUCTION_DISTRIBUTION',
        usable_for_reference: true,
      })

      expect(tableLabel(report)).toBe('Production point-in-time historical P/E')
      expect(screen.queryByText('Band')).not.toBeInTheDocument()
    })

    it('names a user multiple as the operator assumption, not "Band"', () => {
      const report = withMultiple({
        value: 30.0,
        source: 'user_supplied',
        is_user_assumption: true,
        eligibility_state: 'USER_SPECIFIED',
        usable_for_reference: false,
      })

      expect(tableLabel(report)).toBe('User Assumption')
      expect(screen.queryByText('Band')).not.toBeInTheDocument()
    })

    it('retains an accurate label for a vendor historical P/E band', () => {
      const report = withMultiple({
        value: 25.0,
        source: 'historical_pe_band_percentile',
        is_user_assumption: false,
        eligibility_state: 'ELIGIBLE_HISTORICAL_BAND',
        usable_for_reference: true,
      })

      expect(tableLabel(report)).toBe('Vendor historical P/E band')
    })

    it('does not relabel an unrecognised source as a valid band', () => {
      const report = withMultiple({
        value: 28.0,
        source: 'some_other_reference',
        is_user_assumption: false,
        eligibility_state: 'DESCRIPTIVE_ONLY_UNVERIFIED_SAMPLE_COUNT',
        usable_for_reference: false,
      })

      // The raw identifier stays visible rather than being dressed up as a
      // band, so a reader is never told a source is a band when it is not.
      expect(tableLabel(report)).toBe('some_other_reference')
      expect(screen.queryByText('Band')).not.toBeInTheDocument()
    })

    it('localises the production distribution label', () => {
      render(
        <I18nProvider initialLang="zh-TW">
          <ReverseRequirementsMatrix
            report={withMultiple({
              value: 33.2,
              source: 'production_historical_pe_percentile',
              period_label: 'p50',
              is_user_assumption: false,
              eligibility_state: 'ELIGIBLE_PRODUCTION_DISTRIBUTION',
              usable_for_reference: true,
            })}
          />
        </I18nProvider>
      )

      expect(
        screen.getByText('產出時點正確之歷史本益比'),
      ).toBeInTheDocument()
      expect(screen.queryByText('Band')).not.toBeInTheDocument()
    })

    it('keeps the drawer form on the same source vocabulary', () => {
      // The row and its audit trail must agree about the source; the drawer
      // keeps the prefixed, period-bearing form it already had.
      render(
        <I18nProvider initialLang="en">
          <ReverseRequirementsMatrix
            report={withMultiple({
              value: 33.2,
              source: 'production_historical_pe_percentile',
              period_label: '10th (2021-07-28 to 2026-07-30)',
              sample_size: 24,
              is_user_assumption: false,
              eligibility_state: 'ELIGIBLE_PRODUCTION_DISTRIBUTION',
              usable_for_reference: true,
            })}
          />
        </I18nProvider>
      )
      fireEvent.click(screen.getAllByTitle('Toggle details')[0])

      expect(
        screen.getByText(
          'Source: Production point-in-time historical P/E (10th (2021-07-28 to 2026-07-30))',
        ),
      ).toBeInTheDocument()
    })
  })

  describe('consensus reference panel', () => {
    const withConsensus = (
      scenario: Partial<ReverseRequirementsReportDTO['reverse_requirements_matrix'][number]>,
      consensus_reference: ReverseRequirementsReportDTO['consensus_reference'],
    ): ReverseRequirementsReportDTO => ({
      ...mockReport,
      reverse_requirements_matrix: [{ ...mockReport.reverse_requirements_matrix[1], ...scenario }],
      consensus_reference,
    })

    it('shows the consensus value, its source label and the declared period end', () => {
      const report = withConsensus(
        { gap_vs_consensus_terminal_eps: -0.2648 },
        {
          eps: 9.58043,
          provider: 'YahooFinanceFundamentals',
          source_period_label: '+1y',
          period_end: '2027-09-30',
          period_end_declared_by_source: true,
          target_period_end: '2027-10-09',
          comparison_tolerance_days: 92,
        },
      )

      render(
        <I18nProvider initialLang="en">
          <ReverseRequirementsMatrix report={report} />
        </I18nProvider>
      )
      fireEvent.click(screen.getAllByTitle('Toggle details')[0])

      const panel = screen.getByTestId('consensus-reference')
      expect(panel).toBeInTheDocument()
      expect(panel.textContent).toContain('9.5804')
      expect(panel.textContent).toContain('YahooFinanceFundamentals')
      // The label stays the source's own; it is never rewritten into a date.
      expect(panel.textContent).toContain('+1y')
      expect(panel.textContent).toContain('2027-09-30')
      expect(panel.textContent).toContain('2027-10-09')
      expect(panel.textContent).toContain('-26.48%')
    })

    it('explains a missing gap with the reason that names both period ends', () => {
      const report = withConsensus(
        {
          gap_vs_consensus_terminal_eps: null,
          flags: ['CONSENSUS_PERIOD_NOT_COMPARABLE'],
          comparison_notes: [
            'The consensus period ends on 2028-06-30 while the terminal EPS window ends on 2027-10-09, a difference of 265 days. These are different periods and are not compared here.',
          ],
        },
        {
          eps: 23.67732,
          source_period_label: '+1y',
          period_end: '2028-06-30',
          period_end_declared_by_source: true,
          target_period_end: '2027-10-09',
          comparison_tolerance_days: 92,
        },
      )

      render(
        <I18nProvider initialLang="en">
          <ReverseRequirementsMatrix report={report} />
        </I18nProvider>
      )
      fireEvent.click(screen.getAllByTitle('Toggle details')[0])

      const panel = screen.getByTestId('consensus-reference')
      expect(panel.textContent).toContain('2028-06-30')
      expect(panel.textContent).toContain('2027-10-09')
      expect(panel.textContent).toContain('265 days')
      expect(panel.textContent).not.toContain('0.00%')
    })

    it('states an undeclared period end instead of deriving one from the label', () => {
      const report = withConsensus(
        {
          gap_vs_consensus_terminal_eps: null,
          flags: ['CONSENSUS_PERIOD_NOT_COMPARABLE'],
          comparison_notes: [
            'The consensus EPS declares no readable period end, so no calendar year can be identified to line it up against the terminal EPS.',
          ],
        },
        {
          eps: 23.67732,
          source_period_label: '+1y',
          period_end: null,
          period_end_declared_by_source: false,
          target_period_end: '2027-10-09',
          comparison_tolerance_days: 92,
        },
      )

      render(
        <I18nProvider initialLang="en">
          <ReverseRequirementsMatrix report={report} />
        </I18nProvider>
      )
      fireEvent.click(screen.getAllByTitle('Toggle details')[0])

      const panel = screen.getByTestId('consensus-reference')
      expect(panel.textContent).toContain('undeclared')
      expect(panel.textContent).toContain('+1y')
    })

    it('reports a run with no consensus at all as unavailable', () => {
      const report = withConsensus(
        { gap_vs_consensus_terminal_eps: null, flags: ['NO_CONSENSUS_FOR_COMPARISON'] },
        { eps: null, source_period_label: null, period_end: null },
      )

      render(
        <I18nProvider initialLang="en">
          <ReverseRequirementsMatrix report={report} />
        </I18nProvider>
      )
      fireEvent.click(screen.getAllByTitle('Toggle details')[0])

      const panel = screen.getByTestId('consensus-reference')
      expect(panel.textContent).toContain('No consensus EPS was supplied')
      expect(panel.textContent).toContain('undeclared')
    })

    it('omits the panel entirely when the report carries no consensus block', () => {
      const report: ReverseRequirementsReportDTO = {
        ...mockReport,
        reverse_requirements_matrix: [mockReport.reverse_requirements_matrix[1]],
      }

      render(
        <I18nProvider initialLang="en">
          <ReverseRequirementsMatrix report={report} />
        </I18nProvider>
      )
      fireEvent.click(screen.getAllByTitle('Toggle details')[0])

      expect(screen.queryByTestId('consensus-reference')).not.toBeInTheDocument()
    })
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

// R2.1: a selected EPS value whose direct SEC source cannot be established must
// keep the value and its declared provider, state the missing provenance
// explicitly, and present any related filing only as cross-check evidence.
const unresolvedProvenanceReport: ReverseRequirementsReportDTO = {
  formula_version: 'reverse-requirements/1.1',
  fingerprint: 'mock-fp-unresolved',
  status: 'COMPUTED',
  status_reason: null,
  matrix_size: 1,
  reverse_requirements_matrix: [
    {
      horizon_years: 3.0,
      required_return: 0.10,
      required_return_basis: 'PRICE_RETURN_ONLY',
      exit_multiple: {
        value: 20.0,
        source: 'user_supplied',
      },
      required_exit_price: 133.1,
      required_terminal_eps: 6.655,
      start_eps: {
        value: 13.2,
        basis: 'FORWARD_TWELVE_MONTHS',
        months_covered: 12.0,
        provider: 'RegressionFixture',
      },
      growth_years: 3.0,
      required_eps_cagr: 0.146,
      total_terminal_eps_growth: 0.504,
      comparison_notes: [],
      flags: [],
      formula_version: 'reverse-requirements/1.1',
      calculation_steps: [],
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
          value: 13.2,
          basis: 'FORWARD_TWELVE_MONTHS',
          months_covered: 12.0,
          period_label: 'forward',
          provider: 'RegressionFixture',
          currency: 'USD',
          period_undeclared_by_source: false,
          source_type: 'REGRESSION_FIXTURE',
          observation_id: 'ev-forward-eps-001',
          is_user_assumption: false,
          sec_fact: null,
        },
        multiple_evidence: {
          value: 20.0,
          source: 'user_supplied',
          is_user_assumption: true,
          eligibility_state: 'USER_SPECIFIED',
          usable_for_reference: false,
        },
        user_assumptions: [
          'Holding Horizon: 3 years',
          'Required Return Hurdle: 10% (PRICE_RETURN_ONLY)',
          'Exit Multiple: 20x (user-supplied)',
        ],
        sourced_facts: [
          'Market Price: 100 USD (as-of 2026-09-18, provider: RegressionFixture)',
          'Starting EPS: 13.2 USD (FORWARD_TWELVE_MONTHS, provider: RegressionFixture)',
        ],
        missing_or_unvalidated: [
          'Direct SEC source of selected EPS not established; related filing shown for cross-check only',
        ],
        related_sec_evidence: {
          accession: '0001193125-26-323660',
          form: '10-K',
          filed_date: '2026-07-30',
          concept: 'us-gaap:EarningsPerShareDiluted',
          unit: 'USD/shares',
          period_start: '2025-07-01',
          period_end: '2026-06-30',
          note: 'Related SEC filing (cross-check); not verified as direct source of selected EPS value',
        },
      },
    },
  ],
  reading_notes: [],
}

describe('ReverseRequirementsMatrix SEC provenance labels', () => {
  it('states missing direct SEC provenance without hiding the EPS value', () => {
    render(
      <I18nProvider initialLang="en">
        <ReverseRequirementsMatrix report={unresolvedProvenanceReport} />
      </I18nProvider>
    )

    const toggleBtns = screen.getAllByTitle('Toggle details')
    fireEvent.click(toggleBtns[0])

    // The value and its declared provider remain visible.
    expect(screen.getAllByText('Starting EPS Anchor').length).toBeGreaterThan(0)
    expect(screen.getAllByText('$13.20').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Provider: RegressionFixture').length).toBeGreaterThan(0)
    expect(screen.getByText('EPS provider: RegressionFixture')).toBeInTheDocument()


    // The unresolved provenance is explicit, not silently omitted.
    expect(screen.getByText('Direct SEC source: not established')).toBeInTheDocument()
    expect(
      screen.getByText('Direct SEC source of selected EPS not established; related filing shown for cross-check only'),
    ).toBeInTheDocument()
    expect(screen.getByText('Provider-Sourced (SEC Link Not Established)')).toBeInTheDocument()

    // No filing is presented as the direct source of this value.
    expect(screen.queryByText('Source: SEC 10-K')).not.toBeInTheDocument()
    expect(
      screen.queryByText(/SEC 10-K accession 0001193125-26-323660/),
    ).not.toBeInTheDocument()

    // The related filing is labelled cross-check evidence, never a source.
    expect(screen.getByText(/Related SEC 10-K \(cross-check\)/)).toBeInTheDocument()
    expect(
      screen.getByText('Related SEC filing (cross-check); not verified as direct source of selected EPS value'),
    ).toBeInTheDocument()
  })

  it('labels a linked SEC fact as the direct source of the selected EPS', () => {
    render(
      <I18nProvider initialLang="en">
        <ReverseRequirementsMatrix report={mockReport} />
      </I18nProvider>
    )

    const toggleBtns = screen.getAllByTitle('Toggle details')
    fireEvent.click(toggleBtns[1])

    expect(screen.getByText('Source: SEC 10-K')).toBeInTheDocument()
    expect(screen.getByText('SEC-Linked Source')).toBeInTheDocument()
    expect(screen.getByText(/accn: 0001193125-26-323660/)).toBeInTheDocument()
  })
})
