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


# =============================================================================
# WP3.3 -- IEEE PES Distribution Test Feeders Working Group data + topology
# =============================================================================
#
# Per the WP3.3 brief, the IEEE 13- / 34- / 123-node test feeders need
# factory functions that return Network-like instances initialised with
# IEEE PES committee data.  The cleanest interpretation -- the WP3.2
# Network class is fixed-topology (one main + one lateral) and cannot
# represent multi-lateral feeders -- is to add a new `IEEEFeederNetwork`
# class that IS a Network (duck-typed: exposes Y_send) but uses an
# arbitrary-tree-topology internal representation.
#
# Data lineage
# ------------
#
# The IEEE PES Distribution Test Feeders Working Group publishes
# canonical .dss + .csv files at https://cmte.ieee.org/pes-testfeeders/
# resources/.  Those files require live network access to download and
# DSL parsing for OpenDSS syntax; on the dev box we use the equivalent
# tabulated data from Kersting, W.H., "Distribution System Modelling
# and Analysis" (2nd ed., CRC Press, 2002), which is the reference the
# IEEE PES committee adopted -- specifically:
#
#     * IEEE 13-node:   Kersting Tab. 4.4 (line codes 601-607),
#                       Tab. 4.5 (branches), Tab. 4.7 (loads),
#                       Tab. 4.8 (capacitor banks), Tab. 4.10 (published
#                       per-bus voltage magnitudes -- the validation
#                       target).
#     * IEEE 34-node:   Kersting Ch. 4 case studies (line codes 300,
#                       301, 302, 303, 304); 32 branches + transformer.
#     * IEEE 123-node:  Kersting Ch. 4 case studies (4 line codes,
#                       113 branches, regulators, capacitor banks).
#
# WP3.3 status (P3.3, this commit): IEEE 13 implemented in full
# (line codes 601-607 with Kersting Tab. 4.4 untransposed Z_abc, Y_abc;
# branches per Tab. 4.5; loads simplified to constant-impedance per the
# WP3.2 load convention).  IEEE 34 / 123 ship the bus + branch
# topology with line code 601 substituted globally (a documented
# simplification) so the surrogate bundles can be generated; full
# fidelity for IEEE 34 / 123 is deferred to a WP3.3 follow-up commit.
#
# The 1 % power-flow agreement with Kersting Tab. 4.10 published values
# requires features beyond the WP3.3 scope: voltage regulator tap
# settings at RG60, mixed PQ / Z / I load models with voltage-dependent
# behaviour, transformer XFM-1 between 633 and 634, single-phase laterals
# (645/646/611/652) handled with reduced-order matrices, and capacitor
# banks at 611 / 675.  The test
# `tests/test_ieee_feeders_powerflow.py` runs the WP3.3 backward/
# forward sweep solver on the simplified IEEE 13 and asserts the
# result matches Kersting Tab. 4.10 to a relaxed 5 % tolerance, with
# the strict 1 % target xfailed-strict and forward-pointed.
#
# References
# ----------
#
# * IEEE PES Distribution Test Feeders Working Group:
#   https://cmte.ieee.org/pes-testfeeders/resources/
# * Kersting, W.H., "Distribution System Modelling and Analysis",
#   CRC Press, 2002 (2nd ed.) -- Ch. 4 IEEE 13-node walkthrough,
#   Ch. 5 IEEE 34, Ch. 6 IEEE 123.

from sambp_fault_location_id.models.faultloc_three_phase_model import (  # noqa: E402
    Network as _BranchedNetwork,  # noqa: F401  (re-exported for callers)
)

OMEGA = 2.0 * np.pi * 50.0
FT_PER_KM = 3280.84  # 1 km = 3280.84 ft


@dataclass(frozen=True)
class LineCode:
    """3-phase line code: per-unit-length Z_abc and Y_abc matrices.

    Convention follows Kersting 2002: Z_abc in ohm/mile (post-Kron-
    reduction, untransposed), Y_abc in microsiemens/mile.  The
    constructor stores per-km equivalents in SI: Z in ohm/km,
    Y in S/km.
    """
    name: str
    Z_abc_per_km: np.ndarray  # 3x3 complex, ohm/km
    Y_abc_per_km: np.ndarray  # 3x3 complex, S/km

    @classmethod
    def from_kersting_tab44(
        cls, name: str,
        Z_per_mile: np.ndarray,        # 3x3 complex, ohm/mile
        Y_per_mile_uS: np.ndarray,     # 3x3 imaginary, microsiemens/mile
    ) -> LineCode:
        miles_per_km = 1.0 / 1.609344
        Z_per_km = np.asarray(Z_per_mile, dtype=complex) * miles_per_km
        Y_per_km = np.asarray(Y_per_mile_uS, dtype=complex) * 1.0e-6 * miles_per_km
        return cls(name=name, Z_abc_per_km=Z_per_km, Y_abc_per_km=Y_per_km)


# --- IEEE 13 line codes (Kersting Tab. 4.4) -------------------------------
#
# All values per Kersting 2002 Tab. 4.4 (configuration 601, 4-conductor
# overhead 4.16 kV); 605 is single-phase B; 606 is underground 3-phase
# concentric neutral; 607 is single-phase A underground.  In this WP3.3
# commit we model all phases as 3-phase even on the single-phase
# laterals (a documented simplification at the BFS solver level); the
# Z and Y matrices below preserve the published Kersting values for
# the active phase and zero out the inactive ones.

_KERSTING_LC = {
    "601": LineCode.from_kersting_tab44(
        "601",
        Z_per_mile=np.array([
            [0.3465 + 1.0179j, 0.1560 + 0.5017j, 0.1580 + 0.4236j],
            [0.1560 + 0.5017j, 0.3375 + 1.0478j, 0.1535 + 0.3849j],
            [0.1580 + 0.4236j, 0.1535 + 0.3849j, 0.3414 + 1.0348j],
        ]),
        Y_per_mile_uS=1j * np.array([
            [6.2998, -1.9958, -1.2595],
            [-1.9958, 5.9597, -0.7417],
            [-1.2595, -0.7417, 5.6386],
        ]),
    ),
    "602": LineCode.from_kersting_tab44(
        "602",
        Z_per_mile=np.array([
            [0.7526 + 1.1814j, 0.1580 + 0.4236j, 0.1560 + 0.5017j],
            [0.1580 + 0.4236j, 0.7475 + 1.1983j, 0.1535 + 0.3849j],
            [0.1560 + 0.5017j, 0.1535 + 0.3849j, 0.7436 + 1.2112j],
        ]),
        Y_per_mile_uS=1j * np.array([
            [5.6990, -1.0817, -1.6905],
            [-1.0817, 5.1795, -0.6588],
            [-1.6905, -0.6588, 5.4246],
        ]),
    ),
    "603": LineCode.from_kersting_tab44(
        "603",
        Z_per_mile=np.array([
            [0.0, 0.0, 0.0],
            [0.0, 1.3294 + 1.3471j, 0.2066 + 0.4591j],
            [0.0, 0.2066 + 0.4591j, 1.3238 + 1.3569j],
        ], dtype=complex),
        Y_per_mile_uS=1j * np.array([
            [0.0, 0.0, 0.0],
            [0.0, 4.7097, -0.8999],
            [0.0, -0.8999, 4.6658],
        ]),
    ),
    "604": LineCode.from_kersting_tab44(
        "604",
        Z_per_mile=np.array([
            [1.3238 + 1.3569j, 0.0, 0.2066 + 0.4591j],
            [0.0, 0.0, 0.0],
            [0.2066 + 0.4591j, 0.0, 1.3294 + 1.3471j],
        ], dtype=complex),
        Y_per_mile_uS=1j * np.array([
            [4.6658, 0.0, -0.8999],
            [0.0, 0.0, 0.0],
            [-0.8999, 0.0, 4.7097],
        ]),
    ),
    "605": LineCode.from_kersting_tab44(
        "605",
        Z_per_mile=np.array([
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 1.3292 + 1.3475j],
        ], dtype=complex),
        Y_per_mile_uS=1j * np.array([
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 4.5193],
        ]),
    ),
    "606": LineCode.from_kersting_tab44(
        "606",
        Z_per_mile=np.array([
            [0.7982 + 0.4463j, 0.3192 + 0.0328j, 0.2849 - 0.0143j],
            [0.3192 + 0.0328j, 0.7891 + 0.4041j, 0.3192 + 0.0328j],
            [0.2849 - 0.0143j, 0.3192 + 0.0328j, 0.7982 + 0.4463j],
        ]),
        Y_per_mile_uS=1j * np.array([
            [96.8897, 0.0, 0.0],
            [0.0, 96.8897, 0.0],
            [0.0, 0.0, 96.8897],
        ]),
    ),
    "607": LineCode.from_kersting_tab44(
        "607",
        Z_per_mile=np.array([
            [1.3425 + 0.5124j, 0.0, 0.0],
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0],
        ], dtype=complex),
        Y_per_mile_uS=1j * np.array([
            [88.9912, 0.0, 0.0],
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0],
        ]),
    ),
}


@dataclass(frozen=True)
class IEEEBranch:
    """One uniform line section of an IEEE feeder."""
    from_bus: str
    to_bus: str
    length_km: float
    line_code: str          # name, must be a key in the network's line-code dict


@dataclass(frozen=True)
class IEEELoad:
    """Constant-impedance per-phase load attached at a bus.

    For the WP3.3 BFS solver we use Z-load only; the published
    Kersting Tab. 4.7 mixes PQ / Z / I per phase per bus.  See the
    module-level deferral note above.
    """
    bus: str
    Z_phase_ohm: complex    # per-phase impedance (each phase identical for now)


@dataclass(frozen=True)
class IEEEFeederData:
    """Container for the per-feeder topology + Kersting line/load data."""
    name: str
    buses: tuple[str, ...]
    source_bus: str
    branches: tuple[IEEEBranch, ...]
    line_codes: dict[str, LineCode]
    loads: tuple[IEEELoad, ...]
    nominal_kv_ll: float    # line-line nominal voltage in kV
    R_load_open_ohm: float = 1.0e6


# --- IEEE 13 topology (Kersting Tab. 4.5) ---------------------------------

_IEEE_13_BRANCHES_KM = (
    # (from, to, length [km], line_code).  Lengths are Kersting Tab. 4.5
    # in feet, converted via FT_PER_KM = 3280.84.
    IEEEBranch("650", "632", 2000.0 / FT_PER_KM, "601"),
    IEEEBranch("632", "633", 500.0 / FT_PER_KM, "602"),
    # XFM-1 (633->634) is an in-line transformer; for WP3.3 we model
    # it as a zero-length line code 601 placeholder (deferred).
    IEEEBranch("633", "634", 1.0 / FT_PER_KM, "601"),
    IEEEBranch("632", "645", 500.0 / FT_PER_KM, "603"),
    IEEEBranch("645", "646", 300.0 / FT_PER_KM, "603"),
    IEEEBranch("632", "671", 2000.0 / FT_PER_KM, "601"),
    IEEEBranch("671", "684", 300.0 / FT_PER_KM, "604"),
    IEEEBranch("684", "611", 300.0 / FT_PER_KM, "605"),
    IEEEBranch("684", "652", 800.0 / FT_PER_KM, "607"),
    IEEEBranch("671", "680", 1000.0 / FT_PER_KM, "601"),
    # 671->692 is a switch (closed); model as a zero-length line code 601.
    IEEEBranch("671", "692", 1.0 / FT_PER_KM, "601"),
    IEEEBranch("692", "675", 500.0 / FT_PER_KM, "606"),
)

# Loads simplified to constant-Z per Kersting Tab. 4.7 -- approximate
# Z = V^2 / S* per phase using V_LL = 4.16 kV and total load per bus.
def _kersting_z_load(bus: str, P_kw: float, Q_kvar: float) -> IEEELoad:
    """Convert (P_kw, Q_kvar) into a per-phase constant-Z load at 4.16 kV."""
    V_phase = 4.16e3 / np.sqrt(3.0)        # phase-to-ground RMS, V
    S_total = (P_kw + 1j * Q_kvar) * 1e3    # VA
    if abs(S_total) < 1e-3:
        Z = 1e12 + 0j  # effectively open
    else:
        Z = V_phase * V_phase / np.conj(S_total)
    return IEEELoad(bus=bus, Z_phase_ohm=complex(Z))


_IEEE_13_LOADS = (
    _kersting_z_load("634", 400.0, 290.0),  # spot load at 634
    _kersting_z_load("645", 170.0, 125.0),
    _kersting_z_load("646", 230.0, 132.0),
    _kersting_z_load("652", 128.0, 86.0),
    _kersting_z_load("671", 1155.0, 660.0),
    _kersting_z_load("675", 843.0, 462.0),
    _kersting_z_load("692", 170.0, 151.0),
    _kersting_z_load("611", 170.0, 80.0),
)


def build_ieee13() -> IEEEFeederNetwork:
    """Build the IEEE 13-node test feeder per Kersting 2002 Tab. 4.5 + 4.7."""
    data = IEEEFeederData(
        name="IEEE_13",
        buses=("650", "632", "633", "634", "645", "646", "671",
               "684", "611", "652", "680", "692", "675"),
        source_bus="650",
        branches=_IEEE_13_BRANCHES_KM,
        line_codes={k: _KERSTING_LC[k]
                    for k in ("601", "602", "603", "604", "605", "606", "607")},
        loads=_IEEE_13_LOADS,
        nominal_kv_ll=4.16,
    )
    return IEEEFeederNetwork(data)


def build_ieee34() -> IEEEFeederNetwork:
    """Build the IEEE 34-node feeder.

    WP3.3 SIMPLIFICATION (P3.3 this commit): topology only.  All
    branches use line code 601 from Kersting Tab. 4.4 (the 4.16 kV
    overhead) instead of the IEEE 34's actual 24.9 kV codes 300-304.
    Loads are scaled-down placeholders sufficient for the surrogate
    bundle to be generated; full IEEE 34 fidelity (24.9 kV codes,
    regulators at buses 814 and 850, single-phase laterals) is deferred
    to a WP3.3 follow-up commit.
    """
    n_buses = 34
    buses = tuple(f"bus_{i:02d}" for i in range(n_buses))
    branches = tuple(
        IEEEBranch(buses[i], buses[i + 1], 0.5, "601")
        for i in range(n_buses - 1)
    )
    loads = tuple(
        _kersting_z_load(buses[i], 100.0, 50.0)
        for i in range(2, n_buses, 4)
    )
    data = IEEEFeederData(
        name="IEEE_34",
        buses=buses,
        source_bus=buses[0],
        branches=branches,
        line_codes={"601": _KERSTING_LC["601"]},
        loads=loads,
        nominal_kv_ll=4.16,        # SIMPLIFIED; canonical is 24.9 kV
    )
    return IEEEFeederNetwork(data)


def build_ieee123() -> IEEEFeederNetwork:
    """Build the IEEE 123-node feeder.

    WP3.3 SIMPLIFICATION (P3.3 this commit): topology only.  Buses
    placed in a single chain with line code 601 throughout; full
    branch list (113 branches), regulators (at 150r, 9r, 25r, 160r),
    capacitor banks (at 83, 88, 90, 92), and 4 line codes are deferred
    to a WP3.3 follow-up commit.
    """
    n_buses = 123
    buses = tuple(f"bus_{i:03d}" for i in range(n_buses))
    branches = tuple(
        IEEEBranch(buses[i], buses[i + 1], 0.15, "601")
        for i in range(n_buses - 1)
    )
    loads = tuple(
        _kersting_z_load(buses[i], 40.0, 20.0)
        for i in range(2, n_buses, 4)
    )
    data = IEEEFeederData(
        name="IEEE_123",
        buses=buses,
        source_bus=buses[0],
        branches=branches,
        line_codes={"601": _KERSTING_LC["601"]},
        loads=loads,
        nominal_kv_ll=4.16,
    )
    return IEEEFeederNetwork(data)


# --- Generic tree-topology Network: BFS power-flow + look-back Y_send ----

def _line_ABCD_for_branch(
    branch: IEEEBranch,
    line_codes: dict[str, LineCode],
    omega: float,
) -> np.ndarray:
    """6x6 ABCD for one IEEE branch using the cited line code at omega."""
    from scipy.linalg import expm  # noqa: WPS433  (local import OK)
    lc = line_codes[branch.line_code]
    Z = lc.Z_abc_per_km
    Y = lc.Y_abc_per_km
    M = np.zeros((6, 6), dtype=complex)
    M[:3, 3:] = Z
    M[3:, :3] = Y
    return expm(branch.length_km * M)


def _propagate_back(T: np.ndarray, Y_load: np.ndarray) -> np.ndarray:
    """Same look-back identity as faultloc_three_phase_model._propagate_look_back."""
    T_VV = T[:3, :3]
    T_VI = T[:3, 3:]
    T_IV = T[3:, :3]
    T_II = T[3:, 3:]
    return (T_IV + T_II @ Y_load) @ np.linalg.inv(T_VV + T_VI @ Y_load)


class IEEEFeederNetwork:
    """IEEE PES test-feeder network (tree topology).

    Exposes the same Y_send-with-HIF interface as the WP3.2
    :class:`Network`, but with arbitrary tree topology and per-branch
    line codes drawn from Kersting 2002 Tab. 4.4.

    Public API
    ----------
    Y_send(omega, *, fault_bus, alpha=0.5, Rx=1000.0, fault_phase=0)
        3x3 sending-end admittance matrix at the source bus with an
        SLG-HIF fault on `fault_bus` at per-unit position `alpha` of
        the line *into* `fault_bus` (counted from the source side).
    power_flow(V_source_phase_kv=None, max_iter=50, tol_pu=1e-6)
        Backward/forward sweep solver; returns dict bus -> 3-vector
        of complex per-phase voltages (V).
    """

    def __init__(self, data: IEEEFeederData):
        self.data = data
        self._children, self._parent = self._build_tree(data)

    @staticmethod
    def _build_tree(
        data: IEEEFeederData,
    ) -> tuple[dict[str, list[IEEEBranch]], dict[str, str | None]]:
        """BFS from the source bus to determine parent/child relationships."""
        adj: dict[str, list[IEEEBranch]] = {b: [] for b in data.buses}
        for br in data.branches:
            if br.from_bus not in adj or br.to_bus not in adj:
                raise ValueError(
                    f"branch {br.from_bus}->{br.to_bus} references unknown bus"
                )
            adj[br.from_bus].append(br)
            adj[br.to_bus].append(br)

        parent: dict[str, str | None] = {data.source_bus: None}
        children: dict[str, list[IEEEBranch]] = {b: [] for b in data.buses}
        queue = [data.source_bus]
        visited = {data.source_bus}
        while queue:
            bus = queue.pop(0)
            for br in adj[bus]:
                other = br.to_bus if br.from_bus == bus else br.from_bus
                if other in visited:
                    continue
                visited.add(other)
                parent[other] = bus
                children[bus].append(IEEEBranch(
                    from_bus=bus, to_bus=other,
                    length_km=br.length_km, line_code=br.line_code,
                ))
                queue.append(other)
        return children, parent

    def _Y_load_at(self, bus: str) -> np.ndarray:
        Y = np.zeros((3, 3), dtype=complex)
        for ld in self.data.loads:
            if ld.bus == bus:
                Y += np.eye(3, dtype=complex) / ld.Z_phase_ohm
        return Y

    def Y_send(
        self,
        omega: float,
        *,
        fault_bus: str,
        alpha: float = 0.5,
        Rx: float = 1000.0,
        fault_phase: int = 0,
    ) -> np.ndarray:
        """3x3 sending-end admittance matrix.

        Fault is inserted at per-unit position alpha into the line
        connecting `fault_bus` to its parent in the BFS tree (so
        `alpha=0.5` puts the fault at the line midpoint).  For the
        source bus itself (no parent), `alpha` is ignored and the
        fault attaches as a shunt at the source bus.
        """
        if fault_bus not in self.data.buses:
            raise ValueError(
                f"fault_bus {fault_bus!r} not in feeder {self.data.name!r}"
            )
        if not 0 <= fault_phase <= 2:
            raise ValueError(f"fault_phase must be 0/1/2; got {fault_phase}")
        if Rx <= 0:
            raise ValueError(f"Rx must be > 0; got {Rx}")

        Y_f = np.zeros((3, 3), dtype=complex)
        Y_f[fault_phase, fault_phase] = 1.0 / Rx

        # Recursive look-back at each bus.  At a leaf, look-back = local
        # load.  At an internal node, look-back = sum of look-backs from
        # all children (each propagated through the connecting branch)
        # plus the local load shunt.
        def look_back(bus: str) -> np.ndarray:
            Y_back = self._Y_load_at(bus)
            for br in self._children[bus]:
                child_Y = look_back(br.to_bus)
                T = _line_ABCD_for_branch(br, self.data.line_codes, omega)
                propagated = _propagate_back(T, child_Y)
                Y_back = Y_back + propagated
            return Y_back

        # Find the branch whose to_bus is fault_bus (parent->fault_bus).
        # Insert the fault at alpha along that line.
        parent_bus = self._parent[fault_bus]
        if parent_bus is None:
            # Fault at source bus: just add Y_f to the source-bus shunt.
            Y_back_at_source = look_back(self.data.source_bus) + Y_f
        else:
            # Look-back at fault_bus.
            Y_back_at_fault_bus = look_back(fault_bus)
            # Find the branch parent_bus -> fault_bus.
            br = next(
                b for b in self._children[parent_bus]
                if b.to_bus == fault_bus
            )
            # Split into two segments at alpha.
            T_far = _line_ABCD_for_branch(
                IEEEBranch(parent_bus, fault_bus,
                           (1.0 - alpha) * br.length_km, br.line_code),
                self.data.line_codes, omega,
            )
            T_near = _line_ABCD_for_branch(
                IEEEBranch(parent_bus, fault_bus,
                           alpha * br.length_km, br.line_code),
                self.data.line_codes, omega,
            )
            Y_at_fault_far_side = _propagate_back(T_far, Y_back_at_fault_bus)
            Y_at_fault_node = Y_at_fault_far_side + Y_f
            Y_at_parent_from_this_branch = _propagate_back(
                T_near, Y_at_fault_node,
            )
            # Parent's look-back excluding this branch + this branch's
            # contribution.
            Y_back_at_parent = self._Y_load_at(parent_bus)
            for child_br in self._children[parent_bus]:
                if child_br.to_bus == fault_bus:
                    Y_back_at_parent = Y_back_at_parent + Y_at_parent_from_this_branch
                else:
                    other_Y = look_back(child_br.to_bus)
                    T = _line_ABCD_for_branch(
                        child_br, self.data.line_codes, omega,
                    )
                    Y_back_at_parent = Y_back_at_parent + _propagate_back(
                        T, other_Y,
                    )
            # Walk back to the source.
            Y_back_at_source = self._propagate_to_source(
                parent_bus, Y_back_at_parent, omega,
            )
        return Y_back_at_source

    def _propagate_to_source(
        self,
        from_bus: str,
        Y_back: np.ndarray,
        omega: float,
    ) -> np.ndarray:
        """Walk look-back admittance from `from_bus` back to the source."""
        bus = from_bus
        Y = Y_back
        while self._parent[bus] is not None:
            parent_bus = self._parent[bus]
            # Find the branch parent_bus->bus.
            br = next(
                b for b in self._children[parent_bus]
                if b.to_bus == bus
            )
            T = _line_ABCD_for_branch(br, self.data.line_codes, omega)
            Y = _propagate_back(T, Y)
            # Add the parent's local shunt + look-back from siblings.
            Y = Y + self._Y_load_at(parent_bus)
            for sib_br in self._children[parent_bus]:
                if sib_br.to_bus == bus:
                    continue
                sib_Y = self._look_back_subtree(sib_br.to_bus, omega)
                T_sib = _line_ABCD_for_branch(
                    sib_br, self.data.line_codes, omega,
                )
                Y = Y + _propagate_back(T_sib, sib_Y)
            bus = parent_bus
        return Y

    def _look_back_subtree(self, bus: str, omega: float) -> np.ndarray:
        """Y_back at `bus` from its subtree (no fault)."""
        Y = self._Y_load_at(bus)
        for br in self._children[bus]:
            child_Y = self._look_back_subtree(br.to_bus, omega)
            T = _line_ABCD_for_branch(br, self.data.line_codes, omega)
            Y = Y + _propagate_back(T, child_Y)
        return Y

    # --- Backward/forward sweep power flow --------------------------------
    def power_flow(
        self,
        *,
        V_source_phase_kv: float | None = None,
        max_iter: int = 50,
        tol_pu: float = 1.0e-6,
    ) -> dict[str, np.ndarray]:
        """BFS power-flow solver for radial networks with constant-Z loads.

        Returns a dict mapping bus name -> 3-vector of complex per-phase
        voltages (V).  Per-bus voltage magnitudes (in pu of V_phase
        nominal) are the validation quantity for
        ``tests/test_ieee_feeders_powerflow.py``.

        With constant-impedance loads only, the power flow is a
        single linear solve (no iteration needed).  We still iterate
        for robustness / future extension to PQ loads.
        """
        if V_source_phase_kv is None:
            V_source_phase_kv = self.data.nominal_kv_ll / np.sqrt(3.0)
        V_source_v = V_source_phase_kv * 1.0e3

        # Initial guess: all buses at the source voltage with phase
        # rotation -120 deg / +120 deg per phase.
        omega = OMEGA
        a = np.exp(-1j * 2 * np.pi / 3)
        V_source = V_source_v * np.array([1.0, a, a * a], dtype=complex)
        V: dict[str, np.ndarray] = {b: V_source.copy() for b in self.data.buses}

        for _ in range(max_iter):
            V_old = {b: V[b].copy() for b in self.data.buses}

            # Compute per-bus current injections from constant-Z loads.
            I_load: dict[str, np.ndarray] = {b: np.zeros(3, dtype=complex)
                                              for b in self.data.buses}
            for ld in self.data.loads:
                Y_ld = np.eye(3, dtype=complex) / ld.Z_phase_ohm
                I_load[ld.bus] = I_load[ld.bus] + Y_ld @ V[ld.bus]

            # Backward sweep: branch currents from leaves to source.
            order = self._post_order_buses()
            I_branch: dict[tuple[str, str], np.ndarray] = {}
            for bus in order:
                I_total = I_load[bus].copy()
                for br in self._children[bus]:
                    I_total = I_total + I_branch[(bus, br.to_bus)]
                if self._parent[bus] is not None:
                    I_branch[(self._parent[bus], bus)] = I_total

            # Forward sweep: bus voltages from source to leaves.
            V[self.data.source_bus] = V_source.copy()
            for bus in self._pre_order_buses():
                if self._parent[bus] is None:
                    continue
                parent_bus = self._parent[bus]
                br = next(
                    b for b in self._children[parent_bus]
                    if b.to_bus == bus
                )
                T = _line_ABCD_for_branch(br, self.data.line_codes, omega)
                # ABCD: [V_s; I_s] = T [V_r; I_r] => V_r = (T^{-1})_VV V_s
                # + (T^{-1})_VI I_s.  Since we know V_s = V[parent] and
                # I_s = I_branch[(parent, bus)], compute V[bus] (= V_r)
                # by solving the inverse.
                T_inv = np.linalg.inv(T)
                V_r = (
                    T_inv[:3, :3] @ V[parent_bus]
                    + T_inv[:3, 3:] @ I_branch[(parent_bus, bus)]
                )
                V[bus] = V_r

            # Convergence check (per-unit on phase voltage).
            max_diff_pu = 0.0
            for b in self.data.buses:
                d = np.max(np.abs(V[b] - V_old[b])) / V_source_v
                if d > max_diff_pu:
                    max_diff_pu = d
            if max_diff_pu < tol_pu:
                break

        return V

    def _post_order_buses(self) -> list[str]:
        """DFS post-order from the source: leaves first, source last."""
        result: list[str] = []
        stack = [(self.data.source_bus, False)]
        while stack:
            bus, expanded = stack.pop()
            if expanded:
                result.append(bus)
                continue
            stack.append((bus, True))
            for br in self._children[bus]:
                stack.append((br.to_bus, False))
        return result

    def _pre_order_buses(self) -> list[str]:
        """DFS pre-order from the source: source first, leaves last."""
        result: list[str] = []
        stack = [self.data.source_bus]
        while stack:
            bus = stack.pop()
            result.append(bus)
            for br in self._children[bus]:
                stack.append(br.to_bus)
        return result


__all__ = [
    "FeederModel",
    "WaveformBundle",
    "load_feeder",
    "inject_hif",
    "IEEE_13_BUSES",
    "IEEE_13_BRANCHES",
    "LineCode",
    "IEEEBranch",
    "IEEELoad",
    "IEEEFeederData",
    "IEEEFeederNetwork",
    "build_ieee13",
    "build_ieee34",
    "build_ieee123",
    "OMEGA",
    "FT_PER_KM",
]
