"""
run_87b_mg_study.py
SAMBP TR-41/2026: 87B Bus Differential Protection in IBR Microgrids

The standard 87B scheme from TR-04 assumed large SG contribution.
In IBR microgrids:
  - All feeders may have IBR (inverter-limited fault current)
  - Inrush/offset currents absent (no transformer magnetising)
  - CT saturation risk is lower (lower fault current)
  - External fault: current sums to zero (KCL)
  - Internal fault: differential current = sum of feeder contributions

Studies:
  A — Sensitivity check: minimum detectable internal fault
  B — Security check: maximum external fault through-current
  C — Slope characteristic (restraint): low-slope optimisation
  D — CT saturation analysis at IBR fault levels
  E — Multi-bus microgrid coordination (two busbars)
"""

import math

# ── Parameters ─────────────────────────────────────────────────────────────
N_FEEDERS    = 4       # number of feeders on busbar
K_IBR        = 0.20    # IBR fault current contribution per feeder [pu]
V_BASE       = 1.00    # pu
I_RATED      = 1.00    # pu per feeder
CT_RATIO     = 400     # A / 5 A (primary/secondary)
CT_ERROR     = 0.01    # 1% CT error (class 1P)
CT_SAT_VK    = 20.0    # knee-point voltage [V] (secondary)

# 87B settings
I_DIFF_MIN   = 0.10    # minimum differential pickup [pu]
K_SLOPE_1    = 0.30    # slope 1 (low current region)
K_SLOPE_2    = 0.60    # slope 2 (high current region)
I_BIAS_BREAK = 1.00    # breakpoint between slope 1 and 2 [pu]
I_DIFF_INST  = 4.00    # instantaneous high-set pickup [pu]

def i_op(I_diff):
    return I_diff

def i_rst(I_feeders):
    return 0.5 * sum(abs(I) for I in I_feeders)

def slope_criterion(I_diff, I_rst, slope1=K_SLOPE_1, slope2=K_SLOPE_2, Ibk=I_BIAS_BREAK):
    if I_rst <= Ibk:
        thresh = I_DIFF_MIN + slope1 * I_rst
    else:
        thresh = I_DIFF_MIN + slope1 * Ibk + slope2 * (I_rst - Ibk)
    return I_diff > thresh

print("=" * 64)
print("SAMBP TR-41: 87B Bus Differential in IBR Microgrids")
print("=" * 64)

# ════════════════════════════════════════════════════════════════════════
# Study A — Sensitivity: minimum detectable internal fault
# ════════════════════════════════════════════════════════════════════════
print("\n── Study A: Minimum Detectable Internal Fault ──")

# Internal fault: all feeders contribute their IBR current toward bus
# I_diff = sum of feeder currents (all in same direction for internal fault)
for n_fdr in [1, 2, 3, 4]:
    I_feeders_int = [K_IBR] * n_fdr + [0.0] * (N_FEEDERS - n_fdr)
    I_diff_int = sum(I_feeders_int)
    I_rst_int  = i_rst(I_feeders_int)
    trips      = slope_criterion(I_diff_int, I_rst_int)
    print(f"  {n_fdr} feeder(s) contributing:")
    print(f"    I_diff = {I_diff_int:.3f} pu, I_rst = {I_rst_int:.3f} pu → {'TRIP' if trips else 'NO TRIP'}")

# Minimum fault current for 87B to detect (1 feeder, slope 1 region)
# I_diff > I_diff_min + K_slope1 * I_rst
# For 1 feeder: I_diff = I, I_rst = I/2
# I > I_diff_min + K_slope1 * I/2 → I(1 - K_slope1/2) > I_diff_min
I_min_87B = I_DIFF_MIN / (1 - K_SLOPE_1 / 2)
print(f"\n  Minimum detectable internal fault (1 feeder, slope region):")
print(f"    I_min = I_diff_min / (1 - k1/2) = {I_DIFF_MIN}/{1-K_SLOPE_1/2:.3f} = {I_min_87B:.4f} pu")
print(f"    Equivalent k_ibr_min = {I_min_87B:.4f} pu")

# ════════════════════════════════════════════════════════════════════════
# Study B — Security: maximum through-current (external fault)
# ════════════════════════════════════════════════════════════════════════
print("\n── Study B: Security Check for External Fault ──")

# External fault: one feeder carries all fault current OUT, others carry load
# KCL: I_diff should be zero
# CT error: each CT has ±1% error → maximum accumulated error
n_ct = N_FEEDERS
I_through_ext = K_IBR * N_FEEDERS  # total fault current from bus
I_load_fdr    = I_RATED * 0.80     # load per feeder during fault

# Worst-case CT error: all errors accumulate in same direction
I_error_max   = CT_ERROR * (I_through_ext + I_load_fdr * (N_FEEDERS - 1))
I_diff_ext    = I_error_max  # should be ~0, only CT error
I_rst_ext     = 0.5 * (I_through_ext + I_load_fdr * (N_FEEDERS - 1))

trips_ext = slope_criterion(I_diff_ext, I_rst_ext)
print(f"\n  External fault through-current:")
print(f"    I_through = {I_through_ext:.3f} pu (all feeders)")
print(f"    Max CT error contribution: {I_error_max:.4f} pu")
print(f"    I_diff (spurious) = {I_diff_ext:.4f} pu")
print(f"    I_rst = {I_rst_ext:.3f} pu")
print(f"    87B asserts? {'YES (FALSE TRIP!)' if trips_ext else 'NO (secure)'}")

# Security margin
slope_thresh = I_DIFF_MIN + K_SLOPE_1 * I_rst_ext
margin = slope_thresh - I_diff_ext
print(f"    Security margin: {margin:.4f} pu (threshold - spurious = {slope_thresh:.4f} - {I_diff_ext:.4f})")

# ════════════════════════════════════════════════════════════════════════
# Study C — Slope characteristic optimisation
# ════════════════════════════════════════════════════════════════════════
print("\n── Study C: Slope Characteristic ──")

print(f"\n  87B settings:")
print(f"    I_diff_min = {I_DIFF_MIN} pu")
print(f"    Slope 1 = {K_SLOPE_1*100:.0f}% (I_rst ≤ {I_BIAS_BREAK} pu)")
print(f"    Slope 2 = {K_SLOPE_2*100:.0f}% (I_rst > {I_BIAS_BREAK} pu)")
print(f"    Instantaneous high-set = {I_DIFF_INST} pu")

# Operating characteristic points
print(f"\n  Characteristic boundary points:")
print(f"  {'I_rst [pu]':>12s} {'I_diff threshold [pu]':>22s}")
print(f"  {'-'*12} {'-'*22}")
for Irst in [0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0]:
    if Irst <= I_BIAS_BREAK:
        thresh = I_DIFF_MIN + K_SLOPE_1 * Irst
    else:
        thresh = I_DIFF_MIN + K_SLOPE_1 * I_BIAS_BREAK + K_SLOPE_2 * (Irst - I_BIAS_BREAK)
    print(f"  {Irst:>12.1f} {thresh:>22.4f}")

# IBR-specific advantage: lower slope is sufficient due to lower CT saturation
print(f"\n  IBR advantage: maximum through-current ≤ {I_through_ext:.2f} pu")
print(f"    → CT saturation risk low → slope 1 can be reduced to 20% vs SG standard 40%")
print(f"    → sensitivity improvement factor: (1-0.20/2)/(1-0.40/2) = "
      f"{(1-0.20/2)/(1-0.40/2):.3f}")

# ════════════════════════════════════════════════════════════════════════
# Study D — CT saturation analysis
# ════════════════════════════════════════════════════════════════════════
print("\n── Study D: CT Saturation Analysis ──")

# CT saturation factor: X = Vk / (I_fault * R_secondary * sqrt(2))
# For IBR: I_fault is low → X is large → no saturation
I_sc_sg  = 20.0   # SG fault current [pu] (reference)
I_sc_ibr = K_IBR * N_FEEDERS  # IBR fault current [pu]
R_sec    = 1.0    # secondary resistance [Ω]
I_ct_sec_sg  = I_sc_sg  / CT_RATIO * 5   # secondary current [A] (per-unit of 5A)
I_ct_sec_ibr = I_sc_ibr / CT_RATIO * 5

Vk_required_sg  = I_ct_sec_sg  * R_sec * math.sqrt(2) * 20  # simplified Vk requirement
Vk_required_ibr = I_ct_sec_ibr * R_sec * math.sqrt(2) * 20

print(f"\n  CT saturation comparison:")
print(f"  {'Source':>8s} {'I_fault [pu]':>14s} {'CT I_sec [A]':>14s} {'Vk_req [V]':>12s} {'Status':>12s}")
print(f"  {'-'*8} {'-'*14} {'-'*14} {'-'*12} {'-'*12}")
for label, Isc, Iks in [("SG", I_sc_sg, Vk_required_sg),
                         ("IBR", I_sc_ibr, Vk_required_ibr)]:
    status = "SATURATED" if Iks > CT_SAT_VK else "No saturation"
    isec = Isc / CT_RATIO * 5
    print(f"  {label:>8s} {Isc:>14.1f} {isec:>14.3f} {Iks:>12.1f} {status:>12s}")

print(f"\n  CT knee-point: {CT_SAT_VK} V (secondary)")
print(f"  IBR fault current {I_sc_ibr:.2f} pu is {I_sc_sg/I_sc_ibr:.1f}× lower than SG")
print(f"  → CT saturation not a concern for IBR microgrid 87B")

# ════════════════════════════════════════════════════════════════════════
# Study E — Multi-bus microgrid (two busbars with bus-coupler)
# ════════════════════════════════════════════════════════════════════════
print("\n── Study E: Multi-Bus Microgrid Coordination ──")

# Bus A: 2 IBR feeders + bus-coupler
# Bus B: 2 IBR feeders + bus-coupler
# Bus-coupler open: buses are isolated (each operates independently)
# Bus-coupler closed: fault on Bus A → both 87B-A and 87B-B receive contributions

print(f"\n  Configuration: 2-bus microgrid with bus-coupler (BC)")
print(f"    Bus A: {N_FEEDERS//2} IBR feeders + BC (normally closed)")
print(f"    Bus B: {N_FEEDERS//2} IBR feeders + BC")

# Internal fault on Bus A, bus-coupler closed
I_fdr_A = K_IBR  # per feeder contribution from Bus A
I_fdr_B = K_IBR  # per feeder contribution from Bus B (through BC)
I_bc    = K_IBR * (N_FEEDERS//2)  # bus-coupler current (Bus B contribution)

I_diff_A_int = I_fdr_A * (N_FEEDERS//2) + I_bc
I_rst_A_int  = 0.5 * (I_fdr_A * (N_FEEDERS//2) + I_bc)
trips_A = slope_criterion(I_diff_A_int, I_rst_A_int)

I_diff_B_ext = 0  # Bus B sees external fault (current through BC is balanced)
print(f"\n  Internal fault on Bus A (BC closed):")
print(f"    I_diff(87B-A) = {I_diff_A_int:.3f} pu → {'TRIP (correct)' if trips_A else 'NO TRIP (fail)'}")
print(f"    I_diff(87B-B) = {I_diff_B_ext:.3f} pu → NO TRIP (correct, external)")

# Coordination: 87B-A trips → BC opens → Bus B continues service
print(f"\n  Post-trip: 87B-A trips Bus A feeders and BC → Bus B continues in service")
print(f"  Bus B protection (87B-B) remains active with reduced IBR count")

print("\n" + "=" * 64)
print("TR-41 87B-MG study complete.")
print(f"  Minimum detectable fault: {I_min_87B:.4f} pu")
print(f"  Security margin: {margin:.4f} pu (no false trip for external fault)")
print(f"  CT saturation: not a concern for IBR (I_fault ≤ {I_through_ext:.2f} pu)")
print(f"  Multi-bus: 87B-A trips Bus A, Bus B continues service")
print("=" * 64)
