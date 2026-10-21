import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import App from '../App'
import * as researchApi from '../services/researchApi'
import { ResearchCatalogue, ResearchMetricDetail } from '../types/research'

vi.mock('../services/researchApi', () => ({
  getResearchCatalogue: vi.fn(),
  getResearchMetric: vi.fn(),
  getResearchObservationEvidence: vi.fn(),
  runResearchCalculation: vi.fn(),
  ResearchApiError: class ResearchApiError extends Error {
    status: number
    refusal?: { reason_code: string; detail: string; production_eligible: boolean }
    constructor(
      status: number,
      message: string,
      refusal?: { reason_code: string; detail: string; production_eligible: boolean },
    ) {
      super(message)
      this.name = 'ResearchApiError'
      this.status = status
      this.refusal = refusal
    }
  },
}))

const METRIC_ID = 'RESEARCH_KO_REPORTED_REVENUE_MULTIPLE'

const catalogue: ResearchCatalogue = {
  metrics: [
    {
      metric_id: METRIC_ID,
      lane_id: 'ko_reported_revenue_multiple',
      issuer_id: 'CIK0000021344',
      instrument_id: 'KO',
      metric_label: 'KO reported-revenue multiple (research)',
      research_purpose:
        'Research use only. A named alternative to a price-to-sales reference for KO.',
      research_use_label: 'RESEARCH USE ONLY. Not a valuation reference.',
      formula_expression:
        '(as-traded close x cover-page shares outstanding) / TTM of us-gaap:Revenues',
      formula_version: 'research-multiples/1.0',
      formula_numerator: 'as-traded close times cover-page shares outstanding',
      formula_denominator: "TTM of us-gaap:Revenues, KO's reported net operating revenues",
      numerator_kind: 'market_cap',
      numerator_label: 'Market capitalisation: the as-traded close times the cover-page share count.',
      denominator_label: "TTM of us-gaap:Revenues, KO's reported net operating revenues",
      status: 'RESEARCH_DISTRIBUTION',
      production_eligible: false,
      candidate_metric: true,
      sample_count: 29,
      total_evaluations: 67,
      refused_count: 38,
      period_start: '2019-07-26',
      period_end: '2026-07-29',
      mean: 6.460903,
      std: 0.56218,
      minimum: 5.248888,
      maximum: 7.776665,
      percentiles: { median: 6.403373 },
      median: 6.403373,
      sampling_cadence: 'PERIODIC_FILING_USABLE_DATES',
      registry_standing: {
        revenue: {
          Revenues: {
            role: 'revenue',
            element: 'us-gaap:Revenues',
            registry_metric_id: 'revenue',
            registry_decision: 'NOT_QUALIFIED',
            reason_code: 'NO_MAPPING_FOR_METRIC',
            qualified: false,
            mapping_type: null,
            relation_kind: null,
            scope: null,
            effective_from: null,
            effective_to: null,
            basis: 'Retired by decision 2.99.',
          },
        },
      },
      production_refusal: { production_eligible: false },
      data_limitations: ['The capture covers periodic filings only.'],
      basis_breaks: {},
      prior_period_revisions: [],
      input_set_id: 'input-set-id-0001',
      content_hash: 'lane-content-hash',
      methodology: 'research-multiples/1.0',
      logic_version: 'research-multiples/1.0.0',
    },
  ],
  research_use_notice: 'RESEARCH USE ONLY. It is not a valuation reference.',
  user_assumption_label: 'user_supplied_research_assumption',
  calculator_version: 'research-calculator/1.0',
}

const detail: ResearchMetricDetail = {
  metric: catalogue.metrics[0],
  observations: [
    {
      evaluation_date: '2026-07-29',
      status: 'AVAILABLE',
      value: 6.403373,
      reason_code: null,
      reason_detail: null,
      price: 69.5,
      shares_outstanding: 4300000000,
      market_cap: 298850000000,
      enterprise_value: null,
      denominator: 46660000000,
      basis_breaks: [],
      content_hash: 'obs-hash-1',
    },
    {
      evaluation_date: '2010-02-26',
      status: 'UNAVAILABLE',
      value: null,
      reason_code: 'RESEARCH_REASON_NO_DENOMINATOR_WINDOW',
      reason_detail: 'The four-quarter window is not knowable at 2010-02-26.',
      price: null,
      shares_outstanding: null,
      market_cap: null,
      enterprise_value: null,
      denominator: null,
      basis_breaks: [],
      content_hash: 'obs-hash-2',
    },
  ],
}

describe('the research surface', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(researchApi.getResearchCatalogue).mockResolvedValue(catalogue)
    vi.mocked(researchApi.getResearchMetric).mockResolvedValue(detail)
  })

  const enterResearchMode = async () => {
    render(<App />)
    fireEvent.click(screen.getByTestId('mode-research'))
    await waitFor(() => {
      expect(screen.getByTestId('research-notice')).toBeInTheDocument()
    })
  }

  it('is a separate surface from the valuation path', async () => {
    render(<App />)
    expect(screen.getByPlaceholderText(/Enter ticker/i)).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('mode-research'))
    await waitFor(() => {
      expect(screen.getByTestId('research-notice')).toBeInTheDocument()
    })
    expect(screen.queryByPlaceholderText(/Enter ticker/i)).not.toBeInTheDocument()
  })

  it('states the research-only standing before any figure is shown', async () => {
    await enterResearchMode()
    expect(screen.getByTestId('research-notice')).toHaveTextContent(
      /not a valuation reference/i,
    )
  })

  it('does not choose a research metric for the user', async () => {
    await enterResearchMode()
    const select = screen.getByTestId('research-metric-select') as HTMLSelectElement
    expect(select.value).toBe('')
    expect(screen.queryByTestId('research-metric-card')).not.toBeInTheDocument()
    expect(screen.queryByTestId('research-calculator')).not.toBeInTheDocument()
    expect(researchApi.getResearchMetric).not.toHaveBeenCalled()
  })

  it('offers only the selectable research metrics', async () => {
    await enterResearchMode()
    await waitFor(() => {
      expect(screen.getByTestId('research-metric-select')).toBeInTheDocument()
    })
    const options = Array.from(
      (screen.getByTestId('research-metric-select') as HTMLSelectElement).options,
    ).map((option) => option.value)
    expect(options).toEqual(['', METRIC_ID])
    expect(options.join(' ')).not.toContain('DOUBLE_COUNTED')
  })

  it('shows the metric, its formula, its counts and why it is not production', async () => {
    await enterResearchMode()
    fireEvent.change(screen.getByTestId('research-metric-select'), {
      target: { value: METRIC_ID },
    })
    await waitFor(() => {
      expect(screen.getByTestId('research-metric-card')).toBeInTheDocument()
    })
    expect(screen.getByTestId('research-valid-count')).toHaveTextContent('29')
    expect(screen.getByTestId('research-median')).toHaveTextContent('6.403373')
    expect(screen.getByTestId('research-metric-card')).toHaveTextContent(
      /us-gaap:Revenues/,
    )
    const refusal = screen.getByTestId('research-production-refusal')
    expect(refusal).toHaveTextContent('NO_MAPPING_FOR_METRIC')
    expect(refusal).toHaveTextContent('NOT_QUALIFIED')
  })

  it('shows the refused observation dates with their reasons', async () => {
    await enterResearchMode()
    fireEvent.change(screen.getByTestId('research-metric-select'), {
      target: { value: METRIC_ID },
    })
    await waitFor(() => {
      expect(screen.getByTestId('research-observations')).toBeInTheDocument()
    })
    const table = screen.getByTestId('research-observations')
    expect(table).toHaveTextContent('2010-02-26')
    expect(table).toHaveTextContent('RESEARCH_REASON_NO_DENOMINATOR_WINDOW')
    expect(table).toHaveTextContent('2026-07-29')
  })

  it('computes a reverse calculation from the user chosen metric', async () => {
    vi.mocked(researchApi.runResearchCalculation).mockResolvedValue({
      metric_id: METRIC_ID,
      lane_id: 'ko_reported_revenue_multiple',
      issuer_id: 'CIK0000021344',
      instrument_id: 'KO',
      status: 'AVAILABLE',
      production_eligible: false,
      research_use_label:
        'RESEARCH USE ONLY. It is not a valuation reference, it is not a production reference chain input, and it must not be presented as one.',
      multiple: 6.403373,
      multiple_source: 'HISTORY_MEDIAN',
      multiple_label: "The metric's own median over its 29 valid observations.",
      multiple_observation_date: null,
      multiple_observation_content_hash: null,
      numerator: 298850000000,
      numerator_source: 'OBSERVATION',
      numerator_label: "This lane's own market capitalisation on 2026-07-29.",
      numerator_kind: 'market_cap',
      numerator_date: '2026-07-29',
      numerator_observation_content_hash: 'obs-hash-1',
      implied_denominator: 46660000000,
      implied_denominator_label: "TTM of us-gaap:Revenues",
      formula_expression: '(as-traded close x cover-page shares outstanding) / TTM of us-gaap:Revenues',
      formula_version: 'research-multiples/1.0',
      formula_operands: { numerator: 298850000000, multiple: 6.403373 },
      lane_input_set_id: 'input-set-id-0001',
      lane_content_hash: 'lane-content-hash',
      calculation_content_hash: 'calculation-hash',
      calculation_version: 'research-calculator/1.0',
      methodology: 'research-multiples/1.0',
      logic_version: 'research-multiples/1.0.0',
      numerator_evidence: { evaluation_date: '2026-07-29' },
      multiple_evidence: { statistic: 'median' },
      registry_standing: {},
      basis_breaks: [],
      prior_period_revisions: [],
      production_refusal: { production_eligible: false },
      data_limitations: [],
    })

    await enterResearchMode()
    fireEvent.change(screen.getByTestId('research-metric-select'), {
      target: { value: METRIC_ID },
    })
    await waitFor(() => {
      expect(screen.getByTestId('research-calculator')).toBeInTheDocument()
    })
    fireEvent.click(screen.getByTestId('research-calculate'))

    await waitFor(() => {
      expect(screen.getByTestId('research-result')).toBeInTheDocument()
    })
    expect(researchApi.runResearchCalculation).toHaveBeenCalledWith({
      metric_id: METRIC_ID,
      multiple_source: 'HISTORY_MEDIAN',
      multiple: null,
      observation_date: null,
      numerator_source: 'OBSERVATION',
      numerator_value: null,
      numerator_date: null,
    })
    expect(screen.getByTestId('research-implied-denominator')).toHaveTextContent(
      '46.660B',
    )
    expect(screen.getByTestId('research-result')).toHaveTextContent(
      /not a valuation reference/i,
    )
  })

  it('labels a user supplied input as a research assumption', async () => {
    vi.mocked(researchApi.runResearchCalculation).mockResolvedValue({
      ...detail.metric,
      metric_id: METRIC_ID,
      lane_id: 'ko_reported_revenue_multiple',
      issuer_id: 'CIK0000021344',
      instrument_id: 'KO',
      status: 'AVAILABLE',
      production_eligible: false,
      research_use_label:
        'RESEARCH USE ONLY. It is not a valuation reference, it is not a production reference chain input, and it must not be presented as one.',
      multiple: 6.5,
      multiple_source: 'USER_SUPPLIED',
      multiple_label: 'A multiple the user supplied.',
      multiple_observation_date: null,
      multiple_observation_content_hash: null,
      numerator: 250000000000,
      numerator_source: 'USER_SUPPLIED',
      numerator_label: 'A market value the user supplied.',
      numerator_kind: 'market_cap',
      numerator_date: null,
      numerator_observation_content_hash: null,
      implied_denominator: 38461538461.5,
      implied_denominator_label: "TTM of us-gaap:Revenues",
      formula_expression: 'formula',
      formula_version: 'research-multiples/1.0',
      formula_operands: {},
      lane_input_set_id: 'input-set-id-0001',
      lane_content_hash: 'lane-content-hash',
      calculation_content_hash: 'calculation-hash',
      calculation_version: 'research-calculator/1.0',
      methodology: 'research-multiples/1.0',
      logic_version: 'research-multiples/1.0.0',
      numerator_evidence: {},
      multiple_evidence: {},
      registry_standing: {},
      basis_breaks: [],
      prior_period_revisions: [],
      production_refusal: { production_eligible: false },
      data_limitations: [],
    })

    await enterResearchMode()
    fireEvent.change(screen.getByTestId('research-metric-select'), {
      target: { value: METRIC_ID },
    })
    await waitFor(() => {
      expect(screen.getByTestId('research-calculator')).toBeInTheDocument()
    })
    fireEvent.change(screen.getByTestId('research-multiple-source'), {
      target: { value: 'USER_SUPPLIED' },
    })
    fireEvent.change(screen.getByTestId('research-multiple-value'), {
      target: { value: '6.5' },
    })
    fireEvent.change(screen.getByTestId('research-numerator-source'), {
      target: { value: 'USER_SUPPLIED' },
    })
    fireEvent.change(screen.getByTestId('research-numerator-value'), {
      target: { value: '250000000000' },
    })
    fireEvent.click(screen.getByTestId('research-calculate'))

    await waitFor(() => {
      expect(screen.getByTestId('research-result')).toBeInTheDocument()
    })
    expect(researchApi.runResearchCalculation).toHaveBeenCalledWith(
      expect.objectContaining({
        multiple_source: 'USER_SUPPLIED',
        multiple: 6.5,
        numerator_source: 'USER_SUPPLIED',
        numerator_value: 250000000000,
      }),
    )
    const badges = screen.getAllByTestId('research-user-assumption')
    expect(badges.length).toBeGreaterThan(0)
    expect(badges[0]).toHaveTextContent('user_supplied_research_assumption')
  })

  it('shows a refusal with its reason code', async () => {
    const failure = new researchApi.ResearchApiError(
      400,
      'refused',
      {
        reason_code: 'RESEARCH_CALCULATION_REFUSED_OBSERVATION_REJECTED',
        detail: 'The evaluation dated 2010-02-26 was refused.',
        production_eligible: false,
      },
    )
    vi.mocked(researchApi.runResearchCalculation).mockRejectedValue(failure)

    await enterResearchMode()
    fireEvent.change(screen.getByTestId('research-metric-select'), {
      target: { value: METRIC_ID },
    })
    await waitFor(() => {
      expect(screen.getByTestId('research-calculator')).toBeInTheDocument()
    })
    fireEvent.click(screen.getByTestId('research-calculate'))

    await waitFor(() => {
      expect(screen.getByTestId('research-error')).toHaveTextContent(
        'RESEARCH_CALCULATION_REFUSED_OBSERVATION_REJECTED',
      )
    })
    expect(screen.queryByTestId('research-result')).not.toBeInTheDocument()
  })

  it('opens the source evidence of one evaluation date', async () => {
    vi.mocked(researchApi.getResearchObservationEvidence).mockResolvedValue({
      evaluation_date: '2026-07-29',
      price: 69.5,
      price_accounting_basis: 'as_traded',
      shares_outstanding: 4300000000,
      shares_accession: '0000021344-26-000047',
      market_cap: 298850000000,
      denominator: { quarters: [] },
      bridge: { components: {} },
    })

    await enterResearchMode()
    fireEvent.change(screen.getByTestId('research-metric-select'), {
      target: { value: METRIC_ID },
    })
    await waitFor(() => {
      expect(screen.getByTestId('research-observations')).toBeInTheDocument()
    })
    fireEvent.click(screen.getByTestId('research-open-2026-07-29'))

    await waitFor(() => {
      expect(screen.getByTestId('research-evidence')).toBeInTheDocument()
    })
    expect(screen.getByTestId('research-evidence')).toHaveTextContent(
      '0000021344-26-000047',
    )
  })
})
