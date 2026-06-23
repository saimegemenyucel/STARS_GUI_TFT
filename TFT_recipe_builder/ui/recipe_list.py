"""Left-hand panel listing saved recipes with New / Load / Delete actions."""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QGroupBox,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from TFT_recipe_builder.logic.recipe_service import RecipeService

logger = logging.getLogger(__name__)


class RecipeListPanel(QWidget):
    """Shows saved recipes and emits signals for editor actions."""

    new_requested = pyqtSignal()
    load_requested = pyqtSignal(int)
    delete_requested = pyqtSignal(int)

    def __init__(self, service: RecipeService, parent=None):
        super().__init__(parent)
        self._service = service

        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self._emit_load)

        self.new_btn = QPushButton("New Recipe")
        self.load_btn = QPushButton("Load Selected")
        self.delete_btn = QPushButton("Delete Selected")
        self.new_btn.clicked.connect(self.new_requested.emit)
        self.load_btn.clicked.connect(self._emit_load)
        self.delete_btn.clicked.connect(self._emit_delete)

        box = QGroupBox("Saved recipes")
        inner = QVBoxLayout(box)
        inner.addWidget(self.list_widget)
        inner.addWidget(self.new_btn)
        inner.addWidget(self.load_btn)
        inner.addWidget(self.delete_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(box)
        self.refresh()

    def refresh(self) -> None:
        """Reload the recipe list from the service."""
        self.list_widget.clear()
        for recipe in self._service.list_recipes():
            status = "" if recipe.is_active else "  (inactive)"
            item = QListWidgetItem(
                f"{recipe.recipe_name}  [{recipe.target_process_node}]{status}"
            )
            item.setData(Qt.ItemDataRole.UserRole, recipe.recipe_id)
            self.list_widget.addItem(item)

    def _current_id(self) -> Optional[int]:
        item = self.list_widget.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _emit_load(self, *_args) -> None:
        rid = self._current_id()
        if rid is not None:
            self.load_requested.emit(rid)

    def _emit_delete(self) -> None:
        rid = self._current_id()
        if rid is not None:
            self.delete_requested.emit(rid)
