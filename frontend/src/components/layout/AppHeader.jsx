import { Link, NavLink } from 'react-router-dom'
import { ClipboardList, MessageSquarePlus } from 'lucide-react'
import { useLanguage } from '../../context/LanguageContext'
import Segmented from '../ui/Segmented'
import ModeToggle from '../ModeToggle'

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
            `flex min-h-12 items-center justify-center gap-2 whitespace-nowrap rounded-control px-2 font-semibold transition-colors duration-150 sm:px-4 ${itemClassName} ${
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
  const { t, uiLang, setUiLang } = useLanguage()
  return (
    <header className="sticky top-0 z-20 border-b border-line bg-surface/95 backdrop-blur-sm">
      <div className="mx-auto flex max-w-wide items-center gap-3 px-4 py-2.5 sm:gap-4 sm:px-6">
        <Link to="/" aria-label={t('app.home')} className="flex min-h-12 min-w-0 shrink-0 items-center xl:shrink gap-2.5 rounded-control sm:gap-3">
          <BrandMark />
          <span className="min-w-0 leading-tight">
            <span className="block whitespace-nowrap text-xl font-bold text-primary-deep">{t('app.title')}</span>
            <span className="hidden truncate text-sm text-muted xl:block">{t('app.tagline')}</span>
          </span>
        </Link>
        <NavItems className="ml-auto hidden gap-1 lg:flex" />
        <div className="ml-auto flex shrink-0 items-center gap-2 sm:gap-3 lg:ml-0">
          <ModeToggle />
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
      <NavItems className="grid grid-cols-2 gap-1 border-t border-line px-2 py-1.5 lg:hidden" itemClassName="text-base" />
    </header>
  )
}
