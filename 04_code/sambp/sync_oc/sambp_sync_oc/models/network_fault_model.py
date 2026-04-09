# =============================================================================
# sambp / sambp_sync_oc
# models/network_fault_model.py
#
# Computes fault state flags and equivalent network modifiers for each
# time step. Used by the forward simulation to switch between pre-fault,
# fault, and post-fault network conditions.
#
# Public API
# ----------
# apply_fault_condition(t, fault_time_s, fault_type,
#                       fault_resistance_pu, prefault_voltage_pu)
#   → dict  {is_faulted, phase_faulted, Z_fault_pu, V_driving_pu,
#             fault_mask, clear_mask}
# =============================================================================

import numpy as np


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _faulted_phases(fault_type):
    """
    Return list of phase labels involved in the fault.

    3PH → ['A', 'B', 'C']
    LL  → ['A', 'B']        (phases A–B, most common LL convention)
    SLG → ['A']             (phase A to ground)
    """
    mapping = {
        "3PH": ["A", "B", "C"],
        "LL":  ["A", "B"],
        "SLG": ["A"],
    }
    if fault_type not in mapping:
        raise ValueError(
            f"Unknown fault_type: '{fault_type}'. "
            f"Expected one of {list(mapping.keys())}."
        )
    return mapping[fault_type]


def _fault_impedance_pu(fault_type, fault_resistance_pu):
    """
    Return complex fault impedance (pu) for each fault type.

    Stage 1: reactance component of the fault path is zero (pure resistive).
    The fault type scaling accounts for the number of sequence networks
    in series (1 for 3PH, 2 for LL, 3 for SLG).
    """
    seq_multiplier = {"3PH": 1.0, "LL": 2.0, "SLG": 3.0}
    R_f = fault_resistance_pu * seq_multiplier[fault_type]
    return complex(R_f, 0.0)


def _driving_voltage(fault_type, prefault_voltage_pu):
    """
    Return the equivalent driving voltage (pu) seen at the fault point.

    3PH : V_f = V_prefault  (all three phases, balanced)
    LL  : V_f = √3 × V_prefault  (line-to-line driving voltage)
    SLG : V_f = V_prefault  (phase-to-neutral)
    """
    scale = {"3PH": 1.0, "LL": np.sqrt(3.0), "SLG": 1.0}
    return prefault_voltage_pu * scale[fault_type]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def apply_fault_condition(
    t,
    fault_time_s,
    fault_type,
    fault_resistance_pu,
    prefault_voltage_pu=1.0,
):
    """
    Compute fault state flags and equivalent network modifiers for each
    time sample.

    Parameters
    ----------
    t                   : ndarray — full simulation time vector (s)
    fault_time_s        : float   — fault inception time (s)
    fault_type          : str     — "3PH" | "LL" | "SLG"
    fault_resistance_pu : float   — fault path resistance (pu)
    prefault_voltage_pu : float   — pre-fault terminal voltage magnitude (pu)

    Returns
    -------
    dict with keys:
        is_faulted      : bool    — True if any time sample is faulted
        phase_faulted   : list    — phase labels involved, e.g. ['A','B']
        Z_fault_pu      : complex — equivalent fault impedance (pu)
        V_driving_pu    : float   — driving voltage at fault point (pu)
        fault_mask      : ndarray[bool] — True for samples during fault
        prefault_mask   : ndarray[bool] — True for samples before fault
    """
    t = np.asarray(t)

    fault_mask    = t >= fault_time_s
    prefault_mask = t <  fault_time_s

    Z_fault    = _fault_impedance_pu(fault_type, fault_resistance_pu)
    V_driving  = _driving_voltage(fault_type, prefault_voltage_pu)
    phases     = _faulted_phases(fault_type)

    return {
        "is_faulted":    bool(np.any(fault_mask)),
        "phase_faulted": phases,
        "Z_fault_pu":    Z_fault,
        "V_driving_pu":  V_driving,
        "fault_mask":    fault_mask,
        "prefault_mask": prefault_mask,
    }
