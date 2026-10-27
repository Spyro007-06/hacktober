# Kural

Kural turns a spoken complaint (Tamil or English) plus a photo into the right
government document. Built in a 12-hour hackathon, theme "Best Use of Gemma 4".
Full requirements: @docs/PRD.md

## How it works
1. User records voice (max 30 s per clip) and adds 0-3 photos.
2. Gemma 4 extracts structured fields (Extraction schema) and checks the photo
   matches the claim. Missing fields -> follow-up questions, never guesses.
3. Deterministic rules (data/rules.json, R1-R5) choose the route:
   local_body | cm_helpline | rti. Department comes from data/departments.json.
4. Jinja2 templates render a bilingual Tamil + English document -> WeasyPrint PDF,
   plus portal-ready fields for the CM Helpline form.
5. Next steps are spoken by an offline Tamil TTS engine.
6. Filed complaints are saved in SQLite; history feeds the routing rules.

## Hard rules
- Gemma NEVER chooses the route, department, legal wording or deadlines.
  Those come only from rules.json, departments.json and templates/.
- Every model response is validated with Pydantic (app/models/schemas.py).
  Retry once on invalid output, then return MODEL_INVALID_OUTPUT.
- All model calls go through services/llm.py generate(). The online/offline
  switch (MODEL_MODE) exists only there.
- Audio: convert to 16 kHz mono, split into 30-second chunks before STT.
- PDFs must use the Noto Sans Tamil font so Tamil renders correctly.
- Never commit .env, backend/storage/, or *.db.
- Don't add new dependencies without asking.
- 12-hour build: choose the simplest working solution. No auth, no portal
  submission, no WhatsApp bot, no languages beyond Tamil and English.

## Stack
- Backend: Python 3.11, FastAPI, Pydantic, SQLModel (SQLite), Jinja2, WeasyPrint,
  google-genai (online), Ollama (offline, Gemma 4 E4B)
- Frontend: React + Vite + Tailwind, JavaScript (.jsx)
- All API routes under /api. Endpoint list: docs/api.md

## Commands
- Backend (repo root): uvicorn backend.main:app --reload --port 8000
- Frontend: cd frontend && npm run dev
- Tests (repo root): python -m pytest -q

## Priorities
P0 must work for the demo; P1 only after P0 is done. See the Scope table in
docs/PRD.md. Feature freeze at hour 8.

## Team ownership
- Frontend: frontend/
- AI pipeline: backend/app/services/ (llm, extraction, stt, audio), prompts/
- Rules and data: backend/data/, templates/, services/rules.py, lookup.py, tests/
- Lead: integration, routers, demo
Only edit files in your own area unless asked.
