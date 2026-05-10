"""faultloc_noise_impairments.py
=================================
Five field-grade impairment generators for the SAMBPS-DTaaS Fault-
Location Identification project.  Each takes a clean ``(v, i)``
waveform pair (or one of the two for the asymmetric channels --
CT saturation only on the current side) and returns a corrupted
copy.  The set covers the dominant non-Gaussian phenomena seen on
real distribution feeders that the WP1.1 / WP1.4 dual-channel AWGN
noise model alone does not capture.

WP4.1 (P4.1) implementation.

Generator catalogue
-------------------

1. ``add_impulsive(v, i, *, prob, mag_db)``
   Bernoulli-Gaussian impulsive noise: per-sample Bernoulli switch
   draws an "impulse" event with probability ``prob``; on each
   event add a zero-mean Gaussian sample of standard deviation
   ``mag_db`` dB above the per-channel rms.  Defaults: prob = 0.005,
   mag_db = 20 dB (typical PLC / partial-discharge background).

2. ``add_harmonic_background(v, i, *, harmonics)``
   Fundamental-rooted additive harmonics; ``harmonics`` is a dict
   mapping harmonic order to per-unit amplitude relative to the
   fundamental rms.  Default {2: 0.02, 5: 0.04, 7: 0.03, 11: 0.02}
   matches the IEEE Std 519-2014 Tab. 2 distortion limits for
   < 1 kV residential / commercial feeders (TDD <= 5 %).

3. ``add_ct_saturation(i, *, remanence_pu, burden_ohm, ct_class)``
   CT remanence + burden distortion after the IEEE C37.110-2007
   guide for protective relaying applications.  The CT secondary
   current is clipped via a smooth-saturation envelope parameterised
   by the residual flux (``remanence_pu``) and the secondary burden
   (``burden_ohm``, sweeping the saturation-knee voltage).
   ``ct_class`` selects the CT accuracy class; default ``5P20``.

4. ``add_off_nominal_frequency(v, i, *, df_hz)``
   Replaces the fundamental at f0 with a fundamental at f0 + df_hz
   while preserving the harmonic / transient residual.  Models the
   IEEE C37.118.1-2018 P-class compliance envelope (df_hz +/- 2 Hz).

5. ``add_adc_quantisation(v, i, *, bits, vref_v, iref_a)``
   Uniform mid-tread quantiser at ``bits`` resolution with the
   given full-scale references.  Default 14 bits (typical relay
   IED ADC); sweep over {12, 14, 16}.

Composite-impairment helper
---------------------------

``add_composite_field_grade(v, i, fs, f0, *, rng=None)`` chains
all five in the canonical order
    impulsive -> harmonics -> CT saturation -> off-nominal -> ADC
to model the "field-grade" worst-case scenario.

References
----------

* IEEE Std 519-2014, *IEEE Recommended Practice and Requirements
  for Harmonic Control in Electric Power Systems*.  Cited for the
  per-order amplitude limits in ``add_harmonic_background``.
* IEEE Std C37.110-2007, *IEEE Guide for the Application of
  Current Transformers Used for Protective Relaying Purposes*.
  Cited for the CT remanence + burden saturation model.
* IEEE Std C37.118.1-2018, *IEEE Standard for Synchrophasor
  Measurements for Power Systems*.  Cited for the off-nominal
  frequency P-class compliance envelope.
* See ``docs/feeder_assumptions.md`` for the per-class default
  parameter rationale.
"""

from __future__ import annotations

import numpy as np


def _rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x * x)))


# =============================================================================
# (1) Impulsive noise
# =============================================================================

def add_impulsive(
    v: np.ndarray,
    i: np.ndarray,
    *,
    prob: float = 0.005,
    mag_db: float = 20.0,
    rng: np.random.Generator | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Bernoulli-Gaussian impulsive noise.

    Parameters
    ----------
    v, i : array_like
        Clean voltage and current waveforms, same length.
    prob : float in [0, 1]
        Per-sample Bernoulli probability of an impulse.
    mag_db : float
        Impulse standard deviation in dB above the per-channel rms.
        ``mag_db = 20`` means impulses 10 x the channel rms.
    rng : numpy.random.Generator, optional
    """
    if rng is None:
        rng = np.random.default_rng()
    if not 0.0 <= prob <= 1.0:
        raise ValueError(f"prob must be in [0, 1]; got {prob}")
    v = np.asarray(v, dtype=float)
    i = np.asarray(i, dtype=float)
    if v.shape != i.shape:
        raise ValueError(
            f"v and i must have the same shape; got {v.shape} vs {i.shape}"
        )
    factor = 10.0 ** (mag_db / 20.0)
    rms_v, rms_i = _rms(v), _rms(i)

    mask = rng.random(v.shape) < prob
    v_out = v + mask * rng.standard_normal(v.shape) * (rms_v * factor)
    i_out = i + mask * rng.standard_normal(i.shape) * (rms_i * factor)
    return v_out, i_out


# =============================================================================
# (2) Harmonic background
# =============================================================================

DEFAULT_HARMONICS = {2: 0.02, 5: 0.04, 7: 0.03, 11: 0.02}


def add_harmonic_background(
    v: np.ndarray,
    i: np.ndarray,
    *,
    fs: float = 10_000.0,
    f0: float = 50.0,
    harmonics: dict[int, float] | None = None,
    rng: np.random.Generator | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Add a sum of harmonics at the listed multiples of f0.

    Each ``harmonics[k]`` is the per-unit amplitude of the k-th
    harmonic relative to the channel rms.  Phases are randomised
    independently per channel (the canonical IEEE 519 assumption is
    that harmonics from different sources are statistically
    uncorrelated).  Default amplitudes follow IEEE 519-2014 Tab. 2
    for residential / commercial feeders.
    """
    if rng is None:
        rng = np.random.default_rng()
    if harmonics is None:
        harmonics = DEFAULT_HARMONICS
    v = np.asarray(v, dtype=float)
    i = np.asarray(i, dtype=float)
    if v.shape != i.shape:
        raise ValueError(
            f"v and i must have the same shape; got {v.shape} vs {i.shape}"
        )
    omega0 = 2.0 * np.pi * f0
    n = np.arange(v.size)
    t = n / fs
    rms_v, rms_i = _rms(v), _rms(i)
    v_harm = np.zeros_like(v)
    i_harm = np.zeros_like(i)
    for order, amp in harmonics.items():
        phi_v = float(rng.uniform(-np.pi, np.pi))
        phi_i = float(rng.uniform(-np.pi, np.pi))
        v_harm += rms_v * amp * np.sqrt(2.0) * np.cos(order * omega0 * t + phi_v)
        i_harm += rms_i * amp * np.sqrt(2.0) * np.cos(order * omega0 * t + phi_i)
    return v + v_harm, i + i_harm


# =============================================================================
# (3) CT saturation (remanence + burden)
# =============================================================================

CT_CLASSES = {
    # Saturation-knee secondary voltage (V) at rated burden + accuracy
    # class per IEEE C37.110-2007 Tab. 5 -- representative values.
    "5P20":  100.0,
    "10P20": 60.0,
    "5P10":  50.0,
    "10P10": 30.0,
}


def add_ct_saturation(
    i: np.ndarray,
    *,
    remanence_pu: float = 0.3,
    burden_ohm: float = 2.0,
    ct_class: str = "5P20",
) -> np.ndarray:
    """CT saturation envelope after IEEE C37.110-2007.

    Models the secondary current under a smooth tanh-saturation
    envelope where the EFFECTIVE knee is reduced by the residual
    flux:
    ``I_knee_eff = (V_knee / burden) * (1 - remanence_pu)``,
    ``i_sec(t)  = I_knee_eff * tanh( i_unsat(t) / I_knee_eff )``.

    In the linear regime ``|i| << I_knee_eff`` the output equals
    the input (CT acts as an ideal turns-ratio transformer; the
    primary->secondary scaling is folded into ``burden_ohm``).  As
    ``|i| -> I_knee_eff`` the output saturates smoothly at the
    knee.  Higher ``remanence_pu`` reduces the effective knee,
    forcing earlier saturation -- the canonical WP4.1 sweep is
    remanence in {0, 0.3, 0.5, 0.8} and burden in {1, 2, 4, 8} Ohm.

    Parameters
    ----------
    i : array_like
        Clean (unsaturated) CT secondary current.
    remanence_pu : float in [0, 1)
        Fractional residual flux at t = 0; 0.0 = no remanence,
        approaching 1.0 = fully saturated at start.  Capped strictly
        below 1.0 to keep ``I_knee_eff`` positive.
    burden_ohm : float, ohms
        CT secondary burden.
    ct_class : str
        IEEE C37.110-2007 accuracy class.  ``5P20`` = 5 % composite
        error at 20 x rated current (default protection class).
    """
    if ct_class not in CT_CLASSES:
        raise ValueError(
            f"ct_class must be one of {list(CT_CLASSES.keys())}; "
            f"got {ct_class!r}"
        )
    if not 0.0 <= remanence_pu < 1.0:
        raise ValueError(
            f"remanence_pu must be in [0, 1); got {remanence_pu}"
        )
    if burden_ohm <= 0:
        raise ValueError(f"burden_ohm must be > 0; got {burden_ohm}")
    i = np.asarray(i, dtype=float)
    v_knee = CT_CLASSES[ct_class]
    i_knee_eff = (v_knee / burden_ohm) * (1.0 - remanence_pu)
    return i_knee_eff * np.tanh(i / i_knee_eff)


# =============================================================================
# (4) Off-nominal frequency
# =============================================================================

def add_off_nominal_frequency(
    v: np.ndarray,
    i: np.ndarray,
    *,
    fs: float = 10_000.0,
    f0: float = 50.0,
    df_hz: float = 0.5,
) -> tuple[np.ndarray, np.ndarray]:
    """Shift the fundamental from f0 to f0 + df_hz, preserving the
    harmonic / transient residual.

    Models the IEEE C37.118.1-2018 P-class compliance envelope
    (df_hz in [-2, +2]).
    """
    if abs(df_hz) > 5.0:
        raise ValueError(
            f"df_hz outside the +/- 5 Hz IEEE C37.118.1 envelope; "
            f"got {df_hz}"
        )
    v = np.asarray(v, dtype=float)
    i = np.asarray(i, dtype=float)
    if v.shape != i.shape:
        raise ValueError(
            f"v and i must have the same shape; got {v.shape} vs {i.shape}"
        )
    if df_hz == 0.0:
        return v.copy(), i.copy()
    omega0 = 2.0 * np.pi * f0
    omega1 = 2.0 * np.pi * (f0 + df_hz)
    Ns = v.size
    n = np.arange(Ns)
    t = n / fs
    k = int(round(f0 * Ns / fs))
    Vp = (2.0 / Ns) * np.sum(v * np.exp(-1j * 2 * np.pi * k * n / Ns))
    Ip = (2.0 / Ns) * np.sum(i * np.exp(-1j * 2 * np.pi * k * n / Ns))
    v_fund_orig = np.real(Vp * np.exp(1j * omega0 * t))
    i_fund_orig = np.real(Ip * np.exp(1j * omega0 * t))
    v_fund_new = np.real(Vp * np.exp(1j * omega1 * t))
    i_fund_new = np.real(Ip * np.exp(1j * omega1 * t))
    return v - v_fund_orig + v_fund_new, i - i_fund_orig + i_fund_new


# =============================================================================
# (5) ADC quantisation
# =============================================================================

def add_adc_quantisation(
    v: np.ndarray,
    i: np.ndarray,
    *,
    bits: int = 14,
    vref_v: float = 100.0,
    iref_a: float = 10.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Uniform mid-tread quantiser at ``bits`` resolution.

    Parameters
    ----------
    v, i : array_like
        Clean voltage / current waveforms.
    bits : int
        ADC resolution (e.g., 14 = typical IED).  Sweep over
        {12, 14, 16}.
    vref_v : float
        Voltage full-scale reference (peak amplitude beyond which
        the ADC clips).
    iref_a : float
        Current full-scale reference.

    Returns
    -------
    v_q, i_q : ndarray
        Quantised waveforms.
    """
    if bits < 4 or bits > 32:
        raise ValueError(f"bits must be in [4, 32]; got {bits}")
    if vref_v <= 0 or iref_a <= 0:
        raise ValueError(
            f"vref_v and iref_a must be > 0; got {vref_v}, {iref_a}"
        )
    v = np.asarray(v, dtype=float)
    i = np.asarray(i, dtype=float)
    n_levels = 2 ** bits
    v_step = 2.0 * vref_v / n_levels
    i_step = 2.0 * iref_a / n_levels
    v_clipped = np.clip(v, -vref_v + v_step / 2.0, vref_v - v_step / 2.0)
    i_clipped = np.clip(i, -iref_a + i_step / 2.0, iref_a - i_step / 2.0)
    v_q = np.round(v_clipped / v_step) * v_step
    i_q = np.round(i_clipped / i_step) * i_step
    return v_q, i_q


# =============================================================================
# Composite field-grade pipeline
# =============================================================================

def add_composite_field_grade(
    v: np.ndarray,
    i: np.ndarray,
    *,
    fs: float = 10_000.0,
    f0: float = 50.0,
    rng: np.random.Generator | None = None,
    impulsive_prob: float = 0.005,
    impulsive_mag_db: float = 20.0,
    harmonics: dict[int, float] | None = None,
    remanence_pu: float = 0.3,
    burden_ohm: float = 2.0,
    ct_class: str = "5P20",
    df_hz: float = 0.5,
    bits: int = 14,
    vref_v: float = 100.0,
    iref_a: float = 10.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Apply all 5 impairments in the canonical order: impulsive ->
    harmonics -> CT saturation -> off-nominal -> ADC.  Used by the
    WP4.1 runner as the "field-grade" composite case."""
    v_, i_ = add_impulsive(v, i, prob=impulsive_prob,
                           mag_db=impulsive_mag_db, rng=rng)
    v_, i_ = add_harmonic_background(v_, i_, fs=fs, f0=f0,
                                     harmonics=harmonics, rng=rng)
    i_ = add_ct_saturation(i_, remanence_pu=remanence_pu,
                           burden_ohm=burden_ohm, ct_class=ct_class)
    v_, i_ = add_off_nominal_frequency(v_, i_, fs=fs, f0=f0, df_hz=df_hz)
    v_, i_ = add_adc_quantisation(v_, i_, bits=bits,
                                  vref_v=vref_v, iref_a=iref_a)
    return v_, i_


__all__ = [
    "add_impulsive",
    "add_harmonic_background",
    "add_ct_saturation",
    "add_off_nominal_frequency",
    "add_adc_quantisation",
    "add_composite_field_grade",
    "DEFAULT_HARMONICS",
    "CT_CLASSES",
]
