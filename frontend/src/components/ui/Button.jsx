import { LoaderCircle } from 'lucide-react'

// primary: turmeric with an ink label (the one action per screen) | secondary: bordered | ghost: low priority | danger: risky only
const VARIANTS = {
  primary: 'border-2 border-transparent bg-primary text-heading shadow-card hover:bg-primary-hover active:bg-primary-hover',
  secondary: 'border-2 border-line-strong bg-surface text-heading hover:border-heading hover:bg-primary-soft active:bg-primary-soft',
  ghost: 'border-2 border-transparent text-heading hover:bg-primary-soft active:bg-primary-soft',
  danger: 'border-2 border-danger bg-surface text-danger hover:bg-danger-soft active:bg-danger-soft',
}

const SIZES = {
  md: 'min-h-12 px-5',
  lg: 'min-h-14 w-full px-7 sm:w-auto',
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
      className={`inline-flex select-none items-center justify-center gap-2.5 rounded-control text-[0.9444rem] font-bold transition-[background-color,border-color,color,transform] duration-150 ease-out active:scale-[0.98] disabled:cursor-not-allowed disabled:border-line disabled:bg-surface-muted disabled:text-muted disabled:shadow-none disabled:active:scale-100 ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
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
