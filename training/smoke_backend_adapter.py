"""Load Person A's private artifact through the unmodified Backend adapter.

Pass a local checkout of the teammate's Backend PR. This script does not edit
that checkout, call Gemini, or upload model weights.
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend-root", type=Path, required=True)
    parser.add_argument("--base-model", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(1, str(args.backend_root.resolve()))
    os.environ["MODEL_BASE_PATH"] = str(args.base_model.resolve())

    from backend.config import Settings  # noqa: PLC0415
    from backend.coverage_service import CoverageService  # noqa: PLC0415

    service = CoverageService(Settings(artifacts=args.artifact_dir.resolve()))
    await asyncio.to_thread(service.load)
    if not service.ready:
        raise RuntimeError(f"Backend adapter failed to load: {service.load_error}")

    fixtures = json.loads((ROOT / "contracts/v1/fixtures.json").read_text(encoding="utf-8"))
    question = fixtures["questions"]["q1"]
    await service.validate(question, question["text"], "จัดมุมเงียบ ๆ และมีที่ให้แมวหลบ")
    result = await service.predict(question, question["text"], "จัดมุมเงียบ ๆ และมีที่ให้แมวหลบ")
    assert result["model_version"] == service.version
    assert [criterion["status"] for criterion in result["criteria"]] == ["covered", "covered"]
    assert [criterion["id"] for criterion in result["criteria"]] == [criterion["id"] for criterion in question["criteria"]]
    print(json.dumps({"ready": service.ready, "model_version": service.version,
                      "statuses": [c["status"] for c in result["criteria"]],
                      "gates": {name: service.thresholds[name] for name in ("coverage", "off_topic")}},
                     ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
