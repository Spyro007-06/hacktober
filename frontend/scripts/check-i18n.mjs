// ta.json and en.json must have exactly the same keys and no empty values.
import { readFileSync } from 'node:fs'

const load = (lang) => JSON.parse(readFileSync(new URL(`../src/i18n/${lang}.json`, import.meta.url), 'utf8'))
const ta = load('ta')
const en = load('en')

const problems = [
  ...Object.keys(en).filter((k) => !(k in ta)).map((k) => `missing in ta.json: ${k}`),
  ...Object.keys(ta).filter((k) => !(k in en)).map((k) => `missing in en.json: ${k}`),
  ...Object.entries({ ...ta }).filter(([, v]) => !String(v).trim()).map(([k]) => `empty in ta.json: ${k}`),
  ...Object.entries({ ...en }).filter(([, v]) => !String(v).trim()).map(([k]) => `empty in en.json: ${k}`),
]

if (problems.length) {
  console.error(problems.join('\n'))
  process.exit(1)
}
console.log(`i18n ok: ${Object.keys(en).length} keys in both languages`)
