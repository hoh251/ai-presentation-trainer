"""Exploratory per-criterion normalization for unseen-slide coverage.

Selects status thresholds using validation only; already-viewed tests are diagnostic.
Never changes model_package, manifest, or the deployed checkpoint.
"""

import json
import sys
from pathlib import Path

import torch
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[2]
sys.path.insert(0, str(PROJECT / "work/deadlocks_100"))

from compare_diverse_checkpoints import load_checkpoint  # noqa: E402
from train_embeddinggemma import (encode_texts, read_augmented_split,
                                  read_diverse_split, passages)  # noqa: E402
from evaluate import summarize  # noqa: E402

BASE = PROJECT / "work/models/embeddinggemma-300m"
CHECKPOINT = PROJECT / "work/experiments/improve-mse-hard/checkpoint"
MANIFEST = ROOT.parent / "model_package/manifest.json"
OUTPUT = ROOT / "optimization/reference_normalization_pilot.json"
LABELS = ("covered", "partial", "missing")


def scores(model, rows):
    pairs = [passages(row) for row in rows]
    anchors = encode_texts(model, [pair[0] for pair in pairs], 4)
    answers = encode_texts(model, [pair[1] for pair in pairs], 4)
    references = encode_texts(
        model, [f"task: sentence similarity | query: คำตอบ: {row['criterion']}" for row in rows], 4)
    raw = F.cosine_similarity(anchors, answers).cpu().tolist()
    self_reference = F.cosine_similarity(anchors, references).cpu().tolist()
    return raw, [value - reference for value, reference in zip(raw, self_reference)]


def predict(raw, adjusted, low, high, off):
    return [
        {"status": "missing" if original < off or value < low else
                   "partial" if value < high else "covered",
         "off_topic": original < off}
        for original, value in zip(raw, adjusted)
    ]


def calibrate(rows, raw, adjusted, off, max_false_covered=0.03):
    unique = sorted(set(adjusted))
    thresholds = [unique[0] - 0.001] + [(left + right) / 2 for left, right in zip(unique, unique[1:])] + [unique[-1] + 0.001]
    best = None
    for low in thresholds:
        for high in thresholds:
            if low >= high:
                continue
            predicted = predict(raw, adjusted, low, high, off)
            result = summarize(rows, predicted)
            if result["false_covered"]["rate"] > max_false_covered:
                continue
            key = (result["coverage_macro_f1"], result["per_class"]["covered"]["recall"],
                   -result["false_covered"]["rate"])
            if best is None or key > best[0]:
                best = (key, low, high)
    if best is None:
        raise RuntimeError("No threshold pair satisfied validation false-covered cap")
    return best[1], best[2]


def compact(result):
    return {key: result[key] for key in ("cases", "exact_status_correct", "coverage_macro_f1",
                                         "per_class", "off_topic", "false_covered")}


def main():
    torch.set_grad_enabled(False)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    old_low, old_high, old_off = manifest["validation_thresholds"]
    datasets = {
        "validation": read_augmented_split("validation", include_hard=True) + read_diverse_split("validation"),
        "previously_opened_synthetic_test": read_augmented_split("test_synthetic") + read_diverse_split("test"),
        "previously_opened_deadlocks_diagnostic": [json.loads(line) for line in
            (PROJECT / "work/deadlocks_100/deadlocks_100.jsonl").read_text(encoding="utf-8").splitlines() if line],
    }
    for rows in datasets.values():
        for row in rows:
            row.setdefault("pattern", "unspecified")
    model = load_checkpoint(BASE, CHECKPOINT)
    computed = {}
    for name, rows in datasets.items():
        raw, adjusted = scores(model, rows)
        computed[name] = (raw, adjusted)
        print(f"encoded {name} rows={len(rows)}", flush=True)
    del model
    torch.cuda.empty_cache()
    validation_raw, validation_adjusted = computed["validation"]
    raw_calibration = calibrate(datasets["validation"], validation_raw, validation_raw, old_off)
    adjusted_calibration = calibrate(datasets["validation"], validation_raw, validation_adjusted, old_off)
    report = {
        "method": "answer similarity minus anchor-to-criterion self-reference similarity",
        "status": "exploratory; no production change",
        "selection": "thresholds calibrated on validation only; existing test and Deadlocks already opened",
        "deployed_v2_thresholds": [old_low, old_high, old_off],
        "raw_recalibrated_thresholds": [round(value, 5) for value in raw_calibration],
        "normalized_thresholds": [round(value, 5) for value in adjusted_calibration],
        "datasets": {},
    }
    for name, rows in datasets.items():
        raw, adjusted = computed[name]
        report["datasets"][name] = {
            "deployed_v2": compact(summarize(rows, predict(raw, raw, old_low, old_high, old_off))),
            "raw_recalibrated": compact(summarize(rows, predict(raw, raw, *raw_calibration, old_off))),
            "normalized": compact(summarize(rows, predict(raw, adjusted, *adjusted_calibration, old_off))),
        }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for name, options in report["datasets"].items():
        print(name, {option: {"macro_f1": item["coverage_macro_f1"],
                              "covered_recall": item["per_class"]["covered"]["recall"],
                              "false_covered": item["false_covered"]["rate"]}
                     for option, item in options.items()}, flush=True)


if __name__ == "__main__":
    main()
