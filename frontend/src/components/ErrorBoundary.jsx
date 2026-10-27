import { Component } from 'react'
import { useLanguage } from '../context/LanguageContext'
import Button from './ui/Button'

function Fallback() {
  const { t } = useLanguage()
  function restart() {
    try {
      sessionStorage.removeItem('kural.session')
    } catch {
      // Storage blocked: nothing to clear.
    }
    window.location.assign('/')
  }
  return (
    <div role="alert" className="mx-auto max-w-content space-y-4 px-4 py-16 text-center">
      <h1 className="text-page font-bold">{t('boundary.title')}</h1>
      <p className="text-muted">{t('boundary.body')}</p>
      <Button onClick={restart}>{t('boundary.restart')}</Button>
    </div>
  )
}

/** A render error in any screen shows a way out instead of a blank page. */
export default class ErrorBoundary extends Component {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidCatch(error) {
    console.error('[kural]', error)
  }

  render() {
    return this.state.failed ? <Fallback /> : this.props.children
  }
}
