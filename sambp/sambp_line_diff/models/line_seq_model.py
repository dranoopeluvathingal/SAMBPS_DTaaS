"""
line_seq_model.py
=================
Symmetrical-component extraction for the SAMBP 87LN negative-sequence
line differential element.

Background
----------
For an asymmetric internal fault (single-line-to-ground, line-to-line, or
double-line-to-ground), the 3-phase differential current contains a
significant negative-sequence component I₂.  For a symmetric 3-phase fault
or a healthy line with balanced loading, I₂ ≈ 0.

The negative-sequence differential relay (87LN) measures:
    I₂_diff = |I₂_L + I₂_R|

where I₂_L and I₂_R are the negative-sequence phasors at the local and
remote terminals.  For an internal asymmetric fault, both ends contribute
in-phase (additive); for an external fault, contributions cancel (the
current passes straight through without net differential).

Motivation for IBR networks
----------------------------
Inverter-based resources (IBRs) current-limit their positive-sequence output
during faults to protect the power electronics.  The limit is typically
1.0–1.2 pu, giving a positive-sequence differential of:
    I₁_diff = I₁_IBR (limited) + I₁_grid

When the IBR dominates (microgrid, weak grid), I₁_diff can fall below the
87L threshold (0.12 pu).

The negative-sequence current from a SLG fault is governed by the sequence
network and is NOT directly limited by the IBR positive-sequence current
limiter (most commercially deployed IBRs use positive-sequence current
references during FRT; I₂ injection depends on the control strategy).
Thus I₂_diff may remain above the 87LN threshold even when I₁_diff < I₁_thr.

Symmetrical components (time-domain extraction)
------------------------------------------------
Given three-phase differential waveforms ia(t), ib(t), ic(t):

    [I₀]   1  [1   1   1 ] [Ia]
    [I₁] = ─  [1   a   a²] [Ib]   a = e^{j2π/3}
    [I₂]   3  [1   a²  a ] [Ic]

In the time domain the negative-sequence component is extracted via:
    i₂(t) = Re{ (1/3)[ia(t) + a²·ib(t) + a·ic(t)] }

where the phasors a, a² are applied as 120°/240° phase-advances, implemented
by a time-shift of ±T/3 (one-third of the power cycle) on each phase.

Alternatively, for short windows, estimate the phasor at each terminal via
DFT, apply the symmetrical component transform, and compute |I₂|.  This is
the approach implemented here.

References
----------
    Stevenson, W.D. (1994). Elements of Power System Analysis, §12.
    IEEE Std C37.243-2015 §8 — Directional comparison for line differential.
    IEC 60255-181:2019 §7 — Negative-sequence overcurrent.
    SAMBP TR-21/2026 — Harmonic pre-filter for IBR networks.
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass


# Symmetrical-component rotation operator
_A = np.exp(1j * 2 * np.pi / 3)    # a  = e^{j120°}
_A2 = np.conjugate(_A)              # a² = e^{j240°} = e^{-j120°}


# ---------------------------------------------------------------------------
# Phasor extraction (DFT)
# ---------------------------------------------------------------------------

def extract_phasor(waveform: np.ndarray, freq_hz: float, fs: float) -> complex:
    """
    Extract the fundamental-frequency phasor from a time-domain waveform.

    Uses single-bin DFT (Goertzel-equivalent).  Returns complex phasor in
    peak-value convention: if x(t) = A×sin(ωt+φ), returns A×e^{jφ}.

    Parameters
    ----------
    waveform : (N,) single-phase waveform [pu]
    freq_hz  : fundamental frequency [Hz]
    fs       : sampling rate [Hz]

    Returns
    -------
    complex phasor (peak convention) [pu]
    """
    N = len(waveform)
    F = np.fft.rfft(waveform)
    idx = int(round(freq_hz * N / fs))
    idx = np.clip(idx, 0, len(F) - 1)
    # Peak amplitude = 2|F[k]|/N, angle = angle(F[k])
    return complex(F[idx]) * 2.0 / N


# ---------------------------------------------------------------------------
# Symmetrical components from 3-phase phasors
# ---------------------------------------------------------------------------

def symmetrical_components(
    phasor_a: complex,
    phasor_b: complex,
    phasor_c: complex,
) -> tuple[complex, complex, complex]:
    """
    Compute zero-, positive-, and negative-sequence phasors.

    Returns
    -------
    I0, I1, I2 : complex phasors (peak convention) [pu]
    """
    I0 = (phasor_a + phasor_b + phasor_c) / 3.0
    I1 = (phasor_a + _A * phasor_b + _A2 * phasor_c) / 3.0
    I2 = (phasor_a + _A2 * phasor_b + _A * phasor_c) / 3.0
    return I0, I1, I2


# ---------------------------------------------------------------------------
# 87LN measurement from 3-phase differential waveforms
# ---------------------------------------------------------------------------

@dataclass
class NegSeqDiffResult:
    """Output of the 87LN negative-sequence differential measurement."""
    I1_diff: float          # Positive-sequence differential magnitude [pu]
    I2_diff: float          # Negative-sequence differential magnitude [pu]
    phi_I1: float           # Phase of I1_diff [rad]
    phi_I2: float           # Phase of I2_diff [rad]
    trip_87L: bool          # Positive-sequence trip
    trip_87LN: bool         # Negative-sequence trip
    trip_combined: bool     # 87L OR 87LN
    network_sig: str        # "SG" | "asymmetric" | "symmetric_ibr" | "healthy"


def measure_neg_seq_diff(
    i_diff_abc: np.ndarray,   # (3, N) three-phase differential [pu]
    freq_hz: float = 50.0,
    fs: float = 4000.0,
    I1_threshold: float = 0.12,
    I2_threshold: float = 0.06,
) -> NegSeqDiffResult:
    """
    Compute the 87L and 87LN differential measurements.

    Parameters
    ----------
    i_diff_abc   : (3, N) three-phase differential current [pu]
    freq_hz      : fundamental frequency [Hz]
    fs           : sampling rate [Hz]
    I1_threshold : 87L trip threshold [pu]   (positive-sequence)
    I2_threshold : 87LN trip threshold [pu]  (negative-sequence)

    Returns
    -------
    NegSeqDiffResult
    """
    # Extract fundamental phasors for each phase
    Pa = extract_phasor(i_diff_abc[0], freq_hz, fs)
    Pb = extract_phasor(i_diff_abc[1], freq_hz, fs)
    Pc = extract_phasor(i_diff_abc[2], freq_hz, fs)

    I0, I1, I2 = symmetrical_components(Pa, Pb, Pc)

    I1_mag = float(abs(I1))
    I2_mag = float(abs(I2))

    trip_87L  = I1_mag >= I1_threshold
    trip_87LN = I2_mag >= I2_threshold
    trip_comb = trip_87L or trip_87LN

    # Network signature heuristic
    H_ratio = I2_mag / max(I1_mag, 1e-6)
    if I1_mag < 0.01 and I2_mag < 0.01:
        sig = "healthy"
    elif H_ratio > 0.30:
        sig = "asymmetric"
    elif trip_87L and not trip_87LN:
        sig = "SG" if I1_mag > 0.5 else "symmetric_ibr"
    else:
        sig = "asymmetric" if trip_87LN else "healthy"

    return NegSeqDiffResult(
        I1_diff       = I1_mag,
        I2_diff       = I2_mag,
        phi_I1        = float(np.angle(I1)),
        phi_I2        = float(np.angle(I2)),
        trip_87L      = trip_87L,
        trip_87LN     = trip_87LN,
        trip_combined = trip_comb,
        network_sig   = sig,
    )


# ---------------------------------------------------------------------------
# Waveform generation helpers
# ---------------------------------------------------------------------------

def make_abc_waveform(
    I1: float,
    I2: float,
    freq_hz: float,
    fs: float,
    n_samples: int,
    phi1: float = 0.0,
    phi2: float = 0.0,
) -> np.ndarray:
    """
    Generate 3-phase waveform from positive- and negative-sequence amplitudes.

    The reconstruction formula (inverse symmetrical components):
        ia = I1×sin(ωt+φ1)       + I2×sin(ωt+φ2)
        ib = I1×sin(ωt+φ1−2π/3) + I2×sin(ωt+φ2+2π/3)
        ic = I1×sin(ωt+φ1+2π/3) + I2×sin(ωt+φ2−2π/3)

    Parameters
    ----------
    I1, I2 : amplitudes [pu] (positive- and negative-sequence)
    freq_hz, fs : frequency [Hz] and sampling rate [Hz]
    n_samples   : number of time samples
    phi1, phi2  : phase angles [rad]

    Returns
    -------
    (3, n_samples) three-phase waveform [pu]
    """
    t = np.arange(n_samples) / fs
    omega = 2.0 * np.pi * freq_hz

    # Positive sequence: phases a, b−120°, c+120°
    i_pos_a =  I1 * np.sin(omega * t + phi1)
    i_pos_b =  I1 * np.sin(omega * t + phi1 - 2*np.pi/3)
    i_pos_c =  I1 * np.sin(omega * t + phi1 + 2*np.pi/3)

    # Negative sequence: phases a, b+120°, c−120° (reversed rotation)
    i_neg_a =  I2 * np.sin(omega * t + phi2)
    i_neg_b =  I2 * np.sin(omega * t + phi2 + 2*np.pi/3)
    i_neg_c =  I2 * np.sin(omega * t + phi2 - 2*np.pi/3)

    return np.array([
        i_pos_a + i_neg_a,
        i_pos_b + i_neg_b,
        i_pos_c + i_neg_c,
    ])


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== line_seq_model.py self-test ===\n")

    FS   = 4000.0
    N    = int(FS * 2 / 50)    # 2 cycles at 50 Hz
    FREQ = 50.0

    test_cases = [
        ("Healthy",           0.003, 0.003, False, False),
        ("SG 3PH fault",      2.500, 0.000, True,  False),
        ("IBR SLG, lim 0.14", 0.140, 0.100, True,  True),
        ("IBR SLG, lim 0.08", 0.080, 0.100, False, True),
        ("IBR 3PH, lim 0.14", 0.140, 0.000, True,  False),
        ("IBR 3PH, lim 0.08", 0.080, 0.000, False, False),
    ]

    print(f"{'Case':<24} {'I1':>6} {'I2':>6} {'87L':>5} {'87LN':>5} "
          f"{'trip_87L':>9} {'trip_87LN':>10} {'comb':>6} {'PASS':>5}")
    print("-" * 82)

    all_pass = True
    for label, I1, I2, exp_87L, exp_87LN in test_cases:
        abc = make_abc_waveform(I1, I2, FREQ, FS, N)
        r = measure_neg_seq_diff(abc, FREQ, FS, I1_threshold=0.12, I2_threshold=0.06)

        ok = (r.trip_87L == exp_87L) and (r.trip_87LN == exp_87LN)
        if not ok:
            all_pass = False
        flag = "PASS" if ok else "FAIL"

        print(f"{label:<24} {r.I1_diff:6.4f} {r.I2_diff:6.4f} "
              f"{'YES' if exp_87L else ' no':>5} {'YES' if exp_87LN else ' no':>5} "
              f"{'YES' if r.trip_87L else ' no':>9} "
              f"{'YES' if r.trip_87LN else ' no':>10} "
              f"{'YES' if r.trip_combined else ' no':>6} {flag:>5}")

    print()
    if all_pass:
        print("ALL TESTS PASSED")
    else:
        print("SOME TESTS FAILED")
        raise SystemExit(1)
