/** Two-or-more option toggle (aria-pressed buttons). options: [{ value, label, lang }] */
export default function Segmented({ label, labelId, options, value, onChange, disabled = false }) {
  return (
    <div
      role="group"
      aria-label={labelId ? undefined : label}
      aria-labelledby={labelId}
      className="inline-flex rounded-control border-2 border-line-strong bg-surface p-0.5"
    >
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          lang={o.lang}
          aria-pressed={value === o.value}
          disabled={disabled}
          onClick={() => onChange(o.value)}
          className={`min-h-11 min-w-12 rounded-[10px] px-2.5 text-[0.9444rem] font-bold transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-55 sm:px-3 ${
            value === o.value ? 'bg-heading text-white' : 'text-muted hover:bg-primary-soft hover:text-heading'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}
