import { useCallback, useEffect, useRef, useState } from 'react'

// First type the browser supports is used; the backend accepts webm, mp4 and wav.
const MIME_TYPES = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4']

const isSupported = () =>
  typeof window !== 'undefined' && Boolean(navigator.mediaDevices?.getUserMedia) && typeof MediaRecorder !== 'undefined'

/**
 * MediaRecorder wrapper with a hard time limit.
 * onStop(blob, seconds, peak) fires once per finished clip. `peak` is the loudest input level heard (0..1), or
 * undefined when the browser could not measure it; a peak near 0 means the microphone delivered silence.
 * error: null | 'unsupported' | 'denied' | 'noMic' | 'failed'
 */
export default function useRecorder({ maxSeconds = 30, onStop } = {}) {
  const [level, setLevel] = useState(0) // live input level 0..1 while recording
  const [isRecording, setIsRecording] = useState(false)
  const [secondsLeft, setSecondsLeft] = useState(maxSeconds)
  const [blob, setBlob] = useState(null)
  const [error, setError] = useState(null)
  const recorderRef = useRef(null)
  const timerRef = useRef(null)
  const onStopRef = useRef(onStop)
  onStopRef.current = onStop

  const stop = useCallback(() => {
    clearInterval(timerRef.current)
    if (recorderRef.current?.state === 'recording') recorderRef.current.stop()
  }, [])

  const start = useCallback(async () => {
    if (recorderRef.current?.state === 'recording') return
    if (!isSupported()) return setError('unsupported')
    setError(null)

    let stream
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    } catch (err) {
      const kind = { NotAllowedError: 'denied', SecurityError: 'denied', NotFoundError: 'noMic' }[err.name]
      return setError(kind ?? 'failed')
    }

    const mimeType = MIME_TYPES.find((t) => MediaRecorder.isTypeSupported(t))
    let recorder
    try {
      recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
    } catch {
      stream.getTracks().forEach((t) => t.stop())
      return setError('failed')
    }

    // Measure the input level so a silent or muted microphone is caught before the clip is uploaded.
    let meter = null
    try {
      const ctx = new AudioContext()
      const analyser = ctx.createAnalyser()
      analyser.fftSize = 1024
      ctx.createMediaStreamSource(stream).connect(analyser)
      const data = new Uint8Array(analyser.fftSize)
      meter = { ctx, peak: 0 }
      meter.timer = setInterval(() => {
        analyser.getByteTimeDomainData(data)
        let loudest = 0
        for (const v of data) loudest = Math.max(loudest, Math.abs(v - 128) / 128)
        meter.peak = Math.max(meter.peak, loudest)
        setLevel(loudest)
      }, 100)
    } catch {
      meter = null // no level reading: the clip is still recorded and sent
    }

    const chunks = []
    const startedAt = Date.now()
    recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data)
    recorder.onstop = () => {
      clearInterval(timerRef.current)
      if (meter) {
        clearInterval(meter.timer)
        meter.ctx.close().catch(() => {})
      }
      setLevel(0)
      stream.getTracks().forEach((t) => t.stop())
      setIsRecording(false)
      if (recorder.discarded) return
      const clip = new Blob(chunks, { type: recorder.mimeType || mimeType || 'audio/webm' })
      setBlob(clip)
      if (clip.size > 0) {
        onStopRef.current?.(clip, Math.min(maxSeconds, Math.round((Date.now() - startedAt) / 1000)), meter?.peak)
      }
    }
    recorder.onerror = () => {
      setError('failed')
      stop()
    }

    recorderRef.current = recorder
    recorder.start()
    setSecondsLeft(maxSeconds)
    setIsRecording(true)
    timerRef.current = setInterval(() => {
      const left = Math.max(0, maxSeconds - Math.floor((Date.now() - startedAt) / 1000))
      setSecondsLeft(left)
      if (left === 0) stop() // auto-stop at 0
    }, 250)
  }, [maxSeconds, stop])

  // Leaving the page mid-recording releases the mic and drops the partial clip.
  useEffect(
    () => () => {
      if (recorderRef.current) recorderRef.current.discarded = true
      stop()
    },
    [stop],
  )

  return { start, stop, isRecording, secondsLeft, blob, error, level, supported: isSupported() }
}
