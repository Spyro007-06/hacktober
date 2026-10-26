/** "2026-11-25" -> "25 November 2026" / "25 நவம்பர், 2026" in the UI language (local date, no timezone shift). */
export function formatDate(iso, uiLang) {
  if (!iso) return ''
  return new Intl.DateTimeFormat(uiLang === 'ta' ? 'ta-IN' : 'en-IN', { dateStyle: 'long' }).format(new Date(`${iso}T00:00:00`))
}
