"""Trained local coverage scorer for API contract v1."""

from .coverage import CoverageModel, ModelInputTooLong

_model: CoverageModel | None = None


def configure_model(base_model_path: str, checkpoint_dir: str, manifest_path: str,
                    device: str | None = None) -> CoverageModel:
    """Load and verify the model once at Backend startup."""
    global _model
    _model = CoverageModel(base_model_path, checkpoint_dir, manifest_path, device=device)
    return _model


def validate_attempt(question: dict, current_prompt: str, criteria: list[dict], answer: str) -> None:
    if _model is None:
        raise RuntimeError("Call configure_model at startup before validating answers")
    _model.validate_attempt(question, current_prompt, criteria, answer)


def predict_attempt(question: dict, current_prompt: str, criteria: list[dict], answer: str) -> dict:
    if _model is None:
        raise RuntimeError("Call configure_model at startup before scoring answers")
    return _model.predict_attempt(question, current_prompt, criteria, answer)

__all__ = ["CoverageModel", "ModelInputTooLong", "configure_model", "validate_attempt", "predict_attempt"]
