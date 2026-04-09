# =============================================================================
# sambp / sambp_sync_oc
# evaluation/comparison.py
#
# Produce compact per-case comparison summaries for batch reporting.
#
# Public API
# ----------
# compare_fixed_vs_adaptive(case_result) → dict
# summarise_batch(case_results)          → list[dict]
# =============================================================================

import numpy as np


def compare_fixed_vs_adaptive(case_result):
    """
    Return a compact summary dict for one simulation case.

    Parameters
    ----------
    case_result : dict — expected keys (all optional with defaults):
        "case_name"         : str
        "fault_type"        : str
        "fault_R_pu"        : float
        "fit_metrics"       : dict  — from compute_fit_metrics
        "protection_metrics": dict  — from compute_protection_metrics
        "confidence"        : float — γ from confidence_logic
        "theta_hat"         : dict  — estimated parameters
        "fixed_settings"    : dict  — {"pickup_pu", "tms"}
        "adaptive_settings" : dict  — {"pickup_pu", "tms"}

    Returns
    -------
    dict — flat summary suitable for CSV row or DataFrame record
    """
    fm  = case_result.get("fit_metrics",        {})
    pm  = case_result.get("protection_metrics", {})
    th  = case_result.get("theta_hat",          {})
    fs  = case_result.get("fixed_settings",     {})
    ads = case_result.get("adaptive_settings",  {})

    return {
        # Case identity
        "case_name":              case_result.get("case_name",    ""),
        "fault_type":             case_result.get("fault_type",   ""),
        "fault_R_pu":             case_result.get("fault_R_pu",   float("nan")),

        # Fit quality
        "rmse_combined":          fm.get("rmse_combined",         float("nan")),
        "r2_combined":            fm.get("r2_combined",           float("nan")),
        "peak_error_a":           fm.get("peak_error_a",          float("nan")),

        # Estimation result
        "theta_I_ss":             th.get("I_ss",                  float("nan")),
        "theta_I_sub":            th.get("I_sub",                 float("nan")),
        "theta_tau_ac":           th.get("tau_ac",                float("nan")),
        "theta_I_dc":             th.get("I_dc",                  float("nan")),
        "theta_tau_dc":           th.get("tau_dc",                float("nan")),
        "confidence":             case_result.get("confidence",   float("nan")),

        # Relay settings
        "fixed_pickup_pu":        fs.get("pickup_pu",             float("nan")),
        "fixed_tms":              fs.get("tms",                   float("nan")),
        "adaptive_pickup_pu":     ads.get("pickup_pu",            float("nan")),
        "adaptive_tms":           ads.get("tms",                  float("nan")),

        # Protection performance
        "fixed_trip_time":        pm.get("fixed_trip_time",       float("nan")),
        "adaptive_trip_time":     pm.get("adaptive_trip_time",    float("nan")),
        "trip_time_delta":        pm.get("trip_time_delta",       float("nan")),
        "fixed_tripped":          pm.get("fixed_tripped",         False),
        "adaptive_tripped":       pm.get("adaptive_tripped",      False),
        "speed_improvement":      pm.get("speed_improvement",     False),
        "security_maintained":    pm.get("security_maintained",   True),
    }


def summarise_batch(case_results):
    """
    Apply compare_fixed_vs_adaptive to a list of case results.

    Parameters
    ----------
    case_results : list[dict]

    Returns
    -------
    list[dict] — one summary dict per case, ready for reporting
    """
    return [compare_fixed_vs_adaptive(cr) for cr in case_results]
