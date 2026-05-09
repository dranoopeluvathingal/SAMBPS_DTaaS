"""emtp_surrogate.py
======================

Producer for ``data/emtp_720.mat`` on machines without EMTP-RV.

**Independent numerical pathway** from ``tools/pscad_surrogate.py``.
The PSCAD surrogate uses cosh/sinh distributed-parameter ABCD
cascading (continuous distributed line at $f_0$).  This EMTP
surrogate uses a 50-section pi-model state-space cascade (high-
resolution lumped approximation), which is structurally different
and converges to the same physics from a different direction.  The
two surrogates are deliberately built by separate code paths so
``tools/compare_pscad_emtp.py`` is measuring something rather than
trivially returning zero (R1 mitigation per v3 plan §10).

Schema mirrors ``data/pscad_720.mat`` byte-for-byte (cell ordering,
key names, dtypes).

Usage
-----
    python tools/emtp_surrogate.py
    python tools/emtp_surrogate.py --out data/emtp_720.mat
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from scipy.io import savemat

# Per-km parameters (Saha 2010, mirror of pscad_surrogate.py).
R_PER_KM = 0.0728
L_PER_KM = 0.927e-3
C_PER_KM = 11.6e-9
G_PER_KM = 0.0
LINE_LENGTH_KM = 100.0
R_LOAD = 1.0e6

V_PHASE = 11000.0 / np.sqrt(3.0)
F0 = 50.0
FS = 10000.0
NS = 200

# Independent grid sub-sampling rule.  See HIFL_11kV_100km_design.md
# "Grid sizing note"; matches pscad_surrogate so the per-cell index
# alignment in compare_pscad_emtp.py is straightforward.
ALPHAS = np.round(np.arange(0.10, 0.91, 0.10), 6)
RXS = np.array([100.0, 500.0, 1000.0, 2000.0, 5000.0])
SNR_V = np.array([20.0, 30.0, 40.0, np.inf])
SNR_I = np.array([20.0, 30.0, 40.0, np.inf])
N_GRID = len(ALPHAS) * len(RXS) * len(SNR_V) * len(SNR_I)
assert N_GRID == 720

# 50-section pi: per-side; total 50+50 sections across the feeder.
N_PI_PER_SIDE = 50


def build_pi_section_AB(L_km: float, n_sections: int):
    """Build a series of n cascaded pi-sections of total length L_km.

    Each pi has shunt C/2 at each end and series R-L between.
    Returns (R_section_per_node, L_section_per_node, C_node) arrays.

    Implementation: n+1 nodes, n series R-L between adjacent nodes.
    Each node carries a shunt C equal to the sum of the half-sections
    on either side of it.
    """
    dl = L_km / n_sections
    R = R_PER_KM * dl    # per-section
    L = L_PER_KM * dl
    Csec = C_PER_KM * dl
    return R, L, Csec, n_sections + 1   # number of nodes incl. endpoints


def H_50section(alpha: float, Rx: float, omega: float) -> complex:
    """50-section pi-model state-space.

    Topology:
      source --[N pi sections]-- fault node (shunt R_x) --[N pi sections]--
        remote node (shunt R_load)
    Node 0  = source bus (driven by V_s)
    Node N1 = fault bus (R_x shunt)
    Node N1 + N2 = remote bus (R_load shunt)

    For frequency-domain analysis at omega, build the nodal
    admittance matrix Y(j*omega) and solve V = Y^-1 * I_inj where
    only node 0 is driven.  Output H = I_in / V_in at the source.
    """
    n1 = N_PI_PER_SIDE
    n2 = N_PI_PER_SIDE
    R1, L1, C1sec, _ = build_pi_section_AB(alpha * LINE_LENGTH_KM, n1)
    R2, L2, C2sec, _ = build_pi_section_AB((1 - alpha) * LINE_LENGTH_KM, n2)

    n_nodes = n1 + n2 + 1                        # 0..n1 ..n1+n2
    fault_idx = n1
    remote_idx = n1 + n2

    Y = np.zeros((n_nodes, n_nodes), dtype=complex)

    # Series admittance of an R-L branch:
    def y_series(R, L):
        return 1.0 / (R + 1j * omega * L)

    # Section 1: nodes 0..n1
    ys1 = y_series(R1, L1)
    yc1 = 1j * omega * (C1sec / 2.0)            # half-pi shunt at each node end
    for k in range(n1):
        Y[k, k] += ys1
        Y[k + 1, k + 1] += ys1
        Y[k, k + 1] -= ys1
        Y[k + 1, k] -= ys1
        # Shunt halves at each adjacent node:
        Y[k, k] += yc1
        Y[k + 1, k + 1] += yc1

    # Section 2: nodes n1..n1+n2
    ys2 = y_series(R2, L2)
    yc2 = 1j * omega * (C2sec / 2.0)
    for k in range(n2):
        i = n1 + k
        j = n1 + k + 1
        Y[i, i] += ys2
        Y[j, j] += ys2
        Y[i, j] -= ys2
        Y[j, i] -= ys2
        Y[i, i] += yc2
        Y[j, j] += yc2

    # Fault shunt at fault_idx
    Y[fault_idx, fault_idx] += 1.0 / Rx

    # Remote shunt at remote_idx
    Y[remote_idx, remote_idx] += 1.0 / R_LOAD

    # Driven-source pattern: fix V[0] = 1; eliminate row/col 0,
    # solve for V[1..n_nodes-1].
    Y_red = Y[1:, 1:]
    b = -Y[1:, 0]                                # +1 V at node 0
    V_rest = np.linalg.solve(Y_red, b)
    V = np.empty(n_nodes, dtype=complex)
    V[0] = 1.0
    V[1:] = V_rest

    # Source-end injection: I_in = sum of currents leaving node 0
    # = Y[0, :] @ V
    I_in = Y[0, :] @ V
    # H = I_in / V[0] (= I_in since V[0] = 1).
    return complex(I_in)


def add_awgn(x: np.ndarray, snr_db: float, rng) -> np.ndarray:
    if not np.isfinite(snr_db):
        return x
    px = float(np.mean(x ** 2))
    pn = px / (10.0 ** (snr_db / 10.0))
    return x + np.sqrt(pn) * rng.standard_normal(x.shape)


def synthesise_one_cell(alpha, Rx, snrV, snrI, rng):
    omega = 2 * np.pi * F0
    H = H_50section(alpha, Rx, omega)
    Vph = V_PHASE * np.sqrt(2.0)
    t = np.arange(NS) / FS
    v_clean = Vph * np.cos(omega * t)
    Iph = H * Vph
    i_clean = (Iph * np.exp(1j * omega * t)).real
    return (
        add_awgn(v_clean, snrV, rng).astype(np.float64),
        add_awgn(i_clean, snrI, rng).astype(np.float64),
    )


def build_dataset(out_path: Path, *, rng_seed: int = 4242) -> Path:
    rng = np.random.default_rng(rng_seed)
    V = np.zeros((N_GRID, NS))
    Ic = np.zeros((N_GRID, NS))
    grid_alpha = np.zeros(N_GRID)
    grid_Rx = np.zeros(N_GRID)
    grid_SNR_V = np.zeros(N_GRID)
    grid_SNR_I = np.zeros(N_GRID)

    n = 0
    for a in ALPHAS:
        for R in RXS:
            for sv in SNR_V:
                for si in SNR_I:
                    V[n], Ic[n] = synthesise_one_cell(a, R, sv, si, rng)
                    grid_alpha[n] = a
                    grid_Rx[n] = R
                    grid_SNR_V[n] = sv
                    grid_SNR_I[n] = si
                    n += 1

    meta = {
        "f0": F0,
        "Fs": FS,
        "Ns": NS,
        "line_length_km": LINE_LENGTH_KM,
        "rng_seed": rng_seed,
        "builder": "tools/emtp_surrogate.py",
        "version": "0.2.0-phase1-WP1.2",
        "n_pi_per_side": N_PI_PER_SIDE,
        "note": (
            "50-section pi-model state-space (independent numerical "
            "pathway from pscad_surrogate's cosh/sinh ABCD).  Replace "
            "with canonical EMTP-RV output via emtp/run_emtp_720.py."
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
    print(
        f"emtp_surrogate: wrote {out_path}\n"
        f"  V shape    {V.shape}\n"
        f"  I shape    {Ic.shape}\n"
        f"  pi/side    {N_PI_PER_SIDE}\n"
        f"  rng seed   {rng_seed} (independent of pscad_surrogate)"
    )
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data/emtp_720.mat"),
    )
    parser.add_argument(
        "--rng-seed",
        type=int,
        default=4242,
        help="Independent of pscad_surrogate's seed (=42).",
    )
    args = parser.parse_args(argv)
    build_dataset(args.out, rng_seed=args.rng_seed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
