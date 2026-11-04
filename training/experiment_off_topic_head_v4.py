"""Test a SetFit-style off-topic head on the diversified checkpoint.

Selection uses validation only. The old 50-case suite is diagnostic.
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "training"))

from ablate_anchor_v2 import stress_rows  # noqa: E402
from compare_diverse_checkpoints import load_checkpoint  # noqa: E402
from experiment_off_topic import best_threshold, features  # noqa: E402
from train_embeddinggemma import binary_f1, read_augmented_split, read_diverse_split  # noqa: E402


def case_metrics(rows, probabilities, threshold):
    grouped = {}
    for row, probability in zip(rows, probabilities):
        grouped.setdefault(row["case_id"], []).append((row["off_topic"], probability))
    actual = [items[0][0] for items in grouped.values()]
    predicted = [min(probability for _, probability in items) >= threshold for items in grouped.values()]
    return {"cases": len(actual), "f1": round(binary_f1(actual, predicted), 3),
            "true_positive": sum(a and p for a, p in zip(actual, predicted)),
            "false_positive": sum(not a and p for a, p in zip(actual, predicted)),
            "false_negative": sum(a and not p for a, p in zip(actual, predicted))}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-model", required=True, type=Path)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    model = load_checkpoint(args.base_model, args.checkpoint)
    train = read_augmented_split("train", include_hard=True) + read_diverse_split("train")
    validation = read_augmented_split("validation", include_hard=True) + read_diverse_split("validation")
    train_x, val_x = features(model, train), features(model, validation)
    train_y = np.array([int(r["off_topic"]) for r in train])
    val_y = [bool(r["off_topic"]) for r in validation]
    report = {"train_rows": len(train), "validation_rows": len(validation),
              "stress_50_used_for_selection": False, "candidates": {}}
    selected = None
    for weight in (None, "balanced"):
        for c in (0.03, 0.3, 3.0):
            classifier = make_pipeline(StandardScaler(), LogisticRegression(C=c, class_weight=weight,
                                                                             max_iter=1000, random_state=2026))
            classifier.fit(train_x, train_y)
            probabilities = classifier.predict_proba(val_x)[:, 1]
            threshold, f1, fp = best_threshold(val_y, probabilities)
            key = f"C={c},weight={weight}"
            report["candidates"][key] = {"validation_f1": round(float(f1), 3),
                                          "validation_false_positives": int(fp),
                                          "threshold": round(float(threshold), 5)}
            if selected is None or (f1, -fp) > selected[0]:
                selected = ((f1, -fp), key, classifier, threshold)
            print(key, f1, fp, flush=True)
    report["selected_by_validation"] = selected[1]
    classifier, threshold = selected[2], selected[3]
    test = read_augmented_split("test_synthetic") + read_diverse_split("test")
    stress = stress_rows(ROOT / "training" / "robustness_50.json")
    test_x, stress_x = features(model, test), features(model, stress)
    test_pred = classifier.predict_proba(test_x)[:, 1] >= threshold
    report["new_test"] = {"rows": len(test), "f1": round(binary_f1([bool(r["off_topic"]) for r in test], test_pred), 3)}
    report["stress_50"] = case_metrics(stress, classifier.predict_proba(stress_x)[:, 1], threshold)
    print("selected", selected[1], report["new_test"], report["stress_50"], flush=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                      default=lambda value: value.item() if hasattr(value, "item") else str(value)) + "\n",
                           encoding="utf-8")


if __name__ == "__main__":
    main()
