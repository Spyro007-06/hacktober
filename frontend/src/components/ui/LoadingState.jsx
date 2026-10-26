import { LoaderCircle } from 'lucide-react'

/** Honest wait indicator: a spinner and what is happening, no fake percentages. */
export default function LoadingState({ label }) {
  return (
    <div role="status" aria-live="polite" className="flex items-center gap-4 rounded-card border border-line bg-surface p-5 shadow-card">
      <span className="flex size-11 shrink-0 items-center justify-center rounded-full bg-primary-soft">
        <LoaderCircle className="size-6 animate-spin text-primary" aria-hidden="true" />
      </span>
      <p className="font-medium">{label}</p>
    </div>
  )
}
