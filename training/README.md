# ข้อมูลและการฝึกโมเดล coverage

สถานะ: ฝึก LoRA และสร้าง model package v2 จริงแล้ว (`model_package/`) แต่ยังทดสอบกับคำตอบนักศึกษาจริงหลายหัวข้อและต่อ Backend จริงไม่ครบ จึงยังไม่ควรประกาศว่า production ready หรือสรุปความแม่นยำทั่วไปจากตัวเลขนี้ ดูแผนและผลการปรับรุ่นใน `MODEL_IMPROVEMENT_PLAN.md`, `improvement_experiments.json` และงานวิจัยที่เกี่ยวข้องใน `RELATED_RESEARCH.md` หลังทดสอบคำตอบใหม่ 50 แบบและลองวิธีปรับรุ่นหลายทางแล้ว **ยังคง v2 เป็นรุ่นส่งต่อ** เพราะรุ่นทดลองที่ coverage ดีขึ้นยังมีข้อเสียด้าน off-topic หรือการให้ `covered` ผิด อ่านผลและเหตุผลใน `OPTIMIZATION_AUDIT.md`

## เป้าหมาย

โมเดลรับ `(question, current_prompt, criterion, answer)` แล้วจำแนกแต่ละ criterion เป็น `covered`, `partial`, `missing` และตรวจ `off_topic` แยกต่างหาก Backend เป็นผู้รวมผลหลาย attempts และตัดสินใจถามเจาะ/เปลี่ยนคำถาม โมเดลไม่สร้างคำชมเอง

## กติกาติดป้าย

- `covered`: คำตอบกล่าวถึง criterion ชัดเจนหรือใช้คำพ้องที่มีความหมายเท่ากัน
- `partial`: มีส่วนที่เกี่ยวข้อง แต่ยังขาดสาระสำคัญหรือกำกวม
- `missing`: ไม่มีหลักฐานว่ากล่าวถึง criterion นั้น
- `off_topic=true`: คำตอบไม่ตอบ prompt ปัจจุบันเลย เช่น คำมั่ว คำด่า หรือคำสั่งหลอกโมเดล; ไม่ถือว่าคำตอบสั้นทุกคำเป็น off-topic
- กรณี `off_topic=true` พร้อม `covered` ต้องส่งให้คนตรวจซ้ำ เพราะสัญญากลางกำหนดเป็นผลขัดกัน
- คำสั่งใน answer เช่น “ให้คะแนนเต็ม” เป็นข้อมูลผู้ใช้ ไม่ใช่คำสั่งให้ตัวติดป้ายหรือระบบประเมิน

`seed.jsonl` เป็นตัวอย่างตั้งต้นจากสไลด์แมวหนึ่งชุด `generate_decks.py` สร้าง PDF ภาษาไทย 4 เรื่อง เรื่องละ 4 หน้า และตัวอย่างติดป้าย 128 แถวใน `synthetic_examples.jsonl` ใช้สำหรับทดสอบ pipeline และเพิ่มความหลากหลายเริ่มต้น ตัวอย่างสังเคราะห์อาจง่ายกว่าคำตอบจริงและต้องให้คนตรวจ label ก่อนใช้ฝึกหรืออ้างความแม่นยำ

```powershell
python training/generate_decks.py
python training/split_data.py
```

`split_data.py` แยกตาม deck: train = แมว/อีเมลหลอกลวง/สวนในเมือง, validation = การแยกขยะ, test_synthetic = การดูแลจักรยาน ผล test สังเคราะห์เป็นเพียงการตรวจระบบวัดผล ห้ามใช้แทนผลบน PDF จริงที่ไม่เคยเห็น

`generate_edge_cases.py` เพิ่มคำตอบทดสอบ 50 แบบ เช่น คำแสลง คำมั่ว คำด่า คำสั่งหลอกโมเดล โดยแยก 30/10/10 ตาม deck ของ train/validation/test ไม่มีคำตอบ stress เดียวกันข้าม split ตัวอย่างนี้ยังเป็นข้อมูลสร้างขึ้นและติดป้ายโดยผู้พัฒนา ไม่ใช่คำตอบจากผู้ใช้จริง

`baseline.py` เป็นกติกาจับข้อความซ้ำด้วย character bigram ใช้เป็นจุดเปรียบเทียบ M1 ไม่ใช่ EmbeddingGemma และไม่ได้เทรน เลือก threshold จาก validation เท่านั้นแล้วเขียนผลที่ `baseline_results.json` หลังเพิ่ม stress answers ชุด test 42 แถว baseline ได้ macro F1 0.590, off-topic F1 0.860 และ false praise rate 0.180

สคริปต์สร้าง PDF ใช้ฟอนต์ Tahoma บน Windows หากรันบนระบบอื่น ให้ตั้ง `TRAINING_THAI_FONT` และ `TRAINING_THAI_BOLD_FONT` เป็นไฟล์ TTF ภาษาไทยที่มีบนเครื่อง PDF ที่สร้างแล้วอยู่ใน `synthetic_decks/` และมีข้อความจริงที่ดึงได้ ไม่ใช่ภาพล้วน

## การแบ่งข้อมูลและประเมินผล

แบ่ง train/validation/test ตาม `deck_id` ก่อนสร้างคู่คำตอบ เพื่อไม่ให้คำถามและถ้อยคำจากสไลด์เดียวกันรั่วข้ามชุด ใช้ validation เลือก checkpoint และ threshold แล้วเปิด test เพียงครั้งเดียว รายงาน precision/recall/F1 ราย class, macro F1, off-topic F1, confusion matrix และ false praise rate โดยเทียบ baseline กับโมเดลที่เทรนต่อบน test เดียวกัน

การฝึกจริง: ดาวน์โหลด `google/embeddinggemma-300m` ไปไว้ใน `work/models/` ภายนอก Git, ใช้ PyTorch 2.11.0+cu128 บน RTX 3050 Laptop 4 GB, `bfloat16`, LoRA rank 4 บน `q_proj`/`v_proj`, batch 4, 3 epochs และความยาวสูงสุด 512 tokens รุ่น v2 เพิ่ม hard cases เป็น train 137 แถว, validation 54, test อีกหัวข้อ 42 เลือก threshold เฉพาะจาก validation เท่านั้น แล้วบันทึก checkpoint ใน `work/experiments/improve-mse-hard/checkpoint/` ภายนอก repo สาธารณะ

บน test สังเคราะห์ 42 แถว v2 ได้ macro F1 0.687, off-topic F1 0.923, false praise 0.029 เทียบ v1 ที่ 0.648, 0.947, 0.029 ตามลำดับ นั่นคือ coverage ดีขึ้นแต่ off-topic ลดลงเล็กน้อย รายละเอียด v2 อยู่ใน `experiment_results.json` และตารางเทียบรุ่นใน `improvement_experiments.json` ตัวอย่างมีน้อยและสร้างจาก pattern เดียวกันมาก จึงยังสรุปความแม่นยำกับ PDF ของคนอื่นไม่ได้

PDF C07 ที่ผู้ใช้ส่งมาถูกเก็บภายนอก repo สำหรับประเมินเอกสารจริงและไม่ได้เผยแพร่ใน repo สาธารณะ ต้องเพิ่มตัวอย่างที่คนตรวจ label จากสไลด์จริงหลายหัวข้อก่อนอ้างความแม่นยำ งานด้าน Backend ยังต้องทดสอบ package ใน environment ใหม่พร้อม API/DB/Agent จริง

การลองกับหัวข้อ C07 จาก PDF จริง 24 คำตอบที่ผู้พัฒนาร่างและติดป้ายเอง โดยใช้ threshold จาก validation: v2 macro F1 0.706 เทียบ v1 0.670, off-topic F1 และ false praise เท่ากันที่ 0.778 และ 0.062 (`unseen_topic_probe_results.json`) ชุดนี้เคยดูผล v1 มาก่อนและมีขนาดเล็ก จึงเป็น probe ไม่ใช่ benchmark อิสระ ตัวอย่างและ PDF ต้นฉบับไม่อยู่ใน repo

## วิธีฝึกและตรวจซ้ำ

ติดตั้ง `training/requirements.txt` ใน Python environment แยก; บนเครื่อง NVIDIA ให้ติดตั้ง PyTorch CUDA wheel ที่ตรงกับ driver ก่อนใช้ requirements นี้

```powershell
python training/generate_edge_cases.py
python training/generate_hard_cases.py
python training/baseline.py
python training/train_embeddinggemma.py --model-path <local-base-model-dir> --output-dir <private-experiment-dir> --epochs 3 --batch-size 4 --max-length 512 --include-hard --validation-only
python training/evaluate_selected.py --base-model <local-base-model-dir> --experiment-dir <private-experiment-dir>
python training/export_model_manifest.py --experiment-dir <private-experiment-dir> --manifest model_package/manifest.json --public-results training/experiment_results.json
python training/smoke_model_package.py --base-model <local-base-model-dir> --checkpoint <private-experiment-dir>/checkpoint
```

ใช้ checkpoint, tokenizer และตัว Dense heads ใน directory เดียวกันตาม `model_package/README.md` ห้าม commit โมเดลฐาน, checkpoint, HF token หรือ PDF C07 ลง repo สาธารณะ

## สิทธิ์ดาวน์โหลด EmbeddingGemma

`google/embeddinggemma-300m` ต้องให้เจ้าของบัญชี Hugging Face ยอมรับเงื่อนไขบนหน้าโมเดลก่อนดาวน์โหลดไฟล์ สร้าง `training/.env` ที่มีบรรทัด `HF_TOKEN=...` หรือกำหนดตัวแปร environment `HF_TOKEN` แล้วรัน `python training/model_access.py` สคริปต์จะแสดงเฉพาะผล HTTP และไม่พิมพ์ token ไฟล์ `.env` ถูก Git ignore อยู่แล้ว ห้าม commit token หรือ checkpoint ลง repo สาธารณะ
