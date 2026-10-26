import { useId } from 'react'
import { CircleAlert } from 'lucide-react'
import { useLanguage } from '../../context/LanguageContext'

// Edge uses border-line-strong (3:1) so the control is findable; focus/invalid/disabled each read differently.
const CONTROL =
  'block w-full rounded-control border-2 border-line-strong bg-surface px-4 text-text placeholder:text-muted transition-[border-color,box-shadow] duration-150 hover:border-heading/60 focus:border-heading focus:outline-none focus:ring-4 focus:ring-primary/50 aria-[invalid=true]:border-danger aria-[invalid=true]:focus:ring-danger/20 disabled:cursor-not-allowed disabled:border-line disabled:bg-surface-muted disabled:text-muted'

// Label, required/optional marker, hint and error wired to the control via aria attributes.
// The error row only appears when needed and sits below the control, so the label never jumps.
function Field({ label, hint, error, required, children }) {
  const id = useId()
  const { t } = useLanguage()
  const hintId = hint ? `${id}-hint` : undefined
  const errorId = error ? `${id}-error` : undefined

  return (
    <div className="space-y-2">
      <label htmlFor={id} className="flex flex-wrap items-baseline justify-between gap-x-3 text-label font-bold text-heading">
        <span>{label}</span>
        <span className="text-support font-semibold text-muted">{required ? t('form.required') : t('form.optional')}</span>
      </label>
      {hint && (
        <p id={hintId} className="text-support text-muted">
          {hint}
        </p>
      )}
      {children({
        id,
        required,
        'aria-invalid': error ? true : undefined,
        'aria-describedby': [hintId, errorId].filter(Boolean).join(' ') || undefined,
      })}
      {error && (
        <p id={errorId} className="flex items-start gap-2 text-support font-semibold text-danger">
          <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          {error}
        </p>
      )}
    </div>
  )
}

export function Input({ label, hint, error, required, className = '', ...props }) {
  return (
    <Field label={label} hint={hint} error={error} required={required}>
      {(a11y) => <input {...a11y} {...props} className={`${CONTROL} min-h-14 ${className}`} />}
    </Field>
  )
}

export function Textarea({ label, hint, error, required, rows = 5, className = '', ...props }) {
  return (
    <Field label={label} hint={hint} error={error} required={required}>
      {(a11y) => <textarea {...a11y} rows={rows} {...props} className={`${CONTROL} resize-y py-3 leading-relaxed ${className}`} />}
    </Field>
  )
}
