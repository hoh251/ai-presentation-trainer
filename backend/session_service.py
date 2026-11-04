from copy import deepcopy
from uuid import uuid4

from .agent import decide, feedback, initial_coverage, report_summary
from .contract import check
from .errors import APIError, conflict, unavailable


class SessionService:
    def __init__(self, store, model, questions):
        self.store, self.model, self.questions = store, model, questions

    def ensure_ready(self):
        if not self.store.ready():
            raise unavailable("DATABASE_UNAVAILABLE", "ฐานข้อมูลยังไม่พร้อม")
        if not self.model.ready:
            raise unavailable(getattr(self.model, "load_error_code", None) or "MODEL_UNAVAILABLE")
        if not self.questions.ready:
            raise unavailable("QUESTION_SERVICE_UNAVAILABLE", "บริการสร้างคำถามยังไม่พร้อม")

    def mode(self):
        return dict(model_source=self.model.source, test_mode=self.model.settings.test_mode)

    async def start(self, request):
        self.ensure_ready()
        deck = self.store.deck(request["deck_id"])
        question = await self.questions.create(deck, request["difficulty"], 1, [])
        sid = str(uuid4())
        state = dict(status="ok", contract_version=1, deck_id=deck["id"], filename=deck["filename"],
                     page_count=len(deck["pages"]), difficulty=request["difficulty"], round=1, question=question,
                     current_prompt=question["text"], attempts=[], history=[], coverage=initial_coverage(question),
                     state_version=0, completed=False, **self.mode())
        response = dict(status="ok", contract_version=1, session_id=sid, round=1, question=question,
                        current_prompt=question["text"], state_version=0, **self.mode())
        check(state, "session_state")
        check(response, "session_start")
        self.store.create_session(sid, state, self.model.identity)
        return response

    async def answer(self, sid, request):
        # Replay precedes readiness and current-state checks (including after a restart).
        replay = self.store.replay(sid, request)
        if replay is not None:
            return replay
        state, model_version = self.store.session(sid)
        if state["completed"] or state["state_version"] != request["state_version"] or state["question"]["id"] != request["question_id"]:
            raise conflict()
        self.ensure_ready()
        if state["model_source"] != self.model.source or model_version != self.model.identity:
            raise unavailable("SESSION_MODEL_CHANGED", "โมเดลเปลี่ยนรุ่น กรุณาเริ่มรอบซ้อมใหม่")
        question = state["question"]
        raw = await self.model.predict(question, state["current_prompt"], request["answer"])
        coverage, action, outcome, reason = decide(state["coverage"], raw, len(state["attempts"]) + 1, self.model.thresholds)
        original_action = action
        if action == "close":
            action = "finish" if state["round"] == 3 else "next"
        attempt = dict(attempt_id=request["attempt_id"], prompt_at_attempt=state["current_prompt"],
                       answer=request["answer"], agent_action=action)
        current_attempts = [*state["attempts"], attempt]
        fb = feedback(question, coverage, original_action, raw["off_topic"]["value"])
        # Ambiguity on attempt 3 must not produce praise either.
        if outcome == "incomplete" and (raw["off_topic"]["value"] or "ไม่ชัดเจน" in reason):
            fb["strengths"] = []
        updated = deepcopy(state)
        updated["state_version"] += 1
        closed = None
        if outcome is not None:
            closed = dict(round=state["round"], question=question, outcome=outcome, attempts=current_attempts,
                          answer="\n".join(a["answer"] for a in current_attempts), coverage=coverage,
                          feedback=fb, source_pages=question["source_pages"])
            updated["history"].append(closed)
            updated["attempts"] = []
            if action == "finish":
                updated.update(completed=True, question=None, current_prompt=None, coverage=[])
            else:
                deck = self.store.deck(state["deck_id"])
                next_question = await self.questions.create(deck, state["difficulty"], state["round"] + 1, updated["history"])
                updated.update(round=state["round"] + 1, question=next_question, current_prompt=next_question["text"],
                               coverage=initial_coverage(next_question))
        else:
            prompt = await self.questions.prompt(question, coverage, action)
            updated.update(attempts=current_attempts, coverage=coverage, current_prompt=prompt)
        response = dict(status="ok", contract_version=1, state_version=updated["state_version"], round=updated["round"],
                        next_question=updated["question"], current_prompt=updated["current_prompt"],
                        attempts=updated["attempts"], history=updated["history"], coverage=updated["coverage"],
                        model_version=self.model.version, off_topic=raw["off_topic"], agent_action=action,
                        agent_reason=reason, counted_round=outcome is not None, feedback=fb,
                        completed=updated["completed"], **self.mode())
        check(updated, "session_state")
        check(response, "answer_response")
        return self.store.commit_answer(sid, request, updated, response, raw, closed)

    def report(self, sid):
        state, _ = self.store.session(sid)
        if not state["completed"]:
            raise APIError(409, "SESSION_NOT_COMPLETED", "กรุณาซ้อมให้ครบ 3 รอบก่อนดูรายงาน")
        result = dict(status="ok", contract_version=1, rounds=state["history"], overall=report_summary(state["history"]),
                      model_source=state["model_source"], test_mode=state["test_mode"])
        check(result, "report")
        return result
