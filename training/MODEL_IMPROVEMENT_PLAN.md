# แผนปรับปรุง EmbeddingGemma coverage scorer

## เป้าหมายและฐานเปรียบเทียบ

รุ่นปัจจุบัน `embeddinggemma-coverage-lora-v1` ฝึกจากแถว train 107 (รวม stress 30), validation 42, test สังเคราะห์ 42 บน test ได้ macro F1 0.648, off-topic F1 0.947 และ false praise 0.029 การลองหัวข้อ PDF C07 ที่ไม่เคยฝึก 24 คำตอบที่ผู้พัฒนาร่างเอง ได้ macro F1 0.670 เท่ากับโมเดลก่อน fine-tune ข้อมูลทั้งหมดนี้ยังเล็กและไม่ใช่คำตอบนักศึกษาจริง

## ขั้นตอน

1. **ล็อกชุดประเมิน**: เก็บ `bike_care` เป็น fixed synthetic test และ C07 เป็น external probe ที่เคยเห็นผล v1 แล้ว ห้ามฝึกหรือเลือก hyperparameter จากผลสองชุดนี้ เลือกตัวทดลองจาก `waste_sorting` validation เท่านั้น รายงานทั้ง precision/recall/F1 ของ `covered`, `partial`, `missing`, off-topic F1 และ false praise
2. **ตรวจ/เพิ่มข้อมูลยาก**: เพิ่มคำตอบที่เกี่ยวกับหัวข้อแต่ไม่ครอบคลุมเกณฑ์, คำตอบผิดแต่ใช้ศัพท์เดียวกัน, คำตอบถูกสั้น/ใช้คำพ้อง, คำตอบที่ตอบเพียงเกณฑ์ข้างเคียง, คำมั่ว/แสลง/คำด่า ให้มี `status` กับ `off_topic` แยกกัน แยกตาม deck ก่อนฝึก
3. **ทดลอง objective**: เทียบ LoRA เดิม (cosine MSE) กับ MSE + ranking loss ที่บังคับให้คำตอบถูกของเกณฑ์มีคะแนนสูงกว่าคำตอบของเกณฑ์ข้างเคียง ทดสอบ 2–3 ค่า weight/learning rate บน validation เดียวกัน บันทึก seed, loss, threshold และ checkpoint ของแต่ละรุ่น
4. **ทดลอง off-topic แยก**: ฝึกตัวจำแนกเล็กจาก embedding/score ที่ได้จาก train เท่านั้น แล้วเลือก threshold จาก validation เทียบกับวิธี threshold เดิม ใช้เฉพาะเมื่อช่วย validation โดยไม่เพิ่ม false praise และยังผ่านคำตอบสั้นที่ถูก
5. **เลือก/ตรวจซ้ำ**: เลือกรุ่นตามเกณฑ์ที่กำหนดล่วงหน้า: false praise validation ไม่สูงกว่า v1, macro F1 validation สูงกว่า v1 อย่างมีความหมาย หรือ off-topic F1 สูงขึ้นโดย coverage ไม่ลด จากนั้นเปิด holdout สังเคราะห์หนึ่งครั้ง และใช้ C07 เป็น probe จริงหนึ่งครั้ง บันทึกทั้งผลที่ดีขึ้นและผลที่ไม่ดีขึ้น
6. **ส่งต่อ Backend**: เฉพาะรุ่นที่ผ่านเกณฑ์เท่านั้นจึงเปลี่ยน `model_package/manifest.json` และชุด checkpoint ส่งต่อ ตรวจ checksum, API schema, 512-token limit, covered/partial/missing/off-topic และการโหลดใหม่ใน environment แยก

## ข้อจำกัดและเกณฑ์หยุด

- เพิ่ม epoch หรือ LoRA rank อย่างเดียวไม่ถือว่าดีขึ้น ต้องแสดงผลบน holdout และไม่เพิ่มการชมผิด
- C07 มีเพียง 24 คำตอบที่ผู้พัฒนาร่างและเคยเห็นผล v1 แล้ว ไม่ใช่ benchmark อิสระ ห้ามเลือกโมเดลจากผล C07
- หากรุ่นทดลองไม่ผ่านเกณฑ์ ให้คง v1 ไว้และบันทึกผลล้มเหลว ไม่เปลี่ยน production manifest เพื่อให้คะแนนบน validation ดูสวย
- ถ้าต้องการกล่าวว่าทั่วไปได้จริง ขั้นถัดไปต้องมีคำตอบจากสไลด์จริงหลายหัวข้อที่คนตรวจ label อย่างน้อยสองคนในกรณีกำกวม

## แบ่งงานสองคน

- **คน A (Frontend + โมเดล)**: ทำข้อมูล/label guideline, train/evaluation, checkpoint/manifest, model package, smoke test และหน้า UI แสดงสถานะ low confidence
- **คน B (Backend + Agent)**: โหลด package ใน API, บังคับ 512-token validation/503 readiness, รวม coverage ข้าม attempts, ให้ Agent เลือก probe เมื่อ confidence ต่ำ และทดสอบ PDF/DB/การเรียก Gemini แบบครบ flow
- จุดต่อร่วมคือ `contracts/v1/model.schema.json` และ `predict_attempt(question, current_prompt, criteria, answer)`; เปลี่ยนสัญญากลางต้องปรับ fixture/test ทั้งสองฝ่ายก่อน

## ผลรอบนี้

- เพิ่ม hard cases 30 train/12 validation; test `bike_care` ไม่มี hard cases ใหม่ เลือก v2 จาก validation ก่อนรันทดสอบ
- ทดลอง MSE + hard cases, ranking weight 0.2 และ 0.5: ranking ได้ macro F1 validation สูงกว่าเล็กน้อย แต่ false praise เป็น 0.048 เทียบกับ MSE 0.024 จึงเลือก MSE
- ตัวจำแนก off-topic แยกได้ validation F1 0.895 ต่ำกว่า threshold เดิม 0.919 จึงไม่ใส่ใน package
- v2 บน fixed synthetic test 42 แถว: macro F1 0.687 เทียบ v1 0.648, false praise เท่ากัน 0.029; off-topic F1 ลดจาก 0.947 เป็น 0.923
- external C07 probe 24 คำตอบที่ผู้พัฒนาร่าง: macro F1 0.706 เทียบ v1 0.670, off-topic F1 และ false praise เท่ากัน 0.778/0.062
- รายละเอียดและข้อจำกัดอยู่ใน `improvement_experiments.json`; การปรับต่อจากนี้ควรเริ่มจากคำตอบจริงที่คนตรวจ label และ deck ใหม่ ไม่วนปรับ hyperparameter บนชุด test เดิม
