"""Reproduces [F] Fig. 6 (zero-consumption / STATCOM mode: i_dc = 0).

The microgrid neither sources nor sinks bulk power. The converter behaves
as a pure active filter — i_m carries only reactive + harmonic components
and i_s ≈ fundamental load current. Validates the limit-case behaviour.

Run:
    python scripts/run_statcom_mode.py
    -> figures/statcom_mode.png
"""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _plot_helpers import plot_4panel

from fs_mpc_mg.scenarios import statcom_mode


def main() -> None:
    out_dir = Path(__file__).resolve().parent.parent / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)

    sim = statcom_mode()
    res = sim.run(t_end=80e-3)

    metrics = plot_4panel(
        res,
        title="FS-MPC reproduction of Perez 2016 Fig. 6 — STATCOM mode (i_dc = 0)",
        out_path=out_dir / "statcom_mode.png",
    )

    print(f"THD i_s (phase a) = {100 * metrics['thd_is']:5.2f} %")
    print(f"THD i_l (phase a) = {100 * metrics['thd_il']:5.2f} %")
    print(f"v_dc final        = {metrics['v_dc_final']:7.2f} V (target 900 V)")
    print(f"Saved: {out_dir / 'statcom_mode.png'}")


if __name__ == "__main__":
    main()
