"""faultloc_taylor_fourier.py
==============================
First-order Taylor-Fourier (TFT) phasor estimator for the SAMBPS-DTaaS
Fault-Location Identification project.

WP3.5 (P3.5) implementation.

Why TFT
-------

The single-bin DFT (used through Phase 1 / Phase 2) is the
maximum-likelihood phasor estimator for a STATIC sinusoid in white
Gaussian noise.  Under HIF arc modulation the phasor is
non-stationary -- amplitude and phase drift within the observation
window because of arc reignition / extinction harmonics -- and the
single-bin DFT picks up a bias that is often comparable to or larger
than the noise term it is meant to combat.

The Taylor-Fourier transform (Platas-Garza & de la O Serna 2010 IEEE
TIM 59(7); 2011 IEEE TIM 60(3)) extends the static-phasor estimator
to a Kth-order Taylor series in time around the window centre:
::

    H(t) = sum_{k=0}^{K} (1/k!) (d^k H/dt^k) (t - t0)^k.

For ``K = 1`` (this module's default) the model captures the linear
time variation of the complex envelope, which is the leading
non-stationary term under arc modulation; higher K trade
robustness for variance and are not required for the WP3.5 K06
acceptance.

Algorithm
---------

For a real observed signal v[n] = Re{ H(t_n) * exp(j 2 pi f0 t_n) }
sampled at t_n = n / fs, n = 0 .. N-1, the TFT model expanded as a
real linear combination of basis functions is
::

    v[n] = a0 cos(w0 t_n) + b0 sin(w0 t_n)
         + a1 t_n cos(w0 t_n) + b1 t_n sin(w0 t_n) + ...

(the t_n are centred so the LS problem is well-conditioned).
Stacking yields v = Phi * theta with Phi an N x 2(K+1) basis matrix;
LS solution theta = pinv(Phi) * v gives:

* (a0, b0) = (Re H, -Im H) at t = t0,
* (a1, b1) = (Re dH/dt, -Im dH/dt),
* ... up to order K.

The complex phasor and its first time-derivative are then
H = a0 - j b0,  dH/dt = a1 - j b1.

References
----------

* Platas-Garza, M.A. and de la O Serna, J.A., "Dynamic Phasor and
  Frequency Estimates Through Maximally Flat Differentiators", IEEE
  Transactions on Instrumentation and Measurement, vol. 59, no. 7,
  pp. 1803-1811, 2010.  doi:10.1109/TIM.2009.2030921.
* Platas-Garza, M.A. and de la O Serna, J.A., "Polynomial Implementation
  of the Taylor-Fourier Transform for Harmonic Analysis", IEEE
  Transactions on Instrumentation and Measurement, vol. 60, no. 3,
  pp. 989-994, 2011.  doi:10.1109/TIM.2010.2058852.
* Villaverde, A.F. et al., "STRIKE-GOLDD 4.0: User-Friendly,
  Efficient Analysis of Structural Identifiability and
  Observability", arXiv:2410.06984, 2024 (referenced by
  adaptation/faultloc_identifiability_check.py).

Public API
----------

* ``tft_phasor(v_t, fs, f0, K=1)`` -> (V_phasor: complex, dV_dt: complex)
* ``tft_phasor_batch(V_array, fs, f0, K=1)`` -> arrays of phasors
* ``H_meas_from_waveforms_tft(v, i, fs, f0, K=1)`` -> complex
  (analogue of inverse_estimation/...single_bin_dft H_meas helper;
   ratio of TFT phasor of i over TFT phasor of v).
"""

from __future__ import annotations

import numpy as np


def _build_tft_basis(
    n_samples: int,
    fs: float,
    f0: float,
    K: int,
) -> np.ndarray:
    """Build the real Taylor-Fourier basis matrix Phi of shape (N, 2(K+1)).

    Columns ordered: a0 (cos), b0 (sin), a1 (t cos), b1 (t sin), ...

    Sample times t_n = n / fs are taken from the WINDOW START so the
    recovered phasor matches the single-bin DFT convention
    ``H = sum_n v_n exp(-j w0 t_n)`` (phasor at window start, the
    standard power-systems convention).  The t_n values are normalised
    by f0 so the t^k columns stay O(1) for moderate K.
    """
    if K < 0:
        raise ValueError(f"K must be >= 0; got {K}")
    n = np.arange(n_samples, dtype=float)
    t = n / fs                                    # window start at t = 0
    omega0 = 2.0 * np.pi * f0
    cos_carrier = np.cos(omega0 * t)
    sin_carrier = np.sin(omega0 * t)
    t_norm = t * f0                               # normalised time, O(1)
    cols: list[np.ndarray] = []
    for k in range(K + 1):
        weight = t_norm ** k
        cols.append(weight * cos_carrier)
        cols.append(weight * sin_carrier)
    return np.stack(cols, axis=1)


def tft_phasor(
    v_t: np.ndarray,
    fs: float = 10_000.0,
    f0: float = 50.0,
    K: int = 1,
) -> tuple[complex, complex]:
    """Estimate the complex phasor and its first time-derivative at the
    centre of the observation window.

    Parameters
    ----------
    v_t : array_like shape (N,)
        Real observed signal; one or more 50 Hz cycles at fs.
    fs : float
        Sampling frequency, Hz.
    f0 : float
        Fundamental frequency, Hz.
    K : int
        Taylor order; default 1 (linear).

    Returns
    -------
    H : complex
        Phasor at window centre, normalised so that for a clean
        cosine ``v(t) = A cos(w0 t + phi)`` the result is
        ``H = A * exp(j phi)``.
    dH_dt : complex
        First time-derivative of the phasor (per second), at the
        window centre.  Useful for the WP3.x downstream phasor
        derivative consumer; not needed by the WP3.5 K06 bias
        comparison.

    Notes
    -----
    For ``K = 0`` the estimator degenerates to a least-squares fit
    of the static phasor to the observed window -- numerically
    equivalent to the single-bin DFT under integer-cycle windows.
    """
    v = np.asarray(v_t, dtype=float)
    if v.ndim != 1:
        raise ValueError(f"v_t must be 1-D; got shape {v.shape}")
    N = v.size
    if N < 2 * (K + 1):
        raise ValueError(
            f"v_t too short for K={K}: need >= {2 * (K + 1)} samples, "
            f"got {N}"
        )
    Phi = _build_tft_basis(N, fs, f0, K)
    # LS solution theta = pinv(Phi) v
    theta, *_ = np.linalg.lstsq(Phi, v, rcond=None)
    # The static-phasor convention: v(t) = A cos(w0 t + phi) =
    # Re[A e^{j phi} e^{j w0 t}] = A cos(phi) cos(w0 t) - A sin(phi) sin(w0 t).
    # The basis pairs are (cos, sin) with column ordering as built; so
    # the phasor at order k is theta[2k] - 1j * theta[2k+1].  Multiply
    # by the inverse of the (1/k! f0^k) Jacobian factor inherited from
    # using t_norm = t * f0 in the basis weights.
    a0 = theta[0]
    b0 = theta[1]
    H = a0 - 1j * b0
    if K >= 1:
        a1 = theta[2]
        b1 = theta[3]
        # weight was (t * f0)^1 so undo the f0 factor to recover dH/dt.
        dH_dt = (a1 - 1j * b1) * f0
    else:
        dH_dt = 0.0 + 0.0j
    return complex(H), complex(dH_dt)


def H_meas_from_waveforms_tft(
    v: np.ndarray,
    i: np.ndarray,
    fs: float = 10_000.0,
    f0: float = 50.0,
    K: int = 1,
) -> complex:
    """Sending-end admittance via Taylor-Fourier: H = I_TFT / V_TFT.

    Drop-in analogue of ``inverse_estimation/faultloc_two_stage_optimiser.
    H_meas_from_waveforms`` (which uses the single-bin DFT).  Use
    ``H_meas_from_waveforms`` for the WP1.4 / Phase 2 baseline and
    this function for the WP3.5 / R5-closure measurements.
    """
    Vp, _ = tft_phasor(v, fs=fs, f0=f0, K=K)
    Ip, _ = tft_phasor(i, fs=fs, f0=f0, K=K)
    return Ip / Vp


__all__ = [
    "tft_phasor",
    "H_meas_from_waveforms_tft",
]
