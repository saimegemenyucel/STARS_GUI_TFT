"""Curve Analysis panel: load Id-Vg / Id-Vd sweeps and extract TFT parameters.

This is the GUI front-end for :mod:`shared.tft_analysis` — the TFT analogue of
the memristor project's feature-extraction stage. The raw data are the transfer
and output measurement files; the panel displays the standard figures of merit
and the diagnostic plots.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from shared.tft_analysis import (
    extract_output_features,
    extract_transfer_features,
    load_output,
    load_transfer,
)
from shared.tft_plots import draw_full_analysis
from shared.db import get_connection
from shared.iv_ingest import ingest_file
from shared.iv_features import save_transfer_features
from shared.qt_widgets import PlusMinusSpin

logger = logging.getLogger(__name__)

_FILE_FILTER = "Measurement files (*.xls *.xlsx *.csv);;All files (*)"


class CurveAnalysisPanel(QWidget):
    """Load transfer/output sweeps, extract parameters and plot them."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._transfer = None        # TransferCurve
        self._transfer_feat = None   # TransferFeatures
        self._outputs = None         # list[OutputCurve]
        self._transfer_path = None
        self._outputs_path = None

        self.figure = Figure(figsize=(8, 6))
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)

        self._build_ui()
        self._redraw()

    # -- construction -------------------------------------------------------
    def _build_ui(self) -> None:
        # Device / oxide parameters (drive Vth & mobility extraction).
        self.w_spin = self._spin(0.1, 100000, 10.0, " µm")
        self.l_spin = self._spin(0.1, 100000, 5.0, " µm")
        self.tox_spin = self._spin(0.5, 1000, 25.0, " nm")
        self.eps_spin = self._spin(1.0, 100, 8.0, "")
        for s in (self.w_spin, self.l_spin, self.tox_spin, self.eps_spin):
            s.valueChanged.connect(self._reextract)

        param_box = QGroupBox("Device / oxide")
        pv = QVBoxLayout(param_box)
        pv.addWidget(PlusMinusSpin(self.w_spin, up_down=True, flat=True, label="W (µm)"))
        pv.addWidget(PlusMinusSpin(self.l_spin, up_down=True, flat=True, label="L (µm)"))
        pv.addWidget(PlusMinusSpin(self.tox_spin, up_down=True, flat=True, label="tox (nm)"))
        pv.addWidget(PlusMinusSpin(self.eps_spin, up_down=True, flat=True, label="εr"))
        hint = QLabel("Cox = ε0·εr / tox  →  drives Vth & mobility. "
                      "Set these to your real oxide.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#9aa0aa; font-size:11px;")
        pv.addWidget(hint)

        self.load_all_btn = QPushButton("Select transistor measurement…")
        self.load_all_btn.clicked.connect(self.prompt_and_load)
        self.load_all_btn.setMinimumHeight(42)
        self.load_all_btn.setStyleSheet("font-size:14px; font-weight:600;")

        self.save_db_btn = QPushButton("Save results to database")
        self.save_db_btn.clicked.connect(self.save_to_db)
        self.save_db_btn.setMinimumHeight(34)

        self.idvg_btn = QPushButton("Load Id-Vg only…")
        self.idvd_btn = QPushButton("Load Id-Vd only…")
        self.idvg_btn.clicked.connect(self.load_idvg)
        self.idvd_btn.clicked.connect(self.load_idvd)
        self.idvg_label = QLabel("— no transfer file —")
        self.idvd_label = QLabel("— no output file —")
        for lbl in (self.idvg_label, self.idvd_label):
            lbl.setWordWrap(True)
            lbl.setStyleSheet("color:#9aa0aa; font-size:11px;")

        load_box = QGroupBox("Raw data")
        lb = QVBoxLayout(load_box)
        lb.addWidget(self.load_all_btn)
        lb.addWidget(self.idvg_btn)
        lb.addWidget(self.idvg_label)
        lb.addWidget(self.idvd_btn)
        lb.addWidget(self.idvd_label)
        lb.addWidget(self.save_db_btn)

        controls = QWidget()
        cl = QVBoxLayout(controls)
        cl.addWidget(load_box)
        cl.addWidget(param_box)
        cl.addStretch(1)
        controls.setMaximumWidth(280)

        # Plot + parameter table in a vertical splitter.
        plot_side = QWidget()
        pl = QVBoxLayout(plot_side)
        pl.addWidget(self.toolbar)
        pl.addWidget(self.canvas, stretch=1)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Parameter", "Value", "Unit"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)

        right = QSplitter(Qt.Orientation.Vertical)
        right.addWidget(plot_side)
        right.addWidget(self.table)
        right.setSizes([520, 240])

        layout = QHBoxLayout(self)
        layout.addWidget(controls)
        layout.addWidget(right, stretch=1)

    def _spin(self, lo, hi, val, suffix) -> QDoubleSpinBox:
        s = QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setDecimals(2)
        s.setValue(val)
        s.setSuffix(suffix)
        s.setKeyboardTracking(False)
        s.setMinimumHeight(28)
        return s

    # -- loading ------------------------------------------------------------
    def prompt_and_load(self) -> None:
        """Ask for one or more Id-Vg / Id-Vd files and analyse them at once."""
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select Id-Vg and/or Id-Vd Excel files", "", _FILE_FILTER)
        if paths:
            self.load_paths(paths)

    def load_paths(self, paths: list[str]) -> None:
        """Classify each file (transfer vs output) by name/content and analyse."""
        errors: list[str] = []
        for path in paths:
            kind = self._classify(path)
            try:
                if kind == "vg":
                    self._transfer = load_transfer(path)
                    self._transfer_path = path
                    self.idvg_label.setText(Path(path).name)
                elif kind == "vd":
                    self._outputs = load_output(path)
                    self._outputs_path = path
                    self.idvd_label.setText(Path(path).name)
                self._maybe_parse_geometry(path)
            except Exception as exc:  # noqa: BLE001 - report and keep going
                errors.append(f"{Path(path).name}: {exc}")
        if errors:
            QMessageBox.warning(self, "Some files could not be read",
                                "\n".join(errors[:8]))
        self._reextract()

    def _classify(self, path: str) -> str:
        """Return 'vg' or 'vd' from the filename token, falling back to content."""
        low = Path(path).name.lower()
        if "idvg" in low:
            return "vg"
        if "idvd" in low:
            return "vd"
        # Unknown token: an output file usually has multiple bias families.
        try:
            if len(load_output(path)) >= 2:
                return "vd"
        except Exception:  # noqa: BLE001
            pass
        return "vg"

    def load_idvg(self) -> None:
        """Pick and load an Id-Vg transfer file."""
        path, _ = QFileDialog.getOpenFileName(self, "Load Id-Vg file", "", _FILE_FILTER)
        if not path:
            return
        try:
            self._transfer = load_transfer(path)
        except Exception as exc:  # pragma: no cover - defensive UI guard
            QMessageBox.critical(self, "Load failed", str(exc))
            return
        self._transfer_path = path
        self.idvg_label.setText(Path(path).name)
        self._maybe_parse_geometry(path)
        self._reextract()

    def load_idvd(self) -> None:
        """Pick and load an Id-Vd output file."""
        path, _ = QFileDialog.getOpenFileName(self, "Load Id-Vd file", "", _FILE_FILTER)
        if not path:
            return
        try:
            self._outputs = load_output(path)
        except Exception as exc:  # pragma: no cover - defensive UI guard
            QMessageBox.critical(self, "Load failed", str(exc))
            return
        self._outputs_path = path
        self.idvd_label.setText(Path(path).name)
        self._maybe_parse_geometry(path)
        self._reextract()

    def _maybe_parse_geometry(self, path: str) -> None:
        """Auto-fill W/L from an ``L<#>W<#>`` token in the filename, if present."""
        m = re.search(r"[Ll](\d+(?:\.\d+)?)[Ww](\d+(?:\.\d+)?)", Path(path).name)
        if m:
            self.l_spin.blockSignals(True); self.w_spin.blockSignals(True)
            self.l_spin.setValue(float(m.group(1)))
            self.w_spin.setValue(float(m.group(2)))
            self.l_spin.blockSignals(False); self.w_spin.blockSignals(False)

    # -- persistence --------------------------------------------------------
    def save_to_db(self) -> None:
        """Ingest the loaded raw files and store the computed transfer features."""
        if self._transfer is None and self._outputs is None:
            QMessageBox.information(self, "Save", "Load Excel data first.")
            return
        conn = get_connection()
        ingested = 0
        try:
            # Ingest raw sweeps (idempotent); ignore files that fail the naming rule.
            for path in (self._transfer_path, self._outputs_path):
                if not path:
                    continue
                try:
                    res = ingest_file(path, conn)
                    if not res["skipped"]:
                        ingested += 1
                except ValueError:
                    pass  # filename not in convention; features still saved below

            # Save computed transfer features, linked to the Id-Vg sweep if present.
            saved = False
            if self._transfer_feat is not None and self._transfer_path:
                name = Path(self._transfer_path).name
                row = conn.execute(
                    "SELECT sweep_id FROM iv_sweeps WHERE source_file = ?", (name,)
                ).fetchone()
                sweep_id = row[0] if row else None
                save_transfer_features(
                    conn, name, self._transfer_feat,
                    self.w_spin.value(), self.l_spin.value(),
                    self.tox_spin.value(), self.eps_spin.value(), sweep_id,
                )
                saved = True
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Save failed", str(exc))
            return
        finally:
            conn.close()
        msg = f"Raw sweeps ingested: {ingested}. "
        msg += "Features saved." if saved else "No transfer features to save."
        QMessageBox.information(self, "Saved to database", msg)

    # -- analysis -----------------------------------------------------------
    def _reextract(self) -> None:
        """Re-run feature extraction with the current W/L/tox/εr and refresh."""
        if self._transfer is not None:
            try:
                self._transfer_feat = extract_transfer_features(
                    self._transfer, self.w_spin.value(), self.l_spin.value(),
                    self.tox_spin.value(), self.eps_spin.value(),
                )
            except Exception:  # pragma: no cover - defensive UI guard
                logger.exception("Transfer extraction failed")
                self._transfer_feat = None
        self._redraw()
        self._fill_table()

    def _redraw(self) -> None:
        draw_full_analysis(self.figure, self._transfer, self._transfer_feat, self._outputs)
        self.canvas.draw_idle()

    def _fill_table(self) -> None:
        rows: list[tuple[str, str, str]] = []
        tf = self._transfer_feat
        if tf is not None:
            rows += [
                ("Threshold voltage Vth", f"{tf.vth_sat:.3f}", "V"),
                ("Subthreshold swing SS", f"{tf.ss_min:.1f}", "mV/dec"),
                ("On/Off ratio", f"{tf.on_off_ratio:.2e}", "—"),
                ("Ion (max |Id|)", f"{tf.ion:.3e}", "A"),
                ("Ioff (min |Id|)", f"{tf.ioff:.3e}", "A"),
                ("Peak transconductance gm", f"{tf.gm_max:.3e}", "S"),
                ("gm peak @ Vg", f"{tf.gm_max_vg:.2f}", "V"),
                ("Saturation mobility μ_sat", f"{tf.mu_sat:.2f}", "cm²/Vs"),
                ("Vth (transition, Zhou)", f"{tf.vth_transition:.3f}", "V"),
                ("μ_AVG peak (linear, Zhou)", f"{tf.mu_avg_peak:.2f}", "cm²/Vs"),
                ("Gate leakage (max |Ig|)", f"{tf.gate_leakage_max:.2e}", "A"),
                ("Cox", f"{tf.cox:.3e}", "F/cm²"),
            ]
        if self._outputs:
            for oc in self._outputs:
                of = extract_output_features(oc)
                rows.append((f"Idsat @ Vg={of.gate_v:+.1f} V", f"{of.idsat:.3e}", "A"))
                rows.append((f"Ron @ Vg={of.gate_v:+.1f} V", f"{of.ron:.3e}", "Ω"))
                rows.append((f"gd @ Vg={of.gate_v:+.1f} V", f"{of.gd:.3e}", "S"))

        self.table.setRowCount(len(rows))
        for r, (name, val, unit) in enumerate(rows):
            self.table.setItem(r, 0, QTableWidgetItem(name))
            item_v = QTableWidgetItem(val)
            item_v.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(r, 1, item_v)
            self.table.setItem(r, 2, QTableWidgetItem(unit))
        self.table.resizeColumnsToContents()
