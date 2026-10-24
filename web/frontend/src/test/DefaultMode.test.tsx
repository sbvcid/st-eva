import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import App from '../App'
import * as apiClient from '../services/apiClient'

vi.mock('../services/apiClient', () => ({
  startAnalysis: vi.fn(),
  getJobStatus: vi.fn(),
  checkHealth: vi.fn(),
  getCoverage: vi.fn(),
}))

const completedJob = (overrides: Record<string, unknown> = {}) =>
  ({
    job_id: 'job-default-mode',
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
      admission_summary: {
        total_admitted: 1,
        total_refused: 0,
        metrics_admitted: ['revenue'],
        refusals: [],
      },
      valuation_summary: { limitations: [] },
      replay_summary: {
        attempted: false,
        matched: false,
        reconstructed: false,
        observations_used: 0,
        observations_considered: 0,
      },
      refusal_reasons: [],
      reverse_requirements: {
        formula_version: 'reverse-requirements/1.1',
        status: 'COMPUTED',
        status_reason: null,
        matrix_size: 1,
        reverse_requirements_matrix: [
          {
            horizon_years: 3.0,
            required_return: 0.1,
            required_return_basis: 'PRICE_RETURN_ONLY',
            exit_multiple: { value: 30.0, source: 'user_supplied' },
            required_exit_price: 400.0,
            required_terminal_eps: 13.33,
            start_eps: { value: 8.72, basis: 'TRAILING_TWELVE_MONTHS', months_covered: 12.0 },
            growth_years: 3.0,
            required_eps_cagr: 0.15,
            total_terminal_eps_growth: 0.528,
            comparison_notes: [],
            flags: [],
            formula_version: 'reverse-requirements/1.1',
          },
        ],
        reading_notes: [],
      },
      ...overrides,
    },
  }) as never

const modeSelect = (): HTMLSelectElement => {
  // The execution-mode control is the drawer's first <select>.
  const selects = screen.getAllByRole('combobox') as HTMLSelectElement[]
  return selects[0]
}

describe('default execution mode and assumptions discoverability', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(apiClient.getCoverage).mockResolvedValue({ issuers: {} })
  })

  it('shows the assumptions/settings panel expanded on initial render', () => {
    render(<App />)
    // No click is required to reach the settings fields.
    expect(screen.getByPlaceholderText('e.g. 20.0')).toBeInTheDocument()
    expect(screen.getByText('Execution Mode')).toBeInTheDocument()
    // The data-source hint is visible on first use.
    expect(screen.getByText(/Live: real Yahoo\/SEC market data/i)).toBeInTheDocument()
    // The always-visible badge states where numbers come from.
    expect(screen.getByTestId('mode-badge')).toHaveTextContent(/live \(Yahoo \/ SEC\)/i)
  })

  it('selects live as the initial mode', () => {
    render(<App />)
    expect(modeSelect().value).toBe('live')
  })

  it('can still be collapsed intentionally and reopened', () => {
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: /Hide Assumptions/i }))
    expect(screen.queryByPlaceholderText('e.g. 20.0')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Scenario Assumptions/i }))
    expect(screen.getByPlaceholderText('e.g. 20.0')).toBeInTheDocument()
  })

  it('sends mode "live" on the first analysis without any interaction', async () => {
    const mockStart = vi.mocked(apiClient.startAnalysis).mockResolvedValue({
      job_id: 'job-default-mode',
      ticker: 'AAPL',
      status: 'PENDING',
    })
    vi.mocked(apiClient.getJobStatus).mockResolvedValue(completedJob())

    render(<App />)
    fireEvent.change(screen.getByPlaceholderText(/Enter ticker/i), { target: { value: 'AAPL' } })
    fireEvent.click(screen.getByRole('button', { name: /^Analyze$/i }))

    await waitFor(() => {
      expect(mockStart).toHaveBeenCalledWith(expect.objectContaining({ ticker: 'AAPL', mode: 'live' }))
    })
  })

  it('restores live when assumptions are reset', () => {
    render(<App />)
    fireEvent.change(modeSelect(), { target: { value: 'regression' } })
    expect(modeSelect().value).toBe('regression')
    fireEvent.click(screen.getByRole('button', { name: /Reset Assumptions/i }))
    expect(modeSelect().value).toBe('live')
  })

  it('keeps regression an explicit choice that stays clearly identified', async () => {
    const mockStart = vi.mocked(apiClient.startAnalysis).mockResolvedValue({
      job_id: 'job-regression',
      ticker: 'MSFT',
      status: 'PENDING',
    })
    vi.mocked(apiClient.getJobStatus).mockResolvedValue(
      completedJob({ ticker: 'MSFT', company_name: 'Microsoft Corporation', source_identifiers: ['RegressionFixture'] })
    )

    render(<App />)
    fireEvent.change(modeSelect(), { target: { value: 'regression' } })
    expect(screen.getByTestId('mode-badge')).toHaveTextContent(/regression fixture/i)
    fireEvent.change(screen.getByPlaceholderText(/Enter ticker/i), { target: { value: 'MSFT' } })
    fireEvent.click(screen.getByRole('button', { name: /^Analyze$/i }))

    await waitFor(() => {
      expect(mockStart).toHaveBeenCalledWith(expect.objectContaining({ ticker: 'MSFT', mode: 'regression' }))
    })
    // The fixture warning banner and provenance distinction are preserved.
    expect(await screen.findByText('REGRESSION FIXTURE (TEST DATA)')).toBeInTheDocument()
    expect(
      screen.getByText(/static test fixture data, not live market observations/i)
    ).toBeInTheDocument()
  })

  it('reports a failed live acquisition visibly instead of falling back', async () => {
    vi.mocked(apiClient.startAnalysis).mockResolvedValue({
      job_id: 'job-failed-live',
      ticker: 'AAPL',
      status: 'PENDING',
    })
    vi.mocked(apiClient.getJobStatus).mockResolvedValue({
      job_id: 'job-failed-live',
      ticker: 'AAPL',
      status: 'FAILED',
      stage: 'failed',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      error: "Could not acquire usable market data for ticker 'AAPL'.",
    } as never)

    render(<App />)
    fireEvent.change(screen.getByPlaceholderText(/Enter ticker/i), { target: { value: 'AAPL' } })
    fireEvent.click(screen.getByRole('button', { name: /^Analyze$/i }))

    expect(await screen.findByText('Analysis Request Error')).toBeInTheDocument()
    expect(
      screen.getByText("Could not acquire usable market data for ticker 'AAPL'.")
    ).toBeInTheDocument()
    // No analysis verdict was fabricated for the failed run.
    expect(screen.queryByText('Analysis Verdict')).not.toBeInTheDocument()
  })

  it('honours a mode change on a second submission', async () => {
    const mockStart = vi.mocked(apiClient.startAnalysis).mockResolvedValue({
      job_id: 'job-default-mode',
      ticker: 'AAPL',
      status: 'PENDING',
    })
    vi.mocked(apiClient.getJobStatus).mockResolvedValue(completedJob())

    render(<App />)
    fireEvent.change(screen.getByPlaceholderText(/Enter ticker/i), { target: { value: 'AAPL' } })
    fireEvent.click(screen.getByRole('button', { name: /^Analyze$/i }))
    await waitFor(() => expect(mockStart).toHaveBeenCalledTimes(1))

    fireEvent.change(modeSelect(), { target: { value: 'auto' } })
    fireEvent.click(screen.getByRole('button', { name: /^Analyze$/i }))

    await waitFor(() => {
      expect(mockStart).toHaveBeenLastCalledWith(
        expect.objectContaining({ ticker: 'AAPL', mode: 'auto' })
      )
    })
  })
})
