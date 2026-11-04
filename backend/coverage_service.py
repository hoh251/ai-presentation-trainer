"""Only this adapter imports the training team's package. No fallback in real mode."""
import asyncio
import json
import math
import threading

from .contract import check, normalize
from .errors import APIError, unavailable
from .model_loader import load as load_bundle, ModelLoadError


class CoverageService:
    def __init__(self, settings):
        self.settings = settings
        self.source = "test_fake" if settings.test_mode else "local_finetuned"
        self.version = "test-fake-v1" if settings.test_mode else None
        self.identity = self.version
        self.predictor = None
        self.ready = False
        self.load_error = None
        self.load_error_code = None
        self.validation_thresholds = None
        self.lock = threading.Lock()
        # These thresholds are for deterministic fake tests only.
        self.thresholds = {"coverage": 0.8, "off_topic": 0.8}

    def load(self):
        if self.settings.test_mode:
            self.ready = True
            return
        try:
            self.ready = False
            self.predictor = self.version = self.identity = None
            bundle = load_bundle(self.settings)
            self.predictor, self.version, self.identity = bundle.predictor, bundle.version, bundle.identity
            self.thresholds = bundle.agent_gates
            self.validation_thresholds = bundle.validation_thresholds
            self.ready = True
            self.load_error = self.load_error_code = None
        except Exception as exc:
            self.ready = False
            self.load_error_code = (exc.code if isinstance(exc, ModelLoadError) else
                                    "MODEL_DEPENDENCY_MISSING" if isinstance(exc, ImportError) else
                                    "MODEL_ARTIFACT_MISSING" if isinstance(exc, FileNotFoundError) else
                                    "MODEL_MANIFEST_INVALID" if isinstance(exc, (ValueError, KeyError, TypeError)) else "MODEL_LOAD_FAILED")
            self.load_error = self.load_error_code

    def _input(self, question, prompt, answer):
        if not self.ready:
            raise unavailable(self.load_error_code or "MODEL_UNAVAILABLE")
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
