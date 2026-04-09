# =============================================================================
# sambp / sambp_sync_oc
# evaluation/metrics.py
#
# Waveform fit metrics and protection performance metrics.
#
# Public API
# ----------
# compute_fit_metrics(ia_meas, ia_est, ib_meas, ib_est, ic_meas, ic_est)
#   → dict
# compute_protection_metrics(fixed_result, adaptive_result)
#   → dict
# =============================================================================

import numpy as np

# Coordination metrics imported lazily inside compute_coordination_metrics
# to avoid circular imports (coordination_logic imports nothing from evaluation)


# ---------------------------------------------------------------------------
# Waveform fit metrics
# ---------------------------------------------------------------------------

def compute_fit_metrics(ia_meas, ia_est, ib_meas, ib_est, ic_meas, ic_est):
    """
    Compute waveform-level goodness-of-fit metrics between measured and
    estimated three-phase currents.

    Parameters
    ----------
    ia_meas, ib_meas, ic_meas : array-like — measured currents (pu)
    ia_est,  ib_est,  ic_est  : array-like — model-estimated currents (pu)

    Returns
    -------
    dict with keys (per phase + combined):
        rmse_a, rmse_b, rmse_c     : float — RMSE per phase (pu)
        rmse_combined              : float — RMSE over all three phases
        nrmse_a, nrmse_b, nrmse_c  : float — normalised RMSE (% of peak meas)
        peak_error_a, _b, _c       : float — max absolute error per phase (pu)
        r2_a, r2_b, r2_c           : float — R² coefficient of determination
        r2_combined                : float — R² over concatenated signals
    """
    results = {}
    combined_meas, combined_est = [], []

    for ph, meas, est in [("a", ia_meas, ia_est),
                           ("b", ib_meas, ib_est),
                           ("c", ic_meas, ic_est)]:
        meas = np.asarray(meas, dtype=float)
        est  = np.asarray(est,  dtype=float)

        err       = meas - est
        rmse      = float(np.sqrt(np.mean(err ** 2)))
        peak_meas = float(np.max(np.abs(meas))) + 1e-12
        nrmse     = rmse / peak_meas
        peak_err  = float(np.max(np.abs(err)))

        ss_res = np.sum(err ** 2)
        ss_tot = np.sum((meas - np.mean(meas)) ** 2) + 1e-14
        r2     = float(1.0 - ss_res / ss_tot)

        results[f"rmse_{ph}"]       = rmse
        results[f"nrmse_{ph}"]      = nrmse
        results[f"peak_error_{ph}"] = peak_err
        results[f"r2_{ph}"]         = r2

        combined_meas.append(meas)
        combined_est.append(est)

    # Combined across all phases
    cm = np.concatenate(combined_meas)
    ce = np.concatenate(combined_est)
    err_all = cm - ce
    results["rmse_combined"] = float(np.sqrt(np.mean(err_all ** 2)))
    ss_res_all = np.sum(err_all ** 2)
    ss_tot_all = np.sum((cm - np.mean(cm)) ** 2) + 1e-14
    results["r2_combined"]   = float(1.0 - ss_res_all / ss_tot_all)

    return results


# ---------------------------------------------------------------------------
# Protection performance metrics
# ---------------------------------------------------------------------------

def compute_protection_metrics(fixed_result, adaptive_result):
    """
    Compare trip times, pickup success, and security between fixed and
    adaptive relay responses.

    Parameters
    ----------
    fixed_result    : dict — output of run_overcurrent_relay (fixed settings)
    adaptive_result : dict — output of run_overcurrent_relay (adaptive settings)

    Returns
    -------
    dict with keys:
        fixed_trip_time    : float or None — trip time with fixed settings (s)
        adaptive_trip_time : float or None — trip time with adaptive settings (s)
        trip_time_delta    : float or None — adaptive − fixed (negative = faster)
        fixed_tripped      : bool
        adaptive_tripped   : bool
        speed_improvement  : bool — True if adaptive tripped faster
        security_maintained: bool — True if adaptive did not trip when fixed didn't
        pickup_count_fixed : int  — number of samples in pickup
        pickup_count_adaptive: int
    """
    t_fixed    = fixed_result.get("trip_time")
    t_adaptive = adaptive_result.get("trip_time")

    fixed_tripped    = t_fixed    is not None
    adaptive_tripped = t_adaptive is not None

    delta = None
    if fixed_tripped and adaptive_tripped:
        delta = float(t_adaptive - t_fixed)

    speed_improvement  = (fixed_tripped and adaptive_tripped and delta < 0.0)
    security_maintained = not (adaptive_tripped and not fixed_tripped)

    return {
        "fixed_trip_time":       t_fixed,
        "adaptive_trip_time":    t_adaptive,
        "trip_time_delta":       delta,
        "fixed_tripped":         fixed_tripped,
        "adaptive_tripped":      adaptive_tripped,
        "speed_improvement":     speed_improvement,
        "security_maintained":   security_maintained,
        "pickup_count_fixed":    int(np.sum(fixed_result.get("pickup",    []))),
        "pickup_count_adaptive": int(np.sum(adaptive_result.get("pickup", []))),
    }


# ---------------------------------------------------------------------------
# Multi-generator coordination metrics (thin wrapper)
# ---------------------------------------------------------------------------

def compute_coordination_metrics(relay_settings_list, I_fault_min_pu,
                                  delta_I_margin_pu=0.20,
                                  delta_t_grade_s=0.15):
    """
    Compute pickup selectivity and time-grading metrics for an ordered list
    of relay settings (upstream → downstream).

    Delegates to adaptation.coordination_logic.compute_coordination_metrics.
    """
    from adaptation.coordination_logic import compute_coordination_metrics as _ccm
    return _ccm(relay_settings_list, I_fault_min_pu,
                delta_I_margin_pu, delta_t_grade_s)
