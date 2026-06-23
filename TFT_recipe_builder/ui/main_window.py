"""Main window for the recipe builder: header + step table editor."""

from __future__ import annotations

import logging
from copy import deepcopy

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from TFT_recipe_builder.bootstrap import config
from TFT_recipe_builder.bootstrap.container import Container
from TFT_recipe_builder.logic.models import Recipe
from TFT_recipe_builder.logic.recipe_service import RecipeExistsError
from TFT_recipe_builder.logic.validation import validate_recipe
from TFT_recipe_builder.ui.dialogs.process_step_dialog import (
    ProcessStepDialog,
    format_gas_mixture,
)
from TFT_recipe_builder.ui.dialogs.save_recipe_dialog import SaveRecipeDialog
from TFT_recipe_builder.ui.recipe_list import RecipeListPanel
from TFT_recipe_builder.ui.device_structure_panel import DeviceStructurePanel

logger = logging.getLogger(__name__)

_STEP_HEADERS = [
    "#", "Type", "Name", "Temp (°C)", "Dur (min)", "Pressure", "Power", "Gas", "Notes",
]


def _empty_recipe() -> Recipe:
    """Return a blank draft recipe."""
    return Recipe(recipe_name="", substrate_type="glass", target_process_node="")


class MainWindow(QMainWindow):
    """Recipe editor window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{config.APP_NAME} v{config.APP_VERSION}")
        self.setGeometry(*config.WINDOW_GEOMETRY)

        self.container = Container()
        self._recipe: Recipe = _empty_recipe()

        self._build_ui()
        self._build_menu()
        self._refresh_all()

    # -- construction -------------------------------------------------------
    def _build_ui(self) -> None:
        self.recipe_panel = RecipeListPanel(self.container.main_service)
        self.recipe_panel.new_requested.connect(self.new_recipe)
        self.recipe_panel.load_requested.connect(self.load_recipe)
        self.recipe_panel.delete_requested.connect(self.delete_recipe)

        # Header summary + edit button.
        self.header_label = QLabel()
        self.header_label.setWordWrap(True)
        self.header_label.setTextFormat(Qt.TextFormat.RichText)
        edit_info_btn = QPushButton("Edit Recipe Details…")
        edit_info_btn.clicked.connect(self.edit_details)
        header_box = QGroupBox("Recipe")
        hb = QVBoxLayout(header_box)
        hb.addWidget(self.header_label)
        hb.addWidget(edit_info_btn)

        # Step table.
        self.table = QTableWidget(0, len(_STEP_HEADERS))
        self.table.setHorizontalHeaderLabels(_STEP_HEADERS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(lambda _i: self.edit_step())
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )

        # Step action buttons.
        self.add_btn = QPushButton("Add Step")
        self.edit_btn = QPushButton("Edit Step")
        self.remove_btn = QPushButton("Remove Step")
        self.up_btn = QPushButton("Move Up")
        self.down_btn = QPushButton("Move Down")
        self.save_btn = QPushButton("Save Recipe")
        self.add_btn.clicked.connect(self.add_step)
        self.edit_btn.clicked.connect(self.edit_step)
        self.remove_btn.clicked.connect(self.remove_step)
        self.up_btn.clicked.connect(lambda: self.move_step(-1))
        self.down_btn.clicked.connect(lambda: self.move_step(1))
        self.save_btn.clicked.connect(self.save_recipe)

        btn_row = QHBoxLayout()
        for b in (self.add_btn, self.edit_btn, self.remove_btn,
                  self.up_btn, self.down_btn):
            btn_row.addWidget(b)
        btn_row.addStretch(1)
        btn_row.addWidget(self.save_btn)

        centre = QWidget()
        cl = QVBoxLayout(centre)
        cl.addWidget(header_box)
        cl.addWidget(self.table, stretch=1)
        cl.addLayout(btn_row)

        # Central editor is a tabbed view: process-step editor + device cross-section.
        self.device_panel = DeviceStructurePanel()
        self.editor_tabs = QTabWidget()
        self.editor_tabs.addTab(centre, "Process Steps")
        self.editor_tabs.addTab(self.device_panel, "Device Structure")

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.recipe_panel)
        splitter.addWidget(self.editor_tabs)
        splitter.setSizes([300, 860])
        self.setCentralWidget(splitter)
        self.statusBar().showMessage("Ready.")

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        new_action = QAction("&New Recipe", self)
        new_action.setShortcut(QKeySequence("Ctrl+N"))
        new_action.triggered.connect(self.new_recipe)
        file_menu.addAction(new_action)

        save_action = QAction("&Save Recipe", self)
        save_action.setShortcut(QKeySequence("Ctrl+S"))
        save_action.triggered.connect(self.save_recipe)
        file_menu.addAction(save_action)

        file_menu.addSeparator()
        quit_action = QAction("&Quit", self)
        quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

    # -- recipe-level actions ----------------------------------------------
    def new_recipe(self) -> None:
        """Start a fresh draft recipe after collecting header details."""
        draft = _empty_recipe()
        dialog = SaveRecipeDialog(self, draft)
        if dialog.exec():
            dialog.apply_to(draft)
            self._recipe = draft
            self._refresh_all()
            self.statusBar().showMessage(f"New recipe '{draft.recipe_name}'.")

    def edit_details(self) -> None:
        """Edit the current recipe's header fields."""
        dialog = SaveRecipeDialog(self, self._recipe)
        if dialog.exec():
            dialog.apply_to(self._recipe)
            self._after_change("Recipe details updated.")

    def load_recipe(self, recipe_id: int) -> None:
        """Load a saved recipe into the editor."""
        recipe = self.container.main_service.load_recipe(recipe_id)
        if recipe is None:
            QMessageBox.warning(self, "Load", "Recipe not found.")
            return
        # deepcopy so edits do not mutate anything cached.
        self._recipe = deepcopy(recipe)
        self._refresh_all()
        self.statusBar().showMessage(f"Loaded '{recipe.recipe_name}'.")

    def delete_recipe(self, recipe_id: int) -> None:
        """Delete a saved recipe after confirmation."""
        reply = QMessageBox.question(
            self, "Delete recipe", "Delete the selected recipe permanently?"
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.container.main_service.delete_recipe(recipe_id)
        if self._recipe.recipe_id == recipe_id:
            self._recipe = _empty_recipe()
        self._refresh_all()
        self.statusBar().showMessage("Recipe deleted.")

    def save_recipe(self) -> None:
        """Validate and persist the current recipe to the main database."""
        errors = validate_recipe(self._recipe)
        if errors:
            QMessageBox.warning(self, "Cannot save", "\n".join(errors))
            return
        try:
            self.container.commit_to_main(self._recipe)
        except RecipeExistsError as exc:
            QMessageBox.warning(self, "Name conflict", str(exc))
            return
        self.recipe_panel.refresh()
        self.statusBar().showMessage(f"Saved '{self._recipe.recipe_name}'.")

    # -- step-level actions -------------------------------------------------
    def add_step(self) -> None:
        """Append a new process step."""
        dialog = ProcessStepDialog(self)
        if dialog.exec():
            order = len(self._recipe.steps) + 1
            self._recipe.steps.append(dialog.build_step(order))
            self._after_change("Step added.")

    def edit_step(self) -> None:
        """Edit the selected process step."""
        row = self.table.currentRow()
        if row < 0:
            return
        dialog = ProcessStepDialog(self, self._recipe.steps[row])
        if dialog.exec():
            self._recipe.steps[row] = dialog.build_step(row + 1)
            self._after_change("Step updated.")
            self.table.selectRow(row)

    def remove_step(self) -> None:
        """Remove the selected process step."""
        row = self.table.currentRow()
        if row < 0:
            return
        del self._recipe.steps[row]
        self._after_change("Step removed.")

    def move_step(self, delta: int) -> None:
        """Move the selected step up (delta=-1) or down (delta=+1)."""
        row = self.table.currentRow()
        new_row = row + delta
        if row < 0 or not (0 <= new_row < len(self._recipe.steps)):
            return
        steps = self._recipe.steps
        steps[row], steps[new_row] = steps[new_row], steps[row]
        self._after_change("Step reordered.")
        self.table.selectRow(new_row)

    # -- presentation -------------------------------------------------------
    def _after_change(self, message: str) -> None:
        """Renumber, autosave the draft, refresh the table, update the status."""
        self._recipe.renumber_steps()
        self.container.autosave_working(self._recipe)
        self._refresh_table()
        self._refresh_header()
        self.statusBar().showMessage(message)

    def _refresh_all(self) -> None:
        self._refresh_header()
        self._refresh_table()
        self.recipe_panel.refresh()

    def _refresh_header(self) -> None:
        r = self._recipe
        self.header_label.setText(
            "<b>{name}</b><br>Substrate: {sub} &nbsp; Node: {node}<br>"
            "Steps: {n} &nbsp; Est. duration: {dur:.0f} min<br>"
            "<i>{desc}</i>".format(
                name=r.recipe_name or "(unnamed draft)",
                sub=r.substrate_type or "—",
                node=r.target_process_node or "—",
                n=r.step_count,
                dur=r.estimated_duration_min,
                desc=r.description or "",
            )
        )

    def _refresh_table(self) -> None:
        self.table.setRowCount(len(self._recipe.steps))
        for row, step in enumerate(self._recipe.steps):
            values = [
                str(step.step_order),
                step.process_type,
                step.process_name,
                _fmt(step.temperature),
                _fmt(step.duration),
                _fmt(step.pressure),
                _fmt(step.power),
                format_gas_mixture(step.gas_mixture),
                step.notes,
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                if col in (0, 3, 4, 5, 6):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, col, item)

    def closeEvent(self, event):  # noqa: N802
        """Close database connections cleanly on exit."""
        self.container.close()
        super().closeEvent(event)


def _fmt(value) -> str:
    """Format an optional numeric cell value."""
    return "" if value is None else f"{value:g}"
