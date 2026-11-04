import React, { useEffect, useRef, useState } from 'react'
import PdfPreview from './PdfPreview.jsx'
import { inspectSlideFile, MAX_SLIDE_PAGES } from './slideCheck.js'
import {
  answerQuestion,
  deckFileUrl,
  getReport,
  getReady,
  getSession,
  startSession,
  uploadDeck,
} from './api'
import { demoDeck, demoFeedback, demoQuestions, demoReport } from './demo'

const SESSION_KEY = 'apt_session_id'
const PENDING_KEY = 'apt_pending_answer'
const roleLabel = { concept: 'ด้านแนวคิด', technical: 'ด้านเทคนิค' }
const relevanceLabel = { relevant: 'ตรงประเด็น', partial: 'ตรงบางส่วน', unrelated: 'ไม่ตรงคำถาม' }

function normalizeQuestion(question) {
  if (!question) return null
  return {
    id: question.id,
    text: question.text,
    judge_role: question.judge_role || 'concept',
    source_pages: Array.isArray(question.source_pages) ? question.source_pages : [],
    topic: question.topic || '',
    decision_reason: question.decision_reason || '',
    criteria: Array.isArray(question.criteria) ? question.criteria : [],
  }
}

function ErrorNotice({ message, onClose }) {
  if (!message) return null
  return (
    <div className="error-notice" role="alert">
      <span>{message}</span>
      <button type="button" onClick={onClose} aria-label="ปิดข้อความแจ้งเตือน">×</button>
    </div>
  )
}

function LoadingStatus({ label }) {
  if (!label) return null
  return (
    <div className="loading-status" role="status" aria-live="polite">
      <span>{label}</span>
      <div className="loading-track" aria-hidden="true"><div className="loading-fill" /></div>
    </div>
  )
}

function Header({ mode, testMode, view, round, onHome }) {
  return (
    <header className="topbar">
      <button type="button" className="brand" onClick={onHome}>
        <svg className="brand-paw" viewBox="0 0 32 32" aria-hidden="true" focusable="false">
          <ellipse cx="6.4" cy="11" rx="3" ry="4" transform="rotate(-25 6.4 11)" />
          <ellipse cx="13" cy="6.4" rx="3" ry="4" transform="rotate(-8 13 6.4)" />
          <ellipse cx="20.4" cy="6.7" rx="3" ry="4" transform="rotate(12 20.4 6.7)" />
          <ellipse cx="26.5" cy="11.6" rx="3" ry="4" transform="rotate(28 26.5 11.6)" />
          <path d="M16 14.5c-3.2 0-4.7 3-6.8 4.9-1.6 1.5-2.1 4.1-.6 5.8 1.2 1.4 3.2 1.4 5.1.8 1.4-.4 2.2-.7 3.3-.7 1.1 0 1.9.3 3.3.7 1.9.6 3.9.6 5.1-.8 1.5-1.7 1-4.3-.6-5.8-2.1-1.9-3.6-4.9-6.8-4.9Z" />
        </svg>
        <span>AI Presentation Trainer</span>
      </button>
      <div className="topbar-right">
        {mode === 'demo' && view !== 'home' && <span className="demo-tag">โหมดตัวอย่าง</span>}
        {testMode && view !== 'home' && <span className="demo-tag">Backend ทดสอบ</span>}
        {view === 'practice' && <><span className="status-dot" /><span className="running-label">กำลังซ้อมนำเสนอ</span><span className="topbar-divider" /><span className="round-indicator">รอบที่ {round} / 3</span></>}
        {view === 'report' && <span>รายงานผลการซ้อม</span>}
      </div>
    </header>
  )
}

function UploadView({ file, setFile, difficulty, setDifficulty, busy, onStartReal, onStartDemo, error, setError }) {
  const inputRef = useRef(null)
  const checkVersion = useRef(0)
  const [dragging, setDragging] = useState(false)
  const [checking, setChecking] = useState(false)

  async function selectFile(candidate) {
    const version = ++checkVersion.current
    setError('')
    setFile(null)
    setChecking(false)
    if (!candidate) return
    if (candidate.type !== 'application/pdf' && !candidate.name.toLowerCase().endsWith('.pdf')) {
      setError('กรุณาเลือกไฟล์ PDF')
      return
    }
    setChecking(true)
    try {
      const result = await inspectSlideFile(candidate)
      if (version !== checkVersion.current) return
      if (result.kind === 'too_large') {
        setError('PDF ต้องมีขนาดไม่เกิน 15 MB')
      } else if (result.kind === 'unreadable') {
        setError('PDF นี้มีข้อความที่อ่านได้ไม่เพียงพอ กรุณาส่งออกสไลด์แบบที่เลือกข้อความได้')
      } else if (result.kind === 'document') {
        setError('ไฟล์นี้ดูเป็นเอกสาร PDF ทั่วไป กรุณาส่งออกสไลด์จากโปรแกรมนำเสนอเป็น PDF')
      } else if (result.pageCount > MAX_SLIDE_PAGES) {
        setError(`ตรวจพบสไลด์ ${result.pageCount} หน้า แต่ระบบรองรับ 1–${MAX_SLIDE_PAGES} หน้า กรุณาแบ่งไฟล์เป็นชุดละไม่เกิน ${MAX_SLIDE_PAGES} หน้า`)
      } else {
        setFile(candidate)
      }
    } catch {
      if (version === checkVersion.current) setError('เปิด PDF นี้ไม่ได้ กรุณาตรวจว่าไฟล์ไม่เสียหรือถูกล็อกด้วยรหัสผ่าน')
    } finally {
      if (version === checkVersion.current) setChecking(false)
    }
  }

  return (
    <main className="upload-shell">
      <section className="intro">
        <div className="intro-copy">
          <div className="intro-kicker">ฝึกตอบคำถามก่อนนำเสนอจริง</div>
          <h1>ซ้อมนำเสนอจากสไลด์ของคุณ</h1>
          <p>อัปโหลด PDF แล้วให้กรรมการ AI ตั้งคำถามจากเนื้อหาในสไลด์ ตอบ 3 รอบและดูข้อเสนอแนะพร้อมหน้าอ้างอิง</p>
        </div>
        <div className="mascot-panel" aria-hidden="true">
          <img src="/assets/red-panda-presenter.png" alt="" />
        </div>
      </section>

      <div className="upload-grid">
        <section className="upload-card">
          <div className="section-heading">
            <h2>อัปโหลดสไลด์</h2>
            <span>PDF สไลด์แนวนอน 1–10 หน้า</span>
          </div>
          <label className="difficulty-control" htmlFor="difficulty-select">
            <span>ระดับคำถาม</span>
            <select id="difficulty-select" value={difficulty} onChange={(event) => setDifficulty(event.target.value)} disabled={busy}>
              <option value="basic">พื้นฐาน — อธิบายใจความสำคัญ</option>
              <option value="standard">ทั่วไป — อธิบายการนำไปใช้</option>
              <option value="challenge">ท้าทาย — วิเคราะห์และเชื่อมโยง</option>
            </select>
          </label>
          <div
            className={`dropzone ${dragging ? 'dragging' : ''}`}
            onDragOver={(event) => { event.preventDefault(); setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              event.preventDefault()
              setDragging(false)
              selectFile(event.dataTransfer.files[0])
            }}
          >
            <div className="pdf-icon">PDF</div>
            <strong>{file ? file.name : 'ลากไฟล์ PDF มาวางที่นี่'}</strong>
            <span>{file ? `${(file.size / 1024 / 1024).toFixed(2)} MB` : 'หรือเลือกไฟล์จากเครื่องของคุณ'}</span>
            <input
              ref={inputRef}
              type="file"
              accept="application/pdf,.pdf"
              hidden
              onChange={(event) => { selectFile(event.target.files[0]); event.target.value = '' }}
            />
            <button type="button" className="secondary-button" onClick={() => inputRef.current?.click()} disabled={busy}>
              เลือกไฟล์
            </button>
          </div>
          {checking && <LoadingStatus label="กำลังตรวจว่า PDF เป็นสไลด์และมีข้อความให้อ่าน..." />}
          <ErrorNotice message={error} onClose={() => setError('')} />
          <button type="button" className="primary-button wide" onClick={onStartReal} disabled={!file || busy || checking}>
            {busy ? 'กำลังอ่านสไลด์...' : 'เริ่มซ้อมกับ AI'}
          </button>
          <p className="upload-hint">โหมดนี้เชื่อม Backend และเรียก AI API จริง</p>
        </section>

        <section className="sample-card">
          <div className="section-heading">
            <h2>ทดลองหน้าจอก่อน</h2>
            <span className="demo-tag">โหมดตัวอย่าง</span>
          </div>
          <div className="sample-preview">
            <div className="cat-mark">🐈</div>
            <div>
              <strong>รู้จักแมวผ่านพฤติกรรม</strong>
              <p>สไลด์ตัวอย่าง 6 หน้า</p>
            </div>
          </div>
          <p>ลองดูขั้นตอนการซ้อมและหน้ารายงานด้วยคำถามตัวอย่าง โหมดนี้ยังไม่เรียก AI API</p>
          <button type="button" className="secondary-button wide" onClick={onStartDemo}>เปิดสไลด์ตัวอย่าง</button>
        </section>
      </div>
    </main>
  )
}

function PdfPanel({ deck, page, setPage, pdfUrl }) {
  const pageCount = deck?.page_count || 1
  function step(delta) {
    setPage((current) => Math.min(pageCount, Math.max(1, current + delta)))
  }
  return (
    <section className="pdf-panel">
      <h2>สไลด์นำเสนอ (PDF)</h2>
      <div className="pdf-toolbar">
        <div className="pdf-name"><span className="file-icon">▤</span><span title={deck?.filename}>{deck?.filename}</span></div>
        <div className="page-controls">
          <button type="button" onClick={() => step(-1)} disabled={page <= 1} aria-label="หน้าก่อนหน้า">‹</button>
          <label>
            <span className="sr-only">เลือกหน้าสไลด์</span>
            <select value={page} onChange={(event) => setPage(Number(event.target.value))}>
              {Array.from({ length: pageCount }, (_, index) => (
                <option key={index + 1} value={index + 1}>หน้า {index + 1} / {pageCount}</option>
              ))}
            </select>
          </label>
          <button type="button" onClick={() => step(1)} disabled={page >= pageCount} aria-label="หน้าถัดไป">›</button>
        </div>
      </div>
      <div className="pdf-stage">
        {pdfUrl ? (
          <PdfPreview url={pdfUrl} pageNumber={page} />
        ) : (
          <div className="pdf-placeholder">ไม่สามารถแสดงไฟล์ PDF ได้</div>
        )}
      </div>
    </section>
  )
}

function PracticeView({
  deck, pdfUrl, page, setPage, round, question, currentPrompt, attempts, history, coverage, answer, setAnswer,
  busy, error, setError, onSubmit, onReport, mode, testMode,
}) {
  const endRef = useRef(null)
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }) }, [history, question])
  return (
    <main className="practice-shell">
      <div className="practice-grid">
        <PdfPanel deck={deck} pdfUrl={pdfUrl} page={page} setPage={setPage} />
        <section className="qa-panel">
          {mode === 'demo' && <div className="test-banner">โหมดตัวอย่าง: ลองขั้นตอนการซ้อมได้ แต่ยังไม่ตรวจหรือให้คะแนนคำตอบ</div>}
          {testMode && <div className="test-banner">คำถามจาก Backend ทดสอบ ยังไม่ได้เรียก AI API</div>}
          <div className="qa-heading">
            <h2>รอบซ้อม {Math.min(round, 3)} / 3</h2>
            <span className="role-tag">กรรมการ: {roleLabel[question?.judge_role] || 'ด้านแนวคิด'}</span>
          </div>
          <div className="conversation">
            {history.map((item, index) => (
              <div className="history-block" key={item.question?.id || index}>
                <div className="bubble question-bubble previous">
                  <span className="avatar ai-avatar">Q</span>
                  <div><strong>{item.question?.text}</strong><PageLinks pages={item.question?.source_pages} setPage={setPage} /></div>
                </div>
                {(item.attempts?.length ? item.attempts : [{ answer: item.answer }]).map((attempt, attemptIndex) => (
                  <div className="bubble answer-bubble" key={attempt.attempt_id || attemptIndex}>
                    <span className="avatar user-avatar">●</span>
                    <div><span className="bubble-label">คำตอบครั้งที่ {attemptIndex + 1}</span><p>{attempt.answer}</p></div>
                  </div>
                ))}
                {item.feedback && (
                  <div className="inline-feedback">
                    <strong>{item.feedback.note ? 'หมายเหตุโหมดตัวอย่าง' : 'ข้อเสนอแนะ'}</strong>
                    <p>{item.feedback.note || item.feedback.improvements?.[0] || item.feedback.summary || 'บันทึกคำตอบแล้ว'}</p>
                  </div>
                )}
              </div>
            ))}
            {question && (
              <div className="bubble question-bubble current">
                <span className="avatar ai-avatar">Q</span>
                <div>
                  <strong>{question.text}</strong>
                  <PageLinks pages={question.source_pages} setPage={setPage} />
                  {question.decision_reason && <p className="question-reason">เหตุผลที่ถาม: {question.decision_reason}</p>}
                  {currentPrompt && currentPrompt !== question.text && <p className="followup-prompt"><strong>คำถามเจาะ:</strong> {currentPrompt}</p>}
                </div>
              </div>
            )}
            {attempts.map((attempt, index) => (
              <div className="bubble answer-bubble" key={attempt.attempt_id || index}>
                <span className="avatar user-avatar">●</span>
                <div><span className="bubble-label">คำตอบครั้งที่ {index + 1}</span><p>{attempt.answer}</p></div>
              </div>
            ))}
            {coverage.length > 0 && <div className="coverage-summary" aria-label="ผลตรวจประเด็นจาก Backend">
              {coverage.map((criterion) => <span key={criterion.criterion_id}>{question?.criteria?.find((item) => item.id === criterion.criterion_id)?.text || criterion.criterion_id}: {criterion.status === 'covered' ? 'ครบ' : criterion.status === 'partial' ? 'บางส่วน' : 'ยังไม่ครบ'}</span>)}
            </div>}
            <div ref={endRef} />
          </div>
          <form className="answer-form" onSubmit={onSubmit}>
            <ErrorNotice message={error} onClose={() => setError('')} />
            <label htmlFor="answer-input" className="sr-only">พิมพ์คำตอบสำหรับคำถามปัจจุบัน</label>
            <textarea
              id="answer-input"
              placeholder={currentPrompt || 'พิมพ์คำตอบของคุณที่นี่...'}
              value={answer}
              onChange={(event) => setAnswer(event.target.value)}
              disabled={busy || !question}
              rows={3}
            />
            <div className="answer-actions">
              <span>ตอบจากความเข้าใจของคุณ แล้ว AI จะถามต่อ</span>
              <button type="submit" className="primary-button" disabled={busy || !question || !answer.trim()}>
                {busy ? 'กำลังประเมิน...' : 'ส่งคำตอบ'}
              </button>
            </div>
          </form>
        </section>
      </div>
      <ProgressBar round={round} onReport={onReport} completed={!question} />
    </main>
  )
}

function PageLinks({ pages = [], setPage }) {
  if (!pages?.length) return null
  return (
    <div className="source-links">
      {pages.map((page) => <button type="button" key={page} onClick={() => setPage(page)}>อ้างอิงสไลด์หน้า {page}</button>)}
    </div>
  )
}

function ProgressBar({ round, completed, onReport }) {
  return (
    <div className="progress-bar">
      <div className="steps">
        {[1, 2, 3].map((number) => (
          <div className={`step ${number < round || completed ? 'done' : number === round ? 'active' : ''}`} key={number}>
            <span className="step-circle">{number < round || completed ? '✓' : number}</span>
            <span><strong>รอบซ้อม {number} / 3</strong><small>{number < round || completed ? 'เสร็จสิ้น' : number === round ? 'กำลังดำเนินการ' : 'รอดำเนินการ'}</small></span>
          </div>
        ))}
      </div>
      <button type="button" className="report-button" disabled={!completed} onClick={onReport}>▥ &nbsp; ดูรายงานผล</button>
    </div>
  )
}

function ReportView({ report, history, deck, mode, testMode, error, onRetryReport, onHome, setPage, onViewSlides }) {
  const rounds = Array.isArray(report?.rounds) && report.rounds.length ? report.rounds : history.map((item, index) => ({
    round: index + 1,
    question: item.question?.text,
    answer: item.answer,
    feedback: item.feedback,
  }))
  const overall = report?.overall || {}
  return (
    <main className="report-shell">
      <div className="report-top">
        <div><span className="intro-kicker">รายงานผลการซ้อม</span><h1>ซ้อมครบ 3 รอบแล้ว</h1><p>{deck?.filename}</p></div>
        <button type="button" className="secondary-button" onClick={onHome}>เริ่มซ้อมใหม่</button>
      </div>
      {error && <div className="error-notice"><span>{error}</span><button type="button" onClick={onRetryReport}>ลองใหม่</button></div>}
      {mode === 'demo' && <div className="demo-banner">โหมดตัวอย่างแสดงขั้นตอนการใช้งานเท่านั้น ยังไม่ได้ประเมินคำตอบหรือให้คะแนน</div>}
      {testMode && <div className="demo-banner">นี่คือรายงานจาก Backend ทดสอบ ยังไม่ได้ใช้ AI API</div>}
      <section className={`report-summary ${mode === 'demo' ? 'demo-summary' : ''}`}>
        <div><h2>ภาพรวม</h2><p>{overall.summary || 'ระบบสรุปผลจากคำตอบทั้ง 3 รอบ'}</p></div>
        {mode !== 'demo' && <div><h3>จุดที่ทำได้ดี</h3><ul>{(overall.strengths || []).map((item, index) => <li key={index}>{item}</li>)}</ul></div>}
        {mode !== 'demo' && <div><h3>สิ่งที่ควรปรับ</h3><ul>{(overall.improvements || []).map((item, index) => <li key={index}>{item}</li>)}</ul></div>}
      </section>
      <div className="report-rounds">
        <h2>รายละเอียดแต่ละรอบ</h2>
        {rounds.map((item, index) => (
          <section className="round-card" key={index}>
            <span className="round-number">รอบ {item.round || index + 1}</span>
            <h3>{item.question?.text || item.question || history[index]?.question?.text}</h3>
            <p><strong>ผลรอบนี้:</strong> {item.outcome === 'complete' ? 'ตอบครบประเด็น' : item.outcome === 'incomplete' ? 'ยังตอบไม่ครบ' : 'โหมดตัวอย่าง'}</p>
            {(item.attempts?.length ? item.attempts : [{ answer: item.answer || history[index]?.answer }]).map((attempt, attemptIndex) => (
              <p key={attempt.attempt_id || attemptIndex}><strong>คำตอบครั้งที่ {attemptIndex + 1}:</strong> {attempt.answer}</p>
            ))}
            {item.coverage?.map((criterion) => <p key={criterion.criterion_id}><strong>{item.question?.criteria?.find((entry) => entry.id === criterion.criterion_id)?.text || criterion.criterion_id}:</strong> {criterion.status === 'covered' ? 'ครบ' : criterion.status === 'partial' ? 'บางส่วน' : 'ยังไม่ครบ'}</p>)}
            {item.feedback?.relevance && <p className={`answer-verdict ${item.feedback.relevance}`}>ผลตรวจ: {relevanceLabel[item.feedback.relevance] || item.feedback.relevance}</p>}
            {item.feedback?.strengths?.length > 0 && <p><strong>จุดที่ดี:</strong> {item.feedback.strengths.join(' · ')}</p>}
            {item.feedback?.improvements?.length > 0 && <p><strong>ควรปรับ:</strong> {item.feedback.improvements.join(' · ')}</p>}
            {item.feedback?.note && <p className="demo-feedback-note">{item.feedback.note}</p>}
            <div className="source-text">อ้างอิงสไลด์หน้า {(item.source_pages || item.feedback?.source_pages || history[index]?.question?.source_pages || []).filter((page) => page >= 1 && page <= (deck?.page_count || 0)).map((page) => <button type="button" key={page} onClick={() => { setPage(page); onViewSlides() }}>{page}</button>)}</div>
          </section>
        ))}
      </div>
    </main>
  )
}

export default function App() {
  const [view, setView] = useState('home')
  const [mode, setMode] = useState('api')
  const [file, setFile] = useState(null)
  const [difficulty, setDifficulty] = useState('standard')
  const [deck, setDeck] = useState(null)
  const [pdfUrl, setPdfUrl] = useState('')
  const [sessionId, setSessionId] = useState('')
  const [round, setRound] = useState(1)
  const [question, setQuestion] = useState(null)
  const [currentPrompt, setCurrentPrompt] = useState('')
  const [attempts, setAttempts] = useState([])
  const [coverage, setCoverage] = useState([])
  const [stateVersion, setStateVersion] = useState(0)
  const [history, setHistory] = useState([])
  const [answer, setAnswer] = useState('')
  const [page, setPage] = useState(1)
  const [report, setReport] = useState(null)
  const [busy, setBusy] = useState(false)
  const [busyLabel, setBusyLabel] = useState('')
  const [error, setError] = useState('')
  const [restoring, setRestoring] = useState(() => Boolean(localStorage.getItem(SESSION_KEY)))
  const [testMode, setTestMode] = useState(false)

  function applySessionState(data, fromAnswer = false) {
    const active = normalizeQuestion(fromAnswer ? data.next_question : data.question)
    setQuestion(active)
    setCurrentPrompt(data.current_prompt || '')
    setAttempts(Array.isArray(data.attempts) ? data.attempts : [])
    setCoverage(Array.isArray(data.coverage) ? data.coverage : [])
    setHistory(Array.isArray(data.history) ? data.history : [])
    setStateVersion(data.state_version ?? 0)
    setRound(data.round || 1)
    setTestMode(data.test_mode === true)
    if (active?.source_pages?.length) setPage(active.source_pages[0])
    return active
  }

  useEffect(() => {
    const saved = localStorage.getItem(SESSION_KEY)
    if (!saved) { setRestoring(false); return }
    let cancelled = false
    getSession(saved).then((data) => {
      if (cancelled) return
      const deckId = data.deck_id
      setMode('api')
      setTestMode(data.test_mode === true)
      setDeck({ deck_id: deckId, filename: data.filename || 'สไลด์นำเสนอ.pdf', page_count: data.page_count || 1 })
      setPdfUrl(deckFileUrl(deckId))
      setSessionId(saved)
      applySessionState(data)
      const pending = JSON.parse(sessionStorage.getItem(PENDING_KEY) || 'null')
      if (pending?.session_id === saved) {
        const recorded = [...(data.attempts || []), ...(data.history || []).flatMap((round) => round.attempts || [])].some((attempt) => attempt.attempt_id === pending.attempt_id)
        if (recorded) sessionStorage.removeItem(PENDING_KEY)
        else if (pending.question_id === data.question?.id && pending.state_version === data.state_version) setAnswer(pending.answer)
      }
      setView(data.completed ? 'report' : 'practice')
      if (data.completed) getReport(saved).then((result) => { if (!cancelled) setReport(result) }).catch(() => {
        if (!cancelled) setError('โหลดรายงานไม่ได้ กรุณาลองใหม่')
      })
    }).catch(() => {
      if (!cancelled) {
        localStorage.removeItem(SESSION_KEY)
        setError('กลับเข้ารอบซ้อมเดิมไม่ได้ กรุณาตรวจ Backend หรือเริ่มซ้อมใหม่')
      }
    }).finally(() => { if (!cancelled) setRestoring(false) })
    return () => { cancelled = true }
  }, [])

  function goHome() {
    localStorage.removeItem(SESSION_KEY)
    sessionStorage.removeItem(PENDING_KEY)
    setView('home')
    setMode('api')
    setTestMode(false)
    setDeck(null)
    setPdfUrl('')
    setSessionId('')
    setRound(1)
    setQuestion(null)
    setCurrentPrompt('')
    setAttempts([])
    setCoverage([])
    setStateVersion(0)
    setHistory([])
    setAnswer('')
    setReport(null)
    setError('')
    setBusyLabel('')
    setPage(1)
    setFile(null)
  }

  function startDemo() {
    setMode('demo')
    setTestMode(false)
    setDeck(demoDeck)
    setPdfUrl(demoDeck.url)
    setRound(1)
    setQuestion(demoQuestions[0])
    setCurrentPrompt(demoQuestions[0].text)
    setAttempts([])
    setCoverage([])
    setHistory([])
    setAnswer('')
    setPage(demoQuestions[0].source_pages[0])
    setError('')
    setView('practice')
  }

  async function startReal() {
    if (!file) return
    setBusy(true)
    setBusyLabel('กำลังอัปโหลดและอ่าน PDF...')
    setError('')
    try {
      setBusyLabel('กำลังตรวจความพร้อมของระบบ...')
      await getReady()
      setBusyLabel('กำลังอัปโหลดและอ่าน PDF...')
      const uploaded = await uploadDeck(file)
      setBusyLabel('กำลังค้นสไลด์และสร้างคำถามแรก...')
      const result = await startSession(uploaded.deck_id, difficulty)
      setMode('api')
      setTestMode(uploaded.test_mode === true || result.test_mode === true)
      setDeck(uploaded)
      setPdfUrl(deckFileUrl(uploaded.deck_id))
      setSessionId(result.session_id)
      localStorage.setItem(SESSION_KEY, result.session_id)
      applySessionState(result)
      setView('practice')
    } catch (caught) {
      setError(caught.message)
    } finally {
      setBusy(false)
    }
  }

  async function submitAnswer(event) {
    event.preventDefault()
    if (!answer.trim() || !question || busy) return
    setBusy(true)
    setBusyLabel('กำลังตรวจคำตอบและเตรียมคำถามถัดไป...')
    setError('')
    const submitted = answer.trim()
    try {
      if (mode === 'demo') {
        const feedback = demoFeedback(round)
        const updated = [...history, { question, answer: submitted, feedback }]
        const next = demoQuestions[round] || null
        setHistory(updated)
        setQuestion(next)
        setCurrentPrompt(next?.text || '')
        setRound(next ? round + 1 : 3)
        if (next) setPage(next.source_pages[0])
        else setReport(demoReport(updated))
      } else {
        const previous = JSON.parse(sessionStorage.getItem(PENDING_KEY) || 'null')
        const request = previous?.session_id === sessionId && previous.question_id === question.id && previous.state_version === stateVersion && previous.answer === submitted
          ? previous
          : { session_id: sessionId, question_id: question.id, attempt_id: crypto.randomUUID(), state_version: stateVersion, answer: submitted }
        sessionStorage.setItem(PENDING_KEY, JSON.stringify(request))
        const result = await answerQuestion(sessionId, { question_id: request.question_id, attempt_id: request.attempt_id, state_version: request.state_version, answer: request.answer })
        sessionStorage.removeItem(PENDING_KEY)
        if (result.state_version < stateVersion) applySessionState(await getSession(sessionId))
        else applySessionState(result, true)
        setAnswer('')
        if (result.completed) {
          setBusyLabel('กำลังจัดทำรายงานผล...')
          try { setReport(await getReport(sessionId)) }
          catch { setError('บันทึกคำตอบแล้ว แต่โหลดรายงานไม่สำเร็จ กดดูรายงานเพื่อลองใหม่') }
        }
      }
      if (mode === 'demo') setAnswer('')
    } catch (caught) {
      if (mode === 'api' && caught.httpStatus === 409) {
        try {
          const fresh = await getSession(sessionId)
          applySessionState(fresh)
          const pending = JSON.parse(sessionStorage.getItem(PENDING_KEY) || 'null')
          const recorded = [...(fresh.attempts || []), ...(fresh.history || []).flatMap((item) => item.attempts || [])].some((item) => item.attempt_id === pending?.attempt_id)
          if (recorded) { sessionStorage.removeItem(PENDING_KEY); setAnswer(''); setError('คำตอบนี้ถูกบันทึกแล้ว โหลดสถานะล่าสุดให้แล้ว') }
          else { sessionStorage.removeItem(PENDING_KEY); setError('คำถามเปลี่ยนไปแล้ว ตรวจคำถามล่าสุดก่อนส่งอีกครั้ง') }
        } catch { setError('สถานะการซ้อมเปลี่ยนไป แต่โหลดสถานะล่าสุดไม่ได้ กรุณาลองรีเฟรช') }
      } else {
        setError(caught.httpStatus === 413 ? 'คำตอบยาวเกินขีดจำกัด กรุณาย่อคำตอบแล้วส่งใหม่' : caught.httpStatus === 429 ? 'ระบบรับคำขอมากเกินไป รอสักครู่แล้วกดส่งอีกครั้ง' : caught.message)
        if (caught.httpStatus === 413 || caught.httpStatus === 503) sessionStorage.removeItem(PENDING_KEY)
      }
    } finally {
      setBusy(false)
    }
  }

  async function openReport() {
    if (mode === 'api' && !report) {
      setBusy(true)
      setBusyLabel('กำลังโหลดรายงานผล...')
      setError('')
      try { setReport(await getReport(sessionId)) }
      catch (caught) { setError(caught.message); setBusy(false); return }
      setBusy(false)
    }
    setView('report')
  }

  return (
    <div className="app">
      <Header mode={mode} testMode={testMode} view={view} round={round} onHome={goHome} />
      <LoadingStatus label={restoring ? 'กำลังกลับเข้ารอบซ้อมเดิม...' : busy ? busyLabel : ''} />
      {restoring && <main className="restore-screen">กำลังกลับเข้ารอบซ้อมเดิม...</main>}
      {!restoring && view === 'home' && <UploadView file={file} setFile={setFile} difficulty={difficulty} setDifficulty={setDifficulty} busy={busy} onStartReal={startReal} onStartDemo={startDemo} error={error} setError={setError} />}
      {!restoring && view === 'practice' && <PracticeView deck={deck} pdfUrl={pdfUrl} page={page} setPage={setPage} round={round} question={question} currentPrompt={currentPrompt} attempts={attempts} history={history} coverage={coverage} answer={answer} setAnswer={setAnswer} busy={busy} error={error} setError={setError} onSubmit={submitAnswer} onReport={openReport} mode={mode} testMode={testMode} />}
      {!restoring && view === 'report' && <ReportView report={report} history={history} deck={deck} mode={mode} testMode={testMode} error={error} onRetryReport={openReport} onHome={goHome} setPage={setPage} onViewSlides={() => setView('practice')} />}
    </div>
  )
}
