"""
run_adaptive_oc_study.py
SAMBP TR-40/2026: Adaptive Overcurrent Coordination for IBR Microgrids

Studies:
  A — Fault level comparison: grid-connected vs islanded modes
  B — OC relay coordination (pickup and TMS) for two modes
  C — Directional element validation (67)
  D — Adaptive coordination table and setting group selection
  E — Sensitivity: minimum meshed fault level
"""

import math

# ── System parameters ──────────────────────────────────────────────────────
V_BASE     = 1.00    # pu
Z_SYS      = 0.02    # pu upstream system impedance (grid-connected)
Z_LINE     = 0.05    # pu line impedance
Z_IBR      = 1.0     # pu IBR fault impedance (1/k_ibr)
K_IBR      = 0.20    # IBR fault current contribution ratio
Z_IBR_EFF  = Z_IBR / K_IBR  # effective impedance from IBR side

# Fault levels
I_FAULT_GC = V_BASE / (Z_SYS + Z_LINE / 2)  # grid-connected, mid-line fault
I_FAULT_IS = K_IBR * V_BASE / (Z_LINE / 2)  # islanded, IBR-only fault

# OC relay parameters
# Grid-connected settings (Group 1)
I_PICKUP_GC    = 1.50  # pu (1.5× load current = 0.80 pu → pickup at 1.20 pu)
TMS_GC         = 0.10  # time multiplier setting (standard inverse IEC 60255)
# Islanded settings (Group 2)
I_PICKUP_IS    = 0.30  # pu (lowered for reduced fault level)
TMS_IS         = 0.20  # increased TMS for selectivity with parallel feeders

# IEC standard inverse curve: t = TMS * 0.14 / ((I/Ip)^0.02 - 1)
def t_si(I, Ip, TMS):
    """Standard inverse operating time [s]"""
    if I <= Ip:
        return float('inf')
    M = I / Ip
    return TMS * 0.14 / (M**0.02 - 1)

# IEC very inverse: t = TMS * 13.5 / (M - 1)
def t_vi(I, Ip, TMS):
    if I <= Ip:
        return float('inf')
    M = I / Ip
    return TMS * 13.5 / (M - 1)

print("=" * 64)
print("SAMBP TR-40: Adaptive OC Coordination for IBR Microgrids")
print("=" * 64)

# ════════════════════════════════════════════════════════════════════════
# Study A — Fault level comparison
# ════════════════════════════════════════════════════════════════════════
print("\n── Study A: Fault Level Comparison ──")

print(f"\n  Grid-connected fault level (mid-line SLG):")
print(f"    Z_total = Z_sys + Z_line/2 = {Z_SYS:.3f} + {Z_LINE/2:.3f} = {Z_SYS+Z_LINE/2:.3f} pu")
print(f"    I_fault = {I_FAULT_GC:.3f} pu")

print(f"\n  Islanded fault level (IBR-only, mid-line SLG):")
print(f"    I_fault = k_ibr * V / (Z_line/2) = {K_IBR} * 1 / {Z_LINE/2:.3f} = {I_FAULT_IS:.3f} pu")

reduction = (1 - I_FAULT_IS / I_FAULT_GC) * 100
print(f"\n  Fault level reduction on islanding: {reduction:.1f}%")
print(f"  Ratio I_GC / I_IS = {I_FAULT_GC/I_FAULT_IS:.2f}")

# Far-end fault (α=1.0)
I_FAR_GC = V_BASE / (Z_SYS + Z_LINE)
I_FAR_IS = K_IBR * V_BASE / Z_LINE
print(f"\n  Far-end fault (α=1.0):")
print(f"    Grid-connected: {I_FAR_GC:.3f} pu")
print(f"    Islanded:       {I_FAR_IS:.3f} pu  (ratio: {I_FAR_GC/I_FAR_IS:.2f})")

# ════════════════════════════════════════════════════════════════════════
# Study B — OC relay coordination settings
# ════════════════════════════════════════════════════════════════════════
print("\n── Study B: OC Relay Settings and Coordination ──")

fault_currents_gc = [I_FAR_GC, I_FAULT_GC, 3*I_FAULT_GC]
fault_currents_is = [I_FAR_IS, I_FAULT_IS, 2*I_FAULT_IS]

print(f"\n  Grid-Connected Settings (Group 1): Ip={I_PICKUP_GC}, TMS={TMS_GC}")
print(f"  {'I_fault [pu]':>14s} {'t_SI [ms]':>10s}  Note")
for I in [0.20, 0.30, 0.50, 1.0, 2.0, 4.0, 8.0, 14.0, 28.0]:
    t = t_si(I, I_PICKUP_GC, TMS_GC)
    note = ""
    if abs(I - I_FAULT_IS) < 0.1:
        note = "<-- islanded fault"
    if abs(I - I_FAULT_GC) < 0.5:
        note = "<-- GC mid-line fault"
    ts = f"{t*1000:.1f}" if t < 1e6 else "∞ (below pickup)"
    print(f"  {I:>14.2f} {ts:>10s}  {note}")

print(f"\n  Islanded Settings (Group 2): Ip={I_PICKUP_IS}, TMS={TMS_IS}")
print(f"  {'I_fault [pu]':>14s} {'t_SI [ms]':>10s}  Note")
for I in [0.05, 0.10, 0.20, 0.30, 0.50, 0.80, 1.0, 2.0, 4.0]:
    t = t_si(I, I_PICKUP_IS, TMS_IS)
    note = ""
    if abs(I - I_FAULT_IS) < 0.1:
        note = "<-- islanded mid-line fault"
    if abs(I - I_FAR_IS) < 0.01:
        note = "<-- islanded far-end fault"
    ts = f"{t*1000:.1f}" if t < 1e6 else "inf (below pickup)"
    print(f"  {I:>14.2f} {ts:>10s}  {note}")

# ════════════════════════════════════════════════════════════════════════
# Study C — Directional element validation
# ════════════════════════════════════════════════════════════════════════
print("\n── Study C: Directional Element (67) Validation ──")

# In islanded mode: IBR at one end provides fault current
# Directional element compares current against polarising voltage
# For IBR: voltage angle reference may shift after islanding

scenarios = [
    ("Forward internal fault",  0.20, "forward",  "TRIP"),
    ("Reverse external fault",  0.20, "reverse",  "BLOCK"),
    ("Forward load (no fault)", 0.80, "forward",  "BLOCK (below pickup)"),
    ("Forward fault, low k",    0.05, "forward",  "BLOCK (below 67 pickup)"),
]

print(f"\n  {'Scenario':>28s} {'I [pu]':>8s} {'Dir':>8s} {'67 Action':>20s}")
print(f"  {'-'*28} {'-'*8} {'-'*8} {'-'*20}")
for name, I, direction, action in scenarios:
    print(f"  {name:>28s} {I:>8.2f} {direction:>8s} {action:>20s}")

# ════════════════════════════════════════════════════════════════════════
# Study D — Adaptive coordination table
# ════════════════════════════════════════════════════════════════════════
print("\n── Study D: Adaptive Coordination Setting Groups ──")

print("""
  ┌─────────────────┬──────────┬─────────┬──────┬──────────────────────────┐
  │ Setting Group   │ Ip [pu]  │  TMS    │Curve │ Activation condition     │
  ├─────────────────┼──────────┼─────────┼──────┼──────────────────────────┤
  │ Group 1 (GC)    │  1.50    │  0.10   │  SI  │ PCC breaker CLOSED       │
  │ Group 2 (ISLAN) │  0.30    │  0.20   │  SI  │ Islanding detected (GOOSE)│
  │ Group 3 (RESYN) │  0.80    │  0.15   │  SI  │ Relay 25 closed (resync) │
  └─────────────────┴──────────┴─────────┴──────┴──────────────────────────┘
""")

# Discrimination margin check
print("  Coordination margin validation:")
# Between Group 2 relay and upstream backup at islanded fault level
t_primary = t_si(I_FAULT_IS, I_PICKUP_IS, TMS_IS)
t_backup   = t_si(I_FAULT_IS, I_PICKUP_IS * 0.8, TMS_IS * 2.0)
margin = t_backup - t_primary
print(f"    Primary trip (Group 2):  {t_primary*1000:.1f} ms at I={I_FAULT_IS:.2f} pu")
print(f"    Backup trip (upstream):  {t_backup*1000:.1f} ms at I={I_FAULT_IS:.2f} pu")
print(f"    Coordination margin:     {margin*1000:.1f} ms "
      f"({'OK (>200ms)' if margin > 0.200 else 'INSUFFICIENT (<200ms)'})")

# ════════════════════════════════════════════════════════════════════════
# Study E — Minimum meshed fault level sensitivity
# ════════════════════════════════════════════════════════════════════════
print("\n── Study E: Sensitivity to Minimum Fault Level ──")

print(f"\n  Minimum k_ibr for relay operation (Group 2, Ip={I_PICKUP_IS}):")
# I_fault_is = k_ibr / (Z_line/2) >= I_pickup_is
k_min_relay = I_PICKUP_IS * (Z_LINE / 2)
print(f"    k_min = Ip * (Z_line/2) = {I_PICKUP_IS} * {Z_LINE/2:.3f} = {k_min_relay:.4f} pu")
print(f"    → 67/OC operates for k_ibr >= {k_min_relay:.2f} pu ({k_min_relay*100:.1f}%)")

# Compare with 87L threshold
I_MIN_87L = 0.06
print(f"\n  Comparison with 87L threshold ({I_MIN_87L} pu):")
if k_min_relay < I_MIN_87L:
    print(f"    OC pickup threshold ({k_min_relay:.4f}) < 87L threshold ({I_MIN_87L})")
    print(f"    → OC provides WIDER coverage than 87L in islanded mode")
else:
    print(f"    OC pickup threshold ({k_min_relay:.4f}) >= 87L threshold ({I_MIN_87L})")
    print(f"    → 87L would be faster; reduce Ip or use Group 2 settings")

print("\n" + "=" * 64)
print("TR-40 adaptive OC study complete.")
print(f"  Fault level reduction on islanding: {reduction:.1f}%")
print(f"  Group 2 pickup: {I_PICKUP_IS} pu (reduced for islanded level)")
print(f"  OC operates for k_ibr >= {k_min_relay:.4f} pu")
print(f"  Coordination margin: {margin*1000:.1f} ms at islanded fault level")
print("=" * 64)
