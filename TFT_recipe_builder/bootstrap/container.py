"""Tiny dependency-injection container wiring services together.

Holds the persistent main-database :class:`RecipeService` and a separate
in-memory 'working' service. The editor auto-saves the in-progress recipe to the
working service; an explicit Save copies it to the main service.
"""

from __future__ import annotations

import logging

from TFT_recipe_builder.logic.models import Recipe
from TFT_recipe_builder.logic.recipe_service import RecipeService
from TFT_recipe_builder.sql import db_ops

logger = logging.getLogger(__name__)


class Container:
    """Owns the database connections and the recipe services."""

    def __init__(self) -> None:
        self._main_conn = db_ops.open_main_connection()
        self._working_conn = db_ops.create_working_connection()
        self.main_service = RecipeService(self._main_conn)
        self.working_service = RecipeService(self._working_conn)

    def autosave_working(self, recipe: Recipe) -> None:
        """Persist the in-progress recipe into the in-memory working store.

        The working store always holds exactly one recipe row, so it is cleared
        first. Validation errors are intentionally *not* enforced here — drafts
        may be incomplete.

        Args:
            recipe: The current editor recipe (a draft copy is stored).
        """
        self._working_conn.execute("DELETE FROM recipes")
        self._working_conn.commit()
        draft = Recipe(
            recipe_name=recipe.recipe_name or "(draft)",
            substrate_type=recipe.substrate_type,
            target_process_node=recipe.target_process_node,
            description=recipe.description,
            is_active=recipe.is_active,
            steps=list(recipe.steps),
        )
        try:
            self.working_service.save_recipe(draft)
        except Exception:  # pragma: no cover - drafts may be invalid
            logger.debug("Working autosave skipped (incomplete draft).")

    def commit_to_main(self, recipe: Recipe) -> int:
        """Persist the recipe to the main database and return its recipe_id."""
        return self.main_service.save_recipe(recipe)

    def close(self) -> None:
        """Close both connections."""
        self._main_conn.close()
        self._working_conn.close()
