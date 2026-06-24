"""Wafer-map data layer: map ingested I-V sweeps onto a die / transistor grid.

The measurement metadata already encodes position:
  * ``die_col_row``  e.g. "C4R2"  -> die at column 4, row 2 on the wafer
  * ``subdie_col_row`` e.g. "c1r2" -> transistor at column 1, row 2 in the die

This module parses those positions, aggregates one cell per (die, transistor)
with its computed features, and computes per-die yield. The grid size is
supplied by the caller so it scales to any wafer (7x4 dies, 8x8 cells, ...).
"""

from __future__ import annotations

import logging
import re
import sqlite3
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_POS_RX = re.compile(r"[Cc](\d+)[Rr](\d+)")


@dataclass
class FunctionalThresholds:
    """Lenient pass/fail rule for classifying a transistor from its features."""

    vth_min: float = -15.0
    vth_max: float = 15.0
    mobility_min: float = 1.0          # cm^2/Vs
    on_off_min: float = 10.0           # raw ratio (>=1 decade)

    def passes(self, vth, mu, on_off) -> bool:
        """True if the device meets every threshold (NaN/None fails)."""
        try:
            if vth is None or mu is None or on_off is None:
                return False
            if pd.isna(vth) or pd.isna(mu) or pd.isna(on_off):
                return False
            return (self.vth_min <= vth <= self.vth_max
                    and mu >= self.mobility_min
                    and on_off >= self.on_off_min)
        except TypeError:
            return False


def parse_position(token: str) -> Optional[tuple[int, int]]:
    """Parse a ``C<col>R<row>`` token into ``(col, row)`` 1-based, or None."""
    if not token:
        return None
    m = _POS_RX.search(str(token))
    return (int(m.group(1)), int(m.group(2))) if m else None


def get_cells(conn: sqlite3.Connection, wafer_id: Optional[str] = None) -> pd.DataFrame:
    """One row per (die, transistor) that has ingested data, with features.

    Returns:
        DataFrame with columns: die_col, die_row, tr_col, tr_row, sweep_types,
        vth, mu_sat, on_off_ratio, ss_min, functional. Empty if no data.
    """
    sql = """
        SELECT s.die_col_row, s.subdie_col_row, s.sweep_type, s.source_file,
               s.material_stack, s.channel_length, s.channel_width,
               f.vth, f.mu_sat, f.on_off_ratio, f.ss_min
        FROM iv_sweeps s
        LEFT JOIN tft_curve_features f ON f.sweep_id = s.sweep_id
    """
    params: tuple = ()
    if wafer_id is not None:
        sql += " WHERE s.wafer_id = ?"
        params = (wafer_id,)
    try:
        raw = pd.read_sql_query(sql, conn, params=params)
    except sqlite3.Error:
        return pd.DataFrame()
    if raw.empty:
        return pd.DataFrame()

    thresholds = FunctionalThresholds()
    rows = []
    grouped = raw.groupby(["die_col_row", "subdie_col_row"], dropna=False)
    for (die_tok, sub_tok), g in grouped:
        die = parse_position(die_tok)
        sub = parse_position(sub_tok)
        if die is None or sub is None:
            continue
        # Features come from the Id-Vg row (if analysed & saved).
        feat = g.dropna(subset=["vth"])
        vth = float(feat["vth"].iloc[0]) if not feat.empty else None
        mu = float(feat["mu_sat"].iloc[0]) if not feat.empty else None
        onoff = float(feat["on_off_ratio"].iloc[0]) if not feat.empty else None
        ss = float(feat["ss_min"].iloc[0]) if not feat.empty else None
        mat = next((m for m in g["material_stack"].dropna()), None)
        lval = next((x for x in g["channel_length"].dropna()), None)
        wval = next((x for x in g["channel_width"].dropna()), None)
        rows.append({
            "die_col": die[0], "die_row": die[1],
            "tr_col": sub[0], "tr_row": sub[1],
            "sweep_types": ",".join(sorted(set(g["sweep_type"].dropna()))),
            "material_stack": mat, "channel_length": lval, "channel_width": wval,
            "vth": vth, "mu_sat": mu, "on_off_ratio": onoff, "ss_min": ss,
            "functional": thresholds.passes(vth, mu, onoff),
        })
    return pd.DataFrame(rows)


def die_summary(cells: pd.DataFrame, tr_rows: int, tr_cols: int) -> pd.DataFrame:
    """Per-die counts and yield.

    Args:
        cells: Output of :func:`get_cells`.
        tr_rows, tr_cols: Transistor grid size per die (for the total cell count).

    Returns:
        DataFrame indexed by (die_col, die_row) with measured, functional,
        total, and yield_pct columns.
    """
    total = tr_rows * tr_cols
    rows = []
    if not cells.empty:
        for (dc, dr), g in cells.groupby(["die_col", "die_row"]):
            measured = len(g)
            functional = int(g["functional"].sum())
            rows.append({
                "die_col": dc, "die_row": dr,
                "measured": measured, "functional": functional,
                "total": total,
                "yield_pct": (functional / total * 100.0) if total else 0.0,
            })
    return pd.DataFrame(rows)


def cell_at(cells: pd.DataFrame, die_col, die_row, tr_col, tr_row) -> Optional[dict]:
    """Return the cell dict at a die/transistor position, or None."""
    if cells.empty:
        return None
    m = cells[(cells.die_col == die_col) & (cells.die_row == die_row)
              & (cells.tr_col == tr_col) & (cells.tr_row == tr_row)]
    return m.iloc[0].to_dict() if not m.empty else None


def sweep_ids_for_device(
    conn: sqlite3.Connection, wafer_id: str, die_tok: str, sub_tok: str
) -> dict[str, int]:
    """Return ``{sweep_type: sweep_id}`` for one (wafer, die, transistor).

    Lets the UI jump from a device shown in the table / spatial map straight
    to its raw Id-Vg / Id-Vd sweeps (e.g. to reload them in Curve Analysis),
    without needing the original measurement file.

    Args:
        conn: An open database connection.
        wafer_id: The wafer identifier.
        die_tok: Die position token, e.g. ``"C2R3"``.
        sub_tok: Transistor position token, e.g. ``"c1r1"``.

    Returns:
        A mapping of ``sweep_type`` (``"IdVg"`` / ``"IdVd"``) to ``sweep_id``.
    """
    rows = conn.execute(
        "SELECT sweep_type, sweep_id FROM iv_sweeps "
        "WHERE wafer_id = ? AND die_col_row = ? AND subdie_col_row = ?",
        (wafer_id, die_tok, sub_tok),
    ).fetchall()
    return {r["sweep_type"]: r["sweep_id"] for r in rows if r["sweep_type"]}


def list_wafers(conn: sqlite3.Connection) -> list[str]:
    """Distinct wafer ids that have ingested sweeps (plus any in the wafers table)."""
    ids: list[str] = []
    try:
        rows = conn.execute(
            "SELECT DISTINCT wafer_id FROM iv_sweeps WHERE wafer_id IS NOT NULL "
            "ORDER BY wafer_id"
        ).fetchall()
        ids = [r[0] for r in rows]
    except sqlite3.Error:
        pass
    return ids


def cells_to_measurement_df(cells: pd.DataFrame) -> pd.DataFrame:
    """Shape :func:`get_cells` output into the measurement-table column set.

    Both the measurement viewer and the yield analyzer need their per-device
    DataFrame to look the same -- ``device_id``/``position_x``/``position_y``
    for the spatial map, plus the parameters :mod:`shared.criteria` checks --
    even though devices actually live in ``iv_sweeps``/``tft_curve_features``,
    not the legacy ``tft_measurements`` table. Centralising the shaping here
    keeps both UIs in sync. NOTE: ``on_off_ratio`` is converted to log10 here
    to match the convention used by ``quality_criteria.on_off_ratio_min`` (its
    seeded description is explicitly "log10").

    Args:
        cells: Output of :func:`get_cells`.

    Returns:
        DataFrame with ``device_id``, ``material``, ``position_x/y``, ``vth``,
        ``mobility``, ``on_off_ratio`` (log10), ``subthreshold_swing``,
        ``max_drain_current``, ``leakage_current``, ``is_functional``,
        ``defect_type``, ``sweeps``. Empty if ``cells`` is empty.
    """
    if cells.empty:
        return pd.DataFrame()

    dc = cells["die_col"].astype(int).astype(str)
    dr = cells["die_row"].astype(int).astype(str)
    tc = cells["tr_col"].astype(int).astype(str)
    tr = cells["tr_row"].astype(int).astype(str)
    onoff = pd.to_numeric(cells["on_off_ratio"], errors="coerce")

    df = pd.DataFrame()
    df["device_id"] = "C" + dc + "R" + dr + " c" + tc + "r" + tr
    df["material"] = cells["material_stack"]
    # On-wafer coordinates: dies on an integer grid, transistors offset
    # within their die so every device gets a distinct spatial-map position.
    df["position_x"] = cells["die_col"].astype(float) + cells["tr_col"].astype(float) * 0.08
    df["position_y"] = cells["die_row"].astype(float) + cells["tr_row"].astype(float) * 0.08
    df["vth"] = pd.to_numeric(cells["vth"], errors="coerce")
    df["mobility"] = pd.to_numeric(cells["mu_sat"], errors="coerce")
    df["on_off_ratio"] = np.log10(onoff.where(onoff > 0))
    df["subthreshold_swing"] = pd.to_numeric(cells["ss_min"], errors="coerce")
    df["max_drain_current"] = np.nan
    df["leakage_current"] = np.nan
    df["is_functional"] = cells["functional"].astype("boolean")
    df["defect_type"] = None
    df["sweeps"] = cells["sweep_types"]
    return df


def grid_extent(cells: pd.DataFrame) -> dict[str, int]:
    """Infer grid sizes from the largest die / transistor positions present.

    Returns a dict with die_cols, die_rows, tr_cols, tr_rows (each >= 1) so the
    map can auto-size itself to the data (e.g. a folder containing C7R8 -> a
    7-col x 8-row die grid).
    """
    def _max(col: str) -> int:
        if cells.empty or col not in cells.columns or cells[col].dropna().empty:
            return 1
        return int(max(1, cells[col].max()))
    return {
        "die_cols": _max("die_col"), "die_rows": _max("die_row"),
        "tr_cols": _max("tr_col"), "tr_rows": _max("tr_row"),
    }
