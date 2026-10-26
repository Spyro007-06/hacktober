import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import ta from '../i18n/ta.json'
import en from '../i18n/en.json'

const STRINGS = { ta, en }
const LanguageContext = createContext(null)

// UI language only. The complaint language sent to the backend lives in the complaint state.
export function LanguageProvider({ children }) {
  const [uiLang, setUiLang] = useState('ta')

  useEffect(() => {
    document.documentElement.lang = uiLang
  }, [uiLang])

  const t = useCallback(
    (key, vars) => {
      let s = STRINGS[uiLang][key] ?? en[key] ?? key
      if (vars) for (const [k, v] of Object.entries(vars)) s = s.replaceAll(`{${k}}`, v)
      return s
    },
    [uiLang],
  )

  const value = useMemo(() => ({ uiLang, setUiLang, t }), [uiLang, t])
  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>
}

export function useLanguage() {
  return useContext(LanguageContext)
}
