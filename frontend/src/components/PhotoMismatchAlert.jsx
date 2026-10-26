import { Camera } from 'lucide-react'
import { useLanguage } from '../context/LanguageContext'
import Button from './ui/Button'
import Banner from './ui/Banner'

/** Backend's mismatch note shown as-is, with the two choices. */
export default function PhotoMismatchAlert({ note, photos, onRetake, onContinue, busy }) {
  const { t } = useLanguage()
  return (
    <div className="space-y-6">
      <Banner tone="warning">
        {note && <p className="text-lg font-semibold text-heading">{note}</p>}
        <p className="text-muted">{t('mismatch.explain')}</p>
      </Banner>

      <div className="flex flex-col gap-3 sm:flex-row">
        <Button size="lg" icon={Camera} onClick={onRetake} disabled={busy}>
          {t('mismatch.retake')}
        </Button>
        <Button size="lg" variant="secondary" onClick={onContinue} loading={busy}>
          {t('mismatch.continue')}
        </Button>
      </div>

      {photos.length > 0 && (
        <ul className="grid grid-cols-3 gap-3 sm:max-w-md">
          {photos.map((p, i) => (
            <li key={p.id} className="aspect-square overflow-hidden rounded-control border border-line">
              <img src={p.url} alt={t('photos.alt', { n: i + 1 })} className="size-full object-cover" />
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
