"""Dialog to edit recipe header fields before saving."""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
)

from TFT_recipe_builder.logic.enums import SubstrateType
from TFT_recipe_builder.logic.models import Recipe

logger = logging.getLogger(__name__)


class SaveRecipeDialog(QDialog):
    """Collect / edit the recipe name, substrate, node, description, active flag."""

    def __init__(self, parent=None, recipe: Optional[Recipe] = None):
        super().__init__(parent)
        self.setWindowTitle("Recipe Details")

        self.name_edit = QLineEdit()
        self.substrate_combo = QComboBox()
        self.substrate_combo.addItems(SubstrateType.values())
        self.node_edit = QLineEdit()
        self.node_edit.setPlaceholderText("e.g. 5µm")
        self.desc_edit = QPlainTextEdit()
        self.desc_edit.setFixedHeight(70)
        self.active_check = QCheckBox("Active")
        self.active_check.setChecked(True)

        form = QFormLayout(self)
        form.addRow("Recipe name:", self.name_edit)
        form.addRow("Substrate:", self.substrate_combo)
        form.addRow("Process node:", self.node_edit)
        form.addRow("Description:", self.desc_edit)
        form.addRow("", self.active_check)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

        if recipe is not None:
            self.name_edit.setText(recipe.recipe_name)
            if recipe.substrate_type:
                self.substrate_combo.setCurrentText(recipe.substrate_type)
            self.node_edit.setText(recipe.target_process_node)
            self.desc_edit.setPlainText(recipe.description)
            self.active_check.setChecked(recipe.is_active)

    def apply_to(self, recipe: Recipe) -> None:
        """Copy the dialog's header values onto an existing recipe object."""
        recipe.recipe_name = self.name_edit.text().strip()
        recipe.substrate_type = self.substrate_combo.currentText()
        recipe.target_process_node = self.node_edit.text().strip()
        recipe.description = self.desc_edit.toPlainText().strip()
        recipe.is_active = self.active_check.isChecked()

    def _on_accept(self) -> None:
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Invalid", "Recipe name is required.")
            return
        if not self.node_edit.text().strip():
            QMessageBox.warning(self, "Invalid", "Process node is required.")
            return
        self.accept()
