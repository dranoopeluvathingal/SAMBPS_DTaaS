"""
run_ar_study.py
SAMBP TR-36: Auto-Reclosing Strategy for IBR Lines

Core tension:
  Arc deionisation requires dead time T_dead >= T_arc(I_fault).
  Memory polarisation expires at T_mem = 100 ms.
  IBR under-voltage protection trips IBR if V < V_thresh for T_uvt.

  T_dead is typically 300-500 ms (arc deionisation at 230 kV).
  T_dead >> T_mem → memory expired before reclose.
  Second trip (reclose onto permanent fault) CANNOT use memory-polarised distance.

  BUT: IBR reduces fault current → faster arc deionisation → shorter T_dead possible.
       This is the TR-36 design opportunity.

Arc deionisation model (ANSI/IEEE C37.04, adapted):
  T_arc = T_arc0 * (I_base / I_fault)^0.5   [simplified power law]
  T_arc0 = 400 ms at I_base = 10 kA (230 kV typical)
  For IBR: I_fault = I_SG_component + I_IBR = I_SG*(1 + k_ibr)... actually
           for 3PH fault, I_fault at relay = I_IBR = k_ibr * I_SG
  So T_arc_ibr = T_arc0 * (1/k_ibr)^0.5  [IBR-limited current only]

IBR under-voltage protection (grid code, typical):
  Ride-through: V >= 0.85 pu for unlimited time; V < 0.85 pu for T_uvt <= 625 ms
  IBR disconnects if V < 0.85 pu for > T_uvt = 625 ms (AEMO / IEC 61727)

System parameters:
  V_base = 230 kV
  I_SG_base = 10 kA  (synchronous source fault current)
  T_mem = 100 ms
  T_arc0 = 400 ms at I_base = 10 kA
  T_uvt = 625 ms (IBR ride-through limit)
  T_dead_min = max(T_arc, T_margin=50ms)
  T_dead_max = T_uvt - T_reclose_overhead = 625 - 50 = 575 ms
"""

import math

# ─────────────────────────────────────────────────────────────────
T_MEM    = 0.100   # memory polarisation hold [s]
T_ARC0   = 0.400   # arc deionisation at I_base [s]
I_BASE   = 10.0    # base fault current for arc model [kA]
T_UVT    = 0.625   # IBR ride-through limit (under-voltage) [s]
T_MARGIN = 0.050   # AR dead-time safety margin [s]
T_OVERHEAD = 0.050 # AR initiation + CB close overhead [s]
T_DEAD_MAX = T_UVT - T_OVERHEAD   # 575 ms


def t_arc(i_fault_ka):
    """Arc deionisation time [s] from simplified ANSI/IEEE C37.04 model.
    Higher fault current → more arc ionisation → longer deionisation.
    T_arc = T_arc0 * (I_fault / I_base)^0.5
    At I_base=10kA: T_arc=400ms (SG-level); at k=0.10 I=1kA: T_arc=126ms.
    IBR-limited fault current → SHORTER arc → SHORTER T_dead needed.
    """
    if i_fault_ka <= 0:
        return float("inf")
    return T_ARC0 * math.sqrt(i_fault_ka / I_BASE)


def t_dead(i_fault_ka):
    """Minimum safe dead time [s]: arc deionisation + margin."""
    return t_arc(i_fault_ka) + T_MARGIN


def ibr_fault_current(k_ibr, i_sg_ka=I_BASE):
    """IBR fault current seen by relay [kA]. IBR current-limited."""
    return k_ibr * i_sg_ka


# ─────────────────────────────────────────────────────────────────
def study_a_dead_time():
    """Arc deionisation and dead time vs k_ibr."""
    print("=" * 72)
    print("STUDY A — Arc deionisation and dead time vs k_ibr")
    print("=" * 72)
    print()
    print(f"  Arc model: T_arc = {T_ARC0*1e3:.0f}ms * sqrt(I_fault / {I_BASE:.0f}kA)")
    print(f"  T_dead = T_arc + {T_MARGIN*1e3:.0f}ms safety margin")
    print(f"  IBR ride-through limit: T_uvt = {T_UVT*1e3:.0f}ms")
    print(f"  Dead-time window: [T_dead_min, {T_DEAD_MAX*1e3:.0f}ms]")
    print()

    k_vals = [0.10, 0.15, 0.20, 0.30, 0.40, 0.50, 0.80, 1.00]
    print(f"  {'k_ibr':>7}  {'I_fault[kA]':>12}  {'T_arc[ms]':>10}  "
          f"{'T_dead[ms]':>11}  {'< T_uvt?':>9}  {'> T_mem?':>9}  Status")
    print("  " + "-" * 78)

    feasible_k = None
    for k in k_vals:
        i_f  = ibr_fault_current(k)
        ta   = t_arc(i_f)
        td   = t_dead(i_f)
        ok_uvt  = td <= T_DEAD_MAX
        gt_mem  = td > T_MEM
        if ok_uvt and feasible_k is None:
            feasible_k = k
        status = "OK" if ok_uvt else "TOO LONG (IBR disconnects)"
        flag   = " ***" if ok_uvt and gt_mem else ""
        print(f"  {k:>7.2f}  {i_f:>12.2f}  {ta*1e3:>10.1f}  "
              f"{td*1e3:>11.1f}  {'YES' if ok_uvt else 'NO':>9}  "
              f"{'YES' if gt_mem else 'no':>9}  {status}{flag}")

    print()
    print(f"  *** All feasible dead times exceed T_mem = {T_MEM*1e3:.0f}ms.")
    print(f"  Memory polarisation is ALWAYS expired before reclose.")
    print(f"  Second trip (reclose onto permanent fault) cannot use Zone 1 or Z2/POTT.")
    print()
    return feasible_k


# ─────────────────────────────────────────────────────────────────
def study_b_second_trip():
    """Protection function availability at second trip (post-dead-time)."""
    print("=" * 72)
    print("STUDY B — Protection function availability at second trip")
    print("=" * 72)
    print()
    print("  After dead time T_dead >> T_mem = 100 ms:")
    print("  Memory polarisation has expired → Z1 and Z2/POTT CANNOT trip.")
    print()

    k_vals   = [0.10, 0.15, 0.20]
    alphas   = [0.50, 0.90]

    print(f"  {'alpha':>7}  {'k_ibr':>7}  {'T_dead[ms]':>11}  "
          f"{'Z1 avail?':>10}  {'Z2/POTT?':>9}  "
          f"{'67N/67Q?':>9}  {'87L?':>5}  1st available")
    print("  " + "-" * 78)

    for alpha in alphas:
        for k in k_vals:
            i_f  = ibr_fault_current(k)
            td   = t_dead(i_f)
            mem_ok = td < T_MEM   # always False for feasible AR

            # Zone 1 and Z2/POTT require memory polarisation for IBR 3PH faults
            z1_avail  = mem_ok
            z2_avail  = mem_ok

            # 67Q/67N: operate on sequence currents — NO memory needed
            q67 = k >= 0.04

            # 87L: differential — NO memory needed
            l87 = k >= 0.06

            # Determine first available element
            if z1_avail:
                first = "Z1 (20ms)"
            elif l87:
                first = "87L (20ms)"
            elif q67:
                first = "67Q (30ms)"
            else:
                first = "NONE"

            print(f"  {alpha:>7.2f}  {k:>7.2f}  {td*1e3:>11.1f}  "
                  f"{'YES' if z1_avail else 'NO':>10}  "
                  f"{'YES' if z2_avail else 'NO':>9}  "
                  f"{'YES' if q67 else 'NO':>9}  "
                  f"{'Y' if l87 else '-':>5}  {first}")

    print()
    print("  Second-trip clearance relies on: 87L (primary) and 67Q/67N (backup).")
    print("  Neither requires memory polarisation → both available after any dead time.")
    print()


# ─────────────────────────────────────────────────────────────────
def study_c_ibr_ride_through():
    """IBR ride-through window and AR feasibility diagram."""
    print("=" * 72)
    print("STUDY C — IBR ride-through window and AR feasibility")
    print("=" * 72)
    print()

    # Timeline after fault inception:
    # t0   = fault inception
    # t1   = first trip  (20-32 ms)
    # t2   = breaker open (t1 + 50 ms CB opening time)
    # t3   = reclose     (t2 + T_dead)
    # IBR V < V_thresh from t_fault onset; if t3 - t0 > T_uvt → IBR disconnected

    T_FIRST_TRIP = 0.032   # POTT (worst case primary trip time)
    T_CB_OPEN    = 0.050   # CB opening time [s]
    T_V_START    = 0.000   # voltage depression starts at fault inception

    print(f"  Timeline:")
    print(f"    t0 = fault inception")
    print(f"    t1 = first trip   = {T_FIRST_TRIP*1e3:.0f} ms (Z1 or Z2/POTT)")
    print(f"    t2 = breaker open = t1 + {T_CB_OPEN*1e3:.0f} ms CB time = "
          f"{(T_FIRST_TRIP+T_CB_OPEN)*1e3:.0f} ms from t0")
    print(f"    t3 = reclose      = t2 + T_dead")
    print(f"    IBR under-voltage: V < 0.85 pu from t0 to t3 (line energised)")
    print(f"    If (t3 - t0) > T_uvt = {T_UVT*1e3:.0f} ms → IBR may disconnect")
    print()

    k_vals = [0.10, 0.15, 0.20, 0.30, 0.50]
    t_before_reclose = T_FIRST_TRIP + T_CB_OPEN

    print(f"  {'k_ibr':>7}  {'T_dead[ms]':>11}  {'t3-t0 [ms]':>11}  "
          f"{'< T_uvt?':>9}  {'IBR status':>15}  AR feasible?")
    print("  " + "-" * 72)

    for k in k_vals:
        i_f  = ibr_fault_current(k)
        td   = t_dead(i_f)
        t3   = t_before_reclose + td
        ok   = t3 <= T_UVT
        ibr_status = "Connected" if ok else "May disconnect"
        feasible   = "YES" if td <= T_DEAD_MAX else "NO"
        print(f"  {k:>7.2f}  {td*1e3:>11.1f}  {t3*1e3:>11.1f}  "
              f"{'YES' if ok else 'NO':>9}  {ibr_status:>15}  {feasible}")

    print()
    print(f"  All feasible k_ibr: t3 <= T_uvt → IBR remains connected through AR.")
    print(f"  However: IBR may activate low-voltage ride-through (LVRT) limiting.")
    print(f"  On reclose, IBR resumes full output within ~100 ms (typical ramp time).")
    print()


# ─────────────────────────────────────────────────────────────────
def study_d_singlephase_ar():
    """Single-phase vs three-phase AR for IBR lines."""
    print("=" * 72)
    print("STUDY D — Single-phase vs three-phase AR for IBR lines")
    print("=" * 72)
    print()

    criteria = [
        ("Transient fault clearance",
         "Both adequate",
         "3PH AR clears SLG transient fault"),
        ("Negative-seq during open phase",
         "1PH AR: V2 injected for T_dead",
         "IBR I2 injection during open phase (TR-32 concern)"),
        ("Arc energy (IBR-limited)",
         "IBR lower I: faster deion. for 1PH",
         "Asymmetric open phase → continuous I2 stress on IBR"),
        ("Synchronism check on reclose",
         "1PH: easier (2 phases live)",
         "3PH: requires synchrocheck or voltage check"),
        ("Reclose onto permanent SLG",
         "1PH AR re-energises faulty phase",
         "3PH AR trips all phases → cleaner isolation"),
        ("IBR I_min sensitivity",
         "3PH: I1=I2=k_ibr (balanced)",
         "SLG: I0 adds; I_relay may exceed I_min more easily"),
    ]

    print(f"  {'Criterion':>38}  {'1PH AR':>28}  {'3PH AR':>28}")
    print("  " + "-" * 98)
    for c, p1, p3 in criteria:
        print(f"  {c:>38}  {p1:>28}")
        print(f"  {'':>38}  vs  {p3}")
        print()

    print("  Recommendation for IBR lines:")
    print("    Use THREE-PHASE AR as the default.")
    print("    Rationale:")
    print("    1. IBR controllers are not designed for sustained negative-seq injection")
    print("       during the 300-500 ms single-phase open interval.")
    print("    2. 3PH AR avoids continuous I2 stress on IBR current control loops.")
    print("    3. If AR fails (permanent fault), 3PH tripping provides clean isolation.")
    print("    4. Synchrocheck on 3PH reclose is straightforward: check V_dead-bus")
    print("       vs V_live-bus angle/magnitude (IBR and SG both contribute live-side).")
    print()


# ─────────────────────────────────────────────────────────────────
def study_e_ar_scheme():
    """Complete AR scheme decision matrix."""
    print("=" * 72)
    print("STUDY E — AR scheme decision matrix")
    print("=" * 72)
    print()

    scenarios = [
        ("Transient SLG, k>=0.10",
         "Z1/87L (20ms)", "T_dead(k)", "87L (20ms)", "Return to service"),
        ("Transient 3PH, k>=0.10, a<=0.80",
         "Z1 (20ms)",     "T_dead(k)", "87L (20ms)", "Return to service"),
        ("Transient 3PH, k>=0.10, a>0.80",
         "Z2/POTT (32ms)","T_dead(k)", "87L (20ms)", "Return to service"),
        ("Permanent SLG, k>=0.10",
         "Z1/87L (20ms)", "T_dead(k)", "87L (20ms, 2nd)", "Lock out"),
        ("Permanent 3PH, k>=0.10",
         "Z1/POTT (20ms)","T_dead(k)", "87L or 67Q (20-30ms, 2nd)", "Lock out"),
        ("Any fault, k<0.06",
         "87L (20ms)",    "T_dead",   "N/A (IBR below I_min_87L)", "Manual restoration"),
    ]

    print(f"  {'Scenario':>40}  {'1st trip':>16}  {'Dead time':>10}  "
          f"{'2nd trip':>24}  {'Outcome':>20}")
    print("  " + "-" * 116)
    for s in scenarios:
        print(f"  {s[0]:>40}  {s[1]:>16}  {s[2]:>10}  {s[3]:>24}  {s[4]:>20}")

    print()
    # Calculate T_dead for representative k values
    print("  Dead-time settings by k_ibr:")
    for k in [0.10, 0.15, 0.20]:
        i_f = ibr_fault_current(k)
        td  = t_dead(i_f)
        print(f"    k_ibr={k:.2f}: T_dead = {td*1e3:.0f} ms  "
              f"(arc {t_arc(i_f)*1e3:.0f}ms + {T_MARGIN*1e3:.0f}ms margin)")

    print()
    print("  AR mode: 3-phase, single shot.")
    print("  Lock-out after one failed reclose (permanent fault identified by 2nd trip).")
    print("  Memory-independent functions (87L, 67Q/67N) confirmed as 2nd-trip path.")
    print()


# ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print()
    print("SAMBP TR-36: Auto-Reclosing Strategy for IBR Lines")
    print("=" * 72)
    print()

    feasible_k = study_a_dead_time()
    study_b_second_trip()
    study_c_ibr_ride_through()
    study_d_singlephase_ar()
    study_e_ar_scheme()

    print("=" * 72)
    print("TR-36 SUMMARY")
    print("=" * 72)
    print()
    print(f"  Arc deionisation time exceeds T_mem={T_MEM*1e3:.0f}ms for all k_ibr.")
    print(f"  Memory-polarised distance (Z1, Z2/POTT) UNAVAILABLE at second trip.")
    print(f"  Second-trip path: 87L (primary, 20ms) + 67Q/67N (backup, 30ms).")
    print(f"  AR dead time feasible for k_ibr >= {feasible_k:.2f} (IBR stays connected).")
    print(f"  Recommended: 3PH AR, single-shot, T_dead = T_arc(k_ibr) + 50ms.")
    print(f"  Synchrocheck required on reclose (IBR and SG both present on live side).")
    print()
    print("  TR-36 complete.")
