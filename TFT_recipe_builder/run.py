"""Launch the TFT Recipe Builder."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from TFT_recipe_builder.bootstrap.qt_app import run  # noqa: E402


if __name__ == "__main__":
    sys.exit(run())
