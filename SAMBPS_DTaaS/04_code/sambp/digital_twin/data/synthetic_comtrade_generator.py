# =============================================================================
# sambp / digital_twin / data / synthetic_comtrade_generator.py
#
# Synthetic COMTRADE generator — IEEE C37.111-2013 ASCII format.
#
# Produces realistic three-phase fault recordings that mimic SP Group
# field records.  Waveforms are physics-informed:
#
#   Pre-fault   : balanced 1.0 pu with 1–3% THD harmonic injection
#   Fault onset : voltage sag per fault type; current increases limited
#                 by IBR current-limiter model
#   Post-fault  : 5–10 cycle recovery transient with exponential decay
#
# IBR current-limiter model (IEC 61727 / IEC 61850-90-7)
# -------------------------------------------------------
# Each IBR type has a rated current ceiling I_max and a priority mode
# (voltage-priority or current-priority).  During fault the IBR injects
# up to I_max into the positive-sequence, with negative-sequence
# suppressed except for SG/DFIG machines:
#
#   SG   : synchronous — subtransient surge ~8–12 pu → limited by X"d
#   DFIG : doubly-fed IG — 1.0–1.3 pu limited by crow-bar protection
#   GFM  : grid-forming   — 1.0–1.1 pu (tight current limit)
#   GFL  : grid-following  — 1.1–1.5 pu (P-priority during fault)
#   PV   : photovoltaic   — 1.0–1.2 pu (DC-link limited)
#   BESS : battery ESS    — 1.0–1.5 pu (bidirectional)
#
# Public API
# ----------
# gen = SyntheticComtradeGenerator(output_dir="data/field_records/synthetic")
# cfg_path, dat_path = gen.generate_fault_record(
#     fault_type="SLG", ibr_type="GFL",
#     ibr_penetration=0.40, grid_strength=5.0)
# =============================================================================

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import numpy as np


# ---------------------------------------------------------------------------
# IBR current-limiter parameters
# ---------------------------------------------------------------------------

@dataclass
class IBRProfile:
    """Physics parameters for one IBR type during fault."""
    i_max_pu:        float   # peak fault current ceiling [pu]
    neg_seq_ratio:   float   # I2/I1 during SLG fault
    response_cycles: float   # cycles to reach current limit from fault onset
    recovery_cycles: float   # cycles for post-fault recovery
    thd_pct:         float   # pre-fault THD level [%]


_IBR_PROFILES: dict[str, IBRProfile] = {
    "SG":   IBRProfile(i_max_pu=8.0,  neg_seq_ratio=0.40, response_cycles=0.5,  recovery_cycles=5.0,  thd_pct=1.0),
    "DFIG": IBRProfile(i_max_pu=1.25, neg_seq_ratio=0.30, response_cycles=1.0,  recovery_cycles=6.0,  thd_pct=2.0),
    "GFM":  IBRProfile(i_max_pu=1.10, neg_seq_ratio=0.05, response_cycles=0.25, recovery_cycles=5.0,  thd_pct=1.5),
    "GFL":  IBRProfile(i_max_pu=1.40, neg_seq_ratio=0.08, response_cycles=0.5,  recovery_cycles=7.0,  thd_pct=2.5),
    "PV":   IBRProfile(i_max_pu=1.15, neg_seq_ratio=0.04, response_cycles=0.75, recovery_cycles=8.0,  thd_pct=3.0),
    "BESS": IBRProfile(i_max_pu=1.50, neg_seq_ratio=0.06, response_cycles=0.25, recovery_cycles=6.0,  thd_pct=2.0),
}

# Fault-type voltage sag depth per phase [Va_sag, Vb_sag, Vc_sag] in pu
# Values below 1.0 mean that phase voltage drops to this fraction during fault
_VOLTAGE_SAG: dict[str, tuple[float, float, float]] = {
    "SLG":                  (0.20, 0.92, 0.92),   # phase A to ground
    "LL":                   (0.30, 0.30, 0.95),   # phase A–B
    "DLG":                  (0.15, 0.15, 0.92),   # phase A–B to ground
    "3PH":                  (0.10, 0.10, 0.10),   # balanced three-phase
    "evolving_SLG_to_DLG":  (0.20, 0.92, 0.92),   # starts as SLG
    "cross_country":        (0.25, 0.92, 0.30),   # A-gnd on line1, C on line2
}

# Fault-type current amplification per phase (pu multiplier on rated current)
_CURRENT_FAULT: dict[str, tuple[float, float, float]] = {
    "SLG":                  (3.0, 0.10, 0.10),
    "LL":                   (2.5, 2.5,  0.10),
    "DLG":                  (2.8, 2.8,  0.10),
    "3PH":                  (3.5, 3.5,  3.5 ),
    "evolving_SLG_to_DLG":  (2.5, 1.8,  0.10),
    "cross_country":        (2.5, 0.10, 2.0 ),
}

VALID_FAULT_TYPES = list(_VOLTAGE_SAG.keys())
VALID_IBR_TYPES   = list(_IBR_PROFILES.keys())


# ---------------------------------------------------------------------------
# Waveform builders
# ---------------------------------------------------------------------------

def _balanced_3phase(
    t: np.ndarray,
    amplitude: float,
    frequency: float,
    phase_offset: float = 0.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return balanced Va, Vb, Vc sinusoids."""
    phi = 2 * np.pi * frequency * t + phase_offset
    va = amplitude * np.sin(phi)
    vb = amplitude * np.sin(phi - 2 * np.pi / 3)
    vc = amplitude * np.sin(phi + 2 * np.pi / 3)
    return va, vb, vc


def _add_thd(
    rng: np.random.Generator,
    signal: np.ndarray,
    t: np.ndarray,
    thd_pct: float,
    frequency: float,
) -> np.ndarray:
    """
    Add harmonic noise to approximate a given THD level.

    Injects 3rd, 5th, 7th harmonics (dominant in IBR output) with random
    phase so repeated calls produce varied waveforms.
    """
    if thd_pct <= 0:
        return signal
    total_h_amp = thd_pct / 100.0  # target RMS of harmonics relative to fundamental
    # Split amplitude across 3rd, 5th, 7th (weights: 0.6, 0.3, 0.1)
    weights = np.array([0.6, 0.3, 0.1])
    harmonics = [3, 5, 7]
    out = signal.copy()
    for h, w in zip(harmonics, weights):
        amp = total_h_amp * w
        ph  = rng.uniform(0, 2 * np.pi)
        out += amp * np.sin(2 * np.pi * h * frequency * t + ph)
    return out


def _ramp(t: np.ndarray, t_start: float, t_end: float) -> np.ndarray:
    """Smooth 0→1 ramp between t_start and t_end (Hann-shaped)."""
    x = np.clip((t - t_start) / max(t_end - t_start, 1e-9), 0.0, 1.0)
    return 0.5 * (1 - np.cos(np.pi * x))


def _exp_recovery(
    t: np.ndarray,
    t_start: float,
    tau: float,
) -> np.ndarray:
    """Exponential decay starting at t_start: 1 * exp(-(t-t_start)/tau) for t >= t_start."""
    out = np.zeros_like(t)
    mask = t >= t_start
    out[mask] = np.exp(-(t[mask] - t_start) / tau)
    return out


# ---------------------------------------------------------------------------
# SyntheticComtradeGenerator
# ---------------------------------------------------------------------------

class SyntheticComtradeGenerator:
    """
    Generates synthetic IEEE C37.111-2013 ASCII COMTRADE file pairs.

    Parameters
    ----------
    output_dir : str
        Directory where .cfg and .dat files are written.
        Created if it does not exist.
    seed : int, optional
        Random seed for reproducibility.  Each generate_fault_record() call
        advances an internal RNG derived from this seed.
    """

    # Analog channel definitions: (ch_id, ph, unit, a_scaling)
    # a_scaling chosen so raw values in ±1.0 pu map to raw ints in a useful range
    _ANALOG_CHANNELS = [
        ("Va", "A", "kV",  1.0),
        ("Vb", "B", "kV",  1.0),
        ("Vc", "C", "kV",  1.0),
        ("Ia", "A", "A",   1.0),
        ("Ib", "B", "A",   1.0),
        ("Ic", "C", "A",   1.0),
    ]

    _DIGITAL_CHANNELS = [
        ("TRIP",   "", 0),
        ("CLOSE",  "", 0),
        ("87L_OP", "", 0),
        ("21_OP",  "", 0),
        ("OC_OP",  "", 0),
    ]

    def __init__(self, output_dir: str = "data/field_records/synthetic", seed: int = 42) -> None:
        self._out_dir = Path(output_dir)
        self._out_dir.mkdir(parents=True, exist_ok=True)
        self._rng = np.random.default_rng(seed)
        self._record_counter = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_fault_record(
        self,
        fault_type:           str,
        ibr_type:             str,
        ibr_penetration:      float,    # 0.0–1.0 fraction of generation
        grid_strength:        float,    # SCR (short-circuit ratio)
        pre_fault_duration:   float = 0.10,   # seconds
        fault_duration:       float = 0.15,   # seconds
        post_fault_duration:  float = 0.20,   # seconds
        sample_rate:          float = 4800.0, # Sa/s
        frequency:            float = 50.0,   # Hz
        record_id:            Optional[str] = None,
    ) -> Tuple[str, str]:
        """
        Generate a synthetic COMTRADE fault record.

        Parameters
        ----------
        fault_type : str
            One of: SLG, LL, DLG, 3PH, evolving_SLG_to_DLG, cross_country.
        ibr_type : str
            One of: SG, DFIG, GFM, GFL, PV, BESS.
        ibr_penetration : float
            Fraction of total generation supplied by IBR [0.0, 1.0].
        grid_strength : float
            Short-circuit ratio (SCR).  Low SCR (3–5) = weak grid.
        pre_fault_duration, fault_duration, post_fault_duration : float
            Window lengths in seconds.
        sample_rate : float
            Samples per second (4800 = 96 Sa/cycle at 50 Hz).
        frequency : float
            Nominal power system frequency [Hz].
        record_id : str, optional
            Explicit file stem.  Auto-generated if not given.

        Returns
        -------
        (cfg_path, dat_path) : tuple[str, str]
            Absolute string paths to the written .cfg and .dat files.
        """
        if fault_type not in _VOLTAGE_SAG:
            raise ValueError(f"Unknown fault_type {fault_type!r}. "
                             f"Valid: {VALID_FAULT_TYPES}")
        if ibr_type not in _IBR_PROFILES:
            raise ValueError(f"Unknown ibr_type {ibr_type!r}. "
                             f"Valid: {VALID_IBR_TYPES}")

        profile = _IBR_PROFILES[ibr_type]
        self._record_counter += 1
        if record_id is None:
            record_id = (f"rec{self._record_counter:04d}"
                         f"_{fault_type}_{ibr_type}"
                         f"_k{int(ibr_penetration * 100):02d}"
                         f"_scr{int(grid_strength):02d}")

        # ---- Build time axis ----
        t_total = pre_fault_duration + fault_duration + post_fault_duration
        n_total = int(round(t_total * sample_rate))
        t       = np.arange(n_total) / sample_rate
        ts_us   = (t * 1e6).astype(np.int64)

        t_fault_on  = pre_fault_duration
        t_fault_off = pre_fault_duration + fault_duration

        # ---- Waveform synthesis ----
        va, vb, vc, ia, ib, ic, digi = self._build_waveforms(
            t=t,
            t_on=t_fault_on,
            t_off=t_fault_off,
            fault_type=fault_type,
            profile=profile,
            ibr_penetration=ibr_penetration,
            grid_strength=grid_strength,
            frequency=frequency,
        )

        # ---- Write files ----
        cfg_path = self._out_dir / f"{record_id}.cfg"
        dat_path = self._out_dir / f"{record_id}.dat"

        self._write_cfg(cfg_path, record_id, frequency, sample_rate, n_total)
        self._write_dat(dat_path, ts_us, va, vb, vc, ia, ib, ic, digi)

        return str(cfg_path), str(dat_path)

    # ------------------------------------------------------------------
    # Waveform builder
    # ------------------------------------------------------------------

    def _build_waveforms(
        self,
        t:               np.ndarray,
        t_on:            float,
        t_off:           float,
        fault_type:      str,
        profile:         IBRProfile,
        ibr_penetration: float,
        grid_strength:   float,
        frequency:       float,
    ) -> tuple:
        """
        Synthesise Va/Vb/Vc/Ia/Ib/Ic and 5 digital channels.

        Returns
        -------
        va, vb, vc, ia, ib, ic : ndarray (N,)  — pu quantities
        digi                   : ndarray (N, 5) — 0/1 digital channels
        """
        N = len(t)

        # Random inception angle (uniformly distributed 0–360°)
        inception_angle = self._rng.uniform(0, 2 * np.pi)

        # ---- Pre-fault balanced signal ----
        va_pf, vb_pf, vc_pf = _balanced_3phase(t, 1.0, frequency, inception_angle)
        ia_pf, ib_pf, ic_pf = _balanced_3phase(t, 0.20, frequency,
                                                inception_angle - np.pi / 6)

        # Add THD harmonic noise (scaled by IBR penetration)
        thd = profile.thd_pct * ibr_penetration
        for sig in (va_pf, vb_pf, vc_pf, ia_pf, ib_pf, ic_pf):
            # In-place addition via helper
            pass
        va_pf = _add_thd(self._rng, va_pf, t, thd * 0.3, frequency)
        vb_pf = _add_thd(self._rng, vb_pf, t, thd * 0.3, frequency)
        vc_pf = _add_thd(self._rng, vc_pf, t, thd * 0.3, frequency)
        ia_pf = _add_thd(self._rng, ia_pf, t, thd, frequency)
        ib_pf = _add_thd(self._rng, ib_pf, t, thd, frequency)
        ic_pf = _add_thd(self._rng, ic_pf, t, thd, frequency)

        # ---- Fault: voltage sag envelope ----
        sag_a, sag_b, sag_c = _VOLTAGE_SAG[fault_type]
        cur_a, cur_b, cur_c = _CURRENT_FAULT[fault_type]

        # Fault ramp-on (quarter-cycle rise) and ramp-off
        t_rise = 1.0 / (4 * frequency)
        t_fall = 1.0 / (2 * frequency)
        fault_env  = _ramp(t, t_on, t_on + t_rise)          # 0→1 at fault onset
        recov_env  = 1.0 - _ramp(t, t_off, t_off + t_fall)  # 1→0 at fault clearing

        # Combined fault window (1 during fault, transitions at edges)
        win = fault_env * recov_env

        # Voltage during fault: interpolate between pre-fault and sagged value
        va = va_pf * (1.0 - (1.0 - sag_a) * win)
        vb = vb_pf * (1.0 - (1.0 - sag_b) * win)
        vc = vc_pf * (1.0 - (1.0 - sag_c) * win)

        # ---- Fault current: IBR-limited ----
        # Grid contribution scaled by SCR and fault impedance
        scr_factor   = min(grid_strength / 5.0, 3.0)   # normalise to SCR=5 reference
        i_fault_grid = np.array([cur_a, cur_b, cur_c]) * scr_factor * (1.0 - ibr_penetration)

        # IBR contribution capped at I_max
        i_fault_ibr  = np.array([cur_a, cur_b, cur_c]) * ibr_penetration
        i_fault_ibr  = np.clip(i_fault_ibr, 0.0, profile.i_max_pu)

        # Combined fault current amplitude per phase
        i_fault = i_fault_grid + i_fault_ibr

        # Ramp-in the fault current with IBR response delay
        resp_cycles = profile.response_cycles
        t_ibr_on    = t_on + resp_cycles / frequency
        ibr_ramp    = _ramp(t, t_on, t_ibr_on)

        # Phase current during fault: pre-fault + fault increment * window
        ia_fault = i_fault[0] * np.sin(2*np.pi*frequency*t + inception_angle - np.pi/6)
        ib_fault = i_fault[1] * np.sin(2*np.pi*frequency*t + inception_angle - np.pi/6 - 2*np.pi/3)
        ic_fault = i_fault[2] * np.sin(2*np.pi*frequency*t + inception_angle - np.pi/6 + 2*np.pi/3)

        ia = ia_pf + (ia_fault - ia_pf) * win * ibr_ramp
        ib = ib_pf + (ib_fault - ib_pf) * win * ibr_ramp
        ic = ic_pf + (ic_fault - ic_pf) * win * ibr_ramp

        # ---- Evolving fault: SLG → DLG midway through fault window ----
        if fault_type == "evolving_SLG_to_DLG":
            t_evolve = t_on + fault_duration / 2 if hasattr(self, '_last_fault_dur') \
                       else t_on + 0.075
            ev_sag_b, ev_cur_b = 0.15, 2.8
            ev_env = _ramp(t, t_evolve, t_evolve + t_rise) * recov_env
            vb *= 1.0 - (1.0 - ev_sag_b / max(sag_b, 0.01)) * ev_env
            ib_extra = ev_cur_b * np.sin(2*np.pi*frequency*t + inception_angle - np.pi/6 - 2*np.pi/3)
            ib += (ib_extra - ib) * ev_env

        # ---- Post-fault recovery oscillation ----
        tau_v = profile.recovery_cycles / frequency
        tau_i = tau_v * 0.7
        # Add decaying sinusoidal transient (sub-synchronous oscillation)
        osc_freq  = frequency * self._rng.uniform(0.3, 0.7)   # 15–35 Hz
        osc_amp_v = self._rng.uniform(0.02, 0.06)             # 2–6% transient
        osc_amp_i = self._rng.uniform(0.05, 0.15)
        decay_v   = _exp_recovery(t, t_off, tau_v)
        decay_i   = _exp_recovery(t, t_off, tau_i)
        va += osc_amp_v * decay_v * np.sin(2*np.pi*osc_freq*t + self._rng.uniform(0, 2*np.pi))
        vb += osc_amp_v * decay_v * np.sin(2*np.pi*osc_freq*t + self._rng.uniform(0, 2*np.pi))
        vc += osc_amp_v * decay_v * np.sin(2*np.pi*osc_freq*t + self._rng.uniform(0, 2*np.pi))
        ia += osc_amp_i * decay_i * np.sin(2*np.pi*osc_freq*t + self._rng.uniform(0, 2*np.pi))
        ib += osc_amp_i * decay_i * np.sin(2*np.pi*osc_freq*t + self._rng.uniform(0, 2*np.pi))
        ic += osc_amp_i * decay_i * np.sin(2*np.pi*osc_freq*t + self._rng.uniform(0, 2*np.pi))

        # ---- Measurement noise (CT/VT error ~0.5%) ----
        noise_v = 0.005
        noise_i = 0.010
        va += self._rng.normal(0, noise_v, N)
        vb += self._rng.normal(0, noise_v, N)
        vc += self._rng.normal(0, noise_v, N)
        ia += self._rng.normal(0, noise_i, N)
        ib += self._rng.normal(0, noise_i, N)
        ic += self._rng.normal(0, noise_i, N)

        # ---- Digital channels ----
        # TRIP: asserts after 1-cycle detection delay from fault onset
        t_trip_on  = t_on + 1.5 / frequency
        t_trip_off = t_off + 0.5 / frequency   # breaker clears ~0.5 cycle after relay
        TRIP   = ((t >= t_trip_on) & (t < t_trip_off)).astype(np.int32)

        # CLOSE: momentary assert at post-fault auto-reclose (150 ms after clearing)
        t_close = t_off + 0.150
        CLOSE = ((t >= t_close) & (t < t_close + 3.0/frequency)).astype(np.int32)

        # 87L_OP (line differential): asserts same time as TRIP for internal faults
        L87_OP = TRIP.copy()

        # 21_OP (distance): asserts slightly later (0.5 cycle margin)
        t_21_on = t_on + 2.0 / frequency
        OP_21   = ((t >= t_21_on) & (t < t_trip_off)).astype(np.int32)

        # OC_OP (overcurrent): asserts if fault current exceeds threshold
        i_mag   = np.sqrt((ia**2 + ib**2 + ic**2) / 3)
        OC_OP   = (i_mag > 1.5).astype(np.int32)

        digi = np.column_stack([TRIP, CLOSE, L87_OP, OP_21, OC_OP])
        return va, vb, vc, ia, ib, ic, digi

    # ------------------------------------------------------------------
    # File writers
    # ------------------------------------------------------------------

    def _write_cfg(
        self,
        path:        Path,
        record_id:   str,
        frequency:   float,
        sample_rate: float,
        n_samples:   int,
    ) -> None:
        """Write IEEE C37.111-2013 .cfg file."""
        na = len(self._ANALOG_CHANNELS)
        nd = len(self._DIGITAL_CHANNELS)
        lines = []

        # Line 1: station, device, rev
        lines.append(f"{record_id},SAMBP-DT,2013")

        # Line 2: channel counts
        lines.append(f"{na + nd},{na}A,{nd}D")

        # Analog channel definitions
        for i, (ch_id, ph, uu, a) in enumerate(self._ANALOG_CHANNELS, start=1):
            lines.append(f"{i},{ch_id},{ph},,{uu},{a:.6f},0.000000,0,-999999,999999,1.0,1.0,P")

        # Digital channel definitions
        for i, (ch_id, ph, y) in enumerate(self._DIGITAL_CHANNELS, start=1):
            lines.append(f"{i},{ch_id},{ph},,{y}")

        # Frequency
        lines.append(f"{frequency:.1f}")

        # nrates = 1
        lines.append("1")
        lines.append(f"{sample_rate:.1f},{n_samples}")

        # Timestamps (use a fixed reference; real timestamps from .dat)
        ts = time.strftime("%d/%m/%Y,%H:%M:%S.000000")
        lines.append(ts)
        lines.append(ts)

        # Data format
        lines.append("ASCII")

        path.write_text("\n".join(lines) + "\n", encoding="ascii")

    def _write_dat(
        self,
        path:     Path,
        ts_us:    np.ndarray,
        va:       np.ndarray,
        vb:       np.ndarray,
        vc:       np.ndarray,
        ia:       np.ndarray,
        ib:       np.ndarray,
        ic:       np.ndarray,
        digi:     np.ndarray,
    ) -> None:
        """Write ASCII .dat file: sample_no, timestamp_μs, a0..a5, d0..d4"""
        N    = len(ts_us)
        rows = []
        for i in range(N):
            vals = [str(i + 1), str(int(ts_us[i]))]
            vals += [f"{v:.8f}" for v in (va[i], vb[i], vc[i], ia[i], ib[i], ic[i])]
            vals += [str(int(digi[i, j])) for j in range(digi.shape[1])]
            rows.append(",".join(vals))
        path.write_text("\n".join(rows) + "\n", encoding="ascii")
