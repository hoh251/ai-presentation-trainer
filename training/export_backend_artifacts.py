"""Export private model weights into PR #3's artifact layout.

The output is not for Git. MODEL_BASE_PATH still points to separately obtained
Google base weights. Confidence gates come from validation calibration.
"""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--gates", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Output already exists; choose a new private directory")
    manifest = json.loads((ROOT / "model_package/manifest.json").read_text(encoding="utf-8"))
    adapter = args.checkpoint / "adapter_model.safetensors"
    if sha(adapter) != manifest["checkpoint_sha256"]:
        raise SystemExit("Adapter hash differs from frozen manifest")
    for dirname, expected in manifest["dense_sha256"].items():
        if sha(args.checkpoint / dirname / "model.safetensors") != expected:
            raise SystemExit(f"{dirname} hash differs from frozen manifest")
    gates = json.loads(args.gates.read_text(encoding="utf-8"))
    if not all(0 < gates[name] <= 1 for name in ("coverage", "off_topic")):
        raise SystemExit("Validation-derived confidence gates are required")
    args.output.mkdir(parents=True)
    try:
        shutil.copytree(args.checkpoint, args.output / "checkpoint")
        manifest["checkpoint_file"] = "checkpoint/adapter_model.safetensors"
        (args.output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        (args.output / "thresholds.json").write_text(json.dumps(gates, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        # Retain the partial private directory for inspection; do not delete it.
        raise
    print(json.dumps({"artifact_dir": str(args.output.resolve()), "model_version": manifest["model_version"],
                      "checkpoint_sha256": manifest["checkpoint_sha256"], "gates": {k: gates[k] for k in ("coverage", "off_topic")}},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
