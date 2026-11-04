"""Trained local coverage scorer for API contract v1."""

import json
import os
from pathlib import Path

from .coverage import CoverageModel, ModelInputTooLong

_model: CoverageModel | None = None


def configure_model(base_model_path: str, checkpoint_dir: str, manifest_path: str,
                    device: str | None = None) -> CoverageModel:
    """Load and verify the model once at Backend startup."""
    global _model
    _model = CoverageModel(base_model_path, checkpoint_dir, manifest_path, device=device)
    return _model


def load_model(artifact_dir: str | Path) -> CoverageModel:
    """Load the private artifact layout expected by Backend contract v1.

    The base weights remain outside the artifact directory and are supplied by
    MODEL_BASE_PATH after the Google license has been accepted.  The manifest
    and all checkpoint hashes are verified by CoverageModel.
    """
    root = Path(artifact_dir).resolve()
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    checkpoint_file = manifest.get("checkpoint_file")
    if checkpoint_file != "checkpoint/adapter_model.safetensors":
        raise ValueError("Unsupported checkpoint layout")
    base_path = os.environ.get("MODEL_BASE_PATH")
    if not base_path:
        raise ValueError("MODEL_BASE_PATH is required for local inference")
    return configure_model(base_path, str(root / "checkpoint"), str(manifest_path))


def validate_attempt(question: dict, current_prompt: str, criteria: list[dict], answer: str) -> None:
    if _model is None:
        raise RuntimeError("Call configure_model at startup before validating answers")
    _model.validate_attempt(question, current_prompt, criteria, answer)


def predict_attempt(question: dict, current_prompt: str, criteria: list[dict], answer: str) -> dict:
    if _model is None:
        raise RuntimeError("Call configure_model at startup before scoring answers")
    return _model.predict_attempt(question, current_prompt, criteria, answer)

__all__ = ["CoverageModel", "ModelInputTooLong", "configure_model", "load_model", "validate_attempt", "predict_attempt"]
