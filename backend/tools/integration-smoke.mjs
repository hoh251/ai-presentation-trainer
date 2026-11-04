// Run the actual FastAPI app with the team's actual Frontend; no fixture API server.
import assert from 'node:assert/strict'
import { spawn, execFileSync } from 'node:child_process'
import { createRequire } from 'node:module'
import net from 'node:net'
import { once } from 'node:events'
import { createHash } from 'node:crypto'
import { existsSync, mkdirSync, writeFileSync } from 'node:fs'
import { dirname, resolve, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const args = process.argv.slice(2)
const option = (name, fallback) => args.includes(name) ? args[args.indexOf(name) + 1] : fallback
const backend = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const frontend = resolve(option('--frontend', join(backend, '../../frontend')))
const python = option('--python', join(backend, '.venv/Scripts/python.exe'))
const production = args.includes('--production')
const output = resolve(option('--output', join(backend, '.integration', production ? 'production' : 'development')))
mkdirSync(output, { recursive: true })
const requireFrontend = createRequire(join(frontend, 'package.json'))
const { chromium } = requireFrontend('playwright')
const chrome = option('--chrome', 'C:/Program Files/Google/Chrome/Application/chrome.exe')
assert.ok(existsSync(chrome), 'Pass --chrome with an installed Chrome executable')
assert.ok(existsSync(python), 'Pass --python with the Backend environment interpreter')
if (production) assert.ok(existsSync(join(frontend, 'dist/index.html')), 'Build Frontend before --production')

async function freePort() {
  const socket = net.createServer()
  await new Promise(resolveReady => socket.listen(0, '127.0.0.1', resolveReady))
  const port = socket.address().port
  await new Promise(resolveClosed => socket.close(resolveClosed))
  return port
}
const port = await freePort()
const api = `http://127.0.0.1:${port}`
let backendProcess, browser, vite
let backendLogs = ''
const results = []
const pause = ms => new Promise(resolvePause => setTimeout(resolvePause, ms))
async function check(name, action) {
  try { await action(); results.push({ name, status: 'passed' }) }
  catch (error) { results.push({ name, status: 'failed', error: error.message }); console.error(`${name}: ${error.message}`) }
}
async function startBackend() {
  const command = [join(backend, 'run.py'), '--test-mode', '--port', String(port)]
  if (production) command.push('--frontend-dist', join(frontend, 'dist'))
  backendProcess = spawn(python, command, {
    cwd: dirname(backend), env: { ...process.env, TRAINER_STORAGE: join(output, 'storage'), PYTHONIOENCODING: 'utf-8' },
    stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true,
  })
  backendProcess.stdout.on('data', data => { backendLogs += data.toString() })
  backendProcess.stderr.on('data', data => { backendLogs += data.toString() })
  backendProcess.on('error', error => { backendLogs += error.message })
  for (let n = 0; n < 150; n++) {
    try { if ((await fetch(`${api}/api/ready`)).ok) return }
    catch {}
    if (backendProcess.exitCode !== null) throw new Error('Backend exited during startup')
    await pause(100)
  }
  throw new Error('Backend readiness timeout')
}
async function stopBackend() {
  if (backendProcess && backendProcess.exitCode === null) {
    const exit = once(backendProcess, 'exit')
    backendProcess.kill()
    await exit
  }
}
let page, context, origin, sid
async function state() {
  const response = await context.request.get(`${origin}/api/sessions/${sid}`)
  assert.equal(response.status(), 200)
  return response.json()
}
async function submit(text, clicks = 1) {
  await page.locator('#answer-input').fill(text)
  const pending = page.waitForResponse(r => r.url().endsWith(`/api/sessions/${sid}/answers`) && r.request().method() === 'POST')
  await page.getByRole('button', { name: 'ส่งคำตอบ', exact: true }).click({ clickCount: clicks })
  const response = await pending
  return { status: response.status(), body: await response.json(), request: response.request().postDataJSON() }
}
async function restored() {
  await page.reload({ waitUntil: 'networkidle' })
  await page.locator('#answer-input').waitFor()
}
let frontendCommit = 'unknown', frontendChanges = '', frontendDiffHash = null
try {
  frontendCommit = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: frontend, encoding: 'utf8' }).trim()
  frontendChanges = execFileSync('git', ['diff', '--stat', '--', 'src/App.jsx'], { cwd: frontend, encoding: 'utf8' }).trim()
  const frontendDiff = execFileSync('git', ['diff', '--', 'src/App.jsx'], { cwd: frontend })
  if (frontendDiff.length) frontendDiffHash = createHash('sha256').update(frontendDiff).digest('hex')
  await startBackend()
  if (!production) {
    const { createServer } = await import(pathToFileURL(requireFrontend.resolve('vite')).href)
    process.env.VITE_API_BASE_URL = ''
    vite = await createServer({ root: frontend, server: { host: '127.0.0.1', port: await freePort(), strictPort: true,
      proxy: { '/api': { target: api, changeOrigin: true } } } })
    await vite.listen()
    origin = vite.resolvedUrls.local[0].replace(/\/$/, '')
  } else origin = api
  browser = await chromium.launch({ headless: true, executablePath: chrome })
  context = await browser.newContext({ viewport: { width: 1366, height: 900 } })
  page = await context.newPage()
  page.setDefaultTimeout(12000)
  const pageErrors = [], browserApiOrigins = new Set()
  page.on('pageerror', error => pageErrors.push(error.message))
  page.on('request', request => { if (new URL(request.url()).pathname.startsWith('/api/')) browserApiOrigins.add(new URL(request.url()).origin) })
  await page.goto(origin, { waitUntil: 'networkidle' })
  await page.locator('input[type=file]').setInputFiles(join(backend, 'examples/acceptance/integration-slides.pdf'))
  const [sessionResponse] = await Promise.all([
    page.waitForResponse(r => r.url().endsWith('/api/sessions') && r.request().method() === 'POST'),
    page.getByRole('button', { name: 'เริ่มซ้อมกับ AI', exact: true }).click(),
  ])
  assert.equal(sessionResponse.status(), 200)
  const session = await sessionResponse.json()
  sid = session.session_id
  await check('Upload actual PDF, start session and render PDF canvas', async () => {
    assert.equal(session.model_source, 'test_fake')
    assert.equal(session.test_mode, true)
    await page.waitForFunction(() => [...document.querySelectorAll('.pdf-preview canvas')].some(c => c.width > 0))
    await page.locator('.pdf-preview .pdf-message').waitFor({ state: 'hidden' })
    const pdf = await context.request.get(`${origin}/api/decks/${(await state()).deck_id}/file`)
    assert.equal(pdf.headers()['content-type'], 'application/pdf')
    await page.screenshot({ path: join(output, 'practice.png'), fullPage: true })
  })
  let first
  await check('Double click records one attempt; partial answer probes in round 1', async () => {
    first = await submit('Quiet corner', 2)
    assert.equal(first.status, 200)
    assert.equal(first.body.agent_action, 'probe')
    assert.equal(first.body.next_question.id, session.question.id)
    const current = await state()
    assert.equal(current.state_version, 1)
    assert.equal(current.attempts.length, 1)
    assert.deepEqual(current.coverage.map(c => c.status), ['covered', 'missing'])
  })
  await check('Exact duplicate POST replays and changed payload returns 409', async () => {
    const replay = await context.request.post(`${origin}/api/sessions/${sid}/answers`, { data: first.request })
    assert.deepEqual(await replay.json(), first.body)
    const conflicting = await context.request.post(`${origin}/api/sessions/${sid}/answers`, { data: { ...first.request, answer: 'changed' } })
    assert.equal(conflicting.status(), 409)
    assert.equal((await state()).state_version, 1)
  })
  await check('Refresh restores actual DB session, attempts and probe', async () => {
    await restored()
    await page.getByText('คำถามเจาะ:', { exact: true }).waitFor()
    await page.getByText('Quiet corner', { exact: true }).waitFor()
    assert.equal((await state()).round, 1)
  })
  assert.equal((await submit('Hiding place')).body.agent_action, 'next')
  await check('Long answer returns 413, retains text and consumes no attempt', async () => {
    const before = await state()
    const long = 'x'.repeat(10000)
    assert.equal((await submit(long)).status, 413)
    assert.equal(await page.locator('#answer-input').inputValue(), long)
    assert.deepEqual(await state(), before)
  })
  await check('Offline submission preserves pending text and recovers after refresh', async () => {
    await page.locator('#answer-input').fill('Unrelated socks')
    await context.setOffline(true)
    await page.getByRole('button', { name: 'ส่งคำตอบ', exact: true }).click()
    await page.getByText('เชื่อมต่อ Backend ไม่ได้ กรุณาตรวจว่าเซิร์ฟเวอร์ทำงานอยู่', { exact: true }).waitFor()
    assert.equal(await page.locator('#answer-input').inputValue(), 'Unrelated socks')
    await context.setOffline(false)
    await restored()
    assert.equal(await page.locator('#answer-input').inputValue(), 'Unrelated socks')
    assert.equal((await state()).attempts.length, 0)
  })
  const retry1 = await submit('Unrelated socks')
  assert.equal(retry1.body.agent_action, 'retry')
  assert.equal(retry1.body.feedback.strengths.length, 0)
  let unavailableRequest
  await page.route(`**/api/sessions/${sid}/answers`, async route => {
    unavailableRequest = route.request().postDataJSON()
    await route.fulfill({ status: 503, json: { status: 'error', error: { code: 'MODEL_UNAVAILABLE', message: 'Integration 503' } } })
  }, { times: 1 })
  const before503 = await state()
  assert.equal((await submit('I do not know')).status, 503)
  await page.getByText('Integration 503', { exact: true }).waitFor()
  await check('503 preserves exact pending request and DB state', async () => {
    const pending = await page.evaluate(() => JSON.parse(sessionStorage.getItem('apt_pending_answer') || 'null'))
    assert.ok(pending, '503 discarded the pending request')
    const { session_id, ...payload } = pending
    assert.equal(session_id, sid)
    assert.deepEqual(payload, unavailableRequest)
    assert.deepEqual(await state(), before503)
  })
  await stopBackend()
  if (!production) {
    await page.reload({ waitUntil: 'networkidle' })
    await check('Refresh while Backend is down retains saved session ID', async () => {
      await page.getByRole('alert').waitFor()
      assert.equal(await page.evaluate(() => localStorage.getItem('apt_session_id')), sid)
    })
  } else {
    await check('Static-server outage keeps saved session in the open browser', async () => {
      assert.equal(await page.evaluate(() => localStorage.getItem('apt_session_id')), sid)
    })
  }
  await startBackend()
  // Allow remaining checks to run even when diagnosing a failing source Frontend.
  if (results.some(r => r.status === 'failed')) {
    await page.evaluate(({ id, pending }) => {
      localStorage.setItem('apt_session_id', id)
      sessionStorage.setItem('apt_pending_answer', JSON.stringify({ session_id: id, ...pending }))
    }, { id: sid, pending: unavailableRequest })
  }
  await check('Restart restores state; 503 retry uses original ID/version/answer', async () => {
    await restored()
    assert.equal(await page.locator('#answer-input').inputValue(), 'I do not know')
    const retried = await submit('I do not know')
    assert.deepEqual(retried.request, unavailableRequest)
    assert.equal(retried.body.agent_action, 'retry')
    assert.equal((await state()).attempts.length, 2)
  })
  assert.equal((await submit('Unrelated again')).body.agent_action, 'next')
  assert.equal((await submit('Tail communication')).body.agent_action, 'finish')
  await check('Three rounds produce actual report with complete/incomplete and six attempts', async () => {
    await page.getByRole('button', { name: 'ดูรายงานผล' }).click()
    await page.getByText('ซ้อมครบ 3 รอบแล้ว', { exact: true }).waitFor()
    await page.getByText('ผลรอบนี้: ยังตอบไม่ครบ', { exact: true }).waitFor()
    const response = await context.request.get(`${origin}/api/sessions/${sid}/report`)
    const report = await response.json()
    assert.deepEqual(report.rounds.map(r => r.outcome), ['complete', 'incomplete', 'complete'])
    assert.deepEqual(report.rounds.map(r => r.attempts.length), [2, 3, 1])
    assert.equal(report.test_mode, true)
    await page.screenshot({ path: join(output, 'report.png'), fullPage: true })
  })
  await check('Report source link opens and renders the correct PDF page', async () => {
    await page.locator('.round-card').nth(1).getByRole('button', { name: '2', exact: true }).click()
    assert.equal(await page.locator('.page-controls select').inputValue(), '2')
    await page.locator('.pdf-preview .pdf-message').waitFor({ state: 'hidden' })
  })
  await check('Browser API requests use the UI origin and no JavaScript errors', async () => {
    assert.deepEqual([...browserApiOrigins], [new URL(origin).origin])
    assert.deepEqual(pageErrors, [])
  })
} catch (error) {
  results.push({ name: 'Integration runner', status: 'failed', error: error.message })
  console.error(error.stack)
} finally {
  if (browser) await browser.close()
  if (vite) await vite.close()
  await stopBackend()
  const report = { client_date: '2026-11-05', mode: production ? 'production-static' : 'vite-proxy',
    model_source: 'test_fake', trained_model_used: false, fixture_api_used: false,
    injected_faults: ['503 before commit', 'browser offline', 'backend process stopped'],
    frontend_commit: frontendCommit, frontend_local_changes: frontendChanges, frontend_diff_sha256: frontendDiffHash,
    passed: results.filter(r => r.status === 'passed').length,
    failed: results.filter(r => r.status === 'failed').length, checks: results }
  writeFileSync(join(output, 'results.json'), JSON.stringify(report, null, 2) + '\n')
  writeFileSync(join(output, 'backend.log'), backendLogs)
  console.log(JSON.stringify({ mode: report.mode, passed: report.passed, failed: report.failed, output }))
  if (report.failed) process.exitCode = 1
}
