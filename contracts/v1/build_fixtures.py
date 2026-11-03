"""Build deterministic, illustrative API/model v1 fixtures."""
from __future__ import annotations

import copy
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
Q1 = {
    "id": "q_cat_home", "text": "จะจัดบ้านให้แมวรู้สึกปลอดภัยอย่างไร?",
    "source_pages": [2], "topic": "สภาพแวดล้อมแมว", "judge_role": "concept",
    "decision_reason": "ถามจากเนื้อหาสไลด์หน้า 2",
    "criteria": [
        {"id": "quiet", "text": "จัดมุมเงียบ", "source_page": 2, "evidence_quote": "จัดมุมเงียบให้แมว"},
        {"id": "hide", "text": "จัดที่หลบ", "source_page": 2, "evidence_quote": "มีที่หลบให้แมว"},
    ],
}
Q2 = {
    "id": "q_water", "text": "ควรเตรียมน้ำให้แมวอย่างไร?", "source_pages": [3],
    "topic": "การดูแล", "judge_role": "concept", "decision_reason": "ถามจากสไลด์หน้า 3",
    "criteria": [{"id": "water", "text": "น้ำสะอาด", "source_page": 3, "evidence_quote": "มีน้ำสะอาดให้แมว"}],
}
Q3 = {
    "id": "q_behavior", "text": "แมวสื่อสารด้วยวิธีใด?", "source_pages": [4],
    "topic": "พฤติกรรม", "judge_role": "concept", "decision_reason": "ถามจากสไลด์หน้า 4",
    "criteria": [{"id": "tail", "text": "ภาษาหาง", "source_page": 4, "evidence_quote": "แมวใช้หางสื่อสาร"}],
}


def attempt(number: int, prompt: str, answer: str, action: str) -> dict:
    return {
        "attempt_id": f"00000000-0000-4000-8000-{number:012d}",
        "prompt_at_attempt": prompt, "answer": answer, "agent_action": action,
    }


def feedback(relevance: str, strengths: list[str], improvements: list[str], pages: list[int]) -> dict:
    return {"relevance": relevance, "strengths": strengths, "improvements": improvements, "source_pages": pages}


def closed_round(number: int, question: dict, outcome: str, attempts: list[dict], coverage: list[dict], result: dict) -> dict:
    return {
        "round": number, "question": question, "outcome": outcome,
        "attempts": attempts, "answer": " / ".join(item["answer"] for item in attempts),
        "coverage": coverage, "feedback": result, "source_pages": question["source_pages"],
    }


quiet_only = [
    {"criterion_id": "quiet", "status": "covered", "confidence": 0.91},
    {"criterion_id": "hide", "status": "missing", "confidence": 0.86},
]
both = [
    {"criterion_id": "quiet", "status": "covered", "confidence": 0.91},
    {"criterion_id": "hide", "status": "covered", "confidence": 0.88},
]
water_missing = [{"criterion_id": "water", "status": "missing", "confidence": 0.95}]
tail_covered = [{"criterion_id": "tail", "status": "covered", "confidence": 0.92}]

a1 = attempt(1, Q1["text"], "จัดมุมเงียบ ๆ ให้", "probe")
a2 = attempt(2, "ในมุมเงียบนั้นจะเพิ่มอะไรให้แมวหลบได้?", "จัดบ้านแมวให้เข้าไปหลบ", "next")
a3 = attempt(3, Q2["text"], "ถุงเท้า", "retry")
a4 = attempt(4, "ลองตอบเรื่องน้ำของแมวอีกครั้ง", "ไม่รู้", "retry")
a5 = attempt(5, "ควรให้น้ำลักษณะใด?", "แมวชอบปลาทู", "next")
a6 = attempt(6, Q3["text"], "แมวใช้หางสื่อสาร", "finish")

r1 = closed_round(1, Q1, "complete", [a1, a2], both, feedback("relevant", ["กล่าวถึงมุมเงียบและที่หลบ"], [], [2]))
r2 = closed_round(2, Q2, "incomplete", [a3, a4, a5], water_missing, feedback("unrelated", [], ["ยังไม่ได้กล่าวถึงน้ำสะอาด"], [3]))
r3 = closed_round(3, Q3, "complete", [a6], tail_covered, feedback("relevant", ["อธิบายการสื่อสารด้วยหาง"], [], [4]))


def answer_response(version: int, round_number: int, question: dict | None, prompt: str | None,
                    attempts: list[dict], history: list[dict], coverage: list[dict], action: str,
                    counted: bool, completed: bool, off_topic: bool, result: dict, reason: str) -> dict:
    return {
        "status": "ok", "contract_version": 1, "state_version": version,
        "round": round_number, "next_question": question, "current_prompt": prompt,
        "attempts": attempts, "history": history, "coverage": coverage,
        "model_version": "embeddinggemma-coverage-v1", "model_source": "local_finetuned",
        "off_topic": {"value": off_topic, "confidence": 0.93},
        "agent_action": action, "agent_reason": reason, "counted_round": counted,
        "feedback": result, "completed": completed, "test_mode": False,
    }


fixtures = {
    "deck_upload": {"status": "ok", "contract_version": 1, "deck_id": "deck_fixture", "filename": "cats.pdf", "page_count": 6},
    "deck_pages": ["บทนำเรื่องแมว", "จัดมุมเงียบให้แมว และมีที่หลบให้แมว", "มีน้ำสะอาดให้แมว", "แมวใช้หางสื่อสาร", "สรุป", "ขอบคุณ"],
    "session_start_request": {"deck_id": "deck_fixture", "difficulty": "standard"},
    "readiness": {"status": "ok", "contract_version": 1, "database_ready": True, "model_ready": True, "question_service_ready": True, "model_source": "local_finetuned", "model_version": "embeddinggemma-coverage-v1"},
    "questions": {"q1": Q1, "q2": Q2, "q3": Q3},
    "session_start": {
        "status": "ok", "contract_version": 1, "session_id": "ses_fixture",
        "round": 1, "question": Q1, "current_prompt": Q1["text"],
        "state_version": 0, "model_source": "local_finetuned", "test_mode": False,
    },
    "model_input": {"question": Q1, "current_prompt": Q1["text"], "criteria": Q1["criteria"], "answer": a1["answer"]},
    "model_output": {
        "model_version": "embeddinggemma-coverage-v1",
        "off_topic": {"value": False, "confidence": 0.94},
        "criteria": [
            {"id": "quiet", "status": "covered", "confidence": 0.91},
            {"id": "hide", "status": "missing", "confidence": 0.86},
        ],
    },
    "manifest_example": {
        "contract_version": 1,
        "model_version": "embeddinggemma-coverage-v1",
        "base_model": "google/embeddinggemma-300m",
        "fine_tuned": True,
        "checkpoint_sha256": "0" * 64,
        "max_input_tokens": 512,
        "example_only": True,
    },
    "answer_requests": {
        "first": {"question_id": Q1["id"], "attempt_id": a1["attempt_id"], "state_version": 0, "answer": a1["answer"]},
        "follow_up": {"question_id": Q1["id"], "attempt_id": a2["attempt_id"], "state_version": 1, "answer": a2["answer"]},
        "third": {"question_id": Q2["id"], "attempt_id": a3["attempt_id"], "state_version": 2, "answer": a3["answer"]},
        "fourth": {"question_id": Q2["id"], "attempt_id": a4["attempt_id"], "state_version": 3, "answer": a4["answer"]},
        "fifth": {"question_id": Q2["id"], "attempt_id": a5["attempt_id"], "state_version": 4, "answer": a5["answer"]},
        "sixth": {"question_id": Q3["id"], "attempt_id": a6["attempt_id"], "state_version": 5, "answer": a6["answer"]},
    },
    "responses": {
        "probe": answer_response(1, 1, Q1, a2["prompt_at_attempt"], [a1], [], quiet_only, "probe", False, False, False, feedback("partial", ["กล่าวถึงมุมเงียบ"], ["เพิ่มที่หลบให้แมว"], [2]), "ยังขาดที่หลบ"),
        "next": answer_response(2, 2, Q2, Q2["text"], [], [r1], [], "next", True, False, False, r1["feedback"], "ครอบคลุมทั้งสองประเด็น"),
        "retry": answer_response(3, 2, Q2, "ลองตอบเรื่องน้ำของแมวอีกครั้ง", [a3], [r1], water_missing, "retry", False, False, True, feedback("unrelated", [], ["คำตอบยังไม่เกี่ยวกับการให้น้ำ"], [3]), "คำตอบนอกเรื่อง"),
        "retry_again": answer_response(4, 2, Q2, a5["prompt_at_attempt"], [a3, a4], [r1], water_missing, "retry", False, False, False, feedback("partial", [], ["ยังไม่ได้ตอบเรื่องน้ำสะอาด"], [3]), "คำตอบยังไม่ครบ"),
        "incomplete": answer_response(5, 3, Q3, Q3["text"], [], [r1, r2], [], "next", True, False, True, r2["feedback"], "ครบสามครั้งแล้วยังไม่ครอบคลุม"),
        "finish": answer_response(6, 3, None, None, [], [r1, r2, r3], [], "finish", True, True, False, r3["feedback"], "ปิดครบสามรอบ"),
    },
    "session_state_after_probe": {
        "status": "ok", "contract_version": 1, "deck_id": "deck_fixture", "filename": "cats.pdf",
        "page_count": 6, "difficulty": "standard", "round": 1, "question": Q1,
        "current_prompt": a2["prompt_at_attempt"], "attempts": [a1], "history": [],
        "coverage": quiet_only, "state_version": 1, "completed": False,
        "model_source": "local_finetuned", "test_mode": False,
    },
    "report": {
        "status": "ok", "contract_version": 1, "model_source": "local_finetuned", "test_mode": False,
        "overall": {"summary": "จบสามรอบ โดยรอบที่สองยังตอบไม่ครบ", "strengths": ["อธิบายมุมเงียบและที่หลบ"], "improvements": ["อธิบายเรื่องน้ำสะอาด"]},
        "rounds": [r1, r2, r3],
    },
    "errors": {
        "conflict": {"http_status": 409, "body": {"status": "error", "error": {"code": "STATE_CONFLICT", "message": "สถานะรอบซ้อมเปลี่ยนไป กรุณาโหลดใหม่"}}},
        "too_long": {"http_status": 413, "body": {"status": "error", "error": {"code": "ANSWER_TOO_LONG", "message": "กรุณาย่อคำตอบแล้วลองใหม่"}}},
        "rate_limit": {"http_status": 429, "body": {"status": "error", "error": {"code": "AI_RATE_LIMIT", "message": "กรุณารอสักครู่แล้วลองใหม่"}}},
        "unavailable": {"http_status": 503, "body": {"status": "error", "error": {"code": "MODEL_UNAVAILABLE", "message": "โมเดลยังไม่พร้อมใช้งาน"}}},
    },
}

fixtures["idempotent_replay"] = copy.deepcopy(fixtures["responses"]["probe"])
fixtures["edge_cases"] = {
    "conflicting_model_output": {
        "model_version": "embeddinggemma-coverage-v1",
        "off_topic": {"value": True, "confidence": 0.91},
        "criteria": [
            {"id": "quiet", "status": "covered", "confidence": 0.75},
            {"id": "hide", "status": "missing", "confidence": 0.81},
        ],
    },
    "clarify_response": answer_response(
        1, 1, Q1, "ช่วยอธิบายว่าคำตอบนี้เกี่ยวกับการจัดมุมให้แมวอย่างไร?",
        [a1], [], [
            {"criterion_id": "quiet", "status": "missing", "confidence": 0.75},
            {"criterion_id": "hide", "status": "missing", "confidence": 0.81},
        ], "clarify", False, False, True,
        feedback("unrelated", [], ["กรุณาอธิบายให้ตรงกับคำถาม"], [2]),
        "โมเดลให้ผล off-topic และ covered ขัดกัน",
    ),
}

ROOT.joinpath("fixtures.json").write_text(json.dumps(fixtures, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("Wrote contracts/v1/fixtures.json")
