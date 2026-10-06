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
        mode: 'auto',
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
})
