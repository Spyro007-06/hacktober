import { AlarmClock, ArrowUpRight, CircleCheck, Send } from 'lucide-react'
import { useLanguage } from '../../context/LanguageContext'

// Each status has its own icon and wording as well as colour, so none relies on colour alone.
const STYLES = {
  filed: { icon: Send, className: 'border-info/25 bg-info-soft text-info' },
  overdue: { icon: AlarmClock, className: 'border-danger/25 bg-danger-soft text-danger' },
  resolved: { icon: CircleCheck, className: 'border-success/25 bg-success-soft text-success' },
  escalated: { icon: ArrowUpRight, className: 'border-primary bg-primary-soft text-primary-ink' },
}

/** Complaint status: filed | overdue | resolved | escalated. */
export default function StatusBadge({ status }) {
  const { t } = useLanguage()
  const { icon: Icon, className } = STYLES[status] ?? STYLES.filed
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-control border px-2.5 py-1 text-badge font-bold ${className}`}>
      <Icon className="size-4 shrink-0" aria-hidden="true" />
      {t(`status.${status}`)}
    </span>
  )
}
