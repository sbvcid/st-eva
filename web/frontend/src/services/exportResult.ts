import {
  AnalysisResultDTO,
  AnalyzeRequest,
  EpsScenarioDTO,
  ReverseRequirementsReportDTO,
} from '../types/api'

/**
 * Export of the reverse-requirements report and its row-level audit trail.
 *
 * The export is built from the exact typed response the interface is showing
 * for the current analysis submission: nothing is recomputed, and the nested
 * evidence / calculation-trace structure is preserved rather than flattened
 * away. The duplicated and possibly large `raw_analysis` presentation payload
 * is not exported by default.
 */

/** Bump when the JSON envelope or CSV column set changes incompatibly. */
export const EXPORT_SCHEMA_VERSION = 'st-eva-reverse-requirements-export/1.0'
export const EXPORT_GENERATOR = 'st-eva-web'

export interface ReverseRequirementsExportEnvelope {
  export: {
    schema_version: string
    generated_at: string
    generator: string
    ticker: string
    /** Original request that produced this result, echoed where available. */
    mode?: string | null
  }
  request: AnalyzeRequest | null
  result: Omit<AnalysisResultDTO, 'raw_analysis'>
}

/**
 * Build the versioned, machine-readable representation of the analysis
 * currently displayed. The typed `AnalysisResultDTO` travels verbatim (with
 * its nested evidence and calculation traces); only `raw_analysis` is omitted.
 */
export function buildReverseRequirementsExport(
  result: AnalysisResultDTO,
  request?: AnalyzeRequest | null,
  generatedAt: Date = new Date(),
): ReverseRequirementsExportEnvelope {
  // Omit the duplicated presentation payload by default. The archive, the
  // context document and the CLI keep every byte; the export simply does not
  // repeat a multi-megabyte block no export consumer reads.
  const { raw_analysis: _rawAnalysis, ...resultForExport } = result
  return {
    export: {
      schema_version: EXPORT_SCHEMA_VERSION,
      generated_at: generatedAt.toISOString(),
      generator: EXPORT_GENERATOR,
      ticker: result.ticker,
      mode: request?.mode ?? null,
    },
    request: request ?? null,
    result: resultForExport,
  }
}

export function buildReverseRequirementsJson(
  result: AnalysisResultDTO,
  request?: AnalyzeRequest | null,
  generatedAt: Date = new Date(),
): string {
  return JSON.stringify(
    buildReverseRequirementsExport(result, request, generatedAt),
    null,
    2,
  )
}

/**
 * Stable, documented CSV columns for the full scenario-matrix export. The
 * order is part of the contract. Structured evidence and calculation traces
 * that cannot be represented as ordinary scalars without losing information
 * are carried in the `*_json` columns as stable JSON strings, so the audit
 * trail is never silently discarded and the file can be re-parsed offline.
 */
export const REVERSE_REQUIREMENTS_CSV_COLUMNS = [
  // Export metadata (identical on every row).
  'export_schema_version',
  'export_generated_at',
  // Identity / display context.
  'ticker',
  'company_name',
  'as_of',
  'currency',
  'research_id',
  // Report-level state (repeated on every row, and on the status-only row).
  'report_status',
  'report_status_reason',
  'report_matrix_size',
  'report_formula_version',
  // Consensus reference. The gap is not a first-class scenario column, so the
  // period facts it depends on are stated at report level and repeated on
  // every scenario row, while the verdict stays with the row's flags and
  // notes. A missing gap is never written as a zero.
  'report_consensus_eps',
  'report_consensus_source_period_label',
  'report_consensus_period_end',
  'report_consensus_period_end_declared_by_source',
  'report_consensus_target_period_end',
  'report_consensus_comparison_tolerance_days',
  'report_production_pe_status',
  'report_production_pe_usable_for_reference',
  'report_unavailable_json',
  // Distinguishes a real scenario row from a report-status-only row emitted for
  // an uncomputed matrix; it is never a manufactured scenario.
  'record_type',
  // Scenario assumptions.
  'scenario_formula_version',
  'horizon_years',
  'required_return',
  'required_return_basis',
  'exit_multiple_value',
  'exit_multiple_source',
  'exit_multiple_eligibility_state',
  'exit_multiple_is_user_assumption',
  'exit_multiple_sample_size',
  'exit_multiple_sample_period',
  'start_eps_value',
  'start_eps_basis',
  'start_eps_source_type',
  'start_eps_is_user_assumption',
  'start_eps_months_covered',
  'start_eps_period_label',
  'start_eps_period_undeclared',
  'start_eps_period_start',
  'start_eps_period_end',
  // Scenario results.
  'required_exit_price',
  'required_terminal_eps',
  'total_terminal_eps_growth',
  'required_eps_cagr',
  'growth_years',
  // Reproducibility.
  'calculation_steps_count',
  'calculation_steps_reproducible',
  // Direct SEC provenance, only when R2.1's identity linkage establishes it.
  'eps_direct_source_type',
  'eps_direct_sec_form',
  'eps_direct_sec_accession',
  'eps_direct_sec_filed_date',
  'eps_direct_sec_concept',
  // Related / cross-check SEC evidence, kept distinct from direct source.
  'eps_related_sec_form',
  'eps_related_sec_accession',
  'eps_related_sec_note',
  // Structured, JSON-encoded audit fields (stable and re-parseable).
  // `scenario_json` carries the entire typed scenario so no field (dividend
  // relief, terminal-P/E change, consensus gap, ...) is silently discarded;
  // `calculation_steps_json` and `evidence_json` expose the two named audit
  // structures directly, with direct SEC source and cross-check evidence kept
  // distinct inside them.
  'scenario_json',
  'calculation_steps_json',
  'evidence_json',
  'user_assumptions_json',
  'sourced_facts_json',
  'missing_or_unvalidated_json',
  'flags_json',
  'comparison_notes_json',
] as const

type CsvRow = Record<string, unknown>

function csvField(value: unknown): string {
  if (value === null || value === undefined) return ''
  let text: string
  if (typeof value === 'number') {
    text = Number.isFinite(value) ? String(value) : ''
  } else if (typeof value === 'boolean') {
    text = value ? 'true' : 'false'
  } else if (typeof value === 'object') {
    text = JSON.stringify(value)
  } else {
    text = String(value)
  }
  if (/[",\r\n]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`
  }
  return text
}

const jsonColumn = (value: unknown): string => JSON.stringify(value ?? null)

function reportLevelFields(
  result: AnalysisResultDTO,
  report: ReverseRequirementsReportDTO | null | undefined,
): CsvRow {
  const summary = report?.production_historical_pe_summary ?? null
  const consensus = report?.consensus_reference ?? null
  return {
    ticker: result.ticker,
    company_name: result.company_name,
    as_of: result.as_of ?? null,
    currency: result.valuation_summary?.currency ?? null,
    research_id: result.research_id ?? null,
    report_status: report?.status ?? null,
    report_status_reason: report?.status_reason ?? null,
    report_matrix_size: report?.matrix_size ?? 0,
    report_formula_version: report?.formula_version ?? null,
    report_consensus_eps: consensus?.eps ?? null,
    report_consensus_source_period_label: consensus?.source_period_label ?? null,
    report_consensus_period_end: consensus?.period_end ?? null,
    report_consensus_period_end_declared_by_source:
      consensus?.period_end_declared_by_source ?? null,
    report_consensus_target_period_end: consensus?.target_period_end ?? null,
    report_consensus_comparison_tolerance_days:
      consensus?.comparison_tolerance_days ?? null,
    report_production_pe_status: summary?.status ?? null,
    report_production_pe_usable_for_reference:
      summary?.usable_for_reference ?? null,
    report_unavailable_json: jsonColumn(report?.unavailable ?? []),
  }
}

function scenarioRow(
  result: AnalysisResultDTO,
  report: ReverseRequirementsReportDTO,
  scenario: EpsScenarioDTO,
): CsvRow {
  const evidence = scenario.evidence ?? null
  const steps = scenario.calculation_steps ?? []
  const epsEvidence = evidence?.eps_evidence
  const directSecFact = epsEvidence?.sec_fact ?? null
  const relatedSecEvidence = evidence?.related_sec_evidence ?? null
  const stepsReproducible =
    steps.length > 0 ? steps.every((step) => step.reproducible === true) : null

  return {
    ...reportLevelFields(result, report),
    record_type: 'scenario',
    scenario_formula_version: scenario.formula_version ?? null,
    horizon_years: scenario.horizon_years ?? null,
    required_return: scenario.required_return ?? null,
    required_return_basis: scenario.required_return_basis ?? null,
    exit_multiple_value: scenario.exit_multiple?.value ?? null,
    exit_multiple_source: scenario.exit_multiple?.source ?? null,
    exit_multiple_eligibility_state:
      scenario.exit_multiple?.eligibility_state ?? null,
    exit_multiple_is_user_assumption:
      scenario.exit_multiple?.is_user_assumption ?? null,
    exit_multiple_sample_size: scenario.exit_multiple?.sample_size ?? null,
    exit_multiple_sample_period: scenario.exit_multiple?.sample_period ?? null,
    start_eps_value: scenario.start_eps?.value ?? null,
    start_eps_basis: scenario.start_eps?.basis ?? null,
    start_eps_source_type: scenario.start_eps?.source_type ?? null,
    start_eps_is_user_assumption: scenario.start_eps?.is_user_assumption ?? null,
    start_eps_months_covered: scenario.start_eps?.months_covered ?? null,
    start_eps_period_label: scenario.start_eps?.period_label ?? null,
    start_eps_period_undeclared: scenario.start_eps?.period_undeclared_by_source ?? null,
    start_eps_period_start: scenario.start_eps?.period_start ?? null,
    start_eps_period_end: scenario.start_eps?.period_end ?? null,
    required_exit_price: scenario.required_exit_price ?? null,
    required_terminal_eps: scenario.required_terminal_eps ?? null,
    total_terminal_eps_growth: scenario.total_terminal_eps_growth ?? null,
    required_eps_cagr: scenario.required_eps_cagr ?? null,
    growth_years: scenario.growth_years ?? null,
    calculation_steps_count: steps.length,
    calculation_steps_reproducible: stepsReproducible,
    eps_direct_source_type: epsEvidence?.source_type ?? null,
    eps_direct_sec_form: directSecFact?.form ?? null,
    eps_direct_sec_accession: directSecFact?.accession ?? null,
    eps_direct_sec_filed_date: directSecFact?.filed_date ?? null,
    eps_direct_sec_concept: directSecFact?.concept ?? null,
    eps_related_sec_form: relatedSecEvidence?.form ?? null,
    eps_related_sec_accession: relatedSecEvidence?.accession ?? null,
    eps_related_sec_note: relatedSecEvidence?.note ?? null,
    scenario_json: jsonColumn(scenario),
    calculation_steps_json: jsonColumn(steps),
    evidence_json: jsonColumn(evidence),
    user_assumptions_json: jsonColumn(evidence?.user_assumptions ?? []),
    sourced_facts_json: jsonColumn(evidence?.sourced_facts ?? []),
    missing_or_unvalidated_json: jsonColumn(
      evidence?.missing_or_unvalidated ?? [],
    ),
    flags_json: jsonColumn(scenario.flags ?? []),
    comparison_notes_json: jsonColumn(scenario.comparison_notes ?? []),
  }
}

function statusOnlyRow(
  result: AnalysisResultDTO,
  report: ReverseRequirementsReportDTO,
): CsvRow {
  // For an uncomputed matrix this is the single preserved row: the report
  // status, its reason and its input/evidence limitations travel here, and
  // every scenario-specific column is left empty. No scenario rows are
  // manufactured and no absent value is replaced with zero.
  return {
    ...reportLevelFields(result, report),
    record_type: 'report_status_only',
    scenario_formula_version: report.formula_version ?? null,
    calculation_steps_count: 0,
    user_assumptions_json: jsonColumn([]),
    sourced_facts_json: jsonColumn([]),
    missing_or_unvalidated_json: jsonColumn([]),
    flags_json: jsonColumn([]),
    comparison_notes_json: jsonColumn([]),
    scenario_json: jsonColumn(null),
    calculation_steps_json: jsonColumn([]),
    evidence_json: jsonColumn(null),
  }
}

/**
 * Build the full scenario-matrix CSV. Every matrix row is exported regardless
 * of any on-screen filter, because the file is built from the full typed
 * matrix rather than from the filtered view. An uncomputed matrix is exported
 * with its status and reason instead of fabricated rows or zero-filled values.
 */
export function buildReverseRequirementsCsv(
  result: AnalysisResultDTO,
  generatedAt: Date = new Date(),
): string {
  const report = result.reverse_requirements ?? null
  const exportedAt = generatedAt.toISOString()

  const rows: CsvRow[] = []
  const scenarios = report?.reverse_requirements_matrix ?? []
  if (scenarios.length > 0) {
    scenarios.forEach((scenario) => rows.push(scenarioRow(result, report!, scenario)))
  } else if (report) {
    rows.push(statusOnlyRow(result, report))
  }

  const header = REVERSE_REQUIREMENTS_CSV_COLUMNS.join(',')
  const body = rows.map((row) =>
    REVERSE_REQUIREMENTS_CSV_COLUMNS.map((column) => {
      let value = row[column]
      if (column === 'export_schema_version') value = EXPORT_SCHEMA_VERSION
      else if (column === 'export_generated_at') value = exportedAt
      return csvField(value)
    }).join(','),
  )

  return [header, ...body].join('\r\n')
}

// --- Download helpers (imperative side effects kept out of the builders) ---

function sanitizeFilenamePart(value: string): string {
  return value.replace(/[^A-Za-z0-9._-]+/g, '_')
}

function fileTimestamp(date: Date): string {
  return date.toISOString().replace(/[:.]/g, '-')
}

function triggerDownload(filename: string, mime: string, content: string): void {
  const blob = new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
}

export function downloadReverseRequirementsJson(
  result: AnalysisResultDTO,
  request?: AnalyzeRequest | null,
  generatedAt: Date = new Date(),
): void {
  const ticker = sanitizeFilenamePart(result.ticker || 'UNKNOWN')
  const filename = `st-eva-${ticker}-reverse-requirements-${fileTimestamp(
    generatedAt,
  )}.json`
  triggerDownload(
    filename,
    'application/json',
    buildReverseRequirementsJson(result, request, generatedAt),
  )
}

export function downloadReverseRequirementsCsv(
  result: AnalysisResultDTO,
  generatedAt: Date = new Date(),
): void {
  const ticker = sanitizeFilenamePart(result.ticker || 'UNKNOWN')
  const filename = `st-eva-${ticker}-reverse-requirements-full-matrix-${fileTimestamp(
    generatedAt,
  )}.csv`
  triggerDownload(
    filename,
    'text/csv',
    buildReverseRequirementsCsv(result, generatedAt),
  )
}
