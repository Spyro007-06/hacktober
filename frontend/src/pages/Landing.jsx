import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ArrowRight } from 'lucide-react'
import { useComplaint } from '../context/ComplaintContext'
import { useLanguage } from '../context/LanguageContext'
import Button from '../components/ui/Button'
import { Textarea } from '../components/ui/Field'

// Page margins used by every section; the background fields run edge to edge.
const FRAME = 'mx-auto w-full max-w-wide px-4 sm:px-6'

/** Each part of a section rises into place once as it scrolls into view. */
function Reveal({ children, delay = 0, className = '' }) {
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '0px 0px -80px 0px' }}
      transition={{ duration: 0.5, delay, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </motion.div>
  )
}

/** The artefact: a complaint letter. The citizen writes the body of it right here, then the wizard takes over. */
function Letter() {
  const { t, uiLang } = useLanguage()
  const { text, setText } = useComplaint()
  const navigate = useNavigate()
  const [draft, setDraft] = useState(text)

  function start(e) {
    e.preventDefault()
    if (draft.trim()) setText(draft)
    navigate('/new')
  }

  return (
    <form
      onSubmit={start}
      className="rotate-0 space-y-5 rounded-[6px] bg-surface p-6 sm:p-8 lg:-rotate-[1.5deg]"
      aria-label={t('landing.sheet.title')}
    >
      <p className="text-card font-bold text-heading">{t('landing.sheet.title')}</p>
      <div className="space-y-1 bg-surface-muted px-4 py-3 text-support text-text">
        <p>{t('landing.sheet.to')}</p>
        <p>{t('landing.sheet.subject')}</p>
      </div>
      <Textarea
        label={t('landing.sheet.label')}
        hint={t('landing.sheet.hint')}
        rows={4}
        marker={false}
        maxLength={5000}
        lang={uiLang}
        placeholder={t('landing.sheet.placeholder')}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
      />
      <Button type="submit" size="lg" icon={ArrowRight} className="flex-row-reverse !shadow-none sm:w-full">
        {t('landing.sheet.start')}
      </Button>
    </form>
  )
}

function Hero() {
  const { t, uiLang } = useLanguage()
  // Tamil runs longer and its glyphs are wider, so it steps down to stay within two lines.
  const size = uiLang === 'ta' ? 'text-[clamp(1.6rem,3.6vw+0.5rem,3.4rem)]' : 'text-[clamp(2.4rem,5.4vw+0.5rem,5rem)]'
  return (
    <section aria-labelledby="hero-title" className="bg-heading">
      <div className={`${FRAME} space-y-12 pb-16 pt-12 sm:pb-24 sm:pt-20`}>
        <motion.h1
          id="hero-title"
          className={`font-bold leading-[1.08] text-white ${size} ${uiLang === 'ta' ? '' : 'max-w-[22ch]'}`}
          initial={{ opacity: 0, y: 28 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
        >
          {t('landing.hero.title')}
        </motion.h1>
        <div className="grid items-start gap-12 lg:grid-cols-2 lg:gap-16">
          <motion.div
            className="space-y-6"
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.12, ease: [0.22, 1, 0.36, 1] }}
          >
            <p className="max-w-[40ch] text-card leading-relaxed text-white/90">{t('landing.hero.lead')}</p>
            <p className="text-white/70">{t('landing.hero.note')}</p>
          </motion.div>
          <motion.div
            initial={{ opacity: 0, y: 32 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.22, ease: [0.22, 1, 0.36, 1] }}
          >
            <Letter />
          </motion.div>
        </div>
      </div>
    </section>
  )
}

const STEPS = [
  { key: 'landing.how.1', offset: 'lg:mt-0' },
  { key: 'landing.how.2', offset: 'lg:mt-14' },
  { key: 'landing.how.3', offset: 'lg:mt-28' },
]

function HowItWorks() {
  const { t } = useLanguage()
  return (
    <section aria-labelledby="how-title" className="bg-surface-muted py-16 sm:py-24">
      <div className={FRAME}>
        <Reveal>
          <h2 id="how-title" className="max-w-[24ch] text-page font-bold">
            {t('landing.how.title')}
          </h2>
        </Reveal>
        <ol className="mt-12 grid gap-6 lg:grid-cols-3 lg:gap-8">
          {STEPS.map(({ key, offset }, i) => (
            <li key={key} className={offset}>
              <Reveal delay={i * 0.08} className="h-full space-y-3 rounded-card bg-surface p-6 sm:p-8">
                <h3 className="text-section font-bold">{t(`${key}.title`)}</h3>
                <p className="text-text">{t(`${key}.body`)}</p>
              </Reveal>
            </li>
          ))}
        </ol>
      </div>
    </section>
  )
}

const ROUTES = [
  { route: 'local_body', key: 'landing.where.local' },
  { route: 'cm_helpline', key: 'landing.where.cm' },
  { route: 'rti', key: 'landing.where.rti' },
]

/** The three destinations, set like a printed menu: name, a dotted leader, who answers. */
function Where() {
  const { t } = useLanguage()
  return (
    <section aria-labelledby="where-title" className="bg-background py-16 sm:py-24">
      <div className={`${FRAME} grid items-start gap-12 lg:grid-cols-[5fr_6fr] lg:gap-16`}>
        <Reveal className="space-y-5">
          <h2 id="where-title" className="text-page font-bold">
            {t('landing.where.title')}
          </h2>
          <p className="max-w-[44ch] text-card leading-relaxed text-text">{t('landing.where.note')}</p>
        </Reveal>
        <Reveal delay={0.1} className="rounded-[6px] bg-surface p-6 sm:p-10">
          <ul className="space-y-8">
            {ROUTES.map(({ route, key }) => (
              <li key={route}>
                <div className="flex items-baseline gap-3">
                  <h3 className="text-card font-bold">{t(`route.${route}`)}</h3>
                  <span aria-hidden="true" className="min-w-6 flex-1 translate-y-[-0.3em] border-b-4 border-dotted border-primary" />
                </div>
                <p className="mt-1 font-semibold text-primary-ink">{t(`${key}.who`)}</p>
                <p className="mt-1 max-w-[40ch] text-text">{t(`${key}.body`)}</p>
              </li>
            ))}
          </ul>
        </Reveal>
      </div>
    </section>
  )
}

function Trust() {
  const { t } = useLanguage()
  return (
    <section aria-labelledby="trust-title" className="bg-heading py-16 sm:py-24">
      <div className={`${FRAME} grid items-start gap-12 lg:grid-cols-2 lg:gap-16`}>
        <Reveal>
          <h2 id="trust-title" className="text-page font-bold text-white">
            {t('landing.trust.title')}
          </h2>
        </Reveal>
        <ul className="space-y-8">
          {[1, 2, 3].map((n, i) => (
            <li key={n}>
              <Reveal delay={i * 0.08} className="space-y-1">
                <h3 className="text-card font-bold text-primary">{t(`landing.trust.${n}.title`)}</h3>
                <p className="max-w-[44ch] text-white/85">{t(`landing.trust.${n}.body`)}</p>
              </Reveal>
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}

const LINK_BASE =
  'inline-flex min-h-14 items-center justify-center gap-2.5 rounded-control px-7 text-[0.9444rem] font-bold transition-[background-color,transform] duration-150 active:scale-[0.98]'

function Closing() {
  const { t } = useLanguage()
  return (
    <section aria-labelledby="cta-title" className="overflow-hidden bg-primary pt-16 sm:pt-24">
      <div className={`${FRAME} grid items-end gap-12 lg:grid-cols-2 lg:gap-16`}>
        <Reveal className="space-y-4 pb-4 lg:pb-16">
          <h2 id="cta-title" className="text-page font-bold text-heading">
            {t('landing.cta.title')}
          </h2>
          <p className="max-w-[32ch] text-section leading-snug text-heading">{t('landing.cta.body')}</p>
        </Reveal>
        <Reveal delay={0.1} className="lg:translate-y-10">
          <div className="space-y-5 rounded-[6px] bg-surface p-6 text-center sm:p-10 lg:rotate-2">
            <Link to="/new" className={`${LINK_BASE} w-full bg-heading text-white hover:bg-text`}>
              {t('landing.cta.start')}
              <ArrowRight className="size-5" aria-hidden="true" />
            </Link>
            <Link to="/complaints" className="inline-flex min-h-12 items-center font-bold text-heading underline underline-offset-4 hover:text-primary-ink">
              {t('landing.cta.mine')}
            </Link>
          </div>
        </Reveal>
      </div>
    </section>
  )
}

function Footer() {
  const { t } = useLanguage()
  return (
    <footer className="bg-heading py-12">
      <div className={`${FRAME} flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between`}>
        <div>
          <p lang="ta" className="text-[clamp(3rem,10vw,6rem)] font-bold leading-[1.3] text-primary">
            குரல்
          </p>
          <p className="mt-3 text-section font-bold text-white">{t('landing.footer.sign')}</p>
        </div>
        <p className="text-white/70">{t('landing.footer.made')}</p>
      </div>
    </footer>
  )
}

/** Public home page: what Kural is, how it works, where complaints go, and the way in. */
export default function Landing() {
  return (
    <>
      <Hero />
      <HowItWorks />
      <Where />
      <Trust />
      <Closing />
      <Footer />
    </>
  )
}
