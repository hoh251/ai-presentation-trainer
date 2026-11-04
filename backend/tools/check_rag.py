"""Preview live Gemini/RAG independently of model_package; does not grade or start sessions."""
import argparse
import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import httpx
from jsonschema import ValidationError

from backend.config import ROOT, Settings
from backend.contract import validate_question
from backend.db import Store
from backend.errors import APIError
from backend.gemini_service import GeminiService
from backend.pdf_service import extract_pages
from backend.question_service import QuestionService, question_schema


async def inspect_pdf(path, settings, store, gemini):
    pages = extract_pages(path.read_bytes())
    deck = dict(id=str(uuid4()), pages=pages)
    store.save_deck(deck["id"], path.name, pages, path)
    service = QuestionService(settings, store, gemini, None)
    question = await service.preview(deck, "standard", 1, [])
    return dict(file=path.name, status="passed", pages=len(pages), question=question, evidence_quotes_verified=True,
                tokenizer_budget_verified=False, answer_coverage_evaluated=False)


async def run(paths, settings, output, transport=None):
    configured = dict(api_key_configured=bool(settings.gemini_key), generation_model_configured=bool(settings.gemini_model),
                      retrieval_model_configured=bool(settings.embedding_model))
    result = dict(mode="live-gemini-rag-preview", model_package_required=False, sessions_created=False,
                  tokenizer_budget_verified=False, config=configured, checks=[])
    if not all(configured.values()):
        result.update(status="blocked", reason="Set GEMINI_API_KEY, GEMINI_MODEL and GEMINI_EMBEDDING_MODEL in backend/.env; never send the key in chat.")
    else:
        with TemporaryDirectory(prefix="trainer-rag-") as temporary:
            store = Store(Path(temporary))
            store.migrate()
            async with httpx.AsyncClient(timeout=settings.provider_timeout, transport=transport) as client:
                gemini = GeminiService(settings, client)
                for path in paths:
                    try:
                        async with asyncio.timeout(settings.deadline_seconds):
                            result["checks"].append(await inspect_pdf(path, settings, store, gemini))
                    except APIError as error:
                        result["checks"].append(dict(file=path.name, status="failed", code=error.code, retry_after_seconds=error.headers.get("Retry-After")))
                        if error.status == 429:
                            break
                    except TimeoutError:
                        result["checks"].append(dict(file=path.name, status="failed", code="AI_TIMEOUT"))
        result["status"] = "passed" if len(result["checks"]) == len(paths) and all(r["status"] == "passed" for r in result["checks"]) else "failed"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dict(status=result["status"], files_checked=len(result["checks"]), config=configured)))
    return 0 if result["status"] == "passed" else 2 if result["status"] == "blocked" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pdfs", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, default=ROOT / ".integration/live-rag.json")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.pdfs, Settings.from_env(), args.output)))
