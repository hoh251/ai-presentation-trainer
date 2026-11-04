# จุดรับ model package จากคน A

อัปเดต 5 พฤศจิกายน 2569: ใช้ `model_package/` จาก `feat/frontend-v1` commit `fab4331` โดยตรง ไม่เพิ่ม runtime bridge Backend รองรับ `CoverageModel` ของ v2 และ factory `load_model(artifact_dir)` แบบเดิม โดยไม่แก้ required fields ของ `contracts/v1/`

## ไฟล์ที่ต้องรับจริง

```text
private-artifacts/
  manifest.json                 # หรือใช้ model_package/manifest.json ที่ดึงมา
  thresholds.json               # Agent gates ที่ calibrate แล้ว
  checkpoint/
    adapter_config.json
    adapter_model.safetensors
    2_Dense/config.json
    2_Dense/model.safetensors
    3_Dense/config.json
    3_Dense/model.safetensors
private-base-model/
  ... weights, tokenizer/config และ SentenceTransformer modules ของ base
```

ไฟล์น้ำหนักและ gates ไม่อยู่ใน branch ที่ดึงมา ต้องรับจากคน A พร้อม dependency versions และ calibration/evaluation report ห้ามใช้ checkpoint จำลองใน tests เป็นของจริง

```dotenv
TRAINER_TEST_MODE=false
MODEL_PACKAGE_MODULE=model_package
MODEL_LOADER=auto
MODEL_ARTIFACT_DIR=C:/private/private-artifacts
MODEL_BASE_PATH=C:/private/private-base-model
MODEL_CHECKPOINT_DIR=C:/private/private-artifacts/checkpoint
MODEL_MANIFEST_PATH=C:/path/to/repo/model_package/manifest.json
MODEL_AGENT_GATES_PATH=C:/private/private-artifacts/thresholds.json
```

`auto` เลือก CoverageModel เมื่อ manifest มี dense_sha256 ตั้ง `coverage_v2` หรือ `package` เพื่อเลือก interface ชัดเจนได้ รองรับ checkpoint ที่ artifact root หรือโฟลเดอร์ checkpoint และ manifest เดิมที่ไม่มี checkpoint_file หากไม่ตั้ง manifest path และ artifact manifest ไม่มี จะใช้ repo/model_package/manifest.json

## การตรวจและ threshold

1. Manifest ต้องผ่าน model schema v1 และไม่เป็น example_only
2. ตรวจ SHA256 adapter ตาม checkpoint_sha256 และ Dense 2/3 ตาม dense_sha256 ถ้ามี artifact_sha256 เพิ่มจะตรวจตามนั้นด้วย
3. validation_thresholds v2 เป็น cosine class boundaries ของ partial/covered/off-topic แยกจาก Agent confidence gates และไม่ใช่ calibrated probability
4. Agent sidecar ต้องมี coverage/off_topic ในช่วง (0,1] พร้อม calibration.rows จำนวนเต็มบวกและ selection ที่บอกวิธีเลือก ขาดแล้วได้ MODEL_GATES_UNCALIBRATED ไม่สร้างค่า .25/.8 แทน Metadata ไม่พิสูจน์ว่าผ่าน human validation ต้องอ่าน report ประกอบ
5. Session identity v2 รวม hash manifest/gates และทุกไฟล์ใน base/checkpoint นอก .cache และ __pycache__ การ fingerprint config ที่ไม่มี expected hash ใช้ตรวจชุดไฟล์เปลี่ยน ไม่ยืนยัน provenance
6. ไม่สลับไป test_fake/Gemini grading เมื่อ real model โหลดไม่ได้ Readiness ส่ง 503 พร้อม X-Model-Error โดยไม่เปิดเผย private path

การ hash base ทั้งชุดอาจทำให้ startup ช้าตามขนาดโมเดล โหลดครั้งเดียวต่อ process ต้องวัดกับของจริง

## Python interface

v2 ใช้ `CoverageModel(base_model_path, checkpoint_dir, manifest_path)` Predictor ต้องมี model_version ตรง manifest, thresholds ตรง validation_thresholds และ methods:

```python
validate_attempt(question, current_prompt, criteria, answer)
predict_attempt(question, current_prompt, criteria, answer)
```

Legacy factory ใช้ `load_model(artifact_dir=Path(...))` และ method เดียวกัน โดย checkpoint_file เป็น relative path ภายใน artifact directory

Package v2 ตรวจ anchor ของแต่ละ criterion และ answer แยกกันด้วย tokenizer จริงไม่เกิน 512 tokens ห้ามอ้างตัวประมาณความยาว fake เป็นผล tokenizer จริง Backend ส่ง canonical question/current_prompt จาก state และตรวจ output shape/version/criterion IDs ก่อน Agent รวมผล

## ตรวจหลังได้รับไฟล์

ติดตั้ง package requirements ใน environment แยกที่เข้ากับเครื่อง → hashes/readiness → 512 boundary และ covered/partial/missing/off-topic → calibrated gates/false praise → restart → API state/replay → Frontend → tunnel/อีกเครื่อง

ปัจจุบันผ่าน adapter tests ด้วย stub และ missing-artifact readiness จริง ยังไม่ได้โหลด LoRA/Dense weights หรือวัด F1/false praise/latency ของ checkpoint ต้องรับ baseline, dataset split ตาม deck/topic, class/macro F1, off-topic F1 และ calibration limitations จากคน A
