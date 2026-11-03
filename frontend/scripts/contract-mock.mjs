import http from 'node:http'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
const fixture = JSON.parse(fs.readFileSync(path.join(root, 'contracts/v1/fixtures.json'), 'utf8'))
const pdf = fs.readFileSync(path.join(root, 'frontend/public/cats-demo.pdf'))
const port = Number(process.env.MOCK_PORT || 8000)
const order = ['probe', 'next', 'retry', 'retry_again', 'incomplete', 'finish']
let session = null
let index = 0
const replay = new Map()

function send(response, status, body, type = 'application/json') {
  response.writeHead(status, { 'Content-Type': type, 'Cache-Control': 'no-store' })
  response.end(type === 'application/json' ? JSON.stringify(body) : body)
}
function tagged(body) { return { ...body, model_source: 'test_fake', test_mode: true } }
function state() {
  const source = index === 0 ? fixture.session_start : fixture.responses[order[index - 1]]
  return tagged({
    ...source,
    question: source.question ?? source.next_question,
    deck_id: 'deck_fixture', filename: 'cats-demo.pdf', page_count: 6,
    session_id: 'ses_fixture',
    attempts: source.attempts || [], history: source.history || [], coverage: source.coverage || [],
    completed: source.completed || false,
  })
}

const server = http.createServer(async (request, response) => {
  const pathname = new URL(request.url, 'http://localhost').pathname
  if (request.method === 'GET' && pathname === '/api/ready') return send(response, 200, tagged(fixture.readiness))
  if (request.method === 'POST' && pathname === '/api/decks') return send(response, 200, tagged(fixture.deck_upload))
  if (request.method === 'GET' && pathname === '/api/decks/deck_fixture/file') return send(response, 200, pdf, 'application/pdf')
  if (request.method === 'POST' && pathname === '/api/sessions') {
    session = 'ses_fixture'; index = 0; replay.clear()
    return send(response, 200, tagged(fixture.session_start))
  }
  if (request.method === 'GET' && pathname === '/api/sessions/ses_fixture') {
    if (!session) return send(response, 404, { status: 'error', error: { code: 'NOT_FOUND', message: 'ไม่พบ session' } })
    return send(response, 200, state())
  }
  if (request.method === 'GET' && pathname === '/api/sessions/ses_fixture/report') {
    if (index < order.length) return send(response, 409, { status: 'error', error: { code: 'SESSION_NOT_COMPLETE', message: 'ยังซ้อมไม่ครบ' } })
    return send(response, 200, tagged(fixture.report))
  }
  if (request.method === 'POST' && pathname === '/api/sessions/ses_fixture/answers') {
    let body
    try { body = JSON.parse(await new Promise((resolve, reject) => { let raw = ''; request.on('data', (part) => raw += part); request.on('end', () => resolve(raw)); request.on('error', reject) })) }
    catch { return send(response, 400, { status: 'error', error: { code: 'INVALID_JSON', message: 'JSON ไม่ถูกต้อง' } }) }
    const previous = replay.get(body.attempt_id)
    if (previous) return send(response, previous.request === JSON.stringify(body) ? 200 : 409, previous.request === JSON.stringify(body) ? previous.response : { status: 'error', error: { code: 'ATTEMPT_CONFLICT', message: 'attempt_id ถูกใช้แล้ว' } })
    const active = state()
    if (!body.attempt_id || !body.answer || body.state_version !== active.state_version || body.question_id !== active.question?.id || index >= order.length) {
      return send(response, 409, { status: 'error', error: { code: 'STATE_CONFLICT', message: 'สถานะไม่ตรง' } })
    }
    const result = tagged(fixture.responses[order[index]])
    index += 1
    replay.set(body.attempt_id, { request: JSON.stringify(body), response: result })
    return send(response, 200, result)
  }
  send(response, 404, { status: 'error', error: { code: 'NOT_FOUND', message: 'ไม่พบเส้นทาง' } })
})
server.listen(port, '127.0.0.1', () => console.log(`Contract mock ready on http://127.0.0.1:${port}`))
