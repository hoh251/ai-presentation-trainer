# Model package: EmbeddingGemma coverage scorer

This is Person A's Backend handoff for contract v1. The actual model is `google/embeddinggemma-300m` fine-tuned locally with LoRA on `q_proj`/`v_proj`, plus the two Sentence Transformers Dense modules. The package returns one `covered`/`partial`/`missing` decision per criterion and a separate `off_topic` decision. It does not generate praise, choose a new question, access the database, or call Gemini; the Backend Agent owns those actions.

## Files and handoff

- `coverage.py`: `CoverageModel` and token-count validation.
- `__init__.py`: `configure_model`, `predict_attempt`, `validate_attempt` interface used by the Backend.
- `manifest.json`: model version, 512-token limit, validation thresholds, and SHA-256 hashes for the adapter and Dense heads.
- `requirements.txt`: Python dependencies used for this checkpoint. On the training machine PyTorch `2.11.0+cu128` worked with RTX 3050 4 GB and bfloat16.
- The **checkpoint directory and base-model weights are outside this public repository**. The owner must deliver the checkpoint through an approved private channel. A fresh machine must separately obtain the gated base model after accepting its license; a Hugging Face token is only needed to download it, not for local inference after download.

## Backend startup

Install dependencies in a clean Python environment. For NVIDIA CUDA, install the matching PyTorch CUDA wheel first, then the remaining requirements. Resolve model paths at deployment rather than editing the manifest or embedding a machine-specific path in Backend code.

```python
from model_package import configure_model, predict_attempt, validate_attempt

configure_model(
    base_model_path="<local directory of google/embeddinggemma-300m>",
    checkpoint_dir="<private LoRA checkpoint directory>",
    manifest_path="model_package/manifest.json",
)

validate_attempt(question, current_prompt, criteria, answer)
result = predict_attempt(question, current_prompt, criteria, answer)
```

Call `configure_model` once when the Backend starts. It checks the checkpoint hashes and loads the model. If loading fails, `/api/ready` must report `model_ready=false` and requests that require the model must fail clearly. Do not fall back silently to a fake predictor. `ModelInputTooLong` signals that the checkpoint tokenizer counted more than 512 tokens in an anchor or answer input; the Backend maps an overlong submitted answer to HTTP 413 without storing the attempt. The Backend should ensure its generated question/criterion prefix fits before starting a question.

The package returns contract v1's exact criterion IDs. Confidence is a **distance from a decision threshold**, not a calibrated probability. Low confidence should cause the Agent to clarify rather than confidently praise. `off_topic=true` can never appear with `covered` from this package.

## Reproduce the model check

```powershell
python training/smoke_model_package.py --base-model <local-base-dir> --checkpoint <private-checkpoint-dir>
```

The smoke test validates the manifest and output against `contracts/v1/model.schema.json`, checks a complete answer, a partial answer, a slang/refusal answer, and a 512-token rejection. The checkpoint cannot be tested by cloning this repository alone because its weights are intentionally stored separately.

## Evaluation limit

`training/experiment_results.json` compares an untrained EmbeddingGemma scorer and this fine-tuned scorer on a held-out **synthetic** deck, including 10 stress answers. `training/baseline_results.json` is a character-bigram rule baseline on the same deck. The sample is small; it does not establish accuracy on arbitrary PDF slides. A real evaluation needs human-reviewed answers from multiple new presentations, especially ambiguous, short, and adversarial Thai responses.
