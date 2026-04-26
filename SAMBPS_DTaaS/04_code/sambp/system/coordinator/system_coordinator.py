"""
system_coordinator.py
======================
SAMBP system integration coordinator.

Runs all four protection functions simultaneously on a NetworkSnapshot
and collects the trip decisions:

    1. OC relay       — synchronous generator overcurrent (simplified)
    2. 87B_A relay    — bus section A differential
    3. 87L relay      — line differential
    4. 87B_B relay    — bus section B differential
    5. 87T relay      — transformer differential

Each relay runs its conventional baseline + SAMBP zone estimator +
Stage-2 confidence gate.  The coordinator records:
    - which relays trip
    - their source (model / conventional / model_veto / no_trip)
    - trip time (first sample crossing threshold)
    - SAMBP zone parameters (κ_n, f_int)

Selectivity is assessed by comparing the set of tripped relays against
the expected set for each fault scenario.
"""

from __future__ import annotations

import sys, os
import numpy as np
from dataclasses import dataclass

# ---- Add project root to path -----------------------------------------------
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, ".."))

from network.radial_network import NetworkSnapshot

# ---- Load each SAMBP module via direct file path (avoids models/ conflicts) -
import importlib.util as _il_util

_SAMBP = os.path.abspath(os.path.join(_ROOT, ".."))   # .../sambp/


def _load(proj: str, subpkg: str, modname: str):
    """
    Load a SAMBP sub-module in an isolated models namespace.

    Each project's `models/` package conflicts with others in sys.modules.
    Strategy:
      1. Clear all `models.*` entries from sys.modules.
      2. Put this project root at sys.path[0] so its `models/` is found first.
      3. Load the module — its `from models.xxx import` resolves correctly.
      4. Rename `models.*` in sys.modules to `{proj}.models.*` so the next
         project load starts with a clean `models` namespace.
    After renaming, all internal references in the loaded module still work
    because `from models.xxx import YYY` creates direct object references.
    """
    proj_root = os.path.join(_SAMBP, proj)
    qualname  = f"_sambp.{proj}.{subpkg}.{modname}"
    if qualname in sys.modules:
        return sys.modules[qualname]

    # 1. Clear models namespace
    for key in [k for k in sys.modules if k == "models" or k.startswith("models.")]:
        del sys.modules[key]

    # 2. Project root at front of sys.path
    if proj_root in sys.path:
        sys.path.remove(proj_root)
    sys.path.insert(0, proj_root)

    # 3. Load the module
    path = os.path.join(proj_root, subpkg, modname + ".py")
    spec = _il_util.spec_from_file_location(qualname, path)
    mod  = _il_util.module_from_spec(spec)
    sys.modules[qualname] = mod
    spec.loader.exec_module(mod)

    # 4. Rename models.* → {proj}.models.* to avoid cross-project pollution
    for key in [k for k in sys.modules if k == "models" or k.startswith("models.")]:
        sys.modules[f"{proj}.{key}"] = sys.modules.pop(key)

    return mod


# 87B bus differential
_b_base = _load("bus_diff", "models",             "bus_diff_baseline")
_b_est  = _load("bus_diff", "inverse_estimation", "bus_inverse_estimator")
_b_gate = _load("bus_diff", "adaptation",         "bus_confidence_gate")

BusDiffRelayConfig           = _b_base.BusDiffRelayConfig
run_87B_relay                = _b_base.run_87B_relay
estimate_bus_zone_parameters = _b_est.estimate_bus_zone_parameters
BusGateConfig                = _b_gate.BusGateConfig
BusGateState                 = _b_gate.BusGateState
evaluate_87B_confidence_gate = _b_gate.evaluate_87B_confidence_gate

# 87T transformer differential
_t_base = _load("transformer_diff", "models",             "transformer_diff_baseline")
_t_est  = _load("transformer_diff", "inverse_estimation", "transformer_inverse_estimator")
_t_gate = _load("transformer_diff", "adaptation",         "transformer_confidence_gate")

TransformerRelayConfig   = _t_base.TransformerRelayConfig
run_87T_relay            = _t_base.run_87T_relay
_rated_current_H         = _t_base._rated_current_H
_rated_current_X         = _t_base._rated_current_X
compensate_winding       = _t_base.compensate_winding
_vector_group_matrix     = _t_base._vector_group_matrix
tr_estimate              = _t_est.estimate_zone_parameters
ConfidenceGateConfig     = _t_gate.ConfidenceGateConfig
GateState                = _t_gate.GateState
evaluate_confidence_gate = _t_gate.evaluate_confidence_gate

# 87L line differential
_l_base = _load("line_diff", "models",             "line_diff_baseline")
_l_est  = _load("line_diff", "inverse_estimation", "line_inverse_estimator")
_l_gate = _load("line_diff", "adaptation",         "line_confidence_gate")

LineDiffRelayConfig          = _l_base.LineDiffRelayConfig
run_87L_relay                = _l_base.run_87L_relay
estimate_line_zone_parameters = _l_est.estimate_line_zone_parameters
LineConfidenceGateConfig     = _l_gate.LineConfidenceGateConfig
LineGateState                = _l_gate.LineGateState
evaluate_87L_confidence_gate = _l_gate.evaluate_87L_confidence_gate


# ---------------------------------------------------------------------------
# Per-relay result
# ---------------------------------------------------------------------------

@dataclass
class RelayResult:
    relay_id:     str       # "OC" | "87B_A" | "87L" | "87B_B" | "87T"
    final_trip:   bool
    conv_trip:    bool
    source:       str       # "model" | "conventional" | "model_veto" | "no_trip"
    kappa_n:      float
    f_int:        float
    residual_norm: float
    I_op_peak:    float     # peak operate current [pu]


@dataclass
class CoordinatorDecision:
    fault_loc:    str
    fault_type:   str
    I_fault_pu:   float
    relay_results: list[RelayResult]

    @property
    def tripped_relays(self) -> list[str]:
        return [r.relay_id for r in self.relay_results if r.final_trip]

    @property
    def vetoed_relays(self) -> list[str]:
        return [r.relay_id for r in self.relay_results
                if not r.final_trip and r.conv_trip]

    def is_selective(self, expected_trips: set[str]) -> bool:
        return set(self.tripped_relays) == expected_trips


# ---------------------------------------------------------------------------
# Simplified OC relay (standalone, no full SAMBP pipeline)
# ---------------------------------------------------------------------------

def _run_oc_relay(i_pu: np.ndarray, I_oc_pickup: float = 2.5) -> tuple[bool, float]:
    """
    Simple overcurrent relay: trip if any-phase RMS > I_oc_pickup [pu].
    Returns (trip_bool, I_rms_max).
    """
    I_rms = np.sqrt(np.mean(i_pu**2, axis=1))
    I_max  = float(I_rms.max())
    return I_max > I_oc_pickup, I_max


# ---------------------------------------------------------------------------
# Coordinator
# ---------------------------------------------------------------------------

def run_system_coordination(
    snap: NetworkSnapshot,
    I_bus_rated: float = 1.0,    # pu reference (already in pu)
) -> CoordinatorDecision:
    """
    Run all four SAMBP protection functions on a NetworkSnapshot.

    Parameters
    ----------
    snap : NetworkSnapshot from radial_network.generate_network_snapshot
    I_bus_rated : normalisation reference for bus relays (1.0 = already in pu)

    Returns
    -------
    CoordinatorDecision with per-relay results and selectivity info
    """
    t   = snap.time_s
    results = []

    # ------------------------------------------------------------------
    # 1. OC relay (generator overcurrent, simplified instantaneous)
    # ------------------------------------------------------------------
    oc_trip, I_oc_rms = _run_oc_relay(snap.i_oc_pu, I_oc_pickup=1.5)
    results.append(RelayResult(
        relay_id      = "OC",
        final_trip    = oc_trip,
        conv_trip     = oc_trip,
        source        = "conventional" if oc_trip else "no_trip",
        kappa_n       = float("nan"),
        f_int         = float("nan"),
        residual_norm = float("nan"),
        I_op_peak     = I_oc_rms,
    ))

    # ------------------------------------------------------------------
    # 2. 87B_A (Bus A differential)
    # ------------------------------------------------------------------
    cfg_B = BusDiffRelayConfig(n_feeders=2, I_bus_rated_A=1.0)
    dec_B_A = run_87B_relay(t, snap.i_B_A_feeders, cfg_B)

    i_diff_B_A = (snap.i_B_A_feeders[0] + snap.i_B_A_feeders[1])[0]
    est_B_A    = estimate_bus_zone_parameters(t, i_diff_B_A, freq_hz=50.0)
    gs_B_A     = BusGateState()
    gate_B_A, _ = evaluate_87B_confidence_gate(
        est_B_A["state"],
        conventional_trip = dec_B_A.t_trip_s is not None,
        gate_cfg  = BusGateConfig(n_confirm=1),
        gate_state = gs_B_A,
    )
    results.append(RelayResult(
        relay_id      = "87B_A",
        final_trip    = gate_B_A.final_trip,
        conv_trip     = dec_B_A.t_trip_s is not None,
        source        = gate_B_A.source,
        kappa_n       = est_B_A["kappa_n"],
        f_int         = est_B_A["state"].f_int,
        residual_norm = est_B_A["residual_norm"],
        I_op_peak     = float(dec_B_A.I_op.max()),
    ))

    # ------------------------------------------------------------------
    # 3. 87L (line differential)
    # ------------------------------------------------------------------
    cfg_L = LineDiffRelayConfig(channel_delay_samples=0)
    dec_L = run_87L_relay(t, snap.i_L_near_pu, snap.i_L_far_pu, cfg_L)

    i_diff_L = (snap.i_L_near_pu + snap.i_L_far_pu)[0]
    est_L    = estimate_line_zone_parameters(t, i_diff_L, freq_hz=50.0)
    gs_L     = LineGateState()
    gate_L, _ = evaluate_87L_confidence_gate(
        est_L["state"],
        conventional_trip = dec_L.t_trip_s is not None,
        gate_cfg  = LineConfidenceGateConfig(),
        gate_state = gs_L,
    )
    results.append(RelayResult(
        relay_id      = "87L",
        final_trip    = gate_L.final_trip,
        conv_trip     = dec_L.t_trip_s is not None,
        source        = gate_L.source,
        kappa_n       = est_L["kappa_n"],
        f_int         = est_L["state"].f_int,
        residual_norm = est_L["residual_norm"],
        I_op_peak     = float(dec_L.I_op.max()),
    ))

    # ------------------------------------------------------------------
    # 4. 87B_B (Bus B differential)
    # ------------------------------------------------------------------
    dec_B_B = run_87B_relay(t, snap.i_B_B_feeders, cfg_B)

    i_diff_B_B = (snap.i_B_B_feeders[0] + snap.i_B_B_feeders[1])[0]
    est_B_B    = estimate_bus_zone_parameters(t, i_diff_B_B, freq_hz=50.0)
    gs_B_B     = BusGateState()
    gate_B_B, _ = evaluate_87B_confidence_gate(
        est_B_B["state"],
        conventional_trip = dec_B_B.t_trip_s is not None,
        gate_cfg  = BusGateConfig(n_confirm=1),
        gate_state = gs_B_B,
    )
    results.append(RelayResult(
        relay_id      = "87B_B",
        final_trip    = gate_B_B.final_trip,
        conv_trip     = dec_B_B.t_trip_s is not None,
        source        = gate_B_B.source,
        kappa_n       = est_B_B["kappa_n"],
        f_int         = est_B_B["state"].f_int,
        residual_norm = est_B_B["residual_norm"],
        I_op_peak     = float(dec_B_B.I_op.max()),
    ))

    # ------------------------------------------------------------------
    # 5. 87T (transformer differential)
    # ------------------------------------------------------------------
    cfg_T = TransformerRelayConfig()
    # Scale pu waveforms to primary Amperes for 87T relay
    I_H_ref = _rated_current_H(cfg_T)
    I_X_ref = _rated_current_X(cfg_T)
    i_T_H_A = snap.i_T_H_pu * I_H_ref
    i_T_X_A = snap.i_T_X_pu * I_X_ref

    dec_T = run_87T_relay(t, i_T_H_A, i_T_X_A, cfg_T)

    # Compute compensated differential for estimator
    M_X = _vector_group_matrix(cfg_T.vector_group)
    i_Hc = compensate_winding(i_T_H_A, cfg_T.CT_ratio_H, I_H_ref, np.eye(3), 1.0)
    i_Xc = compensate_winding(i_T_X_A, cfg_T.CT_ratio_X, I_X_ref, M_X, 1.0)
    i_diff_T = (i_Hc + i_Xc)[0]

    est_T  = tr_estimate(t, i_diff_T, freq_hz=50.0)
    gs_T   = GateState()
    gate_T, _ = evaluate_confidence_gate(
        est_T["state"],
        conventional_trip = dec_T.t_trip_s is not None,
        gate_cfg  = ConfidenceGateConfig(n_confirm=1),
        gate_state = gs_T,
    )
    results.append(RelayResult(
        relay_id      = "87T",
        final_trip    = gate_T.final_trip,
        conv_trip     = dec_T.t_trip_s is not None,
        source        = gate_T.source,
        kappa_n       = est_T["kappa_n"],
        f_int         = est_T["state"].f_int,
        residual_norm = est_T["residual_norm"],
        I_op_peak     = float(dec_T.I_op.max()),
    ))

    return CoordinatorDecision(
        fault_loc     = snap.fault_loc,
        fault_type    = snap.fault_type,
        I_fault_pu    = snap.I_fault_pu,
        relay_results = results,
    )


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from network.radial_network import generate_network_snapshot

    snap = generate_network_snapshot("transformer_hv", "3ph")
    dec  = run_system_coordination(snap)

    print(f"Fault: {dec.fault_loc}  I_f={dec.I_fault_pu:.2f} pu")
    for r in dec.relay_results:
        print(f"  {r.relay_id:7s}: trip={r.final_trip}  source={r.source:14s}  "
              f"I_op={r.I_op_peak:.2f}  "
              f"κ_n={r.kappa_n:.1f}  f_int={r.f_int:.3f}")

    print(f"\nTripped: {dec.tripped_relays}")
    print(f"Vetoed:  {dec.vetoed_relays}")
    print("system_coordinator self-test done.")
