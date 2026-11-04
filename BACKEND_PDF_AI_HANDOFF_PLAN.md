# แผนส่งต่อฝั่ง Backend: PDF ใหม่, หลักฐานภาพ และการต่อโมเดล

วันที่ 5 พฤศจิกายน 2569 — คน A เขียนแผนและชุดตรวจในเครื่อง; คน B เป็นเจ้าของ `backend/`

## เป้าหมายและขอบเขต

รับ PDF สไลด์ 1–10 หน้า ไม่เกิน 15 MB ตามสัญญา v1 เท่านั้น ตรวจว่าเป็นสไลด์ อ่านข้อความและภาพที่มีสาระ เก็บหลักฐานย้อนกลับไปหน้า/บริเวณได้ สร้างคำถามและเกณฑ์จากหลักฐาน แล้วเรียก `model_package.predict_attempt()` ของคน A เพื่อตรวจคำตอบ ระบบต้องแยกข้อผิดพลาดของ PDF extraction, question/rubric และ answer scoring ใน log/ผลทดสอบ

## ลำดับงานของคน B

1. **PDF gate:** ตรวจชนิดไฟล์จริง, เปิดได้, รหัสผ่าน, ขนาดและจำนวนหน้า; จำแนก `slide/document/uncertain` จากหลายหน้า ไม่ใช้สัดส่วนหน้าอย่างเดียว; เก็บผลรายหน้าให้ Frontend แสดงได้
2. **Extract + quality:** ดึง text layer พร้อมเลขหน้า/บล็อก/ตำแหน่ง แล้วตรวจหน้าที่ข้อความหายหรืออ่านผิดลำดับ ทดลอง layout-aware parser เทียบ `pdfplumber` เดิมบนไฟล์เดียวกัน เลือกเมื่อมีผลวัดดีกว่า
3. **Vision เฉพาะจำเป็น:** หน้าภาพล้วนหรือหน้าที่ flow/ตาราง/กราฟมีสาระเกิน text layer ให้ Gemini Vision อธิบาย `node`, `edge`, ทิศทาง และบริเวณ ตรวจว่าข้อความที่ Vision ถอดมาไม่ขัดกับ text layer; ถ้าไม่มั่นใจไม่ใช้ตั้งคำถาม
4. **Evidence store + retrieval:** เก็บ text evidence และ visual evidence แยกกันพร้อม page/region/source/version; index page parent + block/visual relation child; ค้นแล้วคืนหน้า/บริเวณอ้างอิง
5. **Question/rubric:** ให้ Gemini สร้างคำถามและ 1–3 criteria จาก evidence ที่ผ่านการตรวจ ไม่ใส่คำบรรยายที่ระบบเติมเองเป็นหลักฐาน; แสดงว่าคำถามใดอ้าง text หรือ visual
6. **Model adapter + Agent:** โหลด model package/checkpoint ตอน startup; `/api/ready` ต้องบอกจริงว่าโมเดลพร้อมหรือไม่; ใช้ `predict_attempt(question,current_prompt,criteria,answer)` ไม่ใช้ Gemini ประเมินแทนโดยเงียบ ๆ; Agent ถามเจาะเมื่อ coverage กำกวมหรือขาด ห้ามตีความ `confidence` เป็น probability
7. **API errors:** กรณี 413/429/503 และ retry ต้องไม่ commit attempt ผิด; log stage ที่ล้มโดยไม่แสดง key/token

### จุดเชื่อมที่ตรวจพบจาก PR #3 commit `8056755`

Backend PR #3 มี loader `load_model(artifact_dir)` และต้องการ `manifest.checkpoint_file` + `thresholds.json` แต่ model package v2 ของคน A ใช้ `configure_model(base_model_path,checkpoint_dir,manifest_path)`, adapter LoRA และ Dense heads แยกไฟล์ จึงยังโหลดร่วมกันไม่ได้จากไฟล์ที่ส่งต่อเดิม คน B ควรปรับ `coverage_service.py` ให้รับรูปแบบ package จริง หรือทั้งสองฝ่ายตกลง wrapper/artifact layout ที่เป็นทางการพร้อม checksum ครบทุกไฟล์ **ก่อน merge**

ทดสอบ local แบบ bridge ที่แยกจาก PR แล้วผ่าน readiness, Gemini question, model scoring และ report ครบ 3 รอบ แต่ sidecar `thresholds.json` ใน local เป็นค่าทดสอบ 0.25 ไม่ใช่ค่าที่คาลิเบรตสำหรับ production; ห้ามคัดลอกไปใช้จริง การเริ่ม session บางครั้งยังได้ Gemini `AI_UNAVAILABLE` 503 ต้องทดสอบ retry/failure path ด้วย

## สัญญากลางที่ต้องตกลงร่วมกันก่อนใช้ภาพ

`criterion.evidence_quote` v1 ต้องพบใน text layer จึงใช้กับลูกศร/ภาพไม่ได้ เสนอ contract v2 ที่มี `evidence: {modality, page_number, region, literal_text | observed_fact, verification_status}` และ `deck.pages[]` ที่มี `text_status`, `visual_status`, `slide_status`, `usable_for_questions` พร้อม fixtures ของหน้าข้อความ หน้าภาพ หน้ากำกวม และ error. ทั้งสองฝ่ายต้องยืนยันก่อนแก้ schema กลาง; ห้ามใส่ข้อความ Vision ใน `evidence_quote` แล้วอ้างว่าเป็นข้อความต้นฉบับ

## เกณฑ์ตรวจรับของคน B

- API ปฏิเสธ non-PDF/ไฟล์เสีย/เกินขนาด/เกินหน้า โดยไม่บันทึก deck; สไลด์ 4:3 และภาพล้วนไม่ถูกจัดเป็นรายงานเพราะสัดส่วนหรือไม่มี text layer อย่างเดียว
- ทุก criterion ระบุหน้าและ evidence ที่เปิดกลับไปตรวจได้; ถ้าเป็น flow ต้องชี้ region และ node-edge ที่ตรวจแล้ว
- Backend ใหม่รัน schema/fixture tests, restart, retry, 3 rounds และ tunnel test; real mode ต้องรายงาน `model_source:local_finetuned` และเรียก checkpoint จริง
- ส่ง endpoint/fixture ตัวอย่าง `slide`, `document`, `uncertain`, `visual`, `text`, `probe`, `finish` ให้คน A ต่อ UI

## การวัดผลร่วมกัน

1. PDF gate: precision/recall ของ slide detection และ false reject บน PDF สไลด์ใหม่กับเอกสารทั่วไป
2. Extraction: text accuracy, reading order และ node-edge accuracy ของ flow โดยคนตรวจ
3. Retrieval: Recall@2 ของหน้าหลักฐาน; question grounding: สัดส่วนคำถามที่มีหลักฐานจริง
4. Answer model: คน A รายงาน covered/partial/missing precision, recall, F1, macro F1, off-topic F1, false-covered และกรณีที่ต้องถามเจาะบน PDF หัวข้อใหม่

**การทดสอบในเครื่องคน A:** ใช้สำเนา Backend ท้องถิ่นหรือ adapter ทดสอบที่แยกจาก branch คน B; ผล adapter ยืนยันได้ว่า model package เรียกผ่าน HTTP ได้ แต่ยังไม่ใช่หลักฐานว่า Backend เต็มระบบเชื่อมสำเร็จ ต้องทดสอบหลังคน B ส่ง implementation จริง

## งานคน A ที่ทำคู่กัน

- คง EmbeddingGemma v2 เป็น baseline; ไม่เลือก threshold/checkpoint จาก Deadlocks 100 ที่เปิดผลแล้ว
- ทำชุดประเมินที่เรียก package ผ่าน local HTTP และรายงาน confusion matrix/precision/recall/F1; ระบุชุดสังเคราะห์หรือคำตอบจริงให้ชัด
- เก็บและติดป้ายคำตอบหลาย PDF ใหม่โดยคนสองคน, แยก train/validation/test ตาม PDF ก่อนฝึก candidate ใหม่
- เทียบ candidate กับ v2 บน holdout ใหม่ โดยเน้น covered recall และ false-covered; เปลี่ยน package เฉพาะเมื่อทั้งสองด้านผ่านเกณฑ์
- Frontend แสดงผลตรวจรายหน้าและหลักฐานภาพหลัง contract v2 ตกลงแล้ว
