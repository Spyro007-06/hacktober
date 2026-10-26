import { CircleAlert, CircleCheck, Info, TriangleAlert } from 'lucide-react'

// One look for every message box. Meaning is carried by the icon and the text, never by colour alone.
const TONES = {
  error: { icon: CircleAlert, box: 'border-danger/30 bg-danger-soft', icon_: 'text-danger', role: 'alert' },
  warning: { icon: TriangleAlert, box: 'border-warning/30 bg-warning-soft', icon_: 'text-warning', role: 'alert' },
  success: { icon: CircleCheck, box: 'border-success/30 bg-success-soft', icon_: 'text-success', role: 'status' },
  info: { icon: Info, box: 'border-info/30 bg-info-soft', icon_: 'text-info', role: 'status' },
}

/** Message box. `compact` is for inline notices inside a card; `children` can carry actions. */
export default function Banner({ tone = 'info', compact = false, role, className = '', children, ...props }) {
  const { icon: Icon, box, icon_, role: defaultRole } = TONES[tone]
  return (
    <div
      role={role ?? defaultRole}
      className={`flex gap-3 rounded-control border text-text ${box} ${compact ? 'px-3.5 py-3 text-support' : 'p-4 sm:gap-4 sm:p-5'} ${className}`}
      {...props}
    >
      <Icon className={`shrink-0 ${compact ? 'mt-0.5 size-5' : 'mt-0.5 size-6'} ${icon_}`} aria-hidden="true" />
      <div className="min-w-0 flex-1 space-y-3">{children}</div>
    </div>
  )
}
