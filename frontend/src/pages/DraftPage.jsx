import { useState } from 'react'
import { ArrowLeft, ClipboardCheck, Download, Landmark } from 'lucide-react'
import { fetchPdf } from '../api/client'
import { useComplaint } from '../context/ComplaintContext'
import { useLanguage } from '../context/LanguageContext'
import DraftPreview from '../components/DraftPreview'
import PortalFields from '../components/PortalFields'
import NextSteps from '../components/NextSteps'
import FlowError from '../components/FlowError'
import Button from '../components/ui/Button'
import ErrorBanner from '../components/ui/ErrorBanner'
import LoadingState from '../components/ui/LoadingState'
import PageHeading from '../components/ui/PageHeading'

export default function DraftPage({ focusHeading }) {
  const { t, uiLang } = useLanguage()
  const { draft, session, complainant, saveDraft, markFiled, backToRoute, pending } = useComplaint()
  const fromWizard = Boolean(session) // false for an escalation draft opened from My complaints
  const dept = draft.department
  const route = draft.route ?? draft.decision?.route // the effective route (the operator's override if set)
  const filing = pending === 'file'
  const [pdf, setPdf] = useState({ busy: false, error: null })
  const hasPortalFields = Object.keys(draft.portal_fields ?? {}).length > 0

  async function downloadPdf() {
    setPdf({ busy: true, error: null })
    try {
      const url = URL.createObjectURL(await fetchPdf(draft.draft_id))
      const a = Object.assign(document.createElement('a'), { href: url, download: `kural_${route}_${draft.draft_id}.pdf` })
      a.click()
      URL.revokeObjectURL(url)
      setPdf({ busy: false, error: null })
    } catch (error) {
      setPdf({ busy: false, error })
    }
  }

  return (
    <div className="space-y-10">
      <PageHeading title={t('draft.title')} intro={t('draft.intro')} focus={focusHeading} />

      {dept && (
        <section aria-label={t('draft.sendTo')} className="flex gap-4 rounded-card border border-line bg-surface p-5 shadow-card sm:p-6">
          <span className="flex size-12 shrink-0 items-center justify-center rounded-control bg-surface-muted text-heading">
            <Landmark className="size-6" aria-hidden="true" />
          </span>
          <div className="min-w-0 space-y-1">
            <p className="text-support font-semibold text-muted">
              {t('draft.sendTo')} · {t(`route.${route}`)}
            </p>
            <p className="text-lg font-semibold">{dept.name}</p>
            {dept.address && <p className="text-muted">{dept.address}</p>}
            {dept.submit_via && (
              <p>
                <span className="font-semibold">{t('draft.submitVia')}:</span> {dept.submit_via}
              </p>
            )}
            {dept.response_days && <p className="text-muted">{t('draft.replyIn', { n: dept.response_days })}</p>}
          </div>
        </section>
      )}

      <div className="space-y-4">
        <DraftPreview
          draft={draft}
          complainant={complainant}
          onSave={saveDraft}
          saving={pending === 'save'}
          error={<FlowError from="save" />}
          editPerson={fromWizard}
        />
        {pdf.error && <ErrorBanner error={pdf.error} onRetry={downloadPdf} />}
        <Button size="lg" icon={Download} onClick={downloadPdf} loading={pdf.busy}>
          {t('btn.download')}
        </Button>
      </div>

      {hasPortalFields && <PortalFields fields={draft.portal_fields} />}

      {draft.next_steps && <NextSteps nextSteps={draft.next_steps} uiLang={uiLang} />}

      <section aria-labelledby="file-title" className="space-y-4 rounded-card bg-heading p-5 text-white sm:p-7">
        <h2 id="file-title" className="text-card font-bold text-white">
          {t('filed.title')}
        </h2>
        <p className="text-white/85">{t('filed.explain')}</p>
        <FlowError from="file" />
        {filing && <LoadingState label={t('loading.filing')} />}
        <Button
          size="lg"
          icon={ClipboardCheck}
          onClick={markFiled}
          loading={filing}
          disabled={Boolean(pending)}
          className="focus-visible:outline-white"
        >
          {t('btn.markFiled')}
        </Button>
      </section>

      {fromWizard && (
        <Button variant="ghost" icon={ArrowLeft} onClick={backToRoute} disabled={Boolean(pending)}>
          {t('btn.back')}
        </Button>
      )}
    </div>
  )
}
