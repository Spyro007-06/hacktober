import { useEffect, useRef } from 'react'

/** Step title. `focus` moves keyboard/screen-reader focus here after a wizard step change. */
export default function PageHeading({ title, intro, focus = false }) {
  const ref = useRef(null)

  useEffect(() => {
    if (!focus) return
    window.scrollTo({ top: 0 })
    ref.current?.focus({ preventScroll: true })
  }, [focus])

  return (
    <header className="space-y-2.5">
      <h1 ref={ref} tabIndex={-1} className="text-page font-bold focus:outline-none">
        {title}
      </h1>
      {intro && <p className="max-w-prose text-lg text-muted">{intro}</p>}
    </header>
  )
}
