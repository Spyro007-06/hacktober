# API

All routes are under `/api`. Requests and responses are JSON unless noted. The source of truth is
`backend/models.py` and `backend/routers/`; `backend/tests/test_api_contract.py` checks the shapes the
frontend relies on. Frontend-specific additions are in [frontend-requirements.md](frontend-requirements.md).

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Health check and current model mode |
| PUT | `/config/mode` | Switch online or offline (in memory only) |
| POST | `/transcribe` | Audio to text (local Whisper) |
| POST | `/sessions` | Start a complaint session (text, photos, location) |
| POST | `/sessions/{id}/answers` | Answer follow-up questions or confirm a photo |
| GET | `/sessions/{id}` | Session state, used to recover after a refresh |
| POST | `/drafts` | Create a draft from a ready session |
| PATCH | `/drafts/{id}` | Edit the editable fields and complainant details |
| GET | `/drafts/{id}/pdf` | Download the bilingual PDF |
| POST | `/tts` | Text to speech (501 when no engine is configured) |
| POST | `/complaints` | Record that a draft was filed |
| GET | `/complaints` | List filed complaints with days left |
| POST | `/complaints/{id}/escalate` | Prepare the next-step draft for an overdue complaint |

## Errors

Every error has the same body: `{"error": {"code": "...", "message": "..."}}`.

| Status | Code | When |
|---|---|---|
| 400 | `BAD_INPUT` | Invalid or missing input (the message says which) |
| 404 | `NOT_FOUND` | Unknown session, draft, complaint or route |
| 409 | `SESSION_NOT_READY` | A draft was requested before follow-up questions or the photo check were resolved |
| 422 | `MODEL_INVALID_OUTPUT` | The model replied with invalid output twice (after the one retry) |
| 422 | `NO_DEPARTMENT` | No department matches the route and category |
| 500 | `INTERNAL_ERROR` | An unexpected server error |
| 501 | `TTS_UNAVAILABLE` | No text-to-speech engine or voice for that language |
| 503 | `MODEL_UNAVAILABLE` / `PDF_UNAVAILABLE` | Model provider not configured or not reachable, or PDF libraries missing |
| 504 | `MODEL_TIMEOUT` | The model took too long |

## Endpoints

### `GET /health`

`{"status": "ok", "model_mode": "online" | "offline", "model": "<configured model id>"}`

### `PUT /config/mode`

Body `{"mode": "online" | "offline"}`. Returns the same shape as `/health`. A mode that is not fully
configured, or an offline mode whose Ollama is not running, returns `503 MODEL_UNAVAILABLE` and the current mode stays.

### `POST /transcribe`

`multipart/form-data`: `audio` (WebM, WAV or MP4/M4A, up to 30 s per clip in the UI) and `language` (`ta` or `en`).
Returns `{"transcript": "...", "language": "ta", "engine": "whisper"}`.

### `POST /sessions`

`multipart/form-data`:

| Field | Notes |
|---|---|
| `text` | The complaint, up to 5000 characters |
| `language` | `ta` or `en` |
| `photos` | Zero to three JPEG, PNG or WebP files, up to 8 MB each (repeat the field) |
| `lat`, `lon` | Optional position, only when the citizen shared it |
| `input_source` | `typed` (default) or `speech` |
| `transcript_confirmed` | Must be `true` when `input_source` is `speech` |

Returns a **session**:

```json
{
  "session_id": "s_ab12cd",
  "status": "needs_info",
  "extraction": { "category": "streetlight", "summary_en": "...", "summary_ta": "...",
                  "location_text": null, "duration": "3 weeks", "severity": "medium",
                  "photo_findings": [], "photo_matches_claim": null, "photo_mismatch_note": null,
                  "wants_records": false, "user_says_ignored": false,
                  "requested_info": [], "missing_fields": ["location_text"] },
  "decision": null,
  "ward": null,
  "follow_up_questions": [{ "field": "location_text", "question_en": "...", "question_ta": "..." }],
  "notice": null
}
```

`status` is one of `needs_info` (answer the questions), `photo_mismatch` (retake or confirm the photo),
`not_civic` (R5; `notice` has `{en, ta}` text) or `ready`. When the status is `ready`, `decision` is set:
`{"route", "rule_id", "reason_en", "reason_ta", "escalation_level"}`. The route always comes from the rule table.

### `POST /sessions/{id}/answers`

Body `{"answers": {"location_text": "Gandhi Street"}, "confirm_photo_mismatch": false}`. `answers` is required
but may be empty (a skipped question still counts as a round; after two rounds the session continues with
what is filled). Allowed keys: `location_text`, `duration`, `area`, and `photo_mismatch: "confirm"` as an
alternative to `confirm_photo_mismatch`. Returns a session.

### `GET /sessions/{id}`

The same fields as a session, plus the stored session (`transcript`, `language`, `answers`, ...).

### `POST /drafts`

```json
{ "session_id": "s_ab12cd",
  "complainant": { "name": "R. Priya", "address": "14 Gandhi Street", "phone": "9800000000" },
  "route_override": null }
```

`phone` and `route_override` are optional. Returns a **draft**:

```json
{
  "draft_id": "d_ef34",
  "decision": { "route": "local_body", "rule_id": "R2", "reason_en": "...", "reason_ta": "...", "escalation_level": 1 },
  "route": "local_body",
  "route_override": null,
  "department": { "id": "...", "name": "...", "address": "...", "submit_via": "...", "response_days": 15 },
  "department_verified": false,
  "html": "<html>...</html>",
  "portal_fields": { "Complaint": "..." },
  "portal_fields_verified": false,
  "next_steps": { "en": "...", "ta": "..." },
  "editable_fields": { "summary_en": "...", "summary_ta": "...", "location_text": "...", "duration": "...", "requested_info": [] }
}
```

`decision` is always the rule's choice; `route` is the effective route (the operator's override if set).
`*_verified: false` means the data are demo placeholders and the document says so.

### `PATCH /drafts/{id}`

Body `{"fields": {"summary_en": "..."}, "complainant": {"phone": "..."}}`. Only `summary_en`, `summary_ta`,
`location_text`, `duration` and `requested_info` (a list of lines) can be edited; anything else is a `400`.
Returns a draft.

### `GET /drafts/{id}/pdf`

`application/pdf`, downloaded as `kural_<route>_<draft_id>.pdf`.

### `POST /tts`

Body `{"text": "...", "language": "ta" | "en"}`. Returns `audio/wav`, or `501 TTS_UNAVAILABLE`.

### `POST /complaints`

Body `{"draft_id": "d_ef34", "filed_on": "2026-10-27"}`. Filing the same draft twice returns the same record.
Returns `{"id", "draft_id", "route", "category", "location_text", "ward", "filed_on", "due_on", "status", "parent_complaint_id", "escalation_level"}`.
`due_on` is `filed_on` plus the department's `response_days`. Kural submits nothing to any portal.

### `GET /complaints`

A list of `{"id", "draft_id", "title", "route", "category", "filed_on", "due_on", "days_left", "due_date_verified", "status", ...}`,
overdue first, then by days left. `status` is `filed`, `overdue`, `resolved` or `escalated`.

### `POST /complaints/{id}/escalate`

No body. Only an overdue complaint can escalate. Returns a draft (same shape as `POST /drafts`) for the next rung
of the ladder. The original complaint becomes `escalated` only when that draft is filed.
