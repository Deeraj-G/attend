// Backend client. Vite proxies /api -> http://localhost:8000.

export type Case = { id: string; procedure: string | null; approved: boolean; created_at: string }
export type ExecutorOutput = { contract_id: string; artifacts: string[]; summary: string }

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
