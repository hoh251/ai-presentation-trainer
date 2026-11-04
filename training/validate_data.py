"""Check annotation shape and obvious contradictions before training."""
import json
from collections import Counter
from pathlib import Path

REQUIRED = {"deck_id", "question", "current_prompt", "criterion_id", "criterion", "answer", "status", "off_topic"}
STATUSES = {"covered", "partial", "missing"}


def validate(path: Path) -> Counter:
    counts: Counter = Counter()
    seen = set()
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        item = json.loads(line)
        missing = REQUIRED - item.keys()
        if missing:
            raise ValueError(f"line {number}: missing {sorted(missing)}")
        if item["status"] not in STATUSES or not isinstance(item["off_topic"], bool):
            raise ValueError(f"line {number}: invalid label")
        if any(not isinstance(item[key], str) or not item[key].strip() for key in REQUIRED - {"off_topic"}):
            raise ValueError(f"line {number}: empty text field")
        if item["off_topic"] and item["status"] == "covered":
            raise ValueError(f"line {number}: off-topic and covered conflict")
        identity = tuple(item[key] for key in ("deck_id", "question", "current_prompt", "criterion_id", "answer"))
        if identity in seen:
            raise ValueError(f"line {number}: duplicate example")
        seen.add(identity)
        counts[item["status"]] += 1
        counts["off_topic_true" if item["off_topic"] else "off_topic_false"] += 1
        counts[f"deck:{item['deck_id']}"] += 1
    if not seen:
        raise ValueError("dataset is empty")
    return counts


if __name__ == "__main__":
    result = validate(Path(__file__).with_name("seed.jsonl"))
    print(f"Seed annotation format OK: {sum(result[key] for key in STATUSES)} rows, {sum(key.startswith('deck:') for key in result)} deck")
    print(dict(result))
