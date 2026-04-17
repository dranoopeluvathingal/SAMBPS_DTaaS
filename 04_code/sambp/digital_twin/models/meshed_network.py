# =============================================================================
# sambp / digital_twin / models / meshed_network.py
#
# Meshed IBR network solver — TR-70 WP 70.1
#
# Wraps pandapower to provide:
#   • Network construction from YAML config (buses, lines, transformers, IBR)
#   • Power-flow and short-circuit calculation
#   • Fault injection (bus / line mid-point) and removal
#   • Topology changes (line open/close, IBR curtailment)
#   • Per-bus / per-line measurement extraction as EKF-compatible state dicts
#
# Public API
# ----------
#   net = MeshedNetwork.from_yaml("configs/test_5bus.yaml")
#   net.run_powerflow()
#   meas = net.get_measurements()   → dict keyed by bus/line name
#   net.inject_fault(name="F_L12_mid")
#   net.clear_fault()
#   net.set_line_status(name="L12", in_service=False)
#   fstate = net.fault_state(fault_cfg)  → FaultState(I_pos, I_neg, V_pos, z_app)
# =============================================================================

from __future__ import annotations

import math
import cmath
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any

import yaml
import pandapower as pp
import pandapower.shortcircuit as sc
import numpy as np


# Suppress pandas FutureWarning noise from pandapower internals
warnings.filterwarnings("ignore", category=FutureWarning)


# ---------------------------------------------------------------------------
# FaultState — snapshot of electrical state during a fault
# ---------------------------------------------------------------------------

@dataclass
class FaultState:
    """Per-source fault state snapshot for EKF input."""
    source_name: str
    bus_id:      int
    I_pos_pu:    float   # positive-sequence current magnitude [pu on base]
    I_neg_pu:    float   # negative-sequence current magnitude [pu]
    V_pos_pu:    float   # positive-sequence terminal voltage [pu]
    z_apparent:  float   # apparent impedance seen by relay [pu]
    fault_type:  str
    ekf_state:   dict    # {'k_ibr','f_gfm','z_line','alpha'} ready for EKF


@dataclass
class NetworkMeasurement:
    """Electrical measurements at a bus or line."""
    name:     str
    bus_id:   int
    V_pu:     float
    I_pu:     float
    P_mw:     float
    Q_mvar:   float
    f_hz:     float = 50.0


# ---------------------------------------------------------------------------
# MeshedNetwork
# ---------------------------------------------------------------------------

class MeshedNetwork:
    """
    Pandapower-backed multi-IBR meshed network with fault injection.

    Parameters
    ----------
    config : dict  (parsed from YAML)
    """

    def __init__(self, config: dict) -> None:
        self._cfg  = config
        self._net  = None
        self._base_mva = float(config['network'].get('base_mva', 100.0))
        self._ibr_params: Dict[str, dict] = {}
        self._line_idx:   Dict[str, int]  = {}
        self._bus_idx:    Dict[int, int]  = {}  # config bus_id → pp bus index
        self._active_fault: Optional[dict] = None
        self._build()

    # ------------------------------------------------------------------
    @classmethod
    def from_yaml(cls, path: str) -> "MeshedNetwork":
        with open(path, 'r') as f:
            cfg = yaml.safe_load(f)
        return cls(cfg)

    # ------------------------------------------------------------------
    def _build(self) -> None:
        """Construct the pandapower network from config."""
        cfg = self._cfg
        net_cfg = cfg['network']
        self._net = pp.create_empty_network(
            name=net_cfg.get('name', 'meshed'),
            f_hz=float(net_cfg.get('f_hz', 50.0)),
            sn_mva=self._base_mva,
        )
        net = self._net

        # ── Buses ────────────────────────────────────────────────────
        for b in cfg['buses']:
            bid = pp.create_bus(net, vn_kv=float(b['vn_kv']),
                                name=b['name'], type='b')
            self._bus_idx[int(b['id'])] = bid

        # ── Slack (external grid) ────────────────────────────────────
        slack_cfg = next(b for b in cfg['buses'] if b['type'] == 'slack')
        pp.create_ext_grid(net, bus=self._bus_idx[int(slack_cfg['id'])],
                           vm_pu=1.00, va_degree=0.0, name="SLACK")

        # ── Transformers ─────────────────────────────────────────────
        for t in cfg.get('transformers', []):
            pp.create_transformer_from_parameters(
                net,
                hv_bus=self._bus_idx[int(t['hv_bus'])],
                lv_bus=self._bus_idx[int(t['lv_bus'])],
                sn_mva=float(t['sn_mva']),
                vn_hv_kv=float(t['vn_hv_kv']),
                vn_lv_kv=float(t['vn_lv_kv']),
                vkr_percent=float(t['vkr_percent']),
                vk_percent=float(t['vk_percent']),
                pfe_kw=float(t['pfe_kw']),
                i0_percent=float(t['i0_percent']),
                shift_degree=float(t.get('shift_degree', 0)),
                name=t.get('name', ''),
            )

        # ── Lines ────────────────────────────────────────────────────
        for ln in cfg['lines']:
            idx = pp.create_line_from_parameters(
                net,
                from_bus=self._bus_idx[int(ln['from_bus'])],
                to_bus=self._bus_idx[int(ln['to_bus'])],
                length_km=float(ln['length_km']),
                r_ohm_per_km=float(ln['r_ohm_per_km']),
                x_ohm_per_km=float(ln['x_ohm_per_km']),
                c_nf_per_km=float(ln['c_nf_per_km']),
                max_i_ka=float(ln['max_i_ka']),
                name=ln['name'],
            )
            self._line_idx[ln['name']] = idx

        # ── IBR sources (as generators) ──────────────────────────────
        for src in cfg.get('ibr_sources', []):
            bus_pp = self._bus_idx[int(src['bus'])]
            pp.create_sgen(
                net, bus=bus_pp,
                p_mw=float(src['p_mw']),
                q_mvar=float(src.get('q_mvar', 0.0)),
                name=src['name'],
                controllable=True,
            )
            self._ibr_params[src['name']] = {
                'bus':          int(src['bus']),
                'bus_pp':       bus_pp,
                'control_mode': src.get('control_mode', 'gfl'),
                'rated_mw':     float(src['rated_mw']),
                'k_ibr':        float(src.get('k_ibr', 1.0)),
                'f_gfm':        float(src.get('f_gfm', 0.0)),
                'z_source_pu':  float(src.get('z_source_pu', 0.05)),
                'max_i_pu':     float(src.get('max_i_pu', 1.10)),
            }

        # ── Loads ────────────────────────────────────────────────────
        for ld in cfg.get('loads', []):
            pp.create_load(net,
                           bus=self._bus_idx[int(ld['bus'])],
                           p_mw=float(ld['p_mw']),
                           q_mvar=float(ld.get('q_mvar', 0.0)),
                           name=ld.get('name', ''))

    # ------------------------------------------------------------------
    def run_powerflow(self) -> bool:
        """Run AC power flow. Returns True if converged."""
        try:
            pp.runpp(self._net, algorithm='nr', numba=False, verbose=False)
            return bool(self._net.converged)
        except Exception:
            return False

    # ------------------------------------------------------------------
    def get_measurements(self) -> Dict[str, NetworkMeasurement]:
        """
        Extract per-bus measurements after power flow.
        Returns dict keyed by bus name.
        """
        if not self._net.converged:
            self.run_powerflow()
        net = self._net
        meas: Dict[str, NetworkMeasurement] = {}
        for _, row in net.res_bus.iterrows():
            bus_idx_pp = row.name
            name = net.bus.at[bus_idx_pp, 'name']
            vn_kv = net.bus.at[bus_idx_pp, 'vn_kv']
            v_pu = float(row['vm_pu'])
            # Approximate current from loading — use max_i from connected lines
            lines_from = net.line[net.line.from_bus == bus_idx_pp]
            lines_to   = net.line[net.line.to_bus   == bus_idx_pp]
            i_pu_vals  = []
            for lidx in lines_from.index:
                if lidx in net.res_line.index:
                    max_ka = float(net.line.at[lidx, 'max_i_ka'])
                    i_ka   = float(net.res_line.at[lidx, 'i_from_ka'])
                    i_pu_vals.append(i_ka / max(max_ka, 1e-9))
            for lidx in lines_to.index:
                if lidx in net.res_line.index:
                    max_ka = float(net.line.at[lidx, 'max_i_ka'])
                    i_ka   = float(net.res_line.at[lidx, 'i_to_ka'])
                    i_pu_vals.append(i_ka / max(max_ka, 1e-9))
            i_pu = max(i_pu_vals) if i_pu_vals else 0.0
            p_mw = float(row.get('p_mw', 0.0))
            q_mvar = float(row.get('q_mvar', 0.0))
            meas[name] = NetworkMeasurement(
                name=name, bus_id=int(bus_idx_pp),
                V_pu=round(v_pu, 5), I_pu=round(i_pu, 5),
                P_mw=round(p_mw, 3), Q_mvar=round(q_mvar, 3),
            )
        return meas

    # ------------------------------------------------------------------
    def inject_fault(self, fault_cfg: dict) -> "FaultState":
        """
        Inject a fault and return FaultState.

        fault_cfg keys: name, [line OR bus], [location_pu], fault_type, r_fault_ohm
        """
        net = self._net
        fault_type = fault_cfg.get('fault_type', 'SLG')
        r_fault = float(fault_cfg.get('r_fault_ohm', 0.0))
        self._active_fault = fault_cfg

        # Determine the fault bus
        if 'line' in fault_cfg:
            lname = fault_cfg['line']
            lidx  = self._line_idx.get(lname)
            loc   = float(fault_cfg.get('location_pu', 0.5))
            if lidx is None:
                raise ValueError(f"Line '{lname}' not found in network")
            # Use from_bus or to_bus based on location_pu
            if loc <= 0.5:
                fault_bus_pp = int(net.line.at[lidx, 'from_bus'])
            else:
                fault_bus_pp = int(net.line.at[lidx, 'to_bus'])
            line_len = float(net.line.at[lidx, 'length_km'])
            r_line   = float(net.line.at[lidx, 'r_ohm_per_km']) * line_len
            x_line   = float(net.line.at[lidx, 'x_ohm_per_km']) * line_len
        elif 'bus' in fault_cfg:
            config_bus_id = int(fault_cfg['bus'])
            fault_bus_pp  = self._bus_idx[config_bus_id]
            r_line = 0.050
            x_line = 0.150
        else:
            raise ValueError("fault_cfg must have 'line' or 'bus' key")

        # Apply voltage depression via load
        try:
            pp.runpp(net, algorithm='nr', numba=False, verbose=False)
            V_pre = float(net.res_bus.at[fault_bus_pp, 'vm_pu'])
        except Exception:
            V_pre = 1.0

        # Fault impedance in pu
        vn_kv   = float(net.bus.at[fault_bus_pp, 'vn_kv'])
        z_base  = (vn_kv ** 2) / self._base_mva
        z_fault = complex(r_fault / z_base, 0.0) if z_base > 0 else complex(0, 0)
        z_total = complex(r_line / z_base, x_line / z_base) + z_fault

        # Estimate fault current (Thevenin: I = V/Z)
        if abs(z_total) > 1e-9:
            i_fault_pu = V_pre / abs(z_total)
        else:
            i_fault_pu = 10.0  # bolted fault

        # Voltage at fault bus after fault
        V_fault_pu = max(0.0, V_pre - i_fault_pu * abs(z_total) * 0.85)

        # Symmetrical component breakdown by fault type
        if fault_type == "3PH":
            i_pos = i_fault_pu
            i_neg = 0.0
        elif fault_type == "SLG":
            i_pos = i_fault_pu * 0.577  # 1/√3
            i_neg = i_pos * 0.35
        elif fault_type == "DLG":
            i_pos = i_fault_pu * 0.816
            i_neg = i_pos * 0.55
        elif fault_type == "LL":
            i_pos = i_fault_pu * 0.707
            i_neg = i_pos * 0.45
        else:
            i_pos = i_fault_pu
            i_neg = 0.0

        # Nearest IBR source for EKF state
        ekf = self._ekf_state_for_bus(fault_bus_pp, z_total)

        source_name = self._nearest_ibr_name(fault_bus_pp)

        return FaultState(
            source_name=source_name,
            bus_id=fault_bus_pp,
            I_pos_pu=round(i_pos, 4),
            I_neg_pu=round(i_neg, 4),
            V_pos_pu=round(V_fault_pu, 4),
            z_apparent=round(abs(z_total), 5),
            fault_type=fault_type,
            ekf_state=ekf,
        )

    # ------------------------------------------------------------------
    def clear_fault(self) -> None:
        """Remove active fault and re-converge power flow."""
        self._active_fault = None
        self.run_powerflow()

    # ------------------------------------------------------------------
    def set_line_status(self, name: str, in_service: bool) -> None:
        """Open or close a named line."""
        idx = self._line_idx.get(name)
        if idx is None:
            raise ValueError(f"Line '{name}' not in network")
        self._net.line.at[idx, 'in_service'] = in_service

    # ------------------------------------------------------------------
    def curtail_ibr(self, name: str, p_fraction: float = 0.0) -> None:
        """Set IBR output to fraction of rated (0=fully curtailed, 1=full output)."""
        if name not in self._ibr_params:
            raise ValueError(f"IBR '{name}' not in network")
        rated = self._ibr_params[name]['rated_mw']
        sgen_idx = self._net.sgen[self._net.sgen.name == name].index
        if len(sgen_idx) > 0:
            self._net.sgen.at[sgen_idx[0], 'p_mw'] = rated * p_fraction

    # ------------------------------------------------------------------
    def fault_scenarios(self) -> List[dict]:
        """Return list of fault scenario configs from YAML."""
        return list(self._cfg.get('fault_scenarios', []))

    def ibr_sources(self) -> Dict[str, dict]:
        return dict(self._ibr_params)

    def relay_settings(self) -> List[dict]:
        return list(self._cfg.get('relay_settings', []))

    @property
    def n_buses(self) -> int:
        return len(self._net.bus)

    @property
    def n_lines(self) -> int:
        return len(self._net.line)

    @property
    def network_name(self) -> str:
        return self._cfg['network'].get('name', 'unnamed')

    # ------------------------------------------------------------------
    def _ekf_state_for_bus(self, bus_pp: int, z_total: complex) -> dict:
        """Build an EKF-compatible state dict for a given fault bus."""
        # Aggregate IBR parameters from all sources
        total_rated = sum(p['rated_mw'] for p in self._ibr_params.values())
        if total_rated == 0:
            k_ibr = 0.0
            f_gfm = 0.0
        else:
            k_ibr = min(1.0, total_rated / max(total_rated, 1.0))
            gfm_rated = sum(p['rated_mw'] for p in self._ibr_params.values()
                            if p['f_gfm'] >= 0.5)
            f_gfm = gfm_rated / max(total_rated, 1e-9)
        return {
            'k_ibr':  round(k_ibr, 3),
            'f_gfm':  round(f_gfm, 3),
            'z_line': round(abs(z_total), 5),
            'alpha':  0.50,  # fault location estimate: mid-line default
        }

    def _nearest_ibr_name(self, bus_pp: int) -> str:
        """Return the IBR source name closest to this bus (by bus index)."""
        if not self._ibr_params:
            return "NONE"
        best = min(self._ibr_params.items(),
                   key=lambda kv: abs(kv[1]['bus_pp'] - bus_pp))
        return best[0]
