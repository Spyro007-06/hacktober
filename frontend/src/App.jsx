import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { useLanguage } from './context/LanguageContext'
import AppHeader from './components/layout/AppHeader'
import NewComplaint from './pages/NewComplaint'
import Landing from './pages/Landing'
import Splash from './components/Splash'
import Complaints from './pages/Complaints'

export default function App() {
  const { t } = useLanguage()
  const landing = useLocation().pathname === '/'
  return (
    <div className="flex min-h-dvh flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-control focus:bg-heading focus:px-5 focus:py-3 focus:text-white"
      >
        {t('app.skip')}
      </a>
      <AppHeader />
      {landing && <Splash />}
      <main
        id="main"
        tabIndex={-1}
        className={`flex-1 focus:outline-none ${landing ? '' : 'mx-auto w-full max-w-content px-4 pb-16 pt-6 sm:px-6 sm:pt-10'}`}
      >
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/new" element={<NewComplaint />} />
          <Route path="/complaints" element={<Complaints />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
}
