"""Validate the shared v1 examples without third-party dependencies."""
from __future__ import annotations

import json
import re
from pathlib import Path
from uuid import UUID


ROOT = Path(__file__).resolve().parent
api = json.loads(ROOT.joinpath("api.schema.json").read_text(encoding="utf-8"))
model = json.loads(ROOT.joinpath("model.schema.json").read_text(encoding="utf-8"))
fixtures = json.loads(ROOT.joinpath("fixtures.json").read_text(encoding="utf-8"))


def schema_check(value, rule: dict, schema: dict = api, path: str = "root") -> None:
    """Check all JSON Schema keywords used by these two local contracts."""
    if "$ref" in rule:
        ref = rule["$ref"]
        target = api if ref.startswith("api.schema.json#") else schema
        name = ref.rsplit("/", 1)[-1]
        assert name in target["$defs"], f"{path}: unresolved ref {ref}"
        schema_check(value, target["$defs"][name], target, path)
        return
    if "anyOf" in rule:
        for option in rule["anyOf"]:
            try:
                schema_check(value, option, schema, path)
                break
            except AssertionError:
                pass
        else:
            raise AssertionError(f"{path}: no anyOf branch matched")
    if "const" in rule:
        assert value == rule["const"], f"{path}: wrong constant"
    if "enum" in rule:
        assert value in rule["enum"], f"{path}: invalid enum {value!r}"
    if "type" in rule:
        allowed = rule["type"] if isinstance(rule["type"], list) else [rule["type"]]
        matches = {
            "object": lambda: isinstance(value, dict),
            "array": lambda: isinstance(value, list),
            "string": lambda: isinstance(value, str),
            "integer": lambda: type(value) is int,
            "number": lambda: type(value) in (int, float),
            "boolean": lambda: type(value) is bool,
            "null": lambda: value is None,
        }
        assert any(matches[kind]() for kind in allowed), f"{path}: expected {allowed}, got {type(value).__name__}"
    if isinstance(value, dict):
        assert set(rule.get("required", [])) <= value.keys(), f"{path}: missing fields"
        for key, child in rule.get("properties", {}).items():
            if key in value:
                schema_check(value[key], child, schema, f"{path}.{key}")
    if isinstance(value, list):
        assert len(value) >= rule.get("minItems", 0), f"{path}: too few items"
        assert len(value) <= rule.get("maxItems", len(value)), f"{path}: too many items"
        if "items" in rule:
            for index, item in enumerate(value):
                schema_check(item, rule["items"], schema, f"{path}[{index}]")
    if isinstance(value, str):
        assert len(value) >= rule.get("minLength", 0), f"{path}: too short"
        if "pattern" in rule:
            assert re.search(rule["pattern"], value), f"{path}: pattern mismatch"
        if rule.get("format") == "uuid":
            UUID(value)
    if type(value) in (int, float):
        assert value >= rule.get("minimum", value), f"{path}: below minimum"
        assert value <= rule.get("maximum", value), f"{path}: above maximum"


def check(value, definition: str, schema: dict = api) -> None:
    schema_check(value, schema["$defs"][definition], schema, definition)


def required(value: dict, definition: str, schema: dict = api) -> None:
    missing = set(schema["$defs"][definition]["required"]) - set(value)
    assert not missing, f"{definition}: missing {sorted(missing)}"


def question(value: dict) -> None:
    required(value, "question")
    assert 1 <= len(value["criteria"]) <= 3
    assert len({item["id"] for item in value["criteria"]}) == len(value["criteria"])
    for item in value["criteria"]:
        required(item, "criterion")
        assert item["source_page"] in value["source_pages"]
        assert item["evidence_quote"].strip()


def coverage(value: list[dict], q: dict) -> None:
    assert {item["criterion_id"] for item in value} == {item["id"] for item in q["criteria"]}
    for item in value:
        required(item, "coverage")
        assert item["status"] in ("covered", "partial", "missing")
        assert 0 <= item["confidence"] <= 1


def attempts(value: list[dict]) -> None:
    assert len(value) <= 3
    for item in value:
        required(item, "attempt")
        UUID(item["attempt_id"])
        assert item["agent_action"] in ("probe", "retry", "clarify", "next", "finish")


def history(value: list[dict]) -> None:
    assert len(value) <= 3
    for index, item in enumerate(value, 1):
        required(item, "closed_round")
        assert item["round"] == index
        assert item["outcome"] in ("complete", "incomplete")
        question(item["question"])
        attempts(item["attempts"])
        coverage(item["coverage"], item["question"])
        required(item["feedback"], "feedback")


for name, value in fixtures["questions"].items():
    check(value, "question")
    question(value)

assert len(fixtures["deck_pages"]) == fixtures["deck_upload"]["page_count"]
for item in fixtures["questions"].values():
    for criterion in item["criteria"]:
        page = fixtures["deck_pages"][criterion["source_page"] - 1]
        assert " ".join(criterion["evidence_quote"].split()) in " ".join(page.split())

check(fixtures["deck_upload"], "deck_upload")
required(fixtures["deck_upload"], "deck_upload")
assert fixtures["deck_upload"]["page_count"] in range(1, 11)
required(fixtures["session_start_request"], "session_start_request")
check(fixtures["session_start_request"], "session_start_request")
assert fixtures["session_start_request"]["deck_id"] == fixtures["deck_upload"]["deck_id"]
required(fixtures["readiness"], "readiness")
check(fixtures["readiness"], "readiness")
assert fixtures["readiness"]["database_ready"] and fixtures["readiness"]["model_ready"] and fixtures["readiness"]["question_service_ready"]

start = fixtures["session_start"]
required(start, "session_start")
check(start, "session_start")
assert start["contract_version"] == 1 and start["state_version"] == 0
assert start["current_prompt"] == start["question"]["text"]
question(start["question"])

required(fixtures["model_input"], "input", model)
required(fixtures["model_output"], "output", model)
check(fixtures["model_input"], "input", model)
check(fixtures["model_output"], "output", model)
check(fixtures["manifest_example"], "manifest", model)
assert fixtures["manifest_example"]["example_only"] is True
assert {item["id"] for item in fixtures["model_output"]["criteria"]} == {item["id"] for item in fixtures["model_input"]["criteria"]}
for item in fixtures["model_output"]["criteria"]:
    assert item["status"] in ("covered", "partial", "missing")
    assert 0 <= item["confidence"] <= 1

for value in fixtures["answer_requests"].values():
    required(value, "answer_request")
    check(value, "answer_request")
    UUID(value["attempt_id"])

responses = fixtures["responses"]
order = ["probe", "next", "retry", "retry_again", "incomplete", "finish"]
versions = []
for name in order:
    value = responses[name]
    required(value, "answer_response")
    check(value, "answer_response")
    assert value["status"] == "ok" and value["contract_version"] == 1
    assert value["agent_action"] in ("probe", "retry", "clarify", "next", "finish")
    assert 0 <= value["off_topic"]["confidence"] <= 1
    assert value["model_source"] in ("local_finetuned", "test_fake")
    assert value["test_mode"] == (value["model_source"] == "test_fake")
    attempts(value["attempts"])
    history(value["history"])
    if value["next_question"]:
        question(value["next_question"])
        coverage(value["coverage"], value["next_question"]) if value["coverage"] else None
    versions.append(value["state_version"])
assert versions == sorted(set(versions)), "state_version must increase"
assert versions == list(range(1, 7)), "each committed answer increments state_version exactly once"
assert [item["state_version"] for item in fixtures["answer_requests"].values()] == list(range(6))
request_names = ["first", "follow_up", "third", "fourth", "fifth", "sixth"]
active_question = start["question"]
active_prompt = start["current_prompt"]
active_version = start["state_version"]
active_round = start["round"]
for request_name, response_name in zip(request_names, order):
    request = fixtures["answer_requests"][request_name]
    response = responses[response_name]
    assert request["question_id"] == active_question["id"], request_name
    assert request["state_version"] == active_version, request_name
    assert response["state_version"] == active_version + 1, response_name
    assert response["round"] == active_round + int(response["counted_round"] and active_round < 3), response_name
    assert response["completed"] == (response_name == "finish"), response_name
    expected_attempt = next(
        (item for item in response["attempts"] if item["attempt_id"] == request["attempt_id"]),
        None,
    )
    if expected_attempt is None:
        expected_attempt = response["history"][-1]["attempts"][-1]
    assert expected_attempt["attempt_id"] == request["attempt_id"]
    assert expected_attempt["answer"] == request["answer"]
    assert expected_attempt["prompt_at_attempt"] == active_prompt
    active_question = response["next_question"]
    active_prompt = response["current_prompt"]
    active_version = response["state_version"]
    active_round = response["round"]
assert [item["attempt_id"] for item in fixtures["answer_requests"].values()] == [
    attempt["attempt_id"] for round_attempts in (
        responses["next"]["history"][0]["attempts"],
        responses["incomplete"]["history"][1]["attempts"],
        responses["finish"]["history"][2]["attempts"],
    ) for attempt in round_attempts
]
assert responses["probe"]["round"] == 1 and not responses["probe"]["counted_round"]
assert responses["probe"]["next_question"]["id"] == start["question"]["id"]
assert responses["next"]["round"] == 2 and responses["next"]["counted_round"]
assert responses["next"]["next_question"]["id"] != start["question"]["id"]
assert responses["retry"]["round"] == 2 and not responses["retry"]["counted_round"]
assert responses["retry_again"]["round"] == 2 and not responses["retry_again"]["counted_round"]
assert len(responses["retry_again"]["attempts"]) == 2
assert responses["incomplete"]["history"][-1]["outcome"] == "incomplete"
assert responses["finish"]["completed"] and responses["finish"]["next_question"] is None
assert responses["finish"]["round"] == 3 and len(responses["finish"]["history"]) == 3
assert all(item["status"] == "covered" for item in responses["finish"]["history"][0]["coverage"])
assert responses["finish"]["history"][1]["outcome"] == "incomplete"
assert any(item["status"] != "covered" for item in responses["finish"]["history"][1]["coverage"])

state = fixtures["session_state_after_probe"]
required(state, "session_state")
check(state, "session_state")
question(state["question"])
attempts(state["attempts"])
coverage(state["coverage"], state["question"])
assert state["state_version"] == responses["probe"]["state_version"]
assert state["test_mode"] == (state["model_source"] == "test_fake")

report = fixtures["report"]
required(report, "report")
check(report, "report")
assert report["test_mode"] == (report["model_source"] == "test_fake")
assert len(report["rounds"]) == 3
history(report["rounds"])
assert report["rounds"] == responses["finish"]["history"]

for name, value in fixtures["errors"].items():
    assert value["http_status"] in (409, 413, 429, 503), name
    required(value["body"], "error")
    check(value["body"], "error")
    assert value["body"]["status"] == "error"
    assert value["body"]["error"]["code"]

assert fixtures["idempotent_replay"] == responses["probe"]
conflict = fixtures["edge_cases"]["conflicting_model_output"]
clarify = fixtures["edge_cases"]["clarify_response"]
check(conflict, "output", model)
check(clarify, "answer_response")
assert conflict["off_topic"]["value"] and any(item["status"] == "covered" for item in conflict["criteria"])
assert clarify["agent_action"] == "clarify" and not clarify["counted_round"]
assert clarify["feedback"]["strengths"] == []

print("Contract v1 fixtures and transitions: OK")
