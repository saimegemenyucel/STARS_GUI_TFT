"""Matplotlib plotting routines used by the plot panel.

Each function draws onto a supplied :class:`~matplotlib.figure.Figure` so the
same code works for an embedded Qt canvas or an off-screen export.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from matplotlib.figure import Figure

from TFT_measurement_viewer.bootstrap import config
from TFT_measurement_viewer.logic.data_validator import clean_for_plot
from shared.parameters import PARAMETERS_BY_KEY

logger = logging.getLogger(__name__)


def _label(column: str) -> str:
    """Return 'Label (unit)' for a parameter column."""
    info = PARAMETERS_BY_KEY.get(column)
    return f"{info.label} ({info.unit})" if info else column


def draw_spatial_map(fig: Figure, df: pd.DataFrame, column: str) -> None:
    """Draw a wafer spatial map coloured by a parameter value.

    Args:
        fig: Target figure (cleared in place).
        df: Measurement DataFrame.
        column: Parameter column to colour points by.
    """
    fig.clear()
    ax = fig.add_subplot(111)
    if "position_x" not in df.columns or "position_y" not in df.columns:
        _empty(ax, "No position data (spatial map disabled)")
        return
    data = clean_for_plot(df, column)
    if data.empty:
        _empty(ax, "No spatial data")
        return

    info = PARAMETERS_BY_KEY.get(column)
    values = data[column].to_numpy()
    if info and info.log_scale:
        values = np.log10(np.clip(values, 1e-30, None))
        cbar_label = f"log₁₀({info.label})"
    else:
        cbar_label = _label(column)

    sc = ax.scatter(
        data["position_x"], data["position_y"],
        c=values, cmap=config.HEATMAP_CMAP, s=config.POINT_SIZE,
        edgecolors="black", linewidths=0.3,
    )
    ax.set_xlabel("Position X (mm)")
    ax.set_ylabel("Position Y (mm)")
    ax.set_title(f"Spatial Map — {info.label if info else column}")
    ax.set_aspect("equal", adjustable="datalim")
    fig.colorbar(sc, ax=ax, label=cbar_label, shrink=0.85)
    fig.tight_layout()


def draw_histogram(fig: Figure, df: pd.DataFrame, column: str, bins: int = 30) -> None:
    """Draw a histogram of one parameter, split by pass/fail.

    Args:
        fig: Target figure (cleared in place).
        df: Measurement DataFrame.
        column: Parameter column.
        bins: Number of histogram bins.
    """
    fig.clear()
    ax = fig.add_subplot(111)
    data = clean_for_plot(df, column)
    if data.empty:
        _empty(ax, "No data")
        return

    func = data[data["is_functional"] == True][column]   # noqa: E712
    fail = data[data["is_functional"] != True][column]    # noqa: E712
    rng = (float(data[column].min()), float(data[column].max()))
    ax.hist(func, bins=bins, range=rng, color=config.PASS_COLOR,
            alpha=0.75, label="Functional")
    ax.hist(fail, bins=bins, range=rng, color=config.FAIL_COLOR,
            alpha=0.6, label="Failed")
    ax.set_xlabel(_label(column))
    ax.set_ylabel("Device count")
    ax.set_title(f"Distribution — {_label(column)}")
    ax.legend()
    fig.tight_layout()


def draw_correlation(fig: Figure, df: pd.DataFrame, x_col: str, y_col: str) -> None:
    """Scatter two parameters against each other, coloured by pass/fail.

    Args:
        fig: Target figure (cleared in place).
        df: Measurement DataFrame.
        x_col: Parameter for the x-axis.
        y_col: Parameter for the y-axis.
    """
    fig.clear()
    ax = fig.add_subplot(111)
    data = df.copy()
    for col in (x_col, y_col):
        data[col] = pd.to_numeric(data[col], errors="coerce")
    data = data.replace([np.inf, -np.inf], np.nan).dropna(subset=[x_col, y_col])
    if data.empty:
        _empty(ax, "No data")
        return

    mask = data["is_functional"] == True  # noqa: E712
    ax.scatter(data[mask][x_col], data[mask][y_col], s=35,
               color=config.PASS_COLOR, alpha=0.7, label="Functional")
    ax.scatter(data[~mask][x_col], data[~mask][y_col], s=35,
               color=config.FAIL_COLOR, alpha=0.7, label="Failed")
    ax.set_xlabel(_label(x_col))
    ax.set_ylabel(_label(y_col))
    ax.set_title(f"{_label(x_col)} vs {_label(y_col)}")
    ax.legend()
    fig.tight_layout()


def _empty(ax, message: str) -> None:
    """Render a centred placeholder message on an empty axis."""
    ax.text(0.5, 0.5, message, ha="center", va="center", transform=ax.transAxes)
    ax.set_xticks([])
    ax.set_yticks([])
