"""Run from inside backend without colliding with another package named backend."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))

from backend.config import Settings
from backend.main import create_app
import uvicorn
import logging


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-mode", action="store_true", help="Explicit fake model/question generation; not a trained model")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--frontend-dist", type=Path)
    args = parser.parse_args()
    provider_log = logging.getLogger("backend.provider")
    provider_log.setLevel(logging.INFO)
    provider_log.addHandler(logging.StreamHandler())
    provider_log.propagate = False
    settings = Settings.from_env()
    if args.test_mode:
        from dataclasses import replace
        settings = replace(settings, test_mode=True)
        print("TEST MODE: fake predictor + test questions. No trained model is used.")
    uvicorn.run(create_app(settings, frontend_dist=args.frontend_dist), host=args.host, port=args.port)
