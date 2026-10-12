import { describe, it, expect } from 'vitest'
import {
  AnalysisResultDTO,
  AnalyzeRequest,
  EpsScenarioDTO,
  ReverseRequirementsReportDTO,
} from '../types/api'
import {
  EXPORT_SCHEMA_VERSION,
  REVERSE_REQUIREMENTS_CSV_COLUMNS,
  buildReverseRequirementsExport,
  buildReverseRequirementsJson,
  buildReverseRequirementsCsv,
} from '../services/exportResult'

/**
 * Minimal RFC-4180-ish CSV parser used only to prove the exported file can be
 * parsed again and inspected without the frontend runtime.
 */
function parseCsv(text: string): string[][] {
  const rows: string[][] = []
  let row: string[] = []
  let field = ''
  let inQuotes = false
  for (let i = 0; i < text.length; i++) {
    const c = text[i]
    if (inQuotes) {
      if (c === '"') {
        if (text[i + 1] === '"') {
          field += '"'
          i++
        } else {
          inQuotes = false
        }
      } else {
        field += c
      }
    } else if (c === '"') {
      inQuotes = true
    } else if (c === ',') {
      row.push(field)
      field = ''
    } else if (c === '\n') {
      row.push(field)
      rows.push(row)
      row = []
      field = ''
    } else if (c === '\r') {
      // Handled by the following '\n'.
    } else {
      field += c
    }
  }
  row.push(field)
  rows.push(row)
  return rows
}

function csvToObjects(text: string): Record<string, string>[] {
  const rows = parseCsv(text)
  const header = rows[0]
  return rows.slice(1).map((cells) => {
    const obj: Record<string, string> = {}
    header.forEach((col, idx) => {
      obj[col] = cells[idx] ?? ''
    })
    return obj
  })
}

const GENERATED_AT = new Date('2026-10-12T00:00:00.000Z')

const userScenario: EpsScenarioDTO = {
  price: 336.64,
  as_of: '2026-10-09',
  horizon_years: 3.0,
  required_return: 0.1,
  required_return_basis: 'PRICE_RETURN_ONLY',
  exit_multiple: {
    value: 30.0,
    source: 'user_supplied',
    is_user_assumption: true,
    eligibility_state: 'USER_SPECIFIED',
    usable_for_reference: false,
  },
  required_exit_price: 448.06784,
  required_exit_price_basis: 'PRICE_ONLY_EXCLUDES_DIVIDENDS',
  required_terminal_eps: 14.935595,
  start_eps: {
    value: 8.72,
    basis: 'TRAILING_TWELVE_MONTHS',
    months_covered: 12.0,
    provider: 'YahooFinance',
    source_type: 'API_LIVE',
    is_user_assumption: false,
  },
  growth_years: 3.0,
  required_eps_cagr: 0.1965,
  total_terminal_eps_growth: 0.7128,
  comparison_notes: [],
  flags: ['REQUIRED_RETURN_EXCLUDES_DIVIDENDS'],
  formula_version: 'reverse-requirements/1.1',
  calculation_steps: [
    {
      step_number: 1,
      step_id: 'required_exit_price',
      name: 'Required Exit Price',
      formula_expression: 'P_T = P_0 * (1 + r)^T',
      operands: { price: 336.64, required_return: 0.1, horizon_years: 3.0 },
      output_value: 448.06784,
      output_unit: 'USD',
      reproducible: true,
      status: 'COMPUTED',
      status_reason: null,
    },
    {
      step_number: 4,
      step_id: 'required_eps_cagr',
      name: 'Required EPS CAGR',
      formula_expression: 'CAGR = (EPS_T / EPS_0)^(1 / t_growth) - 1',
      operands: { required_terminal_eps: 14.935595, start_eps: 8.72, growth_years: 3.0 },
      output_value: 0.1965,
      output_unit: 'percent_per_annum',
      reproducible: true,
      status: 'COMPUTED',
      status_reason: null,
    },
  ],
  evidence: {
    price_evidence: {
      value: 336.64,
      currency: 'USD',
      as_of: '2026-10-09',
      provider: 'YahooFinance',
      source_type: 'API_LIVE',
      observation_id: 'ev-price-001',
      is_user_assumption: false,
    },
    eps_evidence: {
      value: 8.72,
      basis: 'TRAILING_TWELVE_MONTHS',
      months_covered: 12.0,
      provider: 'YahooFinance',
      source_type: 'API_LIVE',
      observation_id: 'ev-current-eps-001',
      is_user_assumption: false,
      // R2.1: a vendor trailing EPS is never linked to a filing fact.
      sec_fact: null,
    },
    multiple_evidence: {
      value: 30.0,
      source: 'user_supplied',
      is_user_assumption: true,
      eligibility_state: 'USER_SPECIFIED',
      usable_for_reference: false,
    },
    user_assumptions: ['Exit Multiple: 30x (user-supplied)'],
    sourced_facts: ['Market Price: 336.64 USD'],
    missing_or_unvalidated: [],
  },
}

// A direct-SEC-linked EPS (input-to-fact linkage established): sec_fact set on
// the EPS evidence, no related cross-check.
const secLinkedScenario: EpsScenarioDTO = {
  price: 336.64,
  as_of: '2026-10-09',
  horizon_years: 3.0,
  required_return: 0.12,
  required_return_basis: 'PRICE_RETURN_ONLY',
  exit_multiple: {
    value: 38.26,
    source: 'production_historical_pe_percentile',
    period_label: 'p50',
    sample_size: 36,
    sample_period: '2018-01-02..2026-07-31',
    is_user_assumption: false,
    eligibility_state: 'ELIGIBLE_PRODUCTION_DISTRIBUTION',
    usable_for_reference: true,
  },
  required_exit_price: 472.954962,
  required_terminal_eps: 12.365391,
  start_eps: {
    value: 8.72,
    basis: 'TRAILING_TWELVE_MONTHS',
    months_covered: 12.0,
    provider: 'sec',
    source_type: 'REGULATORY_FILING',
    is_user_assumption: false,
    sec_fact: {
      accession: '0001193125-26-323660',
      form: '10-K',
      filed_date: '2026-07-30',
      concept: 'us-gaap:EarningsPerShareDiluted',
    },
  },
  growth_years: 3.0,
  required_eps_cagr: 0.1238,
  total_terminal_eps_growth: 0.4179,
  comparison_notes: [],
  flags: [],
  formula_version: 'reverse-requirements/1.1',
  evidence: {
    price_evidence: {
      value: 336.64,
      currency: 'USD',
      as_of: '2026-10-09',
      provider: 'YahooFinance',
      source_type: 'API_LIVE',
      observation_id: 'ev-price-001',
      is_user_assumption: false,
    },
    eps_evidence: {
      value: 8.72,
      basis: 'TRAILING_TWELVE_MONTHS',
      months_covered: 12.0,
      provider: 'sec',
      source_type: 'REGULATORY_FILING',
      observation_id: 'ev-current-eps-001',
      is_user_assumption: false,
      sec_fact: {
        accession: '0001193125-26-323660',
        form: '10-K',
        filed_date: '2026-07-30',
        concept: 'us-gaap:EarningsPerShareDiluted',
      },
    },
    multiple_evidence: {
      value: 38.26,
      source: 'production_historical_pe_percentile',
      sample_size: 36,
      is_user_assumption: false,
      eligibility_state: 'ELIGIBLE_PRODUCTION_DISTRIBUTION',
      usable_for_reference: true,
    },
    user_assumptions: ['Required Return Hurdle: 12% (PRICE_RETURN_ONLY)'],
    sourced_facts: ['Starting EPS: 8.72 USD (via sec; SEC 10-K accession 0001193125-26-323660)'],
    missing_or_unvalidated: [],
  },
}

// Uncomputable CAGR scenario with a descriptive-only vendor band and unresolved
// provenance (value kept, no direct SEC source, related filing cross-check).
const descriptiveUncomputableScenario: EpsScenarioDTO = {
  price: 336.64,
  as_of: '2026-10-09',
  horizon_years: 1.0,
  required_return: 0.1,
  required_return_basis: 'PRICE_RETURN_ONLY',
  exit_multiple: {
    value: 35.65,
    source: 'historical_pe_band_percentile',
    sample_size: 8,
    is_user_assumption: false,
    eligibility_state: 'DESCRIPTIVE_ONLY_INSUFFICIENT_OBSERVATIONS',
    usable_for_reference: false,
  },
  required_exit_price: null,
  required_terminal_eps: null,
  start_eps: {
    value: 13.2,
    basis: 'FORWARD_TWELVE_MONTHS',
    months_covered: 12.0,
    provider: 'YahooFinance',
    source_type: 'API_LIVE',
    is_user_assumption: false,
  },
  growth_years: null,
  required_eps_cagr: null,
  total_terminal_eps_growth: null,
  comparison_notes: ['Growth window too short to annualise.'],
  flags: ['GROWTH_WINDOW_TOO_SHORT_FOR_CAGR'],
  formula_version: 'reverse-requirements/1.1',
  calculation_steps: [],
  evidence: {
    price_evidence: {
      value: 336.64,
      currency: 'USD',
      as_of: '2026-10-09',
      provider: 'YahooFinance',
      source_type: 'API_LIVE',
      observation_id: 'ev-price-001',
      is_user_assumption: false,
    },
    eps_evidence: {
      value: 13.2,
      basis: 'FORWARD_TWELVE_MONTHS',
      months_covered: 12.0,
      provider: 'YahooFinance',
      source_type: 'API_LIVE',
      observation_id: 'ev-forward-eps-001',
      is_user_assumption: false,
      sec_fact: null,
    },
    multiple_evidence: {
      value: 35.65,
      source: 'historical_pe_band_percentile',
      sample_size: 8,
      is_user_assumption: false,
      eligibility_state: 'DESCRIPTIVE_ONLY_INSUFFICIENT_OBSERVATIONS',
      usable_for_reference: false,
    },
    user_assumptions: ['Required Return Hurdle: 10% (PRICE_RETURN_ONLY)'],
    sourced_facts: ['Market Price: 336.64 USD'],
    missing_or_unvalidated: [
      'Direct SEC source of selected EPS not established; related filing shown for cross-check only',
    ],
    related_sec_evidence: {
      accession: '0000320193-25-000079',
      form: '10-K',
      filed_date: '2025-10-31',
      concept: 'us-gaap:EarningsPerShareDiluted',
      note: 'Related SEC filing (cross-check); not verified as direct source of selected EPS value',
    },
  },
}

const computedReport: ReverseRequirementsReportDTO = {
  formula_version: 'reverse-requirements/1.1',
  fingerprint: 'fp-computed',
  status: 'COMPUTED',
  status_reason: null,
  matrix_size: 3,
  reverse_requirements_matrix: [
    userScenario,
    secLinkedScenario,
    descriptiveUncomputableScenario,
  ],
  reading_notes: ['A required return is a price return unless a dividend was supplied.'],
  production_historical_pe_summary: {
    issuer_id: 'CIK0000320193',
    metric_id: 'TTM_GAAP_DILUTED_PE',
    status: 'USABLE_FOR_REFERENCE',
    usable_for_reference: true,
    sample_count: 36,
    total_evaluations: 36,
    min_observations_required: 20,
    period_start: '2018-01-02',
    period_end: '2026-07-31',
    percentiles: { p10: 22.0, p50: 38.26, p90: 55.0 },
    current_pe: 38.26,
    current_pe_as_of: '2026-10-06',
    input_set_id: '01f618068fabc',
  },
}

const buildResult = (
  report: ReverseRequirementsReportDTO,
  ticker = 'AAPL',
): AnalysisResultDTO =>
  ({
    ticker,
    company_name: 'Apple Inc.',
    status: 'success',
    research_id: 'RES-R5-TEST',
    as_of: '2026-10-09',
    source_identifiers: ['YahooFinance', 'Yahoo Finance chart API', 'API_LIVE'],
    admission_summary: {
      total_admitted: 1,
      total_refused: 0,
      metrics_admitted: ['revenue'],
      refusals: [],
    },
    valuation_summary: {
      current_price: 336.64,
      currency: 'USD',
      as_of: '2026-10-09',
      forward_eps_at_reference_multiple: 11.22,
      required_eps_cagr: 0.2858,
      selected_pe: 30.0,
      selected_pe_basis: 'user_supplied_multiple',
      summary_horizon_years: 1.0,
      observed_pe: 38.26,
      limitations: ['Conditional reverse valuation'],
    },
    replay_summary: {
      attempted: true,
      outcome: 'DIVERGED',
      matched: false,
      reconstructed: true,
      observations_used: 12,
      observations_considered: 20,
      reason: 'stored and rebuilt context documents differ',
    },
    refusal_reasons: [],
    reverse_requirements: report,
    production_historical_pe: computedReport.production_historical_pe_summary,
    raw_analysis: {
      evidence_ids: ['ev-price-001'],
      market_snapshot: { price: 336.64 },
      huge_internal_blob: { /* should never appear in an export */ marker: 'RAW' },
    },
  }) as AnalysisResultDTO

const request: AnalyzeRequest = {
  ticker: 'AAPL',
  mode: 'live',
  reference_multiple: 30,
  reverse_horizons: [3.0],
  required_returns: [0.1, 0.12],
}

describe('buildReverseRequirementsJson (typed result contract)', () => {
  it('emits a versioned envelope with export metadata and the echoed request', () => {
    const result = buildResult(computedReport)
    const envelope = buildReverseRequirementsExport(result, request, GENERATED_AT)

    expect(envelope.export.schema_version).toBe(EXPORT_SCHEMA_VERSION)
    expect(envelope.export.generated_at).toBe(GENERATED_AT.toISOString())
    expect(envelope.export.generator).toBe('st-eva-web')
    expect(envelope.export.ticker).toBe('AAPL')
    expect(envelope.export.mode).toBe('live')
    expect(envelope.request).toEqual(request)
  })

  it('omits raw_analysis and keeps the rest of the typed result verbatim', () => {
    const result = buildResult(computedReport)
    const parsed = JSON.parse(
      buildReverseRequirementsJson(result, request, GENERATED_AT),
    )

    expect('raw_analysis' in parsed.result).toBe(false)
    expect(parsed.result.ticker).toBe('AAPL')
    expect(parsed.result.as_of).toBe('2026-10-09')
    expect(parsed.result.source_identifiers).toContain('API_LIVE')
    expect(parsed.result.replay_summary.outcome).toBe('DIVERGED')
    expect(parsed.result.admission_summary.metrics_admitted).toEqual(['revenue'])
    // Summary basis metadata travels so a reader can reconcile the headline cards.
    expect(parsed.result.valuation_summary.selected_pe_basis).toBe(
      'user_supplied_multiple',
    )
  })

  it('preserves the full matrix, nested evidence and calculation traces', () => {
    const result = buildResult(computedReport)
    const parsed = JSON.parse(
      buildReverseRequirementsJson(result, request, GENERATED_AT),
    )
    const rr = parsed.result.reverse_requirements

    expect(rr.formula_version).toBe('reverse-requirements/1.1')
    expect(rr.status).toBe('COMPUTED')
    expect(rr.reverse_requirements_matrix).toHaveLength(3)

    // Nested evidence structure is not flattened.
    const steps = rr.reverse_requirements_matrix[0].calculation_steps
    expect(steps).toHaveLength(2)
    expect(steps[0].formula_expression).toBe('P_T = P_0 * (1 + r)^T')
    expect(steps[0].operands.price).toBe(336.64)

    // Production distribution eligibility summary is preserved.
    expect(rr.production_historical_pe_summary.status).toBe('USABLE_FOR_REFERENCE')
    expect(rr.production_historical_pe_summary.usable_for_reference).toBe(true)
    expect(rr.production_historical_pe_summary.min_observations_required).toBe(20)
  })

  it('keeps R2.1 direct SEC provenance and cross-check evidence distinct', () => {
    const result = buildResult(computedReport)
    const parsed = JSON.parse(
      buildReverseRequirementsJson(result, request, GENERATED_AT),
    )
    const [userRow, secRow, vendorRow] =
      parsed.result.reverse_requirements.reverse_requirements_matrix

    // Direct SEC fact only where the linkage is established.
    expect(userRow.evidence.eps_evidence.sec_fact).toBeNull()
    expect(secRow.evidence.eps_evidence.sec_fact.accession).toBe(
      '0001193125-26-323660',
    )
    // Related filing is cross-check only for the unresolved vendor anchor.
    expect(vendorRow.evidence.eps_evidence.sec_fact).toBeNull()
    expect(vendorRow.evidence.related_sec_evidence.accession).toBe(
      '0000320193-25-000079',
    )
    expect(vendorRow.evidence.missing_or_unvalidated.join(' ')).toMatch(
      /Direct SEC source of selected EPS not established/,
    )
  })
})

describe('buildReverseRequirementsCsv (full scenario matrix)', () => {
  it('writes the documented header and one row per matrix scenario', () => {
    const result = buildResult(computedReport)
    const csv = buildReverseRequirementsCsv(result, GENERATED_AT)
    const lines = csv.split('\r\n')

    expect(lines[0]).toBe(REVERSE_REQUIREMENTS_CSV_COLUMNS.join(','))
    const rows = csvToObjects(csv)
    expect(rows).toHaveLength(3)
    rows.forEach((row) => expect(row.record_type).toBe('scenario'))
    expect(rows.every((row) => row.export_schema_version === EXPORT_SCHEMA_VERSION)).toBe(
      true,
    )
    expect(rows.every((row) => row.export_generated_at === GENERATED_AT.toISOString())).toBe(
      true,
    )
  })

  it('keeps production, user and descriptive-only exit multiples distinct', () => {
    const result = buildResult(computedReport)
    const rows = csvToObjects(buildReverseRequirementsCsv(result, GENERATED_AT))
    const [userRow, productionRow, descriptiveRow] = rows

    expect(userRow.exit_multiple_source).toBe('user_supplied')
    expect(userRow.exit_multiple_eligibility_state).toBe('USER_SPECIFIED')
    expect(userRow.exit_multiple_is_user_assumption).toBe('true')

    expect(productionRow.exit_multiple_source).toBe('production_historical_pe_percentile')
    expect(productionRow.exit_multiple_eligibility_state).toBe(
      'ELIGIBLE_PRODUCTION_DISTRIBUTION',
    )
    expect(productionRow.exit_multiple_is_user_assumption).toBe('false')
    expect(productionRow.exit_multiple_sample_size).toBe('36')

    expect(descriptiveRow.exit_multiple_source).toBe('historical_pe_band_percentile')
    expect(descriptiveRow.exit_multiple_eligibility_state).toBe(
      'DESCRIPTIVE_ONLY_INSUFFICIENT_OBSERVATIONS',
    )
  })

  it('preserves missing values as empty fields rather than zeros', () => {
    const result = buildResult(computedReport)
    const rows = csvToObjects(buildReverseRequirementsCsv(result, GENERATED_AT))
    const descriptiveRow = rows[2]

    expect(descriptiveRow.required_eps_cagr).toBe('')
    expect(descriptiveRow.required_exit_price).toBe('')
    expect(descriptiveRow.required_terminal_eps).toBe('')
    expect(descriptiveRow.calculation_steps_count).toBe('0')
    expect(descriptiveRow.calculation_steps_reproducible).toBe('')
    const flags = JSON.parse(descriptiveRow.flags_json)
    expect(flags).toContain('GROWTH_WINDOW_TOO_SHORT_FOR_CAGR')
    expect(JSON.parse(descriptiveRow.missing_or_unvalidated_json).join(' ')).toMatch(
      /Direct SEC source of selected EPS not established/,
    )
  })

  it('preserves exact figures and calculation traces as re-parseable JSON', () => {
    const result = buildResult(computedReport)
    const rows = csvToObjects(buildReverseRequirementsCsv(result, GENERATED_AT))
    const userRow = rows[0]

    expect(userRow.required_exit_price).toBe('448.06784')
    expect(userRow.required_terminal_eps).toBe('14.935595')
    expect(userRow.required_eps_cagr).toBe('0.1965')
    expect(userRow.calculation_steps_reproducible).toBe('true')

    const steps = JSON.parse(userRow.calculation_steps_json)
    expect(steps).toHaveLength(2)
    expect(steps[0].formula_expression).toBe('P_T = P_0 * (1 + r)^T')

    const scenario = JSON.parse(userRow.scenario_json)
    expect(scenario.exit_multiple.value).toBe(30)
    expect(scenario.start_eps.basis).toBe('TRAILING_TWELVE_MONTHS')

    const evidence = JSON.parse(userRow.evidence_json)
    expect(evidence.multiple_evidence.eligibility_state).toBe('USER_SPECIFIED')
  })

  it('never exports a related SEC filing as the direct source of the EPS', () => {
    const result = buildResult(computedReport)
    const rows = csvToObjects(buildReverseRequirementsCsv(result, GENERATED_AT))
    const [userRow, secRow, vendorRow] = rows

    // Direct SEC columns carry the linked fact only.
    expect(secRow.eps_direct_sec_accession).toBe('0001193125-26-323660')
    expect(secRow.eps_direct_sec_form).toBe('10-K')
    expect(secRow.eps_related_sec_accession).toBe('')

    // The vendor anchor has no direct SEC column value; its related filing sits
    // only in the dedicated cross-check columns.
    expect(vendorRow.eps_direct_sec_accession).toBe('')
    expect(vendorRow.eps_related_sec_accession).toBe('0000320193-25-000079')
    expect(vendorRow.eps_related_sec_note).toMatch(/cross-check/)
  })

  it('exports the whole matrix regardless of any screen filter', () => {
    const result = buildResult(computedReport)
    // A filter that would hide every row on screen must not shrink the file.
    const csv = buildReverseRequirementsCsv(result, GENERATED_AT)
    const rows = csvToObjects(csv)
    expect(rows).toHaveLength(3)
    expect(rows.every((row) => row.report_matrix_size === '3')).toBe(true)
  })
})

describe('uncomputed report export', () => {
  const notComputedReport: ReverseRequirementsReportDTO = {
    formula_version: 'reverse-requirements/1.1',
    status: 'NOT_COMPUTED',
    status_reason:
      'The historical P/E band holds 8 observations, below the 20 required; no user multiple was supplied.',
    matrix_size: 0,
    reverse_requirements_matrix: [],
    unavailable: [
      { item: 'exit_multiple', reason: 'No eligible exit multiple was available.' },
    ],
    production_historical_pe_summary: {
      status: 'UNDER_QUALIFIED',
      usable_for_reference: false,
      sample_count: 8,
      min_observations_required: 20,
      reason_detail: 'Only 8 qualifying observations.',
    },
  }

  it('CSV preserves status/reason without inventing scenario rows or zeros', () => {
    const result = buildResult(notComputedReport, 'MSFT')
    const csv = buildReverseRequirementsCsv(result, GENERATED_AT)
    const rows = csvToObjects(csv)

    expect(rows).toHaveLength(1)
    const only = rows[0]
    expect(only.record_type).toBe('report_status_only')
    expect(only.report_status).toBe('NOT_COMPUTED')
    expect(only.report_status_reason).toMatch(/below the 20 required/)
    expect(only.report_matrix_size).toBe('0')
    expect(only.report_production_pe_usable_for_reference).toBe('false')
    expect(JSON.parse(only.report_unavailable_json)).toHaveLength(1)

    // No manufactured scenario data and no zero-filled financial values.
    expect(only.exit_multiple_value).toBe('')
    expect(only.required_exit_price).toBe('')
    expect(only.required_eps_cagr).toBe('')
    expect(only.scenario_json).toBe('null')
  })

  it('JSON preserves the uncomputed status, reason and unavailable states', () => {
    const result = buildResult(notComputedReport, 'MSFT')
    const parsed = JSON.parse(
      buildReverseRequirementsJson(result, request, GENERATED_AT),
    )
    const rr = parsed.result.reverse_requirements
    expect(rr.status).toBe('NOT_COMPUTED')
    expect(rr.status_reason).toMatch(/below the 20 required/)
    expect(rr.reverse_requirements_matrix).toHaveLength(0)
    expect(rr.unavailable).toHaveLength(1)
    expect(rr.production_historical_pe_summary.usable_for_reference).toBe(false)
  })
})

describe('a second submission exports its own result', () => {
  it('reflects the second response rather than stale data from the first', () => {
    const first = buildResult(computedReport, 'AAPL')
    const secondReport: ReverseRequirementsReportDTO = {
      ...computedReport,
      matrix_size: 1,
      reverse_requirements_matrix: [
        {
          ...secLinkedScenario,
          exit_multiple: {
            ...secLinkedScenario.exit_multiple,
            value: 32.0,
          },
          required_eps_cagr: 0.1923,
        },
      ],
    }
    const second = buildResult(secondReport, 'MSFT')

    const firstJson = JSON.parse(
      buildReverseRequirementsJson(first, request, GENERATED_AT),
    )
    const secondJson = JSON.parse(
      buildReverseRequirementsJson(second, { ticker: 'MSFT', mode: 'auto' }, GENERATED_AT),
    )

    expect(firstJson.export.ticker).toBe('AAPL')
    expect(secondJson.export.ticker).toBe('MSFT')
    expect(firstJson.result.reverse_requirements.reverse_requirements_matrix).toHaveLength(3)
    expect(secondJson.result.reverse_requirements.reverse_requirements_matrix).toHaveLength(1)
    expect(
      secondJson.result.reverse_requirements.reverse_requirements_matrix[0].exit_multiple.value,
    ).toBe(32.0)

    const firstCsv = csvToObjects(buildReverseRequirementsCsv(first, GENERATED_AT))
    const secondCsv = csvToObjects(buildReverseRequirementsCsv(second, GENERATED_AT))
    expect(firstCsv).toHaveLength(3)
    expect(secondCsv).toHaveLength(1)
    expect(secondCsv[0].ticker).toBe('MSFT')
    expect(secondCsv[0].exit_multiple_value).toBe('32')
  })
})
