# งานวิจัยที่เกี่ยวข้องกับการปรับโมเดล

งานของเราเป็นการประเมิน **คำตอบสั้นเทียบ rubric/criterion จากสไลด์** โดยแยก covered, partial, missing และ off-topic รายเกณฑ์ ไม่ได้ใช้ LLM เป็นผู้ตัดสินคะแนนโดยตรง งานต่อไปนี้ช่วยกำหนดสมมติฐานสำหรับการทดลอง แต่ไม่ใช่หลักฐานว่าระบบเราทำได้เท่าคะแนนในบทความ

1. [EmbeddingGemma: Powerful and Lightweight Text Representations (2025)](https://arxiv.org/abs/2509.20354) อธิบายโมเดลฐาน 300M ที่เรา fine-tune ต่อ และการฝึกด้วย positive/hard negative และ contrastive objective เราจึงทดลอง ranking loss บนคำตอบที่ถูกเกณฑ์หนึ่งแต่ผิดอีกเกณฑ์หนึ่ง แทนการเพิ่ม epoch อย่างเดียว
2. [Creating scoring rubric from representative student answers for improved short answer grading (CIKM 2018)](https://research.ibm.com/publications/creating-scoring-rubric-from-representative-student-answers-for-improved-short-answer-grading) พบว่าคำตอบตัวแทนของกลุ่มคะแนนต่าง ๆ ช่วยงาน short-answer grading ในข้อมูลที่ศึกษา แนวคิดที่ใช้กับเราคือเก็บตัวอย่างจริงของ covered/partial/missing หลายสำนวนต่อ criterion โดยให้คนตรวจ label ก่อนฝึก
3. [Are rubrics all you need? Towards rubric-based automatic short answer scoring via guided rubric-answer alignment (LAK 2026)](https://doi.org/10.1145/3785022.3785064) เสนอการจับคู่ข้อความใน rubric กับคำตอบของผู้เรียนโดยตรง สอดคล้องกับการทำนายราย criterion ของเรา และเตือนให้วัด partial credit เป็นเรื่องเฉพาะ ไม่รวมเป็นคะแนนความคล้ายอย่างเดียว
4. [Rubric-guided Prompting for Automatic Assessment Scoring (L@S 2026)](https://doi.org/10.1145/3774398.3811581) รายงานว่าคะแนนจาก LLM อาจพึ่งพารูปแบบ prompt และเหตุผลที่สร้างอาจอ้าง rubric ผิด นี่สนับสนุนการให้ local model ตัดสิน coverage พร้อมหลักฐาน และให้ LLM สร้างถ้อยคำ feedback ภายใต้ผลที่ตรวจแล้ว

5. [Evaluating Sampling Strategies for Similarity-Based Short Answer Scoring: a Case Study in Thailand (SEALP 2025)](https://aclanthology.org/2025.sealp-1.3/) ทดลองคัดคำตอบอ้างอิงด้วย K-center และ K-means บนคำตอบจริงภาษาไทย/อังกฤษ แทนการเลือกแบบสุ่ม แนวนี้เหมาะกับการคัดคำตอบหลายสำนวนมาให้คนติดป้ายก่อนฝึก ไม่ใช่การเติมตัวอย่างสังเคราะห์อย่างเดียว

6. [Efficient Few-Shot Learning Without Prompts / SetFit (2022)](https://arxiv.org/abs/2209.11055) ใช้ sentence embedding กับหัวจำแนกที่ฝึกจากข้อมูลติดป้ายจำนวนน้อย เราทดลองหัวแบบนี้แล้ว coverage เพิ่มบนชุด 50 แต่ `covered` ผิดมากขึ้น จึงยังไม่ใส่ใน package

7. [Model soups (ICML 2022)](https://proceedings.mlr.press/v162/wortsman22a.html) แสดงว่าการเฉลี่ยน้ำหนักโมเดลที่ fine-tune แยกกันอาจช่วยการทั่วไปโดยไม่เพิ่มต้นทุน inference งานนี้ทดลองเฉลี่ย LoRA factors และ Dense heads ซึ่งเป็นการดัดแปลง ไม่ควรอ้างว่ารับประกันผลแบบบทความ ผลวัดจริงอยู่ใน `OPTIMIZATION_AUDIT.md`

8. [SemAntoNeg (BlackboxNLP 2022)](https://aclanthology.org/2022.blackboxnlp-1.20/) และ [ALIGN-SIM (EMNLP 2024)](https://aclanthology.org/2024.findings-emnlp.436/) ตรวจข้อจำกัดของ embedding ต่อคำปฏิเสธ คำตรงข้ามและการแปลงข้อความที่คงหรือเปลี่ยนความหมาย เราจึงเพิ่ม minimal pairs ตรวจทั้งการเรียงคะแนนและสถานะที่ตัดสิน

9. [Conformal Risk Control (ICLR 2024)](https://research.google/pubs/conformal-risk-control/) เป็นแนวคาลิเบรตความเสี่ยงด้วยข้อมูลแยก แต่ข้อมูล validation ของเรายังมีเพียงคำตอบที่ผู้พัฒนาเขียนและมี distribution shift จึงใช้เป็นหลักออกแบบการถามเจาะเมื่อไม่มั่นใจ ไม่กล่าวอ้าง statistical guarantee

**การนำมาใช้จริง:** ทดลอง hard cases และ ranking loss พร้อม ablation เทียบ cosine MSE เดิม; วัดผลบน deck ที่ไม่อยู่ใน train; ปรับข้อมูลจริงและตรวจ label ซ้ำก่อนอ้างความแม่นยำทั่วไป การทดลองของบทความส่วนใหญ่ไม่ใช่ภาษาไทยหรือสไลด์ของเรา จึงต้องรายงานผลของเราแยกจากผลในงานวิจัย
