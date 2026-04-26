# =============================================================================
# sambp / line_diff / run_tr62_andes.py
#
# TR-62: ANDES-validated PV 2-parameter model + 87L line differential results.
#
# Research contribution (TR-62):
#   • 2-parameter solar PV differential current model: i_diff = I_fund·sin(ωt+φ)
#   • Analytically unit condition number (κ_n = 1) → fastest possible convergence
#   • ANDES PVD1 (Type-4 solar PV, current-limited inverter) validated
#   • 87L relay with PV-aware 2-param estimator for trip/no-trip discrimination
#
# ANDES case: ieee14_pvd1 — IEEE 14-bus with PVD1 (10 inverter units, ialim=1.1 pu)
#             at Bus 4 (gen 6, connected to Bus 4).
#
# Case matrix (6 cases = 3 Rf × 2 scenarios):
#   Scenario A — External fault (Bus 3, Rf = 0.01/0.10/0.50 pu)
#                → 87L must NOT trip (security test)
#   Scenario B — Internal fault (synthesised, Rf = 0.01/0.10/0.50 pu)
#                → 87L MUST trip (dependability test)
#                → 2-param PV estimator fit to i_diff
#
# Protected line: Bus 4 (PV terminal) → Bus 5 (network)
#                 Line_7: r=0.01335, x=0.04211, b=0 pu
# PVD1 current limit: k_ibr = 1.1 pu (ialim parameter)
#
# 87L geometry (same as TR-56):
#   External: i_R_abc = -i_L_abc  (exact through-current cancellation)
#   Internal: i_R synthesised from Thevenin at Bus 5 (Z_TH = 0.015+j0.10 pu)
#
# Outputs
# -------
#   outputs/tr62/tr62_results.csv
#   outputs/tr62/tr62_summary.txt
#   outputs/tr62/plots/tr62_<case>.png
#
# Usage
# -----
#   cd 04_code/sambp/line_diff
#   /root/dr_e_venv/bin/python3 run_tr62_andes.py
# =============================================================================

from __future__ import annotations

import os
import sys
import csv
import numpy as np

# ── Path setup ─────────────────────────────────────────────────────────────
_line_diff_dir = os.path.dirname(os.path.abspath(__file__))
_sambp_dir     = os.path.join(_line_diff_dir, "..")
_code_dir      = os.path.join(_line_diff_dir, "..", "..")
sys.path.insert(0, _code_dir)
sys.path.insert(0, _sambp_dir)
sys.path.insert(0, _line_diff_dir)

# ── SAMBP 87L imports ───────────────────────────────────────────────────────
from models.line_diff_baseline import (
    LineDiffRelayConfig, run_87L_relay, trip_boundary,
)
from models.line_pv_model import (
    forward_idiff_pv, I_FUND_THRESH_PV_DEFAULT,
)
from inverse_estimation.line_pv_estimator import estimate_pv_zone_parameters

# ── ANDES adapter ───────────────────────────────────────────────────────────
import importlib.util as _ilu
_adapter_path = os.path.join(_sambp_dir, "io_utils", "andes_adapter.py")
_spec = _ilu.spec_from_file_location("andes_adapter", _adapter_path)
_adapter = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_adapter)
run_andes_tds              = _adapter.run_andes_tds
extract_dfig_87L_waveforms = _adapter.extract_dfig_87L_waveforms  # generic 87L extractor

# ---------------------------------------------------------------------------
# ANDES case configuration
# ---------------------------------------------------------------------------
ANDES_CASE   = "/root/phd_thesis/05_data/test_cases/andes/ieee14_pvd1.json"
LINE_BUS1    = 4      # PV terminal (local relay end)
LINE_BUS2    = 5      # network terminal (remote relay end)
FAULT_TIME   = 1.0    # fault inception [s]
CLEAR_TIME   = 1.15   # fault clearing [s]
TF_ANDES     = 1.6    # TDS end time [s]
FS           = 10000.0
F0           = 50.0

# ANDES fault bus — Bus 3 is adjacent to Bus 4 but NOT on protected line 4→5
# Used for both external and internal scenarios; relay geometry applied at relay level.
FAULT_BUS    = 3

# Thevenin impedance at Bus 5 looking into the network (excl. PV side)
# Bus 5 connects to Bus 1 (slack) via Line_2 and to Bus 2 via Line_5.
# Approximate parallel combination: Z_TH ≈ 0.015+j0.10 pu
Z_TH_REMOTE  = complex(0.015, 0.10)

# PVD1 current limit (k_ibr = ialim) — from ieee14_pvd1.json
K_IBR_PU     = 1.1   # pu

# 87L relay configuration
RELAY_CFG = LineDiffRelayConfig(
    I_op_min_pu          = 0.15,   # minimum operate threshold [pu]
    SLP1                 = 0.30,
    SLP2                 = 0.60,
    I_rst_k_pu           = 1.5,
    use_charging_comp    = False,  # Line_7 has b=0
    freq_nom_hz          = F0,
    sample_rate_hz       = FS,
    channel_delay_samples = 0,
    CT_ratio_L           = 1.0,
    CT_ratio_R           = 1.0,
    I_rated_pu           = 1.0,
)

# PV estimator settings
I_FUND_THRESH = I_FUND_THRESH_PV_DEFAULT   # 0.058 pu
KAPPA_MAX     = 30.0

# Fault resistance sweep
RF_VALUES = [0.01, 0.10, 0.50]

# ---------------------------------------------------------------------------
# Case matrix
# ---------------------------------------------------------------------------
TR62_CASES = []
for rf in RF_VALUES:
    TR62_CASES.append({
        "case_name":  f"tr62_ext_R{int(rf*100):03d}",
        "scenario":   "external",
        "fault_R_pu": rf,
        "expected":   "no_trip",
    })
for rf in RF_VALUES:
    TR62_CASES.append({
        "case_name":  f"tr62_int_R{int(rf*100):03d}",
        "scenario":   "internal",
        "fault_R_pu": rf,
        "expected":   "trip",
    })

# ---------------------------------------------------------------------------
# Output setup
# ---------------------------------------------------------------------------
OUT_DIR     = os.path.join("outputs", "tr62")
PLOT_DIR    = os.path.join(OUT_DIR, "plots")
RESULTS_CSV = os.path.join(OUT_DIR, "tr62_results.csv")
SUMMARY_TXT = os.path.join(OUT_DIR, "tr62_summary.txt")
os.makedirs(PLOT_DIR, exist_ok=True)

CSV_FIELDS = [
    "case_name", "scenario", "fault_R_pu", "source",
    "expected_outcome", "actual_trip",
    "correct_decision", "trip_time_ms",
    "I_L_peak_pu", "i_diff_peak_pu", "i_rst_peak_pu",
    "lm_success", "lm_cost",
    "I_fund_hat", "phi_fund_hat", "kappa_n",
    "k_ibr_pu", "V_pre_bus1", "V_pre_bus2",
]


# ===========================================================================
# Single-case runner
# ===========================================================================

def run_tr62_case(case: dict, andes_result) -> dict:
    case_name  = case["case_name"]
    scenario   = case["scenario"]
    fault_R    = case["fault_R_pu"]
    expected   = case["expected"]

    print(f"\n{'='*60}")
    print(f"  {case_name}  |  {scenario.upper()}  |  Rf={fault_R} pu")
    print(f"  Expected: {expected}  |  k_ibr={K_IBR_PU} pu")
    print(f"{'='*60}")

    # ── Extract 87L waveforms from ANDES ─────────────────────────────────
    # extract_dfig_87L_waveforms is generic — works for any line topology.
    waves = extract_dfig_87L_waveforms(
        andes_result,
        line_bus1          = LINE_BUS1,
        line_bus2          = LINE_BUS2,
        fs                 = FS,
        f0                 = F0,
        window             = (FAULT_TIME - 0.05, CLEAR_TIME + 0.40),
        z_thevenin_remote  = Z_TH_REMOTE,
    )

    t    = waves["t"]
    ia_L = waves["ia_L"]
    ib_L = waves["ib_L"]
    ic_L = waves["ic_L"]

    I_L_cplx = waves["I_L_cplx"]
    I_L_peak = float(np.abs(I_L_cplx).max())
    i_L_abc  = np.vstack([ia_L, ib_L, ic_L])

    # ── Build remote-end 3-phase current ─────────────────────────────────
    # Same carrier strategy as TR-56:
    #   External: i_R = -i_L  (exact cancellation, no carrier mismatch)
    #   Internal: Thevenin synthesised using Hilbert phase of ia_L

    if scenario == "external":
        i_R_abc     = -i_L_abc.copy()
        ia_diff     = np.zeros(len(t))
        i_diff_mag  = np.zeros(len(t))
        i_rst       = np.abs(ia_L)
        i_diff_peak = 0.0

    else:  # internal
        I_R_int_cplx  = waves["I_R_int_cplx"]      # constant complex phasor
        I_R_int_scalar = float(abs(I_R_int_cplx[0]))
        angle_IR_int   = float(np.angle(I_R_int_cplx[0]))

        # Mean angle of I_L during fault window (to compute d_phi)
        fault_m = (t >= FAULT_TIME) & (t <= CLEAR_TIME)
        angle_IL_mean = float(np.angle(
            I_L_cplx[fault_m]).mean()) if fault_m.any() else 0.0
        d_phi = angle_IR_int - angle_IL_mean

        # Build ia_R using instantaneous phase of ia_L (Hilbert) + d_phi
        from scipy.signal import hilbert
        ia_L_phase = np.unwrap(np.angle(hilbert(ia_L)))

        sqrt2 = np.sqrt(2.0)
        ia_R = I_R_int_scalar * sqrt2 * np.cos(ia_L_phase + d_phi)
        ib_R = I_R_int_scalar * sqrt2 * np.cos(ia_L_phase + d_phi - 2.0*np.pi/3.0)
        ic_R = I_R_int_scalar * sqrt2 * np.cos(ia_L_phase + d_phi + 2.0*np.pi/3.0)

        i_R_abc    = np.vstack([ia_R, ib_R, ic_R])
        ia_diff    = ia_L + ia_R
        i_diff_mag = np.abs(ia_diff)
        i_rst      = 0.5 * (np.abs(ia_L) + np.abs(ia_R))
        i_diff_peak = float(i_diff_mag.max())

    i_rst_peak = float(i_rst.max())
    print(f"  I_L peak: {I_L_peak:.4f} pu  |  i_diff peak: {i_diff_peak:.4f} pu")

    # ── 87L relay ─────────────────────────────────────────────────────────
    relay   = run_87L_relay(t, i_L_abc, i_R_abc, cfg=RELAY_CFG)
    tripped = relay.t_trip_s is not None
    trip_ms = relay.t_trip_s * 1e3 if tripped else None
    correct = (expected == "trip") == tripped
    print(f"  87L trip: {tripped}  t_trip: {trip_ms}  Correct: {correct}")

    # ── 2-parameter PV estimator (internal fault only) ────────────────────
    lm_success  = None
    lm_cost     = None
    I_fund_hat  = None
    phi_fund_hat = None
    kappa_n_hat = None
    pv_state    = None

    if scenario == "internal":
        fault_mask = (t >= FAULT_TIME) & (t <= CLEAR_TIME + 0.10)
        t_w        = t[fault_mask]
        i_diff_w   = ia_diff[fault_mask]

        if len(t_w) > 20:
            # Relative time vector (LM fits within window)
            t_rel = t_w - t_w[0]
            try:
                est = estimate_pv_zone_parameters(
                    t_rel, i_diff_w,
                    freq_hz       = F0,
                    kappa_max     = KAPPA_MAX,
                    I_fund_thresh = I_FUND_THRESH,
                )
                lm_success   = est["success"]
                lm_cost      = float(np.sum(
                    (forward_idiff_pv(t_rel, est["theta_hat"], F0) - i_diff_w)**2
                ))
                I_fund_hat   = float(est["theta_hat"][0])
                phi_fund_hat = float(est["theta_hat"][1])
                kappa_n_hat  = est["kappa_n"]
                pv_state     = est["state"]
                print(f"  PV LM: success={lm_success}  I_fund={I_fund_hat:.4f} pu"
                      f"  φ={phi_fund_hat:.3f} rad  κ_n={kappa_n_hat:.2f}"
                      f"  is_internal={pv_state.is_internal}")
            except Exception as exc:
                print(f"  PV estimator error: {exc}")

    # ── Plots ─────────────────────────────────────────────────────────────
    _save_tr62_plots(case, t, ia_L, ib_L, ic_L, ia_diff, i_diff_mag, i_rst,
                     relay, waves, scenario,
                     I_fund_hat=I_fund_hat, phi_fund_hat=phi_fund_hat)

    return {
        "case_name":       case_name,
        "scenario":        scenario,
        "fault_R_pu":      fault_R,
        "source":          "andes",
        "expected_outcome": expected,
        "actual_trip":     tripped,
        "correct_decision": correct,
        "trip_time_ms":    trip_ms,
        "I_L_peak_pu":     I_L_peak,
        "i_diff_peak_pu":  i_diff_peak,
        "i_rst_peak_pu":   i_rst_peak,
        "lm_success":      lm_success,
        "lm_cost":         lm_cost,
        "I_fund_hat":      I_fund_hat,
        "phi_fund_hat":    phi_fund_hat,
        "kappa_n":         kappa_n_hat,
        "k_ibr_pu":        K_IBR_PU,
        "V_pre_bus1":      waves["V_pre_bus1"],
        "V_pre_bus2":      waves["V_pre_bus2"],
    }


# ===========================================================================
# Plot helper
# ===========================================================================

def _save_tr62_plots(case, t, ia_L, ib_L, ic_L, ia_diff, i_diff_mag, i_rst,
                     relay, waves, scenario,
                     I_fund_hat=None, phi_fund_hat=None):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return

    ds        = max(1, int(FS / 1000))   # downsample to ~1 kHz for plots
    case_name = case["case_name"]
    fault_R   = case["fault_R_pu"]

    fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=False)
    fig.suptitle(
        f"TR-62 PV+87L  |  {case_name}  |  {scenario.upper()} fault  |  Rf={fault_R} pu\n"
        f"ANDES ieee14_pvd1  |  PVD1 at Bus 4  |  Protected line Bus 4→5  |  "
        f"k_ibr={K_IBR_PU} pu  |  V_pre_bus1={waves['V_pre_bus1']:.4f} pu",
        fontsize=9, fontweight="bold"
    )

    t_ms = t * 1e3

    # Panel 1: Three-phase PV terminal currents
    ax = axes[0]
    ax.plot(t_ms[::ds], ia_L[::ds], "b-",  lw=0.8, alpha=0.8, label="ia_L (PV)")
    ax.plot(t_ms[::ds], ib_L[::ds], "g-",  lw=0.8, alpha=0.5, label="ib_L")
    ax.plot(t_ms[::ds], ic_L[::ds], "r-",  lw=0.8, alpha=0.5, label="ic_L")
    ax.axvspan(FAULT_TIME*1e3, CLEAR_TIME*1e3, color="red", alpha=0.10, label="Fault")
    ax.set_ylabel("Current (pu)")
    ax.set_title("PV Terminal Current (Local End, Bus 4)")
    ax.legend(fontsize=7, ncol=4)
    ax.grid(True, alpha=0.3)
    ax.set_xlabel("Time (ms)")

    # Panel 2: Differential current + 2-param PV fit
    ax = axes[1]
    ax.plot(t_ms[::ds], i_diff_mag[::ds], "navy", lw=1.2, label="|I_diff| (operate)")
    ax.plot(t_ms[::ds], i_rst[::ds], "steelblue", lw=0.8, ls="--",
            alpha=0.8, label="I_rst (restraint)")
    ax.axhline(RELAY_CFG.I_op_min_pu, color="red", ls=":", lw=1.0,
               label=f"I_op_min={RELAY_CFG.I_op_min_pu:.2f} pu")
    ax.axhline(I_FUND_THRESH, color="purple", ls=":", lw=0.8,
               label=f"PV thresh={I_FUND_THRESH:.3f} pu")

    # Overlay 2-param PV fit on i_diff if available
    if I_fund_hat is not None and phi_fund_hat is not None:
        fault_mask = (t >= FAULT_TIME) & (t <= CLEAR_TIME + 0.10)
        t_fit = t[fault_mask]
        t_rel = t_fit - t_fit[0]
        i_fit = forward_idiff_pv(t_rel, np.array([I_fund_hat, phi_fund_hat]), F0)
        ax.plot(t_fit[::ds]*1e3, np.abs(i_fit[::ds]), "orange", lw=1.5, ls="--",
                label=f"PV LM fit (I_fund={I_fund_hat:.3f} pu)")

    if relay.t_trip_s:
        ax.axvline(relay.t_trip_s*1e3, color="darkorange", ls="-.", lw=2.0,
                   label=f"TRIP at {relay.t_trip_s*1e3:.0f} ms")
    ax.axvspan(FAULT_TIME*1e3, CLEAR_TIME*1e3, color="red", alpha=0.06)
    ax.set_ylabel("Current (pu)")
    ax.set_title("87L Relay: Operate vs Restraint  "
                 f"({'TRIP' if relay.t_trip_s else 'NO TRIP'})")
    ax.legend(fontsize=7)
    ax.grid(True, alpha=0.3)
    ax.set_xlabel("Time (ms)")

    # Panel 3: I_op vs I_rst scatter (relay characteristic)
    ax = axes[2]
    I_rst_line, I_op_line = trip_boundary(RELAY_CFG, I_rst_max=max(i_rst.max()*1.2, 2.0))
    ax.plot(I_rst_line, I_op_line, "k-", lw=1.5, label="Trip boundary")
    sc_mask = (t >= FAULT_TIME - 0.02) & (t <= CLEAR_TIME + 0.10)
    ax.scatter(i_rst[sc_mask][::ds], i_diff_mag[sc_mask][::ds],
               c="blue", s=2, alpha=0.4, label="Fault window")
    pre_mask = t < FAULT_TIME
    ax.scatter(i_rst[pre_mask][::ds], i_diff_mag[pre_mask][::ds],
               c="green", s=2, alpha=0.3, label="Pre-fault")
    ax.set_xlabel("I_rst (pu)")
    ax.set_ylabel("I_op (pu)")
    ax.set_title("87L Operate–Restraint Characteristic")
    ax.legend(fontsize=7)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    out = os.path.join(PLOT_DIR, f"{case_name}.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Plot → {out}")


# ===========================================================================
# Batch runner
# ===========================================================================

def run_tr62_batch():
    print(f"\n{'#'*60}")
    print(f"  TR-62: ANDES PVD1 + 87L  ({len(TR62_CASES)} cases)")
    print(f"  ANDES case : {ANDES_CASE}")
    print(f"  Protected line: Bus {LINE_BUS1} (PV) → Bus {LINE_BUS2} (network)")
    print(f"  PVD1 k_ibr = {K_IBR_PU} pu  |  Fault bus: {FAULT_BUS}")
    print(f"  Rf values: {RF_VALUES} pu")
    print(f"{'#'*60}")

    # Cache ANDES results by fault_R_pu (one TDS run per unique Rf).
    # Scenario geometry (external/internal) is applied at relay level.
    _cache: dict = {}
    results = []
    failed  = []

    for case in TR62_CASES:
        key = round(case["fault_R_pu"], 6)
        if key not in _cache:
            print(f"\nRunning ANDES TDS: fault_bus={FAULT_BUS}  "
                  f"fault_rf={case['fault_R_pu']} pu ...")
            ar = run_andes_tds(
                ANDES_CASE,
                fault_bus         = FAULT_BUS,
                fault_time        = FAULT_TIME,
                clear_time        = CLEAR_TIME,
                tf                = TF_ANDES,
                fault_xf          = 0.001,
                fault_rf          = case["fault_R_pu"],
                disable_togglers  = True,   # disable Toggler in ieee14_pvd1.json
            )
            conv = ar.ss.PFlow.converged
            print(f"  PFlow converged: {conv}  TDS steps: {len(ar.t)}")
            _cache[key] = ar
        else:
            print(f"\n  [cached] Rf={case['fault_R_pu']} (scenario={case['scenario']})")

        try:
            row = run_tr62_case(case, _cache[key])
            results.append(row)
        except Exception as exc:
            import traceback
            print(f"  ERROR in {case['case_name']}: {exc}")
            traceback.print_exc()
            failed.append(case["case_name"])

    # Write CSV
    with open(RESULTS_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in results:
            writer.writerow({
                k: (f"{row[k]:.6g}" if isinstance(row[k], float) else row[k])
                for k in CSV_FIELDS
            })
    print(f"\nResults CSV → {RESULTS_CSV}")

    _write_summary(results, failed)
    return results


def _write_summary(results, failed):
    correct = sum(1 for r in results if r["correct_decision"])
    ext_r   = [r for r in results if r["scenario"] == "external"]
    int_r   = [r for r in results if r["scenario"] == "internal"]

    lines = []
    lines.append("=" * 72)
    lines.append("TR-62: PV 2-param + ANDES-validated 87L — Batch Summary")
    lines.append(f"Cases: {len(results)}  |  Failed: {len(failed)}  |  "
                 f"Correct decisions: {correct}/{len(results)}")
    lines.append("=" * 72)
    lines.append(f"{'Case':<28} {'Scen':>6} {'Rf':>5} {'Expected':>10} "
                 f"{'Trip?':>6} {'OK':>4} {'t_trip':>8} {'I_diff':>8} {'I_fund':>7}")
    lines.append("-" * 72)

    for r in results:
        tt   = f"{r['trip_time_ms']:.0f}ms" if r["trip_time_ms"] else "  --   "
        idp  = f"{r['i_diff_peak_pu']:.3f}" if r["i_diff_peak_pu"] else "  -- "
        ifh  = f"{r['I_fund_hat']:.3f}"     if r["I_fund_hat"]     else "  -- "
        ok   = "✓" if r["correct_decision"] else "✗"
        lines.append(
            f"{r['case_name']:<28} {r['scenario']:>6} {r['fault_R_pu']:>5.2f} "
            f"{r['expected_outcome']:>10} {str(r['actual_trip']):>6} {ok:>4} "
            f"{tt:>8} {idp:>8} {ifh:>7}"
        )

    lines.append("=" * 72)
    lines.append(f"External (security)     : "
                 f"{sum(1 for r in ext_r if not r['actual_trip'])}/{len(ext_r)} no-trip")
    lines.append(f"Internal (dependability): "
                 f"{sum(1 for r in int_r if r['actual_trip'])}/{len(int_r)} tripped")

    pv_r = [r for r in int_r if r["I_fund_hat"] is not None]
    if pv_r:
        lines.append(f"PV I_fund range : "
                     f"{min(r['I_fund_hat'] for r in pv_r):.3f} – "
                     f"{max(r['I_fund_hat'] for r in pv_r):.3f} pu")
        kn_r = [r for r in pv_r if r["kappa_n"] is not None]
        if kn_r:
            lines.append(f"κ_n range       : "
                         f"{min(r['kappa_n'] for r in kn_r):.2f} – "
                         f"{max(r['kappa_n'] for r in kn_r):.2f}  (target ≈ 1.0)")
    lines.append(f"PVD1 k_ibr      : {K_IBR_PU} pu")
    lines.append("=" * 72)

    summary = "\n".join(lines)
    print(f"\n{summary}")
    with open(SUMMARY_TXT, "w") as f:
        f.write(summary + "\n")
    print(f"Summary → {SUMMARY_TXT}")


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    run_tr62_batch()
