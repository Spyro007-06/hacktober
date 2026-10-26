import { useEffect, useId, useState } from 'react'
import { Building2, ChevronDown, FileSearch, Headset } from 'lucide-react'
import { useLanguage } from '../context/LanguageContext'
import Banner from './ui/Banner'

export const ROUTES = ['local_body', 'cm_helpline', 'rti']
const ICONS = { local_body: Building2, cm_helpline: Headset, rti: FileSearch }

/**
 * Backend route decision: route name, rule id, reason, escalation, plus the operator override.
 * The override is never applied silently: it is shown next to the recommendation.
 */
export default function RouteBadge({ decision, uiLang, override, onOverride, disabled, openOverride = false }) {
  const { t } = useLanguage()
  const selectId = useId()
  const [showOverride, setShowOverride] = useState(Boolean(override) || openOverride)
  useEffect(() => {
    if (openOverride) setShowOverride(true)
  }, [openOverride])

  if (!decision) return null
  const route = override ?? decision.route
  const Icon = ICONS[route] ?? Building2
  const reason = uiLang === 'ta' ? decision.reason_ta : decision.reason_en

  return (
    <section aria-labelledby="route-name" className="overflow-hidden rounded-card border border-line bg-surface shadow-card">
      <div className="flex gap-4 p-5 sm:p-6">
        <span className="flex size-14 shrink-0 items-center justify-center rounded-control bg-surface-muted text-heading">
          <Icon className="size-7" aria-hidden="true" />
        </span>
        <div className="min-w-0 space-y-2">
          <p className="text-support font-semibold text-muted">{override ? t('route.chosenByOperator') : t('route.recommended')}</p>
          <h2 id="route-name" className="text-section font-bold text-heading">
            {t(`route.${route}`)}
          </h2>
          <div className="flex flex-wrap gap-2 text-support">
            <span className="rounded-control border border-line bg-background px-2.5 py-0.5 font-semibold">
              {t('route.rule')} {decision.rule_id}
            </span>
            {decision.escalation_level > 0 && (
              <span className="rounded-control border border-primary bg-primary-soft px-2.5 py-0.5 font-bold text-primary-ink">
                {t('route.escalation', { n: decision.escalation_level })}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Where this route sits among the three: the chosen one is filled. */}
      <ol aria-label={t('route.steps')} className="grid grid-cols-3 gap-px border-y border-line bg-line text-center text-support">
        {ROUTES.map((r) => (
          <li
            key={r}
            aria-current={r === route ? 'true' : undefined}
            className={`px-2 py-2.5 leading-snug ${r === route ? 'bg-heading font-bold text-white' : 'bg-surface text-muted'}`}
          >
            {t(`route.${r}`)}
          </li>
        ))}
      </ol>

      <div className="space-y-4 p-5 sm:p-6">
        {reason && (
          <div>
            <p className="text-support font-semibold text-muted">{t('route.reason')}</p>
            <p className="text-lg">{reason}</p>
          </div>
        )}
        {override && override !== decision.route && (
          <Banner tone="warning" compact>
            {t('route.overridden', { route: t(`route.${decision.route}`) })}
          </Banner>
        )}

        <div className="border-t border-line pt-4">
          <button
            type="button"
            aria-expanded={showOverride}
            aria-controls={selectId}
            onClick={() => setShowOverride((v) => !v)}
            className="flex min-h-12 items-center gap-2 rounded-control font-semibold text-heading"
          >
            {t('route.override')}
            <ChevronDown className={`size-5 transition-transform duration-200 ${showOverride ? 'rotate-180' : ''}`} aria-hidden="true" />
          </button>
          {showOverride && (
            <select
              id={selectId}
              aria-label={t('route.override')}
              value={override ?? ''}
              disabled={disabled}
              onChange={(e) => onOverride(e.target.value || null)}
              className="mt-2 block min-h-14 w-full rounded-control border-2 border-line-strong bg-surface px-4 text-text hover:border-heading/60 focus:border-heading focus:outline-none focus:ring-4 focus:ring-primary/50 sm:max-w-md"
            >
              <option value="">{t('route.overrideNone', { route: t(`route.${decision.route}`) })}</option>
              {ROUTES.map((r) => (
                <option key={r} value={r}>
                  {t(`route.${r}`)}
                </option>
              ))}
            </select>
          )}
        </div>
      </div>
    </section>
  )
}
