# Kural frontend requirements

The full spec (scope F1-F17, screens, components, API contracts, error codes,
language keys, build plan) is [frontend-requirements.pdf](frontend-requirements.pdf).

The clarifications below were agreed after the PDF and **override it** where they differ.

## Contract additions (agreed with backend)

- Every draft response (`POST /api/drafts`, `PATCH /api/drafts/{id}`,
  `POST /api/complaints/{id}/escalate`) includes:

  ```json
  "editable_fields": { "summary_en": "", "summary_ta": "", "location_text": "",
                       "duration": "", "requested_info": [] }
  ```

  The frontend uses it to prefill Edit mode; `requested_info` is edited as one item per line.
- Recording uses the first supported type from
  `["audio/webm;codecs=opus", "audio/webm", "audio/mp4"]` (`MediaRecorder.isTypeSupported`)
  and sends the blob with a matching filename extension. The backend accepts webm, mp4 and wav.

## Frontend decisions

- Photos: two buttons, "Take photo" (`capture="environment"`) and "Choose from gallery"
  (no `capture`). Both share the 3-photo limit.
- Draft preview: `<iframe sandbox="" srcDoc={draft.html}>`. Never `allow-scripts` or `allow-same-origin`.
- `client.js` exports `pdfUrl(draftId)`; components use it for the download anchor.
- Session recovery: only `session_id` and the current step go in `sessionStorage`. A refresh
  recovers via `GET /api/sessions/{id}` to Clarify or Route. **Known limitation:** a refresh on
  the Draft screen returns to Route and details.

## Mock mode (`VITE_USE_MOCKS`, default on)

Deterministic triggers on the complaint text:

| Text contains | Result |
|---|---|
| `fail` | `504 MODEL_TIMEOUT` |
| `weather` or `movie` | `not_civic` |
| `pothole` with at least 1 photo | `photo_mismatch` |
| anything else | `needs_info` (one question about `location_text`), then `ready`, route `cm_helpline`, rule `R3` |

In mock mode `pdfUrl` returns `/mock/sample.pdf` and `tts()` returns HTTP 501, so the
text-only next-steps fallback is exercised.

## Known limitations (frontend)

- A refresh on the Draft screen returns to Route and details (the draft is not persisted).
- Complaint text, photos and clips are never stored, so after a refresh the Describe text box is empty.
- An escalation draft opened from My complaints has no wizard session: it cannot go Back to Route,
  and Edit mode only covers the five editable fields (complainant details are not known there).
- In mock mode the mock backend keeps sessions and filed complaints in sessionStorage (`kural.mock`)
  so recovery can be demoed; real mode stores only `session_id` and step.
- `GET /api/complaints` items may include `route` (the mock does); the card hides it when absent.
