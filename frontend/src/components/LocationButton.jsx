import { useState } from 'react'
import { Check, MapPin, X } from 'lucide-react'
import { useComplaint } from '../context/ComplaintContext'
import { useLanguage } from '../context/LanguageContext'
import Button from './ui/Button'

/** Optional. Geolocation is requested only when the user taps the button; failure never blocks Continue. */
export default function LocationButton() {
  const { t } = useLanguage()
  const { location, setLocation, pending } = useComplaint()
  const [status, setStatus] = useState('idle') // idle | locating | denied

  function locate() {
    if (!navigator.geolocation) return setStatus('denied')
    setStatus('locating')
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        setLocation({ lat: coords.latitude, lon: coords.longitude })
        setStatus('idle')
      },
      () => setStatus('denied'),
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 },
    )
  }

  return (
    <section aria-labelledby="loc-title" className="space-y-3">
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="loc-title" className="text-xl font-bold">
          {t('location.title')}
        </h2>
        <span className="text-sm text-muted">{t('form.optional')}</span>
      </div>
      <p className="text-muted">{t('location.hint')}</p>

      {location ? (
        <div className="flex flex-wrap items-center gap-3 rounded-control bg-success-soft px-4 py-2" role="status">
          <Check className="size-5 text-success" strokeWidth={3} aria-hidden="true" />
          <span className="font-semibold text-success">{t('location.got')}</span>
          <button
            type="button"
            onClick={() => setLocation(null)}
            disabled={Boolean(pending)}
            aria-label={t('location.remove')}
            className="ml-auto flex size-12 items-center justify-center rounded-full text-success hover:bg-surface"
          >
            <X className="size-5" aria-hidden="true" />
          </button>
        </div>
      ) : (
        <Button variant="secondary" icon={MapPin} onClick={locate} loading={status === 'locating'} disabled={Boolean(pending)}>
          {status === 'locating' ? t('location.locating') : t('location.use')}
        </Button>
      )}

      {status === 'denied' && !location && (
        <p role="alert" className="rounded-control bg-warning-soft px-4 py-3 text-warning">
          {t('location.denied')}
        </p>
      )}
    </section>
  )
}
