# Kural

Kural turns a spoken complaint (Tamil or English) plus a photo into the right
government document. Gemma 4 extracts structured fields from the voice note and
checks the photo matches the claim; deterministic rules then choose the route
(`local_body`, `cm_helpline` or `rti`) and the department, and Jinja2 templates
fill a bilingual Tamil + English PDF along with portal-ready fields. It runs
online through the Gemini API or fully offline through Ollama. Built in a
12-hour hackathon for the theme "Best Use of Gemma 4".

## Prerequisites

- Python 3.11+
- Node 20+
- [Ollama](https://ollama.com) (offline mode)
- WeasyPrint system dependencies (Pango, HarfBuzz): see the
  [WeasyPrint install guide](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html)

## Setup

```bash
cp .env.example .env           # repo root; then fill in MODEL_MODE etc.
```

### Backend

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000   # run from the repo root
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Tests

```bash
python -m pytest -q          # from the repo root
```

## Team ownership

| Area | Folders | Owner |
|------|---------|-------|
| Frontend | `frontend/` | |
| AI pipeline | `backend/app/services/` (llm, extraction, stt, audio), `backend/app/prompts/` | |
| Rules and data | `backend/data/`, `backend/templates/`, `services/rules.py`, `services/lookup.py`, `backend/tests/` | |
| Lead (integration, routers, demo) | `backend/app/routers/`, `backend/app/main.py`, `demo/` | |
