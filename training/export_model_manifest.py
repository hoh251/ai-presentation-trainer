"""Publish small, non-private model metadata; keep weights and local paths outside Git."""

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment-dir", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--public-results", required=True, type=Path)
    args = parser.parse_args()
    report = json.loads((args.experiment_dir / "experiment_results.json").read_text(encoding="utf-8"))
    checkpoint = args.experiment_dir / "checkpoint"
    manifest = {
        "contract_version": 1,
        "model_version": "embeddinggemma-coverage-lora-v1",
        "base_model": "google/embeddinggemma-300m",
        "fine_tuned": True,
        "checkpoint_sha256": sha256(checkpoint / "adapter_model.safetensors"),
        "dense_sha256": {name: sha256(checkpoint / name / "model.safetensors") for name in ("2_Dense", "3_Dense")},
        "max_input_tokens": 512,
        "training_max_length_tokens": report["max_length_tokens"],
        "validation_thresholds": report["finetuned"]["validation_thresholds"],
        "torch_dtype": "bfloat16 on supported CUDA, float32 on CPU",
        "checkpoint_distribution": "external; never committed to the public repository",
    }
    public_report = {key: value for key, value in report.items() if key != "checkpoint_path"}
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.public_results.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.public_results.write_text(json.dumps(public_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
