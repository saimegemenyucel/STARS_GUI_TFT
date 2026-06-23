"""Database operations for the yield analyzer (reads + metric persistence)."""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

from shared.db import get_connection

logger = logging.getLogger(__name__)

_MEASUREMENT_COLUMNS = [
    "device_id", "position_x", "position_y", "vth", "mobility", "on_off_ratio",
    "subthreshold_swing", "max_drain_current", "leakage_current",
    "is_functional", "defect_type",
]


def load_wafer_metadata() -> pd.DataFrame:
    """Preload one row per wafer with a measured-device count."""
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
    """Load all measurements for one wafer as a DataFrame."""
    cols = ", ".join(_MEASUREMENT_COLUMNS)
    query = f"SELECT {cols} FROM tft_measurements WHERE wafer_id = ? ORDER BY device_id"
    conn = get_connection()
    try:
        df = pd.read_sql_query(query, conn, params=(wafer_id,))
    finally:
        conn.close()
    if not df.empty:
        df["is_functional"] = df["is_functional"].astype("boolean")
    return df


def save_yield_metrics(metrics_row: dict, notes: Optional[str] = None) -> int:
    """Insert a yield metrics row and return its new metric_id.

    Args:
        metrics_row: Mapping with the yield_metrics table columns (e.g. from
            ``YieldMetrics.as_table_row()``).
        notes: Optional free-text note.

    Returns:
        The auto-generated ``metric_id``.
    """
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO yield_metrics
                (wafer_id, total_devices, functional_devices,
                 overall_yield_percentage, vth_pass_count, mobility_pass_count,
                 on_off_ratio_pass_count, defect_density_per_cm2,
                 dominant_defect_type, notes)
            VALUES (:wafer_id, :total_devices, :functional_devices,
                    :overall_yield_percentage, :vth_pass_count,
                    :mobility_pass_count, :on_off_ratio_pass_count,
                    :defect_density_per_cm2, :dominant_defect_type, :notes)
            """,
            {**metrics_row, "notes": notes},
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def load_metric_history(wafer_id: str) -> pd.DataFrame:
    """Return all stored yield_metrics rows for a wafer, newest first."""
    query = """
        SELECT calculation_timestamp, total_devices, functional_devices,
               overall_yield_percentage, defect_density_per_cm2,
               dominant_defect_type, notes
        FROM yield_metrics WHERE wafer_id = ?
        ORDER BY calculation_timestamp DESC
    """
    conn = get_connection()
    try:
        return pd.read_sql_query(query, conn, params=(wafer_id,))
    finally:
        conn.close()
