"""Render a TFT cross-section (top-gate staggered) onto a matplotlib Figure.

Schematic, not strictly to scale: layer thicknesses drive the vertical drawing
while the lateral channel length is compressed for readability (true L and W are
annotated). The IGZO channel is drawn as a single continuous body that fills the
gap and rests slightly above the source/drain; the gate oxide drapes over it
like an umbrella, touching the source and drain on both sides.
"""

from __future__ import annotations

import logging

import numpy as np
from matplotlib.figure import Figure
from matplotlib.patches import PathPatch, Rectangle
from matplotlib.path import Path

from TFT_recipe_builder.logic.device_model import DeviceStructure, Layer

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


def draw_device(fig: Figure, device: DeviceStructure) -> None:
    """Draw the device cross-section onto ``fig`` (cleared in place)."""
    fig.clear()
    ax = fig.add_subplot(111)

    # --- lateral layout (drawn units) ---
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

    # --- vertical layout ---
    y_sub_top = _SUBSTRATE_DRAW_H
    sd_adh_h = _h(device.sd_adhesion.thickness_nm)
    sd_ele_h = _h(device.sd_electrode.thickness_nm)
    sd_h = sd_adh_h + sd_ele_h
    sd_top = y_sub_top + sd_h
    # Channel rises only slightly above the source/drain.
    ch_rise = float(np.clip(device.channel.thickness_nm * 0.7, 10.0, 26.0))
    y_chtop = sd_top + ch_rise

    # --- substrate ---
    _rect(ax, 0, 0, total_w, _SUBSTRATE_DRAW_H, device.substrate, z=1)
    ax.text(total_w / 2, _SUBSTRATE_DRAW_H / 2,
            f"{device.substrate.label}: {device.substrate.material}  "
            f"({device.substrate.thickness_nm:g} nm, not to scale)",
            ha="center", va="center", fontsize=8, color="white", zorder=3)

    # --- source & drain pads (adhesion then electrode) ---
    for x0, name in ((src_x0, "Source"), (drn_x0, "Drain")):
        y = _rect(ax, x0, y_sub_top, pad_w, sd_adh_h, device.sd_adhesion)
        _rect(ax, x0, y, pad_w, sd_ele_h, device.sd_electrode)
        ax.text(x0 + pad_w / 2, (y_sub_top + sd_top) / 2, name,
                ha="center", va="center", fontsize=8, color="#1a1a1a", zorder=4)

    ch_x0 = src_x1 - overlap
    ch_x1 = drn_x0 + overlap

    # --- channel: single continuous body, flat rounded top, fills the gap ---
    channel_pts = [
        (ch_x0, y_chtop),           # 0 top-left  (round)
        (ch_x1, y_chtop),           # 1 top-right (round)
        (ch_x1, sd_top),            # 2 down to drain top
        (drn_x0, sd_top),           # 3 along drain top to inner edge
        (drn_x0, y_sub_top),        # 4 down drain inner wall to substrate
        (src_x1, y_sub_top),        # 5 across gap on substrate
        (src_x1, sd_top),           # 6 up source inner wall
        (ch_x0, sd_top),            # 7 along source top to outer edge
    ]
    _fill_poly(ax, channel_pts, device.channel.color, z=3)

    # --- gate oxide: trapezoidal cap over the channel; each top corner runs
    #     in a single straight slope down to the source/drain (no step) ---
    t_ox = _h(device.gate_oxide.thickness_nm)
    y_ox_top = y_chtop + t_ox
    ox_x0 = max(ch_x0 - max(gate_ov, 16.0), src_x0 + 3)
    ox_x1 = min(ch_x1 + max(gate_ov, 16.0), drn_x1 - 3)
    oxide_pts = [
        (ch_x0, y_ox_top),   # 1 top-left
        (ch_x1, y_ox_top),   # 2 top-right
        (ox_x1, sd_top),     # 3 right wing tip on drain (single-slope edge 2->3)
        (ch_x1, sd_top),     # 4 back along drain top to channel right base
        (ch_x1, y_chtop),    # 5 up the channel right wall
        (ch_x0, y_chtop),    # 6 across the channel top (flush blanket)
        (ch_x0, sd_top),     # 7 down the channel left wall
        (ox_x0, sd_top),     # 8 along source top to left wing tip
    ]
    _fill_poly(ax, oxide_pts, device.gate_oxide.color, z=4)

    # --- gate: adhesion + electrode, rounded top, centred over the gap ---
    gt_x0 = src_x1 - gate_ov
    gt_x1 = drn_x0 + gate_ov
    gt_adh_h = _h(device.gate_adhesion.thickness_nm)
    gt_ele_h = _h(device.gate_electrode.thickness_nm)
    _rect(ax, gt_x0, y_ox_top, gt_x1 - gt_x0, gt_adh_h, device.gate_adhesion, z=5)
    g_y0 = y_ox_top + gt_adh_h
    gate_pts = [
        (gt_x0, g_y0),
        (gt_x0, g_y0 + gt_ele_h),       # top-left (round)
        (gt_x1, g_y0 + gt_ele_h),       # top-right (round)
        (gt_x1, g_y0),
    ]
    _fill_poly(ax, gate_pts, device.gate_electrode.color, round_idx={1, 2}, z=5)
    gate_top = g_y0 + gt_ele_h
    ax.text((gt_x0 + gt_x1) / 2, (y_ox_top + gate_top) / 2, "Gate",
            ha="center", va="center", fontsize=8, color="#1a1a1a", zorder=6)

    # --- in-structure labels (written directly on the layers) ---
    xc = (src_x1 + drn_x0) / 2
    ax.text(xc, (y_sub_top + y_chtop) / 2, "Channel",
            ha="center", va="center", fontsize=8, color="#08332e", zorder=6)
    ax.text(xc, (y_chtop + y_ox_top) / 2, "Gate Oxide",
            ha="center", va="center", fontsize=7, color="#12314e", zorder=6)

    # --- channel length (L) dimension below the substrate ---
    y_dim = -24.0
    for xx in (src_x1, drn_x0):
        ax.plot([xx, xx], [0, y_dim], color="#c0392b", lw=0.8, ls=":")
    ax.annotate("", xy=(src_x1, y_dim), xytext=(drn_x0, y_dim),
                arrowprops=dict(arrowstyle="<->", color="#c0392b", lw=1.3))
    ax.text((src_x1 + drn_x0) / 2, y_dim - 10,
            f"L = {device.channel_length_nm/1000:g} µm", ha="center", va="top",
            fontsize=8, color="#c0392b")

    # --- legend ---
    handles = [Rectangle((0, 0), 1, 1, facecolor=lyr.color, edgecolor="#2c3e50")
               for lyr in device.all_layers()]
    labels = [f"{lyr.label}: {lyr.material} — {lyr.thickness_nm:g} nm"
              for lyr in device.all_layers()]
    ax.legend(handles, labels, loc="center left", bbox_to_anchor=(1.01, 0.5),
              fontsize=8, frameon=True, title="Layer stack")

    ax.text(0.01, 0.02, f"W = {device.channel_width_nm/1000:g} µm  (into page)",
            transform=ax.transAxes, ha="left", va="bottom", fontsize=8,
            color="#34495e", style="italic")

    ax.set_title("TFT Cross-Section — top-gate staggered (schematic)")
    ax.set_xlim(-10, total_w + 10)
    ax.set_ylim(y_dim - 44, gate_top + 30)
    ax.set_aspect("equal", adjustable="box")
    ax.axis("off")
    fig.tight_layout()
