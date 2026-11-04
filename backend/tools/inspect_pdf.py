"""Write private, offline diagnostics; does not index pages or call Vision."""
import argparse
import json
from pathlib import Path

from backend.config import ROOT
from backend.pdf_inspection import inspect_pdf

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / ".integration/pdf-inspection.json")
    args = parser.parse_args()
    result = inspect_pdf(args.pdf.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "pages"}))
