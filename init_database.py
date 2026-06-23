"""Create (or upgrade) the shared TFT_Database.db.

Run this once before launching any module::

    python init_database.py

It is safe to run repeatedly; existing data is preserved.
"""

from __future__ import annotations

import logging
import sys

from shared import init_database
from shared.paths import DB_PATH


def main() -> int:
    """Initialize the shared database and report the location."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    path = init_database()
    print(f"TFT database ready at: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
