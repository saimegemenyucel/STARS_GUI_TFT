"""Ingest legacy .xls / .xlsx I-V sweep files into the iv_* tables.

Pipeline mirrors the real file structure 1:1:

    file (iv_sweeps)
      -> Run<N> sheet, or bias-group within a numbered-column sheet (iv_runs)
           -> raw measurement point (iv_points)

The number of runs/bias-groups per file is *discovered dynamically* — never
hardcoded. Re-ingesting the same file is idempotent via ``iv_sweeps.source_file
UNIQUE`` (skipped by default, or replaced with ``replace=True``).

Only raw I-V points are stored; the Settings and (empty) Calc sheets are
ignored. Derived parameters (Vth, mobility, ...) are computed downstream.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Filename parser (validated against the two real sample files)
# --------------------------------------------------------------------------
FILENAME_PATTERN = re.compile(
    r"^R(?P<run_start>\d+)-"
    r"(?P<sweep_type>IdV[dg])-"
    r"(?P<temp1>\d+)C-"
    r"(?P<die>[A-Za-z]\d[A-Za-z]\d)-"
    r"(?P<subdie>[A-Za-z]\d[A-Za-z]\d)_"
    r"L(?P<length>[\d.]+)W(?P<width>[\d.]+)-"
    r"ch(?P<channel>\d+)_"
    r"(?P<material>[A-Za-z]+)-"
    r"(?P<temp2>\d+)C$"
)


@dataclass
class SweepMetadata:
    """Structured metadata parsed from a measurement filename."""

    source_file: str
    run_start: int
    sweep_type: str
    temperature_c: float
    die_col_row: str
    subdie_col_row: str
    channel_length: float
    channel_width: float
    instrument_ch: str
    material_stack: str
    extra_temp_c: Optional[float]


def parse_filename(filename: str) -> SweepMetadata:
    """Parse the lab's measurement filename convention into structured metadata.

    Args:
        filename: File name or path; only the stem is matched.

    Returns:
        A populated :class:`SweepMetadata`.

    Raises:
        ValueError: If the filename doesn't match the expected pattern. Callers
            should catch this and skip/report the file rather than crash a batch.
    """
    name = Path(filename).name
    stem = Path(filename).stem
    match = FILENAME_PATTERN.match(stem)
    if not match:
        raise ValueError(f"Filename does not match expected convention: {filename!r}")
    g = match.groupdict()
    return SweepMetadata(
        source_file=name,
        run_start=int(g["run_start"]),
        sweep_type=g["sweep_type"],
        temperature_c=float(g["temp1"]),
        die_col_row=g["die"],
        subdie_col_row=g["subdie"],
        channel_length=float(g["length"]),
        channel_width=float(g["width"]),
        instrument_ch=g["channel"],
        material_stack=g["material"],
        extra_temp_c=float(g["temp2"]) if g["temp2"] else None,
    )


# --------------------------------------------------------------------------
# Sheet / column discovery
# --------------------------------------------------------------------------
_RUN_SHEET = re.compile(r"^Run(\d+)$", re.IGNORECASE)
_ROLE_RX = {
    "drain_i": re.compile(r"^drain\s*i$", re.IGNORECASE),
    "drain_v": re.compile(r"^drain\s*v$", re.IGNORECASE),
    "gate_i": re.compile(r"^gate\s*i$", re.IGNORECASE),
    "gate_v": re.compile(r"^gate\s*v$", re.IGNORECASE),
}


def discover_run_sheets(sheet_names: list[str]) -> list[tuple[str, int]]:
    """Return ``(sheet_name, run_number)`` for every ``Run<N>`` sheet, sorted.

    Non-run sheets (Settings, Calc, ...) are ignored.
    """
    runs = []
    for name in sheet_names:
        m = _RUN_SHEET.match(str(name).strip())
        if m:
            runs.append((name, int(m.group(1))))
    runs.sort(key=lambda t: t[1])
    return runs


def _column_role(col: str) -> tuple[Optional[str], Optional[int]]:
    """Map a column name to ``(role, bias_group)``.

    ``"DrainI"`` -> ``("drain_i", None)``; ``"DrainV(2)"`` -> ``("drain_v", 2)``.
    """
    name = str(col).strip()
    grp_match = re.search(r"\((\d+)\)\s*$", name)
    group = int(grp_match.group(1)) if grp_match else None
    base = re.sub(r"\(\d+\)\s*$", "", name).strip()
    for role, rx in _ROLE_RX.items():
        if rx.match(base):
            return role, group
    return None, group


def extract_bias_groups(df: pd.DataFrame) -> list[tuple[Optional[int], pd.DataFrame]]:
    """Split a run sheet into one DataFrame per bias group.

    A plain sheet (columns DrainI/DrainV/GateI/GateV) yields a single group with
    ``bias_group = None``. A sheet with numbered columns (``DrainI(1)``, ...)
    yields one group per index, in ascending order. Row order is preserved so
    the sweep direction survives.

    Returns:
        List of ``(bias_group, points_df)`` where ``points_df`` has columns
        ``drain_i, drain_v, gate_i, gate_v``.
    """
    # Collect role -> column for each bias group.
    groups: dict[Optional[int], dict[str, str]] = {}
    for col in df.columns:
        role, group = _column_role(col)
        if role is not None:
            groups.setdefault(group, {})[role] = col

    ordered_keys = sorted(groups.keys(), key=lambda k: (k is not None, k))
    result: list[tuple[Optional[int], pd.DataFrame]] = []
    for key in ordered_keys:
        roles = groups[key]
        out = pd.DataFrame()
        for role in ("drain_i", "drain_v", "gate_i", "gate_v"):
            col = roles.get(role)
            out[role] = pd.to_numeric(df[col], errors="coerce") if col else pd.Series(dtype=float)
        out = out.dropna(how="all").reset_index(drop=True)
        if not out.empty:
            result.append((key, out))
    return result


# --------------------------------------------------------------------------
# Ingestion
# --------------------------------------------------------------------------
def sweep_exists(conn: sqlite3.Connection, source_file: str) -> bool:
    """Whether a sweep with this source filename is already ingested."""
    row = conn.execute(
        "SELECT 1 FROM iv_sweeps WHERE source_file = ?", (source_file,)
    ).fetchone()
    return row is not None


def ingest_file(
    path: str | Path,
    conn: sqlite3.Connection,
    wafer_id: Optional[str] = None,
    replace: bool = False,
) -> dict:
    """Ingest one measurement file into the iv_* tables.

    Args:
        path: Path to the .xls/.xlsx file.
        conn: Open database connection.
        wafer_id: Optional wafer to link the sweep to.
        replace: If True and the file was already ingested, delete and re-import;
            if False, skip it.

    Returns:
        A summary dict: ``{source_file, skipped, sweep_id, runs, points}``.

    Raises:
        ValueError: If the filename does not match the naming convention.
    """
    path = Path(path)
    meta = parse_filename(path.name)

    if sweep_exists(conn, meta.source_file):
        if not replace:
            logger.info("Skipping already-ingested file: %s", meta.source_file)
            return {"source_file": meta.source_file, "skipped": True,
                    "sweep_id": None, "runs": 0, "points": 0}
        conn.execute("DELETE FROM iv_sweeps WHERE source_file = ?", (meta.source_file,))

    cur = conn.execute(
        """
        INSERT INTO iv_sweeps
            (source_file, run_start, sweep_type, temperature_c, die_col_row,
             subdie_col_row, channel_length, channel_width, instrument_ch,
             material_stack, extra_temp_c, wafer_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (meta.source_file, meta.run_start, meta.sweep_type, meta.temperature_c,
         meta.die_col_row, meta.subdie_col_row, meta.channel_length,
         meta.channel_width, meta.instrument_ch, meta.material_stack,
         meta.extra_temp_c, wafer_id),
    )
    sweep_id = int(cur.lastrowid)

    xls = pd.ExcelFile(path)
    run_sheets = discover_run_sheets(xls.sheet_names)
    if not run_sheets:
        logger.warning("No Run<N> sheets found in %s", path.name)

    total_runs = 0
    total_points = 0
    for sheet_name, run_number in run_sheets:
        df = xls.parse(sheet_name, header=0)
        for bias_group, points in extract_bias_groups(df):
            run_cur = conn.execute(
                "INSERT INTO iv_runs (sweep_id, run_number, sheet_name, bias_group) "
                "VALUES (?, ?, ?, ?)",
                (sweep_id, run_number, sheet_name, bias_group),
            )
            run_id = int(run_cur.lastrowid)
            rows = [
                (run_id, i,
                 _none(r.drain_i), _none(r.drain_v), _none(r.gate_i), _none(r.gate_v))
                for i, r in enumerate(points.itertuples(index=False))
            ]
            conn.executemany(
                "INSERT INTO iv_points "
                "(run_id, point_order, drain_i, drain_v, gate_i, gate_v) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )
            total_runs += 1
            total_points += len(rows)

    conn.commit()
    logger.info("Ingested %s: %d runs, %d points (sweep_id=%d)",
                meta.source_file, total_runs, total_points, sweep_id)
    return {"source_file": meta.source_file, "skipped": False,
            "sweep_id": sweep_id, "runs": total_runs, "points": total_points}


def ingest_folder(
    folder: str | Path,
    conn: sqlite3.Connection,
    wafer_id: Optional[str] = None,
    replace: bool = False,
) -> dict:
    """Ingest every .xls/.xlsx file in a folder, skipping bad filenames.

    Returns:
        Summary dict with ``ingested``, ``skipped``, ``failed`` lists.
    """
    folder = Path(folder)
    files = sorted(p for p in folder.iterdir()
                   if p.suffix.lower() in (".xls", ".xlsx"))
    ingested, skipped, failed = [], [], []
    for path in files:
        try:
            res = ingest_file(path, conn, wafer_id=wafer_id, replace=replace)
        except ValueError as exc:
            failed.append((path.name, str(exc)))
            logger.warning("Skip %s: %s", path.name, exc)
            continue
        except Exception as exc:  # pragma: no cover - unexpected read errors
            failed.append((path.name, str(exc)))
            logger.exception("Failed to ingest %s", path.name)
            continue
        (skipped if res["skipped"] else ingested).append(res)
    return {"ingested": ingested, "skipped": skipped, "failed": failed}


def list_sweeps(conn: sqlite3.Connection) -> pd.DataFrame:
    """Return all ingested sweeps with run/point counts (newest first)."""
    query = """
        SELECT s.sweep_id, s.source_file, s.sweep_type, s.run_start,
               s.die_col_row, s.subdie_col_row, s.channel_length, s.channel_width,
               s.material_stack, s.temperature_c,
               (SELECT COUNT(*) FROM iv_runs r WHERE r.sweep_id = s.sweep_id) AS runs,
               (SELECT COUNT(*) FROM iv_points p
                  JOIN iv_runs r ON p.run_id = r.run_id
                 WHERE r.sweep_id = s.sweep_id) AS points,
               s.imported_at
        FROM iv_sweeps s
        ORDER BY s.imported_at DESC, s.sweep_id DESC
    """
    return pd.read_sql_query(query, conn)


def _none(v):
    """Convert NaN to None for clean SQLite NULLs."""
    return None if pd.isna(v) else float(v)
