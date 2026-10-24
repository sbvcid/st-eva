import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ResultCards } from '../components/ResultCards'
import { MATRIX_SECTION_ID } from '../components/ReverseRequirementsMatrix'
import {
  AdmissionSummary,
  ReplaySummary,
  ValuationSummary,
} from '../types/api'
import { I18nProvider } from '../i18n'

const admission: AdmissionSummary = {
  total_admitted: 1,
  total_refused: 0,
  metrics_admitted: ['revenue'],
  refusals: [],
}
const replay: ReplaySummary = {
  attempted: true,
  outcome: 'MATCH',
  matched: true,
  reconstructed: true,
  observations_used: 12,
  observations_considered: 12,
}

const renderCards = (valuation: Partial<ValuationSummary>) =>
  render(
    <I18nProvider initialLang="en">
      <ResultCards
        valuation={{ limitations: [], ...valuation } as ValuationSummary}
        admission={admission}
        replay={replay}
        refusalReasons={[]}
        sourceIdentifiers={[]}
      />
    </I18nProvider>,
  )

describe('ResultCards headline-metric reconciliation', () => {
  it('labels headline metrics with their single-point, flat-multiple basis', () => {
    renderCards({
      current_price: 336.64,
      currency: 'USD',
      forward_eps_at_reference_multiple: 11.22,
      required_eps_cagr: 0.2858,
      selected_pe: 30.0,
      selected_pe_basis: 'user_supplied_multiple',
      summary_horizon_years: 1.0,
    })

    // Section heading + distinct-from-matrix note are present.
    expect(screen.getByText('Market-Implied Headline Metrics')).toBeInTheDocument()

    // The summary CAGR is relabelled so it cannot be mistaken for the matrix
    // column, which stays "Req. EPS CAGR".
    expect(screen.getByText('Implied EPS Gap (CAGR)')).toBeInTheDocument()
    expect(screen.queryByText('Req. EPS CAGR')).not.toBeInTheDocument()
    expect(screen.getByText('Price-Implied EPS')).toBeInTheDocument()

    // Explicit basis legend.
    const legend = screen.getByTestId('summary-basis-legend')
    expect(legend).toBeInTheDocument()
    expect(legend.textContent).toMatch(/not a forward\/NTM forecast/i)
    expect(legend.textContent).toMatch(/no required-return hurdle/i)
    expect(legend.textContent).toMatch(/annualised over 1y/i)
    expect(legend.textContent).toMatch(/Your supplied reference multiple/i)

    // Explanatory link toward the matrix.
    expect(
      screen.getByText(/See the reverse-requirements matrix for per-scenario figures/i),
    ).toBeInTheDocument()
  })

  it('states the vendor band-median basis when the reference P/E is not user-supplied', () => {
    renderCards({
      current_price: 425.5,
      currency: 'USD',
      selected_pe: 18.5,
      selected_pe_basis: 'historical_pe_median',
      summary_horizon_years: 1.0,
    })
    const legend = screen.getByTestId('summary-basis-legend')
    expect(legend.textContent).toMatch(/Vendor historical P\/E band median/i)
  })

  it('names the production historical P/E distribution median as the basis', () => {
    // The summary and the matrix must not disagree about whether a qualified
    // reference exists, so the production median is named rather than being
    // reported as "no usable reference".
    renderCards({
      current_price: 336.64,
      currency: 'USD',
      forward_eps_at_reference_multiple: 11.986726959466182,
      required_eps_cagr: 0.2858,
      selected_pe: 28.44563,
      selected_pe_basis: 'production_historical_pe_median',
      summary_horizon_years: 1.0,
    })

    const legend = screen.getByTestId('summary-basis-legend')
    expect(legend.textContent).toMatch(
      /production historical P\/E distribution/i,
    )
    // The basis points at where the qualified sample size and observation
    // period stay inspectable, rather than duplicating them here.
    expect(legend.textContent).toMatch(/production-distribution section/i)
    expect(legend.textContent).not.toMatch(/Vendor historical P\/E band median/i)
    expect(legend.textContent).not.toMatch(/No usable reference multiple/i)
    // The card shows the value and its basis together.
    expect(screen.getByText('28.4x')).toBeInTheDocument()
  })

  it('localises the production-distribution basis in Traditional Chinese', () => {
    render(
      <I18nProvider initialLang="zh-TW">
        <ResultCards
          valuation={
            {
              limitations: [],
              current_price: 336.64,
              currency: 'USD',
              selected_pe: 28.44563,
              selected_pe_basis: 'production_historical_pe_median',
            } as ValuationSummary
          }
          admission={admission}
          replay={replay}
          refusalReasons={[]}
          sourceIdentifiers={[]}
        />
      </I18nProvider>,
    )
    const legend = screen.getByTestId('summary-basis-legend')
    expect(legend.textContent).toContain('產出時點正確歷史本益比分佈之中位數')
    expect(legend.textContent).not.toContain('資料商歷史本益比帶')
    expect(legend.textContent).not.toContain('無可用之參考本益比')
  })

  it('states no usable reference multiple when none was selected', () => {
    renderCards({ selected_pe: null, selected_pe_basis: 'none' })
    const legend = screen.getByTestId('summary-basis-legend')
    expect(legend.textContent).toMatch(/No usable reference multiple/i)
  })

  it('scrolls to the matrix section when the explanatory link is clicked', () => {
    const scrollIntoView = vi.fn()
    // jsdom does not implement scrollIntoView.
    ;(window as unknown as { HTMLElement: { prototype: { scrollIntoView: unknown } } }).HTMLElement.prototype.scrollIntoView =
      scrollIntoView

    render(
      <I18nProvider initialLang="en">
        <>
          <ResultCards
            ticker="AAPL"
            companyName="Apple Inc."
            asOf="2026-10-09"
            valuation={{ limitations: [], current_price: 336.64, selected_pe: 30.0, selected_pe_basis: 'user_supplied_multiple' } as ValuationSummary}
            admission={admission}
            replay={replay}
            refusalReasons={[]}
            sourceIdentifiers={[]}
          />
          <div id={MATRIX_SECTION_ID} />
        </>
      </I18nProvider>,
    )

    fireEvent.click(
      screen.getByText(/See the reverse-requirements matrix for per-scenario figures/i),
    )
    expect(scrollIntoView).toHaveBeenCalledTimes(1)
  })
})

describe('ResultCards partial-admission reconciliation', () => {
  it('lists the admitted and refused metrics behind the counts', () => {
    const partial: AdmissionSummary = {
      total_admitted: 1,
      total_refused: 4,
      metrics_admitted: ['revenue'],
      metrics_refused: [
        'operating_cash_flow',
        'capex',
        'operating_income',
        'depreciation_and_amortization',
      ],
      refusals: [],
    }

    render(
      <I18nProvider initialLang="en">
        <ResultCards
          ticker="MU"
          companyName="Micron Technology"
          asOf="2026-10-16"
          valuation={{ limitations: [], current_price: 878.84, currency: 'USD', selected_pfcf: 67.712721, selected_pfcf_basis: 'production_historical_pfcf_median', implied_fcf_at_reference_multiple: 17878087201.56143, market_cap: 1210573930693.0 } as ValuationSummary}
          admission={partial}
          replay={{ ...replay, outcome: 'DIVERGED', matched: false }}
          refusalReasons={[]}
          sourceIdentifiers={[]}
        />
      </I18nProvider>,
    )

    // The count is reconcilable with a list: all four refused metric names are
    // shown, not only the reason feed.
    expect(screen.getByText(/Admitted metrics:/)).toBeInTheDocument()
    const refusedLine = screen.getByTestId('refused-metrics')
    expect(refusedLine.textContent).toMatch(/Refused metrics:/)
    expect(refusedLine.textContent).toMatch(/operating_cash_flow/)
    expect(refusedLine.textContent).toMatch(/capex/)
    expect(refusedLine.textContent).toMatch(/operating_income/)
    expect(refusedLine.textContent).toMatch(/depreciation_and_amortization/)
  })

  it('omits the refused line when nothing was refused', () => {
    renderCards({ current_price: 336.64 })
    expect(screen.queryByTestId('refused-metrics')).not.toBeInTheDocument()
  })
})

describe('ResultCards bilingual admission counts', () => {
  it('renders the admission counts with metric/row semantics in English', () => {
    renderCards({ current_price: 336.64, currency: 'USD' })
    expect(
      screen.getByText('1 metric(s) / 1 row(s) admitted · 0 metric(s) / 0 row(s) refused')
    ).toBeInTheDocument()
  })

  it('renders the admission counts in Traditional Chinese', () => {
    render(
      <I18nProvider initialLang='zh-TW'>
        <ResultCards
          valuation={{ limitations: [], current_price: 336.64, currency: 'USD' } as ValuationSummary}
          admission={admission}
          replay={replay}
          refusalReasons={[]}
          sourceIdentifiers={[]}
        />
      </I18nProvider>
    )
    expect(
      screen.getByText('1 項指標 / 1 列已準入 · 0 項指標 / 0 列已拒絕')
    ).toBeInTheDocument()
    expect(screen.queryByText('1 metric(s) / 1 row(s) admitted')).not.toBeInTheDocument()
  })
})
