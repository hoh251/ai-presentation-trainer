"""Compare predefined anchor text variants with frozen v2 weights.

Select a candidate using the existing validation deck only. The 50-case stress
set is reported for diagnosis, never for candidate or threshold selection.
"""

import argparse
import json
import sys
from pathlib import Path

import torch
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "training"))

from model_package import configure_model  # noqa: E402
from train_embeddinggemma import metrics, read_augmented_split, thresholds_from_validation  # noqa: E402

PREFIX = "task: sentence similarity | query: "
VARIANTS = ("full", "question_criterion", "criterion_evidence", "criterion_only")


def anchor(row: dict, variant: str) -> str:
    prompt = row.get("current_prompt") or row["question"]
    criterion = row["criterion"]
    evidence = row.get("evidence_quote") or criterion
    if variant == "full":
        value = f"คำถาม: {prompt} เกณฑ์: {criterion} หลักฐาน: {evidence}"
    elif variant == "question_criterion":
        value = f"คำถาม: {prompt} เกณฑ์: {criterion}"
    elif variant == "criterion_evidence":
        value = f"เกณฑ์: {criterion} หลักฐาน: {evidence}"
    else:
        value = criterion
    return PREFIX + value


def stress_rows(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for case in data["cases"]:
        topic = data["topics"][case["topic"]]
        for criterion, status in zip(topic["criteria"], case["expected"]):
            rows.append({"deck_id": case["topic"], "case_id": case["id"],
                         "question": topic["question"], "current_prompt": topic["question"],
                         "criterion": criterion["text"], "evidence_quote": criterion["evidence_quote"],
                         "answer": case["answer"], "status": status, "off_topic": case["off_topic"]})
    return rows


def scores(model, rows: list[dict], variant: str) -> list[float]:
    anchors = [anchor(row, variant) for row in rows]
    answers = [PREFIX + "คำตอบ: " + row["answer"] for row in rows]
    with torch.no_grad():
        a = model.encode(anchors, batch_size=4, convert_to_tensor=True, show_progress_bar=False).float()
        b = model.encode(answers, batch_size=4, convert_to_tensor=True, show_progress_bar=False).float()
    return F.cosine_similarity(a, b).cpu().tolist()


def stress_metrics(rows: list[dict], values: list[float], thresholds: tuple[float, float, float]) -> dict:
    low, high, off = thresholds
    predicted = ["missing" if score < low else "partial" if score < high else "covered" for score in values]
    covered_actual = [row["status"] == "covered" for row in rows]
    covered_predicted = [status == "covered" for status in predicted]
    case_ids = list(dict.fromkeys(row["case_id"] for row in rows))
    case_off = {case: next(row["off_topic"] for row in rows if row["case_id"] == case) for case in case_ids}
    case_scores = {case: max(score for row, score in zip(rows, values) if row["case_id"] == case) for case in case_ids}
    correct_off = sum(case_off[case] == (case_scores[case] < off) for case in case_ids)
    from train_embeddinggemma import binary_f1
    return {"coverage": metrics(rows, values, thresholds),
            "covered_recall": round(sum(a and p for a, p in zip(covered_actual, covered_predicted)) /
                                    max(1, sum(covered_actual)), 3),
            "off_topic_case_f1": round(binary_f1([case_off[c] for c in case_ids],
                                                   [case_scores[c] < off for c in case_ids]), 3),
            "off_topic_case_exact": correct_off}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-model", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    predictor = configure_model(args.base_model, args.checkpoint, str(ROOT / "model_package" / "manifest.json"))
    validation = read_augmented_split("validation", include_hard=True)
    stress = stress_rows(ROOT / "training" / "robustness_50.json")
    report = {"selection_data": "waste_sorting validation only", "stress_set_used_for_selection": False,
              "weight_changes": False, "variants": {}}
    for variant in VARIANTS:
        val_scores = scores(predictor.model, validation, variant)
        thresholds = thresholds_from_validation(validation, val_scores)
        val_metrics = metrics(validation, val_scores, thresholds)
        stress_scores = scores(predictor.model, stress, variant)
        report["variants"][variant] = {"thresholds": [round(t, 5) for t in thresholds],
                                       "validation": val_metrics,
                                       "stress_50": stress_metrics(stress, stress_scores, thresholds)}
        print(variant, "validation", val_metrics["macro_f1"], val_metrics["false_praise_rate"],
              "stress", report["variants"][variant]["stress_50"]["coverage"]["macro_f1"], flush=True)
    eligible = [(name, value) for name, value in report["variants"].items()
                if value["validation"]["false_praise_rate"] <= 0.024]
    eligible.sort(key=lambda item: item[1]["validation"]["macro_f1"], reverse=True)
    report["selected_by_validation"] = eligible[0][0] if eligible else "none"
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("selected_by_validation", report["selected_by_validation"], flush=True)


if __name__ == "__main__":
    main()
