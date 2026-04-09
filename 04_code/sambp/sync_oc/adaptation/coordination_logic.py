# =============================================================================
# sambp / sambp_sync_oc
# adaptation/coordination_logic.py
#
# Relay coordination logic for multi-generator busbar systems.
#
# Selectivity constraint
# ----------------------
# For N relays ordered upstream → downstream (index 0 = most upstream):
#
#   I_p[k] > I_p[k+1] + ΔI_margin   for k = 0, 1, ..., N-2
#
# This ensures the downstream relay (closer to the fault, lower pickup)
# trips first, preserving directional selectivity.
#
# The constraint is enforced by a greedy cascade correction: starting from
# the most downstream relay and working upstream, any violation is resolved
# by raising the upstream pickup.  The process repeats until convergent
# (at most max_iter passes).
#
# Time-grading margin (supplemental)
# -----------------------------------
# After pickup coordination, trip time grading is verified at a representative
# fault current (minimum fault current = highest fault resistance case):
#
#   t_op[k](I_fault_min) > t_op[k+1](I_fault_min) + Δt_grade
#
# If the time margin is violated, the downstream relay's TMS is reduced
# minimally to restore grading.  This is only applied when TMS values are
# provided.
#
# Public API
# ----------
# check_selectivity(relay_settings_list, delta_I_margin_pu)
#   → dict {selectivity_ok, violations, margins}
#
# enforce_selectivity(relay_settings_list, delta_I_margin_pu, max_iter)
#   → list[dict]  — corrected settings (new list, originals unchanged)
#
# check_time_grading(relay_settings_list, I_fault_min_pu,
#                    delta_t_grade_s, frequency_hz)
#   → dict {grading_ok, violations, margins_s}
#
# enforce_time_grading(relay_settings_list, I_fault_min_pu,
#                      delta_t_grade_s)
#   → list[dict]  — corrected settings
# =============================================================================

import copy
import numpy as np


# ---------------------------------------------------------------------------
# IEC Very Inverse operate time
# ---------------------------------------------------------------------------

def _iec_very_inverse_time(tms, pickup_pu, i_rms_pu, eps=1e-6):
    """
    IEC 60255-151 Very Inverse operate time (s).

    t_op = TMS × 13.5 / (M − 1),  M = I_rms / pickup_pu
    Returns inf when M ≤ 1 (below pickup — relay does not operate).
    """
    M = i_rms_pu / (pickup_pu + eps)
    if M <= 1.0:
        return np.inf
    return tms * 13.5 / (M - 1.0)


# ---------------------------------------------------------------------------
# Selectivity check
# ---------------------------------------------------------------------------

def check_selectivity(relay_settings_list, delta_I_margin_pu=0.20):
    """
    Check whether pickup settings satisfy the selectivity constraint.

    Parameters
    ----------
    relay_settings_list : list[dict]
        Ordered list of relay settings dicts (upstream → downstream).
        Each dict must contain "pickup_pu".
    delta_I_margin_pu   : float
        Required pickup margin between adjacent relays (pu).

    Returns
    -------
    dict with keys:
        selectivity_ok : bool — True if all pairs satisfy the constraint
        violations     : list of (upstream_idx, downstream_idx) pairs
        margins        : list of floats — I_p[k] − I_p[k+1] per pair
    """
    n = len(relay_settings_list)
    violations = []
    margins    = []

    for k in range(n - 1):
        ip_up   = float(relay_settings_list[k]["pickup_pu"])
        ip_down = float(relay_settings_list[k + 1]["pickup_pu"])
        margin  = ip_up - ip_down
        margins.append(margin)
        if margin < delta_I_margin_pu - 1e-9:   # 1e-9 tolerates IEEE 754 rounding
            violations.append((k, k + 1))

    return {
        "selectivity_ok": len(violations) == 0,
        "violations":     violations,
        "margins":        margins,
    }


# ---------------------------------------------------------------------------
# Selectivity enforcement
# ---------------------------------------------------------------------------

def enforce_selectivity(
    relay_settings_list,
    delta_I_margin_pu=0.20,
    pickup_max_pu=3.0,
    max_iter=10,
):
    """
    Enforce the selectivity constraint by adjusting pickup settings.

    Does NOT modify the input list — returns a new list of corrected dicts.

    Algorithm
    ---------
    Greedy cascade (downstream → upstream):
    For each adjacent pair (upstream k, downstream k+1):
        if I_p[k] < I_p[k+1] + delta_I_margin_pu:
            I_p[k] = I_p[k+1] + delta_I_margin_pu
            (clip to pickup_max_pu)
    Repeat until no violations remain or max_iter is reached.

    Parameters
    ----------
    relay_settings_list : list[dict] — ordered upstream → downstream
    delta_I_margin_pu   : float — minimum pickup separation (pu)
    pickup_max_pu       : float — hard upper limit on pickup (pu)
    max_iter            : int   — maximum correction passes

    Returns
    -------
    list[dict] — corrected relay settings (deep copy of input + corrections)
    """
    settings = copy.deepcopy(relay_settings_list)
    n = len(settings)

    for _ in range(max_iter):
        changed = False
        # Scan upstream direction (from downstream end up)
        for k in range(n - 2, -1, -1):
            ip_up   = float(settings[k]["pickup_pu"])
            ip_down = float(settings[k + 1]["pickup_pu"])
            required = ip_down + delta_I_margin_pu
            if ip_up < required:
                settings[k]["pickup_pu"] = float(np.clip(required, 0.0, pickup_max_pu))
                changed = True
        if not changed:
            break

    return settings


# ---------------------------------------------------------------------------
# Time-grading check
# ---------------------------------------------------------------------------

def check_time_grading(
    relay_settings_list,
    I_fault_min_pu,
    delta_t_grade_s=0.15,
):
    """
    Check whether trip time grading is satisfied at the minimum fault current.

    Uses the IEC Very Inverse operate time formula:
        t_op = TMS × 13.5 / (M − 1)

    Parameters
    ----------
    relay_settings_list : list[dict]
        Each dict must have "pickup_pu" and "tms".
    I_fault_min_pu      : float — minimum expected fault current (pu)
    delta_t_grade_s     : float — required time margin between relays (s),
                          default 0.15 s (numerical relay IEC 60255 guidance)

    Returns
    -------
    dict with keys:
        grading_ok  : bool
        violations  : list of (upstream_idx, downstream_idx)
        margins_s   : list of floats — t_op[k] − t_op[k+1] per pair
        trip_times  : list of floats — operate time per relay at I_fault_min
    """
    trip_times = []
    for rs in relay_settings_list:
        t_op = _iec_very_inverse_time(
            tms=float(rs["tms"]),
            pickup_pu=float(rs["pickup_pu"]),
            i_rms_pu=I_fault_min_pu,
        )
        trip_times.append(t_op)

    n = len(trip_times)
    violations = []
    margins_s  = []

    for k in range(n - 1):
        margin = trip_times[k] - trip_times[k + 1]
        margins_s.append(margin)
        if margin < delta_t_grade_s:
            violations.append((k, k + 1))

    return {
        "grading_ok":  len(violations) == 0,
        "violations":  violations,
        "margins_s":   margins_s,
        "trip_times":  trip_times,
    }


# ---------------------------------------------------------------------------
# Time-grading enforcement
# ---------------------------------------------------------------------------

def enforce_time_grading(
    relay_settings_list,
    I_fault_min_pu,
    delta_t_grade_s=0.15,
    tms_min=0.02,
    tms_max=0.5,
    max_iter=10,
):
    """
    Enforce time-grading by minimally adjusting TMS values.

    To restore grading for a violation at pair (k, k+1):
        Reduce TMS[k+1] so that t_op[k+1] decreases by the required margin.
        t_op_required[k+1] = t_op[k] - delta_t_grade_s
        TMS_new[k+1] = TMS_old[k+1] * t_op_required / t_op_old[k+1]

    Parameters
    ----------
    relay_settings_list : list[dict]
    I_fault_min_pu      : float
    delta_t_grade_s     : float
    tms_min, tms_max    : float — hard TMS bounds
    max_iter            : int

    Returns
    -------
    list[dict] — corrected relay settings (deep copy)
    """
    settings = copy.deepcopy(relay_settings_list)
    n = len(settings)

    for _ in range(max_iter):
        changed = False
        for k in range(n - 2, -1, -1):
            t_up   = _iec_very_inverse_time(
                float(settings[k]["tms"]),
                float(settings[k]["pickup_pu"]),
                I_fault_min_pu,
            )
            t_down = _iec_very_inverse_time(
                float(settings[k + 1]["tms"]),
                float(settings[k + 1]["pickup_pu"]),
                I_fault_min_pu,
            )
            if np.isinf(t_up) or np.isinf(t_down):
                continue   # relay not in pickup — skip

            required_t_down = t_up - delta_t_grade_s
            if required_t_down <= 0.0:
                required_t_down = 0.01   # minimum physically reasonable value

            if t_down > required_t_down + 1e-4:
                # Scale down TMS of downstream relay
                scale = required_t_down / (t_down + 1e-12)
                tms_new = float(settings[k + 1]["tms"]) * scale
                tms_new = float(np.clip(tms_new, tms_min, tms_max))
                settings[k + 1]["tms"] = tms_new
                changed = True

        if not changed:
            break

    return settings


# ---------------------------------------------------------------------------
# Compute coordination metrics (for evaluation/metrics.py integration)
# ---------------------------------------------------------------------------

def compute_coordination_metrics(relay_settings_list, I_fault_min_pu,
                                  delta_I_margin_pu=0.20,
                                  delta_t_grade_s=0.15):
    """
    Return a combined coordination metrics dict for reporting.

    Parameters
    ----------
    relay_settings_list : list[dict] — ordered upstream → downstream
    I_fault_min_pu      : float — minimum fault current for time-grading check
    delta_I_margin_pu   : float
    delta_t_grade_s     : float

    Returns
    -------
    dict with keys:
        n_relays              : int
        selectivity_ok        : bool
        n_selectivity_violations : int
        pickup_margins        : list[float]
        grading_ok            : bool
        n_grading_violations  : int
        grading_margins_s     : list[float]
        trip_times            : list[float]
    """
    sel  = check_selectivity(relay_settings_list, delta_I_margin_pu)
    grad = check_time_grading(relay_settings_list, I_fault_min_pu, delta_t_grade_s)

    return {
        "n_relays":                   len(relay_settings_list),
        "selectivity_ok":             sel["selectivity_ok"],
        "n_selectivity_violations":   len(sel["violations"]),
        "pickup_margins":             sel["margins"],
        "grading_ok":                 grad["grading_ok"],
        "n_grading_violations":       len(grad["violations"]),
        "grading_margins_s":          grad["margins_s"],
        "trip_times":                 grad["trip_times"],
    }
