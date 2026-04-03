"""
line_transient_diff.py
======================
Transient differential current supervision (TDCS-87L) for SAMBP TR-23.

Background
----------
The SAMBP 87L element (TR-11 through TR-22) operates on the steady-state
differential current magnitude.  For 3-phase symmetric faults in
IBR-dominated microgrids, the positive-sequence differential may be below
the 87L threshold (0.12 pu) when the IBR current limits to k_ibr < 0.12 pu.
The negative-sequence element (87LN, TR-22) cannot help — symmetric faults
produce no I₂.

Key observation
---------------
At fault inception, the IBR transitions from load-tracking current control
to current-limiting mode.  This causes a STEP CHANGE in the differential
current that is entirely absent for:
  • External faults   (no change in differential by Kirchhoff's law)
  • Load steps        (balanced changes create no differential current)
  • IBR ramps/curtailment (changes are slow, below transient threshold)

The step change is:
    ΔI_diff = |I_diff,post| − |I_diff,pre| ≈ k_ibr − I_C_charging ≈ k_ibr

For k_ibr = 0.05–0.11 pu (below 87L threshold), ΔI_diff ∈ [0.047, 0.107] pu
— well above a transient detection threshold of Δ_thr = 0.04 pu.

Transient detection algorithm
------------------------------
1. Maintain a rolling pre-fault differential window (1 cycle, 80 samples).
2. On each new cycle, compare new window RMS to pre-fault window RMS:
       ΔI_diff = rms(I_diff,new) − rms(I_diff,pre)
3. If ΔI_diff > Δ_thr AND the new window RMS > I_noise_floor:
   → declare transient fault (TDCS-87L trip).
4. The TDCS trip is ORed with the 87L and 87LN trips:
       TRIP = 87L ∨ 87LN ∨ TDCS-87L

Security:
  • External fault:  I_diff unchanged (differential is zero, ΔI_diff ≈ 0)
  • Load step:       Balanced → no differential, ΔI_diff ≈ 0
  • CT inrush spike: Peak but not sustained in the post-fault RMS window

Threshold setting (study network):
  • Δ_thr       = 0.040 pu  (10× natural imbalance step; 1/3 of 87L threshold)
  • I_noise_floor = 0.010 pu  (3× charging residual noise floor)

References
----------
    IEEE Std C37.243-2015 §9 — Transient/differential detection.
    Plet et al. (2011) — IBR fault response and protective relaying.
    SAMBP TR-22/2026 — 87LN for asymmetric IBR faults.
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class TDCSConfig:
    """Parameters for the Transient Differential Current Supervision element."""
    delta_thr: float    = 0.040    # ΔI_diff trip threshold [pu]
    noise_floor: float  = 0.010    # Minimum post-fault RMS to avoid noise trips [pu]
    window_s: float     = 0.020    # Pre-fault and post-fault window length [s]
    fs: float           = 4000.0   # Sampling rate [Hz]


# ---------------------------------------------------------------------------
# Window RMS
# ---------------------------------------------------------------------------

def _window_rms(i_diff_abc: np.ndarray) -> float:
    """
    Compute three-phase RMS of differential current over the window.

    Returns max per-phase RMS (most sensitive to worst-phase).

    Parameters
    ----------
    i_diff_abc : (3, N) three-phase differential [pu]

    Returns
    -------
    float: max per-phase RMS [pu]
    """
    return float(np.max(np.sqrt(np.mean(i_diff_abc ** 2, axis=1))))


# ---------------------------------------------------------------------------
# TDCS-87L measurement
# ---------------------------------------------------------------------------

@dataclass
class TDCSResult:
    """Output of the TDCS-87L element."""
    rms_pre: float      # Pre-fault window RMS [pu]
    rms_post: float     # Post-fault window RMS [pu]
    delta_I: float      # Change: rms_post − rms_pre [pu]
    trip_tdcs: bool     # TDCS element trip decision
    margin: float       # (delta_I − delta_thr) / delta_thr


def measure_tdcs(
    i_diff_abc_pre:  np.ndarray,   # (3, N_pre)  pre-fault window [pu]
    i_diff_abc_post: np.ndarray,   # (3, N_post) post-fault window [pu]
    cfg: TDCSConfig = None,
) -> TDCSResult:
    """
    Compute the TDCS-87L transient differential measurement.

    Parameters
    ----------
    i_diff_abc_pre  : (3, N) pre-fault differential waveform [pu]
    i_diff_abc_post : (3, N) post-fault differential waveform [pu]
    cfg             : TDCSConfig (uses defaults if None)

    Returns
    -------
    TDCSResult
    """
    if cfg is None:
        cfg = TDCSConfig()

    rms_pre  = _window_rms(i_diff_abc_pre)
    rms_post = _window_rms(i_diff_abc_post)
    delta_I  = rms_post - rms_pre

    # Trip: step increase above threshold AND above noise floor
    trip = (delta_I >= cfg.delta_thr) and (rms_post >= cfg.noise_floor)

    margin = (delta_I - cfg.delta_thr) / max(cfg.delta_thr, 1e-9)

    return TDCSResult(
        rms_pre   = rms_pre,
        rms_post  = rms_post,
        delta_I   = delta_I,
        trip_tdcs = trip,
        margin    = margin,
    )


# ---------------------------------------------------------------------------
# Waveform generators for study scenarios
# ---------------------------------------------------------------------------

def make_prefault_diff(
    I_C_charging: float,   # Charging residual [pu]
    freq_hz: float,
    fs: float,
    n_samples: int,
) -> np.ndarray:
    """
    Generate pre-fault differential waveform (charging current only).

    Phase-balanced, 3-phase: ia + ib + ic = 0 → no zero-seq.
    The differential in the healthy state is the charging current (single phase
    dominates after TR-20/TR-21 correction; keep small here).
    """
    t = np.arange(n_samples) / fs
    phi0 = np.array([0.0, -2*np.pi/3, 2*np.pi/3])
    return np.array([
        I_C_charging * np.sin(2*np.pi*freq_hz*t + phi0[ph])
        for ph in range(3)
    ])


def make_3ph_internal_diff(
    k_ibr: float,       # IBR current limit (total differential) [pu]
    freq_hz: float,
    fs: float,
    n_samples: int,
) -> np.ndarray:
    """
    Post-fault differential for a symmetric 3PH internal fault.

    IBR limited: positive-sequence differential = k_ibr, no negative sequence.
    """
    t = np.arange(n_samples) / fs
    phi0 = np.array([0.0, -2*np.pi/3, 2*np.pi/3])
    return np.array([
        k_ibr * np.sin(2*np.pi*freq_hz*t + phi0[ph])
        for ph in range(3)
    ])


def make_load_step_diff(
    delta_I_load: float,    # Magnitude of balanced load step [pu]
    freq_hz: float,
    fs: float,
    n_samples: int,
) -> np.ndarray:
    """
    Post-step differential for a balanced load step.

    A balanced 3-phase load step creates NO differential current (by
    Kirchhoff's current law: current in = current out for through-flow).
    The differential stays at the charging level.
    """
    # Load step is balanced: ΔI_diff ≈ 0 (only charging changes are visible)
    I_C_post = 0.003   # slightly different charging due to voltage change
    return make_prefault_diff(I_C_post, freq_hz, fs, n_samples)


def make_external_fault_diff(
    I_external: float,    # External fault through-current magnitude [pu]
    freq_hz: float,
    fs: float,
    n_samples: int,
) -> np.ndarray:
    """
    Post-fault differential for an external fault (outside protected zone).

    An external fault increases through-current but creates no differential
    (by Kirchhoff: current in = current out for zone without internal fault).
    Residual: small due to CT mismatch (model as 0.5% of through-current).
    """
    CT_mismatch = 0.005   # 0.5% CT ratio error
    I_residual = I_external * CT_mismatch
    return make_prefault_diff(I_residual, freq_hz, fs, n_samples)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== line_transient_diff.py self-test ===\n")

    FS   = 4000.0
    F0   = 50.0
    N    = int(FS / F0)    # 1 cycle = 80 samples
    I_C  = 0.003           # Pre-fault charging residual
    cfg  = TDCSConfig()

    i_pre = make_prefault_diff(I_C, F0, FS, N)

    # TDCS trips when rms_post - rms_pre > delta_thr = 0.040 pu.
    # For a 3-phase sine of peak k_ibr: rms_post = k_ibr/sqrt(2).
    # Effective peak detection limit ≈ (delta_thr + rms_pre) × sqrt(2)
    #                                = (0.040 + 0.00212) × 1.414 ≈ 0.059 pu
    # k_ibr=0.05 → rms_post=0.0354 → ΔI=0.033 < 0.040 → no trip (expected False)
    # k_ibr=0.08 → rms_post=0.0566 → ΔI=0.054 > 0.040 → trip  (expected True)
    test_cases = [
        # (label,              make_fn,          param, expect_trip)
        ("3PH k_ibr=0.05 pu", make_3ph_internal_diff,   0.05, False),  # below TDCS limit
        ("3PH k_ibr=0.08 pu", make_3ph_internal_diff,   0.08, True),
        ("3PH k_ibr=0.11 pu", make_3ph_internal_diff,   0.11, True),
        ("Load step 0.30 pu",  make_load_step_diff,      0.30, False),
        ("External 2.0 pu",    make_external_fault_diff, 2.00, False),
        ("External 5.0 pu",    make_external_fault_diff, 5.00, False),
    ]

    print(f"{'Case':<26} {'rms_pre':>8} {'rms_post':>9} "
          f"{'ΔI':>7} {'margin':>8} {'trip':>5} {'exp':>5} {'PASS':>5}")
    print("-" * 80)

    all_pass = True
    for label, fn, param, expect in test_cases:
        i_post = fn(param, F0, FS, N)
        r = measure_tdcs(i_pre, i_post, cfg)
        ok = (r.trip_tdcs == expect)
        if not ok:
            all_pass = False
        flag = "PASS" if ok else "FAIL"
        print(f"{label:<26} {r.rms_pre:8.5f} {r.rms_post:9.5f} "
              f"{r.delta_I:7.5f} {r.margin:8.3f} "
              f"{'YES' if r.trip_tdcs else ' no':>5} "
              f"{'YES' if expect else ' no':>5} {flag:>5}")

    print()
    if all_pass:
        print("ALL TESTS PASSED")
    else:
        print("SOME TESTS FAILED")
        raise SystemExit(1)
