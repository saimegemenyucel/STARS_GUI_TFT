"""Import smoke test for the recipe builder (logic + working DB)."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    from TFT_recipe_builder.logic import models, enums, validation, recipe_service  # noqa: F401
    from TFT_recipe_builder.sql import db_ops
    from shared import init_database

    init_database()
    # Exercise the in-memory working DB end-to-end.
    conn = db_ops.create_working_connection()
    svc = recipe_service.RecipeService(conn)
    print(f"OK: imports succeeded, working DB lists {len(svc.list_recipes())} recipes.")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
