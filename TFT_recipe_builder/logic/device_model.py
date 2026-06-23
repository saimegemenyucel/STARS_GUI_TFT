"""Data model for a 2D TFT cross-section (top-gate staggered structure).

Defaults follow the IGZO TFT in Panca et al. ("IGZO Thin-Film Transistor
Optimization for Memristive Applications"): a top-gate staggered stack of
Si/SiO2 substrate -> Ti/Pt source-drain -> IGZO channel -> Al2O3 gate oxide ->
Ti/Pt gate.
"""

from __future__ import annotations

import colorsys
import hashlib
from dataclasses import dataclass, field

# Known materials -> fill colour. Editable combos may add custom materials,
# which get a stable auto-generated colour via :func:`color_for`.
MATERIAL_COLORS: dict[str, str] = {
    "Si": "#7a5b43",
    "SiO2": "#c9b8e8",
    "Si / SiO2": "#6d5742",
    "Glass": "#d8e6e6",
    "Ti": "#c4ccd4",
    "Pt": "#e6c46a",
    "Au": "#f1cf52",
    "Mo": "#7090b0",
    "W": "#8a6f63",
    "Al": "#b9c2cc",
    "IGZO": "#3fb6a8",
    "Al2O3": "#8fb8e0",
    "AlOx": "#8fb8e0",
    "HfO2": "#a0d0c0",
    "SiNx": "#bfa0d0",
    "TiOx": "#c98f6a",
}


def color_for(material: str) -> str:
    """Return a fill colour for a material name.

    Known materials use the curated palette; unknown (custom) names get a
    stable pastel colour derived from a hash so the same name always looks the
    same.

    Args:
        material: Material name (case-insensitive match against the palette).

    Returns:
        A hex colour string.
    """
    if not material:
        return "#cccccc"
    for key, value in MATERIAL_COLORS.items():
        if key.lower() == material.lower():
            return value
    digest = hashlib.md5(material.encode("utf-8")).hexdigest()
    hue = int(digest[:2], 16) / 255.0
    r, g, b = colorsys.hls_to_rgb(hue, 0.65, 0.45)
    return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"


@dataclass
class Layer:
    """One material layer in the stack."""

    role: str            # logical role, e.g. "channel", "gate_oxide"
    label: str           # display label, e.g. "Gate Oxide"
    material: str        # material name (selectable)
    thickness_nm: float  # vertical thickness in nm

    @property
    def color(self) -> str:
        """Fill colour for this layer's material."""
        return color_for(self.material)


@dataclass
class DeviceStructure:
    """A full top-gate staggered TFT cross-section definition.

    Layers are stored individually so each material/thickness can be edited
    independently. Lateral geometry is captured by the channel length/width and
    a few schematic layout dimensions.
    """

    substrate: Layer
    sd_adhesion: Layer       # source/drain adhesion (Ti)
    sd_electrode: Layer      # source/drain electrode (Pt)
    channel: Layer           # semiconductor (IGZO)
    gate_oxide: Layer        # dielectric (Al2O3 / AlOx)
    gate_adhesion: Layer     # gate adhesion (Ti)
    gate_electrode: Layer    # gate electrode (Pt)

    channel_length_nm: float = 3000.0   # L (gap between source and drain)
    channel_width_nm: float = 10000.0   # W (out of plane)
    sd_pad_length_nm: float = 2000.0    # lateral extent of each S/D pad
    channel_overlap_nm: float = 600.0   # channel overlap onto each S/D pad
    gate_overlap_nm: float = 400.0      # gate extension beyond the channel gap

    def electrode_layers(self) -> list[Layer]:
        """S/D sub-layers, bottom to top."""
        return [self.sd_adhesion, self.sd_electrode]

    def gate_layers(self) -> list[Layer]:
        """Gate sub-layers, bottom to top."""
        return [self.gate_adhesion, self.gate_electrode]

    def all_layers(self) -> list[Layer]:
        """Every editable layer, bottom to top."""
        return [
            self.substrate, self.sd_adhesion, self.sd_electrode,
            self.channel, self.gate_oxide, self.gate_adhesion, self.gate_electrode,
        ]


def default_igzo_device() -> DeviceStructure:
    """Return the paper's IGZO TFT with its reported materials and thicknesses."""
    return DeviceStructure(
        substrate=Layer("substrate", "Substrate", "Si / SiO2", 200.0),
        sd_adhesion=Layer("sd_adhesion", "S/D Adhesion", "Ti", 5.0),
        sd_electrode=Layer("sd_electrode", "Source / Drain", "Pt", 20.0),
        channel=Layer("channel", "Channel", "IGZO", 30.0),
        gate_oxide=Layer("gate_oxide", "Gate Oxide", "AlOx", 25.0),
        gate_adhesion=Layer("gate_adhesion", "Gate Adhesion", "Ti", 5.0),
        gate_electrode=Layer("gate_electrode", "Gate", "Pt", 45.0),
        channel_length_nm=3000.0,
        channel_width_nm=10000.0,
    )
