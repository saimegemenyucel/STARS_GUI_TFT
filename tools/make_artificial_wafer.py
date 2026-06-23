"""Generate an artificial 'Artificial Data Wafer' folder of example I-V files.

Creates one wafer folder of Id-Vg (transfer) and Id-Vd (output) .xlsx files for
transistors spread over a 5x8 die grid with up to 8x8 transistors per die,
following the lab's filename convention and sheet structure. Curves use a
smooth (softplus) square-law model so the app's √Id extraction recovers the
intended Vth / mobility. A realistic mix of good / weak / dead devices is
included so the wafer map shows pass (green) and fail (red) cells.

Run on a machine with pandas + openpyxl installed::

    python tools/make_artificial_wafer.py                 # default density
    python tools/make_artificial_wafer.py --per-die 16    # denser
    python tools/make_artificial_wafer.py "C:/path/Wafers"

Then import it (see the reminder printed at the end).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

DEFAULT_BASE = Path(r"C:\Users\suuser\Desktop\egemen\April AI HUB\Wafers")
WAFER_NAME = "Artificial Data Wafer"

EPS0_F_PER_CM = 8.8541878128e-14
TOX_NM, EPS_R = 25.0, 8.0
COX = EPS0_F_PER_CM * EPS_R / (TOX_NM * 1e-7)     # F/cm^2 (AlOx 25 nm)
W_UM, L_UM = 10.0, 5.0
W_CM, L_CM = W_UM * 1e-4, L_UM * 1e-4
VD_TRANSFER = -5.0
VT_THERMAL = 0.02585                              # kT/q at ~300 K
LN10 = np.log(10.0)
I_FLOOR = 1e-13                                   # off-state leakage floor (A)

DIE_COLS, DIE_ROWS = 5, 8                         # wafer = 5 cols x 8 rows of dies
TR_COLS, TR_ROWS = 8, 8                           # up to 8x8 transistors per die
MATERIALS = ["TiPt", "Pt", "W", "TaPt", "MoPt", "AuPt"]


def _softplus(z: np.ndarray) -> np.ndarray:
    """Numerically stable softplus: log(1+exp(z))."""
    return np.maximum(z, 0.0) + np.log1p(np.exp(-np.abs(z)))


def transfer_curve(vth: float, mu: float, ss_mv: float, rng) -> pd.DataFrame:
    """Id-Vg sheet from a smooth square-law model (recovers vth & mu cleanly)."""
    vg = np.round(np.linspace(-5, 5, 41), 4)      # finer sweep → better SS/Vth
    k = 0.5 * (W_CM / L_CM) * mu * COX            # saturation prefactor
    n = (ss_mv / 1000.0) / (VT_THERMAL * LN10)    # ideality from desired SS
    nvt = max(n * VT_THERMAL, 1e-3)
    vov = nvt * _softplus((vg - vth) / nvt)       # smooth overdrive (≥0)
    idd = k * vov ** 2 + I_FLOOR
    idd = np.clip(idd * (1 + rng.normal(0, 0.015, vg.size)), I_FLOOR, None)
    return pd.DataFrame({
        "DrainI": -idd, "DrainV": np.full(vg.size, VD_TRANSFER),
        "GateI": rng.normal(0, 1e-12, vg.size), "GateV": vg,
    })


def _idvd(vd: np.ndarray, vov: float, mu: float) -> np.ndarray:
    """MOSFET-like output current vs drain voltage at a fixed overdrive."""
    if vov <= 0:
        return np.zeros_like(vd)
    k = (W_CM / L_CM) * mu * COX
    a = np.abs(vd)
    mag = np.where(a < vov, k * (vov * a - a ** 2 / 2.0), k * 0.5 * vov ** 2)
    return np.sign(vd) * mag


def output_curve(vth: float, mu: float, rng) -> pd.DataFrame:
    """Id-Vd sheet with three bias groups at Vg = -5, 0, +5 V."""
    vd = np.round(np.linspace(-5, 5, 51), 4)
    cols: dict[str, np.ndarray] = {}
    for i, vg in enumerate((-5.0, 0.0, 5.0), start=1):
        idd = _idvd(vd, vg - vth, mu) * (1 + rng.normal(0, 0.02, vd.size))
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


def device_params(rng) -> tuple[float, float, float]:
    """Return (vth, mu, ss_mv) for a good / weak / dead device."""
    roll = rng.random()
    if roll < 0.70:        # good
        return rng.uniform(-2.0, 1.0), rng.uniform(8.0, 22.0), rng.uniform(90, 170)
    if roll < 0.90:        # weak (low mobility -> fails the mobility criterion)
        return rng.uniform(-1.0, 2.0), rng.uniform(0.3, 0.9), rng.uniform(300, 650)
    return rng.uniform(-1.0, 3.0), rng.uniform(0.002, 0.02), rng.uniform(700, 1200)  # dead


def main() -> int:
    ap = argparse.ArgumentParser(description="Make an artificial wafer of I-V files.")
    ap.add_argument("base", nargs="?", default=str(DEFAULT_BASE),
                    help="Base folder (wafer folder is created inside).")
    ap.add_argument("--per-die", type=int, default=8,
                    help="Transistors measured per die (default 8; max 64).")
    ap.add_argument("--die-coverage", type=float, default=0.85,
                    help="Fraction of dies that have data (default 0.85).")
    args = ap.parse_args()

    out = Path(args.base) / WAFER_NAME
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(7)
    per_die = max(2, min(args.per_die, TR_COLS * TR_ROWS))

    # Corner dies forced present so the map auto-sizes to the full 5x8 grid.
    forced = {(1, 1), (DIE_COLS, 1), (1, DIE_ROWS), (DIE_COLS, DIE_ROWS)}
    run, n = 1000, 0
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
                vth, mu, ss = device_params(rng)
                stem = f"-200C-C{dc}R{dr}-c{tc}r{tr}_L5W10-ch3_{material}-200C.xlsx"
                write_file(out / f"R{run}-IdVg{stem}", run,
                           transfer_curve(vth, mu, ss, rng))
                write_file(out / f"R{run + 1}-IdVd{stem}", run + 1,
                           output_curve(vth, mu, rng))
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
