import { LoaderCircle } from 'lucide-react'

/** Honest wait indicator: a spinner and what is happening, no fake percentages. */
export default function LoadingState({ label }) {
  return (
    <div role="status" aria-live="polite" className="flex items-center gap-4 rounded-card border border-line bg-surface p-4 shadow-card sm:p-5">
      <span className="flex size-11 shrink-0 items-center justify-center rounded-full bg-surface-muted">
        <LoaderCircle className="size-6 animate-spin text-heading" aria-hidden="true" />
      </span>
      <p className="font-semibold text-heading">{label}</p>
    </div>
  )
}
