import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import * as api from '../api/client'

// Only the session id and step are persisted (sessionStorage), never text, photos or personal details.
const STORAGE_KEY = 'kural.session'
export const MAX_PHOTOS = 3

// Errors where retrying the same request cannot help.
const NOT_RETRYABLE = new Set(['BAD_INPUT', 'NOT_FOUND', 'SESSION_NOT_READY', 'NO_DEPARTMENT'])

const stepForStatus = (status) => (status === 'ready' ? 'route' : 'clarify')

function readStored() {
  try {
    return JSON.parse(sessionStorage.getItem(STORAGE_KEY))
  } catch {
    return null
  }
}

function writeStored(value) {
  try {
    if (value) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(value))
    else sessionStorage.removeItem(STORAGE_KEY)
  } catch {
    // Storage blocked (private mode): recovery after refresh just won't be available.
  }
}

const initialState = () => ({
  step: 'describe', // describe | clarify | route | draft | done
  complaintLang: 'ta', // sent to the backend; independent of the UI language
  text: '',
  spoken: false, // true once any voice clip was transcribed into the text
  clips: [], // { id, blob, url, seconds, status: transcribing | done | error, error }
  photos: [], // { id, file, url }
  location: null, // { lat, lon } only after the user explicitly shares it
  session: null,
  rounds: 0, // follow-up answer rounds submitted
  answers: {},
  complainant: { name: '', address: '', phone: '' },
  routeOverride: null, // operator override: local_body | cm_helpline | rti
  draft: null, // last draft response (POST/PATCH /drafts or escalate)
  filed: null, // complaint record from POST /complaints
  pending: null, // name of the in-flight wizard request
  error: null,
  retry: null,
  recovering: false,
})

const revokeAll = (s) => [...s.clips, ...s.photos].forEach((x) => URL.revokeObjectURL(x.url))
let nextId = 1

const ComplaintContext = createContext(null)

export function ComplaintProvider({ children }) {
  const [state, setState] = useState(() => ({ ...initialState(), recovering: Boolean(readStored()?.session_id) }))
  const stateRef = useRef(state)
  stateRef.current = state
  const pendingRef = useRef(null) // synchronous guard against double submits

  const update = useCallback((patch) => setState((s) => ({ ...s, ...(typeof patch === 'function' ? patch(s) : patch) })), [])

  useEffect(() => {
    if (state.session && state.step !== 'done') writeStored({ session_id: state.session.session_id, step: state.step })
  }, [state.session, state.step])

  /** Runs one wizard request at a time; failures become { error, retry } for the ErrorBanner. Resolves true on success. */
  const run = useCallback(
    async (pending, fn, retry) => {
      if (pendingRef.current) return false
      pendingRef.current = pending
      update({ pending, error: null, retry: null })
      try {
        await fn()
        return true
      } catch (error) {
        update({ error, errorFrom: pending, retry: NOT_RETRYABLE.has(error.code) ? null : retry })
        return false
      } finally {
        pendingRef.current = null
        update({ pending: null })
      }
    },
    [update],
  )

  const recover = useCallback(async () => {
    const stored = readStored()
    if (!stored?.session_id) return update({ recovering: false })
    update({ recovering: true, error: null, retry: null })
    try {
      const session = await api.getSession(stored.session_id)
      // A refresh on Draft lands on Route and details (the draft itself is not persisted).
      update({ session, step: stepForStatus(session.status), recovering: false })
    } catch (error) {
      if (error.code === 'NOT_FOUND') writeStored(null)
      update({ recovering: false, error, retry: error.code === 'NOT_FOUND' ? null : () => recover() })
    }
  }, [update])

  useEffect(() => {
    recover()
  }, [recover])

  // ---------- describe ----------

  const setClip = (id, patch) => update((s) => ({ clips: s.clips.map((c) => (c.id === id ? { ...c, ...patch } : c)) }))

  const transcribeClip = useCallback(
    async (clip) => {
      setClip(clip.id, { status: 'transcribing', error: null })
      try {
        const { transcript } = await api.transcribe(clip.blob, stateRef.current.complaintLang)
        update((s) => ({
          text: [s.text.trim(), transcript.trim()].filter(Boolean).join(' '),
          spoken: true,
          clips: s.clips.map((c) => (c.id === clip.id ? { ...c, status: 'done', error: null } : c)),
        }))
      } catch (error) {
        setClip(clip.id, { status: 'error', error })
      }
    },
    [update],
  )

  const addClip = useCallback(
    (blob, seconds) => {
      const clip = { id: nextId++, blob, url: URL.createObjectURL(blob), seconds, status: 'transcribing', error: null }
      update((s) => ({ clips: [...s.clips, clip] }))
      transcribeClip(clip)
    },
    [update, transcribeClip],
  )

  const addPhotos = useCallback(
    (files) =>
      update((s) => ({
        photos: [
          ...s.photos,
          ...files.slice(0, MAX_PHOTOS - s.photos.length).map((file) => ({ id: nextId++, file, url: URL.createObjectURL(file) })),
        ],
      })),
    [update],
  )

  const removePhoto = useCallback(
    (id) =>
      update((s) => {
        s.photos.filter((p) => p.id === id).forEach((p) => URL.revokeObjectURL(p.url))
        return { photos: s.photos.filter((p) => p.id !== id) }
      }),
    [update],
  )

  const submitDescribe = useCallback(
    () =>
      run(
        'session',
        async () => {
          const s = stateRef.current
          const session = await api.createSession({
            text: s.text.trim(),
            language: s.complaintLang,
            photos: s.photos.map((p) => p.file),
            lat: s.location?.lat,
            lon: s.location?.lon,
            spoken: s.spoken,
          })
          update({ session, rounds: 0, answers: {}, step: stepForStatus(session.status) })
        },
        () => submitDescribe(),
      ),
    [run, update],
  )

  // ---------- clarify ----------

  const setAnswer = useCallback((field, value) => update((s) => ({ answers: { ...s.answers, [field]: value } })), [update])

  const applySession = (session) =>
    update((s) => ({ session, rounds: s.rounds + 1, step: stepForStatus(session.status) }))

  const submitAnswers = useCallback(
    () =>
      run(
        'answers',
        async () => {
          const s = stateRef.current
          const answers = {}
          for (const { field } of s.session.follow_up_questions) {
            const value = s.answers[field]?.trim()
            if (value) answers[field] = value
          }
          applySession(await api.answerSession(s.session.session_id, { answers }))
        },
        () => submitAnswers(),
      ),
    [run],
  )

  const confirmPhotoMismatch = useCallback(
    () =>
      run(
        'answers',
        async () => {
          applySession(await api.answerSession(stateRef.current.session.session_id, { confirmPhotoMismatch: true }))
        },
        () => confirmPhotoMismatch(),
      ),
    [run],
  )

  /** Back to Describe keeping the text; photos are kept unless `clearPhotos`. A new session is created on Continue. */
  const backToDescribe = useCallback(
    ({ clearPhotos = false } = {}) => {
      writeStored(null)
      update((s) => {
        if (clearPhotos) s.photos.forEach((p) => URL.revokeObjectURL(p.url))
        return { step: 'describe', session: null, rounds: 0, error: null, retry: null, ...(clearPhotos && { photos: [] }) }
      })
    },
    [update],
  )

  const startOver = useCallback(() => {
    if (pendingRef.current) return
    writeStored(null)
    revokeAll(stateRef.current)
    setState(initialState())
  }, [])

  // ---------- route, draft, file ----------

  const generateDraft = useCallback(
    () =>
      run(
        'draft',
        async () => {
          const s = stateRef.current
          try {
            const draft = await api.createDraft({
              sessionId: s.session.session_id,
              complainant: { name: s.complainant.name.trim(), address: s.complainant.address.trim(), phone: s.complainant.phone.trim() },
              routeOverride: s.routeOverride,
            })
            update({ draft, filed: null, step: 'draft' })
          } catch (error) {
            // 409: the backend still needs answers; refresh the session and go back to Clarify.
            if (error.code === 'SESSION_NOT_READY') {
              const session = await api.getSession(s.session.session_id).catch(() => null)
              if (session && session.status !== 'ready') update({ session, step: 'clarify' })
            }
            throw error
          }
        },
        () => generateDraft(),
      ),
    [run, update],
  )

  /** PATCH only what changed. Resolves true when saved. */
  const saveDraft = useCallback(
    ({ fields, complainant }) =>
      run(
        'save',
        async () => {
          const draft = await api.updateDraft(stateRef.current.draft.draft_id, { fields, complainant })
          update((s) => ({ draft, complainant: { ...s.complainant, ...complainant } }))
        },
        () => saveDraft({ fields, complainant }),
      ),
    [run, update],
  )

  const markFiled = useCallback(
    () =>
      run(
        'file',
        async () => {
          const filed = await api.fileComplaint({
            draftId: stateRef.current.draft.draft_id,
            filedOn: new Date().toLocaleDateString('en-CA'), // local YYYY-MM-DD
          })
          writeStored(null)
          update({ filed, step: 'done' })
        },
        () => markFiled(),
      ),
    [run, update],
  )

  const actions = useMemo(
    () => ({
      update,
      setText: (text) => update({ text }),
      setComplaintLang: (complaintLang) => update({ complaintLang }),
      addClip,
      retryClip: transcribeClip,
      addPhotos,
      removePhoto,
      submitDescribe,
      setAnswer,
      submitAnswers,
      confirmPhotoMismatch,
      backToDescribe,
      retakePhotos: () => backToDescribe({ clearPhotos: true }),
      startOver,
      dismissError: () => update({ error: null, retry: null }),
      setComplainant: (patch) => update((s) => ({ complainant: { ...s.complainant, ...patch } })),
      setRouteOverride: (routeOverride) => update({ routeOverride }),
      generateDraft,
      saveDraft,
      markFiled,
      backToRoute: () => update({ step: 'route', error: null, retry: null }),
      setLocation: (location) => update({ location }),
      /** Open a draft that did not come from this wizard (escalation): fresh state, straight to Draft. */
      openDraft: (draft) => {
        writeStored(null)
        revokeAll(stateRef.current)
        setState({ ...initialState(), draft, step: 'draft' })
      },
    }),
    [update, addClip, transcribeClip, addPhotos, removePhoto, submitDescribe, setAnswer, submitAnswers, confirmPhotoMismatch, backToDescribe, startOver, generateDraft, saveDraft, markFiled],
  )

  const value = useMemo(() => ({ ...state, ...actions }), [state, actions])
  return <ComplaintContext.Provider value={value}>{children}</ComplaintContext.Provider>
}

export function useComplaint() {
  return useContext(ComplaintContext)
}
