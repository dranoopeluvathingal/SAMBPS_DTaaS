# =============================================================================
# sambp / digital_twin / models / ssci_scenario_lib.py
#
# SSCI / SSRO scenario library — TR-75 WP 75.3
#
# 40 scenarios across 4 groups:
#   Group A (1–10) : Type-4 GFL wind, low compensation (≤20%) — NO SSCI
#   Group B (11–20): Type-4 GFL wind, medium compensation (25–50%) — SSCI RISK
#   Group C (21–30): Type-4 GFL wind, high compensation (55–80%) — SSCI ACTIVE
#   Group D (31–40): Type-4 GFM wind, any compensation — NO SSCI (GFM immune)
#
# Each scenario specifies:
#   • Line parameters (R, XL, compensation%)
#   • Converter parameters (mode, k_p, k_i, bandwidth)
#   • Expected outcomes: ssci_risk, resonance_f_hz range, risk_level
#   • A synthetic waveform generator for SSCIDetector testing
# =============================================================================

from __future__ import annotations

import math
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from models.impedance_scan import SeriesCompLineParams, ConverterParams


# ---------------------------------------------------------------------------
# SSCIScenario
# ---------------------------------------------------------------------------

@dataclass
class SSCIScenario:
    id:              int
    name:            str
    group:           str          # "GFL_LOW" | "GFL_MED" | "GFL_HIGH" | "GFM"
    line_params:     SeriesCompLineParams
    conv_params:     ConverterParams
    # Expected detection outcomes
    expected_ssci:   bool         # True if SSCI expected
    expected_risk:   str          # "NONE" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
    res_f_lo:        float        # expected resonance frequency lower bound [Hz]
    res_f_hi:        float        # expected resonance frequency upper bound [Hz]
    description:     str = ""
    # Waveform simulation params
    grow_time_s:     float = 0.05  # time for alarm to trigger [s] if SSCI active
    i_ss_amplitude:  float = 0.00  # sub-synchronous current amplitude [pu]
    f_ss_hz:         float = 20.0  # sub-synchronous frequency [Hz]

    def generate_waveform(self,
                          fs: float = 1000.0,
                          f0: float = 50.0,
                          duration_s: float = 0.20,
                          growth_rate: float = 5.0) -> np.ndarray:
        """
        Generate a synthetic three-phase current waveform for this scenario.

        Returns array of shape (N_samples, 7):
          columns: [t, ia, ib, ic, va, vb, vc]
        """
        N  = int(duration_s * fs)
        ts = np.arange(N) / fs
        omega0  = 2 * math.pi * f0
        omega_ss = 2 * math.pi * self.f_ss_hz

        # Fundamental (positive-sequence, 1 pu)
        ia_fund = np.cos(omega0 * ts)
        ib_fund = np.cos(omega0 * ts - 2*math.pi/3)
        ic_fund = np.cos(omega0 * ts + 2*math.pi/3)

        # Sub-synchronous component (grows if SSCI active)
        if self.expected_ssci:
            env = self.i_ss_amplitude * np.exp(growth_rate * ts)
            env = np.minimum(env, 3.0 * self.i_ss_amplitude)  # cap
        else:
            env = np.zeros(N)

        ia_ss = env * np.cos(omega_ss * ts)
        ib_ss = env * np.cos(omega_ss * ts - 2*math.pi/3)
        ic_ss = env * np.cos(omega_ss * ts + 2*math.pi/3)

        ia = ia_fund + ia_ss
        ib = ib_fund + ib_ss
        ic = ic_fund + ic_ss

        # Voltage: fundamental + small SS dip
        va = np.cos(omega0 * ts) * (1.0 - 0.05 * env / max(self.i_ss_amplitude, 1e-9))
        vb = np.cos(omega0 * ts - 2*math.pi/3) * (1.0 - 0.05 * env / max(self.i_ss_amplitude, 1e-9))
        vc = np.cos(omega0 * ts + 2*math.pi/3) * (1.0 - 0.05 * env / max(self.i_ss_amplitude, 1e-9))

        return np.column_stack([ts, ia, ib, ic, va, vb, vc])


# ---------------------------------------------------------------------------
# Scenario factory
# ---------------------------------------------------------------------------

def build_scenarios() -> List[SSCIScenario]:
    scens: List[SSCIScenario] = []

    # k_p and k_i calibrated to this simplified GFL impedance model (100 MVA base):
    #   Re[Z_conv(f)] < 0 when f_res > f_cross = sqrt(k_i / L_f) / (2π)
    #
    # Group A uses k_i=3000 → f_cross=30.8 Hz; comp ≤20% → f_res ≤22.4 Hz < f_cross → no SSCI
    # Groups B/C use k_i=3600 → f_cross=33.8 Hz:
    #   comp ≤45% → f_res ≤33.5 Hz < f_cross → no SSCI
    #   comp ≥50% → f_res ≥35.4 Hz > f_cross → SSCI

    # ── Group A: GFL, low compensation (0–20%) — NO SSCI ────────────────────
    group_a_params = [
        # (id, comp_pct, xl, desc)
        ( 1,  0.0, 0.12, "GFL 0% comp, no compensation"),
        ( 2,  5.0, 0.12, "GFL 5% comp, minimal"),
        ( 3, 10.0, 0.14, "GFL 10% comp, low"),
        ( 4, 12.0, 0.14, "GFL 12% comp, low"),
        ( 5, 15.0, 0.16, "GFL 15% comp, low-medium"),
        ( 6, 15.0, 0.12, "GFL 15% comp, alternate line"),
        ( 7, 18.0, 0.14, "GFL 18% comp"),
        ( 8, 20.0, 0.15, "GFL 20% comp, marginal low"),
        ( 9, 20.0, 0.10, "GFL 20% comp, short line"),
        (10, 20.0, 0.18, "GFL 20% comp, long line"),
    ]
    for sid, comp, xl, desc in group_a_params:
        lp = SeriesCompLineParams.from_compensation_pct(xl, comp)
        cp = ConverterParams(L_f_pu=0.08, k_p=3.0, k_i=3000.0, R_f_pu=0.005,
                             control_mode="gfl", bandwidth_hz=60.0)
        res_f = 50.0 * math.sqrt(comp / 100.0) if comp > 0 else 0.0
        scens.append(SSCIScenario(
            id=sid, name=f"A{sid:02d}_gfl_{int(comp)}pct",
            group="GFL_LOW", line_params=lp, conv_params=cp,
            expected_ssci=False, expected_risk="NONE",
            res_f_lo=0.0, res_f_hi=50.0,
            description=desc,
            i_ss_amplitude=0.005, f_ss_hz=max(res_f, 5.0),
        ))

    # ── Group B: GFL, medium compensation (25–50%) — SSCI RISK ──────────────
    # k_i=3800 → f_cross=34.8 Hz: comp ≤45% no SSCI, comp=50% triggers SSCI.
    group_b_params = [
        (11, 25.0, 0.14, "GFL 25% comp, SSCI risk begins"),
        (12, 30.0, 0.14, "GFL 30% comp, risk"),
        (13, 35.0, 0.15, "GFL 35% comp, moderate risk"),
        (14, 35.0, 0.15, "GFL 35% comp, alternate line"),
        (15, 40.0, 0.16, "GFL 40% comp, significant risk"),
        (16, 40.0, 0.16, "GFL 40% comp, alternate line"),
        (17, 45.0, 0.15, "GFL 45% comp, high risk"),
        (18, 45.0, 0.18, "GFL 45% comp, heavy line"),
        (19, 50.0, 0.14, "GFL 50% comp, borderline active"),
        (20, 50.0, 0.14, "GFL 50% comp, alternate — active SSCI"),
    ]
    for sid, comp, xl, desc in group_b_params:
        lp = SeriesCompLineParams.from_compensation_pct(xl, comp)
        cp = ConverterParams(L_f_pu=0.08, k_p=3.5, k_i=3600.0, R_f_pu=0.005,
                             control_mode="gfl", bandwidth_hz=60.0)
        res_f = 50.0 * math.sqrt(comp / 100.0)
        i_ss  = 0.04 + 0.002 * (comp - 25)
        scens.append(SSCIScenario(
            id=sid, name=f"B{sid:02d}_gfl_{int(comp)}pct",
            group="GFL_MED", line_params=lp, conv_params=cp,
            expected_ssci=(sid >= 19),   # only 19,20 expected to alarm (50% comp)
            expected_risk="LOW" if sid < 17 else ("MEDIUM" if sid < 20 else "HIGH"),
            res_f_lo=max(5.0, res_f - 5.0),
            res_f_hi=min(45.0, res_f + 5.0),
            description=desc,
            i_ss_amplitude=i_ss, f_ss_hz=min(45.0, max(5.0, res_f)),
            grow_time_s=0.08,
        ))

    # ── Group C: GFL, high compensation (55–80%) — SSCI ACTIVE ──────────────
    # All f_res ≥ 37.1 Hz > f_cross=34.8 Hz → active SSCI for all scenarios.
    group_c_params = [
        (21, 55.0, 0.14, "GFL 55% comp, SSCI active"),
        (22, 58.0, 0.15, "GFL 58% comp, SSCI active"),
        (23, 60.0, 0.14, "GFL 60% comp, strong SSCI"),
        (24, 60.0, 0.16, "GFL 60% comp, alternate line"),
        (25, 65.0, 0.15, "GFL 65% comp, strong SSCI"),
        (26, 65.0, 0.15, "GFL 65% comp, alternate line"),
        (27, 70.0, 0.14, "GFL 70% comp, severe SSCI"),
        (28, 75.0, 0.16, "GFL 75% comp, severe SSCI"),
        (29, 78.0, 0.15, "GFL 78% comp, critical"),
        (30, 80.0, 0.14, "GFL 80% comp, critical SSCI"),
    ]
    for sid, comp, xl, desc in group_c_params:
        lp = SeriesCompLineParams.from_compensation_pct(xl, comp)
        cp = ConverterParams(L_f_pu=0.08, k_p=3.5, k_i=3600.0, R_f_pu=0.005,
                             control_mode="gfl", bandwidth_hz=60.0)
        res_f = 50.0 * math.sqrt(comp / 100.0)
        i_ss  = 0.06 + 0.003 * (comp - 55)
        risk  = "HIGH" if comp < 70 else "CRITICAL"
        scens.append(SSCIScenario(
            id=sid, name=f"C{sid:02d}_gfl_{int(comp)}pct",
            group="GFL_HIGH", line_params=lp, conv_params=cp,
            expected_ssci=True, expected_risk=risk,
            res_f_lo=max(5.0, res_f - 5.0),
            res_f_hi=min(45.0, res_f + 5.0),
            description=desc,
            i_ss_amplitude=i_ss, f_ss_hz=min(45.0, max(5.0, res_f)),
            grow_time_s=0.06,
        ))

    # ── Group D: GFM, any compensation — NO SSCI (GFM immune) ───────────────
    group_d_params = [
        (31,  0.0, 0.12, "GFM 0% comp"),
        (32, 20.0, 0.14, "GFM 20% comp"),
        (33, 35.0, 0.15, "GFM 35% comp"),
        (34, 40.0, 0.16, "GFM 40% comp"),
        (35, 50.0, 0.14, "GFM 50% comp"),
        (36, 55.0, 0.15, "GFM 55% comp"),
        (37, 60.0, 0.14, "GFM 60% comp"),
        (38, 65.0, 0.15, "GFM 65% comp"),
        (39, 70.0, 0.16, "GFM 70% comp"),
        (40, 80.0, 0.14, "GFM 80% comp — should not SSCI"),
    ]
    for sid, comp, xl, desc in group_d_params:
        lp = SeriesCompLineParams.from_compensation_pct(xl, comp)
        cp = ConverterParams(L_f_pu=0.08, k_p=3.0, k_i=3000.0, R_f_pu=0.005,
                             control_mode="gfm", bandwidth_hz=60.0)
        scens.append(SSCIScenario(
            id=sid, name=f"D{sid:02d}_gfm_{int(comp)}pct",
            group="GFM", line_params=lp, conv_params=cp,
            expected_ssci=False, expected_risk="NONE",
            res_f_lo=0.0, res_f_hi=50.0,
            description=desc,
            i_ss_amplitude=0.003, f_ss_hz=20.0,
        ))

    return scens


class SSCIScenarioLibrary:
    """Container for the 40 SSCI scenarios."""

    def __init__(self) -> None:
        self._scenarios = build_scenarios()

    def __len__(self) -> int:
        return len(self._scenarios)

    def __iter__(self):
        return iter(self._scenarios)

    def __getitem__(self, idx: int) -> SSCIScenario:
        return self._scenarios[idx]

    def get_by_group(self, group: str) -> List[SSCIScenario]:
        return [s for s in self._scenarios if s.group == group]

    def get_by_id(self, scenario_id: int) -> SSCIScenario:
        for s in self._scenarios:
            if s.id == scenario_id:
                return s
        raise KeyError(scenario_id)
