import { useId } from 'react'
import { CircleAlert } from 'lucide-react'
import { useLanguage } from '../../context/LanguageContext'

const CONTROL =
  'block w-full rounded-control border-2 border-line bg-surface px-4 text-ink placeholder:text-muted/80 transition-colors hover:border-muted/40 focus:border-primary focus:outline-none focus:ring-4 focus:ring-primary/20 aria-[invalid=true]:border-danger'

// Label, required/optional marker, hint and error wired to the control via aria attributes.
function Field({ label, hint, error, required, children }) {
  const id = useId()
  const { t } = useLanguage()
  const hintId = hint ? `${id}-hint` : undefined
  const errorId = error ? `${id}-error` : undefined

  return (
    <div className="space-y-2">
      <label htmlFor={id} className="flex flex-wrap items-baseline justify-between gap-x-3 font-semibold">
        <span>{label}</span>
        <span className="text-sm font-normal text-muted">{required ? t('form.required') : t('form.optional')}</span>
      </label>
      {hint && (
        <p id={hintId} className="text-sm text-muted">
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
        <p id={errorId} className="flex items-center gap-2 text-sm font-medium text-danger">
          <CircleAlert className="size-4 shrink-0" aria-hidden="true" />
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
      {(a11y) => <textarea {...a11y} rows={rows} {...props} className={`${CONTROL} resize-y py-3 ${className}`} />}
    </Field>
  )
}
