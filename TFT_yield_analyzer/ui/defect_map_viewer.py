"""Spatial defect map: device positions coloured pass/fail with hotspots."""

from __future__ import annotations

import logging

import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from TFT_yield_analyzer.bootstrap import config
from TFT_yield_analyzer.logic.clustering import Hotspot

logger = logging.getLogger(__name__)


class DefectMapViewer(QWidget):
    """Scatter of device positions, red = failed, green = pass, with hotspots."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.figure = Figure(figsize=(5, 4), tight_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        layout = QVBoxLayout(self)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas, stretch=1)

    def update_map(self, df: pd.DataFrame, hotspots: list[Hotspot]) -> None:
        """Redraw the defect map for a wafer.

        Args:
            df: Measurement DataFrame with positions and ``is_functional``.
            hotspots: Hotspot cells to outline.
        """
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        data = df.copy()
        for col in ("position_x", "position_y"):
            data[col] = pd.to_numeric(data.get(col), errors="coerce")
        data = data.dropna(subset=["position_x", "position_y"])
        if data.empty:
            ax.text(0.5, 0.5, "No spatial data", ha="center", va="center",
                    transform=ax.transAxes)
            ax.set_xticks([]); ax.set_yticks([])
            self.canvas.draw_idle()
            return

        passed = data["is_functional"] == True  # noqa: E712
        ax.scatter(data[passed]["position_x"], data[passed]["position_y"],
                   s=45, color=config.PASS_COLOR, label="Functional",
                   edgecolors="black", linewidths=0.3)
        ax.scatter(data[~passed]["position_x"], data[~passed]["position_y"],
                   s=45, color=config.FAIL_COLOR, label="Failed", marker="X",
                   edgecolors="black", linewidths=0.3)
        for hs in hotspots:
            ax.scatter(hs.x_center, hs.y_center, s=400, facecolors="none",
                       edgecolors="yellow", linewidths=2.0)
        ax.set_xlabel("Position X (mm)")
        ax.set_ylabel("Position Y (mm)")
        ax.set_title("Defect Map (yellow rings = failure hotspots)")
        ax.set_aspect("equal", adjustable="datalim")
        ax.legend(loc="upper right")
        self.canvas.draw_idle()
