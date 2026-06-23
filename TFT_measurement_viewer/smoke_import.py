"""Import smoke test for the measurement viewer.

Verifies every module imports cleanly and the shared database can be opened.
Run with::

    python TFT_measurement_viewer/smoke_import.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    """Import all viewer modules and confirm DB connectivity."""
    from TFT_measurement_viewer.bootstrap import config  # noqa: F401
    from TFT_measurement_viewer.logic import data_validator, plot_helpers  # noqa: F401
    from TFT_measurement_viewer.sql import db_ops
    from shared import init_database

    init_database()
    meta = db_ops.load_wafer_metadata()
    print(f"OK: imports succeeded, {len(meta)} wafers visible.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
