# =============================================================================
# sambp / digital_twin / models / ieee118_network.py
#
# IEEE 118-bus test network with IBR overlay — TR-86 WP 86.1
#
# Wraps pandapower.networks.case118() and adds:
#   • IBR penetration overlay (replace top-N generators by capacity)
#   • Fault injection at any bus (3PH, SLG, DLG, LL)
#   • FaultState118 compatible with SAMBPStack86
#   • Load scaling for Monte Carlo load-level variation
#
# Public API
# ----------
#   cfg = IEEE118Config(ibr_penetration=0.30, ibr_mode='gfl')
#   net = IEEE118Network.from_config(cfg)
#   fs  = net.inject_fault(bus_idx=5, fault_type='SLG', R_f_ohm=0.5)
#   net.clear_fault()
#   info = net.get_ibr_info()
# =============================================================================

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandapower as pp
import pandapower.shortcircuit as sc

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

import copy

# ---------------------------------------------------------------------------
# Module-level case118 singleton — loaded once, deep-copied per network
# ---------------------------------------------------------------------------
_CASE118_BASE = None

def _get_case118_base():
    """Return the cached case118 base network (load once per process)."""
    global _CASE118_BASE
    if _CASE118_BASE is None:
        _CASE118_BASE = pp.networks.case118()
    return _CASE118_BASE


# ---------------------------------------------------------------------------
# FaultState118
# ---------------------------------------------------------------------------

@dataclass
class FaultState118:
    """Snapshot of the electrical state during a fault on the 118-bus network."""
    scenario_id:      int
    bus_idx:          int         # pandapower bus index (0-based)
    fault_type:       str         # '3PH', 'SLG', 'DLG', 'LL'
    R_f_ohm:          float       # fault resistance [Ω]
    I_pos_pu:         float       # positive-sequence current [pu]
    I_neg_pu:         float       # negative-sequence current [pu]
    V_pos_pu:         float       # positive-sequence bus voltage after fault [pu]
    k_ibr:            float       # IBR fraction at/near fault bus
    f_gfm:            float       # GFM fraction at/near fault bus
    protection_zone:  str         # 'zone1', 'zone2', 'none'
    z_line_pu:        float       # representative line impedance [pu]


# ---------------------------------------------------------------------------
# IEEE118Config
# ---------------------------------------------------------------------------

@dataclass
class IEEE118Config:
    """Configuration for the 118-bus IBR overlay."""
    ibr_penetration: float = 0.0      # fraction of gen capacity replaced by IBR {0,0.3,0.5,1.0}
    ibr_mode:        str   = 'gfl'    # 'gfl', 'gfm', 'mixed'
    load_level:      float = 1.0      # load scaling factor (0.7 – 1.3)
    base_mva:        float = 100.0    # system base

    def __post_init__(self) -> None:
        valid_modes = ('gfl', 'gfm', 'mixed')
        if self.ibr_mode not in valid_modes:
            raise ValueError(f"ibr_mode must be one of {valid_modes}")
        if not (0.0 <= self.ibr_penetration <= 1.0):
            raise ValueError("ibr_penetration must be in [0, 1]")


# ---------------------------------------------------------------------------
# IEEE118Network
# ---------------------------------------------------------------------------

class IEEE118Network:
    """
    IEEE 118-bus test network with IBR overlay for large-scale Monte Carlo.

    The network is built from pandapower.networks.case118(). IBR penetration
    replaces the top-N generators (sorted by rated MW) with virtual IBR
    sources whose fault contribution is modelled analytically.
    """

    def __init__(self, cfg: IEEE118Config) -> None:
        self.cfg = cfg
        self._net = None
        self._ibr_bus_map: Dict[int, dict] = {}   # bus_idx → {k_ibr, f_gfm, I_max}
        self._gen_rated: Dict[int, float] = {}     # gen_idx → rated MW
        self._active_fault: Optional[dict] = None
        self._build()

    # ------------------------------------------------------------------
    @classmethod
    def from_config(cls, cfg: IEEE118Config) -> 'IEEE118Network':
        return cls(cfg)

    # ------------------------------------------------------------------
    def _build(self) -> None:
        """Load case118 and apply IBR overlay + load scaling."""
        self._net = copy.deepcopy(_get_case118_base())
        net = self._net

        # Scale loads
        if self.cfg.load_level != 1.0:
            net.load['p_mw']   = net.load['p_mw']   * self.cfg.load_level
            net.load['q_mvar'] = net.load['q_mvar']  * self.cfg.load_level

        # Pre-cache per-bus Thevenin data (avoid runpp in inject_fault)
        self._v_pre_cache: Dict[int, float] = {}
        self._z_th_cache:  Dict[int, complex] = {}

        # Collect generator capacities
        # case118 uses gen table (not ext_grid) for most generators
        gen_data = []
        for gidx in net.gen.index:
            rated = float(net.gen.at[gidx, 'max_p_mw'])
            bus   = int(net.gen.at[gidx, 'bus'])
            gen_data.append((gidx, bus, rated))

        # Sort descending by rated capacity
        gen_data.sort(key=lambda x: x[2], reverse=True)

        # How many generators to replace?
        if self.cfg.ibr_penetration == 0.0:
            n_replace = 0
        elif self.cfg.ibr_penetration >= 1.0:
            n_replace = len(gen_data)
        else:
            total_cap = sum(g[2] for g in gen_data)
            cumulative = 0.0
            n_replace = 0
            for _, _, rated in gen_data:
                cumulative += rated
                n_replace  += 1
                if cumulative >= self.cfg.ibr_penetration * total_cap:
                    break

        # Apply IBR overlay
        for i, (gidx, bus, rated) in enumerate(gen_data[:n_replace]):
            if self.cfg.ibr_mode == 'gfl':
                k_ibr = 1.0; f_gfm = 0.0; I_max = 1.2
            elif self.cfg.ibr_mode == 'gfm':
                k_ibr = 1.0; f_gfm = 1.0; I_max = 1.5
            else:  # mixed — alternate
                if i % 2 == 0:
                    k_ibr = 1.0; f_gfm = 0.0; I_max = 1.2   # GFL
                else:
                    k_ibr = 1.0; f_gfm = 1.0; I_max = 1.5   # GFM

            self._ibr_bus_map[bus] = {
                'k_ibr': k_ibr,
                'f_gfm': f_gfm,
                'I_max': I_max,
                'rated_mw': rated,
            }

    # ------------------------------------------------------------------
    def inject_fault(self, bus_idx: int, fault_type: str,
                     R_f_ohm: float = 0.0,
                     scenario_id: int = 0) -> FaultState118:
        """
        Inject a fault at bus_idx and return a FaultState118.

        Uses Thevenin-based analytical fault calculation (avoids pandapower
        shortcircuit instability on buses without grounding).
        """
        net = self._net
        n_buses = len(net.bus)

        if bus_idx < 0 or bus_idx >= n_buses:
            raise ValueError(f"bus_idx {bus_idx} out of range [0, {n_buses-1}]")

        # ── Pre-fault voltage (use cached value or nominal 1.0 pu) ───
        # Avoid calling runpp per fault to keep MC fast (<2 min for 500 scenarios).
        # The 118-bus is well-regulated; V_pre ≈ 1.0 pu at all buses.
        if bus_idx in self._v_pre_cache:
            V_pre = self._v_pre_cache[bus_idx]
        else:
            V_pre = 1.0  # nominal pre-fault voltage

        vn_kv   = float(net.bus.at[bus_idx, 'vn_kv'])
        z_base  = (vn_kv ** 2) / self.cfg.base_mva   # Ω

        # ── Estimate Thevenin impedance from connected lines ──────────
        if bus_idx in self._z_th_cache:
            z_th_pu = self._z_th_cache[bus_idx]
        else:
            z_th_pu = self._thevenin_impedance(bus_idx)
            self._z_th_cache[bus_idx] = z_th_pu

        # Fault impedance in pu
        R_f_pu  = (R_f_ohm / z_base) if z_base > 0 else 0.0
        z_total = z_th_pu + complex(R_f_pu, 0.0)

        # Fault current magnitude [pu]
        if abs(z_total) > 1e-9:
            I_fault_pu = V_pre / abs(z_total)
        else:
            I_fault_pu = 10.0  # bolted fault

        # ── Symmetrical component breakdown ───────────────────────────
        if fault_type == '3PH':
            I_pos = I_fault_pu
            I_neg = 0.0
            V_pos = max(0.0, V_pre - I_pos * abs(z_total))
        elif fault_type == 'SLG':
            I_pos = I_fault_pu * 0.577
            I_neg = I_pos * 0.40
            V_pos = max(0.0, V_pre * 0.45)
        elif fault_type == 'DLG':
            I_pos = I_fault_pu * 0.816
            I_neg = I_pos * 0.55
            V_pos = max(0.0, V_pre * 0.35)
        elif fault_type == 'LL':
            I_pos = I_fault_pu * 0.707
            I_neg = I_pos * 0.45
            V_pos = max(0.0, V_pre * 0.55)
        else:
            raise ValueError(f"Unknown fault_type '{fault_type}'")

        # ── IBR parameters at fault bus ───────────────────────────────
        k_ibr, f_gfm = self._ibr_at_bus(bus_idx)

        # IBR current limiting: cap I_pos AND scale I_neg proportionally.
        # Critical: I_neg must be capped consistently with I_pos to avoid
        # artificially large I_neg/I_pos ratios in the differential relay.
        # (TR-86 finding — the original uncapped I_neg caused false RESTRAINs.)
        I_max = 1.5 if f_gfm > 0.5 else 1.2
        if k_ibr > 0:
            I_cap = I_max * (1.0 + 0.5 * (1.0 - k_ibr))
            if I_pos > I_cap:
                scale = I_cap / I_pos   # proportional scale factor
                I_pos = I_cap
                I_neg = I_neg * scale   # maintain I_neg/I_pos ratio

        # ── Protection zone assignment ────────────────────────────────
        z_app = V_pos / max(I_pos, 1e-6)
        z_line_pu = abs(z_th_pu)
        if z_app < 0.85 * z_line_pu:
            zone = 'zone1'
        elif z_app < 1.20 * z_line_pu:
            zone = 'zone2'
        else:
            zone = 'none'

        self._active_fault = {
            'bus_idx': bus_idx,
            'fault_type': fault_type,
            'R_f_ohm': R_f_ohm,
        }

        return FaultState118(
            scenario_id=scenario_id,
            bus_idx=bus_idx,
            fault_type=fault_type,
            R_f_ohm=R_f_ohm,
            I_pos_pu=round(I_pos, 4),
            I_neg_pu=round(I_neg, 4),
            V_pos_pu=round(V_pos, 4),
            k_ibr=round(k_ibr, 3),
            f_gfm=round(f_gfm, 3),
            protection_zone=zone,
            z_line_pu=round(z_line_pu, 5),
        )

    # ------------------------------------------------------------------
    def clear_fault(self) -> None:
        self._active_fault = None

    # ------------------------------------------------------------------
    def get_ibr_info(self) -> Dict[int, dict]:
        """Return IBR parameters keyed by bus index."""
        return dict(self._ibr_bus_map)

    # ------------------------------------------------------------------
    def _thevenin_impedance(self, bus_idx: int) -> complex:
        """
        Estimate Thevenin impedance at bus_idx from connected line parameters.
        Returns complex impedance in pu.
        """
        net = self._net
        z_base = (float(net.bus.at[bus_idx, 'vn_kv']) ** 2) / self.cfg.base_mva
        if z_base <= 0:
            return complex(0.05, 0.15)

        # Lines connected to this bus
        connected_lines = net.line[
            (net.line.from_bus == bus_idx) | (net.line.to_bus == bus_idx)
        ]

        z_values = []
        for lidx in connected_lines.index:
            r_ohm = (float(net.line.at[lidx, 'r_ohm_per_km']) *
                     float(net.line.at[lidx, 'length_km']))
            x_ohm = (float(net.line.at[lidx, 'x_ohm_per_km']) *
                     float(net.line.at[lidx, 'length_km']))
            z_values.append(complex(r_ohm / z_base, x_ohm / z_base))

        if not z_values:
            return complex(0.05, 0.15)

        # Use minimum impedance (worst-case fault level)
        return min(z_values, key=abs)

    # ------------------------------------------------------------------
    def _ibr_at_bus(self, bus_idx: int) -> Tuple[float, float]:
        """
        Return (k_ibr, f_gfm) for the given bus.
        If no IBR at that bus, look at nearest IBR-connected bus.
        """
        if bus_idx in self._ibr_bus_map:
            info = self._ibr_bus_map[bus_idx]
            return info['k_ibr'], info['f_gfm']

        if not self._ibr_bus_map:
            return 0.0, 0.0

        # Aggregate — use network-wide IBR fraction
        total_rated = sum(v['rated_mw'] for v in self._ibr_bus_map.values())
        all_rated   = (
            sum(float(self._net.gen.at[g, 'max_p_mw'])
                for g in self._net.gen.index)
            + 1e-9
        )
        k_ibr = min(1.0, total_rated / all_rated)

        gfm_rated = sum(v['rated_mw'] for v in self._ibr_bus_map.values()
                        if v['f_gfm'] > 0.5)
        f_gfm = gfm_rated / max(total_rated, 1e-9) if total_rated > 0 else 0.0

        return round(k_ibr, 3), round(f_gfm, 3)

    # ------------------------------------------------------------------
    @property
    def n_buses(self) -> int:
        return len(self._net.bus)

    @property
    def n_ibr_buses(self) -> int:
        return len(self._ibr_bus_map)
