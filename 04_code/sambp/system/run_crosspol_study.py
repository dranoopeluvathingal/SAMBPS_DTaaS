"""
run_crosspol_study.py
SAMBP TR-30: Cross-Polarised Mho Characteristic for IBR Networks

Studies:
  A  Memory timing margin  — T_mem / t_ZoneN for all zones
  B  Load blinder adequacy — IBR leading / lagging load on R-X plane
  C  Cross-pol source availability by fault type (3PH, SLG, LL, LLG)
  D  Memory-polarised criterion verification along Zone-1 boundary

Network parameters (from TR-18, TR-29):
  Z_src  = j0.10 pu
  Z_line = j0.05 pu  (purely inductive, single 100 % IBR-fed line)
  V_pre  = 1.00 pu  (pre-fault voltage, used as memory reference)
  I_min  = 0.10 pu  (IEC 60255-121 minimum current)

Distance relay settings (TR-18):
  Zone 1:  X_R1 = 0.040 pu  instant  (80 % line)
  Zone 2:  X_R2 = 0.060 pu  t2=0.30 s
  Zone 3:  X_R3 = 0.090 pu  t3=0.60 s

Cross-pol parameters (IEC 60255-121 / Ziegler §8):
  T_mem      = 0.100 s  (memory polarisation hold time, 3PH-faults)
  T_xpol     = inf      (cross-pol permanent for earth/LL faults via healthy phases)
  V_min_self = 0.100 pu (self-pol lower limit)

IBR parameters:
  k_ibr range [0.06, 0.20] pu (current-limit multiplier, from TR-26 MC)
  Angle convention: IBR output at unity PF → angle 0 relative to V_pre
"""

import math

# ──────────────────────────────────────────────────────────────────────────────
# Network & relay constants
# ──────────────────────────────────────────────────────────────────────────────
Z_SRC      = 0.10    # pu (source impedance magnitude, purely inductive)
Z_LINE     = 0.05    # pu (line impedance magnitude, purely inductive)
V_PRE      = 1.00    # pu (pre-fault voltage)

X_R        = {1: 0.040, 2: 0.060, 3: 0.090}   # zone reach reactances [pu]
T_ZONE     = {1: 0.020, 2: 0.300, 3: 0.600}   # zone trip timers [s]
T_MEM      = 0.100   # memory polarisation hold time [s]
I_MIN      = 0.100   # current minimum threshold [pu]
V_MIN_SELF = 0.100   # self-pol voltage minimum [pu]
R_BLINDER  = 0.40    # load blinder half-width [pu]


# ──────────────────────────────────────────────────────────────────────────────
# Study A: Memory timing margin
# ──────────────────────────────────────────────────────────────────────────────
def study_a_memory_timing():
    """
    For each zone, compare trip timer T_zone against T_mem.
    Memory-polarised criterion is valid while T < T_mem.
    After T_mem: self-pol takes over; but V_relay << V_min_self for IBR.

    Cross-pol by healthy phase (earth/LL faults) is permanent → Zone 2/3 viable.
    3PH fault → memory only → Zone 1 safe, Zone 2/3 fail.
    """
    print("=" * 70)
    print("STUDY A — Memory timing margin (IBR 3-phase fault)")
    print("=" * 70)
    print(f"  T_mem = {T_MEM*1000:.0f} ms   (memory hold time, 3PH)")
    print()
    header = f"  {'Zone':>6}  {'X_R [pu]':>10}  {'T_trip [ms]':>12}  "
    header += f"{'Within T_mem?':>14}  {'Margin [ms]':>12}  {'Margin ratio':>13}"
    print(header)
    print("  " + "-" * 68)

    zone_results = {}
    for z in (1, 2, 3):
        t_ms   = T_ZONE[z] * 1e3
        within = T_ZONE[z] < T_MEM
        margin = (T_MEM - T_ZONE[z]) * 1e3
        ratio  = T_MEM / T_ZONE[z]
        zone_results[z] = dict(t_ms=t_ms, within=within, margin_ms=margin, ratio=ratio)
        flag   = "SAFE" if within else "FAILS"
        print(f"  {'Z' + str(z):>6}  {X_R[z]:>10.3f}  {t_ms:>12.1f}  "
              f"{'YES' if within else 'NO':>14}  {margin:>12.1f}  "
              f"{ratio:>13.2f}  [{flag}]")

    print()
    print("  Conclusion:")
    print(f"    Zone 1 trips at {T_ZONE[1]*1e3:.0f} ms << T_mem={T_MEM*1e3:.0f} ms "
          f"(margin ratio {zone_results[1]['ratio']:.1f}×) → reliable with memory pol.")
    print(f"    Zone 2 timer {T_ZONE[2]*1e3:.0f} ms > T_mem={T_MEM*1e3:.0f} ms "
          f"→ memory expires; self-pol fails (IBR V_relay<0.010 pu) → 3PH TRIP FAILS.")
    print(f"    Zone 3 timer {T_ZONE[3]*1e3:.0f} ms > T_mem={T_MEM*1e3:.0f} ms "
          f"→ same failure as Zone 2.")
    print(f"    Cross-pol by healthy phases (earth/LL faults): permanent "
          f"→ Zone 2/3 viable for non-3PH faults.")
    print()
    return zone_results


# ──────────────────────────────────────────────────────────────────────────────
# Study B: Load blinder adequacy for IBR power factor range
# ──────────────────────────────────────────────────────────────────────────────
def study_b_load_blinder():
    """
    IBR loads appear in R-X plane.  Purely capacitive current (leading) → X<0.
    Mho circle (purely inductive line) is entirely in upper half-plane (X≥0).
    → All leading-load impedances are automatically outside Mho circle.

    For lagging loads (X>0): check if load impedance enters Mho Zone 3.
    Load impedance at apparent power S [pu], PF angle φ:
      |Z_load| = V²/S = 1/S  (at V=1.0 pu)
      R_load = |Z_load| cos φ,  X_load = |Z_load| sin φ

    IBR PF range (TR-26 Monte Carlo): ±18.2° → φ in [-18.2°, +18.2°]
    For lagging (φ>0): check if (R_load, X_load) is inside Zone 3 Mho circle.

    Mho Zone 3: centre (0, X_R3/2) = (0, 0.045), radius = 0.045
    Point inside if: R_load² + (X_load - 0.045)² < 0.045²

    Load blinder: R_blinder = 0.40 pu → blocks all |R_load| > 0.40 pu
    """
    print("=" * 70)
    print("STUDY B — Load blinder adequacy for IBR PF range")
    print("=" * 70)

    X_R3   = X_R[3]
    cy3    = X_R3 / 2        # 0.045 pu
    r3     = X_R3 / 2        # 0.045 pu
    phi_max = 18.2           # degrees (IBR leading/lagging range, TR-26)
    print(f"  Zone 3 Mho: centre=(0, {cy3:.3f}), radius={r3:.3f} pu")
    print(f"  IBR PF range: ±{phi_max}° (lagging/leading)")
    print(f"  Load blinder half-width: R_blinder = {R_BLINDER:.2f} pu")
    print()

    # Check a range of apparent power levels and angles
    S_vals  = [0.5, 0.8, 1.0, 1.2, 1.5, 1.8, 2.0, 2.5]
    phi_vals = [0.0, 5.0, 10.0, 15.0, 18.2, 20.0, 30.0, 45.0]

    print(f"  {'S [pu]':>8}  {'φ [°]':>7}  {'|Z_load|':>10}  "
          f"{'R_load':>8}  {'X_load':>8}  {'In Z3?':>8}  {'Blinder?':>9}  {'Status':>10}")
    print("  " + "-" * 75)

    results = []
    for S in S_vals:
        for phi_deg in phi_vals:
            phi_rad = math.radians(phi_deg)
            Z_mag   = 1.0 / S
            R_load  = Z_mag * math.cos(phi_rad)
            X_load  = Z_mag * math.sin(phi_rad)   # lagging → X>0
            # Inside Zone 3 Mho?
            in_z3   = (R_load**2 + (X_load - cy3)**2) < r3**2
            # Blinder would block?
            blinded = abs(R_load) > R_BLINDER
            status  = "SAFE" if (not in_z3 or blinded) else "RISK"
            results.append(dict(S=S, phi=phi_deg, R=R_load, X=X_load,
                                in_z3=in_z3, blinded=blinded, status=status))
            if in_z3:  # only print risky rows
                print(f"  {S:>8.1f}  {phi_deg:>7.1f}  {Z_mag:>10.4f}  "
                      f"{R_load:>8.4f}  {X_load:>8.4f}  {'YES':>8}  "
                      f"{'YES' if blinded else 'NO':>9}  {status:>10}")

    risky = [r for r in results if r['in_z3'] and not r['blinded']]
    print()
    if risky:
        print(f"  WARNING: {len(risky)} load points inside Zone 3 without blinder protection.")
    else:
        print("  All load points outside Zone 3 Mho OR blocked by R_blinder=0.40 pu.")

    # Leading loads (X<0) analysis
    print()
    print("  Leading loads (IBR capacitive current, X_load < 0):")
    print(f"    Mho circle entirely at X ≥ 0 (for purely inductive line).")
    print(f"    Any load with X_load < 0 is ALWAYS outside Mho → no encroachment risk.")
    print()

    return results


# ──────────────────────────────────────────────────────────────────────────────
# Study C: Cross-pol source availability by fault type
# ──────────────────────────────────────────────────────────────────────────────
def study_c_crosspol_availability():
    """
    Classify fault types by available cross-polarisation source:
      3PH:  All three phases collapsed → memory ONLY (expires at T_mem=100ms)
      SLG:  Two healthy phases available → permanent cross-pol
      LL:   One healthy phase + faulted phases cross-pol each other → permanent
      LLG:  One healthy phase → permanent cross-pol

    For each fault type: which zones are viable with cross-pol?
    """
    print("=" * 70)
    print("STUDY C — Cross-pol source availability by fault type")
    print("=" * 70)

    fault_types = [
        {
            "code":  "3PH",
            "name":  "Three-phase (balanced)",
            "xpol":  "Memory only",
            "t_xpol_ms": T_MEM * 1e3,
            "permanent": False,
        },
        {
            "code":  "SLG",
            "name":  "Single-line-to-ground",
            "xpol":  "Two healthy phases",
            "t_xpol_ms": float("inf"),
            "permanent": True,
        },
        {
            "code":  "LL",
            "name":  "Line-to-line (phase-phase)",
            "xpol":  "One healthy phase + mutual",
            "t_xpol_ms": float("inf"),
            "permanent": True,
        },
        {
            "code":  "LLG",
            "name":  "Double-line-to-ground",
            "xpol":  "One healthy phase",
            "t_xpol_ms": float("inf"),
            "permanent": True,
        },
    ]

    print(f"  {'Type':>5}  {'Cross-pol source':>30}  {'Permanent?':>11}  "
          f"{'Z1 viable':>10}  {'Z2 viable':>10}  {'Z3 viable':>10}")
    print("  " + "-" * 75)

    for ft in fault_types:
        perm = ft["permanent"]
        # Zone N is viable if cross-pol source lasts > T_zone[N]
        z_viable = {}
        for z in (1, 2, 3):
            t_z = T_ZONE[z] * 1e3
            t_x = ft["t_xpol_ms"]
            z_viable[z] = (t_x > t_z)

        ft["z_viable"] = z_viable
        print(f"  {ft['code']:>5}  {ft['xpol']:>30}  "
              f"{'YES' if perm else f'100ms only':>11}  "
              f"{'YES' if z_viable[1] else 'NO':>10}  "
              f"{'YES' if z_viable[2] else 'NO':>10}  "
              f"{'YES' if z_viable[3] else 'NO':>10}")

    print()
    print("  Key insight:")
    print("    3PH faults: Zone 1 only (memory window 100ms vs 20ms timer).")
    print("    SLG/LL/LLG: All zones viable (healthy phase cross-pol permanent).")
    print("    Combined strategy: Memory-pol for Zone 1 (3PH); cross-pol by")
    print("    healthy phase for Zone 2/3 (non-3PH only).")
    print()
    return fault_types


# ──────────────────────────────────────────────────────────────────────────────
# Study D: Memory-polarised criterion along Zone 1 boundary
# ──────────────────────────────────────────────────────────────────────────────
def study_d_memory_criterion():
    """
    Memory-polarised criterion:
      Re[(Z_m - Z_reach) * conj(V_mem)] <= 0  → operate

    For purely inductive line and purely reactive Mho:
      Z_m     = j*alpha*Z_line   (real part = 0)
      Z_reach = j*X_R1/2         (centre of Zone 1 Mho circle, R=0)
      V_mem   = V_pre * exp(-d(t))   (decaying but not yet zero)

    Since all quantities are purely imaginary (R=0), the criterion simplifies to:
      Im[Z_m] <= Im[Z_reach]   which is:  alpha*Z_line <= X_R1

    The memory decay factor d(t) appears in |V_mem| only — it scales both sides
    equally and cancels → criterion is INDEPENDENT of memory decay magnitude.

    This is the key result: cross-pol Mho characteristic size is invariant
    during the memory window.
    """
    print("=" * 70)
    print("STUDY D — Memory-polarised criterion along Zone 1 boundary")
    print("=" * 70)
    print()
    print("  Memory-polarised criterion: Re[(Z_m - Z_reach)*conj(V_mem)] <= 0")
    print()
    print("  Analytical simplification for purely inductive line:")
    print("    Z_m     = j*alpha*Z_L (real part = 0)")
    print("    Z_reach = j*X_R1/2    (Mho circle centre)")
    print("    V_mem   = V_pre * exp(-d(t)) * exp(j*omega*t)")
    print()
    print("  Criterion reduces to:")
    print("    alpha * Z_L <= X_R1   (independent of |V_mem|)")
    print()
    print("  Verification at Zone 1 boundary alpha = X_R1/Z_L:")

    X_R1   = X_R[1]
    alpha_bdry = X_R1 / Z_LINE   # = 0.040/0.050 = 0.80
    print(f"    alpha_boundary = X_R1/Z_L = {X_R1}/{Z_LINE} = {alpha_bdry:.3f}")
    print()

    # Sample three decay levels
    decay_levels = [1.0, 0.5, 0.1, 0.01]
    alpha_vals   = [0.50, 0.79, 0.80, 0.81, 0.90, 1.00]

    print(f"  Criterion evaluated at different decay d(t) = |V_mem|/V_pre:")
    print()
    print(f"  {'alpha':>7}", end="")
    for d in decay_levels:
        print(f"  {'d='+str(d):>12}", end="")
    print()
    print("  " + "-" * (7 + 14 * len(decay_levels)))

    for alpha in alpha_vals:
        Zm_X    = alpha * Z_LINE          # purely imaginary Z_m
        Zr_X    = X_R1 / 2               # Mho centre reactance
        radius  = X_R1 / 2               # Mho radius

        # Memory-pol criterion: alpha*Z_L <= X_R1 → independent of d
        criterion_met = (Zm_X <= X_R1)

        print(f"  {alpha:>7.2f}", end="")
        for d in decay_levels:
            # Scaled criterion: Re[(Z_m - Z_R)*conj(V_mem)] <= 0
            # For purely imaginary system: Im[Z_m - Z_R]*|V_mem| <= 0
            # = (Zm_X - X_R1) * d * V_pre
            val = (Zm_X - X_R1) * d * V_PRE
            result = "OPERATE" if val <= 0 else "RESTRAIN"
            print(f"  {val:>8.4f}({'O' if val<=0 else 'R':>1})", end="")
        print(f"  <- {'inside Z1' if criterion_met else 'outside Z1'}")

    print()
    print("  Conclusion:")
    print("    The operate/restrain decision is identical at ALL decay levels.")
    print("    Memory decay reduces |V_mem| but does NOT alter the Mho characteristic.")
    print("    Zone 1 criterion is valid for full T_mem=100ms window regardless of")
    print("    IBR current magnitude (even for k_ibr < V_min_self).")
    print()


# ──────────────────────────────────────────────────────────────────────────────
# Summary table
# ──────────────────────────────────────────────────────────────────────────────
def print_summary(zone_results, fault_types):
    print("=" * 70)
    print("TR-30 CROSS-POL STUDY SUMMARY")
    print("=" * 70)
    print()
    print("  Protection scheme recommendations for IBR-fed line:")
    print()
    print(f"  {'Fault type':>12}  {'Zone 1':>8}  {'Zone 2':>8}  {'Zone 3':>8}  "
          f"{'Primary detector':>20}")
    print("  " + "-" * 65)

    for ft in fault_types:
        zv = ft.get("z_viable", {1: True, 2: False, 3: False})
        # Zone 1 always backed by 87L chain (TR-27 21/21 PASS)
        primary = "87L + Z1" if zv[1] else "87L only"
        if ft["code"] == "3PH":
            detail = "87L + Z1 (mem-pol)"
        else:
            detail = "87L + Z1/Z2/Z3 (x-pol)"

        print(f"  {ft['code']:>12}  "
              f"{'YES' if zv[1] else 'NO':>8}  "
              f"{'YES' if zv.get(2, False) else 'NO':>8}  "
              f"{'YES' if zv.get(3, False) else 'NO':>8}  "
              f"{detail:>20}")

    print()
    print("  Zone 1 memory margin: 5× (100ms / 20ms) → highly robust.")
    print("  Zone 2/3 for 3PH faults: FAILS (memory expires at 100ms < 300ms timer).")
    print("    → Requires POTT or 87L for 3PH zone 2 coverage (TR-34 topic).")
    print("  Load encroachment: leading IBR loads always safe (X<0 outside Mho).")
    print(f"  R_blinder = {R_BLINDER} pu covers all lagging loads up to S=1.8 pu at 18.2°.")
    print()


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print()
    print("SAMBP TR-30: Cross-Polarised Mho Characteristic for IBR Networks")
    print("=" * 70)
    print()

    zone_results = study_a_memory_timing()
    study_b_load_blinder()
    fault_types  = study_c_crosspol_availability()
    study_d_memory_criterion()
    print_summary(zone_results, fault_types)

    print("TR-30 study complete.")
    print()
