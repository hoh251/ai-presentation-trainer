# PDF slide pipeline — review and Backend handoff

วันที่ 5 พฤศจิกายน 2569 — ข้อเสนอสำหรับฝั่ง Backend; ยังไม่ใช่การแก้สัญญากลางหรือโค้ด Backend

## ขอบเขตและสถานะจริง

- รับ **PDF เท่านั้น** ไม่เพิ่ม PPTX ตามสัญญา v1: ไม่เกิน 15 MB, 1–10 หน้า เว้นแต่ทั้งสองฝ่ายตกลงเปลี่ยนสัญญา
- Frontend branch นี้มี `src/slideCheck.js` ตรวจเบื้องต้นจากสัดส่วนหน้า ขนาดตัวอักษร และจำนวนตัวอักษร แต่สไลด์ภาพล้วน/ข้อความหนาแน่นอาจถูกปฏิเสธผิด การตัดสินที่ API ต้องอยู่ฝั่ง Backend
- Backend prototype ใช้ `pdfplumber.extract_text()` ไม่มี slide classifier, OCR หรือ Vision; PDF ภาพล้วนได้ `PDF_NO_TEXT`
- EmbeddingGemma LoRA v2 ที่คน A ฝึก ใช้ **ตรวจคำตอบตามเกณฑ์** ไม่ได้อ่านภาพหรือดึงข้อความจาก PDF
- Deadlocks PDF มี 53 หน้า เป็นสไลด์จริงแต่เกินขีดจำกัด v1; คัด 10 หน้ามาทดสอบ parser ได้โดยไม่เปลี่ยนข้อจำกัดอัปโหลด

## ประเมิน pipeline ในภาพ

| ข้อเสนอ | ข้อสรุป |
|---|---|
| Layout-aware parser เช่น PyMuPDF4LLM, MinerU หรือ Marker | ควรทดลองเทียบกับ `pdfplumber` บน PDF ไทยของเรา ตำแหน่งบล็อกและลำดับอ่านอาจช่วย แต่ยังไม่มีผลวัดว่าเครื่องมือใดดีกว่าสำหรับไฟล์ของเรา |
| `1 slide = 1 chunk = 1 vector` | ใช้หน้าเป็น **หน่วยอ้างอิง** ได้ แต่ไม่บังคับหนึ่งเวกเตอร์ หน้าเดียวอาจมีหลายประเด็นและมีเนื้อหายาว ให้ทำ page parent + block/region child |
| เติมชื่อหัวข้อใหญ่/บทลงทุกหน้า | ใช้เป็น metadata ช่วยค้นได้เฉพาะเมื่อเห็นใน deck จริง; ห้ามเอาข้อความที่เติมไปเป็นหลักฐานหรือเกณฑ์คำตอบ |
| Fine-tune anchor-positive-negative จากคนละสไลด์ | เป็นการทดลอง retrieval model คนละงานกับ coverage scorer v2 ปัจจุบัน; negative จากหน้าอื่นอาจยังเกี่ยวข้อง ต้องมีป้ายกำกับและชุดทดสอบใหม่ |

## Pipeline ที่แนะนำ

1. **File gate:** ตรวจ PDF magic bytes, parseability, password, ขนาด และจำนวนหน้า ก่อนบันทึก deck; ปฏิเสธไฟล์อื่นพร้อมเหตุผล
2. **Slide gate:** ตรวจสัญญาณหลายหน้า เช่น aspect ratio, ความหนาแน่นข้อความ, ขนาดฟอนต์, บล็อก/คอลัมน์ และพื้นที่ภาพ สรุประดับ deck เป็น `slide`, `document`, `uncertain`; สไลด์ 4:3, แนวตั้ง, ภาพล้วนและรายงานแนวนอนต้องอยู่ในชุดทดสอบ ไม่ใช้ 16:9 เป็นกฎตายตัว
3. **Text extraction:** เก็บ text layer ตามหน้า/บล็อก/ตำแหน่ง; เทียบ parser บนไฟล์เดียวกัน แล้วเลือกด้วยผลตรวจข้อความและ reading order จริง
4. **Visual pass:** ส่งทั้งหน้าภาพล้วน **และหน้าที่มี flow/กราฟ/ตารางซึ่ง text layer อธิบายไม่ครบ** ให้ Gemini Vision ขอวัตถุ กล่อง ลูกศร ทิศทาง และตำแหน่งโดยประมาณ แยกข้อสังเกตจากข้ออนุมาน ถ้าไม่แน่ใจให้ `uncertain` และไม่ใช้ตั้งคำถาม
5. **Evidence store:** เก็บ page number, block/region ID, modality (`text`/`visual`), bbox, literal text หรือ observed visual fact, verification status และ parser/vision version; ข้อมูลจาก Vision เป็นผลอนุมาน ต้องตรวจย้อนกับภาพต้นฉบับ
6. **Retrieval:** หน้าเป็น parent; index บล็อกหรือ visual relation เป็น child แล้วรวมผลกลับตามหน้า ไม่บังคับหนึ่งเวกเตอร์ต่อหน้า; 512 tokens คือขีดจำกัด input ของ coverage model v2 ไม่ใช่ขนาด chunk ที่พิสูจน์แล้ว
7. **Question and answer:** Gemini สร้างคำถาม/เกณฑ์จาก evidence ที่ตรวจแล้ว, EmbeddingGemma v2 ตรวจ `covered/partial/missing/off_topic`, Agent เลือกถามเจาะ/ถามใหม่, Gemini เรียบเรียง feedback ตามผลและหลักฐาน

## ข้อเสนอเปลี่ยนสัญญากลางสำหรับ visual evidence

สัญญา v1 บังคับ `criterion.evidence_quote` ให้พบในข้อความ PDF หน้าอ้างอิง จึงยังอ้างลูกศรหรือภาพที่ไม่มี text layer ไม่ได้ ก่อน implement ต้องให้ทั้งสองฝ่ายตกลง version ใหม่ พร้อม schema/fixtures:

```json
{
  "id": "c1",
  "text": "อธิบายทิศทางจาก A ไป B",
  "source_page": 4,
  "evidence": {
    "modality": "visual",
    "page_number": 4,
    "region": [0.12, 0.20, 0.78, 0.65],
    "observed_fact": "ลูกศรจากกล่อง A ชี้ไปกล่อง B",
    "verification_status": "verified"
  }
}
```

- `text` evidence ต้องมี quote จริงใน text layer หลัง normalize whitespace; `visual` evidence ต้องมีหน้าและ region แบบ normalized 0–1 พร้อมตรวจภาพต้นฉบับ
- ห้ามนำประโยคที่ Vision สร้างไปใส่ `evidence_quote` แล้วอ้างว่าอยู่ใน PDF; metadata ที่เติมเพื่อช่วยค้นไม่เป็นหลักฐาน
- Frontend ต้องแสดงหน้า/บริเวณอ้างอิงและสถานะอ่านภาพ/ไม่แน่ใจ; ปัจจุบันยังไม่มี field เหล่านี้
- Visual criteria เป็นข้อมูลรูปแบบใหม่ที่ coverage model v2 ไม่เคยฝึกโดยตรง ต้องทดสอบหรือฝึกเพิ่มก่อนอ้างความแม่นยำ

## พิสูจน์ว่าใหม่ดีกว่าเดิมอย่างไร

ล็อก PDF/เฉลยก่อนทดลอง: สไลด์ไทย 16:9/4:3, ภาพล้วน, flow, หลายคอลัมน์, หน้าแน่น, PDF รายงานแนวตั้ง/แนวนอน และไฟล์ไม่ใช่ PDF ให้คนสองคนตรวจกรณีกำกวม

| ขั้น | ตัววัดและฐานเปรียบเทียบ |
|---|---|
| Slide gate | precision/recall, false reject ของสไลด์จริง เทียบ heuristic เดิม |
| Extraction | ความถูกต้องของ text, reading order, ตาราง และ node-edge ของ flow เทียบ `pdfplumber` |
| Retrieval | Recall@2 ของหน้าหลักฐานและ region ที่คนระบุ เทียบ text-only page retrieval |
| Question | สัดส่วนคำถามที่ตอบได้จากหลักฐานจริงและอ้างหน้าถูก เทียบเดิม |
| Coverage | macro F1, covered recall, off-topic F1, false-covered บนหัวข้อใหม่ เทียบ v2 เดิม โดยไม่ปรับ threshold จากชุดทดสอบ |

Deadlocks 100 กรณีถูกเปิดผลแล้ว (v2 ตรงสถานะ 53/100) ใช้วิเคราะห์ข้อผิดพลาดได้ แต่ไม่ใช่ holdout ใหม่สำหรับเลือก parser/threshold/model

## เจ้าของงาน

- **คน A (Frontend + model):** UI แสดงผลตรวจและบริเวณหลักฐาน, ชุดทดสอบ/label ใหม่, ประเมิน EmbeddingGemma v2 กับ visual criteria, ฝึกใหม่เมื่อมีข้อมูลและผลรองรับ
- **คน B (Backend):** file/slide gate ที่ API, parser comparison, Vision, evidence store, retrieval, Gemini, Agent และ model adapter; คน A ไม่แก้ Backend แทน
- **ทั้งสองฝ่าย:** ตกลง contract version ใหม่ก่อนต่อ visual evidence และทดสอบ end-to-end ร่วมกัน

## แหล่งอ้างอิง

- [DocLayNet (2022)](https://arxiv.org/abs/2206.01062): document layout analysis สำคัญต่อ PDF conversion แต่ไม่ยืนยันผลกับไฟล์ของเรา
- [SlideVQA (AAAI 2023)](https://ojs.aaai.org/index.php/AAAI/article/view/26598): การถามตอบจากสไลด์หลายหน้าต้องเลือกหลักฐานภาพและหน้าที่เกี่ยวข้อง
- [PyMuPDF4LLM chunking documentation](https://github.com/pymupdf/pymupdf4llm/blob/main/CHUNKING.md): page breaks, layout blocks และ retrieval chunks
- [Marker documentation](https://github.com/datalab-to/marker/blob/master/README.md): OCR/VLM แบบเลือกใช้กับหน้าที่ข้อความเดิมใช้ไม่ได้ พร้อมข้อจำกัดของ parsing
- [Gemini document understanding](https://ai.google.dev/gemini-api/docs/document-processing): รองรับภาพ แผนภาพ ตาราง และ structured output จาก PDF
