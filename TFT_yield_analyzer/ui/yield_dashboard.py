"""KPI dashboard: headline yield numbers, parameter pass chart and stats table."""

from __future__ import annotations

import logging

import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from TFT_yield_analyzer.bootstrap import config
from TFT_yield_analyzer.logic.statistics import parameter_statistics
from TFT_yield_analyzer.logic.yield_calculator import YieldMetrics
from shared.qt_models import DataFrameModel

logger = logging.getLogger(__name__)


class _KpiCard(QGroupBox):
    """A small titled card showing one big value."""

    def __init__(self, title: str):
        super().__init__(title)
        self.value_label = QLabel("—")
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.value_label.setStyleSheet("font-size: 22px; font-weight: bold;")
        layout = QVBoxLayout(self)
        layout.addWidget(self.value_label)

    def set_value(self, text: str) -> None:
        self.value_label.setText(text)


class YieldDashboard(QWidget):
    """Composite dashboard widget driven by a :class:`YieldMetrics`."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.kpi_yield = _KpiCard("Overall Yield")
        self.kpi_devices = _KpiCard("Functional / Total")
        self.kpi_density = _KpiCard("Defect Density (/cm²)")
        self.kpi_defect = _KpiCard("Dominant Defect")

        kpi_row = QHBoxLayout()
        for card in (self.kpi_yield, self.kpi_devices, self.kpi_density, self.kpi_defect):
            kpi_row.addWidget(card)

        # Parameter pass/fail bar chart.
        self.figure = Figure(figsize=(5, 2.6), tight_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        chart_box = QGroupBox("Parameter pass counts")
        chart_layout = QVBoxLayout(chart_box)
        chart_layout.addWidget(self.canvas)

        # Statistics table.
        self.stats_model = DataFrameModel()
        self.stats_table = QTableView()
        self.stats_table.setModel(self.stats_model)
        stats_box = QGroupBox("Parameter statistics")
        stats_layout = QVBoxLayout(stats_box)
        stats_layout.addWidget(self.stats_table)

        body = QGridLayout()
        body.addWidget(chart_box, 0, 0)
        body.addWidget(stats_box, 0, 1)

        layout = QVBoxLayout(self)
        layout.addLayout(kpi_row)
        layout.addLayout(body, stretch=1)

    def update_dashboard(self, metrics: YieldMetrics, df: pd.DataFrame) -> None:
        """Refresh all KPI cards, the bar chart and the statistics table."""
        self.kpi_yield.set_value(f"{metrics.overall_yield_percentage:.1f}%")
        self.kpi_devices.set_value(
            f"{metrics.functional_devices} / {metrics.total_devices}"
        )
        self.kpi_density.set_value(f"{metrics.defect_density_per_cm2:.3g}")
        self.kpi_defect.set_value(metrics.dominant_defect_type or "—")

        self._draw_param_chart(metrics)
        stats = parameter_statistics(df).reset_index()
        self.stats_model.set_dataframe(stats)
        self.stats_table.resizeColumnsToContents()

    def _draw_param_chart(self, metrics: YieldMetrics) -> None:
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        labels = ["Vth", "Mobility", "On/Off", "SS", "Leakage"]
        passes = [
            metrics.vth_pass_count, metrics.mobility_pass_count,
            metrics.on_off_ratio_pass_count, metrics.ss_pass_count,
            metrics.leakage_pass_count,
        ]
        fails = [metrics.total_devices - p for p in passes]
        ax.bar(labels, passes, color=config.PASS_COLOR, label="Pass")
        ax.bar(labels, fails, bottom=passes, color=config.FAIL_COLOR, label="Fail")
        ax.set_ylabel("Devices")
        ax.legend(fontsize=8)
        self.canvas.draw_idle()
