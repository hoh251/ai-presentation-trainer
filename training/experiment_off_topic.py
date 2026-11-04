"""Compare a separate off-topic head against the shared cosine threshold.

Train on train decks and select threshold on the validation deck. Never read test.
"""

import argparse
import json
import math
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from sentence_transformers import SentenceTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from baseline import similarity as lexical_similarity
from train_embeddinggemma import binary_f1, encode_texts, passages, read_augmented_split


def features(model: SentenceTransformer, rows: list[dict]) -> np.ndarray:
    pairs = [passages(row) for row in rows]
    anchor = encode_texts(model, [pair[0] for pair in pairs], 8)
    answer = encode_texts(model, [pair[1] for pair in pairs], 8)
    prompts = encode_texts(model, [f"task: sentence similarity | query: {row['current_prompt']}" for row in rows], 8)
    criteria = encode_texts(model, [f"task: sentence similarity | query: {row['criterion']}" for row in rows], 8)
    numeric = np.array([
        [float(F.cosine_similarity(anchor[i:i+1], answer[i:i+1])[0]),
         float(F.cosine_similarity(prompts[i:i+1], answer[i:i+1])[0]),
         float(F.cosine_similarity(criteria[i:i+1], answer[i:i+1])[0]),
         math.log1p(len(row["answer"])),
         lexical_similarity(row["answer"], row["criterion"])]
        for i, row in enumerate(rows)
    ], dtype=np.float32)
    return numeric


def best_threshold(actual: list[bool], probabilities: np.ndarray) -> tuple[float, float, int]:
    candidates = sorted(set([0.0, 0.5, 1.0] + probabilities.tolist()))
    best = None
    for threshold in candidates:
        pred = [p >= threshold for p in probabilities]
        f1 = binary_f1(actual, pred)
        fp = sum(not a and p for a, p in zip(actual, pred))
        key = (f1, -fp)
        if best is None or key > best[0]:
            best = (key, threshold, f1, fp)
    return best[1], best[2], best[3]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    model = SentenceTransformer(str(args.checkpoint), device="cuda", model_kwargs={"torch_dtype": torch.bfloat16})
    model.max_seq_length = 512
    train = read_augmented_split("train", include_hard=True)
    validation = read_augmented_split("validation", include_hard=True)
    train_x, val_x = features(model, train), features(model, validation)
    train_y = np.array([int(r["off_topic"]) for r in train])
    val_y = [bool(r["off_topic"]) for r in validation]
    variants = {}
    for regularization in (0.03, 0.3, 3.0):
        clf = make_pipeline(StandardScaler(), LogisticRegression(C=regularization, class_weight="balanced", max_iter=500))
        clf.fit(train_x, train_y)
        probabilities = clf.predict_proba(val_x)[:, 1]
        threshold, f1, fp = best_threshold(val_y, probabilities)
        variants[str(regularization)] = {"validation_f1": round(float(f1), 3),
                                          "validation_false_positives": int(fp),
                                          "threshold": round(float(threshold), 5)}
    report = {"train_rows": len(train), "validation_rows": len(validation),
              "features": ["anchor_answer_cosine", "prompt_answer_cosine", "criterion_answer_cosine", "log_answer_length", "character_bigram_overlap"],
              "variants": variants}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
