import { useCallback, useEffect, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import { useLanguage } from '../context/LanguageContext'

const KEY = 'kural.splash'
const SHOW_MS = 2400
const BARS = [0.35, 0.7, 1, 0.55, 0.85, 0.4, 0.65] // a voice, drawn as sound bars

const seen = () => {
  try {
    // People who ask for reduced motion skip the intro entirely.
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return true
    return sessionStorage.getItem(KEY) === '1'
  } catch {
    return false
  }
}

/**
 * Opening screen: the voice bars turn into the word "குரல்" (Kural, "voice"). Shown once per browser session, only on the
 * landing page, and skippable by click, Enter, Space or Escape. With reduced motion it is not shown at all.
 */
export default function Splash() {
  const { t } = useLanguage()
  const reduce = useReducedMotion()
  const [open, setOpen] = useState(() => !seen())

  const close = useCallback(() => {
    try {
      sessionStorage.setItem(KEY, '1')
    } catch {
      // Storage blocked: the intro may show again after a refresh, which is harmless.
    }
    setOpen(false)
  }, [])

  useEffect(() => {
    if (!open) return undefined
    const timer = setTimeout(close, SHOW_MS)
    const onKey = (e) => ['Escape', 'Enter', ' '].includes(e.key) && close()
    window.addEventListener('keydown', onKey)
    return () => {
      clearTimeout(timer)
      window.removeEventListener('keydown', onKey)
    }
  }, [open, close, reduce])

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          key="splash"
          role="status"
          aria-label={t('app.tagline')}
          onClick={close}
          initial={{ opacity: 1 }}
          exit={{ y: '-100%' }}
          transition={{ duration: 0.6, ease: [0.76, 0, 0.24, 1] }}
          className="fixed inset-0 z-50 flex cursor-pointer flex-col items-center justify-center bg-heading px-6 text-center"
        >
          <div className="flex h-16 items-center gap-2" aria-hidden="true">
            {BARS.map((h, i) => (
              <motion.span
                key={i}
                className="w-2.5 rounded-full bg-primary"
                style={{ height: `${h * 100}%` }}
                initial={reduce ? false : { scaleY: 0.15, opacity: 0.4 }}
                animate={reduce ? undefined : { scaleY: [0.15, 1, 0.55, 1], opacity: 1 }}
                transition={{ duration: 1.1, delay: i * 0.07, ease: 'easeInOut' }}
              />
            ))}
          </div>

          <motion.p
            lang="ta"
            className="mt-8 text-[clamp(4rem,16vw,8rem)] font-bold leading-none text-primary"
            initial={reduce ? false : { opacity: 0, y: 28 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: reduce ? 0 : 0.7, ease: [0.22, 1, 0.36, 1] }}
          >
            குரல்
          </motion.p>
          <motion.p
            lang="en"
            className="mt-6 text-section font-bold tracking-[0.3em] text-white"
            initial={reduce ? false : { opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.5, delay: reduce ? 0 : 1.05 }}
          >
            KURAL
          </motion.p>
          <motion.p
            className="mt-8 max-w-md text-white/80"
            initial={reduce ? false : { opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.5, delay: reduce ? 0 : 1.3 }}
          >
            {t('app.tagline')}
          </motion.p>

          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              close()
            }}
            className="absolute bottom-8 min-h-12 rounded-control border-2 border-white/40 px-5 font-bold text-white hover:border-white focus-visible:outline-white"
          >
            {t('splash.skip')}
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
