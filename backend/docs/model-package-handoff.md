# จุดรับ model package จากคน A

API/model schema v1 ใน `contracts/v1/` ที่ราก repository ไม่ได้กำหนดชื่อฟังก์ชันโหลด package จึงแยก **ข้อเสนอการติดตั้ง adapter ของ Backend นี้** ไว้ที่นี่ โดยไม่เปลี่ยน schema กลาง คน A ต้องยืนยัน wrapper นี้ หรือคน B ปรับ loader ให้ตรงกับ package จริงก่อน integration

## Python interface

`MODEL_PACKAGE_MODULE` เป็นชื่อ module ที่ติดตั้งและ import ได้ใน environment ของ Backend:

```python
from pathlib import Path

def load_model(artifact_dir: Path):
    # โหลด checkpoint, tokenizer/config, heads/LoRA โดยใช้ path นี้
    return predictor

class Predictor:
    model_version: str  # ต้องตรง manifest

    def validate_attempt(self, question, current_prompt, criteria, answer):
        # ใช้ serialization + tokenizer เดียวกับ predict_attempt
        # จำกัดข้อมูลนำเข้าทั้งหมดรวม special tokens ไม่เกิน 512 tokens
        # return None/True เมื่อผ่าน; False หรือ raise ModelInputTooLong เมื่อเกิน
        ...

    def predict_attempt(self, question, current_prompt, criteria, answer):
        # synchronous; ส่ง dict ตาม model.schema.json output
        ...
```

`question` เป็น canonical question object ตาม schema รวม criteria และหลักฐาน `current_prompt` คือคำถามที่ผู้ใช้กำลังตอบ ไม่รับ prompt ที่ browser อ้างเอง Package ต้องตรวจ token budget โดยไม่ตัดคำตอบเงียบ ๆ และต้องไม่เรียก Gemini หรือแตะ DB/Backend

## Artifact directory

```text
artifacts/
  manifest.json
  checkpoint.bin       # หรือ checkpoint_file ใน manifest
  thresholds.json
  ... tokenizer, config, heads, adapters และไฟล์ที่ loader ต้องใช้
```

Manifest ต้องผ่าน `model.schema.json#/$defs/manifest`:

```json
{
  "contract_version": 1,
  "model_version": "ทีมกำหนดตาม checkpoint จริง",
  "base_model": "google/embeddinggemma-300m",
  "fine_tuned": true,
  "checkpoint_file": "checkpoint.bin",
  "checkpoint_sha256": "ใส่ SHA256 จริง 64 ตัวอักษร hex ตัวเล็ก",
  "max_input_tokens": 512
}
```

ตัวอย่างด้านบนยังใช้รันไม่ได้ ต้องเติม hash จริงก่อน `checkpoint_file` เป็น relative path ภายใน artifact directory ใช้ไฟล์ checkpoint/export หลักหนึ่งไฟล์เพื่อตรวจ hash; ถ้า package ส่งหลาย shards ให้ตกลงวิธีรวม hash กับคน B แล้วปรับ adapter ก่อน ไม่มีการสมมติ hash ให้เอง ฟิลด์เสริมนี้ไม่เปลี่ยน required fields ของ v1

`thresholds.json` เป็น sidecar สำหรับ Agent ต้องส่งค่าที่เลือกจาก validation set จริง:

```text
{"coverage": <ค่าที่วัดจริงในช่วง (0,1]>, "off_topic": <ค่าที่วัดจริงในช่วง (0,1]>}
```

ไม่กำหนด threshold จริงล่วงหน้า ค่า `.8` ในโค้ดใช้เฉพาะ fake tests เท่านั้น Real mode จะไม่พร้อมถ้าขาด thresholds

Backend ตรวจ shape, confidence, criterion IDs แบบครบและไม่ซ้ำ, model version และ checkpoint hash ขณะ startup การตรวจ hash ไม่ได้พิสูจน์ว่าไฟล์ถูกฝึกหรือคุณภาพผ่านเกณฑ์ คน A ยังต้องส่ง dependency lock, baseline, metrics แยก class/macro F1/off-topic F1/false praise rate, dataset split ตาม deck/topic และข้อจำกัดผลทดลอง

การทดสอบใน repository ใช้ stub package + checkpoint ข้อความจำลองเพื่อทดสอบขอบเขต adapter เท่านั้น ห้ามนำไฟล์หรือผลทดสอบนั้นอ้างเป็นโมเดลจริง

เมื่อได้รับของจริง: ติดตั้งใน environment ใหม่ → readiness → predict ตัวอย่าง covered/partial/missing/off-topic/ขัดกัน/ยาวเกิน → restart → flow API → Frontend → tunnel แล้วบันทึกผลใน `verification.md`
