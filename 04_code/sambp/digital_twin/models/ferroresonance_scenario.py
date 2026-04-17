# =============================================================================
# sambp / digital_twin / models / ferroresonance_scenario.py
#
# Ferroresonance scenario library — TR-84
#
# 20 scenarios in 4 groups:
#   Group N (1–5)  : Normal / no ferroresonance
#   Group F (6–10) : Fundamental-mode ferroresonance
#   Group S (11–15): Subharmonic (period-3 / period-5) ferroresonance
#   Group C (16–20): Chaotic ferroresonance
#
# Each scenario provides a synthetic voltage waveform generator for
# FerroresonanceDetector validation.
# =============================================================================

from __future__ import annotations

import math
import numpy as np
from dataclasses import dataclass, field
from typing import List


@dataclass
class FerroresonanceScenario:
    id:               int
    name:             str
    group:            str      # "NORMAL" | "FUNDAMENTAL" | "SUBHARMONIC" | "CHAOTIC"
    expected_mode:    str      # expected classifier output
    description:      str = ""
    # Waveform parameters
    v_fundamental:    float = 1.0     # fundamental amplitude [pu]
    thd_target:       float = 0.0     # approximate THD to generate
    sub_freqs:        List[float] = field(default_factory=list)   # sub-harmonic freqs [Hz]
    sub_amps:         List[float] = field(default_factory=list)   # sub-harmonic amplitudes [pu]
    chaotic_noise:    float = 0.0     # broadband noise amplitude [pu]
    zc_jitter:        float = 0.0     # ZC timing jitter parameter (unused in generator)
    crest_boost:      float = 0.0     # extra peak boost [pu]

    def generate_waveform(self,
                          fs: float = 1000.0,
                          f0: float = 50.0,
                          duration_s: float = 0.25) -> np.ndarray:
        """
        Synthetic three-phase voltage waveform.

        Returns array shape (N, 7): [t, va, vb, vc, ia, ib, ic]
        Currents are set equal to voltages (single-phase equivalent).
        """
        N   = int(duration_s * fs)
        ts  = np.arange(N) / fs
        w0  = 2 * math.pi * f0

        # Fundamental three-phase
        va = self.v_fundamental * np.cos(w0 * ts)
        vb = self.v_fundamental * np.cos(w0 * ts - 2*math.pi/3)
        vc = self.v_fundamental * np.cos(w0 * ts + 2*math.pi/3)

        # Harmonics (THD target)
        for h in range(2, 8):
            amp = self.thd_target * self.v_fundamental / math.sqrt(6)
            phase = math.pi * h / 7   # varied phase per harmonic
            va += amp * np.cos(h * w0 * ts + phase)
            vb += amp * np.cos(h * w0 * ts - 2*math.pi/3 + phase)
            vc += amp * np.cos(h * w0 * ts + 2*math.pi/3 + phase)

        # Sub-harmonic components
        for f_ss, a_ss in zip(self.sub_freqs, self.sub_amps):
            w_ss = 2 * math.pi * f_ss
            va += a_ss * np.cos(w_ss * ts)
            vb += a_ss * np.cos(w_ss * ts - 2*math.pi/3)
            vc += a_ss * np.cos(w_ss * ts + 2*math.pi/3)

        # Crest boost
        if self.crest_boost > 0:
            # Sharpen peaks with a narrow pulse
            boost_env = self.crest_boost * np.exp(-((np.mod(ts, 1/f0) - 1/(2*f0))**2) /
                                                   (2 * (1/(20*f0))**2))
            va += boost_env

        # Chaotic broadband noise
        if self.chaotic_noise > 0:
            rng = np.random.default_rng(seed=self.id * 17)
            va += self.chaotic_noise * rng.standard_normal(N)
            vb += self.chaotic_noise * rng.standard_normal(N)
            vc += self.chaotic_noise * rng.standard_normal(N)

        return np.column_stack([ts, va, vb, vc, va, vb, vc])


# ---------------------------------------------------------------------------
# Scenario factory
# ---------------------------------------------------------------------------

def build_scenarios() -> List[FerroresonanceScenario]:
    scens: List[FerroresonanceScenario] = []

    # ── Group N: Normal — no ferroresonance ─────────────────────────────────
    normal_params = [
        (1,  "N01_nominal",    "Nominal 1 pu, clean sinusoid",  0.00, [], [],  0.000, 0.0),
        (2,  "N02_light_harm", "1 pu + 3% harmonics",           0.03, [], [],  0.000, 0.0),
        (3,  "N03_low_v",      "0.9 pu voltage, no distortion", 0.00, [], [],  0.000, 0.0),
        (4,  "N04_high_v",     "1.1 pu voltage, no distortion", 0.00, [], [],  0.000, 0.0),
        (5,  "N05_mild_dist",  "5% THD, acceptable level",      0.05, [], [],  0.000, 0.0),
    ]
    v_amps = [1.0, 1.0, 0.9, 1.1, 1.0]
    for (sid, name, desc, thd, sf, sa, noise, cb), v_amp in zip(normal_params, v_amps):
        scens.append(FerroresonanceScenario(
            id=sid, name=name, group="NORMAL", expected_mode="NORMAL",
            description=desc, v_fundamental=v_amp,
            thd_target=thd, sub_freqs=sf, sub_amps=sa,
            chaotic_noise=noise, crest_boost=cb,
        ))

    # ── Group F: Fundamental-mode ferroresonance ────────────────────────────
    fund_params = [
        ( 6, "F06_fund_mild",   "Fundamental FR, mild THD=25%",          0.25, [],       [],      0.00, 0.00),
        ( 7, "F07_fund_mod",    "Fundamental FR, THD=35%, crest boost",  0.35, [],       [],      0.00, 0.20),
        ( 8, "F08_fund_cvt",    "CVT ferroresonance, THD=30%",           0.30, [],       [],      0.00, 0.15),
        ( 9, "F09_fund_cable",  "Cable-induced, THD=28%",                0.28, [],       [],      0.00, 0.10),
        (10, "F10_fund_severe", "Fundamental FR, THD=32%, high crest",   0.32, [],       [],      0.00, 0.30),
    ]
    for sid, name, desc, thd, sf, sa, noise, cb in fund_params:
        scens.append(FerroresonanceScenario(
            id=sid, name=name, group="FUNDAMENTAL", expected_mode="FUNDAMENTAL",
            description=desc, v_fundamental=1.0,
            thd_target=thd, sub_freqs=sf, sub_amps=sa,
            chaotic_noise=noise, crest_boost=cb,
        ))

    # ── Group S: Subharmonic ferroresonance ─────────────────────────────────
    sub_params = [
        (11, "S11_period3",    "Period-3: 16.7 Hz subharmonic",   [50/3],    [0.25],  0.00),
        (12, "S12_period5",    "Period-5: 10 Hz subharmonic",     [10.0],    [0.22],  0.00),
        (13, "S13_period2",    "Period-2: 25 Hz subharmonic",     [25.0],    [0.30],  0.00),
        (14, "S14_multi_sub",  "Multi-sub: 16.7 + 25 Hz",         [50/3, 25],[0.20, 0.18], 0.00),
        (15, "S15_sub_noisy",  "Subharmonic + light noise",        [50/3],   [0.22],  0.03),
    ]
    for sid, name, desc, sf, sa, noise in sub_params:
        scens.append(FerroresonanceScenario(
            id=sid, name=name, group="SUBHARMONIC", expected_mode="SUBHARMONIC",
            description=desc, v_fundamental=1.0,
            thd_target=0.10, sub_freqs=sf, sub_amps=sa,
            chaotic_noise=noise, crest_boost=0.0,
        ))

    # ── Group C: Chaotic ferroresonance ─────────────────────────────────────
    chaotic_params = [
        (16, "C16_chaotic_low",  "Chaotic FR, noise=0.40 pu",   0.40),
        (17, "C17_chaotic_mod",  "Chaotic FR, noise=0.50 pu",   0.50),
        (18, "C18_chaotic_high", "Chaotic FR, noise=0.60 pu",   0.60),
        (19, "C19_chaotic_sub",  "Chaotic + sub + noise=0.35",  0.35),
        (20, "C20_chaotic_max",  "Chaotic FR, noise=0.70 pu",   0.70),
    ]
    sub_extras = [[], [], [], [50/3], []]
    sub_amps_e  = [[], [], [], [0.15], []]
    for (sid, name, desc, noise), sf, sa in zip(chaotic_params, sub_extras, sub_amps_e):
        scens.append(FerroresonanceScenario(
            id=sid, name=name, group="CHAOTIC", expected_mode="CHAOTIC",
            description=desc, v_fundamental=1.0,
            thd_target=0.15, sub_freqs=sf, sub_amps=sa,
            chaotic_noise=noise, crest_boost=0.0,
        ))

    return scens


class FerroresonanceScenarioLibrary:
    def __init__(self) -> None:
        self._scenarios = build_scenarios()

    def __len__(self) -> int:
        return len(self._scenarios)

    def __iter__(self):
        return iter(self._scenarios)

    def __getitem__(self, idx: int):
        return self._scenarios[idx]

    def get_by_group(self, group: str) -> List[FerroresonanceScenario]:
        return [s for s in self._scenarios if s.group == group]

    def get_by_id(self, sid: int) -> FerroresonanceScenario:
        for s in self._scenarios:
            if s.id == sid:
                return s
        raise KeyError(sid)
