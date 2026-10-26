import { useCallback, useEffect, useRef, useState } from 'react'

// First type the browser supports is used; the backend accepts webm, mp4 and wav.
const MIME_TYPES = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4']

const isSupported = () =>
  typeof window !== 'undefined' && Boolean(navigator.mediaDevices?.getUserMedia) && typeof MediaRecorder !== 'undefined'

/**
 * MediaRecorder wrapper with a hard time limit.
 * onStop(blob, seconds) fires once per finished clip.
 * error: null | 'unsupported' | 'denied' | 'noMic' | 'failed'
 */
export default function useRecorder({ maxSeconds = 30, onStop } = {}) {
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

    const chunks = []
    const startedAt = Date.now()
    recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data)
    recorder.onstop = () => {
      clearInterval(timerRef.current)
      stream.getTracks().forEach((t) => t.stop())
      setIsRecording(false)
      if (recorder.discarded) return
      const clip = new Blob(chunks, { type: recorder.mimeType || mimeType || 'audio/webm' })
      setBlob(clip)
      if (clip.size > 0) onStopRef.current?.(clip, Math.min(maxSeconds, Math.round((Date.now() - startedAt) / 1000)))
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

  return { start, stop, isRecording, secondsLeft, blob, error, supported: isSupported() }
}
