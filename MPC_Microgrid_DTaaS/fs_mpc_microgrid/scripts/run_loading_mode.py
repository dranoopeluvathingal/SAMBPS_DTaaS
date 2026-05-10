"""First-light reproduction of [F] Fig. 4 (loading mode with non-linear load).

Usage:
    python scripts/run_loading_mode.py
    -> figures/loading_mode.png
    -> prints THD of i_s (post-control) and i_l (load).
"""

from __future__ import annotations

from pathlib import Path
import numpy as np
import matplotlib

matplotlib.use("Agg")  # headless-safe
import matplotlib.pyplot as plt

from fs_mpc_mg.scenarios import loading_mode


# ---------------------------------------------------------------------------
def thd(signal: np.ndarray, fs: float, f_fund: float, n_harmonics: int = 50) -> float:
    """Crude THD estimator on a single-phase time series.

    Returns the fraction (NOT percent): e.g. 0.05 means 5% THD.
    """
    N = len(signal)
    # window the tail (steady state) — last 5 cycles
    n_keep = int(5.0 * fs / f_fund)
    n_keep = min(n_keep, N)
    sig = signal[-n_keep:] - np.mean(signal[-n_keep:])

    # FFT
    spectrum = np.abs(np.fft.rfft(sig))
    freqs = np.fft.rfftfreq(len(sig), 1.0 / fs)

    def amp_at(f: float) -> float:
        idx = int(round(f * len(sig) / fs))
        if 0 <= idx < len(spectrum):
            return spectrum[idx]
        return 0.0

    fund = amp_at(f_fund)
    if fund < 1e-9:
        return float("nan")

    harm_sq = 0.0
    for k in range(2, n_harmonics + 1):
        harm_sq += amp_at(k * f_fund) ** 2
    return float(np.sqrt(harm_sq) / fund)


# ---------------------------------------------------------------------------
def main() -> None:
    out_dir = Path(__file__).resolve().parent.parent / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)

    sim = loading_mode(i_dc_load_amp=80.0)
    res = sim.run(t_end=80e-3)  # 80 ms = 4 cycles at 50 Hz
    fs = 1.0 / sim.inner.p.T_s

    # -----------------------------------------------------------------
    # THD (phase a)
    thd_is = thd(res.i_s[:, 0], fs=fs, f_fund=res.f_grid)
    thd_il = thd(res.i_l[:, 0], fs=fs, f_fund=res.f_grid)
    print(f"THD i_s (phase a) = {100 * thd_is:5.2f} %")
    print(f"THD i_l (phase a) = {100 * thd_il:5.2f} %  (load reference)")
    print(f"v_dc final        = {res.v_dc[-1]:7.2f} V (target 900 V)")

    # -----------------------------------------------------------------
    # Plot
    fig, axes = plt.subplots(4, 1, figsize=(9, 9), sharex=True)

    ax = axes[0]
    ax.plot(res.t * 1e3, res.v_s[:, 0], label="v_s,a", color="C0", linewidth=0.8)
    ax.set_ylabel("Grid voltage (V)")
    ax.legend(loc="upper right")
    ax.grid(alpha=0.3)

    ax = axes[1]
    ax.plot(res.t * 1e3, res.i_s[:, 0], label="i_s,a (PCC)", color="C2", linewidth=0.8)
    ax.set_ylabel("System current (A)")
    ax.legend(loc="upper right")
    ax.grid(alpha=0.3)
    ax.text(
        0.02, 0.95, f"THD i_s = {100 * thd_is:.2f}%", transform=ax.transAxes,
        verticalalignment="top", fontsize=9, color="C2",
    )

    ax = axes[2]
    ax.plot(res.t * 1e3, res.i_m[:, 0], label="i_m,a (converter)", color="C3", linewidth=0.8)
    ax.plot(res.t * 1e3, res.i_l[:, 0], label="i_l,a (load)", color="C1", linewidth=0.8, alpha=0.7)
    ax.set_ylabel("Currents (A)")
    ax.legend(loc="upper right")
    ax.grid(alpha=0.3)

    ax = axes[3]
    ax.plot(res.t * 1e3, res.v_dc, label="v_dc", color="C4", linewidth=1.0)
    ax.axhline(900.0, color="k", linestyle="--", alpha=0.5, label="v_dc_ref")
    ax.set_ylabel("DC-link voltage (V)")
    ax.set_xlabel("time (ms)")
    ax.legend(loc="lower right")
    ax.grid(alpha=0.3)

    fig.suptitle("FS-MPC reproduction of Perez 2016 Fig. 4 — loading mode (i_dc < 0)")
    fig.tight_layout()

    out_file = out_dir / "loading_mode.png"
    fig.savefig(out_file, dpi=140)
    print(f"Saved: {out_file}")


if __name__ == "__main__":
    main()
