import { useEffect } from 'react'
import { RotateCcw } from 'lucide-react'
import { errorKey } from '../../api/client'
import { useLanguage } from '../../context/LanguageContext'
import Banner from './Banner'
import Button from './Button'

/** Friendly, translated message for an ApiError; technical details go to the console only. */
export default function ErrorBanner({ error, onRetry, actionLabel, onAction }) {
  const { t } = useLanguage()

  useEffect(() => {
    if (error) console.warn('[kural]', error.code ?? '', error.status ?? '', error.message)
  }, [error])

  if (!error) return null

  return (
    <Banner tone="error">
      <p className="font-semibold text-heading">{t(errorKey(error))}</p>
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
    </Banner>
  )
}
