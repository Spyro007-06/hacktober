import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Check, Copy } from 'lucide-react'
import { useLanguage } from '../context/LanguageContext'
import Banner from './ui/Banner'

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    // Clipboard API needs a secure context and permission; fall back to the legacy copy command.
  }
  try {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.setAttribute('readonly', '')
    ta.style.cssText = 'position:fixed;opacity:0'
    document.body.appendChild(ta)
    ta.select()
    const ok = document.execCommand('copy')
    ta.remove()
    return ok
  } catch {
    return false
  }
}

/** Every backend portal field with a one-tap Copy button and a 2-second "Copied" state. */
export default function PortalFields({ fields }) {
  const { t } = useLanguage()
  const [copied, setCopied] = useState(null)
  const [failed, setFailed] = useState(null)
  const timer = useRef(null)
  const valueRefs = useRef({})
  useEffect(() => () => clearTimeout(timer.current), [])

  async function copy(label, value) {
    clearTimeout(timer.current)
    if (await copyText(value)) {
      setFailed(null)
      setCopied(label)
      timer.current = setTimeout(() => setCopied(null), 2000)
    } else {
      // Select the value so the user can copy it by hand.
      setCopied(null)
      setFailed(label)
      const range = document.createRange()
      range.selectNodeContents(valueRefs.current[label])
      window.getSelection().removeAllRanges()
      window.getSelection().addRange(range)
    }
  }

  return (
    <section aria-labelledby="portal-title" className="space-y-4">
      <div>
        <h2 id="portal-title" className="text-section font-bold">
          {t('portal.title')}
        </h2>
        <p className="mt-1 text-muted">{t('portal.intro')}</p>
      </div>
      <dl className="divide-y divide-line overflow-hidden rounded-card border border-line bg-surface shadow-card">
        {Object.entries(fields).map(([label, value]) => {
          const isCopied = copied === label
          return (
            <div key={label} className="flex flex-col gap-3 p-4 sm:flex-row sm:items-start sm:gap-4 sm:p-5">
              <div className="min-w-0 flex-1">
                <dt className="text-support font-semibold text-muted">{label}</dt>
                <dd ref={(el) => (valueRefs.current[label] = el)} className="mt-1 whitespace-pre-wrap break-words">
                  {value || '—'}
                </dd>
                {failed === label && (
                  <Banner tone="warning" compact className="mt-2">
                    {t('portal.copyFailed')}
                  </Banner>
                )}
              </div>
              <button
                type="button"
                onClick={() => copy(label, String(value ?? ''))}
                disabled={!value}
                aria-label={isCopied ? t('btn.copied') : t('portal.copyLabel', { field: label })}
                className={`inline-flex min-h-12 min-w-[7.5rem] shrink-0 items-center justify-center gap-2 rounded-control border-2 px-4 font-semibold transition-colors duration-150 disabled:opacity-40 ${
                  isCopied ? 'border-success bg-success-soft text-success' : 'border-line bg-surface text-heading hover:border-heading hover:bg-primary-soft'
                }`}
              >
                <AnimatePresence mode="wait" initial={false}>
                  <motion.span
                    key={isCopied ? 'done' : 'copy'}
                    initial={{ opacity: 0, scale: 0.8 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.8 }}
                    transition={{ duration: 0.15 }}
                    className="inline-flex items-center gap-2"
                  >
                    {isCopied ? <Check className="size-5" strokeWidth={3} aria-hidden="true" /> : <Copy className="size-5" aria-hidden="true" />}
                    {isCopied ? t('btn.copied') : t('btn.copy')}
                  </motion.span>
                </AnimatePresence>
              </button>
            </div>
          )
        })}
      </dl>
      <p className="sr-only" aria-live="polite">
        {copied ? t('btn.copied') : ''}
      </p>
    </section>
  )
}
