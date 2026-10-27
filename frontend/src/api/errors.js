// Error codes with a citizen-facing message in i18n (error.<CODE>). Section 7 of the API spec, plus NETWORK.
const KNOWN = new Set([
  'BAD_INPUT',
  'NOT_FOUND',
  'SESSION_NOT_READY',
  'MODEL_INVALID_OUTPUT',
  'NO_DEPARTMENT',
  'MODEL_UNAVAILABLE',
  'MODEL_TIMEOUT',
  'PDF_UNAVAILABLE',
  'NETWORK',
])

export class ApiError extends Error {
  constructor(code, status = 0, message = code) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
  }
}

/** i18n key of the friendly message for any thrown error. */
export function errorKey(err) {
  return KNOWN.has(err?.code) ? `error.${err.code}` : 'error.UNKNOWN'
}
