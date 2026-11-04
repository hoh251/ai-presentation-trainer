"""Predefined weight averages of two LoRA runs with the same initialization.

Choose by validation coverage with an off-topic and false-praise safety gate.
The stress set and synthetic test are diagnostic after selection only.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

import torch
from safetensors.torch import load_file, save_file

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "training"))

from ablate_anchor_v2 import stress_metrics, stress_rows  # noqa: E402
from compare_diverse_checkpoints import constrained_thresholds, load_checkpoint  # noqa: E402
from train_embeddinggemma import metrics, read_augmented_split, read_diverse_split, similarities  # noqa: E402

WEIGHT_FILES = ("adapter_model.safetensors", "2_Dense/model.safetensors", "3_Dense/model.safetensors")
ALPHAS = (0.25, 0.5, 0.75)


def blend(v2: Path, v3: Path, target: Path, alpha: float) -> None:
    shutil.copytree(v2, target, dirs_exist_ok=True)
    first_config = json.loads((v2 / "adapter_config.json").read_text(encoding="utf-8"))
    second_config = json.loads((v3 / "adapter_config.json").read_text(encoding="utf-8"))
    first_config.pop("base_model_name_or_path", None)
    second_config.pop("base_model_name_or_path", None)
    if first_config != second_config:
        raise ValueError("Adapters have different configurations")
    for name in WEIGHT_FILES:
        first, second = load_file(str(v2 / name)), load_file(str(v3 / name))
        if set(first) != set(second) or any(first[k].shape != second[k].shape for k in first):
            raise ValueError(f"Incompatible weights: {name}")
        mixed = {key: ((1 - alpha) * first[key].float() + alpha * second[key].float()).to(first[key].dtype).contiguous()
                 for key in first}
        save_file(mixed, str(target / name))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-model", required=True, type=Path)
    parser.add_argument("--v2-checkpoint", required=True, type=Path)
    parser.add_argument("--v3-checkpoint", required=True, type=Path)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--baseline-comparison", required=True, type=Path)
    args = parser.parse_args()
    args.work_dir.mkdir(parents=True, exist_ok=True)
    validation = read_augmented_split("validation", include_hard=True) + read_diverse_split("validation")
    baseline = json.loads(args.baseline_comparison.read_text(encoding="utf-8"))
    base_off_topic_f1 = baseline["candidates"]["v2"]["validation"]["off_topic_f1"]
    report = {"method": "linear average of same-seed LoRA factors and Dense heads",
              "alphas_predefined": list(ALPHAS), "selection_data": "validation decks only",
              "baseline_v2_off_topic_f1": base_off_topic_f1,
              "min_validation_off_topic_f1": round(base_off_topic_f1 - 0.01, 3),
              "max_validation_false_praise": 0.03, "candidates": {}}
    for alpha in ALPHAS:
        name = f"soup_{int(alpha * 100)}"
        path = args.work_dir / name / "checkpoint"
        blend(args.v2_checkpoint, args.v3_checkpoint, path, alpha)
        model = load_checkpoint(args.base_model, path)
        values = similarities(model, validation, 4)
        threshold = constrained_thresholds(validation, values, 0.03)
        measured = metrics(validation, values, threshold)
        report["candidates"][name] = {"alpha": alpha, "thresholds": [round(x, 5) for x in threshold],
                                       "validation": measured}
        del model
        torch.cuda.empty_cache()
        print(name, measured["macro_f1"], measured["off_topic_f1"], measured["false_praise_rate"], flush=True)
    eligible = [(name, data) for name, data in report["candidates"].items()
                if data["validation"]["off_topic_f1"] >= base_off_topic_f1 - 0.01]
    if not eligible:
        report["selected_by_validation"] = "v2"
    else:
        selected, data = max(eligible, key=lambda item: item[1]["validation"]["macro_f1"])
        report["selected_by_validation"] = selected if data["validation"]["macro_f1"] > baseline["candidates"]["v2"]["validation"]["macro_f1"] else "v2"
    print("selected_by_validation", report["selected_by_validation"], flush=True)
    if report["selected_by_validation"] != "v2":
        selected = report["selected_by_validation"]
        model = load_checkpoint(args.base_model, args.work_dir / selected / "checkpoint")
        threshold = tuple(report["candidates"][selected]["thresholds"])
        test = read_augmented_split("test_synthetic") + read_diverse_split("test")
        stress = stress_rows(ROOT / "training" / "robustness_50.json")
        report["candidates"][selected]["test_diagnostic"] = metrics(test, similarities(model, test, 4), threshold)
        report["candidates"][selected]["stress_50_diagnostic"] = stress_metrics(stress, similarities(model, stress, 4), threshold)
        print("test", report["candidates"][selected]["test_diagnostic"], flush=True)
        print("stress", report["candidates"][selected]["stress_50_diagnostic"], flush=True)
    (args.work_dir / "soup_experiment.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
