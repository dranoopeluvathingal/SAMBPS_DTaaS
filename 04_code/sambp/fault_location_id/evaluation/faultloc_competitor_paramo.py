"""
faultloc_competitor_paramo.py
==============================

WP4.5 Competitor 1 of 4: Paramo, Bretas & Meyn 2023 ISGT
eigenvalue HIF method, EXTENDED to a single-ended location
estimator for the head-to-head benchmark.

Original method (Paramo 2023)
------------------------------

Paramo, G., Bretas, A.S., Meyn, S., "Eigenvalue-based
high-impedance fault DETECTION at low PMU sampling rates",
*IEEE PES ISGT 2023*.  The published method only DETECTS faults
(binary classifier); it does not estimate location.  The detection
score is the dominant eigenvalue magnitude of the time-windowed
sample-covariance matrix of the post-fault PMU residuals; faults
are detected when this eigenvalue rises above a threshold.

Extension to a location estimator (this module)
-----------------------------------------------

Per the WP4.5 brief, the eigenvalue-magnitude detection statistic
is extended to a LOCATION estimator by treating the dominant
eigenvalue magnitude as a function of the candidate fault
location ``alpha`` along the feeder.  We sweep ``alpha`` on a
coarse grid, build the residual-covariance matrix at each
candidate from a small Monte-Carlo perturbation of R_x, compute
its dominant eigenvalue, and pick the ``alpha_hat`` that
MAXIMISES the eigenvalue (the candidate at which the post-fault
residual signature is most cleanly aligned with the dominant
subspace).  ``R_x`` is then obtained from the fundamental-
frequency admittance at ``alpha_hat`` via a one-shot algebraic
step.

THIS EXTENSION IS DOCUMENTED HERE FOR FAIR-COMPARISON
TRANSPARENCY.  The Paramo et al. method as published does not
provide a location estimate; the extension was authored at WP4.5
brief time and reviewed by the PI (see
``docs/competitor_blind_review.md``).

API
---

Single entry point ``estimate(v, i, fs, network) -> {alpha, Rx,
cpu_ms}``.  ``network`` is expected to provide a callable
``forward(alpha, Rx) -> H`` (single-bin admittance) for the
inner-loop residual computation; the runner injects a wrapper
around the WP2.4 single-bin DFT optimiser's forward model.
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
    """Paramo-2023 (extended) eigenvalue-based location estimator."""
    t0 = time.perf_counter()
    f0 = getattr(network, "f0", 50.0)
    H_meas = H_meas_from_waveforms(v, i, fs=fs, f0=f0)

    alpha_grid = np.linspace(0.02, 0.98, 41)
    Rx_grid = np.geomspace(50.0, 5000.0, 9)
    eig_max = -np.inf
    alpha_hat = 0.5
    Rx_hat = 1000.0
    for alpha in alpha_grid:
        residuals = []
        for Rx in Rx_grid:
            try:
                H_model = network.forward(alpha, Rx)
                e = H_meas - H_model
                residuals.append([float(np.real(e)), float(np.imag(e))])
            except Exception:
                residuals.append([0.0, 0.0])
        R = np.array(residuals)
        C = np.cov(R.T)
        if not np.all(np.isfinite(C)):
            continue
        evals = np.linalg.eigvalsh(C)
        dom = float(np.max(np.abs(evals)))
        if dom > eig_max:
            eig_max = dom
            alpha_hat = float(alpha)
    best_rx_err = np.inf
    for Rx in np.geomspace(20.0, 10000.0, 25):
        try:
            H_model = network.forward(alpha_hat, Rx)
            err = abs(H_meas - H_model)
            if err < best_rx_err:
                best_rx_err = err
                Rx_hat = float(Rx)
        except Exception:
            continue
    cpu_ms = 1000.0 * (time.perf_counter() - t0)
    return {"alpha": alpha_hat, "Rx": Rx_hat, "cpu_ms": cpu_ms}
