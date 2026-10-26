import { Navigate, Route, Routes } from 'react-router-dom'
import { useLanguage } from './context/LanguageContext'
import AppHeader from './components/layout/AppHeader'
import NewComplaint from './pages/NewComplaint'
import Complaints from './pages/Complaints'

export default function App() {
  const { t } = useLanguage()
  return (
    <div className="flex min-h-dvh flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-control focus:bg-primary-deep focus:px-5 focus:py-3 focus:text-white"
      >
        {t('app.skip')}
      </a>
      <AppHeader />
      <main id="main" tabIndex={-1} className="mx-auto w-full max-w-content flex-1 px-4 pb-16 pt-6 focus:outline-none sm:px-6 sm:pt-10">
        <Routes>
          <Route path="/" element={<NewComplaint />} />
          <Route path="/complaints" element={<Complaints />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
}
