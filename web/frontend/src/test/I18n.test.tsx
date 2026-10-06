import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import React from 'react'
import App from '../App'
import { detectBrowserLanguage, STORAGE_KEY } from '../i18n'
import * as apiClient from '../services/apiClient'
import { JobDetailResponse } from '../types/api'

vi.mock('../services/apiClient', () => ({
  startAnalysis: vi.fn(),
  getJobStatus: vi.fn(),
  checkHealth: vi.fn(),
}))

describe('Bilingual (i18n) Interface', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    Object.defineProperty(navigator, 'onLine', {
      value: true,
      configurable: true,
    })
  })

  it('detects default language based on browser setting', () => {
    // English browser
    Object.defineProperty(navigator, 'languages', {
      value: ['en-US', 'en'],
      configurable: true,
    })
    expect(detectBrowserLanguage()).toBe('en')

    // Traditional Chinese browser
    Object.defineProperty(navigator, 'languages', {
      value: ['zh-TW', 'zh'],
      configurable: true,
    })
    expect(detectBrowserLanguage()).toBe('zh-TW')

    // Hong Kong Chinese
    Object.defineProperty(navigator, 'languages', {
      value: ['zh-HK'],
      configurable: true,
    })
    expect(detectBrowserLanguage()).toBe('zh-TW')

    // Other non-zh
    Object.defineProperty(navigator, 'languages', {
      value: ['ja-JP'],
      configurable: true,
    })
    expect(detectBrowserLanguage()).toBe('en')
  })

  it('supports manual language switch and updates UI immediately', () => {
    const { unmount } = render(<App initialLang="en" />)

    // Initial English UI
    expect(screen.getByText('Reverse-engineer market expectations')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Analyze$/i })).toBeInTheDocument()

    // Switch to Chinese
    const zhButton = screen.getByRole('button', { name: '中文' })
    fireEvent.click(zhButton)

    // Immediate Chinese translation
    expect(screen.getByText('反推市場定價預期')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^開始分析$/i })).toBeInTheDocument()
    expect(
      screen.getByText(/目前針對美國 SEC 申報企業最佳化/i)
    ).toBeInTheDocument()

    // Switch back to English
    const enButton = screen.getByRole('button', { name: 'EN' })
    fireEvent.click(enButton)

    expect(screen.getByText('Reverse-engineer market expectations')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Analyze$/i })).toBeInTheDocument()

    unmount()
  })

  it('persists language preference to localStorage', () => {
    const { unmount } = render(<App initialLang="en" />)

    const zhButton = screen.getByRole('button', { name: '中文' })
    fireEvent.click(zhButton)

    expect(localStorage.getItem(STORAGE_KEY)).toBe('zh-TW')

    const enButton = screen.getByRole('button', { name: 'EN' })
    fireEvent.click(enButton)

    expect(localStorage.getItem(STORAGE_KEY)).toBe('en')

    unmount()
  })

  it('renders completed analysis in bilingual mode without translating raw data', async () => {
    const completedJob: JobDetailResponse = {
      job_id: 'job-aapl',
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
        source_identifiers: ['EDGAR:10-K:0000320193-23-000106'],
        admission_summary: {
          total_admitted: 4,
          total_refused: 0,
          metrics_admitted: ['Revenues', 'OperatingIncome'],
          refusals: [],
        },
        valuation_summary: {
          current_price: 189.5,
          currency: 'USD',
          forward_eps_at_reference_multiple: 8.5,
          required_eps_cagr: 0.12,
          selected_pe: 25.0,
          observed_pe: 28.5,
          observed_ps: 7.2,
          observed_pfcf: 24.1,
          observed_ev_ebitda: 21.0,
          limitations: ['Static peer multiple used'],
        },
        replay_summary: {
          attempted: true,
          outcome: 'MATCH',
          matched: true,
          reconstructed: true,
          observations_used: 12,
          observations_considered: 12,
          replay_fidelity: '1.0',
        },
        refusal_reasons: [],
        raw_analysis: {
          evidence_ids: ['EVID-SEC-AAPL-2023'],
        },
      },
    }

    vi.mocked(apiClient.startAnalysis).mockImplementation(async (req) => ({
      job_id: 'job-aapl',
      ticker: req.ticker,
      status: 'PENDING',
    }))
    vi.mocked(apiClient.getJobStatus).mockImplementation(async () => completedJob)

    const { unmount } = render(<App initialLang="en" />)

    const input = screen.getByPlaceholderText(/Enter ticker/i)
    fireEvent.change(input, { target: { value: 'AAPL' } })
    const submitBtn = screen.getByRole('button', { name: /Analyze/i })
    fireEvent.click(submitBtn)

    // Wait for completed result
    expect(await screen.findByText('Apple Inc.')).toBeInTheDocument()

    // English labels
    expect(screen.getByText('Market Price')).toBeInTheDocument()
    expect(screen.getByText(/Admission Status:\s*ADMITTED/i)).toBeInTheDocument()
    expect(screen.getByText('Observed Valuation Multiples')).toBeInTheDocument()
    expect(screen.getByText('Point-in-Time Replay Verification')).toBeInTheDocument()
    expect(screen.getByText('Evidence & Regulatory Provenance')).toBeInTheDocument()

    // Raw facts MUST NOT be translated
    expect(screen.getAllByText('AAPL').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('Apple Inc.')).toBeInTheDocument()

    // Switch to Chinese while result is displayed (without resetting)
    const zhButton = screen.getByRole('button', { name: '中文' })
    fireEvent.click(zhButton)

    // Chinese labels rendered immediately
    expect(screen.getByText('分析結果裁決')).toBeInTheDocument()
    expect(screen.getByText('市場價格')).toBeInTheDocument()
    expect(screen.getByText(/準入審查狀態：\s*已準入/i)).toBeInTheDocument()
    expect(screen.getByText('觀測估值倍數')).toBeInTheDocument()
    expect(screen.getByText('歷史切點重演驗證')).toBeInTheDocument()
    expect(screen.getByText('事實證據與監管溯源')).toBeInTheDocument()

    // Raw data STILL intact
    expect(screen.getAllByText('AAPL').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('Apple Inc.')).toBeInTheDocument()
    expect(screen.getByText('USD 189.50')).toBeInTheDocument()

    unmount()
  })

  it('renders TSM refusal in both languages without generic error', async () => {
    const tsmJob: JobDetailResponse = {
      job_id: 'job-tsm',
      ticker: 'TSM',
      status: 'COMPLETED',
      stage: 'completed',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      result: {
        ticker: 'TSM',
        company_name: 'Taiwan Semiconductor Manufacturing Co.',
        status: 'refused',
        as_of: '2026-06-30',
        source_identifiers: [],
        admission_summary: {
          total_admitted: 0,
          total_refused: 1,
          metrics_admitted: [],
          refusals: [{ category: 'CURRENCY_MISMATCH', reason: 'cross-currency ratio must be withheld: USD vs TWD' }],
        },
        valuation_summary: { limitations: [] },
        replay_summary: { attempted: false, matched: false, reconstructed: false, observations_used: 0, observations_considered: 0 },
        refusal_reasons: ['cross-currency ratio must be withheld: USD vs TWD'],
      },
    }

    vi.mocked(apiClient.startAnalysis).mockImplementation(async (req) => ({
      job_id: 'job-tsm',
      ticker: req.ticker,
      status: 'PENDING',
    }))
    vi.mocked(apiClient.getJobStatus).mockImplementation(async () => tsmJob)

    const { unmount } = render(<App initialLang="en" />)

    const input = screen.getByPlaceholderText(/Enter ticker/i)
    fireEvent.change(input, { target: { value: 'TSM' } })
    const submitBtn = screen.getByRole('button', { name: /Analyze/i })
    fireEvent.click(submitBtn)

    expect(await screen.findByText(/Admission Status:\s*REFUSED/i)).toBeInTheDocument()

    // English refusal text
    expect(screen.getByText(/This issuer was legitimately withheld per data contract/i)).toBeInTheDocument()
    expect(screen.getByText('cross-currency ratio must be withheld: USD vs TWD')).toBeInTheDocument()

    // Switch to Chinese
    const zhButton = screen.getByRole('button', { name: '中文' })
    fireEvent.click(zhButton)

    // Chinese refusal text
    expect(screen.getByText(/準入審查狀態：\s*拒絕準入/i)).toBeInTheDocument()
    expect(screen.getByText(/依據數據契約與可比性規則/i)).toBeInTheDocument()
    // Raw contract refusal string preserved
    expect(screen.getByText('cross-currency ratio must be withheld: USD vs TWD')).toBeInTheDocument()

    unmount()
  })

  it('allows mobile language switch without layout failure', () => {
    const { unmount } = render(<App initialLang="en" />)

    const zhBtn = screen.getByRole('button', { name: '中文' })
    expect(zhBtn).toBeInTheDocument()

    fireEvent.click(zhBtn)
    expect(screen.getByText('反推市場定價預期')).toBeInTheDocument()

    const enBtn = screen.getByRole('button', { name: 'EN' })
    fireEvent.click(enBtn)
    expect(screen.getByText('Reverse-engineer market expectations')).toBeInTheDocument()

    unmount()
  })
})
