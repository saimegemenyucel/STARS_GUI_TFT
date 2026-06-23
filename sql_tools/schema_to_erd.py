"""Generate a simple ER diagram (SVG) from the live database schema.

Usage::

    python sql_tools/schema_to_erd.py [output.svg]

Self-contained: reads table/column/foreign-key info via PRAGMA and emits an SVG
by hand (no graphviz dependency). Tables are laid out on a grid; foreign keys
are drawn as connecting lines.
"""

from __future__ import annotations

import sys
from html import escape
from pathlib import Path

import _common  # noqa: F401

from shared import init_database
from shared.db import get_connection

BOX_W = 230
ROW_H = 18
HEADER_H = 26
COL_GAP = 70
ROW_GAP = 50
COLS_PER_ROW = 3


def _collect():
    """Return (tables dict[name -> columns], fks list of (src, dst))."""
    conn = get_connection()
    try:
        names = [
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        ]
        tables: dict[str, list[tuple[str, str, bool]]] = {}
        fks: list[tuple[str, str]] = []
        for table in names:
            cols = []
            for col in conn.execute(f"PRAGMA table_info('{table}')").fetchall():
                cols.append((col["name"], col["type"] or "", bool(col["pk"])))
            tables[table] = cols
            for fk in conn.execute(f"PRAGMA foreign_key_list('{table}')").fetchall():
                fks.append((table, fk["table"]))
    finally:
        conn.close()
    return tables, fks


def build_svg(tables, fks) -> str:
    """Render the schema to an SVG string."""
    # Lay out tables on a grid and remember each box rectangle.
    positions: dict[str, tuple[int, int, int]] = {}  # name -> (x, y, height)
    x = y = 20
    row_max_h = 0
    col = 0
    max_width = 20
    for name, cols in tables.items():
        height = HEADER_H + ROW_H * max(len(cols), 1) + 6
        positions[name] = (x, y, height)
        row_max_h = max(row_max_h, height)
        max_width = max(max_width, x + BOX_W + 20)
        col += 1
        if col >= COLS_PER_ROW:
            col = 0
            x = 20
            y += row_max_h + ROW_GAP
            row_max_h = 0
        else:
            x += BOX_W + COL_GAP
    total_h = y + row_max_h + 40

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{max_width}" '
        f'height="{total_h}" font-family="Segoe UI, sans-serif" font-size="11">'
    )
    parts.append(f'<rect width="{max_width}" height="{total_h}" fill="#ffffff"/>')

    # FK connector lines (drawn first, under the boxes).
    for src, dst in fks:
        if src not in positions or dst not in positions:
            continue
        sx, sy, sh = positions[src]
        dx, dy, dh = positions[dst]
        x1, y1 = sx + BOX_W / 2, sy + sh / 2
        x2, y2 = dx + BOX_W / 2, dy + dh / 2
        parts.append(
            f'<line x1="{x1:.0f}" y1="{y1:.0f}" x2="{x2:.0f}" y2="{y2:.0f}" '
            f'stroke="#c0392b" stroke-width="1.5" stroke-dasharray="4,3"/>'
        )

    # Table boxes.
    for name, cols in tables.items():
        bx, by, height = positions[name]
        parts.append(
            f'<rect x="{bx}" y="{by}" width="{BOX_W}" height="{height}" rx="6" '
            f'fill="#f4f6fb" stroke="#34495e" stroke-width="1.5"/>'
        )
        parts.append(
            f'<rect x="{bx}" y="{by}" width="{BOX_W}" height="{HEADER_H}" rx="6" '
            f'fill="#3d8bfd"/>'
        )
        parts.append(
            f'<text x="{bx + BOX_W / 2:.0f}" y="{by + 18}" text-anchor="middle" '
            f'fill="white" font-weight="bold">{escape(name)}</text>'
        )
        for i, (cname, ctype, is_pk) in enumerate(cols):
            ty = by + HEADER_H + ROW_H * i + 14
            label = ("🔑 " if is_pk else "") + cname
            weight = "bold" if is_pk else "normal"
            parts.append(
                f'<text x="{bx + 10}" y="{ty:.0f}" font-weight="{weight}" '
                f'fill="#2c3e50">{escape(label)}</text>'
            )
            parts.append(
                f'<text x="{bx + BOX_W - 10}" y="{ty:.0f}" text-anchor="end" '
                f'fill="#7f8c8d">{escape(ctype)}</text>'
            )
    parts.append("</svg>")
    return "\n".join(parts)


def main() -> int:
    init_database()
    tables, fks = _collect()
    svg = build_svg(tables, fks)
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "schema_erd.svg"
    out.write_text(svg, encoding="utf-8")
    print(f"ERD written to {out} ({len(tables)} tables, {len(fks)} relationships)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
