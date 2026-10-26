import { Check } from 'lucide-react'
import { useLanguage } from '../../context/LanguageContext'

export const STEPS = ['describe', 'clarify', 'route', 'draft', 'done']

// done: ink bar + check | current: turmeric bar + ringed number | upcoming: grey bar + outlined number.
// Position and the check mark carry progress too, so it never depends on colour alone.
const BAR = { done: 'bg-heading', current: 'bg-primary', todo: 'bg-line' }
const DOT = {
  done: 'bg-heading text-white',
  current: 'bg-primary text-heading ring-2 ring-heading ring-offset-2 ring-offset-background',
  todo: 'border-2 border-line-strong bg-surface text-muted',
}

/** Wizard progress. `current` is an index into STEPS. */
export default function StepIndicator({ current }) {
  const { t } = useLanguage()

  return (
    <nav aria-label={t('step.progress')}>
      <p className="text-support font-bold text-muted md:sr-only">
        {t('step.label', { n: current + 1, total: STEPS.length })}
        <span aria-hidden="true"> · </span>
        <span className="text-heading">{t(`step.${STEPS[current]}`)}</span>
      </p>
      <ol className="mt-2 grid grid-cols-5 gap-1.5 md:mt-0 md:gap-3">
        {STEPS.map((step, i) => {
          const state = i < current ? 'done' : i === current ? 'current' : 'todo'
          return (
            <li key={step} aria-current={state === 'current' ? 'step' : undefined} className="min-w-0">
              <span className={`block h-1.5 rounded-full transition-colors duration-200 ${BAR[state]}`} />
              {/* Number above label so long Tamil labels get the full column width. */}
              <span className="mt-2.5 hidden flex-col items-start gap-1.5 text-support leading-snug md:flex">
                <span className={`flex size-6 shrink-0 items-center justify-center rounded-full text-badge font-bold ${DOT[state]}`}>
                  {state === 'done' ? <Check className="size-3.5" strokeWidth={3} aria-hidden="true" /> : i + 1}
                </span>
                <span className={`max-w-full [overflow-wrap:anywhere] ${state === 'todo' ? 'text-muted' : 'font-bold text-heading'}`}>
                  {t(`step.${step}`)}
                </span>
                <span className="sr-only">{t(`step.state.${state}`)}</span>
              </span>
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
