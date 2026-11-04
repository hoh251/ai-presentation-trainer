"""Checks for pre-model tools; live provider tests use an HTTP transport stub."""
import asyncio
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import httpx

from backend.config import ROOT, Settings
from backend.contract import validate_question
from backend.pdf_service import extract_pages
from backend.tools.check_rag import run


def test_acceptance_inputs_have_real_quotes_and_expected_shapes():
    root = ROOT / "examples/acceptance"
    suite = json.loads((root / "model-cases.json").read_text(encoding="utf-8"))
    assert suite["synthetic_data_only"] and suite["human_label_review_required"]
    assert suite["trained_model_evaluated"] is False
    assert len(suite["documents"]) == 4 and len(suite["cases"]) == 23
    assert len({c["id"] for c in suite["cases"]}) == 23
    for document in suite["documents"]:
        raw = (root / document["file"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == document["sha256"]
        assert len(extract_pages(raw)) == document["pages"] == 4
    for case in suite["cases"]:
        validate_question(case["question"], extract_pages((root / case["pdf"]).read_bytes()))
        if "expected" in case:
            assert {c["id"] for c in case["expected"]["criteria"]} == {c["id"] for c in case["question"]["criteria"]}
            assert all(c["status"] in {"covered", "partial", "missing"} for c in case["expected"]["criteria"])
        else:
            assert case["expected_http_status"] == 413 and case["expected_saved_attempts"] == 0


def test_rag_preview_without_configuration_never_calls_provider(tmp_path):
    output = tmp_path / "blocked.json"
    def unexpected(_):
        raise AssertionError("Provider must not be called without configuration")
    result = asyncio.run(run([ROOT / "examples/demo-slides.pdf"], Settings(), output, httpx.MockTransport(unexpected)))
    data = json.loads(output.read_text(encoding="utf-8"))
    assert result == 2 and data["status"] == "blocked"
    assert data["checks"] == [] and data["sessions_created"] is False


def test_live_rag_preview_boundary_with_mocked_provider(tmp_path):
    def provider(request):
        if request.url.path.endswith(":batchEmbedContents"):
            inputs = json.loads(request.content)["requests"]
            return httpx.Response(200, json=dict(embeddings=[dict(values=[1., .5]) for _ in inputs]))
        question = dict(id="preview", text="How can a cat hide?", source_pages=[1], topic="cat home", judge_role="concept",
                        criteria=[dict(id="hide", text="Hiding place", source_page=1, evidence_quote="Hiding place")])
        return httpx.Response(200, json=dict(candidates=[dict(finishReason="STOP", content=dict(parts=[dict(text=json.dumps(question))]))]))
    settings = Settings(gemini_key="private-test-key", gemini_model="test-generation", embedding_model="test-embedding")
    output = tmp_path / "rag.json"
    result = asyncio.run(run([ROOT / "examples/demo-slides.pdf"], settings, output, httpx.MockTransport(provider)))
    text = output.read_text(encoding="utf-8")
    data = json.loads(text)
    assert result == 0 and data["status"] == "passed"
    assert data["checks"][0]["evidence_quotes_verified"] is True
    assert data["checks"][0]["tokenizer_budget_verified"] is False
    assert data["checks"][0]["answer_coverage_evaluated"] is False
    assert "private-test-key" not in text


def test_rag_preview_redacts_provider_error(tmp_path):
    settings = Settings(gemini_key="private-test-key", gemini_model="test-generation", embedding_model="test-embedding")
    output = tmp_path / "error.json"
    provider = httpx.MockTransport(lambda _: httpx.Response(429, json=dict(secret="do not log provider body")))
    result = asyncio.run(run([ROOT / "examples/demo-slides.pdf"], settings, output, provider))
    text = output.read_text(encoding="utf-8")
    assert result == 1 and json.loads(text)["checks"][0]["code"] == "AI_RATE_LIMIT"
    assert "private-test-key" not in text and "do not log provider body" not in text
