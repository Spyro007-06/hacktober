import { Link, NavLink } from 'react-router-dom'
import { ClipboardList, MessageSquarePlus } from 'lucide-react'
import { useLanguage } from '../../context/LanguageContext'
import useHealth from '../../hooks/useHealth'

const NAV = [
  { to: '/', key: 'nav.new', icon: MessageSquarePlus, end: true },
  { to: '/complaints', key: 'nav.complaints', icon: ClipboardList },
]

function BrandMark() {
  return (
    <svg viewBox="0 0 44 44" className="size-11 shrink-0" aria-hidden="true">
      <rect width="44" height="44" rx="13" className="fill-primary-deep" />
      <text x="19" y="29.5" textAnchor="middle" fontFamily="'Noto Sans Tamil', sans-serif" fontWeight="700" fontSize="18" className="fill-bg">
        கு
      </text>
      <path d="M32 16.5a8 8 0 0 1 0 11" strokeWidth="2.6" strokeLinecap="round" fill="none" className="stroke-accent" />
      <path d="M36 13a13 13 0 0 1 0 18" strokeWidth="2.6" strokeLinecap="round" fill="none" className="stroke-accent/60" />
    </svg>
  )
}

function ServiceStatus() {
  const { t } = useLanguage()
  const { status } = useHealth()
  const dot = { checking: 'bg-muted/50', ready: 'bg-success', down: 'bg-danger' }[status]

  return (
    <p role="status" className="flex min-h-12 items-center gap-2 text-sm text-muted" title={t(`service.${status}`)}>
      <span className="relative flex size-3">
        {status === 'ready' && <span className="absolute inset-0 rounded-full bg-success/30 motion-safe:animate-ping [animation-iteration-count:2]" />}
        <span className={`relative size-3 rounded-full ${dot}`} />
      </span>
      <span className="sr-only lg:not-sr-only">{t(`service.${status}`)}</span>
    </p>
  )
}

function LanguageSwitch() {
  const { t, uiLang, setUiLang } = useLanguage()
  return (
    <div role="group" aria-label={t('lang.toggle')} className="flex rounded-control border-2 border-line bg-surface p-1">
      {['ta', 'en'].map((code) => (
        <button
          key={code}
          type="button"
          lang={code}
          aria-pressed={uiLang === code}
          onClick={() => setUiLang(code)}
          className={`min-h-11 min-w-12 rounded-[10px] px-2.5 text-base sm:px-3 font-semibold transition-colors duration-150 ${
            uiLang === code ? 'bg-primary text-white' : 'text-muted hover:bg-primary-soft hover:text-primary-deep'
          }`}
        >
          {t(`lang.${code}`)}
        </button>
      ))}
    </div>
  )
}

function NavItems({ className, itemClassName }) {
  const { t } = useLanguage()
  return (
    <nav aria-label={t('nav.label')} className={className}>
      {NAV.map(({ to, key, icon: Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          className={({ isActive }) =>
            `flex min-h-12 items-center justify-center gap-2 whitespace-nowrap rounded-control px-2 font-semibold sm:px-4 transition-colors duration-150 ${itemClassName} ${
              isActive ? 'bg-primary-soft text-primary-deep' : 'text-muted hover:bg-primary-soft/60 hover:text-ink'
            }`
          }
        >
          <Icon className="size-5 shrink-0" aria-hidden="true" />
          {t(key)}
        </NavLink>
      ))}
    </nav>
  )
}

export default function AppHeader() {
  const { t } = useLanguage()
  return (
    <header className="sticky top-0 z-20 border-b border-line bg-surface/95 backdrop-blur-sm">
      <div className="mx-auto flex max-w-wide items-center gap-3 px-4 py-2.5 sm:gap-4 sm:px-6">
        <Link to="/" aria-label={t('app.home')} className="flex min-h-12 min-w-0 shrink-0 items-center gap-2.5 rounded-control sm:gap-3">
          <BrandMark />
          <span className="min-w-0 leading-tight">
            <span className="block whitespace-nowrap text-xl font-bold text-primary-deep">{t('app.title')}</span>
            <span className="hidden truncate text-sm text-muted sm:block">{t('app.tagline')}</span>
          </span>
        </Link>
        <NavItems className="ml-auto hidden gap-1 md:flex" />
        <div className="ml-auto flex shrink-0 items-center gap-2 sm:gap-3 md:ml-0">
          <ServiceStatus />
          <LanguageSwitch />
        </div>
      </div>
      <NavItems className="grid grid-cols-2 gap-1 border-t border-line px-2 py-1.5 md:hidden" itemClassName="text-base" />
    </header>
  )
}
