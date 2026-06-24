"""Measurement table widget with sorting and pass/fail row colouring."""

from __future__ import annotations

from typing import Optional

import pandas as pd
from PyQt6.QtCore import QModelIndex, QSortFilterProxyModel, Qt
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

    def device_id_at(self, proxy_index: QModelIndex) -> Optional[str]:
        """Return the ``device_id`` for a (possibly sorted) view row, or None."""
        if not proxy_index.isValid():
            return None
        source_row = self._proxy.mapToSource(proxy_index).row()
        df = self._model.dataframe
        if "device_id" not in df.columns or not (0 <= source_row < len(df)):
            return None
        return str(df.iloc[source_row]["device_id"])

    def current_device_id(self) -> Optional[str]:
        """Return the ``device_id`` of the currently selected row, or None."""
        return self.device_id_at(self.currentIndex())
