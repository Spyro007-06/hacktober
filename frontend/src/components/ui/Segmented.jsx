/** Two-or-more option toggle (aria-pressed buttons). options: [{ value, label, lang }] */
export default function Segmented({ label, labelId, options, value, onChange, disabled = false }) {
  return (
    <div
      role="group"
      aria-label={labelId ? undefined : label}
      aria-labelledby={labelId}
      className="inline-flex rounded-control border-2 border-line bg-surface p-1"
    >
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          lang={o.lang}
          aria-pressed={value === o.value}
          disabled={disabled}
          onClick={() => onChange(o.value)}
          className={`min-h-11 min-w-12 rounded-[10px] px-2.5 text-base font-semibold transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-55 sm:px-3 ${
            value === o.value ? 'bg-primary text-white' : 'text-muted hover:bg-primary-soft hover:text-primary-deep'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}
