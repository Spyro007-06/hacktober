// Self-check for the deterministic mock backend (src/api/mocks.js). Run: npm run check
import assert from 'node:assert/strict'
import * as m from '../src/api/mocks.js'

const photo = new File(['x'], 'p.jpg', { type: 'image/jpeg' })
const rejects = (fn, code) => assert.throws(fn, (e) => e.code === code, `expected ${code}`)

// Triggers
rejects(() => m.createSession({ text: 'it will fail', language: 'en' }), 'MODEL_TIMEOUT')
rejects(() => m.createSession({ text: '  ', language: 'en' }), 'BAD_INPUT')
rejects(() => m.createSession({ text: 'x', photos: [photo, photo, photo, photo] }), 'BAD_INPUT')
assert.equal(m.createSession({ text: 'Nice weather today' }).status, 'not_civic')
assert.equal(m.createSession({ text: 'a MOVIE review' }).status, 'not_civic')
assert.equal(m.createSession({ text: 'big pothole', photos: [photo] }).status, 'photo_mismatch')
assert.equal(m.createSession({ text: 'big pothole', photos: [] }).status, 'needs_info')

// Happy path: needs_info -> ready (cm_helpline / R3) -> draft -> edit -> file
const s = m.createSession({ text: 'Streetlight broken', language: 'ta', photos: [photo] })
assert.equal(s.status, 'needs_info')
assert.equal(s.decision, null)
assert.deepEqual(s.follow_up_questions.map((q) => q.field), ['location_text'])
rejects(() => m.createDraft({ session_id: s.session_id, complainant: { name: 'A', address: 'B' } }), 'SESSION_NOT_READY')

const ready = m.answerSession(s.session_id, { answers: { location_text: 'Gandhi Street' } })
assert.equal(ready.status, 'ready')
assert.deepEqual([ready.decision.route, ready.decision.rule_id], ['cm_helpline', 'R3'])
assert.deepEqual(m.getSession(s.session_id), ready)

rejects(() => m.createDraft({ session_id: s.session_id, complainant: { name: 'A', address: '' } }), 'BAD_INPUT')
const draft = m.createDraft({ session_id: s.session_id, complainant: { name: 'R. Priya', address: '14 Gandhi St' } })
assert.equal(draft.decision.route, 'cm_helpline')
assert.equal(draft.editable_fields.location_text, 'Gandhi Street')
assert.ok(draft.html.includes('R. Priya'))
assert.ok(Object.keys(draft.portal_fields).length > 0)
assert.ok(draft.next_steps.en && draft.next_steps.ta)

const overridden = m.createDraft({ session_id: s.session_id, complainant: { name: 'A', address: 'B' }, route_override: 'rti' })
assert.equal(overridden.decision.route, 'rti')

const edited = m.updateDraft(draft.draft_id, { fields: { summary_en: 'Edited <b>' } })
assert.equal(edited.editable_fields.summary_en, 'Edited <b>')
assert.ok(edited.html.includes('Edited &lt;b&gt;'), 'user text must be escaped in draft html')
rejects(() => m.updateDraft(draft.draft_id, { fields: { legal_text: 'x' } }), 'BAD_INPUT')
rejects(() => m.updateDraft('d_nope', { fields: {} }), 'NOT_FOUND')

const filed = m.fileComplaint({ draft_id: draft.draft_id, filed_on: '2026-10-26' })
assert.equal(filed.status, 'filed')
assert.equal(filed.due_on, '2026-11-25')
assert.equal(m.fileComplaint({ draft_id: draft.draft_id, filed_on: '2026-10-26' }).id, filed.id, 'filing twice is idempotent')

// Two rounds max: unanswered questions still end in ready
const s2 = m.createSession({ text: 'Garbage everywhere' })
assert.equal(m.answerSession(s2.session_id, { answers: {} }).status, 'needs_info')
assert.equal(m.answerSession(s2.session_id, { answers: {} }).status, 'ready')

// Photo mismatch: stays until confirmed
const pm = m.createSession({ text: 'pothole', photos: [photo] })
assert.equal(m.answerSession(pm.session_id, {}).status, 'photo_mismatch')
assert.equal(m.answerSession(pm.session_id, { answers: { photo_mismatch: 'confirm' } }).status, 'ready')

// TTS always 501 in mock mode
assert.throws(() => m.tts({ text: 'x', language: 'ta' }), (e) => e.status === 501)

// Complaints: overdue escalates into a new draft; others refuse
const list = m.listComplaints()
const overdue = list.find((c) => c.status === 'overdue')
assert.ok(overdue && list.some((c) => c.status === 'resolved') && list.some((c) => c.status === 'escalated'))
const escalated = m.escalateComplaint(overdue.id)
assert.equal(escalated.decision.escalation_level, 2)
assert.equal(m.listComplaints().find((c) => c.id === overdue.id).status, 'escalated')
rejects(() => m.escalateComplaint(list.find((c) => c.status === 'resolved').id), 'BAD_INPUT')

rejects(() => m.getSession('s_nope'), 'NOT_FOUND')
assert.equal(m.setMode({ mode: 'offline' }).model_mode, 'offline')

console.log('mocks ok')
