"""Minimal positive/negated-answer pairs on fresh topics.

This test is inspired by SemAntoNeg and ALIGN-SIM. It is diagnostic only and
must not be used to choose the checkpoint or tune thresholds.
"""

import argparse
import json
import sys
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "training"))

from compare_diverse_checkpoints import load_checkpoint  # noqa: E402
from train_embeddinggemma import similarities  # noqa: E402

# question, criterion, valid answer, explicitly negated/wrong answer
PAIRS = [
    ("ก่อนออกจากบ้านควรทำอะไรกับประตู?", "ล็อกประตูก่อนออกจากบ้าน", "ล็อกประตูก่อนออก", "ไม่ต้องล็อกประตูก่อนออก"),
    ("ก่อนเผยแพร่พอดแคสต์ควรตรวจอะไร?", "ตรวจคุณภาพเสียงก่อนเผยแพร่", "ฟังเช็กเสียงก่อนปล่อยตอน", "ไม่ต้องตรวจเสียงก่อนเผยแพร่"),
    ("ก่อนจัดโต๊ะอาหารควรทำอย่างไร?", "เช็ดโต๊ะให้สะอาดก่อนวางอาหาร", "เช็ดโต๊ะก่อนเอาอาหารมาวาง", "ไม่ต้องเช็ดโต๊ะก่อนวางอาหาร"),
    ("ก่อนลบภาพจากกล้องควรทำอะไร?", "คัดลอกภาพเก็บไว้อีกที่ก่อนลบ", "ย้ายรูปไปเก็บที่อื่นก่อนลบจากกล้อง", "ลบรูปจากกล้องทันทีโดยไม่คัดลอกเก็บ"),
    ("ก่อนเริ่มเกมกระดานควรทำอะไร?", "อ่านกติกาก่อนเริ่มเล่น", "ดูวิธีเล่นให้เข้าใจก่อนเริ่ม", "ไม่ต้องอ่านกติกาก่อนเล่น"),
    ("ก่อนสั่งซื้อของเข้าร้านควรทำอย่างไร?", "นับจำนวนสินค้าคงเหลือก่อนสั่ง", "เช็กสต็อกก่อนสั่งของเพิ่ม", "ไม่ต้องนับของในสต็อกก่อนสั่ง"),
    ("ก่อนขึ้นรถไฟควรตรวจอะไร?", "ตรวจหมายเลขขบวนบนตั๋ว", "ดูเลขขบวนให้ตรงกับตั๋ว", "ขึ้นรถโดยไม่ดูเลขขบวนบนตั๋ว"),
    ("ก่อนใช้เตารีดควรตรวจอะไร?", "ตรวจระดับความร้อนให้เหมาะกับผ้า", "ปรับไฟเตารีดตามชนิดผ้า", "ไม่ต้องดูระดับความร้อนของเตารีด"),
    ("ก่อนเริ่มวาดภาพควรเตรียมอะไร?", "เตรียมอุปกรณ์วาดภาพให้ครบ", "จัดดินสอและกระดาษไว้ให้พร้อม", "ไม่ต้องเตรียมอุปกรณ์วาดภาพ"),
    ("เมื่อจอดรถควรทำอย่างไร?", "จอดรถในช่องที่กำหนด", "นำรถเข้าช่องจอดที่ระบุ", "จอดรถนอกช่องที่กำหนด"),
    ("ก่อนพิมพ์เอกสารควรทำอะไร?", "ตรวจหน้าตัวอย่างก่อนสั่งพิมพ์", "ดูพรีวิวหน้าเอกสารก่อนกดพิมพ์", "กดพิมพ์โดยไม่ดูหน้าตัวอย่าง"),
    ("ก่อนเปิดร้านค้าควรทำอะไรกับป้ายราคา?", "ตรวจป้ายราคาสินค้าให้ตรงกับระบบ", "เทียบราคาหน้าชั้นกับราคาในเครื่อง", "ไม่ต้องตรวจว่าป้ายราคาตรงกับระบบ"),
]


def row(question: str, criterion: str, answer: str) -> dict:
    return {"question": question, "current_prompt": question, "criterion": criterion,
            "evidence_quote": criterion, "answer": answer, "status": "covered", "off_topic": False}


def status(score: float, threshold: list[float]) -> str:
    return "missing" if score < threshold[0] else "partial" if score < threshold[1] else "covered"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-model", required=True, type=Path)
    parser.add_argument("--v2-checkpoint", required=True, type=Path)
    parser.add_argument("--soup-checkpoint", required=True, type=Path)
    parser.add_argument("--comparison", required=True, type=Path)
    parser.add_argument("--soup-report", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    comparison = json.loads(args.comparison.read_text(encoding="utf-8"))
    soup = json.loads(args.soup_report.read_text(encoding="utf-8"))
    rows = [row(question, criterion, answer) for question, criterion, positive, negative in PAIRS
            for answer in (positive, negative)]
    report = {"pairs": len(PAIRS), "selection_used_this_probe": False, "models": {}}
    for name, path, threshold in (
        ("v2", args.v2_checkpoint, comparison["candidates"]["v2"]["thresholds"]),
        ("soup_50", args.soup_checkpoint, soup["candidates"]["soup_50"]["thresholds"]),
    ):
        model = load_checkpoint(args.base_model, path)
        values = similarities(model, rows, 4)
        del model
        torch.cuda.empty_cache()
        pairs = []
        for i, (question, criterion, positive, negative) in enumerate(PAIRS):
            good, bad = values[2 * i:2 * i + 2]
            pairs.append({"id": i + 1, "criterion": criterion, "positive": positive, "negative": negative,
                          "positive_score": round(good, 5), "negative_score": round(bad, 5),
                          "positive_status": status(good, threshold), "negative_status": status(bad, threshold),
                          "rank_correct": good > bad})
        report["models"][name] = {"rank_correct": sum(p["rank_correct"] for p in pairs),
                                  "positive_covered": sum(p["positive_status"] == "covered" for p in pairs),
                                  "negative_covered_wrong": sum(p["negative_status"] == "covered" for p in pairs),
                                  "both_exact": sum(p["positive_status"] == "covered" and p["negative_status"] == "missing" for p in pairs),
                                  "pairs": pairs}
        print(name, {key: report["models"][name][key] for key in
                     ("rank_correct", "positive_covered", "negative_covered_wrong", "both_exact")}, flush=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
