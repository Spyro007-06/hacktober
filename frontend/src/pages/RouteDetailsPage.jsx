import { ArrowLeft } from 'lucide-react'
import { useComplaint } from '../context/ComplaintContext'
import { useLanguage } from '../context/LanguageContext'
import Button from '../components/ui/Button'
import PageHeading from '../components/ui/PageHeading'

// Milestone 3 adds the route card, operator override, complainant form and Generate draft.
export default function RouteDetailsPage({ focusHeading }) {
  const { t } = useLanguage()
  const { backToDescribe } = useComplaint()
  return (
    <div className="space-y-8">
      <PageHeading title={t('route.title')} focus={focusHeading} />
      <Button variant="ghost" icon={ArrowLeft} onClick={() => backToDescribe()}>
        {t('btn.back')}
      </Button>
    </div>
  )
}
