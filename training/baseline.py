"""Character-gram rule baseline. This is not EmbeddingGemma or a trained model.

Tune thresholds on the validation deck only, then report the held-out synthetic deck.
"""
import json
from collections import Counter, defaultdict
from itertools import product
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LABELS = ("covered", "partial", "missing")


def grams(text: str) -> set[str]:
    compact = "".join(character.lower() for character in text if character.isalnum())
    return {compact[i:i + 2] for i in range(max(0, len(compact) - 1))}


def similarity(left: str, right: str) -> float:
    a, b = grams(left), grams(right)
    return (2 * len(a & b) / (len(a) + len(b))) if a and b else 0.0


def read_rows(name: str) -> list[dict]:
    return [json.loads(line) for line in (ROOT / "splits" / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()]


def context(rows: list[dict]) -> dict[tuple[str, int], set[str]]:
    grouped = defaultdict(set)
    for row in rows:
        grouped[(row["deck_id"], row["source_page"])].add(row["criterion"])
    return grouped


def predict(row: dict, grouped: dict, thresholds: tuple[float, float, float]) -> tuple[str, bool]:
    low, high, off = thresholds
    answer = row["answer"]
    target = max(similarity(answer, row["criterion"]), similarity(answer, row["evidence_quote"]))
    related = max(similarity(answer, item) for item in grouped[(row["deck_id"], row["source_page"])])
    label = "missing" if target < low else "partial" if target < high else "covered"
    return label, related < off


def score(rows: list[dict], thresholds: tuple[float, float, float]) -> dict:
    grouped = context(rows)
    pairs = [(row, *predict(row, grouped, thresholds)) for row in rows]
    per_class = {}
    for label in LABELS:
        tp = sum(row["status"] == label and predicted == label for row, predicted, _ in pairs)
        fp = sum(row["status"] != label and predicted == label for row, predicted, _ in pairs)
        fn = sum(row["status"] == label and predicted != label for row, predicted, _ in pairs)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        per_class[label] = {"precision": round(precision, 3), "recall": round(recall, 3), "f1": round(2 * precision * recall / (precision + recall), 3) if precision + recall else 0.0}
    off_tp = sum(row["off_topic"] and predicted_off for row, _, predicted_off in pairs)
    off_fp = sum(not row["off_topic"] and predicted_off for row, _, predicted_off in pairs)
    off_fn = sum(row["off_topic"] and not predicted_off for row, _, predicted_off in pairs)
    off_p = off_tp / (off_tp + off_fp) if off_tp + off_fp else 0.0
    off_r = off_tp / (off_tp + off_fn) if off_tp + off_fn else 0.0
    false_praise_denominator = sum(row["status"] != "covered" or row["off_topic"] for row, _, _ in pairs)
    false_praise = sum((row["status"] != "covered" or row["off_topic"]) and predicted == "covered" for row, predicted, _ in pairs)
    return {
        "rows": len(rows), "thresholds": {"missing_below": thresholds[0], "covered_from": thresholds[1], "off_topic_below": thresholds[2]},
        "macro_f1": round(sum(item["f1"] for item in per_class.values()) / len(LABELS), 3),
        "per_class": per_class,
        "off_topic_f1": round(2 * off_p * off_r / (off_p + off_r), 3) if off_p + off_r else 0.0,
        "false_praise_rate": round(false_praise / false_praise_denominator, 3) if false_praise_denominator else 0.0,
        "confusion": dict(Counter(f"{row['status']}->{predicted}" for row, predicted, _ in pairs)),
    }


if __name__ == "__main__":
    validation = read_rows("validation")
    candidates = ((low, high, off) for low, high, off in product([i / 20 for i in range(1, 9)], [i / 20 for i in range(5, 16)], [i / 20 for i in range(1, 7)]) if low < high)
    best = max(candidates, key=lambda item: (score(validation, item)["macro_f1"] + score(validation, item)["off_topic_f1"], -score(validation, item)["false_praise_rate"]))
    result = {"method": "character_bigram_rule_baseline", "synthetic_data_only": True,
              "threshold_selection": "validation deck only", "validation": score(validation, best),
              "test_synthetic": score(read_rows("test_synthetic"), best)}
    (ROOT / "baseline_results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
