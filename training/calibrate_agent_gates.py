"""Select conservative Agent confidence gates from existing validation topics only.

This is a development calibration for the PR #3 integration. It does not
modify the coverage model's class thresholds and never reads unseen-slide tests.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from model_package import configure_model  # noqa: E402


def rows(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-model", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    validation = rows(ROOT / "training/splits/validation.jsonl")
    validation_decks = {row["deck_id"] for row in validation}
    for name in ("edge_cases.jsonl", "hard_cases.jsonl"):
        validation.extend(row for row in rows(ROOT / "training" / name) if row["deck_id"] in validation_decks)
    validation += rows(ROOT / "training/diverse_validation.jsonl")
    model = configure_model(args.base_model, args.checkpoint, str(ROOT / "model_package/manifest.json"))
    predictions = []
    for row in validation:
        result = model.predict_attempt(
            {"text": row["question"]}, row.get("current_prompt") or row["question"],
            [{"id": row["criterion_id"], "text": row["criterion"], "evidence_quote": row["evidence_quote"]}],
            row["answer"],
        )
        predictions.append({"gold": row["status"], "gold_off_topic": bool(row["off_topic"]),
                            "pred": result["criteria"][0]["status"],
                            "coverage_confidence": result["criteria"][0]["confidence"],
                            "off_topic": result["off_topic"]["value"],
                            "off_confidence": result["off_topic"]["confidence"]})
    candidates = [round(i / 100, 2) for i in range(1, 51)]
    scored = []
    for coverage_gate in candidates:
        for off_gate in candidates:
            accepted = [p for p in predictions if not p["off_topic"] and
                        p["coverage_confidence"] >= coverage_gate and p["off_confidence"] >= off_gate]
            false_complete = sum(p["pred"] == "covered" and p["gold"] != "covered" for p in accepted)
            true_complete = sum(p["pred"] == "covered" and p["gold"] == "covered" for p in accepted)
            scored.append((false_complete, -true_complete, len(predictions) - len(accepted), coverage_gate, off_gate))
    selected = min(scored)
    false_complete, neg_true_complete, clarifications, coverage_gate, off_gate = selected
    result = {"coverage": coverage_gate, "off_topic": off_gate,
              "calibration": {"rows": len(validation), "false_complete": false_complete,
                              "true_complete": -neg_true_complete, "clarifications": clarifications,
                              "selection": "minimize false complete, maximize true complete, then minimize clarifications",
                              "note": "Synthetic validation only; not a deployed quality guarantee"}}
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
