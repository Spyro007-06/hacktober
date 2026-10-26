import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { MotionConfig } from 'framer-motion'
// Fonts are bundled locally (no Google Fonts) so the kiosk works with WiFi off.
// Only the Latin and Tamil subsets are needed.
import '@fontsource/noto-sans/latin-400.css'
import '@fontsource/noto-sans/latin-600.css'
import '@fontsource/noto-sans/latin-700.css'
import '@fontsource/noto-sans-tamil/tamil-400.css'
import '@fontsource/noto-sans-tamil/tamil-600.css'
import '@fontsource/noto-sans-tamil/tamil-700.css'
import './index.css'
import { LanguageProvider } from './context/LanguageContext'
import { ComplaintProvider } from './context/ComplaintContext'
import App from './App'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <MotionConfig reducedMotion="user">
        <LanguageProvider>
          {/* Above the routes so the wizard survives a visit to My complaints. */}
          <ComplaintProvider>
            <App />
          </ComplaintProvider>
        </LanguageProvider>
      </MotionConfig>
    </BrowserRouter>
  </StrictMode>,
)
