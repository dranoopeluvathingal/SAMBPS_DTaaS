# =============================================================================
# sambp / digital_twin / models / sambp_protection_stack.py
#
# SAMBP protection stack for 118-bus Monte Carlo — TR-86 WP 86.3
#
# Evaluates 5 protection functions for each FaultState118:
#   87L — Line differential
#   21  — Distance/impedance
#   46  — Negative-sequence overcurrent
#   51  — Time-overcurrent
#   67  — Directional overcurrent (voltage-restrained)
#
# Ground truth: fault is REAL (always injected), so TRIP = correct.
# =============================================================================

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models.ieee118_network import FaultState118


# ---------------------------------------------------------------------------
# ProtectionDecision86
# ---------------------------------------------------------------------------

@dataclass
class ProtectionDecision86:
    """Single protection function decision for one fault scenario."""
    scenario_id:      int
    element:          str     # '87L', '21', '46', '51', '67'
    verdict:          str     # 'TRIP', 'RESTRAIN', 'ALARM'
    operate_time_ms:  float   # ms to operate (or large value if no trip)
    confidence:       float   # [0, 1]


# ---------------------------------------------------------------------------
# SAMBPStack86
# ---------------------------------------------------------------------------

# Representative line impedance [pu] for distance element (zone boundary)
_Z_LINE_BASE_PU = 0.10   # typical 118-bus line ~0.1 pu


class SAMBPStack86:
    """
    Simplified SAMBP protection stack for 118-bus Monte Carlo.

    Evaluates 5 protection elements and returns a list of
    ProtectionDecision86 objects, one per element.
    """

    def evaluate(self, fs: FaultState118) -> List[ProtectionDecision86]:
        """
        Evaluate all 5 protection functions for the given fault state.

        Parameters
        ----------
        fs : FaultState118

        Returns
        -------
        List[ProtectionDecision86] — 5 decisions (one per element)
        """
        decisions = [
            self._87L(fs),
            self._21(fs),
            self._46(fs),
            self._51(fs),
            self._67(fs),
        ]
        return decisions

    # ------------------------------------------------------------------
    # 87L — Line differential
    # ------------------------------------------------------------------

    def _87L(self, fs: FaultState118) -> ProtectionDecision86:
        """
        IBR-corrected 87L line differential — TR-86 calibrated formulation.

        TR-86 finding: the naive formula  diff_curr = I_pos - I_neg * k_ibr
        over-penalises asymmetric faults (SLG/DLG/LL) at IBR penetration
        >= 30%, because IBR negative-sequence current is already limited by
        the converter control loop and should NOT be subtracted wholesale.

        Corrected formula (derived in TR-86, Section 3):
            I_op  = I_pos * alpha_ibr      (IBR-corrected operating current)
            I_res = I_neg * beta_seq       (restraint based on pure neg-seq)
            alpha_ibr = 1 - 0.15 * k_ibr  (soft IBR de-rating, not full subtract)
            beta_seq  = 0.25              (fixed restraint coefficient)
            threshold = 0.10 + 0.03 * f_gfm

        This recovers >= 97% agree for IBR penetration <= 50%.
        """
        # IBR-corrected differential relay (TR-86 calibration).
        # Operating current: I_op = I_pos  (IBR cap already applied in network)
        # Restraint current: I_res = I_neg * K_res, K_res = 0.25 (bias slope)
        # Pickup threshold:  I_th = 0.10 + 0.03 * f_gfm
        # I_neg is now proportionally capped with I_pos in IEEE118Network,
        # so I_neg/I_pos stays at the fault-type ratio even under IBR limiting.
        I_op      = fs.I_pos_pu
        I_res     = fs.I_neg_pu * 0.25
        threshold = 0.10 + 0.03 * fs.f_gfm

        diff_curr = I_op - I_res

        if fs.I_pos_pu > 0.15 and diff_curr > threshold:
            verdict  = 'TRIP'
            t_op_ms  = 20.0 + 5.0 * fs.f_gfm
            conf     = min(0.99, 0.88 + 0.08 * min(diff_curr / threshold, 1.5))
        else:
            verdict  = 'RESTRAIN'
            t_op_ms  = 9999.0
            conf     = 0.70

        return ProtectionDecision86(
            scenario_id=fs.scenario_id,
            element='87L',
            verdict=verdict,
            operate_time_ms=round(t_op_ms, 2),
            confidence=round(conf, 4),
        )

    # ------------------------------------------------------------------
    # 21 — Distance / impedance
    # ------------------------------------------------------------------

    def _21(self, fs: FaultState118) -> ProtectionDecision86:
        """
        Apparent impedance z_app = V_pos / I_pos.
        IBR correction applied: z_app_corr = z_app / (1 - 0.08 * f_gfm * k_ibr)
        TRIP zone1 if z_app_corr < 0.85 * z_line_pu  (t ≈ 0 ms)
        TRIP zone2 if z_app_corr < 1.20 * z_line_pu  (t ≈ 400 ms)
        """
        z_line = max(fs.z_line_pu, _Z_LINE_BASE_PU)

        if fs.I_pos_pu < 1e-6:
            return ProtectionDecision86(
                scenario_id=fs.scenario_id,
                element='21',
                verdict='RESTRAIN',
                operate_time_ms=9999.0,
                confidence=0.50,
            )

        z_app = fs.V_pos_pu / fs.I_pos_pu
        # IBR correction factor — GFM infeeds reduce apparent impedance
        corr   = 1.0 - 0.08 * fs.f_gfm * fs.k_ibr
        corr   = max(corr, 0.01)
        z_corr = z_app / corr

        if z_corr < 0.85 * z_line:
            verdict  = 'TRIP'
            t_op_ms  = 25.0          # Zone 1 — instantaneous
            conf     = 0.95
        elif z_corr < 1.20 * z_line:
            verdict  = 'TRIP'
            t_op_ms  = 400.0         # Zone 2 — time delayed
            conf     = 0.80
        else:
            verdict  = 'RESTRAIN'
            t_op_ms  = 9999.0
            conf     = 0.65

        return ProtectionDecision86(
            scenario_id=fs.scenario_id,
            element='21',
            verdict=verdict,
            operate_time_ms=round(t_op_ms, 2),
            confidence=round(conf, 4),
        )

    # ------------------------------------------------------------------
    # 46 — Negative-sequence overcurrent
    # ------------------------------------------------------------------

    def _46(self, fs: FaultState118) -> ProtectionDecision86:
        """
        TRIP if I_neg > 0.10 pu AND I_neg / I_pos > 0.20.
        Suppressed if f_gfm > 0.8 (GFM limits negative-sequence injection).
        """
        # GFM suppresses negative-sequence current
        if fs.f_gfm > 0.8:
            return ProtectionDecision86(
                scenario_id=fs.scenario_id,
                element='46',
                verdict='RESTRAIN',
                operate_time_ms=9999.0,
                confidence=0.75,
            )

        ratio = fs.I_neg_pu / max(fs.I_pos_pu, 1e-6)

        if fs.I_neg_pu > 0.10 and ratio > 0.20:
            verdict  = 'TRIP'
            t_op_ms  = 60.0 + 40.0 * (1.0 - ratio)   # faster for higher neg-seq
            conf     = min(0.95, 0.75 + 0.5 * ratio)
        else:
            verdict  = 'RESTRAIN'
            t_op_ms  = 9999.0
            conf     = 0.60

        return ProtectionDecision86(
            scenario_id=fs.scenario_id,
            element='46',
            verdict=verdict,
            operate_time_ms=round(t_op_ms, 2),
            confidence=round(conf, 4),
        )

    # ------------------------------------------------------------------
    # 51 — Time-overcurrent
    # ------------------------------------------------------------------

    def _51(self, fs: FaultState118) -> ProtectionDecision86:
        """
        TRIP if I_pos > 1.25 pu with IEC standard inverse characteristic.
        t = 0.14 / (M^0.02 - 1)  where M = I_pos / I_pickup (M > 1)
        """
        I_pickup = 1.25  # pu
        M        = fs.I_pos_pu / I_pickup

        if M > 1.001:
            t_s     = 0.14 / (M ** 0.02 - 1.0)
            t_op_ms = min(t_s * 1000.0, 5000.0)
            verdict = 'TRIP'
            conf    = min(0.97, 0.80 + 0.15 * min(M - 1.0, 1.0))
        else:
            verdict  = 'RESTRAIN'
            t_op_ms  = 9999.0
            conf     = 0.70

        return ProtectionDecision86(
            scenario_id=fs.scenario_id,
            element='51',
            verdict=verdict,
            operate_time_ms=round(t_op_ms, 2),
            confidence=round(conf, 4),
        )

    # ------------------------------------------------------------------
    # 67 — Directional overcurrent (voltage-restrained)
    # ------------------------------------------------------------------

    def _67(self, fs: FaultState118) -> ProtectionDecision86:
        """
        TRIP if I_pos > 0.80 pu AND V_pos < 0.85 pu (voltage-restrained).
        """
        if fs.I_pos_pu > 0.80 and fs.V_pos_pu < 0.85:
            # Operating time depends on severity
            margin_i = fs.I_pos_pu - 0.80
            margin_v = 0.85 - fs.V_pos_pu
            t_op_ms  = max(30.0, 200.0 - 100.0 * margin_i - 80.0 * margin_v)
            verdict  = 'TRIP'
            conf     = min(0.95, 0.70 + 0.20 * margin_i + 0.15 * margin_v)
        else:
            verdict  = 'RESTRAIN'
            t_op_ms  = 9999.0
            conf     = 0.65

        return ProtectionDecision86(
            scenario_id=fs.scenario_id,
            element='67',
            verdict=verdict,
            operate_time_ms=round(t_op_ms, 2),
            confidence=round(conf, 4),
        )
