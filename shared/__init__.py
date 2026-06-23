"""Shared infrastructure for the TFT Analysis System.

Exposes the common database location and a small set of helpers that all
three GUI modules (measurement viewer, yield analyzer, recipe builder) use
to talk to the single shared ``TFT_Database.db`` file.
"""

from shared.paths import DB_PATH, PROJECT_ROOT, SCHEMA_PATH
from shared.db import get_connection, init_database

__all__ = [
    "DB_PATH",
    "PROJECT_ROOT",
    "SCHEMA_PATH",
    "get_connection",
    "init_database",
]
