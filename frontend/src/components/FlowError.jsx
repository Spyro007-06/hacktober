import { useComplaint } from '../context/ComplaintContext'
import { useLanguage } from '../context/LanguageContext'
import ErrorBanner from './ui/ErrorBanner'

/**
 * The current wizard request error, with Retry or Start over as the spec's error table says.
 * `from` limits it to errors raised by that request (e.g. 'save'), so it shows next to the right action.
 */
export default function FlowError({ from }) {
  const { t } = useLanguage()
  const { error, errorFrom, retry, startOver } = useComplaint()
  if (from && errorFrom !== from) return null
  const notFound = error?.code === 'NOT_FOUND'
  return (
    <ErrorBanner
      error={error}
      onRetry={retry ?? undefined}
      actionLabel={notFound ? t('btn.startOver') : undefined}
      onAction={notFound ? startOver : undefined}
    />
  )
}
