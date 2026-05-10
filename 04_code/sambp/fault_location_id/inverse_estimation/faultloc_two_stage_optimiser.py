"""faultloc_two_stage_optimiser.py
====================================
Two-stage joint estimator of (alpha, R_x) from a single-frequency
admittance observation ``H_meas``.  Mirrors ``matlab/faultloc_optimiser.m``
algorithmically:

  Stage 1 - n_alpha x n_Rx grid + top-`n_seeds` multi-start
            (Phase-1 unchanged in P2.4).

  Stage 2 - gradient descent with Armijo line-search, box
            constraints, max-iter cap.  In P2.4 the central-FD
            gradient is replaced by the closed-form analytical
            gradient from
            ``inverse_estimation/faultloc_analytical_gradients.py``
            on top of the closed-form distributed-parameter forward
            model from ``models/faultloc_distributed_param_model.py``.

Modes (added by WP2.4)
----------------------
The Phase-1 baseline behaviour is preserved via three flags:

    forward_model = 'distributed'  (default; P2.1)
                  | 'cascaded_gamma' (Phase-1, P0.5)

    gradient = 'analytical'  (default; P2.2)
             | 'fd'           (Phase-1 central-FD)

    cost = 'ml'      (default; J = |dH|^2 / sigma_H^2 with sigma_H from
                      proper-ratio CRLB - constant during one Stage-2
                      pass, recomputed per call site)
         | 'euclid'  (Phase-1; J = |dH|^2)

The Phase-1 baseline is exactly reproducible by passing
``opts={'forward_model': 'cascaded_gamma', 'gradient': 'fd',
'cost': 'euclid'}`` and keeping all other defaults.

Brief defaults (WP2.4)
----------------------
    bounds:    alpha in [1e-4, 1 - 1e-4];  R_x >= 1.0  ohm
    Armijo:    beta = 0.5; c = 1e-4; t_0 = 1e-3
    Termination: |grad J| < 1e-14 OR J < 1e-20 OR 2000 iter

WP-trace
--------
* WP1.4   Initial Python port.
* P2.4    Analytical-gradient + distributed-parameter swap; ML cost.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
from sambp_fault_location_id.inverse_estimation.faultloc_analytical_gradients import (
    dH_dtheta,
)
from sambp_fault_location_id.models.faultloc_distributed_param_model import (
    H_distributed,
)
from sambp_fault_location_id.models.faultloc_pi_section_model import H_model

# Defaults reflect WP2.4 (Phase-2) behaviour
DEFAULT_OPTS = {
    "n_alpha": 100,
    "n_Rx": 50,
    "n_seeds": 3,
    "forward_model": "distributed",
    "gradient": "analytical",
    "cost": "ml",
    "h_alpha": 1.0e-4,        # FD step (only used when gradient='fd')
    "h_Rx": 1.0e-1,           # FD step
    "beta": 0.5,              # Armijo backtracking ratio
    "c1": 1.0e-4,             # Armijo sufficient-decrease constant
    "t0": 1.0e-3,             # WP2.4 brief: initial Armijo step (was 1.0)
    "max_iter": 2000,
    "tol_J": 1.0e-20,         # WP2.4 brief: J threshold (was 1e-18)
    "tol_grad": 1.0e-14,      # WP2.4 brief: |grad J| termination
    "bounds": (1.0e-4, 1.0 - 1.0e-4, 1.0, 1.0e6),  # WP2.4 brief
    "f0": 50.0,
    "snr_v_db": float("inf"),
    "snr_i_db": float("inf"),
    "v_phase": 11000.0 / np.sqrt(3.0) * np.sqrt(2.0),
    "ns_dft": 200,
}


@dataclass(frozen=True)
class EstimateInfo:
    J_min: float
    n_iters: int
    n_J_evals: int
    n_grad_evals: int
    cpu_time_s: float
    stage1_J0: float
    grad_norm_at_exit: float


# ---------------------------------------------------------------------------
# Forward model dispatch
# ---------------------------------------------------------------------------
def _H_at(forward_model: str, alpha: float, Rx: float, omega: float) -> complex:
    if forward_model == "distributed":
        return H_distributed(alpha, Rx, omega)
    if forward_model == "cascaded_gamma":
        return H_model(alpha, Rx, omega)
    raise ValueError(f"unknown forward_model {forward_model!r}")


# ---------------------------------------------------------------------------
# Cost functions
# ---------------------------------------------------------------------------
def _sigma_H_sq(H_at_theta: complex, snr_v_db: float, snr_i_db: float,
                v_phase: float, ns: int) -> float:
    """Proper-ratio variance per real/imag of H_meas (mirror of
    inverse_estimation.faultloc_crlb_proper)."""
    rms_v_clean = abs(v_phase) / np.sqrt(2.0)
    rms_i_clean = abs(H_at_theta * v_phase) / np.sqrt(2.0)
    if not np.isfinite(snr_v_db):
        sig_V_sq = 0.0
    else:
        sig_V_sq = 2.0 * (rms_v_clean ** 2 / 10 ** (snr_v_db / 10.0)) / ns
    if not np.isfinite(snr_i_db):
        sig_I_sq = 0.0
    else:
        sig_I_sq = 2.0 * (rms_i_clean ** 2 / 10 ** (snr_i_db / 10.0)) / ns
    s = (sig_I_sq + abs(H_at_theta) ** 2 * sig_V_sq) / abs(v_phase) ** 2
    # If both channels are noiseless (sigma_V = sigma_I = 0) the ML
    # cost is undefined; degenerate to the Euclidean cost (sigma_H = 1)
    # to keep J finite.  This matches the same global minimum.
    if s <= 0:
        return 1.0
    return float(s)


def _cost(theta, H_meas: complex, omega0: float, *, opts: dict) -> float:
    H = _H_at(opts["forward_model"], float(theta[0]), float(theta[1]), omega0)
    e = H_meas - H
    j_eu = e.real * e.real + e.imag * e.imag
    if opts["cost"] == "euclid":
        return j_eu
    if opts["cost"] == "ml":
        sH2 = _sigma_H_sq(
            H, opts["snr_v_db"], opts["snr_i_db"],
            opts["v_phase"], opts["ns_dft"],
        )
        return j_eu / sH2
    raise ValueError(f"unknown cost {opts['cost']!r}")


# ---------------------------------------------------------------------------
# Gradient: analytical or central-FD
# ---------------------------------------------------------------------------
def _grad_analytical(theta, H_meas: complex, omega0: float, *, opts: dict
                     ) -> tuple[np.ndarray, np.ndarray, int]:
    """Closed-form gradient + diagonal Gauss-Newton Hessian.

    Returns (grad, hess_diag, n_J_evals_used).
    For J = |dH|^2:  grad_k = -2 Re{dH^* dH/dtheta_k}
                     hess_diag_k = 2 |dH/dtheta_k|^2  (Gauss-Newton).
    For 'ml' cost both are scaled by 1/sigma_H^2.
    """
    a, R = float(theta[0]), float(theta[1])
    H = _H_at(opts["forward_model"], a, R, omega0)
    if opts["forward_model"] != "distributed":
        raise ValueError("analytical gradient requires forward_model='distributed'")
    dH_da, dH_dR = dH_dtheta(a, R, omega0)
    dH = H_meas - H
    g = -2.0 * np.array(
        [dH.real * dH_da.real + dH.imag * dH_da.imag,
         dH.real * dH_dR.real + dH.imag * dH_dR.imag],
        dtype=float,
    )
    h_diag = 2.0 * np.array(
        [abs(dH_da) ** 2, abs(dH_dR) ** 2], dtype=float,
    )
    if opts["cost"] == "ml":
        sH2 = _sigma_H_sq(
            H, opts["snr_v_db"], opts["snr_i_db"],
            opts["v_phase"], opts["ns_dft"],
        )
        g = g / sH2
        h_diag = h_diag / sH2
    return g, h_diag, 0


def _grad_fd(theta, H_meas: complex, omega0: float, *, opts: dict
             ) -> tuple[np.ndarray, np.ndarray, int]:
    """Central-FD gradient + 2nd-FD diagonal Hessian.  Phase-1 baseline."""
    h_a = opts["h_alpha"]
    h_R = opts["h_Rx"]
    J0 = _cost(theta, H_meas, omega0, opts=opts)
    Ja_p = _cost(np.array([theta[0] + h_a, theta[1]]), H_meas, omega0, opts=opts)
    Ja_m = _cost(np.array([theta[0] - h_a, theta[1]]), H_meas, omega0, opts=opts)
    JR_p = _cost(np.array([theta[0], theta[1] + h_R]), H_meas, omega0, opts=opts)
    JR_m = _cost(np.array([theta[0], theta[1] - h_R]), H_meas, omega0, opts=opts)
    g = np.array(
        [(Ja_p - Ja_m) / (2 * h_a), (JR_p - JR_m) / (2 * h_R)], dtype=float,
    )
    h_diag = np.array([
        (Ja_p - 2.0 * J0 + Ja_m) / (h_a ** 2),
        (JR_p - 2.0 * J0 + JR_m) / (h_R ** 2),
    ], dtype=float)
    return g, h_diag, 5   # 4 + 1 cost calls per gradient


def _gradient(theta, H_meas, omega0, *, opts: dict
              ) -> tuple[np.ndarray, np.ndarray, int]:
    if opts["gradient"] == "analytical":
        return _grad_analytical(theta, H_meas, omega0, opts=opts)
    if opts["gradient"] == "fd":
        return _grad_fd(theta, H_meas, omega0, opts=opts)
    raise ValueError(f"unknown gradient {opts['gradient']!r}")


# ---------------------------------------------------------------------------
# Armijo line search
# ---------------------------------------------------------------------------
def _armijo(fun, x, p, J0, grad, *, beta: float, c1: float,
            t0: float = 1.0, max_iter: int = 30):
    g_dot_p = float(np.dot(grad, p))
    if g_dot_p >= 0:
        return None, 0
    step = t0
    n_calls = 0
    for _ in range(max_iter):
        n_calls += 1
        if fun(x + step * p) <= J0 + c1 * step * g_dot_p:
            return step, n_calls
        step *= beta
    return None, n_calls


# ---------------------------------------------------------------------------
# Stage 2 driver
# ---------------------------------------------------------------------------
def _grad_descent(cost, gradient, theta, lo, hi, *, opts: dict):
    J_at = cost(theta)
    n_J = 1
    n_grad = 0
    n_it = 0
    g = np.zeros(2)
    for k in range(1, opts["max_iter"] + 1):
        n_it = k
        if J_at < opts["tol_J"]:
            break
        g, h_diag, n_extra_J = gradient(theta)
        n_grad += 1
        n_J += n_extra_J
        if float(np.linalg.norm(g)) < opts["tol_grad"]:
            break
        # Diagonal-Newton step direction (handles flat-valley cost
        # surfaces); fall back to steepest descent if Hessian
        # diagonal is non-positive.
        if h_diag[0] > 0 and h_diag[1] > 0:
            p = -g / h_diag
            if float(np.dot(g, p)) >= 0:  # not a descent direction
                p = -g
        else:
            p = -g
        step, n_step_J = _armijo(
            cost, theta, p, J_at, g,
            beta=opts["beta"], c1=opts["c1"], t0=opts["t0"],
        )
        n_J += n_step_J
        if step is None:
            break
        theta_new = np.minimum(np.maximum(theta + step * p, lo), hi)
        J_new = cost(theta_new)
        n_J += 1
        if J_new >= J_at:
            break
        theta, J_at = theta_new, J_new
    return theta, J_at, n_it, n_J, n_grad, float(np.linalg.norm(g))


def estimate_alpha_Rx(
    H_meas: complex,
    *,
    opts: dict | None = None,
) -> tuple[np.ndarray, EstimateInfo]:
    o = {**DEFAULT_OPTS, **(opts or {})}
    omega0 = 2.0 * np.pi * o["f0"]
    a_lo, a_hi, R_lo, R_hi = o["bounds"]
    lo = np.array([a_lo, R_lo])
    hi = np.array([a_hi, R_hi])

    def cost(theta):
        return _cost(theta, H_meas, omega0, opts=o)

    def gradient(theta):
        return _gradient(theta, H_meas, omega0, opts=o)

    t0 = time.perf_counter()

    # ---- Stage 1: coarse grid (Stage-1 unchanged in algorithm; Rx grid
    # is log-spaced because the new wide WP2.4 bounds R_x in [1, 1e6]
    # span six decades and a linear grid would be unusably coarse).
    aa = np.linspace(a_lo, a_hi, o["n_alpha"])
    RR = np.geomspace(max(R_lo, 1e-9), R_hi, o["n_Rx"])
    Jgrid = np.empty((o["n_alpha"], o["n_Rx"]))
    for i, a in enumerate(aa):
        for j, R in enumerate(RR):
            Jgrid[i, j] = cost([a, R])
    flat = Jgrid.ravel()
    n_J_total = o["n_alpha"] * o["n_Rx"]

    n_seeds = int(o["n_seeds"])
    seed_idx_unord = np.argpartition(flat, n_seeds - 1)[:n_seeds]
    seed_idx = seed_idx_unord[np.argsort(flat[seed_idx_unord])]
    seeds = []
    for idx in seed_idx:
        i, j = np.unravel_index(int(idx), Jgrid.shape)
        seeds.append(np.array([aa[i], RR[j]]))

    # ---- Stage 2: gradient descent on each seed ---------------------
    best_J = np.inf
    best_theta = seeds[0]
    best_n_iters = 0
    best_grad_norm = float("nan")
    n_grad_total = 0
    for theta_init in seeds:
        theta, J, n_it, n_J, n_grad, gn = _grad_descent(
            cost, gradient, theta_init.copy(), lo, hi, opts=o,
        )
        n_J_total += n_J
        n_grad_total += n_grad
        if J < best_J:
            best_J = float(J)
            best_theta = theta
            best_n_iters = n_it
            best_grad_norm = gn

    return best_theta, EstimateInfo(
        J_min=best_J,
        n_iters=best_n_iters,
        n_J_evals=n_J_total,
        n_grad_evals=n_grad_total,
        cpu_time_s=time.perf_counter() - t0,
        stage1_J0=float(flat[seed_idx[0]]),
        grad_norm_at_exit=best_grad_norm,
    )


# ---------------------------------------------------------------------------
# Single-bin DFT helpers (unchanged)
# ---------------------------------------------------------------------------
def single_bin_dft(x: np.ndarray, fs: float, f0: float) -> complex:
    Ns = len(x)
    n = np.arange(Ns)
    k = int(round(f0 * Ns / fs))
    return complex((2.0 / Ns) * np.sum(x * np.exp(-1j * 2 * np.pi * k * n / Ns)))


def H_meas_from_waveforms(
    v: np.ndarray, i: np.ndarray, fs: float = 10000.0, f0: float = 50.0
) -> complex:
    Vp = single_bin_dft(v, fs, f0)
    Ip = single_bin_dft(i, fs, f0)
    return Ip / Vp


# =============================================================================
# WP3.4 -- Multi-fault-type classifier on a 3-phase IEEEFeederNetwork
# =============================================================================
#
# Per the WP3.4 brief, the optimiser parameter vector becomes
# (alpha, R_x, fault_type) and the fault_type is identified by trying
# all three (SLG, LL, LLG) and picking the candidate that minimises
# the fit cost J = ||Y_send_meas - Y_send_model||^2_F.
#
# The implementation is an OUTER LOOP over fault_type around an INNER
# coarse-grid search over (alpha, R_x).  The (alpha, R_x) inner step
# uses a coarse grid rather than the WP2.4 two-stage Phase-2 optimiser
# because (a) WP3.x has not yet integrated the 3-phase Y_send model
# into the WP2.4 optimiser cost function (the WP2.4 optimiser is
# single-phase H_meas), and (b) for the WP3.4 acceptance the
# CLASSIFICATION accuracy is what's tested, not the (alpha, R_x)
# estimation residual.  Inner-step refinement to gradient-based
# is a clean extension at WP3.5 / WP3.6 where the optimiser is
# rewired for 3-phase Y_send.

@dataclass
class FaultTypeEstimate:
    """Result of the WP3.4 multi-type classifier."""
    fault_type_hat: str         # argmin over fault types of J_min
    alpha_hat: float            # best (alpha, R_x) under fault_type_hat
    Rx_hat: float
    J_min: float                # min J across all fault types
    J_per_type: dict[str, float]   # J_min per candidate fault type
    fault_bus: str              # the bus the network was searched at


def classify_fault_type_3ph(
    Y_meas: np.ndarray,
    network,
    *,
    fault_bus: str,
    omega: float = 2 * np.pi * 50.0,
    fault_types: tuple[str, ...] = ("SLG", "LL", "LLG"),
    alpha_grid: tuple[float, ...] = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9),
    Rx_grid: tuple[float, ...] = (100.0, 500.0, 1000.0, 2000.0, 5000.0),
    fault_phase: int = 0,
) -> FaultTypeEstimate:
    """Identify the most likely fault type for an observed 3x3 Y_meas.

    Parameters
    ----------
    Y_meas : ndarray (3, 3) complex
        Observed sending-end admittance (possibly noisy).
    network : object with .Y_send(omega, *, fault_bus, alpha, Rx, fault_phase, fault_type)
        IEEEFeederNetwork instance (or any duck-type-equivalent).
    fault_bus : str
        Bus name where the fault is assumed to be located.  In the
        WP3.4 acceptance we use the TRUE fault_bus (so the classifier
        is fault-bus-conditional); in WP3.5 / WP3.6 the optimiser will
        marginalise over fault_bus.
    omega : float
        Angular frequency at f0.
    fault_types : tuple of str
        Candidate fault types (default {SLG, LL, LLG}).
    alpha_grid : tuple of float
        Inner-loop alpha grid for the coarse search.
    Rx_grid : tuple of float
        Inner-loop R_x grid for the coarse search.
    fault_phase : int
        Phase index for the SLG candidate.

    Returns
    -------
    FaultTypeEstimate
    """
    best_per_type: dict[str, tuple[float, float, float]] = {}  # ft -> (J, alpha, Rx)
    for ft in fault_types:
        best = (np.inf, alpha_grid[0], Rx_grid[0])
        for alpha in alpha_grid:
            for Rx in Rx_grid:
                Y_pred = network.Y_send(
                    omega,
                    fault_bus=fault_bus,
                    alpha=alpha,
                    Rx=Rx,
                    fault_phase=fault_phase,
                    fault_type=ft,
                )
                J = float(np.sum(np.abs(Y_meas - Y_pred) ** 2))
                if J < best[0]:
                    best = (J, alpha, Rx)
        best_per_type[ft] = best

    ft_hat = min(best_per_type, key=lambda ft: best_per_type[ft][0])
    J_hat, alpha_hat, Rx_hat = best_per_type[ft_hat]
    J_per_type = {ft: best_per_type[ft][0] for ft in fault_types}
    return FaultTypeEstimate(
        fault_type_hat=ft_hat,
        alpha_hat=alpha_hat,
        Rx_hat=Rx_hat,
        J_min=J_hat,
        J_per_type=J_per_type,
        fault_bus=fault_bus,
    )


def add_complex_gaussian_noise_to_Y(
    Y_clean: np.ndarray,
    snr_db: float,
    *,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Add per-entry circular complex Gaussian noise to a 3x3 Y matrix.

    Used by the WP3.4 MC runner as a fast analytic substitute for
    full waveform synthesis + Y_send recovery via single-bin DFT.
    snr_db is interpreted relative to the per-entry magnitude:
    sigma_per_entry = |Y_clean[k,l]| * 10**(-snr_db/20).
    """
    if rng is None:
        rng = np.random.default_rng()
    if not np.isfinite(snr_db):
        return Y_clean.copy()
    mag = np.abs(Y_clean)
    sigma = mag * 10.0 ** (-snr_db / 20.0)
    real = rng.standard_normal(Y_clean.shape)
    imag = rng.standard_normal(Y_clean.shape)
    noise = (real + 1j * imag) * (sigma / np.sqrt(2.0))
    return Y_clean + noise
