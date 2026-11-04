# ข้อเสนอร่วมกับคน A — ยังไม่เปิดใช้ใน HTTP

ไฟล์ schema/fixtures นี้เป็น draft ที่ตรวจรูปแบบได้ ไม่ได้แทน `contracts/v1/` และไม่ได้หมายความว่า ingestion background หรือ Vision ทำแล้ว

## PDF ยาว

- ระยะสั้นเสนอ original PDF ไม่เกิน 100 หน้า/15 MB และให้ผู้ใช้เลือกไม่เกิน 30 หน้าเพื่อ index เลขหน้าอ้างอิงใช้เลขเดิมเสมอ `GET file` ยังเสิร์ฟ PDF ต้นฉบับ
- `page_count` หมายถึงจำนวนหน้าต้นฉบับ; `selected_pages` คือหน้าที่นำไปค้น ห้ามใช้จำนวนหน้าที่เลือกแทนเลขหน้าต้นฉบับ
- ช่วงที่เลือกไม่เกิน 80 chunks ใช้ batch 16 จึงไม่เกิน 5 calls สำหรับ document embeddings มี context top 2 chunks และ deadline รวม 115 วินาที
- ถ้าจะ index เต็ม 58/86 หน้า เสนอ POST คืน 202 พร้อม deck/job ID และ GET status แสดง queued/extracting/indexing/ready/failed ภายหลัง จำกัด 512 chunks, แบ่ง batch 16, มี worker lease/retry และ cache ด้วย PDF SHA-256 + extraction/index/model version
- ต้องทดสอบไฟล์จริง 10/30/58/86 หน้า, Recall@k, latency, memory และ call counts ก่อนเปิดใช้ ไม่ยก cap แล้วส่ง embeddings ทั้งไฟล์ใน call เดียว
- ปัจจุบัน v1 ยังรับ 1–10 หน้า และตอบ PDF_PAGE_LIMIT พร้อมคำแนะนำแบ่งช่วง ไม่ได้มีตัวเลือกช่วงหน้าใน UI v1

## Slide/document และภาพ

- รายงานรายหน้าเป็น slide/document/uncertain พร้อมสถานะ text/visual แยกกัน UI ต้องให้ผู้ใช้พิจารณากรณี uncertain ไม่ reject จาก aspect ratio เพียงอย่างเดียว
- `pdf_inspection.py` ตอนนี้เป็น heuristic ที่ยังไม่วัด precision/recall และ coordinates จาก text visitor ยังไม่ยืนยันความถูกต้อง จึงไม่ใช้เป็น visual evidence หรือเปลี่ยน upload policy อัตโนมัติ
- text evidence ต้อง match literal text หลัง normalize whitespace ส่วน visual evidence ใช้ observed_fact และ region ที่ตรวจได้ ไม่แปลงคำบรรยายภาพเป็น evidence_quote ของ v1
- region ใน draft เป็น normalized top-left coordinates ต้องตรวจ x+width<=1 และ y+height<=1 เพิ่มใน runtime
- uncertain visual evidence ต้อง usable_for_questions=false การมี confidence สูงอย่างเดียวไม่เพียงพอให้ตั้งคำถาม
- ต้องตกลงว่าใคร/ขั้นตอนใดยืนยัน reviewed_visual และทดสอบภาพ flow/สูตร/กราฟจริงก่อนใช้ flag นี้

## Quota metadata

v1 ตอนนี้ส่ง Retry-After และ X-AI-Endpoint/X-AI-Error-Category พร้อม error code โดยไม่เพิ่ม required JSON fields ส่วน draft เสนอ error.stage, quota_scope, retry_after_seconds/retry_at เพื่อให้ UI แสดงเวลาลองใหม่ตามสาเหตุจริง

คน A ต้องปรับ UI ให้อ่านเวลาจาก header/field ที่ตกลงและไม่แสดงข้อความให้ retry ทันทีเมื่อ RPD หมด ปัจจุบันไม่ได้อ้างว่า UI แสดงเวลานี้แล้ว

## จุดที่ต้องยืนยัน

1. เพดาน original/selected pages, synchronous budget และ 202 status/job lifecycle
2. ความหมายและหน่วย region, verification status และสิทธิ์ตัดสิน uncertain
3. รูปแบบ quota metadata และ backward compatibility ของ API client
4. version ใหม่และชุด fixtures/error cases ร่วมกันก่อนแก้ active schema และ routes
