import {
  AnalyzeRequest,
  AnalyzeResponse,
  HealthResponse,
  JobDetailResponse,
} from '../types/api'

const API_BASE = '/api'

export class ApiError extends Error {
  status: number
  detail?: string

  constructor(status: number, message: string, detail?: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

export async function checkHealth(): Promise<HealthResponse> {
  const res = await fetch(`${API_BASE}/health`)
  if (!res.ok) {
    throw new ApiError(res.status, `Health check failed with status ${res.status}`)
  }
  return res.json()
}

export async function startAnalysis(request: AnalyzeRequest): Promise<AnalyzeResponse> {
  const res = await fetch(`${API_BASE}/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })

  if (!res.ok) {
    let detail = ''
    try {
      const data = await res.json()
      detail = data.detail || JSON.stringify(data)
    } catch {
      detail = await res.text()
    }
    throw new ApiError(
      res.status,
      res.status === 400 ? detail || 'Invalid ticker format' : `Analysis request failed (${res.status})`,
      detail
    )
  }

  return res.json()
}

export async function getJobStatus(jobId: string): Promise<JobDetailResponse> {
  const res = await fetch(`${API_BASE}/jobs/${encodeURIComponent(jobId)}`)
  if (!res.ok) {
    let detail = ''
    try {
      const data = await res.json()
      detail = data.detail || ''
    } catch {
      detail = await res.text()
    }
    throw new ApiError(res.status, `Failed to fetch job status (${res.status})`, detail)
  }
  return res.json()
}

