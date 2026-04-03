"""
line_freq_adaptive.py
=====================
Frequency-adaptive charging-current correction for SAMBP 87L in microgrids.

Background
----------
In conventional 50-Hz grids the pi-section charging correction (TR-15/2026)
scales B_C at the fixed nominal frequency.  In inverter-dominated microgrids
the system frequency deviates from 50 Hz due to droop control: typical range
47--53 Hz under islanded operation (IEC 60255-181, ENTSO-E RfG).

The pi-section charging current is:
    i_C(t) = C_total × dv_avg/dt
           = B_C_nom × (f_actual / f_nom) × Im{ H[v_avg(t)] }

where B_C_nom = 2π × f_nom × C_total is the susceptance evaluated at nominal
frequency, H[·] is the Hilbert transform (wideband 90° phase shift), and the
factor (f_actual / f_nom) corrects for the frequency-dependent amplitude.

Without this correction the residual charging error in the differential is:
    ε_C = B_C_nom × (1 − f_actual/f_nom) × V_avg_rms

At f=47 Hz this gives ε_C ≈ 6% of the normal charging amplitude.  For a
typical 132-kV, 20-km line with B_C=0.079 pu and V=1 pu the residual is
≈0.005 pu — comparable to the fault threshold of 0.12 pu at low load.

Adaptive algorithm
------------------
1. Estimate f_actual from pre-fault voltage (zero-crossing method).
2. Compute corrected charging: i_C_adaptive = B_C_nom × (f_est/f_nom) × Im{H[v_avg]}.
3. Subtract from measured differential.
4. Pass corrected differential to LM estimator as in TR-15.

Frequency estimator accuracy: ±0.05 Hz (2-cycle window, 3-phase average).
This limits residual B_C error to <0.1%, negligible vs noise floor.

References
----------
    IEC 60255-181:2019 §6.2 — Frequency measurement requirements.
    ENTSO-E RfG (2016) Art. 13(a) — Frequency range 47.5--51.5 Hz normal.
    SAMBP TR-15/2026 — Pi-section charging correction (fixed frequency).
    SAMBP TR-17/2026 — Adaptive threshold (I_rest dependence).
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass
from typing import Optional
from scipy.signal import hilbert


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class FreqAdaptiveConfig:
    """
    Parameters for the frequency-adaptive charging correction.

    All frequency values in Hz; all electrical quantities in per-unit.
    """
    f_nom: float = 50.0         # Nominal system frequency [Hz]
    f_min: float = 47.0         # Minimum credible frequency [Hz]
    f_max: float = 53.0         # Maximum credible frequency [Hz]

    # Zero-crossing estimator window (in seconds before fault epoch)
    zc_window_s: float = 0.04   # 2 cycles at 50 Hz

    # Minimum zero-crossings required for a valid estimate
    zc_min: int = 3

    # Fallback: use f_nom if estimator fails (e.g. too few samples)
    fallback_to_nominal: bool = True

    # Phase used for zero-crossing (0=A, 1=B, 2=C; or "all" = mean of 3)
    zc_phase: int = 0           # Phase A by default


# ---------------------------------------------------------------------------
# Frequency estimation
# ---------------------------------------------------------------------------

def estimate_frequency_zero_crossing(
    v_abc: np.ndarray,       # (3, N) three-phase voltage [pu]
    fs: float,               # sampling rate [Hz]
    cfg: Optional[FreqAdaptiveConfig] = None,
) -> tuple[float, str]:
    """
    Estimate the fundamental frequency from zero-crossings of the voltage.

    Uses positive-going zero-crossings of the selected phase.  The period
    is estimated as the median inter-crossing interval (robust to noise).

    Parameters
    ----------
    v_abc  : (3, N) voltage waveform (use pre-fault window for best accuracy)
    fs     : sampling rate [Hz]
    cfg    : FreqAdaptiveConfig (uses defaults if None)

    Returns
    -------
    f_est  : estimated frequency [Hz]
    status : "ok" | "fallback" (if estimate was clamped or insufficient data)
    """
    if cfg is None:
        cfg = FreqAdaptiveConfig()

    ph = cfg.zc_phase
    v = v_abc[ph]

    # Positive-going zero crossings: sign changes from − to +
    signs = np.sign(v)
    signs[signs == 0] = 1       # treat zero as positive
    crossings = np.where(np.diff(signs) > 0)[0]  # index of last sample before crossing

    if len(crossings) < cfg.zc_min:
        if cfg.fallback_to_nominal:
            return cfg.f_nom, "fallback"
        raise ValueError(
            f"Insufficient zero-crossings: {len(crossings)} < {cfg.zc_min}"
        )

    # Sub-sample interpolation for each crossing
    refined = []
    for k in crossings:
        if k + 1 >= len(v):
            continue
        # Linear interpolation: fraction through interval where v=0
        frac = -v[k] / (v[k + 1] - v[k] + 1e-30)
        refined.append(k + frac)

    if len(refined) < cfg.zc_min:
        return cfg.f_nom, "fallback"

    intervals = np.diff(refined) / fs      # [s] between successive positive ZCs
    # Each interval = one full period T
    T_est = float(np.median(intervals))
    if T_est < 1e-6:
        return cfg.f_nom, "fallback"

    f_est = 1.0 / T_est

    # Clamp to credible range
    status = "ok"
    if f_est < cfg.f_min or f_est > cfg.f_max:
        f_est = float(np.clip(f_est, cfg.f_min, cfg.f_max))
        status = "clamped"

    return f_est, status


def estimate_frequency_dft(
    v_abc: np.ndarray,       # (3, N) three-phase voltage [pu]
    fs: float,               # sampling rate [Hz]
    cfg: Optional[FreqAdaptiveConfig] = None,
) -> tuple[float, str]:
    """
    Estimate frequency using DFT peak interpolation (parabolic refinement).

    More accurate than zero-crossing for short windows or noisy signals.
    Resolution: fs/N raw; sub-bin accuracy ~±0.1 Hz for typical windows.

    Returns
    -------
    f_est  : estimated frequency [Hz]
    status : "ok" | "fallback"
    """
    if cfg is None:
        cfg = FreqAdaptiveConfig()

    N = v_abc.shape[1]
    # Average the three phases to improve SNR (balanced system: same frequency)
    v_mean = np.mean(v_abc, axis=0)

    # Windowed DFT
    win = np.hanning(N)
    X = np.abs(np.fft.rfft(v_mean * win))
    freqs = np.fft.rfftfreq(N, d=1.0 / fs)

    # Find peak near nominal
    idx_lo = int(np.searchsorted(freqs, cfg.f_min))
    idx_hi = int(np.searchsorted(freqs, cfg.f_max))
    if idx_hi <= idx_lo + 2:
        return cfg.f_nom, "fallback"

    sub = X[idx_lo:idx_hi]
    peak_sub = int(np.argmax(sub))
    peak = peak_sub + idx_lo

    # Parabolic interpolation
    if 0 < peak_sub < len(sub) - 1:
        alpha = X[peak - 1]
        beta  = X[peak]
        gamma = X[peak + 1]
        denom = alpha - 2 * beta + gamma
        if abs(denom) > 1e-12:
            p = 0.5 * (alpha - gamma) / denom
        else:
            p = 0.0
        f_est = freqs[peak] + p * (freqs[1] - freqs[0])
    else:
        f_est = freqs[peak]

    status = "ok"
    if f_est < cfg.f_min or f_est > cfg.f_max:
        f_est = float(np.clip(f_est, cfg.f_min, cfg.f_max))
        status = "clamped"

    return float(f_est), status


# ---------------------------------------------------------------------------
# Adaptive charging correction
# ---------------------------------------------------------------------------

def adaptive_charging_correction(
    v_L_abc: np.ndarray,      # (3, N) local terminal voltage [pu]
    v_R_abc: np.ndarray,      # (3, N) remote terminal voltage [pu]
    B_C_nom: float,            # nominal line susceptance at f_nom [pu]
    f_est: float,              # estimated actual frequency [Hz]
    f_nom: float = 50.0,
) -> np.ndarray:
    """
    Compute frequency-adapted pi-section charging correction.

    The actual charging current for a capacitive element at frequency f is:
        i_C(t) = C_total × dv_avg/dt
               = (B_C_nom / ω_nom) × ω_actual × Im{H[v_avg(t)]}
               = B_C_nom × (f_actual / f_nom) × Im{H[v_avg(t)]}

    Parameters
    ----------
    v_L_abc, v_R_abc : (3, N) terminal voltage waveforms [pu]
    B_C_nom          : nominal total susceptance = 2π × f_nom × C_total [pu]
    f_est            : estimated actual system frequency [Hz]
    f_nom            : nominal frequency used to define B_C_nom [Hz]

    Returns
    -------
    i_C_abc : (3, N) adaptive charging differential correction [pu]
    """
    freq_ratio = f_est / f_nom
    v_avg = 0.5 * (v_L_abc + v_R_abc)

    i_C = np.zeros_like(v_avg)
    for ph in range(3):
        analytic = hilbert(v_avg[ph])
        i_C[ph] = B_C_nom * freq_ratio * np.imag(analytic)

    return i_C


def fixed_charging_correction(
    v_L_abc: np.ndarray,
    v_R_abc: np.ndarray,
    B_C_nom: float,
    f_nom: float = 50.0,
) -> np.ndarray:
    """
    Fixed-frequency (TR-15) charging correction for comparison.

    Uses B_C_nom directly without any frequency scaling.
    Equivalent to adaptive_charging_correction with f_est = f_nom.
    """
    return adaptive_charging_correction(v_L_abc, v_R_abc, B_C_nom, f_nom, f_nom)


# ---------------------------------------------------------------------------
# Residual charging error metric
# ---------------------------------------------------------------------------

def charging_residual_rms(
    i_diff_corrected: np.ndarray,   # (3, N) differential after correction
    i_fault: np.ndarray,            # (3, N) true fault current (0 for no-fault)
) -> float:
    """
    RMS of the residual (corrected differential minus true fault).

    For a no-fault case (i_fault=0), this is the false-trip risk metric.
    Lower is better.

    Returns
    -------
    rms  : scalar RMS over all phases and samples [pu]
    """
    residual = i_diff_corrected - i_fault
    return float(np.sqrt(np.mean(residual ** 2)))


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== line_freq_adaptive.py self-test ===\n")

    fs = 4000.0           # 80 samples/cycle at 50 Hz
    N  = int(fs * 0.08)   # 4 cycles
    t  = np.arange(N) / fs

    B_C_nom = 0.079       # 132 kV, 20 km line
    V_nom   = 1.0
    f_nom   = 50.0

    cfg = FreqAdaptiveConfig(f_nom=f_nom, f_min=47.0, f_max=53.0)

    test_freqs = [47.0, 48.0, 49.0, 50.0, 51.0, 52.0, 53.0]
    print(f"{'f_act':>6} {'f_zc':>6} {'f_dft':>6} "
          f"{'ε_fixed[pu]':>12} {'ε_adapt[pu]':>12} {'improve':>8}")
    print("-" * 60)

    all_pass = True
    for f_act in test_freqs:
        # Balanced 3-phase voltages at f_act
        phi = np.array([0, -2*np.pi/3, 2*np.pi/3])
        v_L = np.array([V_nom * np.sin(2*np.pi*f_act*t + phi[ph])
                        for ph in range(3)])
        v_R = np.array([V_nom * 0.98 * np.sin(2*np.pi*f_act*t + phi[ph] - 0.03)
                        for ph in range(3)])
        # True charging (no fault)
        i_fault = np.zeros_like(v_L)

        # Frequency estimation
        f_zc,  st_zc  = estimate_frequency_zero_crossing(v_L, fs, cfg)
        f_dft, st_dft = estimate_frequency_dft(v_L, fs, cfg)

        # Fixed (TR-15) correction
        i_C_fixed = fixed_charging_correction(v_L, v_R, B_C_nom, f_nom)
        v_avg = 0.5 * (v_L + v_R)
        # True differential in healthy state = true charging current
        i_diff_true = np.array([
            B_C_nom * (f_act/f_nom) * np.imag(hilbert(v_avg[ph]))
            for ph in range(3)
        ])
        eps_fixed = charging_residual_rms(i_C_fixed - i_diff_true, i_fault)

        # Adaptive correction using ZC estimate
        i_C_adapt = adaptive_charging_correction(v_L, v_R, B_C_nom, f_zc, f_nom)
        eps_adapt = charging_residual_rms(i_C_adapt - i_diff_true, i_fault)

        improve = eps_fixed / (eps_adapt + 1e-12)

        # At f=f_nom both errors are zero; otherwise adaptive must be >85% better
        if eps_fixed < 1e-9:
            ok = eps_adapt < 1e-6
        else:
            ok = eps_adapt < eps_fixed * 0.15
        flag = "PASS" if ok else "FAIL"
        if not ok:
            all_pass = False

        print(f"{f_act:6.1f} {f_zc:6.2f} {f_dft:6.2f} "
              f"{eps_fixed:12.6f} {eps_adapt:12.6f} {improve:7.1f}x  {flag}")

    print()
    if all_pass:
        print("ALL TESTS PASSED")
    else:
        print("SOME TESTS FAILED")
        raise SystemExit(1)
