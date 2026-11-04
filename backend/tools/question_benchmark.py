"""Bounded live question audit; no answer grading or untrained model bridge."""
import argparse
import asyncio
import csv
import json
from pathlib import Path
import hashlib
import tempfile
from uuid import uuid4

import httpx

from backend.config import ROOT, Settings
from backend.db import Store
from backend.errors import APIError
from backend.gemini_service import GeminiService
from backend.pdf_service import extract_pages
from backend.question_service import QuestionService
from backend.contract import validate_question


async def audit(pdfs, count, output, resume=False):
    settings = Settings.from_env()
    report = dict(client_date="2026-11-05", synthetic_inputs=True, model=settings.gemini_model, embedding=settings.embedding_model,
                  tokenizer_budget_verified=False, trained_model_evaluated=False, human_quality_review_complete=False,
                  questions=[], failures=[], telemetry=[])
    output.mkdir(parents=True, exist_ok=True)
    if resume and (output / "results.json").is_file():
        previous = json.loads((output / "results.json").read_text(encoding="utf-8"))
        if previous["model"] != settings.gemini_model or previous["embedding"] != settings.embedding_model:
            raise ValueError("Resume requires the original model IDs")
        report = previous
    if resume and "phases" not in report:
        report["phases"] = [dict(resume=False, questions=len(report["questions"]), failures=len(report["failures"]), question_policy_sha256=None,
                                note="Initial run retained; policy hash was not recorded at execution time")]
    previous_events = list(report["telemetry"])
    report.setdefault("phases", []).append(dict(resume=resume, prior_questions=len(report["questions"]),
        question_policy_sha256=hashlib.sha256((ROOT / "question_service.py").read_bytes()).hexdigest()))
    def save():
        (output / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="question-audit-") as directory:
        store = Store(Path(directory))
        store.migrate()
        # Quota cooldown is deployment-wide, even though test deck/session data is temporary.
        async with httpx.AsyncClient(timeout=settings.provider_timeout) as client:
            gemini = GeminiService(settings, client)
            service = QuestionService(settings, store, gemini, None)
            for path in pdfs:
                pages = extract_pages(path.read_bytes())
                deck = dict(id=str(uuid4()), pages=pages)
                store.save_deck(deck["id"], path.name, pages, path)
                existing = [q for q in report["questions"] if q["file"] == path.name]
                for entry in existing:
                    validate_question(entry["question"], pages)
                history = [dict(question=q["question"]) for q in existing]
                prior_samples = [q["sample"] for q in report["questions"] + report["failures"] if q["file"] == path.name]
                first_index = max(prior_samples, default=0)
                for attempt in range(max(0, count - len(history)) + 2):
                    if len(history) >= count:
                        break
                    index = first_index + attempt
                    difficulty = ("basic", "standard", "challenge")[index % 3]
                    try:
                        async with asyncio.timeout(settings.deadline_seconds):
                            question = await service.preview(deck, difficulty, (index % 3) + 1, history)
                        report["questions"].append(dict(file=path.name, sample=index + 1, difficulty=difficulty, question=question,
                                                        schema_and_quotes_valid=True, human_review="pending"))
                        history.append(dict(question=question))
                        print(json.dumps(dict(file=path.name, sample=index + 1, difficulty=difficulty, status="passed")), flush=True)
                    except (APIError, TimeoutError) as error:
                        code = error.code if isinstance(error, APIError) else "AI_TIMEOUT"
                        report["failures"].append(dict(file=path.name, sample=index + 1, code=code,
                            validation=error.headers.get("X-Question-Validation") if isinstance(error, APIError) else None))
                        print(json.dumps(dict(file=path.name, sample=index + 1, status="failed", code=code)), flush=True)
                        if isinstance(error, APIError) and error.status == 429:
                            report["status"] = "quota_blocked"
                            report["telemetry"] = previous_events + list(gemini.events)
                            save()
                            return 2
                    report["telemetry"] = previous_events + list(gemini.events)
                    save()
    report["status"] = "passed_automated_checks" if len(report["questions"]) == len(pdfs) * count else "partial"
    report["quota_events"] = sum(r["status"] == 429 for r in report["telemetry"])
    save()
    with (output / "human-review.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["file", "sample", "difficulty", "question", "answerable", "citation_correct", "not_repetitive", "difficulty_matches", "notes"])
        for row in report["questions"]:
            writer.writerow([row["file"], row["sample"], row["difficulty"], row["question"]["text"], "", "", "", "", ""])
    print(json.dumps(dict(status=report["status"], questions=len(report["questions"]), failures=len(report["failures"]), quota_events=report["quota_events"])))
    return 0 if report["status"] == "passed_automated_checks" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pdfs", type=Path, nargs="+")
    parser.add_argument("--count-per-deck", type=int, default=10, choices=range(1, 11))
    parser.add_argument("--output", type=Path, default=ROOT / ".integration/question-audit")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(audit(args.pdfs, args.count_per_deck, args.output, args.resume)))
