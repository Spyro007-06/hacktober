import { ArrowRight } from 'lucide-react'
import { useComplaint } from '../context/ComplaintContext'
import { useLanguage } from '../context/LanguageContext'
import Recorder from '../components/Recorder'
import PhotoUpload from '../components/PhotoUpload'
import FlowError from '../components/FlowError'
import Button from '../components/ui/Button'
import LoadingState from '../components/ui/LoadingState'
import PageHeading from '../components/ui/PageHeading'
import { Textarea } from '../components/ui/Field'

export default function DescribePage({ focusHeading }) {
  const { t } = useLanguage()
  const { text, setText, complaintLang, clips, pending, submitDescribe } = useComplaint()

  const transcribing = clips.some((c) => c.status === 'transcribing')
  const blockedReason = !text.trim() ? t('describe.needText') : transcribing ? t('describe.waitTranscribing') : null
  const submitting = pending === 'session'

  return (
    <div className="space-y-8">
      <PageHeading title={t('describe.title')} intro={t('describe.intro')} focus={focusHeading} />

      <Recorder />

      <Textarea
        label={t('text.label')}
        hint={t('text.hint')}
        required
        rows={6}
        lang={complaintLang}
        placeholder={t('text.placeholder')}
        value={text}
        onChange={(e) => setText(e.target.value)}
        disabled={submitting}
      />

      <PhotoUpload />

      <div className="space-y-4 border-t border-line pt-6">
        <FlowError />
        {submitting && <LoadingState label={t('loading.understanding')} />}
        <Button size="lg" icon={ArrowRight} onClick={submitDescribe} disabled={Boolean(blockedReason)} loading={submitting} aria-describedby={blockedReason ? 'continue-why' : undefined} className="flex-row-reverse">
          {t('btn.continue')}
        </Button>
        {blockedReason && (
          <p id="continue-why" className="text-muted">
            {blockedReason}
          </p>
        )}
      </div>
    </div>
  )
}
