"""Interactive wafer map (driven by the host window's wafer selection).

The host supplies a wafer id and its cell data via :meth:`display`; this panel
draws the two-level map:

    Wafer view — dies coloured by yield; click a die to zoom in.
    Die view   — transistor cells (green=pass, red=fail, grey=no data), or
                 coloured by a chosen feature; click a cell for its measurements.

Grid sizes auto-fit the largest die / transistor position in the data and can
then be nudged with the +/- controls.
"""

from __future__ import annotations

import logging

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
from PyQt6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from shared import wafer_map
from shared.qt_widgets import PlusMinusSpin

logger = logging.getLogger(__name__)

_PASS = "#2ca02c"
_FAIL = "#d62728"
_NODATA = "#3a3c46"
_METRICS = {
    "Pass / Fail": None,
    "Vth (V)": "vth",
    "Mobility (cm²/Vs)": "mu_sat",
    "On/Off ratio": "on_off_ratio",
    "SS (mV/dec)": "ss_min",
}


class WaferMapPanel(QWidget):
    """A two-level interactive wafer/die map fed by the host window."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cells = wafer_map.pd.DataFrame()
        self._wafer_id = None
        self._view = "wafer"
        self._current_die = None

        self.figure = Figure(figsize=(7, 6))
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.mpl_connect("button_press_event", self._on_click)

        self._build_ui()
        self._draw_wafer()

    # -- construction -------------------------------------------------------
    def _build_ui(self) -> None:
        self.die_rows = self._pm(1, 200, 7)
        self.die_cols = self._pm(1, 200, 4)
        self.tr_rows = self._pm(1, 200, 8)
        self.tr_cols = self._pm(1, 200, 8)
        grid_box = QGroupBox("Grid (auto-fits the data)")
        gl = QHBoxLayout(grid_box)
        gl.addWidget(QLabel("Dies  rows:")); gl.addWidget(self.die_rows)
        gl.addWidget(QLabel("cols:")); gl.addWidget(self.die_cols)
        gl.addSpacing(16)
        gl.addWidget(QLabel("Transistors  rows:")); gl.addWidget(self.tr_rows)
        gl.addWidget(QLabel("cols:")); gl.addWidget(self.tr_cols)
        gl.addStretch(1)

        self.back_btn = QPushButton("← Back to wafer")
        self.back_btn.clicked.connect(self._show_wafer)
        self.back_btn.setVisible(False)
        self.color_combo = QComboBox()
        self.color_combo.addItems(list(_METRICS.keys()))
        self.color_combo.currentIndexChanged.connect(self._redraw)
        ctrl = QHBoxLayout()
        ctrl.addWidget(self.back_btn)
        ctrl.addWidget(QLabel("Colour by:"))
        ctrl.addWidget(self.color_combo)
        ctrl.addStretch(1)

        centre = QWidget()
        cl = QVBoxLayout(centre)
        cl.addWidget(grid_box)
        cl.addLayout(ctrl)
        cl.addWidget(self.canvas, stretch=1)

        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setMaximumWidth(340)

        layout = QHBoxLayout(self)
        layout.addWidget(centre, stretch=1)
        layout.addWidget(self.detail)

    def _pm(self, lo, hi, val) -> PlusMinusSpin:
        spin = QSpinBox()
        spin.setRange(lo, hi)
        spin.setValue(val)
        spin.setMinimumHeight(30)
        spin.setMaximumWidth(64)
        spin.valueChanged.connect(self._redraw)
        return PlusMinusSpin(spin)

    # -- public API ---------------------------------------------------------
    def display(self, wafer_id: str | None, cells) -> None:
        """Show a wafer's cells, auto-sizing the grid to the data."""
        self._wafer_id = wafer_id
        self._cells = cells if cells is not None else wafer_map.pd.DataFrame()
        ext = wafer_map.grid_extent(self._cells)
        for spin, key in ((self.die_rows, "die_rows"), (self.die_cols, "die_cols"),
                          (self.tr_rows, "tr_rows"), (self.tr_cols, "tr_cols")):
            spin.spin.blockSignals(True)
            spin.setValue(ext[key])
            spin.spin.blockSignals(False)
        self._current_die = None
        self.detail.clear()
        self._draw_wafer()

    # -- drawing ------------------------------------------------------------
    def _redraw(self) -> None:
        if self._view == "die" and self._current_die is not None:
            self._draw_die(*self._current_die)
        else:
            self._draw_wafer()

    def _draw_wafer(self) -> None:
        self._view = "wafer"
        self.back_btn.setVisible(False)
        rows, cols = self.die_rows.value(), self.die_cols.value()
        summary = wafer_map.die_summary(
            self._cells, self.tr_rows.value(), self.tr_cols.value())
        ylut = {(int(r.die_col), int(r.die_row)): r for r in summary.itertuples()} \
            if not summary.empty else {}

        self.figure.clear()
        ax = self.figure.add_subplot(111)
        from matplotlib import colormaps
        cmap = colormaps["RdYlGn"]
        for c in range(1, cols + 1):
            for r in range(1, rows + 1):
                info = ylut.get((c, r))
                if info is None or info.measured == 0:
                    color, label = _NODATA, f"C{c}R{r}"
                else:
                    color = cmap(min(info.yield_pct / 100.0, 1.0))
                    label = f"C{c}R{r}\n{info.yield_pct:.0f}%"
                ax.add_patch(Rectangle((c - 1, r - 1), 0.96, 0.96,
                                       facecolor=color, edgecolor="#222", lw=1.0))
                ax.text(c - 0.52, r - 0.5, label, ha="center", va="center",
                        fontsize=9, color="#111")
        ax.set_xlim(0, cols); ax.set_ylim(0, rows)
        ax.invert_yaxis(); ax.set_aspect("equal"); ax.axis("off")
        title = f"Wafer {self._wafer_id} — click a die" if self._wafer_id \
            else "No wafer selected"
        ax.set_title(title)
        self.figure.tight_layout()
        self.canvas.draw_idle()

    def _draw_die(self, die_col: int, die_row: int) -> None:
        self._view = "die"
        self.back_btn.setVisible(True)
        rows, cols = self.tr_rows.value(), self.tr_cols.value()
        metric = _METRICS[self.color_combo.currentText()]

        sub = self._cells
        if not sub.empty:
            sub = sub[(sub.die_col == die_col) & (sub.die_row == die_row)]
        vmin = vmax = None
        if metric and not sub.empty and sub[metric].notna().any():
            vmin, vmax = float(sub[metric].min()), float(sub[metric].max())

        self.figure.clear()
        ax = self.figure.add_subplot(111)
        from matplotlib import colormaps
        cmap = colormaps["viridis"]
        for c in range(1, cols + 1):
            for r in range(1, rows + 1):
                cell = wafer_map.cell_at(self._cells, die_col, die_row, c, r)
                if cell is None:
                    color = _NODATA
                elif metric is None:
                    color = _PASS if cell["functional"] else _FAIL
                else:
                    val = cell.get(metric)
                    if val is None or wafer_map.pd.isna(val) or vmax is None or vmax == vmin:
                        color = _NODATA if val is None else cmap(0.5)
                    else:
                        color = cmap((val - vmin) / (vmax - vmin))
                ax.add_patch(Rectangle((c - 1, r - 1), 0.96, 0.96,
                                       facecolor=color, edgecolor="#222", lw=0.8))
        ax.set_xlim(0, cols); ax.set_ylim(0, rows)
        ax.invert_yaxis(); ax.set_aspect("equal"); ax.axis("off")
        title = f"Die C{die_col}R{die_row} — click a transistor"
        if metric:
            title += f"  (colour: {self.color_combo.currentText()})"
        ax.set_title(title)
        self.figure.tight_layout()
        self.canvas.draw_idle()

        summ = wafer_map.die_summary(self._cells, rows, cols)
        info = summ[(summ.die_col == die_col) & (summ.die_row == die_row)] \
            if not summ.empty else summ
        if not info.empty:
            i = info.iloc[0]
            self._set_detail({
                "Die": f"C{die_col}R{die_row}",
                "Measured transistors": int(i.measured),
                "Functional": int(i.functional),
                "Total cells": int(i.total),
                "Die yield": f"{i.yield_pct:.1f}%",
            })
        else:
            self._set_detail({"Die": f"C{die_col}R{die_row}", "Data": "none"})

    # -- interaction --------------------------------------------------------
    def _on_click(self, event) -> None:
        if event.inaxes is None or event.xdata is None or event.ydata is None:
            return
        col = int(np.floor(event.xdata)) + 1
        row = int(np.floor(event.ydata)) + 1
        if self._view == "wafer":
            if 1 <= col <= self.die_cols.value() and 1 <= row <= self.die_rows.value():
                self._current_die = (col, row)
                self._draw_die(col, row)
        else:
            if 1 <= col <= self.tr_cols.value() and 1 <= row <= self.tr_rows.value():
                self._show_transistor(col, row)

    def _show_transistor(self, tr_col: int, tr_row: int) -> None:
        dc, dr = self._current_die
        cell = wafer_map.cell_at(self._cells, dc, dr, tr_col, tr_row)
        if cell is None:
            self._set_detail({
                "Die": f"C{dc}R{dr}", "Transistor": f"c{tr_col}r{tr_row}",
                "Status": "no measurement data",
            })
            return
        self._set_detail({
            "Wafer": self._wafer_id,
            "Die": f"C{dc}R{dr}", "Transistor": f"c{tr_col}r{tr_row}",
            "Material stack": cell.get("material_stack") or "—",
            "Channel L / W (µm)": f"{_g(cell.get('channel_length'))} / {_g(cell.get('channel_width'))}",
            "Sweeps": cell["sweep_types"] or "—",
            "Functional": "PASS" if cell["functional"] else "FAIL",
            "— features —": "",
            "Vth (V)": _g(cell["vth"], 3),
            "μ_sat (cm²/Vs)": _g(cell["mu_sat"], 2),
            "On/Off ratio": _g(cell["on_off_ratio"], 1, sci=True),
            "SS (mV/dec)": _g(cell["ss_min"], 1),
        })

    def _show_wafer(self) -> None:
        self._current_die = None
        self.detail.clear()
        self._draw_wafer()

    # -- helpers ------------------------------------------------------------
    def _set_detail(self, mapping: dict) -> None:
        rows = "".join(
            f"<tr><td style='color:#9aa0aa;padding-right:12px'>{k}</td>"
            f"<td><b>{'' if v is None else v}</b></td></tr>"
            for k, v in mapping.items()
        )
        self.detail.setHtml(f"<table cellspacing='5'>{rows}</table>")


def _g(value, ndigits=2, sci=False) -> str:
    """Format an optional numeric value for the detail panel."""
    if value is None or wafer_map.pd.isna(value):
        return "—"
    try:
        return f"{value:.{ndigits}e}" if sci else f"{value:.{ndigits}f}"
    except (TypeError, ValueError):
        return str(value)
