# Kural frontend

React 18 + Vite + Tailwind (JavaScript). Spec: [docs/frontend-requirements.md](../docs/frontend-requirements.md).

```bash
npm install
npm run dev        # mock backend (default), http://localhost:5173
npm run dev:real   # real backend: proxies /api to http://localhost:8000
npm run check      # i18n key parity + mock backend self-check
npm run build
```

Mock mode is on unless `VITE_USE_MOCKS=false` (set by `.env.real` / `--mode real`).

## Layout

- `src/api/client.js` – every backend call, one function per endpoint. Components never call `fetch`.
- `src/api/mocks.js` – deterministic in-memory backend used in mock mode.
- `src/i18n/{ta,en}.json` – all UI strings, same keys. Tamil is the default.
- `src/context/LanguageContext.jsx` – UI language and `t(key, vars)`.
- `src/components/layout/` – AppHeader, StepIndicator.
- Design tokens ("Manjal & Ink": turmeric action colour, ink text, stone neutrals, cobalt for info): `--color-*` variables in `src/index.css`,
  mapped in `tailwind.config.js`. `npm run check` also asserts their WCAG contrast (`scripts/check-contrast.mjs`).
- Type scale: Tailwind sizes `text-page`, `text-section`, `text-card`, `text-label`, `text-support`, `text-badge` (root is 18px).
- Fonts: Manrope (English) and Noto Sans Tamil (Tamil) bundled via `@fontsource`; no network needed.
- Shared UI: Button, Field (Input/Textarea), Banner, ErrorBanner, StatusBadge, Segmented, EmptyState, LoadingState.
