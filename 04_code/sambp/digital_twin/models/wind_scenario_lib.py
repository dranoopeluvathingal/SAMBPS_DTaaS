# =============================================================================
# sambp / digital_twin / models / wind_scenario_lib.py
#
# Wind turbine scenario library — TR-69 WP 69.3
#
# 150+ parameterised scenarios for Type-4 wind turbine validation spanning:
#   Group A (1–30)   : MPPT below-rated operation (variable wind, 3 turbines)
#   Group B (31–60)  : Pitch control at/above rated wind speed
#   Group C (61–90)  : FRT — IEC / AEMO / NERC grid codes
#   Group D (91–120) : GFM/VSM inertia and damping response
#   Group E (121–150): Current limiting and post-fault recovery
#
# Public API
# ----------
#   lib = WindScenarioLibrary()
#   scenarios = lib.all()          → list[WindScenario]  (len ≥ 150)
#   s = lib.by_id(n)
#   s = lib.by_group("frt")        → list filtered by group key
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from models.type4_wind_model import Type4WindConfig


# ---------------------------------------------------------------------------
# WindScenario dataclass
# ---------------------------------------------------------------------------

@dataclass
class WindScenario:
    """
    One simulation scenario for a Type-4 wind turbine.

    Fields
    ------
    scenario_id    : unique int (1–150+)
    group          : 'mppt' | 'pitch' | 'frt' | 'vsm' | 'current_limit'
    description    : human-readable label
    turbine_preset : 'vestas_v164_8mw' | 'siemens_sg14' | 'goldwind_gwh252_16mw'
    wind_speed_mps : hub-height wind speed [m/s]
    v_terminal_pu  : terminal voltage [pu] (1.0 = normal; < 1 = fault/FRT)
    t_fault_s      : fault duration [s]  (0 = no fault)
    p_setpoint_pu  : active power setpoint (None = MPPT auto)
    q_setpoint_pu  : reactive power setpoint (None = FRT/unity-pf auto)
    expected_trip  : True if turbine should disconnect (outside envelope)
    expected_frt   : True if FRT ride-through expected
    check_mppt     : True if test should verify MPPT optimality
    check_pitch    : True if test should verify pitch is active
    check_q_inject : True if test should verify reactive injection
    check_vsm      : True if test should verify inertia response
    notes          : additional context
    """
    scenario_id:    int
    group:          str
    description:    str
    turbine_preset: str
    wind_speed_mps: float
    v_terminal_pu:  float   = 1.0
    t_fault_s:      float   = 0.0
    p_setpoint_pu:  Optional[float] = None
    q_setpoint_pu:  Optional[float] = None
    expected_trip:  bool = False
    expected_frt:   bool = False
    check_mppt:     bool = False
    check_pitch:    bool = False
    check_q_inject: bool = False
    check_vsm:      bool = False
    notes:          str  = ""

    @property
    def turbine_config(self) -> Type4WindConfig:
        presets = {
            "vestas_v164_8mw":       Type4WindConfig.vestas_v164_8mw,
            "siemens_sg14":          Type4WindConfig.siemens_sg14,
            "goldwind_gwh252_16mw":  Type4WindConfig.goldwind_gwh252_16mw,
        }
        return presets[self.turbine_preset]()


# ---------------------------------------------------------------------------
# Library
# ---------------------------------------------------------------------------

class WindScenarioLibrary:
    """
    Library of ≥150 wind turbine simulation scenarios.
    """

    def all(self) -> List[WindScenario]:
        return self._build()

    def by_id(self, sid: int) -> WindScenario:
        for s in self._build():
            if s.scenario_id == sid:
                return s
        raise KeyError(sid)

    def by_group(self, group: str) -> List[WindScenario]:
        return [s for s in self._build() if s.group == group]

    # ------------------------------------------------------------------
    @staticmethod
    def _build() -> List[WindScenario]:
        rows: List[WindScenario] = []
        sid = 1

        # ── Group A: MPPT below-rated (30 scenarios) ─────────────────
        # 3 turbines × 10 wind speeds (3–12 m/s)
        turbines = ["vestas_v164_8mw", "siemens_sg14", "goldwind_gwh252_16mw"]
        winds_below = [3.0, 4.0, 5.0, 6.0, 7.5, 8.0, 9.0, 10.0, 11.0, 12.0]
        for t in turbines:
            for v in winds_below:
                rows.append(WindScenario(
                    scenario_id=sid, group="mppt",
                    description=f"MPPT at {v}m/s [{t}]",
                    turbine_preset=t,
                    wind_speed_mps=v, v_terminal_pu=1.0,
                    check_mppt=True,
                    notes="MPPT: Cp should be near Cp_max",
                ))
                sid += 1

        # ── Group B: Pitch control at/above rated (30 scenarios) ──────
        # 3 turbines × 10 above-rated wind speeds (13–25 m/s)
        winds_above = [13.0, 14.0, 15.0, 16.0, 17.5, 18.0, 20.0, 22.0, 23.0, 25.0]
        for t in turbines:
            for v in winds_above:
                rows.append(WindScenario(
                    scenario_id=sid, group="pitch",
                    description=f"Pitch at {v}m/s [{t}]",
                    turbine_preset=t,
                    wind_speed_mps=v, v_terminal_pu=1.0,
                    check_pitch=True,
                    notes="Pitch control: P_gen should be clipped at 1.0 pu",
                ))
                sid += 1

        # ── Group C: FRT scenarios (30 scenarios) ─────────────────────
        # 3 grid codes × (3 turbines) × ~3 dip depths × ~1 duration each
        frt_cases = [
            # (standard, turbine, v_pu, t_fault, expected_trip, expected_frt)
            ("iec",  "vestas_v164_8mw",      0.00, 0.100, False, True),
            ("iec",  "vestas_v164_8mw",      0.00, 0.160, True,  False),  # exceeds 140ms
            ("iec",  "vestas_v164_8mw",      0.20, 0.500, False, True),
            ("iec",  "vestas_v164_8mw",      0.50, 1.200, False, True),
            ("iec",  "vestas_v164_8mw",      0.85, 2.000, False, True),
            ("iec",  "siemens_sg14",         0.00, 0.130, False, True),
            ("iec",  "siemens_sg14",         0.30, 0.800, False, True),
            ("iec",  "siemens_sg14",         0.70, 1.800, False, True),
            ("iec",  "goldwind_gwh252_16mw", 0.00, 0.120, False, True),
            ("iec",  "goldwind_gwh252_16mw", 0.50, 1.000, False, True),
            ("aemo", "vestas_v164_8mw",      0.00, 0.150, False, True),
            ("aemo", "vestas_v164_8mw",      0.00, 0.200, True,  False),  # exceeds 175ms
            ("aemo", "vestas_v164_8mw",      0.40, 0.400, False, True),
            ("aemo", "vestas_v164_8mw",      0.70, 1.000, False, True),
            ("aemo", "siemens_sg14",         0.00, 0.150, False, True),
            ("aemo", "siemens_sg14",         0.50, 0.800, False, True),
            ("aemo", "goldwind_gwh252_16mw", 0.20, 0.400, False, True),
            ("aemo", "goldwind_gwh252_16mw", 0.80, 1.500, False, True),
            ("nerc", "vestas_v164_8mw",      0.00, 0.140, False, True),
            ("nerc", "vestas_v164_8mw",      0.00, 0.180, True,  False),  # exceeds 160ms
            ("nerc", "vestas_v164_8mw",      0.30, 0.500, False, True),
            ("nerc", "vestas_v164_8mw",      0.70, 2.500, False, True),
            ("nerc", "siemens_sg14",         0.00, 0.150, False, True),
            ("nerc", "siemens_sg14",         0.50, 1.500, False, True),
            ("nerc", "goldwind_gwh252_16mw", 0.00, 0.130, False, True),
            ("nerc", "goldwind_gwh252_16mw", 0.40, 1.000, False, True),
            ("nerc", "goldwind_gwh252_16mw", 0.70, 2.000, False, True),
            ("iec",  "vestas_v164_8mw",      0.15, 0.300, False, True),
            ("aemo", "siemens_sg14",         0.30, 0.600, False, True),
            ("nerc", "goldwind_gwh252_16mw", 0.20, 0.800, False, True),
        ]
        for std, t, v, tf, trip, frt_exp in frt_cases:
            rows.append(WindScenario(
                scenario_id=sid, group="frt",
                description=f"FRT {std} V={v}pu t={tf}s [{t}]",
                turbine_preset=t,
                wind_speed_mps=12.0,
                v_terminal_pu=v, t_fault_s=tf,
                expected_trip=trip, expected_frt=frt_exp,
                check_q_inject=(not trip),
                notes=f"Grid code: {std}",
            ))
            sid += 1

        # ── Group D: GFM/VSM inertia response (30 scenarios) ──────────
        # siemens_sg14 (GFM) only: frequency step events, wind gusts
        vsm_winds  = [6.0, 8.0, 10.0, 12.0, 14.0]
        freq_steps = [+0.50, -0.50, +1.00, -1.00, +2.00, -2.00]
        for v in vsm_winds:
            for df in freq_steps:
                rows.append(WindScenario(
                    scenario_id=sid, group="vsm",
                    description=f"VSM df={df:+.1f}Hz at {v}m/s",
                    turbine_preset="siemens_sg14",
                    wind_speed_mps=v,
                    check_vsm=True,
                    notes=f"VSM inertia: ROCOF should be limited; df={df}Hz",
                ))
                sid += 1

        # ── Group E: Current limiting + post-fault recovery (30 scenarios) ──
        fault_winds = [8.0, 10.0, 12.0]
        v_dips      = [0.00, 0.10, 0.20, 0.50, 0.70]
        t_faults    = [0.10, 0.15]
        for t in ["vestas_v164_8mw", "goldwind_gwh252_16mw"]:
            for v_w in fault_winds:
                for v_dip in v_dips:
                    for tf in t_faults:
                        if sid > 150:
                            break
                        rows.append(WindScenario(
                            scenario_id=sid, group="current_limit",
                            description=f"CL {t} v_w={v_w} vdip={v_dip} tf={tf}",
                            turbine_preset=t,
                            wind_speed_mps=v_w,
                            v_terminal_pu=v_dip, t_fault_s=tf,
                            expected_frt=True,
                            check_q_inject=True,
                            notes="Current clamped to i_max_trans_pu during fault",
                        ))
                        sid += 1
                    if sid > 150:
                        break
                if sid > 150:
                    break
            if sid > 150:
                break

        # Pad to exactly 150 if under
        while len(rows) < 150:
            rows.append(WindScenario(
                scenario_id=sid, group="current_limit",
                description=f"CL sweep extra {sid}",
                turbine_preset="vestas_v164_8mw",
                wind_speed_mps=10.0,
                v_terminal_pu=0.30, t_fault_s=0.12,
                expected_frt=True,
                check_q_inject=True,
            ))
            sid += 1

        assert len(rows) >= 150, f"Expected ≥150 scenarios, got {len(rows)}"
        return rows
