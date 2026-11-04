"""Export actual TestClient responses in explicit fake mode, for Frontend handoff."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from backend.config import ROOT, Settings
from backend.main import create_app
from backend.tests.test_backend import answer, pdf_bytes, req, start


def export(destination=ROOT / "examples"):
    destination.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="trainer-examples-") as temp:
        with TestClient(create_app(Settings(storage=Path(temp), test_mode=True))) as client:
            s, deck = start(client)
            sid = s["session_id"]
            examples = dict(note="Actual Backend test_fake responses; not trained model results.",
                            readiness=client.get("/api/ready").json(), deck_upload=deck, session_start=s,
                            responses={}, errors={})
            payload = req(s, "Quiet corner")
            s = client.post(f"/api/sessions/{sid}/answers", json=payload).json()
            examples["responses"]["probe"] = s
            examples["session_state_after_probe"] = client.get(f"/api/sessions/{sid}").json()
            examples["idempotent_replay"] = client.post(f"/api/sessions/{sid}/answers", json=payload).json()
            for label, request in [("conflict", {**payload, "answer": "different"}),
                                   ("too_long", req(s, "x" * 10000))]:
                r = client.post(f"/api/sessions/{sid}/answers", json=request)
                examples["errors"][label] = dict(http_status=r.status_code, body=r.json())
            s = answer(client, sid, s, "Hiding place")
            examples["responses"]["next"] = s
            for label in ("retry", "retry_again", "incomplete"):
                s = answer(client, sid, s, "Unrelated socks")
                examples["responses"][label] = s
            s = answer(client, sid, s, "Tail communication")
            examples["responses"]["finish"] = s
            examples["report"] = client.get(f"/api/sessions/{sid}/report").json()
    target = destination / "api-responses.test.json"
    target.write_text(json.dumps(examples, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (destination / "demo-slides.pdf").write_bytes(pdf_bytes())
    print("Exported labeled fake responses and 3-page English PDF.")


if __name__ == "__main__":
    export()
