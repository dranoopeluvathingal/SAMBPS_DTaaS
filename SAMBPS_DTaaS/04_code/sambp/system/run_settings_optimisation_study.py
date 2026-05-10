"""
run_settings_optimisation_study.py
SAMBP TR-51/2026: Automatic Protection Settings Optimisation

Offline relay coordination engine that computes Ip pickup and TMS
time-multiplier settings for all 11 relays on the 10-bus test network.
Grading direction: radial from bus 9/4 extremities toward bus 0 (grid
infeed).  Meshed tie-lines (R10, R11) are graded via their weakest-infeed
backup path.

Studies:
  A — Sensitivity analysis: fault current vs k_ibr (0.35, 0.60)
  B — CTI grading: primary/backup coordination time intervals
  C — Optimised settings table with operating times and CTI margins
  D — Fleet-change resetting: relay count requiring TMS update (k: 0.35→0.60)
  E — Setting robustness: per-pair CTI pass rate under ±10% Z uncertainty
"""

import math
import random
import numpy as np
from collections import defaultdict, deque

random.seed(42)
np.random.seed(42)

# ── 10-bus network ────────────────────────────────────────────────────────
# Arranged as approximate radial feeders from bus 0 (grid) and bus 5 (IBR)
LINES = [
    (0, 1, 0.050, 'R01'),  # grid infeed
    (1, 2, 0.040, 'R02'),
    (2, 3, 0.060, 'R03'),
    (3, 4, 0.050, 'R04'),
    (4, 9, 0.070, 'R10'),  # tie to ring
    (1, 5, 0.030, 'R05'),  # to IBR bus
    (5, 6, 0.040, 'R06'),
    (6, 7, 0.050, 'R07'),
    (7, 8, 0.060, 'R08'),
    (8, 9, 0.040, 'R09'),
    (3, 7, 0.050, 'R11'),  # inter-area
]
N_RELAY = len(LINES)
RELAY_IDS = [l[3] for l in LINES]

# Grading order: extremities first (longest electrical path from source)
# Each relay's "depth" = sum of upstream impedances from bus 0
RELAY_DEPTH = {
    'R01': 0.050,
    'R02': 0.090,
    'R03': 0.150,
    'R04': 0.200,
    'R10': 0.270,
    'R05': 0.080,
    'R06': 0.120,
    'R07': 0.170,
    'R08': 0.230,
    'R09': 0.270,
    'R11': 0.200,
}
# Primary → backup: backup is the relay one step closer to bus 0
PRIMARY_BACKUP = {
    'R09': 'R08', 'R10': 'R04',
    'R08': 'R07', 'R04': 'R03',
    'R11': 'R03', 'R07': 'R06',
    'R03': 'R02', 'R06': 'R05',
    'R02': 'R01', 'R05': 'R01',
}

# Protection constants
CTI_MIN   = 0.200   # s
I_MARGIN  = 0.200   # 20% sensitivity margin: I_fault > 1.2 * Ip
REACH_PCT = 0.800   # zone-1 reach 80%
TMS_MIN   = 0.050
TMS_MAX   = 1.200
Z_SRC     = 0.020   # grid source impedance (pu)
Z_IBR_SRC = 0.030   # IBR source impedance (pu)

def fault_current(zl, k_ibr=0.35):
    """Fault current at relay for bolted 3-phase fault at relay bus."""
    I_grid = 1.0 / (zl + Z_SRC)
    I_ibr  = k_ibr / (zl + Z_IBR_SRC)
    return I_grid + I_ibr

def t_op(I, Ip, TMS):
    """IEC Standard Inverse operating time (returns inf if I<=Ip)."""
    M = I / Ip
    if M <= 1.001: return 1e9
    return TMS * 0.14 / (M**0.02 - 1.0)

def required_tms(I, Ip, t_req):
    """TMS needed to achieve operating time t_req at current I."""
    M = I / Ip
    if M <= 1.001: return TMS_MAX
    return t_req * (M**0.02 - 1.0) / 0.14

print("=" * 64)
print("SAMBP TR-51: Automatic Protection Settings Optimisation")
print("=" * 64)

# ════════════════════════════════════════════════════════════════════════
# Study A — Sensitivity analysis
# ════════════════════════════════════════════════════════════════════════
print("\n── Study A: Fault Current vs k_ibr ──")

print(f"\n  {'Relay':>6s}  {'Z_L':>6s}  {'I_flt (k=0.35)':>16s}  "
      f"{'I_flt (k=0.60)':>16s}  {'Ratio':>7s}")
print(f"  {'-'*6}  {'-'*6}  {'-'*16}  {'-'*16}  {'-'*7}")

ifc35, ifc60 = {}, {}
for a, b, z, rid in LINES:
    i35 = fault_current(RELAY_DEPTH[rid], k_ibr=0.35)
    i60 = fault_current(RELAY_DEPTH[rid], k_ibr=0.60)
    ifc35[rid] = i35;  ifc60[rid] = i60
    print(f"  {rid:>6s}  {z:>6.3f}  {i35:>16.3f}  {i60:>16.3f}  {i60/i35:>7.3f}")

mean_ratio = np.mean([ifc60[r]/ifc35[r] for r in RELAY_IDS])
print(f"\n  Mean fault current increase (k: 0.35→0.60): {mean_ratio:.3f}×")

# ════════════════════════════════════════════════════════════════════════
# Study B — Primary/backup pairs
# ════════════════════════════════════════════════════════════════════════
print("\n── Study B: Coordination Pairs ──")
print(f"\n  {'Primary':>8s} → {'Backup':>8s}  {'CTI':>6s}")
print(f"  {'-'*8}   {'-'*8}  {'-'*6}")
for pri, bak in sorted(PRIMARY_BACKUP.items()):
    print(f"  {pri:>8s} → {bak:>8s}  {CTI_MIN:.3f} s")
print(f"\n  Total pairs: {len(PRIMARY_BACKUP)}")

# ════════════════════════════════════════════════════════════════════════
# Study C — Optimised settings
# ════════════════════════════════════════════════════════════════════════
print("\n── Study C: Optimised Settings (k_ibr = 0.35) ──")

# Step 1: Ip = fault_current at 80% reach / (1 + I_MARGIN)
# Use depth of relay + 80% of line impedance as reach point
line_z = {rid: z for a,b,z,rid in LINES}
def reach_fault(rid, k_ibr):
    d_reach = RELAY_DEPTH[rid] + 0.80 * line_z[rid]
    return fault_current(d_reach, k_ibr)

settings = {}
for _, _, _, rid in LINES:
    I_reach = reach_fault(rid, k_ibr=0.35)
    Ip      = I_reach / (1.0 + I_MARGIN)
    Ip      = max(0.10, min(1.50, Ip))
    settings[rid] = {'Ip': Ip, 'TMS': TMS_MIN}

# Step 2: TMS grading from extremities toward source
# Grade in order of decreasing depth (extremities first = minimum TMS)
# then work inward ensuring backup TMS satisfies CTI
relay_by_depth = sorted(RELAY_IDS, key=lambda r: -RELAY_DEPTH[r])

for rid in relay_by_depth:
    if rid not in PRIMARY_BACKUP: continue
    bak  = PRIMARY_BACKUP[rid]
    I_f  = ifc35[rid]              # fault current at primary relay bus
    t_pri = t_op(I_f, settings[rid]['Ip'],  settings[rid]['TMS'])
    t_bak_needed = t_pri + CTI_MIN
    tms_need = required_tms(I_f, settings[bak]['Ip'], t_bak_needed)
    settings[bak]['TMS'] = min(TMS_MAX, max(settings[bak]['TMS'], tms_need))

# Print results
print(f"\n  {'Relay':>6s}  {'Ip':>7s}  {'TMS':>7s}  "
      f"{'t_op (s)':>9s}  {'CTI (s)':>9s}  {'OK?':>5s}")
print(f"  {'-'*6}  {'-'*7}  {'-'*7}  {'-'*9}  {'-'*9}  {'-'*5}")

n_viol = 0
for _, _, _, rid in LINES:
    I_f  = ifc35[rid]
    top  = t_op(I_f, settings[rid]['Ip'], settings[rid]['TMS'])
    if rid in PRIMARY_BACKUP:
        bak = PRIMARY_BACKUP[rid]
        t_b = t_op(I_f, settings[bak]['Ip'], settings[bak]['TMS'])
        cti = t_b - top
        ok  = cti >= CTI_MIN - 0.001
        if not ok: n_viol += 1
        cti_str = f"{cti:>9.3f}"
        ok_str  = "OK" if ok else "FAIL"
    else:
        cti_str = "      ---"
        ok_str  = " ---"
    print(f"  {rid:>6s}  {settings[rid]['Ip']:>7.3f}  {settings[rid]['TMS']:>7.3f}  "
          f"{top:>9.3f}  {cti_str}  {ok_str:>5s}")

print(f"\n  CTI violations: {n_viol}/{len(PRIMARY_BACKUP)}")

# ════════════════════════════════════════════════════════════════════════
# Study D — Fleet-change resetting
# ════════════════════════════════════════════════════════════════════════
print("\n── Study D: Fleet-Change Resetting (k_ibr 0.35 → 0.60) ──")

settings60 = {}
for _, _, _, rid in LINES:
    I_reach = reach_fault(rid, k_ibr=0.60)
    Ip      = I_reach / (1.0 + I_MARGIN)
    Ip      = max(0.10, min(1.50, Ip))
    settings60[rid] = {'Ip': Ip, 'TMS': TMS_MIN}

for rid in relay_by_depth:
    if rid not in PRIMARY_BACKUP: continue
    bak = PRIMARY_BACKUP[rid]
    I_f = ifc60[rid]
    t_pri = t_op(I_f, settings60[rid]['Ip'], settings60[rid]['TMS'])
    tms_n = required_tms(I_f, settings60[bak]['Ip'], t_pri + CTI_MIN)
    settings60[bak]['TMS'] = min(TMS_MAX, max(settings60[bak]['TMS'], tms_n))

n_Ip_chg = n_TMS_chg = 0
print(f"\n  {'Relay':>6s}  {'Ip_35':>7s}  {'Ip_60':>7s}  "
      f"{'TMS_35':>7s}  {'TMS_60':>7s}  {'Δ?':>5s}")
print(f"  {'-'*6}  {'-'*7}  {'-'*7}  {'-'*7}  {'-'*7}  {'-'*5}")

for _, _, _, rid in LINES:
    dIp  = abs(settings60[rid]['Ip']  - settings[rid]['Ip'])  > 0.005
    dTMS = abs(settings60[rid]['TMS'] - settings[rid]['TMS']) > 0.005
    if dIp:  n_Ip_chg  += 1
    if dTMS: n_TMS_chg += 1
    flag = "YES" if (dIp or dTMS) else "---"
    print(f"  {rid:>6s}  {settings[rid]['Ip']:>7.3f}  {settings60[rid]['Ip']:>7.3f}  "
          f"{settings[rid]['TMS']:>7.3f}  {settings60[rid]['TMS']:>7.3f}  {flag:>5s}")

print(f"\n  Ip  changes: {n_Ip_chg}/{N_RELAY}")
print(f"  TMS changes: {n_TMS_chg}/{N_RELAY}")

# ════════════════════════════════════════════════════════════════════════
# Study E — Robustness under ±10% impedance uncertainty
# ════════════════════════════════════════════════════════════════════════
print("\n── Study E: Per-Pair CTI Robustness (±10% Z, N=500) ──")

N_T = 500
pair_pass = {pri: 0 for pri in PRIMARY_BACKUP}
pair_cti_vals = {pri: [] for pri in PRIMARY_BACKUP}

for _ in range(N_T):
    for pri, bak in PRIMARY_BACKUP.items():
        zl_unc = line_z[pri] * (1 + np.random.uniform(-0.10, 0.10))
        d_unc  = RELAY_DEPTH[pri] + 0.5 * zl_unc   # approx
        I_f    = fault_current(d_unc, k_ibr=0.35)
        top    = t_op(I_f, settings[pri]['Ip'], settings[pri]['TMS'])
        tbak   = t_op(I_f, settings[bak]['Ip'], settings[bak]['TMS'])
        cti    = tbak - top
        pair_cti_vals[pri].append(cti)
        if cti >= CTI_MIN - 0.001:
            pair_pass[pri] += 1

print(f"\n  {'Pair':>12s}  {'Pass%':>7s}  {'Mean CTI':>10s}  {'Min CTI':>10s}")
print(f"  {'-'*12}  {'-'*7}  {'-'*10}  {'-'*10}")
all_pass = 0
for pri, bak in sorted(PRIMARY_BACKUP.items()):
    pct  = pair_pass[pri] / N_T * 100
    if pct > 99: all_pass += 1
    vals = pair_cti_vals[pri]
    print(f"  {pri}→{bak}  {pct:>7.1f}  {np.mean(vals):>10.3f}  {np.min(vals):>10.3f}")

print(f"\n  Pairs with >99% CTI pass rate: {all_pass}/{len(PRIMARY_BACKUP)}")

print("\n" + "=" * 64)
print("TR-51 settings optimisation complete.")
print(f"  CTI violations (nominal): {n_viol}/{len(PRIMARY_BACKUP)}")
print(f"  Fleet change: {n_Ip_chg} Ip + {n_TMS_chg} TMS updates")
print(f"  Robust pairs (>99% pass): {all_pass}/{len(PRIMARY_BACKUP)}")
print("=" * 64)
