"""Launch the TFT Measurement Viewer.

Usage::

    python TFT_measurement_viewer/run.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the project root is importable so `shared` and the module package
# resolve regardless of the directory this script is launched from.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from TFT_measurement_viewer.bootstrap.qt_app import run  # noqa: E402


if __name__ == "__main__":
    sys.exit(run())
