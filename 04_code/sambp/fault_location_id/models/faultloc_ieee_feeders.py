"""
faultloc_ieee_feeders.py
=========================
IEEE 13- / 34- / 123-node test feeder digital twins for the SAMBP
Fault-Location Identification project.  Replaces the single-feeder /
single-section restriction of the IEEE Access manuscript with the
benchmark feeders used by the HIF location community.

WP3.1 SKELETON (status this commit).  The IEEE 13-node feeder is
described as a small, fully populated `FeederModel` data structure
(buses, branches with line code, loads, regulators).  IEEE 34 and
IEEE 123 carry name + bus-count placeholders pending WP3.3.  The
`inject_hif()` API is a stub that returns a deterministic
synthetic-waveform bundle suitable for downstream skeleton tests; the
canonical waveform export from PSCAD / MATLAB lands in WP3.3.

Maps to v3 Execution Manual work packages
-----------------------------------------
    WP3.1  Three-phase Y_abc (this skeleton's prerequisite -- see
           `faultloc_three_phase_model.py`).
    WP3.3  Build IEEE 13 / 34 / 123 digital twins in PSCAD + MATLAB
           (THIS MODULE GROWS to host them).
    WP3.7  Validate on the CNRS-2024 IEEE-34 HIF dataset
           (DOI 10.57745/KRYCYY).

Acceptance test (T-D1)
----------------------
Mean location error < 3 % on IEEE 34-node at SNR >= 30 dB.

Public API
----------

    load_feeder(name) -> FeederModel
        name in {'IEEE_13', 'IEEE_34', 'IEEE_123'}.

    inject_hif(feeder, bus, alpha, Rx, *, fault_type='SLG',
               n_samples=200, fs_hz=10000.0) -> WaveformBundle
        Returns a (V, I) sending-end pair derived from the WP3.1
        three-phase Y_abc model with the line geometry approximated as
        the nearest IEEE 13 branch.  WP3.3 replaces this with PSCAD-
        sourced waveforms.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from sambp_fault_location_id.models.faultloc_three_phase_model import (
    H_phase,
)

# --- IEEE 13-node feeder data (Kersting 2002 Table 4.1) -------------------
# Subset sufficient for the WP3.1 skeleton; full per-bus loads + regulators
# land in WP3.3.

IEEE_13_BUSES = ("650", "RG60", "632", "633", "634", "645", "646",
                 "671", "680", "684", "611", "652", "692", "675")

IEEE_13_BRANCHES = (
    # (from_bus, to_bus, length_ft, line_code)
    ("632", "645", 500, "603"),
    ("632", "633", 500, "602"),
    ("633", "634", 0,   "XFM-1"),  # transformer
    ("645", "646", 300, "603"),
    ("650", "632", 2000, "601"),
    ("684", "652", 800, "607"),
    ("632", "671", 2000, "601"),
    ("671", "684", 300, "604"),
    ("671", "680", 1000, "601"),
    ("671", "692", 0,   "switch"),
    ("684", "611", 300, "605"),
    ("692", "675", 500, "606"),
)


@dataclass(frozen=True)
class FeederModel:
    """Lightweight feeder description; full per-line Z_abc / Y_abc
    matrices land in WP3.3."""
    name: str
    buses: tuple[str, ...]
    branches: tuple[tuple[str, str, int, str], ...] = field(default_factory=tuple)
    nominal_kv: float = 4.16   # IEEE 13 line-line at 632
    n_phases: int = 3


def load_feeder(name: str) -> FeederModel:
    """Return a FeederModel for one of the IEEE benchmark feeders."""
    if name == "IEEE_13":
        return FeederModel(
            name="IEEE_13",
            buses=IEEE_13_BUSES,
            branches=IEEE_13_BRANCHES,
            nominal_kv=4.16,
        )
    elif name == "IEEE_34":
        # WP3.3 grows this; placeholder to make `load_feeder` symmetric.
        return FeederModel(
            name="IEEE_34",
            buses=tuple(f"bus_{i:02d}" for i in range(34)),
            branches=(),
            nominal_kv=24.9,
        )
    elif name == "IEEE_123":
        return FeederModel(
            name="IEEE_123",
            buses=tuple(f"bus_{i:03d}" for i in range(123)),
            branches=(),
            nominal_kv=4.16,
        )
    else:
        raise ValueError(
            f"unknown feeder name {name!r}; "
            "valid: 'IEEE_13', 'IEEE_34', 'IEEE_123'"
        )


@dataclass(frozen=True)
class WaveformBundle:
    """V/I sending-end waveforms produced by `inject_hif`.  Schema
    matches the WP1.1 single-phase bundle except V and I are now
    shape (3, n_samples) carrying the three phase channels."""
    V: np.ndarray  # shape (3, n_samples), volts
    I: np.ndarray  # shape (3, n_samples), amperes
    fs_hz: float
    f0_hz: float = 50.0
    feeder_name: str = ""
    fault_bus: str = ""
    fault_alpha: float = 0.0
    fault_Rx_ohm: float = 0.0


def inject_hif(
    feeder: FeederModel,
    bus: str,
    alpha: float,
    Rx: float,
    *,
    fault_type: str = "SLG",
    n_samples: int = 200,
    fs_hz: float = 10_000.0,
) -> WaveformBundle:
    """Synthesise a 3-phase V/I waveform bundle at the sending end for
    a fault at the given bus with per-unit position alpha and arc
    resistance Rx.

    WP3.1 SKELETON: uses the WP3.1 three-phase H_phase() model with
    the canonical 100 km line as a placeholder for the actual feeder
    branch impedance.  WP3.3 replaces this with the real per-branch
    impedance pulled from the feeder data.
    """
    if fault_type != "SLG":
        raise NotImplementedError(
            f"fault_type={fault_type!r} lands at WP3.4; SLG is WP3.1 default."
        )
    if bus not in feeder.buses:
        raise ValueError(
            f"bus {bus!r} not in feeder {feeder.name!r}; "
            f"first 5 buses: {feeder.buses[:5]}"
        )
    omega0 = 2.0 * np.pi * 50.0
    H_per_phase = H_phase(omega0, alpha, Rx, line_length_km=100.0)

    t = np.arange(n_samples) / fs_hz
    # Nominal phase-to-ground source at L-N RMS, three phases at
    # 120 deg apart, peak amplitude derived from feeder.nominal_kv.
    V_peak = feeder.nominal_kv * 1e3 * np.sqrt(2.0 / 3.0)
    phases = np.array([0.0, -2 * np.pi / 3, 2 * np.pi / 3])
    V_phase = (
        V_peak
        * np.cos(omega0 * t[None, :] + phases[:, None])
    )
    I_phase = np.zeros_like(V_phase)
    for k in range(3):
        # I = H_kk * V_k, time-domain by phasor reconstruction.
        I_phase[k] = (
            np.real(H_per_phase[k]) * V_phase[k]
            - np.imag(H_per_phase[k])
            * V_peak
            * np.sin(omega0 * t + phases[k])
        )
    return WaveformBundle(
        V=V_phase,
        I=I_phase,
        fs_hz=fs_hz,
        feeder_name=feeder.name,
        fault_bus=bus,
        fault_alpha=alpha,
        fault_Rx_ohm=Rx,
    )


__all__ = [
    "FeederModel",
    "WaveformBundle",
    "load_feeder",
    "inject_hif",
    "IEEE_13_BUSES",
    "IEEE_13_BRANCHES",
]
