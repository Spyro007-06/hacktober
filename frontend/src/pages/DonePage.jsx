import { motion } from 'framer-motion'
import { Check, ClipboardList, MessageSquarePlus } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useComplaint } from '../context/ComplaintContext'
import { useLanguage } from '../context/LanguageContext'
import Button from '../components/ui/Button'
import PageHeading from '../components/ui/PageHeading'
import { formatDate } from '../utils/format'

export default function DonePage({ focusHeading }) {
  const { t, uiLang } = useLanguage()
  const { filed, draft, startOver } = useComplaint()
  const navigate = useNavigate()

  const due = formatDate(filed?.due_on, uiLang)
  const steps = draft?.next_steps?.[uiLang]

  return (
    <div className="space-y-8">
      <div className="flex flex-col items-start gap-5">
        <motion.span
          initial={{ scale: 0.6, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ type: 'spring', stiffness: 260, damping: 18 }}
          className="flex size-16 items-center justify-center rounded-full bg-success text-white shadow-lift"
        >
          <Check className="size-9" strokeWidth={3} aria-hidden="true" />
        </motion.span>
        <PageHeading title={t('done.title')} intro={t('done.intro')} focus={focusHeading} />
      </div>

      {(filed?.id || due) && (
        <dl className="grid gap-px overflow-hidden rounded-card border border-line bg-line sm:grid-cols-2">
          {filed?.id && (
            <div className="bg-surface p-5">
              <dt className="text-sm font-semibold text-muted">{t('done.referenceLabel')}</dt>
              <dd className="mt-1 text-xl font-bold tabular-nums">{filed.id}</dd>
            </div>
          )}
          {due && (
            <div className="bg-surface p-5">
              <dt className="text-sm font-semibold text-muted">{t('done.dueLabel')}</dt>
              <dd className="mt-1 text-xl font-bold">{due}</dd>
            </div>
          )}
        </dl>
      )}

      {steps && (
        <section aria-labelledby="done-next" className="rounded-card border border-line bg-surface p-5 shadow-card">
          <h2 id="done-next" className="text-lg font-bold">
            {t('nextSteps.title')}
          </h2>
          <p className="mt-2" lang={uiLang}>
            {steps}
          </p>
        </section>
      )}

      <div className="flex flex-col gap-3 sm:flex-row">
        <Button size="lg" icon={MessageSquarePlus} onClick={startOver}>
          {t('done.another')}
        </Button>
        <Button
          size="lg"
          variant="secondary"
          icon={ClipboardList}
          onClick={() => {
            startOver()
            navigate('/complaints')
          }}
        >
          {t('btn.viewComplaints')}
        </Button>
      </div>
    </div>
  )
}
