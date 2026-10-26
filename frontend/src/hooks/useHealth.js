import { useCallback, useEffect, useState } from 'react'
import { health } from '../api/client'

/**
 * Checks GET /api/health on mount, then every 30 s while the tab is visible.
 * status: checking | ready | down. setHealth() applies a response from PUT /config/mode.
 */
export default function useHealth(intervalMs = 30000) {
  const [state, setState] = useState({ status: 'checking', health: null })

  useEffect(() => {
    let alive = true
    const check = () =>
      health().then(
        (h) => alive && setState({ status: 'ready', health: h }),
        () => alive && setState((s) => ({ ...s, status: 'down' })),
      )
    check()
    const id = setInterval(() => !document.hidden && check(), intervalMs)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [intervalMs])

  const setHealth = useCallback((h) => setState({ status: 'ready', health: h }), [])
  return { ...state, setHealth }
}
