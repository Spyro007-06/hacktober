// Deterministic in-memory backend used when VITE_USE_MOCKS is not "false".
// Same request/response shapes as docs/frontend-requirements.pdf section 6. Only client.js imports this.
//
// Triggers (complaint text, case-insensitive):
//   "fail"               -> 504 MODEL_TIMEOUT
//   "weather" | "movie"  -> not_civic
//   "pothole" + >=1 photo -> photo_mismatch
//   anything else        -> needs_info (location_text), then ready: cm_helpline / R3
import { ApiError } from './errors.js'

let seq = 0x100
const newId = (prefix) => `${prefix}_${(seq++).toString(16)}`
const clone = (v) => structuredClone(v)

const today = () => new Date().toLocaleDateString('en-CA') // YYYY-MM-DD in local time
function addDays(iso, n) {
  const d = new Date(`${iso}T00:00:00`)
  d.setDate(d.getDate() + n)
  return d.toLocaleDateString('en-CA')
}
const daysBetween = (fromIso, toIso) =>
  Math.round((new Date(`${toIso}T00:00:00`) - new Date(`${fromIso}T00:00:00`)) / 86400000)

const escapeHtml = (s) =>
  String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c])

// ---------- reference data ----------

const DECISIONS = {
  local_body: {
    route: 'local_body',
    rule_id: 'R1',
    reason_en: 'This is a first complaint about a local civic problem, so it goes to your local body.',
    reason_ta: 'இது உள்ளூர் குடிமைப் பிரச்சினை பற்றிய முதல் புகார், எனவே இது உங்கள் உள்ளாட்சி அமைப்புக்குச் செல்கிறது.',
    escalation_level: 0,
  },
  cm_helpline: {
    route: 'cm_helpline',
    rule_id: 'R3',
    reason_en: 'Your earlier complaints were ignored, so this goes to the CM Helpline.',
    reason_ta: 'உங்கள் முந்தைய புகார்கள் கவனிக்கப்படவில்லை, எனவே இது முதல்வர் உதவி மையத்துக்குச் செல்கிறது.',
    escalation_level: 1,
  },
  rti: {
    route: 'rti',
    rule_id: 'R5',
    reason_en: 'You asked for official records, so this is an RTI application.',
    reason_ta: 'நீங்கள் அதிகாரப்பூர்வ பதிவுகளைக் கேட்டுள்ளீர்கள், எனவே இது தகவல் அறியும் உரிமை மனு.',
    escalation_level: 0,
  },
}

const DEPARTMENTS = {
  local_body: {
    id: 'muni-ward-office',
    name: 'Assistant Engineer, Ward Office, City Municipal Corporation',
    address: 'Ward Office, Gandhi Road',
    submit_via: 'In person at the ward office',
    response_days: 15,
  },
  cm_helpline: {
    id: 'muni-electrical',
    name: 'Executive Engineer (Electrical), City Municipal Corporation',
    address: 'Municipal Office, Main Road',
    submit_via: 'CM Helpline portal or phone 1100',
    response_days: 30,
  },
  rti: {
    id: 'muni-pio',
    name: 'Public Information Officer, City Municipal Corporation',
    address: 'Municipal Office, Main Road',
    submit_via: 'By post with the Rs. 10 application fee',
    response_days: 30,
  },
}

const SUBJECTS = {
  local_body: ['Complaint regarding a civic problem', 'குடிமைப் பிரச்சினை தொடர்பான புகார்'],
  cm_helpline: ['Grievance petition to the CM Helpline', 'முதல்வர் உதவி மையத்துக்கான குறைதீர் மனு'],
  rti: ['Application under the Right to Information Act, 2005', 'தகவல் அறியும் உரிமைச் சட்டம், 2005-இன் கீழ் மனு'],
}

const TRANSCRIPTS = {
  ta: 'எங்கள் தெருவில் உள்ள தெருவிளக்கு மூன்று மாதங்களாக எரியவில்லை. இரண்டு முறை புகார் கொடுத்தும் யாரும் சரிசெய்யவில்லை.',
  en: 'The streetlight on our street has not worked for three months. We complained twice and nobody fixed it.',
}

// ---------- state ----------

let modelMode = 'online'
const sessions = new Map() // id -> { session, rounds }
const drafts = new Map() // id -> draft record (internal)
const complaints = seedComplaints()

// Mock mode only: sessions and filed complaints survive a page refresh so session recovery can be
// demoed. Drafts (names, addresses) are never persisted; a refresh on Draft returns to Route anyway.
const MOCK_KEY = 'kural.mock'
try {
  const saved = JSON.parse(globalThis.sessionStorage?.getItem(MOCK_KEY) ?? 'null')
  if (saved) {
    seq = saved.seq
    for (const [id, rec] of saved.sessions) sessions.set(id, rec)
    complaints.splice(0, complaints.length, ...saved.complaints)
  }
} catch {
  // No storage (Node self-check, private mode): start fresh.
}
function saveMock() {
  try {
    globalThis.sessionStorage?.setItem(MOCK_KEY, JSON.stringify({ seq, sessions: [...sessions], complaints }))
  } catch {
    // ignore
  }
}

function seedComplaints() {
  const t = today()
  const row = (id, title, route, category, location_text, filedAgo, days, status) => ({
    id,
    draft_id: `d_seed_${id}`,
    title,
    route,
    category,
    location_text,
    ward: null,
    filed_on: addDays(t, -filedAgo),
    due_on: addDays(t, -filedAgo + days),
    status,
    parent_complaint_id: null,
  })
  return [
    row('c_seed1', 'Streetlight, Gandhi Street', 'cm_helpline', 'streetlight', 'Gandhi Street', 10, 30, 'filed'),
    row('c_seed2', 'Garbage not cleared, Nehru Nagar', 'local_body', 'garbage', 'Nehru Nagar', 40, 15, 'overdue'),
    row('c_seed3', 'Water leak, Anna Salai', 'local_body', 'water', 'Anna Salai', 60, 15, 'resolved'),
    row('c_seed4', 'Blocked drain, Market Road', 'local_body', 'drainage', 'Market Road', 50, 15, 'escalated'),
  ]
}

// ---------- sessions ----------

function baseExtraction(overrides) {
  return {
    category: 'streetlight',
    summary_en: 'The streetlight on the street has not worked for 3 months despite 2 earlier complaints.',
    summary_ta: 'தெருவில் உள்ள தெருவிளக்கு, இரண்டு முறை புகார் அளித்தும், 3 மாதங்களாக எரியவில்லை.',
    location_text: null,
    duration: '3 months',
    severity: 'medium',
    photo_findings: [],
    photo_matches_claim: true,
    photo_mismatch_note: null,
    wants_records: false,
    user_says_ignored: true,
    requested_info: [],
    missing_fields: [],
    ...overrides,
  }
}

function getRecord(id) {
  const rec = sessions.get(id)
  if (!rec) throw new ApiError('NOT_FOUND', 404, `session ${id} not found`)
  return rec
}

export function health() {
  return { status: 'ok', model_mode: modelMode, model: 'gemma-4' }
}

export function setMode({ mode }) {
  if (mode !== 'online' && mode !== 'offline') throw new ApiError('BAD_INPUT', 400, 'mode must be online or offline')
  modelMode = mode
  return health()
}

export function transcribe({ audio, language }) {
  if (!audio) throw new ApiError('BAD_INPUT', 400, 'audio is required')
  return { transcript: TRANSCRIPTS[language] ?? TRANSCRIPTS.ta, language, engine: 'mock' }
}

export function createSession({ text, photos = [] }) {
  if (!text?.trim()) throw new ApiError('BAD_INPUT', 400, 'text is required')
  if (photos.length > 3) throw new ApiError('BAD_INPUT', 400, 'max 3 photos')

  const lower = text.toLowerCase()
  if (lower.includes('fail')) throw new ApiError('MODEL_TIMEOUT', 504, 'mock timeout')

  const session = { session_id: newId('s'), status: 'needs_info', extraction: null, decision: null, ward: null, follow_up_questions: [] }

  if (lower.includes('weather') || lower.includes('movie')) {
    session.status = 'not_civic'
    session.extraction = baseExtraction({ category: 'other', summary_en: '', summary_ta: '', duration: null, user_says_ignored: false })
  } else if (lower.includes('pothole') && photos.length >= 1) {
    session.status = 'photo_mismatch'
    session.extraction = baseExtraction({
      category: 'pothole',
      summary_en: 'There is a large pothole on the road that has not been repaired.',
      summary_ta: 'சாலையில் உள்ள பெரிய பள்ளம் சரிசெய்யப்படவில்லை.',
      duration: null,
      user_says_ignored: false,
      location_text: 'Kamarajar Road',
      photo_findings: ['Overflowing garbage bin'],
      photo_matches_claim: false,
      photo_mismatch_note: 'The photo shows an overflowing garbage bin, but the complaint is about a pothole.',
    })
  } else {
    session.extraction = baseExtraction({ missing_fields: ['location_text'] })
    session.follow_up_questions = [
      { field: 'location_text', question_en: 'Which street is this on?', question_ta: 'இது எந்தத் தெருவில் உள்ளது?' },
    ]
  }
  sessions.set(session.session_id, { session, rounds: 0 })
  saveMock()
  return clone(session)
}

export function answerSession(id, { answers = {}, confirm_photo_mismatch = false } = {}) {
  const rec = getRecord(id)
  const s = rec.session

  if (s.status === 'photo_mismatch' && confirm_photo_mismatch) {
    Object.assign(s, { status: 'ready', decision: clone(DECISIONS.local_body), follow_up_questions: [] })
  } else if (s.status === 'needs_info') {
    rec.rounds += 1
    for (const field of s.extraction.missing_fields) {
      const value = answers[field]?.trim?.()
      if (value) s.extraction[field] = value
    }
    s.extraction.missing_fields = s.extraction.missing_fields.filter((f) => !s.extraction[f])
    s.follow_up_questions = s.follow_up_questions.filter((q) => s.extraction.missing_fields.includes(q.field))
    // Backend stops asking after 2 rounds and continues with what is filled.
    if (s.extraction.missing_fields.length === 0 || rec.rounds >= 2) {
      Object.assign(s, { status: 'ready', decision: clone(DECISIONS.cm_helpline), follow_up_questions: [] })
    }
  }
  saveMock()
  return clone(s)
}

export function getSession(id) {
  return clone(getRecord(id).session)
}

// ---------- drafts ----------

const EDITABLE = ['summary_en', 'summary_ta', 'location_text', 'duration', 'requested_info']

function renderDraft(d) {
  const dept = DEPARTMENTS[d.decision.route]
  const f = d.fields
  const [subjectEn, subjectTa] = SUBJECTS[d.decision.route]
  const info = f.requested_info.length
    ? `<ol>${f.requested_info.map((i) => `<li>${escapeHtml(i)}</li>`).join('')}</ol>`
    : ''

  const html = `<!doctype html><html><head><meta charset="utf-8"><style>
body{font-family:"Noto Sans Tamil","Noto Sans",sans-serif;color:#202923;margin:0;padding:40px 44px;line-height:1.7;font-size:15px}
h1{font-size:18px;margin:0 0 4px}h2{font-size:15px;margin:28px 0 6px;color:#245C45}
.meta{color:#626B64;font-size:13px}.block{margin:18px 0}hr{border:0;border-top:1px solid #E3E5DC;margin:28px 0}
.sign{margin-top:36px}
</style></head><body>
<p class="meta">${escapeHtml(d.created_on)} · ${escapeHtml(d.draft_id)}</p>
<div class="block"><strong>To / பெறுநர்:</strong><br>${escapeHtml(dept.name)}<br>${escapeHtml(dept.address)}</div>
<h1>${escapeHtml(subjectTa)}</h1><p class="meta">${escapeHtml(subjectEn)}</p>
<h2>தமிழ்</h2>
<p>${escapeHtml(f.summary_ta)}</p>
<p><strong>இடம்:</strong> ${escapeHtml(f.location_text || '—')} · <strong>காலம்:</strong> ${escapeHtml(f.duration || '—')}</p>
<h2>English</h2>
<p>${escapeHtml(f.summary_en)}</p>
<p><strong>Location:</strong> ${escapeHtml(f.location_text || '—')} · <strong>Duration:</strong> ${escapeHtml(f.duration || '—')}</p>
${info ? `<h2>Information requested / கோரப்படும் தகவல்</h2>${info}` : ''}
<p>I request you to take action on this within ${dept.response_days} days. / இதன் மீது ${dept.response_days} நாட்களுக்குள் நடவடிக்கை எடுக்கக் கோருகிறேன்.</p>
<hr>
<div class="sign"><strong>${escapeHtml(d.complainant.name)}</strong><br>${escapeHtml(d.complainant.address)}${d.complainant.phone ? `<br>${escapeHtml(d.complainant.phone)}` : ''}</div>
</body></html>`

  return {
    draft_id: d.draft_id,
    decision: clone(d.decision),
    department: clone(dept),
    html,
    portal_fields: {
      'Grievance details': `${f.summary_en} Location: ${f.location_text || 'not stated'}.`,
      'Grievance category': d.category,
      'Department': dept.name,
      'Communication address': `${d.complainant.name}, ${d.complainant.address}`,
      'Mobile number': d.complainant.phone || '',
    },
    next_steps: {
      en: `Submit this document via: ${dept.submit_via}. Keep the reference number. The office should reply within ${dept.response_days} days.`,
      ta: `இந்த ஆவணத்தைச் சமர்ப்பிக்கவும்: ${dept.submit_via}. குறிப்பு எண்ணைப் பாதுகாத்து வைக்கவும். ${dept.response_days} நாட்களுக்குள் அலுவலகம் பதிலளிக்க வேண்டும்.`,
    },
    editable_fields: clone(f),
  }
}

function storeDraft({ decision, category, fields, complainant, parent_complaint_id = null }) {
  const d = { draft_id: newId('d'), created_on: today(), decision, category, fields, complainant, parent_complaint_id }
  drafts.set(d.draft_id, d)
  return renderDraft(d)
}

export function createDraft({ session_id, complainant, route_override = null }) {
  const s = getRecord(session_id).session
  if (s.status !== 'ready') throw new ApiError('SESSION_NOT_READY', 409, 'session is not ready')
  if (!complainant?.name?.trim() || !complainant?.address?.trim()) {
    throw new ApiError('BAD_INPUT', 400, 'complainant name and address are required')
  }
  if (route_override && !DECISIONS[route_override]) throw new ApiError('BAD_INPUT', 400, 'unknown route')

  const { route, rule_id, escalation_level } = s.decision
  const e = s.extraction
  return storeDraft({
    decision: { route: route_override ?? route, rule_id, escalation_level },
    category: e.category,
    fields: {
      summary_en: e.summary_en,
      summary_ta: e.summary_ta,
      location_text: e.location_text ?? '',
      duration: e.duration ?? '',
      requested_info: [...e.requested_info],
    },
    complainant: { name: complainant.name.trim(), address: complainant.address.trim(), phone: complainant.phone?.trim() ?? '' },
  })
}

export function updateDraft(id, { fields = {}, complainant = {} } = {}) {
  const d = drafts.get(id)
  if (!d) throw new ApiError('NOT_FOUND', 404, `draft ${id} not found`)
  const bad = Object.keys(fields).filter((k) => !EDITABLE.includes(k))
  if (bad.length) throw new ApiError('BAD_INPUT', 400, `not editable: ${bad.join(', ')}`)
  Object.assign(d.fields, clone(fields))
  Object.assign(d.complainant, complainant)
  return renderDraft(d)
}

export function tts() {
  throw new ApiError('TTS_UNAVAILABLE', 501, 'no offline TTS engine in mock mode')
}

// ---------- complaints ----------

export function fileComplaint({ draft_id, filed_on }) {
  const d = drafts.get(draft_id)
  if (!d) throw new ApiError('NOT_FOUND', 404, `draft ${draft_id} not found`)
  if (!/^\d{4}-\d{2}-\d{2}$/.test(filed_on ?? '')) throw new ApiError('BAD_INPUT', 400, 'filed_on must be YYYY-MM-DD')

  const existing = complaints.find((c) => c.draft_id === draft_id)
  if (existing) return publicComplaint(existing)

  const c = {
    id: newId('c'),
    draft_id,
    title: `${d.category[0].toUpperCase()}${d.category.slice(1)}, ${d.fields.location_text || 'location not stated'}`,
    route: d.decision.route,
    category: d.category,
    location_text: d.fields.location_text || null,
    ward: null,
    filed_on,
    due_on: addDays(filed_on, DEPARTMENTS[d.decision.route].response_days),
    status: 'filed',
    parent_complaint_id: d.parent_complaint_id,
  }
  complaints.push(c)
  saveMock()
  return publicComplaint(c)
}

function publicComplaint(c) {
  const { title: _title, ...rest } = c
  return clone(rest)
}

export function listComplaints() {
  const t = today()
  return complaints.map((c) => ({
    id: c.id,
    draft_id: c.draft_id,
    title: c.title,
    route: c.route,
    filed_on: c.filed_on,
    due_on: c.due_on,
    days_left: daysBetween(t, c.due_on),
    status: c.status === 'filed' && c.due_on < t ? 'overdue' : c.status,
  }))
}

export function escalateComplaint(id) {
  const c = complaints.find((x) => x.id === id)
  if (!c) throw new ApiError('NOT_FOUND', 404, `complaint ${id} not found`)
  const overdue = c.status === 'overdue' || (c.status === 'filed' && c.due_on < today())
  if (!overdue) throw new ApiError('BAD_INPUT', 400, 'only overdue complaints can be escalated')
  c.status = 'escalated'
  saveMock()
  return storeDraft({
    decision: { route: 'cm_helpline', rule_id: 'R4', escalation_level: 2 },
    category: c.category,
    fields: {
      summary_en: `My complaint "${c.title}" filed on ${c.filed_on} received no reply by ${c.due_on}.`,
      summary_ta: `${c.filed_on} அன்று அளித்த "${c.title}" புகாருக்கு ${c.due_on} வரை பதில் இல்லை.`,
      location_text: c.location_text ?? '',
      duration: `${daysBetween(c.filed_on, today())} days`,
      requested_info: [],
    },
    complainant: { name: 'R. Priya', address: '14 Gandhi Street', phone: '' },
    parent_complaint_id: c.id,
  })
}
