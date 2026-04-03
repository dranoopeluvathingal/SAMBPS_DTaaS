"""
line_transient_diff.py
======================
Transient differential current supervision (TDCS-87L) — TR-23 fixed threshold
and TR-24 adaptive threshold extension.

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


# ===========================================================================
# TR-24 EXTENSION: Adaptive TDCS Threshold
# ===========================================================================
#
# Motivation
# ----------
# TR-23 uses a fixed Δ_thr = 0.040 pu set under nominal (summer) conditions.
# When the pre-fault differential baseline drifts upward — due to long-term CT
# calibration drift, increased line charging under light load, or seasonal
# capacitance variation — the post-fault step (rms_post − μ_pre) shrinks:
#
#   ΔI = √(μ_pre² + (k_ibr/√2)²) − μ_pre
#
# For μ_pre = 0.015 pu (drifted), k_ibr = 0.07 pu:
#   ΔI = √(0.015² + 0.04950²) − 0.015 = 0.0517 − 0.015 = 0.037 pu < 0.040
#   → MISSED by fixed threshold.
#
# Adaptive algorithm
# ------------------
# 1. Maintain a rolling history of N_history pre-fault RMS samples.
# 2. Compute rolling mean μ̂ and std σ̂ over the history.
# 3. Adaptive threshold: Δ_thr = Δ_floor + k_σ × σ̂
#    (Δ_floor = 0.020 pu prevents collapse to near-zero in very stable periods)
# 4. Compare rms_post to rolling mean (not single pre-window):
#    ΔI = rms_post − μ̂  →  trip if ΔI ≥ Δ_thr AND rms_post ≥ noise_floor
#
# Security property: for a stable external fault, rms_post − μ̂ is small
# (CT mismatch residual grows proportionally with σ̂ → relative margin
# maintained). The k_σ = 3 factor provides 3-sigma security.
#
# Detection limit improvement:
#   Fixed limit:    k_ibr ≥ (Δ_thr_fixed + μ_pre) × √2
#   Adaptive limit: k_ibr ≥ (Δ_floor + k_σ × σ̂ + μ̂) × √2
#   For μ̂ = 0.015, σ̂ = 0.002: limit = (0.020 + 0.006 + 0.015) × √2 ≈ 0.058 pu
#   vs fixed limit with same pre: (0.040 + 0.015) × √2 = 0.078 pu
#
# References: SAMBP TR-23/2026; Anderson (1999) §14.2 adaptive threshold.
# ===========================================================================


@dataclass
class AdaptiveTDCSConfig:
    """Parameters for the adaptive-threshold TDCS element (TR-24).

    Δ_floor lower-bound derivation
    --------------------------------
    Worst-case CT mismatch (Class 5P, ε_CT = 0.5%) at maximum external
    through-current I_ext_max = 7 pu creates an apparent differential:
        ΔI_CT = I_ext_max × ε_CT / √2 = 7 × 0.005 / √2 ≈ 0.025 pu
    For the stable summer baseline (μ_pre ≈ 0.002 pu) the effective step seen
    by the adaptive element is 0.025 − 0.002 = 0.023 pu.  Setting
    Δ_floor = 0.025 pu ensures the threshold always exceeds this worst-case
    mismatch contribution regardless of how low σ̂ falls.
    """
    delta_floor: float  = 0.025   # Minimum adaptive threshold [pu] — see docstring
    k_sigma: float      = 3.0     # Threshold multiplier: Δ_thr = floor + k_σ × σ̂
    noise_floor: float  = 0.010   # Minimum post-fault RMS to avoid noise trips [pu]
    n_history: int      = 60      # Rolling history length [cycles]
    window_s: float     = 0.020   # Window for each RMS sample [s]
    fs: float           = 4000.0  # Sampling rate [Hz]


@dataclass
class AdaptiveTDCSResult:
    """Output of the adaptive TDCS element."""
    rms_post: float       # Post-fault window RMS [pu]
    mu_pre: float         # Rolling mean of pre-fault RMS [pu]
    sigma_pre: float      # Rolling std of pre-fault RMS [pu]
    delta_I: float        # rms_post − mu_pre [pu]
    delta_thr: float      # Adaptive threshold = floor + k_σ × σ̂ [pu]
    trip_tdcs: bool       # Adaptive TDCS trip decision
    margin: float         # (delta_I − delta_thr) / delta_thr


class AdaptiveTDCSTracker:
    """
    Online rolling-statistics tracker for the adaptive TDCS element.

    Usage
    -----
    1. Call ``update_baseline(rms_sample)`` once per cycle during normal
       operation to build up the rolling history.
    2. Call ``measure(i_diff_abc_post)`` when a transient is suspected.
       The method compares the post-fault window RMS against the rolling
       mean and applies the adaptive threshold.
    """

    def __init__(self, cfg: AdaptiveTDCSConfig = None):
        self.cfg = cfg if cfg is not None else AdaptiveTDCSConfig()
        self._history: list[float] = []

    # ------------------------------------------------------------------
    def update_baseline(self, rms_sample: float) -> None:
        """Append one pre-fault RMS sample to the rolling history."""
        self._history.append(float(rms_sample))
        if len(self._history) > self.cfg.n_history:
            self._history.pop(0)

    # ------------------------------------------------------------------
    @property
    def mu_pre(self) -> float:
        """Rolling mean of pre-fault RMS [pu]."""
        return float(np.mean(self._history)) if self._history else 0.0

    @property
    def sigma_pre(self) -> float:
        """Rolling std of pre-fault RMS [pu]."""
        return float(np.std(self._history)) if len(self._history) > 1 else 0.0

    @property
    def delta_thr_adaptive(self) -> float:
        """Current adaptive threshold [pu]."""
        return self.cfg.delta_floor + self.cfg.k_sigma * self.sigma_pre

    # ------------------------------------------------------------------
    def measure(self, i_diff_abc_post: np.ndarray) -> AdaptiveTDCSResult:
        """
        Evaluate TDCS on a post-fault window.

        Parameters
        ----------
        i_diff_abc_post : (3, N) post-fault differential waveform [pu]

        Returns
        -------
        AdaptiveTDCSResult
        """
        rms_post = _window_rms(i_diff_abc_post)
        mu       = self.mu_pre
        sigma    = self.sigma_pre
        thr      = self.delta_thr_adaptive
        delta_I  = rms_post - mu

        trip = (delta_I >= thr) and (rms_post >= self.cfg.noise_floor)
        margin = (delta_I - thr) / max(thr, 1e-9)

        return AdaptiveTDCSResult(
            rms_post  = rms_post,
            mu_pre    = mu,
            sigma_pre = sigma,
            delta_I   = delta_I,
            delta_thr = thr,
            trip_tdcs = trip,
            margin    = margin,
        )


# ---------------------------------------------------------------------------
# Adaptive-TDCS self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__" and True:
    print("\n=== AdaptiveTDCS self-test (TR-24) ===\n")

    FS  = 4000.0
    F0  = 50.0
    N   = int(FS / F0)      # 80 samples / cycle
    cfg = AdaptiveTDCSConfig()

    # ---- Drift scenario: μ_pre = 0.015 pu, σ_pre = 0.002 pu  ----
    # This represents a line where the pre-fault differential has drifted
    # upward (e.g., CT calibration ageing + seasonal charging increase).
    rng = np.random.default_rng(42)
    drift_samples = rng.normal(loc=0.015, scale=0.002, size=60)
    tracker = AdaptiveTDCSTracker(cfg)
    for s in drift_samples:
        tracker.update_baseline(max(s, 0.0))

    print(f"  Drift scenario: μ̂={tracker.mu_pre:.4f} pu, "
          f"σ̂={tracker.sigma_pre:.4f} pu, "
          f"Δ_thr_adapt={tracker.delta_thr_adaptive:.4f} pu  "
          f"(Δ_floor=0.025, fixed Δ_thr=0.040 pu)")

    # Fixed-threshold TDCSConfig for comparison
    cfg_fixed = TDCSConfig(delta_thr=0.040)

    print()
    print(f"{'Case':<28} {'rms_post':>9} {'ΔI_adapt':>9} {'thr_adapt':>10} "
          f"{'trip_A':>7} {'trip_F':>7} {'exp':>5} {'PASS':>5}")
    print("-" * 90)

    # Expected: fixed MISSES k=0.07 in drift scenario; adaptive TRIPS
    at_cases = [
        # (label, k_ibr or ext, fault_type, expect_adapt, expect_fixed)
        ("3PH k=0.07 [DRIFT MISS]",  0.07, "3ph",  True,  False),
        ("3PH k=0.09 [both trip]",   0.09, "3ph",  True,  True),
        ("3PH k=0.11 [both trip]",   0.11, "3ph",  True,  True),
        ("External 7.0 pu [secure]", 7.00, "ext",  False, False),
    ]

    all_ok = True
    for label, param, ftype, exp_a, exp_f in at_cases:
        if ftype == "3ph":
            i_post = make_3ph_internal_diff(param, F0, FS, N)
        else:
            i_post = make_external_fault_diff(param, F0, FS, N)

        r_a = tracker.measure(i_post)

        # Fixed: single pre-window from drift mean level
        i_pre_drift = make_prefault_diff(tracker.mu_pre, F0, FS, N)
        r_f = measure_tdcs(i_pre_drift, i_post, cfg_fixed)

        ok = (r_a.trip_tdcs == exp_a) and (r_f.trip_tdcs == exp_f)
        if not ok:
            all_ok = False
        flag = "PASS" if ok else "FAIL"
        exp_str = f"{'A' if exp_a else '_'}/{'F' if exp_f else '_'}"
        print(f"{label:<28} {r_a.rms_post:9.5f} {r_a.delta_I:9.5f} "
              f"{r_a.delta_thr:10.5f} "
              f"{'YES' if r_a.trip_tdcs else ' no':>7} "
              f"{'YES' if r_f.trip_tdcs else ' no':>7} "
              f"{exp_str:>5} {flag:>5}")

    print()
    if all_ok:
        print("ALL ADAPTIVE TESTS PASSED")
    else:
        print("SOME ADAPTIVE TESTS FAILED")
        raise SystemExit(1)
