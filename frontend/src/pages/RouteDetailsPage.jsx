import { useState } from 'react'
import { ArrowLeft, FileText } from 'lucide-react'
import { useComplaint } from '../context/ComplaintContext'
import { useLanguage } from '../context/LanguageContext'
import RouteBadge from '../components/RouteBadge'
import ComplainantForm, { validateComplainant } from '../components/ComplainantForm'
import FlowError from '../components/FlowError'
import Button from '../components/ui/Button'
import LoadingState from '../components/ui/LoadingState'
import PageHeading from '../components/ui/PageHeading'

export default function RouteDetailsPage({ focusHeading }) {
  const { t, uiLang } = useLanguage()
  const { session, complainant, setComplainant, routeOverride, setRouteOverride, generateDraft, backToDescribe, pending, error } =
    useComplaint()
  const [errors, setErrors] = useState({})
  const busy = pending === 'draft'

  function onSubmit(e) {
    e.preventDefault()
    const found = validateComplainant(complainant)
    setErrors(found)
    const first = Object.keys(found)[0]
    if (first) return document.querySelector(`[data-field="${first}"]`)?.focus()
    generateDraft()
  }

  return (
    <form className="space-y-8" onSubmit={onSubmit} noValidate>
      <PageHeading title={t('route.title')} focus={focusHeading} />

      <RouteBadge
        decision={session?.decision}
        uiLang={uiLang}
        override={routeOverride}
        onOverride={setRouteOverride}
        disabled={busy}
        openOverride={error?.code === 'NO_DEPARTMENT'}
      />

      <section aria-labelledby="form-title" className="space-y-4">
        <div>
          <h2 id="form-title" className="text-xl font-bold">
            {t('form.title')}
          </h2>
          <p className="mt-1 text-muted">{t('form.intro')}</p>
        </div>
        <ComplainantForm
          value={complainant}
          onChange={(patch) => {
            setComplainant(patch)
            setErrors((prev) => Object.fromEntries(Object.entries(prev).filter(([k]) => !(k in patch))))
          }}
          errors={errors}
          disabled={busy}
        />
      </section>

      <div className="space-y-4 border-t border-line pt-6">
        <FlowError />
        {busy && <LoadingState label={t('loading.drafting')} />}
        <div className="flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-between">
          <Button variant="ghost" icon={ArrowLeft} onClick={() => backToDescribe()} disabled={busy}>
            {t('btn.back')}
          </Button>
          <Button type="submit" size="lg" icon={FileText} loading={busy}>
            {t('btn.generate')}
          </Button>
        </div>
      </div>
    </form>
  )
}
