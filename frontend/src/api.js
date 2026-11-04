const API_BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

export class ApiError extends Error {
  constructor(message, httpStatus = 0, code = 'NETWORK_ERROR', body = null) {
    super(message)
    this.name = 'ApiError'
    this.httpStatus = httpStatus
    this.code = code
    this.body = body
  }
}

export function deckFileUrl(deckId) {
  return `${API_BASE}/api/decks/${encodeURIComponent(deckId)}/file`
}

async function request(path, options = {}) {
  let response
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 150000)
  try {
    response = await fetch(`${API_BASE}${path}`, { ...options, signal: controller.signal })
  } catch (error) {
    if (error?.name === 'AbortError') throw new ApiError('Backend ตอบช้าเกิน 150 วินาที กรุณาลองอีกครั้ง', 0, 'TIMEOUT')
    throw new ApiError('เชื่อมต่อ Backend ไม่ได้ กรุณาตรวจว่าเซิร์ฟเวอร์ทำงานอยู่')
  } finally {
    clearTimeout(timer)
  }

  let data
  try {
    data = await response.json()
  } catch {
    throw new ApiError('Backend ส่งข้อมูลกลับมาในรูปแบบที่อ่านไม่ได้', response.status, 'INVALID_RESPONSE')
  }

  if (!response.ok || data.status === 'error') {
    throw new ApiError(data.error?.message || (response.status === 503 ? 'ระบบยังไม่พร้อม กรุณาลองอีกครั้ง' : 'เกิดข้อผิดพลาด กรุณาลองใหม่'), response.status, data.error?.code || (response.status === 503 ? 'SERVICE_UNAVAILABLE' : 'HTTP_ERROR'), data)
  }
  return data
}

export function uploadDeck(file) {
  const form = new FormData()
  form.append('file', file)
  return request('/api/decks', { method: 'POST', body: form })
}

export function startSession(deckId, difficulty = 'standard') {
  return request('/api/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ deck_id: deckId, difficulty }),
  })
}

export function answerQuestion(sessionId, submission) {
  return request(`/api/sessions/${encodeURIComponent(sessionId)}/answers`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(submission),
  })
}

export function getReady() {
  return request('/api/ready')
}

export function getSession(sessionId) {
  return request(`/api/sessions/${encodeURIComponent(sessionId)}`)
}

export function getReport(sessionId) {
  return request(`/api/sessions/${encodeURIComponent(sessionId)}/report`)
}
