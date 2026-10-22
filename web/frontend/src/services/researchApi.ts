import {
  ResearchCalculation,
  ResearchCatalogue,
  ResearchComparability,
  ResearchComparison,
  ResearchMetricDetail,
  ResearchSensitivity,
} from '../types/research'

/**
 * The research API client.
 *
 * A separate base path from the production analysis client, because the
 * research path is a separate thing: it starts no job, it writes no
 * archive, and every figure it returns is a research figure.
 */
const RESEARCH_API_BASE = '/api/research'

export class ResearchApiError extends Error {
  status: number
  refusal?: { reason_code: string; detail: string; production_eligible: boolean }

  constructor(status: number, message: string, refusal?: ResearchApiError['refusal']) {
    super(message)
    this.name = 'ResearchApiError'
    this.status = status
    this.refusal = refusal
  }
}

async function readError(res: Response): Promise<ResearchApiError> {
  let detail = ''
  let refusal: ResearchApiError['refusal'] | undefined
  try {
    const data = await res.json()
    if (data && typeof data.detail === 'object' && data.detail !== null) {
      refusal = data.detail as ResearchApiError['refusal']
      detail = refusal?.detail || ''
    } else if (typeof data.detail === 'string') {
      detail = data.detail
    } else {
      detail = JSON.stringify(data)
    }
  } catch {
    detail = await res.text()
  }
  return new ResearchApiError(
    res.status,
    detail || `Research request failed (${res.status})`,
    refusal,
  )
}

export async function getResearchCatalogue(): Promise<ResearchCatalogue> {
  const res = await fetch(`${RESEARCH_API_BASE}/metrics`)
  if (!res.ok) throw await readError(res)
  return res.json()
}

export async function getResearchMetric(
  metricId: string,
): Promise<ResearchMetricDetail> {
  const res = await fetch(
    `${RESEARCH_API_BASE}/metrics/${encodeURIComponent(metricId)}`,
  )
  if (!res.ok) throw await readError(res)
  return res.json()
}

export async function getResearchObservationEvidence(
  metricId: string,
  evaluationDate: string,
): Promise<Record<string, any>> {
  const res = await fetch(
    `${RESEARCH_API_BASE}/metrics/${encodeURIComponent(metricId)}` +
      `/observations/${encodeURIComponent(evaluationDate)}`,
  )
  if (!res.ok) throw await readError(res)
  const payload = await res.json()
  return payload.evidence
}

export interface ResearchCalculationInput {
  metric_id: string
  multiple_source: string
  multiple?: number | null
  observation_date?: string | null
  numerator_source: string
  numerator_value?: number | null
  numerator_date?: string | null
}

export async function runResearchCalculation(
  input: ResearchCalculationInput,
): Promise<ResearchCalculation> {
  const res = await fetch(`${RESEARCH_API_BASE}/calculate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
  if (!res.ok) throw await readError(res)
  return res.json()
}

/**
 * The comparability attributes of every selectable research metric, and the
 * named sensitivity assumptions on offer.
 */
export async function getResearchDefinitions(): Promise<{
  definitions: any[]
  sensitivity_assumptions: Record<string, any>
  comparison_version: string
}> {
  const res = await fetch(`${RESEARCH_API_BASE}/definitions`)
  if (!res.ok) throw await readError(res)
  return res.json()
}

export async function getResearchComparability(
  leftMetricId: string,
  rightMetricId: string,
): Promise<ResearchComparability> {
  const res = await fetch(`${RESEARCH_API_BASE}/compare/compatibility`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      left_metric_id: leftMetricId,
      right_metric_id: rightMetricId,
    }),
  })
  if (!res.ok) throw await readError(res)
  return res.json()
}

export async function compareResearchHistory(
  metricId: string,
  earlierDate: string,
  laterDate: string,
): Promise<ResearchComparison> {
  const res = await fetch(`${RESEARCH_API_BASE}/compare/history`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      metric_id: metricId,
      earlier_date: earlierDate,
      later_date: laterDate,
    }),
  })
  if (!res.ok) throw await readError(res)
  return res.json()
}

export async function compareResearchBridges(
  leftMetricId: string,
  rightMetricId: string,
): Promise<ResearchComparison> {
  const res = await fetch(`${RESEARCH_API_BASE}/compare/bridges`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      left_metric_id: leftMetricId,
      right_metric_id: rightMetricId,
    }),
  })
  if (!res.ok) throw await readError(res)
  return res.json()
}

export async function runResearchSensitivity(input: {
  metric_id: string
  evaluation_date: string
  assumption: string
  value: number
}): Promise<ResearchSensitivity> {
  const res = await fetch(`${RESEARCH_API_BASE}/sensitivity`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
  if (!res.ok) throw await readError(res)
  return res.json()
}
