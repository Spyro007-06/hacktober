# Kural frontend: test report

**Date:** 2026-10-27 | **Build under test:** `main` @ `739cf3b` (milestones 1 to 4 + redesign) | **Tester:** Claude (automated, Playwright + Chromium)

## 1. Verdict

**Ship-ready for a mock-mode demo; not yet proven against a real backend.**

- Every P0 and P1 flow works end to end in mock mode, on phone, tablet and desktop, in Tamil and English.
- Real-mode request/response handling matches the written API contract (17/17 contract checks, 15/16 error-handling checks; the one "fail" was the browser logging the sandbox blocking a hostile test document, i.e. the defence working).
- **The backend on `main` is still entirely TODO stubs**, so "matches the real backend" cannot be claimed. Real-mode tests ran against a stub I wrote from `docs/frontend-requirements.pdf`, which only proves the frontend agrees with the spec, not with whatever the backend team builds.
- **5 medium defects** need a decision before a kiosk demo (section 4), most importantly a header that overflows at 1024-1090 px in Tamil and a missing error boundary.

| | |
|---|---|
| Automated checks executed | ~190 test cases + 121 per-screen audits (11 width/language combinations x 11 screens) |
| Defects found | 5 Medium, 6 Low, 4 observations |
| Blocking (Critical/High) | none |
| Console errors from the app itself | none (only expected HTTP-error resource logs) |

## 2. Scope and method

| Layer | What was done |
|---|---|
| Static | `npm run check` (i18n parity, contrast, mock self-check), production build, `npm audit`, grep for `fetch` outside the client, `localStorage`, `innerHTML`/`eval`, remote URLs, hard-coded strings |
| Functional (mock mode) | Describe, Clarify (all 4 statuses), Route, Draft, Done, My complaints, service panel, recovery after refresh, privacy (web storage), keyboard-only flow |
| Contract (real mode) | Frontend run with `VITE_USE_MOCKS=false` through the Vite proxy against a spec-following stub that logs every request (method, path, content type, multipart parts, JSON body) and injects faults |
| Error handling | HTTP 400/422/503/504/502(HTML)/500(wrong shape), network down, slow (3 s), duplicate clicks, navigating away mid-request, hostile HTML in a draft |
| Robustness | Incomplete/unexpected backend responses (missing fields, unknown status, malformed list items, 300 items) |
| Recorder | Real `MediaRecorder` on a synthetic microphone stream, 30 s auto-stop, transcribe, permission/device failures |
| Responsive + a11y | 360/390/768/1024/1440 plus 320 px, Tamil and English: overflow, touch targets (>= 48 px), clipped/off-screen text, raw i18n keys, names/labels, heading structure, duplicate ids, `lang` attributes; runtime colour-contrast of 479 rendered text colours per language; Tab order and focus visibility; `prefers-reduced-motion`; 200%/400% reflow |
| Performance (prod build) | FCP/LCP/CLS/long tasks, transfer size, hosts contacted, fonts loaded, heap and DOM growth over 8 repeated flows, object-URL release |

## 3. Results by area

| Area | Result |
|---|---|
| Describe: input gating, 0-3 photos, camera/gallery inputs, non-image rejection, 20 000-char text, location (denied/granted), language independence, no text in web storage, keyboard flow, double-click safety | **Pass** (21 checks) |
| Clarify: needs_info (2 rounds), whitespace answers, photo mismatch (retake / continue anyway), not_civic, timeout + retry, Back keeps text and photos, new session after Back | **Pass** (18) |
| Recovery: refresh on Clarify/Route restores; Draft returns to Route (documented); unknown session shows "not found" + Start over; corrupt storage ignored | **Pass** (6). Language not restored: D-03 |
| Route: card, rule, reason (both languages), override shown next to the recommendation, validation, focus, phone optional | **Pass** (7) |
| Draft: sandbox `""`, edit mode (5 allowed fields + person), cancel discards, save re-renders, copy for every field, PDF link, TTS 501 fallback, next steps, Mark as filed once | **Pass** (13) |
| Done / My complaints: reference + localised due date, file another, sorting, escalate once, status badges (icon + text) | **Pass** (10) |
| Service panel: opens, AI-mode switch, Escape returns focus, outside click closes, offline line, works on phone | **Pass** (5 + phone) |
| Real-mode contract | **Pass** 17/17: multipart fields and photo parts, Tamil text intact, lat/lon only after consent, answers JSON, drafts JSON, PATCH only changed fields, PDF relative link + filename, TTS JSON/WAV/cache/501, complaints POST/GET, escalate without body, mode PUT with 503 revert |
| Error mapping | **Pass** 15/16 (E16 = sandbox console messages from the hostile document) |
| Hostile draft HTML (script, `onerror`, `javascript:` link) | **Pass**: title unchanged, no message received, iframe DOM unreachable |
| Recorder | **Pass** 11/11: countdown, auto-stop at 30.5 s, webm/opus upload (about 16 KB/s), mic released, clips queued in order, retry, denied / no device / unsupported |
| Responsive sweep (11 screens each) | English: clean at 320, 360, 390, 768, 1024. Tamil: issues D-01, D-05, D-06 |
| Runtime contrast | **Pass**: 479 rendered text colours per language, plus placeholders, all >= 4.5:1 (large text >= 3:1). One reading of 2.79:1 was a mid-transition frame; the settled "Copied" state is 4.67:1 |
| Keyboard | **Pass**: logical order, every stop has a visible indicator, skip link works (checked on Describe) |
| Reduced motion | CSS transitions collapse (`1e-05s`); the sliding tab-underline could not be observed in either mode (see O-4) |
| Performance (prod) | FCP 84 ms, LCP 84 ms, CLS 0, 0 long tasks, 8 requests, 86 KB transferred; JS 434 KB (139 KB gzip); only the local origin contacted; fonts loaded; heap 32.7 -> 28.2 MB and DOM 166 -> 167 nodes after 8 flows |
| Static | `npm audit --omit=dev`: 0 vulnerabilities; no `fetch` outside `client.js`; no `localStorage`, `innerHTML`, `eval` or remote URLs |

## 4. Defects

Severity: Medium = real user impact or a spec/WCAG miss; Low = polish or edge case.

### Medium

**D-01. Header overflows horizontally at 1024-1090 px in Tamil.** `+69 px` at 1024, `+33 px` at 1060; fine from 1100 and in English. The "English" button is pushed off-screen. 1024 px is iPad landscape and a common kiosk width. *Cause:* at the `lg` breakpoint the desktop nav, the status chip with its label (`md:inline`) and the language switch share one row, and Tamil labels are wider. *Fix:* show the chip label only from `xl`, or drop the nav icons until `xl`.

**D-02. Browser/hardware Back leaves the app.** Wizard steps create no history entries, so Android Back from Clarify exits to the previous page. *Fix:* push a history entry per step, or handle `popstate` as the in-app Back.

**D-03. UI language is not kept across a refresh.** An English user who refreshes mid-flow (session recovery works) comes back in Tamil. *Fix:* keep the UI language in `sessionStorage` (it is not sensitive).

**D-04. No error boundary: one render error blanks the whole app.** Reproduced by `needs_info` without `follow_up_questions`: `TypeError ... reading 'map'` then a white page. A real backend that omits an optional field would trigger it. *Fix:* add an `ErrorBoundary` with a friendly Start-over screen, and default optional arrays (`follow_up_questions ?? []`).

**D-05. WCAG 1.4.10 Reflow fails at 320 px in Tamil on the Draft screen** (+10 px; the line "30 நாட்களுக்குள் பதில் எதிர்பார்க்கப்படுகிறது." cannot wrap). *Fix:* `overflow-wrap: anywhere` on that block.

### Low

- **D-06.** The Listen button's label is in the UI language but sits inside a `lang="en"`/`lang="ta"` block, so screen readers pronounce Tamil text with an English voice. Put `lang={uiLang}` on the button.
- **D-07.** A session with an unexpected `status` (a 5th value) leaves an endless spinner with no Back/Start over.
- **D-08.** Header tagline is ellipsized at >= 1280 px in both languages.
- **D-09.** No favicon: `GET /favicon.ico` returns 404 and logs a console error on every load.
- **D-10.** An unknown `decision.route` shows the raw key `route.foo` to the citizen.
- **D-11.** Photos upload at full resolution with no client-side size check (3 x 8 MB = 24 MB in the test); slow on cellular.

### Observations (not defects)

- **O-1.** The spec's sort (overdue first, then `days_left` ascending) puts Resolved and Escalated items (negative `days_left`) above active Filed ones.
- **O-2.** The page title is always "Kural" (acceptable, but gives no cue on route change).
- **O-3.** If the geolocation prompt is ignored, the "not available" notice appears after about 12 s.
- **O-4.** The tab underline's slide animation was not observable in either motion mode (1 distinct position over 700 ms); it may complete within one frame. Cosmetic.

## 5. What the tests could not tell us

- **No real backend.** Real-mode tests used my spec-derived stub. The three contract additions agreed later (`editable_fields`, audio formats, `route` on list items) are only as right as my reading of them.
- **Chromium only**: no Safari (iOS records mp4, not webm), Firefox, physical phone, kiosk, screen reader (NVDA/VoiceOver/TalkBack), or real microphone/camera/geolocation hardware (a synthetic stream and stubbed positions were used).
- Keyboard order and focus visibility were checked on the Describe screen only.
- Not tested: forced-colors/high-contrast mode, long-session behaviour beyond 8 flows, CI.

## 6. Test setup (for reproduction)

- Mock mode: `npm run dev` (default). Real mode: `npm run dev:real` with a backend on `:8000`.
- The stub backend, the Playwright suites and a composer script lived in the session scratchpad, not the repo. A contract stub like this is worth committing under `frontend/scripts/` if you want these checks repeatable.
- The Playwright tool's browser window kept changing size and throttling animation frames during the run; tests were stabilised by pinning the viewport and bringing the tab to the front. Several early "failures" were test or environment bugs and were re-run before being counted.
