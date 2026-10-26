import { useRef } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useComplaint } from '../context/ComplaintContext'
import { useLanguage } from '../context/LanguageContext'
import StepIndicator, { STEPS } from '../components/layout/StepIndicator'
import LoadingState from '../components/ui/LoadingState'
import DescribePage from './DescribePage'
import ClarifyPage from './ClarifyPage'
import RouteDetailsPage from './RouteDetailsPage'

const PAGES = { describe: DescribePage, clarify: ClarifyPage, route: RouteDetailsPage }

/** The New complaint wizard: one step at a time, driven by ComplaintContext. */
export default function NewComplaint() {
  const { t } = useLanguage()
  const { step, recovering } = useComplaint()

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
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={step}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
          >
            <Page focusHeading={moved.current} />
          </motion.div>
        </AnimatePresence>
      )}
    </div>
  )
}
