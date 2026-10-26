// Colors come from CSS variables in src/index.css so every component shares one token set.
const token = (name) => `rgb(var(--${name}) / <alpha-value>)`

/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        bg: token('bg'),
        surface: token('surface'),
        ink: token('ink'),
        muted: token('muted'),
        line: token('line'),
        primary: { DEFAULT: token('primary'), deep: token('primary-deep'), soft: token('primary-soft') },
        accent: { DEFAULT: token('accent'), soft: token('accent-soft'), ink: token('accent-ink') },
        danger: { DEFAULT: token('danger'), soft: token('danger-soft') },
        warning: { DEFAULT: token('warning'), soft: token('warning-soft') },
        success: { DEFAULT: token('success'), soft: token('success-soft') },
      },
      fontFamily: {
        sans: ['"Noto Sans"', '"Noto Sans Tamil"', 'system-ui', 'sans-serif'],
      },
      borderRadius: {
        control: '14px',
        card: '20px',
      },
      boxShadow: {
        card: '0 1px 2px rgb(24 61 48 / 0.04), 0 4px 16px rgb(24 61 48 / 0.06)',
        lift: '0 2px 4px rgb(24 61 48 / 0.06), 0 12px 32px rgb(24 61 48 / 0.10)',
      },
      maxWidth: {
        content: '44rem',
        wide: '64rem',
      },
    },
  },
  plugins: [],
}
