"""Create deterministic deck-level splits for pipeline development.

These synthetic splits check implementation. They are not a claim of real-world accuracy.
"""
import json
from pathlib import Path
from validate_data import validate

ROOT = Path(__file__).resolve().parent
SPLITS = {
    "train": {"cats_demo", "phishing", "urban_garden"},
    "validation": {"waste_sorting"},
    "test_synthetic": {"bike_care"},
}

if __name__ == "__main__":
    sources = [ROOT / "seed.jsonl", ROOT / "synthetic_examples.jsonl"]
    rows = [json.loads(line) for source in sources for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
    all_decks = {row["deck_id"] for row in rows}
    assigned = set().union(*SPLITS.values())
    if all_decks != assigned or sum(len(group) for group in SPLITS.values()) != len(assigned):
        raise ValueError(f"Deck split mismatch: data={all_decks}, assigned={assigned}")
    output = ROOT / "splits"
    output.mkdir(exist_ok=True)
    for name, decks in SPLITS.items():
        selected = [row for row in rows if row["deck_id"] in decks]
        target = output / f"{name}.jsonl"
        target.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in selected) + "\n", encoding="utf-8")
        counts = validate(target)
        print(name, len(selected), "rows", sorted(decks), {label: counts[label] for label in ("covered", "partial", "missing", "off_topic_true")})
