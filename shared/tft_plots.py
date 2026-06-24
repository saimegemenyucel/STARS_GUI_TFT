"""Plot routines for TFT curve analysis (pure functions drawing onto a Figure)."""

from __future__ import annotations

import logging

import numpy as np
from matplotlib.figure import Figure

from shared.tft_analysis import (
    OutputCurve,
    TransferCurve,
    TransferFeatures,
    smoothed_derivative,
)

logger = logging.getLogger(__name__)

_PASS = "#2ca02c"
_ACCENT = "#3d8bfd"
_RED = "#d62728"


def draw_full_analysis(
    fig: Figure,
    tc: TransferCurve | None,
    tf: TransferFeatures | None,
    outputs: list[OutputCurve] | None,
) -> None:
    """Draw a 2x2 analysis dashboard (cleared in place).

    Panels: transfer (log), sqrt(Id) with Vth extrapolation, transconductance,
    and the output Id-Vd families.

    Args:
        fig: Target figure.
        tc: Transfer curve (or None).
        tf: Extracted transfer features (or None).
        outputs: Output curves (or None).
    """
    fig.clear()
    ax_log = fig.add_subplot(2, 2, 1)
    ax_sqrt = fig.add_subplot(2, 2, 2)
    ax_gm = fig.add_subplot(2, 2, 3)
    ax_out = fig.add_subplot(2, 2, 4)

    if tc is not None and tf is not None:
        _draw_transfer_log(ax_log, tc, tf)
        _draw_sqrt(ax_sqrt, tc, tf)
        _draw_gm(ax_gm, tc, tf)
    else:
        for ax in (ax_log, ax_sqrt, ax_gm):
            _empty(ax, "Load an Id-Vg file")

    if outputs:
        _draw_output(ax_out, outputs)
    else:
        _empty(ax_out, "Load an Id-Vd file")

    fig.tight_layout()


def _draw_transfer_log(ax, tc: TransferCurve, tf: TransferFeatures) -> None:
    ax.semilogy(tc.gate_v, tc.abs_drain_i, "o-", color=_ACCENT, ms=3, label="|Id|")
    ax.semilogy(tc.gate_v, np.abs(tc.gate_i), ".--", color="#999", ms=2, label="|Ig|")
    if np.isfinite(tf.vth_sat):
        ax.axvline(tf.vth_sat, color=_RED, ls=":", lw=1, label=f"Vth={tf.vth_sat:.2f} V")
    ax.set_xlabel("Gate voltage Vg (V)")
    ax.set_ylabel("|Id| (A)")
    ax.set_title(f"Transfer (Vd={tf.drain_v:.1f} V)")
    ax.legend(fontsize=7)
    ax.grid(True, which="both", alpha=0.25)


def _draw_sqrt(ax, tc: TransferCurve, tf: TransferFeatures) -> None:
    ax.plot(tc.gate_v, np.sqrt(tc.abs_drain_i), "o-", color=_PASS, ms=3, label="√|Id|")
    if tf.fit_vg is not None:
        ax.plot(tf.fit_vg, tf.fit_sqrt_id, "--", color=_RED, lw=1.2,
                label=f"fit → Vth={tf.vth_sat:.2f} V")
    ax.axhline(0, color="#aaa", lw=0.6)
    ax.set_xlabel("Gate voltage Vg (V)")
    ax.set_ylabel("√|Id| (A$^{1/2}$)")
    ax.set_title(f"√Id extrapolation — μ_sat={tf.mu_sat:.1f} cm²/Vs")
    ax.legend(fontsize=7)
    ax.grid(True, alpha=0.25)


def _draw_gm(ax, tc: TransferCurve, tf: TransferFeatures) -> None:
    gm = smoothed_derivative(tc.drain_i.astype(float), tc.gate_v.astype(float))
    ax.plot(tc.gate_v, np.abs(gm), "o-", color="#9467bd", ms=3)
    ax.plot([tf.gm_max_vg], [tf.gm_max], "v", color=_RED,
            label=f"gm_max={tf.gm_max:.2e} S")
    ax.set_xlabel("Gate voltage Vg (V)")
    ax.set_ylabel("|gm| (S)")
    ax.set_title("Transconductance")
    ax.legend(fontsize=7)
    ax.grid(True, alpha=0.25)


def _draw_output(ax, outputs: list[OutputCurve]) -> None:
    # Signed Id, not |Id|: abs() folds a Vd sweep that crosses zero (or
    # reverses polarity) into a false V-shape and hides genuine asymmetry
    # between the positive- and negative-Vd branches (seen on real devices).
    cmap = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b"]
    for i, oc in enumerate(outputs):
        ax.plot(oc.drain_v, oc.drain_i, "-", color=cmap[i % len(cmap)],
                lw=1.4, label=f"Vg={oc.gate_v:+.1f} V")
    ax.axhline(0, color="#aaa", lw=0.6)
    ax.set_xlabel("Drain voltage Vd (V)")
    ax.set_ylabel("Id (A)")
    ax.set_title("Output characteristics")
    ax.legend(fontsize=7)
    ax.grid(True, alpha=0.25)


def _empty(ax, msg: str) -> None:
    ax.text(0.5, 0.5, msg, ha="center", va="center", transform=ax.transAxes,
            fontsize=9, color="#888")
    ax.set_xticks([]); ax.set_yticks([])
