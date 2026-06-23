"""Dialog to pick an existing recipe to load from the main database."""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from TFT_recipe_builder.logic.recipe_service import RecipeService

logger = logging.getLogger(__name__)


class LoadRecipeDialog(QDialog):
    """List saved recipes and return the chosen ``recipe_id``."""

    def __init__(self, service: RecipeService, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Load Recipe")
        self.resize(380, 420)
        self._selected_id: Optional[int] = None

        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(lambda _i: self._on_accept())
        for recipe in service.list_recipes():
            label = f"{recipe.recipe_name}  [{recipe.substrate_type}, {recipe.target_process_node}]"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, recipe.recipe_id)
            self.list_widget.addItem(item)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Open | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.list_widget)
        layout.addWidget(buttons)

    @property
    def selected_recipe_id(self) -> Optional[int]:
        """The recipe_id chosen by the user, or ``None``."""
        return self._selected_id

    def _on_accept(self) -> None:
        item = self.list_widget.currentItem()
        if item is None:
            self.reject()
            return
        self._selected_id = item.data(Qt.ItemDataRole.UserRole)
        self.accept()
