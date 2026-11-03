# ทดลอง API ใน PowerShell

เปิดเซิร์ฟเวอร์จาก `backend` ด้วย `.\.venv\Scripts\python.exe run.py --test-mode` ก่อน

ตรวจและอัปโหลดด้วย curl จากโฟลเดอร์ `backend`:

```powershell
curl.exe http://127.0.0.1:8000/api/ready
curl.exe -F "file=@examples/demo-slides.pdf;type=application/pdf" http://127.0.0.1:8000/api/decks
```

คัดลอก `deck_id` ที่ได้รับ แล้วใช้ PowerShell เพื่อหลีกเลี่ยงปัญหาการ quote JSON ของ curl บน Windows:

```powershell
$origin = 'http://127.0.0.1:8000'
$startBody = @{ deck_id = 'แทนด้วย deck_id ที่อัปโหลด'; difficulty = 'standard' } | ConvertTo-Json
$session = Invoke-RestMethod "$origin/api/sessions" -Method Post -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($startBody))
$session | ConvertTo-Json -Depth 15

$sessionId = $session.session_id
$answerBody = @{
    question_id = $session.question.id
    attempt_id = [guid]::NewGuid().ToString()
    state_version = $session.state_version
    answer = 'Quiet corner'
} | ConvertTo-Json
$result = Invoke-RestMethod "$origin/api/sessions/$sessionId/answers" -Method Post -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($answerBody))
$result | ConvertTo-Json -Depth 20

# Retry คำขอเดิม ต้องใช้ answerBody เดิมทุกตัว จะได้ response snapshot เดิม
Invoke-RestMethod "$origin/api/sessions/$sessionId/answers" -Method Post -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($answerBody))

# โหลด state ปัจจุบัน
Invoke-RestMethod "$origin/api/sessions/$sessionId" | ConvertTo-Json -Depth 20

# ใช้หลังปิดครบ 3 รอบเท่านั้น ก่อนจบจะได้ 409
Invoke-RestMethod "$origin/api/sessions/$sessionId/report" | ConvertTo-Json -Depth 25
```

คำตอบใหม่ต้องสร้าง UUID ใหม่ ใช้ `state_version` จากผลล่าสุดและ `next_question.id` จาก answer response หรือ `question.id` จาก GET session ข้อความที่ผู้ใช้ต้องตอบคือ `current_prompt`

การยิงตัวอย่างด้วย PowerShell ข้างบนเป็นคำแนะนำสำหรับคน A ไม่ใช่หลักฐานว่า Frontend/tunnel ถูกทดสอบแล้ว หลักฐานที่รันอัตโนมัติอยู่ใน `verification.md`
