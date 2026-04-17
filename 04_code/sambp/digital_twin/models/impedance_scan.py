# =============================================================================
# sambp / digital_twin / models / impedance_scan.py
#
# Online impedance scanner — TR-75 WP 75.2
#
# Network impedance as a function of frequency, Z(f), is the key tool for
# assessing SSCI risk.  When Re[Z_network(f)] + Re[Z_converter(f)] < 0 at
# any sub-synchronous frequency, the composite impedance has negative
# resistance → growing oscillation → SSCI.
#
# Algorithm
# ---------
# 1. At each probe frequency f_k the scanner injects a virtual probe signal
#    (in DT — no physical injection) by modulating the terminal voltage:
#        ΔV_probe(t) = V_probe × sin(2π f_k t)
# 2. The resulting probe current ΔI_probe(t) is estimated from the converter
#    admittance model and the line Π-equivalent.
# 3. Z(f_k) = ΔV_probe / ΔI_probe  (complex — magnitude and angle)
# 4. Re[Z(f_k)] < Z_neg_threshold → negative damping → NegativeDampingEvent
#
# Converter admittance model (GFL, Type-4 wind, simplified)
# ----------------------------------------------------------
# The d-axis current-control loop with PI controller (k_p, k_i) gives:
#   Y_conv(s) = (k_p·s + k_i) / (L_f·s² + k_p·s + k_i)
# where L_f is the filter inductance.
# At f = f_k: s = j·2π·f_k
#
# Network impedance
# -----------------
# Series-compensated line Π-model:
#   Z_line(f) = R_line + j·2π·f·L_line – j / (2π·f·C_series)
# The C_series term creates a resonance at f_r = 1/(2π√(L_line·C_series)).
#
# Public API
# ----------
#   scanner = OnlineImpedanceScanner(line_params, converter_params)
#   result  = scanner.scan(f_sweep=None)   → ImpedanceScanResult
#   scanner.update_line(line_params)
#   scanner.update_converter(converter_params)
# =============================================================================

from __future__ import annotations

import math
import cmath
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np


# ---------------------------------------------------------------------------
# Default sweep frequencies (5–45 Hz in 2 Hz steps + fine around resonance)
# ---------------------------------------------------------------------------
_DEFAULT_SWEEP = list(range(5, 46, 2))   # 5,7,9,...,45 Hz (21 points)


# ---------------------------------------------------------------------------
# NegativeDampingEvent
# ---------------------------------------------------------------------------

@dataclass
class NegativeDampingEvent:
    """Emitted when Re[Z_total(f)] < Z_neg_threshold at any SS frequency."""
    f_hz:           float   # frequency of negative damping [Hz]
    Z_total:        complex # Z_network(f) + Z_converter(f)  [pu]
    Z_network:      complex # network impedance at f [pu]
    Z_converter:    complex # converter impedance at f [pu]
    re_z:           float   # Re[Z_total] — negative
    resonance_risk: str     # "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"


# ---------------------------------------------------------------------------
# ImpedanceScanResult
# ---------------------------------------------------------------------------

@dataclass
class ImpedanceScanResult:
    """Full impedance scan output."""
    freqs_hz:       List[float]          # sweep frequencies [Hz]
    Z_network:      List[complex]        # network Z at each freq [pu]
    Z_converter:    List[complex]        # converter admittance inverse [pu]
    Z_total:        List[complex]        # Z_network + Z_converter
    re_z_total:     List[float]          # Re[Z_total] at each freq
    resonance_f_hz: float                # natural resonance freq of line [Hz]
    f_negative_damping: List[float]      # freqs with Re[Z_total] < 0
    neg_damp_events:    List[NegativeDampingEvent]
    ssci_risk:      bool                 # True if any Re[Z_total] < threshold


# ---------------------------------------------------------------------------
# Line and converter parameter dataclasses
# ---------------------------------------------------------------------------

@dataclass
class SeriesCompLineParams:
    """Π-equivalent parameters for a series-compensated line."""
    R_pu:     float = 0.010   # series resistance [pu]
    XL_pu:    float = 0.150   # series inductive reactance at f0 [pu]
    XC_pu:    float = 0.060   # series capacitive reactance at f0 [pu] (compensation)
    B_pu:     float = 0.002   # shunt susceptance at f0 [pu] (per half-section)
    f0:       float = 50.0    # power frequency [Hz]
    comp_pct: float = 40.0    # series compensation level [%]  XC/(XL)×100

    @classmethod
    def from_compensation_pct(cls, xl_pu: float, comp_pct: float,
                               r_pu: float = 0.010, f0: float = 50.0) -> "SeriesCompLineParams":
        xc = xl_pu * (comp_pct / 100.0)
        return cls(R_pu=r_pu, XL_pu=xl_pu, XC_pu=xc,
                   B_pu=xl_pu * 0.01, f0=f0, comp_pct=comp_pct)


@dataclass
class ConverterParams:
    """
    GFL converter current-control parameters (Type-4 wind), per-unit on system base.

    k_p and k_i must be consistent with L_f_pu:
        k_p ≈ 2π × bandwidth_hz × L_f_pu   (e.g. 2π×60×0.08 ≈ 30)
        k_i ≈ (2π × bandwidth_hz)² × L_f_pu (e.g. (2π×60)² × 0.08 ≈ 11,300)
    Typical GFL Type-4 wind: bandwidth_hz = 30–100 Hz.
    """
    L_f_pu:   float = 0.080    # filter inductance [pu]
    k_p:      float = 3.0      # current controller proportional gain [pu/pu]
    k_i:      float = 3000.0   # current controller integral gain [pu/pu·rad/s]
    R_f_pu:   float = 0.005    # filter resistance [pu]
    control_mode: str = "gfl"  # "gfl" | "gfm"
    bandwidth_hz: float = 60.0 # closed-loop bandwidth [Hz]


# ---------------------------------------------------------------------------
# OnlineImpedanceScanner
# ---------------------------------------------------------------------------

class OnlineImpedanceScanner:
    """
    Compute Z(f) for a series-compensated line + Type-4 GFL converter.

    Parameters
    ----------
    line_params      : SeriesCompLineParams
    converter_params : ConverterParams
    z_neg_threshold  : Re[Z_total] below this → negative damping (default –0.005 pu)
    base_mva         : system base [MVA]
    """

    def __init__(self,
                 line_params: SeriesCompLineParams,
                 converter_params: ConverterParams,
                 z_neg_threshold: float = -0.005,
                 base_mva: float = 100.0) -> None:
        self._line  = line_params
        self._conv  = converter_params
        self._z_neg = z_neg_threshold
        self._base  = base_mva

    # ------------------------------------------------------------------
    def scan(self, f_sweep: Optional[List[float]] = None) -> ImpedanceScanResult:
        """
        Perform an impedance sweep over f_sweep frequencies.

        Parameters
        ----------
        f_sweep : list of frequencies [Hz] to sweep (default 5–45 Hz, 2 Hz steps)

        Returns
        -------
        ImpedanceScanResult
        """
        if f_sweep is None:
            f_sweep = _DEFAULT_SWEEP

        Z_net_list   = []
        Z_conv_list  = []
        Z_tot_list   = []
        re_z_list    = []
        neg_damp_evs = []
        neg_damp_fs  = []

        for f in f_sweep:
            z_n = self._z_network(f)
            z_c = self._z_converter(f)
            z_t = z_n + z_c
            re  = z_t.real

            Z_net_list.append(z_n)
            Z_conv_list.append(z_c)
            Z_tot_list.append(z_t)
            re_z_list.append(re)

            if re < self._z_neg:
                risk = self._risk_level(re)
                neg_damp_fs.append(f)
                neg_damp_evs.append(NegativeDampingEvent(
                    f_hz=f,
                    Z_total=z_t,
                    Z_network=z_n,
                    Z_converter=z_c,
                    re_z=round(re, 6),
                    resonance_risk=risk,
                ))

        res_f = self._resonance_frequency()
        # SSCI risk is only meaningful at the line's natural resonance frequency.
        # Re(Z_total(f_res)) < threshold → negatively-damped resonance → SSCI.
        # Evaluating at the swept bins may miss the exact resonance or pick up
        # negative damping at non-resonant frequencies (no physical excitation).
        if res_f > 0:
            z_n_r = self._z_network(res_f)
            z_c_r = self._z_converter(res_f)
            ssci_risk = (z_n_r + z_c_r).real < self._z_neg
        else:
            ssci_risk = False

        return ImpedanceScanResult(
            freqs_hz=list(f_sweep),
            Z_network=Z_net_list,
            Z_converter=Z_conv_list,
            Z_total=Z_tot_list,
            re_z_total=re_z_list,
            resonance_f_hz=round(res_f, 2),
            f_negative_damping=neg_damp_fs,
            neg_damp_events=neg_damp_evs,
            ssci_risk=ssci_risk,
        )

    # ------------------------------------------------------------------
    def update_line(self, params: SeriesCompLineParams) -> None:
        self._line = params

    def update_converter(self, params: ConverterParams) -> None:
        self._conv = params

    @property
    def resonance_frequency(self) -> float:
        return self._resonance_frequency()

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _z_network(self, f: float) -> complex:
        """
        Network impedance at frequency f [Hz] — series-compensated line Π model.

        Z_line(f) = R + j·(f/f0)·XL – j·(f0/f)·XC
        (frequency scaling: inductance ∝ f, capacitance ∝ 1/f)
        """
        lp = self._line
        f0 = lp.f0
        if f <= 0:
            return complex(lp.R_pu, 1e9)   # DC → capacitor is open circuit
        z = complex(lp.R_pu,
                    (f / f0) * lp.XL_pu - (f0 / f) * lp.XC_pu)
        return z

    def _z_converter(self, f: float) -> complex:
        """
        Converter apparent impedance at frequency f.

        For GFL with PI current controller:
          Y_conv(s) = (k_p·s + k_i) / (L_f·s² + (k_p + R_f)·s + k_i)
          Z_conv = 1 / Y_conv

        For GFM (virtual impedance + droop):
          Z_conv ≈ R_virt + j·(f/f0)·X_virt  (purely positive — no SSCI)
        """
        cp = self._conv
        s  = 2j * math.pi * f

        if cp.control_mode.lower() == "gfm":
            # GFM: virtual impedance gives positive resistance → no SSCI
            r_virt = 0.02 + 0.001 * (f / 50.0)
            x_virt = cp.L_f_pu * (f / 50.0)
            return complex(r_virt, x_virt)

        # GFL PI current controller impedance
        num = cp.k_p * s + cp.k_i
        den = cp.L_f_pu * s**2 + (cp.k_p + cp.R_f_pu) * s + cp.k_i

        if abs(den) < 1e-12:
            return complex(1e6, 0)

        y_conv = num / den
        if abs(y_conv) < 1e-12:
            return complex(1e6, 0)

        return 1.0 / y_conv

    def _resonance_frequency(self) -> float:
        """
        Natural resonance frequency of the series-compensated line [Hz].
        f_r = f0 × sqrt(XC / XL)
        """
        lp = self._line
        if lp.XL_pu <= 0:
            return 0.0
        return lp.f0 * math.sqrt(lp.XC_pu / max(lp.XL_pu, 1e-9))

    @staticmethod
    def _risk_level(re_z: float) -> str:
        if re_z < -0.050:
            return "CRITICAL"
        elif re_z < -0.020:
            return "HIGH"
        elif re_z < -0.010:
            return "MEDIUM"
        else:
            return "LOW"
