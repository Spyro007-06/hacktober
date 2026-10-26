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
cp .env.example backend/.env   # then fill in GEMINI_API_KEY etc.
```

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Tests

```bash
cd backend
pytest
```

## Team ownership

| Area | Folders | Owner |
|------|---------|-------|
| Frontend | `frontend/` | |
| AI pipeline | `backend/app/services/` (llm, extraction, stt, audio), `backend/app/prompts/` | |
| Rules and data | `backend/data/`, `backend/templates/`, `services/rules.py`, `services/lookup.py`, `backend/tests/` | |
| Lead (integration, routers, demo) | `backend/app/routers/`, `backend/app/main.py`, `demo/` | |
