# =============================================================================
# sambp / sambp_sync_oc
# signal_processing/sequence_components.py
#
# Symmetrical component transformation for three-phase quantities.
#
# Provides both:
#   (a) Instantaneous time-domain sequence signals (Clarke + Park style)
#   (b) Phasor-domain sequence components from complex phasor inputs
#
# Public API
# ----------
# symmetrical_components(ia, ib, ic, domain="instantaneous")
#   → dict {I0, I1, I2}
#
# phasor_sequence(Ia_phasor, Ib_phasor, Ic_phasor)
#   → dict {I0, I1, I2}  (complex phasors)
# =============================================================================

import numpy as np

# Fortescue operator a = exp(j·2π/3)
_A  = np.exp(1j * 2.0 * np.pi / 3.0)
_A2 = _A ** 2

# Symmetrical component transformation matrix  [I0, I1, I2]^T = (1/3)·T·[Ia,Ib,Ic]^T
_T = (1.0 / 3.0) * np.array([
    [1,    1,    1   ],
    [1,    _A,   _A2 ],
    [1,    _A2,  _A  ],
], dtype=complex)


def phasor_sequence(Ia_phasor, Ib_phasor, Ic_phasor):
    """
    Compute positive, negative and zero sequence components from
    complex phasor inputs (phasor domain).

    Parameters
    ----------
    Ia_phasor, Ib_phasor, Ic_phasor : complex — phase phasors (pu)

    Returns
    -------
    dict with keys:
        I0 : complex — zero sequence phasor
        I1 : complex — positive sequence phasor
        I2 : complex — negative sequence phasor
    """
    vec = np.array([Ia_phasor, Ib_phasor, Ic_phasor], dtype=complex)
    seq = _T @ vec
    return {"I0": seq[0], "I1": seq[1], "I2": seq[2]}


def symmetrical_components(ia, ib, ic, domain="instantaneous"):
    """
    Compute symmetrical (sequence) components of three-phase currents.

    Parameters
    ----------
    ia, ib, ic : array-like — phase currents (pu)
                 For 'instantaneous': real-valued time-domain arrays.
                 For 'phasor': complex scalars (single phasor per phase).
    domain     : str        — "instantaneous" | "phasor"

    Instantaneous mode
    ------------------
    Applies the Fortescue transformation sample-by-sample to the
    analytic (complex) signal obtained via the Hilbert transform.
    Returns real part of I0, I1, I2 as time-domain waveforms.

    Phasor mode
    -----------
    Applies transformation directly to complex phasor inputs.
    Returns complex sequence phasors.

    Returns
    -------
    dict with keys: I0, I1, I2
        instantaneous: ndarray (real, pu)
        phasor:        complex scalar (pu)
    """
    if domain == "phasor":
        return phasor_sequence(
            complex(ia), complex(ib), complex(ic)
        )

    elif domain == "instantaneous":
        from scipy.signal import hilbert

        ia = np.asarray(ia, dtype=float)
        ib = np.asarray(ib, dtype=float)
        ic = np.asarray(ic, dtype=float)

        # Analytic signals
        Ia = hilbert(ia)
        Ib = hilbert(ib)
        Ic = hilbert(ic)

        # Apply Fortescue transform sample-by-sample
        I0 = (Ia + Ib + Ic) / 3.0
        I1 = (Ia + _A  * Ib + _A2 * Ic) / 3.0
        I2 = (Ia + _A2 * Ib + _A  * Ic) / 3.0

        return {
            "I0": np.real(I0),
            "I1": np.real(I1),
            "I2": np.real(I2),
        }

    else:
        raise ValueError(
            f"Unknown domain: '{domain}'. Expected 'instantaneous' or 'phasor'."
        )
