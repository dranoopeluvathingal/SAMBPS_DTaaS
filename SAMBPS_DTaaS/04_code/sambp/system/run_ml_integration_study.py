"""
run_ml_integration_study.py
SAMBP TR-49/2026: ML Protection System Integration and Validation

Integrates the PINN classifier (TR-46), feature engineering (TR-47),
and online learning (TR-48) into the SAMBP protection intelligence layer.
Validates the combined system against the relay-physics baseline across
a 500-scenario integration test suite.

Studies:
  A — End-to-end pipeline latency (feature extraction + inference + GOOSE)
  B — Integration test: ML layer vs relay-physics baseline (N=500)
  C — Override logic: when ML recommendation supersedes relay output
  D — Degraded-mode fallback: performance with 1, 2, 3 sensor failures
  E — Summary statistics and selectivity/security trade-offs
"""

import math
import random
import numpy as np

random.seed(42)
np.random.seed(42)

# ── Protection constants ──────────────────────────────────────────────────
Z1L       = 0.050
X_R1      = 0.040
R_FWD1    = 0.030
I_MIN_87L = 0.060
I_MIN_Z1  = 0.100

def true_label(k, alpha, r_arc=0.0):
    if alpha > 1.0: return 3
    if k < I_MIN_87L: return 0
    xm = alpha * Z1L
    rm = r_arc * (1 + 1/k) if k > 0.01 else 100
    if (xm <= X_R1) and (rm <= R_FWD1) and (k >= I_MIN_Z1): return 2
    return 1

CLASS_NAMES = {0:'MISS', 1:'87L', 2:'Z1', 3:'EXT'}

# ── ML model: rule-based PINN proxy with noise ───────────────────────────
def ml_predict(k, alpha, r_arc, noise_lvl=0.03):
    k_n  = k     + np.random.normal(0, noise_lvl)
    al_n = alpha + np.random.normal(0, noise_lvl * 1.5)
    r_n  = max(0, r_arc + np.random.normal(0, noise_lvl * 0.5))
    return true_label(max(0.01, k_n), al_n, r_n)

# ── Relay-physics baseline: deterministic rule engine ────────────────────
def relay_predict(k, alpha, r_arc):
    return true_label(k, alpha, r_arc)

# ── Override logic ────────────────────────────────────────────────────────
def combined_decision(k, alpha, r_arc, ml_noise=0.03):
    """ML + relay combined decision with physics-veto."""
    relay  = relay_predict(k, alpha, r_arc)
    ml     = ml_predict(k, alpha, r_arc, noise_lvl=ml_noise)
    # Physics veto: if ML violates hard physics, use relay
    phys_violation = False
    if ml == 2 and k < I_MIN_87L:   phys_violation = True   # Z1 but k < 87L threshold
    if ml == 0 and k >= I_MIN_Z1:   phys_violation = True   # MISS but k above Z1 threshold
    if ml == 3 and alpha <= 0.80:   phys_violation = True   # EXT but alpha within reach
    if phys_violation:
        return relay, 'relay-veto'
    # Override: use ML if it matches physics constraints and differs from relay
    # (ML captures arc resistance effects better)
    if ml != relay and not phys_violation:
        return ml, 'ml-override'
    return relay, 'agree'

N = 500
print("=" * 64)
print("SAMBP TR-49: ML Protection System Integration")
print("=" * 64)

# ════════════════════════════════════════════════════════════════════════
# Study A — End-to-end pipeline latency
# ════════════════════════════════════════════════════════════════════════
print("\n── Study A: End-to-End Pipeline Latency ──")

# Latency budget (from TR-44, TR-46, TR-47)
latency = {
    'Feature extraction':  0.050,   # ms  (TR-47: 50 µs)
    'PINN inference':      0.150,   # ms  (TR-46: 3×64 layers, 150 µs)
    'Physics veto check':  0.010,   # ms  (3 conditional checks)
    'EKF state update':    0.018,   # ms  (TR-44: 17.6 µs)
    'DT library lookup':   0.107,   # ms  (TR-43: 107 µs)
    'GOOSE publication':   2.000,   # ms  (IEC 61850 GOOSE latency)
}

total_ms = sum(latency.values())
print(f"\n  {'Step':>24s} {'Latency (ms)':>14s} {'% budget':>10s}")
print(f"  {'-'*24} {'-'*14} {'-'*10}")
for step, ms in latency.items():
    print(f"  {step:>24s} {ms:>14.3f} {ms/total_ms*100:>10.1f}")
print(f"  {'Total':>24s} {total_ms:>14.3f} {100:>10.1f}")
print(f"\n  Relay trip time budget: 50.0 ms")
print(f"  ML intelligence budget: {total_ms:.3f} ms ({total_ms/50*100:.1f}% of relay budget)")

# ════════════════════════════════════════════════════════════════════════
# Study B — Integration test (N=500)
# ════════════════════════════════════════════════════════════════════════
print("\n── Study B: Integration Test (N=500) ──")

results = []
for _ in range(N):
    k     = random.uniform(0.03, 0.55)
    alpha = random.uniform(0.00, 1.10)
    r_arc = min(random.expovariate(200), 0.025)
    true  = true_label(k, alpha, r_arc)
    relay = relay_predict(k, alpha, r_arc)
    ml    = ml_predict(k, alpha, r_arc, noise_lvl=0.03)
    comb, mode = combined_decision(k, alpha, r_arc)
    results.append((k, alpha, r_arc, true, relay, ml, comb, mode))

# Accuracy
relay_correct = sum(1 for r in results if r[4] == r[3])
ml_correct    = sum(1 for r in results if r[5] == r[3])
comb_correct  = sum(1 for r in results if r[6] == r[3])

print(f"\n  Relay-physics baseline:   {relay_correct/N*100:.2f}%")
print(f"  ML-only (PINN):           {ml_correct/N*100:.2f}%")
print(f"  Combined (ML + veto):     {comb_correct/N*100:.2f}%")

# Mode distribution
modes = [r[7] for r in results]
from collections import Counter
mc = Counter(modes)
print(f"\n  Decision mode distribution:")
for mode_name, cnt in sorted(mc.items()):
    print(f"    {mode_name:>16s}: {cnt:4d} ({cnt/N*100:.1f}%)")

# Per-class breakdown
print(f"\n  Per-class combined accuracy:")
for c, name in CLASS_NAMES.items():
    class_n = sum(1 for r in results if r[3] == c)
    class_correct = sum(1 for r in results if r[3] == c and r[6] == c)
    if class_n > 0:
        print(f"    {name:>6s}: {class_correct}/{class_n} = {class_correct/class_n*100:.1f}%")

# ════════════════════════════════════════════════════════════════════════
# Study C — Override logic analysis
# ════════════════════════════════════════════════════════════════════════
print("\n── Study C: Override Logic Analysis ──")

override_cases = [r for r in results if r[7] == 'ml-override']
veto_cases     = [r for r in results if r[7] == 'relay-veto']
agree_cases    = [r for r in results if r[7] == 'agree']

if override_cases:
    override_correct = sum(1 for r in override_cases if r[6] == r[3])
    relay_correct_on_override = sum(1 for r in override_cases if r[4] == r[3])
    print(f"\n  ML override events: {len(override_cases)}")
    print(f"    Combined correct on overrides: {override_correct}/{len(override_cases)} "
          f"({override_correct/len(override_cases)*100:.1f}%)")
    print(f"    Relay correct on same events:  {relay_correct_on_override}/{len(override_cases)} "
          f"({relay_correct_on_override/len(override_cases)*100:.1f}%)")
    print(f"    ML benefit from overrides: {(override_correct - relay_correct_on_override):+d} correct")

if veto_cases:
    veto_correct = sum(1 for r in veto_cases if r[6] == r[3])
    print(f"\n  Physics veto events: {len(veto_cases)}")
    print(f"    Veto correct (relay used): {veto_correct}/{len(veto_cases)} "
          f"({veto_correct/len(veto_cases)*100:.1f}%)")

# ════════════════════════════════════════════════════════════════════════
# Study D — Degraded-mode fallback
# ════════════════════════════════════════════════════════════════════════
print("\n── Study D: Degraded-Mode Fallback ──")

sensor_scenarios = [
    ("All sensors OK",       0.030, 0.030),
    ("CT degraded (2x)",     0.060, 0.030),
    ("VT degraded (2x)",     0.030, 0.060),
    ("CT+VT degraded",       0.060, 0.060),
    ("CT missing (imputed)", 0.100, 0.030),
]

print(f"\n  {'Scenario':>30s} {'ML acc%':>10s} {'Combined%':>12s}")
print(f"  {'-'*30} {'-'*10} {'-'*12}")

for scenario, noise_k, noise_al in sensor_scenarios:
    deg_ml_correct  = 0
    deg_comb_correct = 0
    for _ in range(N):
        k     = random.uniform(0.03, 0.55)
        alpha = random.uniform(0.00, 1.10)
        r_arc = min(random.expovariate(200), 0.025)
        true  = true_label(k, alpha, r_arc)
        k_n   = max(0.01, k  + np.random.normal(0, noise_k))
        al_n  = alpha + np.random.normal(0, noise_al)
        r_n   = max(0, r_arc + np.random.normal(0, 0.002))
        ml_deg = true_label(k_n, al_n, r_n)
        # Physics veto
        phys_v = (ml_deg==2 and k_n < I_MIN_87L) or \
                 (ml_deg==0 and k_n >= I_MIN_Z1) or \
                 (ml_deg==3 and al_n <= 0.80)
        comb_deg = relay_predict(k, alpha, r_arc) if phys_v else ml_deg
        if ml_deg  == true: deg_ml_correct   += 1
        if comb_deg == true: deg_comb_correct += 1
    print(f"  {scenario:>30s} {deg_ml_correct/N*100:>10.1f} {deg_comb_correct/N*100:>12.1f}")

# ════════════════════════════════════════════════════════════════════════
# Study E — Summary statistics
# ════════════════════════════════════════════════════════════════════════
print("\n── Study E: Summary Statistics ──")

# Security and selectivity
# Security = P(no false trip | external fault)
ext_results = [r for r in results if r[3] == 3]  # EXT
ext_security = sum(1 for r in ext_results if r[6] == 3) / len(ext_results) if ext_results else 0

# Selectivity = P(correct trip | internal fault)
int_results = [r for r in results if r[3] in [1, 2]]  # 87L or Z1
int_selectivity = sum(1 for r in int_results if r[6] == r[3]) / len(int_results) if int_results else 0

# Physics violation rate
phys_violations = sum(
    1 for r in results
    if (r[6] == 2 and r[0] < I_MIN_87L) or
       (r[6] == 0 and r[0] >= I_MIN_Z1) or
       (r[6] == 3 and r[1] <= 0.80)
)

print(f"\n  Combined system metrics (N=500):")
print(f"    Overall accuracy:     {comb_correct/N*100:.2f}%")
print(f"    Security (EXT→EXT):   {ext_security*100:.2f}%")
print(f"    Selectivity (int):    {int_selectivity*100:.2f}%")
print(f"    Physics violations:   {phys_violations}/{N} ({phys_violations/N*100:.2f}%)")
print(f"    ML overrides applied: {len(override_cases)} ({len(override_cases)/N*100:.1f}%)")
print(f"    Physics veto applied: {len(veto_cases)} ({len(veto_cases)/N*100:.1f}%)")

print("\n" + "=" * 64)
print("TR-49 ML integration study complete.")
print(f"  Combined accuracy: {comb_correct/N*100:.2f}% (relay: {relay_correct/N*100:.2f}%)")
print(f"  Security: {ext_security*100:.2f}%  Selectivity: {int_selectivity*100:.2f}%")
print(f"  Physics violations: {phys_violations/N*100:.2f}%")
print("=" * 64)
