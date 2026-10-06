import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ResultCards } from '../components/ResultCards'
import { ProgressStepper } from '../components/ProgressStepper'

describe('Responsive and Mobile sanity tests', () => {
  it('renders all stepper stages on small screens without throwing', () => {
    render(<ProgressStepper currentStage="admission" />)
    expect(screen.getByText('Resolving company')).toBeInTheDocument()
    expect(screen.getByText('Admission')).toBeInTheDocument()
    expect(screen.getByText('Archive / Replay')).toBeInTheDocument()
  })

  it('renders refusal status with high contrast banner and explanations', () => {
    render(
      <ResultCards
        ticker="TSM"
        companyName="Taiwan Semiconductor Manufacturing Co."
        asOf="2026-06-30"
        researchId="RES-TSM"
        valuation={{
          current_price: 175.0,
          currency: 'USD',
          limitations: ['Descriptive valuation only'],
        }}
        admission={{
          total_admitted: 0,
          total_refused: 1,
          metrics_admitted: [],
          refusals: [
            {
              ref: 'revenue',
              reason: 'Cross-currency ratio withheld: USD market cap / TWD revenue',
            },
          ],
        }}
        replay={{
          attempted: true,
          outcome: 'INSUFFICIENT',
          matched: false,
          reconstructed: false,
          observations_used: 0,
          observations_considered: 2,
          reason: 'No price observation at cutoff',
        }}
        refusalReasons={['Cross-currency ratio withheld: USD market cap / TWD revenue']}
      />
    )

    expect(screen.getByText(/Admission Status: REFUSED/i)).toBeInTheDocument()
    expect(
      screen.getByText(/Cross-currency ratio withheld: USD market cap \/ TWD revenue/i)
    ).toBeInTheDocument()
    expect(screen.getByText('INSUFFICIENT')).toBeInTheDocument()
  })
})

