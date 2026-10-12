import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import App from '../App'
import * as apiClient from '../services/apiClient'
import { JobDetailResponse } from '../types/api'

vi.mock('../services/apiClient', () => ({
  startAnalysis: vi.fn(),
  getJobStatus: vi.fn(),
  checkHealth: vi.fn(),
}))

describe('ST-EVA Frontend App Component', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders title, input, and quick examples', () => {
    render(<App />)
    expect(screen.getByText('ST-EVA')).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/Enter ticker/i)).toBeInTheDocument()
    expect(screen.getByText('AAPL')).toBeInTheDocument()
    expect(screen.getByText('TSM')).toBeInTheDocument()
  })

  it('renders coverage notice near the ticker search area', () => {
    render(<App />)
    expect(
      screen.getByText(
        'Currently optimized for U.S. SEC-reporting companies. Coverage may vary for foreign issuers and non-U.S. securities.'
      )
    ).toBeInTheDocument()
  })

  it('handles ticker input change and submission to API', async () => {
    const mockStart = vi.mocked(apiClient.startAnalysis).mockResolvedValue({
      job_id: 'job-test123',
      ticker: 'AAPL',
      status: 'PENDING',
    })

    vi.mocked(apiClient.getJobStatus).mockResolvedValue({
      job_id: 'job-test123',
      ticker: 'AAPL',
      status: 'COMPLETED',
      stage: 'completed',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      result: {
        ticker: 'AAPL',
        company_name: 'Apple Inc.',
        status: 'success',
        as_of: '2026-06-30',
        source_identifiers: [],
        admission_summary: { total_admitted: 0, total_refused: 0, metrics_admitted: [], refusals: [] },
        valuation_summary: { limitations: [] },
        replay_summary: { attempted: false, matched: false, reconstructed: false, observations_used: 0, observations_considered: 0 },
        refusal_reasons: [],
      },
    })

    const { unmount } = render(<App />)
    const input = screen.getByPlaceholderText(/Enter ticker/i)
    fireEvent.change(input, { target: { value: 'AAPL' } })
    const submitBtn = screen.getByRole('button', { name: /Analyze/i })
    fireEvent.click(submitBtn)

    await waitFor(() => {
      expect(mockStart).toHaveBeenCalledWith({
        ticker: 'AAPL',
        mode: 'live',
      })
    })

    await waitFor(() => {
      expect(screen.getByText('Apple Inc.')).toBeInTheDocument()
    })
    unmount()
  })

  it('renders completed analysis with valuation and MATCH replay status', async () => {
    const completedJob: JobDetailResponse = {
      job_id: 'job-msft-done',
      ticker: 'MSFT',
      status: 'COMPLETED',
      stage: 'completed',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      result: {
        ticker: 'MSFT',
        company_name: 'Microsoft Corporation',
        status: 'success',
        as_of: '2026-09-18',
        research_id: 'RES-TEST001',
        source_identifiers: ['RegressionFixture'],
        admission_summary: {
          total_admitted: 1,
          total_refused: 0,
          metrics_admitted: ['revenue'],
          refusals: [],
        },
        valuation_summary: {
          current_price: 425.50,
          currency: 'USD',
          forward_eps_at_reference_multiple: 23.0,
          selected_pe: 18.5,
          observed_pe: 35.2,
          observed_ps: 12.1,
          limitations: ['Conditional reverse valuation'],
        },
        replay_summary: {
          attempted: true,
          outcome: 'MATCH',
          matched: true,
          reconstructed: true,
          observations_used: 12,
          observations_considered: 12,
        },
        refusal_reasons: [],
        raw_analysis: {
          evidence_ids: ['ev-price-001'],
        },
      },
    }

    vi.mocked(apiClient.startAnalysis).mockImplementation(async (req) => ({
      job_id: 'job-msft-done',
      ticker: req.ticker,
      status: 'PENDING',
    }))
    vi.mocked(apiClient.getJobStatus).mockImplementation(async () => completedJob)

    const { unmount } = render(<App />)
    const input = screen.getByPlaceholderText(/Enter ticker/i)
    fireEvent.change(input, { target: { value: 'MSFT' } })
    const submitBtn = screen.getByRole('button', { name: /Analyze/i })

    fireEvent.click(submitBtn)

    expect(await screen.findByText('Microsoft Corporation')).toBeInTheDocument()
    expect(screen.getByText(/Admission Status: ADMITTED/i)).toBeInTheDocument()
    unmount()
  })

  it('renders TSM contract refusal correctly as 1st class UX rather than generic error', async () => {
    const tsmJob: JobDetailResponse = {
      job_id: 'job-tsm-refused',
      ticker: 'TSM',
      status: 'COMPLETED',
      stage: 'completed',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      result: {
        ticker: 'TSM',
        company_name: 'Taiwan Semiconductor Manufacturing Co.',
        status: 'success',
        as_of: '2026-06-30',
        source_identifiers: ['SecEdgar'],
        admission_summary: {
          total_admitted: 0,
          total_refused: 1,
          metrics_admitted: [],
          refusals: [
            {
              ref: 'revenue',
              reason: 'cross-currency ratio must be withheld: USD vs TWD',
              category: 'CURRENCY_MISMATCH',
            },
          ],
        },
        valuation_summary: {
          current_price: 175.0,
          currency: 'USD',
          limitations: [],
        },
        replay_summary: {
          attempted: true,
          outcome: 'INSUFFICIENT',
          matched: false,
          reconstructed: false,
          observations_used: 0,
          observations_considered: 4,
          reason: 'no price observation for TSM is knowable at 2026-06-30',
        },
        refusal_reasons: ['cross-currency ratio must be withheld: USD vs TWD'],
        raw_analysis: {},
      },
    }

    vi.mocked(apiClient.startAnalysis).mockResolvedValue({
      job_id: 'job-tsm-refused',
      ticker: 'TSM',
      status: 'PENDING',
    })
    vi.mocked(apiClient.getJobStatus).mockResolvedValue(tsmJob)

    render(<App />)
    const tsmBtn = screen.getByText('TSM')
    fireEvent.click(tsmBtn)

    await waitFor(() => {
      expect(screen.getByText('Taiwan Semiconductor Manufacturing Co.')).toBeInTheDocument()
      expect(screen.getByText(/Admission Status: REFUSED/i)).toBeInTheDocument()
      expect(screen.getByText(/cross-currency ratio must be withheld: USD vs TWD/i)).toBeInTheDocument()
      expect(screen.queryByText(/Something went wrong/i)).not.toBeInTheDocument()
    })
  })

  it('renders FAILED status with detailed server error message', async () => {
    const failedJob: JobDetailResponse = {
      job_id: 'job-failed',
      ticker: 'UNKNOWN',
      status: 'FAILED',
      stage: 'failed',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      error: 'Upstream vendor market data unreachable',
      result: null,
    }

    vi.mocked(apiClient.startAnalysis).mockResolvedValue({
      job_id: 'job-failed',
      ticker: 'UNKNOWN',
      status: 'PENDING',
    })
    vi.mocked(apiClient.getJobStatus).mockResolvedValue(failedJob)

    render(<App />)
    const input = screen.getByPlaceholderText(/Enter ticker/i)
    fireEvent.change(input, { target: { value: 'UNKNOWN' } })
    fireEvent.click(screen.getByRole('button', { name: /Analyze/i }))

    await waitFor(() => {
      expect(screen.getByText(/Upstream vendor market data unreachable/i)).toBeInTheDocument()
    })
  })

  it('passes user-specified scenario assumptions to startAnalysis', async () => {
    const mockStart = vi.mocked(apiClient.startAnalysis).mockResolvedValue({
      job_id: 'job-custom-assumptions',
      ticker: 'AAPL',
      status: 'PENDING',
    })

    vi.mocked(apiClient.getJobStatus).mockResolvedValue({
      job_id: 'job-custom-assumptions',
      ticker: 'AAPL',
      status: 'COMPLETED',
      stage: 'completed',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      result: {
        ticker: 'AAPL',
        company_name: 'Apple Inc.',
        status: 'success',
        as_of: '2026-06-30',
        source_identifiers: [],
        admission_summary: { total_admitted: 0, total_refused: 0, metrics_admitted: [], refusals: [] },
        valuation_summary: { limitations: [] },
        replay_summary: { attempted: false, matched: false, reconstructed: false, observations_used: 0, observations_considered: 0 },
        refusal_reasons: [],
        reverse_requirements: {
          formula_version: 'reverse-requirements/1.1',
          status: 'COMPUTED',
          matrix_size: 1,
          reverse_requirements_matrix: [
            {
              horizon_years: 3.0,
              required_return: 0.12,
              required_return_basis: 'PRICE_RETURN_ONLY',
              exit_multiple: { value: 25.0, source: 'user_supplied' },
              required_exit_price: 200.0,
              required_terminal_eps: 8.0,
              start_eps: { value: 6.0, basis: 'TRAILING_TWELVE_MONTHS', months_covered: 12.0 },
              growth_years: 3.0,
              required_eps_cagr: 0.10,
              total_terminal_eps_growth: 0.33,
              comparison_notes: [],
              flags: [],
              formula_version: 'reverse-requirements/1.1',
            },
          ],
        },
      },
    })

    render(<App />)

    // The assumptions drawer is expanded by default, so its fields are reachable
    // without opening anything.

    // Set assumptions
    const refMultipleInput = screen.getByPlaceholderText('e.g. 20.0')
    fireEvent.change(refMultipleInput, { target: { value: '25.0' } })

    const horizonsInput = screen.getByPlaceholderText('e.g. 1.0, 2.0, 3.0, 5.0')
    fireEvent.change(horizonsInput, { target: { value: '3.0' } })

    const returnsInput = screen.getByPlaceholderText('e.g. 8, 10, 12, 15')
    fireEvent.change(returnsInput, { target: { value: '12' } })

    const input = screen.getByPlaceholderText(/Enter ticker/i)
    fireEvent.change(input, { target: { value: 'AAPL' } })
    fireEvent.click(screen.getByRole('button', { name: /^Analyze$/i }))

    await waitFor(() => {
      expect(mockStart).toHaveBeenCalledWith({
        ticker: 'AAPL',
        mode: 'live',
        reference_multiple: 25.0,
        reverse_horizons: [3.0],
        required_returns: [0.12],
      })
    })

    // Matrix component is rendered with formula version
    expect(await screen.findByText('Reverse Requirements Matrix')).toBeInTheDocument()
    expect(screen.getByText('reverse-requirements/1.1')).toBeInTheDocument()
  })

  it('renders regression fixture notice when data comes from RegressionFixture', async () => {
    vi.mocked(apiClient.startAnalysis).mockResolvedValue({
      job_id: 'job-regression-fixture',
      ticker: 'MSFT',
      status: 'PENDING',
    })

    vi.mocked(apiClient.getJobStatus).mockResolvedValue({
      job_id: 'job-regression-fixture',
      ticker: 'MSFT',
      status: 'COMPLETED',
      stage: 'completed',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      result: {
        ticker: 'MSFT',
        company_name: 'Microsoft Corporation',
        status: 'success',
        as_of: '2026-09-18',
        source_identifiers: ['RegressionFixture'],
        admission_summary: { total_admitted: 1, total_refused: 0, metrics_admitted: [], refusals: [] },
        valuation_summary: { limitations: [] },
        replay_summary: { attempted: false, matched: false, reconstructed: false, observations_used: 0, observations_considered: 0 },
        refusal_reasons: [],
      },
    })

    render(<App />)
    const input = screen.getByPlaceholderText(/Enter ticker/i)
    fireEvent.change(input, { target: { value: 'MSFT' } })
    fireEvent.click(screen.getByRole('button', { name: /Analyze/i }))

    await waitFor(() => {
      expect(screen.getByText('REGRESSION FIXTURE (TEST DATA)')).toBeInTheDocument()
      expect(
        screen.getByText(/This valuation reflects static test fixture data, not live market observations/i)
      ).toBeInTheDocument()
    })
  })
})

// R5: the results interface exposes JSON/CSV exports of the analysis currently
// displayed, built from the exact typed response (never recomputed), and a
// second submission must export its own result rather than stale data.
describe('ST-EVA result exports', () => {
  const captureBlobUrl = () => {
    const captured: { blob: Blob | null } = { blob: null }
    URL.createObjectURL = vi.fn((b: Blob) => {
      captured.blob = b
      return 'blob:mock'
    }) as unknown as typeof URL.createObjectURL
    URL.revokeObjectURL = vi.fn() as unknown as typeof URL.revokeObjectURL
    return captured
  }

  const readBlobText = async (blob: Blob): Promise<string> => {
    if (typeof (blob as { text?: () => Promise<string> }).text === 'function') {
      return blob.text()
    }
    return new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(String(reader.result))
      reader.onerror = () => reject(reader.error)
      reader.readAsText(blob)
    })
  }

  const buildJob = (
    jobId: string,
    ticker: string,
    scenarios: unknown[],
    matrixSize: number,
  ): JobDetailResponse => ({
    job_id: jobId,
    ticker,
    status: 'COMPLETED',
    stage: 'completed',
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    result: {
      ticker,
      company_name: 'Test Corp',
      status: 'success',
      as_of: '2026-10-09',
      research_id: 'RES-R5',
      source_identifiers: ['YahooFinance', 'API_LIVE'],
      admission_summary: { total_admitted: 1, total_refused: 0, metrics_admitted: ['revenue'], refusals: [] },
      valuation_summary: { limitations: [], current_price: 100.0, currency: 'USD', selected_pe: 20.0, selected_pe_basis: 'user_supplied_multiple', summary_horizon_years: 1.0 },
      replay_summary: { attempted: false, matched: false, reconstructed: false, observations_used: 0, observations_considered: 0 },
      refusal_reasons: [],
      reverse_requirements: {
        formula_version: 'reverse-requirements/1.1',
        status: 'COMPUTED',
        status_reason: null,
        matrix_size: matrixSize,
        reverse_requirements_matrix: scenarios,
        reading_notes: [],
      },
      raw_analysis: { leaked_marker: 'RAW' },
    } as unknown as JobDetailResponse['result'],
  })

  const scenario = (exitValue: number, cagr: number) => ({
    horizon_years: 3.0,
    required_return: 0.1,
    required_return_basis: 'PRICE_RETURN_ONLY',
    exit_multiple: { value: exitValue, source: 'user_supplied', is_user_assumption: true, eligibility_state: 'USER_SPECIFIED', usable_for_reference: false },
    required_exit_price: 100.0 * 1.1 ** 3,
    required_terminal_eps: (100.0 * 1.1 ** 3) / exitValue,
    start_eps: { value: 4.0, basis: 'TRAILING_TWELVE_MONTHS', months_covered: 12.0, source_type: 'API_LIVE', is_user_assumption: false },
    growth_years: 3.0,
    required_eps_cagr: cagr,
    total_terminal_eps_growth: cagr * 3,
    comparison_notes: [],
    flags: [],
    formula_version: 'reverse-requirements/1.1',
  })

  it('renders export controls after a completed analysis', async () => {
    vi.mocked(apiClient.startAnalysis).mockResolvedValue({ job_id: 'job-exp', ticker: 'AAPL', status: 'PENDING' })
    vi.mocked(apiClient.getJobStatus).mockResolvedValue(buildJob('job-exp', 'AAPL', [scenario(20, 0.13)], 1))

    render(<App />)
    fireEvent.change(screen.getByPlaceholderText(/Enter ticker/i), { target: { value: 'AAPL' } })
    fireEvent.click(screen.getByRole('button', { name: /Analyze/i }))

    expect(await screen.findByTestId('export-json')).toBeInTheDocument()
    expect(screen.getByTestId('export-csv')).toBeInTheDocument()
  })

  it('exports the currently displayed result as re-parseable JSON without raw_analysis', async () => {
    vi.mocked(apiClient.startAnalysis).mockResolvedValue({ job_id: 'job-json', ticker: 'AAPL', status: 'PENDING' })
    vi.mocked(apiClient.getJobStatus).mockResolvedValue(buildJob('job-json', 'AAPL', [scenario(20, 0.13)], 1))
    const capture = captureBlobUrl()

    render(<App />)
    fireEvent.change(screen.getByPlaceholderText(/Enter ticker/i), { target: { value: 'AAPL' } })
    fireEvent.click(screen.getByRole('button', { name: /Analyze/i }))
    await screen.findByTestId('export-json')

    fireEvent.click(screen.getByTestId('export-json'))
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1)

    const envelope = JSON.parse(await readBlobText(capture.blob as Blob))
    expect(envelope.export.ticker).toBe('AAPL')
    expect(envelope.export.mode).toBe('live')
    expect('raw_analysis' in envelope.result).toBe(false)
    expect(JSON.stringify(envelope)).not.toContain('leaked_marker')
    expect(envelope.result.reverse_requirements.reverse_requirements_matrix).toHaveLength(1)
  })

  it('a second submission exports its own CSV, not stale data from the first', async () => {
    let call = 0
    vi.mocked(apiClient.startAnalysis).mockImplementation(async (req) => ({
      job_id: `job-${req.ticker}`,
      ticker: req.ticker,
      status: 'PENDING',
    }))
    vi.mocked(apiClient.getJobStatus).mockImplementation(async () => {
      call += 1
      return call === 1
        ? buildJob('job-AAPL', 'AAPL', [scenario(20, 0.13), scenario(22, 0.11)], 2)
        : buildJob('job-MSFT', 'MSFT', [scenario(32, 0.19)], 1)
    })
    const capture = captureBlobUrl()

    render(<App />)
    // Submission 1: AAPL with two scenarios.
    fireEvent.change(screen.getByPlaceholderText(/Enter ticker/i), { target: { value: 'AAPL' } })
    fireEvent.click(screen.getByRole('button', { name: /^Analyze$/i }))
    await screen.findByTestId('export-csv')

    // Submission 2: MSFT with a single, different scenario.
    fireEvent.change(screen.getByPlaceholderText(/Enter ticker/i), { target: { value: 'MSFT' } })
    fireEvent.click(screen.getByRole('button', { name: /^Analyze$/i }))
    await screen.findByText('Test Corp')

    fireEvent.click(screen.getByTestId('export-csv'))
    const csv = await readBlobText(capture.blob as Blob)
    const lines = csv.split('\r\n')

    expect(lines[0]).toContain('record_type')
    // Header + exactly one scenario row for the second (current) submission.
    expect(lines).toHaveLength(2)
    expect(lines[1]).toContain('MSFT')
    expect(lines[1]).toContain('32')
    expect(lines[1]).toContain('0.19')
  })
})
