"""
run_islanding_study.py
SAMBP TR-39/2026: Islanding Detection and Protection Mode Switching
for IBR Microgrids

Studies:
  A — Passive islanding detection: ROCOF, voltage/frequency window thresholds
  B — Active islanding detection: ROACF, reactive power injection, NDZ analysis
  C — Protection mode switching: grid-connected → islanded → resync
  D — Non-detection zone (NDZ) for balanced load case
  E — Resynchronisation check relay (25) criteria
"""

import math
import numpy as np

# ── System parameters ──────────────────────────────────────────────────────
F_NOM    = 50.0       # Hz
V_NOM    = 1.00       # pu
S_IBR    = 1.00       # IBR rated power (pu)
P_LOAD   = 0.80       # pu real load
Q_LOAD   = 0.10       # pu reactive load
H_EQ     = 0.50       # equivalent inertia constant (very low for IBR microgrid, s)

# Passive detection thresholds (IEC 62116 / IEEE 1547-2018)
ROCOF_THRESH  = 1.0   # Hz/s
V_MIN         = 0.88  # pu  (88% V_nom)
V_MAX         = 1.10  # pu  (110% V_nom)
F_MIN         = 49.0  # Hz
F_MAX         = 50.5  # Hz

# Active method: reactive power injection
DQ_INJECT     = 0.05  # pu reactive power perturbation
K_FREQ_Q      = 2.0   # Hz/pu (frequency sensitivity to Q injection in islanded)

# Relay operating times
T_ROCOF_TRIP  = 0.10  # s
T_V_TRIP      = 0.10  # s
T_F_TRIP      = 0.16  # s
T_MODE_SWITCH = 0.02  # s (mode switch after islanding confirmed)
T_RESYNC_MAX  = 5.00  # s (max resync window before lockout)

# Resynchronisation check relay (25) settings
DV_MAX_25     = 0.05  # pu (max voltage magnitude difference)
DF_MAX_25     = 0.10  # Hz (max frequency difference)
DTHETA_MAX_25 = 10.0  # degrees (max angle difference)

print("=" * 64)
print("SAMBP TR-39: Islanding Detection and Mode Switching")
print("=" * 64)

# ════════════════════════════════════════════════════════════════════════
# Study A — Passive detection: ROCOF and V/f window
# ════════════════════════════════════════════════════════════════════════
print("\n── Study A: Passive Islanding Detection ──")

def rocof_at_mismatch(dp_pu):
    """
    ROCOF after islanding with power mismatch dp_pu [pu].
    df/dt = -dp * f_nom / (2 * H_eq)    [synchronous machine analogy]
    For IBR microgrid: H_eq is very small (virtual inertia only).
    """
    return abs(dp_pu) * F_NOM / (2.0 * H_EQ)

# Scan mismatch from -0.40 to +0.40 pu
mismatches = [-0.40, -0.30, -0.20, -0.10, -0.05, 0.00, 0.05, 0.10, 0.20, 0.30, 0.40]

print(f"\n  {'ΔP [pu]':>10s} {'ROCOF [Hz/s]':>14s} {'Detected?':>10s} {'T_trip [ms]':>12s}")
print(f"  {'-'*10} {'-'*14} {'-'*10} {'-'*12}")

rocof_data = []
for dp in mismatches:
    roc = rocof_at_mismatch(dp)
    det = roc >= ROCOF_THRESH
    t_trip = T_ROCOF_TRIP * 1000 if det else float('inf')
    status = "YES" if det else "NO"
    print(f"  {dp:>10.2f} {roc:>14.2f} {status:>10s} {t_trip:>12.1f}")
    rocof_data.append((dp, roc, det))

# NDZ for ROCOF: |ΔP| < ROCOF_THRESH * 2H / f_nom
ndz_dp_rocof = ROCOF_THRESH * 2 * H_EQ / F_NOM
print(f"\n  ROCOF NDZ: |ΔP| < {ndz_dp_rocof:.4f} pu = {ndz_dp_rocof*100:.2f}% of rated")

# V/f window — check frequency deviation from mismatch
print(f"\n  V/f window: f_min={F_MIN}Hz, f_max={F_MAX}Hz, V_min={V_MIN}pu, V_max={V_MAX}pu")
print(f"  Frequency deviation after islanding at ΔP=+0.10 pu (steady state):")
# In islanded mode, IBR droop: Δf = -kD * ΔP (droop coefficient ~5%)
k_droop = 0.05 * F_NOM  # Hz/pu
df_steady = -k_droop * 0.10
f_steady  = F_NOM + df_steady
print(f"    Δf = {df_steady:.2f} Hz → f_steady = {f_steady:.2f} Hz "
      f"({'DETECTED' if f_steady < F_MIN or f_steady > F_MAX else 'within window'})")

# ════════════════════════════════════════════════════════════════════════
# Study B — Active detection: reactive power injection
# ════════════════════════════════════════════════════════════════════════
print("\n── Study B: Active Islanding Detection (Q-injection) ──")

def freq_response_islanded(dq_inject):
    """
    Frequency change due to Q injection when islanded.
    In grid-connected: frequency is stiff → Δf ≈ 0.
    In islanded: Q-V droop causes voltage change → inverter PLL-free freq shift.
    Model: Δf = K_freq_Q * ΔQ (islanded); 0 (grid-connected).
    """
    return K_FREQ_Q * dq_inject  # Hz

df_grid  = 0.0                               # stiff grid: no freq change
df_islan = freq_response_islanded(DQ_INJECT) # islanded: freq shifts

print(f"  Q injection: ΔQ = {DQ_INJECT:.2f} pu")
print(f"  Grid-connected response: Δf = {df_grid:.3f} Hz (stiff bus)")
print(f"  Islanded response:       Δf = {df_islan:.3f} Hz")
print(f"  Discrimination threshold: Δf > {DF_MAX_25:.2f} Hz → "
      f"{'ISLANDING DETECTED' if abs(df_islan) > DF_MAX_25 else 'not detected'}")

# Active method NDZ
ndz_active_dp = DQ_INJECT * K_FREQ_Q / ROCOF_THRESH  # rough bound
print(f"  Active NDZ (estimated): much smaller than passive; "
      f"residual ~{ndz_active_dp:.4f} pu mismatch range")

# ════════════════════════════════════════════════════════════════════════
# Study C — Mode switching sequence and timing
# ════════════════════════════════════════════════════════════════════════
print("\n── Study C: Protection Mode Switching Sequence ──")

events = [
    (0.000, "Grid fault → upstream breaker opens (islanding event)"),
    (0.000, "ROCOF monitoring starts"),
    (0.060, "ROCOF threshold exceeded (ΔP=0.20 pu → ROCOF=10 Hz/s)"),
    (0.100, "Passive detection confirmed → islanding declared"),
    (0.120, "Mode switch: Grid-connected → Islanded protection mode"),
    (0.120, "Z1/Z2 distance elements disabled (no remote infeed reference)"),
    (0.120, "OC elements re-scaled for islanded fault level"),
    (0.120, "87L removed from service (remote comms path lost)"),
    (0.120, "Frequency/voltage regulation mode activated in GFM inverters"),
    (1.500, "Grid restored: upstream breaker reclosed"),
    (1.500, "Relay 25 (sync-check) initiated"),
    (1.520, "ΔV, Δf, Δθ within 25 settings → reconnection approved"),
    (1.520, "Mode switch: Islanded → Grid-connected (resync complete)"),
]

print(f"\n  {'Time [ms]':>10s}  Event")
print(f"  {'-'*10}  {'-'*55}")
for t, ev in events:
    print(f"  {t*1000:>10.1f}  {ev}")

t_island_detect   = 0.100  # s
t_mode_switch     = 0.120  # s
t_protection_gap  = t_mode_switch - t_island_detect
print(f"\n  Detection → mode switch gap: {t_protection_gap*1000:.0f} ms")
print(f"  Protection re-coordinated within: {t_mode_switch*1000:.0f} ms of islanding")

# ════════════════════════════════════════════════════════════════════════
# Study D — NDZ analysis (balanced load)
# ════════════════════════════════════════════════════════════════════════
print("\n── Study D: Non-Detection Zone Analysis ──")

# NDZ is defined in (ΔP/P_load, ΔQ/Q_load) space
# For passive: |ΔP/P_load| < rocof_thresh * 2H / (f_nom * P_load)
ndz_p_passive = ndz_dp_rocof / P_LOAD * 100  # percent of load
ndz_q_passive = 5.0                           # pu % (f window capture)

print(f"\n  Passive methods NDZ:")
print(f"    ΔP range: ±{ndz_p_passive:.2f}% of load power")
print(f"    ΔQ range: ±{ndz_q_passive:.2f}% (frequency window)")

# Combined passive + active NDZ
ndz_p_combined = min(ndz_p_passive, DQ_INJECT/P_LOAD*100)
ndz_q_combined = min(ndz_q_passive, DQ_INJECT/Q_LOAD*100) if Q_LOAD > 0 else ndz_q_passive

print(f"\n  Combined passive + active NDZ:")
print(f"    ΔP range: ±{ndz_p_combined:.2f}% of load power")
print(f"    ΔQ range: ±{ndz_q_combined:.2f}% of load reactive")
print(f"    Practical elimination of NDZ for microgrid loads > 0.10 pu imbalance")

# Area ratio (approximate)
ndz_area_passive   = 4 * ndz_p_passive * ndz_q_passive
ndz_area_combined  = 4 * ndz_p_combined * ndz_q_combined
print(f"\n  NDZ area reduction: {100*(1 - ndz_area_combined/ndz_area_passive):.1f}%")

# ════════════════════════════════════════════════════════════════════════
# Study E — Resynchronisation check (relay 25) criteria
# ════════════════════════════════════════════════════════════════════════
print("\n── Study E: Resynchronisation Check (Relay 25) ──")

# Simulate islanded frequency drift (droop control)
print(f"\n  Relay 25 settings:")
print(f"    Max ΔV:     {DV_MAX_25:.2f} pu")
print(f"    Max Δf:     {DF_MAX_25:.2f} Hz")
print(f"    Max Δθ:     {DTHETA_MAX_25:.1f}°")

# Scenarios
scenarios = [
    (0.02, 0.03, 5.0,  "Light load island"),
    (0.04, 0.08, 8.0,  "Moderate mismatch island"),
    (0.06, 0.15, 15.0, "Heavy mismatch island"),
    (0.08, 0.25, 25.0, "Severe drift — BLOCKED"),
]

print(f"\n  {'Scenario':>28s} {'ΔV[pu]':>8s} {'Δf[Hz]':>8s} {'Δθ[°]':>7s} {'25 CLOSES?':>12s}")
print(f"  {'-'*28} {'-'*8} {'-'*8} {'-'*7} {'-'*12}")
for (dv, df, dth, name) in scenarios:
    ok = (dv <= DV_MAX_25) and (df <= DF_MAX_25) and (dth <= DTHETA_MAX_25)
    result = "YES" if ok else "BLOCKED"
    print(f"  {name:>28s} {dv:>8.2f} {df:>8.2f} {dth:>7.1f} {result:>12s}")

print(f"\n  Closing transient energy at Δθ=10°: "
      f"ΔW = 0.5 * S_rated * (1 - cos(10°)) = "
      f"{0.5 * S_IBR * (1 - math.cos(math.radians(DTHETA_MAX_25))):.4f} pu·s")

print("\n" + "=" * 64)
print("TR-39 islanding study complete.")
print(f"  ROCOF NDZ: ±{ndz_dp_rocof:.4f} pu mismatch")
print(f"  Mode switch: {t_mode_switch*1000:.0f} ms from islanding")
print(f"  NDZ eliminated for |ΔP| > {DQ_INJECT/P_LOAD*100:.1f}% load imbalance (active)")
print(f"  25 closes: ΔV≤{DV_MAX_25:.2f} AND Δf≤{DF_MAX_25:.2f} AND Δθ≤{DTHETA_MAX_25:.0f}°")
print("=" * 64)
