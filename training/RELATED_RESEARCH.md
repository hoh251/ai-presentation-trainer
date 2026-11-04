# งานวิจัยที่เกี่ยวข้องกับการปรับโมเดล

งานของเราเป็นการประเมิน **คำตอบสั้นเทียบ rubric/criterion จากสไลด์** โดยแยก covered, partial, missing และ off-topic รายเกณฑ์ ไม่ได้ใช้ LLM เป็นผู้ตัดสินคะแนนโดยตรง งานต่อไปนี้ช่วยกำหนดสมมติฐานสำหรับการทดลอง แต่ไม่ใช่หลักฐานว่าระบบเราทำได้เท่าคะแนนในบทความ

1. [EmbeddingGemma: Powerful and Lightweight Text Representations (2025)](https://arxiv.org/abs/2509.20354) อธิบายโมเดลฐาน 300M ที่เรา fine-tune ต่อ และการฝึกด้วย positive/hard negative และ contrastive objective เราจึงทดลอง ranking loss บนคำตอบที่ถูกเกณฑ์หนึ่งแต่ผิดอีกเกณฑ์หนึ่ง แทนการเพิ่ม epoch อย่างเดียว
2. [Creating scoring rubric from representative student answers for improved short answer grading (CIKM 2018)](https://research.ibm.com/publications/creating-scoring-rubric-from-representative-student-answers-for-improved-short-answer-grading) พบว่าคำตอบตัวแทนของกลุ่มคะแนนต่าง ๆ ช่วยงาน short-answer grading ในข้อมูลที่ศึกษา แนวคิดที่ใช้กับเราคือเก็บตัวอย่างจริงของ covered/partial/missing หลายสำนวนต่อ criterion โดยให้คนตรวจ label ก่อนฝึก
3. [Are rubrics all you need? Towards rubric-based automatic short answer scoring via guided rubric-answer alignment (LAK 2026)](https://doi.org/10.1145/3785022.3785064) เสนอการจับคู่ข้อความใน rubric กับคำตอบของผู้เรียนโดยตรง สอดคล้องกับการทำนายราย criterion ของเรา และเตือนให้วัด partial credit เป็นเรื่องเฉพาะ ไม่รวมเป็นคะแนนความคล้ายอย่างเดียว
4. [Rubric-guided Prompting for Automatic Assessment Scoring (L@S 2026)](https://doi.org/10.1145/3774398.3811581) รายงานว่าคะแนนจาก LLM อาจพึ่งพารูปแบบ prompt และเหตุผลที่สร้างอาจอ้าง rubric ผิด นี่สนับสนุนการให้ local model ตัดสิน coverage พร้อมหลักฐาน และให้ LLM สร้างถ้อยคำ feedback ภายใต้ผลที่ตรวจแล้ว

**การนำมาใช้จริง:** ทดลอง hard cases และ ranking loss พร้อม ablation เทียบ cosine MSE เดิม; วัดผลบน deck ที่ไม่อยู่ใน train; ปรับข้อมูลจริงและตรวจ label ซ้ำก่อนอ้างความแม่นยำทั่วไป การทดลองของบทความส่วนใหญ่ไม่ใช่ภาษาไทยหรือสไลด์ของเรา จึงต้องรายงานผลของเราแยกจากผลในงานวิจัย
