"""Generate CSV documentation of the database structure.

Usage::

    python sql_tools/generate_docs.py [output_dir]

Writes ``tables.csv`` (one row per column with type / nullability / pk) and
``foreign_keys.csv`` (one row per FK relationship).
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import _common  # noqa: F401

from shared import init_database
from shared.db import get_connection


def generate(output_dir: Path) -> tuple[Path, Path]:
    """Write ``tables.csv`` and ``foreign_keys.csv`` into ``output_dir``."""
    init_database()
    output_dir.mkdir(parents=True, exist_ok=True)
    conn = get_connection()
    try:
        tables = [
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        ]
        cols_path = output_dir / "tables.csv"
        with cols_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["table", "column", "type", "not_null", "default", "primary_key"])
            for table in tables:
                for col in conn.execute(f"PRAGMA table_info('{table}')").fetchall():
                    writer.writerow([
                        table, col["name"], col["type"], col["notnull"],
                        col["dflt_value"], col["pk"],
                    ])

        fk_path = output_dir / "foreign_keys.csv"
        with fk_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["table", "column", "references_table", "references_column"])
            for table in tables:
                for fk in conn.execute(f"PRAGMA foreign_key_list('{table}')").fetchall():
                    writer.writerow([table, fk["from"], fk["table"], fk["to"]])
    finally:
        conn.close()
    return cols_path, fk_path


def main() -> int:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "docs_out"
    cols, fks = generate(out_dir)
    print(f"Wrote {cols} and {fks}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
