# =============================================================================
# sambp / digital_twin / models / protection_mirror.py
#
# Protection model mirror — the DT's internal replica of the relay logic.
#
# The mirror runs the same deterministic protection algorithm as the physical
# relay, but on DT-estimated states (k_ibr, alpha) rather than raw measurements.
# It is used by DecisionComparator to predict what the relay *should* do,
# so that discrepancies between the mirror's prediction and the relay's actual
# action can be flagged.
#
# Single source of truth
# ----------------------
# ALL protection logic (relay and DT mirror) routes through predict().
# The run_dt_lab.py Study E relay decision calls mirror.predict() with the
# relay's own noisy single-sample measurement; the DT comparator calls
# mirror.predict() with the EKF-smoothed estimate.  No duplicate logic.
#
# Relay elements modelled
# -----------------------
#   Z1/87L  — Zone 1 mho + line differential (fastest, ~20 ms)
#   87L     — Line differential only (all internal faults beyond Z1 reach)
#   87T     — Transformer differential (inrush-blocked)
#   87B     — Bus differential
#   OC      — Overcurrent (definite time and inverse time)
#   EXTERNAL — Out-of-zone event (alpha > 1.0)
#   MISS    — Below all pickup thresholds
#
# Trip family grouping (for AGREE logic in DecisionComparator)
# ------------------------------------------------------------
# Z1/87L and 87L are the same *protection family* (line differential /
# pilot distance).  A Z1↔87L element mismatch between relay and DT
# means the DT disagrees on *speed*, not on *whether to trip* — this is
# a selectivity note, not a protection failure.
#
#   Family 'line'  : Z1/87L, 87L
#   Family 'xfmr'  : 87T
#   Family 'bus'   : 87B
#   Family 'oc'    : OC
#   Family None    : MISS, EXTERNAL (block family)
#
# Z1 boundary and margin
# ----------------------
# Z1 alpha boundary:  alpha_Z1 = X_R1 / Z_LINE = 0.040 / 0.050 = 0.80
#
# A margin band of _Z1_MARGIN (0.05 pu, i.e. 5 % of line length) is applied
# below the Z1 boundary.  For alpha in (0.75, 0.80], the mirror conservatively
# predicts '87L' rather than 'Z1/87L', reducing sensitivity to EKF alpha
# estimation error near the boundary.  The relay's own measurement (based on
# direct V/I) may still pick Z1 in this zone — both are treated as AGREE.
#
# Public API
# ----------
# mirror = ProtectionMirror()
# prediction = mirror.predict(k_ibr, alpha, fault_type, r_arc=0.0)
#   → {'element': str, 'action': str, 'confidence': float,
#      'near_boundary': bool}
# ProtectionMirror.TRIP_FAMILIES        — element → family dict
# ProtectionMirror.is_same_family(a, b) — bool
# =============================================================================


# ── Protection thresholds (consistent with TR-35 / TR-43) ──────────────────
_I_MIN_87L  = 0.060   # pu
_I_MIN_Z1   = 0.100   # pu
_X_R1       = 0.040   # pu  — Zone 1 reactance reach
_R_REACH    = 0.030   # pu  — Zone 1 resistance reach (load blinder)
_Z_LINE     = 0.050   # pu  — nominal line impedance
_I_MIN_87T  = 0.150   # pu
_I_MIN_87B  = 0.100   # pu
_I_MIN_OC   = 0.050   # pu

# Z1 alpha boundary and conservative margin
_Z1_ALPHA_BOUNDARY = _X_R1 / _Z_LINE   # = 0.80
_Z1_MARGIN         = 0.05              # pu — margin below boundary (relay conservatism)
_Z1_ALPHA_SAFE     = _Z1_ALPHA_BOUNDARY - _Z1_MARGIN   # = 0.75


class ProtectionMirror:
    """
    Deterministic model mirror of the SAMBP relay suite.

    Given measured or DT-estimated system state, predicts which relay element
    would operate and with what confidence.

    This class is the single source of truth for all protection logic in the
    Digital Twin Lab.  Both the physical relay decision (in study runners) and
    the DT mirror prediction call predict() — with different inputs (relay raw
    measurement vs DT EKF estimate) but identical logic.

    Attributes
    ----------
    TRIP_FAMILIES : dict
        Maps element name → protection family string.  Same family = same
        protection outcome (trip/block); element difference = speed difference.
    """

    TRIP_FAMILIES = {
        'Z1/87L':   'line',   # Pilot distance / line differential — fastest
        '87L':      'line',   # Line differential — same family as Z1
        '87T':      'xfmr',
        '87B':      'bus',
        'OC':       'oc',
        'MISS':     None,
        'EXTERNAL': None,
    }

    @staticmethod
    def is_same_family(elem_a, elem_b):
        """
        Return True if elem_a and elem_b belong to the same protection family.

        Same-family TRIP mismatch (e.g. Z1/87L vs 87L) is a selectivity
        observation, not a protection failure.

        Parameters
        ----------
        elem_a, elem_b : str — relay element names

        Returns
        -------
        bool
        """
        fa = ProtectionMirror.TRIP_FAMILIES.get(elem_a)
        fb = ProtectionMirror.TRIP_FAMILIES.get(elem_b)
        # Both None → both block → same outcome
        # One None, one not → different outcomes
        return fa is not None and fa == fb

    # ------------------------------------------------------------------
    def predict(self, k_ibr, alpha, fault_type='SLG', r_arc=0.0):
        """
        Predict relay operation from state estimate or measurement.

        Parameters
        ----------
        k_ibr      : float — IBR contribution ratio or measured current [pu]
        alpha      : float — fault location (0 = relay end, 1 = remote bus)
        fault_type : str   — 'SLG', 'LL', 'LLG', '3PH'
        r_arc      : float — arc resistance [pu].  Default 0.0.

        Returns
        -------
        dict with keys:
            element       : str   — element label (see module header)
            action        : str   — 'TRIP' or 'BLOCK'
            confidence    : float — distance-to-threshold in [0, 1]
            near_boundary : bool  — True if within _Z1_MARGIN of Z1 boundary
                                    (comparator uses this to annotate results)
        """
        near_boundary = False

        # ── External fault ───────────────────────────────────────────────
        if alpha > 1.0:
            return {'element': 'EXTERNAL', 'action': 'BLOCK',
                    'confidence': min(1.0, (alpha - 1.0) / 0.05),
                    'near_boundary': False}

        # Apparent impedance components at relay terminal
        x_m = alpha * _Z_LINE
        r_m = (r_arc * (1.0 + 1.0 / k_ibr)) if k_ibr > 0.01 else 1e6

        # Check whether we are in the Z1 boundary margin zone
        # alpha in (_Z1_ALPHA_SAFE, _Z1_ALPHA_BOUNDARY] → near boundary
        near_boundary = _Z1_ALPHA_SAFE < alpha <= _Z1_ALPHA_BOUNDARY

        # ── Z1/87L (pilot distance + line differential, fastest ~20 ms) ─
        # Conservative: only claim Z1 if alpha is clearly inside Z1 reach
        # (alpha <= _Z1_ALPHA_SAFE = 0.75).  In the margin zone (0.75, 0.80]
        # fall through to 87L — both are correct, 87L is slightly slower.
        in_z1_geometry = (0.0 <= x_m <= _X_R1) and (r_m <= _R_REACH)
        in_z1_current  = k_ibr >= _I_MIN_Z1
        in_z1_safe     = alpha <= _Z1_ALPHA_SAFE   # strict: not in margin

        if in_z1_geometry and in_z1_current and in_z1_safe:
            margin_x = (_X_R1 - x_m) / _X_R1
            margin_r = (_R_REACH - r_m) / _R_REACH if _R_REACH > 0 else 1.0
            margin_k = (k_ibr - _I_MIN_Z1) / _I_MIN_Z1
            conf = min(margin_x, margin_r, margin_k)
            return {'element': 'Z1/87L', 'action': 'TRIP',
                    'confidence': max(0.0, min(1.0, conf)),
                    'near_boundary': near_boundary}

        # ── 87L (line differential, all internal faults) ────────────────
        if k_ibr >= _I_MIN_87L:
            # Confidence: distance from 87L pickup threshold
            conf_k = min(1.0, (k_ibr - _I_MIN_87L) / _I_MIN_87L)
            # Reduce confidence near Z1 boundary (operating point is debatable)
            conf   = conf_k * (0.5 if near_boundary else 1.0)
            return {'element': '87L', 'action': 'TRIP',
                    'confidence': max(0.0, conf),
                    'near_boundary': near_boundary}

        # ── OC (definite-time overcurrent, last resort) ──────────────────
        if k_ibr >= _I_MIN_OC:
            conf = min(1.0, (k_ibr - _I_MIN_OC) / _I_MIN_OC)
            return {'element': 'OC', 'action': 'TRIP',
                    'confidence': max(0.0, conf),
                    'near_boundary': False}

        # ── No element operates (IBR contribution too small) ─────────────
        return {'element': 'MISS', 'action': 'BLOCK',
                'confidence': max(0.0, 1.0 - k_ibr / _I_MIN_OC),
                'near_boundary': False}

    # ------------------------------------------------------------------
    def predict_87t(self, i_diff, k2_ratio, k5_ratio, eps_ct):
        """
        Predict 87T (transformer differential) operation.

        Parameters
        ----------
        i_diff   : float — differential current magnitude [pu]
        k2_ratio : float — 2nd harmonic / fundamental ratio
        k5_ratio : float — 5th harmonic / fundamental ratio
        eps_ct   : float — CT ratio error estimate
        """
        if k2_ratio > 0.15:
            return {'element': '87T', 'action': 'BLOCK',
                    'confidence': min(1.0, (k2_ratio - 0.15) / 0.15),
                    'near_boundary': False}
        if k5_ratio > 0.30:
            return {'element': '87T', 'action': 'BLOCK',
                    'confidence': min(1.0, (k5_ratio - 0.30) / 0.30),
                    'near_boundary': False}
        if eps_ct > 0.10:
            return {'element': '87T', 'action': 'BLOCK',
                    'confidence': min(1.0, (eps_ct - 0.10) / 0.10),
                    'near_boundary': False}
        if i_diff >= _I_MIN_87T:
            conf = min(1.0, (i_diff - _I_MIN_87T) / _I_MIN_87T)
            return {'element': '87T', 'action': 'TRIP',
                    'confidence': max(0.0, conf), 'near_boundary': False}
        return {'element': 'MISS', 'action': 'BLOCK',
                'confidence': 0.0, 'near_boundary': False}

    # ------------------------------------------------------------------
    def predict_87b(self, i_diff, eps_ct):
        """
        Predict 87B (bus differential) operation.

        Parameters
        ----------
        i_diff : float — bus differential current [pu]
        eps_ct : float — CT error estimate
        """
        if eps_ct > 0.10:
            return {'element': '87B', 'action': 'BLOCK',
                    'confidence': min(1.0, eps_ct / 0.10),
                    'near_boundary': False}
        if i_diff >= _I_MIN_87B:
            conf = min(1.0, (i_diff - _I_MIN_87B) / _I_MIN_87B)
            return {'element': '87B', 'action': 'TRIP',
                    'confidence': max(0.0, conf), 'near_boundary': False}
        return {'element': 'MISS', 'action': 'BLOCK',
                'confidence': 0.0, 'near_boundary': False}
