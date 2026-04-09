"""
crowbar_cusum.py
=================
SAMBP TR-56/2026 — CUSUM-based crowbar firing detector for DFIG 87L/87G.

Physical basis
--------------
When the DFIG crowbar fires, the rotor circuit transitions from RSC-controlled
to resistive.  The stator current gains a natural response component at the
slip frequency ω_slip = s × ω₀.  Before crowbar firing the band power at
ω_slip is at the noise floor; after firing it jumps by typically 10--30 dB.

The CUSUM (Page 1954) detector monitors the short-window power spectral
density in the slip-frequency band and raises an alarm when the cumulative
evidence of a level increase exceeds a threshold h.

Algorithm
---------
  1. Initialise pre-fault PSD estimate P₀ from a pre-event reference window.
  2. At each sliding window k (step Δt_step, length T_win):
       P_k ← band-power in [ω_slip − Δω, ω_slip + Δω]
       g_k ← max(0, g_{k-1} + P_k − P₀ − K)
     If g_k ≥ h: alarm → t_cb estimate = k × Δt_step
  3. Return t_cb_est and the CUSUM score series for diagnostic plotting.

Parameter calibration (TR-56 simulation study):
  K = 0.5 × (P_post − P_pre)   ← half-step reference (Wald optimal)
  h = K × n_alarm               ← threshold for ≤ 2 cycle detection at 50 Hz
  Δω = 0.3 × ω_slip_max         ← band covers slip ±30% of max

Slip range: |ω_slip| ∈ [0.03×ω₀, 0.35×ω₀] = [9.4, 110] rad/s at 50 Hz.

When slip is unknown (typical case): the detector sweeps the full
[ω_slip_min, ω_slip_max] band as a single broadband monitor.  This is
conservative (wider band → more noise) but avoids needing a slip estimate
before detection.

Interface
---------
    CUSUMConfig     — detector configuration dataclass
    CUSUMState      — running state (g, baseline P0)
    cusum_update(P_k, state, cfg) → (alarm, new_state)
    estimate_band_power(i_win, fs, omega_lo, omega_hi) → float
    run_crowbar_detection(i_diff, fs, cfg) → CUSUMResult
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class CUSUMConfig:
    """Parameters for CUSUM crowbar detector."""
    # Frequency band [rad/s]
    omega_slip_min: float = 9.4    # 0.03 × 2π × 50 rad/s
    omega_slip_max: float = 110.0  # 0.35 × 2π × 50 rad/s
    # Window and step
    # 2-cycle windows: Hanning main lobe ~2 Hz wide → negligible 50 Hz leakage
    # into slip band [1.5, 17.5 Hz]. 1-cycle (20 samples) gives 100 Hz main
    # lobe that floods the slip band with leakage.
    win_cycles:     float = 2.0    # analysis window length [cycles]
    step_cycles:    float = 0.50   # step size [cycles] → 10 ms at 50 Hz
    freq_hz:        float = 50.0   # power system frequency
    fs:             float = 1000.0 # sampling rate [Hz]
    # CUSUM parameters
    K_factor:       float = 0.5    # half-step reference factor (Wald-optimal)
    h_cycles:       float = 1.5    # alarm threshold in units of K (≤2 cycles)
    # Pre-event baseline
    n_baseline_wins: int  = 4      # number of windows used to estimate P0


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

@dataclass
class CUSUMState:
    """Running CUSUM state — one instance per protection cycle."""
    g:         float = 0.0          # current CUSUM score
    P0:        float = 0.0          # baseline band power
    K:         float = 1.0          # reference value
    h:         float = 5.0          # alarm threshold
    n_init:    int   = 0            # windows used in baseline estimate
    baseline_P_sum: float = 0.0     # accumulator for baseline
    alarm:     bool  = False
    t_alarm:   Optional[float] = None


# ---------------------------------------------------------------------------
# Band-power estimator
# ---------------------------------------------------------------------------

def estimate_band_power(
    i_win: np.ndarray,
    fs: float,
    omega_lo: float,
    omega_hi: float,
) -> float:
    """
    Compute the PSD integral in [omega_lo, omega_hi] rad/s via Welch-like
    single-window FFT.

    Parameters
    ----------
    i_win    : (N_win,) windowed signal [pu]
    fs       : sampling rate [Hz]
    omega_lo : lower band edge [rad/s]
    omega_hi : upper band edge [rad/s]

    Returns
    -------
    Band power [pu²] (sum of squared DFT magnitudes in band)
    """
    N    = len(i_win)
    win  = np.hanning(N)
    # Zero-pad to at least 2048 points so frequency resolution ≤ fs/2048.
    # At fs=1000 Hz this gives Δf ≤ 0.49 Hz, resolving slip bands down to ~1 Hz.
    # Zero-padding does not add spectral resolution beyond 1/T_win, but it
    # ensures that every frequency in [omega_lo, omega_hi] maps to at least
    # one DFT bin for power accumulation.
    N_fft = max(2048, 1 << (N - 1).bit_length() + 2)
    F    = np.fft.rfft(i_win * win, n=N_fft)
    freq = np.fft.rfftfreq(N_fft, d=1.0 / fs)   # [Hz]

    # Convert rad/s → Hz for comparison
    f_lo = omega_lo / (2 * np.pi)
    f_hi = omega_hi / (2 * np.pi)

    mask = (freq >= f_lo) & (freq <= f_hi)
    # Normalise by N (not N_fft) to give physical power in pu²
    return float(np.sum(np.abs(F[mask]) ** 2) * 2.0 / N**2)


# ---------------------------------------------------------------------------
# CUSUM update
# ---------------------------------------------------------------------------

def cusum_update(
    P_k:   float,
    state: CUSUMState,
    cfg:   CUSUMConfig,
    t_k:   float = 0.0,
) -> CUSUMState:
    """
    One-step CUSUM update.

    If still in baseline phase (n_init < n_baseline_wins), accumulate P0.
    Once baseline is established, run the CUSUM test.
    """
    if state.alarm:
        return state   # latch: once fired, keep state

    if state.n_init < cfg.n_baseline_wins:
        # Baseline accumulation
        state.baseline_P_sum += P_k
        state.n_init += 1
        if state.n_init == cfg.n_baseline_wins:
            state.P0 = state.baseline_P_sum / cfg.n_baseline_wins
            # K = half the expected jump (calibrated from simulations)
            # Default: assume post-crowbar PSD ≈ 10× baseline → jump = 9×P0
            state.K  = cfg.K_factor * 9.0 * state.P0
            state.K  = max(state.K, 1e-12)   # guard against zero baseline
            state.h  = cfg.h_cycles * state.K
        return state

    # CUSUM accumulation
    state.g = max(0.0, state.g + P_k - state.P0 - state.K)

    if state.g >= state.h:
        state.alarm   = True
        state.t_alarm = t_k

    return state


# ---------------------------------------------------------------------------
# Convenience: run full detection on a waveform
# ---------------------------------------------------------------------------

@dataclass
class CUSUMResult:
    """Output of run_crowbar_detection."""
    alarm:        bool
    t_cb_est:     Optional[float]  # estimated crowbar time [s], None if no alarm
    g_series:     np.ndarray       # CUSUM score at each step
    t_series:     np.ndarray       # time of each window centre [s]
    P_series:     np.ndarray       # band power at each step
    P0:           float            # estimated baseline power
    K:            float            # reference value used


def run_crowbar_detection(
    i_diff: np.ndarray,
    fs:     float,
    cfg:    Optional[CUSUMConfig] = None,
    t0:     float = 0.0,
) -> CUSUMResult:
    """
    Run CUSUM crowbar detector on the differential current waveform.

    Parameters
    ----------
    i_diff : (N,) measured differential current [pu]
    fs     : sampling rate [Hz]
    cfg    : detector configuration (None = defaults)
    t0     : start time of the waveform [s]

    Returns
    -------
    CUSUMResult with alarm flag, estimated crowbar time, and diagnostic series
    """
    if cfg is None:
        cfg = CUSUMConfig(fs=fs)

    N_win  = int(cfg.win_cycles  * fs / cfg.freq_hz)
    N_step = max(1, int(cfg.step_cycles * fs / cfg.freq_hz))

    state = CUSUMState()
    g_list, t_list, P_list = [], [], []

    k = 0
    while k + N_win <= len(i_diff):
        i_win = i_diff[k : k + N_win]
        t_cen = t0 + (k + N_win // 2) / fs

        P_k = estimate_band_power(
            i_win, fs, cfg.omega_slip_min, cfg.omega_slip_max
        )

        state = cusum_update(P_k, state, cfg, t_k=t_cen)

        g_list.append(state.g)
        t_list.append(t_cen)
        P_list.append(P_k)

        if state.alarm:
            break

        k += N_step

    return CUSUMResult(
        alarm     = state.alarm,
        t_cb_est  = state.t_alarm,
        g_series  = np.array(g_list),
        t_series  = np.array(t_list),
        P_series  = np.array(P_list),
        P0        = state.P0,
        K         = state.K,
    )


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    fs   = 1000.0
    freq = 50.0
    t    = np.arange(0, 0.30, 1.0 / fs)
    N    = len(t)

    # Synthesise DFIG differential current: crowbar fires at t=0.10s
    t_cb_true = 0.10
    s_true    = 0.12   # 12% slip
    omega_s   = s_true * 2 * np.pi * freq   # 37.7 rad/s

    i_diff = np.zeros(N)
    for n, tn in enumerate(t):
        t_rel = max(tn - t_cb_true, 0.0)
        if tn < t_cb_true:
            # Pre-crowbar: IBR-like
            i_diff[n] = 1.0 * np.sin(2 * np.pi * freq * tn)
        else:
            # Post-crowbar: fundamental + slip-frequency natural response + DC
            i_diff[n] = (0.70 * np.sin(2 * np.pi * freq * tn - 0.2)
                         + 0.40 * np.exp(-t_rel / 0.08) * np.sin(omega_s * t_rel + 0.5)
                         + 0.20 * np.exp(-t_rel / 0.08))

    i_diff += 0.005 * np.random.randn(N)

    cfg = CUSUMConfig(fs=fs, freq_hz=freq,
                      win_cycles=2.0, step_cycles=0.50,
                      K_factor=0.5, h_cycles=1.5,
                      n_baseline_wins=4)

    result = run_crowbar_detection(i_diff, fs, cfg, t0=0.0)

    print(f"[CUSUM]  alarm={result.alarm}  "
          f"t_cb_est={result.t_cb_est:.3f}s  "
          f"(true={t_cb_true:.3f}s)  "
          f"error={abs(result.t_cb_est - t_cb_true)*1000:.1f}ms")
    assert result.alarm, "CUSUM must detect crowbar"
    assert abs(result.t_cb_est - t_cb_true) < 0.04, \
        f"Crowbar time error {abs(result.t_cb_est-t_cb_true)*1000:.0f}ms > 40ms"

    # Test: no crowbar (pure IBR, no slip-frequency component)
    i_no_cb = 1.0 * np.sin(2 * np.pi * freq * t) + 0.005 * np.random.randn(N)
    result2  = run_crowbar_detection(i_no_cb, fs, cfg)
    print(f"[CUSUM]  No-crowbar:  alarm={result2.alarm}  [expected False]")
    assert not result2.alarm, "Pure IBR current must NOT trigger crowbar alarm"

    print("crowbar_cusum self-test PASSED.")
