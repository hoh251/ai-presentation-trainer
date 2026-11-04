"""Choose a low-false-praise calibration on validation, then open new test.

The old 50-case stress suite is diagnostic only and never used for selection.
"""

import argparse
import json
import sys
from pathlib import Path

import torch
from safetensors.torch import load_file
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "training"))

from ablate_anchor_v2 import stress_metrics, stress_rows  # noqa: E402
from train_embeddinggemma import (binary_f1, false_praise_rate, macro_f1, metrics,
                                  read_augmented_split, read_diverse_split, similarities)  # noqa: E402


def candidates(scores: list[float]) -> list[float]:
    unique = sorted(set(scores))
    return [unique[0] - 0.001] + [(a + b) / 2 for a, b in zip(unique, unique[1:])] + [unique[-1] + 0.001]


def constrained_thresholds(rows: list[dict], scores: list[float], max_false_praise: float) -> tuple[float, float, float]:
    values = candidates(scores)
    best = None
    for low in values:
        for high in values:
            if low >= high:
                continue
            labels = ["missing" if score < low else "partial" if score < high else "covered" for score in scores]
            wrong_covered = false_praise_rate(rows, labels)
            if wrong_covered > max_false_praise:
                continue
            key = (macro_f1(rows, labels), -wrong_covered)
            if best is None or key > best[0]:
                best = (key, low, high)
    if best is None:
        raise RuntimeError("No calibration meets false-praise cap")
    actual_off = [bool(row["off_topic"]) for row in rows]
    off = max(values, key=lambda value: (binary_f1(actual_off, [s < value for s in scores]),
                                         -sum(s < value for s in scores)))
    return best[1], best[2], off


def load_checkpoint(base_path: Path, path: Path) -> SentenceTransformer:
    model = SentenceTransformer(str(base_path), device="cuda", model_kwargs={"torch_dtype": torch.bfloat16})
    model.max_seq_length = 512
    model.load_adapter(str(path))
    for index, dirname in ((2, "2_Dense"), (3, "3_Dense")):
        model[index].load_state_dict(load_file(str(path / dirname / "model.safetensors")))
    model.eval()
    return model


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-model", required=True, type=Path)
    parser.add_argument("--v2-checkpoint", required=True, type=Path)
    parser.add_argument("--v3-checkpoint", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--max-false-praise", type=float, default=0.03)
    args = parser.parse_args()
    validation = read_augmented_split("validation", include_hard=True) + read_diverse_split("validation")
    print("validation rows", len(validation), flush=True)
    paths = {"v2": args.v2_checkpoint, "v3_diverse": args.v3_checkpoint}
    result = {"selection": "validation macro F1 subject to false-praise cap",
              "max_validation_false_praise": args.max_false_praise,
              "validation_decks": sorted({row["deck_id"] for row in validation}),
              "stress_50_used_for_selection": False, "candidates": {}}
    for name, path in paths.items():
        model = load_checkpoint(args.base_model, path)
        values = similarities(model, validation, 4)
        threshold = constrained_thresholds(validation, values, args.max_false_praise)
        result["candidates"][name] = {"thresholds": [round(v, 5) for v in threshold],
                                       "validation": metrics(validation, values, threshold)}
        del model
        torch.cuda.empty_cache()
        print(name, "validation", result["candidates"][name], flush=True)
    selected = max(result["candidates"], key=lambda name: result["candidates"][name]["validation"]["macro_f1"])
    result["selected_by_validation"] = selected
    print("selected", selected, "opening held-out tests", flush=True)

    test = read_augmented_split("test_synthetic") + read_diverse_split("test")
    stress = stress_rows(ROOT / "training" / "robustness_50.json")
    result["test_decks"] = sorted({row["deck_id"] for row in test})
    for name, path in paths.items():
        model = load_checkpoint(args.base_model, path)
        threshold = tuple(result["candidates"][name]["thresholds"])
        result["candidates"][name]["new_test"] = metrics(test, similarities(model, test, 4), threshold)
        result["candidates"][name]["stress_50_diagnostic"] = stress_metrics(
            stress, similarities(model, stress, 4), threshold)
        del model
        torch.cuda.empty_cache()
        print(name, "test", result["candidates"][name]["new_test"],
              "stress", result["candidates"][name]["stress_50_diagnostic"], flush=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
