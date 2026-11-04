# AI Presentation Trainer — ชุดเอกสารส่งต่อ

เอกสารชุดนี้ใช้แบ่งงานสองคนและประกอบระบบตามสัญญากลาง v1 ฝั่ง Backend มีโค้ด API/state และโหมดทดสอบแล้ว ส่วนการใช้โมเดลจริงและการเชื่อมทั้งระบบยังไม่ยืนยัน

โค้ดฝั่งคน B อยู่ใน [`backend/`](backend/README.md) พร้อมวิธีรัน ตัวอย่าง response และผลทดสอบ ใช้สัญญากลางที่ `contracts/v1/` ร่วมกันโดยไม่ทำสำเนาแยกใน Backend การทดสอบ AI ที่มีอยู่ใช้ fake model/stub package/mock provider ยังไม่มีผลยืนยันการเทรนโมเดลจริงหรือการเชื่อม Frontend/tunnel

## ลำดับอ่าน

1. [ภาพรวมระบบ](shared-system-overview-v1.md) — ระบบทำอะไร ผู้ใช้ใช้อย่างไร AI แต่ละส่วนทำหน้าที่อะไร และ flow ข้อมูล
2. [งานคน A: Frontend + เทรนโมเดล](frontend-implementation-plan-v1.md) — UI, mock API, ชุดข้อมูล, fine-tune, metrics และ `model_package`
3. [งานคน B: Backend + RAG/Agent](backend-ai-implementation-plan-v1.md) — PDF/RAG, Gemini, DB, session, Agent และ adapter เชื่อมโมเดล
4. [สัญญากลาง](contracts/v1/README.md) — กติกา API และ model interface; schema/fixtures/tests อยู่ใน `contracts/v1/`

## จุดส่งมอบร่วม

- คน A ส่ง `frontend/`, `training/`, `model_package/`, checkpoint manifest และผลวัด
- คน B ส่ง `backend/` ที่ตอบ API v1 และติดตั้ง package ของคน A ได้
- ทั้งคู่ใช้ `contracts/v1/` รุ่นเดียวกัน; ถ้าจะเปลี่ยน field/ความหมาย ให้แก้ schema, fixtures และ tests ร่วมกันก่อน

รันตรวจสัญญาจากรากโฟลเดอร์นี้ด้วย Python ที่มีบนเครื่อง:

```powershell
python contracts/v1/validate.py
python -m unittest discover -s contracts/v1 -p test_contract.py -q
```

`central-contract-v1.zip` เป็นสำเนาสัญญากลางสำหรับส่งแยก หากส่งทั้งโฟลเดอร์นี้อยู่แล้ว ใช้ `contracts/v1/` โดยตรงได้
