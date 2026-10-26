# API

All routes are under `/api`.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Health check, current model mode |
| PUT | `/config/mode` | Switch online / offline |
| POST | `/transcribe` | Audio -> text |
| POST | `/sessions` | Start a complaint session (transcript + photos) |
| POST | `/sessions/{id}/answers` | Answer follow-up questions |
| GET | `/sessions/{id}` | Session state |
| POST | `/drafts` | Create a draft from a completed session |
| PATCH | `/drafts/{id}` | Edit a draft |
| GET | `/drafts/{id}/pdf` | Download the bilingual PDF |
| POST | `/tts` | Text -> speech (next steps) |
| POST | `/complaints` | File a complaint (save to SQLite) |
| GET | `/complaints` | List filed complaints |
| POST | `/complaints/{id}/escalate` | Escalate a complaint |

TODO: request/response shapes per endpoint.
