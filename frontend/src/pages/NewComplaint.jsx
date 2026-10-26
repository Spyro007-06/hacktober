import { useRef } from 'react'
import { motion } from 'framer-motion'
import { useComplaint } from '../context/ComplaintContext'
import { useLanguage } from '../context/LanguageContext'
import StepIndicator, { STEPS } from '../components/layout/StepIndicator'
import LoadingState from '../components/ui/LoadingState'
import DescribePage from './DescribePage'
import ClarifyPage from './ClarifyPage'
import RouteDetailsPage from './RouteDetailsPage'
import DraftPage from './DraftPage'
import DonePage from './DonePage'

const PAGES = { describe: DescribePage, clarify: ClarifyPage, route: RouteDetailsPage, draft: DraftPage, done: DonePage }

/** The New complaint wizard: one step at a time, driven by ComplaintContext. */
export default function NewComplaint() {
  const { t } = useLanguage()
  const { step: rawStep, recovering, draft } = useComplaint()
  const step = rawStep === 'draft' && !draft ? 'route' : rawStep

  // Focus the heading only after the user moves between steps, not on first load.
  const firstStep = useRef(step)
  const moved = useRef(false)
  if (step !== firstStep.current) moved.current = true

  const Page = PAGES[step] ?? DescribePage

  return (
    <div className="space-y-8">
      <StepIndicator current={Math.max(0, STEPS.indexOf(step))} />
      {recovering ? (
        <LoadingState label={t('loading.checking')} />
      ) : (
        // Enter-only transition: the next step mounts at once, even if animation frames are paused (background tab).
        <motion.div
          key={step}
          initial={moved.current ? { opacity: 0, y: 12 } : false}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.2, ease: 'easeOut' }}
        >
          <Page focusHeading={moved.current} />
        </motion.div>
      )}
    </div>
  )
}
