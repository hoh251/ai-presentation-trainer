import { chromium } from 'playwright'
import { resolve } from 'node:path'
import { spawn } from 'node:child_process'
import { createServer } from 'vite'

const mock = spawn(process.execPath, [resolve('scripts/contract-mock.mjs')], { env: { ...process.env, MOCK_PORT: '8011' }, stdio: 'ignore' })
process.env.API_PROXY_TARGET = 'http://127.0.0.1:8011'
const vite = await createServer({ server: { host: '127.0.0.1', port: 5175, strictPort: true } })
await vite.listen()
for (let attempt = 0; attempt < 30; attempt += 1) {
  try { if ((await fetch('http://127.0.0.1:8011/api/ready')).ok) break }
  catch { await new Promise((resolveWait) => setTimeout(resolveWait, 100)) }
}

const browser = await chromium.launch({ headless: true, executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' })
const page = await browser.newPage({ viewport: { width: 1366, height: 900 } })
const errors = []
page.on('pageerror', (error) => errors.push(error.message))
page.on('request', (request) => { if (request.url().includes('localhost:8000')) errors.push('Browser called localhost:8000') })

try {
  await page.goto('http://127.0.0.1:5175/', { waitUntil: 'networkidle' })
  await page.locator('input[type=file]').setInputFiles(resolve('public/cats-demo.pdf'))
  await page.waitForFunction(() => !document.querySelector('button.primary-button.wide')?.disabled)
  await page.getByRole('button', { name: 'เริ่มซ้อมกับ AI' }).click()
  await page.getByText('คำถามจาก Backend ทดสอบ').waitFor()
  if (!(await page.getByText('รอบซ้อม 1 / 3').count())) throw new Error('Round 1 missing')

  let failureCount = 0
  let rateLimitAttempt = ''
  let retryAttempt = ''
  await page.route('**/api/sessions/ses_fixture/answers', async (route) => {
    const body = JSON.parse(route.request().postData())
    if (failureCount === 0) {
      failureCount += 1
      return route.fulfill({ status: 413, json: { status: 'error', error: { code: 'ANSWER_TOO_LONG', message: 'ยาวเกิน' } } })
    }
    if (failureCount === 1) {
      failureCount += 1
      rateLimitAttempt = body.attempt_id
      return route.fulfill({ status: 429, json: { status: 'error', error: { code: 'AI_RATE_LIMIT', message: 'รอก่อน' } } })
    }
    if (failureCount === 2) { failureCount += 1; retryAttempt = body.attempt_id }
    return route.continue()
  })
  await page.locator('#answer-input').fill('คำตอบที่ต้องแก้')
  await page.getByRole('button', { name: 'ส่งคำตอบ' }).click()
  await page.getByText('คำตอบยาวเกินขีดจำกัด').waitFor()
  if ((await page.locator('#answer-input').inputValue()) !== 'คำตอบที่ต้องแก้') throw new Error('413 cleared typed answer')
  await page.locator('#answer-input').fill('จัดมุมเงียบ ๆ ให้')
  await page.getByRole('button', { name: 'ส่งคำตอบ' }).click()
  await page.getByText('ระบบรับคำขอมากเกินไป').waitFor()

  const answers = ['จัดมุมเงียบ ๆ ให้', 'จัดบ้านแมวให้เข้าไปหลบ', 'ถุงเท้า', 'ไม่รู้', 'แมวชอบปลาทู', 'แมวใช้หางสื่อสาร']
  for (let i = 0; i < answers.length; i += 1) {
    await page.locator('#answer-input').fill(answers[i])
    await page.getByRole('button', { name: 'ส่งคำตอบ' }).click()
    await page.getByText(answers[i], { exact: true }).first().waitFor()
    if (i === 0) {
      await page.getByText('คำถามเจาะ:').waitFor()
      if (!(await page.getByText('รอบซ้อม 1 / 3').count())) throw new Error('Probe advanced round')
      await page.reload({ waitUntil: 'networkidle' })
      await page.getByText('คำถามเจาะ:').waitFor()
      if (!(await page.getByText('คำตอบครั้งที่ 1').count())) throw new Error('Attempt missing after refresh')
    }
    if (i === 1 && !(await page.getByText('รอบซ้อม 2 / 3').count())) throw new Error('Round 2 missing')
  }
  if (!rateLimitAttempt || rateLimitAttempt !== retryAttempt) throw new Error('429 retry changed attempt ID')
  await page.getByRole('button', { name: 'ดูรายงานผล' }).click()
  await page.getByText('ซ้อมครบ 3 รอบแล้ว').waitFor()
  await page.getByText('ผลรอบนี้: ยังตอบไม่ครบ').waitFor()
  if ((await page.getByText('คำตอบครั้งที่ 3').count()) < 1) throw new Error('Third attempt missing from report')
  if (errors.length) throw new Error(errors.join(' | '))
  console.log('Contract UI flow passed: upload, probe, refresh, 6 attempts, incomplete report; browser uses same-origin API')
} finally {
  await browser.close()
  await vite.close()
  mock.kill()
}
