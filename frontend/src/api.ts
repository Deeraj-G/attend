// Backend client. Vite proxies /api -> http://localhost:8000.

export type Case = { id: string; procedure: string | null; approved: boolean; created_at: string }
export type ExecutorOutput = {
  contract_id: string
  artifacts: string[]
  summary: string
  data: Record<string, number>
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, init)
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail ?? `${res.status} ${res.statusText}`)
  }
  return res.json() as Promise<T>
}

export const createCase = () => request<Case>('/cases', { method: 'POST' })

export function uploadAudio(caseId: string, wav: Blob) {
  const form = new FormData()
  form.append('file', wav, 'recording.wav')
  return request<{ path: string; duration_s: number }>(`/cases/${caseId}/audio`, {
    method: 'POST',
    body: form,
  })
}

export const transcribe = (caseId: string) =>
  request<ExecutorOutput>(`/cases/${caseId}/transcribe`, { method: 'POST' })

export const getTranscript = (caseId: string) =>
  request<{ text: string }>(`/cases/${caseId}/transcript`)

// --- Manage-Execute-Audit harness ---

export type Report = {
  id: string
  contract_id: string
  subtask: string
  status: 'complete' | 'incomplete' | 'blocked'
  integrity: 'clean' | 'suspect' | 'violation'
  state_update: { facts: string[]; gaps: string[]; data: Record<string, unknown> }
  created_at: string
}

export type HarnessStatus = {
  state: 'idle' | 'running' | 'waiting' | 'done' | 'error'
  kind?: 'recording' | 'conflict' | 'retries_exhausted' | 'approval'
  question?: string
  subtask?: string | null
  error?: string
}

export type Video = { status: string; sample_url: string | null; message: string | null }

const post = <T,>(path: string, body?: unknown) =>
  request<T>(path, {
    method: 'POST',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })

export const runHarness = (caseId: string) => post<HarnessStatus>(`/cases/${caseId}/run`)
export const getStatus = (caseId: string) => request<HarnessStatus>(`/cases/${caseId}/status`)
export const getReports = (caseId: string) => request<Report[]>(`/cases/${caseId}/reports`)
export const getVideo = (caseId: string) => request<Video>(`/cases/${caseId}/video`)
export const answer = (caseId: string, text: string, target?: string | null) =>
  post<HarnessStatus>(`/cases/${caseId}/answer`, { text, target })
export const requestEdit = (caseId: string, text: string) =>
  post<HarnessStatus>(`/cases/${caseId}/edit`, { text, target: 'video' })
export const approve = (caseId: string) => post<HarnessStatus>(`/cases/${caseId}/approve`)
