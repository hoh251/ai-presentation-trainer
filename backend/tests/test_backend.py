import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from io import BytesIO
import json
from pathlib import Path
import sqlite3
import threading
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, NameObject

from backend.config import Settings
from backend.contract import check
from backend.coverage_service import CoverageService
from backend.db import Store
from backend.errors import APIError
from backend.main import create_app


def pdf_bytes(texts=("Quiet corner. Hiding place.", "Clean water.", "Tail communication.")):
    writer = PdfWriter()
    for text in texts:
        page = writer.add_blank_page(width=595, height=842)
        if text is not None:
            font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
            page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
            stream = DecodedStreamObject()
            stream.set_data(f"BT /F1 12 Tf 30 800 Td ({text}) Tj ET".encode("ascii"))
            page[NameObject("/Contents")] = writer._add_object(stream)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


@pytest.fixture
def settings(tmp_path):
    return Settings(storage=tmp_path / "storage", test_mode=True)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as value:
        yield value


def upload(client, content=None):
    response = client.post("/api/decks", files={"file": ("cats.pdf", content or pdf_bytes(), "application/pdf")})
    assert response.status_code == 200, response.text
    check(response.json(), "deck_upload")
    return response.json()


def start(client):
    deck = upload(client)
    response = client.post("/api/sessions", json=dict(deck_id=deck["deck_id"], difficulty="standard"))
    assert response.status_code == 200, response.text
    check(response.json(), "session_start")
    return response.json(), deck


def req(state, answer, question=None):
    return dict(question_id=(question or state.get("question") or state.get("next_question"))["id"],
                attempt_id=str(uuid4()), state_version=state["state_version"], answer=answer)


def answer(client, sid, state, text):
    response = client.post(f"/api/sessions/{sid}/answers", json=req(state, text))
    assert response.status_code == 200, response.text
    check(response.json(), "answer_response")
    return response.json()


def test_six_attempt_flow_report_pdf_and_retry(client):
    s, deck = start(client)
    sid = s["session_id"]
    assert client.get("/api/ready").json()["model_source"] == "test_fake"
    assert client.get(f"/api/sessions/{sid}/report").status_code == 409
    assert client.get(f"/api/decks/{deck['deck_id']}/file").content == pdf_bytes()
    first_request = req(s, "Quiet corner")
    probe = client.post(f"/api/sessions/{sid}/answers", json=first_request).json()
    assert probe["agent_action"] == "probe" and probe["round"] == 1
    assert probe["next_question"]["id"] == s["question"]["id"]
    assert probe["coverage"][0]["status"] == "covered"
    n = answer(client, sid, probe, "Hiding place")
    assert n["agent_action"] == "next" and len(n["history"]) == 1
    assert all(c["status"] == "covered" for c in n["history"][0]["coverage"])
    # Lost response retry must still replay after advancing to question 2.
    replay = client.post(f"/api/sessions/{sid}/answers", json=first_request)
    assert replay.json() == probe
    for count in range(3):
        n = answer(client, sid, n, "Unrelated socks")
        assert n["agent_action"] == ("retry" if count < 2 else "next")
    assert n["round"] == 3 and n["history"][1]["outcome"] == "incomplete"
    n = answer(client, sid, n, "Tail communication")
    assert n["agent_action"] == "finish" and n["completed"]
    assert n["next_question"] is None and n["current_prompt"] is None and n["round"] == 3
    assert n["attempts"] == [] and len(n["history"]) == 3
    assert n["test_mode"] is True and n["model_source"] == "test_fake"
    report = client.get(f"/api/sessions/{sid}/report").json()
    check(report, "report")
    assert report["rounds"] == n["history"]
    assert len(report["overall"]["improvements"]) == 1
    state = client.get(f"/api/sessions/{sid}").json()
    check(state, "session_state")
    assert state["history"] == report["rounds"]


def test_duplicate_payload_stale_version_and_long_answer_are_atomic(client):
    s, _ = start(client)
    sid = s["session_id"]
    original = req(s, "Quiet corner")
    accepted = client.post(f"/api/sessions/{sid}/answers", json=original).json()
    for changed in ({**original, "answer": "different"}, {**original, "state_version": 2},
                    {**original, "question_id": "other"}, {**original, "attempt_id": str(uuid4())}):
        assert client.post(f"/api/sessions/{sid}/answers", json=changed).status_code == 409
    before = client.get(f"/api/sessions/{sid}").json()
    long_response = client.post(f"/api/sessions/{sid}/answers", json=req(accepted, "x" * 10000))
    assert long_response.status_code == 413
    assert client.get(f"/api/sessions/{sid}").json() == before


@pytest.mark.parametrize("status,code", [(429, "AI_RATE_LIMIT"), (503, "MODEL_UNAVAILABLE")])
def test_dependency_failure_does_not_commit(client, status, code, monkeypatch):
    s, _ = start(client)
    sid = s["session_id"]
    before = client.get(f"/api/sessions/{sid}").json()
    original = client.app.state.model.predict
    async def fail(*_):
        raise APIError(status, code, "unavailable")
    monkeypatch.setattr(client.app.state.model, "predict", fail)
    payload = req(s, "Quiet corner")
    assert client.post(f"/api/sessions/{sid}/answers", json=payload).status_code == status
    assert client.get(f"/api/sessions/{sid}").json() == before
    monkeypatch.setattr(client.app.state.model, "predict", original)
    assert client.post(f"/api/sessions/{sid}/answers", json=payload).status_code == 200


def test_gemini_failure_after_model_does_not_save_attempt(client, monkeypatch):
    s, _ = start(client)
    sid = s["session_id"]
    before = client.get(f"/api/sessions/{sid}").json()
    async def fail(*_):
        raise APIError(429, "AI_RATE_LIMIT", "rate limited")
    monkeypatch.setattr(client.app.state.questions, "prompt", fail)
    assert client.post(f"/api/sessions/{sid}/answers", json=req(s, "Quiet corner")).status_code == 429
    assert client.get(f"/api/sessions/{sid}").json() == before


def test_restart_keeps_state_and_replays_when_model_not_ready(settings):
    with TestClient(create_app(settings)) as client:
        s, _ = start(client)
        sid = s["session_id"]
        payload = req(s, "Quiet corner")
        expected = client.post(f"/api/sessions/{sid}/answers", json=payload).json()
        state = client.get(f"/api/sessions/{sid}").json()
    with TestClient(create_app(replace(settings, test_mode=False))) as client:
        assert client.get("/api/ready").status_code == 503
        assert client.get(f"/api/sessions/{sid}").json() == state
        assert client.post(f"/api/sessions/{sid}/answers", json=payload).json() == expected
        assert client.post(f"/api/sessions/{sid}/answers", json=req(expected, "Hiding place")).status_code == 503


def test_concurrent_different_attempts_only_one_commits(client, monkeypatch):
    s, _ = start(client)
    sid = s["session_id"]
    original = client.app.state.model.predict
    barrier = threading.Barrier(2)
    async def synchronize(*args):
        output = await original(*args)
        await asyncio.to_thread(barrier.wait, 5)
        return output
    monkeypatch.setattr(client.app.state.model, "predict", synchronize)
    payloads = [req(s, "Quiet corner"), req(s, "Hiding place")]
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda p: client.post(f"/api/sessions/{sid}/answers", json=p), payloads))
    assert sorted(r.status_code for r in responses) == [200, 409]
    state = client.get(f"/api/sessions/{sid}").json()
    assert state["state_version"] == 1 and len(state["attempts"]) == 1


def test_concurrent_identical_attempt_returns_same_snapshot(client, monkeypatch):
    s, _ = start(client)
    sid = s["session_id"]
    original = client.app.state.model.predict
    barrier = threading.Barrier(2)
    async def synchronize(*args):
        output = await original(*args)
        await asyncio.to_thread(barrier.wait, 5)
        return output
    monkeypatch.setattr(client.app.state.model, "predict", synchronize)
    payload = req(s, "Quiet corner")
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.post(f"/api/sessions/{sid}/answers", json=payload), range(2)))
    assert [r.status_code for r in responses] == [200, 200]
    assert responses[0].json() == responses[1].json()
    assert len(client.get(f"/api/sessions/{sid}").json()["attempts"]) == 1


def test_conflict_outputs_clarify_then_close_incomplete(client, monkeypatch):
    s, _ = start(client)
    sid = s["session_id"]
    async def contradiction(question, prompt, text):
        return dict(model_version="test-fake-v1", off_topic=dict(value=True, confidence=.99),
                    criteria=[dict(id=c["id"], status="covered", confidence=.99) for c in question["criteria"]])
    monkeypatch.setattr(client.app.state.model, "predict", contradiction)
    for count in range(3):
        s = answer(client, sid, s, "conflict")
        assert s["feedback"]["strengths"] == []
        assert s["agent_action"] == ("clarify" if count < 2 else "next")
    assert s["history"][0]["outcome"] == "incomplete"
    assert all(c["status"] == "missing" for c in s["history"][0]["coverage"])


def test_offtopic_preserves_confirmed_coverage(client):
    s, _ = start(client)
    sid = s["session_id"]
    s = answer(client, sid, s, "Quiet corner")
    s = answer(client, sid, s, "Socks")
    assert s["agent_action"] == "retry"
    assert s["coverage"][0]["status"] == "covered"
    s = answer(client, sid, s, "Hiding place")
    assert s["history"][0]["outcome"] == "complete"


@pytest.mark.parametrize("content,code", [(b"not a pdf", "PDF_INVALID"), (pdf_bytes([None]), "PDF_NO_TEXT"),
                                          (pdf_bytes(["a"] * 11), "PDF_PAGE_LIMIT")])
def test_invalid_pdfs(client, content, code):
    response = client.post("/api/decks", files={"file": ("test.pdf", content, "application/pdf")})
    assert response.status_code == 422 and response.json()["error"]["code"] == code


def test_pdf_size_limit(client):
    response = client.post("/api/decks", files={"file": ("large.pdf", b"%PDF-" + b"x" * (15*1024*1024), "application/pdf")})
    assert response.status_code == 413 and response.json()["error"]["code"] == "PDF_TOO_LARGE"


def test_request_errors_follow_contract(client):
    for response in [client.get("/api/unknown"), client.post("/api/sessions", json={}),
                     client.get("/api/sessions/missing"), client.get("/api/decks/missing/file")]:
        check(response.json(), "error")
        assert response.status_code >= 400


def test_real_mode_never_falls_back(settings):
    with TestClient(create_app(replace(settings, test_mode=False))) as client:
        readiness = client.get("/api/ready")
        assert readiness.status_code == 503
        assert readiness.json()["model_source"] == "local_finetuned"
        assert readiness.json()["model_ready"] is False
        assert readiness.json()["question_service_ready"] is False
        deck = upload(client)
        assert client.post("/api/sessions", json=dict(deck_id=deck["deck_id"], difficulty="basic")).status_code == 503


def test_additive_migration_preserves_existing_database(settings):
    settings.storage.mkdir()
    path = settings.storage / "trainer.sqlite3"
    with sqlite3.connect(path) as con:
        con.execute("CREATE TABLE answers(id INTEGER PRIMARY KEY, answer TEXT)")
        con.execute("INSERT INTO answers VALUES (1,'old prototype')")
    Store(settings.storage).migrate()
    Store(settings.storage).migrate()
    with sqlite3.connect(path) as con:
        assert con.execute("SELECT answer FROM answers").fetchone()[0] == "old prototype"


def test_timeout_leaves_state_unchanged(settings, monkeypatch):
    with TestClient(create_app(settings)) as client:
        s, _ = start(client)
        sid = s["session_id"]
        before = client.get(f"/api/sessions/{sid}").json()
    short = replace(settings, deadline_seconds=.03, provider_timeout=.01)
    with TestClient(create_app(short)) as client:
        async def slow(*_):
            await asyncio.sleep(1)
        monkeypatch.setattr(client.app.state.model, "predict", slow)
        r = client.post(f"/api/sessions/{sid}/answers", json=req(s, "Quiet corner"))
        assert r.status_code == 503 and r.json()["error"]["code"] == "AI_TIMEOUT"
        assert client.get(f"/api/sessions/{sid}").json() == before


def test_generated_question_failure_does_not_create_session(client, monkeypatch):
    deck = upload(client)
    async def fail(*_):
        raise APIError(503, "QUESTION_INVALID", "bad quote")
    monkeypatch.setattr(client.app.state.questions, "create", fail)
    assert client.post("/api/sessions", json=dict(deck_id=deck["deck_id"], difficulty="basic")).status_code == 503
    with client.app.state.store.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM trainer_sessions").fetchone()[0] == 0
