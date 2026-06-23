"""Persist and read TFT parameters computed from raw I-V sweeps.

This closes the loop with :mod:`shared.tft_analysis`: the analysis engine
extracts features in memory, and these helpers write them into the
``tft_curve_features`` table so every GUI can read the same derived values.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Optional

import pandas as pd

from shared.tft_analysis import TransferFeatures

logger = logging.getLogger(__name__)


def save_transfer_features(
    conn: sqlite3.Connection,
    source_file: str,
    feats: TransferFeatures,
    w_um: float,
    l_um: float,
    tox_nm: float,
    eps_r: float,
    sweep_id: Optional[int] = None,
) -> int:
    """Insert or replace the computed features for one transfer file.

    Idempotent on ``source_file`` (re-saving overwrites the previous row).

    Args:
        conn: Open database connection.
        source_file: The Id-Vg filename the features came from.
        feats: Extracted :class:`TransferFeatures`.
        w_um, l_um, tox_nm, eps_r: Geometry / oxide used for the extraction.
        sweep_id: Optional link to the ingested ``iv_sweeps`` row.

    Returns:
        The feature_id of the stored row.
    """
    conn.execute("DELETE FROM tft_curve_features WHERE source_file = ?", (source_file,))
    cur = conn.execute(
        """
        INSERT INTO tft_curve_features
            (sweep_id, source_file, vth, mu_sat, ss_min, on_off_ratio, ion, ioff,
             gm_max, gm_max_vg, cox, w_um, l_um, tox_nm, eps_r)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (sweep_id, source_file, _f(feats.vth_sat), _f(feats.mu_sat), _f(feats.ss_min),
         _f(feats.on_off_ratio), _f(feats.ion), _f(feats.ioff), _f(feats.gm_max),
         _f(feats.gm_max_vg), _f(feats.cox), w_um, l_um, tox_nm, eps_r),
    )
    conn.commit()
    return int(cur.lastrowid)


def load_features(conn: sqlite3.Connection) -> pd.DataFrame:
    """Return all stored curve features (most recent first)."""
    return pd.read_sql_query(
        "SELECT * FROM tft_curve_features ORDER BY computed_at DESC, feature_id DESC",
        conn,
    )


def features_for_sweep(conn: sqlite3.Connection, sweep_id: int) -> Optional[dict]:
    """Return the stored feature row for a sweep, or None."""
    row = conn.execute(
        "SELECT * FROM tft_curve_features WHERE sweep_id = ?", (sweep_id,)
    ).fetchone()
    return dict(row) if row is not None else None


def _f(value) -> Optional[float]:
    """Coerce inf/NaN to None so SQLite stores clean NULLs."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v != v or v in (float("inf"), float("-inf")):
        return None
    return v
