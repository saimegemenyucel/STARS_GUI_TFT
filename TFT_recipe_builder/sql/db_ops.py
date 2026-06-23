"""Connection helpers for the recipe builder.

Provides the persistent main-database connection and a throwaway in-memory
'working' connection (initialised with the shared schema) used for the editing
session before changes are committed to the main database.
"""

from __future__ import annotations

import logging
import sqlite3

from shared.db import get_connection
from shared.paths import SCHEMA_PATH

logger = logging.getLogger(__name__)


def open_main_connection() -> sqlite3.Connection:
    """Open a persistent connection to the shared main database."""
    return get_connection()


def create_working_connection() -> sqlite3.Connection:
    """Create an in-memory SQLite DB initialised with the shared schema.

    Used as a scratch 'working database' for the current editing session so the
    recipe can be auto-saved without touching the persistent store.

    Returns:
        An open in-memory connection with all tables created.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()
    return conn
