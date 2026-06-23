"""Canonical metadata for TFT electrical parameters.

Centralising labels, units and tooltips here keeps every module's tables,
plots and tooltips consistent.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ParameterInfo:
    """Display metadata for a single measurement parameter."""

    key: str          # database column name
    label: str        # human-readable label
    unit: str         # physical unit
    tooltip: str      # explanation shown on hover
    log_scale: bool = False  # whether plots should use a log axis


# Order here defines the default column / selector order in the UI.
PARAMETERS: list[ParameterInfo] = [
    ParameterInfo("vth", "Threshold Voltage", "V",
                  "Gate voltage at which the channel turns on."),
    ParameterInfo("mobility", "Mobility", "cm²/Vs",
                  "Carrier mobility. Higher is better."),
    ParameterInfo("on_off_ratio", "On/Off Ratio", "log₁₀(Ion/Ioff)",
                  "Ratio of on-state to off-state current. Higher is better."),
    ParameterInfo("subthreshold_swing", "Subthreshold Swing", "mV/dec",
                  "Gate swing per decade of current. Lower is better."),
    ParameterInfo("max_drain_current", "Max Drain Current", "A",
                  "Peak on-state drain current.", log_scale=True),
    ParameterInfo("leakage_current", "Leakage Current", "A",
                  "Off-state leakage. Lower is better.", log_scale=True),
]

PARAMETERS_BY_KEY: dict[str, ParameterInfo] = {p.key: p for p in PARAMETERS}

# Defect categories used across modules.
DEFECT_TYPES: list[str] = [
    "open_circuit",
    "short",
    "high_vth",
    "low_mobility",
    "high_leakage",
    "high_ss",
    "other",
]

__all__ = ["ParameterInfo", "PARAMETERS", "PARAMETERS_BY_KEY", "DEFECT_TYPES"]
