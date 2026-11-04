"""Deterministic Agent policy. Gemini never assigns or overrides coverage."""
from copy import deepcopy


def initial_coverage(question):
    return [dict(criterion_id=c["id"], status="missing", confidence=0.0) for c in question["criteria"]]


def decide(previous, prediction, attempt_count, thresholds):
    coverage = deepcopy(previous)
    by_id = {c["criterion_id"]: c for c in coverage}
    off = prediction["off_topic"]
    conflict = off["value"] and any(c["status"] == "covered" for c in prediction["criteria"])
    uncertain = conflict or off["confidence"] < thresholds["off_topic"] or any(
        c["confidence"] < thresholds["coverage"] for c in prediction["criteria"])
    # Off-topic or ambiguous answers cannot erase or add confirmed coverage.
    if not off["value"] and not uncertain:
        ranks = {"missing": 0, "partial": 1, "covered": 2}
        for item in prediction["criteria"]:
            old = by_id[item["id"]]
            if ranks[item["status"]] > ranks[old["status"]] or (
                item["status"] == old["status"] and item["confidence"] > old["confidence"]
            ):
                old.update(status=item["status"], confidence=item["confidence"])
    if uncertain:
        action, reason = "clarify", "ผลโมเดลไม่ชัดเจนหรือขัดกัน กรุณาอธิบายเพิ่ม"
    elif off["value"]:
        action, reason = "retry", "คำตอบยังไม่เกี่ยวข้องกับคำถาม"
    elif all(c["status"] == "covered" for c in coverage):
        return coverage, "close", "complete", "ครอบคลุมเกณฑ์ที่ตรวจยืนยันแล้ว"
    else:
        action, reason = "probe", "ยังมีเกณฑ์ที่ตอบไม่ครบ"
    if attempt_count >= 3:
        return coverage, "close", "incomplete", reason + " และครบโอกาสตอบ 3 ครั้งแล้ว"
    return coverage, action, None, reason


def feedback(question, coverage, action, off_topic):
    by_id = {c["criterion_id"]: c["status"] for c in coverage}
    covered = [c["text"] for c in question["criteria"] if by_id[c["id"]] == "covered"]
    missing = [c["text"] for c in question["criteria"] if by_id[c["id"]] != "covered"]
    # Conservative feedback is generated from confirmed evidence, never free-form praise.
    return dict(
        relevance="unrelated" if off_topic else ("partial" if missing else "relevant"),
        strengths=[] if action in {"retry", "clarify"} or off_topic else ["ตอบครอบคลุม: " + t for t in covered],
        improvements=["อธิบายเพิ่มเรื่อง: " + t for t in missing],
        source_pages=question["source_pages"],
    )


def report_summary(rounds):
    complete = sum(r["outcome"] == "complete" for r in rounds)
    return dict(
        summary=f"ตอบครบเกณฑ์ {complete} จาก 3 คำถามหลัก",
        strengths=[f"คำถามที่ {r['round']}: ตอบครบเกณฑ์" for r in rounds if r["outcome"] == "complete"],
        improvements=[f"คำถามที่ {r['round']}: ยังตอบไม่ครบหรือผลไม่ชัดเจน" for r in rounds if r["outcome"] == "incomplete"],
    )
