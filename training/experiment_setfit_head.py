"""Frozen EmbeddingGemma plus a small supervised classification head.

Inspired by SetFit's second stage. Model and hyperparameters are selected on
the existing validation deck; the 50-case suite is diagnostic only.
"""

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "training"))

from baseline import similarity as lexical_similarity  # noqa: E402
from model_package import configure_model  # noqa: E402
from train_embeddinggemma import read_augmented_split, binary_f1  # noqa: E402
from ablate_anchor_v2 import anchor, stress_rows, PREFIX  # noqa: E402

LABELS = ("covered", "partial", "missing")


def features(model, rows: list[dict]) -> np.ndarray:
    with torch.no_grad():
        answers = model.encode([PREFIX + "คำตอบ: " + r["answer"] for r in rows], batch_size=4,
                               convert_to_tensor=True, show_progress_bar=False).float()
        full = model.encode([anchor(r, "full") for r in rows], batch_size=4,
                            convert_to_tensor=True, show_progress_bar=False).float()
        criteria = model.encode([anchor(r, "criterion_only") for r in rows], batch_size=4,
                                convert_to_tensor=True, show_progress_bar=False).float()
        questions = model.encode([PREFIX + r["question"] for r in rows], batch_size=4,
                                 convert_to_tensor=True, show_progress_bar=False).float()
    full_sim = F.cosine_similarity(full, answers).cpu().numpy()
    criterion_sim = F.cosine_similarity(criteria, answers).cpu().numpy()
    question_sim = F.cosine_similarity(questions, answers).cpu().numpy()
    numeric = [[full_sim[i], criterion_sim[i], question_sim[i],
                math.log1p(len(r["answer"])), lexical_similarity(r["answer"], r["criterion"]),
                int("ไม่" in r["answer"] or "ห้าม" in r["answer"] or "never" in r["answer"].lower())]
               for i, r in enumerate(rows)]
    return np.asarray(numeric, dtype=np.float32)


def evaluate(rows, predicted) -> dict:
    actual = [r["status"] for r in rows]
    bad = [p for a, p in zip(actual, predicted) if a != "covered"]
    return {"macro_f1": round(f1_score(actual, predicted, labels=LABELS, average="macro"), 3),
            "per_class_f1": {label: round(f1_score([a == label for a in actual],
                                                   [p == label for p in predicted]), 3) for label in LABELS},
            "false_covered": sum(p == "covered" for p in bad),
            "false_covered_rate": round(sum(p == "covered" for p in bad) / len(bad), 3),
            "covered_recall": round(sum(a == p == "covered" for a, p in zip(actual, predicted)) /
                                    max(1, actual.count("covered")), 3)}


def predict_with_cover_gate(classifier, x, threshold: float) -> list[str]:
    probabilities = classifier.predict_proba(x)
    labels = list(classifier.classes_)
    covered_index = labels.index("covered")
    return ["covered" if row[covered_index] >= threshold else
            labels[max((i for i in range(len(labels)) if i != covered_index), key=lambda i: row[i])]
            for row in probabilities]


def calibrate_cover_gate(classifier, x, rows) -> tuple[float, dict]:
    covered_index = list(classifier.classes_).index("covered")
    values = sorted(set(classifier.predict_proba(x)[:, covered_index].tolist()))
    candidates = [0.0] + [(a + b) / 2 for a, b in zip(values, values[1:])] + [1.0]
    eligible = []
    for threshold in candidates:
        measured = evaluate(rows, predict_with_cover_gate(classifier, x, threshold))
        if measured["false_covered_rate"] <= 0.024:
            eligible.append((threshold, measured))
    return max(eligible, key=lambda item: item[1]["macro_f1"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-model", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    predictor = configure_model(args.base_model, args.checkpoint, str(ROOT / "model_package" / "manifest.json"))
    train = read_augmented_split("train", include_hard=True)
    val = read_augmented_split("validation", include_hard=True)
    stress = stress_rows(ROOT / "training" / "robustness_50.json")
    train_x, val_x, stress_x = (features(predictor.model, rows) for rows in (train, val, stress))
    report = {"train_rows": len(train), "validation_rows": len(val), "stress_50_rows": len(stress),
              "validation_deck": "waste_sorting", "stress_used_for_selection": False,
              "features": ["full_cos", "criterion_cos", "question_cos", "answer_length",
                           "character_overlap", "negation_present"], "candidates": {}}
    candidates = []
    for weight in (None, "balanced"):
        for c in (0.03, 0.3, 3.0):
            classifier = make_pipeline(StandardScaler(), LogisticRegression(C=c, class_weight=weight,
                                                                             max_iter=1000, random_state=2026))
            classifier.fit(train_x, [r["status"] for r in train])
            threshold, validation = calibrate_cover_gate(classifier, val_x, val)
            key = f"C={c},weight={weight}"
            candidates.append((key, c, weight, threshold, validation))
            report["candidates"][key] = {"covered_probability_gate": round(threshold, 5),
                                          "validation": validation}
            print(key, threshold, validation, flush=True)
    selected = max(candidates, key=lambda item: item[4]["macro_f1"])
    report["selected_by_validation"] = selected[0]
    classifier = make_pipeline(StandardScaler(), LogisticRegression(C=selected[1], class_weight=selected[2],
                                                                     max_iter=1000, random_state=2026))
    classifier.fit(train_x, [r["status"] for r in train])
    stress_predicted = predict_with_cover_gate(classifier, stress_x, selected[3])
    report["stress_50"] = evaluate(stress, stress_predicted)
    report["stress_errors"] = [dict(case_id=row["case_id"], criterion=row["criterion"],
                                    expected=row["status"], predicted=prediction,
                                    old_full_cos=round(float(stress_x[i][0]), 5))
                               for i, (row, prediction) in enumerate(zip(stress, stress_predicted))
                               if row["status"] != prediction]
    print("stress_50", report["stress_50"], flush=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
