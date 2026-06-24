"""Data model for a 2D TFT cross-section, in any of the four standard
gate/contact topologies.

Defaults follow the IGZO TFT in Panca et al. ("IGZO Thin-Film Transistor
Optimization for Memristive Applications"): a staggered top-gate stack of
Si/SiO2 substrate -> Ti/Pt source-drain -> IGZO channel -> Al2O3 gate oxide ->
Ti/Pt gate.
"""

from __future__ import annotations

import colorsys
import hashlib
from dataclasses import dataclass

# Known materials, offered in the editable combo boxes. Layer *color* in the
# cross-section is keyed by role (see ROLE_COLORS below), not by material, so
# picking a different material never changes which color a given layer draws
# in -- only color_for() (kept for any other material-keyed use) varies by name.
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

# Fixed fill colour per structural role -- stays the same regardless of which
# material is typed into that layer's combo box, so the cross-section's
# colour coding always means "this is the gate" / "this is the channel" etc.
ROLE_COLORS: dict[str, str] = {
    "substrate": "#6d5742",
    "sd_adhesion": "#c4ccd4",
    "sd_electrode": "#e6c46a",
    "channel": "#3fb6a8",
    "gate_oxide": "#8fb8e0",
    "gate_adhesion": "#c4ccd4",
    "gate_electrode": "#e6c46a",
}

# The four standard TFT cross-section topologies (gate position x contact
# position). "Staggered" = gate and source/drain contacts on opposite sides
# of the channel; "coplanar" = gate and contacts on the same side.
TOP_GATE_BOTTOM_CONTACT = "staggered_top_gate"        # gate above, S/D below channel (default)
TOP_GATE_TOP_CONTACT = "coplanar_top_gate"            # gate above, S/D above channel
BOTTOM_GATE_BOTTOM_CONTACT = "coplanar_bottom_gate"   # gate below, S/D below channel
BOTTOM_GATE_TOP_CONTACT = "staggered_bottom_gate"     # gate below, S/D above channel

TOPOLOGIES: dict[str, str] = {
    TOP_GATE_BOTTOM_CONTACT: "Staggered, top-gate (bottom contact)",
    TOP_GATE_TOP_CONTACT: "Coplanar, top-gate (top contact)",
    BOTTOM_GATE_BOTTOM_CONTACT: "Coplanar, bottom-gate (bottom contact)",
    BOTTOM_GATE_TOP_CONTACT: "Staggered, bottom-gate (top contact)",
}


def gate_position(topology: str) -> str:
    """``"top"`` or ``"bottom"`` -- which side of the channel the gate is on."""
    return "bottom" if topology in (BOTTOM_GATE_BOTTOM_CONTACT, BOTTOM_GATE_TOP_CONTACT) else "top"


def contact_position(topology: str) -> str:
    """``"top"`` or ``"bottom"`` -- which side of the channel the S/D contacts are on."""
    return "top" if topology in (TOP_GATE_TOP_CONTACT, BOTTOM_GATE_TOP_CONTACT) else "bottom"


def color_for(material: str) -> str:
    """Return a fill colour for a material name.

    Known materials use the curated palette; unknown (custom) names get a
    stable pastel colour derived from a hash so the same name always looks
    the same. Not used for layer rendering (see :data:`ROLE_COLORS`); kept
    as a general material->colour utility.

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
        """Fill colour for this layer's role (fixed; independent of material)."""
        return ROLE_COLORS.get(self.role, "#cccccc")


@dataclass
class DeviceStructure:
    """A full TFT cross-section definition, in one of the four topologies.

    Layers are stored individually so each material/thickness can be edited
    independently. Lateral geometry is captured by the channel length/width and
    a few schematic layout dimensions. ``topology`` selects which of the four
    standard gate/contact arrangements :func:`TFT_recipe_builder.logic.device_render.draw_device`
    renders (see :data:`TOPOLOGIES`).
    """

    substrate: Layer
    sd_adhesion: Layer       # source/drain adhesion (Ti)
    sd_electrode: Layer      # source/drain electrode (Pt)
    channel: Layer           # semiconductor (IGZO)
    gate_oxide: Layer        # dielectric (Al2O3 / AlOx)
    gate_adhesion: Layer     # gate adhesion (Ti)
    gate_electrode: Layer    # gate electrode (Pt)

    topology: str = TOP_GATE_BOTTOM_CONTACT

    channel_length_nm: float = 5000.0   # L (gap between source and drain)
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
        topology=TOP_GATE_BOTTOM_CONTACT,
        channel_length_nm=5000.0,
        channel_width_nm=10000.0,
    )
