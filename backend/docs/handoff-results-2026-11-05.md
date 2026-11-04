# ผลแก้ Backend ตาม handoff — 5 พฤศจิกายน 2569

ทำงานใน branch `backend-v1` ที่ checkout หลัก ดึงเฉพาะ `model_package/` จาก `origin/feat/frontend-v1` commit `fab43318f7626ae87955e240660561bf97b0c6c6` โดยไม่ merge branch Frontend รายงานนี้บันทึกผลตรวจ implementation ก่อนส่ง commit ให้รีวิว

## ส่วนที่ทำและตรวจแล้ว

| งาน | ผลปัจจุบัน |
|---|---|
| Model v2 loader | รองรับ CoverageModel โดยตรงและ factory เดิม; ตรวจ LoRA/Dense 2/Dense 3 hashes, class thresholds, Agent gates แยกกัน; stub tests ผ่าน |
| Gemini quota | แยก endpoint และ RPM/RPD, อ่าน RetryInfo/Retry-After, bounded retry, daily cooldown ข้าม restart; mock tests ผ่าน |
| RAG | embedding batch/cache จาก content hash, เลือกหน้าที่ยังไม่ใช้, ตรวจ quote ใน retrieved chunk และ semantic dedup; tests และ live preview ผ่านตามขอบเขตด้านล่าง |
| PDF diagnostics | CLI แยก slide/document/uncertain รายหน้าและ text blocks/coordinates แบบ heuristic; ทดสอบเอกสารสังเคราะห์ 10/30/58/86 หน้า |
| Contract v2 proposal | schema/fixtures สำหรับ original/selected pages, async ingestion, evidence และ quota metadata; schema tests ผ่าน แต่ยังไม่เปิดใน HTTP |
| Backend ใน environment ใหม่ | `pytest backend/tests -q`: 54 passed, 1 warning, 13.21 วินาที |
| สัญญากลางเดิม | validator ผ่าน, unittest 7 tests ผ่าน; ไม่เปลี่ยน `contracts/v1/` |
| Dependency check | `pip check`: No broken requirements found |
| Frontend production candidate + Backend หลังแก้ | 12 checks ผ่าน, fake model เท่านั้น |

Warning เดิมมาจาก Starlette TestClient ที่ใช้ httpx; ไม่ใช่ test failure ใช้ environment ใหม่ `backend/.venv` จาก requirements.lock.txt ของ Backend ไม่ได้ติดตั้ง model GPU stack หรืออ้างว่าทดสอบ torch/LoRA แล้ว

## ผล live Gemini ที่ทำจริง

ใช้ generation `gemini-3.5-flash-lite` และ retrieval `gemini-embedding-001` กับ PDF สังเคราะห์ใหม่ 3 เรื่อง เรื่องละ 10 หน้า/10 คำถาม ได้แก่ library_pilot, repair_cafe และ campus_delivery เนื้อหาเป็นข้อมูลแต่งสำหรับทดสอบ ไม่มีข้อมูลผู้ใช้จริง

- เก็บคำถามที่ผ่าน schema/เลขหน้า/literal quote ในหลักฐาน/duplicate guard ครบ 30 ข้อ แต่ละ deck มีหลักฐานรวมครอบคลุมหน้า 1–10
- มีคำขอระดับ preview ไม่ผ่าน 7 ครั้งจากทั้งหมด 37 ครั้ง เก็บ failures ไว้ด้วย ไม่ใช่ผลสำเร็จ 100% ในการลองครั้งแรก ภายใน preview อาจลอง generation ได้ 2 ครั้ง
- provider requests รวม 132 ครั้ง ไม่พบ HTTP 429 ในรอบนี้ การแยก RPM/RPD จึงยืนยันจาก mock error tests ไม่ได้อ้างว่าจงใจใช้โควตาจริงจนหมด
- รอบแรกได้ 27 ข้อ ต่อมาจึงเพิ่ม diagnostics/แก้การนับหน้าที่ใช้จริงและเปลี่ยนหลักฐานเมื่อ semantic duplicate แล้วเก็บเพิ่มถึง 30 ข้อ `phases` แสดง policy hashes สำหรับช่วงที่บันทึกได้ รอบแรกไม่มี hash ณ เวลารันจึงใส่ null ไม่แต่งหลักฐานย้อนหลัง
- เป็น question-only preview ที่ข้าม model tokenizer budget โดยตั้งใจ ไม่มีการเริ่ม session หรือให้คะแนนคำตอบใน real mode
- `human-review.csv` ยังว่าง รอคนตรวจความถูกต้องทางความหมาย/ความตรงประเด็น/ความซ้ำ/ความยาก ความตรงของ literal quote และ cosine guard ไม่รับรองว่าคำถามไม่มีการตีความเกินสไลด์

ผลเต็ม: [handoff-questions.json](integration-results/handoff-questions.json), [แบบตรวจโดยคน](integration-results/handoff-human-review.csv), [production flow](integration-results/handoff-production.json)

PDF fixtures อยู่ `examples/question-audit/` สร้างด้วย `tools/make_question_decks.py` ตรวจภาพ render ทั้ง 30 หน้าแล้ว คำสั่ง live audit จากราก repo:

```powershell
backend/.venv/Scripts/python.exe -B -m backend.tools.question_benchmark backend/examples/question-audit/library_pilot.pdf backend/examples/question-audit/repair_cafe.pdf backend/examples/question-audit/campus_delivery.pdf --count-per-deck 10 --output backend/.integration/question-audit
```

`--resume` เก็บคำถามและ failures เดิม เติมเฉพาะจำนวนที่ขาด มีจำนวนลองเพิ่มจำกัดและหยุดเมื่อ provider ส่ง 429 การรันซ้ำใช้โควตาจริง ห้ามนำรายงานหลายรอบมารวมแล้วลบ failures

## โมเดลจริงยังขาดอะไร

Branch ของคน A มี Python interface/README/requirements/manifest แต่ไม่มี actual base model, LoRA checkpoint, Dense heads และ calibrated Agent gates การค้น Downloads/Documents/Desktop และ Hugging Face cache ไม่พบชุดน้ำหนักนี้ ไม่สร้าง sidecar ค่าทดลองแทนของจริง

Readiness จริงเมื่อใช้ package นี้ได้ HTTP 503, `model_source:local_finetuned`, `model_ready:false`, `question_service_ready:true` และ `X-Model-Error:MODEL_ARTIFACT_MISSING` ไม่มี fallback รายงาน: [handoff-model-readiness.json](integration-results/handoff-model-readiness.json)

จึงยังไม่ได้ยืนยัน actual tokenizer 512 tokens, predict/coverage/false praise, latency/memory ของ checkpoint และ real-model API/UI end-to-end ต้องรับไฟล์จากคน A แล้วทำต่อ ดู [model-package-handoff.md](model-package-handoff.md)

## PDF และ Frontend ที่ยังต้องตกลง

Active v1 ยังรับ PDF 1–10 หน้า เกินได้ PDF_PAGE_LIMIT พร้อมคำแนะนำแบ่งช่วง CLI inspect อ่านไฟล์ยาวได้ แต่ไม่ได้หมายความว่า HTTP/UI รับ 30/58/86 หน้าแล้ว ดู [draft schema และข้อเสนอ](../proposals/README.md) เพื่อยืนยันร่วมกันก่อนปรับ active contract

Classifier เป็น heuristic ที่ยังไม่มี precision/recall พิกัดจาก pypdf ยังไม่ verified ไม่ทำ OCR/Vision และไม่เปลี่ยนคำบรรยายภาพเป็น literal evidence_quote ไม่มีผลภาพ flow/สูตร/กราฟจริงที่ยืนยันแล้ว

Frontend smoke ใช้ candidate commit `133b2a8` บวก recovery patch เดิมใน isolated checkout ไม่ใช่การยืนยัน Frontend ล่าสุด `fab4331` ทั้ง branch ไม่มีการแก้ UI เพิ่มในงานรอบนี้ Public tunnel และอุปกรณ์อีกเครื่องยังไม่ทดสอบ
