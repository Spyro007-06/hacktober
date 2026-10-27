# PRD summary

The full document, with the data model and the backend API, is [Kural_PRD_and_Backend_API.pdf](Kural_PRD_and_Backend_API.pdf).
This page keeps the parts a reader needs most.

**Goal.** A working demo where a Tamil voice complaint plus a photo becomes a ready-to-file document in
under 15 seconds, privately.

**Users.** Residents who prefer Tamil, including elderly and less confident people helped by an operator
at a kiosk such as an e-Sevai centre, and students who want a quick, correct complaint.

## Demo success metrics

| Metric | Target |
|---|---|
| Correct route on the 15 test cases | 13 of 15 or better |
| Voice and photo to draft (online) | Under 15 seconds |
| Same flow offline (Gemma 4 on Ollama) | Completes without errors |
| Legal wording or department invented by the model | Never |

These are targets from the plan, not measured results.

## Scope

Ten P0 features must work for the demo; four P1 features are built only if P0 is done early.

| # | Feature | Priority | Done when |
|---|---|---|---|
| 1 | Voice input | P0 | Tamil or English recording with a 30-second countdown; longer audio split into 30-second chunks; typed input as fallback |
| 2 | Photo evidence and claim check | P0 | Gemma describes 1 to 3 photos and flags a mismatch with the spoken claim before drafting |
| 3 | Problem understanding | P0 | Gemma fills structured fields only; it never chooses the route |
| 4 | Follow-up questions | P0 | Missing required fields are asked in Tamil, never invented |
| 5 | Rule-based routing | P0 | A rule table picks the route and shows the rule id that fired |
| 6 | Department lookup | P0 | The department comes from a JSON table |
| 7 | Complaint history | P0 | Every filed complaint is saved in SQLite; past complaints feed the routing rules |
| 8 | Editable preview | P0 | Only Gemma-written text and personal details are editable |
| 9 | Bilingual PDF and portal fields | P0 | Tamil and English PDF with photos, plus each portal form field with a copy button |
| 10 | Spoken next steps | P0 | Next steps read aloud by an offline Tamil text-to-speech engine |
| 11 | GPS ward detection | P1 | Browser location matched to one city's ward boundary file |
| 12 | Tracker screen | P1 | Saved complaints with a deadline countdown |
| 13 | One-tap escalation | P1 | Moves a complaint one step up the routing ladder |
| 14 | WiFi-off demo | P1 | Full flow on Gemma 4 through Ollama with no network |

Out of scope: consumer complaints, login and accounts, submitting to government portals, a WhatsApp bot,
languages beyond Tamil and English, a phone app, and checking officials' replies.

## Routing rules

| Rule | When | Route |
|---|---|---|
| R1 | The user wants records or information, not a fix | RTI |
| R2 | A civic problem and no earlier complaint | Local body complaint |
| R3 | An earlier local-body complaint was ignored, or the problem spans departments | CM Helpline grievance |
| R4 | A CM Helpline grievance was ignored after escalation | RTI asking for action taken |
| R5 | Not a civic problem | No route; tell the user Kural does not cover it |

The CM Helpline has three escalation levels (designated officer, first appellate officer, second appellate
officer), so one-tap escalation climbs those before R4 fires. RTI is always a separate path, never mixed
into a grievance.

## Non-functional requirements

- **Privacy.** In offline mode no request leaves the kiosk laptop. Photos, audio and personal details stay in
  local SQLite and the local uploads folder. No analytics or third-party logging.
- **Reliability.** Every model response is validated against the Pydantic schema; one automatic retry, then a clear error.
- **Correctness.** Routes, departments, legal wording and deadlines come only from the rule table, the JSON
  lookup and the Jinja2 templates.
- **Speed.** Photos are resized to at most 1024 px before any model call.
- **Tamil rendering.** PDFs use WeasyPrint with Noto Sans Tamil.
- **Model switch.** One `MODEL_MODE` setting (online or offline) changes the backend; no other code path differs.
