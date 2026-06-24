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
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import savgol_filter

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
def _read_table(path: str | Path, sheet: str | int = 0) -> pd.DataFrame:
    """Read an .xls/.xlsx/.csv measurement file into a raw DataFrame."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in (".xls", ".xlsx"):
        return pd.read_excel(path, sheet_name=sheet, header=0)
    return pd.read_csv(path, header=0)


def _first_col(df: pd.DataFrame, pattern: str) -> str | None:
    """Return the first column whose name matches ``pattern`` (case-insensitive)."""
    rx = re.compile(pattern, re.IGNORECASE)
    for col in df.columns:
        if rx.search(str(col)):
            return col
    return None


_RUN_SHEET_RX = re.compile(r"^Run\d+$", re.IGNORECASE)


def _best_transfer_sheet(path: Path) -> str | int:
    """Pick the ``Run<N>`` sheet holding the saturation transfer sweep.

    Some lab files contain multiple Run<N> sheets for the *same* transistor,
    one per fixed drain bias the lab re-measured at: a small Vd (linear
    region), a large positive Vd (saturation), and sometimes a reverse-bias
    sweep at negative Vd that is dominated by leakage rather than channel
    current. Excel's sheet-tab order does not reflect this -- it is often
    reverse-chronological (the highest run number, frequently the reverse
    leakage check, ends up first) -- so a plain ``sheet_name=0`` read can
    silently pick the wrong run. The saturation sweep is the one run at the
    largest *positive* drain bias (n-type devices conduct at Vd > 0); falls
    back to the first sheet when there's only one Run<N> sheet to choose from.
    """
    xls = pd.ExcelFile(path)
    run_sheets = [s for s in xls.sheet_names if _RUN_SHEET_RX.match(str(s).strip())]
    if len(run_sheets) <= 1:
        return run_sheets[0] if run_sheets else 0
    best_sheet, best_vd = run_sheets[0], float("-inf")
    for name in run_sheets:
        df = xls.parse(name, header=0)
        c_dv = _first_col(df, r"drain.?v")
        if c_dv is None:
            continue
        vd = pd.to_numeric(df[c_dv], errors="coerce").median()
        if pd.notna(vd) and vd > best_vd:
            best_vd, best_sheet = vd, name
    return best_sheet


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

    When the file has multiple ``Run<N>`` sheets (the same transistor
    re-measured at different fixed drain biases), the saturation run -- the
    largest positive Vd -- is selected; see :func:`_best_transfer_sheet`.

    Args:
        path: Path to the .xls/.csv transfer measurement.

    Returns:
        A :class:`TransferCurve` sorted by ascending gate voltage.
    """
    path = Path(path)
    sheet = _best_transfer_sheet(path) if path.suffix.lower() in (".xls", ".xlsx") else 0
    df = _read_table(path, sheet)
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


def load_transfer_from_db(conn: sqlite3.Connection, sweep_id: int) -> TransferCurve | None:
    """Reconstruct a :class:`TransferCurve` from already-ingested ``iv_points``.

    Lets the UI re-display a sweep's curve without needing the original
    Excel file on disk: ``iv_points`` already holds every raw measurement
    point captured at ingest time.

    Args:
        conn: An open database connection.
        sweep_id: The Id-Vg sweep's ``iv_sweeps.sweep_id``.

    Returns:
        A :class:`TransferCurve`, or ``None`` if no points are stored for it.
    """
    df = pd.read_sql_query(
        "SELECT r.run_id, p.gate_v, p.drain_i, p.gate_i, p.drain_v FROM iv_points p "
        "JOIN iv_runs r ON p.run_id = r.run_id "
        "WHERE r.sweep_id = ? ORDER BY r.run_id, p.point_order",
        conn, params=(sweep_id,),
    )
    if df.empty:
        return None
    # A sweep can hold multiple runs at different fixed Vd (linear region,
    # saturation, reverse-bias leakage check, ...); concatenating them all
    # and sorting by gate_v would interleave points from different bias
    # conditions into one non-physical curve. Keep only the saturation run:
    # the one with the largest positive median Vd (mirrors
    # _best_transfer_sheet's file-based selection).
    best_run = df.groupby("run_id")["drain_v"].median().idxmax()
    df = df[df["run_id"] == best_run]
    gv = pd.to_numeric(df["gate_v"], errors="coerce").to_numpy()
    di = pd.to_numeric(df["drain_i"], errors="coerce").to_numpy()
    gi = pd.to_numeric(df["gate_i"], errors="coerce").to_numpy()
    dv = pd.to_numeric(df["drain_v"], errors="coerce").to_numpy()
    mask = ~(np.isnan(gv) | np.isnan(di))
    gv, di, gi, dv = gv[mask], di[mask], gi[mask], dv[mask]
    if gv.size == 0:
        return None
    order = np.argsort(gv)
    drain_v = float(np.nanmedian(dv)) if dv.size else float("nan")
    return TransferCurve(gv[order], di[order], gi[order], drain_v)


def load_output_from_db(conn: sqlite3.Connection, sweep_id: int) -> list[OutputCurve]:
    """Reconstruct :class:`OutputCurve` list from already-ingested ``iv_points``.

    Mirrors :func:`load_transfer_from_db` for Id-Vd sweeps: one curve per
    ``iv_runs.bias_group`` (or per run, if the sweep predates bias grouping).

    Args:
        conn: An open database connection.
        sweep_id: The Id-Vd sweep's ``iv_sweeps.sweep_id``.

    Returns:
        A list of :class:`OutputCurve`, sorted by gate voltage.
    """
    df = pd.read_sql_query(
        "SELECT r.run_id, r.bias_group, p.drain_v, p.drain_i, p.gate_v FROM iv_points p "
        "JOIN iv_runs r ON p.run_id = r.run_id "
        "WHERE r.sweep_id = ? ORDER BY r.run_id, p.point_order",
        conn, params=(sweep_id,),
    )
    curves: list[OutputCurve] = []
    if df.empty:
        return curves
    group_key = "bias_group" if df["bias_group"].notna().any() else "run_id"
    for _, g in df.groupby(group_key):
        dv = pd.to_numeric(g["drain_v"], errors="coerce").to_numpy()
        di = pd.to_numeric(g["drain_i"], errors="coerce").to_numpy()
        gv = pd.to_numeric(g["gate_v"], errors="coerce").to_numpy()
        mask = ~(np.isnan(dv) | np.isnan(di))
        dv, di, gv = dv[mask], di[mask], gv[mask]
        if dv.size == 0:
            continue
        gate_v = float(np.nanmedian(gv)) if gv.size else float("nan")
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
    # --- Robustness / fit-quality flags (for shared.device_quality) ---
    sqrt_fit_r2: float = float("nan")      # R^2 of the sqrt(Id) linear fit window
    gm_at_edge: bool = False               # True if the gm peak sits at the sweep edge (artifact, not a real peak)
    log_id_std_decades: float = float("nan")  # std of log10|Id| across the sweep (flat-film check)
    # --- Zhou et al. (2022) corrected linear-region extraction ---
    vth_transition: float = float("nan")   # V, exp->power-law transition Vth
    mu_avg_peak: float = float("nan")      # cm^2/Vs, peak linear-region average mobility
    rc_used: float = 0.0                   # ohm, contact resistance used for Vch
    mu_avg: np.ndarray = field(default=None, repr=False)     # array mu_AVG(Vg)
    mu_avg_vg: np.ndarray = field(default=None, repr=False)  # Vg array for mu_avg


def smoothed_derivative(y: np.ndarray, x: np.ndarray) -> np.ndarray:
    """dy/dx via a smoothed (Savitzky-Golay) derivative.

    A point-to-point ``np.gradient`` on noisy measured data is jagged and
    distorts most at the sweep's endpoints (no symmetric neighbor to average
    against), which is what made transconductance plots look like sawtooth
    noise instead of the smooth peak-then-rolloff shape a real device
    produces. Fitting a local polynomial (and differentiating that fit)
    tracks the underlying trend instead of point noise. Falls back to a
    plain gradient when there aren't enough points for the filter window.

    Args:
        y: Dependent variable, evenly spaced in ``x``.
        x: Independent variable (ascending).

    Returns:
        dy/dx, same shape as ``y``.
    """
    n = y.size
    window = min(11, n if n % 2 == 1 else n - 1)
    if window < 5 or n < 5:
        return np.gradient(y, x)
    polyorder = min(3, window - 2)
    dx = float(np.median(np.diff(x))) if n > 1 else 1.0
    return savgol_filter(y, window, polyorder, deriv=1, delta=dx)


# Subthreshold-swing window: only look between this many decades above the
# noise floor (Ioff) and this fraction of Ion -- the "true" subthreshold
# region, not the noise floor itself or the already-on saturation region.
SS_NOISE_FLOOR_DECADE_MARGIN = 1.0
SS_ION_FRACTION = 0.1
# A point is leakage-dominated (and excluded) if |Ig| is within this many
# decades of |Id| -- i.e. |Ig| > |Id| / 10**margin.
SS_LEAKAGE_DECADE_MARGIN = 1.0
# Local window width for the steepest-slope fit. Kept small (3 = the
# minimum for a linear fit) deliberately: subthreshold ln(Id) vs Vg curves
# have real curvature, so a wider window averages in shallower neighboring
# segments and *overestimates* SS (reports a worse number than the true
# steepest transition) -- a 5-point window inflated SS from ~245 to ~345
# mV/dec on a clean real device during calibration against lab data.
SS_FIT_WINDOW_POINTS = 3
SS_MIN_FIT_POINTS = 3              # minimum (leakage-free, in-window) points required


def _robust_subthreshold_swing(
    vg: np.ndarray, idd: np.ndarray, ig: np.ndarray, ion: float, ioff: float,
) -> float:
    """Subthreshold swing from the steepest, leakage-free decade only.

    A single point-to-point ``d(log10|Id|)/dVg`` maximum (the old approach)
    locks onto whichever pair of adjacent points happens to have the most
    measurement noise between them, which is what produced obviously-wrong
    numbers like 500+ mV/dec on weak devices. This instead: (1) restricts to
    the region between ``SS_NOISE_FLOOR_DECADE_MARGIN`` decades above Ioff
    and ``SS_ION_FRACTION`` of Ion -- the true subthreshold decade, not the
    noise floor or the already-saturated region; (2) drops any point where
    gate leakage is within ``SS_LEAKAGE_DECADE_MARGIN`` decades of the drain
    current, since the "current" there is partly leakage, not channel
    modulation; (3) slides a small fit window across what's left and keeps
    the steepest local linear fit. Returns NaN if no clean window exists.

    Args:
        vg: Gate-voltage array, V.
        idd: |Id| array (already floor-clipped), A.
        ig: |Ig| array, A.
        ion, ioff: Already-computed max/min |Id|, A.

    Returns:
        SS in mV/dec, or NaN if no clean subthreshold region was found.
    """
    if ioff <= 0 or ion <= ioff or vg.size < SS_MIN_FIT_POINTS:
        return float("nan")

    lo_bound = ioff * (10.0 ** SS_NOISE_FLOOR_DECADE_MARGIN)
    hi_bound = ion * SS_ION_FRACTION
    if hi_bound <= lo_bound:
        return float("nan")  # device barely turns on; no real subthreshold decade

    leakage_clean = np.abs(ig) < idd / (10.0 ** SS_LEAKAGE_DECADE_MARGIN)
    in_window = (idd >= lo_bound) & (idd <= hi_bound) & leakage_clean
    idx = np.flatnonzero(in_window)
    if idx.size < SS_MIN_FIT_POINTS:
        return float("nan")

    log_id = np.log10(idd)
    window = min(SS_FIT_WINDOW_POINTS, idx.size)
    best_slope = 0.0
    for start in range(idx.size - window + 1):
        sel = idx[start:start + window]
        slope = float(np.polyfit(vg[sel], log_id[sel], 1)[0])
        if slope > best_slope:
            best_slope = slope
    if best_slope <= 0:
        return float("nan")
    return float(1000.0 / best_slope)


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
    log_id_std = float(np.nanstd(np.log10(idd_c)))

    # Transconductance gm = dId/dVg (on signed Id for correct slope sign).
    # Smoothed before differentiating: see smoothed_derivative().
    gm = smoothed_derivative(curve.drain_i.astype(float), vg)
    gm_abs = np.abs(gm)
    i_gm = int(np.nanargmax(gm_abs))
    gm_max = float(gm_abs[i_gm])
    gm_max_vg = float(vg[i_gm])
    # A peak sitting right at the sweep boundary is usually an edge artifact
    # (no symmetric neighbor for the derivative to average against) rather
    # than a real transconductance rolloff -- flag it instead of trusting it.
    gm_at_edge = (i_gm < GM_EDGE_MARGIN_POINTS
                  or i_gm >= len(vg) - GM_EDGE_MARGIN_POINTS)

    # Subthreshold swing: steepest leakage-free decade only (see docstring).
    ss_min = _robust_subthreshold_swing(vg, idd_c, ig, ion, ioff)

    # Saturation Vth + mobility from sqrt(|Id|) vs Vg linear extrapolation.
    cox = oxide_capacitance_per_area(tox_nm, eps_r)
    vth, mu_sat, fvg, fsqrt, r2 = _sqrt_extrapolation(vg, idd_c, gm_abs, w_um, l_um, cox)

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
        sqrt_fit_r2=r2, gm_at_edge=gm_at_edge, log_id_std_decades=log_id_std,
        vth_transition=vth_tr, mu_avg_peak=mu_avg_peak, rc_used=rc_ohm,
        mu_avg=mu_avg, mu_avg_vg=mu_avg_vg,
    )


MAX_PHYSICAL_MU_SAT_CM2VS = 500.0  # generous ceiling for oxide/poly-Si TFTs
SQRT_FIT_HALF_WINDOW = 2           # +/- points around peak slope for the local fit
SQRT_SLOPE_SNR_MIN = 3.0           # fitted slope's per-step rise must exceed this many noise std-devs
GM_EDGE_MARGIN_POINTS = 2          # gm peak within this many points of either edge -> flagged, not a real peak


def _sqrt_extrapolation(vg, idd, gm_abs, w_um, l_um, cox):
    """Fit sqrt(Id) vs Vg near peak slope.

    Returns:
        ``(vth, mu_sat, fit_vg, fit_y, r2)`` -- ``r2`` is the linear fit's
        coefficient of determination over the fit window (NaN if rejected).
    """
    sqrt_id = np.sqrt(idd)
    # Smooth before differentiating. A device that never really turns on
    # (Id stays pinned near the noise/off-current floor across the whole
    # sweep, e.g. a dead transistor) has a sqrt(Id) trace that is flat except
    # for point-to-point measurement noise. Without smoothing, argmax of the
    # raw gradient locks onto that noise as the "steepest slope", and because
    # mu_sat scales with slope**2 this turns a tiny noise wiggle into an
    # unphysical (sometimes billions of cm^2/Vs) mobility.
    smooth = (np.convolve(sqrt_id, np.ones(3) / 3.0, mode="same")
              if sqrt_id.size >= 3 else sqrt_id)
    dsq = np.gradient(smooth, vg)
    i_peak = int(np.nanargmax(dsq))
    lo = max(i_peak - SQRT_FIT_HALF_WINDOW, 0)
    hi = min(i_peak + SQRT_FIT_HALF_WINDOW + 1, len(vg))
    if hi - lo < 2:
        lo, hi = 0, len(vg)
    slope, intercept = np.polyfit(vg[lo:hi], sqrt_id[lo:hi], 1)
    vth = -intercept / slope if slope != 0 else float("nan")

    # mu_sat from slope^2: Id = (W/2L) mu Cox (Vg-Vth)^2  ->  d sqrt(Id)/dVg = sqrt(W mu Cox / 2L)
    w_cm = w_um * 1e-4
    l_cm = l_um * 1e-4
    mu_sat = (2.0 * l_cm / (w_cm * cox)) * slope ** 2 if slope > 0 else float("nan")

    # Goodness of the local linear fit (low R^2 -> "low-confidence", not a
    # hard rejection by itself, but exposed so callers can flag it).
    fit_y_window = slope * vg[lo:hi] + intercept
    ss_tot = float(np.sum((sqrt_id[lo:hi] - np.mean(sqrt_id[lo:hi])) ** 2))
    ss_res = float(np.sum((sqrt_id[lo:hi] - fit_y_window) ** 2))
    r2 = (1.0 - ss_res / ss_tot) if ss_tot > 0 else float("nan")

    # Reject the fit outright if the device never visibly turned on: its
    # sqrt(Id) excursion is then indistinguishable from noise, and any Vth /
    # mobility "extracted" from it is meaningless rather than just imprecise.
    sqrt_range = float(np.nanmax(sqrt_id) - np.nanmin(sqrt_id))
    noise_level = float(np.nanstd(np.diff(sqrt_id))) if sqrt_id.size > 1 else 0.0
    turned_on = sqrt_range > max(5.0 * noise_level, 1e-9)

    # A near-zero (but positive) slope still passes "slope > 0" above and
    # would report a tiny-but-precise-looking mu_sat (e.g. "0.0 cm^2/Vs")
    # instead of admitting the fit is noise-dominated. Require the fitted
    # rise per Vg-step to clear the point-to-point noise by a healthy margin.
    # The noise estimate is taken from the off-state (near-floor) points only
    # -- using the whole curve would conflate real signal (the rise itself)
    # with actual measurement noise and reject perfectly good devices.
    floor_est = float(np.nanmin(idd))
    off_state = idd <= floor_est * 10.0
    off_noise = (float(np.nanstd(np.diff(sqrt_id[off_state])))
                 if np.count_nonzero(off_state) >= 3 else noise_level)
    step = float(np.median(np.diff(vg))) if len(vg) > 1 else 1.0
    slope_signal = abs(slope) * step
    slope_is_noise = slope_signal < SQRT_SLOPE_SNR_MIN * off_noise

    # If the extrapolated Vth falls outside the measured Vg range, the
    # saturation-square-law model doesn't actually describe this sweep --
    # treat the "fit" as failed rather than report an extrapolated number.
    vth_in_range = np.isfinite(vth) and (np.nanmin(vg) <= vth <= np.nanmax(vg))

    if (not turned_on or slope_is_noise or not vth_in_range
            or not np.isfinite(mu_sat) or mu_sat > MAX_PHYSICAL_MU_SAT_CM2VS):
        logger.debug(
            "Rejecting sqrt-extrapolation fit: turned_on=%s slope_is_noise=%s "
            "vth_in_range=%s mu_sat=%s (sqrt_range=%.3g, noise_level=%.3g)",
            turned_on, slope_is_noise, vth_in_range, mu_sat, sqrt_range, noise_level,
        )
        return (float("nan"), float("nan"), np.array([vg[lo], vg[hi - 1]]),
                np.array([np.nan, np.nan]), float("nan"))

    fit_vg = np.array([vth, vg[hi - 1]])
    fit_y = slope * fit_vg + intercept
    return float(vth), float(mu_sat), fit_vg, fit_y, float(r2)


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
    # The 1e-9 V "near zero" guard used to only reject points within ~1 nV of
    # the overdrive=0 or vch=0 singularity. Points merely *close* to either
    # singularity (tens to hundreds of mV away, common whenever rc_ohm makes
    # vch data-dependent) still blow the denominator up into a huge but finite
    # number -- not the literal 1e-9 case, but just as unphysical. Require
    # both terms to be comfortably away from zero, and cap the result at a
    # generous physical ceiling as a final backstop.
    min_denom_term_v = 0.05
    valid = (
        (vg > vth) & np.isfinite(mu)
        & (np.abs(overdrive) > min_denom_term_v) & (np.abs(vch) > min_denom_term_v)
        & (np.abs(mu) <= MAX_PHYSICAL_MU_SAT_CM2VS)
    )
    mu = np.where(valid, mu, np.nan)
    return mu, vg
