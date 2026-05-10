"""
faultloc_competitor_zeng.py
============================

WP4.5 Competitor 4 of 4: Zeng et al. 2021 EPSR S0142061521009157
damping-rate double-ended HIF detection and resistance method.

Original method
---------------

Zeng, X. et al., "Double-ended high-impedance fault detection
and resistance estimation based on damping-rate of post-fault
transients", *Electric Power Systems Research*, vol. 200,
p. 107463, 2021 (S0142061521009157).

The method exploits the post-fault transient damping rate of the
fault loop, which (for a uniform line) is monotone in the
location ``alpha``.  The damping rate is obtained from the
exponential envelope of the post-fault current transient.
Algorithm:

  1. Window the post-fault current waveform.
  2. Estimate the per-cycle envelope by Hilbert magnitude.
  3. Fit ``log envelope vs t`` over the first 2-3 cycles to
     obtain the damping coefficient ``zeta_hat``.
  4. Map ``zeta_hat`` to ``alpha_hat`` via a pre-computed
     calibration table built from the line parameters
     (lookup at runtime).
  5. R_x is recovered from the steady-state fundamental
     admittance at ``alpha_hat``.

Per the WP4.5 brief, this is a DOUBLE-ENDED method: the damping-
rate calibration assumes both substation and remote ends are
instrumented to bracket the post-fault transient.  Communications
infrastructure: requires a synchronised remote-end current
channel with µs-grade alignment.

API
---

Single entry point ``estimate(v, i, fs, network) -> {alpha, Rx,
cpu_ms}``.  ``network`` provides ``forward(alpha, Rx)`` and a
calibration table ``zeta_to_alpha`` (pre-computed from line
parameters).
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np
from sambp_fault_location_id.inverse_estimation.faultloc_two_stage_optimiser import (
    H_meas_from_waveforms,
)


def _hilbert_envelope(x: np.ndarray) -> np.ndarray:
    """Hilbert-transform-based instantaneous envelope.  Pure NumPy
    implementation -- avoid the scipy.signal dependency."""
    n = len(x)
    X = np.fft.fft(x)
    h = np.zeros(n)
    if n % 2 == 0:
        h[0] = h[n // 2] = 1.0
        h[1:n // 2] = 2.0
    else:
        h[0] = 1.0
        h[1:(n + 1) // 2] = 2.0
    z = np.fft.ifft(X * h)
    return np.abs(z)


def estimate(
    v: np.ndarray,
    i: np.ndarray,
    fs: float,
    network: Any,
) -> dict[str, float]:
    """Zeng-2021 damping-rate double-ended HIF location estimator."""
    t0 = time.perf_counter()
    f0 = getattr(network, "f0", 50.0)

    # Compute the envelope of the current waveform via Hilbert
    # transform.  Take a small log-linear fit over the post-fault
    # window to estimate the damping rate.
    env = _hilbert_envelope(np.asarray(i, dtype=float))
    env = np.maximum(env, 1e-9)
    t = np.arange(len(env)) / fs
    log_env = np.log(env)
    # Fit log_env = a - zeta * t over the first ~2 cycles.
    fit_n = min(len(env), int(round(2.0 * fs / f0)))
    if fit_n >= 4:
        slope, _ = np.polyfit(t[:fit_n], log_env[:fit_n], 1)
        zeta_hat = -float(slope)
    else:
        zeta_hat = 0.0

    # Map zeta_hat -> alpha_hat via runtime calibration.
    if hasattr(network, "zeta_to_alpha"):
        alpha_hat = float(network.zeta_to_alpha(zeta_hat))
    else:
        # Fallback: a simple monotone calibration with line params.
        # zeta(alpha) ~ R_loop / (2*L_loop) -> proportional to alpha.
        zeta_max = getattr(network, "zeta_max", 50.0)
        alpha_hat = float(np.clip(zeta_hat / max(zeta_max, 1e-9),
                                  0.02, 0.98))

    H_meas = H_meas_from_waveforms(v, i, fs=fs, f0=f0)
    Rx_hat = 1000.0
    best_rx_err = np.inf
    for Rx in np.geomspace(20.0, 10000.0, 25):
        try:
            H_model = network.forward(alpha_hat, Rx)
            err = abs(H_meas - H_model)
        except Exception:
            err = np.inf
        if err < best_rx_err:
            best_rx_err = err
            Rx_hat = float(Rx)

    cpu_ms = 1000.0 * (time.perf_counter() - t0)
    return {"alpha": alpha_hat, "Rx": Rx_hat, "cpu_ms": cpu_ms}
