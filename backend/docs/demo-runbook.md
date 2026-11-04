# ซ้อมเดโมระหว่างรอ model package

ใช้ Backend จริงสำหรับ HTTP, PDF, SQLite, session, Agent และ report ส่วน predictor และการสร้างคำถามอยู่ใน `test_fake` ผลนี้ตรวจการเชื่อมระบบและ recovery เท่านั้น

## เตรียม environment

จากราก repo ที่มีทั้ง `backend/` และ checkout ของ Frontend ตามที่ทีมกำหนด:

```powershell
python -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.lock.txt
cd frontend
npm ci
cd ..
```

หาก Frontend อยู่คนละ checkout ให้ใช้ absolute path ของโฟลเดอร์ที่มี `package.json` ในคำสั่งถัดไป Backend ไม่ต้อง merge branch ของ Frontend เพื่อใช้ไฟล์ build

ก่อนซ้อมให้ใช้ Frontend ที่รวมการแก้ใน `backend/integration/frontend-recovery.patch` แล้ว Patch นี้สร้างจาก Frontend commit `133b2a8` และยังต้องให้คน A ตรวจและนำเข้า branch ของตน:

```powershell
# จากราก checkout ของ Frontend ใช้ path ของ patch ที่ดาวน์โหลด/คัดลอกมาจริง
git apply --check C:/path/to/backend/integration/frontend-recovery.patch
git apply C:/path/to/backend/integration/frontend-recovery.patch
```

## เปิดแบบ build และ same-origin

```powershell
# จากราก repo Backend ปรับ path Frontend ให้ตรงกับเครื่อง
./backend/tools/start_demo.ps1 -FrontendDirectory C:/path/to/frontend
```

สคริปต์ build Frontend แล้วเปิด FastAPI เสิร์ฟหน้าเว็บ, `/api` และ PDF จาก port เดียวกัน ปกติใช้ `http://127.0.0.1:8000` ตรวจ `/api/ready` ว่าเป็น `test_fake` อย่าเรียกสิ่งนี้ว่าโมเดลที่เทรนแล้ว

## ลำดับสาธิต

1. อัปโหลด `backend/examples/acceptance/integration-slides.pdf` เป็นสไลด์แนวนอน 3 หน้า
2. ข้อแรกตอบ `Quiet corner` ควรยังอยู่รอบ 1 และถามเจาะ จากนั้น refresh เพื่อแสดงว่า state มาจาก DB
3. ตอบ `Hiding place` ควรปิดรอบแรกเป็น complete และขึ้นรอบ 2
4. รอบ 2 ตอบ `Unrelated socks`, `I do not know`, `Unrelated again` จะมีโอกาสตอบรวม 3 ครั้งและปิด incomplete
5. รอบ 3 ตอบ `Tail communication` แล้วเปิดรายงาน ต้องมี outcome complete/incomplete/complete และจำนวน attempts 2/3/1
6. คลิกหน้าอ้างอิงและเปิด PDF เพื่อตรวจว่าตรงหน้าเดิม

มีการทดสอบอัตโนมัติเพิ่มเรื่อง duplicate POST, double click, 413, offline, 503 และ restart ใน `tools/integration-smoke.mjs` ผลวัดอยู่ใน `docs/integration-results/` หลังรันทดสอบ ไม่ได้ประเมินคุณภาพโมเดลจริง

## เตรียม tunnel

เครื่องนี้ยังไม่พบ `cloudflared` หรือ `ngrok` ใน PATH จึงยังไม่มีผลยืนยัน public tunnel หรืออุปกรณ์อีกเครื่อง ใช้ [Quick Tunnel ของ Cloudflare](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/) เมื่อมี CLI แล้ว เปิดอีก terminal:

```powershell
cloudflared tunnel --url http://127.0.0.1:8000
```

ใช้ URL ชั่วคราวที่คำสั่งคืนมาในมือถือผ่านเครือข่ายมือถือ/อีกเครื่อง แล้วทดสอบหน้าเว็บ, upload, PDF, `/api/ready`, ครบ 3 รอบและ report ห้ามชี้ tunnel ไป Vite อย่างเดียวโดยไม่มี API proxy และห้ามตั้ง URL API ใน browser เป็น localhost ของเครื่องผู้ชม

การทดสอบ production-static ในเครื่องช่วยยืนยันเส้นทาง same-origin แต่ยังใช้แทนผลทดสอบ tunnel หรืออีกอุปกรณ์ไม่ได้

## Gemini/RAG จริงโดยยังไม่มี model package

ตั้ง `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_EMBEDDING_MODEL` ใน `backend/.env` บนเครื่องเจ้าของ key แล้วรันจากราก repo:

```powershell
backend/.venv/Scripts/python.exe -m backend.tools.check_rag backend/examples/acceptance/bike_care.pdf backend/examples/acceptance/phishing.pdf backend/examples/acceptance/urban_garden.pdf backend/examples/acceptance/waste_sorting.pdf
```

เครื่องมือนี้ทำ extraction/retrieval/Gemini question generation และตรวจ quote/เลขหน้าจริงโดยไม่เริ่ม session หรือประเมินคำตอบ หากไม่มี config จะเขียนสถานะ blocked และไม่เรียก provider ไม่มีการบันทึก key ในผลลัพธ์

ยังตรวจ budget 512 tokens ด้วย tokenizer จริงไม่ได้จนกว่าจะได้รับ package ของคน A ผล preview จึงระบุ `tokenizer_budget_verified:false` เสมอ เก็บผลไว้ที่ `backend/.integration/live-rag.json`

## รับโมเดลจากคน A

ใช้ `backend/examples/acceptance/model-cases.json` จำนวน 23 กรณี มีคำตอบครบ บางส่วน นอกเรื่อง คำสั่งหลอก การตอบ probe และคำตอบยาวพร้อมผลคาดหวัง เกณฑ์มี quote ที่ดึงได้จาก PDF จริง แต่ labels เป็นตัวอย่างสังเคราะห์ที่ยังต้องให้คนตรวจ ไม่ใช่ test set สำหรับอ้างความแม่นยำ

รับ package/tokenizer/checkpoint/hash/version/thresholds/metrics ตาม `model-package-handoff.md` แล้วจึงรัน acceptance เหล่านี้กับของจริง ไม่ใช้การเทียบข้อความตรงของ `test_fake` ตัดสินว่าการจำแนกความหมาย partial สำเร็จแล้ว
