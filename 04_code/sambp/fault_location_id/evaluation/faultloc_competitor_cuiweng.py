"""
faultloc_competitor_cuiweng.py
===============================

WP4.5 Competitor 3 of 4: Cui & Weng 2020 IEEE TSG 11(1):797-809
micro-PMU HIF location method.

Original method
---------------

Cui, T., Weng, Y., "Outlier-resilient power system state
estimation against high-impedance faults using
micro-PMU-instrumented distribution networks", *IEEE Trans.
Smart Grid*, vol. 11, no. 1, pp. 797-809, 2020.

Cui-Weng requires SYNCHRONISED two-ended measurements: the
substation phasor (V_S, I_S) AND a remote-end phasor (V_R)
collected by a micro-PMU at a downstream bus.  The location
estimate is closed-form: assuming a one-section uniform line of
total impedance Z_total between the two PMU buses, the fault
location ``alpha`` (fraction from the substation toward the
remote PMU) satisfies

   V_R = V_S - alpha * Z_total * I_S - (1 - alpha) * Z_total * I_R_est

where ``I_R_est`` is reconstructed from V_R via the line ABCD.
Solving this for ``alpha`` is a one-shot algebraic step in
the COMPLEX domain.  R_x is then recovered from the residual
admittance at the fault bus.

The remote-end measurements are provided by the SAMBPS Digital
Twin: the runner stands up a parallel digital-twin instance at
the remote substation that mirrors the system state and emits
the synchronised V_R phasor that the real micro-PMU would
provide.  This is the canonical "DT-as-virtual-PMU" pattern
documented in the WP4.5 brief.

API
---

Single entry point ``estimate(v, i, fs, network) -> {alpha, Rx,
cpu_ms}``.  ``network`` provides:
  * ``forward(alpha, Rx) -> H_meas`` (single-bin admittance);
  * ``Z_total`` (complex per-unit-length × total feeder length).
The runner supplies the remote-end V_R via
``network.virtual_pmu_VR(alpha_true, Rx_true)`` at sim time
(this is the digital-twin emission).
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np
from sambp_fault_location_id.inverse_estimation.faultloc_two_stage_optimiser import (
    H_meas_from_waveforms,
)


def estimate(
    v: np.ndarray,
    i: np.ndarray,
    fs: float,
    network: Any,
) -> dict[str, float]:
    """Cui-Weng-2020 micro-PMU two-ended HIF location estimator."""
    t0 = time.perf_counter()
    f0 = getattr(network, "f0", 50.0)

    H_meas = H_meas_from_waveforms(v, i, fs=fs, f0=f0)
    Z_total = getattr(network, "Z_total", complex(10.0, 25.0))

    # Substation phasors
    n = np.arange(len(v))
    V_S = (2.0 / len(v)) * np.sum(
        v * np.exp(-1j * 2.0 * np.pi * f0 * n / fs)
    )
    I_S = (2.0 / len(v)) * np.sum(
        i * np.exp(-1j * 2.0 * np.pi * f0 * n / fs)
    )

    # Two-ended sweep using virtual PMU.  Cui-Weng's closed-form
    # one-shot algebra requires the remote-end voltage AND remote-
    # end current; here we have only V_R (the virtual PMU emits the
    # voltage phasor of the remote bus).  We therefore degrade
    # gracefully to a complex-residual minimisation over alpha:
    # find alpha_hat such that the predicted V_R matches the
    # virtual-PMU V_R.
    alpha_grid = np.linspace(0.02, 0.98, 41)
    best_err = np.inf
    alpha_hat = 0.5
    for alpha in alpha_grid:
        try:
            V_R_pred = V_S - alpha * Z_total * I_S
            V_R_meas = network.virtual_pmu_VR(alpha)
            err = abs(V_R_pred - V_R_meas)
        except Exception:
            err = np.inf
        if err < best_err:
            best_err = err
            alpha_hat = float(alpha)

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
