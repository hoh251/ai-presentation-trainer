"""Load Person A's public interface and private artifacts without a runtime bridge."""
from dataclasses import dataclass
import hashlib
import importlib
import json
import math
from pathlib import Path
from jsonschema import ValidationError

from .contract import check


class ModelLoadError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def inside(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ModelLoadError("MODEL_ARTIFACT_MISSING")
    return path


def verify(path, expected):
    if not isinstance(expected, str) or len(expected) != 64 or digest(path) != expected:
        raise ModelLoadError("MODEL_HASH_MISMATCH")


def read_gates(path, require_calibration):
    if not path.is_file():
        raise ModelLoadError("MODEL_GATES_MISSING")
    gates = json.loads(path.read_text(encoding="utf-8"))
    for name in ("coverage", "off_topic"):
        value = gates.get(name)
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= 1:
            raise ModelLoadError("MODEL_GATES_INVALID")
    calibration = gates.get("calibration", {})
    if require_calibration and (type(calibration.get("rows")) is not int or calibration["rows"] < 1
                                or not isinstance(calibration.get("selection"), str) or not calibration["selection"].strip()):
        raise ModelLoadError("MODEL_GATES_UNCALIBRATED")
    return gates


@dataclass
class LoadedModel:
    predictor: object
    version: str
    identity: str
    agent_gates: dict
    validation_thresholds: tuple | None


def load(settings):
    root = settings.artifacts.resolve()
    manifest_path = settings.model_manifest or root / "manifest.json"
    if settings.model_manifest is None and not manifest_path.is_file() and settings.package_module == "model_package":
        packaged_manifest = Path(__file__).resolve().parent.parent / "model_package/manifest.json"
        if packaged_manifest.is_file():
            manifest_path = packaged_manifest
    if not manifest_path.is_file():
        raise ModelLoadError("MODEL_ARTIFACT_MISSING")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    try:
        check(manifest, "manifest", model=True)
    except ValidationError as exc:
        raise ModelLoadError("MODEL_MANIFEST_INVALID") from exc
    if manifest.get("example_only"):
        raise ModelLoadError("MODEL_EXAMPLE_ARTIFACT")
    v2 = "dense_sha256" in manifest
    checkpoint_root = (settings.model_checkpoint or (root / "checkpoint" if (root / "checkpoint").is_dir() else root)).resolve()
    validation = None
    if v2:
        adapter = inside(checkpoint_root, "adapter_model.safetensors")
        verify(adapter, manifest["checkpoint_sha256"])
        dense = manifest["dense_sha256"]
        if set(dense) != {"2_Dense", "3_Dense"}:
            raise ModelLoadError("MODEL_MANIFEST_INVALID")
        for name, expected in dense.items():
            verify(inside(checkpoint_root, name + "/model.safetensors"), expected)
        validation = manifest.get("validation_thresholds")
        if not isinstance(validation, list) or len(validation) != 3 or any(
            type(x) not in (int, float) or not math.isfinite(x) or not -1 <= x <= 1 for x in validation
        ) or validation[0] >= validation[1]:
            raise ModelLoadError("MODEL_CLASS_THRESHOLDS_INVALID")
        validation = tuple(validation)
        base = settings.model_base
        if base is None or not base.is_dir():
            raise ModelLoadError("MODEL_BASE_MISSING")
        if not any(base.rglob("*.safetensors")) and not any(base.rglob("pytorch_model*.bin")):
            raise ModelLoadError("MODEL_BASE_MISSING")
    else:
        adapter = inside(root, manifest.get("checkpoint_file", "checkpoint.bin"))
        verify(adapter, manifest["checkpoint_sha256"])
    # Expected hashes from A are verified; every remaining checkpoint/config file
    # is also fingerprinted into session identity (not claimed as provenance).
    for name, expected in manifest.get("artifact_sha256", {}).items():
        verify(inside(checkpoint_root, name), expected)
    gates_path = settings.agent_gates_path or root / "thresholds.json"
    gates = read_gates(gates_path, require_calibration=v2)
    package = importlib.import_module(settings.package_module)
    loader = settings.model_loader
    if loader == "coverage_v2" or (loader == "auto" and v2):
        cls = getattr(package, "CoverageModel", None)
        if cls is None:
            raise ModelLoadError("MODEL_INTERFACE_INVALID")
        predictor = cls(base_model_path=str(settings.model_base), checkpoint_dir=str(checkpoint_root), manifest_path=str(manifest_path))
    else:
        factory = getattr(package, "load_model", None)
        if not callable(factory):
            raise ModelLoadError("MODEL_INTERFACE_INVALID")
        predictor = factory(artifact_dir=root)
    if not all(callable(getattr(predictor, method, None)) for method in ("predict_attempt", "validate_attempt")):
        raise ModelLoadError("MODEL_INTERFACE_INVALID")
    if predictor.model_version != manifest["model_version"]:
        raise ModelLoadError("MODEL_VERSION_MISMATCH")
    if v2 and tuple(getattr(predictor, "thresholds", ())) != validation:
        raise ModelLoadError("MODEL_CLASS_THRESHOLDS_INVALID")
    if not v2:
        identity = manifest["model_version"] + ":" + digest(adapter)
    else:
        inventory = dict(manifest=digest(manifest_path), agent_gates=digest(gates_path))
        for label, directory in (("checkpoint", checkpoint_root), ("base", settings.model_base.resolve())):
            for item in sorted(directory.rglob("*")):
                if item.is_file() and "__pycache__" not in item.parts and ".cache" not in item.parts:
                    resolved = item.resolve()
                    if label == "checkpoint" and not resolved.is_relative_to(directory):
                        raise ModelLoadError("MODEL_MANIFEST_INVALID")
                    inventory[label + "/" + item.relative_to(directory).as_posix()] = digest(resolved)
        identity = manifest["model_version"] + ":" + hashlib.sha256(json.dumps(inventory, sort_keys=True).encode()).hexdigest()
    return LoadedModel(predictor, manifest["model_version"], identity, gates, validation)
