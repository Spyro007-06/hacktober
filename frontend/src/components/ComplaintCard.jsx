import { ArrowUpRight } from 'lucide-react'
import { useLanguage } from '../context/LanguageContext'
import { formatDate } from '../utils/format'
import StatusBadge from './ui/StatusBadge'
import Button from './ui/Button'

function daysText(t, c) {
  if (c.status === 'resolved' || c.status === 'escalated' || c.days_left == null) return null
  if (c.days_left < 0) return t('complaints.daysOverdue', { n: Math.abs(c.days_left) })
  if (c.days_left === 0) return t('complaints.dueToday')
  return t('complaints.daysLeft', { n: c.days_left })
}

/** One tracked complaint. Escalate only appears for overdue complaints. */
export default function ComplaintCard({ complaint: c, onEscalate, escalating, disabled }) {
  const { t, uiLang } = useLanguage()
  const overdue = c.status === 'overdue'
  const days = daysText(t, c)

  return (
    <article
      aria-labelledby={`c-${c.id}`}
      className={`space-y-4 rounded-card border bg-surface p-5 shadow-card ${overdue ? 'border-danger/30' : 'border-line'}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <h2 id={`c-${c.id}`} className="text-card font-bold">
            {c.title}
          </h2>
          {c.route && <p className="text-support text-muted">{t(`route.${c.route}`)}</p>}
        </div>
        <StatusBadge status={c.status} />
      </div>

      <dl className="grid grid-cols-2 gap-3 text-support sm:grid-cols-3">
        <div>
          <dt className="text-muted">{t('complaints.filedOn')}</dt>
          <dd className="font-semibold">{formatDate(c.filed_on, uiLang)}</dd>
        </div>
        <div>
          <dt className="text-muted">{t('complaints.dueOn')}</dt>
          <dd className="font-semibold">{formatDate(c.due_on, uiLang)}</dd>
        </div>
        {days && (
          <div className="col-span-2 sm:col-span-1">
            <dt className="sr-only">{t('complaints.daysLabel')}</dt>
            <dd className={`text-base font-bold ${overdue ? 'text-danger' : 'text-heading'}`}>{days}</dd>
          </div>
        )}
      </dl>

      {overdue && (
        <div className="flex flex-col gap-3 border-t border-line pt-4 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-muted">{t('complaints.escalateHint')}</p>
          <Button icon={ArrowUpRight} onClick={() => onEscalate(c.id)} loading={escalating} disabled={disabled}>
            {t('btn.escalate')}
          </Button>
        </div>
      )}
    </article>
  )
}
