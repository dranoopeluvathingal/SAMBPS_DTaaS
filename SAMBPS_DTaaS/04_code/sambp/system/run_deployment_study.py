"""
run_deployment_study.py
SAMBP TR-54/2026: Field Deployment and Commissioning Guide

Defines the pre-commissioning checklist, sensor calibration tolerances,
settings acceptance tests, and the fleet-change re-trigger protocol
for SAMBP deployment on a live IBR substation.

Studies:
  A — Pre-commissioning checklist: hardware, communication, settings
  B — Sensor calibration acceptance: CT/VT ratio and phase angle error
  C — Commissioning acceptance tests: end-to-end injection tests
  D — Fleet-change protocol: CUSUM trigger → settings update → validation
  E — Maintenance schedule: periodic re-validation intervals
"""

import math
import random
import numpy as np

random.seed(42)
np.random.seed(42)

# ── Tolerance limits (from IEC 60044, IEC 61869) ─────────────────────────
CT_RATIO_TOL  = 0.010   # pu  ±1% ratio error (Class 1P)
CT_PHASE_TOL  = 1.0     # degrees (Class 1P)
VT_RATIO_TOL  = 0.005   # pu  ±0.5% (Class 0.5)
VT_PHASE_TOL  = 0.5     # degrees (Class 0.5)
GOOSE_LAT_MAX = 4.0     # ms  maximum one-way GOOSE latency
GOOSE_JITTER  = 0.5     # ms  maximum jitter
HMAC_PASS     = True    # HMAC must authenticate before commissioning
CTI_MIN       = 0.200   # s   minimum coordination time interval

print("=" * 64)
print("SAMBP TR-54: Field Deployment and Commissioning Guide")
print("=" * 64)

# ════════════════════════════════════════════════════════════════════════
# Study A — Pre-commissioning checklist
# ════════════════════════════════════════════════════════════════════════
print("\n── Study A: Pre-Commissioning Checklist ──")

checklist = [
    # (category, item, acceptance_criterion, priority)
    ("Hardware",     "CT ratio error",               f"<{CT_RATIO_TOL*100:.1f}%",       "MANDATORY"),
    ("Hardware",     "CT phase angle error",          f"<{CT_PHASE_TOL:.1f}°",           "MANDATORY"),
    ("Hardware",     "VT ratio error",                f"<{VT_RATIO_TOL*100:.1f}%",       "MANDATORY"),
    ("Hardware",     "VT phase angle error",          f"<{VT_PHASE_TOL:.1f}°",           "MANDATORY"),
    ("Hardware",     "IED firmware version",          "≥ v4.2 (IBR-aware)",             "MANDATORY"),
    ("Hardware",     "FPGA PINN bitfile",             "SHA256 checksum verified",        "MANDATORY"),
    ("Communication","GOOSE one-way latency",         f"<{GOOSE_LAT_MAX:.1f} ms",        "MANDATORY"),
    ("Communication","GOOSE latency jitter",          f"<{GOOSE_JITTER:.1f} ms",         "MANDATORY"),
    ("Communication","HMAC key provisioned",          "Key loaded, test MAC passes",     "MANDATORY"),
    ("Communication","VLAN segmentation",             "GOOSE isolated from IT LAN",      "MANDATORY"),
    ("Communication","PMU synchronisation",           "IEEE 1588 PTP <1 µs",             "MANDATORY"),
    ("Settings",     "Ip pickup current",             "Match TR-51 table ±2%",           "MANDATORY"),
    ("Settings",     "TMS time multiplier",           "Match TR-51 table ±1%",           "MANDATORY"),
    ("Settings",     "CTI margin verification",       f"All pairs ≥{CTI_MIN:.3f} s",     "MANDATORY"),
    ("Settings",     "WAPC N-1 map loaded",           "10-bus topology file verified",   "MANDATORY"),
    ("Settings",     "PINN model weights",            "SHA256 checksum vs TR-46",        "MANDATORY"),
    ("Settings",     "CUSUM parameters",              "h=5.0, delta=0.15 (TR-48)",       "RECOMMENDED"),
    ("Settings",     "Fleet k_ibr initial estimate",  "Measured from load flow",         "RECOMMENDED"),
    ("Functional",   "Injection test: 3-phase fault", "Trip within 50 ms, correct zone", "MANDATORY"),
    ("Functional",   "Injection test: EXT fault",     "No trip, EXT flag only",          "MANDATORY"),
    ("Functional",   "Injection test: GOOSE spoof",   "HMAC reject, no false trip",      "MANDATORY"),
    ("Functional",   "N-1 security: R01 block",       "Operator advisory raised",        "MANDATORY"),
    ("Functional",   "Online learning: warm-start",   "EKF converges in <5 samples",     "RECOMMENDED"),
]

print(f"\n  {'Category':>14s}  {'Item':>36s}  {'Priority'}")
print(f"  {'-'*14}  {'-'*36}  {'-'*12}")
for cat, item, crit, pri in checklist:
    marker = "✓" if pri == "MANDATORY" else "○"
    print(f"  {cat:>14s}  {item:>36s}  {pri}")

n_mand = sum(1 for _,_,_,p in checklist if p == "MANDATORY")
n_rec  = sum(1 for _,_,_,p in checklist if p == "RECOMMENDED")
print(f"\n  Mandatory items: {n_mand}   Recommended: {n_rec}   Total: {len(checklist)}")

# ════════════════════════════════════════════════════════════════════════
# Study B — Sensor calibration acceptance
# ════════════════════════════════════════════════════════════════════════
print("\n── Study B: Sensor Calibration Acceptance (N=100 units) ──")

N_UNITS = 100
np.random.seed(42)

# Simulate CT measurement errors from manufactured units
ct_ratio_errors  = np.random.normal(0, 0.004, N_UNITS)   # pu, sigma ~ 0.4%
ct_phase_errors  = np.random.normal(0, 0.35,  N_UNITS)   # deg, sigma ~ 0.35°
vt_ratio_errors  = np.random.normal(0, 0.002, N_UNITS)   # pu
vt_phase_errors  = np.random.normal(0, 0.18,  N_UNITS)   # deg

def pass_rate(errors, tol):
    return np.mean(np.abs(errors) < tol) * 100

ct_r_pass = pass_rate(ct_ratio_errors, CT_RATIO_TOL)
ct_p_pass = pass_rate(ct_phase_errors, CT_PHASE_TOL)
vt_r_pass = pass_rate(vt_ratio_errors, VT_RATIO_TOL)
vt_p_pass = pass_rate(vt_phase_errors, VT_PHASE_TOL)

print(f"\n  {'Sensor':>8s}  {'Parameter':>12s}  {'Tolerance':>12s}  "
      f"{'Mean error':>12s}  {'σ':>8s}  {'Pass%':>8s}")
print(f"  {'-'*8}  {'-'*12}  {'-'*12}  {'-'*12}  {'-'*8}  {'-'*8}")
rows = [
    ("CT",  "Ratio",  f"±{CT_RATIO_TOL*100:.1f}%",  ct_ratio_errors,  ct_r_pass),
    ("CT",  "Phase",  f"±{CT_PHASE_TOL:.1f}°",       ct_phase_errors,  ct_p_pass),
    ("VT",  "Ratio",  f"±{VT_RATIO_TOL*100:.1f}%",  vt_ratio_errors,  vt_r_pass),
    ("VT",  "Phase",  f"±{VT_PHASE_TOL:.1f}°",       vt_phase_errors,  vt_p_pass),
]
for sensor, param, tol, errs, pct in rows:
    print(f"  {sensor:>8s}  {param:>12s}  {tol:>12s}  "
          f"{np.mean(np.abs(errs)):>12.4f}  {np.std(errs):>8.4f}  {pct:>8.1f}")

all_pass_rate = np.mean(
    (np.abs(ct_ratio_errors) < CT_RATIO_TOL) &
    (np.abs(ct_phase_errors) < CT_PHASE_TOL) &
    (np.abs(vt_ratio_errors) < VT_RATIO_TOL) &
    (np.abs(vt_phase_errors) < VT_PHASE_TOL)
) * 100
print(f"\n  All-four-pass rate (complete IED set): {all_pass_rate:.1f}%")

# ════════════════════════════════════════════════════════════════════════
# Study C — Commissioning acceptance tests
# ════════════════════════════════════════════════════════════════════════
print("\n── Study C: Commissioning Acceptance Tests ──")

# Simulate acceptance test outcomes for a new substation installation
# Each test has a base pass probability reflecting typical commissioning issues
acceptance_tests = [
    # (test_name, n_trials, base_pass_prob)
    ("3-phase fault injection (R03)",      20, 1.00),
    ("Single-line-to-ground (R07)",        20, 0.98),
    ("External fault (R09 territory)",     20, 1.00),
    ("GOOSE spoof rejection",              10, 1.00),
    ("HMAC key authentication",            10, 1.00),
    ("WAPC N-1 block on R01",             10, 1.00),
    ("CTI verification (all pairs)",       10, 0.97),
    ("PINN physics constraint C1",         15, 1.00),
    ("Fleet change protocol dry-run",      10, 0.95),
    ("GOOSE latency < 4 ms",              30, 0.99),
]

print(f"\n  {'Test':>38s}  {'Trials':>7s}  {'Pass':>6s}  {'Rate':>7s}  {'Status'}")
print(f"  {'-'*38}  {'-'*7}  {'-'*6}  {'-'*7}  {'-'*8}")
total_t = total_p = 0
for name, n, prob in acceptance_tests:
    passed = sum(random.random() < prob for _ in range(n))
    rate   = passed / n * 100
    status = "PASS" if rate >= 90 else "FAIL"
    total_t += n; total_p += passed
    print(f"  {name:>38s}  {n:>7d}  {passed:>6d}  {rate:>7.1f}%  {status}")
print(f"\n  Overall commissioning result: {total_p}/{total_t} "
      f"({total_p/total_t*100:.1f}%)")

# ════════════════════════════════════════════════════════════════════════
# Study D — Fleet-change re-trigger protocol
# ════════════════════════════════════════════════════════════════════════
print("\n── Study D: Fleet-Change Re-Trigger Protocol ──")

protocol_steps = [
    # (step, trigger, action, latency, responsible)
    (1, "Continuous",      "CUSUM monitors classification error rate",          "0 ms",    "WAPC"),
    (2, "CUSUM alarm",     "Flag fleet-change event, log timestamp",            "0 ms",    "WAPC"),
    (3, "t + 0 ms",        "Suspend setting-group auto-update",                 "0 ms",    "WAPC"),
    (4, "t + 21 min",      "Collect 50 post-alarm fault samples (field rate)",  "21 min",  "DT/EKF"),
    (5, "50 samples ready","Run settings optimisation engine (TR-51)",          "<1 ms",   "WAPC"),
    (6, "Settings ready",  "WAPC issues GOOSE MMS setting-group activation",    "<10 ms",  "WAPC→IED"),
    (7, "Settings live",   "Run 10-scenario regression test (Study C subset)",  "10 min",  "Test PC"),
    (8, "Regression pass", "Re-enable CUSUM monitoring with new baseline",      "0 ms",    "WAPC"),
    (9, "Regression fail", "Raise operator alarm, hold previous settings",      "0 ms",    "WAPC"),
]

print(f"\n  {'Step':>5s}  {'Trigger':>18s}  {'Action':>42s}  {'Latency':>8s}")
print(f"  {'-'*5}  {'-'*18}  {'-'*42}  {'-'*8}")
for step, trig, action, lat, resp in protocol_steps:
    print(f"  {step:>5d}  {trig:>18s}  {action:>42s}  {lat:>8s}")

total_protocol_min = 21 + 10   # CUSUM latency + regression
print(f"\n  Total protocol wall-clock time: ~{total_protocol_min} min")
print(f"  Automated steps: {sum(1 for s in protocol_steps if s[4]!='Test PC')}/{len(protocol_steps)}")

# ════════════════════════════════════════════════════════════════════════
# Study E — Maintenance schedule
# ════════════════════════════════════════════════════════════════════════
print("\n── Study E: Maintenance Schedule ──")

schedule = [
    # (interval, activity, duration_min, reference)
    ("Daily",      "CUSUM alarm log review",                  5,   "TR-48"),
    ("Weekly",     "GOOSE latency histogram check",          15,   "TR-52/TR-53"),
    ("Monthly",    "10-scenario regression test",            30,   "TR-53"),
    ("Quarterly",  "CT/VT ratio and phase calibration",      60,   "TR-54 Study B"),
    ("Semi-annual","HMAC key rotation",                      30,   "TR-52"),
    ("Annual",     "Full 100-scenario HIL acceptance retest",240,  "TR-53"),
    ("On CUSUM",   "Fleet-change re-trigger protocol",       31,   "TR-54 Study D"),
    ("On event",   "Post-fault DT validation run",           15,   "TR-45"),
]

print(f"\n  {'Interval':>12s}  {'Activity':>42s}  {'Duration':>10s}  {'Ref'}")
print(f"  {'-'*12}  {'-'*42}  {'-'*10}  {'-'*10}")
for interval, act, dur, ref in schedule:
    print(f"  {interval:>12s}  {act:>42s}  {dur:>8d}min  {ref}")

annual_h = sum(
    dur * {'Daily':365, 'Weekly':52, 'Monthly':12, 'Quarterly':4,
           'Semi-annual':2, 'Annual':1, 'On CUSUM':2, 'On event':10}[interval]
    for interval, _, dur, _ in schedule
) / 60
print(f"\n  Estimated total maintenance burden: {annual_h:.0f} h/year")

print("\n" + "=" * 64)
print("TR-54 deployment study complete.")
print(f"  Pre-commissioning: {n_mand} mandatory + {n_rec} recommended items")
print(f"  Sensor calibration: {all_pass_rate:.1f}% all-pass on simulated fleet")
print(f"  Commissioning acceptance: {total_p}/{total_t} "
      f"({total_p/total_t*100:.1f}%)")
print(f"  Fleet-change protocol: ~{total_protocol_min} min wall-clock")
print(f"  Annual maintenance burden: {annual_h:.0f} h")
print("=" * 64)
