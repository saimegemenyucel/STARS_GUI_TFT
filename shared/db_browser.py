"""Read-only queries that power the Database Browser.

Aggregates the contents of the shared database (wafers, ingested I-V sweeps with
their die/transistor metadata and computed features, recipes, yield metrics) so
a single tree view can show everything currently stored.
"""

from __future__ import annotations

import logging
import sqlite3

import pandas as pd

logger = logging.getLogger(__name__)


def table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """Return a row count for each main table (missing tables count as 0)."""
    tables = ["wafers", "tft_measurements", "iv_sweeps", "iv_runs", "iv_points",
              "recipes", "recipe_steps", "yield_metrics", "tft_curve_features"]
    counts: dict[str, int] = {}
    for t in tables:
        try:
            counts[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        except sqlite3.Error:
            counts[t] = 0
    return counts


def get_wafers(conn: sqlite3.Connection) -> pd.DataFrame:
    """Wafer headers with measured-device counts."""
    return pd.read_sql_query(
        """
        SELECT w.*,
               (SELECT COUNT(*) FROM tft_measurements m WHERE m.wafer_id = w.wafer_id)
                   AS measured_count
        FROM wafers w ORDER BY w.wafer_id
        """,
        conn,
    )


def get_sweeps(conn: sqlite3.Connection) -> pd.DataFrame:
    """Ingested sweeps with run/point counts and any computed features.

    Sorted by die → transistor → sweep so the browser can group them.
    """
    query = """
        SELECT s.sweep_id, s.source_file, s.sweep_type, s.run_start,
               s.die_col_row, s.subdie_col_row, s.channel_length, s.channel_width,
               s.material_stack, s.instrument_ch, s.temperature_c, s.extra_temp_c,
               s.wafer_id, s.imported_at,
               (SELECT COUNT(*) FROM iv_runs r WHERE r.sweep_id = s.sweep_id) AS runs,
               (SELECT COUNT(*) FROM iv_points p JOIN iv_runs r ON p.run_id = r.run_id
                 WHERE r.sweep_id = s.sweep_id) AS points,
               f.vth, f.mu_sat, f.ss_min, f.on_off_ratio
        FROM iv_sweeps s
        LEFT JOIN tft_curve_features f ON f.sweep_id = s.sweep_id
        ORDER BY s.die_col_row, s.subdie_col_row, s.sweep_type, s.run_start
    """
    try:
        return pd.read_sql_query(query, conn)
    except sqlite3.Error:
        return pd.DataFrame()


def get_recipes(conn: sqlite3.Connection) -> pd.DataFrame:
    """Recipe headers with step counts."""
    return pd.read_sql_query(
        """
        SELECT r.*,
               (SELECT COUNT(*) FROM recipe_steps s WHERE s.recipe_id = r.recipe_id)
                   AS step_count
        FROM recipes r ORDER BY r.recipe_name
        """,
        conn,
    )


def get_recipe_steps(conn: sqlite3.Connection, recipe_id: int) -> pd.DataFrame:
    """Ordered steps for one recipe."""
    return pd.read_sql_query(
        "SELECT * FROM recipe_steps WHERE recipe_id = ? ORDER BY step_order",
        conn, params=(recipe_id,),
    )


def get_yield_metrics(conn: sqlite3.Connection) -> pd.DataFrame:
    """All stored yield-metric rows."""
    return pd.read_sql_query(
        "SELECT * FROM yield_metrics ORDER BY calculation_timestamp DESC", conn
    )
