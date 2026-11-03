# วิธีรวมงานของทีม

ใช้เส้นทาง **งานแต่ละส่วน → `dev` → `main`** โดย `dev` เป็นจุดประกอบและทดสอบร่วม ส่วน `main` เก็บรุ่นที่พร้อมสาธิต

## 1. แยก branch ก่อนเริ่มงาน

เริ่มจาก `dev` ล่าสุดแล้วสร้าง branch สำหรับงานหนึ่งเรื่อง เช่น `feature/frontend-practice`, `feature/model-training`, `feature/backend-session`, `fix/report-outcome` หรือ `docs/contract-update` คน A ดูแล Frontend และ training/model package; คน B ดูแล Backend/RAG/Agent ตามแผนใน repo นี้

```bash
git switch dev
git pull origin dev
git switch -c feature/<ชื่องาน>
```

Commit เฉพาะงานที่เกี่ยวข้อง ตรวจ staged files ก่อน push ห้ามใส่ `.env`, API key, DB, PDF ผู้ใช้, checkpoint ใหญ่ หรือไฟล์ cache ข้อความ commit บอกสิ่งที่เปลี่ยนอย่างตรงไปตรงมา

## 2. รวม branch งานเข้า `dev`

1. ผู้ทำงาน push branch และเปิด Pull Request โดยตั้ง **base = `dev`** ห้าม push เข้า `dev` โดยตรง
2. กรอก PR template ให้ครบ: สิ่งที่เปลี่ยน, contract ที่กระทบ, วิธีทดสอบ, ผลทดสอบ และสิ่งที่ยังไม่ผ่าน
3. ถ้าเปลี่ยน API/model interface ให้แก้ `contracts/v1/` (schema, fixtures, tests) ใน PR เดียวกัน แล้วแจ้งอีกฝ่ายตรวจผลกระทบ
4. บัญชี **hoh251 คอมเมนต์ผลตรวจบน PR** ให้ชัดว่าเห็นด้วยหรือให้แก้อะไร ผู้ทำงานตอบคอมเมนต์และ push commit แก้ใน branch เดิมหากมีประเด็น
5. เมื่อคอมเมนต์ที่ต้องแก้ได้รับคำตอบ/แก้ไขแล้วและการทดสอบผ่าน **hoh251 เป็นผู้กด merge** จาก PR เข้า `dev` ผู้เขียน PR ไม่ merge เอง
6. หลัง merge ให้ทั้งสองฝ่ายดึง `dev` ล่าสุดและทดสอบจุดต่อ Frontend ↔ Backend ↔ model package

## 3. รวม `dev` เข้า `main`

เปิด PR โดยตั้ง **base = `main`, compare = `dev`** พร้อมสรุปผล end-to-end: PDF ใหม่, probe/retry, incomplete, report, refresh, error 409/413/429/503, restart และเปิดผ่าน tunnel จากเครื่องอื่น `hoh251` คอมเมนต์ผลตรวจและเป็นผู้กด merge เมื่อพร้อมสาธิต จากนั้นสร้าง tag รุ่นสาธิตหากต้องการ

หากพบข้อผิดพลาดหลัง merge ให้เปิด `fix/<ชื่องาน>` จาก `dev` แล้วทำ PR ตามทางเดิม อย่าแก้ `main` ตรง ๆ

## 4. กฎที่ตรวจด้วยคนในตอนนี้

Repo นี้เป็น **Private** และ GitHub แจ้งว่าบัญชีปัจจุบันต้องใช้ GitHub Pro หรือเปิด repo เป็น Public จึงใช้ branch protection/rulesets ได้ ([เอกสาร GitHub](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches)) ดังนั้นขั้นตอน PR, คอมเมนต์ และการให้ `hoh251` กด merge เป็น **ข้อตกลงของทีมที่ยังไม่ถูก GitHub บังคับอัตโนมัติ** ห้ามเข้าใจผิดว่าระบบบล็อก direct push ได้แล้ว หากอัปเกรดแพ็กเกจภายหลังจึงตั้ง required PR review, conversation resolution และ status checks บน `dev`/`main` ได้
