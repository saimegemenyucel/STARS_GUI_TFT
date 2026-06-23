"""Reusable Qt model classes shared across modules.

Only imported by UI code, so PyQt6 is a dependency of this module but not of
the rest of the ``shared`` package.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd
from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt


class DataFrameModel(QAbstractTableModel):
    """A read-only Qt table model backed by a pandas DataFrame.

    Numeric floats are formatted to a fixed precision for display; the
    underlying values are kept intact for sorting and export.
    """

    def __init__(self, df: Optional[pd.DataFrame] = None, float_format: str = "{:.3g}"):
        super().__init__()
        self._df = df if df is not None else pd.DataFrame()
        self._float_format = float_format

    # -- Qt model interface -------------------------------------------------
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._df)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._df.columns)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            value = self._df.iat[index.row(), index.column()]
            return self._format(value)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            value = self._df.iat[index.row(), index.column()]
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None

    def headerData(  # noqa: N802
        self, section: int, orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return str(self._df.columns[section])
        return str(self._df.index[section])

    # -- helpers ------------------------------------------------------------
    def _format(self, value) -> str:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return ""
        if pd.isna(value):
            return ""
        if isinstance(value, bool):
            return "Pass" if value else "Fail"
        if isinstance(value, float):
            return self._float_format.format(value)
        return str(value)

    def set_dataframe(self, df: pd.DataFrame) -> None:
        """Replace the underlying frame and refresh all views."""
        self.beginResetModel()
        self._df = df.reset_index(drop=True)
        self.endResetModel()

    @property
    def dataframe(self) -> pd.DataFrame:
        """The current underlying DataFrame."""
        return self._df
