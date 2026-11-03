# AI Presentation Trainer — Frontend v1

เว็บ React/Vite สำหรับอัปโหลด PDF, ซ้อมตอบ 3 คำถามหลักพร้อมคำถามเจาะ, และดูรายงานตาม `contracts/v1/` ฝั่ง Frontend ไม่คำนวณคะแนนหรือเรียก Gemini เอง

## รันแยกจาก Backend จริง

```powershell
cd frontend
npm ci
$env:API_PROXY_TARGET='http://127.0.0.1:8000'
npm run dev
```

เปิด `http://127.0.0.1:5173` หน้าเว็บเรียก `/api` บน origin เดียวกัน แล้ว Vite proxy ส่งต่อไปยัง Backend ที่ `API_PROXY_TARGET` หากไม่ตั้งค่า จะใช้ `http://127.0.0.1:8000` เฉพาะฝั่ง dev server เท่านั้น Browser ของเพื่อนที่เปิดผ่าน tunnel จะไม่เรียก localhost ของเครื่องตัวเอง

## ทดสอบโดยไม่รอ Backend

เปิดสอง terminal ที่ราก repo:

```powershell
cd frontend
npm run mock:api
```

```powershell
cd frontend
npm run dev
```

Mock ใช้ `contracts/v1/fixtures.json` และ PDF แมว 6 หน้าเพื่อทดสอบ flow `probe → next → retry → retry → incomplete → finish` โดยตอบ `model_source: test_fake` และ `test_mode: true` เสมอ ผล mock ไม่ใช่ผลโมเดลที่เทรนแล้ว

## กติกาการเชื่อมต่อ

- `GET /api/ready` ตรวจความพร้อม DB/โมเดล/บริการคำถาม; 503 แสดงข้อความและเก็บ body ใน `ApiError`
- ส่งคำตอบด้วย `question_id`, `attempt_id` (UUID), `state_version`, `answer`
- retry คำขอเดิมใช้ UUID/version/คำตอบเดิม; pending request เก็บใน `sessionStorage`
- 409 โหลด session ใหม่, 413 คงข้อความเพื่อแก้, 429/timeout คง pending request เพื่อส่งซ้ำ
- `history` และ `attempts` แสดงจาก Backend เท่านั้น; คำถามเจาะไม่เพิ่มรอบเอง
- รายงานแสดงทุก attempt, outcome และ coverage; อ้างอิงสไลด์เฉพาะเลขหน้าที่อยู่ใน PDF
- `VITE_API_BASE_URL` ปกติไม่ต้องตั้ง ถ้าตั้งต้องเป็น URL ของ proxy ที่ browser ทุกเครื่องเข้าถึงได้ ห้ามใส่ `GEMINI_API_KEY` ในตัวแปร `VITE_*`

`npm run build` สร้าง `dist/` การนำ `dist/` ไปให้เพื่อนใช้ต้องมี reverse proxy ส่ง `/api` ไป Backend หรือให้ Backend เสิร์ฟ static เพราะ Vite dev proxy ไม่ติดไปกับ build

## ขอบเขตงานที่ยังต้องรวมกับเพื่อน

Mock เป็นเพียงตัวตรวจสัญญา Backend จริงต้องทำ PDF extraction/RAG, session state ใน DB, Agent และรายงานตาม `contracts/v1/` หลังรวมงานให้ทดสอบ PDF ใหม่, refresh, 409/413/429/503, restart และ browser บนเครื่องอื่นอีกครั้ง
