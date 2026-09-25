import { useEffect, useMemo, useState } from 'react'
import { createCase, getTranscript, transcribe, uploadAudio } from './api'
import { useRecorder } from './recorder/useRecorder'
import { toWav16k } from './recorder/wav'
import './App.css'

type Phase = 'ready' | 'uploading' | 'transcribing' | 'done' | 'error'

type Result = { caseId: string; seconds: number; summary: string; text: string }

function formatTime(seconds: number) {
  const s = Math.floor(seconds)
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

function App() {
  const recorder = useRecorder()
  const [imported, setImported] = useState<File | null>(null)
  const [phase, setPhase] = useState<Phase>('ready')
  const [message, setMessage] = useState<string | null>(null)
  const [result, setResult] = useState<Result | null>(null)

  const source = recorder.blob ?? imported
  const previewUrl = useMemo(() => (source ? URL.createObjectURL(source) : null), [source])
  useEffect(() => () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl)
  }, [previewUrl])

  const busy = phase === 'uploading' || phase === 'transcribing'
  const recording = recorder.state === 'recording'

  function startOver() {
    recorder.reset()
    setImported(null)
    setResult(null)
    setMessage(null)
    setPhase('ready')
  }

  async function submit() {
    if (!source) return
    setResult(null)
    setMessage(null)
    try {
      setPhase('uploading')
      const { wav, seconds } = await toWav16k(source)
      const { id } = await createCase()
      await uploadAudio(id, wav)
      setPhase('transcribing')
      const output = await transcribe(id)
      const { text } = await getTranscript(id)
      setResult({ caseId: id, seconds, summary: output.summary, text })
      setPhase('done')
    } catch (e) {
      setMessage(e instanceof Error ? e.message : String(e))
      setPhase('error')
    }
  }

  return (
    <main className="recorder">
      <header>
        <p className="eyebrow">Procedure explainer</p>
        <h1>Describe the procedure</h1>
        <p className="lede">
          Walk through the procedure as you would for a patient. The recording and transcript stay
          on this device.
        </p>
      </header>

      <section className="panel" aria-labelledby="step0">
        <h2 id="step0">
          <span className="step">0</span> Record
        </h2>

        <div className="capture">
          <button
            type="button"
            className={`mic ${recording ? 'live' : ''}`}
            onClick={recording ? recorder.stop : recorder.start}
            disabled={busy}
            aria-pressed={recording}
          >
            {recording ? 'Stop' : source ? 'Record again' : 'Start recording'}
          </button>
          <div className="meter" aria-hidden="true">
            <div className="fill" style={{ transform: `scaleX(${Math.min(1, recorder.level * 1.6)})` }} />
          </div>
          <span className="time" aria-live="off">
            {formatTime(recorder.elapsed)}
          </span>
        </div>

        <label className="import">
          or import an audio file
          <input
            type="file"
            accept="audio/*"
            disabled={busy || recording}
            onChange={(e) => {
              recorder.reset()
              setResult(null)
              setImported(e.target.files?.[0] ?? null)
            }}
          />
        </label>

        {recorder.error && <p className="error">Microphone: {recorder.error}</p>}

        {previewUrl && !recording && (
          <div className="preview">
            <audio controls src={previewUrl} />
            <div className="actions">
              <button type="button" className="primary" onClick={submit} disabled={busy}>
                {phase === 'uploading' ? 'Saving…' : phase === 'transcribing' ? 'Transcribing…' : 'Transcribe'}
              </button>
              <button type="button" onClick={startOver} disabled={busy}>
                Discard
              </button>
            </div>
          </div>
        )}
      </section>

      <section className="panel" aria-labelledby="step1" aria-busy={busy}>
        <h2 id="step1">
          <span className="step">1</span> Transcript
        </h2>
        {phase === 'transcribing' && (
          <p className="status">
            Transcribing on device with LFM2.5-Audio. The first run also loads the model.
          </p>
        )}
        {phase === 'error' && <p className="error">{message}</p>}
        {result ? (
          <>
            <p className="meta">
              Case <code>{result.caseId}</code> · {formatTime(result.seconds)} · {result.summary}
            </p>
            <blockquote className="transcript">{result.text || '(no speech detected)'}</blockquote>
          </>
        ) : (
          phase !== 'transcribing' && phase !== 'error' && <p className="muted">Nothing transcribed yet.</p>
        )}
      </section>
    </main>
  )
}

export default App
