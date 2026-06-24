"""Generate an artificial 'Artificial Data Wafer' folder of example I-V files.

Creates one wafer folder of Id-Vg (transfer) and Id-Vd (output) .xlsx files for
transistors spread over a 5x8 die grid with up to 8x8 transistors per die,
following the lab's filename convention and sheet structure. Curves follow a
single n-type IGZO square-law model (with gate-overdrive mobility
degradation) shared by both sweeps, so the app's √Id / gm / output extraction
all see one physically consistent device. A realistic mix of good / weak /
dead devices is included so the wafer map shows pass (green) and fail (red)
cells.

Run on a machine with pandas + openpyxl installed::

    python tools/make_artificial_wafer.py                          # default density
    python tools/make_artificial_wafer.py --per-die 16             # denser
    python tools/make_artificial_wafer.py --name "Artificial Data Wafer V2"
    python tools/make_artificial_wafer.py "/path/to/Wafers"

Then import it (see the reminder printed at the end).

The wafer name doubles as the ingest folder name and as the database wafer_id.
Run numbers are embedded in every filename and ``iv_sweeps.source_file`` is
globally unique, so two wafers generated under the *same* name and seed would
produce byte-identical filenames and collide on import. Each name therefore
gets its own deterministic run-number range (and, by default, its own RNG
seed) derived from a hash of the name, so generating wafers under different
``--name`` values is always safe to import side by side.
"""

from __future__ import annotations

import argparse
import zlib
from pathlib import Path

import numpy as np
import pandas as pd

DEFAULT_BASE = Path.home() / "Desktop" / "Wafers"
DEFAULT_WAFER_NAME = "Artificial Data Wafer"

# --------------------------------------------------------------------------
# n-type IGZO device physics: single source of truth for all four curves
# (transfer log, sqrt(Id) extrapolation, transconductance, output Id-Vd).
# Square law with gate-overdrive mobility degradation:
#   mu_eff(Vg) = mu0 / (1 + theta1*Vov + theta2*Vov^2), Vov = max(Vg-Vth, 0)
#   Saturation: Id = (W/2L) * mu_eff * Cox * (Vg-Vth)^2 * (1 + lambda*Vd)
#   Triode:     Id = (W/L)  * mu_eff * Cox * [(Vg-Vth)*Vd - Vd^2/2]
# The theta1 (linear) term alone only makes Id sub-quadratic in Vov -- gm
# decelerates towards a plateau but never actually turns over. The theta2
# (quadratic, velocity-saturation-like) term is what gives gm a real
# peak-then-decline at high overdrive, matching real short-channel TFTs.
# n-type IGZO is electron-conduction with Vd applied positive; Vth is
# negative (depletion-mode), so the transistor turns on as Vg rises through
# it left-to-right on a transfer plot.
# --------------------------------------------------------------------------
EPS0_F_PER_CM = 8.8541878128e-14
TOX_NM, EPS_R = 25.0, 8.0
COX = EPS0_F_PER_CM * EPS_R / (TOX_NM * 1e-7)     # F/cm^2 (AlOx 25 nm)
W_UM, L_UM = 10.0, 5.0
W_CM, L_CM = W_UM * 1e-4, L_UM * 1e-4
VD_TRANSFER = 5.0                                 # V, positive (n-type) drain bias
LAMBDA = 0.02                                     # /V, channel-length modulation
VT_THERMAL = 0.02585                              # kT/q at ~300 K
LN10 = np.log(10.0)
I_FLOOR = 1e-13                                   # off-state leakage floor (A)

DIE_COLS, DIE_ROWS = 5, 8                         # wafer = 5 cols x 8 rows of dies
TR_COLS, TR_ROWS = 8, 8                           # up to 8x8 transistors per die
MATERIALS = ["TiPt", "Pt", "W", "TaPt", "MoPt", "AuPt"]


def _softplus(z: np.ndarray) -> np.ndarray:
    """Numerically stable softplus: log(1+exp(z))."""
    return np.maximum(z, 0.0) + np.log1p(np.exp(-np.abs(z)))


def _mu_eff(vov: np.ndarray, mu0: float, theta1: float, theta2: float) -> np.ndarray:
    """Gate-overdrive mobility degradation: mu0 / (1 + theta1*Vov + theta2*Vov^2).

    The linear term alone makes Id sub-quadratic in Vov (√Id concave) but
    gm only decelerates towards a plateau, never actually decreasing. The
    quadratic term gives gm a real peak-then-decline at high overdrive,
    matching real short-channel TFTs -- the same curvature both √Id and gm
    must show since they come from this one mu_eff(Vg).
    """
    vov = np.clip(vov, 0.0, None)
    return mu0 / (1.0 + theta1 * vov + theta2 * vov ** 2)


def transfer_curve(vth: float, mu0: float, ss_mv: float, theta1: float,
                    theta2: float, rng) -> pd.DataFrame:
    """Id-Vg sheet: smooth square-law turn-on with mobility degradation."""
    vg = np.round(np.linspace(-5, 5, 41), 4)      # finer sweep → better SS/Vth
    n = (ss_mv / 1000.0) / (VT_THERMAL * LN10)    # ideality from desired SS
    nvt = max(n * VT_THERMAL, 1e-3)
    vov = nvt * _softplus((vg - vth) / nvt)       # smooth overdrive (≥0)
    mu_eff = _mu_eff(vg - vth, mu0, theta1, theta2)
    k = 0.5 * (W_CM / L_CM) * COX * (1.0 + LAMBDA * VD_TRANSFER)
    idd = k * mu_eff * vov ** 2 + I_FLOOR
    idd = np.clip(idd * (1 + rng.normal(0, 0.015, vg.size)), I_FLOOR, None)
    return pd.DataFrame({
        "DrainI": idd, "DrainV": np.full(vg.size, VD_TRANSFER),
        "GateI": rng.normal(0, 1e-12, vg.size), "GateV": vg,
    })


def _idvd(vd: np.ndarray, vov: float, mu0: float, theta1: float, theta2: float) -> np.ndarray:
    """n-type output current vs. positive drain voltage at a fixed gate bias.

    Triode (vd < vov): Id = (W/L)*mu_eff*Cox*[vov*vd - vd^2/2]
    Saturation (vd >= vov): Id = 0.5*(W/L)*mu_eff*Cox*vov^2*(1+lambda*vd)
    """
    if vov <= 0:
        return np.zeros_like(vd)
    mu_eff = _mu_eff(np.full_like(vd, vov), mu0, theta1, theta2)
    k = (W_CM / L_CM) * mu_eff * COX
    triode = k * (vov * vd - vd ** 2 / 2.0)
    sat = k * 0.5 * vov ** 2 * (1.0 + LAMBDA * vd)
    return np.where(vd < vov, triode, sat)


def output_curve(vth: float, mu0: float, theta1: float, theta2: float, rng) -> pd.DataFrame:
    """Id-Vd sheet with three on-state gate-bias groups, Vd swept 0 -> +5 V."""
    vd = np.round(np.linspace(0, 5, 51), 4)
    cols: dict[str, np.ndarray] = {}
    for i, vg in enumerate((0.0, 2.5, 5.0), start=1):
        vov = vg - vth
        idd = _idvd(vd, vov, mu0, theta1, theta2) * (1 + rng.normal(0, 0.02, vd.size))
        cols[f"DrainI({i})"] = idd
        cols[f"DrainV({i})"] = vd
        cols[f"GateI({i})"] = rng.normal(0, 1e-12, vd.size)
        cols[f"GateV({i})"] = np.full(vd.size, vg)
    return pd.DataFrame(cols)


def _settings_sheet(name: str) -> pd.DataFrame:
    return pd.DataFrame({"==================================": [
        f"Test Name: {name}", "Start: -5", "Stop: 5", "Step: 0.25",
        "Compliance: 1e-3", "(artificial data)"]})


def write_file(path: Path, run_no: int, data: pd.DataFrame) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as xl:
        data.to_excel(xl, sheet_name=f"Run{run_no}", index=False)
        _settings_sheet(path.stem).to_excel(xl, sheet_name="Settings", index=False)
        pd.DataFrame().to_excel(xl, sheet_name="Calc", index=False)


def device_params(rng) -> tuple[float, float, float, float, float]:
    """Return (vth, mu0, ss_mv, theta1, theta2) for a good / weak / dead device.

    Vth stays negative (depletion-mode n-type IGZO) and within the default
    seeded vth_min/vth_max criteria (+-2.0 V, see shared/db.py) so "good"
    devices pass on vth and only "weak"/"dead" devices fail (on mobility, as
    intended). mu0 in cm^2/Vs; theta1 (1/V) and theta2 (1/V^2) are the
    linear and quadratic mobility-degradation coefficients -- theta2 is what
    makes gm peak then decline (see _mu_eff docstring).
    """
    roll = rng.random()
    if roll < 0.70:        # good
        return (rng.uniform(-1.8, -0.3), rng.uniform(10.0, 16.0),
                rng.uniform(90, 170), rng.uniform(0.05, 0.15), rng.uniform(0.015, 0.03))
    if roll < 0.90:        # weak (low mobility -> fails the mobility criterion)
        return (rng.uniform(-1.5, 1.0), rng.uniform(0.3, 0.9),
                rng.uniform(300, 650), rng.uniform(0.05, 0.2), rng.uniform(0.015, 0.03))
    return (rng.uniform(-1.5, 1.5), rng.uniform(0.002, 0.02),
            rng.uniform(700, 1200), rng.uniform(0.05, 0.2), rng.uniform(0.015, 0.03))  # dead


def _name_seed(name: str) -> int:
    """Stable per-name seed (str hash() is randomized per-process; this isn't)."""
    return zlib.crc32(name.encode("utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Make an artificial wafer of I-V files.")
    ap.add_argument("base", nargs="?", default=str(DEFAULT_BASE),
                    help="Base folder (wafer folder is created inside).")
    ap.add_argument("--name", default=DEFAULT_WAFER_NAME,
                    help="Wafer name; becomes the folder name and DB wafer_id "
                         "(default: %(default)r). Use a distinct name (e.g. "
                         "'... V2') for a second wafer so filenames don't "
                         "collide with one already in the database.")
    ap.add_argument("--per-die", type=int, default=8,
                    help="Transistors measured per die (default 8; max 64).")
    ap.add_argument("--die-coverage", type=float, default=0.85,
                    help="Fraction of dies that have data (default 0.85).")
    ap.add_argument("--seed", type=int, default=None,
                    help="RNG seed (default: derived from --name, so each "
                         "named wafer is reproducible but distinct).")
    args = ap.parse_args()

    name_hash = _name_seed(args.name)
    out = Path(args.base) / args.name
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(args.seed if args.seed is not None else name_hash)
    per_die = max(2, min(args.per_die, TR_COLS * TR_ROWS))

    # Corner dies forced present so the map auto-sizes to the full 5x8 grid.
    forced = {(1, 1), (DIE_COLS, 1), (1, DIE_ROWS), (DIE_COLS, DIE_ROWS)}
    # Each name gets its own run-number block (10000 wide, ample for any
    # per_die/die_coverage combination) so source filenames never collide
    # with a differently-named wafer already ingested into the database.
    run = 1000 + (name_hash % 500) * 10000
    n = 0
    for dc in range(1, DIE_COLS + 1):
        for dr in range(1, DIE_ROWS + 1):
            if (dc, dr) not in forced and rng.random() > args.die_coverage:
                continue
            material = MATERIALS[(dc + dr) % len(MATERIALS)]
            # Always include transistor corners (1,1) & (8,8) → 8x8 extent.
            cells = {(1, 1), (TR_COLS, TR_ROWS)}
            while len(cells) < per_die:
                cells.add((int(rng.integers(1, TR_COLS + 1)),
                           int(rng.integers(1, TR_ROWS + 1))))
            for (tc, tr) in sorted(cells):
                vth, mu0, ss, theta1, theta2 = device_params(rng)
                stem = f"-200C-C{dc}R{dr}-c{tc}r{tr}_L5W10-ch3_{material}-200C.xlsx"
                write_file(out / f"R{run}-IdVg{stem}", run,
                           transfer_curve(vth, mu0, ss, theta1, theta2, rng))
                write_file(out / f"R{run + 1}-IdVd{stem}", run + 1,
                           output_curve(vth, mu0, theta1, theta2, rng))
                run += 2
                n += 1

    print(f"Created {n} transistors ({n * 2} .xlsx files) in:\n  {out}")
    print(f"(~{per_die}/die over a {DIE_COLS}x{DIE_ROWS} die grid, 8x8 cells per die.)")
    print("Note: ingesting many files takes a while; use --per-die to scale.\n")
    print("How to import:")
    print("  Yield Analyzer ▸ Wafer Map ▸ 'Load wafer folder…' → pick this folder.")
    print("    (folder name = wafer id; Id-Vg features auto-computed & saved.)")
    print("  Then Measurement Viewer ▸ Database / Measurements tabs (F5 to refresh).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
