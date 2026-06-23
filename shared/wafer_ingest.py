"""Ingest a whole folder of measurement files as one wafer.

The folder name becomes the ``wafer_id``: every .xls/.xlsx inside is ingested
and linked to that wafer, and transfer (Id-Vg) files are immediately analysed so
their features (Vth, mobility, ...) land in the database — which means the wafer
map can colour transistors pass/fail straight after a folder import, with no
extra steps.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from shared.iv_features import save_transfer_features
from shared.iv_ingest import ingest_file, parse_filename
from shared.tft_analysis import (
    DEFAULT_EPS_R,
    DEFAULT_TOX_NM,
    extract_transfer_features,
    load_transfer,
)

logger = logging.getLogger(__name__)


def ensure_wafer(conn: sqlite3.Connection, wafer_id: str) -> None:
    """Create a wafers row for this id if it does not already exist."""
    conn.execute(
        "INSERT OR IGNORE INTO wafers (wafer_id, wafer_name) VALUES (?, ?)",
        (wafer_id, wafer_id),
    )
    conn.commit()


def ingest_wafer_folder(
    folder: str | Path,
    conn: sqlite3.Connection,
    tox_nm: float = DEFAULT_TOX_NM,
    eps_r: float = DEFAULT_EPS_R,
    replace: bool = False,
) -> dict:
    """Ingest every measurement file in ``folder`` as one wafer.

    Args:
        folder: Directory of .xls/.xlsx files. Its name becomes the wafer id.
        conn: Open database connection.
        tox_nm, eps_r: Gate-oxide assumptions for the feature extraction.
        replace: Re-import files already present (default: skip).

    Returns:
        Summary dict: ``{wafer_id, ingested, features, skipped, failed}``.
    """
    folder = Path(folder)
    wafer_id = folder.name
    ensure_wafer(conn, wafer_id)

    files = sorted(p for p in folder.iterdir()
                   if p.suffix.lower() in (".xls", ".xlsx"))
    ingested = skipped = features = 0
    failed: list[tuple[str, str]] = []

    for path in files:
        try:
            meta = parse_filename(path.name)
        except ValueError as exc:
            failed.append((path.name, str(exc)))
            continue
        try:
            res = ingest_file(path, conn, wafer_id=wafer_id, replace=replace)
        except Exception as exc:  # pragma: no cover - unexpected read error
            failed.append((path.name, str(exc)))
            continue
        if res["skipped"]:
            skipped += 1
        else:
            ingested += 1
        # Re-link to this wafer even if the file was already ingested earlier
        # (e.g. via Curve Analysis "Save to database" with no wafer), so it
        # always shows under the folder's wafer.
        conn.execute("UPDATE iv_sweeps SET wafer_id = ? WHERE source_file = ?",
                     (wafer_id, meta.source_file))
        conn.commit()

        # Analyse transfer sweeps so the wafer map has features to colour by.
        if meta.sweep_type.lower() == "idvg":
            try:
                curve = load_transfer(path)
                feats = extract_transfer_features(
                    curve, meta.channel_width, meta.channel_length, tox_nm, eps_r)
                row = conn.execute(
                    "SELECT sweep_id FROM iv_sweeps WHERE source_file = ?",
                    (meta.source_file,),
                ).fetchone()
                save_transfer_features(
                    conn, meta.source_file, feats, meta.channel_width,
                    meta.channel_length, tox_nm, eps_r,
                    row[0] if row else None)
                features += 1
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Feature extraction failed for %s: %s", path.name, exc)

    logger.info("Wafer '%s': ingested %d, skipped %d, features %d, failed %d",
                wafer_id, ingested, skipped, features, len(failed))
    return {"wafer_id": wafer_id, "ingested": ingested, "skipped": skipped,
            "features": features, "failed": failed}
