// The only place the frontend talks to the backend. One function per endpoint in
// docs/frontend-requirements.pdf section 6. Components never call fetch directly.
import { ApiError } from './errors.js'
import * as mock from './mocks.js'

export { ApiError, errorKey } from './errors.js'

export const USE_MOCKS = import.meta.env.VITE_USE_MOCKS !== 'false'
const MOCK_DELAY_MS = 1000

// Runs a mock handler after a realistic delay; thrown ApiErrors reject exactly like real failures.
const mocked = (handler) => new Promise((resolve) => setTimeout(resolve, MOCK_DELAY_MS)).then(handler)

async function request(method, path, { json, form, raw = false } = {}) {
  let res
  try {
    res = await fetch(`/api${path}`, {
      method,
      // Multipart: let the browser set Content-Type with the boundary.
      headers: json !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: json !== undefined ? JSON.stringify(json) : form,
    })
  } catch (err) {
    throw new ApiError('NETWORK', 0, err.message)
  }

  if (!res.ok) {
    let code = res.status === 501 ? 'TTS_UNAVAILABLE' : 'UNKNOWN'
    let message = `HTTP ${res.status}`
    try {
      const body = await res.json()
      code = body?.error?.code ?? code
      message = body?.error?.message ?? message
    } catch {
      // Non-JSON error body (e.g. proxy error page); keep the defaults.
    }
    throw new ApiError(code, res.status, message)
  }
  return raw ? res : res.json()
}

const enc = encodeURIComponent

// MediaRecorder may produce webm or mp4 depending on the browser; the backend accepts webm, mp4 and wav.
function audioFilename(blob) {
  const type = blob?.type ?? ''
  if (type.includes('mp4')) return 'clip.mp4'
  if (type.includes('wav')) return 'clip.wav'
  return 'clip.webm'
}

// ---------- endpoints ----------

export function health() {
  return USE_MOCKS ? mocked(() => mock.health()) : request('GET', '/health')
}

export function setMode(mode) {
  return USE_MOCKS ? mocked(() => mock.setMode({ mode })) : request('PUT', '/config/mode', { json: { mode } })
}

export function transcribe(audio, language) {
  if (USE_MOCKS) return mocked(() => mock.transcribe({ audio, language }))
  const form = new FormData()
  form.append('audio', audio, audioFilename(audio))
  form.append('language', language)
  return request('POST', '/transcribe', { form })
}

/** photos: File[] (0-3). lat/lon only when the user explicitly shared location. */
export function createSession({ text, language, photos = [], lat, lon }) {
  if (USE_MOCKS) return mocked(() => mock.createSession({ text, language, photos, lat, lon }))
  const form = new FormData()
  form.append('text', text)
  form.append('language', language)
  for (const photo of photos) form.append('photos', photo, photo.name)
  if (Number.isFinite(lat) && Number.isFinite(lon)) {
    form.append('lat', String(lat))
    form.append('lon', String(lon))
  }
  return request('POST', '/sessions', { form })
}

export function answerSession(sessionId, { answers = {}, confirmPhotoMismatch = false } = {}) {
  const body = { answers, confirm_photo_mismatch: confirmPhotoMismatch }
  return USE_MOCKS
    ? mocked(() => mock.answerSession(sessionId, body))
    : request('POST', `/sessions/${enc(sessionId)}/answers`, { json: body })
}

export function getSession(sessionId) {
  return USE_MOCKS ? mocked(() => mock.getSession(sessionId)) : request('GET', `/sessions/${enc(sessionId)}`)
}

export function createDraft({ sessionId, complainant, routeOverride = null }) {
  const body = { session_id: sessionId, complainant, route_override: routeOverride }
  return USE_MOCKS ? mocked(() => mock.createDraft(body)) : request('POST', '/drafts', { json: body })
}

/** Send only changed editable fields and changed complainant fields. */
export function updateDraft(draftId, { fields = {}, complainant } = {}) {
  const body = complainant ? { fields, complainant } : { fields }
  return USE_MOCKS
    ? mocked(() => mock.updateDraft(draftId, body))
    : request('PATCH', `/drafts/${enc(draftId)}`, { json: body })
}

/** URL for a plain <a download> link; no fetch needed. */
export function pdfUrl(draftId) {
  return USE_MOCKS ? '/mock/sample.pdf' : `/api/drafts/${enc(draftId)}/pdf`
}

/** Resolves to a WAV Blob. Rejects with status 501 when no TTS engine is available. */
export async function tts(text, language) {
  if (USE_MOCKS) return mocked(() => mock.tts({ text, language }))
  const res = await request('POST', '/tts', { json: { text, language }, raw: true })
  return res.blob()
}

export function fileComplaint({ draftId, filedOn }) {
  const body = { draft_id: draftId, filed_on: filedOn }
  return USE_MOCKS ? mocked(() => mock.fileComplaint(body)) : request('POST', '/complaints', { json: body })
}

export function listComplaints() {
  return USE_MOCKS ? mocked(() => mock.listComplaints()) : request('GET', '/complaints')
}

/** Returns a new draft (same shape as createDraft). */
export function escalateComplaint(complaintId) {
  return USE_MOCKS
    ? mocked(() => mock.escalateComplaint(complaintId))
    : request('POST', `/complaints/${enc(complaintId)}/escalate`)
}
