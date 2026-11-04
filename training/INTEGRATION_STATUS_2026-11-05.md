# ฝั่ง Frontend และโมเดล: สถานะส่งต่อ 5 พฤศจิกายน 2569

## สิ่งที่ทำแล้ว

- โมเดลที่ใช้ยังเป็น EmbeddingGemma 300M LoRA **v2**; ไม่ได้อ้างว่าฝึกใหม่หรือแม่นขึ้นจากการเปลี่ยนตัวเชื่อม
- เพิ่ม `model_package.load_model(artifact_dir)` และ `model_version` ให้ตรงกับ `CoverageService` ใน Backend PR #3; โหลดจริงผ่าน adapter ของ PR #3 ได้ โดยไม่แก้โค้ด Backend
- ส่งออก checkpoint และ `thresholds.json` ในโครงสร้างที่ PR #3 อ่านได้ โดยเก็บน้ำหนักไว้ใน private directory นอก Git; ตรวจ SHA-256 ของ adapter และ Dense modules ก่อนส่งออก
- คัดเลือก Agent confidence gates จากข้อมูลพัฒนา **สังเคราะห์** 98 แถว: `coverage=0.08`, `off_topic=0.01`; ค่าเหล่านี้ควบคุมว่า Agent จะขอคำชี้แจงเมื่อคะแนนไม่ชัดเจน ไม่ใช่ความแม่นยำของโมเดล และข้อมูลชุดนี้เคยใช้พัฒนา v2 จึงไม่ใช่ independent test
- หน้าเว็บคง `attempt_id` เดิมเมื่อคำขอตอบกลับ 503 เพื่อให้ retry ตามสัญญากลางได้; smoke test ครอบคลุม 429 และ 503

## ผลตรวจที่ทำซ้ำได้

| ส่วน | ผล |
| --- | --- |
| Frontend production build | ผ่าน |
| Frontend contract smoke | ผ่าน: upload, probe, refresh, 6 attempts, report, retry 429/503 ด้วย ID เดิม |
| Python data tests | 4/4 ผ่าน |
| Backend PR #3 adapter + checkpoint จริง | `ready=true`, version ตรง, คำตอบตัวอย่างได้ `covered/covered` |

คำสั่งทดสอบตัวเชื่อมอยู่ใน [model_package/README.md](../model_package/README.md) โดยต้องมี local checkout ของ Backend PR #3, base weights และ private artifact directory ก่อน

## ข้อจำกัดที่ยังต้องแก้ก่อนอ้างว่าพร้อมใช้กับสไลด์ทุกหัวข้อ

- ผลเดิมบนคำตอบสังเคราะห์จากสไลด์ใหม่ 100 กรณี: exact 78%, macro F1 0.754, `covered` recall 25/40; คำตอบภาษาไทยที่ครบจริงยังถูกลดเป็น `partial` บ่อย ตัวเชื่อมและ Agent gates รอบนี้ไม่ได้เปลี่ยนค่าทดสอบดังกล่าว
- ยังไม่มีคำตอบนักศึกษาจริงที่มีผู้ตรวจอิสระสองคนเพียงพอสำหรับฝึก/เลือก threshold/ทดสอบแยกตามหัวข้อ PDF; จึงยังไม่เลือก v3 เพื่อแทน v2
- Backend PR #3 ยังจำกัด PDF 1–10 หน้าและดึงข้อความด้วย `pypdf`; ฝั่งเรายังไม่รองรับภาพล้วน/flow ใน PDF ผ่าน UI และไม่ได้แก้ Backend ของเพื่อน
- โควตา Gemini และคุณภาพคำถามเป็นความรับผิดชอบของ Backend; แผนส่งต่ออยู่ในเอกสารของเพื่อนแยกต่างหาก

ขั้นถัดไปของโมเดล: รับคำตอบจริงหลายหัวข้อ, ติดป้าย `covered/partial/missing/off_topic` โดยผู้ตรวจสองคน, แยก train/validation/test ตาม PDF ก่อนฝึก แล้วทดลอง hard positives ภาษาไทย–อังกฤษและ hard negatives แบบขาดหนึ่งประเด็น เก็บ PDF test ใหม่ที่ไม่ใช้ปรับพารามิเตอร์
