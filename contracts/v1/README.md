# AI Presentation Trainer — Contract v1

This directory is the **shared handoff** between Person A (Frontend + model training) and Person B (Backend + RAG/Agent). Both sides may work independently after agreeing to this version. The current prototype does **not** implement v1 yet.

## Ownership and boundaries

| Owner | Owns | Sends to other side |
|---|---|---|
| A | `frontend/`, `training/`, `model_package/` | Web App using API v1; labeled data, baseline, fine-tuned `predict_attempt` package, checkpoint/metrics, browser/tunnel validation |
| B | `backend/` | API v1; session state, model adapter, Agent actions, RAG, report and DB |
| Shared | `contracts/v1/` | Changes require both owners to update fixtures and validation before code |

The browser calls only `/api` on the same origin. The Frontend never calls Gemini and never computes scores. The Backend owns session state and calls the model package. `GEMINI_API_KEY` remains in the Backend environment.

## Files

- `api.schema.json`: JSON Schema definitions for API v1 payloads.
- `model.schema.json`: model package input/output and artifact manifest.
- `fixtures.json`: complete example flow and errors.
- `validate.py`: checks the JSON Schema keywords used here, source quotes, IDs and state transitions using only Python stdlib.
- `test_contract.py`: regression tests that reject malformed payloads.

## API rules

Existing routes remain: `POST /api/decks`, `GET /api/decks/{id}/file`, `POST /api/sessions`, `GET /api/sessions/{id}`, `POST /api/sessions/{id}/answers`, `GET /api/sessions/{id}/report`. Add `GET /api/ready` for DB/model/question-service readiness. `POST /api/decks` accepts multipart/form-data field `file` (PDF, 1–10 readable pages) and returns `deck_upload`. `GET /api/decks/{id}/file` returns `application/pdf` bytes, not JSON. `POST /api/sessions` accepts `session_start_request` (`deck_id`, `difficulty`). Successful JSON responses have `status: "ok"` and `contract_version: 1`. Errors use `{ "status":"error", "error": {"code":"...", "message":"..."} }` with an HTTP status. `GET /api/ready` returns HTTP 200 with `status:ok` only when DB, model and question-generation service are ready; otherwise HTTP 503 with `status:unavailable` and readiness booleans. In test mode readiness reports `model_source:test_fake`; it must not be presented as the trained model.

`POST /api/sessions` returns `session_id`, `question`, `current_prompt`, `round=1`, `state_version=0`, `model_source`. Question contains 1–3 criteria; each criterion has stable `id`, `text`, `source_page`, `evidence_quote`. Evidence quote must exist in extracted PDF page text after whitespace normalization. Page numbers start at 1.

Readiness includes `question_service_ready`: in real mode it requires Gemini question generation to be configured and locally initialized; a live provider outage may still surface as 429/503 during a request. Fake question generation is allowed only in clearly labeled test mode. A readiness HTTP 200 requires `database_ready`, `model_ready`, and `question_service_ready` all true.

`POST /api/sessions/{id}/answers` request is `{question_id, attempt_id, state_version, answer}`. `state_version` is the value shown with the current prompt. `attempt_id` is a UUID generated once per submission; retry of the **same** submission reuses the same ID, answer and state version. A new answer, even on the same question, gets a new ID. Backend checks an already committed attempt ID **first**: an exact retry returns its stored response even if the session has advanced; reusing its ID with different question, version or answer returns HTTP 409. A new attempt with a stale state version returns HTTP 409 before model evaluation. This prevents a reply to an old probe prompt being graded against a newer prompt.

Answer response returns `state_version`, `round`, `next_question`, `current_prompt`, `attempts`, `history`, `coverage`, `model_version`, `model_source`, `off_topic`, `agent_action`, `agent_reason`, `counted_round`, `feedback`, `completed`. `next_question` is the full **active canonical question** and may keep the same ID on `probe/retry/clarify`; it is `null` only after finishing. `GET session` returns the same authoritative state using `question` instead of `next_question`.

`round` counts **main questions**, not answer submissions. `probe/retry/clarify` keep the same question ID and round. After at most three attempts, close the round as `complete` or `incomplete`; only then increment round (maximum 3). After closing round 3, `completed=true`, `round=3`, active question and current prompt are `null`. `counted_round=true` means a round was closed, **not** that it was correct. `history` contains closed rounds. `attempts` contains only submissions on the active question; closed-round attempts stay inside `history`.

Backend commits state only after model/Agent/required Gemini work succeeds, using compare-and-swap `state_version` and unique `(session_id, attempt_id)`. On HTTP 429/503 before commit, state does not change. Concurrent stale submissions return 409; Frontend reloads GET session. API total deadline should be below the Frontend's 150-second abort (target ≤120 seconds). Model input is limited to 512 tokens **with the checkpoint tokenizer**. If the static question/criterion prefix is too long, Backend must regenerate before starting the question; if the user's answer exceeds the remaining budget, return HTTP 413 `ANSWER_TOO_LONG` without saving an attempt.

The Frontend displays `current_prompt`, while retaining `question.text` as the main question. It replaces local state from each Backend response and does not append a completed round on every answer. If a replay returns a lower `state_version` than the UI currently holds, Frontend loads `GET session` rather than overwriting newer state. On 409 it reloads state; on 413 it retains the typed answer for editing; on 429/timeout it retains the same attempt ID for retry. Errors preserve HTTP status and `error.code` in the API client.

## Model package rules

Person A supplies `predict_attempt(question, current_prompt, criteria, answer)` and a tokenizer-based `validate_attempt` (or a documented `ModelInputTooLong` exception). The result has `model_version`, `off_topic: {value, confidence}`, and one result per criterion with the **same IDs** and `status: covered|partial|missing`, confidence in `[0,1]`. The package does not import Backend, touch the DB, or call Gemini. Person B validates model IDs and version in the Backend adapter, aggregates coverage across attempts, and owns Agent decisions. A trained LoRA adapter, heads, tokenizer/config, dependency lock and artifact manifest/hash are required for the real-model mode. A fake model is allowed for contract tests only; all session/report responses require `model_source` and `test_mode`, with `test_mode=true` exactly when `model_source=test_fake`.

`off_topic=true` and any `covered` result on the same attempt is a conflict. With fewer than three attempts, Agent chooses `clarify` and does not praise or close the round. Ambiguous/low-confidence outputs follow the same rule. On the **third** attempt, the attempt limit takes precedence: close the round as `incomplete` with `next` (or `finish` on round 3), no unsupported praise, and an `agent_reason` that explains the ambiguity/limit. Previously covered criteria remain in session state when a later off-topic answer arrives, unless the user explicitly corrects their earlier answer and the system confirms the correction.

## Report rules

After three closed rounds, `GET /report` returns `overall` and exactly three `rounds`. Each round has `outcome: complete|incomplete`, `attempts[]`, `answer` summary for legacy display, `coverage`, `feedback`, and `source_pages`. An incomplete round must never appear as fully correct. The UI displays attempts and outcome, not just the summary string.

## Deployment

For local/tunnel use, Vite's development proxy or another same-origin proxy routes `/api` to the Backend. The current Frontend's `|| 'http://localhost:8000'` fallback must be changed; an empty env value does not override `||`. A production `dist/` build needs a reverse proxy or Backend static serving: Vite's dev proxy is not bundled. Use the actual tunnel hostname in Vite `allowedHosts` when appropriate. A browser on another device must be tested with PDF preview and `/api`, not only the home page.

This contract is **not proof of implementation**. Both sides must run fixture/schema tests independently, then test the merged system with a new PDF, multiple attempts, 409/413/429/503, refresh, report, restart and a remote browser.
