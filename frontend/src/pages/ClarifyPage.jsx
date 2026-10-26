import { ArrowLeft, ArrowRight, CircleHelp, RotateCcw } from 'lucide-react'
import { useComplaint } from '../context/ComplaintContext'
import { useLanguage } from '../context/LanguageContext'
import FollowUpQuestions from '../components/FollowUpQuestions'
import PhotoMismatchAlert from '../components/PhotoMismatchAlert'
import FlowError from '../components/FlowError'
import Button from '../components/ui/Button'
import LoadingState from '../components/ui/LoadingState'
import PageHeading from '../components/ui/PageHeading'

function BackButton() {
  const { t } = useLanguage()
  const { backToDescribe, pending } = useComplaint()
  return (
    <Button variant="ghost" icon={ArrowLeft} onClick={() => backToDescribe()} disabled={Boolean(pending)}>
      {t('btn.back')}
    </Button>
  )
}

function NeedsInfo({ focusHeading }) {
  const { t, uiLang } = useLanguage()
  const { session, answers, setAnswer, submitAnswers, pending, rounds, complaintLang } = useComplaint()
  const busy = pending === 'answers'

  return (
    <form
      className="space-y-8"
      onSubmit={(e) => {
        e.preventDefault()
        submitAnswers()
      }}
    >
      <div className="space-y-3">
        <p className="inline-flex rounded-control border border-primary bg-primary-soft px-3 py-1 text-support font-bold text-primary-ink">
          {t('clarify.round', { n: Math.min(rounds + 1, 2) })}
        </p>
        <PageHeading title={t('clarify.title')} intro={t('clarify.intro')} focus={focusHeading} />
      </div>

      <FollowUpQuestions
        questions={session.follow_up_questions}
        uiLang={uiLang}
        complaintLang={complaintLang}
        answers={answers}
        onChange={setAnswer}
        disabled={busy}
      />

      <div className="space-y-4 border-t border-line pt-6">
        <FlowError />
        {busy && <LoadingState label={t('loading.checking')} />}
        <div className="flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-between">
          <BackButton />
          <Button type="submit" size="lg" icon={ArrowRight} loading={busy} className="flex-row-reverse">
            {t('btn.continue')}
          </Button>
        </div>
      </div>
    </form>
  )
}

function PhotoMismatch({ focusHeading }) {
  const { t } = useLanguage()
  const { session, photos, retakePhotos, confirmPhotoMismatch, pending } = useComplaint()
  const busy = pending === 'answers'

  return (
    <div className="space-y-8">
      <PageHeading title={t('mismatch.title')} focus={focusHeading} />
      <PhotoMismatchAlert
        note={session.extraction?.photo_mismatch_note}
        photos={photos}
        onRetake={retakePhotos}
        onContinue={confirmPhotoMismatch}
        busy={busy}
      />
      <FlowError />
      {busy && <LoadingState label={t('loading.checking')} />}
      <BackButton />
    </div>
  )
}

function NotCivic({ focusHeading }) {
  const { t } = useLanguage()
  const { startOver } = useComplaint()

  return (
    <div className="space-y-8">
      <PageHeading title={t('notCivic.title')} focus={focusHeading} />
      <div className="flex gap-4 rounded-card border border-line bg-surface p-5 shadow-card sm:p-6">
        <CircleHelp className="mt-0.5 size-7 shrink-0 text-heading" aria-hidden="true" />
        <p className="text-lg">{t('notCivic.message')}</p>
      </div>
      <div className="flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-between">
        <BackButton />
        <Button size="lg" icon={RotateCcw} onClick={startOver}>
          {t('btn.startOver')}
        </Button>
      </div>
    </div>
  )
}

const VIEWS = { needs_info: NeedsInfo, photo_mismatch: PhotoMismatch, not_civic: NotCivic }

/** Rendered from the backend's session.status; `ready` never reaches here (the context moves to Route). */
export default function ClarifyPage({ focusHeading }) {
  const { t } = useLanguage()
  const { session } = useComplaint()
  const View = VIEWS[session?.status]
  return View ? <View focusHeading={focusHeading} /> : <LoadingState label={t('loading.checking')} />
}
