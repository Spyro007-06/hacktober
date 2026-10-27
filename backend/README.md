# Kural backend

FastAPI backend for Kural, an AI-powered civic complaint assistant. The spec is
`docs/Kural_PRD_and_Backend_API.pdf`.

**Status: Phase 3, step 1.** Implemented: `GET /api/health`, `POST /api/sessions`,
`GET /api/sessions/{id}`, `POST /api/sessions/{id}/answers` (extraction through
a Gemini or Ollama provider, strict validation, deterministic routing), and
`POST /api/drafts`, `PATCH /api/drafts/{id}` (bilingual HTML drafts, see "Drafts") and
`GET /api/drafts/{id}/pdf` (see "PDF export"), and `POST /api/transcribe` (see "Speech to text").
Not implemented: TTS, complaints, and all P1 endpoints.

## Setup (Windows, Python 3.14)

```
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
```

`pip.exe` may be blocked by policy; always use `python -m pip`.

## Run (from the repository root, `D:\Kural`)

```
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --port 8000
```

Run from the repo root: the app is imported as `backend.main`. The `.env` file is
found relative to the repo, so the shell's working directory only matters for the import.

## Test

```
.\.venv\Scripts\python.exe -m pytest -q
```

## Choosing online or offline mode

One setting, `MODEL_MODE`, selects the provider. Nothing else changes the code path.

| | `MODEL_MODE=online` | `MODEL_MODE=offline` |
|---|---|---|
| Provider | Gemini API (`generativelanguage.googleapis.com`) | Ollama on this machine |
| Required | `GEMINI_API_KEY`, `GEMINI_MODEL` | `OLLAMA_MODEL`, and `OLLAMA_URL` if not `http://localhost:11434` |
| Sends complaint text/photos to | Google (Gemini API) | only `OLLAMA_URL` |
| Also used | `MODEL_TIMEOUT_S` (default 30) | `MODEL_TIMEOUT_S` |

- Model IDs are never guessed or defaulted: an empty `GEMINI_MODEL` / `OLLAMA_MODEL` is a
  configuration error. Google's Gemma-on-Gemini-API page lists `gemma-4-31b-it` and
  `gemma-4-26b-a4b-it`; the Ollama tag for E4B is reported as `gemma4:e4b`. Neither
  has been confirmed against a live account/server by this project.
- In offline mode `OLLAMA_URL` must be a loopback/private address, `localhost`, or a
  single-label host name; anything else is rejected, and Gemini is never constructed.
  Requests to Ollama ignore system proxy settings.
- API keys live only in `.env` (git-ignored). They are sent in a request header, never
  in a URL, and never logged or returned in errors.

### Test the provider connection manually

```
.\.venv\Scripts\python.exe -m backend.provider_check
```

It uses your `.env`, contacts only the selected provider, sends no complaint data and
prints no secrets. It checks that the service answers and the configured model exists;
it does **not** test generation. Exit codes: 0 ok, 1 provider unreachable or model
missing, 2 not configured.

### When a provider is unavailable

| Situation | Response |
|---|---|
| Key/model not set, bad `OLLAMA_URL`, connection refused, 401/403/404/429/5xx | `503 MODEL_UNAVAILABLE` |
| No reply within `MODEL_TIMEOUT_S` | `504 MODEL_TIMEOUT` |
| Reply not valid after one retry | `422 MODEL_INVALID_OUTPUT` |

No session is created or changed on any of these; there are no fake extraction results.
`/api/health` only reports the configured mode and model, not reachability.

## API behaviour (Phase 2)

`POST /api/sessions` (multipart): `text`, `language` (`ta`|`en`), optional `photos` (0-3
JPEG/PNG/WebP), optional `lat`/`lon`. Returns `session_id`, `status`
(`needs_info` | `photo_mismatch` | `not_civic` | `ready`), `extraction`, `decision`,
`ward`, `follow_up_questions`, and `notice` (only for `not_civic`).

`POST /api/sessions/{id}/answers` (JSON `{"answers": {...}}`), allowed keys:
`location_text` (alias `location`), `area` (appended to the location), `duration`,
`photo_mismatch` (value `confirm` to keep a photo flagged as not matching; to retake a
photo, start a new session). At most 2 rounds of questions; after that the missing
fields stay blank. Only `location_text` is ever asked; `duration` is optional.
Answers are accepted only while the status is `needs_info` or `photo_mismatch` (else 400).

The route (`decision`) is always computed by `services/routing.py`. The model only
fills `Extraction`; a reply containing a `route` (or any unknown field) is rejected.

**Spoken complaints (transcript safety).** Speech recognition can be wrong, and a wrong word can
change the category or the route, so a transcript is never treated as the complaint until the
citizen has read and, if needed, corrected it. `POST /api/sessions` therefore also accepts:

- `input_source` = `typed` (default, so existing clients are unchanged) | `speech`.
- `transcript_confirmed` = `true` | `false` (default `false`). With `input_source=speech` and no
  `transcript_confirmed=true` the request is a `400 BAD_INPUT` and nothing is extracted or stored.
  The client must send the **corrected** text in `text`; that is what is stored and extracted.
- Text with no readable letters or digits (for example only punctuation) is a `400`, never a
  `not_civic` result. A failed or empty transcription is already an error on `/api/transcribe`
  (`503`/`504`/`400`) and creates no session, so a failure can never become a complaint.
- A location the model reports that does not appear in the citizen's own words (text or answers)
  is dropped and asked about as a follow-up question; it is never used to match earlier complaints.

Not covered: a wrong word that still yields a plausible sentence (the confirmation step is the
safeguard), and `wants_records` / `user_says_ignored`, which come from the model's reading of
the confirmed text. The `/api/transcribe` response is unchanged (no confidence score yet).

## What is tested with mocks, and what needs a real provider

- **Mocked / offline (the whole automated suite, no network, no key, no Ollama):**
  request shapes, response parsing, error mapping, timeouts, provider selection,
  retry logic, validation, session flow, privacy checks (which hosts are contacted,
  no secrets in logs).
- **Requires a real provider and has NOT been verified:** that your Gemini key and
  `GEMINI_MODEL` work; that Gemma accepts `inline_data` images and returns usable JSON
  via the Gemini API without a JSON mode; that Ollama's `format` schema constraint
  works with the Gemma 4 tag; actual extraction quality, Tamil quality and speed.

## Drafts (Phase 3, step 1)

`POST /api/drafts` body: `{"session_id", "complainant": {"name", "address", "phone"?}, "route_override"?}`.
Allowed only when the session status is `ready` (otherwise `409 SESSION_NOT_READY`;
unknown session `404`; no matching department `422 NO_DEPARTMENT`; unknown fields `400`).
Several drafts per session are allowed. The response adds trust flags to the PRD shape:
`route` (effective route), `route_override`, `department_verified`, `portal_fields_verified`.

- The route is the session's deterministic rule decision (`decision`, never replaced).
  A `route_override` is stored beside it, and only when it differs from the rule's route.
- The department comes from `departments.json`. While a record is unverified the document
  carries a visible DEMO banner and the next steps state **no** response time. A response
  time is quoted only for a verified department, from its configured `response_days`.
- `portal_fields.json` holds the form labels per route. Today it is an unverified placeholder
  with only the two labels printed in the PRD example (`cm_helpline`); the PRD defines none
  for `local_body` or `rti`. Replace them with the recorded real labels and set `verified`.
- Templates (`backend/templates/`) contain neutral labels only: no legal citations, fees or
  deadlines. `local_body` and `cm_helpline` share `grievance.html`; `rti` uses `rti.html`.
  Next-step wording lives in `rules.json` (`next_steps`). All Tamil wording is machine-drafted
  and needs native-speaker review.

`PATCH /api/drafts/{id}` body: `{"fields": {...}, "complainant": {...}}` (both optional, at
least one required). Editable `fields`: `summary_en`, `summary_ta`, `location_text`, `duration`
(location and duration may be cleared; summaries may not). Complainant fields may be changed
partially (`phone` may be cleared). Any other key is rejected with `400`, so legal wording,
route logic and department data cannot be overwritten. Edits are stored on the draft and the
document is re-rendered; output is HTML-escaped.

## PDF export (Phase 3, step 2)

`GET /api/drafts/{id}/pdf` returns `application/pdf` (`Content-Disposition: attachment;
filename="kural_<route>_<draft_id>.pdf"`, route = effective route; `Cache-Control: no-store`).
It renders the draft document (reflecting any edits) and, when the session has photos, adds one
evidence page with up to 3 photos (downscaled to 1600 px for the PDF; stored originals are never
changed). A missing or unreadable photo shows "Photo unavailable" instead of failing.

- Fonts: the bundled Noto Sans Tamil variable font (`backend/fonts/`, SIL OFL 1.1, see `SOURCE.md`).
  WeasyPrint creates the Regular and Bold instances itself. A missing font or engine returns
  `503 PDF_UNAVAILABLE` (an error code not in the PRD); the rest of the API keeps working.
- The renderer can load only `data:` URIs and that one font file, so template text can never make it
  read other files or contact the network. The PDF is built in memory, never written to disk or logged.
- Verified by rendering pages to images and looking at them: Tamil shaping (split vowels, conjuncts,
  digits), bold, the DEMO banner, the evidence page. Not verified: how other PDF viewers or printers
  render it. The PDF's **text layer is unreliable for Tamil** (extraction drops some vowel signs such
  as ை), so copy/paste and search of the Tamil text may be wrong even though it displays correctly.
- Dev tools: `pip install -r requirements-dev.txt` adds `pypdf` (used by the tests) and `pypdfium2`
  (optional, only for rendering PDF pages to images by hand).

## Speech to text (Phase 3, step 3c)

`POST /api/transcribe` (multipart: `audio` = WebM or WAV, `language` = `ta` | `en`) returns
`{"transcript", "language", "engine": "whisper"}`. It runs entirely on this machine with
faster-whisper (CPU, int8) and the model in `STT_MODEL_DIR` (default
`backend/data/models/whisper/small`, installed and checked by `scripts/download_stt_model.py`).

- **Set `STT_ENGINE=whisper`** (now the code default and in `.env.example`). `gemma` and `indic`
  are accepted values but not implemented: they return `503` after the upload is validated.
  An existing `.env` that still says `STT_ENGINE=gemma` must be edited.
- **Errors:** `400 BAD_INPUT` (empty, unsupported or corrupt audio, wrong declared type, too large,
  too long, bad language, no speech found), `503 MODEL_UNAVAILABLE` (model folder missing or
  corrupt, package missing, engine not implemented, model failure, service busy),
  `504 MODEL_TIMEOUT` (over `STT_TIMEOUT_S`).
- **Limits:** `MAX_AUDIO_MB` (10), `MAX_AUDIO_S` (300), `STT_TIMEOUT_S` (120). Audio over 30 s is
  split into chunks of at most `AUDIO_CHUNK_S` at quiet points and the texts are joined.
  Only WebM and WAV are accepted (decided by the file header, not the name or declared type).
- **Safeguards:** audio is decoded with PyAV from memory (not `faster_whisper.decode_audio`, which
  is broken with PyAV 19); speech is pre-filtered with the bundled voice-activity model; Whisper's
  temperature fallback is off (on noise it took 34-42 s for 3 s of Tamil-mode audio in a measured
  test); one lazily loaded model, one transcription at a time, at most 3 requests in flight;
  language is fixed (no detection) and nothing is translated.
- **Privacy:** the model loads with `local_files_only` and `HF_HUB_OFFLINE=1`; audio and transcripts
  are never stored or logged (only sizes and timings). Uploads over 1 MB are spooled to a temporary
  file by the web framework while the request runs and removed afterwards.
- **Measured (3 s of synthetic audio, not speech):** model load 2.0 s, peak memory 0.92 GB working
  set / 1.44 GB commit. **Not measured:** speed and accuracy on real Tamil or English speech.
  Tamil transcription quality is unverified until tested against reviewed recordings.
- **Synthetic-speech benchmark (one English and one Tamil text-to-speech clip, the `small` model,
  not human speech):** English WER 11.8% / CER 1.1%; Tamil WER 83.3% / CER 13.5% (e.g. a street
  word heard as a different Tamil word). These single synthetic clips do **not** estimate real-world
  accuracy; no real human recordings have been tested. Treat Tamil as not production-ready and
  keep the transcript-confirmation step. A `medium` model was not tested (larger, slower, more RAM).
- **Import diagnostics:** a missing package, a missing dependency and a package that exists but
  cannot load (damaged, or blocked by a Windows security policy) are reported separately. The API
  message stays generic; the log and the benchmark's `Cause:` line carry a short, path-free detail.
- **Windows Smart App Control:** it can block brand-new unsigned native files in the virtual
  environment. `av` is pinned to 17.1.0 (19.0.2 was blocked) and `fontTools` uses its pure-Python
  wheel. `_brotli` is also blocked but harmless here: fontTools only uses it for WOFF2 fonts and
  falls back cleanly (verified: `fontTools.ttLib.woff2` imports with `haveBrotli = False`, and
  WeasyPrint PDF generation passes its tests). If another native file is blocked, the log names it.

### Benchmarking STT on your own recordings

`scripts/stt_benchmark.py` runs Kural's real STT pipeline on recordings you provide and reports
character, letter (aksharam) and word error rates, speed and memory, with the reference and the
transcript side by side. Put WebM/WAV files in `audio_samples/` (git-ignored) with a matching UTF-8
`.txt` holding exactly what was said, named `ta_...` or `en_...` (or pass `--language`):

```
.\.venv\Scripts\python.exe scripts\stt_benchmark.py --list     # lists clips; decodes nothing, loads no model
.\.venv\Scripts\python.exe scripts\stt_benchmark.py            # runs the benchmark
```

Options: `--beam N`, `--threads N`, `--repeat N`, `--model-dir DIR`, `--report FILE` (must be inside
`audio_samples/`). It reports numbers only and sets no pass/fail threshold. It never reads `.env`,
stays offline, and writes nothing unless `--report` is given. Its console output contains your
transcripts, so treat it as private. Use fictional content in recordings you do not want stored.

## WeasyPrint on Windows

WeasyPrint needs the Pango libraries. This machine uses MSYS2
(`pacman -S mingw-w64-x86_64-pango`). WeasyPrint searches `C:\msys64\ucrt64\bin`
and `C:\msys64\mingw64\bin` by default, so nothing needs configuring in that case.
If the libraries are elsewhere, set the **process environment** variable
`WEASYPRINT_DLL_DIRECTORIES` to that folder before starting the server. Putting it
in `.env` has no effect. Tamil font rendering (Noto Sans Tamil) is not yet verified.

## Data caveat

`backend/data/departments.json` contains **demo placeholders only** (`verified: false`,
names prefixed `[DEMO]`). None of its names, addresses, submission channels or
`response_days` values are official. The server logs a warning at startup while any
unverified record is loaded. `rules.json` Tamil text (reasons, follow-up question,
not-civic notice) needs native-speaker review.
