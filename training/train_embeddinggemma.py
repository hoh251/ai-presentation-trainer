"""Fine-tune EmbeddingGemma with LoRA on deck-separated synthetic labels.

This is an experimental coverage scorer, not a production accuracy claim.
The held-out test deck is read only after training and validation calibration.
"""

import argparse
import json
import random
from collections import Counter
from pathlib import Path

import torch
import torch.nn.functional as F
from peft import LoraConfig
from sentence_transformers import SentenceTransformer

from baseline import LABELS, read_rows

ROOT = Path(__file__).resolve().parent
TARGET = {"covered": 0.95, "partial": 0.60, "missing": 0.15}


def passages(row: dict) -> tuple[str, str]:
    prompt = row.get("current_prompt") or row["question"]
    evidence = row.get("evidence_quote") or row["criterion"]
    anchor = f"task: sentence similarity | query: คำถาม: {prompt} เกณฑ์: {row['criterion']} หลักฐาน: {evidence}"
    answer = f"task: sentence similarity | query: คำตอบ: {row['answer']}"
    return anchor, answer


def read_augmented_split(name: str, include_hard: bool = False) -> list[dict]:
    rows = read_rows(name)
    deck_ids = {row["deck_id"] for row in rows}
    edge_path = ROOT / "edge_cases.jsonl"
    if edge_path.exists():
        edges = [json.loads(line) for line in edge_path.read_text(encoding="utf-8").splitlines()]
        rows.extend(row for row in edges if row["deck_id"] in deck_ids)
    if include_hard:
        hard_path = ROOT / "hard_cases.jsonl"
        if hard_path.exists():
            hard = [json.loads(line) for line in hard_path.read_text(encoding="utf-8").splitlines()]
            rows.extend(row for row in hard if row["deck_id"] in deck_ids)
    return rows


def load_model(model_path: Path, max_length: int) -> SentenceTransformer:
    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
        raise RuntimeError("This training run requires a CUDA GPU with bfloat16 support")
    model = SentenceTransformer(str(model_path), device="cuda", model_kwargs={"torch_dtype": torch.bfloat16})
    model.max_seq_length = max_length
    return model


def encode_texts(model: SentenceTransformer, texts: list[str], batch_size: int) -> torch.Tensor:
    model.eval()
    with torch.no_grad():
        result = model.encode(texts, batch_size=batch_size, convert_to_tensor=True, show_progress_bar=False)
    if not torch.isfinite(result).all():
        raise RuntimeError("Model produced non-finite embeddings")
    return result.float()


def similarities(model: SentenceTransformer, rows: list[dict], batch_size: int) -> list[float]:
    pairs = [passages(row) for row in rows]
    anchors = encode_texts(model, [pair[0] for pair in pairs], batch_size)
    answers = encode_texts(model, [pair[1] for pair in pairs], batch_size)
    return F.cosine_similarity(anchors, answers).cpu().tolist()


def thresholds_from_validation(rows: list[dict], scores: list[float]) -> tuple[float, float, float]:
    unique = sorted(set(scores))
    candidates = [unique[0] - 0.001] + [(a + b) / 2 for a, b in zip(unique, unique[1:])] + [unique[-1] + 0.001]
    # All thresholds are selected using validation data only.
    best = None
    for low in candidates:
        for high in candidates:
            if low >= high:
                continue
            labels = ["missing" if s < low else "partial" if s < high else "covered" for s in scores]
            f1 = macro_f1(rows, labels)
            false_praise = false_praise_rate(rows, labels)
            key = (f1, -false_praise)
            if best is None or key > best[0]:
                best = (key, low, high)
    off_best = None
    for off in candidates:
        predicted = [s < off for s in scores]
        f1 = binary_f1([bool(row["off_topic"]) for row in rows], predicted)
        key = (f1, -sum(predicted))
        if off_best is None or key > off_best[0]:
            off_best = (key, off)
    return best[1], best[2], off_best[1]


def binary_f1(actual: list[bool], predicted: list[bool]) -> float:
    tp = sum(a and p for a, p in zip(actual, predicted))
    fp = sum(not a and p for a, p in zip(actual, predicted))
    fn = sum(a and not p for a, p in zip(actual, predicted))
    return 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0


def macro_f1(rows: list[dict], predicted: list[str]) -> float:
    return sum(binary_f1([r["status"] == label for r in rows], [p == label for p in predicted]) for label in LABELS) / len(LABELS)


def false_praise_rate(rows: list[dict], predicted: list[str]) -> float:
    bad = [(r, p) for r, p in zip(rows, predicted) if r["status"] != "covered" or r["off_topic"]]
    return sum(p == "covered" for _, p in bad) / len(bad) if bad else 0.0


def metrics(rows: list[dict], scores: list[float], thresholds: tuple[float, float, float]) -> dict:
    low, high, off = thresholds
    predicted = ["missing" if s < low else "partial" if s < high else "covered" for s in scores]
    predicted_off = [s < off for s in scores]
    per_class = {}
    for label in LABELS:
        actual = [r["status"] == label for r in rows]
        pred = [p == label for p in predicted]
        tp = sum(a and p for a, p in zip(actual, pred))
        fp = sum(not a and p for a, p in zip(actual, pred))
        fn = sum(a and not p for a, p in zip(actual, pred))
        per_class[label] = {"precision": round(tp / (tp + fp), 3) if tp + fp else 0.0,
                            "recall": round(tp / (tp + fn), 3) if tp + fn else 0.0,
                            "f1": round(binary_f1(actual, pred), 3)}
    return {"rows": len(rows), "macro_f1": round(macro_f1(rows, predicted), 3),
            "per_class": per_class,
            "off_topic_f1": round(binary_f1([bool(r["off_topic"]) for r in rows], predicted_off), 3),
            "false_praise_rate": round(false_praise_rate(rows, predicted), 3),
            "confusion": dict(Counter(f"{r['status']}->{p}" for r, p in zip(rows, predicted)))}


def make_triplets(rows: list[dict]) -> list[tuple[str, str, str]]:
    groups = {}
    for row in rows:
        if row["off_topic"]:
            continue
        key = (row["deck_id"], row["criterion_id"])
        group = groups.setdefault(key, {"covered": [], "missing": []})
        if row["status"] in group:
            group[row["status"]].append(row)
    triplets = []
    for group in groups.values():
        if not group["covered"] or not group["missing"]:
            continue
        positive = group["covered"][0]
        anchor, good = passages(positive)
        for negative in group["missing"][:3]:
            triplets.append((anchor, good, passages(negative)[1]))
    return triplets


def train(model: SentenceTransformer, rows: list[dict], epochs: int, batch_size: int,
          learning_rate: float, ranking_weight: float = 0.0, ranking_margin: float = 0.15) -> list[float]:
    model.add_adapter(LoraConfig(r=4, lora_alpha=8, target_modules=["q_proj", "v_proj"], lora_dropout=0.05))
    optimizer = torch.optim.AdamW((p for p in model.parameters() if p.requires_grad), lr=learning_rate)
    triplets = make_triplets(rows) if ranking_weight else []
    print(f"ranking_triplets={len(triplets)} weight={ranking_weight}", flush=True)
    losses = []
    for epoch in range(epochs):
        order = list(rows)
        random.Random(2026 + epoch).shuffle(order)
        model.train()
        total = 0.0
        for start in range(0, len(order), batch_size):
            batch = order[start:start + batch_size]
            pairs = [passages(row) for row in batch]
            texts = [p[0] for p in pairs] + [p[1] for p in pairs]
            # Keep the text preprocessing and pooling identical for training and inference.
            features = model.tokenize(texts)
            features = {key: value.to("cuda") if isinstance(value, torch.Tensor) else value for key, value in features.items()}
            embeddings = model(features)["sentence_embedding"].float()
            scores = F.cosine_similarity(embeddings[:len(batch)], embeddings[len(batch):])
            targets = torch.tensor([TARGET[row["status"]] for row in batch], device="cuda")
            loss = F.mse_loss(scores, targets)
            if not torch.isfinite(loss):
                raise RuntimeError(f"Non-finite loss at epoch {epoch + 1}, batch {start // batch_size + 1}")
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_((p for p in model.parameters() if p.requires_grad), max_norm=1.0)
            optimizer.step()
            total += float(loss.detach()) * len(batch)
        if triplets:
            ranking_order = list(triplets)
            random.Random(5026 + epoch).shuffle(ranking_order)
            for start in range(0, len(ranking_order), batch_size):
                batch = ranking_order[start:start + batch_size]
                texts = ([item[0] for item in batch] + [item[1] for item in batch]
                         + [item[2] for item in batch])
                features = model.tokenize(texts)
                features = {key: value.to("cuda") if isinstance(value, torch.Tensor) else value
                            for key, value in features.items()}
                emb = model(features)["sentence_embedding"].float()
                size = len(batch)
                positive = F.cosine_similarity(emb[:size], emb[size:2 * size])
                negative = F.cosine_similarity(emb[:size], emb[2 * size:])
                rank_loss = F.relu(ranking_margin + negative - positive).mean() * ranking_weight
                if not torch.isfinite(rank_loss):
                    raise RuntimeError("Non-finite ranking loss")
                optimizer.zero_grad(set_to_none=True)
                rank_loss.backward()
                torch.nn.utils.clip_grad_norm_((p for p in model.parameters() if p.requires_grad), max_norm=1.0)
                optimizer.step()
        average = total / len(rows)
        losses.append(round(average, 5))
        print(f"epoch={epoch + 1} loss={average:.5f} peak_vram_mb={round(torch.cuda.max_memory_allocated() / 1048576)}", flush=True)
    return losses


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--max-length", type=int, default=512)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--include-hard", action="store_true")
    parser.add_argument("--ranking-weight", type=float, default=0.0)
    parser.add_argument("--ranking-margin", type=float, default=0.15)
    parser.add_argument("--validation-only", action="store_true")
    args = parser.parse_args()
    if args.epochs < 1 or args.batch_size < 1 or args.max_length < 32:
        parser.error("epochs and batch-size must be positive, max-length at least 32")
    torch.manual_seed(2026)
    torch.cuda.manual_seed_all(2026)
    train_rows = read_augmented_split("train", include_hard=args.include_hard)
    validation = read_augmented_split("validation", include_hard=args.include_hard)
    model = load_model(args.model_path, args.max_length)
    print("base_validation_embedding", flush=True)
    base_validation = similarities(model, validation, args.batch_size)
    base_thresholds = thresholds_from_validation(validation, base_validation)
    base_val_metrics = metrics(validation, base_validation, base_thresholds)
    print("training_lora", flush=True)
    losses = train(model, train_rows, args.epochs, args.batch_size, args.learning_rate,
                   args.ranking_weight, args.ranking_margin)
    tuned_validation = similarities(model, validation, args.batch_size)
    tuned_thresholds = thresholds_from_validation(validation, tuned_validation)
    tuned_val_metrics = metrics(validation, tuned_validation, tuned_thresholds)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(args.output_dir / "checkpoint"))
    report = {
        "model": "google/embeddinggemma-300m", "method": "LoRA q_proj/v_proj + cosine MSE + optional ranking",
        "synthetic_data_only": True, "split_by_deck": True,
        "train_rows": len(train_rows), "validation_rows": len(validation), "test_rows": 0,
        "stress_answer_rows": {"train": sum("edge_case" in row for row in train_rows),
                               "validation": sum("edge_case" in row for row in validation),
                               "test": 0},
        "hard_answer_rows": {"train": sum("hard_case" in row for row in train_rows),
                             "validation": sum("hard_case" in row for row in validation)},
        "epochs": args.epochs, "batch_size": args.batch_size, "max_length_tokens": args.max_length,
        "learning_rate": args.learning_rate, "ranking_weight": args.ranking_weight,
        "ranking_margin": args.ranking_margin, "ranking_triplets": len(make_triplets(train_rows)),
        "train_loss_by_epoch": losses,
        "base": {"validation_thresholds": [round(x, 5) for x in base_thresholds],
                 "validation": base_val_metrics},
        "finetuned": {"validation_thresholds": [round(x, 5) for x in tuned_thresholds],
                      "validation": tuned_val_metrics},
        "checkpoint_path": str(args.output_dir / "checkpoint"),
    }
    if not args.validation_only:
        # Only the chosen model should be run without --validation-only.
        test_rows = read_augmented_split("test_synthetic")
        tuned_test = similarities(model, test_rows, args.batch_size)
        del model
        torch.cuda.empty_cache()
        base_model = load_model(args.model_path, args.max_length)
        base_test = similarities(base_model, test_rows, args.batch_size)
        report["test_rows"] = len(test_rows)
        report["stress_answer_rows"]["test"] = sum("edge_case" in row for row in test_rows)
        report["base"]["test_synthetic"] = metrics(test_rows, base_test, base_thresholds)
        report["finetuned"]["test_synthetic"] = metrics(test_rows, tuned_test, tuned_thresholds)
    result_path = args.output_dir / "experiment_results.json"
    result_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"result_path": str(result_path),
                      "validation": report["finetuned"]["validation"],
                      "test": report["finetuned"].get("test_synthetic")}), flush=True)


if __name__ == "__main__":
    main()
