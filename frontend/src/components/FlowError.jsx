import { useComplaint } from '../context/ComplaintContext'
import { useLanguage } from '../context/LanguageContext'
import ErrorBanner from './ui/ErrorBanner'

/** The current wizard request error, with Retry or Start over as the spec's error table says. */
export default function FlowError() {
  const { t } = useLanguage()
  const { error, retry, startOver } = useComplaint()
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
