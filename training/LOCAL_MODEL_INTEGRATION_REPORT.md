# ผลทดสอบโมเดลผ่าน local HTTP adapter

วันที่ 5 พฤศจิกายน 2569 — ฝั่งคน A

## สิ่งที่รันจริง

- โหลด base model `google/embeddinggemma-300m` และ checkpoint `embeddinggemma-coverage-lora-v2` จากเครื่อง แล้วเปิด `work/local_integration/model_adapter_api.py` ที่ `127.0.0.1:8123`
- ส่งคำถาม เกณฑ์ และคำตอบ 100 กรณีของ Deadlocks ผ่าน HTTP `POST /predict` ทีละกรณี โมเดลเรียก `model_package.predict_attempt()` จริง ไม่มี Gemini หรือ fake predictor ในขั้นให้คะแนน
- ทำสำเนา source ของ Backend prototype ไว้ที่ `work/local_integration/friend_backend_snapshot/` โดยไม่คัดลอก `.env`, DB หรือ virtual environment; รันทดสอบ 4 กรณีผ่านและเปิด HTTP ที่ `127.0.0.1:8001` ได้ อัปโหลด PDF แมว 6 หน้าสำเร็จ
- อัปโหลด PDF Deadlocks ที่คัดหน้า 5–14 จำนวน 10 หน้าเข้า Backend snapshot สำเร็จ และมี preview text ทั้ง 10 หน้า; ผลนี้ยืนยันแค่ว่า PDF gate/text extraction รับไฟล์ ไม่ยืนยันว่าอ่าน flow หรือสร้างเกณฑ์ถูก
- Backend snapshot **ยังไม่ต่อกับโมเดล** และไม่มี Gemini key ในสำเนา จึงยังไม่ถือว่า full-stack v1 ทำงานครบ การทดสอบคะแนนผ่าน adapter ยืนยันเพียงจุดต่อโมเดลและค่าที่โมเดลคำนวณ

## ทดสอบร่วมกับ PR #3 ของคน B จริงในเครื่อง

ตรวจ PR #3 ที่ commit `8056755` (ยังเปิด PR อยู่) โดยใช้ worktree ท้องถิ่นแบบ read-only; `backend/tests` ผ่าน **31 tests**. พบ interface ไม่ตรงกัน: PR #3 ต้องการ `load_model(artifact_dir)`, `checkpoint_file` ใน manifest และ `thresholds.json` แต่ package v2 ของคน A ให้ `configure_model(base_model_path,checkpoint_dir,manifest_path)` กับ LoRA + Dense heads หลายไฟล์

เพื่อพิสูจน์ทางเชื่อมโดยไม่แก้ branch คน B ได้สร้าง `work/local_integration/local_model_bridge.py` และ artifact directory **เฉพาะ local** ที่ `work/local_integration/pr3_artifacts/`. ค่า Agent confidence gate 0.25 ใน sidecar เป็นค่าทดสอบ ไม่ใช่ threshold production ที่คาลิเบรตแล้ว จึงห้ามนำ directory นี้ไป deploy หรืออ้างคะแนน Agent เป็นคุณภาพจริง

- PR #3 real mode ที่ `127.0.0.1:8002` ตอบ `/api/ready` HTTP 200: DB/model/question service พร้อม, `model_source:local_finetuned`, `model_version:embeddinggemma-coverage-lora-v2`, `test_mode:false` ใน session
- อัปโหลด PDF Deadlocks 10 หน้า HTTP 200, สร้างคำถามจาก Gemini และหลักฐานสไลด์ HTTP 200, ตอบผ่าน EmbeddingGemma v2 แล้ว Agent เลือก `next` HTTP 200; ต่อ session จนครบ 3 รอบและเปิด report HTTP 200
- การเริ่ม session อีกครั้งหนึ่งตอบ HTTP 503 `AI_UNAVAILABLE` จากผู้ให้บริการ Gemini แม้ readiness เป็น 200; แสดงว่า readiness ตรวจ config/การโหลดบริการ ไม่รับประกัน availability ระหว่างคำขอ
- Smoke ใช้ข้อความ criterion เป็นคำตอบเพื่อตรวจเส้นทาง API จึง **ไม่ใช่การวัดคุณภาพคำถามหรือการเข้าใจคำตอบมนุษย์**; ค่า Recall/F1 100 กรณีวัดจาก HTTP adapter แยกด้านบน
- ผลย่ออยู่ใน `work/local_integration/pr3_live_smoke.json` และ `pr3_continue_smoke.json`; เซิร์ฟเวอร์ทดสอบผูกกับ loopback เท่านั้น
- Frontend branch คน A เปิดที่ `127.0.0.1:5174` โดย proxy `/api` ไป PR #3 local port 8002; browser smoke ใช้ Deadlocks PDF 10 หน้า ตรวจไฟล์ผ่านและกดเริ่มซ้อมจนหน้า practice เปิดได้ ไม่มี JavaScript page error

ก่อนรวมงานจริง คน A กับ B ต้องเลือก interface/artifact format เดียวกันและกำหนด confidence gates จาก validation ไม่ใช้ bridge/local sidecar นี้เป็น production config

## ผล 100 กรณี (ผู้พัฒนาเขียนคำตอบและติดป้ายเอง)

| ตัววัด | ผล |
|---|---:|
| สถานะตรงเฉลย | 53/100 |
| Coverage macro F1 | 0.528 |
| `covered` precision / recall / F1 | 0.889 / 0.400 / 0.552 |
| `partial` precision / recall / F1 | 0.271 / 0.650 / 0.382 |
| `missing` precision / recall / F1 | 0.706 / 0.600 / 0.649 |
| Off-topic precision / recall / F1 | 1.000 / 0.800 / 0.889 |
| ให้ `covered` ผิดในคำตอบที่ไม่ครบ | 2/60 |

ผล HTTP ตรงกับการประเมิน checkpoint โดยตรงเดิม จึงยืนยันว่า API adapter ไม่ได้เปลี่ยนคะแนน ปัญหาหลักคือ 24/40 คำตอบที่ควร `covered` ถูกลดเป็น `partial` หรือ `missing`

ทดลองใช้ `confidence` เดิมเป็นเกณฑ์ขอให้ตอบเพิ่ม (เพื่อวิเคราะห์เท่านั้น): ที่ขั้นต่ำ 0.25 โมเดลตัดสินเอง 45/100 กรณีและตรงเพียง 60%; ที่ 0.50 ตัดสินเองเพียง 4/100 แม้ถูกทั้ง 4 กรณี จึง **ยังไม่ควรใช้ confidence gate เป็นคำตอบหลัก** ข้อมูลชุดนี้ถูกเปิดผลแล้ว และ confidence เป็นระยะห่างจาก threshold ไม่ใช่ probability

## ทดลองเพิ่ม: ปรับคะแนนตามเกณฑ์แต่ละข้อ

ทดลองคะแนน `cosine(anchor,answer) - cosine(anchor,criterion-as-answer)` โดยเลือก threshold จาก validation 98 แถวเท่านั้นและคง off-topic gate เดิม ผล **ไม่ผ่าน**: validation macro F1 ลดจาก 0.690 เป็น 0.623, covered recall ลดจาก 0.567 เป็น 0.433 และ false-covered เพิ่มจาก 0.015 เป็น 0.029; บน synthetic test ที่เคยเปิดผลแล้ว macro F1 ลด 0.659 → 0.638; บน Deadlocks diagnostic covered recall ลด 0.40 → 0.35 และ false-covered เพิ่ม 0.033 → 0.067 จึงไม่เปลี่ยน package/checkpoint/manifest วิธีนี้ยังไม่ใช่คำตอบสำหรับ PDF หัวข้อใหม่

การรันคะแนนแบบ batch ใน experiment มี 1 กรณีใกล้ threshold ที่ผล baseline ต่างจากการเรียก package ผ่าน HTTP (52 แทน 53 จาก 100); ให้ใช้ผล HTTP 53/100 เป็นตัวเลขอ้างอิงของ package จริง และอย่าใช้ความต่างใกล้ threshold นี้กล่าวว่าการทดลองดีขึ้น ผลละเอียดอยู่ใน `training/optimization/reference_normalization_pilot.json`

## งานถัดไปของคน A

1. ให้คนที่สองตรวจป้ายของชุดเดิมแบบไม่เห็นเฉลยเดิม เพื่อแยกโมเดลผิดออกจากกรณี rubric/label กำกวม
2. เก็บคำตอบจริงจาก PDF ใหม่หลายหัวข้อพร้อมเกณฑ์/หลักฐาน ตรวจสองคน และแยก deck-level train/validation/test ก่อนฝึก
3. ทดลอง candidate ที่อ่าน question + criterion + answer พร้อมกัน เทียบ v2 บน validation แล้วเปิด holdout ใหม่เพียงเมื่อกำหนดวิธีแล้ว
4. รายงาน covered recall, macro F1, false-covered, off-topic F1, และผลแยกตามหัวข้อ; ไม่เผยแพร่ checkpoint ใหม่หากไม่มีหลักฐานว่าดีกว่า v2 ทั้งด้านจับประเด็นและความปลอดภัยของการให้ `covered`

## รันซ้ำในเครื่องนี้

```powershell
$env:PYTHONUTF8='1'
& work/train-venv/Scripts/python.exe work/local_integration/model_adapter_api.py
# อีก terminal
& work/train-venv/Scripts/python.exe work/local_integration/evaluate_model_api.py
```

รายกรณีและตัวเลขเต็มอยู่ใน `work/local_integration/api_eval_results.json` ซึ่งอยู่นอก repo สาธารณะ น้ำหนักโมเดลและ PDF ต้นฉบับก็อยู่นอก repo
