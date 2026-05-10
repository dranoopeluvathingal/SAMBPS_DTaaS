"""
run_dt_validation_study.py
SAMBP TR-45/2026: Digital Twin Validation and Protection System Integration

Validates the DT (TR-43 + TR-44) against the full SAMBP protection scheme
(TR-35 + TR-37) using a combined Monte Carlo approach.

Studies:
  A — DT-relay agreement rate across 1000 MC trials
  B — DT state estimation accuracy statistics (all parameters)
  C — False-positive and false-negative DT flag rates
  D — DT model update performance (online learning loop)
  E — End-to-end latency: sensor → DT → relay → CB open
"""

import math
import random
import numpy as np
from collections import Counter

random.seed(42)
np.random.seed(42)

# ── Parameters ──────────────────────────────────────────────────────────────
I_MIN_87L  = 0.06    # 87L threshold
I_MIN_Z1   = 0.10    # Z1 threshold
X_R1       = 0.040   # Z1 quadrilateral X reach
I_MIN_67Q  = 0.10    # 67Q threshold (GFM)
DT_RATE    = 1000    # Hz
N_MC       = 1000    # Monte Carlo trials

# ── Protection scheme evaluation (simplified, from TR-35) ─────────���────────
def relay_evaluate(k_ibr, alpha, fault_type, r_arc=0.0):
    """Returns (tripped, element, element_str)."""
    if alpha > 1.0:
        return False, "EXTERNAL", "external"
    if k_ibr < I_MIN_87L:
        return False, "MISS", "below threshold"
    xm = alpha * 0.050
    rm = r_arc * (1.0 + 1.0/k_ibr) if k_ibr > 0.01 else 100
    z1 = (xm >= 0) and (xm <= X_R1) and (rm <= 0.030) and (k_ibr >= I_MIN_Z1)
    l87 = k_ibr >= I_MIN_87L
    if z1:
        return True, "Z1", "Z1"
    if l87:
        return True, "87L", "87L"
    return False, "MISS", "miss"

# ── DT evaluation (includes noise + estimation error) ─────────────────────
def dt_evaluate(k_ibr, alpha, fault_type, r_arc=0.0,
                k_noise=0.010, alpha_noise=0.05):
    """DT evaluates with state estimation uncertainty."""
    k_est   = max(0.001, k_ibr + np.random.normal(0, k_noise))
    al_est  = max(0.001, min(1.05, alpha + np.random.normal(0, alpha_noise)))
    tripped, element, _ = relay_evaluate(k_est, al_est, fault_type, r_arc)
    return tripped, element, k_est, al_est

print("=" * 64)
print("SAMBP TR-45: Digital Twin Validation Study")
print("=" * 64)

# ════════════════════════════════════════════���═══════════════════════════
# Study A — DT-relay agreement rate
# ════════════════════════════════════════════════════════════════════════
print("\n── Study A: DT-Relay Agreement Rate (N=1000) ──")

fault_types = ["3PH","SLG","SLG","SLG","SLG","SLG","SLG","LL","LL","LLG"]
agree = 0
disagree_fp = 0  # DT says TRIP, relay says MISS
disagree_fn = 0  # DT says MISS, relay says TRIP
disagree_other = 0

results_A = []
for _ in range(N_MC):
    k   = random.uniform(0.04, 0.50)
    al  = random.uniform(0.00, 1.05)
    ft  = random.choice(fault_types)
    ra  = min(random.expovariate(250), 0.025)

    r_trip, r_elem, _ = relay_evaluate(k, al, ft, ra)
    d_trip, d_elem, k_est, al_est = dt_evaluate(k, al, ft, ra)

    if r_trip == d_trip:
        agree += 1
        outcome = "AGREE"
    elif r_trip and not d_trip:
        disagree_fn += 1  # relay trips, DT misses
        outcome = "FN"
    elif not r_trip and d_trip:
        disagree_fp += 1  # DT trips, relay misses
        outcome = "FP"
    else:
        disagree_other += 1
        outcome = "OTHER"
    results_A.append((k, al, ft, ra, r_trip, r_elem, d_trip, d_elem, outcome))

print(f"\n  Total trials: {N_MC}")
print(f"  Agreement: {agree} ({agree/N_MC*100:.2f}%)")
print(f"  DT flags relay miss (FN): {disagree_fn} ({disagree_fn/N_MC*100:.2f}%)")
print(f"  DT flags false trip (FP): {disagree_fp} ({disagree_fp/N_MC*100:.2f}%)")
print(f"  Other: {disagree_other}")
print(f"\n  DT agreement rate: {agree/N_MC*100:.2f}%")

# ═════════════════════════════════════════════��════════════════════════��═
# Study B — DT state estimation accuracy
# ═════════════════════════════════════════════════��══════════════════════
print("\n── Study B: DT State Estimation Accuracy ──")

# Re-compute k_est errors from results_A
k_errors_real = []
for res in results_A:
    k_true, al_true = res[0], res[1]
    for _ in range(1):
        k_e = max(0.001, k_true + np.random.normal(0, 0.010))
        k_errors_real.append(abs(k_e - k_true)/k_true*100 if k_true > 0.01 else 0.0)

k_rmse = math.sqrt(sum(e**2 for e in k_errors_real)/len(k_errors_real))
k_max  = max(k_errors_real)
k_p95  = sorted(k_errors_real)[int(0.95*len(k_errors_real))]

print(f"\n  k_ibr estimation (N={N_MC}, σ_I=0.010 pu):")
print(f"    RMSE:  {k_rmse:.2f}%")
print(f"    Max:   {k_max:.2f}%")
print(f"    P95:   {k_p95:.2f}%")
print(f"\n  K_ibr correctly classified in protection zone?")

# Zone classification accuracy
n_correct_zone = 0
for res in results_A:
    k_true, al_true = res[0], res[1]
    k_e = max(0.001, k_true + np.random.normal(0, 0.010))
    zone_true = "ABOVE" if k_true >= I_MIN_87L else "BELOW"
    zone_est  = "ABOVE" if k_e   >= I_MIN_87L else "BELOW"
    if zone_true == zone_est:
        n_correct_zone += 1
print(f"    Zone classification accuracy: {n_correct_zone/N_MC*100:.2f}%")

# ══════════════════════════════���═════════════════════════════════════════
# Study C — Flag rates analysis
# ═════════════════════════════════════��══════════════════════════════════
print("\n── Study C: DT Flag Rate Analysis ──")

# Classify false positives and negatives by k_ibr range
fp_by_region = {'k<0.06': 0, '0.06≤k<0.10': 0, 'k≥0.10': 0}
fn_by_region = {'k<0.06': 0, '0.06≤k<0.10': 0, 'k≥0.10': 0}
total_by_region = {'k<0.06': 0, '0.06≤k<0.10': 0, 'k≥0.10': 0}

for res in results_A:
    k = res[0]; al = res[1]
    if al > 1.0:  # external — skip
        continue
    if k < 0.06:
        reg = 'k<0.06'
    elif k < 0.10:
        reg = '0.06≤k<0.10'
    else:
        reg = 'k≥0.10'
    total_by_region[reg] += 1
    if res[8] == 'FN':
        fn_by_region[reg] += 1
    elif res[8] == 'FP':
        fp_by_region[reg] += 1

print(f"\n  {'Region':>18s} {'Total':>7s} {'FP':>7s} {'FN':>7s} {'FP rate':>10s} {'FN rate':>10s}")
print(f"  {'-'*18} {'-'*7} {'-'*7} {'-'*7} {'-'*10} {'-'*10}")
for reg in ['k<0.06', '0.06≤k<0.10', 'k≥0.10']:
    n = total_by_region[reg]
    fp = fp_by_region[reg]
    fn = fn_by_region[reg]
    fp_r = fp/n*100 if n > 0 else 0
    fn_r = fn/n*100 if n > 0 else 0
    print(f"  {reg:>18s} {n:>7d} {fp:>7d} {fn:>7d} {fp_r:>10.2f} {fn_r:>10.2f}")

# ════════════════════════════════��═══════════════════════════════════════
# Study D — Online model update performance
# ═══════════════════════════════════���══════════════════════════════��═════
print("\n── Study D: Online Model Update (Learning Loop) ──")

# Simulate k_ibr slowly drifting (IBR fleet dispatch changes)
k_drift_true  = [0.20 + 0.10 * math.sin(2*math.pi*i/500) for i in range(1000)]
k_dt_estimate = [0.20]  # DT starts at nominal
forgetting    = 0.995

for i in range(1, 1000):
    # Single RLS update
    noise = np.random.normal(0, 0.01)
    meas  = k_drift_true[i] + noise
    # Simple update: weighted average toward measurement
    k_upd = forgetting * k_dt_estimate[-1] + (1 - forgetting) * meas
    k_dt_estimate.append(k_upd)

# Compute tracking error
tracking_errors = [abs(k_dt_estimate[i] - k_drift_true[i])/0.20*100
                   for i in range(1000)]

print(f"\n  k_ibr slow drift tracking (sinusoidal, period=500 updates):")
print(f"    Max drift amplitude: ±0.10 pu (±50% of nominal)")
print(f"    RLS forgetting factor: {forgetting}")
print(f"\n    Tracking error statistics:")
print(f"    Mean error: {sum(tracking_errors)/len(tracking_errors):.2f}%")
print(f"    Max error:  {max(tracking_errors):.2f}%")
print(f"    P95 error:  {sorted(tracking_errors)[950]:.2f}%")

# ═════════════════��═══════════════════════════════════���═════════════════��
# Study E — End-to-end latency budget
# ═════════════════════════════════════��══════════════════════════════════
print("\n── Study E: End-to-End Latency Budget ──")

print(f"""
  Latency chain (sensor to CB open):

  ┌─────────���─────────────────────────────���──────────────────────────────┐
  │ Stage                          │ Latency [ms] │ Source               │
  ├────────────────────────────────┼──────────────┼──────────────────────┤
  │ CT/VT transducer               │    0.5       │ Class 1P CT          │
  │ IEC 61869-9 digital sampling   │    0.5       │ 80 Sa/cycle + frame  │
  │ Merging unit → relay           │    1.0       │ IEC 61850-9-2        │
  │ Relay protection algorithm     │   18.0       │ Z1/87L trip time     │
  │ GOOSE trip signal              │    2.0       │ IEC 61850-8-1        │
  │ Circuit breaker operation      │   30.0       │ Vacuum CB (std.)     │
  │ TOTAL (sensor → CB open)       │   52.0       │                      │
  ├─────────────────────���──────────┼────────���─────┼─────────────────��────┤
  │ DT cycle (parallel path)       │    1.0       │ TR-43, 1 kHz         │
  │ DT does NOT add latency        │     —        │ non-blocking         │
  └─────────────────────���──────────────────────��─────────────────────────┘
""")

T_TOTAL = 0.5 + 0.5 + 1.0 + 18.0 + 2.0 + 30.0
print(f"  Total fault clearance time (sensor to CB open): {T_TOTAL:.1f} ms")
print(f"  DT contribution to latency: 0 ms (non-blocking parallel path)")
print(f"  T_mem constraint (100 ms): met with {100-T_TOTAL:.1f} ms margin")

print("\n" + "=" * 64)
print("TR-45 DT validation complete.")
print(f"  DT-relay agreement: {agree/N_MC*100:.2f}%")
print(f"  k_ibr zone classification: {n_correct_zone/N_MC*100:.2f}%")
print(f"  Online tracking max error: {max(tracking_errors):.2f}%")
print(f"  End-to-end clearance: {T_TOTAL:.1f} ms (T_mem margin: {100-T_TOTAL:.1f} ms)")
print("=" * 64)
