/** Friendly empty list: icon, message, optional next action. */
export default function EmptyState({ icon: Icon, title, hint, action }) {
  return (
    <div className="flex flex-col items-center gap-4 rounded-card border border-dashed border-line-strong bg-surface px-6 py-12 text-center">
      {Icon && (
        <span className="flex size-14 items-center justify-center rounded-full bg-surface-muted text-heading">
          <Icon className="size-7" aria-hidden="true" />
        </span>
      )}
      <div className="space-y-1">
        <p className="text-card font-bold text-heading">{title}</p>
        {hint && <p className="text-muted">{hint}</p>}
      </div>
      {action}
    </div>
  )
}
