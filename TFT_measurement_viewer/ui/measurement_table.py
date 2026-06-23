"""Measurement table widget with sorting and pass/fail row colouring."""

from __future__ import annotations

import pandas as pd
from PyQt6.QtCore import QSortFilterProxyModel, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QTableView

from TFT_measurement_viewer.bootstrap import config
from shared.qt_models import DataFrameModel


class _ColourModel(DataFrameModel):
    """DataFrameModel that tints rows green/red by the ``is_functional`` column."""

    def data(self, index, role: int = Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.BackgroundRole and "is_functional" in self.dataframe.columns:
            functional = self.dataframe.iloc[index.row()].get("is_functional")
            if functional is True or functional == 1:
                return QColor(config.PASS_COLOR).darker(260)
            if functional is False or functional == 0:
                return QColor(config.FAIL_COLOR).darker(260)
        return super().data(index, role)


class MeasurementTable(QTableView):
    """A sortable table view over a measurement DataFrame."""

    # Columns kept in the DataFrame (e.g. for the spatial map) but hidden here.
    HIDDEN_COLUMNS = {"position_x", "position_y"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model = _ColourModel()
        self._proxy = QSortFilterProxyModel(self)
        self._proxy.setSourceModel(self._model)
        self.setModel(self._proxy)

        self.setSortingEnabled(True)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.horizontalHeader().setStretchLastSection(True)
        self.verticalHeader().setVisible(False)

    def set_data(self, df: pd.DataFrame) -> None:
        """Display a new measurement DataFrame (hiding HIDDEN_COLUMNS)."""
        self._model.set_dataframe(df)
        for i, name in enumerate(df.columns):
            self.setColumnHidden(i, name in self.HIDDEN_COLUMNS)
        self.resizeColumnsToContents()

    def current_dataframe(self) -> pd.DataFrame:
        """Return the DataFrame currently displayed (unsorted source order)."""
        return self._model.dataframe
