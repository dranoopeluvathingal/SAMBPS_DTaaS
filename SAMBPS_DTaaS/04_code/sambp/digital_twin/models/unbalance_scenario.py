# =============================================================================
# sambp / digital_twin / models / unbalance_scenario.py
#
# Unbalanced fault and IBR distortion scenarios — TR-73 WP 73.2
#
# Provides 50 parameterised scenarios that span the full operating space
# of the NegSeqSupervisor: real faults, IBR-induced unbalance, load
# unbalance, and ambiguous mixed cases.
#
# Public API
# ----------
#   lib = UnbalanceScenarioLibrary()
#   scenarios = lib.all()              → list[UnbalanceScenario]  (len=50)
#   s = lib.by_id(n)
#   waveforms = lib.generate_waveform(s, fs=1000, f0=50, n_cycles=4)
# =============================================================================

from __future__ import annotations

import math
import cmath
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------

@dataclass
class UnbalanceScenario:
    """
    Parameterised unbalanced scenario for negative-sequence supervision.

    Fields
    ------
    scenario_id    : unique integer (1-50)
    description    : human-readable label
    category       : "REAL_FAULT" | "IBR_DISTORTION" | "LOAD_UNBALANCE" | "AMBIGUOUS"
    fault_type     : "SLG" | "DLG" | "3PH" | "NONE"
    k_ibr          : IBR penetration fraction (0..1)
    v_pos_pu       : positive-sequence voltage magnitude [pu]
    v_neg_pu       : negative-sequence voltage magnitude [pu]  (V2)
    v_zero_pu      : zero-sequence voltage magnitude [pu]      (V0)
    i_pos_pu       : positive-sequence current magnitude [pu]  (I1)
    i_neg_pu       : negative-sequence current magnitude [pu]  (I2)
    i_zero_pu      : zero-sequence current magnitude [pu]      (I0)
    expected_action: "BLOCK" | "PERMIT" | "ALERT"
    """
    scenario_id:     int
    description:     str
    category:        str
    fault_type:      str
    k_ibr:           float
    v_pos_pu:        float
    v_neg_pu:        float
    v_zero_pu:       float
    i_pos_pu:        float
    i_neg_pu:        float
    i_zero_pu:       float
    expected_action: str

    @property
    def I2_I1_ratio(self) -> float:
        return self.i_neg_pu / max(self.i_pos_pu, 1e-6)

    @property
    def V2_V1_ratio(self) -> float:
        return self.v_neg_pu / max(self.v_pos_pu, 1e-6)


# ---------------------------------------------------------------------------
# Library
# ---------------------------------------------------------------------------

class UnbalanceScenarioLibrary:
    """
    Library of 50 negative-sequence supervision scenarios.

    Groups
    ------
    1–10  : Real SLG faults (variable k_ibr, fault resistance)
    11–20 : Real DLG faults
    21–30 : IBR negative-sequence distortion (no fault)
    31–38 : Load unbalance (single-phase loads, no fault)
    39–45 : Ambiguous: light SLG on high-IBR bus
    46–50 : Three-phase faults (balanced — should not trigger neg-seq alarm)
    """

    def all(self) -> List[UnbalanceScenario]:
        return self._build()

    def by_id(self, sid: int) -> UnbalanceScenario:
        for s in self._build():
            if s.scenario_id == sid:
                return s
        raise KeyError(sid)

    def generate_waveform(
        self,
        scenario: UnbalanceScenario,
        fs: float = 1000.0,
        f0: float = 50.0,
        n_cycles: int = 4,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Synthesise three-phase voltage and current waveforms from scenario
        sequence magnitudes.

        Returns
        -------
        v_abc : ndarray (N, 3) — phase voltages [pu]
        i_abc : ndarray (N, 3) — phase currents [pu]
        """
        N   = round(fs / f0 * n_cycles)
        t   = np.arange(N) / fs
        w   = 2.0 * math.pi * f0

        # Rotation operator a = exp(j120°)
        a   = cmath.rect(1.0,  2.0 * math.pi / 3.0)
        a2  = a * a

        def _phase_abc(mag_012: Tuple[float, float, float]) -> np.ndarray:
            """Convert sequence magnitudes to instantaneous three-phase."""
            m0, m1, m2 = mag_012
            # Phasors: X0 = m0∠0, X1 = m1∠0, X2 = m2∠0
            x0 = complex(m0, 0)
            x1 = complex(m1, 0)
            x2 = complex(m2, 0)
            # Inverse Fortescue (phase quantities)
            xa = x0 + x1 + x2
            xb = x0 + a2 * x1 + a  * x2
            xc = x0 + a  * x1 + a2 * x2
            # Instantaneous: Re[X * exp(jwt)]
            carrier = np.exp(1j * w * t)
            out = np.zeros((N, 3))
            out[:, 0] = np.real(xa * carrier)
            out[:, 1] = np.real(xb * carrier)
            out[:, 2] = np.real(xc * carrier)
            return out

        v_abc = _phase_abc((scenario.v_zero_pu, scenario.v_pos_pu, scenario.v_neg_pu))
        i_abc = _phase_abc((scenario.i_zero_pu, scenario.i_pos_pu, scenario.i_neg_pu))
        return v_abc, i_abc

    # ------------------------------------------------------------------
    @staticmethod
    def _build() -> List[UnbalanceScenario]:
        rows: List[UnbalanceScenario] = []

        # ── Group 1: SLG faults (scenarios 1–10) ─────────────────────
        # High V2 (voltage unbalance) confirms fault → PERMIT
        slg_params = [
            (1,  "SLG low-R, low-IBR",   0.10, 0.90, 0.12, 0.08, 0.30, 0.28, 0.28),
            (2,  "SLG low-R, med-IBR",   0.30, 0.88, 0.14, 0.10, 0.32, 0.32, 0.30),
            (3,  "SLG low-R, high-IBR",  0.60, 0.86, 0.16, 0.12, 0.35, 0.38, 0.36),
            (4,  "SLG high-R, low-IBR",  0.10, 0.92, 0.10, 0.07, 0.22, 0.20, 0.18),
            (5,  "SLG high-R, med-IBR",  0.35, 0.90, 0.13, 0.08, 0.24, 0.22, 0.20),
            (6,  "SLG high-R, high-IBR", 0.65, 0.88, 0.15, 0.10, 0.26, 0.25, 0.22),
            (7,  "SLG remote, low-IBR",  0.15, 0.94, 0.08, 0.05, 0.18, 0.15, 0.14),
            (8,  "SLG remote, high-IBR", 0.55, 0.92, 0.09, 0.06, 0.20, 0.17, 0.15),
            (9,  "SLG with load, low",   0.20, 0.89, 0.14, 0.09, 0.28, 0.30, 0.28),
            (10, "SLG heavy fault",      0.40, 0.82, 0.18, 0.15, 0.40, 0.44, 0.40),
        ]
        for sid, desc, k, vp, vn, vz, ip, i2, i0 in slg_params:
            rows.append(UnbalanceScenario(
                scenario_id=sid, description=desc, category="REAL_FAULT",
                fault_type="SLG", k_ibr=k,
                v_pos_pu=vp, v_neg_pu=vn, v_zero_pu=vz,
                i_pos_pu=ip, i_neg_pu=i2, i_zero_pu=i0,
                expected_action="PERMIT",
            ))

        # ── Group 2: DLG faults (scenarios 11–20) ────────────────────
        dlg_params = [
            (11, "DLG low-R, low-IBR",   0.10, 0.88, 0.15, 0.10, 0.38, 0.42, 0.30),
            (12, "DLG low-R, med-IBR",   0.35, 0.86, 0.17, 0.12, 0.40, 0.45, 0.32),
            (13, "DLG low-R, high-IBR",  0.65, 0.84, 0.19, 0.14, 0.42, 0.50, 0.36),
            (14, "DLG high-R, low-IBR",  0.15, 0.90, 0.12, 0.08, 0.30, 0.32, 0.22),
            (15, "DLG high-R, med-IBR",  0.40, 0.88, 0.14, 0.09, 0.32, 0.35, 0.24),
            (16, "DLG high-R, high-IBR", 0.70, 0.86, 0.16, 0.11, 0.34, 0.38, 0.26),
            (17, "DLG remote, low-IBR",  0.10, 0.92, 0.10, 0.06, 0.22, 0.22, 0.16),
            (18, "DLG remote, high-IBR", 0.60, 0.90, 0.12, 0.07, 0.24, 0.25, 0.18),
            (19, "DLG with load",        0.25, 0.87, 0.16, 0.11, 0.36, 0.40, 0.28),
            (20, "DLG heavy fault",      0.50, 0.80, 0.22, 0.18, 0.48, 0.58, 0.44),
        ]
        for sid, desc, k, vp, vn, vz, ip, i2, i0 in dlg_params:
            rows.append(UnbalanceScenario(
                scenario_id=sid, description=desc, category="REAL_FAULT",
                fault_type="DLG", k_ibr=k,
                v_pos_pu=vp, v_neg_pu=vn, v_zero_pu=vz,
                i_pos_pu=ip, i_neg_pu=i2, i_zero_pu=i0,
                expected_action="PERMIT",
            ))

        # ── Group 3: IBR distortion (scenarios 21–30) ────────────────
        # High I2 but LOW V2 (IBR injects negative sequence — voltage unaffected)
        ibr_params = [
            (21, "IBR distortion, k=0.30", 0.30, 1.00, 0.04, 0.01, 0.30, 0.04, 0.01),
            (22, "IBR distortion, k=0.40", 0.40, 1.00, 0.05, 0.01, 0.35, 0.06, 0.01),
            (23, "IBR distortion, k=0.50", 0.50, 1.00, 0.05, 0.01, 0.40, 0.07, 0.01),
            (24, "IBR distortion, k=0.60", 0.60, 1.00, 0.06, 0.02, 0.45, 0.09, 0.02),
            (25, "IBR distortion, k=0.70", 0.70, 1.00, 0.06, 0.02, 0.50, 0.10, 0.02),
            (26, "IBR distortion, k=0.80", 0.80, 1.00, 0.07, 0.02, 0.55, 0.12, 0.02),
            (27, "IBR distortion high I2", 0.65, 1.00, 0.07, 0.02, 0.48, 0.14, 0.02),
            (28, "IBR distortion, LV bus",  0.35, 0.98, 0.05, 0.01, 0.32, 0.05, 0.01),
            (29, "IBR distortion + load",   0.45, 0.99, 0.06, 0.02, 0.38, 0.08, 0.02),
            (30, "IBR distortion max",      0.90, 1.00, 0.07, 0.02, 0.60, 0.15, 0.02),
        ]
        for sid, desc, k, vp, vn, vz, ip, i2, i0 in ibr_params:
            rows.append(UnbalanceScenario(
                scenario_id=sid, description=desc, category="IBR_DISTORTION",
                fault_type="NONE", k_ibr=k,
                v_pos_pu=vp, v_neg_pu=vn, v_zero_pu=vz,
                i_pos_pu=ip, i_neg_pu=i2, i_zero_pu=i0,
                expected_action="BLOCK",
            ))

        # ── Group 4: Load unbalance (scenarios 31–38) ─────────────────
        # Moderate I2, low V2, no IBR dominance → ALERT
        load_params = [
            (31, "Single-phase load A",   0.10, 0.99, 0.04, 0.01, 0.25, 0.04, 0.01),
            (32, "Single-phase load B",   0.15, 0.99, 0.04, 0.01, 0.28, 0.05, 0.01),
            (33, "Large single-phase",    0.10, 0.97, 0.06, 0.02, 0.30, 0.07, 0.02),
            (34, "LV feeder unbalance",   0.05, 0.98, 0.05, 0.02, 0.22, 0.05, 0.02),
            (35, "MV feeder unbalance",   0.10, 0.98, 0.04, 0.01, 0.20, 0.04, 0.01),
            (36, "Load unbal + low IBR",  0.20, 0.99, 0.05, 0.01, 0.24, 0.05, 0.01),
            (37, "Load unbal + med IBR",  0.30, 0.99, 0.05, 0.01, 0.27, 0.06, 0.01),
            (38, "Severe load unbalance", 0.10, 0.96, 0.07, 0.03, 0.32, 0.09, 0.03),
        ]
        for sid, desc, k, vp, vn, vz, ip, i2, i0 in load_params:
            rows.append(UnbalanceScenario(
                scenario_id=sid, description=desc, category="LOAD_UNBALANCE",
                fault_type="NONE", k_ibr=k,
                v_pos_pu=vp, v_neg_pu=vn, v_zero_pu=vz,
                i_pos_pu=ip, i_neg_pu=i2, i_zero_pu=i0,
                expected_action="ALERT",
            ))

        # ── Group 5: Ambiguous (scenarios 39–45) ─────────────────────
        # Light SLG on high-IBR bus — V2 raised but IBR also contributes
        ambig_params = [
            (39, "Light SLG high-IBR bus",   0.60, 0.94, 0.10, 0.07, 0.26, 0.18, 0.16),
            (40, "Light SLG + IBR dist",     0.55, 0.93, 0.11, 0.07, 0.28, 0.20, 0.17),
            (41, "DLG far + IBR dom",        0.70, 0.91, 0.11, 0.08, 0.30, 0.22, 0.18),
            (42, "High load + light SLG",    0.20, 0.93, 0.09, 0.06, 0.24, 0.16, 0.14),
            (43, "SLG + IBR high I2",        0.65, 0.90, 0.13, 0.08, 0.32, 0.26, 0.22),
            (44, "Moderate unbal + k=0.50",  0.50, 0.95, 0.09, 0.05, 0.26, 0.16, 0.13),
            (45, "DLG far + med-IBR",        0.40, 0.92, 0.10, 0.07, 0.28, 0.19, 0.16),
        ]
        for sid, desc, k, vp, vn, vz, ip, i2, i0 in ambig_params:
            rows.append(UnbalanceScenario(
                scenario_id=sid, description=desc, category="AMBIGUOUS",
                fault_type="SLG", k_ibr=k,
                v_pos_pu=vp, v_neg_pu=vn, v_zero_pu=vz,
                i_pos_pu=ip, i_neg_pu=i2, i_zero_pu=i0,
                expected_action="ALERT",
            ))

        # ── Group 6: Three-phase faults (scenarios 46–50) ─────────────
        # Balanced fault — I2/I1 stays low, no neg-seq alarm needed
        tph_params = [
            (46, "3PH fault low-IBR",   0.10, 0.65, 0.03, 0.02, 0.80, 0.02, 0.02),
            (47, "3PH fault med-IBR",   0.40, 0.60, 0.03, 0.02, 0.85, 0.03, 0.02),
            (48, "3PH fault high-IBR",  0.70, 0.55, 0.02, 0.01, 0.90, 0.02, 0.01),
            (49, "3PH fault remote",    0.20, 0.75, 0.03, 0.02, 0.50, 0.02, 0.02),
            (50, "3PH fault heavy",     0.50, 0.50, 0.02, 0.01, 1.00, 0.02, 0.01),
        ]
        for sid, desc, k, vp, vn, vz, ip, i2, i0 in tph_params:
            rows.append(UnbalanceScenario(
                scenario_id=sid, description=desc, category="REAL_FAULT",
                fault_type="3PH", k_ibr=k,
                v_pos_pu=vp, v_neg_pu=vn, v_zero_pu=vz,
                i_pos_pu=ip, i_neg_pu=i2, i_zero_pu=i0,
                expected_action="PERMIT",   # no block needed; balanced fault trips normally
            ))

        assert len(rows) == 50, f"Expected 50 scenarios, got {len(rows)}"
        return rows
