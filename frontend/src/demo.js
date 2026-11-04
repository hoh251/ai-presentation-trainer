export const demoDeck = {
  filename: 'cats-demo.pdf',
  page_count: 6,
  url: '/cats-demo.pdf',
}

export const demoQuestions = [
  {
    id: 'demo-q1',
    text: 'แมวสื่อสารความต้องการผ่านพฤติกรรมใดบ้าง?',
    judge_role: 'concept',
    source_pages: [2],
    topic: 'การสื่อสารของแมว',
  },
  {
    id: 'demo-q2',
    text: 'ถ้าแมวหางแกว่งแรงและหูเอนไปด้านหลัง คุณจะตีความอย่างไร?',
    judge_role: 'concept',
    source_pages: [2, 3],
    topic: 'การตีความพฤติกรรม',
  },
  {
    id: 'demo-q3',
    text: 'คุณจะจัดสภาพแวดล้อมในบ้านให้แมวปลอดภัยอย่างไร?',
    judge_role: 'technical',
    source_pages: [4, 5],
    topic: 'การดูแลแมว',
  },
]

export function demoFeedback(round) {
  return {
    strengths: [],
    improvements: [],
    note: 'โหมดตัวอย่างบันทึกคำตอบเพื่อให้ลองขั้นตอนเท่านั้น ยังไม่ได้ประเมินว่าคำตอบตรงคำถามหรือไม่',
    source_pages: demoQuestions[round - 1].source_pages,
  }
}

export function demoReport(history) {
  return {
    overall: {
      summary: 'นี่คือการทดลองหน้าจอ ระบบบันทึกคำตอบทั้ง 3 รอบ แต่ไม่ได้ตรวจความถูกต้องหรือให้คะแนน',
      strengths: [],
      improvements: [],
    },
    rounds: history.map((item, index) => ({
      round: index + 1,
      question: item.question.text,
      answer: item.answer,
      feedback: item.feedback,
    })),
    coverage: [],
    references: [2, 3, 4, 5],
  }
}
