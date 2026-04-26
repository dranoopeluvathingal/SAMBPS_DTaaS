"""
run_tr65_opendss.py
====================
TR-65 — OpenDSS Distribution Bus 87B Integration Test

Wires the SAMBP 87B bus-differential relay pipeline to an OpenDSS
distribution network model.  OpenDSS (opendssdirect 0.9.4) provides
physically computed AC fault current phasors for a 4-feeder 11 kV
distribution bus.  Phasors are converted to time-domain waveforms (with
DC offset) and passed through:

    conventional 87B relay  →  zone estimator  →  confidence gate

Network topology (11 kV, 10 MVA base):
    Vsource (infinite bus) ── Z_src ── MainBus ─┬─ F1 (1 km) ── BusF1 ── Load1 (2 MVA)
                                                 ├─ F2 (2 km) ── BusF2 ── Load2 (1 MVA)
                                                 └─ F3 (1.5km) ── BusF3 ── Load3 (0.8 MVA)
                                                                              ± DG (0.5 MVA)

Six test cases:
    tr65_normal_load     : power flow only — security (I_op ≈ 0)
    tr65_ext_F1          : 3ph fault at BusF1 (external) — security
    tr65_ext_F2_ctsat    : 3ph fault at BusF2, CT saturation on F2 — Stage-2 veto
    tr65_int_bus_AG      : A-G fault at MainBus — dependability (differential trip)
    tr65_int_bus_3ph     : 3ph fault at MainBus — dependability (high-set trip)
    tr65_ext_F2_DG       : 3ph fault at BusF2 with DG on F3 (reverse infeed) — security

Outputs:
    outputs/tr65/tr65_results.csv
    outputs/tr65/tr65_summary.txt
"""

from __future__ import annotations

import sys, os, csv
import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

import opendssdirect as dss

from models.bus_diff_baseline import (
    BusDiffRelayConfig, run_87B_relay,
)
from models.bus_reduced_zone_model import (
    condition_number_normalised, interpret_theta,
)
from inverse_estimation.bus_inverse_estimator import estimate_bus_zone_parameters
from adaptation.bus_confidence_gate import (
    BusGateConfig, BusGateState, evaluate_87B_confidence_gate,
)

# ---------------------------------------------------------------------------
# System constants
# ---------------------------------------------------------------------------

SBASE_MVA   = 10.0
VN_KV       = 11.0
FREQ_HZ     = 50.0
FS_HZ       = 1000.0         # waveform sample rate

I_BASE_A    = SBASE_MVA * 1e6 / (np.sqrt(3) * VN_KV * 1e3)   # 524.9 A
I_BUS_RATED = I_BASE_A       # rated current = system base current

# Source Thevenin impedance seen from MainBus
# Z_src (circuit) = 0.0726 + j1.21 Ω  (Z_base = 12.1 Ω, R/X ≈ 0.060)
# Small Zsrc line negligible → Z_th_main = 0.0726 + j1.21
X_SRC = 1.21    # Ω
R_SRC = 0.0726  # Ω
XR_MAIN   = X_SRC / R_SRC                              # 16.67
TAU_MAIN  = XR_MAIN / (2 * np.pi * FREQ_HZ)            # ≈ 53.1 ms

# Feeder line impedances (Ω total, not per km)
Z_F1 = complex(0.121, 0.182)    # 1 km
Z_F2 = complex(0.242, 0.364)    # 2 km
Z_F3 = complex(0.182, 0.273)    # 1.5 km
Z_SRC = complex(R_SRC, X_SRC)

# X/R at feeder fault buses (for DC time constant)
def _tau_at(Z_feeder: complex) -> float:
    Z_tot = Z_SRC + Z_feeder
    return (Z_tot.imag / Z_tot.real) / (2 * np.pi * FREQ_HZ)

TAU_F1 = _tau_at(Z_F1)   # ≈ 22.8 ms
TAU_F2 = _tau_at(Z_F2)   # ≈ 15.9 ms

# DC offset coefficient
K_DC = 0.8  # worst-case point-on-wave

# Relay and gate configuration
RELAY_CFG = BusDiffRelayConfig(
    n_feeders      = 4,
    freq_nom_hz    = FREQ_HZ,
    sample_rate_hz = FS_HZ,
    I_op_min_pu    = 0.20,
    SLP1           = 0.25,
    SLP2           = 0.50,
    I_rst_k_pu     = 1.0,
    I_op_hs_pu     = 8.0,
    CT_ratios      = (200, 200, 200, 200),
    I_bus_rated_A  = I_BUS_RATED,
)

GATE_CFG = BusGateConfig(
    kappa_thresh      = 30.0,
    residual_thresh   = 0.15,
    f_int_trip_thresh = 0.60,
    n_confirm         = 2,
    model_veto_enable = True,
)

# CT saturation knee current (for external_F2_ctsat scenario).
# Set dynamically at 0.60 × fault peak (same fraction as bus_event_library)
# to ensure definite but partial saturation, producing recognisable waveform
# distortion (flat-top) for the zone estimator's ε_CT parameter.
CT_KNEE_FRACTION = 0.60   # × I_fault_peak

# Output directory
OUT_DIR = os.path.join(_HERE, "outputs", "tr65")
os.makedirs(OUT_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# OpenDSS network builder
# ---------------------------------------------------------------------------

def _cmd(s: str) -> None:
    dss.Command(s)


def build_network(with_dg: bool = False) -> None:
    """
    Build the 4-feeder 11 kV distribution bus in OpenDSS.
    The source impedance is specified via z1/z0 on the circuit vsource.
    """
    _cmd("Clear")
    _cmd("Set DefaultBaseFrequency=50")
    _cmd("New Circuit.dist_bus_tr65 basekv=11 pu=1.05 frequency=50")
    # Source Thevenin impedance: Z1 = R+jX in ohms
    _cmd(f"~ z1=[{R_SRC}, {X_SRC}] z0=[{3*R_SRC:.4f}, {3*X_SRC:.4f}]")

    # Feeder F1 — 1 km, industrial load
    _cmd("New Line.F1 Bus1=sourcebus Bus2=BusF1 Phases=3 "
         "R1=0.121 X1=0.182 R0=0.363 X0=0.545 C1=0 C0=0 Length=1 Units=km")

    # Feeder F2 — 2 km, commercial load
    _cmd("New Line.F2 Bus1=sourcebus Bus2=BusF2 Phases=3 "
         "R1=0.121 X1=0.182 R0=0.363 X0=0.545 C1=0 C0=0 Length=2 Units=km")

    # Feeder F3 — 1.5 km, residential + optional DG
    _cmd("New Line.F3 Bus1=sourcebus Bus2=BusF3 Phases=3 "
         "R1=0.121 X1=0.182 R0=0.363 X0=0.545 C1=0 C0=0 Length=1.5 Units=km")

    # Loads
    _cmd("New Load.Ld1 Bus1=BusF1 Phases=3 kV=11 kW=2000 kvar=600 model=1")
    _cmd("New Load.Ld2 Bus1=BusF2 Phases=3 kV=11 kW=1000 kvar=300 model=1")
    _cmd("New Load.Ld3 Bus1=BusF3 Phases=3 kV=11 kW=800  kvar=200 model=1")

    # Optional DG on F3 (500 kW solar PV, unity power factor)
    if with_dg:
        _cmd("New Generator.DG3 Bus1=BusF3 Phases=3 kV=11 kW=500 pf=1.0 "
             "model=1 Vminpu=0.5 Vmaxpu=1.5")

    _cmd("Set VoltageBases=[11]")
    _cmd("CalcVoltageBases")


def solve_power_flow() -> bool:
    _cmd("Solve mode=snapshot")
    return bool(dss.Solution.Converged())


def add_fault(bus: str, phases: int = 3, R_ohm: float = 0.001) -> None:
    if phases == 3:
        _cmd(f"New Fault.BF Bus1={bus} Phases=3 R={R_ohm}")
    else:
        # Single-phase A-G fault on phase A
        _cmd(f"New Fault.BF Bus1={bus}.1.0 Phases=1 R={R_ohm}")


def remove_faults() -> None:
    _cmd("Fault.BF.Enabled=No")


# ---------------------------------------------------------------------------
# Current phasor extraction
# ---------------------------------------------------------------------------

def _get_phasors(element: str, from_end: bool = True) -> np.ndarray:
    """
    Return 3-phase complex current phasors at from_end (True) or to_end.
    Convention: positive = current flowing INTO the element from that end.
    """
    dss.Circuit.SetActiveElement(element)
    c = list(dss.CktElement.Currents())
    off = 0 if from_end else 6
    return np.array([
        complex(c[off + 0], c[off + 1]),
        complex(c[off + 2], c[off + 3]),
        complex(c[off + 4], c[off + 5]),
    ])


def get_bus_feeder_phasors() -> list[np.ndarray]:
    """
    Return the four feeder current phasors at sourcebus (protected bus).
    Sign convention: positive = current flowing INTO sourcebus.

    OpenDSS Vsource uses load convention: CktElement.Currents() from_end
    gives current flowing FROM sourcebus INTO the vsource terminal (i.e.,
    absorbed, not delivered). Negating gives the current INTO the bus:
        i_src = −I_vsource_from_end

    Load feeder lines (Bus1=sourcebus, Bus2=feeder_bus):
    from_end gives current leaving sourcebus. Negating gives INTO-bus:
        i_Fk = −I_Fk_from_end

    With this convention:
        External fault at BusF1: i_src + i_F1 + i_F2 + i_F3 ≈ 0  (KCL)
        Internal bus fault:       sum = I_fault  (differential current)
    """
    I_vs = _get_phasors("Vsource.source", from_end=True)
    I_F1 = _get_phasors("Line.F1", from_end=True)
    I_F2 = _get_phasors("Line.F2", from_end=True)
    I_F3 = _get_phasors("Line.F3", from_end=True)

    # Negate ALL: both vsource (load convention) and feeders (out→into)
    return [-I_vs, -I_F1, -I_F2, -I_F3]


# ---------------------------------------------------------------------------
# Phasor → time-domain waveform synthesis
# ---------------------------------------------------------------------------

def phasor_to_waveform(
    phasor_3ph: np.ndarray,   # (3,) complex phasors [A], INTO-bus convention
    time_s:     np.ndarray,
    fault_time_s: float = 0.02,
    k_dc: float = K_DC,
    tau_dc: float = TAU_MAIN,
) -> np.ndarray:
    """
    Convert 3-phase complex phasors (INTO-bus convention) to time-domain
    waveforms with physically correct DC offset sign.

    i_ph(t) = I_pk × sin(ωt + θ)  −  I_pk × sin(θ) × k_dc × exp(−Δt/τ)

    The DC term uses −sin(θ) × k_dc so that:
      • A positive phasor (current into bus) has DC with sign = −sin(θ)
      • A negative phasor (current out of bus) has DC with opposite sign
      → DC offsets cancel for source + fault-feeder pairs (external faults)
      → DC offsets add for internal bus faults (all INTO bus)

    θ = angle(phasor) + π/2 converts OpenDSS cosine reference to sine.
    """
    omega  = 2 * np.pi * FREQ_HZ
    mask   = time_s >= fault_time_s
    dt     = time_s - fault_time_s
    w      = np.zeros((3, len(time_s)))

    for ph in range(3):
        if abs(phasor_3ph[ph]) < 1e-6:
            continue
        I_pk  = np.sqrt(2) * abs(phasor_3ph[ph])
        theta = np.angle(phasor_3ph[ph]) + np.pi / 2   # cos→sin reference
        dc_coeff = -np.sin(theta) * k_dc               # sign follows phasor direction
        w[ph, mask] = I_pk * (
            np.sin(omega * dt[mask] + theta)
            + dc_coeff * np.exp(-dt[mask] / tau_dc)
        )
    return w


def _ct_saturate(i_abc: np.ndarray, I_knee: float,
                 sat_ratio: float = 0.15) -> np.ndarray:
    """Soft CT saturation above knee current (matches bus_event_library)."""
    out = np.copy(i_abc)
    for ph in range(3):
        x = i_abc[ph]
        above = np.abs(x) > I_knee
        out[ph] = np.where(
            above,
            I_knee * np.sign(x) + (x - I_knee * np.sign(x)) * sat_ratio,
            x,
        )
    return out


# ---------------------------------------------------------------------------
# Single case runner
# ---------------------------------------------------------------------------

def run_tr65_case(
    case_name:    str,
    scenario:     str,        # "external" | "internal" | "normal"
    fault_bus:    str | None,
    fault_phases: int = 3,
    with_dg:      bool = False,
    apply_ct_sat_on: int | None = None,  # feeder index 1-3 (0-indexed in list)
    tau_dc:       float = TAU_MAIN,
    expected_trip: bool | None = None,
) -> dict:
    """
    Build network, apply fault, solve, extract waveforms, run 87B pipeline.
    """
    # Build and solve
    build_network(with_dg=with_dg)

    if fault_bus is not None:
        add_fault(fault_bus, phases=fault_phases)

    converged = solve_power_flow()

    # Extract feeder phasors
    feeders_phasor = get_bus_feeder_phasors()  # [I_src, I_F1, I_F2, I_F3]

    # Synthesize time-domain waveforms
    t           = np.arange(0, 0.15, 1.0 / FS_HZ)
    fault_time  = 0.02

    # For power flow only (no fault): no DC offset
    k_dc_use = K_DC if fault_bus is not None else 0.0

    i_feeders = []
    for k, ph_phasor in enumerate(feeders_phasor):
        w = phasor_to_waveform(ph_phasor, t, fault_time_s=fault_time,
                               k_dc=k_dc_use, tau_dc=tau_dc)
        i_feeders.append(w)

    # Apply CT saturation on one feeder if requested.
    # Knee at 60 % of the fault-current peak: creates partial saturation
    # (flat-top waveform) detectable by the zone estimator's ε_CT parameter.
    if apply_ct_sat_on is not None:
        idx = apply_ct_sat_on
        I_feeder_pk = float(np.max(np.abs(i_feeders[idx])))
        I_knee_dyn  = CT_KNEE_FRACTION * I_feeder_pk if I_feeder_pk > 1.0 else I_BUS_RATED
        i_feeders[idx] = _ct_saturate(i_feeders[idx], I_knee_dyn, sat_ratio=0.15)

    # --- Conventional 87B relay ---
    decision = run_87B_relay(t, i_feeders, cfg=RELAY_CFG)
    conv_trip = decision.t_trip_s is not None

    # --- Zone estimator (on differential current, post-fault window) ---
    t_fault_idx = np.searchsorted(t, fault_time)

    # Compute per-phase differential current
    i_diff_3ph = np.sum([f for f in i_feeders], axis=0)   # (3, T)

    # Use phase A differential (worst case / dominant)
    t_window  = t[t_fault_idx:]
    t_rel     = t_window - t_window[0]
    i_diff_a  = i_diff_3ph[0, t_fault_idx:]

    lm_success  = False
    kappa_n     = float('nan')
    I_diff_hat  = float('nan')
    phi_hat     = float('nan')
    eps_CT_hat  = float('nan')
    f_int       = float('nan')
    gate_action = "not_evaluated"
    final_trip  = conv_trip   # default: pass conventional through

    # Normalize full-window phase-A differential to pu for estimator
    i_diff_full_pu = i_diff_3ph[0, :] / I_BUS_RATED

    if np.max(np.abs(i_diff_full_pu)) > 1e-4:
        est = estimate_bus_zone_parameters(
            t, i_diff_full_pu,
            freq_hz=FREQ_HZ,
        )
        lm_success = est.get("converged", False)
        kappa_n    = float(est["kappa_n"])
        zone_state = est["state"]       # BusZoneModelState
        theta_hat  = est["theta_hat"]

        I_diff_hat = float(theta_hat[0])
        phi_hat    = float(theta_hat[1])
        eps_CT_hat = float(theta_hat[2])
        f_int      = float(zone_state.f_int)

        # --- Confidence gate ---
        gate_dec, _ = evaluate_87B_confidence_gate(
            zone_state        = zone_state,
            conventional_trip = conv_trip,
            gate_cfg          = GATE_CFG,
            gate_state        = BusGateState(),
        )
        gate_action = gate_dec.source   # "model"|"model_veto"|"conventional"|"no_trip"
        final_trip  = gate_dec.final_trip

    # Trip time
    trip_time_ms = None
    if final_trip and decision.t_trip_s is not None:
        trip_time_ms = (decision.t_trip_s - fault_time) * 1000

    # Expected outcome
    if expected_trip is None:
        expected_trip = (scenario == "internal")
    correct = (final_trip == expected_trip)

    # Peak I_op, I_rst from decision
    I_op_peak  = float(np.max(decision.I_op))
    I_rst_peak = float(np.max(decision.I_rst))

    # Source feeder magnitude (pu)
    I_src_pk_pu = float(np.sqrt(2) * np.max(np.abs(feeders_phasor[0])) / I_BUS_RATED)

    return dict(
        case_name      = case_name,
        scenario       = scenario,
        fault_bus      = fault_bus or "none",
        fault_phases   = fault_phases,
        with_dg        = int(with_dg),
        ct_sat_feeder  = apply_ct_sat_on if apply_ct_sat_on is not None else -1,
        source         = "opendss",
        expected_trip  = int(expected_trip),
        conv_trip      = int(conv_trip),
        final_trip     = int(final_trip),
        correct        = int(correct),
        trip_type      = decision.trip_type or "none",
        trip_time_ms   = round(trip_time_ms, 1) if trip_time_ms is not None else "",
        I_src_pk_pu    = round(I_src_pk_pu, 4),
        I_op_peak_pu   = round(I_op_peak, 4),
        I_rst_peak_pu  = round(I_rst_peak, 4),
        lm_success     = int(lm_success),
        kappa_n        = round(kappa_n, 2) if not np.isnan(kappa_n) else "",
        I_diff_hat_pu  = round(I_diff_hat / I_BUS_RATED, 4) if not np.isnan(I_diff_hat) else "",
        phi_hat        = round(phi_hat, 4) if not np.isnan(phi_hat) else "",
        eps_CT_hat     = round(eps_CT_hat, 4) if not np.isnan(eps_CT_hat) else "",
        f_int          = round(f_int, 4) if not np.isnan(f_int) else "",
        gate_action    = gate_action,
        tau_dc_ms      = round(tau_dc * 1000, 1),
    )


# ---------------------------------------------------------------------------
# Test case catalogue
# ---------------------------------------------------------------------------

CASES = [
    dict(
        case_name    = "tr65_normal_load",
        scenario     = "normal",
        fault_bus    = None,
        fault_phases = 0,
        with_dg      = False,
        apply_ct_sat_on = None,
        tau_dc       = TAU_MAIN,
        expected_trip= False,
    ),
    dict(
        case_name    = "tr65_ext_F1",
        scenario     = "external",
        fault_bus    = "BusF1",
        fault_phases = 3,
        with_dg      = False,
        apply_ct_sat_on = None,
        tau_dc       = TAU_F1,
        expected_trip= False,
    ),
    dict(
        case_name    = "tr65_ext_F2_ctsat",
        scenario     = "external",
        fault_bus    = "BusF2",
        fault_phases = 3,
        with_dg      = False,
        apply_ct_sat_on = 2,      # CT saturation on F2 feeder (index 2 in list)
        tau_dc       = TAU_F2,
        expected_trip= False,     # SAMBP veto should suppress mal-trip
    ),
    dict(
        case_name    = "tr65_int_bus_AG",
        scenario     = "internal",
        fault_bus    = "sourcebus",
        fault_phases = 1,
        with_dg      = False,
        apply_ct_sat_on = None,
        tau_dc       = TAU_MAIN,
        expected_trip= True,
    ),
    dict(
        case_name    = "tr65_int_bus_3ph",
        scenario     = "internal",
        fault_bus    = "sourcebus",
        fault_phases = 3,
        with_dg      = False,
        apply_ct_sat_on = None,
        tau_dc       = TAU_MAIN,
        expected_trip= True,
    ),
    dict(
        case_name    = "tr65_ext_F2_DG",
        scenario     = "external",
        fault_bus    = "BusF2",
        fault_phases = 3,
        with_dg      = True,     # DG on F3 — reverse infeed
        apply_ct_sat_on = None,
        tau_dc       = TAU_F2,
        expected_trip= False,
    ),
]

CSV_FIELDS = [
    "case_name", "scenario", "fault_bus", "fault_phases", "with_dg",
    "ct_sat_feeder", "source", "expected_trip", "conv_trip", "final_trip",
    "correct", "trip_type", "trip_time_ms", "I_src_pk_pu", "I_op_peak_pu",
    "I_rst_peak_pu", "lm_success", "kappa_n", "I_diff_hat_pu", "phi_hat",
    "eps_CT_hat", "f_int", "gate_action", "tau_dc_ms",
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 72)
    print("SAMBP TR-65 — OpenDSS Distribution Bus 87B Integration Test")
    print(f"Network: 11 kV, {SBASE_MVA:.0f} MVA base, I_rated = {I_BUS_RATED:.1f} A")
    print(f"Relay:   I_op_min={RELAY_CFG.I_op_min_pu:.2f} SLP1={RELAY_CFG.SLP1:.2f} "
          f"SLP2={RELAY_CFG.SLP2:.2f} HS={RELAY_CFG.I_op_hs_pu:.1f} pu")
    print("=" * 72)

    results = []
    csv_path = os.path.join(OUT_DIR, "tr65_results.csv")

    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()

        for case in CASES:
            name = case["case_name"]
            print(f"  Running {name}...", end=" ", flush=True)
            r = run_tr65_case(**case)
            writer.writerow({k: r.get(k, "") for k in CSV_FIELDS})
            results.append(r)
            ok = "PASS" if r["correct"] else "FAIL"
            trip_str = (f"TRIP@{r['trip_time_ms']}ms ({r['trip_type']})"
                        if r["final_trip"] else "NO_TRIP")
            gate_str = r["gate_action"]
            kn_str   = f"kn={r['kappa_n']}" if r["kappa_n"] != "" else ""
            fi_str   = f"f_int={r['f_int']}" if r["f_int"] != "" else ""
            print(f"{ok:4}  {trip_str:28}  {gate_str:14}  {kn_str}  {fi_str}")

    # Summary
    n_correct = sum(r["correct"] for r in results)
    n_total   = len(results)
    print(f"\nResults: {n_correct}/{n_total} correct")
    print(f"CSV: {csv_path}")

    # Write summary text
    summary_path = os.path.join(OUT_DIR, "tr65_summary.txt")
    with open(summary_path, "w") as f:
        f.write("=" * 72 + "\n")
        f.write("SAMBP TR-65 — OpenDSS Distribution Bus 87B Integration Test\n")
        f.write(f"Network: 11 kV, {SBASE_MVA:.0f} MVA base, I_rated = {I_BUS_RATED:.1f} A\n")
        f.write(f"I_src [pu] at fault conditions:\n")
        for r in results:
            f.write(f"  {r['case_name']:<30}: I_src={r['I_src_pk_pu']:.3f} pu  "
                    f"I_op={r['I_op_peak_pu']:.4f} pu  gate={r['gate_action']}\n")
        f.write(f"\nOverall: {n_correct}/{n_total} correct\n")
        f.write("=" * 72 + "\n")

    print(f"Summary: {summary_path}")
    print("=" * 72)
