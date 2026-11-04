"""Check the shipped launcher over a real local HTTP connection."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import httpx


def test_windows_launcher_serves_ready_and_static_frontend(tmp_path):
    root = Path(__file__).resolve().parents[1]
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<h1>Frontend proxy smoke test</h1>", encoding="utf-8")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = dict(os.environ, TRAINER_STORAGE=str(tmp_path / "runtime"), PYTHONIOENCODING="utf-8")
    process = subprocess.Popen(
        [sys.executable, str(root / "run.py"), "--test-mode", "--port", str(port), "--frontend-dist", str(dist)],
        cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    try:
        deadline = time.monotonic() + 20
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=1, trust_env=False) as client:
            while True:
                try:
                    ready = client.get("/api/ready")
                    break
                except httpx.TransportError:
                    if process.poll() is not None or time.monotonic() >= deadline:
                        raise AssertionError("Backend launcher did not become reachable")
                    time.sleep(.1)
            assert ready.status_code == 200 and ready.json()["model_source"] == "test_fake"
            assert "Frontend proxy smoke test" in client.get("/").text
            assert client.get("/api/not-found").json()["error"]["code"] == "ROUTE_NOT_FOUND"
    finally:
        process.terminate()
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=5)
