import { useLanguage } from '../context/LanguageContext'
import StepIndicator from '../components/layout/StepIndicator'

// Milestone 1 shell. Milestone 2 turns this into the Describe -> Clarify -> Route -> Draft -> Done wizard.
export default function NewComplaint() {
  const { t } = useLanguage()
  return (
    <div className="space-y-8">
      <StepIndicator current={0} />
      <header className="space-y-2">
        <h1 className="text-[1.6rem] font-bold sm:text-4xl">{t('describe.title')}</h1>
        <p className="text-lg text-muted">{t('describe.intro')}</p>
      </header>
    </div>
  )
}
