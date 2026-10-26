import { Check } from 'lucide-react'
import { useLanguage } from '../../context/LanguageContext'

export const STEPS = ['describe', 'clarify', 'route', 'draft', 'done']

/** Wizard progress. `current` is an index into STEPS. */
export default function StepIndicator({ current }) {
  const { t } = useLanguage()

  return (
    <nav aria-label={t('step.progress')}>
      <p className="text-sm font-semibold text-muted md:sr-only">
        {t('step.label', { n: current + 1, total: STEPS.length })}
        <span aria-hidden="true"> · </span>
        <span className="text-ink">{t(`step.${STEPS[current]}`)}</span>
      </p>
      <ol className="mt-2 grid grid-cols-5 gap-1.5 md:mt-0 md:gap-3">
        {STEPS.map((step, i) => {
          const state = i < current ? 'done' : i === current ? 'current' : 'todo'
          return (
            <li key={step} aria-current={state === 'current' ? 'step' : undefined} className="min-w-0">
              <span
                className={`block h-1.5 rounded-full transition-colors duration-200 ${
                  { done: 'bg-primary', current: 'bg-accent', todo: 'bg-line' }[state]
                }`}
              />
              <span className="mt-2.5 hidden items-start gap-2 text-sm leading-snug md:flex">
                <span
                  className={`flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-bold ${
                    {
                      done: 'bg-primary text-white',
                      current: 'bg-primary-deep text-white',
                      todo: 'border border-line bg-surface text-muted',
                    }[state]
                  }`}
                >
                  {state === 'done' ? <Check className="size-3.5" strokeWidth={3} aria-hidden="true" /> : i + 1}
                </span>
                <span className={state === 'todo' ? 'text-muted' : 'font-semibold text-ink'}>{t(`step.${step}`)}</span>
              </span>
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
