import json
import unittest
from pathlib import Path
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent


class TrainingDataChecks(unittest.TestCase):
    def test_synthetic_evidence_is_extractable(self):
        rows = [json.loads(line) for line in (ROOT / "synthetic_examples.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(rows), 128)
        decks = {deck_id: PdfReader(ROOT / "synthetic_decks" / f"{deck_id}.pdf") for deck_id in {row["deck_id"] for row in rows}}
        self.assertEqual(len(decks), 4)
        for deck in decks.values():
            self.assertEqual(len(deck.pages), 4)
        for row in rows:
            page = decks[row["deck_id"]].pages[row["source_page"] - 1]
            self.assertIn(row["evidence_quote"], page.extract_text())

    def test_no_deck_crosses_splits(self):
        deck_groups = []
        for name in ("train", "validation", "test_synthetic"):
            rows = [json.loads(line) for line in (ROOT / "splits" / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertTrue(rows)
            deck_groups.append({row["deck_id"] for row in rows})
        for index, group in enumerate(deck_groups):
            for other in deck_groups[index + 1:]:
                self.assertFalse(group & other)

    def test_hard_cases_do_not_touch_test_deck(self):
        rows = [json.loads(line) for line in (ROOT / "hard_cases.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(rows), 42)
        self.assertEqual({row["deck_id"] for row in rows},
                         {"cats_demo", "phishing", "urban_garden", "waste_sorting"})
        self.assertTrue(all(row["status"] in {"covered", "partial", "missing"} and
                            row["off_topic"] is False for row in rows))

    def test_diverse_splits_have_no_topic_or_off_topic_answer_leakage(self):
        groups = []
        for name, expected_count in (("train", 176), ("validation", 44), ("test", 44)):
            rows = [json.loads(line) for line in (ROOT / f"diverse_{name}.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(rows), expected_count)
            groups.append(({row["deck_id"] for row in rows},
                           {row["answer"] for row in rows if row["off_topic"]}))
        for index, (decks, off_answers) in enumerate(groups):
            for other_decks, other_off_answers in groups[index + 1:]:
                self.assertFalse(decks & other_decks)
                self.assertFalse(off_answers & other_off_answers)
        stress_topics = set(json.loads((ROOT / "robustness_50.json").read_text(encoding="utf-8"))["topics"])
        self.assertFalse(stress_topics & {deck.removeprefix("diverse_") for group, _ in groups for deck in group})


if __name__ == "__main__":
    unittest.main()
