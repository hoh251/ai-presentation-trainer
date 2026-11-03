# AI Presentation Trainer — Backend v1

งานฝั่งคน B ตามเอกสารวันที่ 4 พฤศจิกายน 2569 อยู่ในโฟลเดอร์นี้ ใช้ FastAPI + SQLite + pypdf โดยมี Gemini REST client, RAG และ adapter รับ `model_package` ของคน A ใช้สัญญากลางจาก `contracts/v1/` ที่ราก repository

**สถานะ:** ทดสอบ API/state ด้วย fake model ได้ครบ flow ส่วนโค้ดเชื่อม Gemini และ package ทดสอบด้วย stub/mock แล้ว ยังไม่มี Gemini key, package/checkpoint หรือ metrics จริงจากคน A จึงยังยืนยันการใช้ AI จริงหรือการเชื่อม Frontend/tunnel ไม่ได้ ดูรายละเอียดใน `docs/verification.md`

## เปิดโหมดทดสอบบน Windows

จากรากโปรเจกต์:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe run.py --test-mode
```

เมื่อติดตั้ง dependencies แล้ว ครั้งถัดไปเริ่มด้วยคำสั่งสุดท้ายได้ เปิด `http://127.0.0.1:8000/docs` เพื่อทดลอง API และ `http://127.0.0.1:8000/api/ready` เพื่อดูความพร้อม

โหมดนี้แสดง `model_source:test_fake`, `test_mode:true` ทุก session/report ใช้คำถามจากข้อความ PDF และตรวจคำตอบด้วยการเทียบข้อความตรงเท่านั้น ไม่ใช่โมเดลภาษา ไม่ใช้ Gemini และไม่ใช่ผลโมเดลที่เทรนแล้ว ตัวประมาณความยาวในโหมดนี้ไม่ใช่ tokenizer จริง

ลอง `examples/demo-slides.pdf`: อัปโหลดแล้วเริ่ม session ระดับ `standard` ตอบ `Quiet corner` → ระบบถามเจาะ → ตอบ `Hiding place` → ไปข้อ 2; ตอบนอกเรื่อง 3 ครั้ง → ปิด `incomplete`; ข้อ 3 ตอบ `Tail communication` → จบและเปิดรายงาน

## API สำหรับคน A

| Endpoint | การใช้งาน |
|---|---|
| `GET /api/ready` | 200 เมื่อ DB/model/question service พร้อม; ไม่พร้อมเป็น 503 พร้อม booleans |
| `POST /api/decks` | multipart `file`, PDF ไม่เกิน 15 MiB และ 1–10 หน้า |
| `GET /api/decks/{id}/file` | คืน PDF bytes, `application/pdf`, รองรับ preview |
| `POST /api/sessions` | `{deck_id,difficulty}`; difficulty = `basic/standard/challenge` |
| `GET /api/sessions/{id}` | state ที่บันทึกจริง ใช้หลัง refresh/409 |
| `POST /api/sessions/{id}/answers` | `{question_id,attempt_id,state_version,answer}` |
| `GET /api/sessions/{id}/report` | รายงานหลังปิดครบ 3 รอบ; ก่อนจบเป็น 409 |

Schema และต้นฉบับ fixtures อยู่ `../contracts/v1/` จากโฟลเดอร์ Backend โดยใช้ไฟล์ที่ราก repository โดยตรง ตัวอย่าง response ที่สร้างจาก Backend นี้จริงอยู่ `examples/api-responses.test.json` และติดป้าย fake mode ชัดเจน คำว่า `local_finetuned` ใน fixtures ต้นฉบับเป็นข้อมูลตัวอย่าง ไม่ใช่หลักฐานผลโมเดล

Frontend แสดง `current_prompt` และเก็บ `question.text` เป็นคำถามหลัก ใช้ state จาก Backend ทั้งชุด เมื่อ `probe/retry/clarify` คงคำถามหลักและเลขรอบเดิม `counted_round:true` หมายถึงปิดรอบ รวมกรณี `incomplete` ด้วย `attempts` มีเฉพาะคำถามที่ยังทำอยู่ ส่วน attempts ที่ปิดแล้วอยู่ใน `history`

สร้าง UUID `attempt_id` ใหม่เมื่อตอบใหม่; retry คำขอเดิมต้องส่ง ID, question, version และข้อความเดิมทุกตัว Backend replay response snapshot เดิมแม้ session ไปข้อถัดไปแล้ว ถ้า response ที่ replay เก่ากว่า UI ให้โหลด GET session แทนการทับ state ใหม่

| HTTP / code | การจัดการฝั่ง Frontend |
|---|---|
| 409 `STATE_CONFLICT` | โหลด GET session ใหม่ |
| 409 `SESSION_NOT_COMPLETED` | รายงานยังเปิดไม่ได้ |
| 413 `ANSWER_TOO_LONG` | เก็บข้อความไว้ให้แก้; ยังไม่หัก attempt |
| 413 `PDF_TOO_LARGE` | เลือกไฟล์เล็กลง |
| 422 `PDF_NO_TEXT/PDF_INVALID/PDF_ENCRYPTED/PDF_PAGE_LIMIT/PDF_TEXT_LIMIT` | แสดงข้อความสาเหตุและให้เลือก PDF ใหม่ |
| 422 `REQUEST_INVALID` | ตรวจ payload ฝั่ง client |
| 429 `AI_RATE_LIMIT` | รอแล้ว retry คำขอเดิม |
| 503 `AI_TIMEOUT/AI_UNAVAILABLE/MODEL_BUSY/MODEL_UNAVAILABLE` | เก็บคำตอบแล้ว retry ด้วย ID เดิม |
| 503 `MODEL_OUTPUT_INVALID/MODEL_INPUT_INVALID` | ทีมตรวจ package/adapter; ไม่มี attempt ใหม่ |
| 503 `QUESTION_INVALID/PROMPT_TOO_LONG/QUESTION_SERVICE_UNAVAILABLE/AI_OUTPUT_INVALID` | ทีมตรวจ question service/config; state ไม่เปลี่ยน |
| 503 `SESSION_MODEL_CHANGED` | เริ่ม session ใหม่ เนื่องจาก version/hash หรือโหมดโมเดลเปลี่ยน |
| 503 `DATABASE_UNAVAILABLE` | รอให้ storage พร้อมแล้วลองใหม่ |

Error ปกติเป็น `{status:"error",error:{code,message}}` ส่วน `/api/ready` ไม่พร้อมเป็นกรณีพิเศษตาม contract: `{status:"unavailable",...}` ไม่ห่อใน error

## เปิดโหมดโมเดลจริง

คัดลอก `.env.example` เป็น `.env` แล้วตั้ง `TRAINER_TEST_MODE=false`, `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_EMBEDDING_MODEL`, `MODEL_PACKAGE_MODULE` และ `MODEL_ARTIFACT_DIR` เป็น absolute path ชื่อ Gemini model ให้ใช้รุ่นที่บัญชีทีมเรียกได้จริง ไม่มีชื่อโมเดลเริ่มต้นหรือการสลับรุ่นเงียบ ๆ

ติดตั้ง package/dependency lock ที่คน A ส่งใน `.venv` นี้ตามคู่มือของ package แล้วจัด artifact ตาม `docs/model-package-handoff.md` จากนั้นรัน:

```powershell
.\.venv\Scripts\python.exe run.py
```

โมเดลจริงยังไม่พร้อมจะได้ `/api/ready` 503 ไม่มีการสลับไป fake หรือใช้ Gemini ตรวจ coverage แทน ก่อนสาธิตต้องมี checkpoint/tokenizer, manifest/hash, thresholds จาก validation, baseline และผล test จริง รวมทั้งทดสอบ restart

โมเดลถูกโหลดครั้งเดียวตอน startup ตรวจ manifest/hash/version และผูก identity กับ session ทุกคำตอบ การเปลี่ยน checkpoint แม้ใช้ version เดิมจะไม่ยอมประเมิน session เก่าต่อ ส่วนคำขอที่เคย commit แล้วยัง replay ได้

## ฐานข้อมูลและ AI

ไฟล์ runtime อยู่ `storage/trainer.sqlite3` และ `storage/pdfs/` ตั้ง path อื่นได้ด้วย `TRAINER_STORAGE` ค่า relative path จะอิง working directory จึงแนะนำ absolute path

Migration เพิ่มตารางชื่อ `trainer_*` โดยไม่แก้หรือลบตารางเดิม ใช้ WAL, foreign keys และ unique `(session_id,attempt_id)` ประมวลผลโมเดล/Gemini นอก transaction ก่อน commit แบบ compare-and-swap รุ่น state แล้วเขียน session/attempt/round/response พร้อมกัน ใช้ Backend process เดียวและ DB/PDF ชุดเดียว

PDF เก็บข้อความทุกหน้าพร้อมเลข 1-based หน้าแรกไม่ถูกตัดทิ้ง PDF ภาพล้วนไม่มี OCR จะได้ error การดึงข้อมูลใช้ Gemini embedding แบ่งข้อความตามตัวอักษร 1,200 ตัว overlap 200 ตัว และ top 2 พร้อม cache ที่ผูก model/index version และ hash ข้อความ ค่าเหล่านี้เป็นค่าตั้งต้นที่ยังต้องประเมินจริง ไม่ใช่ token count 300/50 ที่วัดแล้ว จำกัด 80 chunks โดยส่ง error แทนการทิ้งข้อความส่วนท้ายเงียบ ๆ

Gemini สร้างคำถาม/เกณฑ์และช่วยเขียน probe; Backend ตรวจ quote กับข้อความ PDF จริงและตรวจ token budget ด้วย package ของคน A ก่อนเริ่มคำถาม Retry การสร้างคำถามไม่เกิน 2 ครั้งโดยปริยาย รวมทั้งคำขออยู่ภายใน deadline 115 วินาที ตั้งได้ไม่เกิน 120 วินาที สำหรับ Frontend abort 150 วินาที

Agent รวม coverage ตาม criterion ID เฉพาะผลที่มั่นใจ หาก off-topic หรือผลขัดกันจะไม่เพิ่ม/ล้าง covered เดิม กรณีขัดกันหรือ confidence ต่ำจะ clarify และไม่ชม ครบครั้งที่ 3 จะปิด incomplete แม้ยังไม่ชัดเจน Feedback/report สร้างจากผลที่ยืนยันแล้วด้วย template; Gemini ไม่เขียนคำชมอิสระและไม่ตัดสิน coverage

## ทดสอบ

จาก **รากโปรเจกต์**:

```powershell
backend/.venv/Scripts/python.exe contracts/v1/validate.py
backend/.venv/Scripts/python.exe -m unittest discover -s contracts/v1 -p test_contract.py -q
backend/.venv/Scripts/python.exe -m pytest backend/tests -q -o cache_dir=backend/.pytest_cache
backend/.venv/Scripts/python.exe -m backend.tools.export_examples
```

การทดสอบ Gemini ใช้ `httpx.MockTransport` และการโหลด package ใช้ stub artifact เท่านั้น ไม่เรียก API ที่เสียค่าใช้จ่ายหรืออ้างว่ามีโมเดลเทรนจริง ล็อก dependencies ของ environment ที่ใช้ตรวจไว้ใน `requirements.lock.txt` (Python 3.12 บน Windows)

## ต่อ Frontend และ tunnel

Development ให้คน A ตั้ง Vite proxy `/api` → `http://127.0.0.1:8000` และให้ browser เรียก URL `/api/...` โดยตรง ห้าม fallback ไป `localhost:8000` ของเครื่องผู้ชม

Production ให้ build Frontend แล้วใช้ Backend เสิร์ฟ `dist/` พร้อม API จาก origin เดียว:

```powershell
.\.venv\Scripts\python.exe run.py --frontend-dist C:/absolute/path/to/frontend/dist
```

ส่ง tunnel มาที่ port 8000 ของ process นี้ เมื่อใช้ Vite ผ่าน tunnel ให้ตั้ง `allowedHosts` ฝั่ง Frontend ตาม hostname จริง การตั้ง tunnel ไม่ได้ทำไว้ในโฟลเดอร์นี้ ต้องตรวจจากเครื่องอื่นทั้งหน้าเว็บ, PDF และ API จริงก่อนถือว่า integration เสร็จ

## โครงสร้าง

```text
backend/
  main.py                  HTTP API และ lifespan
  session_service.py       state/retry/round/report orchestration
  db.py                    additive migration และ atomic commit
  pdf_service.py           PDF validation และข้อความรายหน้า
  question_service.py      retrieval/cache/question/quote/probe
  gemini_service.py        Gemini REST และ bounded provider calls
  coverage_service.py      fake/real package adapter และ integrity checks
  agent.py                 coverage aggregation และ Agent policy
  tests/                   API, state, package และ provider tests
  examples/                responses จาก fake API + PDF ตัวอย่าง
  docs/                    วิธีส่ง package วิธีเรียก API และผลตรวจ
```

เอกสารอ้างอิงที่ใช้เขียนส่วนเชื่อม: [FastAPI upload](https://fastapi.tiangolo.com/tutorial/request-files/), [Gemini generateContent](https://ai.google.dev/api/generate-content), [Gemini structured output](https://ai.google.dev/gemini-api/docs/generate-content/structured-output)
