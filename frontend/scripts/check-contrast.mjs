// WCAG contrast check for the design tokens in src/index.css (--color-NAME: R G B).
// Text pairs need 4.5:1 (AA); non-text UI (input borders, focus ring) needs 3:1.
import { readFileSync } from 'node:fs'

const css = readFileSync(new URL('../src/index.css', import.meta.url), 'utf8')
const c = {}
for (const [, name, r, g, b] of css.matchAll(/--color-([a-z-]+):\s*(\d+) (\d+) (\d+)/g)) c[name] = [+r, +g, +b]

const lum = ([r, g, b]) => {
  const f = (v) => ((v /= 255) <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4)
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
}
const ratio = (a, b) => {
  const [hi, lo] = [lum(c[a] ?? [255, 255, 255]), lum(c[b] ?? [255, 255, 255])].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

const TEXT = [
  // body copy and headings on every neutral surface
  ...['background', 'surface', 'surface-muted'].flatMap((bg) => [['text', bg], ['heading', bg]]),
  ['text-muted', 'background'], ['text-muted', 'surface'], ['text-muted', 'surface-muted'],
  // primary action: ink label on turmeric (never white), turmeric-as-text on light surfaces
  ['heading', 'primary'], ['heading', 'primary-hover'],
  ['primary-ink', 'surface'], ['primary-ink', 'background'], ['primary-ink', 'primary-soft'],
  ['heading', 'primary-soft'], ['text', 'primary-soft'], ['text-muted', 'primary-soft'],
  ['white', 'heading'],
  // status text on its tint and on a plain surface (info doubles as the link colour)
  ...['success', 'warning', 'danger', 'info'].flatMap((s) => [[s, `${s}-soft`], [s, 'surface']]),
  ['white', 'success'],
]
// Non-text: control edges, and the ink focus ring. The turmeric button is identified by its label, not its edge.
const UI = [['border-strong', 'surface'], ['border-strong', 'background'], ['heading', 'surface'], ['heading', 'background']]

const fails = []
const report = (list, min) =>
  list.forEach(([fg, bg]) => {
    const r = ratio(fg, bg)
    if (r < min) fails.push(`${fg} on ${bg}: ${r.toFixed(2)}:1 (needs ${min}:1)`)
  })
report(TEXT, 4.5)
report(UI, 3)

if (fails.length) {
  console.error(fails.join('\n'))
  process.exit(1)
}
console.log(`contrast ok: ${TEXT.length} text pairs >= 4.5:1, ${UI.length} UI pairs >= 3:1`)
