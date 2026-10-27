import { useEffect, useState } from 'react'
import { Link, NavLink } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ClipboardList, MessageSquarePlus } from 'lucide-react'
import { useLanguage } from '../../context/LanguageContext'
import Segmented from '../ui/Segmented'
import ModeToggle from '../ModeToggle'

const NAV = [
  { to: '/new', key: 'nav.new', icon: MessageSquarePlus, end: true },
  { to: '/complaints', key: 'nav.complaints', icon: ClipboardList },
]

// Ink tile, Tamil "கு", and two turmeric sound-waves: a voice becoming a document.
function BrandMark() {
  return (
    <svg viewBox="0 0 44 44" className="size-11 shrink-0" aria-hidden="true">
      <rect width="44" height="44" rx="13" className="fill-heading" />
      <text x="19" y="29.5" textAnchor="middle" fontFamily="'Noto Sans Tamil', sans-serif" fontWeight="700" fontSize="18" fill="white">
        கு
      </text>
      <path d="M32 16.5a8 8 0 0 1 0 11" strokeWidth="2.6" strokeLinecap="round" fill="none" className="stroke-primary" />
      <path d="M36 13a13 13 0 0 1 0 18" strokeWidth="2.6" strokeLinecap="round" fill="none" className="stroke-primary/60" />
    </svg>
  )
}

// layoutId makes the ink underline glide between tabs; each nav instance needs its own id.
function NavItems({ className, itemClassName, layoutId }) {
  const { t } = useLanguage()
  return (
    <nav aria-label={t('nav.label')} className={className}>
      {NAV.map(({ to, key, icon: Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          className={({ isActive }) =>
            `relative flex min-h-12 items-center justify-center gap-2 whitespace-nowrap rounded-control px-2 text-center font-bold max-[340px]:whitespace-normal max-[340px]:leading-tight transition-colors duration-150 sm:px-4 ${itemClassName} ${
              isActive ? 'bg-primary-soft/60 text-heading' : 'text-muted hover:bg-surface-muted hover:text-heading'
            }`
          }
        >
          {({ isActive }) => (
            <>
              <Icon className={`size-5 shrink-0 max-[420px]:hidden ${isActive ? 'text-primary-ink' : ''}`} aria-hidden="true" />
              {t(key)}
              {isActive && (
                <motion.span
                  layoutId={layoutId}
                  className="absolute inset-x-3 -bottom-px h-[3px] rounded-full bg-heading"
                  transition={{ type: 'spring', visualDuration: 0.25, bounce: 0.1 }}
                />
              )}
            </>
          )}
        </NavLink>
      ))}
    </nav>
  )
}

// One ModeToggle instance (it polls /api/health): in the top row on desktop, in the tab row below lg.
function useIsDesktop() {
  const query = '(min-width: 1024px)'
  const [match, setMatch] = useState(() => window.matchMedia(query).matches)
  useEffect(() => {
    const mq = window.matchMedia(query)
    const on = (e) => setMatch(e.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])
  return match
}

export default function AppHeader() {
  const { t, uiLang, setUiLang } = useLanguage()
  const isDesktop = useIsDesktop()
  return (
    <header className="z-20 border-b border-line bg-surface/95 backdrop-blur-sm lg:sticky lg:top-0">
      <div className="mx-auto flex max-w-wide items-center gap-3 px-3 py-1.5 min-[360px]:px-4 sm:py-2.5 sm:gap-4 sm:px-6">
        <Link to="/" aria-label={t('app.home')} className="flex min-h-12 min-w-0 shrink-0 items-center gap-2.5 rounded-control xl:shrink sm:gap-3">
          <BrandMark />
          <span className="min-w-0 leading-tight">
            <span className="block whitespace-nowrap text-card font-bold text-heading">{t('app.title')}</span>
            <span className="hidden truncate text-support text-muted xl:block">{t('app.tagline')}</span>
          </span>
        </Link>
        <NavItems className="ml-auto hidden gap-1 lg:flex" itemClassName="" layoutId="nav-desktop" />
        <div className="ml-auto flex shrink-0 items-center gap-2 sm:gap-3 lg:ml-0">
          {isDesktop && <ModeToggle />}
          <Segmented
            label={t('lang.toggle')}
            value={uiLang}
            onChange={setUiLang}
            options={[
              { value: 'ta', label: t('lang.ta'), lang: 'ta' },
              { value: 'en', label: t('lang.en'), lang: 'en' },
            ]}
          />
        </div>
      </div>
      <div className="flex items-center gap-1 border-t border-line px-2 py-1 lg:hidden">
        <NavItems className="grid min-w-0 flex-1 grid-cols-2 gap-1" itemClassName="text-label" layoutId="nav-mobile" />
        {!isDesktop && <ModeToggle />}
      </div>
    </header>
  )
}
