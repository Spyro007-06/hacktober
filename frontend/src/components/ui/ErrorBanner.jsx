import { useEffect } from 'react'
import { RotateCcw, TriangleAlert } from 'lucide-react'
import { errorKey } from '../../api/client'
import { useLanguage } from '../../context/LanguageContext'
import Button from './Button'

/** Friendly, translated message for an ApiError; technical details go to the console only. */
export default function ErrorBanner({ error, onRetry, actionLabel, onAction }) {
  const { t } = useLanguage()

  useEffect(() => {
    if (error) console.warn('[kural]', error.code ?? '', error.status ?? '', error.message)
  }, [error])

  if (!error) return null

  return (
    <div role="alert" className="flex gap-3 rounded-card border border-danger/25 bg-danger-soft p-4 sm:gap-4 sm:p-5">
      <TriangleAlert className="mt-0.5 size-6 shrink-0 text-danger" aria-hidden="true" />
      <div className="min-w-0 flex-1 space-y-3">
        <p className="font-medium text-ink">{t(errorKey(error))}</p>
        {(onRetry || onAction) && (
          <div className="flex flex-wrap gap-3">
            {onRetry && (
              <Button variant="secondary" icon={RotateCcw} onClick={onRetry}>
                {t('btn.retry')}
              </Button>
            )}
            {onAction && (
              <Button variant="secondary" onClick={onAction}>
                {actionLabel}
              </Button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
