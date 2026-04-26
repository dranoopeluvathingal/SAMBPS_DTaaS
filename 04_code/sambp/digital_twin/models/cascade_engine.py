#!/usr/bin/env python3
# =============================================================================
# sambp / digital_twin / models / cascade_engine.py
#
# TR-88  N-2 Cascading Contingency Engine
# =========================================
# Models post-N-2 cascade propagation on the IEEE 118-bus network.
#
# Architecture
# ------------
#   N2Contingency      — one (line_a, line_b) initial outage pair
#   CascadeStep        — one propagation step at a given cascade depth
#   CascadeScenario    — full scenario: initial outage + all cascade steps
#   CascadeEngine      — generates contingencies, runs cascade, counts misops
#
# Cascade logic
# -------------
# Depth 0: Remove lines (line_a, line_b) → compute power redistribution
# Depth d: For each overloaded line (loading > overload_threshold):
#           → trip it → recompute flows → check SAMBP verdict
#           → increment misoperation counter if verdict == RESTRAIN
#              on a line that should have tripped (overloaded)
#
# SAMBP verdict model (simplified for cascade context)
# ----------------------------------------------------
# A relay is said to TRIP correctly if the line loading > 120% of rating.
# A relay MISOPERATES if it TRIPs a non-overloaded line OR
#                          RESTRAINs on an overloaded line.
#
# The SAMBP stack reduces misoperation rate by comparing apparent impedance
# against the IBR-corrected Thevenin model:
#   P_misop(SAMBP) = P_misop(conventional) × (1 - η_ibr)
#   η_ibr = 0.30 × f_ibr  (30% improvement per unit IBR fraction)
#
# Source code: 04_code/sambp/digital_twin/models/cascade_engine.py
# =============================================================================

from __future__ import annotations

import copy
import itertools
import random
import warnings
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandapower as pp

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_OVERLOAD_THRESHOLD = 1.10   # 110% of rating triggers cascade trip
_MAX_DEPTH          = 8      # maximum cascade depth before termination
_MAX_TRIPS_PER_STEP = 5      # max lines tripped per depth level
_BASE_MISOP_PROB    = 0.18   # baseline misoperation probability (conventional relay)
_IBR_MISOP_REDUCTION = 0.30  # SAMBP reduces misop by 30% per unit f_ibr


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class N2Contingency:
    """Initial N-2 contingency: two simultaneously tripped lines."""
    line_a: int        # pandapower line index
    line_b: int        # pandapower line index
    contingency_id: int = 0


@dataclass
class CascadeStep:
    """One step in the cascade propagation."""
    depth:            int          # cascade depth (0 = initial outage)
    tripped_lines:    List[int]    # line indices tripped at this depth
    overloaded_lines: List[int]    # lines exceeding overload threshold
    misops_correct:   int = 0      # correct trips (overloaded line tripped)
    misops_false_trip: int = 0     # false trips (healthy line tripped)
    misops_restrain:  int = 0      # failure to trip overloaded line
    n_buses_affected: int = 0      # buses disconnected at this depth
    max_loading_pu:   float = 0.0  # maximum line loading at start of step


@dataclass
class CascadeScenario:
    """Complete cascade scenario from N-2 to termination."""
    contingency_id:    int
    line_a:            int
    line_b:            int
    ibr_penetration:   float
    f_ibr:             float          # fraction IBR at affected buses
    steps:             List[CascadeStep] = field(default_factory=list)
    total_depth:       int = 0        # final cascade depth reached
    total_misops:      int = 0        # total misoperations across all depths
    total_lines_lost:  int = 0        # total lines tripped (including cascade)
    total_buses_lost:  int = 0        # total buses islanded/disconnected
    terminated_by:     str = 'stable' # 'stable'|'max_depth'|'island'|'blackout'

    def add_step(self, step: CascadeStep) -> None:
        self.steps.append(step)
        self.total_depth = step.depth
        self.total_misops += (step.misops_false_trip + step.misops_restrain)
        self.total_lines_lost += len(step.tripped_lines)
        self.total_buses_lost += step.n_buses_affected


# ---------------------------------------------------------------------------
# Cascade Engine
# ---------------------------------------------------------------------------

class CascadeEngine:
    """
    N-2 cascading contingency engine for IEEE 118-bus.

    Parameters
    ----------
    ibr_penetration : float
        Network-wide IBR penetration [0, 1].
    ibr_mode : str
        'gfl' | 'gfm' | 'mixed'
    seed : int
        Random seed for reproducibility.
    """

    def __init__(self,
                 ibr_penetration: float = 0.30,
                 ibr_mode:        str   = 'gfl',
                 seed:            int   = 0) -> None:
        self.ibr_penetration = ibr_penetration
        self.ibr_mode        = ibr_mode
        self._rng            = np.random.default_rng(seed)
        self._base_net       = None
        self._line_ratings   = {}   # line_idx → MVA rating
        self._load()

    # ------------------------------------------------------------------
    def _load(self) -> None:
        """Load case118, set realistic thermal ratings, and cache them."""
        self._base_net = pp.networks.case118()
        net = self._base_net

        # case118() has unrealistically large max_i_ka (→ ~9900 MVA ratings).
        # Replace with realistic IEEE 118-bus thermal limits derived from
        # line impedance: rating = V²/(X × 2) as a rough SIL proxy,
        # capped between 50 and 500 MVA per typical 118-bus data.
        for lidx in net.line.index:
            from_bus = int(net.line.at[lidx, 'from_bus'])
            vn_kv    = float(net.bus.at[from_bus, 'vn_kv'])
            length   = max(1.0, float(net.line.at[lidx, 'length_km']))
            x_ohm_km = float(net.line.at[lidx, 'x_ohm_per_km'])
            x_total  = max(0.01, x_ohm_km * length)
            z_base   = (vn_kv ** 2) / 100.0   # 100 MVA base
            x_pu     = x_total / z_base

            # SIL proxy: P_max ≈ V²/X (pu × base_mva)
            p_max_mva = 100.0 / max(x_pu, 0.01)
            # Clip to realistic range for 118-bus (50–400 MVA)
            rating_mva = float(np.clip(p_max_mva, 50.0, 400.0))
            self._line_ratings[lidx] = rating_mva

            # Set max_i_ka to match this rating: I = S / (√3 · V)
            new_i_ka = rating_mva / (np.sqrt(3) * vn_kv) if vn_kv > 0 else 1.0
            net.line.at[lidx, 'max_i_ka'] = new_i_ka

    # ------------------------------------------------------------------
    def _fresh_net(self, load_scale: float = 1.20) -> pp.pandapowerNet:
        """Return a deep copy of base net with loads scaled for stress testing."""
        net = copy.deepcopy(self._base_net)
        net.load['p_mw']   *= load_scale
        net.load['q_mvar'] *= load_scale
        return net

    # ------------------------------------------------------------------
    def _f_ibr_at_lines(self, net: pp.pandapowerNet,
                         line_indices: List[int]) -> float:
        """
        Estimate IBR fraction near affected lines (network-wide proxy).
        In a full model this would be bus-local; here we use the global
        penetration as a conservative estimate.
        """
        return self.ibr_penetration

    # ------------------------------------------------------------------
    def _run_pf(self, net: pp.pandapowerNet) -> bool:
        """Run AC power flow; return True if converged."""
        try:
            pp.runpp(net, algorithm='nr', numba=False,
                     verbose=False, max_iteration=30,
                     init='flat')
            return net.converged
        except Exception:
            return False

    # ------------------------------------------------------------------
    def _line_loadings(self, net: pp.pandapowerNet) -> Dict[int, float]:
        """
        Return {line_idx: loading_pu} for all in-service lines.
        loading_pu = S_actual / S_rating.
        """
        loadings = {}
        if net.res_line is None or len(net.res_line) == 0:
            return loadings
        for lidx in net.line.index:
            if not net.line.at[lidx, 'in_service']:
                continue
            try:
                loading_pct = float(net.res_line.at[lidx, 'loading_percent'])
                if np.isfinite(loading_pct):
                    loadings[lidx] = loading_pct / 100.0
            except (KeyError, TypeError):
                pass
        return loadings

    # ------------------------------------------------------------------
    def _trip_line(self, net: pp.pandapowerNet, line_idx: int) -> None:
        net.line.at[line_idx, 'in_service'] = False

    # ------------------------------------------------------------------
    def _count_connected_buses(self, net: pp.pandapowerNet) -> int:
        """Count buses that remain connected to the slack bus."""
        try:
            import pandapower.topology as top
            mg = top.create_nxgraph(net, include_out_of_service=False)
            import networkx as nx
            slack_bus = int(net.ext_grid.at[net.ext_grid.index[0], 'bus'])
            if slack_bus not in mg:
                return 0
            cc = nx.node_connected_component(mg.to_undirected(), slack_bus)
            return len(cc)
        except Exception:
            return len(net.bus)

    # ------------------------------------------------------------------
    def _sambp_verdict(self,
                       line_idx:    int,
                       loading_pu:  float,
                       f_ibr:       float) -> str:
        """
        Simulate SAMBP relay verdict for a line at given loading.

        Returns 'TRIP' or 'RESTRAIN'.

        For overloaded lines (loading > 1.0):
            P(correct TRIP) = 1 - P(misop_restrain)
            P(misop_restrain) = BASE_MISOP × (1 - η_ibr) × severity_factor

        For non-overloaded lines:
            P(false TRIP) = BASE_MISOP × (1 - η_ibr) × (1 - loading_pu)
        """
        eta_ibr    = _IBR_MISOP_REDUCTION * f_ibr
        p_base     = _BASE_MISOP_PROB * (1.0 - eta_ibr)

        if loading_pu > _OVERLOAD_THRESHOLD:
            # Should trip — misop = fail to trip
            severity = min(1.0, (loading_pu - _OVERLOAD_THRESHOLD) / 0.5)
            p_restrain = p_base * (1.0 - severity)  # worse overload → less restrain
            verdict = 'RESTRAIN' if self._rng.random() < p_restrain else 'TRIP'
        else:
            # Should not trip — misop = false trip
            margin = max(0.0, 1.0 - loading_pu)
            p_false_trip = p_base * margin * 0.5
            verdict = 'TRIP' if self._rng.random() < p_false_trip else 'RESTRAIN'

        return verdict

    # ------------------------------------------------------------------
    def run_scenario(self, contingency: N2Contingency) -> CascadeScenario:
        """
        Simulate one N-2 cascade scenario.

        Steps:
        1. Trip line_a and line_b (initial N-2 event).
        2. Run power flow.
        3. Find overloaded lines (loading > threshold).
        4. For each overloaded line, get SAMBP verdict.
        5. Trip lines where verdict == TRIP.
        6. Repeat from step 2 until no new trips or max_depth reached.
        """
        f_ibr = self._f_ibr_at_lines(None, [contingency.line_a,
                                            contingency.line_b])
        scenario = CascadeScenario(
            contingency_id  = contingency.contingency_id,
            line_a          = contingency.line_a,
            line_b          = contingency.line_b,
            ibr_penetration = self.ibr_penetration,
            f_ibr           = f_ibr,
        )

        net = self._fresh_net()
        initial_connected = self._count_connected_buses(net)

        # ── Depth 0: initial N-2 outage ──────────────────────────────
        self._trip_line(net, contingency.line_a)
        self._trip_line(net, contingency.line_b)

        step0 = CascadeStep(
            depth         = 0,
            tripped_lines = [contingency.line_a, contingency.line_b],
            overloaded_lines = [],
        )
        converged = self._run_pf(net)
        if not converged:
            step0.n_buses_affected = initial_connected
            scenario.add_step(step0)
            scenario.terminated_by = 'blackout'
            return scenario

        loadings = self._line_loadings(net)
        step0.max_loading_pu = max(loadings.values(), default=0.0)
        step0.overloaded_lines = [l for l, ld in loadings.items()
                                  if ld > _OVERLOAD_THRESHOLD]
        connected_after = self._count_connected_buses(net)
        step0.n_buses_affected = max(0, initial_connected - connected_after)
        scenario.add_step(step0)

        # ── Depths 1..MAX_DEPTH: cascade propagation ─────────────────
        for depth in range(1, _MAX_DEPTH + 1):
            overloaded = [l for l, ld in loadings.items()
                          if ld > _OVERLOAD_THRESHOLD]
            if not overloaded:
                scenario.terminated_by = 'stable'
                break

            step = CascadeStep(
                depth            = depth,
                tripped_lines    = [],
                overloaded_lines = overloaded,
                max_loading_pu   = max(loadings[l] for l in overloaded),
            )

            # Evaluate SAMBP verdict for each overloaded line
            # Limit to _MAX_TRIPS_PER_STEP worst lines (sorted by loading)
            overloaded_sorted = sorted(overloaded,
                                       key=lambda l: loadings[l],
                                       reverse=True)[:_MAX_TRIPS_PER_STEP]

            for lidx in overloaded_sorted:
                loading = loadings[lidx]
                verdict = self._sambp_verdict(lidx, loading, f_ibr)
                if verdict == 'TRIP':
                    step.misops_correct += 1
                    step.tripped_lines.append(lidx)
                    self._trip_line(net, lidx)
                else:
                    # RESTRAIN on overloaded line = misoperation
                    step.misops_restrain += 1

            # Also check for false trips on healthy lines (5% of in-service)
            healthy_lines = [l for l, ld in loadings.items()
                             if ld <= _OVERLOAD_THRESHOLD]
            n_check = max(1, len(healthy_lines) // 20)  # 5% sample
            for lidx in self._rng.choice(healthy_lines,
                                         size=min(n_check, len(healthy_lines)),
                                         replace=False):
                loading = loadings[lidx]
                verdict = self._sambp_verdict(lidx, loading, f_ibr)
                if verdict == 'TRIP':
                    step.misops_false_trip += 1
                    step.tripped_lines.append(lidx)
                    self._trip_line(net, lidx)

            if not step.tripped_lines:
                # All overloaded lines received RESTRAIN — cascade stalls
                scenario.terminated_by = 'stable'
                scenario.add_step(step)
                break

            # Rerun power flow
            converged = self._run_pf(net)
            if not converged:
                step.n_buses_affected = max(
                    0, initial_connected - self._count_connected_buses(net))
                scenario.add_step(step)
                scenario.terminated_by = 'blackout'
                break

            loadings = self._line_loadings(net)
            conn_now = self._count_connected_buses(net)
            step.n_buses_affected = max(0, initial_connected - conn_now)
            scenario.add_step(step)

            # Check for island condition
            if conn_now < initial_connected * 0.5:
                scenario.terminated_by = 'island'
                break

            if depth == _MAX_DEPTH:
                scenario.terminated_by = 'max_depth'

        return scenario

    # ------------------------------------------------------------------
    def generate_n2_contingencies(self, n: int) -> List[N2Contingency]:
        """
        Generate n random N-2 contingency pairs from the 118-bus network.
        Pairs are sampled without replacement from critical lines (lines
        with high loading in the base case or connecting high-generation buses).
        """
        net = self._fresh_net()
        converged = self._run_pf(net)

        if converged:
            loadings = self._line_loadings(net)
            # Prefer lines with loading > 30% — more likely to trigger cascades
            candidates_hi = [l for l, ld in loadings.items() if ld > 0.30]
            candidates_lo = [l for l, ld in loadings.items()
                             if 0.10 < ld <= 0.30]
            # Mix: 70% from high-loaded, 30% from medium-loaded
            candidates = candidates_hi + candidates_lo[:max(10, len(candidates_hi)//3)]
            if not candidates:
                candidates = list(loadings.keys())
        else:
            candidates = list(net.line.index)

        # Generate n distinct pairs
        all_pairs = list(itertools.combinations(candidates, 2))
        if len(all_pairs) < n:
            n = len(all_pairs)

        chosen_indices = self._rng.choice(len(all_pairs), size=n, replace=False)
        contingencies = []
        for cid, idx in enumerate(chosen_indices):
            la, lb = all_pairs[idx]
            contingencies.append(N2Contingency(
                line_a=int(la),
                line_b=int(lb),
                contingency_id=cid,
            ))
        return contingencies
