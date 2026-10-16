"""Run directly from a cloned ArcGIS Pro environment; no install needed."""

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from asbuilt_matcher.environment import check_environment

if __name__ == "__main__":
    result = check_environment()
    print(json.dumps(result, indent=2, default=str))
    raise SystemExit(0 if result["pdf_ready"] else 1)
