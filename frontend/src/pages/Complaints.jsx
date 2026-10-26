import { useLanguage } from '../context/LanguageContext'

// P1 tracker. Milestone 4 adds the list, status badges and escalation.
export default function Complaints() {
  const { t } = useLanguage()
  return (
    <header className="space-y-2">
      <h1 className="text-[1.6rem] font-bold sm:text-4xl">{t('complaints.title')}</h1>
    </header>
  )
}
