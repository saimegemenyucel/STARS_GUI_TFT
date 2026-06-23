"""Database connection management and one-time initialization.

All three modules import :func:`get_connection` so that foreign-key
enforcement and row-factory behaviour are configured identically everywhere.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Optional

from shared.paths import DB_PATH, SCHEMA_PATH

logger = logging.getLogger(__name__)


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Open a configured SQLite connection.

    The connection is returned with ``sqlite3.Row`` as the row factory (so
    columns can be accessed by name) and ``PRAGMA foreign_keys`` enabled.

    Args:
        db_path: Optional explicit database path. Defaults to the shared
            :data:`shared.paths.DB_PATH`.

    Returns:
        An open :class:`sqlite3.Connection`.
    """
    path = Path(db_path) if db_path is not None else DB_PATH
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_database(
    db_path: Optional[Path] = None,
    seed_default_criteria: bool = True,
) -> Path:
    """Create the database file and all tables if they do not yet exist.

    This is idempotent: running it against an existing database leaves data
    untouched because every statement in ``schema.sql`` uses
    ``CREATE TABLE IF NOT EXISTS``.

    Args:
        db_path: Optional explicit database path. Defaults to the shared
            :data:`shared.paths.DB_PATH`.
        seed_default_criteria: When ``True`` and the ``quality_criteria``
            table is empty, insert a sensible default set of pass/fail
            thresholds so the yield analyzer has something to work with.

    Returns:
        The path to the initialized database.

    Raises:
        FileNotFoundError: If the schema file cannot be located.
    """
    path = Path(db_path) if db_path is not None else DB_PATH

    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"Schema file not found: {SCHEMA_PATH}")

    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")

    conn = get_connection(path)
    try:
        conn.executescript(schema_sql)
        conn.commit()
        if seed_default_criteria:
            _seed_default_criteria(conn)
        logger.info("Database initialized at %s", path)
    finally:
        conn.close()
    return path


# Default quality criteria for a typical IGZO TFT process.
# These are starting points the user can edit in the database.
_DEFAULT_CRITERIA: list[tuple[str, float, float, float, str]] = [
    ("vth_min", -2.0, -2.0, 2.0, "Threshold voltage lower bound (V)"),
    ("vth_max", 2.0, -2.0, 2.0, "Threshold voltage upper bound (V)"),
    ("mobility_min", 5.0, 5.0, 50.0, "Minimum carrier mobility (cm^2/Vs)"),
    ("on_off_ratio_min", 6.0, 6.0, 12.0, "Minimum Ion/Ioff (log10)"),
    ("subthreshold_swing_max", 500.0, 60.0, 500.0, "Maximum SS (mV/dec)"),
    ("leakage_current_max", 1e-9, 0.0, 1e-9, "Maximum off-state leakage (A)"),
]


def _seed_default_criteria(conn: sqlite3.Connection) -> None:
    """Insert default quality criteria only when the table is empty."""
    count = conn.execute("SELECT COUNT(*) FROM quality_criteria").fetchone()[0]
    if count:
        return
    conn.executemany(
        """
        INSERT INTO quality_criteria
            (parameter_name, target_value, tolerance_lower, tolerance_upper,
             is_active, description)
        VALUES (?, ?, ?, ?, 1, ?)
        """,
        _DEFAULT_CRITERIA,
    )
    conn.commit()
    logger.info("Seeded %d default quality criteria", len(_DEFAULT_CRITERIA))
