"""Import smoke test for the yield analyzer."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    from TFT_yield_analyzer.bootstrap import config  # noqa: F401
    from TFT_yield_analyzer.logic import yield_calculator, statistics, clustering  # noqa: F401
    from TFT_yield_analyzer.sql import db_ops
    from shared import init_database

    init_database()
    meta = db_ops.load_wafer_metadata()
    print(f"OK: imports succeeded, {len(meta)} wafers visible.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
