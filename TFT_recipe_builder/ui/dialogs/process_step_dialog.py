"""Dialog to add or edit a single process step."""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
)

from TFT_recipe_builder.logic.enums import ProcessType
from TFT_recipe_builder.logic.models import ProcessStep
from TFT_recipe_builder.logic.validation import validate_step

logger = logging.getLogger(__name__)

# Sentinel meaning "not specified" for optional numeric fields.
_UNSET = -1.0


def parse_gas_mixture(text: str) -> dict[str, float]:
    """Parse a ``"SiH4:50, N2O:200"`` string into ``{name: fraction}``.

    Pairs without a numeric value are skipped. Raises nothing; malformed
    fractions default to 0.
    """
    result: dict[str, float] = {}
    for chunk in text.replace(";", ",").split(","):
        chunk = chunk.strip()
        if not chunk or ":" not in chunk:
            continue
        name, _, value = chunk.partition(":")
        name = name.strip()
        if not name:
            continue
        try:
            result[name] = float(value.strip())
        except ValueError:
            result[name] = 0.0
    return result


def format_gas_mixture(gas: dict[str, float]) -> str:
    """Render a gas dict back to ``"A:50, B:200"`` form for editing."""
    return ", ".join(f"{k}:{v:g}" for k, v in gas.items())


class ProcessStepDialog(QDialog):
    """Modal editor for a :class:`ProcessStep`."""

    def __init__(self, parent=None, step: Optional[ProcessStep] = None):
        super().__init__(parent)
        self.setWindowTitle("Process Step")
        self._editing = step is not None

        self.type_combo = QComboBox()
        self.type_combo.addItems(ProcessType.values())
        self.name_edit = QLineEdit()
        self.temp_spin = self._optional_spin(-50, 1500, " °C")
        self.duration_spin = self._optional_spin(0, 100000, " min")
        self.pressure_spin = self._optional_spin(0, 1_000_000, " mTorr")
        self.power_spin = self._optional_spin(0, 100000, " W")
        self.gas_edit = QLineEdit()
        self.gas_edit.setPlaceholderText("e.g. SiH4:50, N2O:200")
        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setFixedHeight(60)

        form = QFormLayout(self)
        form.addRow("Process type:", self.type_combo)
        form.addRow("Process name:", self.name_edit)
        form.addRow("Temperature:", self.temp_spin)
        form.addRow("Duration:", self.duration_spin)
        form.addRow("Pressure:", self.pressure_spin)
        form.addRow("RF Power:", self.power_spin)
        form.addRow("Gas mixture:", self.gas_edit)
        form.addRow("Notes:", self.notes_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

        if step is not None:
            self._load(step)

    def _optional_spin(self, lo: float, hi: float, suffix: str) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(_UNSET, hi)
        spin.setMinimum(_UNSET)
        spin.setDecimals(3)
        spin.setSuffix(suffix)
        spin.setSpecialValueText("(unset)")  # shown when value == minimum
        spin.setValue(_UNSET)
        return spin

    def _load(self, step: ProcessStep) -> None:
        self.type_combo.setCurrentText(step.process_type)
        self.name_edit.setText(step.process_name)
        self.temp_spin.setValue(step.temperature if step.temperature is not None else _UNSET)
        self.duration_spin.setValue(step.duration if step.duration is not None else _UNSET)
        self.pressure_spin.setValue(step.pressure if step.pressure is not None else _UNSET)
        self.power_spin.setValue(step.power if step.power is not None else _UNSET)
        self.gas_edit.setText(format_gas_mixture(step.gas_mixture))
        self.notes_edit.setPlainText(step.notes)

    @staticmethod
    def _value(spin: QDoubleSpinBox) -> Optional[float]:
        return None if spin.value() <= _UNSET else float(spin.value())

    def build_step(self, step_order: int) -> ProcessStep:
        """Construct a :class:`ProcessStep` from the current field values."""
        return ProcessStep(
            step_order=step_order,
            process_type=self.type_combo.currentText(),
            process_name=self.name_edit.text().strip(),
            temperature=self._value(self.temp_spin),
            duration=self._value(self.duration_spin),
            pressure=self._value(self.pressure_spin),
            power=self._value(self.power_spin),
            gas_mixture=parse_gas_mixture(self.gas_edit.text()),
            notes=self.notes_edit.toPlainText().strip(),
        )

    def _on_accept(self) -> None:
        errors = validate_step(self.build_step(1))
        if errors:
            QMessageBox.warning(self, "Invalid step", "\n".join(errors))
            return
        self.accept()
