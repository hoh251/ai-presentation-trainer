"""Exercise the real checkpoint against model contract v1."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "contracts" / "v1"))
from validate import model as model_schema, schema_check  # noqa: E402
from model_package import ModelInputTooLong, configure_model, predict_attempt, validate_attempt  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-model", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--manifest", default=str(ROOT / "model_package" / "manifest.json"))
    args = parser.parse_args()
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    schema_check(manifest, model_schema["$defs"]["manifest"], model_schema)
    configure_model(args.base_model, args.checkpoint, args.manifest)
    fixtures = json.loads((ROOT / "contracts" / "v1" / "fixtures.json").read_text(encoding="utf-8"))
    question = fixtures["questions"]["q1"]
    cases = [
        ("จัดมุมเงียบ ๆ และมีที่ให้แมวหลบ", False, ["covered", "covered"]),
        ("จัดมุมเงียบ ๆ ให้", False, ["covered", "missing"]),
        ("ไม่รู้ว่ะ มั่ว ๆ ไป", True, ["missing", "missing"]),
    ]
    for answer, expected_off, expected_statuses in cases:
        result = predict_attempt(question, question["text"], question["criteria"], answer)
        schema_check(result, model_schema["$defs"]["output"], model_schema)
        assert result["off_topic"]["value"] is expected_off, result
        assert [item["status"] for item in result["criteria"]] == expected_statuses, result
        assert [item["id"] for item in result["criteria"]] == [item["id"] for item in question["criteria"]]
    try:
        validate_attempt(question, question["text"], question["criteria"], "แมว " * 1000)
    except ModelInputTooLong:
        pass
    else:
        raise AssertionError("The tokenizer did not enforce the 512-token contract")
    print("real checkpoint: manifest, schema, three answers and 512-token rejection passed")


if __name__ == "__main__":
    main()
