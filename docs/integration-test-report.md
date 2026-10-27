# Integration test report

Frontend and backend run together and were tested as a whole: the real FastAPI backend, Gemma 4 online
(`gemma-4-26b-a4b-it` through the Gemini API), local Whisper `small`, local Piper voices (Tamil and English) and
WeasyPrint with Pango, driven through the real frontend in a browser (Chromium). All data was synthetic
(generated complaints, drawn images, a text-to-speech voice clip).

## Result

| Layer | Result |
|---|---|
| Backend unit and API tests (`python -m pytest`) | 672 passed, 0 failed |
| Frontend checks (`npm run check`) and production build | pass |
| API contract (13 endpoints, 38 checks with the exact requests the frontend sends) | 38 / 38 |
| Browser end-to-end scenarios (below) | all pass after the fixes listed under "Defects found" |

## Browser scenarios

| Area | Checks |
|---|---|
| Entry | Splash shows once per session; landing page; unknown URL redirects; nav links; favicon |
| Typed flow | Complaint, rule R2 local body with reason, name/address validation, draft with department, sandboxed document, edit and re-render, real PDF download, Listen in Tamil and English, mark as filed, appears in My complaints |
| Voice | A spoken clip is recorded (WebM/Opus), transcribed by Whisper, shown in the text box, and analysed by Gemma 4. A silent microphone is caught before upload |
| Follow-ups | Missing location asks one question and then routes; skipping twice still reaches the route |
| Photos | Matching photo accepted; mismatching photo shows the mismatch screen; "continue anyway" and "retake" both work; non-image rejected; at most 3 photos |
| Routing | Not civic stops with a notice (R5); records request routes to RTI (R1); operator override applies to the draft and the PDF name |
| Tracker | Overdue complaint listed first; Escalate only on overdue; escalation opens the CM Helpline draft that cites the original; filing it marks the original Escalated |
| Mode | Switching to offline without Ollama is refused (503) and the toggle reverts |
| Recovery and errors | Refresh restores the session; model timeout shows a message and Retry; backend unreachable keeps the typed text |
| Security | HTML and script in the complaint, name and address never run (sandboxed iframe) |
| Responsive and keyboard | Phone width (390 px) with no horizontal overflow on Describe, Route, Draft and Tracker; keyboard order and focus rings |

PDF content was inspected: two pages, Noto Sans Tamil embedded, Tamil text present, the citizen's edit and the demo-data
banner included.

## Defects found and fixed

| # | Defect | Fix |
|---|---|---|
| 1 | Gemma 4 spent about 520 hidden "thinking" tokens per call: extraction took 14 to 28 s and often hit the 30 s timeout | `thinkingLevel: minimal`, 4 to 6 s per call |
| 2 | The Gemini API answered HTTP 500 to about 45 % of calls (each in about a second) and stalled past 30 s about 1 call in 7 | Quick retries for transient 5xx and for stalled calls (15 s per attempt, 2 retries). Measured success over 20 sequential calls: 55 % before, 95 % after |
| 3 | An overridden route showed the rule's route on the draft page and in the PDF file name | The draft page uses the effective route |
| 4 | A silent or very quiet microphone produced a misleading "check your complaint text and photos" error | Live level meter, silent clips are not uploaded, accurate "no speech" message |
| 5 | The Listen button appeared even when no voice was configured | `/api/health` reports the available voices; Listen is shown only for those |
| 6 | The UI language reset to Tamil on refresh, and the complaint language stayed on Tamil for an English speaker | Language kept in the session; the complaint language follows the UI language until the citizen chooses |
| 7 | A rendering error blanked the whole page | Error boundary with a "Start again" screen |
| 8 | Inline warnings (such as "location isn't available") were announced as urgent alerts | Warnings use `role="status"` |

## Known limits

- **Gemma availability.** `gemma-4-31b-it` returned HTTP 500 on every call in testing; use `gemma-4-26b-a4b-it`. With the retries, about
  1 call in 20 still fails after all attempts; the interface shows a message and Retry.
- **Tamil quality is unverified.** Tamil speech recognition, the Tamil voice and the fixed Tamil wording were exercised but not judged
  by a native speaker. The test used an English synthetic voice clip because this machine has no Tamil voice.
- **Browser Back** leaves the app instead of going to the previous step (the wizard does not create history entries).
- **Department data and portal field labels are demo placeholders**, and the documents say so.
- The text-to-speech engine starts a process per request: the first playback of a paragraph takes 6 to 12 s (audio is then cached).
