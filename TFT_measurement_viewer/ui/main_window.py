"""Main window: wafer selection, in-memory filtering, table + plots."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from TFT_measurement_viewer.bootstrap import config
from TFT_measurement_viewer.logic.data_validator import validate_measurements
from TFT_measurement_viewer.sql import db_ops
from TFT_measurement_viewer.ui.measurement_table import MeasurementTable
from TFT_measurement_viewer.ui.plot_panel import PlotPanel
from TFT_measurement_viewer.ui.curve_analysis_panel import CurveAnalysisPanel
from TFT_measurement_viewer.ui.db_browser_panel import DatabaseBrowserPanel
from shared.parameters import PARAMETERS
from shared.db import get_connection
from shared.iv_ingest import ingest_file
from shared.tft_analysis import load_output_from_db, load_transfer_from_db
from shared import wafer_map

logger = logging.getLogger(__name__)

_STATUS_OPTIONS = ["All", "Functional only", "Failed only"]


class MainWindow(QMainWindow):
    """Top-level window for browsing TFT measurements."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{config.APP_NAME} v{config.APP_VERSION}")
        self.setGeometry(*config.WINDOW_GEOMETRY)

        # Full (unfiltered) measurement set for the selected wafer.
        self._all_measurements: pd.DataFrame = pd.DataFrame()
        self._current_wafer_id: str | None = None

        self._build_ui()
        self._build_menu()
        self.reload_wafers()

        # On launch, jump to Curve Analysis and immediately ask for Excel data.
        QTimer.singleShot(200, self._startup_prompt)

    # -- construction -------------------------------------------------------
    def _build_ui(self) -> None:
        self.wafer_list = QListWidget()
        self.wafer_list.currentItemChanged.connect(self._on_wafer_selected)

        # Filters.
        self.status_combo = QComboBox()
        self.status_combo.addItems(_STATUS_OPTIONS)
        self.defect_combo = QComboBox()
        self.param_filter_combo = QComboBox()
        self.param_filter_combo.addItem("(none)", None)
        for info in PARAMETERS:
            self.param_filter_combo.addItem(info.label, info.key)
        self.min_spin = QDoubleSpinBox()
        self.max_spin = QDoubleSpinBox()
        for spin in (self.min_spin, self.max_spin):
            spin.setRange(-1e9, 1e9)
            spin.setDecimals(4)
        self.min_spin.setValue(-1e9)
        self.max_spin.setValue(1e9)
        for w in (self.status_combo, self.defect_combo, self.param_filter_combo):
            w.currentIndexChanged.connect(self._apply_filters)
        self.min_spin.valueChanged.connect(self._apply_filters)
        self.max_spin.valueChanged.connect(self._apply_filters)

        filter_box = QGroupBox("Filters")
        form = QFormLayout(filter_box)
        form.addRow("Status:", self.status_combo)
        form.addRow("Defect type:", self.defect_combo)
        form.addRow("Parameter:", self.param_filter_combo)
        form.addRow("Min:", self.min_spin)
        form.addRow("Max:", self.max_spin)

        wafer_box = QGroupBox("Wafers")
        wafer_layout = QVBoxLayout(wafer_box)
        wafer_layout.addWidget(self.wafer_list)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(wafer_box, stretch=2)
        left_layout.addWidget(filter_box, stretch=1)

        # Centre: measurement table + jump-to-curve-analysis button.
        self.table = MeasurementTable()
        self.table.doubleClicked.connect(self._on_table_row_activated)
        self.view_curve_btn = QPushButton("View Curve Analysis →")
        self.view_curve_btn.setToolTip(
            "Show the selected transistor's raw I-V curves in the Curve "
            "Analysis tab (or double-click a row / click a point on the map).")
        self.view_curve_btn.clicked.connect(self._on_view_curve_clicked)
        table_box = QWidget()
        table_layout = QVBoxLayout(table_box)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.addWidget(self.table, stretch=1)
        table_layout.addWidget(self.view_curve_btn)

        # Right: metadata + plots.
        self.meta_label = QLabel("No wafer selected.")
        self.meta_label.setWordWrap(True)
        self.meta_label.setTextFormat(Qt.TextFormat.RichText)
        meta_box = QGroupBox("Wafer metadata")
        meta_layout = QVBoxLayout(meta_box)
        meta_layout.addWidget(self.meta_label)

        self.plot_panel = PlotPanel()
        self.plot_panel.deviceActivated.connect(self._open_curve_analysis_for_device)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(meta_box)
        right_layout.addWidget(self.plot_panel, stretch=1)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(table_box)
        splitter.addWidget(right)
        splitter.setSizes([260, 560, 460])

        # Tabbed central area: device measurements + raw-curve analysis.
        self.curve_panel = CurveAnalysisPanel()
        self.tabs = QTabWidget()
        self.tabs.addTab(splitter, "Measurements")
        self.tabs.addTab(self.curve_panel, "Curve Analysis")
        self.db_browser = DatabaseBrowserPanel()
        self.tabs.addTab(self.db_browser, "Database")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.setCentralWidget(self.tabs)

        self.statusBar().showMessage("Ready.")

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")

        refresh = QAction("&Refresh", self)
        refresh.setShortcut(QKeySequence("F5"))
        refresh.triggered.connect(self.reload_wafers)
        file_menu.addAction(refresh)

        export = QAction("&Export filtered to CSV…", self)
        export.setShortcut(QKeySequence("Ctrl+E"))
        export.triggered.connect(self.export_csv)
        file_menu.addAction(export)

        import_iv = QAction("&Import I-V sweeps…", self)
        import_iv.setShortcut(QKeySequence("Ctrl+I"))
        import_iv.triggered.connect(self.import_iv_sweeps)
        file_menu.addAction(import_iv)

        file_menu.addSeparator()
        quit_action = QAction("&Quit", self)
        quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

    # -- tabs ---------------------------------------------------------------
    def _on_tab_changed(self, _index: int) -> None:
        """Refresh the Database browser whenever it becomes visible."""
        if self.tabs.currentWidget() is self.db_browser:
            self.db_browser.refresh()

    # -- startup ------------------------------------------------------------
    def _startup_prompt(self) -> None:
        """Switch to Curve Analysis and prompt for measurement files on launch."""
        self.tabs.setCurrentWidget(self.curve_panel)
        self.curve_panel.prompt_and_load()

    # -- data flow ----------------------------------------------------------
    def reload_wafers(self) -> None:
        """Reload the wafer list from the database (preloaded metadata)."""
        self.wafer_list.clear()
        try:
            meta = db_ops.load_wafer_metadata()
        except Exception as exc:  # pragma: no cover - defensive UI guard
            logger.exception("Failed to load wafers")
            QMessageBox.critical(self, "Database error", str(exc))
            return

        if meta.empty:
            self.statusBar().showMessage("No wafers in database. Import data first.")
            return

        for _, row in meta.iterrows():
            item = QListWidgetItem(str(row["wafer_id"]))
            item.setData(Qt.ItemDataRole.UserRole, row["wafer_id"])
            self.wafer_list.addItem(item)
        self.statusBar().showMessage(f"Loaded {len(meta)} wafers.")

    def _on_wafer_selected(self, current: QListWidgetItem, _previous=None) -> None:
        if current is None:
            return
        wafer_id = current.data(Qt.ItemDataRole.UserRole)
        self._current_wafer_id = wafer_id
        try:
            self._all_measurements = self._load_wafer_cells(wafer_id)
        except Exception as exc:  # pragma: no cover - defensive UI guard
            logger.exception("Failed to load wafer %s", wafer_id)
            QMessageBox.critical(self, "Database error", str(exc))
            return

        # Defect filter is just "All" here (per-transistor defect typing TBD).
        self.defect_combo.blockSignals(True)
        self.defect_combo.clear()
        self.defect_combo.addItem("All", None)
        self.defect_combo.blockSignals(False)

        self._update_metadata(wafer_id, self._all_measurements)
        self._apply_filters()

    def _load_wafer_cells(self, wafer_id: str) -> pd.DataFrame:
        """Load a wafer's measured transistors (iv_sweeps + features) as a
        DataFrame shaped for the table / filters / spatial map."""
        conn = get_connection()
        try:
            cells = wafer_map.get_cells(conn, wafer_id=wafer_id)
        finally:
            conn.close()
        return wafer_map.cells_to_measurement_df(cells)

    def _apply_filters(self) -> None:
        """Filter the in-memory measurement set and refresh table + plots."""
        df = self._all_measurements
        if df.empty:
            self.table.set_data(df)
            self.plot_panel.set_data(df)
            return

        mask = pd.Series(True, index=df.index)

        status = self.status_combo.currentText()
        if status == "Functional only":
            mask &= df["is_functional"] == True   # noqa: E712
        elif status == "Failed only":
            mask &= df["is_functional"] != True    # noqa: E712

        defect = self.defect_combo.currentData()
        if defect is not None:
            mask &= df["defect_type"] == defect

        param = self.param_filter_combo.currentData()
        if param is not None and param in df.columns:
            values = pd.to_numeric(df[param], errors="coerce")
            mask &= (values >= self.min_spin.value()) & (values <= self.max_spin.value())

        filtered = df[mask]
        self.table.set_data(filtered)
        self.plot_panel.set_data(filtered)
        self._update_status(filtered)

    # -- presentation -------------------------------------------------------
    def _update_metadata(self, wafer_id: str, df: pd.DataFrame) -> None:
        n = len(df)
        if n == 0:
            self.meta_label.setText(
                f"<b>{wafer_id}</b><br>No measured transistors found.<br>"
                "Load this wafer's folder in the Yield Analyzer, or import its "
                "sweeps (File ▸ Import I-V sweeps), then Refresh (F5).")
            return
        func = int((df["is_functional"] == True).sum())   # noqa: E712
        dies = df["device_id"].str.split(" ").str[0].nunique()
        mats = ", ".join(sorted({m for m in df["material"].dropna()}))
        self.meta_label.setText(
            f"<b>{wafer_id}</b><br>"
            f"Transistors measured: {n}<br>"
            f"Functional: {func}<br>"
            f"Dies with data: {dies}<br>"
            f"Yield: {(func / n * 100.0):.1f}%<br>"
            f"Materials: {mats or '—'}"
        )

    def _update_status(self, filtered: pd.DataFrame) -> None:
        total = len(filtered)
        functional = int((filtered["is_functional"] == True).sum()) if total else 0  # noqa: E712
        yield_pct = (functional / total * 100.0) if total else 0.0
        report = validate_measurements(filtered)
        self.statusBar().showMessage(
            f"Showing {total} devices | functional {functional} "
            f"| yield {yield_pct:.1f}% | {report.summary()}"
        )

    # -- actions ------------------------------------------------------------
    def import_iv_sweeps(self) -> None:
        """Ingest selected .xls/.xlsx I-V sweep files into the database."""
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Import I-V sweep files", "",
            "Measurement files (*.xls *.xlsx);;All files (*)")
        if not paths:
            return
        ingested = skipped = failed = 0
        errors: list[str] = []
        conn = get_connection()
        try:
            for path in paths:
                try:
                    res = ingest_file(path, conn)
                    if res["skipped"]:
                        skipped += 1
                    else:
                        ingested += 1
                except Exception as exc:  # noqa: BLE001 - report, keep going
                    failed += 1
                    errors.append(f"{Path(path).name}: {exc}")
        finally:
            conn.close()
        summary = f"Imported {ingested}, skipped {skipped}, failed {failed}."
        detail = summary + ("\n\n" + "\n".join(errors[:8]) if errors else "")
        QMessageBox.information(self, "Import I-V sweeps", detail)
        self.statusBar().showMessage(summary)

    def export_csv(self) -> None:
        """Export the currently filtered measurements to a CSV file."""
        df = self.table.current_dataframe()
        if df.empty:
            QMessageBox.information(self, "Export", "Nothing to export.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export filtered measurements", "measurements.csv",
            "CSV files (*.csv)"
        )
        if not path:
            return
        try:
            df.to_csv(path, index=False)
            self.statusBar().showMessage(f"Exported {len(df)} rows to {path}")
        except OSError as exc:
            QMessageBox.critical(self, "Export failed", str(exc))

    # -- jump to Curve Analysis for one transistor ---------------------------
    def _on_table_row_activated(self, index) -> None:
        """Double-clicking a table row opens that device in Curve Analysis."""
        device_id = self.table.device_id_at(index)
        if device_id:
            self._open_curve_analysis_for_device(device_id)

    def _on_view_curve_clicked(self) -> None:
        """The 'View Curve Analysis' button uses the currently selected row."""
        device_id = self.table.current_device_id()
        if device_id:
            self._open_curve_analysis_for_device(device_id)
        else:
            QMessageBox.information(self, "View Curve Analysis",
                                     "Select a transistor in the table first.")

    def _open_curve_analysis_for_device(self, device_id: str) -> None:
        """Reload a device's raw sweeps from the DB and show them in Curve Analysis.

        ``device_id`` looks like ``"C2R3 c1r1"`` (die token + transistor
        token); both come straight from ``iv_sweeps`` so no original Excel
        file is needed to redisplay the curve.
        """
        if not self._current_wafer_id:
            return
        parts = device_id.split(" ", 1)
        if len(parts) != 2:
            return
        die_tok, sub_tok = parts
        conn = get_connection()
        try:
            sweep_ids = wafer_map.sweep_ids_for_device(
                conn, self._current_wafer_id, die_tok, sub_tok)
            transfer = (load_transfer_from_db(conn, sweep_ids["IdVg"])
                        if "IdVg" in sweep_ids else None)
            outputs = (load_output_from_db(conn, sweep_ids["IdVd"])
                       if "IdVd" in sweep_ids else None)
        except Exception as exc:  # pragma: no cover - defensive UI guard
            logger.exception("Failed to load curves for device %s", device_id)
            QMessageBox.critical(self, "Database error", str(exc))
            return
        finally:
            conn.close()

        if transfer is None and not outputs:
            QMessageBox.information(
                self, "View Curve Analysis",
                f"No raw Id-Vg/Id-Vd sweep stored for {device_id}.")
            return

        self.curve_panel.load_from_db(device_id, transfer, outputs)
        self.tabs.setCurrentWidget(self.curve_panel)
        self.statusBar().showMessage(f"Showing curves for {device_id}.")
