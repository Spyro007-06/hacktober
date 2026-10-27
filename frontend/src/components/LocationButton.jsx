import { useEffect, useState } from 'react'
import { Check, MapPin, X } from 'lucide-react'
import { reverseGeocode } from '../api/client'
import { useComplaint } from '../context/ComplaintContext'
import { useLanguage } from '../context/LanguageContext'
import Button from './ui/Button'
import Banner from './ui/Banner'

const WEAK_ACCURACY_M = 150
const GOOD_ACCURACY_M = 30 // stop refining once the fix is this tight
const MAX_ACCURACY_M = 500 // coarser than this is Wi-Fi/IP guessing, so no address is filled in
const REFINE_MS = 20000 // wait this long for the GPS to settle
let autoTried = false // ask once per page load; the button stays for retries

/**
 * Finds the position with the device GPS as soon as the screen opens (the browser's own permission prompt is the
 * consent), turns it into an address and fills the address fields. Failure never blocks Continue.
 */
export default function LocationButton() {
  const { t, uiLang } = useLanguage()
  const { location, setLocation, pending, complaintLang } = useComplaint()
  const [status, setStatus] = useState('idle') // idle | locating | addressing | denied

  // Phones return a rough first fix and sharpen it over a few seconds, so keep the best one instead of the first.
  function locate() {
    if (!navigator.geolocation) return setStatus('denied')
    setStatus('locating')
    let best = null
    let done = false
    let watchId
    let timer

    async function finish() {
      if (done) return
      done = true
      navigator.geolocation.clearWatch(watchId)
      clearTimeout(timer)
      if (!best) return setStatus('denied')
      setLocation(best)
      if (best.accuracy > MAX_ACCURACY_M) return setStatus('idle')
      setStatus('addressing')
      const address = await reverseGeocode(best.lat, best.lon, complaintLang)
      setLocation({ ...best, address })
      setStatus('idle')
    }

    watchId = navigator.geolocation.watchPosition(
      ({ coords }) => {
        if (!best || coords.accuracy < best.accuracy) best = { lat: coords.latitude, lon: coords.longitude, accuracy: Math.round(coords.accuracy) }
        if (best.accuracy <= GOOD_ACCURACY_M) finish()
      },
      () => finish(),
      { enableHighAccuracy: true, timeout: REFINE_MS, maximumAge: 0 },
    )
    timer = setTimeout(finish, REFINE_MS)
  }

  useEffect(() => {
    if (autoTried || location) return
    autoTried = true
    locate()
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run once on first open
  }, [])

  const busy = status === 'locating' || status === 'addressing'

  return (
    <section aria-labelledby="loc-title" className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h2 id="loc-title" className="text-section font-bold">
          {t('location.title')}
        </h2>
        <span className="text-support text-muted">{t('form.optional')}</span>
      </div>
      <p className="text-muted">{t('location.hint')}</p>

      {location ? (
        <div className="space-y-2 rounded-control border border-success/30 bg-success-soft px-4 py-2" role="status">
          <div className="flex flex-wrap items-center gap-3">
            <Check className="size-5 text-success" strokeWidth={3} aria-hidden="true" />
            <span className="font-semibold text-success">{status === 'addressing' ? t('location.finding') : t('location.got')}</span>
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
          {location.address && <p className="text-heading">{location.address}</p>}
          {location.accuracy != null && <p className="text-support text-muted">{t('location.accuracy', { n: location.accuracy })}</p>}
        </div>
      ) : (
        <Button variant="secondary" icon={MapPin} onClick={locate} loading={busy} disabled={Boolean(pending)}>
          {busy ? t('location.locating') : t('location.use')}
        </Button>
      )}

      {location && status === 'idle' && !location.address && location.accuracy <= MAX_ACCURACY_M && (
        <Banner tone="warning" compact>
          {t('location.noAddress')}
        </Banner>
      )}
      {location && location.accuracy > WEAK_ACCURACY_M && (
        <Banner tone="warning" compact>
          {location.accuracy > MAX_ACCURACY_M ? t('location.coarse', { n: location.accuracy }) : t('location.weak')}
        </Banner>
      )}
      {status === 'denied' && !location && (
        <Banner tone="warning" compact>
          {t('location.denied')}
        </Banner>
      )}
    </section>
  )
}
