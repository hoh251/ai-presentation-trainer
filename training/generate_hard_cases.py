"""Curated Thai answer contrasts for training/validation decks only.

These are authored labels, not real student answers. The bike test deck is
intentionally absent so candidate selection cannot inspect new test variants.
"""

import json
from pathlib import Path

from baseline import read_rows

ROOT = Path(__file__).resolve().parent
# deck, criterion label, answer, coverage label, off-topic flag
CASES = [
    ("cats_demo", "จัดมุมเงียบ", "จัดมุมที่ไม่มีเสียงรบกวนให้แมว", "covered", False),
    ("cats_demo", "จัดมุมเงียบ", "แมวควรมีมุมของตัวเอง", "partial", False),
    ("cats_demo", "จัดมุมเงียบ", "ทำบ้านแมวให้เข้าไปหลบ แต่ตั้งไว้ข้างลำโพง", "missing", False),
    ("cats_demo", "จัดมุมเงียบ", "ให้แมวอยู่ตรงที่เสียงดังตลอด", "missing", False),
    ("cats_demo", "จัดที่หลบ", "มีกล่องหรือบ้านแมวให้ซ่อนเมื่อเครียด", "covered", False),
    ("cats_demo", "จัดที่หลบ", "หาที่อยู่ให้แมว", "partial", False),
    ("cats_demo", "จัดที่หลบ", "จัดห้องให้เงียบอย่างเดียว", "missing", False),
    ("cats_demo", "จัดที่หลบ", "ไม่ให้แมวมีที่ซ่อน", "missing", False),
    ("phishing", "ตรวจโดเมน", "เช็กชื่อโดเมนของผู้ส่งให้ตรงองค์กรก่อนกด", "covered", False),
    ("phishing", "ตรวจโดเมน", "ดูชื่อผู้ส่งสักหน่อย", "partial", False),
    ("phishing", "ตรวจโดเมน", "กดลิงก์เลยโดยไม่ดูชื่อเว็บไซต์", "missing", False),
    ("phishing", "ตรวจโดเมน", "เปิดยืนยันตัวตนสองขั้นตอน", "missing", False),
    ("phishing", "ป้องกันบัญชี", "เปิด 2FA สำหรับบัญชีสำคัญ", "covered", False),
    ("phishing", "ป้องกันบัญชี", "ตั้งรหัสผ่านให้ยาวขึ้น", "missing", False),
    ("phishing", "ป้องกันบัญชี", "ดูโดเมนผู้ส่งก่อนเปิดลิงก์", "missing", False),
    ("phishing", "รับมือเมื่อเผลอกด", "รีบเปลี่ยนรหัสและแจ้งผู้ดูแลระบบ", "covered", False),
    ("phishing", "รับมือเมื่อเผลอกด", "รีบแจ้งใครสักคน", "partial", False),
    ("phishing", "รับมือเมื่อเผลอกด", "ไม่ต้องทำอะไรหลังเผลอกด", "missing", False),
    ("urban_garden", "เลือกพื้นที่", "วางผักในมุมที่ได้แดดอย่างน้อยครึ่งวัน", "covered", False),
    ("urban_garden", "เลือกพื้นที่", "ตั้งกระถางไว้ใกล้หน้าต่าง", "partial", False),
    ("urban_garden", "เลือกพื้นที่", "ปลูกไว้ในที่มืดทั้งวัน", "missing", False),
    ("urban_garden", "เตรียมภาชนะ", "ใช้กระถางที่มีรูให้ระบายน้ำได้", "covered", False),
    ("urban_garden", "เตรียมภาชนะ", "เลือกกระถางขนาดพอดี", "missing", False),
    ("urban_garden", "เตรียมภาชนะ", "ใช้กระถางปิดทึบไม่มีรูระบาย", "missing", False),
    ("urban_garden", "รดน้ำ", "จับดินดูความชื้นก่อนเติมน้ำ", "covered", False),
    ("urban_garden", "รดน้ำ", "รดน้ำตอนเช้า", "missing", False),
    ("urban_garden", "รดน้ำ", "รดน้ำทุกชั่วโมงโดยไม่ดูดิน", "missing", False),
    ("urban_garden", "ลดโรค", "เทน้ำค้างในจานรองกระถางทิ้ง", "covered", False),
    ("urban_garden", "ลดโรค", "ดูความชื้นในกระถาง", "partial", False),
    ("urban_garden", "ลดโรค", "ปล่อยน้ำท่วมจานรองไว้ตลอด", "missing", False),
    ("waste_sorting", "แยกเศษอาหาร", "เอาอาหารเหลือออกจากกล่องก่อนทิ้ง", "covered", False),
    ("waste_sorting", "แยกเศษอาหาร", "แยกขยะเปียก", "partial", False),
    ("waste_sorting", "แยกเศษอาหาร", "ทิ้งอาหารปนกล่องกระดาษไปเลย", "missing", False),
    ("waste_sorting", "ลดกลิ่น", "ใส่เศษอาหารในถังที่มีฝาปิด", "covered", False),
    ("waste_sorting", "ลดกลิ่น", "เอาเศษอาหารใส่ถัง", "partial", False),
    ("waste_sorting", "ลดกลิ่น", "เปิดถังเศษอาหารทิ้งไว้", "missing", False),
    ("waste_sorting", "เตรียมรีไซเคิล", "ล้างคราบอาหารก่อนส่งภาชนะรีไซเคิล", "covered", False),
    ("waste_sorting", "เตรียมรีไซเคิล", "แยกภาชนะรีไซเคิล", "missing", False),
    ("waste_sorting", "เตรียมรีไซเคิล", "ไม่ต้องล้างกล่องที่เลอะอาหาร", "missing", False),
    ("waste_sorting", "แยกแบตเตอรี่", "เอาถ่านเก่าไปจุดรับขยะอันตราย", "covered", False),
    ("waste_sorting", "แยกแบตเตอรี่", "แยกถ่านไฟฉายออกมา", "partial", False),
    ("waste_sorting", "แยกแบตเตอรี่", "ทิ้งแบตเตอรี่รวมกับเศษอาหาร", "missing", False),
]


def main() -> None:
    sources = read_rows("train") + read_rows("validation")
    by_key = {(r["deck_id"], r["criterion"]): r for r in sources}
    rows = []
    for deck, criterion, answer, status, off_topic in CASES:
        original = by_key[(deck, criterion)]
        rows.append({**original, "answer": answer, "status": status,
                     "off_topic": off_topic, "hard_case": True})
    path = ROOT / "hard_cases.jsonl"
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    print(f"Wrote {len(rows)} hard cases: train {sum(r['deck_id'] != 'waste_sorting' for r in rows)}, validation {sum(r['deck_id'] == 'waste_sorting' for r in rows)}")


if __name__ == "__main__":
    main()
