"""Runtime validation uses the supplied schemas without executing supplied scripts."""
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parent.parent / "contracts" / "v1"
API = json.loads((ROOT / "api.schema.json").read_text(encoding="utf-8"))
MODEL = json.loads((ROOT / "model.schema.json").read_text(encoding="utf-8"))
REGISTRY = Registry().with_resources([
    ("api.schema.json", Resource.from_contents(API)),
    ("model.schema.json", Resource.from_contents(MODEL)),
])


def check(value, definition, model=False):
    source = MODEL if model else API
    schema = {"$ref": f"{source['$id']}#/$defs/{definition}"}
    Draft202012Validator(schema, registry=REGISTRY, format_checker=FormatChecker()).validate(value)


def normalize(text):
    return " ".join(text.split())


def validate_question(question, pages):
    check(question, "question")
    ids = [c["id"] for c in question["criteria"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate criterion IDs")
    if any(not 1 <= p <= len(pages) for p in question["source_pages"]):
        raise ValueError("Invalid question source page")
    for c in question["criteria"]:
        p = c["source_page"]
        if p not in question["source_pages"] or not 1 <= p <= len(pages):
            raise ValueError("Invalid evidence page")
        quote = normalize(c["evidence_quote"])
        if not quote or quote not in normalize(pages[p - 1]):
            raise ValueError("Evidence quote not found")
