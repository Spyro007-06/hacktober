import { useEffect, useRef, useState } from 'react'
import { Square, Volume2 } from 'lucide-react'
import { tts } from '../api/client'
import { useLanguage } from '../context/LanguageContext'
import Button from './ui/Button'
import Banner from './ui/Banner'

const sentences = (text) => (text ?? '').split(/(?<=[.!?])\s+/).map((s) => s.trim()).filter(Boolean)

/**
 * Backend next steps in both languages (UI language first), each with a Play button via POST /api/tts.
 * HTTP 501 hides Play for good; other failures keep the written steps and say audio failed.
 */
export default function NextSteps({ nextSteps, uiLang }) {
  const { t } = useLanguage()
  const [ttsAvailable, setTtsAvailable] = useState(true)
  const [playing, setPlaying] = useState({ lang: null, status: 'idle' }) // idle | loading | playing
  const [failed, setFailed] = useState(false)
  const cache = useRef(new Map()) // `${lang}:${text}` -> object URL
  const audio = useRef(null)

  useEffect(
    () => () => {
      audio.current?.pause()
      cache.current.forEach((url) => URL.revokeObjectURL(url))
    },
    [],
  )

  async function toggle(lang) {
    audio.current?.pause()
    if (playing.lang === lang && playing.status === 'playing') return setPlaying({ lang: null, status: 'idle' })
    setFailed(false)

    const text = nextSteps[lang]
    const key = `${lang}:${text}`
    let url = cache.current.get(key)
    if (!url) {
      setPlaying({ lang, status: 'loading' })
      try {
        url = URL.createObjectURL(await tts(text, lang))
        cache.current.set(key, url)
      } catch (err) {
        if (err.status === 501) setTtsAvailable(false)
        else setFailed(true)
        return setPlaying({ lang: null, status: 'idle' })
      }
    }

    const a = new Audio(url)
    a.onended = () => setPlaying({ lang: null, status: 'idle' })
    audio.current = a
    try {
      await a.play()
      setPlaying({ lang, status: 'playing' })
    } catch {
      setFailed(true)
      setPlaying({ lang: null, status: 'idle' })
    }
  }

  const order = uiLang === 'ta' ? ['ta', 'en'] : ['en', 'ta']

  return (
    <section aria-labelledby="next-title" className="space-y-4">
      <h2 id="next-title" className="text-section font-bold">
        {t('nextSteps.title')}
      </h2>
      <div className="grid gap-4 md:grid-cols-2">
        {order
          .filter((lang) => nextSteps?.[lang])
          .map((lang) => {
            const items = sentences(nextSteps[lang])
            const state = playing.lang === lang ? playing.status : 'idle'
            return (
              <div key={lang} lang={lang} className="flex flex-col gap-4 rounded-card border border-line bg-surface p-5 shadow-card">
                <p className="text-support font-semibold text-muted">{t(`lang.${lang}`)}</p>
                {items.length > 1 ? (
                  <ol className="list-decimal space-y-2 pl-6 marker:font-semibold marker:text-primary-ink">
                    {items.map((s, i) => (
                      <li key={i}>{s}</li>
                    ))}
                  </ol>
                ) : (
                  <p>{nextSteps[lang]}</p>
                )}
                {ttsAvailable && (
                  <Button
                    variant="secondary"
                    className="mt-auto self-start"
                    icon={state === 'playing' ? Square : Volume2}
                    loading={state === 'loading'}
                    onClick={() => toggle(lang)}
                  >
                    {state === 'loading' ? t('nextSteps.loadingAudio') : state === 'playing' ? t('btn.stop') : t('btn.play')}
                  </Button>
                )}
              </div>
            )
          })}
      </div>
      {failed && (
        <Banner tone="warning" compact>
          {t('nextSteps.playFailed')}
        </Banner>
      )}
    </section>
  )
}
