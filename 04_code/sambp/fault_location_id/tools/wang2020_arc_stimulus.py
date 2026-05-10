"""tools/wang2020_arc_stimulus.py
====================================
Synthetic distortion-controllable HIF arc stimulus, used by the WP3.5
K06 phasor-bias measurement.  Inspired by the Wang et al. 2020
distortion-controllable arc model for renewable-penetrated
distribution networks.

WP3.5 status (P3.5)
-------------------

PSCAD is not on the dev box, so the canonical Wang-2020 model is not
runnable here.  This module provides a PYTHON-side surrogate that
captures the two phenomenological features the WP3.5 K06 acceptance
needs:

1. **Sub-cycle envelope variation** -- the arc reignites near each
   voltage zero crossing, producing an effective amplitude / phase
   modulation at twice the fundamental (and inter-cycle drift over
   longer windows).  The TFT estimator's K = 1 Taylor term is
   designed to track this.

2. **Harmonic distortion** -- arc nonlinearity injects odd harmonics
   (3rd, 5th, 7th typical, 5-15 % each).  These are far from the
   fundamental DFT bin so they don't bias the static-phasor estimator
   directly, but combined with the envelope variation they break the
   integer-cycle assumption that single-bin DFT relies on.

The ``distortion_index`` parameter in [0, 1] linearly scales both
the harmonic amplitude and the envelope-modulation depth, matching
the Wang-2020 single-knob convention.  ``distortion_index = 0`` gives
a clean sinusoid; ``distortion_index = 1`` gives the heavily distorted
arc-modulated case.

References
----------

* Wang, S. et al., "Distortion-Controllable High-Impedance Fault Arc
  Model for Renewable-Penetrated Distribution Networks", Electric
  Power Systems Research, 2020.
* Aucoin, B.M. and Russell, B.D., "Detection of Distribution High
  Impedance Faults Using Burst Noise Signals near 60 Hz", IEEE
  Transactions on Power Delivery, 2(2), 1987.
* Cassie / Mayr / Kizilcay arc-model family (Phase-4 follow-on).
"""

from __future__ import annotations

import numpy as np

HARMONIC_ORDERS = (3, 5, 7)               # odd harmonics typical of arc
HARMONIC_AMPS_AT_DI_1 = (0.10, 0.05, 0.03)  # peak at distortion_index = 1


def synthesise_voltage(
    *,
    H_true: complex,
    n_cycles: int = 1,
    fs: float = 10_000.0,
    f0: float = 50.0,
    distortion_index: float = 0.5,
    rng: np.random.Generator | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Synthesise a representative arc-modulated voltage waveform.

    Returns ``(t, v)`` where v is the synthesised real-valued voltage
    in arbitrary units (the K06 measurement is bias-relative so the
    absolute scale is irrelevant) and t is the time vector.

    The "true" phasor is ``H_true`` at ``t = 0`` (window start), so
    the static-phasor estimators (DFT and TFT-K=0) should recover
    ``H_true`` exactly when ``distortion_index = 0`` and the envelope
    variations vanish.

    Parameters
    ----------
    H_true : complex
        Underlying static-phasor "truth" at the window start.
    n_cycles : int
        Number of fundamental cycles in the window.
    fs : float
        Sample rate, Hz.  Default 10 kHz to match the WP1.1 scheme.
    f0 : float
        Fundamental, Hz.  Default 50.
    distortion_index : float in [0, 1]
        Wang-2020-style single knob.  0 = clean sinusoid;
        1 = heavily arc-modulated.
    rng : numpy.random.Generator
        Optional; not used by this surrogate (no stochastic component
        in the arc; noise is added downstream by the K06 runner).
    """
    if not 0.0 <= distortion_index <= 1.0:
        raise ValueError(
            f"distortion_index must be in [0, 1]; got {distortion_index}"
        )
    n_samples = int(round(n_cycles * fs / f0))
    t = np.arange(n_samples) / fs
    omega0 = 2.0 * np.pi * f0

    # Carrier + envelope.  The arc heating warms the channel across
    # the observation window, producing a magnitude AND phase drift
    # in the complex phasor.  At t = 0 the envelope is identity
    # (so H_true is the phasor at window start, the standard power-
    # systems convention -- single-bin DFT and Taylor-Fourier
    # estimators are then compared against the same H_true).  The
    # drift across the window is what biases the static-phasor DFT
    # and what TFT-K=1's linear Taylor term captures exactly.
    # At distortion_index = 1.0 the magnitude grows by +25 % across
    # the window and the phase walks by +0.20 rad (Wang 2020
    # Tab. III "heavy distortion" scenario).
    t_norm = (t / t[-1]) if n_samples > 1 else np.zeros_like(t)
    drift_mag = 1.0 + distortion_index * 0.25 * t_norm
    drift_phase = distortion_index * 0.20 * t_norm
    wobble = 1.0 + distortion_index * 0.03 * np.cos(2.0 * omega0 * t)
    envelope = drift_mag * wobble * np.exp(1j * drift_phase)

    fundamental = np.real(H_true * envelope * np.exp(1j * omega0 * t))

    # Harmonic content scaled by the distortion index.  Phase-randomised
    # by H_true's phase so the harmonics align with the arc trace.
    harmonic = np.zeros_like(fundamental)
    base_amp = abs(H_true)
    base_phase = np.angle(H_true)
    for order, h_amp_at_1 in zip(HARMONIC_ORDERS, HARMONIC_AMPS_AT_DI_1, strict=False):
        h_amp = h_amp_at_1 * distortion_index * base_amp
        # Each harmonic phase-locked to fundamental + small offset
        h_phase = base_phase + 0.2 * order
        harmonic += h_amp * np.cos(order * omega0 * t + h_phase)

    return t, fundamental + harmonic


def add_awgn(
    x: np.ndarray, snr_db: float, *, rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Add white Gaussian noise targeting the signal RMS at the given SNR."""
    if rng is None:
        rng = np.random.default_rng()
    if not np.isfinite(snr_db):
        return x.copy()
    rms = float(np.sqrt(np.mean(x * x)))
    sigma = rms * 10.0 ** (-snr_db / 20.0)
    return x + rng.standard_normal(x.shape) * sigma


__all__ = [
    "synthesise_voltage",
    "add_awgn",
    "HARMONIC_ORDERS",
    "HARMONIC_AMPS_AT_DI_1",
]
