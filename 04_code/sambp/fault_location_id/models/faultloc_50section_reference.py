"""
faultloc_50section_reference.py
================================
Pure-numpy generalised N_s-section pi-model state-space, used as the
**reference data-generating model** for the SAMBP Fault-Location
Identification project.  Default N_s = 50 sections per side.

Maps to v3 Execution Manual work packages
-----------------------------------------
    WP1.3  Pure-MATLAB 50-section reference state-space (data-only;
           not used by optimiser).  This module is the Python mirror.
    WP2.3  Reproduce 50-section reference within 1 % across (alpha,
           R_x) grid using the closed-form distributed-parameter model.

Physical model
--------------
Per-section parameters re-use ``faultloc_pi_section_model``:

    R_per_km = 0.0728  ohm/km        (Saha 2010, Springer)
    L_per_km = 0.927e-3 H/km
    C_per_km = 11.6e-9  F/km

The fault is inserted as a shunt R_x at the **section nearest** to
alpha:

    fault_section = round(alpha * N_s_per_side)

This introduces a discretisation residual of order 1/N_s in the
recovered fault location.  At N_s = 50 this is at most 1 % of feeder
length -- acceptable for a *data-generating* model whose role is to
provide a high-resolution waveform set for Phase-1 cross-platform
validation, but **not acceptable** for an optimiser model (the
optimiser must be continuously parametrised in alpha, which is what
WP2.1 lands).

Topology
--------
    source -- [N_s_per_side pi sections] -- fault node (shunt R_x) --
              [N_s_per_side pi sections] -- remote node (shunt R_load)

Each pi section: shunt C/2 at each node end, series R-L between.
N_s_per_side = 50 (default) -> 51 nodes per side -> 101 total nodes
(fault node shared between sides).

Public API
----------
    H_model_n_sections(alpha, Rx, omega, n_per_side=50, ...)
        -> complex   single-frequency transfer function I_in / V_in
    synthesise_one_cell(alpha, Rx, snrV, snrI, ..., n_per_side=50)
        -> (V[Ns], I[Ns])
    build_dataset(out_path, n_per_side=50, rng_seed=...)
        -> Path     writes data/ref_50section_720.mat

Cross-runtime check.  ``tests/test_50section_vs_2section_at_alpha_0p5
.py`` documents the 2-section-vs-50-section gap for (alpha=0.5, R_x=
1000); see that file for the v1-manuscript provenance discrepancy.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

# Per-km defaults (mirror of faultloc_pi_section_model.py).
R_PER_KM = 0.0728
L_PER_KM = 0.927e-3
C_PER_KM = 11.6e-9
G_PER_KM = 0.0
LINE_LENGTH_KM = 100.0
R_LOAD = 1.0e6

V_PHASE = 11000.0 / np.sqrt(3.0)
F0 = 50.0
FS = 10000.0
NS_TIME = 200

# 720-case grid (mirror of pscad/emtp surrogates).
ALPHAS = np.round(np.arange(0.10, 0.91, 0.10), 6)
RXS = np.array([100.0, 500.0, 1000.0, 2000.0, 5000.0])
SNR_V = np.array([20.0, 30.0, 40.0, np.inf])
SNR_I = np.array([20.0, 30.0, 40.0, np.inf])
N_GRID = len(ALPHAS) * len(RXS) * len(SNR_V) * len(SNR_I)
assert N_GRID == 720

DEFAULT_N_PER_SIDE = 50


def H_model_n_sections(
    alpha: float,
    Rx: float,
    omega: float,
    *,
    n_per_side: int = DEFAULT_N_PER_SIDE,
    line_length_km: float = LINE_LENGTH_KM,
    R_per_km: float = R_PER_KM,
    L_per_km: float = L_PER_KM,
    C_per_km: float = C_PER_KM,
    R_load: float = R_LOAD,
) -> complex:
    """Source-end input admittance H = I_in / V_in at angular frequency omega.

    Implementation: assemble the (n_total) x (n_total) nodal admittance
    matrix, drive node 0 at V = 1, solve for the remaining nodal
    voltages, and read off I_in = sum of currents leaving node 0
    = (Y[0, :] @ V).
    """
    # Section lengths (km) per side
    L1_km = alpha * line_length_km
    L2_km = (1.0 - alpha) * line_length_km

    # Per-section per-side parameters
    dl1 = L1_km / n_per_side
    dl2 = L2_km / n_per_side
    R1 = R_per_km * dl1
    X1 = L_per_km * dl1
    C1 = C_per_km * dl1
    R2 = R_per_km * dl2
    X2 = L_per_km * dl2
    C2 = C_per_km * dl2

    n_nodes = 2 * n_per_side + 1
    fault_idx = n_per_side
    remote_idx = 2 * n_per_side

    Y = np.zeros((n_nodes, n_nodes), dtype=complex)

    # Section 1: nodes 0..n_per_side
    ys1 = 1.0 / (R1 + 1j * omega * X1)
    yc1 = 1j * omega * (C1 / 2.0)
    for k in range(n_per_side):
        Y[k, k] += ys1 + yc1
        Y[k + 1, k + 1] += ys1 + yc1
        Y[k, k + 1] -= ys1
        Y[k + 1, k] -= ys1

    # Section 2: nodes n_per_side..2*n_per_side
    ys2 = 1.0 / (R2 + 1j * omega * X2)
    yc2 = 1j * omega * (C2 / 2.0)
    for k in range(n_per_side):
        i = n_per_side + k
        j = i + 1
        Y[i, i] += ys2 + yc2
        Y[j, j] += ys2 + yc2
        Y[i, j] -= ys2
        Y[j, i] -= ys2

    # Fault shunt R_x at fault node
    Y[fault_idx, fault_idx] += 1.0 / Rx
    # Remote-bus load
    Y[remote_idx, remote_idx] += 1.0 / R_load

    # Solve V[1:] given V[0] = 1
    Y_red = Y[1:, 1:]
    b = -Y[1:, 0]
    V_rest = np.linalg.solve(Y_red, b)
    V = np.empty(n_nodes, dtype=complex)
    V[0] = 1.0
    V[1:] = V_rest

    # I_in = current injected at node 0 (driven source)
    I_in = Y[0, :] @ V
    return complex(I_in)


def _add_awgn(x: np.ndarray, snr_db: float, rng: np.random.Generator) -> np.ndarray:
    if not np.isfinite(snr_db):
        return x
    px = float(np.mean(x ** 2))
    pn = px / (10.0 ** (snr_db / 10.0))
    return x + np.sqrt(pn) * rng.standard_normal(x.shape)


def synthesise_one_cell(
    alpha: float,
    Rx: float,
    snrV: float,
    snrI: float,
    rng: np.random.Generator,
    *,
    n_per_side: int = DEFAULT_N_PER_SIDE,
) -> tuple[np.ndarray, np.ndarray]:
    omega = 2.0 * np.pi * F0
    H = H_model_n_sections(alpha, Rx, omega, n_per_side=n_per_side)
    Vph = V_PHASE * np.sqrt(2.0)
    t = np.arange(NS_TIME) / FS
    v_clean = Vph * np.cos(omega * t)
    Iph = H * Vph
    i_clean = (Iph * np.exp(1j * omega * t)).real
    return (
        _add_awgn(v_clean, snrV, rng).astype(np.float64),
        _add_awgn(i_clean, snrI, rng).astype(np.float64),
    )


def build_dataset(
    out_path: Path,
    *,
    n_per_side: int = DEFAULT_N_PER_SIDE,
    rng_seed: int = 17,
) -> Path:
    """Build the canonical 720-cell reference and save as MATLAB v7."""
    from scipy.io import savemat

    rng = np.random.default_rng(rng_seed)
    V = np.zeros((N_GRID, NS_TIME))
    Ic = np.zeros((N_GRID, NS_TIME))
    grid_alpha = np.zeros(N_GRID)
    grid_Rx = np.zeros(N_GRID)
    grid_SNR_V = np.zeros(N_GRID)
    grid_SNR_I = np.zeros(N_GRID)

    n = 0
    for a in ALPHAS:
        for R in RXS:
            for sv in SNR_V:
                for si in SNR_I:
                    V[n], Ic[n] = synthesise_one_cell(
                        a, R, sv, si, rng, n_per_side=n_per_side
                    )
                    grid_alpha[n] = a
                    grid_Rx[n] = R
                    grid_SNR_V[n] = sv
                    grid_SNR_I[n] = si
                    n += 1

    meta = {
        "f0": F0,
        "Fs": FS,
        "Ns": NS_TIME,
        "line_length_km": LINE_LENGTH_KM,
        "n_per_side": n_per_side,
        "rng_seed": rng_seed,
        "builder": "models/faultloc_50section_reference.py",
        "version": "0.2.0-phase1-WP1.3",
        "note": (
            f"{n_per_side}-section pi-model state-space per side; fault "
            f"shunt at section nearest to alpha (1/{n_per_side} "
            f"discretisation residual on alpha).  Data-generating "
            f"reference only; NOT for optimiser use."
        ),
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    savemat(
        str(out_path),
        {
            "V": V,
            "I": Ic,
            "grid_alpha": grid_alpha,
            "grid_Rx": grid_Rx,
            "grid_SNR_V": grid_SNR_V,
            "grid_SNR_I": grid_SNR_I,
            "meta": meta,
        },
        do_compression=True,
        format="5",
    )
    return out_path
