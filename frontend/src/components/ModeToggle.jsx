import { useEffect, useId, useRef, useState } from 'react'
import { Wifi, WifiOff } from 'lucide-react'
import { errorKey, setMode } from '../api/client'
import { useLanguage } from '../context/LanguageContext'
import useHealth from '../hooks/useHealth'
import Segmented from './ui/Segmented'

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
 * Header service button: a status dot that opens a small panel with
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

  const mode = optimistic ?? health?.model_mode
  const dot = { checking: 'bg-muted/50', ready: 'bg-success', down: 'bg-danger' }[status]

  useEffect(() => {
    if (!open) return
    const close = (e) => {
      if (e.type === 'keydown' ? e.key === 'Escape' : !rootRef.current?.contains(e.target)) setOpen(false)
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
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        aria-label={`${t('service.panel')}: ${t(`service.${status}`)}${mode ? `, ${t(`mode.${mode}`)}` : ''}`}
        onClick={() => setOpen((v) => !v)}
        className="flex min-h-12 min-w-12 items-center justify-center gap-2 rounded-control px-2 text-sm text-muted transition-colors hover:bg-primary-soft hover:text-ink"
      >
        <span className="relative flex size-3">
          {status === 'ready' && <span className="absolute inset-0 rounded-full bg-success/30 motion-safe:animate-ping [animation-iteration-count:2]" />}
          <span className={`relative size-3 rounded-full ${dot}`} />
        </span>
        <span className="hidden lg:inline">{mode ? t(`mode.${mode}`) : t(`service.${status}`)}</span>
      </button>

      {open && (
        <div
          id={panelId}
          role="region"
          aria-label={t('service.panel')}
          className="absolute right-0 top-full z-30 mt-2 w-[min(20rem,calc(100vw-2rem))] space-y-4 rounded-card border border-line bg-surface p-4 shadow-lift"
        >
          <p role="status" className="flex items-center gap-2 font-semibold">
            <span className={`size-3 shrink-0 rounded-full ${dot}`} />
            {t(`service.${status}`)}
          </p>

          <div className="space-y-2">
            <p id={`${panelId}-mode`} className="text-sm font-semibold text-muted">
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
            {switching && <p className="text-sm text-muted">{t('mode.switching')}</p>}
            {error && (
              <p role="alert" className="rounded-control bg-warning-soft px-3 py-2 text-sm text-warning">
                {t(error)}
              </p>
            )}
            <p className="text-sm text-muted">{t('mode.help')}</p>
          </div>

          <p className="flex items-center gap-2 border-t border-line pt-3 text-sm">
            {netOnline ? <Wifi className="size-4 text-success" aria-hidden="true" /> : <WifiOff className="size-4 text-danger" aria-hidden="true" />}
            {t(netOnline ? 'net.online' : 'net.offline')}
          </p>
        </div>
      )}
    </div>
  )
}
