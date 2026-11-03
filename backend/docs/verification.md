# ผลตรวจ Backend — 4 พฤศจิกายน 2569

## ผลที่ยืนยันจากเครื่องนี้

ตรวจ branch `backend-v1` ที่เตรียมจาก `main` commit `3f6a3b1` ด้วย Python 3.12.10 บน Windows ใช้ environment ของงาน Backend เดิมที่ `../backend/.venv` จากราก checkout นี้ Dependencies ล็อกไว้ใน `requirements.lock.txt` การ clone ใหม่ต้องสร้าง environment และติดตั้งตาม README

| การตรวจ | ผล |
|---|---|
| `contracts/v1/validate.py` | `Contract v1 fixtures and transitions: OK` |
| `unittest` ของสัญญากลางต้นฉบับ | ผ่าน 7 tests |
| `pytest backend/tests` | ผ่าน 31 tests, 13.13 วินาที |
| `pip check` | `No broken requirements found.` |
| `run.py --help` | ทำงานและแสดง options ครบ |
| เปิด `run.py --test-mode` เป็น subprocess | ผ่าน HTTP จริง: readiness, static index, JSON API 404 |
| สัญญากลางที่ราก repository | ใช้ `contracts/v1/` โดยตรง ไม่แก้ schema/fixtures/scripts และไม่มีสำเนาแยกใน Backend |

มี warning 1 รายการจาก Starlette: TestClient ที่ใช้ `httpx` ถูกประกาศ deprecated ใน dependency รุ่นนี้ แต่ยังทำงานและ tests ผ่าน คง `httpx` ตาม lock ที่ตรวจแล้ว ยังไม่ได้ย้าย test transport ไป `httpx2`

ชุดทดสอบครอบคลุม PDF bytes/ข้อความ/ข้อจำกัดหน้าและขนาด/ภาพล้วน, flow 6 คำตอบจนจบ 3 รอบ, coverage สะสม, off-topic, ผลขัดกัน/ความมั่นใจต่ำ, third-attempt incomplete, report ก่อน/หลังจบ, คำขอซ้ำ, ID เดิมแต่ payload ต่าง, stale version, คำขอแข่งกันทั้ง ID เดียวและต่าง ID, response replay หลังไปข้อถัดไป, restart, migration บน DB เดิม, timeout และ 413/429/503 ที่ไม่ commit state

ส่วน AI ตรวจ quote/เลขหน้าแรก, duplicate criterion IDs, generation retry limit, retrieval cache, Gemini request/error handling, package loader/hash/version/IDs/input length/thresholds และ model identity เปลี่ยนระหว่าง session โดยใช้ **stub package และ mock Gemini เท่านั้น** ไม่ได้ใช้ checkpoint ฝึกจริงหรือส่งคำขอไป Gemini จริง

TestClient ใช้ socket ภายในสำหรับ asyncio บน Windows เครื่องนี้ sandbox ทำให้ค้างขณะสร้าง event loop การทดสอบ API จึงรันนอก sandbox หลังได้รับอนุญาต ไม่ได้เปลี่ยนโค้ดแอปเพื่อข้ามข้อจำกัดนั้น เซิร์ฟเวอร์ที่เปิดเพื่อทดสอบปิดแล้ว ไม่มี process สาธิตที่ตั้งให้ทำงานค้าง

`examples/api-responses.test.json` เป็น response จาก implementation นี้ใน `test_fake` พร้อม `model_version:test-fake-v1`; ไม่ใช่การคัดลอก fixtures แล้วอ้างว่าโมเดลทำงานจริง `examples/demo-slides.pdf` มีข้อความภาษาอังกฤษ 3 หน้า ใช้ประกอบการตรวจ flow

## ความคืบหน้าตามแผน B0–B4

| ขั้น | ส่วนที่ทำแล้ว | ส่วนที่ยังรอ |
|---|---|---|
| B0 contract | เก็บต้นฉบับ ผ่าน validator/tests และสร้าง responses fake จริง | คน A ยืนยัน parse และใช้ contract ชุดเดียวกัน |
| B1 DB/API | API/state/migration/transaction/fake flow/restart/concurrency/error tests ผ่าน | ทดสอบกับ Frontend ของคน A |
| B2 PDF/RAG/Gemini | โค้ด extraction/retrieval/cache/quote verification/regeneration พร้อม; provider mock ผ่าน | Gemini key/model IDs และ PDF ใหม่หลายหัวข้อสำหรับทดสอบ live/คุณภาพคำถาม |
| B3 model adapter | loader, hash/version/IDs/token budget/threshold validation พร้อม; stub tests ผ่าน | package/checkpoint/tokenizer/dependency lock/thresholds/metrics จริงจากคน A และยืนยัน loader interface |
| B4 handoff/integration | README, error table, package handoff, fake responses, static serving และ launcher HTTP test | Frontend จริง, proxy/tunnel จริง, remote browser และทดสอบครบ I1–I6 ตามแผน Frontend |

ยังไม่ถือว่า integration หรือการเทรนโมเดลเสร็จ และไม่มีผล F1/false praise rate ของโมเดลจริงในงานชุดนี้
