"""Evaluate the frozen local checkpoint on 50 new, author-labeled probes.

This is a diagnostic stress set, not training data or an independent benchmark.
Do not select a checkpoint or thresholds using its results.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from model_package import configure_model, predict_attempt  # noqa: E402

LABELS = ("covered", "partial", "missing")


def f1(actual: list[bool], predicted: list[bool]) -> float:
    tp = sum(a and p for a, p in zip(actual, predicted))
    fp = sum(not a and p for a, p in zip(actual, predicted))
    fn = sum(a and not p for a, p in zip(actual, predicted))
    return 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0


def summarize(results: list[dict]) -> dict:
    actual = [label for case in results for label in case["expected"]]
    predicted = [label for case in results for label in case["predicted"]]
    off_actual = [case["expected_off_topic"] for case in results]
    off_predicted = [case["predicted_off_topic"] for case in results]
    bad = [(a, p) for a, p in zip(actual, predicted) if a != "covered"]
    return {
        "cases": len(results),
        "criterion_decisions": len(actual),
        "exact_case_matches": sum(c["expected"] == c["predicted"] and
                                  c["expected_off_topic"] == c["predicted_off_topic"] for c in results),
        "per_class_f1": {label: round(f1([a == label for a in actual],
                                          [p == label for p in predicted]), 3) for label in LABELS},
        "macro_f1": round(sum(f1([a == label for a in actual], [p == label for p in predicted])
                              for label in LABELS) / len(LABELS), 3),
        "off_topic_f1": round(f1(off_actual, off_predicted), 3),
        "false_covered_count": sum(p == "covered" for _, p in bad),
        "not_covered_count": len(bad),
        "false_covered_rate": round(sum(p == "covered" for _, p in bad) / len(bad), 3) if bad else 0.0,
        "confusion": dict(Counter(f"{a}->{p}" for a, p in zip(actual, predicted))),
        "off_topic_confusion": dict(Counter(f"{a}->{p}" for a, p in zip(off_actual, off_predicted))),
        "wrong_case_ids": [c["id"] for c in results if c["expected"] != c["predicted"] or
                           c["expected_off_topic"] != c["predicted_off_topic"]],
    }


def render_markdown(data: dict, report: dict) -> str:
    summary = report["summary"]
    topic_names = {
        "hike": "เดินป่า", "library": "ยืมหนังสือ", "bread": "อบขนมปัง",
        "event": "จัดงาน", "backup": "สำรองข้อมูล",
    }
    lines = [
        "# ผลทดสอบโมเดล v2: 50 คำตอบใหม่",
        "",
        "ชุดนี้เขียนและติดป้ายโดยผู้พัฒนาคนเดียว ใช้หาจุดอ่อน ไม่ใช้ฝึกหรือเลือก threshold และไม่ใช่ benchmark ผู้ใช้จริง",
        "",
        f"- Checkpoint: `{report['model_version']}`; SHA-256 adapter `{report['checkpoint_sha256']}`",
        f"- {summary['cases']} คำตอบ, {summary['criterion_decisions']} การตัดสินรายเกณฑ์, 5 หัวข้อใหม่ หัวข้อละ 10 คำตอบ",
        f"- ตรงเฉลยครบทั้งสองเกณฑ์และ off-topic: **{summary['exact_case_matches']}/50**",
        f"- Coverage macro F1: **{summary['macro_f1']:.3f}**; covered F1 {summary['per_class_f1']['covered']:.3f}, partial F1 {summary['per_class_f1']['partial']:.3f}, missing F1 {summary['per_class_f1']['missing']:.3f}",
        f"- Off-topic F1: **{summary['off_topic_f1']:.3f}**",
        f"- ตัดสินว่า covered ผิด: **{summary['false_covered_count']}/{summary['not_covered_count']}** กรณีที่เฉลยไม่ใช่ covered; ค่านี้ไม่ใช่อัตราคำชมจากหน้าเว็บ",
        "- ผลการตัดสิน: " + ", ".join(f"`{key}` {count}" for key, count in summary["confusion"].items()),
        "",
        "## จุดที่เห็นชัด",
        "",
        "- คำตอบที่เฉลยเป็น covered มี 47 จุด โมเดลให้ covered เพียง 7 จุด อีก 27 จุดถูกลดเป็น partial และ 13 จุดเป็น missing: โมเดลระวังเกินไปกับหัวข้อใหม่",
        "- ตัวอย่างง่ายที่พลาด: B01 ตอบเรื่องอุ่นเตาและจับเวลาแต่เวลาถูกให้ partial; E01 ตอบทั้งลงทะเบียนและทางออกฉุกเฉินแต่ได้ partial ทั้งคู่; D01 ตอบทั้งเก็บสำเนาอีกที่และลองกู้คืนแต่ได้ partial ทั้งคู่",
        "- ตัวอย่างภาษาแชต/คำผิดที่พลาด: H08, H09, B08, D10; ตัวอย่างคำสั่งหลอกที่พลาดการติด off-topic: B07",
        "- ผลนี้อาจมีความคลาดเคลื่อนจากเฉลยที่ผู้พัฒนาคนเดียวกำหนด โดยเฉพาะ partial/covered ควรให้คนที่สองตรวจซ้ำก่อนใช้เป็นข้อสรุปเชิงวิจัย",
        "",
        "## ผลทั้ง 50 กรณี",
        "",
        "รูปแบบสถานะ: `covered / partial / missing`; off-topic แสดง `ใช่ / ไม่` ตามลำดับเฉลย→โมเดล",
        "",
        "| ID | หัวข้อ | รูปแบบ | คำตอบ | เฉลย 2 เกณฑ์ | โมเดล 2 เกณฑ์ | นอกเรื่อง | ผล |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for case in report["results"]:
        safe_answer = case["answer"].replace("|", "\\|").replace("\n", " ")
        expected = "/".join(case["expected"])
        predicted = "/".join(case["predicted"])
        off = ("ใช่" if case["expected_off_topic"] else "ไม่") + "→" + (
            "ใช่" if case["predicted_off_topic"] else "ไม่")
        lines.append(f"| {case['id']} | {topic_names[case['topic']]} | {case['pattern']} | {safe_answer} | {expected} | {predicted} | {off} | {'ผ่าน' if case['match'] else 'พลาด'} |")
    lines.extend([
        "",
        "## ขั้นถัดไป",
        "",
        "1. ให้ผู้ตรวจอีกคนทวนเฉลย โดยเฉพาะตัวอย่างที่แยก `partial` กับ `covered` ยาก",
        "2. เก็บคำตอบจากผู้ใช้จริงและ PDF หัวข้อใหม่ แล้วแยกชุดฝึก/validation/test ตามหัวข้อก่อนปรับโมเดล",
        "3. ศึกษาเหตุที่คำตอบถูกบนหัวข้อใหม่ได้คะแนน similarity ต่ำ แล้วแก้ข้อมูลฝึกหรือรูปแบบ anchor; เลือก threshold จาก validation ใหม่เท่านั้น",
        "4. ทดสอบ checkpoint ใหม่บน holdout ใหม่และผ่าน API/Agent จริง ไม่ใช้ 50 กรณีนี้เป็นคะแนนหลังปรับซ้ำ",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-model", required=True, type=Path)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--manifest", default=ROOT / "model_package" / "manifest.json", type=Path)
    parser.add_argument("--cases", default=ROOT / "training" / "robustness_50.json", type=Path)
    parser.add_argument("--output", default=ROOT / "training" / "robustness_50_results.json", type=Path)
    parser.add_argument("--report", default=ROOT / "training" / "ROBUSTNESS_50_REPORT.md", type=Path)
    args = parser.parse_args()

    data = json.loads(args.cases.read_text(encoding="utf-8"))
    cases = data["cases"]
    assert len(cases) == 50 and len({case["id"] for case in cases}) == 50
    assert set(case["topic"] for case in cases) == set(data["topics"])
    for case in cases:
        assert len(case["expected"]) == 2 and set(case["expected"]) <= set(LABELS)
        assert not (case["off_topic"] and "covered" in case["expected"])

    model = configure_model(str(args.base_model), str(args.checkpoint), str(args.manifest))
    results = []
    for index, case in enumerate(cases, 1):
        topic = data["topics"][case["topic"]]
        question = {"id": case["topic"], "text": topic["question"], "criteria": topic["criteria"]}
        output = predict_attempt(question, topic["question"], topic["criteria"], case["answer"])
        predicted = [item["status"] for item in output["criteria"]]
        result = {
            "id": case["id"], "topic": case["topic"], "pattern": case["pattern"],
            "answer": case["answer"], "expected": case["expected"], "predicted": predicted,
            "expected_off_topic": case["off_topic"],
            "predicted_off_topic": output["off_topic"]["value"],
            "off_topic_confidence": output["off_topic"]["confidence"],
            "criterion_confidences": [item["confidence"] for item in output["criteria"]],
            "match": case["expected"] == predicted and case["off_topic"] == output["off_topic"]["value"],
        }
        results.append(result)
        print(f"{index:02d}/50 {case['id']} {'OK' if result['match'] else 'FAIL'}", flush=True)

    report = {
        "description": data["description"],
        "model_version": json.loads(args.manifest.read_text(encoding="utf-8"))["model_version"],
        "checkpoint_sha256": json.loads(args.manifest.read_text(encoding="utf-8"))["checkpoint_sha256"],
        "thresholds_changed_for_test": False,
        "limitations": "Labels were written by one author; five constructed scenarios are not independent student answers or full PDF/API sessions.",
        "summary": summarize(results),
        "results": results,
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.report.write_text(render_markdown(data, report), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
