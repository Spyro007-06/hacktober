import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ClipboardList, MessageSquarePlus } from 'lucide-react'
import { escalateComplaint, listComplaints } from '../api/client'
import { useComplaint } from '../context/ComplaintContext'
import { useLanguage } from '../context/LanguageContext'
import ComplaintCard from '../components/ComplaintCard'
import Button from '../components/ui/Button'
import EmptyState from '../components/ui/EmptyState'
import ErrorBanner from '../components/ui/ErrorBanner'
import LoadingState from '../components/ui/LoadingState'
import PageHeading from '../components/ui/PageHeading'

// Overdue first, then fewest days left.
const byUrgency = (a, b) => (b.status === 'overdue') - (a.status === 'overdue') || (a.days_left ?? Infinity) - (b.days_left ?? Infinity)

export default function Complaints() {
  const { t } = useLanguage()
  const { openDraft } = useComplaint()
  const navigate = useNavigate()
  const [state, setState] = useState({ status: 'loading', items: [], error: null })
  const [escalating, setEscalating] = useState(null)
  const [escalateError, setEscalateError] = useState(null) // { error, id }
  const alive = useRef(true)
  useEffect(() => {
    alive.current = true // StrictMode remounts: reset after the simulated unmount
    return () => (alive.current = false)
  }, [])

  const load = useCallback(async () => {
    setState((s) => ({ ...s, status: 'loading', error: null }))
    try {
      const items = await listComplaints()
      if (alive.current) setState({ status: 'ready', items: [...items].sort(byUrgency), error: null })
    } catch (error) {
      if (alive.current) setState((s) => ({ ...s, status: 'error', error }))
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  async function escalate(id) {
    if (escalating) return
    setEscalating(id)
    setEscalateError(null)
    try {
      const draft = await escalateComplaint(id)
      if (!alive.current) return
      openDraft(draft)
      navigate('/')
    } catch (error) {
      if (alive.current) setEscalateError({ error, id })
    } finally {
      if (alive.current) setEscalating(null)
    }
  }

  return (
    <div className="space-y-8">
      <PageHeading title={t('complaints.title')} intro={t('complaints.intro')} />

      {state.status === 'loading' && <LoadingState label={t('complaints.loading')} />}

      {state.status === 'error' && <ErrorBanner error={state.error} onRetry={load} />}

      {state.status === 'ready' && state.items.length === 0 && (
        <EmptyState
          icon={ClipboardList}
          title={t('complaints.empty')}
          hint={t('complaints.emptyHint')}
          action={
            <Button icon={MessageSquarePlus} onClick={() => navigate('/')}>
              {t('nav.new')}
            </Button>
          }
        />
      )}

      {state.status === 'ready' && state.items.length > 0 && (
        <>
          <ErrorBanner error={escalateError?.error} onRetry={escalateError ? () => escalate(escalateError.id) : undefined} />
          {escalating && <LoadingState label={t('complaints.escalating')} />}
          <ul className="space-y-4">
            {state.items.map((c) => (
              <li key={c.id}>
                <ComplaintCard complaint={c} onEscalate={escalate} escalating={escalating === c.id} disabled={Boolean(escalating)} />
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}
