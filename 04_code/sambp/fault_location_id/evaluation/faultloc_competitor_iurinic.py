"""
faultloc_competitor_iurinic.py
===============================

WP4.5 Competitor 2 of 4: Iurinic, Orozco-Henao, Ferraz & Bretas
2018 IJEPES + Orozco-Henao 2020 EPSR S0378779620303813
spectral-domain HIF location method.

Original method
---------------

* Iurinic, J.O., Orozco-Henao, C., Ferraz, R.G., Bretas, A.S.,
  "High-impedance fault location: a stochastic estimation
  approach", *Int. Journal of Electrical Power & Energy Systems*,
  vol. 100, pp. 268-279, 2018.
* Orozco-Henao, C. et al., "Practical high-impedance fault
  location methodology for distribution systems", *Electric Power
  Systems Research*, vol. 188, p. 106560, 2020 (S0378779620303813).

The combined method exploits the fact that HIF arc currents carry
significant ODD-HARMONIC content (3rd, 5th, 7th).  The published
algorithm:

  1. Compute fundamental phasor (V_1, I_1) and 3rd-harmonic
     phasor (V_3, I_3) at the substation.
  2. Solve a sequential algebraic system for ``alpha``: the
     ratio of fundamental-to-3rd-harmonic admittance is a
     monotone function of fault location along the feeder
     (because the line series impedance per unit length is
     approximately frequency-flat over 50-150 Hz so the
     admittance ratio depends primarily on alpha).
  3. Given ``alpha_hat``, recover R_f from the fundamental
     residual: R_f = Re(V_1/I_1) - alpha_hat * Z_line_total.

API
---

Single entry point ``estimate(v, i, fs, network) -> {alpha, Rx,
cpu_ms}``.  ``network`` provides ``forward(alpha, Rx, harmonic) ->
H`` (single-bin admittance at the chosen harmonic of f0).
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np


def _bin_phasor(x: np.ndarray, fs: float, f: float) -> complex:
    """Single-bin DFT phasor at frequency f (Hz)."""
    n = np.arange(len(x))
    return (2.0 / len(x)) * np.sum(x * np.exp(-1j * 2.0 * np.pi * f * n / fs))


def estimate(
    v: np.ndarray,
    i: np.ndarray,
    fs: float,
    network: Any,
) -> dict[str, float]:
    """Iurinic-2018 + Orozco-Henao-2020 spectral location estimator."""
    t0 = time.perf_counter()
    f0 = getattr(network, "f0", 50.0)

    V1 = _bin_phasor(v, fs, f0)
    I1 = _bin_phasor(i, fs, f0)
    V3 = _bin_phasor(v, fs, 3.0 * f0)
    I3 = _bin_phasor(i, fs, 3.0 * f0)

    H1_meas = I1 / V1 if abs(V1) > 1e-12 else complex(0.0, 0.0)
    # 3rd-harmonic admittance: handle the case where V3 is essentially
    # zero (clean voltage), in which case use the harmonic CURRENT
    # magnitude as the spectral signature instead.
    if abs(V3) > 1e-3:
        H3_meas = I3 / V3
        ratio_meas = H1_meas / H3_meas if abs(H3_meas) > 1e-12 else complex(0.0, 0.0)
    else:
        # Voltage is too clean to give a 3rd-harmonic admittance.
        # Fall back to using the |I3| / |I1| ratio as the spectral
        # signature -- the canonical Orozco-Henao 2020 §III.B branch
        # for the "stiff source" case.
        ratio_meas = abs(I3) / max(abs(I1), 1e-12) + 0j

    alpha_grid = np.linspace(0.02, 0.98, 49)
    best_err = np.inf
    alpha_hat = 0.5
    for alpha in alpha_grid:
        try:
            H1_model = network.forward(alpha, 1000.0, 1)
            H3_model = network.forward(alpha, 1000.0, 3)
            if abs(V3) > 1e-3 and abs(H3_model) > 1e-12:
                ratio_model = H1_model / H3_model
            else:
                # Spectral-current ratio (proportional to the 3rd-
                # harmonic admittance magnitude at this alpha).
                ratio_model = abs(H3_model) / max(abs(H1_model), 1e-12) + 0j
            err = abs(ratio_meas - ratio_model)
        except Exception:
            err = np.inf
        if err < best_err:
            best_err = err
            alpha_hat = float(alpha)

    Rx_hat = 1000.0
    best_rx_err = np.inf
    for Rx in np.geomspace(20.0, 10000.0, 25):
        try:
            H1_model = network.forward(alpha_hat, Rx, 1)
            err = abs(H1_meas - H1_model)
        except Exception:
            err = np.inf
        if err < best_rx_err:
            best_rx_err = err
            Rx_hat = float(Rx)

    cpu_ms = 1000.0 * (time.perf_counter() - t0)
    return {"alpha": alpha_hat, "Rx": Rx_hat, "cpu_ms": cpu_ms}
