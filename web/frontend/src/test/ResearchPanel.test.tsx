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
  getResearchDefinitions: vi.fn(),
  getResearchComparability: vi.fn(),
  compareResearchHistory: vi.fn(),
  compareResearchBridges: vi.fn(),
  runResearchSensitivity: vi.fn(),
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

const evidenceFixture = () => ({
  evaluation_date: '2026-07-29',
  price: 89.08,
  price_currency: 'USD',
  price_accounting_basis: 'as_traded',
  price_source: {
    source_file: 'daily_prices.json',
    source_sha256: 'abc123',
    source_url: 'https://example.test/prices',
    as_of_date: '2026-07-29',
    source_known: true,
  },
  shares_outstanding: 4302482418,
  shares_accession: '0001628280-26-028802',
  shares_usable_date: '2026-04-30',
  shares_source: {
    source_file: 'shares_outstanding_concept.json',
    source_sha256: 'def456',
    source_url: 'https://example.test/shares',
    unit: 'shares',
    as_of_date: '2026-04-28',
    source_known: true,
  },
  market_cap: 383265133795.44,
  enterprise_value: null,
  numerator_kind: 'market_cap',
  denominator: {
    unit: 'USD',
    currency: 'USD',
    value: 49284000000,
    quarters: [
      {
        period_end: '2026-04-03',
        value: 12472000000,
        unit: 'USD',
        knowable_from: '2026-04-30',
        accessions: ['0001628280-26-028802'],
        input_spans: [
          {
            source_file: 'revenue_concept.json',
            source_sha256: 'aaa111',
            source_url: 'https://example.test/revenues',
            source_known: true,
          },
        ],
      },
    ],
  },
  bridge: { components: {} },
})

const AAPL_METRIC_ID = 'RESEARCH_AAPL_REPORTED_REVENUE_MULTIPLE'

// A second issuer's lane, with its own figures: the AAPL revenue lane's
// homogeneous successor-only sample, not a restatement of the KO fixture.
const aaplMetric = (): any => ({
  ...catalogue.metrics[0],
  metric_id: AAPL_METRIC_ID,
  lane_id: 'aapl_reported_revenue_multiple',
  issuer_id: 'CIK0000320193',
  instrument_id: 'AAPL',
  metric_label: 'AAPL reported-revenue multiple (research)',
  research_purpose:
    'Research use only. A named revenue multiple for AAPL, over one element.',
  status: 'RESEARCH_DISTRIBUTION',
  sample_count: 28,
  total_evaluations: 67,
  refused_count: 35,
  published_observation_count: 32,
  median: 7.257709,
  mean: 7.4,
  percentiles: { median: 7.257709 },
  period_start: '2019-10-31',
  period_end: '2026-07-31',
  basis: {
    revenue: ['us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax'],
  },
  basis_groups: [],
})

const aaplDetail = (): ResearchMetricDetail => ({
  metric: aaplMetric(),
  observations: [
    {
      evaluation_date: '2026-07-31',
      status: 'AVAILABLE',
      value: 7.257709,
      reason_code: null,
      reason_detail: null,
      price: 213.25,
      shares_outstanding: 15000000000,
      market_cap: 3198750000000,
      enterprise_value: null,
      denominator: 440708000000,
      basis_breaks: [],
      content_hash: 'aapl-obs-hash-1',
    },
  ],
})

const multiIssuerCatalogue = (): ResearchCatalogue => ({
  ...catalogue,
  metrics: [catalogue.metrics[0], aaplMetric()],
})

const definitionsFixture = () => ({
  definitions: [
    {
      metric_id: 'C1',
      lane_id: 'ko_filed_ev_bridge_multiple_production_shape',
      metric_label: 'KO filed enterprise-value bridge multiple, production shape (research)',
      numerator_kind: 'enterprise_value',
      numerator_description: 'Enterprise value',
      denominator_definition: 'TTM of operating income plus D&A',
      denominator_elements: [
        'us-gaap:DepreciationDepletionAndAmortization',
        'us-gaap:OperatingIncomeLoss',
      ],
      currency: 'USD',
      unit: 'USD',
      formula_version: 'research-multiples/1.0',
      formula_expression: '(market cap + total debt ... - liquid funds) / TTM',
      bridge_components: ['cash', 'commercial_paper'],
      candidate_metric: true,
      sample_count: 27,
      total_evaluations: 67,
      period_start: '2011-02-28',
      period_end: '2026-07-29',
      registry_standing: {},
      basis_breaks: {},
    },
    {
      metric_id: 'C2',
      lane_id: 'ko_filed_ev_bridge_multiple_short_term_borrowings',
      metric_label: 'KO filed enterprise-value bridge multiple with loans and notes payable (research)',
      numerator_kind: 'enterprise_value',
      numerator_description: 'Enterprise value',
      denominator_definition: 'TTM of operating income plus D&A',
      denominator_elements: [
        'us-gapa:DepreciationDepletionAndAmortization',
        'us-gaap:OperatingIncomeLoss',
      ],
      currency: 'USD',
      unit: 'USD',
      formula_version: 'research-multiples/1.0',
      formula_expression: '(market cap + total debt ... - liquid funds) / TTM',
      bridge_components: ['cash', 'notes_and_loans_payable'],
      candidate_metric: true,
      sample_count: 29,
      total_evaluations: 67,
      period_start: '2018-10-30',
      period_end: '2026-07-29',
      registry_standing: {},
      basis_breaks: {},
    },
    {
      metric_id: METRIC_ID,
      lane_id: 'ko_reported_revenue_multiple',
      metric_label: 'KO reported-revenue multiple (research)',
      numerator_kind: 'market_cap',
      numerator_description: 'Market capitalisation',
      denominator_definition: "TTM of us-gaap:Revenues",
      denominator_elements: ['us-gaap:Revenues'],
      currency: 'USD',
      unit: 'USD',
      formula_version: 'research-multiples/1.0',
      formula_expression: '(as-traded close x cover-page shares outstanding) / TTM of us-gaap:Revenues',
      bridge_components: ['cash', 'commercial_paper'],
      candidate_metric: true,
      sample_count: 29,
      total_evaluations: 67,
      period_start: '2019-07-26',
      period_end: '2026-07-29',
      registry_standing: {},
      basis_breaks: {},
    },
  ],
  sensitivity_assumptions: {
    NUMERATOR_MULTIPLIER: {
      name: 'NUMERATOR_MULTIPLIER',
      label: 'The market value is multiplied by a factor',
      unit: 'factor',
      applies_to: 'numerator',
    },
  },
  comparison_version: 'research-comparison/1.0',
})

describe('the research surface', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(researchApi.getResearchCatalogue).mockResolvedValue(catalogue)
    vi.mocked(researchApi.getResearchMetric).mockResolvedValue(detail)
    vi.mocked(researchApi.getResearchDefinitions).mockResolvedValue(
      definitionsFixture() as any,
    )
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
    vi.mocked(researchApi.getResearchObservationEvidence).mockResolvedValue(
      evidenceFixture(),
    )

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
      '0001628280-26-028802',
    )
  })

  it('shows the source link, the unit and the period of every input', async () => {
    vi.mocked(researchApi.getResearchObservationEvidence).mockResolvedValue(
      evidenceFixture(),
    )

    await enterResearchMode()
    fireEvent.change(screen.getByTestId('research-metric-select'), {
      target: { value: METRIC_ID },
    })
    await waitFor(() => {
      expect(screen.getByTestId('research-observations')).toBeInTheDocument()
    })
    fireEvent.click(screen.getByTestId('research-open-2026-07-29'))

    await waitFor(() => {
      expect(screen.getByTestId('research-evidence-table')).toBeInTheDocument()
    })
    const table = screen.getByTestId('research-evidence-table')
    expect(table).toHaveTextContent('USD')
    expect(table).toHaveTextContent('shares')
    expect(table).toHaveTextContent('2026-07-29')
    expect(table).toHaveTextContent('2026-04-28')
    const link = table.querySelector('a[href="https://example.test/prices"]')
    expect(link).not.toBeNull()
    expect(link?.textContent).toContain('daily_prices.json')
  })

  it('tells a thin sample apart from a research distribution', async () => {
    const thin = {
      ...catalogue.metrics[0],
      status: 'RESEARCH_THIN_SAMPLE',
      sample_count: 9,
      refused_count: 58,
      min_observations_for_description: 20,
    }
    vi.mocked(researchApi.getResearchCatalogue).mockResolvedValue({
      ...catalogue,
      metrics: [thin],
    })
    vi.mocked(researchApi.getResearchMetric).mockResolvedValue({
      metric: thin,
      observations: detail.observations,
    })

    await enterResearchMode()
    fireEvent.change(screen.getByTestId('research-metric-select'), {
      target: { value: METRIC_ID },
    })
    await waitFor(() => {
      expect(screen.getByTestId('research-distribution-status')).toBeInTheDocument()
    })
    const status = screen.getByTestId('research-distribution-status')
    expect(status).toHaveAttribute('data-status', 'RESEARCH_THIN_SAMPLE')
    expect(status).toHaveTextContent(/thin sample/i)
    expect(status).toHaveTextContent('9')
    expect(status).toHaveTextContent('20')
    expect(status).toHaveTextContent('58')
    expect(screen.getByTestId('research-notice')).toHaveTextContent(
      /not a valuation reference/i,
    )
  })

  it('says why a metric holds no usable distribution', async () => {
    const unavailable = {
      ...catalogue.metrics[0],
      status: 'RESEARCH_UNAVAILABLE',
      sample_count: 0,
      refused_count: 67,
      median: null,
      reason_code: 'RESEARCH_REASON_NO_DENOMINATOR_WINDOW',
      reason_detail: 'No window is knowable at any evaluation date.',
    }
    vi.mocked(researchApi.getResearchCatalogue).mockResolvedValue({
      ...catalogue,
      metrics: [unavailable],
    })
    vi.mocked(researchApi.getResearchMetric).mockResolvedValue({
      metric: unavailable,
      observations: detail.observations,
    })

    await enterResearchMode()
    fireEvent.change(screen.getByTestId('research-metric-select'), {
      target: { value: METRIC_ID },
    })
    await waitFor(() => {
      expect(screen.getByTestId('research-distribution-status')).toBeInTheDocument()
    })
    const status = screen.getByTestId('research-distribution-status')
    expect(status).toHaveAttribute('data-status', 'RESEARCH_UNAVAILABLE')
    expect(status).toHaveTextContent('No window is knowable at any evaluation date.')
    expect(screen.getByTestId('research-median')).toHaveTextContent('—')
  })

  it('shows each issuer lane that is selected, not the previous one', async () => {
    vi.mocked(researchApi.getResearchCatalogue).mockResolvedValue(
      multiIssuerCatalogue(),
    )
    vi.mocked(researchApi.getResearchMetric).mockImplementation(
      (metricId: string) =>
        Promise.resolve(metricId === AAPL_METRIC_ID ? aaplDetail() : detail),
    )

    await enterResearchMode()
    fireEvent.change(screen.getByTestId('research-metric-select'), {
      target: { value: METRIC_ID },
    })
    await waitFor(() => {
      expect(screen.getByTestId('research-metric-card')).toBeInTheDocument()
    })
    expect(screen.getByTestId('research-median')).toHaveTextContent('6.403373')

    fireEvent.change(screen.getByTestId('research-metric-select'), {
      target: { value: AAPL_METRIC_ID },
    })
    await waitFor(() => {
      expect(screen.getByTestId('research-metric-card')).toHaveTextContent(
        /AAPL reported-revenue multiple/,
      )
    })
    // The figures are the selected lane's own: the homogeneous successor
    // sample's median and the elements its observations were read from.
    expect(screen.getByTestId('research-median')).toHaveTextContent('7.257709')
    expect(screen.getByTestId('research-basis')).toHaveTextContent(
      'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
    )
    expect(screen.getByTestId('research-basis')).not.toHaveTextContent(
      'us-gaap:Revenues,',
    )
    // The observation table is the selected metric's, and the previous
    // issuer's dates are gone.
    expect(
      screen.queryByTestId('research-open-2026-07-29'),
    ).not.toBeInTheDocument()
    expect(
      screen.getByTestId('research-open-2026-07-31'),
    ).toBeInTheDocument()
    expect(screen.getByTestId('research-observations')).not.toHaveTextContent(
      'RESEARCH_REASON_NO_DENOMINATOR_WINDOW',
    )
  })

  it('does not leave the previous metric behind a selection that fails to load', async () => {
    vi.mocked(researchApi.getResearchCatalogue).mockResolvedValue(
      multiIssuerCatalogue(),
    )
    await enterResearchMode()
    fireEvent.change(screen.getByTestId('research-metric-select'), {
      target: { value: METRIC_ID },
    })
    await waitFor(() => {
      expect(screen.getByTestId('research-metric-card')).toHaveTextContent(
        /KO reported-revenue multiple/,
      )
    })

    vi.mocked(researchApi.getResearchMetric).mockRejectedValueOnce(
      new Error('load failed'),
    )
    fireEvent.change(screen.getByTestId('research-metric-select'), {
      target: { value: AAPL_METRIC_ID },
    })
    await waitFor(() => {
      expect(screen.getByTestId('research-error')).toHaveTextContent(
        'load failed',
      )
    })
    // The failed selection shows the new metric's own catalogue summary and
    // none of the previous metric's figures: nothing of KO survives behind
    // AAPL's selection.
    expect(screen.getByTestId('research-metric-card')).toHaveTextContent(
      /AAPL reported-revenue multiple/,
    )
    expect(screen.getByTestId('research-median')).toHaveTextContent('7.257709')
    expect(screen.queryByTestId('research-median')).not.toHaveTextContent(
      '6.403373',
    )
    expect(screen.queryByTestId('research-open-2026-07-29')).not.toBeInTheDocument()
  })

  it('does not show a late response for an earlier selection', async () => {
    let resolveKo!: (payload: ResearchMetricDetail) => void
    vi.mocked(researchApi.getResearchCatalogue).mockResolvedValue(
      multiIssuerCatalogue(),
    )
    vi.mocked(researchApi.getResearchMetric).mockImplementation(
      (metricId: string) =>
        metricId === METRIC_ID
          ? new Promise<ResearchMetricDetail>((resolve) => {
              resolveKo = resolve
            })
          : Promise.resolve(aaplDetail()),
    )

    await enterResearchMode()
    fireEvent.change(screen.getByTestId('research-metric-select'), {
      target: { value: METRIC_ID },
    })
    await waitFor(() => {
      expect(screen.getByTestId('research-metric-card')).toBeInTheDocument()
    })
    // The user moves on to AAPL before KO's detail arrives.
    fireEvent.change(screen.getByTestId('research-metric-select'), {
      target: { value: AAPL_METRIC_ID },
    })
    await waitFor(() => {
      expect(screen.getByTestId('research-metric-card')).toHaveTextContent(
        /AAPL reported-revenue multiple/,
      )
    })
    resolveKo(detail)
    await waitFor(() => {
      expect(researchApi.getResearchMetric).toHaveBeenCalledTimes(2)
    })
    // KO's late response is stale: AAPL's figures stay on the card.
    expect(screen.getByTestId('research-metric-card')).toHaveTextContent(
      /AAPL reported-revenue multiple/,
    )
    expect(screen.getByTestId('research-median')).toHaveTextContent('7.257709')
    expect(screen.queryByTestId('research-open-2026-07-29')).not.toBeInTheDocument()
  })

  it('offers the comparison modes and chooses no metric for the user', async () => {
    await enterResearchMode()
    await waitFor(() => {
      expect(screen.getByTestId('research-compare')).toBeInTheDocument()
    })
    expect(screen.getByTestId('compare-mode-history')).toBeInTheDocument()
    expect(screen.getByTestId('compare-mode-pair')).toBeInTheDocument()
    expect(screen.getByTestId('compare-mode-sensitivity')).toBeInTheDocument()
    const select = screen.getByTestId(
      'compare-history-metric',
    ) as HTMLSelectElement
    expect(select.value).toBe('')
  })

  it('compares one metric at two dates and shows the refused dates between', async () => {
    vi.mocked(researchApi.compareResearchHistory).mockResolvedValue({
      comparison_kind: 'SAME_LANE_HISTORY',
      comparison_version: 'research-comparison/1.0',
      comparison_hash: 'comparison-hash-0001',
      production_eligible: false,
      metric_id: METRIC_ID,
      lane_id: 'ko_reported_revenue_multiple',
      earlier: { content_hash: 'earlier-hash' },
      later: { content_hash: 'later-hash' },
      comparison: {
        earlier_multiple: 6.875731,
        later_multiple: 7.776665,
        absolute_change: 0.900934,
        percentage_change: 0.131031,
        earlier_numerator: 369360515241.68,
        later_numerator: 413762133795.44,
        earlier_denominator: 49284000000,
        later_denominator: 49284000000,
      },
      evidence_changes: { elements_changed: [] },
      basis_breaks: { earlier: [], later: [] },
      prior_period_revisions: { earlier: [], later: [] },
      refused_between: [
        {
          evaluation_date: '2026-06-30',
          reason_code: 'RESEARCH_REASON_NO_DENOMINATOR_WINDOW',
          reason_detail: 'no window',
        },
      ],
      refused_between_count: 1,
    } as any)

    await enterResearchMode()
    await waitFor(() => {
      expect(screen.getByTestId('research-compare')).toBeInTheDocument()
    })
    fireEvent.change(screen.getByTestId('compare-history-metric'), {
      target: { value: METRIC_ID },
    })
    fireEvent.change(screen.getByTestId('compare-history-earlier'), {
      target: { value: '2026-04-30' },
    })
    fireEvent.change(screen.getByTestId('compare-history-later'), {
      target: { value: '2026-07-29' },
    })
    fireEvent.click(screen.getByTestId('compare-run'))

    await waitFor(() => {
      expect(screen.getByTestId('compare-history-result')).toBeInTheDocument()
    })
    expect(screen.getByTestId('compare-earlier-multiple')).toHaveTextContent(
      '6.875731',
    )
    expect(screen.getByTestId('compare-later-multiple')).toHaveTextContent(
      '7.776665',
    )
    expect(screen.getByTestId('compare-absolute-change')).toHaveTextContent(
      '0.900934',
    )
    // The dates in between that were refused are shown, not hidden.
    expect(screen.getByTestId('compare-refused-between')).toHaveTextContent(
      'RESEARCH_REASON_NO_DENOMINATOR_WINDOW',
    )
  })

  it('compares two metrics on their shared dates and says what may be compared', async () => {
    vi.mocked(researchApi.getResearchComparability).mockResolvedValue({
      left: { metric_id: 'C1', numerator_kind: 'enterprise_value' },
      right: { metric_id: 'C2', numerator_kind: 'enterprise_value' },
      same_formula: false,
      comparable: true,
      comparable_as: 'PAIRED_BRIDGE',
      shared: { numerator_kind: 'enterprise_value' },
      differences: [],
      reasons: ['The two metrics differ only in the short-term component.'],
    } as any)
    vi.mocked(researchApi.compareResearchBridges).mockResolvedValue({
      comparison_kind: 'PAIRED_BRIDGE',
      comparison_version: 'research-comparison/1.0',
      comparison_hash: 'comparison-hash-0002',
      production_eligible: false,
      paired_sample_count: 16,
      attributable_sample_count: 16,
      shared_date_count: 67,
      unpaired_left: [
        {
          evaluation_date: '2019-04-25',
          reason_code: 'RESEARCH_REASON_MIXED_BALANCE_SHEET_PERIODS',
          side: 'left',
        },
      ],
      unpaired_right: [
        {
          evaluation_date: '2016-02-25',
          reason_code: 'RESEARCH_REASON_INCOMPLETE_EV_BRIDGE',
          side: 'right',
        },
      ],
      refused_on_both: [],
      pairs: [
        {
          evaluation_date: '2026-07-29',
          differences: {
            enterprise_value: 82000000,
            short_term_value_difference: 82000000,
            multiple: 0.005288,
          },
          attributable: true,
          other_factors: [],
        },
      ],
    } as any)

    await enterResearchMode()
    await waitFor(() => {
      expect(screen.getByTestId('research-compare')).toBeInTheDocument()
    })
    fireEvent.click(screen.getByTestId('compare-mode-pair'))
    fireEvent.change(screen.getByTestId('compare-left-metric'), {
      target: { value: 'C1' },
    })
    fireEvent.change(screen.getByTestId('compare-right-metric'), {
      target: { value: 'C2' },
    })
    fireEvent.click(screen.getByTestId('compare-run'))

    await waitFor(() => {
      expect(screen.getByTestId('compare-pairs-result')).toBeInTheDocument()
    })
    expect(screen.getByTestId('compare-paired-count')).toHaveTextContent('16')
    expect(screen.getByTestId('compare-attributable-count')).toHaveTextContent('16')
    // The unpaired dates and their reasons are shown.
    expect(screen.getByTestId('compare-unpaired')).toHaveTextContent(
      'RESEARCH_REASON_MIXED_BALANCE_SHEET_PERIODS',
    )
    expect(screen.getByTestId('compare-unpaired')).toHaveTextContent(
      'RESEARCH_REASON_INCOMPLETE_EV_BRIDGE',
    )
    // The compatibility statement is shown before the numbers.
    expect(screen.getByTestId('compare-compatibility-statement')).toHaveTextContent(
      /short-term component/i,
    )
  })

  it('shows a sensitivity as a named assumption, apart from the observation', async () => {
    vi.mocked(researchApi.runResearchSensitivity).mockResolvedValue({
      comparison_kind: 'SENSITIVITY',
      comparison_version: 'research-comparison/1.0',
      comparison_hash: 'comparison-hash-0003',
      assumption_hash: 'assumption-hash-0001',
      production_eligible: false,
      metric_id: METRIC_ID,
      lane_id: 'ko_reported_revenue_multiple',
      evaluation_date: '2026-07-29',
      assumption: {
        name: 'NUMERATOR_MULTIPLIER',
        label: 'The market value is multiplied by a factor',
        unit: 'factor',
        applies_to: 'numerator',
        value: 1.1,
        origin: 'user_supplied_research_assumption',
      },
      baseline: { multiple: 7.776665, numerator: 413762133795.44, denominator: 49284000000 },
      adjusted: { multiple: 9.235012, numerator: 455138347174.98, denominator: 49284000000 },
      change: { absolute: 1.458347, percentage: 0.187528 },
      formula: '(market value x the factor) / the denominator = the adjusted multiple',
      observation: { content_hash: 'observation-hash-0001' },
      notice: 'A sensitivity is a what-if on one named input.',
    } as any)

    await enterResearchMode()
    await waitFor(() => {
      expect(screen.getByTestId('research-compare')).toBeInTheDocument()
    })
    fireEvent.click(screen.getByTestId('compare-mode-sensitivity'))
    fireEvent.change(screen.getByTestId('compare-sensitivity-metric'), {
      target: { value: METRIC_ID },
    })
    fireEvent.change(screen.getByTestId('compare-sensitivity-date'), {
      target: { value: '2026-07-29' },
    })
    fireEvent.change(screen.getByTestId('compare-sensitivity-value'), {
      target: { value: '1.1' },
    })
    fireEvent.click(screen.getByTestId('compare-run'))

    await waitFor(() => {
      expect(screen.getByTestId('compare-sensitivity-result')).toBeInTheDocument()
    })
    expect(screen.getByTestId('compare-baseline')).toHaveTextContent('7.776665')
    expect(screen.getByTestId('compare-adjusted')).toHaveTextContent('9.235012')
    expect(screen.getByTestId('compare-sensitivity-result')).toHaveTextContent(
      'user_supplied_research_assumption',
    )
  })
})
