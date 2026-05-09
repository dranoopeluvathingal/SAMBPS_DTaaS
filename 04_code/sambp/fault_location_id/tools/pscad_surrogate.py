"""pscad_surrogate.py
======================

Producer for ``data/pscad_720.mat`` on machines without PSCAD.

The canonical waveform set comes from the PSCAD case
``pscad/HIFL_11kV_100km.pscx`` (frequency-dependent J. Marti line
+ anti-parallel diode arc + dual-channel CT/PT) executed by
``pscad/run_pscad_720.py`` on a licensed PSCAD station.  Until that
runs, this surrogate produces a Python distributed-parameter
reference using cosh/sinh ABCD cascading at $f_0 = 50$ Hz, which is
the low-frequency limit of the J. Marti FD line.  At 50 Hz the
surrogate and PSCAD agree to within a few percent on $|H|$; the
WP1.4 cross-platform delta-error report is the formal comparator.

Schema (mirrors ``pscad/HIFL_11kV_100km_design.md`` "Output bundle"):

    V              float64 (720, 200)  source-end voltage [V]
    I              float64 (720, 200)  source-end current [A]
    grid_alpha     float64 (720,)      per-unit fault location
    grid_Rx        float64 (720,)      arc resistance [ohm]
    grid_SNR_V     float64 (720,)      voltage SNR [dB] (Inf = noiseless)
    grid_SNR_I     float64 (720,)      current SNR [dB] (Inf = noiseless)
    meta           struct               f0, Fs, Ns, line_length_km,
                                        rng_seed, builder, version

Usage
-----
    python tools/pscad_surrogate.py
    python tools/pscad_surrogate.py --out data/pscad_720.mat
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from scipy.io import savemat

# Per-km defaults (Saha 2010, Springer; mirror of
# models/faultloc_pi_section_model.py)
R_PER_KM = 0.0728     # ohm/km
L_PER_KM = 0.927e-3   # H/km
C_PER_KM = 11.6e-9    # F/km
G_PER_KM = 0.0        # S/km
LINE_LENGTH_KM = 100.0
R_LOAD = 1.0e6        # remote-bus shunt; 1 Mohm = effectively open

V_PHASE = 11000.0 / np.sqrt(3.0)   # phase voltage (peak = V_PHASE * sqrt(2))
F0 = 50.0
FS = 10000.0
NS = 200
NSAMPLES_PER_CYCLE = int(round(FS / F0))   # 200
assert NS == NSAMPLES_PER_CYCLE

# Grid (matches pscad sub-sample of 720)
ALPHAS = np.round(np.arange(0.10, 0.91, 0.10), 6)   # 9 values
RXS = np.array([100.0, 500.0, 1000.0, 2000.0, 5000.0])
SNR_V = np.array([20.0, 30.0, 40.0, np.inf])
SNR_I = np.array([20.0, 30.0, 40.0, np.inf])
N_GRID = len(ALPHAS) * len(RXS) * len(SNR_V) * len(SNR_I)
assert N_GRID == 720, f"grid size = {N_GRID} (expected 720)"


def abcd_section(length_km: float, omega: float) -> np.ndarray:
    """Return the 2x2 ABCD matrix of a uniform distributed line section.

    [V_in]   [A  B] [V_out]
    [I_in] = [C  D] [I_out]

    With per-unit-length R', L', C', G' and section length L:
        gamma   = sqrt((R' + j*omega*L') * (G' + j*omega*C'))
        Z_c     = sqrt((R' + j*omega*L') / (G' + j*omega*C'))
        A = D   = cosh(gamma * L)
        B       = Z_c * sinh(gamma * L)
        C       = sinh(gamma * L) / Z_c
    """
    z = R_PER_KM + 1j * omega * L_PER_KM
    y = G_PER_KM + 1j * omega * C_PER_KM
    gamma = np.sqrt(z * y)
    Z_c = np.sqrt(z / y)
    gL = gamma * length_km
    ch = np.cosh(gL)
    sh = np.sinh(gL)
    return np.array([[ch, Z_c * sh], [sh / Z_c, ch]], dtype=complex)


def shunt_admittance(Y: complex) -> np.ndarray:
    """ABCD of a shunt admittance Y (current sink to ground)."""
    return np.array([[1.0, 0.0], [Y, 1.0]], dtype=complex)


def H_distributed(alpha: float, Rx: float, omega: float) -> complex:
    """Source-end input admittance H = I_in / V_in for the cascaded line.

    Topology (downstream to upstream cascading):
        source ── [section 1] ── fault ── [section 2] ── remote ── R_load ── open
                                  |
                                 R_x to ground
    """
    M1 = abcd_section(alpha * LINE_LENGTH_KM, omega)
    M2 = abcd_section((1.0 - alpha) * LINE_LENGTH_KM, omega)
    Y_fault = shunt_admittance(1.0 / Rx)
    Y_load = shunt_admittance(1.0 / R_LOAD)
    M_total = M1 @ Y_fault @ M2 @ Y_load
    # Open at far end: I_far = 0  =>  V_in = A * V_far ; I_in = C * V_far
    return complex(M_total[1, 0] / M_total[0, 0])


def add_awgn(x: np.ndarray, snr_db: float, rng: np.random.Generator) -> np.ndarray:
    if not np.isfinite(snr_db):
        return x
    px = float(np.mean(x ** 2))
    pn = px / (10.0 ** (snr_db / 10.0))
    return x + np.sqrt(pn) * rng.standard_normal(x.shape)


def synthesise_one_cell(
    alpha: float,
    Rx: float,
    snr_v_db: float,
    snr_i_db: float,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    """Build one (V, I) waveform pair (length NS) for one grid cell."""
    omega = 2.0 * np.pi * F0
    H = H_distributed(alpha, Rx, omega)
    Vph = V_PHASE * np.sqrt(2.0)        # peak phase voltage
    t = np.arange(NS) / FS              # one cycle window
    v_clean = Vph * np.cos(omega * t)
    Iph = H * Vph                       # complex current phasor
    i_clean = (Iph * np.exp(1j * omega * t)).real
    v_noisy = add_awgn(v_clean, snr_v_db, rng)
    i_noisy = add_awgn(i_clean, snr_i_db, rng)
    return v_noisy.astype(np.float64), i_noisy.astype(np.float64)


def build_dataset(out_path: Path, *, rng_seed: int = 42) -> Path:
    rng = np.random.default_rng(rng_seed)

    V = np.zeros((N_GRID, NS), dtype=np.float64)
    Ic = np.zeros((N_GRID, NS), dtype=np.float64)
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
        "builder": "tools/pscad_surrogate.py",
        "version": "0.2.0-phase0",
        "note": (
            "Distributed-parameter ABCD-cascading reference; "
            "frequency-domain at f_0 = 50 Hz.  Replace with the "
            "canonical PSCAD output via pscad/run_pscad_720.py."
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
        f"pscad_surrogate: wrote {out_path}\n"
        f"  V shape    {V.shape}\n"
        f"  I shape    {Ic.shape}\n"
        f"  grid       {len(ALPHAS)} a x {len(RXS)} Rx x "
        f"{len(SNR_V)} SNR_V x {len(SNR_I)} SNR_I = {N_GRID}"
    )
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data/pscad_720.mat"),
        help="Path to write the surrogate .mat (default: data/pscad_720.mat).",
    )
    parser.add_argument(
        "--rng-seed",
        type=int,
        default=42,
    )
    args = parser.parse_args(argv)
    build_dataset(args.out, rng_seed=args.rng_seed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
