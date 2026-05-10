"""Reproduces [F] Fig. 5 (regenerating mode: i_dc > 0).

Microgrid injects 100 A into the DC link; the converter sources fundamental
power into the AC grid (180° from v_s) while still absorbing the non-linear
load harmonics. PCC current i_s should remain near-sinusoidal.

Run:
    python scripts/run_regenerating_mode.py
    -> figures/regenerating_mode.png
"""

from __future__ import annotations

from pathlib import Path
import sys

# Ensure the script can find sibling helpers when run as a file.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _plot_helpers import plot_4panel

from fs_mpc_mg.scenarios import regenerating_mode


def main() -> None:
    out_dir = Path(__file__).resolve().parent.parent / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)

    sim = regenerating_mode(i_dc_inject_amp=100.0)
    res = sim.run(t_end=80e-3)  # 4 cycles

    metrics = plot_4panel(
        res,
        title="FS-MPC reproduction of Perez 2016 Fig. 5 — regenerating mode (i_dc > 0)",
        out_path=out_dir / "regenerating_mode.png",
    )

    print(f"THD i_s (phase a) = {100 * metrics['thd_is']:5.2f} %")
    print(f"THD i_l (phase a) = {100 * metrics['thd_il']:5.2f} %")
    print(f"v_dc final        = {metrics['v_dc_final']:7.2f} V (target 900 V)")
    print(f"Saved: {out_dir / 'regenerating_mode.png'}")


if __name__ == "__main__":
    main()
