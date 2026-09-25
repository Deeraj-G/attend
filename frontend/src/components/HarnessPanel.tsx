import { useState } from 'react'
import { answer, approve, requestEdit, type HarnessStatus, type Report } from '../api'
import { CheckIcon } from './Icons'

const STEPS: { key: string; label: string }[] = [
  { key: 'transcribe', label: 'Transcribed on device' },
  { key: 'deidentify', label: 'De-identified' },
  { key: 'research', label: 'Researched & verified sources' },
  { key: 'video', label: 'Video generated' },
]

type Props = {
  caseId: string
  status: HarnessStatus
  reports: Report[]
  videoUrl: string | null
  onResume: (status: HarnessStatus) => void
}

/** Harness progress plus whatever the Manager is waiting on: an answer or the approval gate. */
export function HarnessPanel({ caseId, status, reports, videoUrl, onResume }: Props) {
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const latest = new Map<string, Report>()
  for (const r of reports) latest.set(r.subtask, r)
  const firstPending = STEPS.find((s) => latest.get(s.key)?.status !== 'complete')?.key

  async function send(action: () => Promise<HarnessStatus>) {
    setSending(true)
    setError(null)
    try {
      onResume(await action())
      setText('')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSending(false)
    }
  }

  const waiting = status.state === 'waiting'
  const approval = waiting && status.kind === 'approval'
  const question = waiting && (status.kind === 'conflict' || status.kind === 'retries_exhausted')

  return (
    <div className="harness">
      <ol className="pipeline" aria-label="Progress">
        <li className="is-done">
          <CheckIcon size={14} /> Recorded
        </li>
        {STEPS.map(({ key, label }) => {
          const r = latest.get(key)
          const done = r?.status === 'complete'
          const active = !done && key === firstPending && status.state === 'running'
          const retrying = !done && r && r.status !== 'complete'
          return (
            <li key={key} className={done ? 'is-done' : active ? 'is-active' : ''}>
              {done && <CheckIcon size={14} />} {label}
              {active && <span className="dots" aria-hidden="true" />}
              {retrying && !active && <span className="harness-note"> · {r.status}</span>}
              {r?.integrity === 'violation' && <span className="harness-note"> · PHI source discarded</span>}
            </li>
          )
        })}
      </ol>

      {status.state === 'error' && <p className="talk-error">Harness stopped: {status.error}</p>}
      {status.state === 'done' && <p className="talk-meta">Approved. Ready to share with the patient.</p>}

      {question && (
        <div className="harness-ask">
          <p className="talk-warn">
            {status.subtask && <strong>{status.subtask}: </strong>}
            {status.question}
          </p>
          <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder="Your answer" rows={2} />
          <button
            type="button"
            className="btn btn-sm btn-ink"
            disabled={sending || !text.trim()}
            onClick={() => send(() => answer(caseId, text.trim(), status.subtask))}
          >
            Send answer
          </button>
        </div>
      )}

      {approval && (
        <div className="harness-ask">
          {videoUrl ? (
            <video className="harness-video" src={videoUrl} controls />
          ) : (
            <p className="talk-meta">The video is ready for review.</p>
          )}
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Request a change, e.g. “less clinical, softer colours”"
            rows={2}
          />
          <div className="harness-buttons">
            <button
              type="button"
              className="btn btn-sm btn-ink"
              disabled={sending || !text.trim()}
              onClick={() => send(() => requestEdit(caseId, text.trim()))}
            >
              Request edit
            </button>
            <button type="button" className="btn btn-sm btn-mint" disabled={sending} onClick={() => send(() => approve(caseId))}>
              Approve
            </button>
          </div>
        </div>
      )}

      {error && <p className="talk-error">{error}</p>}
    </div>
  )
}
