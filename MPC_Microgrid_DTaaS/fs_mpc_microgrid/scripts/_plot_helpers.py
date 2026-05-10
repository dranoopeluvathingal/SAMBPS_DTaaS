"""Shared plotting and THD helpers for the reproduction scripts."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def thd(signal: np.ndarray, fs: float, f_fund: float, n_harmonics: int = 50) -> float:
    """THD as a fraction (e.g. 0.05 = 5%) on a single-phase steady-state tail."""
    N = len(signal)
    n_keep = min(int(5.0 * fs / f_fund), N)
    sig = signal[-n_keep:] - np.mean(signal[-n_keep:])
    spectrum = np.abs(np.fft.rfft(sig))

    def amp(f: float) -> float:
        idx = int(round(f * len(sig) / fs))
        return spectrum[idx] if 0 <= idx < len(spectrum) else 0.0

    fund = amp(f_fund)
    if fund < 1e-9:
        return float("nan")
    harm_sq = sum(amp(k * f_fund) ** 2 for k in range(2, n_harmonics + 1))
    return float(np.sqrt(harm_sq) / fund)


def plot_4panel(res, title: str, out_path: Path) -> dict[str, float]:
    """Render the standard 4-panel figure and save. Returns metrics dict."""
    fs = 1.0 / (res.t[1] - res.t[0])
    metrics = {
        "thd_is": thd(res.i_s[:, 0], fs=fs, f_fund=res.f_grid),
        "thd_il": thd(res.i_l[:, 0], fs=fs, f_fund=res.f_grid),
        "v_dc_final": float(res.v_dc[-1]),
    }

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
        0.02, 0.95, f"THD i_s = {100 * metrics['thd_is']:.2f}%",
        transform=ax.transAxes, va="top", fontsize=9, color="C2",
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

    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    plt.close(fig)

    return metrics
