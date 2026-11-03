"""Create small, original Thai slide decks and labeled examples for pipeline tests.

The generated labels are synthetic training aids, not an accuracy benchmark.
"""
import json
import os
from pathlib import Path
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "synthetic_decks"
FONT = Path(os.getenv("TRAINING_THAI_FONT", "C:/Windows/Fonts/tahoma.ttf"))
BOLD = Path(os.getenv("TRAINING_THAI_BOLD_FONT", "C:/Windows/Fonts/tahomabd.ttf"))

# Each pair is (criterion label, exact slide evidence, covered paraphrase, partial answer).
DECKS = {
    "phishing": [
        ("รู้ทันอีเมลหลอกลวง", "อีเมลที่เร่งให้กดลิงก์ทันทีเป็นสัญญาณเสี่ยง", "ตรวจคำขอที่เร่งให้คลิกลิงก์ก่อน", "ดูอีเมล"),
        ("ตรวจโดเมน", "ตรวจชื่อโดเมนผู้ส่งก่อนเปิดลิงก์", "เช็กชื่อเว็บไซต์และผู้ส่งให้ตรงหน่วยงาน", "เช็กชื่อ"),
        ("ป้องกันบัญชี", "เปิดยืนยันตัวตนสองขั้นตอนสำหรับบัญชีสำคัญ", "ใช้การยืนยันสองชั้นกับบัญชีหลัก", "ตั้งรหัสผ่าน"),
        ("จัดการรหัสผ่าน", "ใช้รหัสผ่านต่างกันในแต่ละบริการ", "ไม่ใช้รหัสเดียวกันทุกเว็บ", "ใช้รหัสผ่าน"),
        ("รับมือเมื่อเผลอกด", "เปลี่ยนรหัสผ่านและแจ้งผู้ดูแลเมื่อสงสัยว่าถูกหลอก", "รีบเปลี่ยนรหัสและแจ้งผู้รับผิดชอบ", "ขอความช่วยเหลือ"),
        ("ตรวจอุปกรณ์", "ตรวจประวัติการเข้าสู่ระบบหลังเหตุการณ์ผิดปกติ", "ดูว่ามีการล็อกอินแปลกจากอุปกรณ์อื่นไหม", "ดูบัญชี"),
        ("ฝึกทีม", "จำลองอีเมลหลอกลวงเพื่อฝึกการสังเกต", "ให้ทีมลองแยกอีเมลปลอมจากตัวอย่าง", "สอนเรื่องอีเมล"),
        ("วัดผล", "บันทึกอัตราการกดลิงก์และการรายงานเหตุการณ์", "ติดตามว่าคนกดลิงก์และแจ้งเหตุเท่าไร", "เก็บสถิติ"),
    ],
    "urban_garden": [
        ("เลือกพื้นที่", "ผักใบส่วนใหญ่ต้องได้รับแสงอย่างน้อยครึ่งวัน", "เลือกมุมที่มีแดดหลายชั่วโมงต่อวัน", "วางไว้ริมหน้าต่าง"),
        ("เตรียมภาชนะ", "กระถางต้องมีรูระบายน้ำเพื่อลดรากเน่า", "ใช้กระถางที่น้ำไหลออกทางก้นได้", "ใช้กระถาง"),
        ("เลือกดิน", "ดินปลูกควรโปร่งและอุ้มน้ำพอเหมาะ", "เลือกวัสดุปลูกที่ระบายน้ำดีแต่ยังชื้น", "ใช้ดิน"),
        ("เริ่มปลูก", "หว่านเมล็ดตามความลึกที่ระบุบนซอง", "ดูคำแนะนำบนซองเมล็ดก่อนกลบ", "ใส่เมล็ด"),
        ("รดน้ำ", "ตรวจความชื้นของดินก่อนรดน้ำแต่ละครั้ง", "จับดินดูก่อนว่าควรเติมน้ำไหม", "รดน้ำทุกวัน"),
        ("ลดโรค", "หลีกเลี่ยงน้ำขังในจานรองกระถาง", "เทน้ำที่ค้างในจานรองทิ้ง", "ดูความชื้น"),
        ("เก็บเกี่ยว", "เก็บผักใบทีละส่วนเพื่อให้ต้นงอกต่อ", "ตัดใบพอใช้และเหลือต้นไว้", "เก็บผัก"),
        ("บันทึกผล", "จดวันปลูกและปริมาณผลผลิตเพื่อปรับรอบถัดไป", "บันทึกวันเริ่มกับผลที่เก็บได้", "จดไว้"),
    ],
    "waste_sorting": [
        ("แยกเศษอาหาร", "แยกเศษอาหารออกจากบรรจุภัณฑ์ก่อนทิ้ง", "เอาอาหารที่เหลือออกจากกล่องก่อน", "แยกขยะ"),
        ("ลดกลิ่น", "เก็บเศษอาหารในภาชนะปิดฝา", "ใส่เศษอาหารในถังที่มีฝาปิด", "ใช้ถัง"),
        ("เตรียมรีไซเคิล", "ล้างภาชนะรีไซเคิลที่เปื้อนอาหาร", "ล้างคราบในขวดหรือกล่องก่อนส่งรีไซเคิล", "ล้างขยะ"),
        ("ประหยัดพื้นที่", "พับกล่องกระดาษก่อนเก็บรวบรวม", "ทำกล่องให้แบนก่อนใส่จุดรับ", "เก็บกล่อง"),
        ("จัดการของมีคม", "ห่อของมีคมก่อนส่งทิ้งเพื่อลดการบาดเจ็บ", "พันเศษแก้วให้ปลอดภัยก่อนทิ้ง", "ทิ้งแก้ว"),
        ("แยกแบตเตอรี่", "ส่งแบตเตอรี่ใช้แล้วไปจุดรับขยะอันตราย", "นำถ่านเก่าไปที่จุดรับเฉพาะ", "ทิ้งถ่าน"),
        ("ลดขยะ", "พกขวดน้ำใช้ซ้ำเพื่อลดขวดพลาสติก", "ใช้ขวดเติมน้ำแทนซื้อขวดใหม่", "ใช้ขวด"),
        ("ติดตามผล", "ชั่งน้ำหนักขยะแต่ละประเภททุกสัปดาห์", "วัดปริมาณขยะรายสัปดาห์แยกชนิด", "ดูปริมาณขยะ"),
    ],
    "bike_care": [
        ("ตรวจลมยาง", "ตรวจแรงดันลมยางตามช่วงที่ระบุข้างยาง", "เติมลมให้อยู่ในค่าบนแก้มยาง", "ดูยาง"),
        ("ดูสภาพยาง", "เปลี่ยนยางเมื่อดอกยางสึกหรือมีรอยแตก", "ถ้ายางแตกลายงาหรือสึกให้เปลี่ยน", "เปลี่ยนยาง"),
        ("ตรวจเบรก", "บีบเบรกก่อนออกเดินทางเพื่อตรวจระยะจับ", "ลองกำเบรกดูว่าหยุดได้ไวพอ", "ดูเบรก"),
        ("เปลี่ยนผ้าเบรก", "เปลี่ยนผ้าเบรกเมื่อเนื้อผ้าเหลือน้อย", "ถ้าผ้าเบรกบางควรเปลี่ยน", "ซ่อมเบรก"),
        ("ดูแลโซ่", "เช็ดโซ่ให้สะอาดก่อนเติมน้ำมันหล่อลื่น", "ทำความสะอาดโซ่แล้วค่อยหยอดน้ำมัน", "หยอดโซ่"),
        ("ปรับโซ่", "ตรวจความตึงโซ่ไม่ให้หย่อนมากเกินไป", "ดูว่าโซ่ไม่หย่อนจนหลุดง่าย", "ดูโซ่"),
        ("ตรวจไฟ", "เปิดไฟหน้าและไฟท้ายเมื่อขี่ในที่มืด", "ใช้ไฟทั้งด้านหน้าและหลังตอนกลางคืน", "ติดไฟ"),
        ("จดงานซ่อม", "บันทึกวันที่เปลี่ยนชิ้นส่วนเพื่อวางแผนตรวจครั้งหน้า", "จดวันเปลี่ยนอะไหล่ไว้ติดตาม", "จดไว้"),
    ],
}


def draw_deck(deck_id: str, criteria: list[tuple[str, str, str, str]]) -> None:
    path = OUTPUT / f"{deck_id}.pdf"
    pdf = canvas.Canvas(str(path), pagesize=(960, 540))
    titles = {"phishing": "รู้ทันอีเมลหลอกลวง", "urban_garden": "ปลูกผักในพื้นที่เล็ก", "waste_sorting": "แยกขยะในชีวิตประจำวัน", "bike_care": "ดูแลจักรยานก่อนเดินทาง"}
    for slide in range(4):
        pdf.setFillColorRGB(0.97, 0.96, 0.93)
        pdf.rect(0, 0, 960, 540, fill=1, stroke=0)
        pdf.setFillColorRGB(0.09, 0.18, 0.24)
        pdf.roundRect(36, 34, 888, 472, 18, fill=1, stroke=0)
        pdf.setFillColorRGB(0.95, 0.68, 0.42)
        pdf.setFont("TahomaBold", 21)
        pdf.drawString(70, 447, titles[deck_id])
        pdf.setFillColorRGB(1, 1, 1)
        pdf.setFont("TahomaBold", 25)
        pdf.drawString(70, 390, f"ประเด็นที่ {slide + 1}")
        for offset, (label, evidence, _, _) in enumerate(criteria[slide * 2:slide * 2 + 2]):
            y = 302 - offset * 118
            pdf.setFillColorRGB(0.95, 0.68, 0.42)
            pdf.circle(83, y + 5, 5, fill=1, stroke=0)
            pdf.setFillColorRGB(1, 1, 1)
            pdf.setFont("TahomaBold", 18)
            pdf.drawString(105, y + 15, label)
            pdf.setFont("Tahoma", 17)
            pdf.drawString(105, y - 20, evidence)
        pdf.setFillColorRGB(0.68, 0.75, 0.78)
        pdf.setFont("Tahoma", 12)
        pdf.drawRightString(890, 57, f"{slide + 1} / 4")
        pdf.showPage()
    pdf.save()


def make_examples() -> list[dict]:
    rows = []
    for deck_id, criteria in DECKS.items():
        for slide in range(4):
            pair = criteria[slide * 2:slide * 2 + 2]
            question = f"จากสไลด์หน้า {slide + 1} ควรทำอย่างไรบ้าง?"
            for index, (label, evidence, good, partial) in enumerate(pair):
                base = {"deck_id": deck_id, "source_page": slide + 1, "question": question,
                        "current_prompt": question, "criterion_id": f"{deck_id}_{slide + 1}_{index + 1}",
                        "criterion": label, "evidence_quote": evidence, "synthetic": True}
                for answer, status, off_topic in ((good, "covered", False), (partial, "partial", False),
                                                  (pair[1 - index][2], "missing", False), ("ชานมไข่มุกอร่อยมาก", "missing", True)):
                    rows.append({**base, "answer": answer, "status": status, "off_topic": off_topic})
    return rows


if __name__ == "__main__":
    if not FONT.exists() or not BOLD.exists():
        raise SystemExit("Thai TTF fonts are required; set TRAINING_THAI_FONT and TRAINING_THAI_BOLD_FONT")
    OUTPUT.mkdir(exist_ok=True)
    pdfmetrics.registerFont(TTFont("Tahoma", str(FONT)))
    pdfmetrics.registerFont(TTFont("TahomaBold", str(BOLD)))
    for deck_name, deck_criteria in DECKS.items():
        draw_deck(deck_name, deck_criteria)
    rows = make_examples()
    (ROOT / "synthetic_examples.jsonl").write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
    print(f"Generated {len(DECKS)} PDFs and {len(rows)} synthetic labeled rows")
