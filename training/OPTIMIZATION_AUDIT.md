# ตรวจและปรับโมเดลหลังชุดทดสอบ 50 กรณี

วันที่ 4 พฤศจิกายน 2569 — ฝั่ง Frontend + โมเดล

## สถานะที่ใช้จริง

**ยังคง `embeddinggemma-coverage-lora-v2` เป็น package ที่ส่งต่อ Backend** ไม่มีการเปลี่ยน `model_package/manifest.json`, `model_package/coverage.py` หรือ checkpoint ที่ใช้งาน ผลทดลองด้านล่างยังไม่ผ่านทุกด้านพร้อมกัน โดยเฉพาะคำตอบนอกเรื่องและคำตอบที่ถูกแต่ถูกให้คะแนนต่ำ จึงไม่ควรประกาศว่ารุ่นใหม่แม่นกว่าโดยรวม

ชุด 50 กรณีที่พบปัญหาเป็นคำตอบที่ผู้พัฒนาเขียนและติดป้ายเอง 5 หัวข้อ หัวข้อละ 10 คำตอบ ถูกเปิดผลก่อนเริ่มงานรอบนี้ จึงใช้ **วิเคราะห์ข้อผิดพลาดเท่านั้น** ไม่ใช้เลือก hyperparameter, threshold หรือรุ่นที่จะเผยแพร่ การทดลองบางอย่างดูผล 50 ซ้ำเพื่อเฝ้าระวัง regression; คะแนนนี้ไม่ใช่ holdout อิสระอีกต่อไป

## สิ่งที่ทดลองและผล

| วิธี | Validation | ชุดทดสอบสังเคราะห์ 86 เกณฑ์ | ชุด 50 กรณีเดิม | ข้อสรุป |
|---|---|---|---|---|
| v2 ปัจจุบัน คาลิเบรตบน validation ใหม่ | macro F1 **0.690**, off-topic F1 **0.906**, ให้ `covered` ผิด **0.015** | macro F1 **0.659**, off-topic F1 **0.945**, ผิด **0.017** | macro F1 **0.420**, off-topic F1 ระดับคำตอบ **0.947**, ให้ `covered` ผิด **0** | ฐานเทียบ |
| ฝึก LoRA ใหม่จากหัวข้อหลากหลายพร้อมข้อความนอกเรื่องไม่ซ้ำ (v4 ทดลอง) | **0.732 / 0.824 / 0** | **0.705 / 0.868 / 0.033** | **0.485 / 0.706 / 0.019** | coverage ดีขึ้น แต่ off-topic และการให้ครบผิดแย่ลง จึงไม่ใช้ |
| เฉลี่ย LoRA factors และ Dense heads: v2 75% + v3 25% (soup25 ทดลอง) | **0.709 / 0.906 / 0.015** | **0.694 / 0.945 / 0.017** | **0.428 / 0.900 / 0** | ผลชุดสังเคราะห์ดีขึ้นเล็กน้อย แต่ชุด 50 ตรวจนอกเรื่องแย่ลง จึงยังไม่แทน v2 |

หมายเหตุ: checkpoint v3 ที่ใช้ทำ soup25 ถูกฝึกก่อนแก้ปัญหาข้อความนอกเรื่องซ้ำระหว่าง split แม้ชุด validation/test ในตารางจะแก้การซ้ำแล้ว จึงยิ่งไม่ควรนำ soup25 ไปใช้จริงจากผลนี้เพียงอย่างเดียว

ตัวเลขสามค่าของแต่ละช่องตามลำดับคือ `coverage macro F1 / off-topic F1 / false-covered rate` โดยช่องชุด 50 วัด off-topic **ระดับคำตอบ** และอีกสองช่องวัดตามแถวเกณฑ์; ไม่ควรเทียบค่าระหว่างชุดโดยไม่ดูหน่วยข้อมูล **ทุกแถวในตารางเป็นการทดลองคาลิเบรต threshold ใหม่บน validation 98 แถว** ยังไม่เปลี่ยน manifest ของ v2 ที่ระบบใช้จริง ผล v2 เดิมบนชุด 50 ก่อนคาลิเบรตคือ macro F1 0.408 ตาม `ROBUSTNESS_50_REPORT.md` ผลละเอียดอยู่ใน [`optimization/v2_v4_comparison.json`](optimization/v2_v4_comparison.json) และ [`optimization/soup_revised.json`](optimization/soup_revised.json) ชุดทดสอบ 86 เกณฑ์ประกอบด้วย 42 เกณฑ์เดิมของหัวข้อจักรยานและ 44 เกณฑ์ใหม่จากสองหัวข้อที่ไม่อยู่ใน train/validation ทั้งหมดเป็นข้อความที่ผู้พัฒนาสร้าง ไม่ใช่คำตอบนักศึกษาจริง

### การทดลองที่ไม่เลือก

- **ย่อ anchor เหลือเกณฑ์+หลักฐาน:** บน validation เดิมที่มีเพียงหัวข้อแยกขยะ macro F1 0.784 และไม่ให้ครบผิด แต่ชุด 50 macro F1 เพียง 0.366 จึงไม่เปลี่ยนรูปแบบข้อความเพราะคะแนน validation หัวข้อเดียวดูดีแต่ไม่ข้ามหัวข้อ ([ผล](optimization/anchor_ablation_v2.json))
- **หัวจำแนกแบบ SetFit บน embedding v2:** เมื่อคาลิเบรตความน่าจะเป็นจาก validation เดิมหัวข้อเดียวได้ macro F1 0.803; ชุด 50 ได้ 0.651 แต่ให้ครบผิด 5/53 เกณฑ์ เทียบ v2 เดิมที่ 0/53 จึงยังไม่ปลอดภัยพอ ([ผล](optimization/setfit_head_v2.json))
- **หัวจำแนก off-topic บน v4:** ได้ F1 0.868 บน validation, 0.939 บน test, และ 0.750 บนชุด 50 ซึ่งต่ำกว่า v2 ทั้งสามชุด จึงไม่เพิ่มหัวนี้เข้า package ([ผล](optimization/off_topic_head_v4.json))
- **minimal pairs คำตอบถูกเทียบกับคำตอบปฏิเสธ 12 คู่:** ทั้ง v2 และ soup50 เรียงคะแนนคำตอบถูกเหนือคำตอบปฏิเสธได้ 12/12 แต่ v2 ให้สถานะทั้งคู่ตรงเฉลยเพียง 1/12 และ soup50 ได้ 4/12 ปัญหาจึงไม่ได้มีแค่การเรียงความหมาย แต่รวม threshold ที่ย้ายข้ามหัวข้อไม่ดี ([ผล](optimization/negation_pairs_probe.json))

## สิ่งที่ตรวจพบเองระหว่างงาน

1. ข้อมูลเพิ่มชุดแรกใช้ข้อความนอกเรื่องประโยคเดียวกันข้าม train, validation และ test ทำให้ผล off-topic มีโอกาสดูดีเกินจริง แก้ใน `generate_diverse_cases.py` ให้แต่ละหัวข้อมีข้อความนอกเรื่องและคำสั่งหลอกคนละแบบ แล้วฝึก v4/ประเมินซ้ำ ผลหลังแก้เป็นตัวเลขที่ใช้ในตารางข้างบน
2. การปรับ threshold จาก validation สามหัวข้อยังไม่รับประกันการใช้กับ PDF หัวข้อใหม่ ชุด 50 แสดง distribution shift ชัดเจน โดย v2 พลาดคำตอบที่ควร `covered` จำนวนมาก
3. ข้อมูลใหม่ยังสร้างตาม template และมีผู้ติดป้ายเพียงคนเดียว รวมถึงชุด test ที่สร้างจาก template คล้าย train คะแนน test จึงมีโอกาสสูงเกินความจริง
4. การผสม LoRA factors ไม่เหมือนการเฉลี่ยน้ำหนักเต็มตามงาน model soups โดยตรง ถึงแม้ checkpoint จะเริ่มจาก seed และโครงเดียวกัน ต้องถือเป็น **สมมติฐานทดลอง** และวัดผลของเราเอง
5. หัวจำแนกเพิ่ม recall ได้ แต่ false-covered บนหัวข้อใหม่สูง งานนี้จึงต้องแยกความผิดพลาดสองชนิด: `ชมผิด` และ `กดคะแนนคำตอบถูก` ไม่รวมดู macro F1 ค่าเดียว

## งานที่ควรทำต่อก่อนอ้างว่าแม่นกับผู้ใช้จริง

1. **เก็บคำตอบจริงหลายหัวข้อ:** ให้คน 2 คนตอบคำถามจาก PDF ใหม่อย่างน้อย 5–10 หัวข้อ โดยมีคำตอบสั้น ถูกบางส่วน ผิดแบบใช้คำศัพท์ตรง คำปฏิเสธ คำแสลง และนอกเรื่อง แยกข้อมูล train/validation/test ตาม PDF ก่อนฝึก ไม่คัดลอกคำตอบจากชุด 50
2. **ตรวจเฉลยสองคน:** ให้ผู้ตรวจอย่างน้อยสองคนติดป้าย `covered/partial/missing/off_topic` แยกกัน แล้วแก้กรณีเห็นไม่ตรงด้วย rubric ที่เขียนไว้ วัดข้อตกลงระหว่างผู้ตรวจ ก่อนใช้ข้อมูลฝึกหรืออ้างผล ความแตกต่างระหว่าง `partial` กับ `covered` ในชุดปัจจุบันมีผลมาก
3. **เลือกตัวอย่างที่หลากหลายสำหรับตรวจ:** เมื่อมีคำตอบจริงมากพอ คัดตัวอย่างด้วย embedding clustering หรือ K-center ให้คนติดป้าย แทนการสุ่มแต่คำตอบคล้ายกัน ตามงาน short-answer scoring ภาษาไทยของ Boonsarngsuk และคณะ (2025) ต้องทดสอบวิธีนี้กับข้อมูลของเราเอง
4. **แยกโมเดลความหมายกับนโยบายถามเจาะ:** ทดลอง classifier หรือ NLI ที่รับ rubric กับคำตอบโดยตรงบนข้อมูลจริง แล้ววัด false-covered ภายใต้เพดานที่ตกลงกัน เมื่อไม่มั่นใจให้ Backend ถามเจาะ ไม่ให้ `covered` อัตโนมัติ การคาลิเบรตจากข้อมูลสังเคราะห์อย่างเดียวไม่มีหลักประกันบนหัวข้อใหม่
5. **สร้าง holdout ใหม่หลังล็อกวิธี:** ชุด 50 และ test สังเคราะห์รอบนี้ถูกดูผลหลายครั้งแล้ว ไม่ใช่หลักฐานอิสระสำหรับอ้างว่ารุ่นถัดไปดีขึ้น ต้องมี PDF และคำตอบจริงชุดใหม่ที่ไม่ใช้เลือกโมเดล

## งานวิจัยที่ใช้กำหนดสมมติฐาน

- [Boonsarngsuk et al., *Evaluating Sampling Strategies for Similarity-Based Short Answer Scoring: a Case Study in Thailand*, SEALP 2025](https://aclanthology.org/2025.sealp-1.3/) — คัดตัวอย่างคำตอบอ้างอิงอย่างมีระบบสำหรับงานคะแนนคำตอบสั้นภาษาไทย/อังกฤษ; ไม่ได้ยืนยันคะแนนของโมเดลเรา
- [Tunstall et al., *Efficient Few-Shot Learning Without Prompts*, 2022](https://arxiv.org/abs/2209.11055) — แนว embedding แล้วฝึกหัวจำแนกด้วยข้อมูลน้อย; หัวที่เราทดลองยังไม่ผ่านด้าน false-covered
- [Wortsman et al., *Model soups*, ICML 2022](https://proceedings.mlr.press/v162/wortsman22a.html) — การเฉลี่ยน้ำหนักโมเดลที่ fine-tune หลายรุ่นมีโอกาสเพิ่มความทนทานโดยไม่เพิ่มต้นทุน inference; การเฉลี่ย LoRA factors ในงานนี้เป็นการดัดแปลงที่ต้องวัดเอง
- [Vahtola et al., *SemAntoNeg*, BlackboxNLP 2022](https://aclanthology.org/2022.blackboxnlp-1.20/) และ [Mahajan et al., *ALIGN-SIM*, EMNLP 2024](https://aclanthology.org/2024.findings-emnlp.436/) — งานวิเคราะห์ข้อจำกัดของ sentence embedding ต่อความหมายที่ใกล้กัน คำปฏิเสธและคำตรงข้าม สนับสนุนการทดสอบ minimal pairs ไม่ใช่หลักฐานว่าโมเดลเราแก้ปัญหาแล้ว
- [Bates et al., *Conformal Risk Control*, ICLR 2024](https://research.google/pubs/conformal-risk-control/) — แนวคุมความเสี่ยงด้วยข้อมูล calibration; ยังไม่ควรอ้าง guarantee กับระบบนี้ เพราะข้อมูลน้อยและการกระจายคำตอบจริงอาจต่างจากข้อมูลสังเคราะห์

## การทำซ้ำ

สคริปต์ที่เพิ่ม: `generate_diverse_cases.py`, `ablate_anchor_v2.py`, `experiment_setfit_head.py`, `compare_diverse_checkpoints.py`, `experiment_model_soup.py`, `probe_negation_pairs.py`, `experiment_off_topic_head_v4.py` ทั้งหมดใช้ checkpoint และโมเดลฐานใน `work/` ที่ไม่เผยแพร่ ตัวเลขที่แชร์ใน `optimization/` ไม่มี key, checkpoint หรือ PDF ผู้ใช้

ตัวอย่างคำสั่งจากราก repo หลังตั้ง `<base-model>` และ `<work>` เป็น path บนเครื่องที่มีสิทธิ์ใช้ EmbeddingGemma:

```powershell
python training/generate_diverse_cases.py
python -m unittest training.test_data -v
python training/train_embeddinggemma.py --model-path <base-model> --output-dir <work>/diverse-unique-off-v4 --epochs 3 --batch-size 4 --max-length 512 --include-hard --include-diverse --validation-only
python training/compare_diverse_checkpoints.py --base-model <base-model> --v2-checkpoint <work>/improve-mse-hard/checkpoint --v3-checkpoint <work>/diverse-unique-off-v4/checkpoint --output <work>/v2_v4_comparison.json
```

การทดสอบที่รันบนเครื่องนี้: `training.test_data` ผ่าน 4 tests, ไฟล์สคริปต์ใหม่ compile ผ่าน และ smoke ของ package v2 ผ่าน manifest/schema, คำตอบสามแบบ และการปฏิเสธ input เกิน 512 tokens
