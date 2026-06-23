"""Extract the live database schema to a .sql file.

Usage::

    python sql_tools/extract_schema.py [output.sql]

Reads the shared database, dumps every table/index DDL, and writes it (default:
``sql_tools/schema_dump.sql``).
"""

from __future__ import annotations

import sys
from pathlib import Path

import _common  # noqa: F401  (adds project root to sys.path)

from shared import init_database
from shared.db import get_connection


def extract_schema(output: Path) -> Path:
    """Write all CREATE statements from the database to ``output``."""
    init_database()
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT sql FROM sqlite_master
            WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'
            ORDER BY CASE type WHEN 'table' THEN 0 ELSE 1 END, name
            """
        ).fetchall()
    finally:
        conn.close()
    ddl = ";\n\n".join(r[0].strip() for r in rows) + ";\n"
    output.write_text("-- Auto-extracted schema\n\n" + ddl, encoding="utf-8")
    return output


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "schema_dump.sql"
    path = extract_schema(out)
    print(f"Schema written to {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
