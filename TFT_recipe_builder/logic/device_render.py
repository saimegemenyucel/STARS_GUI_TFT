"""Render a TFT cross-section onto a matplotlib Figure, in any of the four
standard gate/contact topologies (see :mod:`TFT_recipe_builder.logic.device_model`).

Schematic, not strictly to scale: layer thicknesses drive the vertical drawing
while the lateral channel length is compressed for readability (true L and W
are annotated). The stack is assembled bottom-up in three stages so every
topology reuses the same building blocks:

1. Gate stage (if the gate is on the bottom): a gate bump embedded in a flat
   gate-oxide block, giving a flat surface for the next stage to sit on.
2. Channel/contact stage: either the source/drain pads sit on the floor and
   the channel bridges over them (bottom contact), or the channel is a flat
   slab on the floor and the pads sit on top of it (top contact).
3. Gate stage (if the gate is on top): the gate oxide drapes over the
   channel -- down to the pad tops if the pads are lower (bottom contact), or
   as a simple block plugging the gap if the pads are already higher (top
   contact, so there's no lower shoulder to drape to) -- then the gate sits
   centred on top of the oxide.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from matplotlib.figure import Figure
from matplotlib.patches import PathPatch, Rectangle
from matplotlib.path import Path

from TFT_recipe_builder.logic.device_model import (
    TOPOLOGIES,
    DeviceStructure,
    Layer,
    contact_position,
    gate_position,
)

logger = logging.getLogger(__name__)

_H_SCALE = 0.06            # drawn horizontal units per nm of lateral distance
_SUBSTRATE_DRAW_H = 62.0   # fixed schematic substrate height
_MIN_DRAW_H = 7.0          # visibility floor for thin layers
_GAP_DRAW_MIN = 45.0
_GAP_DRAW_MAX = 520.0
_CORNER_R = 9.0            # rounding radius for top corners


def _h(thickness_nm: float) -> float:
    """Map a real thickness (nm) to a drawn height, with a visibility floor."""
    return max(thickness_nm, _MIN_DRAW_H)


@dataclass
class _Lateral:
    """Shared lateral (x-axis) layout, independent of topology."""

    pad_w: float
    gap: float
    overlap: float
    gate_ov: float
    src_x0: float
    src_x1: float
    drn_x0: float
    drn_x1: float
    total_w: float
    ch_x0: float
    ch_x1: float
    gt_x0: float
    gt_x1: float


def _lateral_layout(device: DeviceStructure) -> _Lateral:
    pad_w = max(device.sd_pad_length_nm * _H_SCALE, 80.0)
    gap = min(max(device.channel_length_nm * _H_SCALE, _GAP_DRAW_MIN), _GAP_DRAW_MAX)
    overlap = max(device.channel_overlap_nm * _H_SCALE, 18.0)
    gate_ov = max(device.gate_overlap_nm * _H_SCALE, 12.0)
    margin = 60.0

    src_x0 = margin
    src_x1 = src_x0 + pad_w
    drn_x0 = src_x1 + gap
    drn_x1 = drn_x0 + pad_w
    total_w = drn_x1 + margin

    return _Lateral(
        pad_w=pad_w, gap=gap, overlap=overlap, gate_ov=gate_ov,
        src_x0=src_x0, src_x1=src_x1, drn_x0=drn_x0, drn_x1=drn_x1, total_w=total_w,
        ch_x0=src_x1 - overlap, ch_x1=drn_x0 + overlap,
        gt_x0=src_x1 - gate_ov, gt_x1=drn_x0 + gate_ov,
    )


def _rounded_polygon(points: list[tuple[float, float]], radius: float,
                     round_idx: set[int]) -> Path:
    """Build a closed Path from ``points``, rounding the listed vertex indices.

    Args:
        points: Polygon vertices in order.
        radius: Corner radius (clamped to half the shorter adjacent edge).
        round_idx: Indices of vertices to round with a quadratic bezier.

    Returns:
        A closed matplotlib Path.
    """
    verts: list[tuple[float, float]] = []
    codes: list[int] = []
    n = len(points)
    first = True
    for i in range(n):
        p = np.array(points[i], dtype=float)
        if i in round_idx:
            prev = np.array(points[(i - 1) % n], dtype=float)
            nxt = np.array(points[(i + 1) % n], dtype=float)
            v1, v2 = prev - p, nxt - p
            l1, l2 = np.hypot(*v1), np.hypot(*v2)
            r = min(radius, l1 / 2, l2 / 2)
            a = p + v1 / l1 * r
            b = p + v2 / l2 * r
            verts.append(tuple(a)); codes.append(Path.MOVETO if first else Path.LINETO)
            verts.append(tuple(p)); codes.append(Path.CURVE3)
            verts.append(tuple(b)); codes.append(Path.CURVE3)
        else:
            verts.append(tuple(p)); codes.append(Path.MOVETO if first else Path.LINETO)
        first = False
    verts.append(verts[0]); codes.append(Path.CLOSEPOLY)
    return Path(verts, codes)


def _fill_poly(ax, points, color, round_idx=None, radius=_CORNER_R, z=2):
    """Draw a filled polygon (optionally with rounded corners)."""
    path = _rounded_polygon(points, radius, round_idx or set())
    ax.add_patch(PathPatch(path, facecolor=color, edgecolor="#2c3e50",
                           linewidth=1.0, zorder=z))


def _rect(ax, x, y, w, h, layer: Layer, z=2):
    """Draw a layer rectangle and return its top y."""
    ax.add_patch(Rectangle((x, y), w, h, facecolor=layer.color,
                           edgecolor="#2c3e50", linewidth=1.0, zorder=z))
    return y + h


def _label(ax, x, y, text, color, z, fontsize=8):
    ax.text(x, y, text, ha="center", va="center", fontsize=fontsize, color=color, zorder=z)


# --------------------------------------------------------------------------
# Stage 1 / 3: the gate (+ its oxide), on whichever side it falls.
# --------------------------------------------------------------------------
def _draw_bottom_gate_block(ax, device: DeviceStructure, lay: _Lateral, z0: int) -> float:
    """Gate embedded in a flat gate-oxide block sitting on the substrate.

    The oxide is drawn as side-fill beside the gate (substrate up to the
    gate's top) plus a thin uniform cap over the whole width, so the gate's
    own colour stays visible as a distinct embedded bump instead of being
    painted over by an opaque full-width oxide rectangle.

    Returns:
        The flat floor y the next stage (channel/contacts) sits on.
    """
    gt_adh_h = _h(device.gate_adhesion.thickness_nm)
    gt_ele_h = _h(device.gate_electrode.thickness_nm)
    gt_top = _SUBSTRATE_DRAW_H + gt_adh_h + gt_ele_h
    t_ox = _h(device.gate_oxide.thickness_nm)

    _rect(ax, lay.src_x0, _SUBSTRATE_DRAW_H, lay.gt_x0 - lay.src_x0,
          gt_adh_h + gt_ele_h, device.gate_oxide, z=z0)
    _rect(ax, lay.gt_x1, _SUBSTRATE_DRAW_H, lay.drn_x1 - lay.gt_x1,
          gt_adh_h + gt_ele_h, device.gate_oxide, z=z0)

    y = _rect(ax, lay.gt_x0, _SUBSTRATE_DRAW_H, lay.gt_x1 - lay.gt_x0,
              gt_adh_h, device.gate_adhesion, z=z0 + 1)
    gate_pts = [(lay.gt_x0, y), (lay.gt_x0, gt_top), (lay.gt_x1, gt_top), (lay.gt_x1, y)]
    _fill_poly(ax, gate_pts, device.gate_electrode.color, round_idx={1, 2}, z=z0 + 1)
    _label(ax, (lay.gt_x0 + lay.gt_x1) / 2, (y + gt_top) / 2, "Gate", "#1a1a1a", z0 + 2)

    floor_y = gt_top + t_ox
    _rect(ax, lay.src_x0, gt_top, lay.drn_x1 - lay.src_x0, t_ox, device.gate_oxide, z=z0 + 3)
    _label(ax, (lay.src_x0 + lay.drn_x1) / 2, gt_top + t_ox / 2, "Gate Oxide", "#12314e", z0 + 4, fontsize=7)
    return floor_y


def _draw_top_gate_block(ax, device: DeviceStructure, lay: _Lateral,
                          channel_top: float, sd_top: float, z0: int) -> float:
    """Gate oxide draped over the channel, with the gate centred on top.

    If the source/drain pads sit lower than the channel (bottom contact),
    the oxide drapes down to the pad tops like an umbrella, as a continuous
    insulator over the whole gap. If the pads already sit higher (top
    contact -- there's no lower shoulder to reach), it's simply a block
    plugging the gap, flush with the channel's exposed top surface.

    Returns:
        The gate's top y (for the figure's vertical extent).
    """
    t_ox = _h(device.gate_oxide.thickness_nm)
    y_ox_top = channel_top + t_ox
    ox_x0 = max(lay.ch_x0 - max(lay.gate_ov, 16.0), lay.src_x0 + 3)
    ox_x1 = min(lay.ch_x1 + max(lay.gate_ov, 16.0), lay.drn_x1 - 3)

    if sd_top < channel_top:
        oxide_pts = [
            (lay.ch_x0, y_ox_top), (lay.ch_x1, y_ox_top),
            (ox_x1, sd_top), (lay.ch_x1, sd_top), (lay.ch_x1, channel_top),
            (lay.ch_x0, channel_top), (lay.ch_x0, sd_top), (ox_x0, sd_top),
        ]
    else:
        # No lower shoulder to drape to (pads already sit above the
        # channel) -- plug exactly the bare gap, not the wider
        # overlap-inclusive channel footprint, or this block would paint
        # over the inner edges of the source/drain pads sitting just above.
        oxide_pts = [
            (lay.src_x1, y_ox_top), (lay.drn_x0, y_ox_top),
            (lay.drn_x0, channel_top), (lay.src_x1, channel_top),
        ]
    _fill_poly(ax, oxide_pts, device.gate_oxide.color, z=z0)
    _label(ax, (lay.src_x1 + lay.drn_x0) / 2, (channel_top + y_ox_top) / 2,
            "Gate Oxide", "#12314e", z0 + 1, fontsize=7)

    gt_adh_h = _h(device.gate_adhesion.thickness_nm)
    gt_ele_h = _h(device.gate_electrode.thickness_nm)
    y = _rect(ax, lay.gt_x0, y_ox_top, lay.gt_x1 - lay.gt_x0, gt_adh_h, device.gate_adhesion, z=z0 + 2)
    gate_pts = [(lay.gt_x0, y), (lay.gt_x0, y + gt_ele_h), (lay.gt_x1, y + gt_ele_h), (lay.gt_x1, y)]
    _fill_poly(ax, gate_pts, device.gate_electrode.color, round_idx={1, 2}, z=z0 + 2)
    gate_top = y + gt_ele_h
    _label(ax, (lay.gt_x0 + lay.gt_x1) / 2, (y_ox_top + gate_top) / 2, "Gate", "#1a1a1a", z0 + 3)
    return gate_top


# --------------------------------------------------------------------------
# Stage 2: the channel and its source/drain contacts.
# --------------------------------------------------------------------------
def _draw_bottom_contact_channel(ax, device: DeviceStructure, lay: _Lateral,
                                  floor_y: float, z0: int) -> tuple[float, float]:
    """Source/drain pads on the floor; channel bridges over them and the gap.

    Returns:
        ``(sd_top, channel_top)``.
    """
    sd_adh_h = _h(device.sd_adhesion.thickness_nm)
    sd_ele_h = _h(device.sd_electrode.thickness_nm)
    sd_top = floor_y + sd_adh_h + sd_ele_h
    ch_rise = float(np.clip(device.channel.thickness_nm * 0.7, 10.0, 26.0))
    channel_top = sd_top + ch_rise

    for x0, name in ((lay.src_x0, "Source"), (lay.drn_x0, "Drain")):
        y = _rect(ax, x0, floor_y, lay.pad_w, sd_adh_h, device.sd_adhesion, z=z0)
        _rect(ax, x0, y, lay.pad_w, sd_ele_h, device.sd_electrode, z=z0)
        _label(ax, x0 + lay.pad_w / 2, (floor_y + sd_top) / 2, name, "#1a1a1a", z0 + 1)

    # Single continuous body: flat rounded top, fills the gap down to the
    # floor, rests slightly above the source/drain on the sides.
    channel_pts = [
        (lay.ch_x0, channel_top), (lay.ch_x1, channel_top),
        (lay.ch_x1, sd_top), (lay.drn_x0, sd_top),
        (lay.drn_x0, floor_y), (lay.src_x1, floor_y),
        (lay.src_x1, sd_top), (lay.ch_x0, sd_top),
    ]
    _fill_poly(ax, channel_pts, device.channel.color, z=z0 + 2)
    xc = (lay.src_x1 + lay.drn_x0) / 2
    _label(ax, xc, (floor_y + channel_top) / 2, "Channel", "#08332e", z0 + 3)
    return sd_top, channel_top


def _draw_top_contact_channel(ax, device: DeviceStructure, lay: _Lateral,
                               floor_y: float, z0: int) -> tuple[float, float]:
    """Channel is a flat slab on the floor; source/drain pads sit on top of it.

    Returns:
        ``(channel_top, sd_top)``.
    """
    ch_h = _h(device.channel.thickness_nm)
    channel_top = floor_y + ch_h
    _rect(ax, lay.src_x0, floor_y, lay.drn_x1 - lay.src_x0, ch_h, device.channel, z=z0)
    xc = (lay.src_x1 + lay.drn_x0) / 2
    _label(ax, xc, (floor_y + channel_top) / 2, "Channel", "#08332e", z0 + 1)

    sd_adh_h = _h(device.sd_adhesion.thickness_nm)
    sd_ele_h = _h(device.sd_electrode.thickness_nm)
    sd_top = channel_top + sd_adh_h + sd_ele_h
    for x0, name in ((lay.src_x0, "Source"), (lay.drn_x0, "Drain")):
        y = _rect(ax, x0, channel_top, lay.pad_w, sd_adh_h, device.sd_adhesion, z=z0 + 2)
        _rect(ax, x0, y, lay.pad_w, sd_ele_h, device.sd_electrode, z=z0 + 2)
        _label(ax, x0 + lay.pad_w / 2, (channel_top + sd_top) / 2, name, "#1a1a1a", z0 + 3)
    return channel_top, sd_top


def draw_device(fig: Figure, device: DeviceStructure) -> None:
    """Draw the device cross-section onto ``fig`` (cleared in place)."""
    fig.clear()
    ax = fig.add_subplot(111)
    lay = _lateral_layout(device)

    # --- substrate (always the floor) ---
    _rect(ax, 0, 0, lay.total_w, _SUBSTRATE_DRAW_H, device.substrate, z=1)
    ax.text(lay.total_w / 2, _SUBSTRATE_DRAW_H / 2,
            f"{device.substrate.label}: {device.substrate.material}  "
            f"({device.substrate.thickness_nm:g} nm, not to scale)",
            ha="center", va="center", fontsize=8, color="white", zorder=1.5)

    # --- stage 1: bottom-gate, if applicable ---
    if gate_position(device.topology) == "bottom":
        floor_y = _draw_bottom_gate_block(ax, device, lay, z0=2)
    else:
        floor_y = _SUBSTRATE_DRAW_H

    # --- stage 2: channel + contacts ---
    if contact_position(device.topology) == "bottom":
        sd_top, channel_top = _draw_bottom_contact_channel(ax, device, lay, floor_y, z0=10)
    else:
        channel_top, sd_top = _draw_top_contact_channel(ax, device, lay, floor_y, z0=10)

    # --- stage 3: top-gate, if applicable ---
    if gate_position(device.topology) == "top":
        top_y = _draw_top_gate_block(ax, device, lay, channel_top, sd_top, z0=20)
    else:
        # Gate was already drawn below in stage 1; the channel/contact
        # stage (2) is the topmost content now, so size to its peak.
        top_y = max(channel_top, sd_top)

    # --- channel length (L) dimension below the substrate ---
    y_dim = -24.0
    for xx in (lay.src_x1, lay.drn_x0):
        ax.plot([xx, xx], [0, y_dim], color="#c0392b", lw=0.8, ls=":")
    ax.annotate("", xy=(lay.src_x1, y_dim), xytext=(lay.drn_x0, y_dim),
                arrowprops=dict(arrowstyle="<->", color="#c0392b", lw=1.3))
    ax.text((lay.src_x1 + lay.drn_x0) / 2, y_dim - 10,
            f"L = {device.channel_length_nm/1000:g} µm", ha="center", va="top",
            fontsize=8, color="#c0392b")

    # --- legend, overlaid inside the drawing's own empty space (top-right)
    #     instead of a separate side column, so the cross-section itself can
    #     use the figure's full width. ---
    handles = [Rectangle((0, 0), 1, 1, facecolor=lyr.color, edgecolor="#2c3e50")
               for lyr in device.all_layers()]
    labels = [f"{lyr.label}: {lyr.material} — {lyr.thickness_nm:g} nm"
              for lyr in device.all_layers()]
    legend = ax.legend(handles, labels, loc="upper right", bbox_to_anchor=(0.99, 0.99),
                       bbox_transform=ax.transAxes, fontsize=7, frameon=True,
                       title="Layer stack", handlelength=1.3, handleheight=1.0,
                       labelspacing=0.35, borderpad=0.6)
    legend.get_frame().set_facecolor("#ffffff")
    legend.get_frame().set_alpha(0.92)
    legend.get_title().set_fontsize(8)
    # Device patches use zorder up to ~24 (see z0 in the stage helpers above);
    # without this the legend (default zorder ~5) renders *behind* whichever
    # layer it happens to overlap, since it's deliberately placed on top of
    # the drawing to save space.
    legend.set_zorder(100)

    ax.text(0.01, 0.02, f"W = {device.channel_width_nm/1000:g} µm  (into page)",
            transform=ax.transAxes, ha="left", va="bottom", fontsize=8,
            color="#34495e", style="italic")

    ax.set_title(f"TFT Cross-Section — {TOPOLOGIES[device.topology]} (schematic)")
    ax.set_xlim(-10, lay.total_w + 10)
    ax.set_ylim(y_dim - 44, top_y + 30)
    ax.set_aspect("equal", adjustable="box")
    ax.axis("off")
    fig.tight_layout()
