"""faultloc_two_stage_optimiser.py
====================================
Two-stage joint estimator of (alpha, R_x) from a single-frequency
admittance observation ``H_meas``.  Mirrors ``matlab/faultloc_optimiser.m``
algorithmically:

  Stage 1 - n_alpha x n_Rx grid + top-`n_seeds` multi-start
  Stage 2 - gradient descent with central FD + Armijo line-search,
            box constraints, max-iter cap

Forward model is the Cascaded-Gamma 2-section state-space from
``models.faultloc_pi_section_model.H_model`` (P0.5 Appendix A).

Numerical-equivalence claim
---------------------------
The Python and MATLAB versions implement the same algorithm with the
same defaults and use the same forward-model construction; given the
same ``H_meas`` they should agree to machine precision.  Runtime
verification of the "1e-9 on a 5-case smoke" claim is gated on a
licensed MATLAB run (see WP0.4 / WP1.4 changelog).

WP-trace
--------
* WP1.4   This module replaces the docstring-only stub from S1.
* WP2.4   Phase-2 swaps central-FD gradient for the closed-form
          analytical gradient (``inverse_estimation/faultloc_analytical_gradients``).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
from sambp_fault_location_id.models.faultloc_pi_section_model import H_model

# Defaults match matlab/faultloc_optimiser.m
DEFAULT_OPTS = {
    "n_alpha": 100,
    "n_Rx": 50,
    "n_seeds": 3,
    "h_alpha": 1.0e-4,
    "h_Rx": 1.0e-1,
    "beta": 0.5,
    "c1": 1.0e-4,
    "max_iter": 2000,
    "tol_J": 1.0e-18,
    "bounds": (0.05, 0.95, 100.0, 5000.0),
    "f0": 50.0,
}


@dataclass(frozen=True)
class EstimateInfo:
    J_min: float
    n_iters: int
    cpu_time_s: float
    stage1_J0: float


def _cost(theta, H_meas: complex, omega0: float) -> float:
    H = H_model(float(theta[0]), float(theta[1]), omega0)
    e = H_meas - H
    return e.real * e.real + e.imag * e.imag


def _armijo(fun, x, p, J0, grad, *, beta: float, c1: float, max_iter: int = 30):
    g_dot_p = float(np.dot(grad, p))
    if g_dot_p >= 0:
        return None  # not a descent direction
    step = 1.0
    for _ in range(max_iter):
        if fun(x + step * p) <= J0 + c1 * step * g_dot_p:
            return step
        step *= beta
    return None


def _grad_descent(
    cost,
    theta,
    lo: np.ndarray,
    hi: np.ndarray,
    *,
    h_a: float,
    h_R: float,
    beta: float,
    c1: float,
    max_iter: int,
    tol_J: float,
):
    J_at = cost(theta)
    n_it = 0
    for k in range(1, max_iter + 1):
        n_it = k
        if J_at < tol_J:
            break
        ea = np.array([h_a, 0.0])
        eR = np.array([0.0, h_R])
        Ja_p = cost(theta + ea)
        Ja_m = cost(theta - ea)
        JR_p = cost(theta + eR)
        JR_m = cost(theta - eR)
        g = np.array(
            [(Ja_p - Ja_m) / (2 * h_a), (JR_p - JR_m) / (2 * h_R)]
        )
        d2a = (Ja_p - 2 * J_at + Ja_m) / (h_a * h_a)
        d2R = (JR_p - 2 * J_at + JR_m) / (h_R * h_R)
        if d2a > 0 and d2R > 0:
            p = -g / np.array([d2a, d2R])
            if float(np.dot(g, p)) >= 0:
                p = -g
        else:
            p = -g
        step = _armijo(cost, theta, p, J_at, g, beta=beta, c1=c1)
        if step is None:
            break
        theta_new = np.minimum(np.maximum(theta + step * p, lo), hi)
        J_new = cost(theta_new)
        if J_new >= J_at:
            break
        theta, J_at = theta_new, J_new
    return theta, J_at, n_it


def estimate_alpha_Rx(
    H_meas: complex,
    *,
    opts: dict | None = None,
) -> tuple[np.ndarray, EstimateInfo]:
    """Two-stage joint estimator.

    Returns (theta_hat = [alpha_hat, Rx_hat], info).
    """
    o = {**DEFAULT_OPTS, **(opts or {})}
    omega0 = 2.0 * np.pi * o["f0"]
    a_lo, a_hi, R_lo, R_hi = o["bounds"]
    lo = np.array([a_lo, R_lo])
    hi = np.array([a_hi, R_hi])

    def cost(theta):
        return _cost(theta, H_meas, omega0)

    t0 = time.perf_counter()

    # ---- Stage 1: coarse grid -------------------------------------------
    aa = np.linspace(a_lo, a_hi, o["n_alpha"])
    RR = np.linspace(R_lo, R_hi, o["n_Rx"])
    Jgrid = np.empty((o["n_alpha"], o["n_Rx"]))
    for i, a in enumerate(aa):
        for j, R in enumerate(RR):
            Jgrid[i, j] = cost([a, R])

    flat = Jgrid.ravel()
    # Top-N seeds by ascending cost
    n_seeds = int(o["n_seeds"])
    seed_idx_unord = np.argpartition(flat, n_seeds - 1)[:n_seeds]
    seed_idx = seed_idx_unord[np.argsort(flat[seed_idx_unord])]
    seeds = []
    for idx in seed_idx:
        i, j = np.unravel_index(int(idx), Jgrid.shape)
        seeds.append(np.array([aa[i], RR[j]]))

    # ---- Stage 2: gradient descent on each seed -------------------------
    best_J = np.inf
    best_theta = seeds[0]
    best_n_iters = 0
    for theta0 in seeds:
        theta, J, n_it = _grad_descent(
            cost,
            theta0.copy(),
            lo,
            hi,
            h_a=o["h_alpha"],
            h_R=o["h_Rx"],
            beta=o["beta"],
            c1=o["c1"],
            max_iter=o["max_iter"],
            tol_J=o["tol_J"],
        )
        if J < best_J:
            best_J = float(J)
            best_theta = theta
            best_n_iters = n_it

    info = EstimateInfo(
        J_min=best_J,
        n_iters=best_n_iters,
        cpu_time_s=time.perf_counter() - t0,
        stage1_J0=float(flat[seed_idx[0]]),
    )
    return best_theta, info


def single_bin_dft(x: np.ndarray, fs: float, f0: float) -> complex:
    """One-cycle single-bin DFT of x at frequency f0."""
    Ns = len(x)
    n = np.arange(Ns)
    k = int(round(f0 * Ns / fs))
    return complex((2.0 / Ns) * np.sum(x * np.exp(-1j * 2 * np.pi * k * n / Ns)))


def H_meas_from_waveforms(
    v: np.ndarray, i: np.ndarray, fs: float = 10000.0, f0: float = 50.0
) -> complex:
    """Compute the single-bin admittance H_meas = I_bin / V_bin."""
    Vp = single_bin_dft(v, fs, f0)
    Ip = single_bin_dft(i, fs, f0)
    return Ip / Vp
