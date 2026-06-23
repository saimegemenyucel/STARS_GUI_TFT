"""CRUD service for recipes, operating on a single SQLite connection.

The same service class drives both the persistent main database and the
in-memory 'working' database used while editing (see ``bootstrap.container``).
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Optional

from TFT_recipe_builder.logic.models import ProcessStep, Recipe

logger = logging.getLogger(__name__)


class RecipeExistsError(Exception):
    """Raised when saving a recipe whose name collides with another recipe."""


class RecipeService:
    """Recipe CRUD bound to one open connection."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    @property
    def connection(self) -> sqlite3.Connection:
        """The underlying connection (exposed for the container/commit logic)."""
        return self._conn

    # -- reads --------------------------------------------------------------
    def list_recipes(self, active_only: bool = False) -> list[Recipe]:
        """Return recipe headers (without steps), newest first."""
        sql = "SELECT * FROM recipes"
        if active_only:
            sql += " WHERE is_active = 1"
        sql += " ORDER BY last_modified_date DESC, recipe_name"
        rows = self._conn.execute(sql).fetchall()
        return [Recipe.from_row(r) for r in rows]

    def load_recipe(self, recipe_id: int) -> Optional[Recipe]:
        """Load a full recipe (header + ordered steps), or ``None`` if missing."""
        header = self._conn.execute(
            "SELECT * FROM recipes WHERE recipe_id = ?", (recipe_id,)
        ).fetchone()
        if header is None:
            return None
        step_rows = self._conn.execute(
            "SELECT * FROM recipe_steps WHERE recipe_id = ? ORDER BY step_order",
            (recipe_id,),
        ).fetchall()
        steps = [ProcessStep.from_row(r) for r in step_rows]
        return Recipe.from_row(header, steps)

    def name_exists(self, name: str, exclude_id: Optional[int] = None) -> bool:
        """Whether another recipe already uses ``name``."""
        if exclude_id is None:
            row = self._conn.execute(
                "SELECT 1 FROM recipes WHERE recipe_name = ?", (name,)
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT 1 FROM recipes WHERE recipe_name = ? AND recipe_id != ?",
                (name, exclude_id),
            ).fetchone()
        return row is not None

    # -- writes -------------------------------------------------------------
    def save_recipe(self, recipe: Recipe) -> int:
        """Insert or update a recipe and fully replace its steps.

        Args:
            recipe: The recipe to persist. If ``recipe.recipe_id`` is set the
                existing row is updated, otherwise a new row is inserted.

        Returns:
            The recipe_id of the saved recipe.

        Raises:
            RecipeExistsError: If the name collides with a different recipe.
        """
        if self.name_exists(recipe.recipe_name, exclude_id=recipe.recipe_id):
            raise RecipeExistsError(
                f"A recipe named {recipe.recipe_name!r} already exists."
            )

        recipe.renumber_steps()
        try:
            if recipe.recipe_id is None:
                recipe_id = self._insert_header(recipe)
            else:
                recipe_id = recipe.recipe_id
                self._update_header(recipe)
                self._conn.execute(
                    "DELETE FROM recipe_steps WHERE recipe_id = ?", (recipe_id,)
                )
            self._insert_steps(recipe_id, recipe.steps)
            self._conn.commit()
        except sqlite3.IntegrityError as exc:
            self._conn.rollback()
            raise RecipeExistsError(str(exc)) from exc
        recipe.recipe_id = recipe_id
        return recipe_id

    def delete_recipe(self, recipe_id: int) -> None:
        """Delete a recipe and its steps (steps cascade via the FK)."""
        self._conn.execute("DELETE FROM recipes WHERE recipe_id = ?", (recipe_id,))
        self._conn.commit()

    # -- internals ----------------------------------------------------------
    def _insert_header(self, recipe: Recipe) -> int:
        cur = self._conn.execute(
            """
            INSERT INTO recipes
                (recipe_name, substrate_type, target_process_node,
                 description, is_active, created_date, last_modified_date)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (recipe.recipe_name, recipe.substrate_type, recipe.target_process_node,
             recipe.description, int(recipe.is_active)),
        )
        return int(cur.lastrowid)

    def _update_header(self, recipe: Recipe) -> None:
        self._conn.execute(
            """
            UPDATE recipes
               SET recipe_name = ?, substrate_type = ?, target_process_node = ?,
                   description = ?, is_active = ?, last_modified_date = CURRENT_TIMESTAMP
             WHERE recipe_id = ?
            """,
            (recipe.recipe_name, recipe.substrate_type, recipe.target_process_node,
             recipe.description, int(recipe.is_active), recipe.recipe_id),
        )

    def _insert_steps(self, recipe_id: int, steps: list[ProcessStep]) -> None:
        self._conn.executemany(
            """
            INSERT INTO recipe_steps
                (recipe_id, step_order, process_type, process_name, temperature,
                 duration, gas_mixture, pressure, power, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (recipe_id, s.step_order, s.process_type, s.process_name,
                 s.temperature, s.duration, s.gas_mixture_json(), s.pressure,
                 s.power, s.notes)
                for s in steps
            ],
        )
