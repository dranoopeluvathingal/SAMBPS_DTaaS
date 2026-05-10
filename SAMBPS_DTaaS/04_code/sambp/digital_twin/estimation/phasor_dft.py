# =============================================================================
# sambp / digital_twin / estimation / phasor_dft.py
#
# Phasor extractor via DFT — fundamental-frequency component of three-phase
# voltage and current waveforms.
#
# Replaces the instantaneous sequence approximation in EKFEstimator with an
# exact Fortescue decomposition at the fundamental frequency bin.
#
# Design
# ------
# PhasorDFT accumulates samples in a one-cycle circular buffer (N = fs/f0
# samples).  Once the buffer is full it computes the DFT fundamental bin
# for each phase and applies the Fortescue transformation to extract
# exact positive- and negative-sequence phasors.
#
# The extractor is intentionally a pure computation class with NO dependencies
# on EKFEstimator, RLSEstimator, or ProtectionMirror.  It is imported by
# EKFPhasorEstimator only.
#
# Measurement model relationship
# --------------------------------
# The EKF observation function h(x) is calibrated to RMS amplitudes:
#   I_pos = k_ibr           (positive-sequence current magnitude)
#   I_neg = k * (1-fg)*0.25 (negative-sequence current magnitude)
#   Z_app = alpha*z_line/k  (apparent impedance)
#
# PhasorDFT.extract() returns |X1| and |X2| (positive/negative sequence
# magnitudes in the same RMS convention), consistent with h(x).  The
# caller is responsible for forming Z_app from V_pos and I_pos.
#
# Accuracy note
# -------------
# The DFT estimate has spectral leakage when the signal is not an integer
# number of cycles in the buffer.  A rectangular window is used (no windowing)
# because:
#   (a) at fs=1000 Hz and f0=50 Hz the buffer holds exactly N=20 samples
#       per cycle — no leakage for integer-cycle signals;
#   (b) adding a window function would bias the magnitude estimate.
# For non-50 Hz or transient conditions the caller should check
# PhasorDFT.ready before using extract().
#
# Public API
# ----------
# dft = PhasorDFT(fs=1000, f0=50)
# dft.push(v_abc, i_abc)            # push one sample (arrays of length 3)
# result = dft.extract()            # returns dict (raises if not ready)
# dft.ready                         # True when buffer holds >= N samples
# dft.n_samples                     # samples received so far
# dft.reset()                       # clear buffer
#
# result dict keys
# ----------------
#   v_phasors : complex array (3,) — phase voltage phasors [pu]
#   i_phasors : complex array (3,) — phase current phasors [pu]
#   V0, V1, V2 : complex — zero/positive/negative sequence voltage phasors
#   I0, I1, I2 : complex — zero/positive/negative sequence current phasors
#   I_pos_mag  : float   — |I1| (positive-sequence current magnitude)
#   I_neg_mag  : float   — |I2| (negative-sequence current magnitude)
#   V_pos_mag  : float   — |V1| (positive-sequence voltage magnitude)
# =============================================================================

import math
import cmath
import numpy as np

# Fortescue rotation operator a = exp(j 2π/3)
_A     = cmath.rect(1.0, 2.0 * math.pi / 3.0)   # e^{j120°}
_A2    = _A * _A                                   # e^{j240°}

# Fortescue transform matrix  [X0, X1, X2]^T = F * [Xa, Xb, Xc]^T
# where F_ij / 3 is the standard Fortescue matrix
_F = np.array([
    [1.0+0j,  1.0+0j,  1.0+0j ],
    [1.0+0j,  _A,      _A2    ],
    [1.0+0j,  _A2,     _A     ],
], dtype=complex) / 3.0


def _fortescue(x_abc):
    """
    Apply the Fortescue transformation to a length-3 phasor vector.

    Parameters
    ----------
    x_abc : complex array (3,) — [Xa, Xb, Xc] phase phasors

    Returns
    -------
    X012 : complex array (3,) — [X0, X1, X2] (zero, positive, negative)
    """
    return _F @ np.asarray(x_abc, dtype=complex)


class PhasorDFT:
    """
    One-cycle DFT phasor extractor for three-phase signals.

    Maintains a circular buffer of N = round(fs / f0) samples per channel
    (3 voltage + 3 current = 6 channels total).  On each push() the oldest
    sample is discarded and replaced.  extract() computes the fundamental
    bin DFT for all six channels and returns sequence phasors.

    Parameters
    ----------
    fs : float — sample rate [Hz].  Default 1000.
    f0 : float — nominal system frequency [Hz].  Default 50.
    """

    def __init__(self, fs: float = 1000.0, f0: float = 50.0):
        self.fs = float(fs)
        self.f0 = float(f0)
        self._N = max(2, round(fs / f0))   # samples per cycle

        # Precompute DFT kernel for fundamental bin (k=1):
        #   W[n] = exp(-j 2π n / N)  for n = 0 .. N-1
        # Scaled by 2/N so the result is the one-sided RMS phasor amplitude.
        n = np.arange(self._N)
        self._kernel = (2.0 / self._N) * np.exp(-1j * 2.0 * math.pi * n / self._N)

        # Circular buffer: shape (6, N)  — [va, vb, vc, ia, ib, ic]
        self._buf   = np.zeros((6, self._N), dtype=float)
        self._ptr   = 0       # write pointer (next slot)
        self._count = 0       # samples received

    # ------------------------------------------------------------------
    def push(self, v_abc, i_abc):
        """
        Push one sample into the buffer.

        Parameters
        ----------
        v_abc : array-like (3,) — [Va, Vb, Vc] phase voltages [pu]
        i_abc : array-like (3,) — [Ia, Ib, Ic] phase currents [pu]
        """
        v = np.asarray(v_abc, dtype=float)
        i = np.asarray(i_abc, dtype=float)
        col = np.concatenate([v, i])          # length 6
        self._buf[:, self._ptr] = col
        self._ptr  = (self._ptr + 1) % self._N
        self._count = min(self._count + 1, 2 * self._N)  # cap to avoid overflow

    # ------------------------------------------------------------------
    def extract(self):
        """
        Compute fundamental-bin DFT phasors and Fortescue sequence components.

        Returns
        -------
        dict — see module header for key descriptions.

        Raises
        ------
        RuntimeError if fewer than N samples have been pushed (buffer not full).
        """
        if not self.ready:
            raise RuntimeError(
                f"PhasorDFT buffer not full: {self._count} of {self._N} "
                "samples received.  Call push() at least N times before extract().")

        # Reorder buffer so index 0 is the oldest sample (chronological order)
        # When ptr == 0 the buffer is already in order; otherwise rotate.
        if self._ptr == 0:
            data = self._buf           # shape (6, N)
        else:
            data = np.roll(self._buf, -self._ptr, axis=1)

        # DFT at fundamental bin: X = data @ kernel  (dot over time axis)
        # kernel[n] = (2/N)*exp(-j2πn/N) — forward DFT convention.
        # Do NOT conjugate: conj() would swap positive↔negative sequence for
        # balanced signals (positive-sequence input arrives at the conjugate
        # bin, giving |I1|=0 and |I2|=k_ibr — opposite of what h(x) expects).
        # Shape: (6,) complex phasors
        X = data @ self._kernel           # (6, N) @ (N,) → (6,)

        v_ph = X[:3]   # [Va, Vb, Vc] phasors
        i_ph = X[3:]   # [Ia, Ib, Ic] phasors

        V012 = _fortescue(v_ph)   # [V0, V1, V2]
        I012 = _fortescue(i_ph)   # [I0, I1, I2]

        return {
            'v_phasors': v_ph,
            'i_phasors': i_ph,
            'V0': V012[0], 'V1': V012[1], 'V2': V012[2],
            'I0': I012[0], 'I1': I012[1], 'I2': I012[2],
            'I_pos_mag': abs(I012[1]),
            'I_neg_mag': abs(I012[2]),
            'V_pos_mag': abs(V012[1]),
        }

    # ------------------------------------------------------------------
    @property
    def ready(self):
        """True when the buffer holds at least N (one full cycle of) samples."""
        return self._count >= self._N

    @property
    def n_samples(self):
        """Total samples pushed (capped at 2*N to avoid integer overflow)."""
        return self._count

    @property
    def cycle_length(self):
        """Buffer length N = round(fs / f0)."""
        return self._N

    # ------------------------------------------------------------------
    def reset(self):
        """Clear the buffer (call when entering a new fault window)."""
        self._buf[:] = 0.0
        self._ptr    = 0
        self._count  = 0

    # ------------------------------------------------------------------
    def __repr__(self):
        return (f"PhasorDFT(fs={self.fs:.0f}, f0={self.f0:.0f}, "
                f"N={self._N}, ready={self.ready}, count={self._count})")
