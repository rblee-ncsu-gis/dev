"""Run the existing package CLI without installing it or changing PYTHONPATH."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from asbuilt_matcher.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
