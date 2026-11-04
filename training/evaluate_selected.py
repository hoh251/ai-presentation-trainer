"""Open the fixed synthetic test once for a selected, frozen checkpoint."""

import argparse
import json
from pathlib import Path

import torch
from sentence_transformers import SentenceTransformer

from train_embeddinggemma import load_model, metrics, read_augmented_split, similarities


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-model", required=True, type=Path)
    parser.add_argument("--experiment-dir", required=True, type=Path)
    args = parser.parse_args()
    path = args.experiment_dir / "experiment_results.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    if report.get("test_rows"):
        raise SystemExit("This checkpoint has already been evaluated on the held-out test")
    rows = read_augmented_split("test_synthetic")
    tuned = SentenceTransformer(str(args.experiment_dir / "checkpoint"), device="cuda",
                                model_kwargs={"torch_dtype": torch.bfloat16})
    tuned.max_seq_length = 512
    tuned_scores = similarities(tuned, rows, 4)
    del tuned
    torch.cuda.empty_cache()
    base = load_model(args.base_model, 512)
    base_scores = similarities(base, rows, 4)
    report["test_rows"] = len(rows)
    report["stress_answer_rows"]["test"] = sum(bool(row.get("edge_case")) for row in rows)
    report["base"]["test_synthetic"] = metrics(rows, base_scores, tuple(report["base"]["validation_thresholds"]))
    report["finetuned"]["test_synthetic"] = metrics(rows, tuned_scores, tuple(report["finetuned"]["validation_thresholds"]))
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"test_rows": len(rows), "base": report["base"]["test_synthetic"],
                      "finetuned": report["finetuned"]["test_synthetic"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
