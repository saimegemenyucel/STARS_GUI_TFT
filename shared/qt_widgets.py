"""Reusable Qt widgets shared across modules."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)


class PlusMinusSpin(QWidget):
    """A spinbox flanked by large, clearly labelled '−' and '+' buttons.

    Wraps any QAbstractSpinBox (QSpinBox / QDoubleSpinBox); the spinbox's own
    tiny up/down arrows are hidden in favour of the big side buttons. Connect to
    ``widget.spin.valueChanged`` and read ``widget.value()`` as usual.
    """

    def __init__(self, spin: QAbstractSpinBox, button_width: int = 38,
                 up_down: bool = False, flat: bool = False, label: str = "",
                 parent=None):
        super().__init__(parent)
        self.spin = spin
        spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)

        # up_down -> ▼ / ▲ glyphs; otherwise − / + . flat -> transparent button.
        minus_text, plus_text = ("▼", "▲") if up_down else ("−", "+")
        self.minus = QPushButton(minus_text)
        self.plus = QPushButton(plus_text)
        style = "font-size: 18px; font-weight: bold;"
        if flat:
            style += " background: transparent; border: none; color: #e8e8e8;"
        for b in (self.minus, self.plus):
            b.setFixedWidth(button_width)
            b.setMinimumHeight(30)
            b.setStyleSheet(style)
            if flat:
                b.setFlat(True)
        self.minus.clicked.connect(spin.stepDown)
        self.plus.clicked.connect(spin.stepUp)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        if label:
            lab = QLabel(label)
            lab.setMinimumWidth(64)
            layout.addWidget(lab)
        layout.addWidget(self.minus)
        layout.addWidget(self.spin, stretch=1)
        layout.addWidget(self.plus)

    def value(self):
        """Current spinbox value."""
        return self.spin.value()

    def setValue(self, v) -> None:  # noqa: N802 (Qt naming)
        """Set the spinbox value."""
        self.spin.setValue(v)
