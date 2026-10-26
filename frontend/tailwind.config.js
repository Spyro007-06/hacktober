// Colors come from the --color-* CSS variables in src/index.css so every component shares one token set.
const token = (name) => `rgb(var(--color-${name}) / <alpha-value>)`
const status = (name) => ({ DEFAULT: token(name), soft: token(`${name}-soft`) })

/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        background: token('background'),
        surface: { DEFAULT: token('surface'), muted: token('surface-muted') },
        heading: token('heading'),
        text: token('text'),
        muted: token('text-muted'),
        line: { DEFAULT: token('border'), strong: token('border-strong') },
        primary: { DEFAULT: token('primary'), hover: token('primary-hover'), soft: token('primary-soft'), ink: token('primary-ink') },
        success: status('success'),
        warning: status('warning'),
        danger: status('danger'),
        info: status('info'),
      },
      fontFamily: {
        // Manrope has no Tamil glyphs, so Tamil text falls through to Noto Sans Tamil per character.
        sans: ['Manrope', '"Noto Sans Tamil"', 'system-ui', '-apple-system', '"Segoe UI"', 'sans-serif'],
      },
      // Type scale (root is 18px): page 28-35px, section 24-28px, card 20-22px, body 18px, label 17px,
      // support 16px, badge 13.5px. The clamps keep phones at the small end without breakpoint jumps.
      fontSize: {
        page: ['clamp(1.5556rem, 1.35rem + 1vw, 1.9444rem)', { lineHeight: '1.2' }],
        section: ['clamp(1.3333rem, 1.2rem + 0.4vw, 1.5556rem)', { lineHeight: '1.3' }],
        card: ['clamp(1.1111rem, 1.05rem + 0.3vw, 1.2222rem)', { lineHeight: '1.35' }],
        label: ['0.9444rem', { lineHeight: '1.45' }],
        support: ['0.8889rem', { lineHeight: '1.5' }],
        badge: ['0.75rem', { lineHeight: '1.4' }],
      },
      borderRadius: {
        control: '14px',
        card: '18px',
      },
      boxShadow: {
        // Navy-tinted and subtle: borders carry the structure, shadows only lift.
        card: '0 1px 2px rgb(20 43 59 / 0.04), 0 4px 14px rgb(20 43 59 / 0.05)',
        lift: '0 2px 4px rgb(20 43 59 / 0.06), 0 12px 28px rgb(20 43 59 / 0.10)',
      },
      maxWidth: {
        content: '44rem',
        wide: '64rem',
      },
      transitionDuration: {
        DEFAULT: '150ms',
      },
    },
  },
  plugins: [],
}
