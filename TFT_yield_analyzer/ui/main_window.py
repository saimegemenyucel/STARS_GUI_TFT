"""Main window for the yield analyzer."""

from __future__ import annotations

import logging

import pandas as pd
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableView,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from TFT_yield_analyzer.bootstrap import config
from TFT_yield_analyzer.logic.clustering import find_hotspots
from TFT_yield_analyzer.logic.yield_calculator import YieldMetrics, calculate_yield
from TFT_yield_analyzer.sql import db_ops
from TFT_yield_analyzer.ui.defect_map_viewer import DefectMapViewer
from TFT_yield_analyzer.ui.yield_dashboard import YieldDashboard
from TFT_yield_analyzer.ui.wafer_map_panel import WaferMapPanel
from shared.criteria import load_criteria
from shared import wafer_map
from shared.wafer_ingest import ingest_wafer_folder
from shared.db import get_connection
from shared.qt_models import DataFrameModel

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Top-level window: pick a wafer, calculate and persist yield metrics."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{config.APP_NAME} v{config.APP_VERSION}")
        self.setGeometry(*config.WINDOW_GEOMETRY)

        self._current_wafer: str | None = None
        self._current_df: pd.DataFrame = pd.DataFrame()
        self._current_metrics: YieldMetrics | None = None

        self._build_ui()
        self._build_menu()
        self.reload_wafers()

    def _build_ui(self) -> None:
        self.wafer_list = QListWidget()
        self.wafer_list.currentItemChanged.connect(self._on_wafer_selected)

        self.calc_btn = QPushButton("Calculate Yield")
        self.calc_btn.clicked.connect(self.calculate)
        self.save_btn = QPushButton("Save Metrics to DB")
        self.save_btn.clicked.connect(self.save_metrics)
        self.save_btn.setEnabled(False)

        self.load_folder_btn = QPushButton("Load wafer folder…")
        self.load_folder_btn.setMinimumHeight(40)
        self.load_folder_btn.setStyleSheet("font-weight:600;")
        self.load_folder_btn.clicked.connect(self.load_wafer_folder)

        wafer_box = QGroupBox("Wafers")
        wb = QVBoxLayout(wafer_box)
        wb.addWidget(self.load_folder_btn)
        wb.addWidget(self.wafer_list)
        wb.addWidget(self.calc_btn)
        wb.addWidget(self.save_btn)

        # Tabs: dashboard / defect map / history.
        self.dashboard = YieldDashboard()
        self.defect_map = DefectMapViewer()

        self.history_model = DataFrameModel()
        self.history_table = QTableView()
        self.history_table.setModel(self.history_model)

        self.wafer_map = WaferMapPanel()
        self.tabs = QTabWidget()
        self.tabs.addTab(self.dashboard, "Dashboard")
        self.tabs.addTab(self.defect_map, "Defect Map")
        self.tabs.addTab(self.wafer_map, "Wafer Map")
        self.tabs.addTab(self.history_table, "Metric History")
        self.tabs.currentChanged.connect(self._on_tab_changed)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(wafer_box)
        splitter.addWidget(self.tabs)
        splitter.setSizes([260, 1000])
        self.setCentralWidget(splitter)
        self.statusBar().showMessage("Ready.")

    def _on_tab_changed(self, _index: int) -> None:
        """Re-feed the wafer map when it becomes visible (picks up new data)."""
        if self.tabs.currentWidget() is self.wafer_map and self._current_wafer:
            self._update_wafer_map(self._current_wafer)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        refresh = QAction("&Refresh", self)
        refresh.setShortcut(QKeySequence("F5"))
        refresh.triggered.connect(self.reload_wafers)
        file_menu.addAction(refresh)

        save = QAction("&Save metrics", self)
        save.setShortcut(QKeySequence("Ctrl+S"))
        save.triggered.connect(self.save_metrics)
        file_menu.addAction(save)

        file_menu.addSeparator()
        quit_action = QAction("&Quit", self)
        quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

    # -- data flow ----------------------------------------------------------
    def reload_wafers(self, select: str | None = None) -> None:
        """Reload the wafer list (folder-imported wafers included)."""
        self.wafer_list.blockSignals(True)
        self.wafer_list.clear()
        try:
            meta = db_ops.load_wafer_metadata()
        except Exception as exc:  # pragma: no cover - defensive UI guard
            QMessageBox.critical(self, "Database error", str(exc))
            self.wafer_list.blockSignals(False)
            return
        for _, row in meta.iterrows():
            item = QListWidgetItem(str(row["wafer_id"]))
            item.setData(Qt.ItemDataRole.UserRole, row["wafer_id"])
            self.wafer_list.addItem(item)
        self.wafer_list.blockSignals(False)

        if not meta.empty:
            target = select or self._current_wafer
            items = (self.wafer_list.findItems(target, Qt.MatchFlag.MatchExactly)
                     if target else [])
            self.wafer_list.setCurrentItem(items[0] if items
                                           else self.wafer_list.item(0))
        self.statusBar().showMessage(f"Loaded {len(meta)} wafers.")

    def load_wafer_folder(self) -> None:
        """Import a folder as one wafer (folder name = wafer id) and show it."""
        folder = QFileDialog.getExistingDirectory(self, "Select a wafer folder")
        if not folder:
            return
        conn = get_connection()
        try:
            summary = ingest_wafer_folder(folder, conn)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Import failed", str(exc))
            return
        finally:
            conn.close()
        QMessageBox.information(
            self, "Wafer imported",
            f"Wafer '{summary['wafer_id']}': {summary['ingested']} files ingested, "
            f"{summary['features']} analysed, {len(summary['failed'])} skipped.")
        self.reload_wafers(select=summary["wafer_id"])

    def _update_wafer_map(self, wafer_id: str) -> None:
        """Load the wafer's cells and hand them to the map panel."""
        conn = get_connection()
        try:
            cells = wafer_map.get_cells(conn, wafer_id=wafer_id)
        finally:
            conn.close()
        self.wafer_map.display(wafer_id, cells)

    def _on_wafer_selected(self, current: QListWidgetItem, _previous=None) -> None:
        if current is None:
            return
        self._current_wafer = current.data(Qt.ItemDataRole.UserRole)
        self.save_btn.setEnabled(False)
        self._current_metrics = None
        try:
            # Devices live in iv_sweeps/tft_curve_features (populated by the
            # I-V ingest pipeline / "Load wafer folder..."), not the legacy
            # tft_measurements table -- same source the Wafer Map tab uses.
            conn = get_connection()
            try:
                cells = wafer_map.get_cells(conn, wafer_id=self._current_wafer)
            finally:
                conn.close()
            self._current_df = wafer_map.cells_to_measurement_df(cells)
            self.history_model.set_dataframe(
                db_ops.load_metric_history(self._current_wafer)
            )
        except Exception as exc:  # pragma: no cover - defensive UI guard
            QMessageBox.critical(self, "Database error", str(exc))
            return
        self.history_table.resizeColumnsToContents()
        self._update_wafer_map(self._current_wafer)
        self.statusBar().showMessage(
            f"{self._current_wafer}: {len(self._current_df)} device rows | "
            "wafer map updated."
        )

    def calculate(self) -> None:
        """Compute yield metrics for the selected wafer and refresh the views."""
        if not self._current_wafer or self._current_df.empty:
            QMessageBox.information(self, "Calculate", "Select a wafer with data first.")
            return
        conn = get_connection()
        try:
            criteria = load_criteria(conn)
        finally:
            conn.close()

        metrics = calculate_yield(self._current_wafer, self._current_df, criteria)
        self._current_metrics = metrics
        hotspots = find_hotspots(self._current_df)

        self.dashboard.update_dashboard(metrics, self._current_df)
        self.defect_map.update_map(self._current_df, hotspots)
        self.save_btn.setEnabled(True)
        self.statusBar().showMessage(
            f"{self._current_wafer}: yield {metrics.overall_yield_percentage:.1f}% "
            f"| {len(hotspots)} hotspot(s)."
        )

    def save_metrics(self) -> None:
        """Persist the most recent calculation to the yield_metrics table."""
        if self._current_metrics is None:
            QMessageBox.information(self, "Save", "Calculate yield first.")
            return
        try:
            metric_id = db_ops.save_yield_metrics(self._current_metrics.as_table_row())
            self.history_model.set_dataframe(
                db_ops.load_metric_history(self._current_wafer)
            )
        except Exception as exc:  # pragma: no cover - defensive UI guard
            QMessageBox.critical(self, "Save failed", str(exc))
            return
        self.statusBar().showMessage(f"Saved metrics (id={metric_id}).")
