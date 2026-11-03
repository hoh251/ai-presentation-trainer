import json
import math
import re

import httpx

from .errors import APIError, unavailable


class GeminiService:
    def __init__(self, settings, client=None):
        self.settings = settings
        self.client = client

    @property
    def ready(self):
        # Local readiness, not a guarantee of provider uptime/quota.
        return bool(self.settings.gemini_key and all(re.fullmatch(r"[a-zA-Z0-9._-]+", name)
                    for name in (self.settings.gemini_model, self.settings.embedding_model)))

    async def _post(self, model, method, body):
        if not self.ready:
            raise unavailable("QUESTION_SERVICE_UNAVAILABLE", "ยังไม่ได้ตั้งค่า Gemini และ retrieval model")
        if not re.fullmatch(r"[a-zA-Z0-9._-]+", model):
            raise unavailable("AI_CONFIG_INVALID", "ชื่อโมเดล Gemini ไม่ถูกต้อง")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:{method}"
        try:
            response = await self.client.post(url, headers={"x-goog-api-key": self.settings.gemini_key}, json=body)
            if response.status_code == 429:
                raise APIError(429, "AI_RATE_LIMIT", "โควตา AI เต็ม กรุณารอแล้วลองใหม่")
            if response.status_code != 200:
                raise unavailable("AI_UNAVAILABLE", "ผู้ให้บริการ AI ไม่พร้อมใช้งาน")
            return response.json()
        except APIError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise unavailable("AI_UNAVAILABLE", "ติดต่อผู้ให้บริการ AI ไม่สำเร็จ") from exc

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
            text = "".join(p.get("text", "") for p in candidate["content"]["parts"] if not p.get("thought"))
            return json.loads(text)
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise unavailable("AI_OUTPUT_INVALID", "AI สร้างคำตอบที่อ่านไม่ได้") from exc

    async def embed(self, texts, task):
        # One bounded batch; cap caller chunks to keep PDF indexing within deadline.
        model = self.settings.embedding_model
        result = await self._post(model, "batchEmbedContents", {"requests": [
            {"model": "models/" + model, "content": {"parts": [{"text": text}]}, "taskType": task}
            for text in texts
        ]})
        try:
            vectors = [e["values"] for e in result["embeddings"]]
            if len(vectors) != len(texts) or not vectors or not vectors[0]:
                raise ValueError("Wrong embedding count")
            dim = len(vectors[0])
            if any(len(v) != dim or not all(type(x) in (int, float) and math.isfinite(x) for x in v) for v in vectors):
                raise ValueError("Invalid embedding")
            return vectors
        except (KeyError, TypeError, ValueError) as exc:
            raise unavailable("AI_OUTPUT_INVALID", "ผล retrieval model ไม่ถูกต้อง") from exc
