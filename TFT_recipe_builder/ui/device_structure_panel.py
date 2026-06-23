"""Interactive 2D TFT cross-section panel.

Left: editable material / thickness controls and lateral dimensions.
Right: a live matplotlib cross-section that redraws on every change.

Redraws are debounced through a short single-shot timer so that holding a
spinbox arrow or typing in a material box stays smooth (one redraw after the
last change, instead of one per event).
"""

from __future__ import annotations

import logging

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from TFT_recipe_builder.logic.device_model import (
    MATERIAL_COLORS,
    DeviceStructure,
    Layer,
    default_igzo_device,
)
from TFT_recipe_builder.logic.device_render import draw_device
from shared.qt_widgets import PlusMinusSpin

logger = logging.getLogger(__name__)

_MATERIALS = sorted(MATERIAL_COLORS.keys())

# (attribute, display label) for each editable layer, bottom to top.
_LAYER_FIELDS = [
    ("substrate", "Substrate"),
    ("sd_adhesion", "S/D Adhesion"),
    ("sd_electrode", "Source / Drain"),
    ("channel", "Channel"),
    ("gate_oxide", "Gate Oxide"),
    ("gate_adhesion", "Gate Adhesion"),
    ("gate_electrode", "Gate"),
]

# (attribute, label, max, step) for the geometry spinboxes.
# Geometry is edited in micrometres; stored on the model in nanometres.
_UM = 1000.0  # nm per µm
_GEOM_FIELDS = [
    ("channel_length_nm", "Channel length L (µm)", 1000.0, 0.5),
    ("channel_width_nm", "Channel width W (µm)", 10000.0, 0.5),
    ("sd_pad_length_nm", "S/D pad length (µm)", 1000.0, 0.5),
    ("channel_overlap_nm", "Channel overlap (µm)", 100.0, 0.1),
    ("gate_overlap_nm", "Gate overlap (µm)", 100.0, 0.1),
]


class DeviceStructurePanel(QWidget):
    """A self-contained widget for editing and viewing the TFT cross-section."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._device: DeviceStructure = default_igzo_device()
        # Suppress widget signals while the UI is being built / programmatically
        # loaded, so we don't redraw against a half-initialised state.
        self._updating = True

        self._material_combos: dict[str, QComboBox] = {}
        self._thickness_spins: dict[str, QDoubleSpinBox] = {}
        self._geom_spins: dict[str, QDoubleSpinBox] = {}

        self.figure = Figure(figsize=(7, 5))
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)

        # Debounced redraw timer (coalesces rapid edits into one redraw).
        self._redraw_timer = QTimer(self)
        self._redraw_timer.setSingleShot(True)
        self._redraw_timer.setInterval(40)
        self._redraw_timer.timeout.connect(self._apply_and_redraw)

        self._build_ui()
        self._load_from_device(self._device)

        self._updating = False
        self._apply_and_redraw()  # initial draw

    # -- construction -------------------------------------------------------
    def _build_ui(self) -> None:
        layer_box = QGroupBox("Layers (material & thickness)")
        layer_form = QFormLayout(layer_box)
        for attr, label in _LAYER_FIELDS:
            combo = QComboBox()
            combo.setEditable(True)
            combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
            combo.addItems(_MATERIALS)
            combo.currentTextChanged.connect(self._on_change)

            spin = QDoubleSpinBox()
            spin.setRange(0.1, 100000.0)
            spin.setDecimals(1)
            spin.setSingleStep(1.0)
            spin.setSuffix(" nm")
            spin.setKeyboardTracking(False)  # emit once on commit, not per digit
            spin.setMinimumHeight(30)
            spin.valueChanged.connect(self._on_change)

            self._material_combos[attr] = combo
            self._thickness_spins[attr] = spin

            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.addWidget(combo, stretch=2)
            rl.addWidget(spin, stretch=1)
            layer_form.addRow(label + ":", row)

        geom_box = QGroupBox("Geometry")
        geom_form = QFormLayout(geom_box)
        for attr, label, maximum, step in _GEOM_FIELDS:
            spin = QDoubleSpinBox()
            spin.setRange(0.01, maximum)
            spin.setDecimals(2)
            spin.setSingleStep(step)
            spin.setKeyboardTracking(False)
            spin.setMinimumHeight(30)
            spin.setMaximumWidth(90)
            spin.valueChanged.connect(self._on_change)
            self._geom_spins[attr] = spin
            geom_form.addRow(label + ":", PlusMinusSpin(spin))

        defaults_btn = QPushButton("Load IGZO Defaults")
        defaults_btn.clicked.connect(self.load_defaults)
        export_btn = QPushButton("Export PNG…")
        export_btn.clicked.connect(self.export_png)
        for btn in (defaults_btn, export_btn):
            btn.setMinimumHeight(44)
            btn.setStyleSheet("font-size: 14px; font-weight: 600; padding: 8px 14px;")
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addWidget(defaults_btn)
        btn_row.addWidget(export_btn)

        controls = QWidget()
        cl = QVBoxLayout(controls)
        cl.addWidget(QLabel("<b>TFT device structure</b>"))
        cl.addWidget(layer_box)
        cl.addWidget(geom_box)
        cl.addLayout(btn_row)
        cl.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(controls)
        scroll.setMinimumWidth(320)
        scroll.setMaximumWidth(420)

        plot_side = QWidget()
        pl = QVBoxLayout(plot_side)
        pl.addWidget(self.toolbar)
        pl.addWidget(self.canvas, stretch=1)

        layout = QHBoxLayout(self)
        layout.addWidget(scroll)
        layout.addWidget(plot_side, stretch=1)

    # -- state <-> widgets --------------------------------------------------
    def _load_from_device(self, device: DeviceStructure) -> None:
        """Populate all widgets from a device (without triggering redraws)."""
        was_updating = self._updating
        self._updating = True
        try:
            for attr, _label in _LAYER_FIELDS:
                layer: Layer = getattr(device, attr)
                self._material_combos[attr].setCurrentText(layer.material)
                self._thickness_spins[attr].setValue(layer.thickness_nm)
            for attr, _label, _max, _step in _GEOM_FIELDS:
                self._geom_spins[attr].setValue(getattr(device, attr) / _UM)
        finally:
            self._updating = was_updating

    def _build_device_from_widgets(self) -> DeviceStructure:
        """Update the device to reflect the current widget values."""
        device = self._device
        for attr, _label in _LAYER_FIELDS:
            layer: Layer = getattr(device, attr)
            text = self._material_combos[attr].currentText().strip()
            if text:
                layer.material = text
            layer.thickness_nm = self._thickness_spins[attr].value()
        for attr, _label, _max, _step in _GEOM_FIELDS:
            setattr(device, attr, self._geom_spins[attr].value() * _UM)
        return device

    # -- events -------------------------------------------------------------
    def _on_change(self, *_args) -> None:
        """Schedule a debounced redraw (ignored while loading programmatically)."""
        if self._updating:
            return
        self._redraw_timer.start()

    def _apply_and_redraw(self) -> None:
        """Rebuild the device from widgets and redraw the canvas."""
        self._build_device_from_widgets()
        try:
            draw_device(self.figure, self._device)
        except Exception:  # pragma: no cover - defensive UI guard
            logger.exception("Failed to render device cross-section")
        self.canvas.draw_idle()

    # -- actions ------------------------------------------------------------
    def load_defaults(self) -> None:
        """Reset to the paper's IGZO TFT values and redraw immediately."""
        self._device = default_igzo_device()
        self._load_from_device(self._device)
        self._apply_and_redraw()

    def export_png(self) -> None:
        """Save the current cross-section as a PNG image."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Export cross-section", "tft_cross_section.png",
            "PNG image (*.png)"
        )
        if not path:
            return
        try:
            self.figure.savefig(path, dpi=200, bbox_inches="tight")
        except OSError as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
