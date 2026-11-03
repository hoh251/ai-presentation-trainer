"""Only this adapter imports the training team's package. No fallback in real mode."""
import asyncio
import hashlib
import importlib
import json
import math
import threading

from .contract import check, normalize
from .errors import APIError, unavailable


class CoverageService:
    def __init__(self, settings):
        self.settings = settings
        self.source = "test_fake" if settings.test_mode else "local_finetuned"
        self.version = "test-fake-v1" if settings.test_mode else None
        self.identity = self.version
        self.predictor = None
        self.ready = False
        self.load_error = None
        self.lock = threading.Lock()
        # These thresholds are for deterministic fake tests only.
        self.thresholds = {"coverage": 0.8, "off_topic": 0.8}

    def load(self):
        if self.settings.test_mode:
            self.ready = True
            return
        try:
            root = self.settings.artifacts.resolve()
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            check(manifest, "manifest", model=True)
            if manifest.get("example_only"):
                raise ValueError("Example manifest cannot be used as a trained artifact")
            checkpoint = (root / manifest.get("checkpoint_file", "checkpoint.bin")).resolve()
            if not checkpoint.is_relative_to(root) or not checkpoint.is_file():
                raise ValueError("Invalid checkpoint path")
            hasher = hashlib.sha256()
            with checkpoint.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    hasher.update(block)
            if hasher.hexdigest() != manifest["checkpoint_sha256"]:
                raise ValueError("Checkpoint hash mismatch")
            thresholds = json.loads((root / "thresholds.json").read_text(encoding="utf-8"))
            for name in ("coverage", "off_topic"):
                if type(thresholds.get(name)) not in (int, float) or not 0 < thresholds[name] <= 1:
                    raise ValueError("Missing validation-derived threshold")
            package = importlib.import_module(self.settings.package_module)
            predictor = package.load_model(artifact_dir=root)
            if not callable(getattr(predictor, "predict_attempt", None)) or not callable(getattr(predictor, "validate_attempt", None)):
                raise ValueError("Package must implement predict_attempt and validate_attempt")
            if predictor.model_version != manifest["model_version"]:
                raise ValueError("Loaded model version mismatch")
            self.predictor, self.version = predictor, manifest["model_version"]
            self.identity = self.version + ":" + hasher.hexdigest()
            self.thresholds = thresholds
            self.ready = True
        except Exception as exc:
            self.ready = False
            self.load_error = type(exc).__name__  # Do not expose paths, provider keys or package tracebacks.

    def _input(self, question, prompt, answer):
        if not self.ready:
            raise unavailable()
        payload = dict(question=question, current_prompt=prompt, criteria=question["criteria"], answer=answer)
        try:
            if self.settings.test_mode:
                # Intentionally approximate fake budget; never used for real inference.
                size = len(json.dumps(payload, ensure_ascii=False))
                if size > 2048:
                    raise APIError(413, "ANSWER_TOO_LONG", "กรุณาย่อคำตอบแล้วลองใหม่")
            else:
                result = self.predictor.validate_attempt(**payload)
                if result is False:
                    raise APIError(413, "ANSWER_TOO_LONG", "กรุณาย่อคำตอบแล้วลองใหม่")
        except APIError:
            raise
        except Exception as exc:
            if type(exc).__name__ == "ModelInputTooLong":
                raise APIError(413, "ANSWER_TOO_LONG", "กรุณาย่อคำตอบแล้วลองใหม่") from exc
            raise unavailable("MODEL_INPUT_INVALID", "โมเดลตรวจข้อมูลนำเข้าไม่สำเร็จ") from exc
        return payload

    async def validate(self, question, prompt, answer="."):
        await asyncio.to_thread(self._input, question, prompt, answer)

    def _predict(self, question, prompt, answer):
        # A timed-out thread may finish inference, but it cannot mutate DB/session state.
        if not self.lock.acquire(blocking=False):
            raise unavailable("MODEL_BUSY", "โมเดลกำลังทำงาน กรุณาลองใหม่")
        try:
            payload = self._input(question, prompt, answer)
            if self.settings.test_mode:
                text = normalize(answer).casefold()
                results = []
                for criterion in question["criteria"]:
                    target = normalize(criterion["text"]).casefold()
                    status = "covered" if target in text else "missing"
                    results.append(dict(id=criterion["id"], status=status, confidence=0.99))
                result = dict(model_version=self.version, off_topic=dict(
                    value=not any(c["status"] == "covered" for c in results), confidence=0.99), criteria=results)
            else:
                result = self.predictor.predict_attempt(**payload)
            check(result, "output", model=True)
            expected = {c["id"] for c in question["criteria"]}
            ids = [c["id"] for c in result["criteria"]]
            if len(ids) != len(set(ids)) or set(ids) != expected or result["model_version"] != self.version:
                raise ValueError("Model IDs/version do not match")
            values = [c["confidence"] for c in result["criteria"]] + [result["off_topic"]["confidence"]]
            if not all(math.isfinite(v) for v in values):
                raise ValueError("Non-finite confidence")
            return result
        except APIError:
            raise
        except Exception as exc:
            raise unavailable("MODEL_OUTPUT_INVALID", "ผลโมเดลไม่ตรงสัญญากลาง") from exc
        finally:
            self.lock.release()

    async def predict(self, question, prompt, answer):
        return await asyncio.to_thread(self._predict, question, prompt, answer)
