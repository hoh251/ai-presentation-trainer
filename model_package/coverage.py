"""Backend-independent EmbeddingGemma coverage inference.

The LoRA checkpoint is kept outside Git. Set base/checkpoint paths when starting
the Backend, then instantiate one CoverageModel and reuse it across requests.
"""

import hashlib
import json
from pathlib import Path

import torch
import torch.nn.functional as F
from safetensors.torch import load_file
from sentence_transformers import SentenceTransformer

MODEL_VERSION = "embeddinggemma-coverage-lora-v1"
MAX_INPUT_TOKENS = 512


class ModelInputTooLong(ValueError):
    """The model tokenizer counted more than 512 tokens in an input pair."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _anchor(prompt: str, criterion: dict) -> str:
    evidence = criterion.get("evidence_quote") or criterion["text"]
    return (f"task: sentence similarity | query: คำถาม: {prompt} "
            f"เกณฑ์: {criterion['text']} หลักฐาน: {evidence}")


class CoverageModel:
    def __init__(self, base_model_path: str | Path, checkpoint_dir: str | Path,
                 manifest_path: str | Path, device: str | None = None):
        self.checkpoint_dir = Path(checkpoint_dir)
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        if manifest["contract_version"] != 1 or manifest["model_version"] != MODEL_VERSION:
            raise ValueError("Unsupported model manifest")
        if manifest["max_input_tokens"] != MAX_INPUT_TOKENS:
            raise ValueError("Model token limit differs from contract v1")
        adapter = self.checkpoint_dir / "adapter_model.safetensors"
        if _sha256(adapter) != manifest["checkpoint_sha256"]:
            raise ValueError("LoRA checkpoint SHA-256 does not match manifest")
        for dirname, expected in manifest["dense_sha256"].items():
            if _sha256(self.checkpoint_dir / dirname / "model.safetensors") != expected:
                raise ValueError(f"{dirname} SHA-256 does not match manifest")
        self.thresholds = tuple(manifest["validation_thresholds"])
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        dtype = torch.bfloat16 if self.device == "cuda" and torch.cuda.is_bf16_supported() else torch.float32
        self.model = SentenceTransformer(str(base_model_path), device=self.device,
                                         model_kwargs={"torch_dtype": dtype})
        self.model.max_seq_length = MAX_INPUT_TOKENS
        self.model.load_adapter(str(self.checkpoint_dir))
        for index, dirname in ((2, "2_Dense"), (3, "3_Dense")):
            self.model[index].load_state_dict(load_file(str(self.checkpoint_dir / dirname / "model.safetensors")))
        self.model.eval()

    def validate_attempt(self, question: dict, current_prompt: str,
                         criteria: list[dict], answer: str) -> None:
        if not question.get("text") or not current_prompt or not answer or not 1 <= len(criteria) <= 3:
            raise ValueError("Question, prompt, answer and 1-3 criteria are required")
        for criterion in criteria:
            if not criterion.get("id") or not criterion.get("text"):
                raise ValueError("Each criterion needs id and text")
            for text in (_anchor(current_prompt, criterion),
                         f"task: sentence similarity | query: คำตอบ: {answer}"):
                tokens = self.model.tokenizer(text, add_special_tokens=True, truncation=False)["input_ids"]
                if len(tokens) > MAX_INPUT_TOKENS:
                    raise ModelInputTooLong(f"Input has {len(tokens)} tokens; maximum is {MAX_INPUT_TOKENS}")

    def predict_attempt(self, question: dict, current_prompt: str,
                        criteria: list[dict], answer: str) -> dict:
        self.validate_attempt(question, current_prompt, criteria, answer)
        anchors = [_anchor(current_prompt, criterion) for criterion in criteria]
        texts = anchors + [f"task: sentence similarity | query: คำตอบ: {answer}"]
        with torch.no_grad():
            embeddings = self.model.encode(texts, batch_size=4, convert_to_tensor=True,
                                           show_progress_bar=False).float()
        if not torch.isfinite(embeddings).all():
            raise RuntimeError("Model returned non-finite embeddings")
        scores = F.cosine_similarity(embeddings[:-1], embeddings[-1:]).cpu().tolist()
        low, high, off = self.thresholds
        off_topic = max(scores) < off
        results = []
        for criterion, score in zip(criteria, scores):
            status = "missing" if score < low else "partial" if score < high else "covered"
            # Confidence is distance to the nearest decision boundary, scaled to [0, 1].
            boundary_distance = min(abs(score - low), abs(score - high))
            confidence = min(1.0, max(0.0, boundary_distance / 0.20))
            results.append({"id": criterion["id"], "status": status,
                            "confidence": round(confidence, 3)})
        if off_topic:
            # Never simultaneously claim an answer is off-topic and fully covers a criterion.
            results = [{**item, "status": "missing"} for item in results]
        return {"model_version": MODEL_VERSION,
                "off_topic": {"value": off_topic,
                              "confidence": round(min(1.0, max(0.0, abs(max(scores) - off) / 0.20)), 3)},
                "criteria": results}
