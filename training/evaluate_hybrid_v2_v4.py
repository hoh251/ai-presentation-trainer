"""Offline comparison: v2 off-topic gate followed by v4 coverage scorer.

Thresholds are frozen from the prior validation-only comparison. The old 50
cases are diagnostics, not an independent selection set.
"""

import argparse
import json
from collections import Counter
from pathlib import Path

import torch

from ablate_anchor_v2 import stress_rows
from compare_diverse_checkpoints import load_checkpoint
from train_embeddinggemma import (binary_f1, false_praise_rate, macro_f1,
                                  read_augmented_split, read_diverse_split,
                                  similarities)

ROOT = Path(__file__).resolve().parents[1]
V2 = (0.51374, 0.70459, 0.30767)
V4 = (0.50645, 0.73443, 0.22878)


def case_key(row: dict) -> tuple:
    return (row["deck_id"], row.get("source_page"), row.get("current_prompt") or row["question"], row["answer"])


def assess(rows: list[dict], v2_scores: list[float], v4_scores: list[float],
           coverage_model: str, gate_model: str, require_v2_covered: bool = False) -> dict:
    scores = v2_scores if coverage_model == "v2" else v4_scores
    low, high, _ = V2 if coverage_model == "v2" else V4
    gate_scores = v2_scores if gate_model == "v2" else v4_scores
    gate_threshold = (V2 if gate_model == "v2" else V4)[2]
    by_case = {}
    for row, score in zip(rows, gate_scores):
        key = case_key(row)
        by_case[key] = max(score, by_case.get(key, float("-inf")))
    case_off = {key: score < gate_threshold for key, score in by_case.items()}
    predicted_off = [case_off[case_key(row)] for row in rows]
    predicted = ["missing" if off or score < low else "partial" if score < high else "covered"
                 for off, score in zip(predicted_off, scores)]
    if require_v2_covered:
        predicted = ["partial" if label == "covered" and v2_score < V2[1] else label
                     for label, v2_score in zip(predicted, v2_scores)]
    actual_off = [bool(row["off_topic"]) for row in rows]
    cases = list(dict.fromkeys(case_key(row) for row in rows))
    case_actual = {case_key(row): bool(row["off_topic"]) for row in rows}
    return {
        "rows": len(rows), "cases": len(cases),
        "coverage_macro_f1": round(macro_f1(rows, predicted), 3),
        "off_topic_case_f1": round(binary_f1([case_actual[c] for c in cases], [case_off[c] for c in cases]), 3),
        "off_topic_row_f1": round(binary_f1(actual_off, predicted_off), 3),
        "false_covered_rate": round(false_praise_rate(rows, predicted), 3),
        "confusion": dict(Counter(f"{row['status']}->{label}" for row, label in zip(rows, predicted))),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-model", required=True, type=Path)
    parser.add_argument("--v2-checkpoint", required=True, type=Path)
    parser.add_argument("--v4-checkpoint", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--scores-cache", type=Path,
                        help="Optional private work-path cache of per-row scores for offline diagnostics")
    args = parser.parse_args()
    sets = {
        "validation": read_augmented_split("validation", include_hard=True) + read_diverse_split("validation"),
        "synthetic_test": read_augmented_split("test_synthetic") + read_diverse_split("test"),
        "old_50_diagnostic": stress_rows(ROOT / "training" / "robustness_50.json"),
    }
    if args.scores_cache and args.scores_cache.exists():
        scores = json.loads(args.scores_cache.read_text(encoding="utf-8"))
        if any(len(scores[name][split]) != len(rows)
               for name in ("v2", "v4") for split, rows in sets.items()):
            raise ValueError("Score cache row count does not match current data")
    else:
        scores = {}
        for name, checkpoint in (("v2", args.v2_checkpoint), ("v4", args.v4_checkpoint)):
            model = load_checkpoint(args.base_model, checkpoint)
            scores[name] = {}
            for split, rows in sets.items():
                scores[name][split] = similarities(model, rows, 4)
                print(name, split, len(rows), flush=True)
            del model
            torch.cuda.empty_cache()
        if args.scores_cache:
            args.scores_cache.parent.mkdir(parents=True, exist_ok=True)
            args.scores_cache.write_text(json.dumps(scores), encoding="utf-8")
    report = {"selection": "Previously fixed validation thresholds; no threshold fitted to test or old 50",
              "thresholds": {"v2": V2, "v4": V4}, "results": {}}
    for combo in (("v2", "v2"), ("v4", "v4"), ("v4", "v2"), ("v2", "v4")):
        label = f"{combo[0]}_coverage__{combo[1]}_off_topic"
        report["results"][label] = {
            split: assess(rows, scores["v2"][split], scores["v4"][split], *combo)
            for split, rows in sets.items()
        }
        print(label, report["results"][label], flush=True)
    label = "v4_coverage__v2_off_topic__v2_covered_consensus"
    report["results"][label] = {
        split: assess(rows, scores["v2"][split], scores["v4"][split], "v4", "v2", True)
        for split, rows in sets.items()
    }
    print(label, report["results"][label], flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
