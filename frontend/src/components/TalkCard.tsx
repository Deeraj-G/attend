import { useEffect, useMemo, useRef, useState } from 'react'
import {
  createCase,
  getReports,
  getStatus,
  getTranscript,
  getVideo,
  runHarness,
  uploadAudio,
  type HarnessStatus,
  type Report,
} from '../api'
import { useRecorder } from '../recorder/useRecorder'
import { toWav16k } from '../recorder/wav'
import { HarnessPanel } from './HarnessPanel'
import { MicIcon, StopIcon } from './Icons'

export type Mode = 'patient' | 'student'

export type TalkResult = {
  caseId: string
  seconds: number
  text: string
  summary: string
  data: Record<string, number>
}

type Phase = 'idle' | 'saving' | 'transcribing' | 'done' | 'error'

const POLL_MS = 2500

function formatTime(seconds: number) {
  const s = Math.floor(seconds)
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

type Props = {
  mode: Mode
  onModeChange: (mode: Mode) => void
  onResult: (result: TalkResult | null) => void
  onVideo: (url: string | null) => void
}

export function TalkCard({ mode, onModeChange, onResult, onVideo }: Props) {
  const recorder = useRecorder()
  const [phase, setPhase] = useState<Phase>('idle')
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<TalkResult | null>(null)
  const [audio, setAudio] = useState<Blob | null>(null)
  const submitOnStop = useRef(false)
  const [caseId, setCaseId] = useState<string | null>(null)
  const [seconds, setSeconds] = useState(0)
  const [status, setStatus] = useState<HarnessStatus>({ state: 'idle' })
  const [reports, setReports] = useState<Report[]>([])
  const [videoUrl, setVideoUrl] = useState<string | null>(null)

  const listening = recorder.state === 'recording'
  const busy = phase === 'saving' || phase === 'transcribing' || status.state === 'running'

  const audioUrl = useMemo(() => (audio ? URL.createObjectURL(audio) : null), [audio])
  useEffect(
    () => () => {
      if (audioUrl) URL.revokeObjectURL(audioUrl)
    },
    [audioUrl],
  )

  async function submit(source: Blob) {
    setAudio(source)
    setError(null)
    setResult(null)
    onResult(null)
    setReports([])
    setVideoUrl(null)
    onVideo(null)
    try {
      setPhase('saving')
      const { wav, seconds } = await toWav16k(source)
      const { id } = await createCase()
      await uploadAudio(id, wav)
      setSeconds(seconds)
      setCaseId(id)
      setStatus(await runHarness(id))
      setPhase('transcribing')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setPhase('error')
    }
  }

  // Poll the harness while it runs; the Manager's decision says what the doctor sees next.
  useEffect(() => {
    if (!caseId || status.state !== 'running') return
    let cancelled = false
    const timer = setInterval(async () => {
      try {
        const [next, log] = await Promise.all([getStatus(caseId), getReports(caseId)])
        if (cancelled) return
        setReports(log)
        setStatus(next)
      } catch (e) {
        if (!cancelled) setStatus({ state: 'error', error: e instanceof Error ? e.message : String(e) })
      }
    }, POLL_MS)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [caseId, status.state])

  // Show the transcript as soon as the transcribe step passes its audit.
  const transcribed = reports.find((r) => r.subtask === 'transcribe' && r.status === 'complete')
  useEffect(() => {
    if (!caseId || !transcribed || result) return
    void getTranscript(caseId).then(({ text }) => {
      const next = { caseId, seconds, text, summary: transcribed.state_update.facts[0] ?? '', data: {} }
      setResult(next)
      onResult(next)
      setPhase('done')
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId, transcribed?.id])

  // Fetch the video when the Manager reaches the approval gate.
  useEffect(() => {
    if (!caseId || status.state !== 'waiting' || status.kind !== 'approval') return
    void getVideo(caseId)
      .then((v) => {
        setVideoUrl(v.sample_url)
        onVideo(v.sample_url)
      })
      .catch(() => setVideoUrl(null))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId, status.state, status.kind, reports.length])

  // MediaRecorder hands over the blob asynchronously after stop().
  useEffect(() => {
    if (recorder.blob && submitOnStop.current) {
      submitOnStop.current = false
      void submit(recorder.blob)
    }
    // submit is recreated each render; the blob is the only trigger that matters.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recorder.blob])

  function onTalk() {
    if (listening) {
      submitOnStop.current = true
      recorder.stop()
    } else {
      setPhase('idle')
      setError(null)
      void recorder.start()
    }
  }

  const flagged = result && (result.data.empty_segments > 0 || result.data.truncated_segments > 0)

  return (
    <div className="talk-card" id="talk">
      <p className="talk-label" id="talk-label">
        What would you like to see?
      </p>

      <div className={`talk-box ${listening ? 'is-listening' : ''}`} aria-live="polite" aria-labelledby="talk-label">
        {listening ? (
          <div className="listening">
            <span className="rec-dot" aria-hidden="true" />
            <span>Listening…</span>
            <div className="meter" aria-hidden="true">
              <div className="meter-fill" style={{ transform: `scaleX(${Math.min(1, recorder.level * 1.6)})` }} />
            </div>
            <span className="rec-time">{formatTime(recorder.elapsed)}</span>
          </div>
        ) : phase === 'saving' ? (
          <p className="talk-status">
            <span className="spinner" aria-hidden="true" />
            Saving your recording…
          </p>
        ) : phase === 'transcribing' ? (
          <p className="talk-status">
            <span className="spinner" aria-hidden="true" />
            Transcribing on this device<span className="dots" aria-hidden="true" />
          </p>
        ) : result ? (
          <p className="transcript">{result.text || '(No speech detected. Try again a little closer to the mic.)'}</p>
        ) : (
          <p className="talk-placeholder">Tap “Talk to me” and describe the procedure, the way you would to a patient.</p>
        )}
      </div>

      {recorder.error && <p className="talk-error">Microphone unavailable: {recorder.error}</p>}
      {phase === 'error' && <p className="talk-error">{error}</p>}

      <div className="talk-actions">
        <div className="segmented" role="radiogroup" aria-label="Who is watching">
          {(['patient', 'student'] as const).map((m) => (
            <button
              key={m}
              type="button"
              role="radio"
              aria-checked={mode === m}
              className={mode === m ? 'is-active' : ''}
              onClick={() => onModeChange(m)}
            >
              {m === 'patient' ? "I'm a patient" : "I'm a med student"}
            </button>
          ))}
        </div>
        <button
          type="button"
          className={`talk-button ${listening ? 'is-live' : ''}`}
          onClick={onTalk}
          disabled={busy}
        >
          {listening ? <StopIcon /> : busy ? <span className="spinner" aria-hidden="true" /> : <MicIcon />}
          {listening ? 'Stop' : busy ? 'Working…' : result ? 'Talk again' : 'Talk to me'}
        </button>
      </div>

      {result && (
        <div className="talk-result">
          <p className="talk-meta">
            Case <code>{result.caseId}</code> · {formatTime(result.seconds)} · {result.summary}
          </p>
          {flagged && (
            <p className="talk-warn">Part of the recording may not have transcribed cleanly. Please read it through.</p>
          )}
          {audioUrl && <audio controls src={audioUrl} />}
        </div>
      )}

      {caseId && status.state !== 'idle' && (
        <HarnessPanel caseId={caseId} status={status} reports={reports} videoUrl={videoUrl} onResume={setStatus} />
      )}

      {!result && !listening && !busy && (
        <p className="talk-hint">
          Try saying: “We’ll do a colonoscopy under light sedation…” ·{' '}
          <label className="upload-link">
            or upload a recording
            <input
              type="file"
              accept="audio/*"
              onChange={(e) => {
                const file = e.target.files?.[0]
                e.target.value = ''
                if (file) void submit(file)
              }}
            />
          </label>
        </p>
      )}
    </div>
  )
}
