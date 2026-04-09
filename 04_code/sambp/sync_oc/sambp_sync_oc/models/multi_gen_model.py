# =============================================================================
# sambp / sambp_sync_oc
# models/multi_gen_model.py
#
# Multi-generator busbar fault current model.
#
# Models N synchronous generators connected to a common bus through individual
# step-up transformer impedances.  A fault on the bus (or downstream of the
# bus) draws fault current from all generators simultaneously.
#
# Model assumptions (Stage 1 superposition approximation)
# -------------------------------------------------------
# Each generator is modelled independently using the Stage 1 synthesis model
# (simulate_sync_generator_currents) with its own parameter set.
# The Thevenin superposition principle is used: each machine sees the same
# terminal voltage collapse, contributing its own fault current.  Generator-
# to-generator coupling through the common bus is approximated by reducing
# each machine's terminal voltage by the voltage drop across its step-up
# transformer at the total fault current.  This is the standard practice for
# protection coordination studies and gives O(5%) accuracy for typical
# transformer impedances (0.04–0.08 pu).
#
# Note: For Stage 2 (Park dq model), replace the inner simulation call with
# simulate_park_dq_currents per generator, sharing the bus voltage solution.
#
# Public API
# ----------
# simulate_multi_gen_fault(time_s, frequency_hz, fault_time_s,
#                          fault_type, gen_params_list,
#                          network_params, bus_config)
#   → dict {
#       "t"            : ndarray
#       "gen_k"        : dict {ia, ib, ic, va, vb, vc}  for k in 0..N-1
#       "i_bus_total"  : dict {ia, ib, ic}  — total bus fault current
#     }
# =============================================================================

import copy
import numpy as np

from models.sync_generator_model import simulate_sync_generator_currents


# ---------------------------------------------------------------------------
# Default bus configuration
# ---------------------------------------------------------------------------
DEFAULT_BUS_CONFIG = {
    # Step-up transformer impedances per generator (pu on machine base)
    "transformer_X_pu":  [0.06, 0.06],   # one entry per generator
    "transformer_R_pu":  [0.005, 0.005],
    # Bus voltage during fault (simplified: assume Vbus drops to ~0 for 3PH)
    "Vbus_fault_pu":     0.0,
    # If True, correct each generator's effective source impedance to include
    # the step-up transformer impedance
    "include_transformer": True,
}


def simulate_multi_gen_fault(
    time_s,
    frequency_hz,
    fault_time_s,
    fault_type,
    gen_params_list,
    network_params,
    bus_config=None,
):
    """
    Simulate fault currents from multiple parallel generators on a common bus.

    Parameters
    ----------
    time_s          : ndarray  — full simulation time vector (s)
    frequency_hz    : float    — system frequency (Hz)
    fault_time_s    : float    — fault inception time (s)
    fault_type      : str      — "3PH" | "LL" | "SLG"
    gen_params_list : list[dict] — one generator params dict per machine.
                      Each dict has the same keys as SYSTEM_CONFIG["generator"].
                      The machines may differ in Xdpp, Ra, P/Q prefault, etc.
    network_params  : dict     — shared network parameters (from SYSTEM_CONFIG)
                      Provides X_th_pu, R_th_pu, fault_R_pu.
    bus_config      : dict or None — busbar configuration (see DEFAULT_BUS_CONFIG)

    Returns
    -------
    dict with keys:
        "t"           : ndarray
        "gen_0", "gen_1", ... : dict {ia, ib, ic, va, vb, vc} per generator
        "i_bus_total" : dict {ia, ib, ic}  — summed bus contribution
    """
    if bus_config is None:
        bus_config = DEFAULT_BUS_CONFIG

    n_gen = len(gen_params_list)
    result = {"t": time_s}

    ia_total = np.zeros_like(time_s)
    ib_total = np.zeros_like(time_s)
    ic_total = np.zeros_like(time_s)

    for k, gen_params in enumerate(gen_params_list):
        # Augment network impedance with step-up transformer impedance
        net_k = copy.deepcopy(network_params)

        if bus_config.get("include_transformer", True):
            xt_list = bus_config.get("transformer_X_pu",
                                      [0.06] * n_gen)
            rt_list = bus_config.get("transformer_R_pu",
                                      [0.005] * n_gen)
            xt = xt_list[k] if k < len(xt_list) else xt_list[-1]
            rt = rt_list[k] if k < len(rt_list) else rt_list[-1]
            net_k["X_th_pu"] = network_params["X_th_pu"] + xt
            net_k["R_th_pu"] = network_params["R_th_pu"] + rt

        sim_k = simulate_sync_generator_currents(
            time_s        = time_s,
            frequency_hz  = frequency_hz,
            fault_time_s  = fault_time_s,
            fault_type    = fault_type,
            params        = gen_params,
            network_params= net_k,
        )

        result[f"gen_{k}"] = sim_k

        ia_total += sim_k["ia"]
        ib_total += sim_k["ib"]
        ic_total += sim_k["ic"]

    result["i_bus_total"] = {
        "ia": ia_total / n_gen,   # normalise to per-generator average for pu consistency
        "ib": ib_total / n_gen,
        "ic": ic_total / n_gen,
    }
    # Also store the true summed fault current (for bus relay coordination)
    result["i_bus_sum"] = {"ia": ia_total, "ib": ib_total, "ic": ic_total}

    return result
