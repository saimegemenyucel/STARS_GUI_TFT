"""Central filesystem locations for the TFT Analysis System.

Using :mod:`pathlib` everywhere keeps path handling portable between
Windows (the target deployment) and POSIX systems used for testing.
"""

from __future__ import annotations

import os
from pathlib import Path

# Repository root = the directory that contains this ``shared`` package.
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent

# Single shared SQLite database used by every module.
# Can be overridden with the TFT_DB_PATH environment variable (useful for tests).
DB_PATH: Path = Path(os.environ.get("TFT_DB_PATH", PROJECT_ROOT / "TFT_Database.db"))

# Canonical schema definition.
SCHEMA_PATH: Path = PROJECT_ROOT / "shared" / "schema.sql"

__all__ = ["PROJECT_ROOT", "DB_PATH", "SCHEMA_PATH"]
