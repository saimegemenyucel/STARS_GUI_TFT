"""Device-level data-quality and pass/fail/warning classification for n-type
IGZO TFTs, built for REAL measured data (gate leakage, weak/dead devices,
mobility-fit failures).

Distinct from :mod:`shared.criteria`, which checks whether a device's
parameters fall inside a user-configurable *target spec* (vth_min,
mobility_min, ...) -- this module asks a prior question: is the measurement
and its derived fit physically trustworthy *at all*? A device can fail here
even if its Vth happens to fall inside someone's spec window, because the
underlying fit was noise-dominated, leakage-corrupted, or never really
turned on. Reasons are attached so a human (or a wafer-map tooltip) can see
why, and fit-derived parameters are blanked to NaN ("N/A") on FAIL so they
can't be mistaken for trustworthy numbers downstream.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np
import sqlite3

from shared.tft_analysis import (
    DEFAULT_EPS_R,
    DEFAULT_TOX_NM,
    TransferFeatures,
    extract_transfer_features,
    load_transfer_from_db,
)
from shared.wafer_map import parse_position

# --------------------------------------------------------------------------
# Tunable thresholds -- all named constants so they're easy to retune.
# --------------------------------------------------------------------------
ON_OFF_RATIO_MIN = 1e2             # below this: no real gate control (open/shorted)

ION_MIN_A = 1e-9                   # Ion floor at the reference geometry below
ION_MIN_REF_W_UM = 10.0
ION_MIN_REF_L_UM = 5.0

LOG_ID_STD_MIN_DECADES = 0.3       # below this, |Id| barely varies with Vg (flat film)

GATE_LEAKAGE_FRACTION_MAX = 0.1    # max|Ig| / Ion above this: leakage-dominated

SS_WARN_MV_DEC = 300.0             # SS above this: warning (still functional)

R2_WARN_MIN = 0.90                 # R2 in [R2_WARN_MIN, R2_FAIL_MIN): warning
R2_FAIL_MIN = 0.95                 # R2 below this (but fit not already NaN): low confidence

# A statistically clean (high-R2, low-noise) fit can still land on a mobility
# so low it's not a real conducting channel -- no working oxide TFT runs at
# a few x 1e-3 to 1e-2 cm^2/Vs. The slope-vs-noise guard inside
# shared.tft_analysis only catches *noise-dominated* fits; this catches
# clean-but-physically-dead ones.
MU_SAT_MIN_CM2VS = 0.1

DEFAULT_DEVICE_W_UM = 10.0         # fallback geometry when a sweep has none recorded
DEFAULT_DEVICE_L_UM = 5.0


class DeviceStatus(str, Enum):
    """Overall device classification."""

    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"


@dataclass
class DeviceQualityResult:
    """One device's classification plus every parameter, wafer-map-ready.

    Collect these in a list while looping over a wafer's devices (see
    :func:`classify_wafer`) and the result is already shaped for a spatial
    yield map: ``device_id``, ``position_x``/``position_y``, ``status``.
    """

    device_id: str
    status: DeviceStatus
    fail_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    position_x: Optional[float] = None
    position_y: Optional[float] = None
    # Raw measured parameters -- always real numbers, kept even on FAIL.
    ion: float = float("nan")
    ioff: float = float("nan")
    on_off_ratio: float = float("nan")
    gate_leakage_max: float = float("nan")
    # Fit-derived parameters -- blanked to NaN ("N/A") when status is FAIL.
    vth_sat: float = float("nan")
    ss_min: float = float("nan")
    mu_sat: float = float("nan")
    gm_max: float = float("nan")
    gm_max_vg: float = float("nan")
    sqrt_fit_r2: float = float("nan")

    @property
    def reason_text(self) -> str:
        """Human-readable banner text for the parameter table / tooltip."""
        if self.status is DeviceStatus.FAIL:
            return "DEVICE FAILED: " + "; ".join(self.fail_reasons)
        if self.status is DeviceStatus.WARNING:
            return "WARNING: " + "; ".join(self.warnings)
        return ""


def _ion_min_for_geometry(w_um: float, l_um: float) -> float:
    """Scale the Ion floor by W/L so wide/short and narrow/long devices
    aren't held to the same absolute current floor."""
    ref_ratio = ION_MIN_REF_W_UM / ION_MIN_REF_L_UM
    ratio = (w_um / l_um) if l_um else ref_ratio
    return ION_MIN_A * (ratio / ref_ratio)


def classify_device(
    device_id: str,
    features: TransferFeatures,
    w_um: float,
    l_um: float,
    position_x: float | None = None,
    position_y: float | None = None,
) -> DeviceQualityResult:
    """Classify one device as PASS / WARNING / FAIL with reasons.

    Args:
        device_id: Label for the device (e.g. ``"C4R2 c1r2"``).
        features: Already-extracted :class:`~shared.tft_analysis.TransferFeatures`.
        w_um, l_um: Channel geometry, for the geometry-scaled Ion floor.
        position_x, position_y: Wafer coordinates, if known (for spatial maps).

    Returns:
        A :class:`DeviceQualityResult` with every raw/fit parameter and a
        human-readable reason for any FAIL/WARNING.
    """
    fail_reasons: list[str] = []
    warnings: list[str] = []

    if not np.isfinite(features.on_off_ratio) or features.on_off_ratio < ON_OFF_RATIO_MIN:
        fail_reasons.append(
            f"on/off ratio {features.on_off_ratio:.2g} < {ON_OFF_RATIO_MIN:g} (no gate control)")

    ion_floor = _ion_min_for_geometry(w_um, l_um)
    if not np.isfinite(features.ion) or features.ion < ion_floor:
        fail_reasons.append(f"Ion {features.ion:.2e} A < {ion_floor:.2e} A floor (too weak)")

    if np.isfinite(features.log_id_std_decades) and features.log_id_std_decades < LOG_ID_STD_MIN_DECADES:
        fail_reasons.append(
            f"|Id| barely varies with Vg (std={features.log_id_std_decades:.2f} decades, flat film)")

    if features.ion > 0 and np.isfinite(features.gate_leakage_max):
        leak_frac = features.gate_leakage_max / features.ion
        if leak_frac > GATE_LEAKAGE_FRACTION_MAX:
            fail_reasons.append(
                f"gate leakage {features.gate_leakage_max:.2e} A is "
                f"{leak_frac:.0%} of Ion (untrustworthy fit)")

    fit_rejected = not np.isfinite(features.mu_sat) or not np.isfinite(features.sqrt_fit_r2)
    if fit_rejected:
        fail_reasons.append("mobility/Vth fit rejected (no clean saturation turn-on)")
    elif features.mu_sat < MU_SAT_MIN_CM2VS:
        fail_reasons.append(
            f"mu_sat={features.mu_sat:.3g} cm2/Vs < {MU_SAT_MIN_CM2VS:g} (collapsed/non-conducting channel)")
    elif features.sqrt_fit_r2 < R2_FAIL_MIN:
        if features.sqrt_fit_r2 < R2_WARN_MIN:
            fail_reasons.append(
                f"sqrt(Id) fit R2={features.sqrt_fit_r2:.2f} < {R2_WARN_MIN:g} (poor fit)")
        else:
            warnings.append(
                f"sqrt(Id) fit R2={features.sqrt_fit_r2:.2f} below {R2_FAIL_MIN:g} (low confidence)")

    if features.gm_at_edge:
        # A peak pinned to the sweep boundary is ambiguous: it can be a noise
        # artifact (the intent of shared.tft_analysis.GM_EDGE_MARGIN_POINTS),
        # but on real high-mobility devices it just as often means gm is
        # still rising and the sweep simply isn't wide enough to capture the
        # true rolloff -- not a device defect. Downgraded to a warning
        # (rather than FAIL) after checking against real lab data showed
        # exactly this on otherwise clean, high-mobility, R2=1.0 devices.
        warnings.append(
            f"gm peak at Vg={features.gm_max_vg:.2f} V sits at the sweep edge "
            "(still rising -- widen the Vg sweep to confirm the true peak)")

    if np.isfinite(features.ss_min) and features.ss_min > SS_WARN_MV_DEC:
        warnings.append(f"SS={features.ss_min:.0f} mV/dec > {SS_WARN_MV_DEC:g} (poor subthreshold)")

    if fail_reasons:
        status = DeviceStatus.FAIL
    elif warnings:
        status = DeviceStatus.WARNING
    else:
        status = DeviceStatus.PASS

    keep_fit = status is not DeviceStatus.FAIL
    return DeviceQualityResult(
        device_id=device_id, status=status,
        fail_reasons=fail_reasons, warnings=warnings,
        position_x=position_x, position_y=position_y,
        ion=features.ion, ioff=features.ioff, on_off_ratio=features.on_off_ratio,
        gate_leakage_max=features.gate_leakage_max,
        vth_sat=features.vth_sat if keep_fit else float("nan"),
        ss_min=features.ss_min if keep_fit else float("nan"),
        mu_sat=features.mu_sat if keep_fit else float("nan"),
        gm_max=features.gm_max, gm_max_vg=features.gm_max_vg,
        sqrt_fit_r2=features.sqrt_fit_r2,
    )


def classify_wafer(
    conn: sqlite3.Connection,
    wafer_id: str,
    tox_nm: float = DEFAULT_TOX_NM,
    eps_r: float = DEFAULT_EPS_R,
) -> list[DeviceQualityResult]:
    """Classify every Id-Vg device on a wafer, ready for spatial yield mapping.

    Loops over every Id-Vg sweep linked to ``wafer_id``, reconstructs its
    transfer curve from already-ingested ``iv_points`` (no original Excel
    file needed), extracts fresh features, and classifies it. Each sweep's
    own recorded channel width/length is used (falls back to
    :data:`DEFAULT_DEVICE_W_UM`/:data:`DEFAULT_DEVICE_L_UM` if missing), so a
    wafer with mixed device geometries is still scaled correctly per device.

    Position is derived from the die/transistor grid coordinates encoded in
    the filename (``die_col_row``/``subdie_col_row``), the same convention
    :func:`shared.wafer_map.cells_to_measurement_df` uses, so results plug
    straight into the existing spatial-map plotting code.

    Args:
        conn: Open database connection.
        wafer_id: The wafer to classify.
        tox_nm, eps_r: Gate-oxide assumptions for feature extraction.

    Returns:
        One :class:`DeviceQualityResult` per Id-Vg sweep that had stored
        points, in database order.
    """
    rows = conn.execute(
        "SELECT sweep_id, die_col_row, subdie_col_row, channel_width, channel_length "
        "FROM iv_sweeps WHERE wafer_id = ? AND sweep_type = 'IdVg'",
        (wafer_id,),
    ).fetchall()

    results: list[DeviceQualityResult] = []
    for row in rows:
        curve = load_transfer_from_db(conn, row["sweep_id"])
        if curve is None:
            continue
        w_um = row["channel_width"] or DEFAULT_DEVICE_W_UM
        l_um = row["channel_length"] or DEFAULT_DEVICE_L_UM
        features = extract_transfer_features(curve, w_um, l_um, tox_nm, eps_r)

        die_tok, sub_tok = row["die_col_row"], row["subdie_col_row"]
        device_id = f"{die_tok or '?'} {sub_tok or '?'}".strip()
        die, sub = parse_position(die_tok), parse_position(sub_tok)
        pos_x = (die[0] + sub[0] * 0.08) if die and sub else None
        pos_y = (die[1] + sub[1] * 0.08) if die and sub else None

        results.append(classify_device(device_id, features, w_um, l_um, pos_x, pos_y))
    return results
