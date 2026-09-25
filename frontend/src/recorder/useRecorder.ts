import { useCallback, useEffect, useRef, useState } from 'react'

export type RecorderState = 'idle' | 'recording' | 'stopped'

/** Mic capture via MediaRecorder, with a live input level (0..1) and elapsed seconds. */
export function useRecorder() {
  const [state, setState] = useState<RecorderState>('idle')
  const [blob, setBlob] = useState<Blob | null>(null)
  const [level, setLevel] = useState(0)
  const [elapsed, setElapsed] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const teardown = useRef<() => void>(() => {})

  const start = useCallback(async () => {
    setError(null)
    setBlob(null)
    let stream: MediaStream
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Microphone unavailable')
      return
    }

    const recorder = new MediaRecorder(stream)
    const chunks: Blob[] = []
    recorder.ondataavailable = (e) => chunks.push(e.data)
    recorder.onstop = () => setBlob(new Blob(chunks, { type: recorder.mimeType }))

    const ctx = new AudioContext()
    const analyser = ctx.createAnalyser()
    analyser.fftSize = 1024
    ctx.createMediaStreamSource(stream).connect(analyser)
    const samples = new Float32Array(analyser.fftSize)
    const startedAt = performance.now()
    let frame = 0
    const tick = () => {
      analyser.getFloatTimeDomainData(samples)
      let peak = 0
      for (const s of samples) peak = Math.max(peak, Math.abs(s))
      setLevel(peak)
      setElapsed((performance.now() - startedAt) / 1000)
      frame = requestAnimationFrame(tick)
    }
    tick()

    teardown.current = () => {
      cancelAnimationFrame(frame)
      if (recorder.state !== 'inactive') recorder.stop()
      stream.getTracks().forEach((t) => t.stop())
      void ctx.close()
      setLevel(0)
    }
    recorder.start()
    setState('recording')
  }, [])

  const stop = useCallback(() => {
    teardown.current()
    setState('stopped')
  }, [])

  const reset = useCallback(() => {
    teardown.current()
    setBlob(null)
    setElapsed(0)
    setState('idle')
  }, [])

  useEffect(() => () => teardown.current(), [])

  return { state, blob, level, elapsed, error, start, stop, reset }
}
