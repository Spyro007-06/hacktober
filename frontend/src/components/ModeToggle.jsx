import { useEffect, useId, useRef, useState } from 'react'
import { CircleAlert, CircleCheck, LoaderCircle, Wifi, WifiOff } from 'lucide-react'
import { errorKey, setMode } from '../api/client'
import { useLanguage } from '../context/LanguageContext'
import useHealth from '../hooks/useHealth'
import Segmented from './ui/Segmented'
import Banner from './ui/Banner'

// Shape, not just colour: a check, an alert or a spinner.
function StatusIcon({ status, className }) {
  if (status === 'ready') return <CircleCheck className={`${className} text-success`} aria-hidden="true" />
  if (status === 'down') return <CircleAlert className={`${className} text-danger`} aria-hidden="true" />
  return <LoaderCircle className={`${className} animate-spin text-muted`} aria-hidden="true" />
}

function useNetworkOnline() {
  const [online, setOnline] = useState(navigator.onLine)
  useEffect(() => {
    const on = () => setOnline(true)
    const off = () => setOnline(false)
    window.addEventListener('online', on)
    window.addEventListener('offline', off)
    return () => {
      window.removeEventListener('online', on)
      window.removeEventListener('offline', off)
    }
  }, [])
  return online
}

/**
 * Header service button: a status icon that opens a small panel with
 * - Kural server status (GET /api/health),
 * - AI mode switch (PUT /api/config/mode; 503 reverts),
 * - internet connectivity, shown separately so "offline AI" is never mistaken for "no internet needed".
 */
export default function ModeToggle() {
  const { t } = useLanguage()
  const { status, health, setHealth } = useHealth()
  const netOnline = useNetworkOnline()
  const [open, setOpen] = useState(false)
  const [optimistic, setOptimistic] = useState(null)
  const [switching, setSwitching] = useState(false)
  const [error, setError] = useState(null)
  const panelId = useId()
  const rootRef = useRef(null)
  const triggerRef = useRef(null)

  const mode = optimistic ?? health?.model_mode

  useEffect(() => {
    if (!open) return
    const close = (e) => {
      if (e.type === 'keydown' && e.key === 'Escape') {
        setOpen(false)
        triggerRef.current?.focus()
      } else if (e.type !== 'keydown' && !rootRef.current?.contains(e.target)) setOpen(false)
    }
    document.addEventListener('pointerdown', close)
    document.addEventListener('keydown', close)
    return () => {
      document.removeEventListener('pointerdown', close)
      document.removeEventListener('keydown', close)
    }
  }, [open])

  async function change(next) {
    if (switching || next === mode) return
    setError(null)
    setOptimistic(next)
    setSwitching(true)
    try {
      setHealth(await setMode(next))
    } catch (err) {
      // Revert to the previous mode; 503 means the offline engine is not running.
      setError(err.status === 503 ? 'mode.switchFailed' : errorKey(err))
    } finally {
      setOptimistic(null)
      setSwitching(false)
    }
  }

  return (
    <div ref={rootRef} className="relative">
      <button
        ref={triggerRef}
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        aria-label={`${t('service.panel')}: ${t(`service.${status}`)}${mode ? `, ${t(`mode.${mode}`)}` : ''}`}
        onClick={() => setOpen((v) => !v)}
        className="flex min-h-12 min-w-12 items-center justify-center gap-2 rounded-control border border-line bg-surface px-3 text-support text-muted transition-colors hover:bg-primary-soft hover:text-heading"
      >
        <StatusIcon status={status} className="size-5 shrink-0" />
        <span className="hidden font-bold text-heading md:inline">{mode ? t(`mode.${mode}`) : t(`service.${status}`)}</span>
      </button>

      {open && (
        <div
          id={panelId}
          role="region"
          aria-label={t('service.panel')}
          className="absolute right-0 top-full z-30 mt-2 w-[min(20rem,calc(100vw-2rem))] space-y-4 rounded-card border border-line bg-surface p-4 shadow-lift"
        >
          <p role="status" className="flex items-center gap-2 font-semibold">
            <StatusIcon status={status} className="size-5 shrink-0" />
            {t(`service.${status}`)}
          </p>

          <div className="space-y-2">
            <p id={`${panelId}-mode`} className="text-support font-semibold text-muted">
              {t('mode.title')}
            </p>
            <Segmented
              labelId={`${panelId}-mode`}
              value={mode}
              onChange={change}
              disabled={switching || status !== 'ready'}
              options={[
                { value: 'online', label: t('mode.online') },
                { value: 'offline', label: t('mode.offline') },
              ]}
            />
            {switching && <p className="text-support text-muted">{t('mode.switching')}</p>}
            {error && (
              <Banner tone="warning" compact>
                {t(error)}
              </Banner>
            )}
            <p className="text-support text-muted">{t('mode.help')}</p>
          </div>

          <p className="flex items-center gap-2 border-t border-line pt-3 text-support">
            {netOnline ? <Wifi className="size-4 text-success" aria-hidden="true" /> : <WifiOff className="size-4 text-danger" aria-hidden="true" />}
            {t(netOnline ? 'net.online' : 'net.offline')}
          </p>
        </div>
      )}
    </div>
  )
}
