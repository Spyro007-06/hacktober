import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Check, LoaderCircle, Mic, MicOff, Pause, Play, RotateCcw, Square } from 'lucide-react'
import { errorKey } from '../api/client'
import { useComplaint } from '../context/ComplaintContext'
import { useLanguage } from '../context/LanguageContext'
import useRecorder from '../hooks/useRecorder'
import Segmented from './ui/Segmented'
import Button from './ui/Button'
import Banner from './ui/Banner'

const MAX_SECONDS = 30
const RING_R = 64
const RING_C = 2 * Math.PI * RING_R

const formatSeconds = (s) => `0:${String(s).padStart(2, '0')}`

function ClipRow({ clip, index, playing, onTogglePlay }) {
  const { t } = useLanguage()
  const { retryClip } = useComplaint()
  const n = index + 1

  return (
    <motion.li
      layout
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-control border border-line bg-surface px-3 py-2"
    >
      <button
        type="button"
        onClick={() => onTogglePlay(clip)}
        aria-label={t(playing ? 'rec.pause' : 'rec.play', { n })}
        className="flex size-12 shrink-0 items-center justify-center rounded-full text-heading transition-colors hover:bg-primary-soft"
      >
        {playing ? <Pause className="size-5" aria-hidden="true" /> : <Play className="size-5" aria-hidden="true" />}
      </button>
      <span className="font-semibold">
        {t('rec.clip', { n })} <span className="font-normal tabular-nums text-muted">· {formatSeconds(clip.seconds)}</span>
      </span>
      <span className="ml-auto flex min-w-0 items-center gap-2 text-support" aria-live="polite">
        {clip.status === 'transcribing' && (
          <>
            <LoaderCircle className="size-4 shrink-0 animate-spin text-heading" aria-hidden="true" />
            <span className="text-muted">{t('loading.transcribing')}</span>
          </>
        )}
        {clip.status === 'done' && (
          <>
            <Check className="size-4 shrink-0 text-success" strokeWidth={3} aria-hidden="true" />
            <span className="text-success">{t('rec.transcribed')}</span>
          </>
        )}
      </span>
      {clip.status === 'error' && (
        <div className="flex w-full flex-wrap items-center gap-3 border-t border-line pt-2" role="alert">
          <p className="flex-1 text-support text-danger">{t(errorKey(clip.error))}</p>
          {clip.error?.code !== 'NO_SOUND' && (
            <Button variant="secondary" icon={RotateCcw} onClick={() => retryClip(clip)}>
              {t('btn.retry')}
            </Button>
          )}
        </div>
      )}
    </motion.li>
  )
}

export default function Recorder() {
  const { t } = useLanguage()
  const { clips, addClip, complaintLang, setComplaintLang, pending } = useComplaint()
  const { start, stop, isRecording, secondsLeft, error, level, supported } = useRecorder({ maxSeconds: MAX_SECONDS, onStop: addClip })
  const [playingId, setPlayingId] = useState(null)
  const audioRef = useRef(null)

  const transcribing = clips.some((c) => c.status === 'transcribing')
  // One clip at a time keeps transcripts in the order they were spoken.
  const disabled = !supported || transcribing || Boolean(pending)

  useEffect(() => () => audioRef.current?.pause(), [])

  function togglePlay(clip) {
    audioRef.current?.pause()
    if (playingId === clip.id) return setPlayingId(null)
    const audio = new Audio(clip.url)
    audio.onended = () => setPlayingId(null)
    audio.play().then(() => setPlayingId(clip.id), () => setPlayingId(null))
    audioRef.current = audio
  }

  const label = isRecording ? t('rec.stop') : clips.length ? t('rec.addClip') : t('rec.start')
  const progress = isRecording ? secondsLeft / MAX_SECONDS : 1
  const errorMessage = !supported ? t('rec.unsupported') : error && t(`rec.${error === 'denied' ? 'micDenied' : error}`)

  return (
    <section aria-labelledby="rec-title" className="rounded-card border border-line bg-surface-muted p-4 sm:p-7">
      {/* The page heading already says what to do; keep the mic above the fold on phones. */}
      <h2 id="rec-title" className="sr-only">
        {t('rec.title')}
      </h2>
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
        <span id="complaint-lang" className="text-support font-semibold text-muted">
          {t('complaintLang.label')}
        </span>
        <div>
          {/* complaint language, independent of the UI language toggle */}
          <Segmented
            labelId="complaint-lang"
            value={complaintLang}
            onChange={setComplaintLang}
            disabled={isRecording}
            options={[
              { value: 'ta', label: t('lang.ta'), lang: 'ta' },
              { value: 'en', label: t('lang.en'), lang: 'en' },
            ]}
          />
        </div>
      </div>

      <div className="mt-4 flex flex-col items-center gap-3 text-center">
        <div className="relative flex size-40 items-center justify-center">
          <svg viewBox="0 0 144 144" className="absolute inset-0 size-full -rotate-90" aria-hidden="true">
            <circle cx="72" cy="72" r={RING_R} fill="none" strokeWidth="6" className="stroke-surface" />
            <circle
              cx="72"
              cy="72"
              r={RING_R}
              fill="none"
              strokeWidth="6"
              strokeLinecap="round"
              strokeDasharray={RING_C}
              strokeDashoffset={RING_C * (1 - progress)}
              className={`transition-[stroke-dashoffset] duration-300 ease-linear ${isRecording ? 'stroke-heading' : 'stroke-transparent'}`}
            />
          </svg>
          <button
            type="button"
            onClick={isRecording ? stop : start}
            disabled={disabled}
            aria-label={label}
            className={`relative flex size-28 items-center justify-center rounded-full shadow-lift transition-[background-color,transform] duration-150 active:scale-95 disabled:cursor-not-allowed disabled:opacity-50 disabled:active:scale-100 ${
              isRecording ? 'bg-heading text-white' : 'bg-primary text-heading hover:bg-primary-hover'
            }`}
          >
            {!supported ? (
              <MicOff className="size-11" aria-hidden="true" />
            ) : isRecording ? (
              <Square className="size-9 fill-current" aria-hidden="true" />
            ) : (
              <Mic className="size-12" aria-hidden="true" />
            )}
          </button>
        </div>

        <div className="min-h-[3.5rem]" aria-live="polite">
          {isRecording ? (
            <div role="timer" aria-live="off">
              <p className="text-3xl font-bold tabular-nums text-heading">{formatSeconds(secondsLeft)}</p>
              <p className="text-muted">{t('rec.secondsLeft', { n: secondsLeft })}</p>
              <div aria-hidden="true" className="mx-auto mt-3 h-2 w-40 overflow-hidden rounded-full bg-surface">
                <div className="h-full rounded-full bg-heading transition-[width] duration-100" style={{ width: `${Math.min(100, level * 200)}%` }} />
              </div>
            </div>
          ) : (
            <p className="font-medium text-text">{transcribing ? t('loading.transcribing') : clips.length ? t('rec.addClip') : t('rec.idle')}</p>
          )}
        </div>

        {errorMessage && (
          <Banner tone="warning" compact>
            {errorMessage}
          </Banner>
        )}
      </div>

      {clips.length > 0 && (
        <div className="mt-5">
          <h3 className="sr-only">{t('rec.clips')}</h3>
          <ul className="space-y-2">
            <AnimatePresence initial={false}>
              {clips.map((clip, i) => (
                <ClipRow key={clip.id} clip={clip} index={i} playing={playingId === clip.id} onTogglePlay={togglePlay} />
              ))}
            </AnimatePresence>
          </ul>
        </div>
      )}
    </section>
  )
}
