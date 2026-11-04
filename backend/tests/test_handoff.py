"""Handoff regression checks. All model weights/predictors here are explicit stubs."""
import asyncio
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import sys
import time
from types import SimpleNamespace

import httpx
import pytest
from jsonschema import Draft202012Validator
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.coverage_service import CoverageService
from backend.db import Store
from backend.errors import APIError
from backend.gemini_service import GeminiService, quota_details
from backend.main import create_app
from backend.question_service import QuestionService
from backend.pdf_inspection import inspect_pdf
from backend.pdf_service import extract_pages
from backend.tests.test_ai_services import QUESTION, StubPredictor
from backend.tests.test_backend import pdf_bytes


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    root, base = tmp_path / "artifacts", tmp_path / "base"
    checkpoint = root / "checkpoint"
    checkpoint.mkdir(parents=True)
    base.mkdir()
    (base / "model.safetensors").write_bytes(b"STUB base, not trained")
    (base / "config.json").write_text('{}')
    for relative in ("adapter_model.safetensors", "2_Dense/model.safetensors", "3_Dense/model.safetensors", "adapter_config.json"):
        path = checkpoint / relative
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(("STUB " + relative).encode())
    sha = lambda name: hashlib.sha256((checkpoint / name).read_bytes()).hexdigest()
    manifest = dict(contract_version=1, model_version="stub-package-v1", base_model="google/embeddinggemma-300m", fine_tuned=True,
                    checkpoint_sha256=sha("adapter_model.safetensors"), max_input_tokens=512,
                    dense_sha256={n: sha(n + "/model.safetensors") for n in ("2_Dense", "3_Dense")},
                    artifact_sha256={"adapter_config.json": sha("adapter_config.json")}, validation_thresholds=[.4, .7, .3])
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    gates = dict(coverage=.14, off_topic=.23, calibration=dict(rows=32, selection="validation only", note="synthetic test stub"))
    (root / "thresholds.json").write_text(json.dumps(gates), encoding="utf-8")
    loaded = []
    class Predictor(StubPredictor):
        def __init__(self, **kwargs):
            loaded.append(kwargs)
            self.thresholds = (.4, .7, .3)
    monkeypatch.setitem(sys.modules, "v2_stub", SimpleNamespace(CoverageModel=Predictor))
    settings = Settings(storage=tmp_path / "storage", artifacts=root, model_base=base, package_module="v2_stub")
    return settings, checkpoint, manifest, loaded


def test_v2_direct_constructor_hash_identity_restart_and_separate_gates(bundle):
    settings, checkpoint, manifest, loaded = bundle
    model = CoverageService(settings)
    model.load()
    assert model.ready and len(loaded) == 1
    assert loaded[0]["checkpoint_dir"] == str(checkpoint)
    assert model.validation_thresholds == (.4, .7, .3)
    assert model.thresholds["coverage"] == .14 and model.thresholds["off_topic"] == .23
    output = asyncio.run(model.predict(QUESTION, QUESTION["text"], "answer"))
    assert output["model_version"] == "stub-package-v1"
    restarted = CoverageService(settings)
    restarted.load()
    assert restarted.ready and restarted.identity == model.identity
    (settings.model_base / "config.json").write_text('{"changed":true}')
    changed = CoverageService(settings)
    changed.load()
    assert changed.ready and changed.identity != model.identity


@pytest.mark.parametrize("relative", ["adapter_model.safetensors", "2_Dense/model.safetensors", "3_Dense/model.safetensors", "adapter_config.json"])
def test_every_declared_artifact_hash_is_verified(bundle, relative):
    settings, checkpoint, _, loaded = bundle
    (checkpoint / relative).write_bytes(b"tampered")
    model = CoverageService(settings)
    model.load()
    assert not model.ready and model.load_error_code == "MODEL_HASH_MISMATCH"
    assert loaded == []


def test_uncalibrated_sidecar_is_not_accepted_for_v2(bundle):
    settings, _, _, loaded = bundle
    (settings.artifacts / "thresholds.json").write_text('{"coverage":0.25,"off_topic":0.25}')
    model = CoverageService(settings)
    model.load()
    assert not model.ready and model.load_error_code == "MODEL_GATES_UNCALIBRATED"
    assert loaded == []


def test_original_v2_layout_without_export_checkpoint_file_is_supported(bundle):
    settings, checkpoint, _, loaded = bundle
    original = replace(settings, artifacts=checkpoint, model_manifest=settings.artifacts / "manifest.json",
                       agent_gates_path=settings.artifacts / "thresholds.json")
    model = CoverageService(original)
    model.load()
    assert model.ready and loaded[0]["checkpoint_dir"] == str(checkpoint)


def test_missing_model_is_503_with_category_and_no_paths_or_fake_fallback(bundle):
    settings, checkpoint, _, _ = bundle
    (checkpoint / "2_Dense/model.safetensors").unlink()
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/ready")
        assert response.status_code == 503
        assert response.headers["x-model-error"] == "MODEL_ARTIFACT_MISSING"
        assert response.json()["model_source"] == "local_finetuned"
        response = client.post("/api/sessions", json=dict(deck_id="irrelevant", difficulty="basic"))
        assert response.status_code == 503 and response.json()["error"]["code"] == "MODEL_ARTIFACT_MISSING"
        assert str(settings.artifacts) not in response.text


def quota_response(scope="day", delay="46837s"):
    details = [{"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [
        {"quotaMetric": "generate_content_free_tier_requests", "quotaId": "GenerateRequestsPerDay" if scope == "day" else "GenerateRequestsPerMinute"}]}]
    if delay is not None:
        details.append({"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": delay})
    return httpx.Response(429, json={"error": {"message": "PRIVATE PROMPT AND KEY MUST NOT BE LOGGED", "details": details}})


def test_daily_quota_stops_calls_survives_restart_and_is_stage_specific(tmp_path):
    settings = Settings(storage=tmp_path, gemini_key="SECRET_KEY", gemini_model="generation", embedding_model="embedding")
    calls = []
    def provider(request):
        calls.append(request.url.path)
        return quota_response() if request.url.path.endswith(":generateContent") else httpx.Response(200, json={"embeddings": [{"values": [1., 0.]}]})
    async def exercise():
        async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as client:
            service = GeminiService(settings, client)
            for _ in range(2):
                with pytest.raises(APIError) as caught:
                    await service.generate("PRIVATE prompt", {}, {})
                assert caught.value.code == "AI_GENERATION_DAILY_QUOTA"
                assert int(caught.value.headers["Retry-After"]) >= 46836
                assert caught.value.headers["X-AI-Endpoint"] == "generateContent"
            assert service.request_count == 1
            assert await service.embed(["private text"], "RETRIEVAL_QUERY") == [[1., 0.]]
            restarted = GeminiService(settings, client)
            with pytest.raises(APIError):
                await restarted.generate("private", {}, {})
            assert restarted.request_count == 0
            serial = json.dumps(list(service.events)) + (tmp_path / "provider-quota.json").read_text()
            assert "SECRET_KEY" not in serial and "PRIVATE" not in serial and "private text" not in serial
    asyncio.run(exercise())
    assert len(calls) == 2


def test_short_rpm_retry_is_bounded_and_embedding_batching_is_complete(tmp_path):
    settings = Settings(storage=tmp_path, gemini_key="key", gemini_model="gen", embedding_model="embed", embedding_batch_size=2)
    sizes = []
    def provider(request):
        if not sizes:
            sizes.append(0)
            return quota_response("minute", "0s")
        batch = json.loads(request.content)["requests"]
        sizes.append(len(batch))
        return httpx.Response(200, json={"embeddings": [{"values": [1., .5]} for _ in batch]})
    async def exercise():
        async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as client:
            service = GeminiService(settings, client)
            assert len(await service.embed(["a", "b", "c", "d", "e"], "RETRIEVAL_DOCUMENT")) == 5
            assert service.request_count == 4
    asyncio.run(exercise())
    assert sizes == [0, 2, 2, 1]


def test_long_rpm_wait_returns_retry_after_without_sleep_or_retry(tmp_path):
    settings = Settings(storage=tmp_path, gemini_key="key", gemini_model="gen", embedding_model="embed")
    calls = []
    async def exercise():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: calls.append(1) or quota_response("minute", "60s"))) as client:
            service = GeminiService(settings, client)
            with pytest.raises(APIError) as caught:
                await service.generate("private", {}, {})
            assert caught.value.code == "AI_GENERATION_RATE_LIMIT" and caught.value.headers["Retry-After"] == "60"
    asyncio.run(exercise())
    assert len(calls) == 1


def test_page_diversity_and_content_cache_across_deck_ids(tmp_path):
    store = Store(tmp_path)
    store.migrate()
    documents = []
    class Retrieval:
        ready = True
        async def embed(self, texts, task):
            if task == "RETRIEVAL_DOCUMENT":
                documents.append(texts)
                return [[1., 0.], [.9, .1], [.8, .2]]
            return [[1., 0.]]
    async def exercise():
        service = QuestionService(Settings(), store, Retrieval(), None)
        pages = ["page one", "page two", "page three"]
        for identifier in ("first", "second"):
            store.save_deck(identifier, "slides.pdf", pages, tmp_path / "unused.pdf")
        first = await service.retrieve(dict(id="first", pages=pages), 1, "standard", [])
        assert [x["source_page"] for x in first] == [1, 2]
        second = await service.retrieve(dict(id="second", pages=pages), 2, "standard", [{"question": dict(source_pages=[1, 2], topic="prior")}])
        assert [x["source_page"] for x in second] == [3]
        alternative = await service.retrieve(dict(id="second", pages=pages), 2, "standard", [], {1, 2})
        assert [x["source_page"] for x in alternative] == [3]
    asyncio.run(exercise())
    assert len(documents) == 1


def test_paraphrased_question_is_rejected_by_semantics():
    class Embeddings:
        async def embed(self, texts, task):
            assert task == "SEMANTIC_SIMILARITY"
            return [[1., 0.], [.999, .001]]
    service = QuestionService(Settings(), None, Embeddings(), None)
    assert asyncio.run(service._duplicate(dict(text="How can the cat hide?"), [{"question": dict(text="Explain a hiding place for cats.")}]))


@pytest.mark.parametrize("pages", [10, 30, 58, 86])
def test_long_pdf_diagnostics_preserve_original_pages_but_upload_cap_stays_v1(pages):
    raw = pdf_bytes(["Readable text on each page."] * pages)
    diagnostic = inspect_pdf(raw)
    assert diagnostic["page_count"] == pages
    assert [p["page"] for p in diagnostic["pages"]] == list(range(1, pages + 1))
    assert diagnostic["contract_v1_page_count_supported"] == (pages <= 10)
    assert not diagnostic["ocr_performed"] and not diagnostic["detection_metrics_available"]
    if pages <= 10:
        assert len(extract_pages(raw)) == pages
    else:
        with pytest.raises(APIError) as caught:
            extract_pages(raw)
        assert caught.value.code == "PDF_PAGE_LIMIT"
        assert "เลือกช่วง" in caught.value.message


def test_scanned_or_blank_page_is_uncertain_and_never_visual_evidence():
    diagnostic = inspect_pdf(pdf_bytes([None]))
    assert diagnostic["classification"] == "uncertain"
    assert diagnostic["pages"][0]["needs_visual_review"]
    assert diagnostic["pages"][0]["visual_status"] == "not_processed"
    assert not diagnostic["pages"][0]["usable_for_visual_questions"]


def test_contract_proposal_fixtures_and_uncertain_visual_guard():
    from backend.config import ROOT
    schema = json.loads((ROOT / "proposals/contract-v2.schema.json").read_text(encoding="utf-8"))
    examples = json.loads((ROOT / "proposals/fixtures.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    for name in ("text", "visual", "uncertain"):
        Draft202012Validator({**schema, "$ref": "#/$defs/evidence"}).validate(examples[name])
    for name in ("ingestion", "quota_error"):
        Draft202012Validator({**schema, "$ref": "#/$defs/" + name}).validate(examples[name])
    unsafe = {**examples["uncertain"], "usable_for_questions": True}
    assert list(Draft202012Validator({**schema, "$ref": "#/$defs/evidence"}).iter_errors(unsafe))
