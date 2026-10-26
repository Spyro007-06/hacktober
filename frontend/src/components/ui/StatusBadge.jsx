import { AlarmClock, ArrowUpRight, CircleCheck, Send } from 'lucide-react'
import { useLanguage } from '../../context/LanguageContext'

const STYLES = {
  filed: { icon: Send, className: 'bg-primary-soft text-primary-deep' },
  overdue: { icon: AlarmClock, className: 'bg-danger-soft text-danger' },
  resolved: { icon: CircleCheck, className: 'bg-success-soft text-success' },
  escalated: { icon: ArrowUpRight, className: 'bg-accent-soft text-accent-ink' },
}

/** Complaint status: filed | overdue | resolved | escalated. Icon + text, never colour alone. */
export default function StatusBadge({ status }) {
  const { t } = useLanguage()
  const { icon: Icon, className } = STYLES[status] ?? STYLES.filed
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-control px-2.5 py-1 text-sm font-semibold ${className}`}>
      <Icon className="size-4 shrink-0" aria-hidden="true" />
      {t(`status.${status}`)}
    </span>
  )
}
