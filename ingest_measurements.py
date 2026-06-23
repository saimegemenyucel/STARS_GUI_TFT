"""Batch-ingest TFT I-V sweep files into the shared database.

Usage::

    python ingest_measurements.py <file-or-folder> [--wafer W_ID] [--replace]

Idempotent: re-running on the same files skips them unless --replace is given.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from shared import init_database
from shared.db import get_connection
from shared.iv_ingest import ingest_file, ingest_folder, list_sweeps


def main() -> int:
    """Parse args, ingest the target path, and print a summary."""
    ap = argparse.ArgumentParser(description="Ingest TFT I-V sweep files.")
    ap.add_argument("path", help="A .xls/.xlsx file or a folder of them.")
    ap.add_argument("--wafer", default=None, help="Optional wafer_id to link.")
    ap.add_argument("--replace", action="store_true",
                    help="Re-import files already present (default: skip).")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    init_database()
    conn = get_connection()
    try:
        target = Path(args.path)
        if target.is_dir():
            summary = ingest_folder(target, conn, wafer_id=args.wafer, replace=args.replace)
            print(f"Ingested {len(summary['ingested'])}, "
                  f"skipped {len(summary['skipped'])}, "
                  f"failed {len(summary['failed'])}.")
            for name, err in summary["failed"]:
                print(f"  FAILED {name}: {err}")
        else:
            res = ingest_file(target, conn, wafer_id=args.wafer, replace=args.replace)
            state = "skipped" if res["skipped"] else "ingested"
            print(f"{state}: {res['source_file']} "
                  f"({res['runs']} runs, {res['points']} points)")

        print(f"\nDatabase now holds {len(list_sweeps(conn))} sweep(s).")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
