"""Bounded Gemini transport with stage-specific quota handling and safe telemetry."""
import asyncio
from collections import deque
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import json
import logging
import math
import re
import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from .errors import APIError, unavailable

LOG = logging.getLogger("backend.provider")


def quota_details(response):
    try:
        error = response.json().get("error", {})
    except (ValueError, AttributeError):
        error = {}
    if not isinstance(error, dict):
        error = {}
    markers, delay = [], None
    details = error.get("details", [])
    for detail in details if isinstance(details, list) else []:
        if not isinstance(detail, dict):
            continue
        if detail.get("@type", "").endswith("RetryInfo"):
            raw = detail.get("retryDelay", "")
            if isinstance(raw, str) and re.fullmatch(r"\d+(?:\.\d+)?s", raw):
                delay = float(raw[:-1])
        violations = detail.get("violations", [])
        for violation in violations if isinstance(violations, list) else []:
            if isinstance(violation, dict):
                markers.extend(str(violation.get(k, "")) for k in ("quotaMetric", "quotaId", "subject", "description"))
    if delay is None and response.headers.get("retry-after"):
        raw = response.headers["retry-after"]
        try:
            delay = float(raw) if re.fullmatch(r"\d+(?:\.\d+)?", raw) else max(0, parsedate_to_datetime(raw).timestamp() - time.time())
        except (ValueError, TypeError, OverflowError):
            pass
    text = " ".join(markers).lower().replace("_", "").replace("-", "")
    scope = "day" if any(k in text for k in ("perday", "daily", "requests/day")) else "minute" if any(k in text for k in ("perminute", "permin", "rpm", "tpm")) else "unknown"
    if delay is not None and delay >= 3600:
        scope = "day"
    if delay is None and scope == "day":
        try:
            now = datetime.now(ZoneInfo("America/Los_Angeles"))
            midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), tzinfo=now.tzinfo)
            delay = (midnight.astimezone(timezone.utc) - now.astimezone(timezone.utc)).total_seconds()
        except ZoneInfoNotFoundError:
            delay = 86400
    return scope, max(0, delay) if delay is not None and math.isfinite(delay) else None


class GeminiService:
    def __init__(self, settings, client=None):
        self.settings, self.client = settings, client
        self._locks, self._last_request, self._blocked = {}, {}, {}
        self.events = deque(maxlen=1000)
        self.request_count = 0
        self.quota_path = settings.storage / "provider-quota.json"
        try:
            data = json.loads(self.quota_path.read_text(encoding="utf-8"))
            self._blocked = {k: v for k, v in data.items() if isinstance(v, dict) and type(v.get("until")) in (int, float)
                             and math.isfinite(v["until"]) and v["until"] > time.time() and v.get("scope") == "day"}
        except (OSError, ValueError, AttributeError):
            pass

    @property
    def ready(self):
        return bool(self.settings.gemini_key and all(re.fullmatch(r"[a-zA-Z0-9._-]+", name)
                    for name in (self.settings.gemini_model, self.settings.embedding_model)))

    def _event(self, method, model, status, category, started, delay=None):
        event = dict(endpoint=method, model=model, status=status, error_category=category,
                     latency_ms=round((time.monotonic() - started) * 1000), retry_delay_seconds=delay, request_count=self.request_count)
        self.events.append(event)
        LOG.info(json.dumps(event, sort_keys=True))

    def _quota_error(self, method, scope, delay):
        stage = "GENERATION" if method == "generateContent" else "EMBEDDING"
        code = f"AI_{stage}_DAILY_QUOTA" if scope == "day" else f"AI_{stage}_RATE_LIMIT" if scope == "minute" else "AI_RATE_LIMIT"
        message = ("โควตารายวันของบริการสร้างคำถามหมด" if stage == "GENERATION" else "โควตารายวันของบริการค้นสไลด์หมด") if scope == "day" else "บริการ AI จำกัดจำนวนคำขอ กรุณารอตามเวลาที่แจ้งแล้วลองใหม่"
        headers = {"X-AI-Endpoint": method, "X-AI-Error-Category": scope + "_quota"}
        if delay is not None:
            headers["Retry-After"] = str(math.ceil(delay))
        return APIError(429, code, message, headers=headers)

    def _save_daily_blocks(self):
        try:
            self.quota_path.parent.mkdir(parents=True, exist_ok=True)
            records = {k: v for k, v in self._blocked.items() if v["scope"] == "day" and v["until"] > time.time()}
            temporary = self.quota_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(records), encoding="utf-8")
            temporary.replace(self.quota_path)
        except OSError:
            pass

    async def _post(self, model, method, body):
        if not self.ready:
            raise unavailable("QUESTION_SERVICE_UNAVAILABLE", "ยังไม่ได้ตั้งค่า Gemini และ retrieval model")
        if not re.fullmatch(r"[a-zA-Z0-9._-]+", model):
            raise unavailable("AI_CONFIG_INVALID", "ชื่อโมเดล Gemini ไม่ถูกต้อง")
        key = method + ":" + model
        async with self._locks.setdefault(key, asyncio.Lock()):
            for attempt in range(self.settings.provider_retries + 1):
                block = self._blocked.get(key)
                if block and block["until"] > time.time():
                    raise self._quota_error(method, block["scope"], block["until"] - time.time())
                rpm = self.settings.generation_rpm if method == "generateContent" else self.settings.embedding_rpm
                wait = self._last_request.get(key, 0) + (60 / rpm if rpm else 0) - time.monotonic()
                if wait > 0:
                    await asyncio.sleep(wait)
                self._last_request[key] = time.monotonic()
                started = time.monotonic()
                self.request_count += 1
                try:
                    response = await self.client.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:{method}",
                                                      headers={"x-goog-api-key": self.settings.gemini_key}, json=body)
                except httpx.HTTPError as exc:
                    self._event(method, model, 0, "network", started)
                    raise unavailable("AI_UNAVAILABLE", "ติดต่อผู้ให้บริการ AI ไม่สำเร็จ") from exc
                if response.status_code == 429:
                    scope, delay = quota_details(response)
                    if delay is None and scope == "minute":
                        delay = 2 ** attempt
                    self._event(method, model, 429, scope + "_quota", started, delay)
                    if delay is not None:
                        self._blocked[key] = dict(scope=scope, until=time.time() + delay)
                        if scope == "day":
                            self._save_daily_blocks()
                    if scope == "minute" and attempt < self.settings.provider_retries and delay <= self.settings.max_backoff_seconds:
                        await asyncio.sleep(delay)
                        continue
                    raise self._quota_error(method, scope, delay)
                if response.status_code != 200:
                    category = "authentication" if response.status_code in (401, 403) else "model_unavailable" if response.status_code == 404 else "request_invalid" if response.status_code == 400 else "provider_unavailable"
                    self._event(method, model, response.status_code, category, started)
                    raise unavailable("AI_MODEL_UNAVAILABLE" if response.status_code == 404 else "AI_UNAVAILABLE", "ผู้ให้บริการ AI ไม่พร้อมใช้งาน")
                try:
                    result = response.json()
                except ValueError as exc:
                    self._event(method, model, 200, "invalid_json", started)
                    raise unavailable("AI_OUTPUT_INVALID", "ผล AI ไม่ใช่ JSON ที่อ่านได้") from exc
                self._event(method, model, 200, None, started)
                return result

    async def generate(self, instruction, data, schema):
        result = await self._post(self.settings.gemini_model, "generateContent", {
            "systemInstruction": {"parts": [{"text": instruction}]},
            "contents": [{"role": "user", "parts": [{"text": json.dumps(data, ensure_ascii=False)}]}],
            "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json", "responseJsonSchema": schema},
        })
        try:
            candidate = result["candidates"][0]
            if candidate.get("finishReason") != "STOP":
                raise ValueError("Incomplete response")
            return json.loads("".join(p.get("text", "") for p in candidate["content"]["parts"] if not p.get("thought")))
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise unavailable("AI_OUTPUT_INVALID", "AI สร้างคำตอบที่อ่านไม่ได้") from exc

    async def embed(self, texts, task):
        if not texts:
            return []
        model, vectors = self.settings.embedding_model, []
        batch_size = self.settings.embedding_batch_size
        for offset in range(0, len(texts), batch_size):
            batch = texts[offset:offset + batch_size]
            result = await self._post(model, "batchEmbedContents", {"requests": [
                {"model": "models/" + model, "content": {"parts": [{"text": text}]}, "taskType": task} for text in batch
            ]})
            try:
                current = [e["values"] for e in result["embeddings"]]
                if len(current) != len(batch) or not current or not current[0]:
                    raise ValueError("Wrong embedding count")
                dim = len(vectors[0]) if vectors else len(current[0])
                if any(len(v) != dim or not all(type(x) in (int, float) and math.isfinite(x) for x in v) for v in current):
                    raise ValueError("Invalid embedding")
                vectors.extend(current)
            except (KeyError, TypeError, ValueError) as exc:
                raise unavailable("AI_OUTPUT_INVALID", "ผล retrieval model ไม่ถูกต้อง") from exc
        return vectors
