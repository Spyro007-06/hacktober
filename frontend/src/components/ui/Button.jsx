import { LoaderCircle } from 'lucide-react'

const VARIANTS = {
  primary: 'bg-primary text-white shadow-card hover:bg-primary-deep',
  secondary: 'border-2 border-line bg-surface text-primary-deep hover:border-primary hover:bg-primary-soft',
  ghost: 'text-primary-deep hover:bg-primary-soft',
  danger: 'border-2 border-danger/30 bg-surface text-danger hover:bg-danger-soft',
}

const SIZES = {
  md: 'min-h-12 px-5 text-base',
  lg: 'min-h-14 w-full px-7 text-lg sm:w-auto',
}

/** `as="a"` renders a link styled as a button (e.g. PDF download). */
export default function Button({
  as: Comp = 'button',
  variant = 'primary',
  size = 'md',
  loading = false,
  icon: Icon,
  disabled,
  className = '',
  children,
  ...props
}) {
  return (
    <Comp
      {...(Comp === 'button' && { type: 'button', disabled: disabled || loading })}
      aria-busy={loading || undefined}
      className={`inline-flex select-none items-center justify-center gap-2.5 rounded-control font-semibold transition-[background-color,border-color,transform] duration-150 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-55 disabled:active:scale-100 ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
      {...props}
    >
      {loading ? (
        <LoaderCircle className="size-5 shrink-0 animate-spin" aria-hidden="true" />
      ) : (
        Icon && <Icon className="size-5 shrink-0" aria-hidden="true" />
      )}
      {children}
    </Comp>
  )
}
