"""Read-oriented database operations for the measurement viewer.

The viewer never mutates measurement data; it preloads lightweight wafer
metadata at startup and lazily loads the (potentially large) per-wafer
measurement set only when a wafer is selected.
"""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

from shared.db import get_connection

logger = logging.getLogger(__name__)

# Columns pulled for the measurement table / plots, in display order.
MEASUREMENT_COLUMNS: list[str] = [
    "device_id",
    "position_x",
    "position_y",
    "vth",
    "mobility",
    "on_off_ratio",
    "subthreshold_swing",
    "max_drain_current",
    "leakage_current",
    "is_functional",
    "defect_type",
    "notes",
]


def load_wafer_metadata() -> pd.DataFrame:
    """Preload one row per wafer with a measured-device count.

    Returns:
        DataFrame with wafer header columns plus ``measured_count``. Empty if
        there are no wafers.
    """
    query = """
        SELECT w.*,
               (SELECT COUNT(*) FROM tft_measurements m
                 WHERE m.wafer_id = w.wafer_id) AS measured_count
        FROM wafers w
        ORDER BY w.fabrication_date DESC, w.wafer_id
    """
    conn = get_connection()
    try:
        return pd.read_sql_query(query, conn)
    finally:
        conn.close()


def load_measurements(wafer_id: str) -> pd.DataFrame:
    """Load all measurements for one wafer.

    Args:
        wafer_id: The wafer to load.

    Returns:
        DataFrame with :data:`MEASUREMENT_COLUMNS`. Empty if the wafer has no
        measurements.
    """
    cols = ", ".join(MEASUREMENT_COLUMNS)
    query = f"SELECT {cols} FROM tft_measurements WHERE wafer_id = ? ORDER BY device_id"
    conn = get_connection()
    try:
        df = pd.read_sql_query(query, conn, params=(wafer_id,))
    finally:
        conn.close()
    if not df.empty:
        df["is_functional"] = df["is_functional"].astype("boolean")
    return df


def get_wafer_header(wafer_id: str) -> Optional[dict]:
    """Return a single wafer's header row as a dict, or ``None`` if missing."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM wafers WHERE wafer_id = ?", (wafer_id,)
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row is not None else None


def list_defect_types(wafer_id: str) -> list[str]:
    """List the distinct non-null defect types present on a wafer."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT defect_type FROM tft_measurements
            WHERE wafer_id = ? AND defect_type IS NOT NULL
            ORDER BY defect_type
            """,
            (wafer_id,),
        ).fetchall()
    finally:
        conn.close()
    return [r[0] for r in rows]
