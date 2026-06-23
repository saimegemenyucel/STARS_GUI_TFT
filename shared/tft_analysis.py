"""TFT curve-analysis engine: extract device parameters from I-V sweeps.

This is the TFT analogue of the memristor project's feature-extraction stage.
The *raw data* are the transfer (Id-Vg) and output (Id-Vd) measurement sweeps;
the *features* are the standard TFT figures of merit computed here:

Transfer (Id-Vg) features
    - threshold voltage Vth (saturation, sqrt(Id) linear extrapolation)
    - subthreshold swing SS (mV/dec)
    - on/off current ratio, Ion, Ioff
    - peak transconductance gm and its gate voltage
    - saturation field-effect mobility mu_sat (cm^2/Vs)
    - gate leakage magnitude

Output (Id-Vd) features (per gate voltage)
    - saturation drain current Idsat
    - on-resistance Ron (linear region)
    - output conductance gd (saturation region)

All functions are pure and operate on numpy/pandas, so they can be unit-tested
without a GUI.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Physical constants.
EPS0_F_PER_CM = 8.8541878128e-14   # vacuum permittivity (F/cm)
Q = 1.602176634e-19                # elementary charge (C)
KB = 1.380649e-23                  # Boltzmann constant (J/K)

# Defaults for the AlOx gate dielectric in the reference IGZO process.
DEFAULT_EPS_R = 8.0                # Al2O3 relative permittivity
DEFAULT_TOX_NM = 25.0              # gate-oxide thickness (nm)


def oxide_capacitance_per_area(tox_nm: float, eps_r: float = DEFAULT_EPS_R) -> float:
    """Gate-oxide capacitance per unit area Cox.

    Args:
        tox_nm: Oxide thickness in nm.
        eps_r: Relative permittivity of the oxide.

    Returns:
        Cox in F/cm^2.
    """
    tox_cm = tox_nm * 1e-7
    return EPS0_F_PER_CM * eps_r / tox_cm


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------
def _read_table(path: str | Path) -> pd.DataFrame:
    """Read an .xls/.xlsx/.csv measurement file into a raw DataFrame."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in (".xls", ".xlsx"):
        return pd.read_excel(path, header=0)
    return pd.read_csv(path, header=0)


def _first_col(df: pd.DataFrame, pattern: str) -> str | None:
    """Return the first column whose name matches ``pattern`` (case-insensitive)."""
    rx = re.compile(pattern, re.IGNORECASE)
    for col in df.columns:
        if rx.search(str(col)):
            return col
    return None


@dataclass
class TransferCurve:
    """A single Id-Vg transfer sweep at fixed drain voltage."""

    gate_v: np.ndarray
    drain_i: np.ndarray
    gate_i: np.ndarray
    drain_v: float

    @property
    def abs_drain_i(self) -> np.ndarray:
        """|Id| with a small floor to keep logs finite."""
        return np.abs(self.drain_i)


@dataclass
class OutputCurve:
    """A single Id-Vd output sweep at fixed gate voltage."""

    gate_v: float
    drain_v: np.ndarray
    drain_i: np.ndarray


def load_transfer(path: str | Path) -> TransferCurve:
    """Load an Id-Vg file (columns DrainI, DrainV, GateI, GateV).

    Args:
        path: Path to the .xls/.csv transfer measurement.

    Returns:
        A :class:`TransferCurve` sorted by ascending gate voltage.
    """
    df = _read_table(path)
    c_di = _first_col(df, r"drain.?i")
    c_dv = _first_col(df, r"drain.?v")
    c_gi = _first_col(df, r"gate.?i")
    c_gv = _first_col(df, r"gate.?v")
    if not all((c_di, c_gv)):
        raise ValueError(f"Could not find DrainI/GateV columns in {path}")

    gv = pd.to_numeric(df[c_gv], errors="coerce").to_numpy()
    di = pd.to_numeric(df[c_di], errors="coerce").to_numpy()
    gi = pd.to_numeric(df[c_gi], errors="coerce").to_numpy() if c_gi else np.zeros_like(gv)
    dv = pd.to_numeric(df[c_dv], errors="coerce").to_numpy() if c_dv else np.full_like(gv, np.nan)

    mask = ~(np.isnan(gv) | np.isnan(di))
    gv, di, gi = gv[mask], di[mask], gi[mask]
    order = np.argsort(gv)
    drain_v = float(np.nanmedian(dv)) if c_dv else float("nan")
    return TransferCurve(gv[order], di[order], gi[order], drain_v)


def load_output(path: str | Path) -> list[OutputCurve]:
    """Load an Id-Vd file with one or more gate-voltage families.

    Handles the grouped-column layout ``DrainI(1),DrainV(1),GateI(1),GateV(1),
    DrainI(2),...`` produced by the measurement tool.

    Args:
        path: Path to the .xls/.csv output measurement.

    Returns:
        A list of :class:`OutputCurve`, one per gate voltage.
    """
    df = _read_table(path)
    cols = [str(c) for c in df.columns]
    # Group columns by the trailing "(n)" index; ungrouped files become group "".
    groups: dict[str, dict[str, str]] = {}
    for col in cols:
        m = re.search(r"\((\d+)\)\s*$", col)
        key = m.group(1) if m else ""
        role = None
        if re.search(r"drain.?i", col, re.IGNORECASE):
            role = "di"
        elif re.search(r"drain.?v", col, re.IGNORECASE):
            role = "dv"
        elif re.search(r"gate.?v", col, re.IGNORECASE):
            role = "gv"
        if role:
            groups.setdefault(key, {})[role] = col

    curves: list[OutputCurve] = []
    for key, roles in groups.items():
        if "di" not in roles or "dv" not in roles:
            continue
        dv = pd.to_numeric(df[roles["dv"]], errors="coerce").to_numpy()
        di = pd.to_numeric(df[roles["di"]], errors="coerce").to_numpy()
        gv = (pd.to_numeric(df[roles["gv"]], errors="coerce").to_numpy()
              if "gv" in roles else np.full_like(dv, np.nan))
        mask = ~(np.isnan(dv) | np.isnan(di))
        dv, di = dv[mask], di[mask]
        gate_v = float(np.nanmedian(gv[mask])) if "gv" in roles else float("nan")
        order = np.argsort(dv)
        curves.append(OutputCurve(gate_v, dv[order], di[order]))
    curves.sort(key=lambda c: c.gate_v)
    return curves


# --------------------------------------------------------------------------
# Transfer-curve feature extraction
# --------------------------------------------------------------------------
@dataclass
class TransferFeatures:
    """Extracted Id-Vg figures of merit."""

    vth_sat: float                 # V, saturation threshold (sqrt extrapolation)
    ss_min: float                  # mV/dec, minimum subthreshold swing
    on_off_ratio: float            # dimensionless (Ion/Ioff)
    ion: float                     # A, max |Id|
    ioff: float                    # A, min |Id| (noise floor)
    gm_max: float                  # S, peak transconductance |dId/dVg|
    gm_max_vg: float               # V, gate voltage at peak gm
    mu_sat: float                  # cm^2/Vs, saturation field-effect mobility
    gate_leakage_max: float        # A, max |Ig|
    drain_v: float                 # V, drain bias during the sweep
    cox: float = 0.0               # F/cm^2 used
    fit_vg: np.ndarray = field(default=None, repr=False)      # sqrt-fit support
    fit_sqrt_id: np.ndarray = field(default=None, repr=False)
    # --- Zhou et al. (2022) corrected linear-region extraction ---
    vth_transition: float = float("nan")   # V, exp->power-law transition Vth
    mu_avg_peak: float = float("nan")      # cm^2/Vs, peak linear-region average mobility
    rc_used: float = 0.0                   # ohm, contact resistance used for Vch
    mu_avg: np.ndarray = field(default=None, repr=False)     # array mu_AVG(Vg)
    mu_avg_vg: np.ndarray = field(default=None, repr=False)  # Vg array for mu_avg


def extract_transfer_features(
    curve: TransferCurve,
    w_um: float,
    l_um: float,
    tox_nm: float = DEFAULT_TOX_NM,
    eps_r: float = DEFAULT_EPS_R,
    temperature_k: float = 300.0,
    rc_ohm: float = 0.0,
) -> TransferFeatures:
    """Extract TFT parameters from a transfer curve.

    Args:
        curve: The transfer sweep.
        w_um: Channel width (um).
        l_um: Channel length (um).
        tox_nm: Gate-oxide thickness (nm).
        eps_r: Gate-oxide relative permittivity.
        temperature_k: Measurement temperature (K), used only for context.

    Returns:
        A populated :class:`TransferFeatures`.
    """
    vg = curve.gate_v.astype(float)
    idd = curve.abs_drain_i.astype(float)
    ig = np.abs(curve.gate_i).astype(float)

    # Noise floor: clip currents so logs/ratios are well behaved.
    floor = max(np.nanmin(idd[idd > 0]) if np.any(idd > 0) else 1e-14, 1e-14)
    idd_c = np.clip(idd, floor, None)

    ion = float(np.nanmax(idd_c))
    ioff = float(np.nanmin(idd_c))
    on_off = ion / ioff if ioff > 0 else float("inf")

    # Transconductance gm = dId/dVg (on signed Id for correct slope sign).
    gm = np.gradient(curve.drain_i.astype(float), vg)
    gm_abs = np.abs(gm)
    i_gm = int(np.nanargmax(gm_abs))
    gm_max = float(gm_abs[i_gm])
    gm_max_vg = float(vg[i_gm])

    # Subthreshold swing: SS = dVg / d(log10 |Id|), minimum over the rising region.
    log_id = np.log10(idd_c)
    dlog = np.gradient(log_id, vg)
    rising = dlog > 0
    if np.any(rising):
        ss_min = float(1000.0 / np.nanmax(dlog[rising]))  # mV/dec
    else:
        ss_min = float("nan")

    # Saturation Vth + mobility from sqrt(|Id|) vs Vg linear extrapolation.
    cox = oxide_capacitance_per_area(tox_nm, eps_r)
    vth, mu_sat, fvg, fsqrt = _sqrt_extrapolation(vg, idd_c, gm_abs, w_um, l_um, cox)

    # --- Zhou et al. (2022) corrected linear-region extraction ---
    vth_tr = corrected_vth_transition(vg, idd_c)
    mu_avg, mu_avg_vg = average_mobility(
        vg, curve.drain_i.astype(float), vth_tr, curve.drain_v,
        w_um, l_um, cox, rc_ohm)
    mu_avg_peak = (float(np.nanmax(mu_avg))
                   if mu_avg is not None and np.any(np.isfinite(mu_avg))
                   else float("nan"))

    return TransferFeatures(
        vth_sat=vth, ss_min=ss_min, on_off_ratio=on_off, ion=ion, ioff=ioff,
        gm_max=gm_max, gm_max_vg=gm_max_vg, mu_sat=mu_sat,
        gate_leakage_max=float(np.nanmax(ig)) if ig.size else float("nan"),
        drain_v=curve.drain_v, cox=cox, fit_vg=fvg, fit_sqrt_id=fsqrt,
        vth_transition=vth_tr, mu_avg_peak=mu_avg_peak, rc_used=rc_ohm,
        mu_avg=mu_avg, mu_avg_vg=mu_avg_vg,
    )


def _sqrt_extrapolation(vg, idd, gm_abs, w_um, l_um, cox):
    """Fit sqrt(Id) vs Vg near peak slope; return (Vth, mu_sat, fit_vg, fit_y)."""
    sqrt_id = np.sqrt(idd)
    # Use the steepest part of the sqrt curve (max derivative) for the fit.
    dsq = np.gradient(sqrt_id, vg)
    i_peak = int(np.nanargmax(dsq))
    lo = max(i_peak - 2, 0)
    hi = min(i_peak + 3, len(vg))
    if hi - lo < 2:
        lo, hi = 0, len(vg)
    slope, intercept = np.polyfit(vg[lo:hi], sqrt_id[lo:hi], 1)
    vth = -intercept / slope if slope != 0 else float("nan")

    # mu_sat from slope^2: Id = (W/2L) mu Cox (Vg-Vth)^2  ->  d sqrt(Id)/dVg = sqrt(W mu Cox / 2L)
    w_cm = w_um * 1e-4
    l_cm = l_um * 1e-4
    mu_sat = (2.0 * l_cm / (w_cm * cox)) * slope ** 2 if slope > 0 else float("nan")

    fit_vg = np.array([vth, vg[hi - 1]])
    fit_y = slope * fit_vg + intercept
    return float(vth), float(mu_sat), fit_vg, fit_y


# --------------------------------------------------------------------------
# Output-curve feature extraction
# --------------------------------------------------------------------------
@dataclass
class OutputFeatures:
    """Extracted Id-Vd figures of merit for one gate voltage."""

    gate_v: float
    idsat: float        # A, |Id| at the largest |Vd|
    ron: float          # ohm, on-resistance near Vd=0 (linear region)
    gd: float           # S, output conductance in saturation


def extract_output_features(curve: OutputCurve) -> OutputFeatures:
    """Extract output-curve parameters for one gate-voltage family.

    Args:
        curve: The Id-Vd sweep at one gate voltage.

    Returns:
        A populated :class:`OutputFeatures`.
    """
    vd = curve.drain_v.astype(float)
    idd = curve.drain_i.astype(float)
    abs_id = np.abs(idd)

    idsat = float(abs_id[np.nanargmax(np.abs(vd))]) if vd.size else float("nan")

    # On-resistance: slope dVd/dId across the near-zero (linear) region.
    near0 = np.argsort(np.abs(vd))[:5]
    near0 = near0[np.argsort(vd[near0])]
    ron = float("nan")
    if len(near0) >= 2:
        slope_i = np.polyfit(vd[near0], idd[near0], 1)[0]  # dId/dVd
        ron = float(1.0 / slope_i) if slope_i != 0 else float("nan")

    # Output conductance gd = dId/dVd in the high-|Vd| (saturation) region.
    sat = np.argsort(np.abs(vd))[-5:]
    sat = sat[np.argsort(vd[sat])]
    gd = float(np.polyfit(vd[sat], idd[sat], 1)[0]) if len(sat) >= 2 else float("nan")

    return OutputFeatures(gate_v=curve.gate_v, idsat=idsat, ron=abs(ron), gd=abs(gd))


# --------------------------------------------------------------------------
# Zhou et al. (2022) corrected linear-region V_TH and mobility
#   "Accurate Field-Effect Mobility and Threshold Voltage Estimation for
#    Thin-Film Transistors with Gate-Voltage-Dependent Mobility in the Linear
#    Region."
# --------------------------------------------------------------------------
def corrected_vth_transition(vg: np.ndarray, idd: np.ndarray) -> float:
    """Threshold voltage as the exponential -> power-law transition gate voltage.

    Subthreshold: Id is exponential in Vg, so ln(Id) is a straight line.
    Accumulation: Id follows a power law in (Vg - Vth) and that line bends.
    V_TH is the gate voltage of strongest downward curvature of ln(Id) over the
    rising part of the sweep (a d/dVg-of-log-current "knee").

    Args:
        vg: Gate-voltage array (ascending), V.
        idd: |Id| array, A.

    Returns:
        The transition threshold voltage (V), or NaN if it cannot be found.
    """
    vg = np.asarray(vg, dtype=float)
    y = np.log(np.clip(np.abs(np.asarray(idd, dtype=float)), 1e-30, None))
    if vg.size < 5:
        return float("nan")
    y = np.convolve(y, np.ones(3) / 3.0, mode="same")  # tame discrete-step noise
    d1 = np.gradient(y, vg)        # d ln(Id) / dVg
    d2 = np.gradient(d1, vg)       # curvature of ln(Id)
    rising = np.where(d1 > 0)[0]   # only where the device is turning on
    if rising.size == 0:
        return float("nan")
    knee = rising[int(np.nanargmin(d2[rising]))]
    return float(vg[knee])


def channel_voltage(vd: float, idd: np.ndarray, rc_ohm: float) -> np.ndarray:
    """Intrinsic channel voltage after the contact drop: V_ch = V_D - Id*Rc.

    Rc lumps the series source+drain contact resistance; rc_ohm = 0 returns V_D.
    """
    return vd - np.asarray(idd, dtype=float) * rc_ohm


def average_mobility(vg, idd, vth, vd, w_um, l_um, cox, rc_ohm: float = 0.0):
    """Gate-voltage-dependent linear-region "Average Mobility" (Zhou et al.).

    For every gate-voltage point::

        mu_AVG(Vg) = (Id * L) / [ W * Cox * (Vg - Vth - Vch/2) * Vch ]

    The paper proves this is exactly equivalent to its first-order
    finite-difference "corrected field-effect mobility", but simpler and
    noise-robust. With ``rc_ohm > 0`` the applied V_D is replaced by the
    intrinsic channel voltage V_ch = V_D - Id*Rc to remove contact-resistance
    artefacts. Pass *signed* Id and Vd (they share sign in the linear model, so
    mu comes out positive).

    Note: valid for *linear-region* data (small |V_D|); on a saturation sweep it
    returns a number that is not the physical linear mobility.

    Args:
        vg: Gate-voltage array, V.
        idd: Signed drain-current array, A.
        vth: Threshold voltage, V.
        vd: Applied drain voltage, V.
        w_um, l_um: Channel width/length, um.
        cox: Oxide capacitance per area, F/cm^2.
        rc_ohm: Series contact resistance, ohm (0 = ignore).

    Returns:
        ``(mu_avg, vg)`` with ``mu_avg`` an array of mobilities (cm^2/Vs), NaN
        below threshold or where undefined.
    """
    vg = np.asarray(vg, dtype=float)
    idd = np.asarray(idd, dtype=float)
    w_cm, l_cm = w_um * 1e-4, l_um * 1e-4
    vch = channel_voltage(vd, idd, rc_ohm)
    overdrive = vg - vth - vch / 2.0
    denom = w_cm * cox * overdrive * vch
    with np.errstate(divide="ignore", invalid="ignore"):
        mu = (idd * l_cm) / denom
    valid = (vg > vth) & np.isfinite(mu) & (np.abs(overdrive) > 1e-9)
    mu = np.where(valid, mu, np.nan)
    return mu, vg
