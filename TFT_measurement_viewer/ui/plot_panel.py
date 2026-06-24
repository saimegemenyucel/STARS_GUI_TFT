"""Embedded matplotlib panel offering spatial / histogram / correlation views."""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from TFT_measurement_viewer.bootstrap import config
from TFT_measurement_viewer.logic import plot_helpers
from shared.parameters import PARAMETERS

logger = logging.getLogger(__name__)


class PlotPanel(QWidget):
    """A figure canvas with selectors for plot mode and parameters."""

    # Emitted with a device_id when the user clicks a point/bar identifying one.
    deviceActivated = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._df: pd.DataFrame = pd.DataFrame()

        self.figure = Figure(figsize=(5, 4), tight_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)

        # Hover-to-identify state (which transistor is under the cursor).
        self._annot = None
        self._hover_pts: list = []
        self._hover_kind = None
        self.canvas.mpl_connect("motion_notify_event", self._on_hover)
        self.canvas.mpl_connect("button_press_event", self._on_click)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(config.PLOT_MODES)
        self.param_combo = QComboBox()
        self.param2_combo = QComboBox()
        for info in PARAMETERS:
            self.param_combo.addItem(info.label, info.key)
            self.param2_combo.addItem(info.label, info.key)
        self.param2_combo.setCurrentIndex(1)
        self.param2_label = QLabel("vs")

        self._build_layout()
        self._connect()
        self._update_param_visibility()

    # -- layout -------------------------------------------------------------
    def _build_layout(self) -> None:
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Plot:"))
        controls.addWidget(self.mode_combo)
        controls.addWidget(QLabel("Parameter:"))
        controls.addWidget(self.param_combo)
        controls.addWidget(self.param2_label)
        controls.addWidget(self.param2_combo)
        controls.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addLayout(controls)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas, stretch=1)

    def _connect(self) -> None:
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self.param_combo.currentIndexChanged.connect(self.redraw)
        self.param2_combo.currentIndexChanged.connect(self.redraw)

    # -- behaviour ----------------------------------------------------------
    def _on_mode_changed(self) -> None:
        self._update_param_visibility()
        self.redraw()

    def _update_param_visibility(self) -> None:
        is_corr = self.mode_combo.currentText() == "Parameter Correlation"
        self.param2_label.setVisible(is_corr)
        self.param2_combo.setVisible(is_corr)

    def set_data(self, df: pd.DataFrame) -> None:
        """Provide a new measurement DataFrame and redraw."""
        self._df = df
        self.redraw()

    def redraw(self) -> None:
        """Render the currently selected plot."""
        self._annot = None
        self._hover_pts = []
        self._hover_kind = None
        if self._df.empty:
            self.figure.clear()
            ax = self.figure.add_subplot(111)
            ax.text(0.5, 0.5, "Select a wafer", ha="center", va="center",
                    transform=ax.transAxes)
            ax.set_xticks([])
            ax.set_yticks([])
            self.canvas.draw_idle()
            return

        mode = self.mode_combo.currentText()
        param = self.param_combo.currentData()
        try:
            if mode == "Spatial Map":
                plot_helpers.draw_spatial_map(self.figure, self._df, param)
            elif mode == "Histogram":
                plot_helpers.draw_histogram(self.figure, self._df, param)
            else:  # Parameter Correlation
                plot_helpers.draw_correlation(
                    self.figure, self._df, param, self.param2_combo.currentData()
                )
        except Exception:  # pragma: no cover - defensive UI guard
            logger.exception("Failed to render plot")
        self._prepare_hover()
        self.canvas.draw_idle()

    # -- hover: identify the transistor under the cursor --------------------
    def _prepare_hover(self) -> None:
        """Collect (x, y, device_id) points for the current plot for hovering."""
        df = self._df
        if df is None or df.empty or "device_id" not in df.columns:
            return
        if not self.figure.axes:
            return
        ax = self.figure.axes[0]
        mode = self.mode_combo.currentText()
        try:
            if mode == "Spatial Map":
                param = self.param_combo.currentData()
                cols = ["position_x", "position_y", param]
                if not all(c in df.columns for c in cols):
                    return
                d = df.dropna(subset=cols)
                self._hover_pts = list(zip(d["position_x"].astype(float),
                                           d["position_y"].astype(float),
                                           d["device_id"].astype(str)))
                self._hover_kind = "scatter"
            elif mode == "Parameter Correlation":
                x = self.param_combo.currentData()
                y = self.param2_combo.currentData()
                if x not in df.columns or y not in df.columns:
                    return
                d = df.dropna(subset=[x, y])
                self._hover_pts = list(zip(d[x].astype(float), d[y].astype(float),
                                           d["device_id"].astype(str)))
                self._hover_kind = "scatter"
            else:  # Histogram (match on the parameter value)
                param = self.param_combo.currentData()
                if param not in df.columns:
                    return
                d = df.dropna(subset=[param])
                self._hover_pts = list(zip(d[param].astype(float),
                                           [0.0] * len(d),
                                           d["device_id"].astype(str)))
                self._hover_kind = "hist"
        except Exception:  # pragma: no cover - defensive
            self._hover_pts = []
            self._hover_kind = None
            return
        if self._hover_pts:
            self._annot = ax.annotate(
                "", xy=(0, 0), xytext=(12, 12), textcoords="offset points",
                bbox=dict(boxstyle="round", fc="#2b2d36", ec="#3d8bfd"),
                color="#e6e6e6", fontsize=8, zorder=20, visible=False)

    def _hit_test(self, event) -> tuple[Optional[int], Optional[tuple[float, float]]]:
        """Return (index into self._hover_pts, xy) of the point under the
        cursor, or (None, None) if nothing is close enough."""
        if not self.figure.axes or not self._hover_pts:
            return None, None
        ax = self.figure.axes[0]
        if event.inaxes is not ax:
            return None, None
        xs = np.array([p[0] for p in self._hover_pts])
        ys = np.array([p[1] for p in self._hover_pts])
        if self._hover_kind == "scatter":
            disp = ax.transData.transform(np.column_stack([xs, ys]))
            d2 = (disp[:, 0] - event.x) ** 2 + (disp[:, 1] - event.y) ** 2
            i = int(np.argmin(d2))
            if d2[i] > 14 ** 2:
                return None, None
            return i, (xs[i], ys[i])
        else:  # histogram: nearest parameter value to the cursor x
            if event.xdata is None:
                return None, None
            xlim = ax.get_xlim()
            tol = abs(xlim[1] - xlim[0]) / 40.0
            i = int(np.argmin(np.abs(xs - event.xdata)))
            if abs(xs[i] - event.xdata) > tol:
                return None, None
            return i, (event.xdata, event.ydata if event.ydata is not None else 0.0)

    def _on_hover(self, event) -> None:
        """Show the device id of the nearest point under the cursor."""
        annot = self._annot
        if annot is None:
            return
        try:
            i, xy = self._hit_test(event)
            if i is None:
                if annot.get_visible():
                    annot.set_visible(False)
                    self.canvas.draw_idle()
                return
            annot.xy = xy
            annot.set_text(self._hover_pts[i][2])
            annot.set_visible(True)
            self.canvas.draw_idle()
        except Exception:  # pragma: no cover - never let hover crash the UI
            pass

    def _on_click(self, event) -> None:
        """Emit deviceActivated for the point the user clicked on, if any."""
        try:
            i, _xy = self._hit_test(event)
            if i is not None:
                self.deviceActivated.emit(self._hover_pts[i][2])
        except Exception:  # pragma: no cover - never let a click crash the UI
            pass
