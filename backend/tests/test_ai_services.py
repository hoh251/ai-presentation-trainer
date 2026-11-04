"""Provider/package tests use stubs, not trained artifacts or live Gemini results."""
import asyncio
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import sys
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.agent import decide, initial_coverage
from backend.config import Settings
from backend.contract import validate_question
from backend.coverage_service import CoverageService
from backend.db import Store
from backend.errors import APIError
from backend.gemini_service import GeminiService
from backend.main import create_app
from backend.question_service import QuestionService, chunks
from backend.tests.test_backend import pdf_bytes, req


QUESTION = dict(id="q", text="How to help cats?", source_pages=[1], topic="cat home", judge_role="concept", criteria=[
    dict(id="quiet", text="Quiet corner", source_page=1, evidence_quote="Quiet corner"),
    dict(id="hide", text="Hiding place", source_page=1, evidence_quote="Hiding place")])


class StubPredictor:
    """Package-boundary test double; deliberately not a trained predictor."""
    model_version = "stub-package-v1"

    def validate_attempt(self, **payload):
        if len(payload["answer"]) > 512:
            class ModelInputTooLong(Exception):
                pass
            raise ModelInputTooLong()

    def predict_attempt(self, **payload):
        return dict(model_version=self.model_version, off_topic=dict(value=False, confidence=.99),
                    criteria=[dict(id=c["id"], status="covered", confidence=.99) for c in payload["criteria"]])


@pytest.fixture
def real_stub(tmp_path, monkeypatch):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    data = b"TEST STUB ONLY - not a trained model"
    (artifacts / "checkpoint.bin").write_bytes(data)
    manifest = dict(contract_version=1, model_version="stub-package-v1", base_model="google/embeddinggemma-300m",
                    fine_tuned=True, checkpoint_sha256=hashlib.sha256(data).hexdigest(), max_input_tokens=512)
    (artifacts / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (artifacts / "thresholds.json").write_text(json.dumps(dict(coverage=.9, off_topic=.9)), encoding="utf-8")
    predictor = StubPredictor()
    monkeypatch.setitem(sys.modules, "test_model_package", SimpleNamespace(load_model=lambda artifact_dir: predictor))
    settings = Settings(storage=tmp_path / "storage", artifacts=artifacts, package_module="test_model_package",
                        gemini_key="test-key-never-sent", gemini_model="test-generation", embedding_model="test-embedding")
    return settings, predictor


def test_package_load_restart_hash_ids_and_length(real_stub):
    settings, predictor = real_stub
    service = CoverageService(settings)
    service.load()
    assert service.ready and service.source == "local_finetuned"
    result = asyncio.run(service.predict(QUESTION, QUESTION["text"], "Quiet corner Hiding place"))
    assert result["model_version"] == "stub-package-v1"
    assert service.identity.endswith(hashlib.sha256(b"TEST STUB ONLY - not a trained model").hexdigest())
    with pytest.raises(APIError) as exc:
        asyncio.run(service.predict(QUESTION, QUESTION["text"], "x" * 513))
    assert exc.value.status == 413
    original = predictor.predict_attempt
    def wrong_id(**payload):
        output = original(**payload)
        output["criteria"][0]["id"] = "unknown"
        return output
    predictor.predict_attempt = wrong_id
    with pytest.raises(APIError) as exc:
        asyncio.run(service.predict(QUESTION, QUESTION["text"], "answer"))
    assert exc.value.code == "MODEL_OUTPUT_INVALID"
    assert CoverageService(settings).ready is False
    reloaded = CoverageService(settings)
    reloaded.load()
    assert reloaded.ready
    (settings.artifacts / "checkpoint.bin").write_bytes(b"tampered")
    broken = CoverageService(settings)
    broken.load()
    assert broken.ready is False


def provider_handler(request):
    if request.url.path.endswith(":batchEmbedContents"):
        body = json.loads(request.content)
        if body["requests"][0].get("taskType") == "SEMANTIC_SIMILARITY":
            return httpx.Response(200, json=dict(embeddings=[dict(values=[float(i == j) for j in range(len(body["requests"]))]) for i in range(len(body["requests"]))]))
        return httpx.Response(200, json=dict(embeddings=[dict(values=[1., .5, .2]) for _ in body["requests"]]))
    assert request.url.path.endswith(":generateContent")
    assert request.headers["x-goog-api-key"] == "test-key-never-sent"
    data = json.loads(json.loads(request.content)["contents"][0]["parts"][0]["text"])
    question = deepcopy(QUESTION)
    evidence = data["evidence"][0]
    quote = evidence["text"].split(".")[0]
    question.update(text=f"Explain page {evidence['source_page']} round {data['round']}", source_pages=[evidence["source_page"]],
                    criteria=[dict(id="test", text=quote, evidence_quote=quote, source_page=evidence["source_page"])])
    return httpx.Response(200, json=dict(candidates=[dict(finishReason="STOP", content=dict(parts=[dict(text=json.dumps(question))]))]))


def test_full_real_service_wiring_with_stub_package_and_mock_provider(real_stub):
    settings, _ = real_stub
    calls = []
    def handler(request):
        calls.append(request.url.path)
        return provider_handler(request)
    transport = httpx.MockTransport(handler)
    with TestClient(create_app(settings, provider_transport=transport)) as client:
        assert client.get("/api/ready").status_code == 200
        upload = client.post("/api/decks", files={"file": ("new.pdf", pdf_bytes(), "application/pdf")}).json()
        start = client.post("/api/sessions", json=dict(deck_id=upload["deck_id"], difficulty="standard"))
        assert start.status_code == 200, start.text
        state = start.json()
        assert state["model_source"] == "local_finetuned" and state["test_mode"] is False
        sid = state["session_id"]
        for _ in range(3):
            response = client.post(f"/api/sessions/{sid}/answers", json=req(state, "all criteria"))
            assert response.status_code == 200, response.text
            state = response.json()
        assert state["completed"] is True
        # One index, three retrieval queries, two semantic-dedup checks.
        assert sum(path.endswith(":batchEmbedContents") for path in calls) == 6
        assert sum(path.endswith(":generateContent") for path in calls) == 3
        assert client.get(f"/api/sessions/{sid}/report").status_code == 200


@pytest.mark.parametrize("status", [429, 500, 401])
def test_provider_errors_do_not_create_session(real_stub, status):
    settings, _ = real_stub
    transport = httpx.MockTransport(lambda _: httpx.Response(status, json={"provider_secret": "never expose"}))
    with TestClient(create_app(settings, provider_transport=transport)) as client:
        deck = client.post("/api/decks", files={"file": ("test.pdf", pdf_bytes(), "application/pdf")}).json()
        response = client.post("/api/sessions", json=dict(deck_id=deck["deck_id"], difficulty="basic"))
        assert response.status_code == (429 if status == 429 else 503)
        assert "provider_secret" not in response.text and "test-key" not in response.text
        with client.app.state.store.connect() as con:
            assert con.execute("SELECT COUNT(*) FROM trainer_sessions").fetchone()[0] == 0


def test_bad_quote_regeneration_limit_and_no_session(real_stub):
    settings, _ = real_stub
    count = []
    def handler(request):
        if request.url.path.endswith(":generateContent"):
            count.append(1)
            bad = deepcopy(QUESTION)
            bad["criteria"][0]["evidence_quote"] = "not in the PDF"
            return httpx.Response(200, json=dict(candidates=[dict(finishReason="STOP", content=dict(parts=[dict(text=json.dumps(bad))]))]))
        return provider_handler(request)
    with TestClient(create_app(settings, provider_transport=httpx.MockTransport(handler))) as client:
        deck = client.post("/api/decks", files={"file": ("test.pdf", pdf_bytes(), "application/pdf")}).json()
        response = client.post("/api/sessions", json=dict(deck_id=deck["deck_id"], difficulty="basic"))
        assert response.status_code == 503 and response.json()["error"]["code"] == "QUESTION_INVALID"
        assert len(count) == settings.generation_tries


def test_source_quote_page_one_and_duplicate_ids():
    validate_question(QUESTION, ["Quiet   corner. Hiding place."])
    bad = deepcopy(QUESTION)
    bad["criteria"][1]["id"] = "quiet"
    with pytest.raises(ValueError):
        validate_question(bad, ["Quiet corner. Hiding place."])
    assert chunks(["Content on page one", "Next page"])[0]["source_page"] == 1


def test_low_confidence_does_not_add_coverage_and_attempt_limit_wins():
    raw = dict(off_topic=dict(value=False, confidence=.99), criteria=[
        dict(id="quiet", status="covered", confidence=.3), dict(id="hide", status="covered", confidence=.99)])
    for count in (1, 3):
        coverage, action, outcome, _ = decide(initial_coverage(QUESTION), raw, count, dict(coverage=.9, off_topic=.9))
        assert all(c["status"] == "missing" for c in coverage)
        assert action == ("clarify" if count == 1 else "close")
        assert outcome == (None if count == 1 else "incomplete")


def test_model_version_swap_requires_new_session(real_stub):
    settings, predictor = real_stub
    with TestClient(create_app(settings, provider_transport=httpx.MockTransport(provider_handler))) as client:
        deck = client.post("/api/decks", files={"file": ("test.pdf", pdf_bytes(), "application/pdf")}).json()
        state = client.post("/api/sessions", json=dict(deck_id=deck["deck_id"], difficulty="basic")).json()
        sid = state["session_id"]
        client.app.state.model.identity = "same-version:new-checkpoint-hash"
        response = client.post(f"/api/sessions/{sid}/answers", json=req(state, "answer"))
        assert response.status_code == 503 and response.json()["error"]["code"] == "SESSION_MODEL_CHANGED"


def test_missing_thresholds_rejects_real_mode(real_stub):
    settings, _ = real_stub
    (settings.artifacts / "thresholds.json").unlink()
    service = CoverageService(settings)
    service.load()
    assert service.ready is False


def test_export_examples_are_actual_fake_responses(tmp_path):
    from backend.tools.export_examples import export
    export(tmp_path)
    data = json.loads((tmp_path / "api-responses.test.json").read_text(encoding="utf-8"))
    assert data["session_start"]["test_mode"] is True
    assert data["idempotent_replay"] == data["responses"]["probe"]
    assert len(data["report"]["rounds"]) == 3
    assert (tmp_path / "demo-slides.pdf").read_bytes().startswith(b"%PDF-")
